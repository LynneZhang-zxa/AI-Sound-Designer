"""One test pass per selected checkpoint. Persist predictions before reporting."""
import argparse
import csv
import json
import time
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import DataLoader
from dataset import LogMelDataset
from dsp_baseline import DSPBaseline
from generate_dataset import ROOT, sha256
from features import log_mel
from inspect_dataset import read_audio
from metrics import NAMES, score, to_normalized, to_physical
from model import ParameterCNN


def load_model(folder):
    checkpoint=torch.load(folder/'best.pt',map_location='cpu',weights_only=True)
    model=ParameterCNN();model.load_state_dict(checkpoint['state_dict']);model.eval()
    return model


def predict(model,loader):
    predictions=[]
    with torch.inference_mode():
        for x,_unused_y in loader: predictions.append(model(x).numpy())
    return np.concatenate(predictions)


def latency(model,validation,directory,cfg):
    x=validation[0][0][None]
    with torch.inference_mode():
        for _ in range(cfg['latency_warmups']): model(x)
        elapsed=[]
        for _ in range(cfg['latency_repeats']):
            start=time.perf_counter_ns();model(x);elapsed.append((time.perf_counter_ns()-start)/1e6)
    return {'device':'cpu','torch_threads':cfg['torch_threads'],'batch_size':1,'warmups':cfg['latency_warmups'],
            'repeats':len(elapsed),'mean_ms':float(np.mean(elapsed)),'median_ms':float(np.median(elapsed)),
            'p95_ms':float(np.percentile(elapsed,95)),'minimum_ms':float(np.min(elapsed)),
            'scope':'CNN forward only on a preprocessed validation example; excludes WAV I/O, log-mel extraction and preprocessing; offline timing, no real-time claim'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=ROOT/'ml/data/experiment_3000');parser.add_argument('--run',type=Path,default=ROOT/'ml/runs/first_experiment');args=parser.parse_args()
    directory,run=args.data.resolve(),args.run.resolve(); record=json.loads((run/'run.json').read_text());cfg=record['training_config']
    torch.set_num_threads(cfg['torch_threads']);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    if sha256(directory/'data_audit.json')!=record['dataset_audit_sha256'] or sha256(directory/'preprocessing.json')!=record['preprocessing_sha256']:
        raise ValueError('Dataset/preprocessing changed after training')
    models={name:load_model(run/name) for name in ('cnn','shuffled')}
    baseline=json.loads((run/'baselines.json').read_text())
    dsp=DSPBaseline();dsp.tables=[(np.array(t['proxy']),np.array(t['physical_target'])) for t in baseline['dsp']['tables']]
    spec=json.loads((directory/'parameter_spec.json').read_text())
    validation=LogMelDataset(directory,'validation')
    timings={name:latency(model,validation,directory,cfg) for name,model in models.items()}
    validation_predictions={name:predict(model,DataLoader(validation,batch_size=cfg['batch_size'])) for name,model in models.items()}
    vtruth=np.load(directory/'validation_targets.npy');vraw=np.load(directory/'validation_physical.npy')
    validation_scores={name:score(pred,vtruth,vraw,spec) for name,pred in validation_predictions.items()}
    validation_scores['training_mean']=score(np.tile(baseline['training_mean_normalized'],(len(vtruth),1)),vtruth,vraw,spec)
    validation_scores['dsp']=score(to_normalized(dsp.predict(np.load(directory/'validation_dsp.npy')),spec),vtruth,vraw,spec)
    # Exclusive marker prevents rerunning test inference after results are visible.
    marker=run/'test_evaluation_started.json'
    with marker.open('x') as stream:
        json.dump({'test_inference_passes_per_checkpoint':1,'checkpoints':{name:sha256(run/name/'best.pt') for name in models}},stream,indent=2)
    test=LogMelDataset(directory,'test');loader=DataLoader(test,batch_size=cfg['batch_size'],shuffle=False)
    predictions={name:predict(model,loader) for name,model in models.items()}
    truth=np.load(directory/'test_targets.npy');raw=np.load(directory/'test_physical.npy')
    predictions['training_mean']=np.tile(baseline['training_mean_normalized'],(len(truth),1))
    predictions['dsp']=to_normalized(dsp.predict(np.load(directory/'test_dsp.npy')),spec)
    np.savez(run/'test_predictions.npz',ground_truth_normalized=truth,ground_truth_physical=raw,**predictions)
    scores={name:score(pred,truth,raw,spec) for name,pred in predictions.items()}
    ids=json.loads((directory/'test_ids.json').read_text())
    with (run/'test_predictions.csv').open('w',newline='') as stream:
        columns=['id','method']+[f'{prefix}_{target}' for prefix in ('true_normalized','pred_normalized','true_physical','pred_physical') for target in NAMES]
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        for method,pred in predictions.items():
            physical=to_physical(pred,spec)
            for i,identifier in enumerate(ids):
                row={'id':identifier,'method':method}
                for j,target in enumerate(NAMES):
                    row.update({f'true_normalized_{target}':float(truth[i,j]),f'pred_normalized_{target}':float(pred[i,j]),
                                f'true_physical_{target}':float(raw[i,j]),f'pred_physical_{target}':float(physical[i,j])})
                writer.writerow(row)
    # Grouping uses reporting sidecars only, AFTER the sole test inference pass.
    manifest=json.loads((directory/'rendered_manifest.json').read_text())
    by_id={r['id']:r for r in manifest['examples']}
    groups={identifier:by_id[identifier].get('evaluation_group','fixed_pitch') for identifier in ids}
    subgroup_scores={}
    for group in sorted(set(groups.values())):
        mask=np.array([groups[identifier]==group for identifier in ids])
        subgroup_scores[group]={'examples':int(mask.sum()),'methods':{
            name:score(pred[mask],truth[mask],raw[mask],spec) for name,pred in predictions.items()}}
    (run/'test_groups.json').write_text(json.dumps(groups,indent=2)+'\n')
    ratio=scores['shuffled']['normalized_mse']/scores['cnn']['normalized_mse']
    results={'test':scores,'test_groups':subgroup_scores,'validation':validation_scores,'offline_latency':timings,
             'shuffled_label_sanity':{'test_mse_ratio_shuffled_over_cnn':ratio,'expected_direction_observed':ratio>1,
                                      'interpretation':'Fixed control; not a main-model candidate. No metric-dependent retraining.'},
             'test_evaluation_count_per_checkpoint':1,'run':record,
             'physical_csv_units':{'cutoff':'Hz','attack':'seconds','release':'seconds'},'reported_metric_units':{'cutoff':'Hz','attack':'ms','release':'ms'}}
    (run/'results.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'test':scores,'shuffled_label_sanity':results['shuffled_label_sanity'],'offline_latency':timings},indent=2),flush=True)
    print('STOP: first fixed experiment evaluated; no model/hyperparameter changes after test.',flush=True)


if __name__=='__main__': main()
