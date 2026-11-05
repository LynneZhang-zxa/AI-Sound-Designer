"""Frozen offline hybrid validation; never imported by the audio processor."""
import json
from pathlib import Path
import shutil
import time
import numpy as np
import torch
from scipy.io import wavfile
from scipy.signal import butter,lfilter,resample_poly,sawtooth,square
from features import log_mel
from generate_dataset import ROOT,sha256,provenance
from initializer_experiment import Initializer,search,write
from metrics import to_physical
from reference_match import envelope_guess
from inspect_dataset import read_audio

RUN=ROOT/'ml/runs/hybrid_match'
DATA=ROOT/'ml/data/initializer_3000'
MODEL=ROOT/'ml/runs/initializer_experiment/model/best.pt'

def hybrid_seed(predicted,waveform,audio):
    attack,release=envelope_guess(resample_poly(audio,1,2)[2400:],1.4)
    return {'cutoff':float(predicted[0]),'waveform':int(waveform),'attack':attack,'release':release}

def fixtures():
    rng=np.random.default_rng(20261027);rows=[];rate=44100;t=np.arange(rate*4)/rate;u=t-.1
    for wave in range(4):
        for index in range(4):
            note=int(rng.integers(48,73));cutoff=float(np.exp(rng.uniform(np.log(150),np.log(8000))))
            attack=float(rng.uniform(.015,.4));release=float(rng.uniform(.04,1.1));sustain=float(rng.uniform(.45,.9));decay=float(rng.uniform(.04,.2));gain=float(rng.uniform(.07,.16))
            env=np.where(u<attack,np.clip(u/attack,0,1),sustain+(1-sustain)*np.clip(1-(u-attack)/decay,0,1))
            env=np.where(u>=1.4,sustain*np.clip(1-(u-1.4)/release,0,1),env);env[u<0]=0
            phase=2*np.pi*440*2**((note-69)/12)*np.maximum(u,0)
            osc=[lambda:np.sin(phase),lambda:sawtooth(phase),lambda:square(phase),lambda:sawtooth(phase,width=.5)][wave]()
            b,a=butter(2,cutoff,fs=rate);mono=lfilter(b,a,gain*osc*env);stereo=np.stack([mono,mono*.85],axis=1).astype(np.float32)
            rows.append(({'id':f'fixture_{wave}_{index}','note':note,'source_waveform':wave,'source_cutoff_Hz':cutoff,'source_attack_s':attack,'source_release_s':release,'source_sustain':sustain,'source_decay_s':decay,'source_gain':gain},stereo))
    return rows

def matched_audio(folder,result):
    for path in sorted(folder.glob('*/render_receipts.json')):
        for row in json.loads(path.read_text())['examples']:
            if row['applied_parameters']==result['parameters']:
                return read_audio(path.parent/row['audio'])[1]
    raise ValueError('Selected candidate missing')

