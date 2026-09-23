import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


def main() -> None:
    subprocess.run([PYTHON, "-m", "backend.app.pipeline", "--data", "data", "--out", "out"], cwd=ROOT, check=True)
    dist = ROOT / "frontend" / "dist"
    if not dist.exists():
        raise SystemExit("frontend/dist отсутствует. Выполните: cd frontend; npm ci; npm run build")
    print("Открывайте http://127.0.0.1:8000")
    try:
        subprocess.run([PYTHON, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, check=True)
    except KeyboardInterrupt:
        print("Сервер остановлен.")


if __name__ == "__main__":
    main()