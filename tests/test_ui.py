from pathlib import Path
import re
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from ui.model import load_snapshot, subgraph, graph_html, LABELS

ROOT = Path(__file__).resolve().parents[1]


def test_snapshot_and_inline_string_identifiers():
    nodes, clusters, top, edges, meta = load_snapshot(ROOT/'out', ROOT/'data/edges.csv')
    visible, links = subgraph(nodes, edges, top, mode='selected', selected=top.iloc[0].gid,
        roles=list(LABELS), clusters=[], depths=list(range(5)), seed_only=False, minimum=0, hops=2)
    html = graph_html(visible, links)
    assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=', html, re.I)
    assert f'"id": "{top.iloc[0].gid}"' in html
    assert 'network.setOptions({physics:false})' in html


def test_missing_column_requests_recalculation(tmp_path):
    import shutil
    shutil.copytree(ROOT/'out', tmp_path/'out')
    frame = pd.read_csv(tmp_path/'out/node_metrics_full.csv', dtype={'gid':str})
    frame.drop(columns='priority_bridge').to_csv(tmp_path/'out/node_metrics_full.csv', index=False)
    with pytest.raises(ValueError, match='priority_bridge'):
        load_snapshot(tmp_path/'out', ROOT/'data/edges.csv')


def test_real_streamlit_search_top_filters_clusters_downloads():
    nodes, clusters, top, edges, meta = load_snapshot(ROOT/'out', ROOT/'data/edges.csv')
    at = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
    assert not at.exception
    isolate = nodes[(nodes.in_deg == 0) & (nodes.out_deg == 0)].iloc[0].gid
    at.text_input(key='query').set_value(isolate).run()
    assert not at.exception
    assert at.session_state['selected'] == isolate
    assert any('Видно узлов: 1 · рёбер: 0' in item.value for item in at.caption)
    assert any('Pass-through: н/д' in item.value for item in at.markdown)
    at.text_input(key='query').set_value('unknown').run()
    assert any('Узел не найден' in item.value for item in at.info)
    at.multiselect(key='roles').set_value([]).run()
    assert any('Нет узлов после фильтров' in item.value for item in at.info)
    at.button(key='top_'+top.iloc[0].gid).click().run()
    assert not at.exception
    assert at.session_state['selected'] == top.iloc[0].gid
    assert len(at.session_state['roles']) == 6
    at.radio(key='mode').set_value('all').run()
    at.checkbox(key='seed_only').check().run()
    assert at.session_state['mode'] == 'all'
    at.selectbox(key='cluster_choice').select(int(clusters.iloc[-1].cluster_id)).run()
    next(b for b in at.button if b.label == 'Показать кластер').click().run()
    assert at.session_state['clusters'] == [int(clusters.iloc[-1].cluster_id)]
    boundary = nodes[nodes.is_frontier_cutoff].iloc[0].gid
    at.text_input(key='query').set_value(boundary).run()
    assert any('Boundary' in item.value for item in at.warning)
    assert len(at.get('download_button')) == 3
    next(b for b in at.button if b.label == 'Обновить данные').click().run()
    assert not at.exception