def main():
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    RUN.mkdir(parents=True,exist_ok=False);(RUN/'references').mkdir();(RUN/'listen').mkdir()
    source=json.loads((DATA/'manifest.json').read_text());config=source['metadata']['config'];spec=json.loads((DATA/'parameter_spec.json').read_text())
    stats=json.loads((DATA/'preprocessing.json').read_text());assert stats['source_split']=='train'
    mean=np.array(stats['mean_per_mel'],dtype=np.float32)[None,:,None];std=np.array(stats['std_per_mel'],dtype=np.float32)[None,:,None]
    identity={'checkpoint_sha256':sha256(MODEL),'preprocessing_sha256':sha256(DATA/'preprocessing.json'),'protocol_sha256':sha256(ROOT/'ml/HYBRID_MATCH_PROTOCOL.md'),'provenance':provenance(),'seed':20261027,'torch':torch.__version__}
    write(RUN/'run.json',identity)
    model=Initializer();model.load_state_dict(torch.load(MODEL,weights_only=True,map_location='cpu')['state_dict']);model.eval()
    prepared=[];forward=[]
    for meta,stereo in fixtures():
        identifier=meta['id'];wavfile.write(RUN/'references'/f'{identifier}.wav',44100,stereo)
        audio=resample_poly(stereo.astype(np.float64).mean(1),160,147)[:192000]
        assert np.isfinite(audio).all() and np.max(np.abs(audio))<1
        feature=log_mel(audio,48000,config['features'])
        before=time.perf_counter()
        with torch.inference_mode(): p,w=model(torch.from_numpy(((feature-mean)/std)[None].copy()))
        forward.append((time.perf_counter()-before)*1000)
        hybrid=hybrid_seed(to_physical(p.numpy(),spec)[0],w.argmax(1)[0],audio)
        dsp=dict(hybrid,cutoff=12000.,waveform=1)
        prepared.append((meta,audio,{'dsp':dsp,'hybrid':hybrid}))
    write(RUN/'frozen_inputs.json',[dict(meta,seeds=seeds) for meta,audio,seeds in prepared])
    results=[];key={};page=['<!doctype html><meta charset="utf-8"><title>Hybrid matching blind listening</title><style>body{font:17px system-ui;background:#14191f;color:#e8edf2;max-width:950px;margin:32px auto}section{padding:18px;border:1px solid #456;margin:18px 0}audio{width:260px}label{display:inline-block;margin:10px}</style><h1>参考音匹配：盲听 A / B</h1><p>先听 Reference，再听 A/B，记录偏好或无明显差别。标签已随机；这里没有显示算法分数。均为合成参考，不是真实录音。</p><p>两个候选使用相同播放增益；评分仍使用原始渲染。尚未进行人工听感评估。</p>']
    rng=np.random.default_rng(20261028)
    for meta,audio,seeds in prepared:
        identifier=meta['id'];row={'id':identifier,'methods':{}}
        for method,seed in seeds.items():
            folder=RUN/'search'/identifier/method
            row['methods'][method]=search(audio,dict(config['fixed_parameters']),seed,meta['note'],config,spec,folder)
            receipts=list(folder.glob('*/render_receipts.json'))
            assert sum(len(json.loads(p.read_text())['examples']) for p in receipts)==52
        candidates={method:matched_audio(RUN/'search'/identifier/method,result) for method,result in row['methods'].items()}
        gain=.7/max(np.max(np.abs(x)) for x in candidates.values())
        methods=list(rng.permutation(['dsp','hybrid']));key[identifier]=dict(zip(['A','B'],methods))
        section=f'<section><h2>{identifier}</h2><label>Reference<br><audio controls src="references/{identifier}.wav"></audio></label>'
        for label,method in zip(['A','B'],methods):
            samples=(candidates[method]*gain).astype(np.float32);assert np.max(np.abs(samples))<1 and np.isfinite(samples).all()
            wavfile.write(RUN/'listen'/f'{identifier}_{label}.wav',48000,samples)
            section+=f'<label>{label}<br><audio controls src="listen/{identifier}_{label}.wav"></audio></label>'
        page.append(section+'</section>');results.append(row);write(RUN/'per_example.json',results)
        print(identifier,{k:v['final_score'] for k,v in row['methods'].items()},flush=True)
    summary={}
    for method in ['dsp','hybrid']:
        scores=[r['methods'][method]['final_score'] for r in results]
        summary[method]={'mean':float(np.mean(scores)),'median':float(np.median(scores)),'mean_seconds':float(np.mean([r['methods'][method]['seconds'] for r in results]))}
    delta=np.array([r['methods']['hybrid']['final_score']-r['methods']['dsp']['final_score'] for r in results])
    summary['paired']={'hybrid_wins':int((delta<-1e-9).sum()),'ties':int((np.abs(delta)<=1e-9).sum()),'hybrid_losses':int((delta>1e-9).sum()),'mean_hybrid_minus_dsp':float(delta.mean())}
    assert sha256(MODEL)==identity['checkpoint_sha256']
    assert provenance()['plugin_source_sha256']==identity['provenance']['plugin_source_sha256']
    summary.update(actual_render_count=16*2*52,checkpoint_unchanged=True,plugin_sources_unchanged=True,forward_ms_including_cold_first={'mean':float(np.mean(forward)),'median':float(np.median(forward))},human_listening_results=None)
    write(RUN/'results.json',summary);write(RUN/'blind_key.json',key);(RUN/'index.html').write_text('\n'.join(page))
    lines=['# Frozen-model hybrid matching validation','','16 new independent SciPy references; no fitting, no reuse of old test predictions. Development validation, not a final generalization benchmark.','','| Method | Mean distance ↓ | Median distance ↓ | Mean search seconds | Renders/reference |','|---|---:|---:|---:|---:|']
    for method in ['dsp','hybrid']:
        m=summary[method];lines.append(f"| {method} | {m['mean']:.12g} | {m['median']:.12g} | {m['mean_seconds']:.12g} | 52 |")
    lines+=['',json.dumps(summary['paired']),f"\nActual rendered candidates: {summary['actual_render_count']}. Frozen checkpoint/preprocessing; unchanged plugin sources.",f"\nOffline forward timings (ms, cold first included; 16 examples): {summary['forward_ms_including_cold_first']}. Excludes feature extraction/search; no real-time claim.",'','The objective is log-mel RMSE + 2 envelope RMSE. Known pitch/gate are shared conditions; source nuisance labels never seed search. The hybrid uses CNN waveform/cutoff and the exact same DSP envelope seed as the baseline. Lower distance does not establish listening preference. Independent Butterworth fixtures do not establish arbitrary real-recording transfer.','', 'Blind listening page: ml/runs/hybrid_match/index.html; mapping is separate in blind_key.json. No human preference numbers have been measured. All initializers, source settings and paired outcomes are retained. No plugin deployment or additional tuning followed this run.']
    (ROOT/'ml/HYBRID_MATCH_RESULTS.md').write_text('\n'.join(lines)+'\n');print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
