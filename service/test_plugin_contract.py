"""Real JUCE HTTP worker against a local structured fixture; no external API call."""
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
from pathlib import Path
import subprocess
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ContractTests(unittest.TestCase):
    def test_real_cpp_worker_structured_history_and_apply(self):
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));received.append(data)
                body=json.dumps({'proposal':{'waveform':0,'attack':.4,'decay':.2,'sustain':.6,'release':1.2,'cutoff':800,'resonance':.8,'gain':.4},'message':'Contract fixture','unsupported':[]}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            result=subprocess.run([str(ROOT/'build/SynthTests'),'--contract',f'http://127.0.0.1:{server.server_port}/propose'],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('CONTRACT PASS',result.stdout);self.assertEqual(len(received),1)
            self.assertEqual(received[0]['history'][0]['action'],'applied');self.assertEqual(len(received[0]['parameters']),8)
            self.assertEqual(received[0]['audio_context']['spectral_centroid_hz'],500)
            self.assertNotIn('audio',received[0])
        finally:server.shutdown();server.server_close();thread.join()

    def test_cpp_worker_close_while_response_is_pending(self):
        received=threading.Event();release=threading.Event()
        class SlowHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.send_header('Content-Length','15');self.end_headers()
                received.set();release.wait(10)
                try:self.wfile.write(b'{"cutoff":800}')
                except (BrokenPipeError,ConnectionResetError):pass
            def log_message(self,*args):pass
        server=HTTPServer(('127.0.0.1',0),SlowHandler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            result=subprocess.run([str(ROOT/'build/SynthTests'),'--cancel',f'http://127.0.0.1:{server.server_port}/propose'],capture_output=True,text=True,timeout=8)
            self.assertTrue(received.is_set(),'The cancellation test never reached its pending-response condition')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertIn('CANCEL PASS',result.stdout)
        finally:release.set();server.shutdown();server.server_close();thread.join()
