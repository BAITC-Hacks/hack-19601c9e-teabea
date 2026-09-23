"""Recalculate real parquet twice, validate the UI contract and save evidence."""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
import pyarrow.parquet as pq
from ui.data import EXPORTS, load_results
from ui.graph import render_graph_html


def main():
    target = ROOT / 'verification'
    target.mkdir(exist_ok=True)
    timings = []
    for number in (1, 2):
        start = time.perf_counter()
        subprocess.run([sys.executable, str(ROOT / 'pipeline.py'), '--data', str(ROOT / 'data_parquet'), '--out', str(target / f'run{number}'), '--edges-export', str(target / f'edges{number}.csv')], check=True, cwd=ROOT)
        timings.append(round(time.perf_counter() - start, 3))
    nodes, clusters, top, edges, meta = load_results(target / 'run1', target / 'edges1.csv')
    parquet_rows = {}
    for name in ['nodes', 'edges', 'transactions']:
        frame = pq.read_table(ROOT / 'data_parquet' / f'{name}.parquet').to_pandas()
        parquet_rows[name] = len(frame)
        pd.testing.assert_frame_equal(frame, pd.read_parquet(ROOT / 'data_parquet' / f'{name}.parquet', engine='pyarrow'))
        if name == 'nodes':
            assert set(frame.gid.astype(str)) == set(nodes.gid)
    hashes = {}
    for name in EXPORTS:
        content = (target / 'run1' / name).read_bytes()
        assert content == (target / 'run2' / name).read_bytes(), name
        hashes[name] = hashlib.sha256(content).hexdigest()
    assert max(timings) <= 300
    assert ((nodes.priority_role + nodes.priority_volume + nodes.priority_bridge + nodes.priority_seed - nodes.priority_score).abs() <= 1e-6).all()
    examples = {'top': str(top.iloc[0].gid), 'arbitrary': str(nodes.iloc[len(nodes)//2].gid), 'isolate': str(nodes[(nodes.in_deg == 0) & (nodes.out_deg == 0)].iloc[0].gid), 'boundary': str(nodes[nodes.is_frontier_cutoff].iloc[0].gid)}
    examples.update({role: str(group.sort_values('priority_score', ascending=False).iloc[0].gid) for role, group in nodes.groupby('role')})
    report = dict(python=sys.version.split()[0], wall_seconds=timings, parquet_rows=parquet_rows, clusters=len(clusters), roles=nodes.role.value_counts().to_dict(), examples=examples, csv_sha256=hashes, metadata=meta)
    (target / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (target / 'graph.html').write_text(render_graph_html(nodes, edges), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
