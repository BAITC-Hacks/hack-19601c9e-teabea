import io
import sys
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from ui import uploads
from ui.data import load_results

ROOT = Path(__file__).resolve().parents[1]


def files():
    return {
        'nodes': ('nodes.csv', b'gid,depth,is_seed\n100000000000000001,0,true\n100000000000000002,5,false\n100000000000000003,6,false\n'),
        'edges': ('edges.csv', b'src,dst,sum_kzt,n_tx,depth\n100000000000000001,100000000000000002,300,2,5\n100000000000000002,100000000000000003,200,1,6\n'),
        'transactions': ('transactions.csv', b'src,dst,date,sum_kzt\n100000000000000001,100000000000000002,2026-08-01,100\n100000000000000001,100000000000000002,2026-08-02,200\n100000000000000002,100000000000000003,2026-08-02,200\n'),
    }


def frames():
    return {name: uploads.read_upload(name, *file) for name, file in files().items()}


def test_real_calculation_csv_parquet_and_observation(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, 'WORK', tmp_path)
    tables = frames()
    for name, table in tables.items():
        buffer = io.BytesIO()
        table.to_parquet(buffer)
        pd.testing.assert_frame_equal(uploads.read_upload(name, name + '.parquet', buffer.getvalue()), table)
    out, edges = uploads.calculate(tables, dict(source='custom', max_depth=None, seed_incomplete=None))
    nodes, clusters, top, links, meta = load_results(out, edges)
    assert set(nodes.gid) == {'100000000000000001', '100000000000000002', '100000000000000003'}
    assert not nodes.is_frontier_cutoff.any()
    assert not (nodes.role == 'terminal').any()
    assert meta['observation']['max_depth'] is None
    assert nodes.depth.max() == 6
    out2, edges2 = uploads.calculate(tables, dict(source='custom', max_depth=6, seed_incomplete=False))
    boundary = load_results(out2, edges2)[0]
    assert boundary.loc[boundary.gid == '100000000000000003', 'is_frontier_cutoff'].item()
    assert Path(out).parent != Path(out2).parent


@pytest.mark.parametrize('table,column,values,message', [
    ('edges', 'n_tx', [1, 1], 'n_tx'),
    ('edges', 'sum_kzt', [999, 200], 'Суммы'),
    ('nodes', 'gid', [1, 2, 3], 'gid'),
    ('nodes', 'gid', [100000000000000001]*3, 'уникальным'),
])
def test_inconsistent_data_rejected(tmp_path, monkeypatch, table, column, values, message):
    monkeypatch.setattr(uploads, 'WORK', tmp_path)
    data = frames()
    data[table].loc[:, column] = values
    with pytest.raises(ValueError, match=message):
        uploads.validate_frames(data, {'max_depth': None})


@pytest.mark.parametrize('data,message', [
    (b'gid,depth,is_seed\n1e18,0,true\n', 'целые'),
    (b'gid,depth,is_seed\n9223372036854775808,0,true\n', 'int64'),
    (b'gid,depth,is_seed\n1,0,yes\n', 'is_seed'),
    (b'gid,depth\n1,0\n', 'столбцы'),
])
def test_strict_csv(data, message):
    with pytest.raises(ValueError, match=message):
        uploads.read_upload('nodes', 'nodes.csv', data)


def test_float_parquet_ids_rejected():
    data = pd.DataFrame(dict(gid=[1e18], depth=[0], is_seed=[True]))
    buffer = io.BytesIO()
    data.to_parquet(buffer)
    with pytest.raises(ValueError, match='float'):
        uploads.read_upload('nodes', 'nodes.parquet', buffer.getvalue())


def test_upload_calculate_search_top_download_and_example(monkeypatch, tmp_path):
    import hashlib
    from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
    organizer_files = list((ROOT/'data_parquet').glob('*.parquet'))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in organizer_files}
    downloads = {}
    original = MemoryMediaFileStorage.load_and_get_id
    def capture(self, path_or_data, mimetype, kind, filename=None):
        if filename in ('nodes_roles.csv', 'clusters.csv', 'top_nodes.csv'):
            downloads[filename] = path_or_data
        return original(self, path_or_data, mimetype, kind, filename)
    monkeypatch.setattr(MemoryMediaFileStorage, 'load_and_get_id', capture)
    monkeypatch.setattr(uploads, 'WORK', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['app.py', '--data', str(ROOT/'verification/run1'), '--edges', str(ROOT/'verification/edges1.csv')])
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=40).run()
    app.radio(key='source_mode').set_value('Свои данные').run()
    assert not app.exception
    assert not app.get('download_button')
    for name, (filename, content) in files().items():
        # Exercise actual uploader widget, including a mixed Parquet/CSV set.
        if name == 'edges':
            buffer = io.BytesIO()
            frames()[name].to_parquet(buffer)
            filename, content = 'edges.parquet', buffer.getvalue()
        app.file_uploader(key='upload_' + name).set_value((filename, content, 'application/octet-stream')).run()
    assert not app.exception
    assert len(app.dataframe) == 3
    def click(label):
        next(b for b in app.button if b.label == label).click().run()
        assert not app.exception
    click('Рассчитать новый граф')
    if 'upload_job' in app.session_state:
        assert next(b for b in app.button if b.label == 'Рассчитать новый граф').disabled
        app.session_state['upload_job'].result(timeout=40)
        app.run()
    assert any('Расчёт завершён' in s.value for s in app.success)
    assert len(app.get('download_button')) == 3
    custom_out = Path(app.session_state['upload_result'][0])
    assert all(content == (custom_out/name).read_bytes() for name, content in downloads.items())
    assert [m.value for m in app.metric][:3] == ['3', '2', '3']
    app.text_input(key='search_gid').set_value('100000000000000003')
    click('Найти по gid')
    assert app.session_state['selected_gid'] == '100000000000000003'
    next(b for b in app.button if b.key and b.key.startswith('top_')).click().run()
    assert not app.exception
    click('Показать весь граф')
    assert app.session_state['graph_mode'] == 'all'
    # Changing a single file hides the previous successful result.
    filename, content = files()['edges']
    app.file_uploader(key='upload_edges').set_value((filename, content.replace(b'300,2', b'300,1'), 'text/csv')).run()
    assert any('Ошибка проверки' in e.value for e in app.error)
    assert not app.get('download_button')
    assert not app.metric
    click('Открыть пример хакатона')
    assert app.session_state['source_mode'] == 'Пример хакатона'
    assert app.metric[0].value == '2248'
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in organizer_files}
