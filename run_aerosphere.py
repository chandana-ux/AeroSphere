"""One-command local demo launcher; never reruns reconstruction."""
import argparse
import json
import importlib.util
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT.parent / '.venv/Scripts/python.exe'
local = ROOT / 'config/local.json'
if local.exists():
    PYTHON = Path(json.loads(local.read_text(encoding='utf-8-sig')).get('python',str(PYTHON)))
elif (ROOT / '.venv/Scripts/python.exe').exists():
    PYTHON = ROOT / '.venv/Scripts/python.exe'


def main():
    if PYTHON.exists() and Path(sys.executable).resolve() != PYTHON.resolve():
        raise SystemExit(subprocess.call([str(PYTHON),str(Path(__file__).resolve()),*sys.argv[1:]]))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8501)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    if importlib.util.find_spec('streamlit') is None:
        raise SystemExit('Streamlit is missing from the project environment. See README.md.')
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1',args.port))
        except OSError:
            raise SystemExit(f'Port {args.port} is already in use. Open an existing AeroSphere session, or use --port {args.port+1}.')
    url=f'http://127.0.0.1:{args.port}'
    print(f'AeroSphere demo: {url}\nPress Ctrl+C to stop. Existing reconstruction is reused.',flush=True)
    def open_when_ready():
        for _ in range(40):
            try:
                with urllib.request.urlopen(url+'/_stcore/health',timeout=1) as response:
                    if response.status==200:
                        webbrowser.open(url)
                        return
            except OSError:
                time.sleep(0.5)
    if not args.no_browser:
        threading.Thread(target=open_when_ready,daemon=True).start()
    cmd=[sys.executable,'-m','streamlit','run',str(ROOT/'app/dashboard.py'),
         '--server.address','127.0.0.1','--server.port',str(args.port),'--server.headless','true',
         '--browser.gatherUsageStats','false','--server.fileWatcherType','none',
         '--client.toolbarMode','minimal','--theme.base','dark','--theme.primaryColor','#56d6c3']
    process=subprocess.Popen(cmd,cwd=ROOT)
    try:
        raise SystemExit(process.wait())
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=10)


if __name__=='__main__':
    main()
