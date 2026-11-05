import io
import json
import os
import unittest
from unittest.mock import patch
import server


class ServiceTests(unittest.TestCase):
    def response(self, updates, status="completed"):
        return io.BytesIO(json.dumps({"status": status, "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps({"updates": updates})}]}]}).encode())

    def test_openai_request_and_response(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-not-a-key"}), patch(
                "urllib.request.urlopen", return_value=self.response([
                    {"parameter": "cutoff", "value": 8000}])) as http:
            self.assertEqual(server.openai_proposal({"prompt": "darker", "parameters": {}}), {"cutoff": 8000})
            request = http.call_args.args[0]
            body = json.loads(request.data)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
            self.assertFalse(body["store"])
            self.assertTrue(body["text"]["format"]["strict"])
            self.assertNotIn("test-not-a-key", request.data.decode())

    def test_current_intent_is_separate_from_historical_intents(self):
        current="保持尾音，声音更柔和"
        with patch.dict(os.environ,{"OPENAI_API_KEY":"fixture"}),patch("urllib.request.urlopen",return_value=self.response([])) as http:
            server.openai_proposal({"prompt":current,"parameters":{},"history":[{"action":"applied","intent":"darker and shorter","applied":{"cutoff":800}}]})
            body=json.loads(http.call_args.args[0].data)
            self.assertTrue(body['input'].endswith(current))
            self.assertIn('CONTEXT ONLY',body['input']);self.assertIn('CURRENT PRODUCER REQUEST',body['input'])
            self.assertIn('0=sine, 1=saw, 2=square, 3=triangle',body['instructions'])

    def test_bad_updates_rejected(self):
        for updates in [
                        [{"parameter": "unknown", "value": 1}],
                        [{"parameter": "cutoff", "value": True}],
                        [{"parameter": "cutoff", "value": "1000"}],
                        [{"parameter": "gain", "value": .5}] * 2]:
            with self.subTest(updates=updates), patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch(
                    "urllib.request.urlopen", return_value=self.response(updates)):
                with self.assertRaises(ValueError):
                    server.openai_proposal({})

    def test_clamp_proposals(self):
        self.assertEqual(server.validate({"cutoff": -10, "release": 100, "waveform": 1.6}, clamp=True),
                         {"cutoff": 20, "release": 8, "waveform": 2})
        with self.assertRaises(ValueError):
            server.validate({"cutoff": float("nan")}, clamp=True)

    def test_incomplete_response(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch(
                "urllib.request.urlopen", return_value=self.response([], "incomplete")):
            with self.assertRaises(ValueError):
                server.openai_proposal({})

    def test_explanation_noop_and_history(self):
        payload={"updates":[],"message":"Reverb is not implemented; no change.","unsupported":["reverb"]}
        response={"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":json.dumps(payload)}]}]}
        with patch.dict(os.environ,{"OPENAI_API_KEY":"test"}),patch("urllib.request.urlopen",return_value=io.BytesIO(json.dumps(response).encode())):
            result=server.openai_proposal({"prompt":"add reverb"},with_details=True)
            self.assertEqual(result["proposal"],{});self.assertEqual(result["unsupported"],["reverb"])
        history=[{"action":"applied","intent":"soft sine pad","applied":{"waveform":0,"attack":.4,"gain":.5}}]
        self.assertEqual(server.validate_history(history),history)
        for bad in [history*5,[{"action":"pending","applied":{"gain":.5}}],[{"action":"applied","applied":{"unknown":1}}]]:
            with self.assertRaises(ValueError): server.validate_history(bad)

    def test_audio_descriptors_are_numeric_and_bounded(self):
        valid={"rms_dbfs":-30,"peak_dbfs":-20,"spectral_centroid_hz":500,"high_frequency_energy_ratio":.1,"silent":False,"duration_seconds":4}
        self.assertEqual(server.validate_audio_context(valid),valid)
        for bad in [dict(valid,spectral_centroid_hz=float("nan")),dict(valid,path="private.wav"),dict(valid,duration_seconds=999)]:
            with self.assertRaises(ValueError):server.validate_audio_context(bad)

    def test_no_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OSError):
                server.openai_proposal({})

    def test_snapshot_and_finite_validation(self):
        for value in [{"cutoff": float("nan")}, {"cutoff": float("inf")}, {}, {"gain": .5}]:
            with self.assertRaises(ValueError):
                server.validate(value, complete=True)


if __name__ == "__main__":
    unittest.main()
