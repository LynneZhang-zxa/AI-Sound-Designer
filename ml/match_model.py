"""Offline seven-control Match experiment; never loaded by the plugin/default matcher."""
import argparse
import copy
import csv
import json
import os
from pathlib import Path
import random
import subprocess
import time
import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset,DataLoader
from scipy.io import wavfile
from scipy.signal import butter,lfilter,sawtooth,square
from initializer_experiment import extended_manifest,classify
from generate_dataset import ROOT,provenance,sha256,merge_receipts,validate_performance_groups
from features import log_mel
from parameters import normalize,denormalize
from inspect_dataset import read_audio
from dsp_baseline import measure,DSPBaseline
from reference_match_v2 import ReferenceMatcherV2,PATCH_KEYS

CONFIG=ROOT/'ml/match_model_config.json'
PROTOCOL=ROOT/'ml/MATCH_MODEL_PROTOCOL.md'
DATA=ROOT/'ml/data/match_model_3000'
RUN=ROOT/'ml/runs/match_model'
NAMES=('cutoff','attack','decay','sustain','release','resonance')


def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def convert(values,spec,inverse=False):
    values=np.asarray(values);result=np.empty(values.shape,dtype=np.float64)
    for index,name in enumerate(NAMES):
        fn=denormalize if inverse else normalize
        result[:,index]=[fn(float(np.clip(v,0,1)) if inverse else float(v),name,spec) for v in values[:,index]]
    return result


def prepare(cfg):
    DATA.mkdir(parents=True,exist_ok=False);renderer=ROOT/'build/DatasetRenderer'
    subprocess.run([str(renderer),'--export-spec',str(DATA/'parameter_spec.json')],check=True)
    spec=json.loads((DATA/'parameter_spec.json').read_text());manifest=extended_manifest(spec,cfg)
    manifest['metadata']['match_protocol_sha256']=sha256(PROTOCOL)
    manifest['metadata']['match_config_sha256']=sha256(CONFIG)
    manifest['metadata']['renderer_sha256']=sha256(renderer)
    write(DATA/'manifest.json',manifest)
    rng=np.random.default_rng(cfg['evaluation_seed']);subset=[]
    for wave in range(4):
        for group in ('seen_pitch','held_out_pitch'):
            pool=[r['id'] for r in manifest['examples'] if r['split']=='test' and r['requested_parameters']['waveform']==wave and r['evaluation_group']==group]
            subset.extend(rng.choice(pool,2,replace=False).tolist())
    write(DATA/'search_subset.json',subset)
    with (DATA/'renderer.log').open('w') as log:subprocess.run([str(renderer),'--render',str(DATA/'manifest.json'),str(DATA)],check=True,stdout=log,stderr=subprocess.STDOUT)
    manifest=merge_receipts(manifest,json.loads((DATA/'render_receipts.json').read_text()));validate_performance_groups(manifest)
    write(DATA/'rendered_manifest.json',manifest);hashes=set();feature_range=[float('inf'),float('-inf')]
    for split in ('train','validation','test'):
        rows=[r for r in manifest['examples'] if r['split']==split]
        x=np.lib.format.open_memmap(DATA/f'{split}_features.npy',mode='w+',dtype=np.float32,shape=(len(rows),1,64,747));raw=[];waves=[];proxies=[]
        for index,row in enumerate(rows):
            path=DATA/row['audio'];digest=sha256(path)
            if digest in hashes:raise ValueError('Duplicate audio')
            hashes.add(digest);rate,audio=read_audio(path)
            if rate!=48000 or audio.shape!=(192000,) or not np.isfinite(audio).all() or not 0<np.abs(audio).max()<.999:raise ValueError('Invalid audio')
            if np.abs(audio[:4800]).max()>2**-22 or np.sqrt(np.mean(audio[-9600:]**2))>=1e-5:raise ValueError('Onset/tail failure')
            for key,value in row['requested_parameters'].items():
                if not np.isclose(value,row['applied_parameters'][key],rtol=3e-6,atol=1e-7):raise ValueError('Wrong ground truth')
            feat=log_mel(audio,rate,manifest['metadata']['config']['features'])
            if feat.shape!=(1,64,747) or not np.isfinite(feat).all():raise ValueError('Invalid features')
            x[index]=feat;feature_range=[min(feature_range[0],float(feat.min())),max(feature_range[1],float(feat.max()))]
            raw.append([row['applied_parameters'][k] for k in NAMES]);waves.append(round(row['applied_parameters']['waveform']))
            proxies.append(measure(audio,rate,manifest['metadata']['config']['renderer']))
        x.flush();raw=np.array(raw);y=convert(raw,spec);np.testing.assert_allclose(convert(y,spec,True),raw,rtol=1e-10,atol=1e-10)
        np.save(DATA/f'{split}_targets.npy',y.astype(np.float32));np.save(DATA/f'{split}_physical.npy',raw)
        np.save(DATA/f'{split}_waves.npy',np.array(waves));np.save(DATA/f'{split}_dsp.npy',np.array(proxies));write(DATA/f'{split}_ids.json',[r['id'] for r in rows])
        print('prepared',split,len(rows),flush=True)
    x=np.load(DATA/'train_features.npy',mmap_mode='r');sums=np.zeros(64);sq=np.zeros(64);n=0
    for first in range(0,len(x),32):
        a=np.asarray(x[first:first+32],dtype=np.float64);sums+=a.sum((0,1,3));sq+=(a*a).sum((0,1,3));n+=len(a)*a.shape[3]
    mean=sums/n;std=np.sqrt(np.maximum(sq/n-mean**2,0));assert np.all(std>1e-6)
    write(DATA/'preprocessing.json',{'source_split':'train','examples':len(x),'mean':mean.tolist(),'std':std.tolist()})
    write(DATA/'audit.json',{'status':'PASS','examples':len(hashes),'split_counts':{'train':2400,'validation':300,'test':300},'features':[1,64,747],'feature_range':feature_range,'amplitude_normalization':False,'target_order':NAMES,'manifest_sha256':sha256(DATA/'manifest.json')})


