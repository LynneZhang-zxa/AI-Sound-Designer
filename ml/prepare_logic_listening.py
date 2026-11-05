"""Create level-matched listening copies; never alter raw audio or matching scores."""
import json
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import welch
from generate_dataset import ROOT,sha256
from hybrid_match import matched_audio


def rms(audio):
    return float(np.sqrt(np.mean(np.asarray(audio,dtype=np.float64)**2)))


def match_levels(signals,rate):
    # Identical held-note window; excludes silence and differing release lengths.
    window=slice(round(.1*rate),round(1.5*rate))
    levels={k:rms(a[window]) for k,a in signals.items()}
    if any(not np.isfinite(v) or v<=1e-8 for v in levels.values()): raise ValueError('Silent/nonfinite comparison')
    target=levels['Reference'];gains={k:target/v for k,v in levels.items()}
    peak=max(float(np.max(np.abs(signals[k])))*gains[k] for k in signals)
    headroom=min(1.,.95/peak)
    gains={k:v*headroom for k,v in gains.items()}
    copies={k:(a*gains[k]).astype(np.float32) for k,a in signals.items()}
    for a in copies.values():
        if not np.isfinite(a).all() or np.max(np.abs(a))>.950001: raise ValueError('Invalid listening copy')
    return copies,{'method':'RMS matching over common held-note window; not LUFS or perceptual loudness equivalence',
                   'window_seconds':[.1,1.5],'input_rms':levels,'linear_gains':gains,'common_headroom_gain':headroom,
                   'output_rms':{k:rms(a[window]) for k,a in copies.items()}}


def spectral(audio,rate):
    freq,power=welch(audio[rate:round(1.4*rate)],fs=rate,nperseg=4096)
    return {'held_centroid_Hz':float(np.sum(freq*power)/power.sum()),'power_fraction_above_2kHz':float(power[freq>=2000].sum()/power.sum())}


def main():
    run=ROOT/'ml/runs/logic_es1_match';out=run/'level_matched';out.mkdir(exist_ok=False)
    preserved={p:sha256(run/p) for p in ['reference.wav','A.wav','B.wav','results.json','blind_key.json']}
    rate,encoded=wavfile.read(run/'reference.wav');ref=encoded.astype(np.float64)/2147483648.
    if ref.ndim==2: ref=ref.mean(1)
    results=json.loads((run/'results.json').read_text());key=json.loads((run/'blind_key.json').read_text())
    signals={'Reference':ref,**{label:matched_audio(run/method,results[method]) for label,method in key.items()}}
    assert rate==48000 and all(a.shape==(192000,) for a in signals.values())
    copies,audit=match_levels(signals,rate)
    audit.update(raw_files_sha256=preserved,raw_AB_samples_identical=bool(np.array_equal(signals['A'],signals['B'])),
                 old_listening_AB_files_identical=preserved['A.wav']==preserved['B.wav'],
                 raw_AB_max_absolute_difference=float(np.max(np.abs(signals['A']-signals['B']))),
                 spectral={k:spectral(a,rate) for k,a in signals.items()},
                 user_feedback_before_alignment='A/B louder than reference; A seemed closer but brighter. Preliminary feedback, not a controlled preference win.')
    for k,a in copies.items(): wavfile.write(out/f'{k}.wav',rate,a)
    (out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    page=['<!doctype html><meta charset="utf-8"><title>Logic ES1 · Level-matched listening</title><style>body{font:18px system-ui;background:#151b22;color:#eee;max-width:850px;margin:40px auto}audio{width:100%}section{margin:24px 0;padding:16px;border:1px solid #456}</style><h1>Logic ES1：修正试听音量</h1><p>Reference、A、B 已在相同持音区间（0.1–1.5 秒）做 RMS 电平对齐，统一单声道。未做 EQ、压缩或重新搜索；原始音频和分数保留。RMS 对齐不等于精确的感知响度一致。</p>']
    if audit['raw_AB_samples_identical']: page.append('<p><strong>核实结果：A 与 B 的原始渲染逐采样相同。</strong>此处比较重点是 Reference 与匹配结果，不应将 A/B 听感差异作为算法胜负。</p>')
    for name in copies: page.append(f'<section><h2>{name}</h2><audio controls preload="metadata" src="{name}.wav"></audio></section>')
    (out/'index.html').write_text('\n'.join(page))
    assert all(sha256(run/p)==digest for p,digest in preserved.items())
    print(json.dumps(audit,indent=2))

if __name__=='__main__': main()
