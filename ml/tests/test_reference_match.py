import json
import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter, sawtooth
from generate_dataset import ROOT
from reference_match import ReferenceMatcher, load_reference, estimate_note, representation, objective


def external_fixture(path,rate=44100):
    """Independent SciPy oscillator/filter, not JUCE, not a training/test sample."""
    t=np.arange(round(1.7*rate))/rate;u=t-.2;gate=.8;attack=.04;release=.3
    envelope=np.where(u<attack,np.clip(u/attack,0,1),.8+.2*np.clip(1-(u-attack)/.1,0,1))
    envelope=np.where(u>=gate,.8*np.clip(1-(u-gate)/release,0,1),envelope)
    envelope[u<0]=0
    oscillator=sawtooth(2*np.pi*130.81278265*np.maximum(u,0))
    b,a=butter(2,1000,fs=rate);audio=lfilter(b,a,.12*oscillator*envelope)
    stereo=np.stack([audio,audio*.8],axis=1)
    wavfile.write(path,rate,np.round(stereo*32767).astype(np.int16))


class ReferenceMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=json.loads(Path(os.environ['ML_PARAMETER_SPEC']).read_text())
        cls.config=json.loads((ROOT/'ml/pitch_velocity_config.json').read_text())
        cls.renderer=Path(os.environ['ML_RENDERER'])

    def test_loading_pitch_and_level_invariant_comparison(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='reference-fixture-') as tmp:
            path=Path(tmp)/'independent.wav';external_fixture(path)
            audio,meta=load_reference(path)
            self.assertEqual(meta['source_rate'],44100)
            note,pitch=estimate_note(audio,.8);self.assertEqual(note,48)
            first=representation(audio,96000);second=representation(audio*.5,96000)
            self.assertLess(objective(first,second)['score'],1e-8)
            wavfile.write(path,44100,np.zeros(44100,dtype=np.int16))
            with self.assertRaises(ValueError): load_reference(path)
            with self.assertRaises(ValueError): estimate_note(np.random.default_rng(7).normal(size=24000),.8)

    def test_real_reference_search_improves_fixed_objective_and_preserves_gain(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='reference-search-') as tmp:
            folder=Path(tmp);path=folder/'independent.wav';external_fixture(path)
            settings=dict(self.config['fixed_parameters'],waveform=0,cutoff=12000.,attack=.005,release=.15,gain=.799734354)
            before=dict(settings);source=path.read_bytes()
            matcher=ReferenceMatcher(self.renderer,self.config,self.spec,folder/'matches')
            result=matcher.match(path,settings,.8)
            self.assertEqual(source,path.read_bytes());self.assertEqual(before,settings)
            self.assertEqual(result['candidates_rendered'],52)
            self.assertEqual(result['midi_note'],48)
            self.assertLess(result['matched']['score'],result['baseline']['score'])
            self.assertEqual(set(result['proposal']),{'waveform','cutoff','attack','release'})
            for key,value in result['proposal'].items():
                p=self.spec['parameters'][key];self.assertTrue(p['minimum']<=value<=p['maximum'])
            self.assertTrue((Path(result['artifacts'])/'matched.wav').exists())
            print('REFERENCE MATCH MEASURED:',json.dumps({k:result[k] for k in ['baseline','matched','proposal','seconds']}))
            with self.assertRaises(ValueError): matcher.match(path,settings,0)
            with self.assertRaises(ValueError): matcher.match(path,settings,.8,128)