class Model(nn.Module):
    def __init__(self):
        super().__init__();self.net=nn.Sequential(nn.Conv2d(1,16,3,2,1),nn.ReLU(),nn.Conv2d(16,32,3,2,1),nn.ReLU(),nn.AdaptiveAvgPool2d((4,16)),nn.Flatten(),nn.Linear(2048,64),nn.ReLU(),nn.Linear(64,10))
    def forward(self,x):
        if x.ndim!=4 or tuple(x.shape[1:])!=(1,64,747):raise ValueError('Expected waveform-only [B,1,64,747]')
        z=self.net(x);return z[:,:6].sigmoid(),z[:,6:]


class Inputs(Dataset):
    def __init__(self,split,permutation=None):
        self.x=np.load(DATA/f'{split}_features.npy',mmap_mode='r');self.y=np.load(DATA/f'{split}_targets.npy');self.w=np.load(DATA/f'{split}_waves.npy')
        stats=json.loads((DATA/'preprocessing.json').read_text());assert stats['source_split']=='train'
        self.mean=np.array(stats['mean'],dtype=np.float32)[None,:,None];self.std=np.array(stats['std'],dtype=np.float32)[None,:,None]
        if permutation is not None:
            if split!='train' or sorted(permutation.tolist())!=list(range(len(self.y))):raise ValueError('Invalid label permutation')
            self.y=self.y[permutation];self.w=self.w[permutation]
    def __len__(self):return len(self.y)
    def __getitem__(self,i):return torch.from_numpy(((self.x[i]-self.mean)/self.std).copy()),torch.from_numpy(self.y[i].copy()),int(self.w[i])


