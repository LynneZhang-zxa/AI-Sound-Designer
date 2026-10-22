"""Offline analysis of controlled single-note saw WAVs; never imported by JUCE."""
import argparse
import json
import os
from pathlib import Path
import time
import numpy as np
import torch
from scipy.ndimage import uniform_filter1d
from dsp_baseline import DSPBaseline, measure
from features import log_mel
from generate_dataset import ROOT, sha256
from inspect_dataset import read_audio
from metrics import NAMES, to_normalized, to_physical
from model import ParameterCNN

LIMITATIONS = ('Experimental estimator for four-second, 48 kHz mono PCM24 saw-wave synth renders only; '
               'note-on 0.1 s, note-off 1.5 s, MIDI 48–60, velocity 0.4–1.0. '
               'Expected cutoff 100–10000 Hz, attack 10–500 ms, release 20–1500 ms; '
               'other synth settings must match pitch_velocity_config.json. '
               'Not validated on arbitrary recordings. No automatic waveform/pitch identification or confidence estimate.')


def combine(cnn, dsp):
    """Fixed policy selected before validation: CNN cutoff, DSP attack/release."""
    cnn, dsp = np.asarray(cnn), np.asarray(dsp)
    if cnn.shape != dsp.shape or cnn.ndim != 2 or cnn.shape[1] != 3:
        raise ValueError('Expected matching [N,3] predictions')
    if not np.isfinite(cnn).all() or not np.isfinite(dsp).all():
        raise ValueError('Nonfinite prediction')
    result = dsp.copy()
    result[:, 0] = cnn[:, 0]
    return np.clip(result, 0, 1)


def validate_audio(rate, audio, timing):
    audio = np.asarray(audio)
    frames = round(timing['sample_rate'] * timing['duration_seconds'])
    if rate != timing['sample_rate'] or audio.ndim != 1 or len(audio) != frames:
        raise ValueError('Use exactly four seconds of 48 kHz mono audio; no automatic resampling/padding')
    if not np.isfinite(audio).all():
        raise ValueError('Nonfinite audio')
    if not 1e-6 < np.max(np.abs(audio)) < .999:
        raise ValueError('Silent or clipped audio')
    on = round(timing['note_on_seconds'] * rate)
    off = round(timing['note_off_seconds'] * rate)
    if np.max(np.abs(audio[:on])) > 2**-22:
        raise ValueError('Expected silence before note-on at 0.1 s')
    if np.sqrt(np.mean(audio[-round(.2*rate):]**2)) >= 1e-5:
        raise ValueError('Release tail is truncated or note timing differs')
    envelope = np.sqrt(np.maximum(0, uniform_filter1d(audio**2, size=round(.02*rate), mode='constant')))
    if np.max(envelope[on:off]) <= 1e-6 or np.median(envelope[off-round(.15*rate):off-round(.03*rate)]) <= 1e-6:
        raise ValueError('No measurable held note at the specified timing')
    return envelope


