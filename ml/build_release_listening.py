"""Build a reference/legacy/v2 listening comparison from saved renders only."""
import json
import shutil
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from generate_dataset import ROOT
from hybrid_match import matched_audio
from inspect_dataset import read_audio
from prepare_logic_listening import match_levels,spectral


def main():
    result=json.loads((ROOT/'build/reference-v2-logic-result.json').read_text());folder=ROOT/'ml/runs/initial_release_listening';folder.mkdir(exist_ok=False)
    legacy=ROOT/'ml/runs/logic_es1_match';rate,encoded=wavfile.read(legacy/'reference.wav');ref=encoded.astype(np.float64).mean(1)/2147483648.
    old=matched_audio(legacy/'dsp',json.loads((legacy/'results.json').read_text())['dsp'])
    rate,new=read_audio(Path(result['artifacts'])/'matched.wav')
    frames=max(len(ref),len(old),len(new));signals={k:np.pad(a,(0,frames-len(a))) for k,a in {'Reference':ref,'Previous':old,'New':new}.items()}
    copies,levels=match_levels(signals,rate)
    for name,audio in copies.items():wavfile.write(folder/f'{name}.wav',rate,audio)
    metrics={'v2_result':result,'levels':levels,'spectral':{name:spectral(a,rate) for name,a in signals.items()},'human_listening_verdict':None,'not_blind':'Named previous/new development comparison; not a preference evaluation.'}
    (folder/'measurements.json').write_text(json.dumps(metrics,indent=2)+'\n')
    shutil.copy2(ROOT/'build/plugin-assistant-preview.png',folder/'plugin.png')
    page=['<!doctype html><meta charset="utf-8"><title>Resonanca · Initial release check</title><style>body{font:18px system-ui;background:#131920;color:#edf3f5;max-width:1000px;margin:40px auto}section{padding:18px;border:1px solid #405461;margin:18px 0}audio,img{width:100%}code{color:#65e2c1}</style><h1>Resonanca：初版验收</h1><p>真实 Logic ES1 参考音、旧匹配与新版匹配。只用于开发试听；没有人工胜负结论，也没有把旧评分与新评分直接比较。</p><p>三段均按 0.1–1.5 秒持音区间对齐 RMS 电平，统一单声道。参考和旧结果仅补静音以统一时长，原始文件保留。</p>']
    for name,title in [('Reference','Reference · Logic ES1'),('Previous','Previous · 旧匹配'),('New','New · 新版完整音色搜索')]:page.append(f'<section><h2>{title}</h2><audio controls preload="metadata" src="{name}.wav"></audio></section>')
    page+=['<h2>插件多参数提案界面</h2><img src="plugin.png" alt="Actual JUCE editor test snapshot"><p>预览、Apply、Undo、过期提案保护已测试。实时 OpenAI 和 Logic 内新版验收要单独完成。</p>']
    (folder/'index.html').write_text('\n'.join(page));print(json.dumps(metrics['spectral'],indent=2))

if __name__=='__main__':main()
