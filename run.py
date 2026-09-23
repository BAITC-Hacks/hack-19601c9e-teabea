"""Recalculate from parquet, then serve the local Streamlit interface."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def wait_for(command):
    child = subprocess.Popen(command, cwd=ROOT)
    try:
        return child.wait()
    except KeyboardInterrupt:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        return 130


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT / 'data_parquet')
    parser.add_argument('--out', type=Path, default=ROOT / 'out')
    parser.add_argument('--edges-export', type=Path, default=ROOT / 'data/edges.csv')
    args = parser.parse_args()
    data, out, edges = (str(p.resolve()) for p in (args.data, args.out, args.edges_export))
    code = wait_for([sys.executable, str(ROOT / 'pipeline.py'), '--data', data,
                     '--out', out, '--edges-export', edges])
    if code:
        return code
    print('http://127.0.0.1:8501', flush=True)
    return wait_for([sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
                     '--server.address', '127.0.0.1', '--server.port', '8501',
                     '--', '--data', out, '--edges', edges])


if __name__ == '__main__':
    sys.exit(main())