def train(cfg):
    RUN.mkdir(parents=True,exist_ok=False)
    # Independently recompute waveform features, and train-only normalization moments.
    manifest=json.loads((DATA/'rendered_manifest.json').read_text())
    for split in ('train','validation'):
        r=next(r for r in manifest['examples'] if r['split']==split);rate,a=read_audio(DATA/r['audio'])
        np.testing.assert_array_equal(log_mel(a,rate,manifest['metadata']['config']['features']),np.load(DATA/f'{split}_features.npy',mmap_mode='r')[0])
    x=np.load(DATA/'train_features.npy',mmap_mode='r');stats=json.loads((DATA/'preprocessing.json').read_text());sums=np.zeros(64);sq=np.zeros(64);n=0
    for first in range(0,len(x),32):
        a=np.asarray(x[first:first+32],dtype=np.float64);sums+=a.sum((0,1,3));sq+=(a*a).sum((0,1,3));n+=len(a)*a.shape[3]
    np.testing.assert_allclose(sums/n,stats['mean'],atol=1e-12,rtol=0);np.testing.assert_allclose(np.sqrt(sq/n-(sums/n)**2),stats['std'],atol=1e-12,rtol=0)
    write(RUN/'run.json',{'config':cfg,'provenance':provenance(),'torch':torch.__version__,'model_parameters':sum(p.numel() for p in Model().parameters()),'protocol_sha256':sha256(PROTOCOL),'data_manifest_sha256':sha256(DATA/'manifest.json'),'preprocessing_sha256':sha256(DATA/'preprocessing.json'),'input_audit':'WAV-derived features recomputed; train-only moments recomputed; model receives tensors only','test_features_opened_during_training':False})
    labels=np.load(DATA/'train_targets.npy')
    for name in ('model','shuffled'):
        folder=RUN/name;folder.mkdir();random.seed(cfg['training_seed']);np.random.seed(cfg['training_seed']);torch.manual_seed(cfg['training_seed'])
        perm=np.random.default_rng(cfg['shuffle_seed']).permutation(len(labels)) if name=='shuffled' else None
        if perm is not None:np.save(folder/'permutation.npy',perm)
        train_loader=DataLoader(Inputs('train',perm),batch_size=32,shuffle=True,generator=torch.Generator().manual_seed(cfg['training_seed']));valid=DataLoader(Inputs('validation'),batch_size=32)
        model=Model();optimizer=torch.optim.Adam(model.parameters(),lr=.001);best=float('inf');bad=0;history=[];started=time.perf_counter()
        initial=sha256_bytes(model)
        for epoch in range(1,36):
            model.train();total=0.;count=0
            for x,y,w in train_loader:
                optimizer.zero_grad(set_to_none=True);p,c=model(x);loss=nn.functional.mse_loss(p,y)+.1*nn.functional.cross_entropy(c,w);loss.backward();optimizer.step();total+=loss.item()*len(x);count+=len(x)
            model.eval();vl=0.;vn=0
            with torch.inference_mode():
                for x,y,w in valid:
                    p,c=model(x);vl+=(nn.functional.mse_loss(p,y)+.1*nn.functional.cross_entropy(c,w)).item()*len(x);vn+=len(x)
            row={'epoch':epoch,'train_loss':total/count,'validation_loss':vl/vn};history.append(row);print(name,row,flush=True)
            if row['validation_loss']<best:best=row['validation_loss'];bad=0;torch.save({'state_dict':model.state_dict(),'epoch':epoch},folder/'best.pt')
            else:bad+=1
            write(folder/'history.json',history)
            if bad>=7:break
        write(folder/'summary.json',{'best_validation_loss':best,'epochs':len(history),'seconds':time.perf_counter()-started,'initial_sha256':initial,'checkpoint_sha256':sha256(folder/'best.pt')})


def sha256_bytes(model):
    import hashlib
    return hashlib.sha256(b''.join(v.numpy().tobytes() for v in model.state_dict().values())).hexdigest()


def load_model(name='model'):
    m=Model();m.load_state_dict(torch.load(RUN/name/'best.pt',map_location='cpu',weights_only=True)['state_dict']);m.eval();return m


def predict(model,loader):
    ys=[];ws=[]
    with torch.inference_mode():
        for x,_y,_w in loader:
            p,w=model(x);ys.append(p.numpy());ws.append(w.argmax(1).numpy())
    return np.concatenate(ys),np.concatenate(ws)


