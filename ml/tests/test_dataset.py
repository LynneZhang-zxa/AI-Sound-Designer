import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import numpy as np
from features import log_mel
from generate_dataset import make_manifest, merge_receipts
from inspect_dataset import read_audio

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "ml/config.json").read_text())


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(Path(os.environ["ML_PARAMETER_SPEC"]).read_text())
        cls.renderer = os.environ["ML_RENDERER"]
        cls.source = {"git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                      "fixture": True}

    def manifest(self):
        return make_manifest(CONFIG, self.spec, self.source)

    def test_seed_and_split_determinism(self):
        a, b = self.manifest(), self.manifest()
        self.assertEqual(a, b)
        c = copy.deepcopy(CONFIG)
        c["seed"] += 1
        self.assertNotEqual(a["examples"], make_manifest(c, self.spec, self.source)["examples"])
        groups = {name: {r["id"] for r in a["examples"] if r["split"] == name} for name in CONFIG["split_counts"]}
        self.assertEqual({name:len(ids) for name, ids in groups.items()}, CONFIG["split_counts"])
        self.assertFalse(groups["train"] & groups["validation"] or groups["train"] & groups["test"] or groups["validation"] & groups["test"])
        self.assertEqual(len({tuple(r["requested_targets"].values()) for r in a["examples"]}), 100)

    def test_sampling_bounds_and_scope_guard(self):
        for row in self.manifest()["examples"]:
            self.assertEqual(set(row["requested_parameters"]), set(self.spec["parameters"]))
            for name, value in row["requested_targets"].items():
                low, high = CONFIG["sampling"][name]
                self.assertTrue(low <= value <= high)
        config = copy.deepcopy(CONFIG)
        config["examples"] = 10000
        with self.assertRaises(ValueError):
            make_manifest(config, self.spec, self.source)

    def test_features_preserve_level(self):
        rate = CONFIG["renderer"]["sample_rate"]
        audio = .1 * np.sin(2 * np.pi * 1000 * np.arange(rate * 4) / rate)
        full, half = log_mel(audio, rate, CONFIG["features"]), log_mel(audio * .5, rate, CONFIG["features"])
        self.assertEqual(full.shape, (1, 64, 747))
        active = full > np.log(CONFIG["features"]["log_floor"]) + 5
        np.testing.assert_allclose((half - full)[active], 2 * np.log(.5), atol=3e-6)
        with self.assertRaises(ValueError):
            log_mel(np.full(192000, np.nan), rate, CONFIG["features"])

    def test_explicit_renderer_and_reproducibility(self):
        manifest = self.manifest()
        # Arbitrary order and explicit split assignment must survive unchanged.
        manifest["examples"] = [copy.deepcopy(manifest["examples"][i]) for i in (9, 3, 17)]
        for row, split in zip(manifest["examples"], ("test", "train", "validation")):
            row["split"] = split
        with tempfile.TemporaryDirectory(dir=ROOT / "build", prefix="ml-test-") as temporary:
            folder = Path(temporary)
            source = folder / "manifest.json"
            source.write_text(json.dumps(manifest))
            input_hash = hashlib.sha256(source.read_bytes()).digest()
            for name in ("first", "second"):
                subprocess.run([self.renderer, "--render", str(source), str(folder / name)], check=True, capture_output=True, text=True)
            result = merge_receipts(manifest, json.loads((folder / "first/render_receipts.json").read_text()))
            self.assertEqual(input_hash, hashlib.sha256(source.read_bytes()).digest())
            self.assertEqual(result["metadata"], manifest["metadata"])
            for requested, actual in zip(manifest["examples"], result["examples"]):
                for key in requested:
                    self.assertEqual(requested[key], actual[key])
                for key, value in actual["targets"].items():
                    self.assertEqual(value, actual["applied_parameters"][key])
                    self.assertTrue(np.isclose(value, requested["requested_targets"][key], rtol=3e-6))
                first, second = folder / "first" / actual["audio"], folder / "second" / actual["audio"]
                self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
                rate, audio = read_audio(first)
                self.assertEqual(rate, 48000)
                self.assertEqual(audio.shape, (192000,))
                self.assertTrue(np.isfinite(audio).all() and 0 < np.max(np.abs(audio)) < 1)
            failed = subprocess.run([self.renderer, "--render", str(source), str(folder / "first")], capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            invalid = copy.deepcopy(manifest)
            invalid["examples"][0]["requested_parameters"]["unknown"] = 1
            source.write_text(json.dumps(invalid))
            failed = subprocess.run([self.renderer, "--render", str(source), str(folder / "invalid")], capture_output=True)
            self.assertNotEqual(failed.returncode, 0)

    def test_renderer_rejects_mismatched_export(self):
        manifest = self.manifest()
        manifest["metadata"]["parameter_specification"]["parameters"]["cutoff"]["maximum"] = 9999
        with tempfile.TemporaryDirectory(dir=ROOT / "build", prefix="ml-test-") as temporary:
            folder = Path(temporary)
            source = folder / "manifest.json"
            source.write_text(json.dumps(manifest))
            result = subprocess.run([self.renderer, "--render", str(source), str(folder / "output")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("specification", result.stderr)
