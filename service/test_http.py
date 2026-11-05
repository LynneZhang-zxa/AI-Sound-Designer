"""Loopback service validation and health, with no paid provider request."""
from http.server import HTTPServer
import json
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import server

class HTTPTests(unittest.TestCase):
    def test_health_valid_history_rejection_and_provider_failure(self):
        http=HTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{http.server_port}'
        params={'waveform':1,'attack':.1,'decay':.1,'sustain':.8,'release':.4,'cutoff':2000,'resonance':.707,'gain':.8}
        def post(value,extra_headers=None):
            request=urllib.request.Request(base+'/propose',data=json.dumps(value).encode(),headers=dict({'Content-Type':'application/json'},**(extra_headers or {})))
            try:
                with urllib.request.urlopen(request,timeout=2) as r:return r.status,json.load(r)
            except urllib.error.HTTPError as e:return e.code,json.load(e)
        try:
            with urllib.request.urlopen(base+'/health',timeout=2) as r:self.assertEqual(json.load(r)['service'],'resonanca-prompt')
            result={'proposal':{'gain':.4},'message':'Quieter','unsupported':[],'provider':'openai'}
            with patch('server.openai_proposal',return_value=result) as provider:
                self.assertEqual(post({'prompt':'quieter','parameters':params,'history':[]}), (200,result))
                self.assertTrue(provider.call_args.kwargs['with_details'])
                self.assertEqual(post({'prompt':'x','parameters':params,'history':[{'action':'pending'}]})[0],400)
                self.assertEqual(post({'prompt':'','parameters':params})[0],400)
                self.assertEqual(post({'prompt':'x','parameters':dict(params,gain=3)})[0],400)
                self.assertEqual(post({'prompt':'x','parameters':params,'audio':'not allowed'})[0],400)
                self.assertEqual(post({'prompt':'x','parameters':params},{'Origin':'https://example.invalid'})[0],403)
                self.assertEqual(provider.call_count,1)
            with patch('server.openai_proposal',side_effect=OSError('private upstream detail')):
                code,body=post({'prompt':'x','parameters':params})
                self.assertEqual(code,503);self.assertNotIn('private',json.dumps(body))
            upstream=urllib.error.HTTPError('https://api.openai.com/v1/responses',401,'unauthorized',{},None)
            with patch('server.openai_proposal',side_effect=upstream):
                code,body=post({'prompt':'x','parameters':params})
                self.assertEqual(code,503);self.assertEqual(body['upstream_status'],401)
                self.assertIn('authentication',body['error'])
        finally:http.shutdown();http.server_close();thread.join()
