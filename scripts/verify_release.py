"""Recalculate twice from parquet; validate contract and record measured evidence."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import load, _validate_outputs

def main():
    work = ROOT / '.verification'
    work.mkdir(exist_ok=True)
    times = []
    for name in ['first', 'second']:
        start = time.perf_counter()
        subprocess.run([sys.executable, str(ROOT/'pipeline.py'), '--data', str(ROOT/'data_parquet'),
            '--out', str(work/name), '--edges-export', str(work/(name+'-edges.csv'))], check=True, stdout=subprocess.DEVNULL)
        times.append(round(time.perf_counter()-start, 3))
    data = load(ROOT/'data_parquet')
    for name in ['nodes','edges','transactions']:
        expected = pq.read_table(ROOT/'data_parquet'/f'{name}.parquet').to_pandas()
        actual = getattr(data, name)
        if name == 'transactions':
            expected['date'] = pd.to_datetime(expected.date)
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False)
    frames = {name: pd.read_csv(work/'first'/f'{name}.csv', dtype={'gid':'int64'})
        for name in ['nodes_roles','clusters','top_nodes','node_metrics_full']}
    full, clusters, top = [frames[x] for x in ['node_metrics_full','clusters','top_nodes']]
    _validate_outputs(full, clusters, top, data.nodes)
    assert list(frames['nodes_roles']) == ['gid','role','role_score','cluster_id','priority_score','evidence']
    assert list(clusters) == ['cluster_id','n_nodes','n_seed','sum_kzt_internal','top_gids','hypothesis']
    assert list(top) == ['rank','gid','role','priority_score','why']
    assert (full.groupby('cluster_id').size().sort_index().to_numpy() == clusters.sort_values('cluster_id').n_nodes.to_numpy()).all()
    assert (full.priority_score-full[['priority_role','priority_volume','priority_bridge','priority_seed']].sum(axis=1)).abs().max() <= 0.000001
    assert full[(full.in_deg == 0)&(full.out_deg == 0)].role.eq('peripheral').all()
    assert top.gid.tolist() == full.sort_values(['priority_score','gid'],ascending=[False,True]).head(len(top)).gid.tolist()
    hashes = {}
    for name in ['nodes_roles.csv','clusters.csv','top_nodes.csv']:
        content = (work/'first'/name).read_bytes()
        assert content == (work/'second'/name).read_bytes(), name
        assert content == (ROOT/'out'/name).read_bytes(), name
        hashes[name] = hashlib.sha256(content).hexdigest()
    examples = {'first_top': str(top.iloc[0].gid), 'arbitrary': str(full.sort_values('gid').iloc[len(full)//2].gid),
                'isolate': str(full[(full.in_deg==0)&(full.out_deg==0)].iloc[0].gid),
                'boundary': str(full[full.is_frontier_cutoff].iloc[0].gid)}
    for role, group in full.groupby('role'):
        examples[role] = str(group.sort_values(['priority_score','gid'], ascending=[False,True]).iloc[0].gid)
    report = dict(python=platform.python_version(), platform=platform.platform(),
        versions={p:importlib.metadata.version(p) for p in ['pandas','numpy','networkx','scipy','pyarrow','streamlit','pyvis','pytest']},
        cli_wall_seconds=times, hashes=hashes, input_rows={n:len(getattr(data,n)) for n in ['nodes','edges','transactions']},
        clusters=len(clusters), isolates=int(((full.in_deg==0)&(full.out_deg==0)).sum()), boundary=int(full.is_frontier_cutoff.sum()),
        role_counts=full.role.value_counts().to_dict(), examples=examples, standard_reader_comparison='all three parquet via pyarrow; no pqmini execution',
        browser='Unavailable in this session; no visual/network/download verification claimed')
    assert max(times) < 300
    (ROOT/'docs/verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))

if __name__ == '__main__':
    main()
