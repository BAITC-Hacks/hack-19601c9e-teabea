import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


def interrupted(signum, frame):
    raise KeyboardInterrupt


def main() -> None:
    parser = argparse.ArgumentParser(description="Пересчёт parquet и запуск Streamlit")
    parser.add_argument("--data", type=Path, default=ROOT / "data_parquet")
    parser.add_argument("--out", type=Path, default=ROOT / "out")
    parser.add_argument("--edges", type=Path, default=ROOT / "data/edges.csv")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    if os.name == "nt":
        signal.signal(signal.SIGBREAK, interrupted)
    data, out, edges = (path.resolve() for path in (args.data, args.out, args.edges))
    out.parent.mkdir(parents=True, exist_ok=True)
    child = None
    try:
        for command in ([PYTHON, str(ROOT / "pipeline.py"), "--data", str(data), "--out", str(out), "--edges-export", str(edges)],
                        [PYTHON, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.address", "127.0.0.1", "--server.port", str(args.port), "--server.headless", "true", "--browser.gatherUsageStats", "false", "--", "--data", str(out), "--edges", str(edges)]):
            child = subprocess.Popen(command, cwd=ROOT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            while True:
                try:
                    # Short waits let Windows deliver console signals to Python.
                    code = child.wait(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if code:
                raise SystemExit(code)
    except KeyboardInterrupt:
        print("Сервер остановлен.")
    finally:
        if child is not None and child.poll() is None:
            if os.name == "nt":
                child.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], check=False, capture_output=True)
                else:
                    child.kill()
                child.wait()


if __name__ == "__main__":
    main()
