import base64
import os
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from generate_dataset import ROOT
from workbench import Workbench, Handler


class WorkbenchTests(unittest.TestCase):
    @unittest.skipIf(os.environ.get("ML_SKIP_LEGACY_MODEL_TESTS")=="1" or not (ROOT/"ml/runs/pitch_velocity/cnn/best.pt").is_file(),"Optional legacy workbench needs its frozen checkpoint; core Match does not")
    def test_http_review_apply_and_boundaries(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='workbench-test-') as temp:
            app=Workbench(Path(temp),ROOT/'ml/runs/pitch_velocity',ROOT/'build/DatasetRenderer')
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.app=app
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def request(path,data=None,headers=None):
                h={'Content-Type':'application/json','X-Session-Token':app.token,'Origin':base}
                if headers: h.update(headers)
                req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers=h)
                return urllib.request.urlopen(req,timeout=10)
            def expect_error(code,path,data,headers=None):
                with self.assertRaises(urllib.error.HTTPError) as error: request(path,data,headers)
                self.assertEqual(error.exception.code,code)
            def wait(identifier,target):
                for _ in range(300):
                    with request('/job/'+identifier) as response: result=json.load(response)
                    if result['state']=='error': self.fail(result['error'])
                    if result['state']==target: return result
                    time.sleep(.05)
                self.fail('Background job timed out')
            try:
                with request('/') as response:
                    page=response.read().decode();self.assertIn(app.token,page);self.assertIn('确认参数并渲染',page)
                expect_error(403,'/propose',{}, {'X-Session-Token':'wrong'})
                expect_error(403,'/propose',{}, {'Origin':'https://example.com'})
                expect_error(403,'/propose',{}, {'Host':'example.com'})
                expect_error(400,'/propose',{'prompt':'valid','audio_base64':'not base64','midi_note':48,'velocity':.8})
                expect_error(400,'/propose',{'prompt':'valid','midi_note':128,'velocity':.8})
                payload={'demo':True,'prompt':'暗一点，尾音短一点，保留起音。','strength':'strong','local_only':True}
                with request('/propose',payload) as response: identifier=json.load(response)['id']
                review=wait(identifier,'review');result=review['result']
                self.assertEqual(result['strength'],'strong');self.assertEqual(result['proposal_source']['source'],'local rules')
                self.assertLess(result['after']['cutoff'],result['before']['cutoff'])
                self.assertEqual(result['after']['attack'],result['before']['attack'])
                expect_error(404,'/artifact/'+identifier+'/modified',None)
                with request('/artifact/'+identifier+'/reconstruction') as response: original=response.read()
                self.assertEqual(original[:4],b'RIFF')
                expect_error(400,'/apply',{'id':identifier,'proposal_sha256':'wrong'})
                with request('/apply',{'id':identifier,'proposal_sha256':result['proposal_sha256']}) as response:
                    self.assertEqual(response.status,202)
                wait(identifier,'applied')
                with request('/artifact/'+identifier+'/modified') as response: modified=response.read()
                self.assertEqual(modified[:4],b'RIFF');self.assertNotEqual(original,modified)
                expect_error(409,'/apply',{'id':identifier,'proposal_sha256':result['proposal_sha256']})
                expect_error(404,'/artifact/'+identifier+'/../../AGENTS.md',None)
                # Uploaded WAV path, no input filenames or parameter labels enter inference.
                payload.pop('demo');payload.update(audio_base64=base64.b64encode(original).decode(),midi_note=48,velocity=.9814434784793344)
                with request('/propose',payload) as response: uploaded=json.load(response)['id']
                self.assertEqual(wait(uploaded,'review')['state'],'review')
            finally:
                server.shutdown();server.server_close();app.worker.shutdown(wait=True);thread.join()
