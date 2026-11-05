import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import torch
import match_model as mm
from match_diagnostics import save_diagnostics
from generate_dataset import ROOT

class MatchModelTests(unittest.TestCase):
    def test_all_six_parameter_roundtrips_and_model_shapes(self):
        spec=json.loads(Path(os.environ['ML_PARAMETER_SPEC']).read_text())
        n=np.array([[0]*6,[.2]*6,[1]*6],dtype=float)
        np.testing.assert_allclose(mm.convert(mm.convert(n,spec,True),spec),n,atol=1e-12)
        with torch.inference_mode():a,b=mm.Model()(torch.zeros(2,1,64,747))
        self.assertEqual(tuple(a.shape),(2,6));self.assertEqual(tuple(b.shape),(2,4))
        with self.assertRaises(ValueError):mm.Model()(torch.zeros(2,64,747))

    def test_target_mutation_cannot_change_model_input(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            folder=Path(tmp);x=np.random.default_rng(1).normal(size=(2,1,64,747)).astype(np.float32)
            np.save(folder/'train_features.npy',x);np.save(folder/'train_targets.npy',np.zeros((2,6),dtype=np.float32));np.save(folder/'train_waves.npy',np.array([0,1]))
            (folder/'preprocessing.json').write_text(json.dumps({'source_split':'train','mean':[0]*64,'std':[1]*64}))
            with patch.object(mm,'DATA',folder):
                original=mm.Inputs('train')[0][0].numpy().copy()
                np.save(folder/'train_targets.npy',np.ones((2,6),dtype=np.float32));np.save(folder/'train_waves.npy',np.array([3,2]))
                (folder/'manifest.json').write_text('{"filename":"cutoff_9999.wav","targets":[9999]}')
                np.testing.assert_array_equal(original,mm.Inputs('train')[0][0].numpy())
                np.testing.assert_array_equal(original,mm.Inputs('train',np.array([1,0]))[0][0].numpy())

    def test_internal_shared_scale_diagnostics(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            folder=Path(tmp);t=np.arange(96000)/24000;x=np.sin(2*np.pi*220*t)*np.exp(-t)
            paths=save_diagnostics(folder,x,x*.01,96000)
            self.assertTrue((folder/paths['image']).stat().st_size>1000)
            arrays=np.load(folder/paths['arrays'])
            np.testing.assert_allclose(arrays['reference_log_power'],arrays['reconstruction_log_power'],atol=1e-9)
            self.assertEqual(json.loads((folder/'diagnostics.json').read_text())['features']['n_mels'],64)
