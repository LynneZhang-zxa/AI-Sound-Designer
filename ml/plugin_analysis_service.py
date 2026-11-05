"""Optional loopback ML comparison for plugin snapshots; never changes a plugin."""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import tempfile
import subprocess
from scipy.signal import welch
import numpy as np
import torch
from analyze_wav import OfflineAnalyzer
from generate_dataset import ROOT
from inspect_dataset import read_audio
from offline_design import render, TARGETS
from reference_match_v2 import ReferenceMatcherV2


def validate_snapshot(values,config,spec):
    if not isinstance(values,dict) or set(values)!=set(spec['parameters']):
        raise ValueError('Expected complete parameter snapshot')
    values=dict(values)
    for key,value in values.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value):
            raise ValueError('Invalid numeric value')
        p=spec['parameters'][key]
        if not p['minimum']<=value<=p['maximum']:
            # JSON's decimal rounding can place a float32 endpoint infinitesimally
            # outside its exported double representation. Accept only the SAME
            # native float32 endpoint, never an arbitrary widened legal range.
            boundary=p['minimum'] if value<p['minimum'] else p['maximum']
            if np.float32(value)!=np.float32(boundary): raise ValueError('Outside JUCE range')
            values[key]=boundary
    if int(values['waveform'])!=values['waveform']: raise ValueError('Waveform must be an integer choice')
    return dict(values)


def ml_domain(values,config):
    reasons=[]
    for key,expected in config['fixed_parameters'].items():
        if not np.isclose(values[key],expected,rtol=3e-6,atol=1e-7): reasons.append(f'{key} outside fixed training condition')
    for key in TARGETS:
        low,high=config['sampling'][key]
        if not low<=values[key]<=high: reasons.append(f'{key} outside trained range')
    return reasons


def audio_summary(audio,rate,timing):
    """Descriptive measurements, not inverse-synth predictions or LUFS."""
    if not np.isfinite(audio).all(): raise ValueError('Nonfinite rendered audio')
    rms=float(np.sqrt(np.mean(audio**2)));peak=float(np.max(np.abs(audio)))
    on=round(timing['note_on_seconds']*rate);off=round(timing['note_off_seconds']*rate)
    f,power=welch(audio[on:off],fs=rate,nperseg=4096)
    total=float(power.sum())
    return {'rms_dbfs':float(20*np.log10(rms)) if rms>0 else None,
            'peak_dbfs':float(20*np.log10(peak)) if peak>0 else None,
            'spectral_centroid_hz':float(np.sum(f*power)/total) if total>0 else None,
            'high_frequency_energy_ratio':float(power[f>=3000].sum()/total) if total>0 else None,
            'silent':peak==0,'duration_seconds':len(audio)/rate,
            'scope':'Full-render RMS/peak; held-note Welch spectrum; no peak normalization; not LUFS or parameter estimates'}


