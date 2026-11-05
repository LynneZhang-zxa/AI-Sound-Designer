import unittest
import numpy as np
from scipy.signal import resample_poly
from hybrid_match import fixtures,hybrid_seed

class HybridMatchTests(unittest.TestCase):
    def test_fixture_determinism_and_hybrid_ownership(self):
        first=fixtures();second=fixtures()
        self.assertEqual(len(first),16)
        for (meta,a),(other,b) in zip(first,second):
            self.assertEqual(meta,other);np.testing.assert_array_equal(a,b)
            self.assertEqual(a.shape,(176400,2));self.assertTrue(np.isfinite(a).all());self.assertLess(np.abs(a).max(),1)
        audio=resample_poly(first[0][1].mean(1),160,147)
        a=hybrid_seed([1000,.01,.02],2,audio);b=hybrid_seed([2000,4,7],3,audio)
        self.assertEqual(a['attack'],b['attack']);self.assertEqual(a['release'],b['release'])
        self.assertEqual((a['cutoff'],a['waveform']),(1000,2));self.assertEqual((b['cutoff'],b['waveform']),(2000,3))
        self.assertGreater(a['attack'],0);self.assertGreater(a['release'],0)
