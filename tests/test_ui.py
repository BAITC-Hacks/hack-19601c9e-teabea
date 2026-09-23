import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from ui.data import ROLE_LABELS, load_results, select_graph, signature
from ui.graph import render_graph_html

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification/run1"
EDGES = ROOT / "verification/edges1.csv"


@pytest.fixture
def results():
    return load_results(OUT, EDGES)


def test_string_ids_offline_html_and_isolate(results):
    nodes, clusters, top, edges, _ = results
    isolated = nodes[(nodes.in_deg == 0) & (nodes.out_deg == 0)].iloc[0].gid
    n, e = select_graph(nodes, edges, top, mode="selected", selected=isolated, roles=list(ROLE_LABELS), clusters=[], depths=[], seed_only=False, minimum=0, hops=2)
    assert list(n.gid) == [isolated] and e.empty
    page = render_graph_html(nodes, edges)
    assert not re.search(r'<(?:script|link)\b[^>]*(?:src|href)\s*=', page, re.I)
    serialized = re.search(r'const nodes=new vis.DataSet\((.*?)\),edges=', page).group(1)
    assert {n['id'] for n in json.loads(serialized)} == set(nodes.gid)
    assert all(isinstance(n['id'], str) for n in json.loads(serialized))
    assert 'setTimeout' in page


def test_filters_and_bidirectional_two_hops(results):
    nodes, _, top, edges, _ = results
    options = dict(mode="all", selected=None, roles=[], clusters=[], depths=[], seed_only=False, minimum=0, hops=1)
    assert select_graph(nodes, edges, top, **options)[0].empty
    options.update(roles=list(ROLE_LABELS), mode="selected", selected=top.iloc[0].gid)
    first, _ = select_graph(nodes, edges, top, **options)
    second, _ = select_graph(nodes, edges, top, **(options | dict(hops=2)))
    assert set(first.gid) <= set(second.gid)
    touching = edges[(edges.src == options['selected']) | (edges.dst == options['selected'])]
    assert set(first.gid) == {options['selected']} | set(touching.src) | set(touching.dst)


def test_missing_contract_and_cache(tmp_path, results):
    import shutil
    for file in OUT.iterdir():
        shutil.copyfile(file, tmp_path / file.name)
    before = signature(tmp_path, EDGES)
    path = tmp_path / 'node_metrics_full.csv'
    data = pd.read_csv(path, dtype={'gid': 'string'}).drop(columns='explanation')
    data.to_csv(path, index=False)
    assert signature(tmp_path, EDGES) != before
    with pytest.raises(ValueError, match='explanation'):
        load_results(tmp_path, EDGES)


def test_streamlit_interactions(monkeypatch, results):
    from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
    downloads = {}
    original = MemoryMediaFileStorage.load_and_get_id
    def capture(self, path_or_data, mimetype, kind, filename=None):
        if filename in ('nodes_roles.csv', 'clusters.csv', 'top_nodes.csv'):
            downloads[filename] = path_or_data
        return original(self, path_or_data, mimetype, kind, filename)
    monkeypatch.setattr(MemoryMediaFileStorage, 'load_and_get_id', capture)
    nodes, clusters, top, _, _ = results
    monkeypatch.setattr(sys, 'argv', ['app.py', '--data', str(OUT), '--edges', str(EDGES)])
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert not app.exception
    def click(label):
        next(b for b in app.button if b.label == label).click().run()
        assert not app.exception
    isolate = nodes[(nodes.in_deg == 0) & (nodes.out_deg == 0)].iloc[0].gid
    app.text_input(key='search_gid').set_value(isolate)
    click('Найти по gid')
    assert app.session_state['selected_gid'] == isolate
    assert app.session_state['graph_mode'] == 'selected'
    assert any('Видимые узлы: 1 · видимые рёбра: 0' in c.value for c in app.caption)
    app.text_input(key='search_gid').set_value('999')
    click('Найти по gid')
    assert app.session_state['selected_gid'] == isolate
    assert any('не найден' in x.value for x in app.info)
    app.multiselect(key='role_filter').set_value([]).run()
    assert any('Нет узлов' in x.value for x in app.info)
    app.button(key='top_' + top.iloc[0].gid).click().run()
    assert not app.exception
    assert app.session_state['selected_gid'] == top.iloc[0].gid
    assert app.session_state['role_filter'] == list(ROLE_LABELS)
    app.radio(key='graph_mode').set_value('all').run()
    app.checkbox(key='seed_only').check().run()
    assert app.session_state['graph_mode'] == 'all'
    click('Сбросить фильтры')
    assert app.session_state['graph_mode'] == 'all'
    app.selectbox(key='cluster_choice').select(clusters.iloc[-1].cluster_id).run()
    click('Показать кластер на графе')
    assert app.session_state['cluster_filter'] == [clusters.iloc[-1].cluster_id]
    boundary = nodes[nodes.is_frontier_cutoff].iloc[0].gid
    app.text_input(key='search_gid').set_value(boundary)
    click('Найти по gid')
    assert any('Boundary' in w.value for w in app.warning)
    click('Обновить данные')
    assert len(app.get('download_button')) == 3
    assert len(downloads) == 3
    for name, content in downloads.items():
        assert content == (OUT / name).read_bytes()
    assert not app.exception


def test_refresh_reads_changed_results_and_missing_schema_stops(monkeypatch, tmp_path, results):
    import shutil
    for file in OUT.iterdir():
        shutil.copyfile(file, tmp_path / file.name)
    monkeypatch.setattr(sys, 'argv', ['app.py', '--data', str(tmp_path), '--edges', str(EDGES)])
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    gid = results[2].iloc[0].gid
    app.button(key='top_' + gid).click().run()
    path = tmp_path / 'node_metrics_full.csv'
    frame = pd.read_csv(path, dtype={'gid': 'string'})
    frame.loc[frame.gid == gid, 'explanation'] = 'Обновлённое объяснение после пересчёта'
    frame.to_csv(path, index=False)
    next(b for b in app.button if b.label == 'Обновить данные').click().run()
    assert not app.exception
    assert any('Обновлённое объяснение' in m.value for m in app.markdown)
    frame.drop(columns='priority_bridge').to_csv(path, index=False)
    app.run()
    assert not app.exception
    assert any('Требуется пересчёт' in e.value for e in app.error)
    assert len(app.get('iframe')) == 0
