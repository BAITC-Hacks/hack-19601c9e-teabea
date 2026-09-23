"""Extract the submission into a fresh folder and run its default CLI and tests."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
work = Path(tempfile.mkdtemp(prefix='archive-', dir=ROOT/'.verification'))
with zipfile.ZipFile(ROOT/'dist/money-graph-submission.zip') as archive:
    assert all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in archive.namelist())
    archive.extractall(work)
project = work/'money-graph'
# Default input and output must resolve from the script, even from a different cwd.
subprocess.run([sys.executable, str(project/'pipeline.py')], cwd=work, check=True, stdout=subprocess.DEVNULL)
for name in ['nodes_roles.csv','clusters.csv','top_nodes.csv']:
    assert (project/'out'/name).read_bytes() == (ROOT/'out'/name).read_bytes()
subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=project, check=True)
print('Archive extraction, default CLI from another cwd, CSV equality, and packaged tests: PASS')
