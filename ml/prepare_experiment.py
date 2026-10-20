"""Generate one approved dataset; extract waveform-only inputs separately from labels."""
import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path
import numpy as np
import scipy
from dsp_baseline import measure
from features import log_mel
from generate_dataset import ROOT, make_manifest, merge_receipts, provenance, sha256
from inspect_dataset import read_audio, demand
from parameters import normalize, denormalize


def waveform_features(path, render_config, feature_config):
    """No row/manifest/target/ID argument; the model input is derived from audio only."""
    rate, audio = read_audio(path)
    demand(rate == render_config["sample_rate"], "Sample rate mismatch")
    return log_mel(audio, rate, feature_config), measure(audio, rate, render_config)


def prepare(directory, renderer):
    directory.mkdir(parents=True, exist_ok=False)
    config = json.loads((ROOT/"ml/experiment_config.json").read_text())
    specfile = directory/"parameter_spec.json"
    subprocess.run([str(renderer),"--export-spec",str(specfile)],check=True)
    source = provenance()
    source.update(renderer_sha256=sha256(renderer), python_version=platform.python_version(), numpy_version=np.__version__, scipy_version=scipy.__version__)
    manifest = make_manifest(config,json.loads(specfile.read_text()),source)
    sourcefile=directory/"manifest.json"
    sourcefile.write_text(json.dumps(manifest,indent=2,sort_keys=True,allow_nan=False)+'\n')
    with (directory/"renderer.log").open('w') as log:
        subprocess.run([str(renderer),"--render",str(sourcefile),str(directory)],stdout=log,stderr=subprocess.STDOUT,check=True)
    rendered=merge_receipts(manifest,json.loads((directory/"render_receipts.json").read_text()))
    (directory/"rendered_manifest.json").write_text(json.dumps(rendered,indent=2,sort_keys=True,allow_nan=False)+'\n')
    spec=manifest['metadata']['parameter_specification']; names=config['target_order']
    per_split={split:[r for r in rendered['examples'] if r['split']==split] for split in config['split_counts']}
    buffers={}; peak_min,peak_max=1.,0.; hashes=set(); target_vectors=set(); frames=192000
    nframes=1+(frames-config['features']['n_fft'])//config['features']['hop_length']
    for split, rows in per_split.items():
        demand(len(rows)==config['split_counts'][split], 'Split count mismatch')
        buffers[split]=np.lib.format.open_memmap(directory/f'{split}_features.npy', mode='w+', dtype=np.float32, shape=(len(rows),1,64,nframes))
        labels=np.array([[r['normalized_targets'][k] for k in names] for r in rows], dtype=np.float32)
        physical=np.array([[r['targets'][k] for k in names] for r in rows], dtype=np.float64)
        np.save(directory/f'{split}_targets.npy',labels); np.save(directory/f'{split}_physical.npy',physical)
        proxies=[]
        for i,row in enumerate(rows):
            audiofile=directory/row['audio']; audio_hash=sha256(audiofile)
            demand(audio_hash not in hashes,'Duplicate audio across dataset splits'); hashes.add(audio_hash)
            vector=tuple(row['targets'][k] for k in names)
            demand(vector not in target_vectors,'Duplicate parameter vectors'); target_vectors.add(vector)
            rate,audio=read_audio(audiofile)
            demand(rate==48000 and len(audio)==frames and np.isfinite(audio).all(),'Invalid audio')
            peak=float(np.max(np.abs(audio))); peak_min=min(peak_min,peak); peak_max=max(peak_max,peak)
            demand(0<peak<.999,'Silent or clipped audio')
            demand(np.max(np.abs(audio[:4800])) <= 2**-22, 'Audio before note-on')
            demand(np.sqrt(np.mean(audio[-9600:]**2))<1e-5,'Tail truncated')
            for k,v in row['applied_parameters'].items():
                demand(np.isclose(v,row['requested_parameters'][k],rtol=3e-6,atol=1e-7),'Incorrect applied parameter')
            for k in names:
                demand(row['targets'][k]==row['applied_parameters'][k],'Label not an applied readback')
                demand(np.isclose(normalize(row['targets'][k],k,spec),row['normalized_targets'][k],rtol=2e-6,atol=2e-7),'Label normalization mismatch')
            feature,proxy=waveform_features(audiofile,config['renderer'],config['features'])
            demand(feature.shape==(1,64,nframes) and np.isfinite(feature).all(),'Invalid feature')
            buffers[split][i]=feature; proxies.append(proxy)
            if (i+1)%200==0: print(f'{split}: {i+1}/{len(rows)} waveform features',flush=True)
        buffers[split].flush(); np.save(directory/f'{split}_dsp.npy',np.array(proxies))
        (directory/f'{split}_ids.json').write_text(json.dumps([r['id'] for r in rows])+'\n')
    # Streaming feature-only moments from TRAINING samples; test is never fitted.
    training=buffers['train']; sums=np.zeros(64); squares=np.zeros(64); total=0
    for first in range(0,len(training),32):
        block=np.asarray(training[first:first+32],dtype=np.float64)
        sums+=block.sum(axis=(0,1,3)); squares+=(block**2).sum(axis=(0,1,3)); total+=block.shape[0]*block.shape[3]
    mean=sums/total; std=np.sqrt(np.maximum(squares/total-mean**2,0))
    demand(np.all(std>1e-6),'Degenerate training feature channel')
    stats={'source_split':'train','examples':len(training),'mean_per_mel':mean.tolist(),'std_per_mel':std.tolist(),'no_per_recording_peak_normalization':True}
    (directory/'preprocessing.json').write_text(json.dumps(stats,indent=2)+'\n')
    audit={'status':'PASS','examples':3000,'split_counts':{k:len(v) for k,v in per_split.items()},'input_shape':[1,64,nframes],
           'unique_audio_hashes':len(hashes),'unique_applied_targets':len(target_vectors),'peak_range':[peak_min,peak_max],
           'model_input':'waveform -> fixed log-mel -> training-feature-only standardization',
           'excluded_from_model_input':['parameter values','manifest columns','IDs','filenames','split indicators','DSP proxies'],
           'dsp_input':'waveform only; fixed timing windows, no true parameter windows',
           'preprocessing_fit_split':'train','provenance':source,'dataset_manifest_sha256':sha256(sourcefile),
           'feature_sha256':{s:sha256(directory/f'{s}_features.npy') for s in per_split}}
    demand(provenance()['plugin_source_sha256']==source['plugin_source_sha256'],'Plugin runtime source changed')
    (directory/'data_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps({k:audit[k] for k in ['status','examples','split_counts','peak_range']},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,default=ROOT/'ml/data/experiment_3000');parser.add_argument('--renderer',type=Path,default=ROOT/'build/DatasetRenderer');args=parser.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(ROOT): raise ValueError('Output must stay inside canonical repository')
    prepare(out,args.renderer.resolve())
