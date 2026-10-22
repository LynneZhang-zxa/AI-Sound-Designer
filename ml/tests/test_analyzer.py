import unittest
import numpy as np
from analyze_wav import combine, validate_audio


class AnalyzerTests(unittest.TestCase):
    def test_fixed_hybrid_policy_and_invalid_predictions(self):
        cnn=np.array([[.1,.2,.3],[.4,.5,.6]])
        dsp=np.array([[.7,.8,.9],[.8,.9,1.]])
        before=dsp.copy(); result=combine(cnn,dsp)
        np.testing.assert_array_equal(result[:,0],cnn[:,0])
        np.testing.assert_array_equal(result[:,1:],dsp[:,1:])
        np.testing.assert_array_equal(dsp,before)
        for bad in [np.zeros((2,2)),np.full((2,3),np.nan)]:
            with self.assertRaises(ValueError): combine(cnn,bad)

    def test_audio_contract_and_absolute_amplitude(self):
        rate=48000;t=np.arange(rate*4)/rate
        envelope=np.minimum(np.maximum((t-.1)/.1,0),1)*np.clip((1.8-t)/.3,0,1)
        audio=.03*np.sin(2*np.pi*220*t)*envelope
        config={'sample_rate':rate,'duration_seconds':4,'note_on_seconds':.1,'note_off_seconds':1.5}
        full=validate_audio(rate,audio,config)
        half=validate_audio(rate,audio*.5,config)
        np.testing.assert_allclose(half,full*.5,atol=1e-10)
        for sr,bad in [(44100,audio),(rate,audio[:-1]),(rate,np.zeros_like(audio)),
                       (rate,np.ones_like(audio)),(rate,np.full_like(audio,np.nan)),
                       (rate,np.stack([audio,audio]))]:
            with self.assertRaises(ValueError): validate_audio(sr,bad,config)
        early=audio.copy();early[:100]=.01
        with self.assertRaises(ValueError): validate_audio(rate,early,config)
        truncated=audio.copy();truncated[-1000:]=.01
        with self.assertRaises(ValueError): validate_audio(rate,truncated,config)