class Analysis:
    def __init__(self,run,renderer):
        torch.set_num_threads(4)
        self.renderer=Path(renderer).resolve()
        self.directory=ROOT/'ml/runs/plugin_analysis';self.directory.mkdir(parents=True,exist_ok=True)
        # Runtime legal ranges always come from C++, independently of the trained model.
        with tempfile.TemporaryDirectory(dir=self.directory,prefix='spec-') as temporary:
            path=Path(temporary)/'spec.json'
            subprocess.run([str(self.renderer),'--export-spec',str(path)],check=True,capture_output=True)
            self.spec=json.loads(path.read_text())
        self.config=json.loads((ROOT/'ml/pitch_velocity_config.json').read_text())
        try:
            self.analyzer=OfflineAnalyzer(run);self.model_error=None
        except (OSError,ValueError,RuntimeError):
            self.analyzer=None;self.model_error='Saved model unavailable or artifact validation failed'

    def match(self,path,options):
        if not isinstance(path,str) or not path or len(path)>4096 or not isinstance(options,dict):
            raise ValueError('Choose a local reference WAV and valid matching options')
        values=validate_snapshot(options.get('settings'),self.config,self.spec)
        matcher=ReferenceMatcherV2(self.renderer,self.config,self.spec,ROOT/'ml/runs/reference_matches_v2')
        return matcher.match(Path(path),values,options.get('gate_seconds'),options.get('midi_note'))

    def compare(self,options):
        """Two actual JUCE renders at identical MIDI/timing; no inverse model or normalization."""
        import time
        started=time.monotonic()
        if not isinstance(options,dict) or set(options)!={'before','after','request_id'}:
            raise ValueError('Expected before/after snapshots and request_id')
        token=options['request_id']
        if isinstance(token,bool) or not isinstance(token,int) or not 0<=token<=2147483647:
            raise ValueError('Invalid request_id')
        before=validate_snapshot(options['before'],self.config,self.spec)
        after=validate_snapshot(options['after'],self.config,self.spec)
        config=copy.deepcopy(self.config);timing=config['renderer']
        timing['note_off_seconds']=max(1.5,timing['note_on_seconds']+max(v['attack']+v['decay'] for v in (before,after))+.25)
        timing['duration_seconds']=max(4.,timing['note_off_seconds']+max(before['release'],after['release'])+.5)
        summaries={};readbacks={}
        with tempfile.TemporaryDirectory(dir=self.directory,prefix='comparison-') as temporary:
            for label,values in [('before',before),('after',after)]:
                cfg=copy.deepcopy(config);cfg['fixed_parameters']={k:values[k] for k in cfg['fixed_parameters']}
                path,receipt=render(Path(temporary)/label,{k:values[k] for k in TARGETS},cfg,self.spec,
                                    {'midi_note':48,'velocity':.8},self.renderer)
                rate,wave=read_audio(path);summaries[label]=audio_summary(wave,rate,timing)
                readbacks[label]=receipt['applied_parameters']
        return {'request_id':token,**summaries,'rendered_parameters':readbacks,'midi_note':48,
                'seconds':time.monotonic()-started,'scope':'Same MIDI-48 note/timing, raw amplitudes; no normalization, no ML or subjective quality score'}

    def predict(self,values):
        values=validate_snapshot(values,self.config,self.spec)
        config=copy.deepcopy(self.config)
        config['fixed_parameters']={k:values[k] for k in config['fixed_parameters']}
        timing=config['renderer']
        timing['note_off_seconds']=max(1.5,timing['note_on_seconds']+values['attack']+values['decay']+.25)
        timing['duration_seconds']=max(4.,timing['note_off_seconds']+values['release']+.5)
        reasons=ml_domain(values,self.config)
        result={'schema_version':2,'actual':dict(values),
                'method':'Measured audio characteristics; actual settings are known, not inferred',
                'midi_note':48,'velocity':.8,
                'ml':{'status':'not_validated','reason':'; '.join(reasons)} if reasons else
                     {'status':'unavailable','reason':self.model_error or 'No valid prediction'}}
        with tempfile.TemporaryDirectory(dir=self.directory,prefix='snapshot-') as temporary:
            path,receipt=render(Path(temporary)/'render',{k:values[k] for k in TARGETS},config,self.spec,
                               {'midi_note':48,'velocity':.8},self.renderer)
            rate,wave=read_audio(path)
            result['audio_summary']=audio_summary(wave,rate,timing)
            result['rendered_parameters']=receipt['applied_parameters']
            if not reasons and self.analyzer is not None:
                prediction,_=self.analyzer.predict(rate,wave)
                estimates=prediction['predictions']['hybrid']['physical']
                result['ml']={'status':'within_training_conditions','estimates':estimates,
                              'method':'CNN cutoff / DSP envelope; no per-example confidence guarantee'}
                # Compatibility with the previous experimental client; never return known
                # settings as predictions when the model is out of its trained domain.
                result.update(estimates)
        return result


class Handler(BaseHTTPRequestHandler):
    def respond(self,code,value):
        body=json.dumps(value,allow_nan=False).encode();self.send_response(code)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass

    def do_GET(self):
        if self.path=='/health': self.respond(200,{'service':'resonanca-analysis','matcher_version':2,'comparison_version':1,'match_diagnostics_version':1});return
        if self.path=='/diagnostics': self.respond(200,getattr(self.server,'last_diagnostic',{'status':'No request received'}))
        else: self.respond(404,{'error':'Unknown route'})

    def do_POST(self):
        try:
            self.connection.settimeout(5)
            if self.headers.get('Origin'):raise ValueError('Browser-origin requests are not accepted')
            if self.path not in ('/analyze','/match','/compare'): self.respond(404,{'error':'Unknown route'});return
            if not self.headers.get('Content-Type','').startswith('application/json'): raise ValueError('Expected JSON')
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=16384: raise ValueError('Invalid size')
            request=json.loads(self.rfile.read(size))
            if self.path=='/compare':
                self.respond(200,self.server.analysis.compare(request.get('parameters')))
                return
            if self.path=='/match':
                self.respond(200,self.server.analysis.match(request.get('prompt'),request.get('parameters')))
                return
            values=request.get('parameters')
            safe={k:v for k,v in values.items() if isinstance(v,(int,float)) and np.isfinite(v)} if isinstance(values,dict) else {}
            self.server.last_diagnostic={'snapshot':safe}
            result=self.server.analysis.predict(values)
            self.server.last_diagnostic.update(status='ok')
            self.respond(200,result)
        except (ValueError,TypeError,AttributeError) as error:
            detail=str(error)[:500]
            diagnostic=getattr(self.server,'last_diagnostic',{})
            diagnostic.update(status='unsupported',error=detail);self.server.last_diagnostic=diagnostic
            self.respond(400,{'error':detail})
        except Exception:
            self.respond(503,{'error':'Offline analysis unavailable'})

    def log_message(self,*_args): pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--run',type=Path,default=ROOT/'ml/runs/pitch_velocity')
    parser.add_argument('--renderer',type=Path,default=ROOT/'build/DatasetRenderer')
    args=parser.parse_args();analysis=Analysis(args.run,args.renderer)
    server=HTTPServer(('127.0.0.1',args.port),Handler);server.analysis=analysis
    print(f'Plugin ML comparison: http://127.0.0.1:{args.port}/analyze',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__': main()
