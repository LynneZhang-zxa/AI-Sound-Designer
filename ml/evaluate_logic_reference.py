"""Evaluate the actual Logic ES1 bounce offline without training or deployment."""
import json
import shutil
import numpy as np
import torch
from scipy.io import wavfile
from generate_dataset import ROOT,sha256,provenance
from hybrid_match import DATA,MODEL,hybrid_seed,matched_audio
from initializer_experiment import Initializer,search,write
from features import log_mel
from metrics import to_physical
from reference_match import load_reference,estimate_note
from inspect_dataset import read_audio


def main():
    source=ROOT/'ml/references/logic_es1/ES1Warm.wav';run=ROOT/'ml/runs/logic_es1_match'
    if run.exists() and any(run.iterdir()): raise FileExistsError('Refusing to overwrite existing evaluation')
    run.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    metadata=json.loads((DATA/'manifest.json').read_text())['metadata'];config=metadata['config'];spec=json.loads((DATA/'parameter_spec.json').read_text())
    rate,encoded=wavfile.read(source)
    if encoded.dtype!=np.int32: raise ValueError('Expected Logic PCM24 WAV')
    audio=encoded.astype(np.float64)/2147483648.
    if audio.ndim==2: audio=audio.mean(axis=1)
    if rate!=48000 or audio.shape!=(192000,) or not np.isfinite(audio).all() or np.abs(audio).max()>=1: raise ValueError('Invalid Logic bounce')
    trimmed,loading=load_reference(source);note,pitch=estimate_note(trimmed,1.4)
    record={'reference_sha256':sha256(source),'checkpoint_sha256':sha256(MODEL),'preprocessing_sha256':sha256(DATA/'preprocessing.json'),'provenance':provenance(),'source':'Logic Pro ES1, manually configured dry patch, real host bounce','gate_s':1.4,'note':note,'pitch_detection':pitch,'loading':loading,'source_peak':float(np.abs(audio).max()),'source_rms':float(np.sqrt(np.mean(audio**2))),'comparison':'single development case, 52 renders per method, no tuning or training'}
    write(run/'protocol_and_source.json',record)
    stats=json.loads((DATA/'preprocessing.json').read_text());assert stats['source_split']=='train'
    mean=np.array(stats['mean_per_mel'],dtype=np.float32)[None,:,None];std=np.array(stats['std_per_mel'],dtype=np.float32)[None,:,None]
    model=Initializer();model.load_state_dict(torch.load(MODEL,weights_only=True,map_location='cpu')['state_dict']);model.eval()
    feature=log_mel(audio,rate,config['features'])
    with torch.inference_mode(): p,w=model(torch.from_numpy(((feature-mean)/std)[None].copy()))
    seed=hybrid_seed(to_physical(p.numpy(),spec)[0],w.argmax(1)[0],audio)
    seeds={'dsp':dict(seed,cutoff=12000.,waveform=1),'hybrid':seed};write(run/'frozen_seeds.json',seeds)
    results={};candidates={}
    for method,initial in seeds.items():
        folder=run/method;results[method]=search(audio,dict(config['fixed_parameters']),initial,note,config,spec,folder)
        assert sum(len(json.loads(p.read_text())['examples']) for p in folder.glob('*/render_receipts.json'))==52
        candidates[method]=matched_audio(folder,results[method])
        write(run/'results.json',results)
    assert sha256(MODEL)==record['checkpoint_sha256']
    assert provenance()['plugin_source_sha256']==record['provenance']['plugin_source_sha256']
    shutil.copy2(source,run/'reference.wav')
    gain=.7/max(np.abs(a).max() for a in candidates.values())
    methods=list(np.random.default_rng(20261029).permutation(['dsp','hybrid']));write(run/'blind_key.json',dict(zip(['A','B'],methods)))
    page=['<!doctype html><meta charset="utf-8"><title>Logic ES1 reference matching</title><style>body{font:18px system-ui;background:#151b22;color:#eee;max-width:900px;margin:40px auto}audio{width:100%;margin:10px 0}</style><h1>Logic ES1：参考与匹配结果</h1><p>真实 Logic ES1 导出；单个开发案例，没有训练或模型更新。先听 Reference，再比较隐藏方法名称的 A/B。两个候选使用相同播放增益。</p><h2>Reference</h2><audio controls src="reference.wav"></audio>']
    for label,method in zip(['A','B'],methods):
        wavfile.write(run/f'{label}.wav',48000,(candidates[method]*gain).astype(np.float32));page.append(f'<h2>{label}</h2><audio controls src="{label}.wav"></audio>')
    (run/'index.html').write_text('\n'.join(page))
    lines=['# Actual Logic ES1 reference: development comparison','','Source: ES1Warm.wav bounced by Logic Pro, 48kHz 24-bit stereo, four seconds, Normalize Off. Dry ES1 patch, chorus/LFO/analog drift disabled. MIDI 60 stimulus with ES1 octave setting 4\'; audio pitch detected as MIDI %d. Shared gate 1.4s; no target-derived parameter seed.'%note,'','| Method | Initial distance | Final distance ↓ | Search seconds | Actual renders |','|---|---:|---:|---:|---:|']
    for method,r in results.items(): lines.append(f"| {method} | {r['initial_score']:.12g} | {r['final_score']:.12g} | {r['seconds']:.12g} | {r['renders']} |")
    lines+=['','Distance = log-mel RMSE + 2 envelope RMSE. This single real host bounce is independent of the training renderer, but is still synthesized audio, not a musical recording. ES1 filter/envelope topology differs; exact original parameter recovery is not claimed. Both searches use the same fixed nuisance defaults and budget. Checkpoint/plugin sources unchanged. No training or deployment. Human listening preference remains unmeasured.','', 'Blind listening: ml/runs/logic_es1_match/index.html; complete initializers, candidate receipts, parameters, source hash and provenance retained. Only one actual Logic reference completed: subsequent UI access timed out after bounce; additional timbres remain pending.']
    (ROOT/'ml/LOGIC_REFERENCE_RESULTS.md').write_text('\n'.join(lines)+'\n');print(json.dumps(results,indent=2))

if __name__=='__main__': main()
