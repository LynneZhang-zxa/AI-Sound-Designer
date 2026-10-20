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

    def test_bad_updates_rejected(self):
        for updates in [[],
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
