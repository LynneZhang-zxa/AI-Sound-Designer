import inspect
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import torch
from dataset import LogMelDataset
from dsp_baseline import DSPBaseline, measure
from generate_dataset import ROOT
from metrics import to_normalized, to_physical, score
from model import ParameterCNN
from train import fit_baselines


class LearningTests(unittest.TestCase):
    def fixture(self, folder):
        features=np.random.default_rng(123).normal(size=(3,1,64,747)).astype(np.float32)
        labels=np.array([[.1,.2,.3],[.4,.5,.6],[.7,.8,.9]],dtype=np.float32)
        np.save(folder/'train_features.npy',features);np.save(folder/'train_targets.npy',labels)
        (folder/'preprocessing.json').write_text(json.dumps({'source_split':'train','mean_per_mel':[0.]*64,'std_per_mel':[1.]*64}))
        return features,labels

    def test_input_excludes_labels_manifest_and_filenames(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='ml-learning-') as temp:
            folder=Path(temp);features,labels=self.fixture(folder)
            (folder/'manifest.json').write_text(json.dumps({'cutoff':999,'targets':'secret'}))
            (folder/'train_ids.json').write_text(json.dumps(['attack_1','cutoff_2','release_3']))
            before=LogMelDataset(folder,'train');before_x=torch.stack([before[i][0] for i in range(3)])
            np.save(folder/'train_targets.npy',labels[::-1].copy())
            (folder/'manifest.json').write_text(json.dumps({'cutoff':123456,'targets':[1,2,3]}))
            (folder/'train_ids.json').write_text(json.dumps(['totally','different','names']))
            after=LogMelDataset(folder,'train');after_x=torch.stack([after[i][0] for i in range(3)])
            self.assertTrue(torch.equal(before_x,after_x))
            self.assertEqual(set(vars(after)),{'features','targets','mean','std'})
            torch.manual_seed(7);model=ParameterCNN().eval()
            with torch.inference_mode(): self.assertTrue(torch.equal(model(before_x),model(after_x)))
            self.assertEqual(list(inspect.signature(model.forward).parameters),['x'])
            self.assertEqual(sum(p.numel() for p in model.parameters()),136131)
            self.assertEqual(model(before_x).shape,(3,3))

    def test_shuffling_changes_only_training_targets(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='ml-learning-') as temp:
            folder=Path(temp);features,labels=self.fixture(folder);permutation=np.array([2,0,1])
            normal=LogMelDataset(folder,'train');shuffled=LogMelDataset(folder,'train',permutation)
            for i in range(3):
                self.assertTrue(torch.equal(normal[i][0],shuffled[i][0]))
                np.testing.assert_array_equal(shuffled[i][1].numpy(),labels[permutation[i]])
            np.save(folder/'validation_features.npy',features);np.save(folder/'validation_targets.npy',labels)
            with self.assertRaises(ValueError): LogMelDataset(folder,'validation',permutation)

    def test_dsp_never_uses_ground_truth_parameter_windows(self):
        rate=48000;t=np.arange(rate*4)/rate
        env=np.minimum(np.maximum((t-.1)/.2,0),1)*np.clip((2.0-t)/.5,0,1)
        audio=.03*np.sin(2*np.pi*440*t)*env
        timing={'note_on_seconds':.1,'note_off_seconds':1.5}
        first=measure(audio,rate,dict(timing,attack=.01,release=.02,cutoff=100))
        second=measure(audio,rate,dict(timing,attack=5.,release=8.,cutoff=20000))
        np.testing.assert_array_equal(first,second)
        self.assertTrue(np.isfinite(first).all())
        baseline=DSPBaseline().fit(np.array([[1,1,1],[2,2,2],[3,3,3]]),np.array([[10,20,30],[20,30,40],[30,40,50]]))
        np.testing.assert_allclose(baseline.predict(np.array([[1.5,1.5,1.5]])),[[15,25,35]])

    def test_baseline_fit_requires_training_data_only(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='ml-learning-') as temp:
            folder=Path(temp);run=folder/'run';run.mkdir()
            _,labels=self.fixture(folder)
            np.save(folder/'train_dsp.npy',np.array([[1,2,3],[2,3,4],[3,4,5]]))
            np.save(folder/'train_physical.npy',np.array([[100,.1,.2],[200,.2,.3],[300,.3,.4]]))
            (folder/'train_ids.json').write_text('["a","b","c"]')
            fit_baselines(folder,run)  # No validation/test artifacts even exist.
            result=json.loads((run/'baselines.json').read_text())
            np.testing.assert_allclose(result['training_mean_normalized'],labels.astype(np.float64).mean(axis=0))
            self.assertEqual(result['fit_split'],'train')

    def test_metrics_units_and_normalization(self):
        spec={'parameters':{name:{'minimum':0.,'maximum':1.,'skew':1.} for name in ('cutoff','attack','release')}}
        truth=np.array([[.1,.2,.3],[.2,.3,.4]])
        predicted=truth+np.array([.01,.001,.002])
        result=score(predicted,truth,truth,spec)
        self.assertAlmostEqual(result['parameters']['cutoff']['mae'],.01)
        self.assertAlmostEqual(result['parameters']['attack']['mae'],1.)
        self.assertAlmostEqual(result['parameters']['release']['rmse'],2.)
        np.testing.assert_allclose(to_normalized(to_physical(truth,spec),spec),truth)
