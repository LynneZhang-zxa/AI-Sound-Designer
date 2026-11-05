"""Product search v2: salience-weighted spectrum and full existing timbral controls.

Runs only in the external offline worker. Legacy experiments keep their original objective.
"""
import copy
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import numpy as np
from scipy.signal import resample_poly
from reference_match import load_reference,estimate_note,envelope_guess,representation
from generate_dataset import sha256
from inspect_dataset import read_audio

PATCH_KEYS=('waveform','cutoff','attack','decay','sustain','release','resonance')


def salient_objective(reference,candidate):
    # Natural log power. Limit comparison to an 80 dB power range below reference peak.
    # Fixed nonzero band weights preserve spectral differences while reducing the
    # influence of silent bands/PCM quantization. No learned weights or target labels.
    r,e=reference;c,ce=candidate
    r=np.asarray(r)[0];c=np.asarray(c)[0]
    floor=float(r.max())-np.log(1e8)
    r=np.maximum(r,floor);c=np.maximum(c,floor)
    band=np.exp((np.mean(r,axis=1)-np.max(np.mean(r,axis=1)))/4)
    band=np.maximum(band,.02)[:,None]
    # Envelope and spectrogram frame grids differ; derive spectral activity by interpolation.
    active=np.interp(np.linspace(0,1,r.shape[1]),np.linspace(0,1,len(e)),e)
    weights=band*np.maximum(active,.02)[None,:]
    spectral=float(np.sqrt(np.sum(weights*(r-c)**2)/np.sum(weights)))
    envelope=float(np.sqrt(np.mean((e-ce)**2)))
    return {'score':spectral+2*envelope,'salient_log_mel_rmse':spectral,'envelope_rmse':envelope}


