"""Read the pipeline contract without recomputing analytical results."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROLE_LABELS = dict(consolidator="Консолидация", transit="Транзит", distributor="Распределение", terminal="Возможный конечный получатель", coordinator="Координация — гипотеза", peripheral="Недостаточно выраженных признаков")
ROLE_COLORS = dict(zip(ROLE_LABELS, ["#ed7772", "#48d5bd", "#579cf5", "#ae91ed", "#efbf58", "#778594"]))
EXPORTS = ("nodes_roles.csv", "clusters.csv", "top_nodes.csv")
SCHEMAS = {
    "nodes_roles.csv": "gid role role_score cluster_id priority_score evidence",
    "clusters.csv": "cluster_id n_nodes n_seed sum_kzt_internal top_gids hypothesis",
    "top_nodes.csv": "rank gid role priority_score why",
    "node_metrics_full.csv": "gid role role_score cluster_id priority_score evidence depth is_seed in_deg out_deg in_kzt out_kzt in_tx out_tx pagerank betweenness pass_through is_frontier_cutoff n_seed_neighbors component_id why explanation priority_role priority_volume priority_bridge priority_seed",
}


def signature(out, edges):
    if (out.parent / ('.' + out.name + '.publishing')).exists():
        raise ValueError('Публикуются новые результаты; обновите страницу после завершения расчёта')
    paths = [out / name for name in SCHEMAS] + [out / "run_metadata.json", edges]
    return hashlib.sha256(b"".join(str(p).encode() + p.read_bytes() for p in paths)).hexdigest()


def load_results(out, edges_path):
    out = Path(out)
    if (out.parent / ('.' + out.name + '.publishing')).exists():
        raise ValueError('Публикуются новые результаты; обновите страницу после завершения расчёта')
    frames = {}
    for name, columns in SCHEMAS.items():
        frame = pd.read_csv(out / name, dtype={"gid": "string", "top_gids": "string"})
        missing = set(columns.split()) - set(frame)
        if missing:
            raise ValueError(f"{name}: отсутствуют поля {', '.join(sorted(missing))}")
        frames[name] = frame
    nodes, roles, clusters, top = (frames[k] for k in ("node_metrics_full.csv", *EXPORTS))
    edges = pd.read_csv(edges_path, dtype={"src": "string", "dst": "string"})
    if not {"src", "dst", "sum_kzt", "n_tx", "depth"} <= set(edges):
        raise ValueError("edges.csv: неполная схема")
    for frame, cols in [(nodes, ["gid"]), (roles, ["gid"]), (top, ["gid"]), (edges, ["src", "dst"])]:
        for col in cols:
            if frame[col].isna().any() or not frame[col].str.fullmatch(r"[0-9]+").all():
                raise ValueError(f"{col}: ожидаются десятичные строковые идентификаторы")
    ids = set(nodes.gid)
    if nodes.gid.duplicated().any() or roles.gid.duplicated().any() or ids != set(roles.gid):
        raise ValueError("Нарушено уникальное покрытие gid")
    if not (set(top.gid) | set(edges.src) | set(edges.dst)) <= ids:
        raise ValueError("Неизвестный gid в топе или рёбрах")
    if not nodes.role.isin(ROLE_LABELS).all():
        raise ValueError("Неизвестная роль")
    numeric = "role_score priority_score cluster_id depth in_deg out_deg in_kzt out_kzt in_tx out_tx pagerank betweenness n_seed_neighbors component_id priority_role priority_volume priority_bridge priority_seed".split()
    if not np.isfinite(nodes[numeric].to_numpy(dtype=float)).all():
        raise ValueError("Неконечные численные метрики")
    if not np.isfinite(edges[["sum_kzt", "n_tx", "depth"]].to_numpy(dtype=float)).all() or (edges.sum_kzt < 0).any():
        raise ValueError("Некорректные метрики рёбер")
    for col in ("role_score", "priority_score"):
        if not nodes[col].between(0, 1).all():
            raise ValueError(f"{col}: ожидается 0–1")
    pd.testing.assert_frame_equal(nodes.set_index("gid")[list(roles.columns[1:])].sort_index(), roles.set_index("gid").sort_index(), check_dtype=False)
    if not nodes.evidence.str.len().between(1, 200).all():
        raise ValueError("Некорректное evidence")
    counts = nodes.groupby("cluster_id").size().sort_index()
    if clusters.cluster_id.duplicated().any() or not counts.equals(clusters.set_index("cluster_id").n_nodes.sort_index()):
        raise ValueError("Нарушено кластерное покрытие")
    if len(top) < min(20, len(nodes)) or top.gid.duplicated().any() or not top.priority_score.is_monotonic_decreasing:
        raise ValueError("Некорректный глобальный топ")
    pd.testing.assert_frame_equal(top.set_index("gid")[["role", "priority_score"]].sort_index(), nodes.set_index("gid").loc[top.gid, ["role", "priority_score"]].sort_index(), check_dtype=False)
    for col in ("is_seed", "is_frontier_cutoff"):
        values = nodes[col].astype(str).str.lower()
        if not values.isin(["true", "false", "1", "0"]).all():
            raise ValueError(f"Некорректный {col}")
        nodes[col] = values.isin(["true", "1"])
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    required_meta = "status input_rows seed_count period_from period_to pipeline_seconds thresholds method warnings".split()
    if not set(required_meta) <= set(meta) or meta["status"] != "success":
        raise ValueError("Метаданные не подтверждают успешный расчёт")
    if meta["input_rows"] != dict(nodes=len(nodes), edges=len(edges), transactions=int(edges.n_tx.sum())):
        raise ValueError("Метаданные и CSV относятся к разным расчётам")
    return nodes, clusters, top, edges, meta


def select_graph(nodes, edges, top, *, mode, selected, roles, clusters, depths, seed_only, minimum, hops):
    visible = nodes[nodes.role.isin(roles)]
    if clusters:
        visible = visible[visible.cluster_id.isin(clusters)]
    if depths:
        visible = visible[visible.depth.isin(depths)]
    if seed_only:
        visible = visible[visible.is_seed]
    ids = set(visible.gid)
    eligible = edges[(edges.sum_kzt >= minimum) & edges.src.isin(ids) & edges.dst.isin(ids)]
    if mode != "all":
        reached = ({selected} if selected else set()) if mode == "selected" else set(top.head(20).gid)
        reached &= ids
        for _ in range(hops if mode == "selected" else 1):
            adjacent = eligible[eligible.src.isin(reached) | eligible.dst.isin(reached)]
            reached |= set(adjacent.src) | set(adjacent.dst)
        ids = reached
    return visible[visible.gid.isin(ids)], eligible[eligible.src.isin(ids) & eligible.dst.isin(ids)]
