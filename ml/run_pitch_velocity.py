"""One bounded offline robustness run; refuses existing data/run directories."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import numpy as np
import scipy
from generate_dataset import ROOT, make_manifest, merge_receipts, provenance, sha256
from inspect_dataset import inspect
from prepare_experiment import prepare
from audit_experiment import audit


def smoke(directory,renderer,config):
    directory.mkdir(parents=True,exist_ok=False)
    config=json.loads(json.dumps(config))
    config['examples']=100;config['split_counts']={'train':80,'validation':10,'test':10}
    config['performance_variation']['test_seen_count']=5
    specfile=directory/'parameter_spec.json'
    subprocess.run([str(renderer),'--export-spec',str(specfile)],check=True)
    source=provenance();source.update(renderer_sha256=sha256(renderer),python_version=platform.python_version(),numpy_version=np.__version__,scipy_version=scipy.__version__)
    manifest=make_manifest(config,json.loads(specfile.read_text()),source)
    manifestfile=directory/'manifest.json';manifestfile.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    subprocess.run([str(renderer),'--render',str(manifestfile),str(directory)],check=True)
    rendered=merge_receipts(manifest,json.loads((directory/'render_receipts.json').read_text()))
    (directory/'rendered_manifest.json').write_text(json.dumps(rendered,indent=2,sort_keys=True)+'\n')
    result=inspect(directory)
    print(json.dumps({k:result[k] for k in ['status','examples','visibility_checks','peak_range','performance_audit']},indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',default='pitch_velocity')
    parser.add_argument('--smoke-only',action='store_true')
    args=parser.parse_args()
    if not args.name.replace('_','').isalnum(): raise ValueError('Use a simple run name')
    configpath=ROOT/'ml/pitch_velocity_config.json';config=json.loads(configpath.read_text())
    small=ROOT/f'ml/data/{args.name}_smoke';data=ROOT/f'ml/data/{args.name}_3000';run=ROOT/f'ml/runs/{args.name}'
    if any(p.exists() for p in [small,data,run]): raise FileExistsError('Use a new name; existing artifacts are immutable')
    renderer=ROOT/'build/DatasetRenderer'
    env=dict(os.environ,ML_PARAMETER_SPEC=str(ROOT/'ml/data/smoke_v3/parameter_spec.json'),ML_RENDERER=str(renderer),
             PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT/'ml'),OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'ml/tests'),'-v'],cwd=ROOT,env=env,check=True)
    smoke(small,renderer,config)
    if args.smoke_only: return
    prepare(data,renderer,configpath)
    audit(data)
    for script in ['train.py','evaluate.py']:
        subprocess.run([sys.executable,str(ROOT/'ml'/script),'--data',str(data),'--run',str(run)],cwd=ROOT,env=env,check=True)
    subprocess.run([sys.executable,str(ROOT/'ml/report_pitch_velocity.py'),'--run',str(run)],cwd=ROOT,env=env,check=True)
    print('STOP: one normal CNN, one shuffled control and one test pass per checkpoint completed. No tuning or plugin integration.',flush=True)


if __name__=='__main__': main()
