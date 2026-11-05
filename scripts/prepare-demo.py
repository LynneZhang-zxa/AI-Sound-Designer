"""Reproducible staged demonstration, using real test-editor state and JUCE audio."""
from pathlib import Path
import sys,copy,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'ml'))
import numpy as np
from scipy.io import wavfile
from offline_design import render,TARGETS
from inspect_dataset import read_audio

def main():
    folder=ROOT/'assets/demo';folder.mkdir(parents=True,exist_ok=True)
    subprocess.run([str(ROOT/'build/EditorTests')],cwd=ROOT,check=True)
    states={}
    for stage in ['before','proposal','applied','undo']:
        for ext in ['png','json']:shutil.copyfile(ROOT/'build'/f'demo-{stage}.{ext}',folder/f'{stage}.{ext}')
        states[stage]=json.loads((folder/f'{stage}.json').read_text())
    assert states['before']==states['proposal']==states['undo']
    config=json.loads((ROOT/'ml/pitch_velocity_config.json').read_text())
    spec_path=ROOT/'build/demo-parameter-spec.json';subprocess.run([str(ROOT/'build/DatasetRenderer'),'--export-spec',str(spec_path)],check=True);spec=json.loads(spec_path.read_text())
    audio={}
    for stage in ['before','applied']:
        cfg=copy.deepcopy(config);v=states[stage];cfg['fixed_parameters']={k:v[k] for k in cfg['fixed_parameters']}
        # Render receipts are regenerated in a new temp area, leaving the final demo repeatable.
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='demo-render-') as tmp:
            path,receipt=render(Path(tmp)/stage,{k:v[k] for k in TARGETS},cfg,spec,{'midi_note':48,'velocity':.8},ROOT/'build/DatasetRenderer')
            shutil.copyfile(path,folder/f'{stage}.wav');(folder/f'{stage}-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
            rate,audio[stage]=read_audio(path)
    wavfile.write(folder/'demo-audio.wav',rate,np.concatenate([audio['before'],audio['before'],audio['applied'],audio['before']]).astype(np.float32))
    subprocess.run(['swiftc','-module-cache-path',str(ROOT/'build/swift-cache'),str(ROOT/'scripts/render-demo.swift'),'-o',str(ROOT/'build/render-demo')],check=True)
    subprocess.run([str(ROOT/'build/render-demo'),str(folder)],check=True)
    (folder/'README.md').write_text('Staged offline demo assembled from actual JUCE test-editor snapshots and renderer receipts; not a Logic screen recording. Before/Preview/Apply/Undo each last four seconds. Preview and Undo use exactly the before audio. Local rules; no live OpenAI claim. No audio peak normalization. Reproduce with ml/.venv/bin/python scripts/prepare-demo.py.\n')
if __name__=='__main__':main()
