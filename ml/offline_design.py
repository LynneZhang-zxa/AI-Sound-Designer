"""Two-stage offline sound design: propose/review, then explicitly apply and render."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import urllib.request
import numpy as np
import torch
from analyze_wav import OfflineAnalyzer
from features import log_mel
from generate_dataset import ROOT, provenance, sha256
from inspect_dataset import read_audio

TARGETS=('cutoff','attack','release')
SERVICE='http://127.0.0.1:8765/propose'
STRENGTHS={'subtle':.5,'medium':1.,'strong':2.5}
STRENGTH_LABELS={'subtle':'轻微','medium':'适中','strong':'明显'}


def save(path,value):
    with Path(path).open('x') as stream: json.dump(value,stream,indent=2,allow_nan=False)


def checked_parameters(values,config,spec):
    if not isinstance(values,dict) or set(values)!=set(TARGETS): raise ValueError('Expected exactly three targets')
    result={}
    for key,value in values.items():
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
            raise ValueError('Invalid numeric parameter')
        low,high=config['sampling'][key];p=spec['parameters'][key]
        result[key]=min(high,p['maximum'],max(low,p['minimum'],value))
    return result


def constrain_updates(updates,before,config,spec):
    if not isinstance(updates,dict): raise ValueError('Expected parameter update object')
    ignored=[];after=dict(before)
    for key,value in updates.items():
        if key not in spec['parameters'] or isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('Unknown or nonfinite service parameter')
        if key in TARGETS: after[key]=value
        else: ignored.append(key)
    after=checked_parameters(after,config,spec)
    return after,ignored


def rules(prompt,before):
    text=prompt.lower();result={}
    if any(word in text for word in ['darker','warmer','暗','暖']): result['cutoff']=before['cutoff']*.6
    if any(word in text for word in ['brighter','亮']): result['cutoff']=before['cutoff']*1.5
    if any(word in text for word in ['shorter','短']): result['release']=before['release']*.6
    if any(word in text for word in ['longer','长']): result['release']=before['release']*1.5
    return result


def scale_strength(before,proposed,strength,config,spec):
    """Scale multiplicative movement: equal ratios are natural for Hz and time."""
    if strength not in STRENGTHS: raise ValueError('Unknown strength')
    start=checked_parameters(before,config,spec)
    target=checked_parameters(proposed,config,spec)
    factor=STRENGTHS[strength]
    scaled={key:start[key]*math.exp(factor*math.log(target[key]/start[key])) for key in TARGETS}
    return checked_parameters(scaled,config,spec)


def request_service(prompt,snapshot):
    # Executed only in a background worker of this standalone Python process.
    request=urllib.request.Request(SERVICE,data=json.dumps({'prompt':prompt+'\nOnly change cutoff, attack and release; preserve all other parameters.',
                                     'parameters':snapshot},allow_nan=False).encode(),
                                   headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=45) as response:
        content=response.read(16385)
    if len(content)>16384: raise ValueError('Oversized response')
    result=json.loads(content)
    return result.get("proposal",result) if isinstance(result,dict) else result


def proposal(prompt,before,config,spec,local_only=False):
    if not isinstance(prompt,str) or not 0<len(prompt.strip())<=1800: raise ValueError('Prompt must be 1..1800 characters')
    failure=None
    if not local_only:
        try:
            snapshot=dict(config['fixed_parameters'],**before)
            with ThreadPoolExecutor(max_workers=1) as worker:
                updates=worker.submit(request_service,prompt,snapshot).result()
            after,ignored=constrain_updates(updates,before,config,spec)
            return after,{'source':'AI service','ignored_non_target_parameters':ignored,'requested_updates':updates}
        except (OSError,ValueError,TypeError): failure='AI service unavailable or invalid response; local rules used'
    updates=rules(prompt,before);after,ignored=constrain_updates(updates,before,config,spec)
    return after,{'source':'local rules','fallback_reason':failure,'ignored_non_target_parameters':ignored,'requested_updates':updates}


def render(folder,values,config,spec,performance,renderer):
    folder.mkdir(parents=True,exist_ok=False)
    row={'id':'render','split':'validation','requested_parameters':dict(config['fixed_parameters'],**values),
         'requested_performance':performance}
    manifest={'metadata':{'config':config,'parameter_specification':spec},'examples':[row]}
    source=folder/'manifest.json';save(source,manifest)
    with (folder/'renderer.log').open('w') as log:
        subprocess.run([str(renderer),'--render',str(source),str(folder)],stdout=log,stderr=subprocess.STDOUT,check=True)
    receipt=json.loads((folder/'render_receipts.json').read_text())['examples'][0]
    for key,value in row['requested_parameters'].items():
        if not np.isclose(value,receipt['applied_parameters'][key],rtol=3e-6,atol=1e-7): raise ValueError('Incorrect render readback')
    if receipt['midi_note']!=performance['midi_note']: raise ValueError('Pitch mismatch')
    return folder/receipt['audio'],receipt


def distance(reference,candidate,config):
    rate,a=read_audio(reference);other_rate,b=read_audio(candidate)
    if rate!=other_rate or a.shape!=b.shape: raise ValueError('Incompatible audio comparison')
    features_a=log_mel(a,rate,config['features']);features_b=log_mel(b,rate,config['features'])
    return {'log_mel_rmse':float(np.sqrt(np.mean((features_a.astype(np.float64)-features_b)**2))),
            'scope':'Full four-second log-mel arrays, absolute levels, no normalization or alignment.',
            'interpretation':'Technical spectral difference only; not a perceptual quality or preference score.'}


def write_page(folder,plan,applied=None):
    rows=''.join(f'<tr><td>{k}</td><td>{plan["before"][k]:.6g}</td><td>{plan["after"][k]:.6g}</td><td>{"Hz" if k=="cutoff" else "s"}</td></tr>' for k in TARGETS)
    digest=sha256(folder/'proposal.json')
    import shlex
    command=shlex.join(['ml/.venv/bin/python','ml/offline_design.py','apply',str(folder),'--approve-sha256',digest])
    strength=plan.get('strength','medium')
    strength_text=STRENGTH_LABELS[strength]
    modified='' if applied is None else '<h2>Modified render</h2><audio controls src="modified/audio/render.wav"></audio>'
    metrics=plan['reconstruction_distance'] if applied is None else applied['reconstruction_distance']
    content=f'''<!doctype html><meta charset="utf-8"><title>Offline sound design</title>
<style>body{{font:16px system-ui;max-width:960px;margin:40px auto;padding:20px;background:#11171c;color:#e6eeef}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #35434c}}h1,h2{{color:#65e2c1}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#1c252c;padding:18px}}audio{{width:100%}}p{{line-height:1.6}}</style>
<h1>离线声音设计 / Offline sound design</h1><p>Intent: {html.escape(plan['prompt'])}</p>
<p>修改强度 / Strength: {strength_text} ({strength}).</p>
<p>Proposal source: {html.escape(plan['proposal_source']['source'])}. {html.escape(plan['proposal_source'].get('fallback_reason') or '')}</p>
<table><tr><th>Parameter</th><th>Estimated / constrained before</th><th>Proposed after</th><th>Unit</th></tr>{rows}</table>
<h2>Original input</h2><audio controls src="original.wav"></audio>
<h2>Reconstruction from estimated parameters</h2><audio controls src="reconstruction/audio/render.wav"></audio>{modified}
<p>Original vs reconstruction log-mel RMSE: {metrics['log_mel_rmse']:.9g}. This measures technical difference, not perceived quality.</p>
<p>Known MIDI note {plan['performance']['midi_note']}, velocity argument {plan['performance']['velocity']}. These are supplied, not inferred. Other synth parameters remain fixed. Playback is not loudness normalized.</p>
<p>仅支持实验条件内的四秒单音锯齿波。估计参数重新合成的声音可能与原音频不同。修改后的声音以重建音频为起点，而非直接处理原音频。</p>
<p>{html.escape(plan['limitations'])}</p>
<h2>{'Applied via explicit CLI command' if applied else 'Review before applying'}</h2>
<p>试听原音频与重建音频，检查参数表。确认后在 canonical repository 的 Terminal 执行下列命令，才会渲染修改后的声音：</p><pre>{html.escape(command)}</pre>
<p>SHA-256 binds the command to these exact proposal bytes. No automatic plugin changes. <a href="proposal.json">Proposal JSON</a></p>'''
    (folder/'index.html').write_text(content)


def create_proposal(args):
    folder=args.output.resolve();renderer=args.renderer.resolve()
    if not folder.is_relative_to(ROOT): raise ValueError('Output must stay in canonical repository')
    if folder.exists(): raise FileExistsError(folder)
    if not 48<=args.midi_note<=60 or not .4<=args.velocity<=1: raise ValueError('Unsupported MIDI performance')
    torch.set_num_threads(4)
    analyzer=OfflineAnalyzer(args.run);rate,audio=read_audio(args.wav)
    analysis,_=analyzer.predict(rate,audio)
    before=checked_parameters(analysis['predictions']['hybrid']['physical'],analyzer.config,analyzer.spec)
    performance={'midi_note':args.midi_note,'velocity':args.velocity}
    after,source=proposal(args.prompt,before,analyzer.config,analyzer.spec,args.local_only)
    base_after=dict(after)
    after=scale_strength(before,base_after,args.strength,analyzer.config,analyzer.spec)
    folder.mkdir(parents=True)
    shutil.copyfile(args.wav,folder/'original.wav')
    reconstruction,receipt=render(folder/'reconstruction',before,analyzer.config,analyzer.spec,performance,renderer)
    plan={'schema_version':1,'prompt':args.prompt,'strength':args.strength,
          'strength_factor':STRENGTHS[args.strength],'base_proposed_after':base_after,'before':before,'after':after,'analysis':analysis,
          'proposal_source':source,'performance':performance,'config':analyzer.config,'parameter_specification':analyzer.spec,
          'input_sha256':sha256(folder/'original.wav'),'renderer_sha256':sha256(renderer),
          'reconstruction_sha256':sha256(reconstruction),'reconstruction_readbacks':receipt,
          'reconstruction_distance':distance(folder/'original.wav',reconstruction,analyzer.config),
          'limitations':analysis['limitations'],'source_provenance':provenance()}
    save(folder/'proposal.json',plan);write_page(folder,plan)
    print(json.dumps({'source':source,'before':before,'after':after,'reconstruction_distance':plan['reconstruction_distance']},indent=2))
    print('Review report:',folder/'index.html')
    print('Proposal SHA-256:',sha256(folder/'proposal.json'))


def apply(folder,approved_hash,renderer):
    folder=Path(folder).resolve();renderer=Path(renderer).resolve()
    if not folder.is_relative_to(ROOT): raise ValueError('Session must remain in canonical repository')
    path=folder/'proposal.json'
    if sha256(path)!=approved_hash: raise ValueError('Proposal differs from the reviewed SHA-256')
    if (folder/'modified').exists(): raise FileExistsError('Proposal already applied; create a new session')
    plan=json.loads(path.read_text());config=plan['config'];spec=plan['parameter_specification']
    for key in ['before','after']:
        if checked_parameters(plan[key],config,spec)!=plan[key]: raise ValueError('Invalid proposal range')
    if sha256(renderer)!=plan['renderer_sha256']: raise ValueError('Renderer changed since proposal')
    if sha256(folder/'original.wav')!=plan['input_sha256'] or sha256(folder/'reconstruction/audio/render.wav')!=plan['reconstruction_sha256']:
        raise ValueError('Session audio changed since review')
    audio,receipt=render(folder/'modified',plan['after'],config,spec,plan['performance'],renderer)
    result={'approved_proposal_sha256':approved_hash,'modified_readbacks':receipt,
            'modified_audio_sha256':sha256(audio),'reconstruction_distance':plan['reconstruction_distance'],
            'modified_vs_reconstruction':distance(folder/'reconstruction/audio/render.wav',audio,config),
            'normalization':False,'plugin_modified':False}
    save(folder/'applied.json',result);write_page(folder,plan,result)
    print('Rendered approved proposal:',audio)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('propose');p.add_argument('wav',type=Path);p.add_argument('--prompt',required=True)
    p.add_argument('--midi-note',type=int,required=True);p.add_argument('--velocity',type=float,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--run',type=Path,default=ROOT/'ml/runs/pitch_velocity')
    p.add_argument('--strength',choices=tuple(STRENGTHS),default='medium',help='subtle=轻微, medium=适中, strong=明显');
    p.add_argument('--local-only',action='store_true');p.add_argument('--renderer',type=Path,default=ROOT/'build/DatasetRenderer')
    p=commands.add_parser('apply');p.add_argument('session',type=Path);p.add_argument('--approve-sha256',required=True)
    p.add_argument('--renderer',type=Path,default=ROOT/'build/DatasetRenderer')
    args=parser.parse_args()
    if args.command=='propose': create_proposal(args)
    else: apply(args.session,args.approve_sha256,args.renderer)


if __name__=='__main__': main()
