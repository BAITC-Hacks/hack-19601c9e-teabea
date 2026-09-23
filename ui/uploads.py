"""Strict upload boundary and isolated calculation workspaces."""
import hashlib
import io
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pipeline

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.user_runs'
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='money-graph')
INTEGER_COLUMNS = {'nodes': ['gid', 'depth'], 'edges': ['src', 'dst', 'n_tx', 'depth'], 'transactions': ['src', 'dst']}


def read_upload(name, filename, content):
    if len(content) > 50 * 1024 * 1024:
        raise ValueError(f'{name}: размер файла превышает 50 МБ')
    suffix = Path(filename).suffix.lower()
    if suffix == '.csv':
        frame = pd.read_csv(io.BytesIO(content), dtype='string', encoding='utf-8-sig')
    elif suffix == '.parquet':
        frame = pd.read_parquet(io.BytesIO(content), engine='pyarrow')
    else:
        raise ValueError(f'{name}: требуется CSV или Parquet')
    missing = pipeline.REQUIRED[name] - set(frame)
    if missing:
        raise ValueError(f'{name}: отсутствуют столбцы {", ".join(sorted(missing))}')
    if len(frame) > 100_000:
        raise ValueError(f'{name}: интерактивная загрузка ограничена 100 000 строками')
    for col in INTEGER_COLUMNS[name]:
        series = frame[col]
        # Reject float identifiers even if they happen to look integral: precision is already lost.
        if pd.api.types.is_float_dtype(series.dtype) and col in ('gid', 'src', 'dst'):
            raise ValueError(f'{name}.{col}: float недопустим; сохраните gid целым int64 или строкой')
        text = series.astype('string')
        if text.isna().any() or not text.str.fullmatch(r'0|[1-9][0-9]*').all():
            raise ValueError(f'{name}.{col}: нужны непустые неотрицательные целые без .0 и экспоненты')
        try:
            frame[col] = text.map(int).astype('int64')
        except (ValueError, OverflowError, TypeError):
            raise ValueError(f'{name}.{col}: значение выходит за пределы int64') from None
    if name == 'nodes':
        values = frame.is_seed.astype('string').str.lower()
        if values.isna().any() or not values.isin(['true', 'false', '1', '0']).all():
            raise ValueError('nodes.is_seed: допустимы true/false или 1/0')
        frame['is_seed'] = values.isin(['true', '1'])
    else:
        values = pd.to_numeric(frame.sum_kzt, errors='coerce')
        if not np.isfinite(values.to_numpy(dtype=float)).all() or (values < 0).any():
            raise ValueError(f'{name}.sum_kzt: нужны конечные неотрицательные числа')
        frame['sum_kzt'] = values.astype(float)
    if name == 'transactions':
        frame['date'] = pd.to_datetime(frame.date, errors='coerce', format='mixed')
        if frame.date.isna().any():
            raise ValueError('transactions.date: некорректная дата; используйте ISO YYYY-MM-DD')
    return frame


def write_inputs(frames, folder):
    folder.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_parquet(folder / f'{name}.parquet', index=False)


def validate_frames(frames, observation):
    if len(frames['nodes']) == 0 or frames['transactions'].empty:
        raise ValueError('Пустой набор: нужны узлы и хотя бы одна транзакция')
    if len(frames['nodes']) > 10_000:
        raise ValueError('Точный интерактивный расчёт ограничен 10 000 узлами')
    WORK.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='validate-', dir=WORK) as directory:
        write_inputs(frames, Path(directory))
        pipeline.load(Path(directory), max_depth=observation.get('max_depth'))


def calculate(frames, observation):
    validate_frames(frames, observation)
    folder = Path(tempfile.mkdtemp(prefix='dataset-', dir=WORK))
    source, out, edges = folder / 'input', folder / 'out', folder / 'edges.csv'
    write_inputs(frames, source)
    pipeline.run(source, out, edges, observation=observation)
    return str(out), str(edges)


def fingerprint(files, observation):
    digest = hashlib.sha256(json.dumps(observation, sort_keys=True).encode())
    for name, filename, content in files:
        digest.update(name.encode() + filename.encode() + content)
    return digest.hexdigest()


def preview(frame):
    result = frame.head(20).copy()
    for col in ('gid', 'src', 'dst'):
        if col in result:
            result[col] = result[col].astype('string')
    return result
