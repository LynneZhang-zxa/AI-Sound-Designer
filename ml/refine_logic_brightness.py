"""One user-directed cutoff audition, not another model evaluation."""
import copy
import json
import subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly
from generate_dataset import ROOT,sha256,provenance
from inspect_dataset import read_audio
from initializer_experiment import write
from prepare_logic_listening import match_levels,spectral
from reference_match import representation,objective


def main():
    previous=ROOT/'ml/runs/logic_es1_match';out=previous/'cutoff_audition';out.mkdir(exist_ok=False)
    source=previous/'reference.wav';original_hashes={name:sha256(previous/name) for name in ['reference.wav','results.json','A.wav','B.wav']}
    spec=json.loads((ROOT/'ml/data/initializer_3000/parameter_spec.json').read_text())
    config=copy.deepcopy(json.loads((ROOT/'ml/data/initializer_3000/manifest.json').read_text())['metadata']['config'])
    info=json.loads((previous/'protocol_and_source.json').read_text());config['renderer'].update(midi_note=info['note'],velocity=.8)
    base=json.loads((previous/'results.json').read_text())['dsp']['parameters'];rows=[]
    # A short, predeclared downward sweep. Listening feedback is not mapped to a percentage formula.
    for i,factor in enumerate([1.,.9,.8,.7,.6]):
        p=dict(base,cutoff=base['cutoff']*factor)
        rows.append({'id':f'candidate_{i}','split':'validation','requested_parameters':p})
    manifest={'metadata':{'config':config,'parameter_specification':spec},'examples':rows}
    write(out/'manifest.json',manifest)
    write(out/'protocol.json',{'purpose':'subjective feedback: still about 10% too bright after RMS matching','cutoff_factors':[1,.9,.8,.7,.6],
          'all_other_parameters_fixed':True,'note':info['note'],'gate_s':info['gate_s'],'training':False,'not_a_held_out_evaluation':True,
          'provenance':provenance(),'previous_hashes':original_hashes,'renderer_sha256':sha256(ROOT/'build/DatasetRenderer')})
    with (out/'renderer.log').open('w') as log:
        subprocess.run([str(ROOT/'build/DatasetRenderer'),'--render',str(out/'manifest.json'),str(out)],check=True,stdout=log,stderr=subprocess.STDOUT)
    rate,encoded=wavfile.read(source);reference=encoded.astype(np.float64)/2147483648.
    if reference.ndim==2: reference=reference.mean(1)
    signals={'Reference':reference};receipts=json.loads((out/'render_receipts.json').read_text())['examples'];assert len(receipts)==5
    for i,row in enumerate(receipts):
        actual=row['applied_parameters']
        for key,value in base.items():
            if key!='cutoff': np.testing.assert_allclose(actual[key],value,rtol=3e-6,atol=1e-7)
        _,signals[f'Option{i}']=read_audio(out/row['audio'])
    copies,levels=match_levels(signals,rate)
    original=wavfile.read(previous/'level_matched/A.wav')[1]
    np.testing.assert_allclose(copies['Option0'],original,rtol=1e-6,atol=1e-8)
    ref=representation(resample_poly(reference,1,2)[2400:],96000);measurements=[]
    for i,row in enumerate(receipts):
        key=f'Option{i}';wave=signals[key]
        measurements.append({'label':key,'cutoff_Hz':row['applied_parameters']['cutoff'],**spectral(wave,rate),
            **objective(ref,representation(resample_poly(wave,1,2)[2400:],96000))})
    write(out/'measurements.json',{'candidates':measurements,'levels':levels,'actual_renders':5,'preference_selected':None})
    html=['<!doctype html><meta charset="utf-8"><title>Logic ES1 · Cutoff audition</title><style>body{font:18px system-ui;background:#151b22;color:#eee;max-width:850px;margin:40px auto}section{border:1px solid #456;padding:16px;margin:16px 0}audio{width:100%}</style><h1>ES1：降低亮度试听</h1><p>只改变 cutoff；起音、尾音、波形等保持不变。所有音频按相同持音区间对齐 RMS 电平。选项 0 是原匹配结果，1–4 的 cutoff 依次降低。降低 cutoff 不保证等比例降低感知亮度。</p><p>请先听 Reference，再选最接近的一档；也可以选择“都不像”。这里没有训练或自动替换插件参数。</p>']
    for key,wave in copies.items():
        wavfile.write(out/f'{key}.wav',rate,wave)
        title='Reference' if key=='Reference' else ('选项 0 · 原结果' if key=='Option0' else '选项 '+key[-1])
        html.append(f'<section><h2>{title}</h2><audio controls preload="metadata" src="{key}.wav"></audio></section>')
    (out/'index.html').write_text('\n'.join(html))
    assert all(sha256(previous/name)==digest for name,digest in original_hashes.items())
    print(json.dumps(measurements,indent=2))

if __name__=='__main__': main()
