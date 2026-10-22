"""Isolation, determinism and exact renderer behaviour for performance variation."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import numpy as np
from generate_dataset import ROOT, make_manifest, merge_receipts, validate_performance_groups
from inspect_dataset import read_audio

class PerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=json.loads(Path(os.environ['ML_PARAMETER_SPEC']).read_text())
        cls.renderer=os.environ['ML_RENDERER']
        cls.config=json.loads((ROOT/'ml/pitch_velocity_config.json').read_text())

    def test_deterministic_disjoint_balanced_groups(self):
        manifest=make_manifest(self.config,self.spec,{})
        self.assertEqual(manifest,make_manifest(self.config,self.spec,{}))
        audit=validate_performance_groups(manifest)
        self.assertEqual(audit['group_counts']['test/held_out_pitch'],150)
        for split,group in [('train','seen_pitch'),('validation','seen_pitch'),('test','seen_pitch'),('test','held_out_pitch')]:
            notes=[r['requested_performance']['midi_note'] for r in manifest['examples'] if r['split']==split and r['evaluation_group']==group]
            counts=np.unique(notes,return_counts=True)[1]
            self.assertLessEqual(counts.max()-counts.min(),1)
        fixed=copy.deepcopy(self.config);del fixed['performance_variation']
        original=make_manifest(fixed,self.spec,{})
        for a,b in zip(manifest['examples'],original['examples']):
            self.assertEqual(a['requested_targets'],b['requested_targets'])
            self.assertEqual(a['split'],b['split'])
        broken=copy.deepcopy(manifest)
        row=next(r for r in broken['examples'] if r['split']=='train')
        row['requested_performance']['midi_note']=49
        with self.assertRaises(ValueError): validate_performance_groups(broken)
        broken=copy.deepcopy(self.config);broken['performance_variation']['held_out_midi_notes']=[48]
        with self.assertRaises(ValueError): make_manifest(broken,self.spec,{})

    def test_renderer_consumes_per_example_pitch_and_velocity(self):
        manifest=make_manifest(self.config,self.spec,{})
        row=copy.deepcopy(manifest['examples'][0]);row['split']='train'
        rows=[]
        for index,(note,velocity) in enumerate([(48,.4),(60,.4),(48,.8)]):
            item=copy.deepcopy(row);item['id']=f'probe_{index}'
            item['requested_performance']={'midi_note':note,'velocity':velocity};rows.append(item)
        manifest['examples']=rows
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='ml-performance-') as tmp:
            folder=Path(tmp);path=folder/'manifest.json';path.write_text(json.dumps(manifest))
            for name in ['first','second']:
                subprocess.run([self.renderer,'--render',str(path),str(folder/name)],check=True,capture_output=True)
            rendered=merge_receipts(manifest,json.loads((folder/'first/render_receipts.json').read_text()))
            audios=[]
            for item in rendered['examples']:
                self.assertEqual(item['midi_note'],item['requested_performance']['midi_note'])
                self.assertEqual(item['midi_velocity_7bit'],round(item['requested_performance']['velocity']*127))
                first=folder/'first'/item['audio'];second=folder/'second'/item['audio']
                self.assertEqual(first.read_bytes(),second.read_bytes())
                _,audio=read_audio(first);audios.append(audio)
            self.assertFalse(np.array_equal(audios[0],audios[1]))
            self.assertGreater(np.sqrt(np.mean(audios[2]**2)),np.sqrt(np.mean(audios[0]**2))*1.8)
            rows[0]['requested_performance']['midi_note']=128
            path.write_text(json.dumps(manifest))
            failed=subprocess.run([self.renderer,'--render',str(path),str(folder/'invalid')],capture_output=True)
            self.assertNotEqual(failed.returncode,0)
