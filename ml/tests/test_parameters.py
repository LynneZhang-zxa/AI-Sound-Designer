import json
import os
from pathlib import Path
import unittest
import numpy as np
from parameters import normalize, denormalize


class ParameterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(Path(os.environ["ML_PARAMETER_SPEC"]).read_text())

    def test_cpp_reference_conversions(self):
        for name in ("cutoff", "attack", "release"):
            for ref in self.spec["parameters"][name]["reference_conversions"]:
                with self.subTest(name=name, reference=ref):
                    self.assertAlmostEqual(normalize(ref["raw"], name, self.spec), ref["normalized"], delta=2e-7)
                    self.assertTrue(np.isclose(denormalize(ref["normalized"], name, self.spec), ref["raw"], rtol=5e-6, atol=2e-6))

    def test_endpoints_roundtrip_monotonic(self):
        for name in ("cutoff", "attack", "release"):
            item = self.spec["parameters"][name]
            self.assertEqual(normalize(item["minimum"], name, self.spec), 0)
            self.assertEqual(normalize(item["maximum"], name, self.spec), 1)
            values = np.linspace(item["minimum"], item["maximum"], 101)
            mapped = np.array([normalize(v, name, self.spec) for v in values])
            self.assertTrue(np.all(np.diff(mapped) > 0))
            np.testing.assert_allclose([denormalize(v, name, self.spec) for v in mapped], values, rtol=1e-12)

    def test_invalid_values(self):
        for name in ("cutoff", "attack", "release"):
            for value in (-1, float("nan"), float("inf"), True, "1"):
                with self.assertRaises(ValueError):
                    normalize(value, name, self.spec)
            for value in (-.1, 1.1, float("nan"), float("inf"), True):
                with self.assertRaises(ValueError):
                    denormalize(value, name, self.spec)
