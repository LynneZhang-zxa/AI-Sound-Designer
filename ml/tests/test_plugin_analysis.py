import json
import os
import threading
import unittest
import urllib.request
import urllib.error
from http.server import HTTPServer
import numpy as np
from generate_dataset import ROOT
from plugin_analysis_service import Analysis, Handler, validate_snapshot, audio_summary


class PluginAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis=Analysis(ROOT/('ml/runs/__no_model_fresh_install__' if os.environ.get('ML_SKIP_LEGACY_MODEL_TESTS')=='1' else 'ml/runs/pitch_velocity'),ROOT/'build/DatasetRenderer')

    def test_legal_settings_are_not_training_gated(self):
        a=self.analysis;values=dict(a.config['fixed_parameters'],cutoff=2000.,attack=.1,release=.4)
        for key,value in [('waveform',0),('cutoff',20000),('resonance',1.2),('gain',.799734354019165),('sustain',0),('release',8)]:
            updated=dict(values);updated[key]=value
            self.assertEqual(validate_snapshot(updated,a.config,a.spec),updated)
        boundary=dict(values,release=.004999999888241)
        self.assertEqual(validate_snapshot(boundary,a.config,a.spec)['release'],a.spec['parameters']['release']['minimum'])
        for key,value in [('waveform',.5),('gain',float('nan')),('attack',True),('cutoff',20001)]:
            with self.assertRaises(ValueError): validate_snapshot(dict(values,**{key:value}),a.config,a.spec)

    def test_real_render_measurements_across_waveforms_and_silence(self):
        a=self.analysis;base=dict(a.config['fixed_parameters'],cutoff=2000.,attack=.1,release=.4)
        for waveform in range(4):
            values=dict(base,waveform=waveform,gain=.799734354019165,resonance=1.2,decay=.15)
            before=dict(values);result=a.predict(values)
            self.assertEqual(values,before);self.assertEqual(result['actual'],values)
            self.assertEqual(result['ml']['status'],'not_validated')
            self.assertNotIn('cutoff',result) # never label known settings as inferred values
            self.assertFalse(result['audio_summary']['silent'])
            self.assertTrue(np.isfinite(result['audio_summary']['rms_dbfs']))
            for key in values: self.assertTrue(np.isclose(values[key],result['rendered_parameters'][key],rtol=3e-6,atol=1e-7))
        for values in [dict(base,gain=0),dict(base,attack=5,decay=5,release=8,sustain=0,cutoff=20),
                       dict(base,cutoff=20000,resonance=2,gain=1,waveform=2)]:
            result=a.predict(values);summary=result['audio_summary']
            if values['gain']==0:
                self.assertTrue(summary['silent']);self.assertIsNone(summary['rms_dbfs'])
                self.assertIsNone(summary['spectral_centroid_hz'])
            else: self.assertFalse(summary['silent'])
            self.assertLessEqual(summary['duration_seconds'],32)
            json.dumps(result,allow_nan=False)
        result=a.predict(base)
        self.assertEqual(result['ml']['status'],'within_training_conditions' if a.analyzer is not None else 'unavailable')
        if a.analyzer is not None:self.assertIn('cutoff',result['ml']['estimates'])
        old=a.analyzer
        try:
            a.analyzer=None;a.model_error='Model intentionally unavailable in test'
            result=a.predict(base)
            self.assertEqual(result['ml']['status'],'unavailable')
            self.assertIn('audio_summary',result)
        finally: a.analyzer=old;a.model_error=None

    def test_http_supported_full_range_and_invalid(self):
        a=self.analysis;values=dict(a.config['fixed_parameters'],waveform=0,gain=.799734354019165,cutoff=12000.,attack=.005,release=2.)
        server=HTTPServer(('127.0.0.1',0),Handler);server.analysis=a
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(parameters):
            return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}/analyze',
                data=json.dumps({'parameters':parameters}).encode(),headers={'Content-Type':'application/json'}),timeout=15)
        try:
            with request(values) as response: result=json.load(response)
            self.assertEqual(result['actual'],values);self.assertIn('audio_summary',result)
            self.assertEqual(result['ml']['status'],'not_validated')
            with self.assertRaises(urllib.error.HTTPError) as error: request(dict(values,waveform=8))
            self.assertEqual(error.exception.code,400)
        finally: server.shutdown();server.server_close();thread.join()

    def test_comparison_uses_matched_render_conditions_and_raw_levels(self):
        a=self.analysis
        before=dict(a.config['fixed_parameters'],waveform=1,cutoff=8000.,resonance=1.2,attack=.01,release=.5,gain=.4)
        after=dict(before,cutoff=2000.,resonance=.96)
        result=a.compare({'before':before,'after':after,'request_id':17})
        self.assertEqual(result['request_id'],17)
        self.assertEqual(result['midi_note'],48)
        self.assertLess(result['after']['spectral_centroid_hz'],result['before']['spectral_centroid_hz'])
        self.assertEqual(result['before']['duration_seconds'],result['after']['duration_seconds'])
        self.assertEqual(before['cutoff'],8000.)
        for label,values in [('before',before),('after',after)]:
            for key,value in values.items():
                self.assertTrue(np.isclose(result['rendered_parameters'][label][key],value,rtol=3e-6,atol=1e-7))
        quieter=a.compare({'before':before,'after':dict(before,gain=.2),'request_id':18})
        self.assertAlmostEqual(quieter['after']['rms_dbfs']-quieter['before']['rms_dbfs'],-6.0206,places=2)
        self.assertAlmostEqual(quieter['after']['spectral_centroid_hz']/quieter['before']['spectral_centroid_hz'],1.,places=3)
        sine=dict(before,waveform=0)
        plain=a.compare({'before':sine,'after':dict(sine,cutoff=2000.),'request_id':19})
        self.assertLess(abs(plain['after']['spectral_centroid_hz']/plain['before']['spectral_centroid_hz']-1),.01)
        with self.assertRaises(ValueError):a.compare({'before':before,'after':dict(after,gain=float('nan')),'request_id':20})
        with self.assertRaises(ValueError):a.compare({'before':before,'after':after,'request_id':True})

    def test_comparison_http_and_origin_rejection(self):
        a=self.analysis;values=dict(a.config['fixed_parameters'],cutoff=2000.,attack=.1,release=.4)
        server=HTTPServer(('127.0.0.1',0),Handler);server.analysis=a
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(origin=None):
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}/compare',
                data=json.dumps({'parameters':{'before':values,'after':values,'request_id':91}}).encode(),headers=headers),timeout=30)
        try:
            with request() as response:result=json.load(response)
            self.assertEqual(result['request_id'],91)
            self.assertEqual(result['before'],result['after'])
            with self.assertRaises(urllib.error.HTTPError) as caught:request('https://example.com')
            self.assertEqual(caught.exception.code,400)
        finally:server.shutdown();server.server_close();thread.join()
