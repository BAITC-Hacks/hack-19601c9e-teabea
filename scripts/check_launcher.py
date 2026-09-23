"""Smoke-test real launcher startup and Windows console group shutdown."""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if os.name != 'nt':
    raise SystemExit('This console-signal check is for Windows')
port = 8502
with socket.socket() as s:
    s.bind(('127.0.0.1', port))
process = subprocess.Popen([sys.executable, str(ROOT / 'run.py'), '--out', str(ROOT / 'verification/launcher'), '--edges', str(ROOT / 'verification/launcher-edges.csv'), '--port', str(port)], cwd=ROOT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError('Launcher stopped before readiness')
        try:
            with urlopen(f'http://127.0.0.1:{port}/_stcore/health', timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.5)
    else:
        raise AssertionError('Server readiness timeout')
    process.send_signal(signal.CTRL_BREAK_EVENT)
    assert process.wait(timeout=20) == 0
    with socket.socket() as s:
        assert s.connect_ex(('127.0.0.1', port)) != 0, 'Orphan server remains'
    print('PASS: real recalculation, HTTP 200, console interruption, no server left on port 8502')
finally:
    if process.poll() is None:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
