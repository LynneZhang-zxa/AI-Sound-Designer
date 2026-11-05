import unittest
import numpy as np
from prepare_logic_listening import match_levels,rms

class ListeningLevelTests(unittest.TestCase):
    def test_gain_only_level_alignment_and_shared_headroom(self):
        t=np.arange(4000)/1000;x=.1*np.sin(2*np.pi*31*t)
        signals={'Reference':x.copy(),'A':x*8,'B':x*.3};original={k:a.copy() for k,a in signals.items()}
        out,audit=match_levels(signals,1000)
        for k in signals:
            np.testing.assert_array_equal(signals[k],original[k])
            np.testing.assert_allclose(out[k],out['Reference'],rtol=1e-6,atol=1e-8)
        loud=x.copy();loud[3000]=10
        out,audit=match_levels({'Reference':x,'A':loud},1000)
        self.assertLess(audit['common_headroom_gain'],1)
        self.assertLessEqual(np.abs(out['A']).max(),.950001)
        self.assertAlmostEqual(rms(out['A'][100:1500]),rms(out['Reference'][100:1500]),places=7)
        with self.assertRaises(ValueError):match_levels({'Reference':x,'A':x*0},1000)
