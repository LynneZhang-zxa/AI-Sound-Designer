"""One foreground command for loopback services; never kills pre-existing services."""
import json
import argparse
import hashlib
import signal
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]


def health(port,expected):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as stream:
            data=json.loads(stream.read(4096))
        return data if isinstance(data,dict) and data.get('service')==expected else None
    except (OSError,ValueError):return None


def restart_ai(current):
    if not current: return
    if not os.environ.get('OPENAI_API_KEY'):raise RuntimeError('Set OPENAI_API_KEY in this terminal before restarting AI; the existing process was left running.')
    listing=subprocess.run(['lsof','-nP','-t','-iTCP:8765','-sTCP:LISTEN'],capture_output=True,text=True,check=True)
    pids=set(int(v) for v in listing.stdout.split())
    if len(pids)!=1:raise RuntimeError('Cannot identify a unique AI worker; existing processes left running.')
    pid=pids.pop();command=subprocess.check_output(['ps','-p',str(pid),'-o','args='],text=True).strip()
    if str(ROOT/'service/server.py') not in command or '--provider openai' not in command:raise RuntimeError('AI process identity differs; refusing to stop it.')
    os.kill(pid,signal.SIGTERM)
    for _ in range(50):
        if not health(8765,'resonanca-prompt'):return
        time.sleep(.1)
    raise RuntimeError('AI worker did not stop normally; no force termination performed.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--restart-ai',action='store_true',help='Restart only the recognized canonical OpenAI worker using this terminal key environment')
    args=parser.parse_args();children=[]
    try:
        for port,name,command in [
            (8766,'resonanca-analysis',[str(ROOT/'ml/.venv/bin/python'),'-u',str(ROOT/'ml/plugin_analysis_service.py')]),
            (8765,'resonanca-prompt',[sys.executable,'-u',str(ROOT/'service/server.py'),'--provider','openai'])]:
            current=health(port,name)
            if port==8765 and args.restart_ai and current:
                restart_ai(current);current=None
            if port==8766 and current and (current.get('comparison_version')!=1 or current.get('match_diagnostics_version')!=1):
                raise RuntimeError('An older analysis worker lacks current comparison/match diagnostics. Stop that worker normally in its terminal, then rerun scripts/start-assistant.sh. Existing processes were left running.')
            if port==8765 and current and current.get('source_sha256')!=hashlib.sha256((ROOT/'service/server.py').read_bytes()).hexdigest():
                raise RuntimeError('An older OpenAI worker is still running. In your key-configured terminal run: bash scripts/start-assistant.sh --restart-ai. No key needs to be re-entered if it is exported there.')
            if current:
                print(f'Reusing {name} on {port}: {json.dumps(current)}',flush=True);continue
            if port==8765 and not os.environ.get('OPENAI_API_KEY'):
                print('OpenAI not configured in this terminal. Plugin local rules remain available. Set OPENAI_API_KEY securely and restart this command to enable Live AI.',flush=True);continue
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
            process=subprocess.Popen(command,cwd=ROOT,env=env);children.append(process)
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                if process.poll() is not None:raise RuntimeError(f'{name} could not start; check whether an older service occupies port {port}. Quit only that service from its own terminal, then retry.')
                if health(port,name):break
                time.sleep(.2)
            else:raise RuntimeError(f'{name} did not become healthy')
        print('Assistant services ready. Keep this terminal open; Ctrl-C stops only processes started here.',flush=True)
        while True:
            if any(p.poll() is not None for p in children):raise RuntimeError('A managed service stopped')
            time.sleep(1)
    except KeyboardInterrupt:pass
    except (RuntimeError,OSError) as error:
        print(str(error),file=sys.stderr);return 1
    finally:
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
    return 0

if __name__=='__main__':sys.exit(main())
