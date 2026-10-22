"""Measure the fixed hybrid on validation only. No test files or test inference."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import DataLoader
from analyze_wav import OfflineAnalyzer, combine
from dataset import LogMelDataset
from generate_dataset import ROOT, sha256
from metrics import score, to_normalized


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,default=ROOT/'ml/runs/pitch_velocity')
    parser.add_argument('--output',type=Path,default=ROOT/'ml/runs/hybrid_validation')
    args=parser.parse_args();run=args.run.resolve();output=args.output.resolve()
    if not output.is_relative_to(ROOT): raise ValueError('Output must remain in canonical repository')
    if output.exists(): raise FileExistsError(output)
    torch.set_num_threads(4)
    analyzer=OfflineAnalyzer(run)
    record=json.loads((run/'run.json').read_text());data=Path(record['dataset_directory'])
    validation=LogMelDataset(data,'validation')
    predictions=[]
    with torch.inference_mode():
        for x,_ in DataLoader(validation,batch_size=32,shuffle=False): predictions.append(analyzer.model(x).numpy())
    cnn=np.concatenate(predictions)
    dsp=to_normalized(analyzer.dsp.predict(np.load(data/'validation_dsp.npy')),analyzer.spec)
    truth=np.load(data/'validation_targets.npy');physical=np.load(data/'validation_physical.npy')
    predictions={'cnn':cnn,'dsp':dsp,'hybrid':combine(cnn,dsp)}
    baseline=json.loads((run/'baselines.json').read_text())
    predictions['training_mean']=np.tile(baseline['training_mean_normalized'],(len(truth),1))
    scores={name:score(p,truth,physical,analyzer.spec) for name,p in predictions.items()}
    output.mkdir(parents=True,exist_ok=False)
    np.savez(output/'validation_predictions.npz',ground_truth_normalized=truth,ground_truth_physical=physical,**predictions)
    (output/'validation_ids.json').write_text((data/'validation_ids.json').read_text())
    result={'split':'validation','examples':len(truth),'policy':'CNN cutoff, DSP attack/release; fixed before validation',
            'test_data_opened':False,'training_or_calibration_performed':False,'metrics':scores,
            'provenance':analyzer.provenance,'analyzer_source_sha256':sha256(ROOT/'ml/analyze_wav.py')}
    (output/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    lines=['# Offline hybrid estimator — validation results','','Fixed policy: CNN cutoff; calibrated DSP attack and release. No retraining, new calibration, or test-set access.','',
           '| Method | Cutoff MAE / RMSE (Hz) | Attack MAE / RMSE (ms) | Release MAE / RMSE (ms) | Normalized MSE |',
           '| --- | ---: | ---: | ---: | ---: |']
    for name,m in scores.items():
        values=[' / '.join(format(m['parameters'][p][k],'.12g') for k in ['mae','rmse']) for p in ['cutoff','attack','release']]
        lines.append('| '+name+' | '+' | '.join(values)+f" | {m['normalized_mse']:.12g} |")
    lines+=['','All 300 validation examples are included. These examples were already used for checkpoint selection; these are development results, not a fresh unbiased generalization estimate. The component choice was motivated by previously reported component performance. No new held-out test claim is made.',
            '', 'Full precision metrics and per-example predictions: `ml/runs/hybrid_validation/`. Existing test results and evaluation markers were left untouched.']
    (ROOT/'ml/HYBRID_VALIDATION_RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(scores,indent=2))


if __name__=='__main__': main()
