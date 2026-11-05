"""Dataset domain, waveform-only input, and joint-shuffle regression checks."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
import torch
from generate_dataset import ROOT
from initializer_experiment import CONFIG, extended_manifest, Inputs, Initializer

class InitializerTests(unittest.TestCase):
    def test_manifest_domain_balance_and_determinism(self):
        spec=json.loads(Path(os.environ['ML_PARAMETER_SPEC']).read_text())
        cfg=json.loads(CONFIG.read_text())
        a=extended_manifest(spec,cfg);b=extended_manifest(spec,cfg)
        self.assertEqual(a,b)
        for split,count in [('train',600),('validation',75),('test',75)]:
            rows=[r for r in a['examples'] if r['split']==split]
            self.assertEqual(np.bincount([r['requested_parameters']['waveform'] for r in rows]).tolist(),[count]*4)
            for row in rows:
                for key,(lo,hi) in cfg['nuisance_ranges'].items():
                    self.assertTrue(lo<=row['requested_parameters'][key]<=hi)
                if split!='test': self.assertNotIn(row['requested_performance']['midi_note'],cfg['held_out_pitches'])

    def test_input_is_independent_of_labels_ids_and_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            folder=Path(tmp);rng=np.random.default_rng(1)
            np.save(folder/'train_features.npy',rng.normal(size=(3,1,64,747)).astype(np.float32))
            labels=np.arange(9,dtype=np.float32).reshape(3,3)/10
            np.save(folder/'train_targets.npy',labels);np.save(folder/'train_waveforms.npy',np.array([0,1,2]))
            (folder/'preprocessing.json').write_text(json.dumps({'source_split':'train','mean_per_mel':[0]*64,'std_per_mel':[1]*64}))
            original=Inputs(folder,'train');x=original[0][0]
            permutation=np.array([2,0,1]);shuffled=Inputs(folder,'train',permutation)
            torch.testing.assert_close(x,shuffled[0][0]);np.testing.assert_array_equal(shuffled[0][1].numpy(),labels[2]);self.assertEqual(shuffled[0][2],2)
            np.save(folder/'train_targets.npy',labels[::-1]);np.save(folder/'train_waveforms.npy',np.array([3,3,3]))
            (folder/'manifest.json').write_text('{"targets":"changed"}');(folder/'train_ids.json').write_text('["different"]')
            mutated=Inputs(folder,'train');torch.testing.assert_close(x,mutated[0][0])
            torch.manual_seed(1);model=Initializer().eval()
            with torch.inference_mode():
                first=model(x[None]);second=model(mutated[0][0][None])
            for p,q in zip(first,second): torch.testing.assert_close(p,q,rtol=0,atol=0)
            self.assertEqual(first[0].shape,(1,3));self.assertEqual(first[1].shape,(1,4))
            self.assertEqual(sum(p.numel() for p in model.parameters()),136391)
