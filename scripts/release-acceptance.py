"""Functional reference-WAV release matrix. Controlled fixtures, not listening approval."""
from pathlib import Path
import sys,json,urllib.request,urllib.error,hashlib,shutil,html
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'ml'))
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter,lfilter,sawtooth,square
from reference_match import load_reference
from inspect_dataset import read_audio

OUT=ROOT/'ml/runs/release_acceptance'
CASES=[('saw_bass',1,40,.8,.01,.15,.65,.2,450),('square_pluck',2,60,.4,.005,.12,.1,.15,2200),('saw_pad',1,64,1.8,.35,.3,.7,.9,1800),('triangle_soft',3,55,1.4,.1,.2,.8,.5,3000),('sine_round',0,48,1.4,.05,.1,.7,.3,1000),('bright_pluck',1,72,.5,.005,.15,.2,.12,4500),('triangle_bass',3,36,.8,.01,.1,.6,.2,600),('square_pad',2,57,1.8,.25,.4,.65,.9,900)]
SETTINGS=dict(waveform=1,cutoff=12000,attack=.01,decay=.1,sustain=.8,release=.15,resonance=.707,gain=.4)


def post(path,gate,note=None):
    options={'settings':SETTINGS,'gate_seconds':gate}
    if note is not None:options['midi_note']=note
    body=json.dumps({'prompt':str(path),'parameters':options}).encode()
    request=urllib.request.Request('http://127.0.0.1:8766/match',data=body,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=50) as r:return json.load(r)


def main():
    OUT.mkdir(parents=True,exist_ok=False);records=[];rejections=[]
    for name,wave,note,gate,attack,decay,sustain,release,cutoff in CASES:
        rate=48000;t=np.arange(rate*4)/rate;u=t-.1
        env=np.where(u<attack,np.clip(u/attack,0,1),sustain+(1-sustain)*np.clip(1-(u-attack)/decay,0,1))
        env=np.where(u>=gate,sustain*np.clip(1-(u-gate)/release,0,1),env);env[u<0]=0
        phase=2*np.pi*440*2**((note-69)/12)*np.maximum(u,0)
        osc=[np.sin(phase),sawtooth(phase),square(phase),sawtooth(phase,width=.5)][wave]
        b,a=butter(2,cutoff,fs=rate);audio=lfilter(b,a,.12*osc*env)
        path=OUT/f'{name}.wav';wavfile.write(path,rate,np.stack([audio,audio*.9],1).astype(np.float32))
        expected=hashlib.sha256(path.read_bytes()).hexdigest();r=post(path,gate,note)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
        assert r['matched']['score']<=r['baseline']['score']+1e-10 and 'gain' not in r['proposal']
        assert r['starting_parameters']['gain']==.4 and not r['experimental_initializer_used']
        artifacts=Path(r['artifacts']);assert (artifacts/'spectrograms.png').exists()
        source,_=load_reference(path);sample_rate,candidate=read_audio(artifacts/'matched.wav')
        # Audition copies use a common held window and RMS alignment, not LUFS or raw levels.
        from scipy.signal import resample_poly
        candidate=resample_poly(candidate,1,2)[2400:]
        held=min(len(source),len(candidate),round(gate*24000));start=round(.1*held)
        rms_a=float(np.sqrt(np.mean(source[start:held]**2)));rms_b=float(np.sqrt(np.mean(candidate[start:held]**2)))
        relative=rms_a/max(rms_b,1e-12);candidate=candidate*relative
        common=.8/max(float(np.abs(source).max()),float(np.abs(candidate).max()),1e-12)
        for label,signal in [('reference',source),('match',candidate)]:wavfile.write(OUT/f'{name}-{label}.wav',24000,(signal*common).astype(np.float32))
        records.append({'name':name,'source':'Independent SciPy oscillator + Butterworth, not JUCE training synth','reference_sha256':expected,'gate_seconds':gate,'known_midi_note':note,'technical_status':'PASS','result':r,'audition_alignment':{'candidate_gain':relative,'common_pair_gain':common,'policy':'Held-window RMS, no LUFS claim; originals retained'},'perceptual_status':'Not judged'})
        print(name,r['baseline']['score'],r['matched']['score'],flush=True)
    # The existing real Logic export remains a separate development case.
    path=ROOT/'ml/references/logic_es1/ES1Warm.wav';r=post(path,1.4,72)
    records.append({'name':'Logic_ES1_existing','source':'Previously exported real Logic ES1 dry note; previously inspected development case','gate_seconds':1.4,'known_midi_note':72,'technical_status':'PASS','result':r,'perceptual_status':'Known residual brightness/tail mismatch; no new listening approval'})
    bad=[('wrong_extension',OUT/'not-audio.txt',1.4,48),('silence',OUT/'silence.wav',1.4,48),('nonfinite',OUT/'nonfinite.wav',1.4,48),('bad_gate',OUT/'saw_bass.wav',0,48),('bad_note',OUT/'saw_bass.wav',.8,999)]
    (OUT/'not-audio.txt').write_text('invalid');wavfile.write(OUT/'silence.wav',48000,np.zeros(192000,dtype=np.float32));wavfile.write(OUT/'nonfinite.wav',48000,np.full(192000,np.nan,dtype=np.float32))
    for name,path,gate,note in bad:
        try:post(path,gate,note)
        except urllib.error.HTTPError as e:
            assert e.code==400;rejections.append({'case':name,'status':e.code,'body':json.load(e)})
        else:raise AssertionError('Invalid input accepted: '+name)
    report={'scope':'Functional/technical matrix, not a perceptual or arbitrary-recording benchmark','valid_references':records,'invalid_inputs':rejections,'fresh_logic_exports_created':0,'human_listening_preference':'Not measured'}
    (OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    cards=[]
    for name,*_ in CASES:
        cards.append(f'<section><h2>{html.escape(name)}</h2><p>Reference (held-window RMS aligned)</p><audio controls src="{name}-reference.wav"></audio><p>Match</p><audio controls src="{name}-match.wav"></audio></section>')
    (OUT/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Release Match listening</title><style>body{font:17px system-ui;max-width:900px;margin:40px auto;background:#10151b;color:#eee}section{padding:20px;border-bottom:1px solid #456}audio{width:100%}</style><h1>Match acceptance listening</h1><p>Controlled independent SciPy references. Same held-window RMS for each pair; not LUFS. Raw files and technical receipts are retained. These sounds are not new Logic recordings or a human preference study.</p>'+''.join(cards))
    print('PASS: 9 valid reference requests, 5 rejected invalid inputs; listening page',OUT/'index.html')
if __name__=='__main__':main()