def evaluate(cfg):
    with (RUN/'evaluation_started.json').open('x') as f:json.dump({'test_passes_per_checkpoint':1},f)
    spec=json.loads((DATA/'parameter_spec.json').read_text());truth=np.load(DATA/'test_targets.npy');physical=np.load(DATA/'test_physical.npy');waves=np.load(DATA/'test_waves.npy')
    predictions={name:predict(load_model(name),DataLoader(Inputs('test'),batch_size=32)) for name in ('model','shuffled')}
    train_y=np.load(DATA/'train_targets.npy');train_w=np.load(DATA/'train_waves.npy');mean=train_y.mean(0);major=int(np.bincount(train_w).argmax())
    predictions['training_mean']=(np.tile(mean,(len(truth),1)),np.full(len(truth),major))
    dsp=DSPBaseline().fit(np.load(DATA/'train_dsp.npy'),np.load(DATA/'train_physical.npy')[:,[0,1,4]])
    dsp_phys=convert(np.tile(mean,(len(truth),1)),spec,True);dsp_phys[:,[0,1,4]]=dsp.predict(np.load(DATA/'test_dsp.npy'))
    predictions['dsp_plus_mean']=(convert(dsp_phys,spec),np.full(len(truth),major))
    result={};saved={};rows=[];ids=json.loads((DATA/'test_ids.json').read_text())
    for name,(norm,w) in predictions.items():
        phys=convert(norm,spec,True);saved[name]=phys;saved[name+'_wave']=w
        scores={}
        for i,key in enumerate(NAMES):
            scale=1000 if key in ('attack','decay','release') else 1;e=(phys[:,i]-physical[:,i])*scale
            scores[key]={'mae':float(np.abs(e).mean()),'rmse':float(np.sqrt(np.mean(e*e))),'unit':'ms' if scale==1000 else 'Hz' if key=='cutoff' else 'Q' if key=='resonance' else 'fraction'}
        result[name]={'normalized_mse':float(np.mean((norm-truth)**2)),'parameters':scores,'waveform':classify(w,waves)}
        for j in range(len(ids)):
            row={'id':ids[j],'method':name,'true_waveform':int(waves[j]),'predicted_waveform':int(w[j])}
            for i,key in enumerate(NAMES):row['true_'+key]=physical[j,i];row['predicted_'+key]=phys[j,i]
            rows.append(row)
    model=load_model();sample=Inputs('validation')[0][0][None];times=[]
    with torch.inference_mode():
        for _ in range(30):model(sample)
        for _ in range(100):
            start=time.perf_counter_ns();model(sample);times.append((time.perf_counter_ns()-start)/1e6)
    result['latency']={'mean_ms':float(np.mean(times)),'p95_ms':float(np.percentile(times,95)),'scope':'CPU4 threads, batch1 forward only, validation input, 30 warmups/100 measured; offline, not audio callback latency'}
    np.savez(RUN/'test_predictions.npz',physical=physical,waveform=waves,**saved)
    with (RUN/'test_predictions.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write(RUN/'results.json',result);print(json.dumps(result,indent=2),flush=True)


def search(cfg):
    with (RUN/'search_started.json').open('x') as f:json.dump({'budget':cfg['render_budget_per_method']},f)
    manifest=json.loads((DATA/'rendered_manifest.json').read_text());config=manifest['metadata']['config'];spec=json.loads((DATA/'parameter_spec.json').read_text())
    subset=json.loads((DATA/'search_subset.json').read_text());cached=np.load(RUN/'test_predictions.npz');test_ids=json.loads((DATA/'test_ids.json').read_text());cases=[]
    for identity in subset:
        row=next(r for r in manifest['examples'] if r['id']==identity);i=test_ids.index(identity)
        seed=dict(zip(NAMES,cached['model'][i].tolist()),waveform=int(cached['model_wave'][i]))
        cases.append((identity,DATA/row['audio'],row['requested_performance']['midi_note'],seed,'held_out_synth'))
    # New independently generated transfer fixtures, no fitting on these sounds.
    independent=RUN/'independent';independent.mkdir();rng=np.random.default_rng(cfg['evaluation_seed']+1);model=load_model();stats=json.loads((DATA/'preprocessing.json').read_text())
    for i in range(8):
        rate=48000;t=np.arange(rate*4)/rate;u=t-.1;note=int(rng.integers(48,73));a=float(rng.uniform(.025,.25));release=float(rng.uniform(.1,.7));wave=i%4
        env=np.where(u<a,np.clip(u/a,0,1),.7+.3*np.clip(1-(u-a)/.15,0,1));env=np.where(u>=1.4,.7*np.clip(1-(u-1.4)/release,0,1),env);env[u<0]=0
        phase=2*np.pi*440*2**((note-69)/12)*np.maximum(u,0);osc=[np.sin(phase),sawtooth(phase),square(phase),sawtooth(phase,width=.5)][wave]
        b,c=butter(2,float(np.exp(rng.uniform(np.log(300),np.log(4000)))),fs=rate);audio=lfilter(b,c,.12*osc*env);path=independent/f'reference_{i}.wav';wavfile.write(path,rate,audio.astype(np.float32))
        feat=log_mel(audio,rate,config['features']);x=torch.from_numpy(((feat-np.array(stats['mean'],dtype=np.float32)[None,:,None])/np.array(stats['std'],dtype=np.float32)[None,:,None]).astype(np.float32)[None])
        with torch.inference_mode():p,w=model(x)
        seed=dict(zip(NAMES,convert(p.numpy(),spec,True)[0].tolist()),waveform=int(w.argmax(1)))
        cases.append((f'independent_{i}',path,note,seed,'independent_scipy'))
    outcomes=[];settings=dict(config['fixed_parameters'],waveform=1,cutoff=12000.,attack=.01,release=.15)
    for identity,path,note,seed,group in cases:
        methods={}
        for name,initial in [('dsp',None),('cnn_seed',seed)]:
            matcher=ReferenceMatcherV2(ROOT/'build/DatasetRenderer',config,spec,RUN/'search'/identity/name)
            r=matcher.match(path,settings,1.4,note,initializer=initial,budget=96,diagnostics=False)
            methods[name]={'score':r['matched']['score'],'renders':r['candidates_rendered'],'seconds':r['seconds'],'parameters':r['proposal'],'artifacts':r['artifacts']}
        outcomes.append({'id':identity,'group':group,'methods':methods});write(RUN/'search_results.json',outcomes);print(identity,methods['dsp']['score'],methods['cnn_seed']['score'],flush=True)
    summary={}
    for group in ('held_out_synth','independent_scipy'):
        rows=[r for r in outcomes if r['group']==group];a=np.array([r['methods']['dsp']['score'] for r in rows]);b=np.array([r['methods']['cnn_seed']['score'] for r in rows]);delta=b-a
        summary[group]={'dsp_mean':float(a.mean()),'cnn_seed_mean':float(b.mean()),'wins':int((delta< -1e-9).sum()),'ties':int((abs(delta)<=1e-9).sum()),'losses':int((delta>1e-9).sum()),'relative_mean_improvement':float(1-b.mean()/a.mean())}
    synth=summary['held_out_synth'];external=summary['independent_scipy'];summary['numeric_gate_passed']=bool(synth['relative_mean_improvement']>=.05 and synth['wins']>=10 and synth['losses']<=4 and external['relative_mean_improvement']>=.05 and external['wins']>=5 and external['losses']<=2)
    summary['deployment']='DSP matcher remains default. Experimental CNN not loaded by plugin/service. No arbitrary-audio or human-preference claim.'
    write(RUN/'search_summary.json',summary);print(json.dumps(summary,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','train','evaluate','search']);args=parser.parse_args();cfg=json.loads(CONFIG.read_text());torch.set_num_threads(cfg['torch_threads']);torch.use_deterministic_algorithms(True)
    globals()[args.phase](cfg)
if __name__=='__main__':main()
