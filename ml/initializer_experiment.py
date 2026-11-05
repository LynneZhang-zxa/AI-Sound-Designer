"""One reproducible offline expanded-domain initializer experiment; no plugin changes."""
import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import time
import numpy as np
import scipy
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from scipy.io import wavfile
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, lfilter, sawtooth, square, resample_poly
from features import log_mel
from generate_dataset import ROOT, make_manifest, merge_receipts, provenance, sha256, validate_performance_groups
from inspect_dataset import read_audio
from metrics import score, to_normalized, to_physical, NAMES
from dsp_baseline import DSPBaseline, measure
from reference_match import representation, objective, envelope_guess

CONFIG=ROOT/'ml/initializer_config.json'
DATA=ROOT/'ml/data/initializer_3000'
RUN=ROOT/'ml/runs/initializer_experiment'


def write(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')


def extended_manifest(spec,cfg,smoke=False):
    base=json.loads((ROOT/'ml/pitch_velocity_config.json').read_text())
    base['seed']=cfg['dataset_seed'];base['examples']=100 if smoke else cfg['examples']
    base['split_counts']={'train':80,'validation':10,'test':10} if smoke else {'train':2400,'validation':300,'test':300}
    base['performance_variation']={'seen_midi_notes':cfg['seen_pitches'],'held_out_midi_notes':cfg['held_out_pitches'],
                                 'velocity_range':cfg['velocity_range'],'test_seen_count':5 if smoke else 150}
    manifest=make_manifest(base,spec,provenance())
    manifest['metadata']['initializer_config']=cfg
    rng=np.random.default_rng(cfg['dataset_seed']+2)
    for split in base['split_counts']:
        rows=[r for r in manifest['examples'] if r['split']==split]
        waveforms=np.resize(np.arange(4),len(rows));rng.shuffle(waveforms)
        for row,waveform in zip(rows,waveforms):
            row['requested_parameters']['waveform']=int(waveform)
            for key,(low,high) in cfg['nuisance_ranges'].items():
                p=spec['parameters'][key]
                if not p['minimum']<=low<high<=p['maximum']: raise ValueError('Nuisance outside exported range')
                row['requested_parameters'][key]=float(np.exp(rng.uniform(np.log(low),np.log(high)))) if key=='decay' else float(rng.uniform(low,high))
    validate_performance_groups(manifest)
    return manifest


def prepare(directory,cfg,smoke=False):
    directory.mkdir(parents=True,exist_ok=False);renderer=ROOT/'build/DatasetRenderer'
    subprocess.run([str(renderer),'--export-spec',str(directory/'parameter_spec.json')],check=True)
    spec=json.loads((directory/'parameter_spec.json').read_text())
    manifest=extended_manifest(spec,cfg,smoke)
    manifest['metadata']['run_environment']={'renderer_sha256':sha256(renderer),'config_sha256':sha256(CONFIG),
        'protocol_sha256':sha256(ROOT/'ml/INITIALIZER_PROTOCOL.md'),'python':platform.python_version(),
        'numpy':np.__version__,'scipy':scipy.__version__,'torch':torch.__version__}
    write(directory/'manifest.json',manifest)
    if not smoke:
        rng=np.random.default_rng(cfg['evaluation_seed']);selected=[]
        for waveform in range(4):
            for group in ['seen_pitch','held_out_pitch']:
                pool=[r['id'] for r in manifest['examples'] if r['split']=='test' and r['requested_parameters']['waveform']==waveform and r['evaluation_group']==group]
                selected.extend(rng.choice(pool,4,replace=False).tolist())
        write(directory/'search_subset.json',selected)
    with (directory/'renderer.log').open('w') as log:
        subprocess.run([str(renderer),'--render',str(directory/'manifest.json'),str(directory)],stdout=log,stderr=subprocess.STDOUT,check=True)
    rendered=merge_receipts(manifest,json.loads((directory/'render_receipts.json').read_text()))
    write(directory/'rendered_manifest.json',rendered);performance=validate_performance_groups(rendered)
    config=manifest['metadata']['config'];hashes=set();targets=set();peaks=[];proxies=[]
    distribution={};shape=(1,64,747);feature_min=float('inf');feature_max=-float('inf')
    for split in config['split_counts']:
        rows=[r for r in rendered['examples'] if r['split']==split]
        inputs=np.lib.format.open_memmap(directory/f'{split}_features.npy',mode='w+',dtype=np.float32,shape=(len(rows),*shape))
        ys=[];physical=[];waves=[];dsp=[];groups=[]
        for i,row in enumerate(rows):
            path=directory/row['audio'];digest=sha256(path)
            if digest in hashes: raise ValueError('Duplicate waveform')
            hashes.add(digest);rate,audio=read_audio(path)
            if rate!=48000 or audio.shape!=(192000,) or not np.isfinite(audio).all(): raise ValueError('Invalid waveform')
            peak=float(np.max(np.abs(audio)));peaks.append(peak)
            if not 0<peak<.999 or np.max(np.abs(audio[:4800]))>2**-22 or np.sqrt(np.mean(audio[-9600:]**2))>=1e-5:
                raise ValueError('Clipping, onset or tail failure')
            for key,value in row['requested_parameters'].items():
                if not np.isclose(value,row['applied_parameters'][key],rtol=3e-6,atol=1e-7): raise ValueError('Incorrect parameter readback')
            y=[row['normalized_targets'][k] for k in NAMES];raw=[row['targets'][k] for k in NAMES]
            np.testing.assert_allclose(to_physical(np.array([y]),spec)[0],raw,rtol=1e-5,atol=1e-5)
            waveform=int(row['applied_parameters']['waveform']);vector=tuple(raw+[waveform])
            if vector in targets: raise ValueError('Duplicate target vector')
            targets.add(vector)
            feature=log_mel(audio,rate,config['features'])
            if feature.shape!=shape or not np.isfinite(feature).all() or feature.std()<.1: raise ValueError('Bad features')
            feature_min=min(feature_min,float(feature.min()));feature_max=max(feature_max,float(feature.max()))
            inputs[i]=feature;ys.append(y);physical.append(raw);waves.append(waveform);groups.append(row['evaluation_group'])
            proxy=measure(audio,rate,config['renderer'])
            if not np.isfinite(proxy).all() or proxy[1]<=0 or proxy[2]<=0: raise ValueError('Envelope visibility failure')
            dsp.append(proxy)
            if (i+1)%400==0: print(f'{split} features {i+1}/{len(rows)}',flush=True)
        inputs.flush()
        np.save(directory/f'{split}_targets.npy',np.array(ys,dtype=np.float32))
        np.save(directory/f'{split}_physical.npy',np.array(physical,dtype=np.float64))
        np.save(directory/f'{split}_waveforms.npy',np.array(waves,dtype=np.int64));np.save(directory/f'{split}_dsp.npy',np.array(dsp))
        write(directory/f'{split}_ids.json',[r['id'] for r in rows]);write(directory/f'{split}_groups.json',groups)
        distribution[split]=np.bincount(waves,minlength=4).tolist()
    train=np.load(directory/'train_features.npy',mmap_mode='r');sums=np.zeros(64);squares=np.zeros(64);n=0
    for first in range(0,len(train),32):
        block=np.asarray(train[first:first+32],dtype=np.float64)
        sums+=block.sum(axis=(0,1,3));squares+=(block**2).sum(axis=(0,1,3));n+=len(block)*block.shape[3]
    mean=sums/n;std=np.sqrt(np.maximum(squares/n-mean**2,0))
    if np.any(std<1e-6): raise ValueError('Degenerate preprocessing')
    write(directory/'preprocessing.json',{'source_split':'train','examples':len(train),'mean_per_mel':mean.tolist(),'std_per_mel':std.tolist()})
    audit={'status':'PASS','examples':len(rendered['examples']),'unique_audio':len(hashes),'unique_targets':len(targets),
        'waveform_counts':distribution,'performance':performance,'feature_shape':list(shape),'feature_range':[feature_min,feature_max],
        'peak_range':[min(peaks),max(peaks)],'no_recording_amplitude_normalization':True,
        'config':cfg,'manifest_sha256':sha256(directory/'manifest.json'),'preprocessing_sha256':sha256(directory/'preprocessing.json'),
        'plugin_sources_unchanged':provenance()['plugin_source_sha256']==manifest['metadata']['provenance']['plugin_source_sha256']}
    if not audit['plugin_sources_unchanged']: raise ValueError('Plugin source changed')
    write(directory/'audit.json',audit);print(json.dumps(audit),flush=True)


class Initializer(nn.Module):
    def __init__(self):
        super().__init__()
        self.net=nn.Sequential(nn.Conv2d(1,16,3,2,1),nn.ReLU(),nn.Conv2d(16,32,3,2,1),nn.ReLU(),
            nn.AdaptiveAvgPool2d((4,16)),nn.Flatten(),nn.Linear(2048,64),nn.ReLU(),nn.Linear(64,7))
    def forward(self,x):
        if x.ndim!=4 or tuple(x.shape[1:])!=(1,64,747): raise ValueError('Expected waveform-only [B,1,64,747]')
        out=self.net(x);return out[:,:3].sigmoid(),out[:,3:]


class Inputs(Dataset):
    def __init__(self,directory,split,permutation=None):
        self.x=np.load(directory/f'{split}_features.npy',mmap_mode='r')
        self.y=np.load(directory/f'{split}_targets.npy');self.wave=np.load(directory/f'{split}_waveforms.npy')
        stats=json.loads((directory/'preprocessing.json').read_text())
        if stats['source_split']!='train': raise ValueError('Wrong preprocessing split')
        self.mean=np.array(stats['mean_per_mel'],dtype=np.float32)[None,:,None]
        self.std=np.array(stats['std_per_mel'],dtype=np.float32)[None,:,None]
        if permutation is not None:
            if split!='train' or sorted(permutation.tolist())!=list(range(len(self.y))): raise ValueError('Invalid shuffle')
            self.y=self.y[permutation].copy();self.wave=self.wave[permutation].copy()
    def __len__(self): return len(self.y)
    def __getitem__(self,index):
        return torch.from_numpy(((self.x[index]-self.mean)/self.std).copy()),torch.from_numpy(self.y[index].copy()),int(self.wave[index])


def train(directory,run,cfg):
    run.mkdir(parents=True,exist_ok=False)
    audit=json.loads((directory/'audit.json').read_text())
    if audit['status']!='PASS': raise ValueError('Audit required')
    # Independently recompute train-only feature moments before fitting.
    x=np.load(directory/'train_features.npy',mmap_mode='r');sums=np.zeros(64);squares=np.zeros(64);count=0
    for first in range(0,len(x),32):
        block=np.asarray(x[first:first+32],dtype=np.float64);sums+=block.sum((0,1,3));squares+=(block**2).sum((0,1,3));count+=len(block)*block.shape[3]
    stats=json.loads((directory/'preprocessing.json').read_text())
    np.testing.assert_allclose(sums/count,stats['mean_per_mel'],rtol=0,atol=1e-12)
    np.testing.assert_allclose(np.sqrt(squares/count-(sums/count)**2),stats['std_per_mel'],rtol=0,atol=1e-12)
    data=json.loads((directory/'rendered_manifest.json').read_text());config=data['metadata']['config']
    for split in ['train','validation']:
        row=next(r for r in data['examples'] if r['split']==split);rate,audio=read_audio(directory/row['audio'])
        np.testing.assert_array_equal(log_mel(audio,rate,config['features']),np.load(directory/f'{split}_features.npy',mmap_mode='r')[0])
    record={'config':cfg,'data':str(directory),'provenance':provenance(),'torch':torch.__version__,'python':platform.python_version(),
            'audit_sha256':sha256(directory/'audit.json'),'preprocessing_sha256':sha256(directory/'preprocessing.json'),
            'protocol_sha256':sha256(ROOT/'ml/INITIALIZER_PROTOCOL.md'),'training_test_split_opened':False,
            'input_audit':'independent train moments and train/validation WAV recomputation passed'}
    write(run/'run.json',record)
    labels=np.load(directory/'train_targets.npy');waves=np.load(directory/'train_waveforms.npy')
    baseline=DSPBaseline().fit(np.load(directory/'train_dsp.npy'),np.load(directory/'train_physical.npy'))
    write(run/'baselines.json',{'mean':labels.astype(np.float64).mean(0).tolist(),'majority':int(np.bincount(waves,minlength=4).argmax()),'dsp':baseline.serializable(),'fit_split':'train'})
    for shuffled in [False,True]:
        name='shuffled' if shuffled else 'model';folder=run/name;folder.mkdir()
        random.seed(cfg['training_seed']);np.random.seed(cfg['training_seed']);torch.manual_seed(cfg['training_seed'])
        permutation=np.random.default_rng(cfg['shuffle_seed']).permutation(len(labels)) if shuffled else None
        if shuffled: np.save(folder/'permutation.npy',permutation)
        loader=DataLoader(Inputs(directory,'train',permutation),batch_size=cfg['batch_size'],shuffle=True,generator=torch.Generator().manual_seed(cfg['training_seed']))
        valid=DataLoader(Inputs(directory,'validation'),batch_size=cfg['batch_size'],shuffle=False)
        model=Initializer();initial=hashlib.sha256(b''.join(v.numpy().tobytes() for v in model.state_dict().values())).hexdigest()
        optimizer=torch.optim.Adam(model.parameters(),lr=cfg['learning_rate']);best=float('inf');bad=0;history=[];started=time.perf_counter()
        for epoch in range(1,cfg['max_epochs']+1):
            model.train();total=0.;n=0
            for x,y,w in loader:
                optimizer.zero_grad(set_to_none=True);p,logits=model(x)
                loss=nn.functional.mse_loss(p,y)+cfg['classification_loss_weight']*nn.functional.cross_entropy(logits,w)
                loss.backward();optimizer.step();total+=loss.item()*len(x);n+=len(x)
            model.eval();vl=0.;vn=0
            with torch.inference_mode():
                for x,y,w in valid:
                    p,logits=model(x);loss=nn.functional.mse_loss(p,y)+cfg['classification_loss_weight']*nn.functional.cross_entropy(logits,w)
                    vl+=loss.item()*len(x);vn+=len(x)
            row={'epoch':epoch,'training_loss':total/n,'validation_loss':vl/vn};history.append(row);print(name,json.dumps(row),flush=True)
            if row['validation_loss']<best:
                best=row['validation_loss'];bad=0;torch.save({'state_dict':model.state_dict(),'epoch':epoch},folder/'best.pt')
            else: bad+=1
            write(folder/'history.json',history)
            if bad>=cfg['patience']: break
        write(folder/'summary.json',{'best_validation_loss':best,'epochs':len(history),'seconds':time.perf_counter()-started,
              'parameters':sum(p.numel() for p in model.parameters()),'initial_sha256':initial,'checkpoint_sha256':sha256(folder/'best.pt')})
    summaries=[json.loads((run/name/'summary.json').read_text()) for name in ['model','shuffled']]
    if summaries[0]['initial_sha256']!=summaries[1]['initial_sha256']: raise ValueError('Initialization mismatch')


def classify(pred,truth):
    matrix=np.zeros((4,4),dtype=int)
    for a,b in zip(truth,pred): matrix[int(a),int(b)]+=1
    f1=[2*matrix[k,k]/max(1,int(matrix[k,:].sum()+matrix[:,k].sum())) for k in range(4)]
    return {'accuracy':float(np.mean(pred==truth)),'macro_f1':float(np.mean(f1)),'confusion_matrix':matrix.tolist()}


def predict(model,loader):
    ys=[];waves=[]
    with torch.inference_mode():
        for x,_y,_w in loader:
            p,logits=model(x);ys.append(p.numpy());waves.append(logits.argmax(1).numpy())
    return np.concatenate(ys),np.concatenate(waves)


def search(audio,settings,seed,note,config,spec,folder):
    """Same 52-render algorithm per method; only the initializer changes."""
    folder.mkdir(parents=True,exist_ok=False);renderer=ROOT/'build/DatasetRenderer'
    config=copy.deepcopy(config);timing=config['renderer'];timing.update(midi_note=int(note),velocity=.8)
    # Same production comparison representation and level policy, shared true MIDI timing.
    reference=resample_poly(audio,1,2)[2400:];ref=representation(reference,96000)
    scores=[];started=time.perf_counter()
    def evaluate(vectors,stage):
        output=folder/stage;output.mkdir();rows=[]
        for i,vector in enumerate(vectors):
            params={k:min(spec['parameters'][k]['maximum'],max(spec['parameters'][k]['minimum'],float(v))) for k,v in vector.items()}
            rows.append({'id':f'candidate_{i:03d}','split':'validation','requested_parameters':params})
        manifest={'metadata':{'config':config,'parameter_specification':spec},'examples':rows};write(output/'manifest.json',manifest)
        with (output/'renderer.log').open('w') as log:
            subprocess.run([str(renderer),'--render',str(output/'manifest.json'),str(output)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
        receipts=json.loads((output/'render_receipts.json').read_text())['examples'];result=[]
        for receipt in receipts:
            rate,wave=read_audio(output/receipt['audio']);wave=resample_poly(wave,1,2)
            metric=objective(ref,representation(wave[2400:],96000))
            result.append({'parameters':receipt['applied_parameters'],**metric})
        return result
    initial=dict(settings,**seed);coarse=[initial]
    for waveform in range(4):
        for cutoff in (30.,100.,400.,1500.,5000.,16000.):
            coarse.append(dict(initial,waveform=waveform,cutoff=cutoff))
    results=evaluate(coarse,'coarse');first=results[0];best=min(results,key=lambda r:r['score']);p=best['parameters']
    local=[dict(p,cutoff=p['cutoff']*cf,attack=p['attack']*af,release=p['release']*rf) for cf in (.6,1.,1.6) for af in (.6,1.,1.6) for rf in (.6,1.,1.6)]
    results+=evaluate(local,'refined');best=min(results,key=lambda r:r['score'])
    return {'initializer':initial,'initial_score':first['score'],'final_score':best['score'],'log_mel_rmse':best['log_mel_rmse'],
            'envelope_rmse':best['envelope_rmse'],'renders':len(results),'seconds':time.perf_counter()-started,'parameters':best['parameters']}


def external_fixture(rate,waveform,index):
    t=np.arange(rate*4)/rate;u=t-.1;gate=1.4;a=(.03,.18)[index];r=(.12,.6)[index]
    env=np.where(u<a,np.clip(u/a,0,1),.8+.2*np.clip(1-(u-a)/.1,0,1))
    env=np.where(u>=gate,.8*np.clip(1-(u-gate)/r,0,1),env);env[u<0]=0
    note=(52,64)[index];phase=2*np.pi*(440*2**((note-69)/12))*np.maximum(u,0)
    oscillator=[lambda:np.sin(phase),lambda:sawtooth(phase),lambda:square(phase),lambda:sawtooth(phase,width=.5)][waveform]()
    b,c=butter(2,(600,2400)[index],fs=rate);audio=lfilter(b,c,.12*oscillator*env)
    return np.stack([audio,audio*.8],1),note


def evaluate(directory,run,cfg):
    record=json.loads((run/'run.json').read_text())
    if record['audit_sha256']!=sha256(directory/'audit.json') or record['preprocessing_sha256']!=sha256(directory/'preprocessing.json'):
        raise ValueError('Dataset changed after training')
    # Exclusive marker before any test feature/prediction load.
    with (run/'evaluation_started.json').open('x') as stream: json.dump({'test_passes_per_checkpoint':1,'protocol_sha256':sha256(ROOT/'ml/INITIALIZER_PROTOCOL.md')},stream)
    models={}
    for name in ['model','shuffled']:
        model=Initializer();model.load_state_dict(torch.load(run/name/'best.pt',map_location='cpu',weights_only=True)['state_dict']);model.eval();models[name]=model
    validation=Inputs(directory,'validation');sample=validation[0][0][None]
    timings=[]
    with torch.inference_mode():
        for _ in range(30): models['model'](sample)
        for _ in range(200):
            before=time.perf_counter_ns();models['model'](sample);timings.append((time.perf_counter_ns()-before)/1e6)
    loader=DataLoader(Inputs(directory,'test'),batch_size=32,shuffle=False)
    predictions={name:predict(model,loader) for name,model in models.items()}
    truth=np.load(directory/'test_targets.npy');raw=np.load(directory/'test_physical.npy');waves=np.load(directory/'test_waveforms.npy')
    spec=json.loads((directory/'parameter_spec.json').read_text());baseline=json.loads((run/'baselines.json').read_text())
    dsp=DSPBaseline();dsp.tables=[(np.array(t['proxy']),np.array(t['physical_target'])) for t in baseline['dsp']['tables']]
    predictions['training_mean']=(np.tile(baseline['mean'],(len(truth),1)),np.full(len(truth),baseline['majority']))
    predictions['dsp']=(to_normalized(dsp.predict(np.load(directory/'test_dsp.npy')),spec),np.full(len(truth),baseline['majority']))
    np.savez(run/'test_predictions.npz',truth=truth,physical=raw,waveforms=waves,**{name:p[0] for name,p in predictions.items()},
             **{name+'_waveforms':p[1] for name,p in predictions.items()})
    metrics={name:dict(score(p,truth,raw,spec),waveform=classify(w,waves)) for name,(p,w) in predictions.items()}
    groups=json.loads((directory/'test_groups.json').read_text());ids=json.loads((directory/'test_ids.json').read_text())
    grouped={g:{name:dict(score(p[np.array(groups)==g],truth[np.array(groups)==g],raw[np.array(groups)==g],spec),
                    waveform=classify(w[np.array(groups)==g],waves[np.array(groups)==g])) for name,(p,w) in predictions.items()} for g in sorted(set(groups))}
    with (run/'test_predictions.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['id','method','waveform_true','waveform_pred','cutoff_true_Hz','attack_true_s','release_true_s','cutoff_pred_Hz','attack_pred_s','release_pred_s'])
        for name,(p,w) in predictions.items():
            physical=to_physical(p,spec)
            for i,id in enumerate(ids): writer.writerow([id,name,int(waves[i]),int(w[i]),*raw[i].tolist(),*physical[i].tolist()])
    manifest=json.loads((directory/'rendered_manifest.json').read_text());rows={r['id']:r for r in manifest['examples']}
    selected_ids=json.loads((directory/'search_subset.json').read_text())
    selected=[ids.index(identifier) for identifier in selected_ids]
    write(run/'search_subset.json',selected_ids)
    config=manifest['metadata']['config'];settings=dict(config['fixed_parameters'])
    default={'cutoff':12000.,'attack':.1,'release':.4,'waveform':1}
    seeds=to_physical(predictions['model'][0],spec);matches=[]
    def compare(identifier,audio,note,model_seed,subset):
        down=resample_poly(audio,1,2)[2400:];a,r=envelope_guess(down,1.4)
        methods={'default':default,'dsp':dict(default,attack=a,release=r),'model':model_seed}
        result={'id':identifier,'subset':subset,'methods':{}}
        for name,seed in methods.items():
            result['methods'][name]=search(audio,settings,seed,note,config,spec,run/'search'/identifier/name)
        matches.append(result);write(run/'search_results.json',matches)
        print('SEARCH',identifier,{k:v['final_score'] for k,v in result['methods'].items()},flush=True)
    for i in selected:
        row=rows[ids[i]];rate,audio=read_audio(directory/row['audio'])
        seed=dict(zip(NAMES,map(float,seeds[i])));seed['waveform']=int(predictions['model'][1][i])
        compare(ids[i],audio,row['requested_performance']['midi_note'],seed,'held_out_synth')
    ext=run/'external';ext.mkdir()
    stats=json.loads((directory/'preprocessing.json').read_text());mean=np.array(stats['mean_per_mel'],dtype=np.float32)[None,:,None];std=np.array(stats['std_per_mel'],dtype=np.float32)[None,:,None]
    for waveform in range(4):
        for index in range(2):
            identifier=f'external_{waveform}_{index}';stereo,note=external_fixture(44100,waveform,index)
            wavfile.write(ext/f'{identifier}.wav',44100,stereo.astype(np.float32))
            audio=resample_poly(stereo.mean(1),160,147);audio=audio[:192000]
            feature=log_mel(audio,48000,config['features'])
            with torch.inference_mode(): p,logits=models['model'](torch.from_numpy(((feature-mean)/std)[None].copy()))
            seed=dict(zip(NAMES,map(float,to_physical(p.numpy(),spec)[0])));seed['waveform']=int(logits.argmax(1)[0])
            compare(identifier,audio,note,seed,'independent_scipy')
    summary={}
    for subset in ['held_out_synth','independent_scipy']:
        subset_rows=[r for r in matches if r['subset']==subset];summary[subset]={}
        for method in ['default','dsp','model']:
            values=[r['methods'][method]['final_score'] for r in subset_rows]
            summary[subset][method]={'mean_score':float(np.mean(values)),'median_score':float(np.median(values)),
                'mean_seconds':float(np.mean([r['methods'][method]['seconds'] for r in subset_rows])),'renders_per_example':52}
        for baseline_name in ['default','dsp']:
            diff=np.array([r['methods']['model']['final_score']-r['methods'][baseline_name]['final_score'] for r in subset_rows])
            summary[subset]['model_vs_'+baseline_name]={'wins':int((diff<-1e-9).sum()),'ties':int((np.abs(diff)<=1e-9).sum()),'losses':int((diff>1e-9).sum()),'mean_score_difference':float(diff.mean())}
    result={'test':metrics,'test_groups':grouped,'search':summary,'shuffled_mse_ratio':metrics['shuffled']['normalized_mse']/metrics['model']['normalized_mse'],
        'offline_forward_latency_ms':{'mean':float(np.mean(timings)),'median':float(np.median(timings)),'p95':float(np.percentile(timings,95)),
                                    'scope':'CPU4 threads batch1; 30 warmups/200 repetitions; validation example; forward only'},
        'test_inference_passes_per_checkpoint':1,'provenance':record,'all_search_renders':len(matches)*3*52}
    write(run/'results.json',result);report(run,result)


def report(run,result):
    lines=['# Expanded-domain initializer — measured results','','One frozen experiment, no tuning or deployment. Model predicts three normalized targets plus waveform; nuisance parameters vary.','',
        '## Test prediction metrics (300 examples)','','| Method | Cutoff MAE / RMSE Hz | Attack MAE / RMSE ms | Release MAE / RMSE ms | Norm MSE | Wave accuracy | Macro F1 |','|---|---:|---:|---:|---:|---:|---:|']
    for name,m in result['test'].items():
        values=[' / '.join(format(m['parameters'][k][v],'.12g') for v in ['mae','rmse']) for k in NAMES]
        lines.append('| '+name+' | '+' | '.join(values)+f" | {m['normalized_mse']:.12g} | {m['waveform']['accuracy']:.12g} | {m['waveform']['macro_f1']:.12g} |")
    for subset,summary in result['search'].items():
        lines+=['',f'## Equal-budget search: {subset}','','| Method | Mean score | Median score | Mean seconds | Renders |','|---|---:|---:|---:|---:|']
        for method in ['default','dsp','model']:
            m=summary[method];lines.append(f"| {method} | {m['mean_score']:.12g} | {m['median_score']:.12g} | {m['mean_seconds']:.12g} | 52 |")
        for baseline_name in ['default','dsp']:
            m=summary['model_vs_'+baseline_name];lines+=['',f"Model vs {baseline_name}: wins {m['wins']}, ties {m['ties']}, losses {m['losses']}; mean difference (model minus baseline) {m['mean_score_difference']:.12g}."]
    lines+=['','## Sanity, timing and interpretation','',f"Shuffled/real test normalized-MSE ratio: {result['shuffled_mse_ratio']:.12g}×.",
        f"Validation-example CPU forward timing: {result['offline_forward_latency_ms']}. No real-time claim.",
        '', 'Parameter errors and waveform confusion matrix/seen-unseen groups are retained in full precision in results.json. Sine/filter and nuisance/envelope ambiguities mean low numerical error alone cannot establish sound similarity.',
        '', 'The practical comparison uses the same 52 renders, objective and fixed nuisance defaults for all methods. Pitch and gate are shared known task conditions; no true nuisance settings seed the renderer. No claim of fewer renders is made from this fixed-budget test. Negative comparisons are retained.',
        '', 'The search evaluates 32 balanced held-out synth references and eight independent SciPy fixtures, not real third-party synth recordings. No listening test or arbitrary-audio generalization is established. No additional fine-tuning, tuning, or plugin integration followed these results.',
        '',f"Artifacts: `{run.relative_to(ROOT)}`. Per-example parameter predictions: test_predictions.csv/.npz. All search outcomes: search_results.json. Protocol/config: INITIALIZER_PROTOCOL.md and initializer_config.json. Source, renderer, commit, environment and preprocessing identities are recorded in the run/dataset manifests."]
    (ROOT/'ml/INITIALIZER_RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(result['search'],indent=2),flush=True)
    print('STOP: completed frozen initializer experiment; no production deployment.',flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['all','prepare','train','evaluate'])
    args=parser.parse_args();cfg=json.loads(CONFIG.read_text())
    torch.set_num_threads(cfg['torch_threads']);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    if args.stage in ['all','prepare']:
        prepare(ROOT/'ml/data/initializer_smoke',cfg,True);prepare(DATA,cfg)
    if args.stage in ['all','train']: train(DATA,RUN,cfg)
    if args.stage in ['all','evaluate']: evaluate(DATA,RUN,cfg)


if __name__=='__main__': main()