class OfflineAnalyzer:
    def __init__(self, run):
        self.run = Path(run).resolve()
        record = json.loads((self.run/'run.json').read_text())
        data = Path(record['dataset_directory'])
        for name, key in [('preprocessing.json','preprocessing_sha256'), ('data_audit.json','dataset_audit_sha256')]:
            if sha256(data/name) != record[key]:
                raise ValueError('Training artifacts changed: '+name)
        summary = json.loads((self.run/'cnn/summary.json').read_text())
        if sha256(self.run/'cnn/best.pt') != summary['checkpoint_sha256']:
            raise ValueError('Checkpoint hash mismatch')
        manifest = json.loads((data/'manifest.json').read_text())
        if sha256(data/'manifest.json') != record['dataset_manifest_sha256']:
            raise ValueError('Manifest hash mismatch')
        self.config = manifest['metadata']['config']
        self.spec = manifest['metadata']['parameter_specification']
        stats = json.loads((data/'preprocessing.json').read_text())
        if stats['source_split'] != 'train': raise ValueError('Expected training-only preprocessing')
        self.mean = np.asarray(stats['mean_per_mel'],dtype=np.float32)[None,:,None]
        self.std = np.maximum(np.asarray(stats['std_per_mel'],dtype=np.float32)[None,:,None],1e-6)
        self.model = ParameterCNN()
        checkpoint = torch.load(self.run/'cnn/best.pt',map_location='cpu',weights_only=True)
        self.model.load_state_dict(checkpoint['state_dict']); self.model.eval()
        baseline = json.loads((self.run/'baselines.json').read_text())
        if baseline['fit_split'] != 'train': raise ValueError('Baseline must be fitted on training only')
        self.dsp = DSPBaseline()
        self.dsp.tables = [(np.array(t['proxy']), np.array(t['physical_target'])) for t in baseline['dsp']['tables']]
        self.provenance = {'run':str(self.run),'checkpoint_sha256':summary['checkpoint_sha256'],
                           'preprocessing_sha256':record['preprocessing_sha256'],
                           'baseline_sha256':sha256(self.run/'baselines.json'),
                           'manifest_sha256':record['dataset_manifest_sha256']}

    def predict(self, rate, audio):
        started = time.perf_counter()
        envelope = validate_audio(rate,audio,self.config['renderer'])
        features = log_mel(audio,rate,self.config['features'])
        x = torch.from_numpy(((features-self.mean)/self.std)[None].copy())
        with torch.inference_mode(): cnn = self.model(x).numpy()
        proxies = measure(audio,rate,self.config['renderer'])
        if not np.isfinite(proxies).all(): raise ValueError('Invalid DSP measurements')
        dsp = to_normalized(self.dsp.predict(proxies[None]),self.spec)
        hybrid = combine(cnn,dsp)
        predictions = {}
        for name, values in [('hybrid',hybrid),('cnn',cnn),('dsp',dsp)]:
            raw = to_physical(values,self.spec)[0]
            predictions[name] = {'normalized':dict(zip(NAMES,map(float,values[0]))),
                                 'physical':dict(zip(NAMES,map(float,raw)))}
        return {'predictions':predictions,'physical_units':{'cutoff':'Hz','attack':'seconds','release':'seconds'},
                'method':{'cutoff':'CNN','attack':'training-calibrated DSP','release':'training-calibrated DSP'},
                'feature_shape':list(x.shape),'peak':float(np.max(np.abs(audio))),
                'analysis_ms':(time.perf_counter()-started)*1000,
                'timing_scope':'audio validation, features, standardization, CNN and DSP; excludes model loading, WAV I/O and report rendering',
                'limitations':LIMITATIONS,'provenance':self.provenance}, envelope


def write_report(folder, rate, audio, envelope, result):
    os.environ.setdefault('MPLCONFIGDIR',str(folder/'matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    t = np.arange(len(audio))/rate
    fig, axes = plt.subplots(2,1,figsize=(11,5),sharex=True,layout='constrained')
    axes[0].plot(t[::12],audio[::12],linewidth=.5,color='#249c89')
    axes[0].set(ylabel='Amplitude',title='Input waveform (absolute level; no peak normalization)')
    axes[1].plot(t[::48],envelope[::48],color='#249c89')
    axes[1].set(ylabel='RMS amplitude',xlabel='Seconds',title='20 ms RMS envelope')
    for ax in axes:
        ax.axvline(.1,color='gray',linestyle='--');ax.axvline(1.5,color='gray',linestyle='--');ax.grid(alpha=.2)
    fig.savefig(folder/'waveform.png',dpi=140);plt.close(fig)
    p = result['predictions']['hybrid']['physical']
    import html
    (folder/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Offline synth analysis</title>'
        '<style>body{font:16px system-ui;background:#11171c;color:#e6eeef;max-width:1000px;margin:40px auto;padding:20px} '
        'strong{color:#65e2c1}img{width:100%}p{line-height:1.6}</style><h1>Offline synth analysis</h1>'
        f'<p><strong>Cutoff: {p["cutoff"]:.3f} Hz · Attack: {p["attack"]*1000:.3f} ms · Release: {p["release"]*1000:.3f} ms</strong></p>'
        '<p>Cutoff: CNN. Attack and release: training-calibrated DSP.</p><img src="waveform.png" alt="Waveform and RMS envelope">'
        f'<p>{html.escape(LIMITATIONS)}</p><p>Analysis: {result["analysis_ms"]:.3f} ms (offline, excludes loading and reporting).</p>'
        '<p><a href="analysis.json">Full numerical results and provenance</a></p>')
    (folder/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wav',type=Path)
    parser.add_argument('--run',type=Path,default=ROOT/'ml/runs/pitch_velocity')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    if not folder.is_relative_to(ROOT): raise ValueError('Output must stay inside canonical repository')
    torch.set_num_threads(4)
    analyzer = OfflineAnalyzer(args.run)
    rate,audio = read_audio(args.wav)
    result,envelope = analyzer.predict(rate,audio)
    result['input'] = {'path':str(args.wav.resolve()),'sha256':sha256(args.wav)}
    folder.mkdir(parents=True,exist_ok=False)
    write_report(folder,rate,audio,envelope,result)
    print(json.dumps(result['predictions']['hybrid'],indent=2))
    print('Report:',folder/'index.html')


if __name__ == '__main__': main()
