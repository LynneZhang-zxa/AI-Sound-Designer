"""One fixed configuration, two label conditions. Never opens the test split."""
import argparse
import hashlib
import json
import platform
import random
import time
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import DataLoader
from dataset import LogMelDataset
from dsp_baseline import DSPBaseline
from generate_dataset import ROOT, provenance, sha256
from model import ParameterCNN


def fit_baselines(directory,run):
    labels=np.load(directory/'train_targets.npy')
    model=DSPBaseline().fit(np.load(directory/'train_dsp.npy'),np.load(directory/'train_physical.npy'))
    artifact={'training_mean_normalized':labels.astype(np.float64).mean(axis=0).tolist(),
              'training_ids_sha256':sha256(directory/'train_ids.json'), 'training_count':len(labels),
              'dsp':model.serializable(), 'fit_split':'train'}
    (run/'baselines.json').write_text(json.dumps(artifact,indent=2)+'\n')


def train_condition(directory,run,cfg,shuffled):
    name='shuffled' if shuffled else 'cnn'; folder=run/name
    folder.mkdir(exist_ok=False)
    random.seed(cfg['seed']); np.random.seed(cfg['seed']); torch.manual_seed(cfg['seed'])
    permutation=None
    if shuffled:
        permutation=np.random.default_rng(cfg['shuffled_label_seed']).permutation(len(np.load(directory/'train_targets.npy')))
        np.save(folder/'training_label_permutation.npy',permutation)
    training=LogMelDataset(directory,'train',permutation)
    validation=LogMelDataset(directory,'validation')
    generator=torch.Generator().manual_seed(cfg['seed'])
    loader=DataLoader(training,batch_size=cfg['batch_size'],shuffle=True,generator=generator,num_workers=0)
    valid_loader=DataLoader(validation,batch_size=cfg['batch_size'],shuffle=False,num_workers=0)
    model=ParameterCNN()
    initial_hash=hashlib.sha256(b''.join(v.detach().numpy().tobytes() for v in model.state_dict().values())).hexdigest()
    optimizer=torch.optim.Adam(model.parameters(),lr=cfg['learning_rate'])
    loss_fn=torch.nn.MSELoss(); best=float('inf'); best_epoch=0; bad=0; history=[]; started=time.perf_counter()
    for epoch in range(1,cfg['max_epochs']+1):
        before=time.perf_counter(); model.train(); total=0.; n=0
        for x,y in loader:
            optimizer.zero_grad(set_to_none=True); predicted=model(x); loss=loss_fn(predicted,y)
            loss.backward(); optimizer.step(); total+=loss.item()*len(x); n+=len(x)
        model.eval(); val=0.; vn=0
        with torch.inference_mode():
            for x,y in valid_loader:
                val+=loss_fn(model(x),y).item()*len(x); vn+=len(x)
        entry={'epoch':epoch,'train_normalized_mse':total/n,'validation_normalized_mse':val/vn,'seconds':time.perf_counter()-before}
        history.append(entry)
        print(name,json.dumps(entry),flush=True)
        if entry['validation_normalized_mse']<best:
            best=entry['validation_normalized_mse'];best_epoch=epoch;bad=0
            torch.save({'state_dict':model.state_dict(),'epoch':epoch,'validation_normalized_mse':best,'config':cfg,'shuffled_labels':shuffled},folder/'best.pt')
        else: bad+=1
        (folder/'history.json').write_text(json.dumps(history,indent=2)+'\n')
        if bad>=cfg['early_stopping_patience']: break
    summary={'condition':name,'epochs_completed':len(history),'best_epoch':best_epoch,'best_validation_normalized_mse':best,
             'training_seconds':time.perf_counter()-started,'trainable_parameters':sum(p.numel() for p in model.parameters()),
             'initial_weights_sha256':initial_hash,'checkpoint_sha256':sha256(folder/'best.pt'),
             'shuffle_seed':cfg['shuffled_label_seed'] if shuffled else None,'validation_labels_shuffled':False,'test_split_loaded':False}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=ROOT/'ml/data/experiment_3000');parser.add_argument('--run',type=Path,default=ROOT/'ml/runs/first_experiment');args=parser.parse_args()
    directory,run=args.data.resolve(),args.run.resolve()
    if not run.is_relative_to(ROOT): raise ValueError('Run must remain in canonical repository')
    cfg=json.loads((ROOT/'ml/training_config.json').read_text())
    torch.set_num_threads(cfg['torch_threads']);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    run.mkdir(parents=True,exist_ok=False)
    audit=json.loads((directory/'data_audit.json').read_text())
    if audit['status']!='PASS': raise ValueError('Dataset audit must pass')
    record={'training_config':cfg,'dataset_directory':str(directory),'dataset_audit_sha256':sha256(directory/'data_audit.json'),
            'preprocessing_sha256':sha256(directory/'preprocessing.json'),'dataset_manifest_sha256':sha256(directory/'manifest.json'),
            'provenance':provenance(),'torch_version':torch.__version__,'python_version':platform.python_version(),
            'device':'cpu','machine':platform.machine(),'deterministic_algorithms':True,
            'architecture':'Conv(1,16,3,s2,p1),ReLU,Conv(16,32,3,s2,p1),ReLU,AdaptiveAvgPool(4,16),Flatten,Linear(2048,64),ReLU,Linear(64,3),Sigmoid'}
    (run/'run.json').write_text(json.dumps(record,indent=2)+'\n')
    fit_baselines(directory,run)  # Only training split, before either CNN fit.
    normal=train_condition(directory,run,cfg,False)
    shuffled=train_condition(directory,run,cfg,True)
    if normal['initial_weights_sha256']!=shuffled['initial_weights_sha256']: raise ValueError('Control initialization mismatch')
    print('Training complete. Test data has not been opened. Evaluate exactly once with evaluate.py.',flush=True)


if __name__=='__main__': main()