class ReferenceMatcherV2:
    def __init__(self,renderer,config,spec,directory):
        self.renderer=Path(renderer);self.config=config;self.spec=spec;self.directory=Path(directory)

    def match(self,path,settings,gate,midi_note=None,*,initializer=None,budget=None,diagnostics=True):
        started=time.perf_counter()
        if budget is not None and (type(budget) is not int or not 33<=budget<=147):raise ValueError('Budget must be 33..147')
        if initializer is not None:
            if set(initializer)!=set(PATCH_KEYS):raise ValueError('Initializer must specify seven timbral controls')
            for key,value in initializer.items():
                p=self.spec['parameters'][key]
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value) or not p['minimum']<=value<=p['maximum']:raise ValueError('Invalid initializer')
            if initializer['waveform']!=round(initializer['waveform']):raise ValueError('Invalid waveform initializer')
        if isinstance(gate,bool) or not isinstance(gate,(int,float)) or not .15<=gate<=3: raise ValueError('Gate must be 0.15–3 seconds')
        if midi_note is not None and (type(midi_note) is not int or not 36<=midi_note<=84): raise ValueError('Invalid MIDI note')
        audio,metadata=load_reference(path)
        if midi_note is None:midi_note,pitch=estimate_note(audio,gate)
        else:pitch={'source':'user supplied'}
        attack,release=envelope_guess(audio,gate)
        config=copy.deepcopy(self.config);timing=config['renderer'];duration=max(4.,.1+gate+3.25,len(audio)/24000+.15)
        timing.update(sample_rate=48000,note_on_seconds=.1,note_off_seconds=.1+gate,duration_seconds=duration,midi_note=midi_note,velocity=.8)
        frames=round(duration*24000);ref=representation(audio,frames)
        self.directory.mkdir(parents=True,exist_ok=True);folder=self.directory/secrets.token_hex(12);folder.mkdir();shutil.copyfile(path,folder/'reference.wav')
        all_results=[];seen=set()
        def evaluate(vectors,stage):
            out=folder/stage;out.mkdir();rows=[]
            for vector in vectors:
                if budget is not None and len(all_results)+len(rows)>=budget:break
                p={k:min(self.spec['parameters'][k]['maximum'],max(self.spec['parameters'][k]['minimum'],float(v))) for k,v in dict(vector,gain=.8).items()}
                p['waveform']=round(p['waveform']);key=tuple(round(p[k],7) for k in sorted(p))
                if key in seen:continue
                seen.add(key);rows.append({'id':f'candidate_{len(rows):03d}','split':'validation','requested_parameters':p})
            if not rows:return []
            manifest={'metadata':{'config':config,'parameter_specification':self.spec},'examples':rows}
            (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
            with (out/'renderer.log').open('w') as log:
                subprocess.run([str(self.renderer),'--render',str(out/'manifest.json'),str(out)],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=40)
            results=[]
            for row in json.loads((out/'render_receipts.json').read_text())['examples']:
                rate,wave=read_audio(out/row['audio']);wave=resample_poly(wave,1,2)
                result={'parameters':row['applied_parameters'],'audio':str(out/row['audio']),**salient_objective(ref,representation(wave[2400:],frames))}
                results.append(result)
            all_results.extend(results);return results
        # An RMS ratio estimates sustain from waveform only; no source parameter labels.
        rate=24000;window=round(.02*rate)
        from scipy.ndimage import uniform_filter1d
        env=np.sqrt(np.maximum(0,uniform_filter1d(audio**2,window,mode='constant')))
        peak=float(env[:round(gate*rate)].max());held=float(np.median(env[round(.7*gate*rate):round(.95*gate*rate)]))
        sustain=float(np.clip(held/max(peak,1e-12),.05,1.))
        seed=dict(settings,attack=attack,release=release,sustain=sustain,decay=.15)
        coarse=[dict(settings)]
        for waveform in range(4):
            for cutoff in (80.,200.,500.,1000.,2000.,4000.,8000.,16000.):coarse.append(dict(seed,waveform=waveform,cutoff=cutoff))
        # Experimental initializer replaces one fixed grid slot, never the retained current patch.
        if initializer is not None:coarse[1]=dict(settings,**initializer)
        first=evaluate(coarse,'coarse');baseline=first[0]
        for iteration in range(2):
            beam=sorted(all_results,key=lambda r:r['score'])[:3];vectors=[]
            for candidate in beam:
                p=candidate['parameters']
                for key,factors in [('cutoff',(.5,.75,1.3,2.)),('attack',(.6,1.6)),('decay',(.5,1.8)),('release',(.6,1.6))]:
                    for factor in factors:vectors.append(dict(p,**{key:p[key]*factor}))
                for key,delta in [('sustain',.2),('resonance',.3)]:
                    for sign in (-1,1):vectors.append(dict(p,**{key:p[key]+sign*delta}))
                for waveform in range(4):
                    if waveform!=round(p['waveform']):vectors.append(dict(p,waveform=waveform))
            evaluate(vectors,f'refine_{iteration}')
        if budget is not None and len(all_results)<budget:
            rng=np.random.default_rng(20261103);vectors=[];best_so_far=min(all_results,key=lambda r:r['score'])['parameters']
            for _ in range(4*budget):
                p=dict(best_so_far)
                for key in ('cutoff','attack','decay','release'):p[key]*=float(np.exp(rng.uniform(-.5,.5)))
                p['sustain']+=float(rng.uniform(-.15,.15));p['resonance']+=float(rng.uniform(-.2,.2));vectors.append(p)
            evaluate(vectors,'budget_fill')
            if len(all_results)!=budget:raise RuntimeError('Could not fulfill equal render budget')
        best=min(all_results,key=lambda r:r['score']);shutil.copyfile(best['audio'],folder/'matched.wav')
        # Gain is deliberately not optimized/applied from a normalized comparison.
        result={'proposal':{k:best['parameters'][k] for k in PATCH_KEYS},'method':'Bounded JUCE search v2; deterministic DSP, not ML inference',
            'baseline':{k:v for k,v in baseline.items() if k not in ('audio','parameters')},'matched':{k:v for k,v in best.items() if k not in ('audio','parameters')},
            'candidates_rendered':len(all_results),'renderer_sha256':sha256(self.renderer),'starting_parameters':dict(settings),'renderer_config':timing,
            'midi_note':midi_note,'gate_seconds':gate,'pitch':pitch,'seconds':time.perf_counter()-started,'reference':metadata,'artifacts':str(folder),
            'objective_version':'salient_log_mel_v2 + 2 * envelope_rmse; not comparable to legacy scores',
            'limits':'Dry single-note starting patch, known gate; topology mismatch possible; no perceptual or exact-parameter guarantee.',
            'level_policy':'RMS alignment for scoring only; plugin gain preserved.'}
        if diagnostics:
            from match_diagnostics import save_diagnostics
            _,matched_audio=read_audio(folder/'matched.wav')
            result['diagnostics']=save_diagnostics(folder,audio,resample_poly(matched_audio,1,2)[2400:],frames)
        result['search_seconds']=result['seconds']
        result['seconds']=time.perf_counter()-started
        if initializer is not None:result['method']='Experimental CNN-seeded bounded JUCE search; not default deployment'
        result['experimental_initializer_used']=initializer is not None
        result['requested_render_budget']=budget
        (folder/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False));return result
