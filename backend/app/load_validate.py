from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


class DataValidationError(ValueError):
    pass


@dataclass
class Dataset:
    edges: pd.DataFrame
    nodes: pd.DataFrame
    transactions: pd.DataFrame
    warnings: list[str]


def _require_columns(frame: pd.DataFrame, name: str, columns: set[str]) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise DataValidationError(f"{name}: отсутствуют колонки {sorted(missing)}")


def load_validate(data_dir: Path) -> Dataset:
    paths = {name: data_dir / f"{name}.parquet" for name in ("nodes", "edges", "transactions")}
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise DataValidationError(f"Не найдены parquet: {', '.join(missing)}")
    nodes, edges, tx = (pd.read_parquet(paths[name]) for name in ("nodes", "edges", "transactions"))
    _require_columns(nodes, "nodes", {"gid", "depth", "is_seed"})
    _require_columns(edges, "edges", {"src", "dst", "sum_kzt", "n_tx", "depth"})
    _require_columns(tx, "transactions", {"src", "dst", "date", "sum_kzt"})
    if nodes.gid.duplicated().any():
        raise DataValidationError("nodes.gid должен быть уникальным")
    if edges.duplicated(["src", "dst"]).any():
        raise DataValidationError("edges содержит повторяющиеся пары src,dst")
    if not nodes.depth.between(0, 4).all() or not edges.depth.between(1, 4).all():
        raise DataValidationError("depth должен быть в диапазоне 0..4 для nodes и 1..4 для edges")
    for frame, name, cols in ((edges, "edges", ["sum_kzt", "n_tx"]), (tx, "transactions", ["sum_kzt"])):
        if not np.isfinite(frame[cols].to_numpy(dtype=float)).all():
            raise DataValidationError(f"{name}: суммы должны быть конечными")
        if (frame["sum_kzt"] < 0).any():
            raise DataValidationError(f"{name}: суммы не могут быть отрицательными")
    if (edges.n_tx < 1).any():
        raise DataValidationError("edges.n_tx должен быть положительным")
    node_ids = set(nodes.gid.astype("int64"))
    if not set(edges.src).issubset(node_ids) or not set(edges.dst).issubset(node_ids):
        raise DataValidationError("edges содержит ссылку на отсутствующий node")
    if not set(tx.src).issubset(node_ids) or not set(tx.dst).issubset(node_ids):
        raise DataValidationError("transactions содержит ссылку на отсутствующий node")
    tx = tx.copy()
    tx["date"] = pd.to_datetime(tx["date"], errors="coerce")
    if tx.date.isna().any():
        raise DataValidationError("transactions.date содержит некорректные даты")
    if tx.empty:
        raise DataValidationError("transactions не может быть пустым")
    agg = tx.groupby(["src", "dst"], as_index=False).agg(sum_tx=("sum_kzt", "sum"), n_tx_tx=("sum_kzt", "size"))
    compared = edges.merge(agg, on=["src", "dst"], how="outer", indicator=True)
    if (compared._merge != "both").any():
        raise DataValidationError("Пары edges и transactions не совпадают")
    if not np.isclose(compared.sum_kzt, compared.sum_tx, rtol=1e-9, atol=0.01).all():
        raise DataValidationError("Суммы edges и transactions расходятся больше допуска 0.01 KZT")
    if not (compared.n_tx == compared.n_tx_tx).all():
        raise DataValidationError("n_tx edges не совпадает с количеством transactions")
    warnings = []
    if int((nodes.is_seed & ~nodes.gid.isin(set(edges.src) | set(edges.dst))).sum()):
        warnings.append("Часть seed не имеет ребер в наблюдаемой выборке")
    return Dataset(edges.astype({"src": "int64", "dst": "int64", "n_tx": "int64"}), nodes.astype({"gid": "int64", "depth": "int64"}), tx, warnings)