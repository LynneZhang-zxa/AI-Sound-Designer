"""Bounded analysis-by-synthesis of dry monophonic reference WAVs; no ML claim."""
import copy
import json
import math
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import numpy as np
from scipy.io import wavfile
from scipy.ndimage import uniform_filter1d
from scipy.signal import correlate, find_peaks, resample_poly
from features import log_mel
from generate_dataset import sha256

TARGETS=('cutoff','attack','release')
FEATURES={'n_fft':1024,'hop_length':256,'n_mels':64,'fmin':20.,'fmax':11000.,'log_floor':1e-12,'center':False,'mel_scale':'htk'}


def load_reference(path):
    path=Path(path).resolve()
    if path.suffix.lower()!='.wav' or not path.is_file() or path.stat().st_size>16000000:
        raise ValueError('Choose a WAV file smaller than 16 MB')
    rate,data=wavfile.read(path)
    if not 8000<=rate<=96000 or not .2<=len(data)/rate<=8:
        raise ValueError('Reference must be 0.2–8 seconds, 8–96 kHz')
    if data.ndim not in (1,2) or (data.ndim==2 and data.shape[1] not in (1,2)):
        raise ValueError('Use a mono or stereo reference')
    if np.issubdtype(data.dtype,np.signedinteger): audio=data.astype(np.float64)/float(2**(data.dtype.itemsize*8-1))
    elif data.dtype==np.uint8: audio=(data.astype(np.float64)-128)/128
    elif np.issubdtype(data.dtype,np.floating): audio=data.astype(np.float64)
    else: raise ValueError('Unsupported WAV encoding')
    if not np.isfinite(audio).all(): raise ValueError('Nonfinite reference audio')
    if audio.ndim==2: audio=audio.mean(axis=1)
    audio-=audio.mean()
    divisor=math.gcd(int(rate),24000)
    audio=resample_poly(audio,24000//divisor,int(rate)//divisor)
    if np.sqrt(np.mean(audio**2))<1e-6: raise ValueError('Reference is silent or stereo downmix cancels')
    envelope=np.sqrt(np.maximum(0,uniform_filter1d(audio**2,120,mode='constant')))
    on=int(np.flatnonzero(envelope>envelope.max()*.02)[0])
    return audio[on:],{'source_rate':int(rate),'analysis_rate':24000,'onset_removed_seconds':on/24000,
                       'source_sha256':sha256(path),'stereo_downmix':'arithmetic mean','dc_removed_for_comparison':True}


def estimate_note(audio,gate):
    rate=24000;end=min(len(audio),round(gate*rate))
    notes=[];strength=[]
    for fraction in (.2,.45,.65):
        start=round(fraction*end);segment=audio[start:min(end,start+6000)]
        if len(segment)<1500: continue
        segment=segment[::2];segment=segment-segment.mean();n=len(segment)
        corr=correlate(segment,segment,mode='full',method='fft')[n-1:]
        energy=np.r_[0,np.cumsum(segment**2)]
        lags=np.arange(max(2,round(12000/1100)),min(n//2,round(12000/60)))
        normal=corr[lags]/np.maximum(np.sqrt(energy[n-lags]*(energy[n]-energy[lags])),1e-20)
        peaks,_=find_peaks(normal)
        if not len(peaks): continue
        highest=float(normal[peaks].max())
        if highest<.65: continue
        peak=int(peaks[np.flatnonzero(normal[peaks]>=max(.65,highest-.04))[0]])
        lag=float(lags[peak])
        if 0<peak<len(normal)-1:
            a,b,c=normal[peak-1:peak+2];den=a-2*b+c
            if abs(den)>1e-12: lag+=float(.5*(a-c)/den)
        note=69+12*np.log2((12000/lag)/440)
        notes.append(note);strength.append(highest)
    if not notes or np.ptp(notes)>.5: raise ValueError('No stable pitch found; choose MIDI note manually. Use one dry sustained note.')
    note=float(np.median(notes));rounded=int(round(note))
    if not 36<=rounded<=84 or abs(note-rounded)>.35:
        raise ValueError('Pitch must be near MIDI 36–84; choose the known MIDI note manually')
    return rounded,{'source':'autocorrelation','median_midi_float':note,'periodicity':float(np.median(strength)),
                    'warning':'Periodicity is not calibrated confidence or proof of monophony'}


def envelope_guess(audio,gate):
    rate=24000;off=round(gate*rate)
    if not 3600<=off<len(audio)-240: raise ValueError('Gate must be 0.15–3 s and end before the reference tail')
    env=np.sqrt(np.maximum(0,uniform_filter1d(audio**2,120,mode='constant')))
    held=env[:off];peak=held.max()
    rise=[int(np.flatnonzero(held>=v*peak)[0]) for v in (.1,.9)]
    attack=np.clip((rise[1]-rise[0])/rate/.8,.001,min(2.,gate*.9))
    level=float(np.median(env[max(0,off-480):off]));tail=env[off:]
    falls=[np.flatnonzero(tail<=v*level) for v in (.9,.1)]
    release=(falls[1][0]-falls[0][0])/rate/.8 if level>1e-8 and all(len(f) for f in falls) else .02
    return float(attack),float(np.clip(release,.005,3.))


def representation(audio,frames):
    aligned=np.zeros(frames,dtype=np.float64)
    count=min(len(audio),frames-2400);aligned[2400:2400+count]=audio[:count]
    rms=np.sqrt(np.mean(aligned**2))
    # Level alignment is only for matching, never applied to saved input or plugin gain.
    scaled=aligned/max(rms,1e-12)
    feature=log_mel(scaled,24000,FEATURES).astype(np.float64)
    envelope=np.sqrt(np.maximum(0,uniform_filter1d(scaled**2,240,mode='constant')))[::240]
    envelope/=max(float(envelope.max()),1e-12)
    return feature,envelope


def objective(reference,candidate):
    spectral=float(np.sqrt(np.mean((reference[0]-candidate[0])**2)))
    envelope=float(np.sqrt(np.mean((reference[1]-candidate[1])**2)))
    return {'score':spectral+2*envelope,'log_mel_rmse':spectral,'envelope_rmse':envelope}


class ReferenceMatcher:
    def __init__(self,renderer,config,spec,directory):
        self.renderer=Path(renderer);self.config=config;self.spec=spec;self.directory=Path(directory)

    def match(self,path,settings,gate,midi_note=None):
        started=time.perf_counter()
        if isinstance(gate,bool) or not isinstance(gate,(int,float)) or not .15<=gate<=3:
            raise ValueError('Gate must be 0.15–3 seconds, measured from note-on to MIDI note-off')
        if midi_note is not None and (type(midi_note) is not int or not 36<=midi_note<=84): raise ValueError('MIDI note must be 36–84 or Auto')
        audio,metadata=load_reference(path)
        if midi_note is None: midi_note,pitch=estimate_note(audio,gate)
        else: pitch={'source':'user supplied'}
        attack,release=envelope_guess(audio,gate)
        config=copy.deepcopy(self.config);timing=config['renderer']
        duration=max(4.,.1+gate+3.25,len(audio)/24000+.15)
        timing.update(sample_rate=48000,note_on_seconds=.1,note_off_seconds=.1+gate,duration_seconds=duration,midi_note=midi_note,velocity=.8)
        frames=round(duration*24000);ref=representation(audio,frames)
        self.directory.mkdir(parents=True,exist_ok=True)
        folder=self.directory/secrets.token_hex(12);folder.mkdir()
        shutil.copyfile(path,folder/'reference.wav')
        # Parameter files are outputs only. Candidate scoring consumes the WAV and no labels.
        def evaluate(vectors,stage):
            out=folder/stage;out.mkdir()
            rows=[]
            for i,parameters in enumerate(vectors):
                parameters=dict(parameters,gain=.8) # analysis render level; user's gain is preserved on apply
                parameters={k:min(self.spec['parameters'][k]['maximum'],max(self.spec['parameters'][k]['minimum'],float(v)))
                            for k,v in parameters.items()}
                rows.append({'id':f'candidate_{i:03d}','split':'validation','requested_parameters':parameters})
            manifest={'metadata':{'config':config,'parameter_specification':self.spec},'examples':rows}
            source=out/'manifest.json';source.write_text(json.dumps(manifest,indent=2))
            with (out/'renderer.log').open('w') as log:
                subprocess.run([str(self.renderer),'--render',str(source),str(out)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=40)
            receipts=json.loads((out/'render_receipts.json').read_text())['examples']
            results=[]
            for row in receipts:
                rate,rendered=wavfile.read(out/row['audio'])
                rendered=rendered.astype(np.float64)/2147483648.
                rendered=resample_poly(rendered,1,2)
                # Renderer already inserts the standard 0.1 s silence.
                candidate=representation(rendered[2400:],frames)
                metrics=objective(ref,candidate)
                results.append({'parameters':row['applied_parameters'],'audio':str(out/row['audio']),**metrics})
            return results
        initial=dict(settings)
        coarse=[initial]
        for waveform in range(4):
            for cutoff in (30.,100.,400.,1500.,5000.,16000.):
                coarse.append(dict(settings,waveform=waveform,cutoff=cutoff,attack=attack,release=release))
        candidates=evaluate(coarse,'coarse');baseline=candidates[0];best=min(candidates,key=lambda x:x['score'])
        seed=best['parameters'];refined=[]
        for cf in (.6,1.,1.6):
            for af in (.6,1.,1.6):
                for rf in (.6,1.,1.6):
                    vector=dict(seed)
                    for key,factor in [('cutoff',cf),('attack',af),('release',rf)]:
                        p=self.spec['parameters'][key]
                        vector[key]=min(p['maximum'],max(p['minimum'],seed[key]*factor))
                    refined.append(vector)
        candidates+=evaluate(refined,'refined');best=min(candidates,key=lambda x:x['score'])
        # Use user's actual gain and other untouched settings; do not apply analysis-level alignment.
        updates={k:best['parameters'][k] for k in ('waveform','cutoff','attack','release')}
        shutil.copyfile(best['audio'],folder/'matched.wav')
        result={'proposal':updates,'method':'Bounded JUCE analysis-by-synthesis search, not a trained external-audio model',
                'baseline':{k:baseline[k] for k in ('score','log_mel_rmse','envelope_rmse')},
                'matched':{k:best[k] for k in ('score','log_mel_rmse','envelope_rmse')},
                'renderer_sha256':sha256(self.renderer),'starting_parameters':dict(settings),
                'renderer_config':dict(timing),'comparison_features':FEATURES,'objective':'log_mel_rmse + 2 * envelope_rmse',
                'candidates_rendered':len(candidates),'midi_note':midi_note,'gate_seconds':gate,'pitch':pitch,
                'seconds':time.perf_counter()-started,'reference':metadata,'artifacts':str(folder),
                'limits':'Dry single pitched note only; known MIDI gate required; fixed current decay/sustain/Q retained; not exact source parameters or a perceptual guarantee.',
                'level_policy':'RMS alignment for scoring only. Reference bytes unchanged; candidate preview at gain 0.8; plugin gain unchanged.'}
        (folder/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False))
        return result
