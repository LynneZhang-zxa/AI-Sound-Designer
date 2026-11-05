"""Loopback-only UI for the offline synth experiment. No plugin integration."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from types import SimpleNamespace
from urllib.parse import urlparse
from generate_dataset import ROOT, sha256
from offline_design import STRENGTHS, create_proposal, apply


class Workbench:
    def __init__(self, directory, run, renderer):
        self.directory=Path(directory).resolve()
        if not self.directory.is_relative_to(ROOT): raise ValueError('Sessions must remain in canonical repository')
        self.directory.mkdir(parents=True,exist_ok=True)
        self.run=Path(run).resolve();self.renderer=Path(renderer).resolve()
        self.token=secrets.token_hex(32)
        self.lock=threading.Lock();self.jobs={};self.busy=False
        self.worker=ThreadPoolExecutor(max_workers=1)

    def submit(self, data):
        prompt=data.get('prompt');strength=data.get('strength','medium')
        if not isinstance(prompt,str) or not 0<len(prompt.strip())<=1800 or strength not in STRENGTHS:
            raise ValueError('请输入 1–1800 字符的修改意图，并选择有效强度。')
        local=data.get('local_only',True)
        if type(local) is not bool: raise ValueError('Invalid service mode')
        demo=data.get('demo',False)
        if type(demo) is not bool: raise ValueError('Invalid demo selection')
        if demo:
            original=ROOT/'ml/runs/offline_design_demo'
            metadata=json.loads((original/'proposal.json').read_text())
            performance=metadata['performance'];audio=(original/'original.wav').read_bytes()
        else:
            performance={'midi_note':data.get('midi_note'),'velocity':data.get('velocity')}
            if type(performance['midi_note']) is not int or not 48<=performance['midi_note']<=60:
                raise ValueError('MIDI 音高必须为 48–60 的整数。')
            v=performance['velocity']
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not .4<=v<=1:
                raise ValueError('Velocity 必须在 0.4–1.0 之间。')
            encoded=data.get('audio_base64')
            if not isinstance(encoded,str): raise ValueError('请选择 WAV 文件。')
            audio=base64.b64decode(encoded,validate=True)
        if not 44<len(audio)<=800000: raise ValueError('音频文件过大或为空；只支持四秒单声道 PCM24 WAV。')
        with self.lock:
            if self.busy: raise RuntimeError('已有任务正在运行，请稍后。')
            identifier=secrets.token_hex(12);folder=self.directory/identifier
            folder.mkdir();(folder/'upload.wav').write_bytes(audio)
            self.jobs[identifier]={'id':identifier,'state':'analyzing','folder':folder}
            self.busy=True
        args=SimpleNamespace(output=folder/'session',renderer=self.renderer,run=self.run,wav=folder/'upload.wav',
                             midi_note=performance['midi_note'],velocity=performance['velocity'],prompt=prompt,
                             strength=strength,local_only=local)
        self.worker.submit(self._propose,identifier,args)
        return identifier

    def _finish(self,identifier,state,**fields):
        with self.lock:
            self.jobs[identifier].update(state=state,**fields);self.busy=False

    def _propose(self,identifier,args):
        try:
            create_proposal(args)
            folder=args.output;plan=json.loads((folder/'proposal.json').read_text())
            result={k:plan[k] for k in ['before','after','prompt','strength','proposal_source','performance','reconstruction_distance']}
            result['proposal_sha256']=sha256(folder/'proposal.json')
            self._finish(identifier,'review',result=result)
        except Exception as error:
            self._finish(identifier,'error',error='分析失败：'+str(error)[:400])

    def snapshot(self,identifier):
        with self.lock:
            if identifier not in self.jobs: raise KeyError(identifier)
            return {k:v for k,v in self.jobs[identifier].items() if k!='folder'}

    def approve(self,identifier,digest):
        with self.lock:
            if identifier not in self.jobs: raise KeyError(identifier)
            job=self.jobs[identifier]
            if self.busy or job['state']!='review': raise RuntimeError('当前建议不可应用，或已有任务正在运行。')
            if digest!=job['result']['proposal_sha256']: raise ValueError('建议已改变，请重新查看。')
            job['state']='rendering';self.busy=True;folder=job['folder']/'session'
        self.worker.submit(self._apply,identifier,folder,digest)

    def _apply(self,identifier,folder,digest):
        try:
            result=apply(folder,digest,self.renderer)
            self._finish(identifier,'applied',applied=result)
        except Exception as error:
            self._finish(identifier,'error',error='渲染失败：'+str(error)[:400])

    def artifact(self,identifier,kind):
        paths={'original':'original.wav','reconstruction':'reconstruction/audio/render.wav',
               'modified':'modified/audio/render.wav','proposal':'proposal.json'}
        if kind not in paths: raise KeyError(kind)
        with self.lock:
            job=self.jobs[identifier]
            if job['state'] not in ('review','rendering','applied'): raise KeyError(kind)
            path=job['folder']/'session'/paths[kind]
        if not path.is_file(): raise KeyError(kind)
        return path


class Handler(BaseHTTPRequestHandler):
    def valid_host(self):
        return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'

    def respond(self,status,body,kind='application/json; charset=utf-8'):
        if not isinstance(body,bytes): body=json.dumps(body,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass

    def do_GET(self):
        if not self.valid_host(): self.respond(403,{'error':'Invalid host'});return
        path=urlparse(self.path).path;app=self.server.app
        try:
            if path=='/':
                page=(ROOT/'ml/workbench.html').read_text().replace('__SESSION_TOKEN__',app.token)
                self.respond(200,page.encode(),'text/html; charset=utf-8')
            elif path.startswith('/job/'):
                self.respond(200,app.snapshot(path.removeprefix('/job/')))
            elif path.startswith('/artifact/'):
                identifier,kind=path.removeprefix('/artifact/').split('/')
                file=app.artifact(identifier,kind)
                self.respond(200,file.read_bytes(),'audio/wav' if file.suffix=='.wav' else 'application/json')
            else: self.respond(404,{'error':'Not found'})
        except (KeyError,ValueError): self.respond(404,{'error':'Not found'})

    def do_POST(self):
        expected=f'http://127.0.0.1:{self.server.server_port}'
        if (not self.valid_host() or self.headers.get('Origin',expected)!=expected
            or self.headers.get('X-Session-Token')!=self.server.app.token):
            self.respond(403,{'error':'Invalid local session'});return
        try:
            self.connection.settimeout(5)
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=1100000 or self.headers.get('Content-Type')!='application/json':
                raise ValueError('Invalid request size or type')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError('Invalid JSON object')
            if self.path=='/propose':
                identifier=self.server.app.submit(data);self.respond(202,{'id':identifier})
            elif self.path=='/apply':
                self.server.app.approve(data['id'],data['proposal_sha256']);self.respond(202,{'id':data['id']})
            else: self.respond(404,{'error':'Not found'})
        except (ValueError,KeyError,TypeError) as error: self.respond(400,{'error':str(error)[:400]})
        except RuntimeError as error: self.respond(409,{'error':str(error)})
        except OSError: self.respond(500,{'error':'Local files unavailable'})

    def log_message(self,*_args): pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8780)
    parser.add_argument('--sessions',type=Path,default=ROOT/'ml/runs/workbench')
    parser.add_argument('--run',type=Path,default=ROOT/'ml/runs/pitch_velocity')
    parser.add_argument('--renderer',type=Path,default=ROOT/'build/DatasetRenderer')
    args=parser.parse_args()
    app=Workbench(args.sessions,args.run,args.renderer)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.app=app
    print(f'Offline workbench: http://127.0.0.1:{server.server_port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close();app.worker.shutdown(wait=True)


if __name__=='__main__': main()
