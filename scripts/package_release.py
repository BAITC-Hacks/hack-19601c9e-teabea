"""Build a local hackathon submission from an explicit allowlist."""
from pathlib import Path
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    files = [ROOT / name for name in ['README.md', 'pipeline.py', 'app.py', 'run.py',
        'requirements.txt', 'requirements-core.txt', 'requirements-ui.txt', 'requirements-dev.txt',
        'requirements-lock.txt', 'pytest.ini', '.streamlit/config.toml']]
    for directory in ['ui','tests','scripts','docs','out','data_parquet']:
        files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file()
            and '__pycache__' not in p.parts and p.suffix in ['.py','.md','.json','.svg','.csv','.parquet'])
    files.append(ROOT/'data/edges.csv')
    target = ROOT/'dist/money-graph-submission.zip'
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            archive.write(path, 'money-graph/'+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert not any(part in name.split('/') for name in archive.namelist()
                       for part in ['.venv','.git','__pycache__','.verification'])
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.sha256').write_text(digest+'  '+target.name+'\n', encoding='ascii')
    print(f'{target.name}: {target.stat().st_size} bytes; SHA256 {digest}')

if __name__ == '__main__':
    main()
