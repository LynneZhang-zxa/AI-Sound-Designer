import json
import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
from generate_dataset import ROOT
from reference_match import representation
from reference_match_v2 import ReferenceMatcherV2,salient_objective,PATCH_KEYS
from test_reference_match import external_fixture

class ReferenceV2Tests(unittest.TestCase):
    def test_level_invariance_finite_and_identity(self):
        t=np.arange(96000)/24000;x=np.sin(2*np.pi*220*t)*np.exp(-t)
        r=representation(x,96000)
        self.assertLess(salient_objective(r,representation(x*.01,96000))['score'],1e-9)
        self.assertEqual(salient_objective(r,r)['score'],0)
        self.assertTrue(np.isfinite(salient_objective(r,representation(x*0,96000))['score']))

    def test_real_search_readbacks_and_budget(self):
        spec=json.loads(Path(os.environ['ML_PARAMETER_SPEC']).read_text());config=json.loads((ROOT/'ml/pitch_velocity_config.json').read_text())
        settings=dict(config['fixed_parameters'],cutoff=12000,attack=.01,release=.15,gain=.42)
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='reference-v2-') as tmp:
            path=Path(tmp)/'reference.wav';external_fixture(path);before=path.read_bytes()
            matcher=ReferenceMatcherV2(os.environ['ML_RENDERER'],config,spec,Path(tmp)/'outputs')
            result=matcher.match(path,settings,.8)
            self.assertEqual(path.read_bytes(),before);self.assertEqual(settings['gain'],.42)
            self.assertTrue((Path(result['artifacts'])/'spectrograms.png').is_file())
            self.assertFalse(result['experimental_initializer_used'])
            with self.assertRaises(ValueError):matcher.match(path,settings,.8,budget=1)
            with self.assertRaises(ValueError):matcher.match(path,settings,.8,initializer={'cutoff':float('nan')})
            self.assertEqual(set(result['proposal']),set(PATCH_KEYS));self.assertNotIn('gain',result['proposal'])
            self.assertLessEqual(result['candidates_rendered'],147);self.assertGreater(result['candidates_rendered'],33)
            self.assertLessEqual(result['matched']['score'],result['baseline']['score'])
            receipts=list(Path(result['artifacts']).glob('*/render_receipts.json'))
            self.assertEqual(sum(len(json.loads(p.read_text())['examples']) for p in receipts),result['candidates_rendered'])
            for key,v in result['proposal'].items():self.assertTrue(spec['parameters'][key]['minimum']<=v<=spec['parameters'][key]['maximum'])
