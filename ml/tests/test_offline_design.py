import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from generate_dataset import ROOT, sha256
from offline_design import checked_parameters, constrain_updates, proposal, render, apply, distance, save, scale_strength


class OfflineDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((ROOT/'ml/pitch_velocity_config.json').read_text())
        cls.spec=json.loads(Path(os.environ['ML_PARAMETER_SPEC']).read_text())
        cls.renderer=Path(os.environ['ML_RENDERER'])
        cls.before={'cutoff':2000.,'attack':.1,'release':.5}

    def test_clamp_and_scope(self):
        after,ignored=constrain_updates({'cutoff':20000,'release':-1,'decay':.05},self.before,self.config,self.spec)
        self.assertEqual(after,dict(self.before,cutoff=10000.,release=.02));self.assertEqual(ignored,['decay'])
        for update in [{'unknown':1},{'attack':True},{'cutoff':float('nan')},{'release':'short'}]:
            with self.assertRaises(ValueError): constrain_updates(update,self.before,self.config,self.spec)

    def test_strength_direction_order_bounds_and_preservation(self):
        before=self.before;target=dict(before,cutoff=1200,release=.3)
        values=[scale_strength(before,target,k,self.config,self.spec) for k in ['subtle','medium','strong']]
        for key in ['cutoff','release']:
            self.assertGreater(before[key],values[0][key]);self.assertGreater(values[0][key],values[1][key])
            self.assertGreater(values[1][key],values[2][key])
        for value in values: self.assertEqual(value['attack'],before['attack'])
        self.assertAlmostEqual(values[1]['cutoff'],target['cutoff'])
        brighter=scale_strength(before,dict(before,cutoff=10000), 'strong',self.config,self.spec)
        self.assertEqual(brighter['cutoff'],10000)
        short=scale_strength(before,dict(before,release=.02),'strong',self.config,self.spec)
        self.assertEqual(short['release'],.02)
        with self.assertRaises(ValueError): scale_strength(before,target,'unknown',self.config,self.spec)

    def test_worker_service_and_fallback(self):
        current=threading.get_ident()
        def service(prompt,snapshot):
            self.assertNotEqual(current,threading.get_ident());self.assertEqual(len(snapshot),8)
            return {'cutoff':1200,'decay':.01}
        with patch('offline_design.request_service',side_effect=service):
            after,source=proposal('darker',self.before,self.config,self.spec)
        self.assertEqual(after['cutoff'],1200);self.assertEqual(source['source'],'AI service')
        with patch('offline_design.request_service',side_effect=OSError('unavailable')):
            after,source=proposal('暗一点，尾音短一点',self.before,self.config,self.spec)
        self.assertEqual(after['cutoff'],1200);self.assertEqual(after['release'],.3)
        self.assertIsNotNone(source['fallback_reason'])
        with patch('offline_design.request_service',return_value={'cutoff':float('nan')}):
            _,source=proposal('darker',self.before,self.config,self.spec)
        self.assertEqual(source['source'],'local rules')
        after,source=proposal('unrecognized intent',self.before,self.config,self.spec,True)
        self.assertEqual(after,self.before)
        with self.assertRaises(ValueError): proposal('',self.before,self.config,self.spec,True)

    def test_explicit_apply_and_real_render_readbacks(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='offline-design-test-') as tmp:
            folder=Path(tmp);performance={'midi_note':48,'velocity':.8}
            reconstruction,receipt=render(folder/'reconstruction',self.before,self.config,self.spec,performance,self.renderer)
            (folder/'original.wav').write_bytes(reconstruction.read_bytes())
            plan={'before':self.before,'after':dict(self.before,cutoff=1200.,release=.3),
                  'config':self.config,'parameter_specification':self.spec,'performance':performance,
                  'renderer_sha256':sha256(self.renderer),'input_sha256':sha256(folder/'original.wav'),
                  'reconstruction_sha256':sha256(reconstruction),'reconstruction_distance':distance(reconstruction,reconstruction,self.config),
                  'prompt':'darker and shorter','proposal_source':{'source':'local rules'},'limitations':'Controlled integration test'}
            self.assertEqual(plan['reconstruction_distance']['log_mel_rmse'],0)
            save(folder/'proposal.json',plan);digest=sha256(folder/'proposal.json')
            with self.assertRaises(ValueError): apply(folder,'incorrect',self.renderer)
            self.assertFalse((folder/'modified').exists())
            result=apply(folder,digest,self.renderer)
            self.assertGreater(result['modified_vs_reconstruction']['log_mel_rmse'],0)
            self.assertAlmostEqual(result['modified_readbacks']['targets']['cutoff'],1200,delta=.01)
            self.assertAlmostEqual(result['modified_readbacks']['targets']['release'],.3,delta=1e-5)
            self.assertTrue((folder/'index.html').exists());self.assertTrue((folder/'applied.json').exists())
            with self.assertRaises(FileExistsError): apply(folder,digest,self.renderer)
