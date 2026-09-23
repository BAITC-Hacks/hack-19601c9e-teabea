from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import networkx as nx
import numpy as np
import pandas as pd

ROLES = ("consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral")
ROLE_WEIGHTS = {"coordinator": 1.0, "consolidator": 0.9, "distributor": 0.75, "transit": 0.35, "terminal": 0.25, "peripheral": 0.10}
REQUIRED = {
    "nodes": {"gid", "depth", "is_seed"},
    "edges": {"src", "dst", "sum_kzt", "n_tx", "depth"},
    "transactions": {"src", "dst", "date", "sum_kzt"},
}


@dataclass
class Dataset:
    nodes: pd.DataFrame
    edges: pd.DataFrame
    transactions: pd.DataFrame
    warnings: list[str]


class ValidationError(ValueError):
    pass


def _root() -> Path:
    return Path(__file__).resolve().parent


def _resolve_cli_path(value: str | None, default: Path) -> Path:
    return default if value is None else Path(value).expanduser().resolve()


def _read_input(data_dir: Path, name: str) -> pd.DataFrame:
    parquet = data_dir / f"{name}.parquet"
    csv = data_dir / f"{name}.csv"
    if parquet.exists() and csv.exists():
        raise ValidationError(f"{data_dir}: одновременно найдены {parquet.name} и {csv.name}; оставьте один полный набор")
    if parquet.exists():
        return pd.read_parquet(parquet)
    if csv.exists():
        return pd.read_csv(csv, parse_dates=["date"] if name == "transactions" else None)
    raise ValidationError(f"{data_dir}: не найден {name}.parquet или {name}.csv")


def _require_columns(frame: pd.DataFrame, name: str) -> None:
    missing = REQUIRED[name] - set(frame.columns)
    if missing:
        raise ValidationError(f"{name}: отсутствуют колонки {sorted(missing)}")


def _is_integer_series(series: pd.Series) -> bool:
    return pd.api.types.is_integer_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype)


def load(data_dir: Path) -> Dataset:
    if not data_dir.is_dir():
        raise ValidationError(f"Входная папка не найдена: {data_dir}")
    nodes = _read_input(data_dir, "nodes")
    edges = _read_input(data_dir, "edges")
    transactions = _read_input(data_dir, "transactions")
    for frame, name in ((nodes, "nodes"), (edges, "edges"), (transactions, "transactions")):
        _require_columns(frame, name)
    for name, frame, columns in (
        ("nodes", nodes, ("gid", "depth")),
        ("edges", edges, ("src", "dst", "n_tx", "depth")),
        ("transactions", transactions, ("src", "dst")),
    ):
        for column in columns:
            if not _is_integer_series(frame[column]):
                raise ValidationError(f"{name}.{column} должен быть целым типом; найден {frame[column].dtype}")
    if not pd.api.types.is_bool_dtype(nodes.is_seed.dtype):
        raise ValidationError(f"nodes.is_seed должен быть bool; найден {nodes.is_seed.dtype}")
    for name, frame in (("edges", edges), ("transactions", transactions)):
        values = pd.to_numeric(frame.sum_kzt, errors="coerce")
        if not np.isfinite(values.to_numpy(dtype="float64")).all() or (values < 0).any():
            raise ValidationError(f"{name}.sum_kzt должен быть конечным и неотрицательным")
    if (edges.n_tx <= 0).any() or not _is_integer_series(edges.n_tx):
        raise ValidationError("edges.n_tx должен быть положительным целым")
    if nodes.gid.isna().any() or nodes.gid.duplicated().any():
        raise ValidationError("nodes.gid должен быть непустым и уникальным")
    if edges[["src", "dst"]].isna().any().any() or edges.duplicated(["src", "dst"]).any():
        raise ValidationError("edges.src/dst не должны быть пустыми; пары должны быть уникальными")
    if not nodes.depth.between(0, 4).all() or not edges.depth.between(1, 4).all():
        raise ValidationError("depth должен быть 0..4 в nodes и 1..4 в edges")
    node_ids = set(nodes.gid.astype("int64"))
    if not set(edges.src).issubset(node_ids) or not set(edges.dst).issubset(node_ids):
        raise ValidationError("edges ссылается на отсутствующий gid")
    if not set(transactions.src).issubset(node_ids) or not set(transactions.dst).issubset(node_ids):
        raise ValidationError("transactions ссылается на отсутствующий gid")
    transactions = transactions.copy()
    transactions["date"] = pd.to_datetime(transactions.date, errors="coerce")
    if transactions.date.isna().any():
        raise ValidationError("transactions.date содержит некорректные даты")
    if transactions.empty:
        raise ValidationError("transactions не может быть пустым")
    aggregate = transactions.groupby(["src", "dst"], as_index=False).agg(sum_tx=("sum_kzt", "sum"), n_tx_tx=("sum_kzt", "size"))
    compared = edges.merge(aggregate, on=["src", "dst"], how="outer", indicator=True)
    if (compared._merge != "both").any():
        raise ValidationError("Пары edges и transactions не совпадают")
    if not np.isclose(compared.sum_kzt, compared.sum_tx, atol=0.01, rtol=1e-12).all():
        raise ValidationError("Суммы edges и transactions расходятся больше допуска 0.01 KZT и rel_tol=1e-12")
    if not (compared.n_tx == compared.n_tx_tx).all():
        raise ValidationError("edges.n_tx не совпадает с количеством transactions")
    warnings: list[str] = []
    edge_ids = set(edges.src) | set(edges.dst)
    if int((nodes.is_seed & ~nodes.gid.isin(edge_ids)).sum()):
        warnings.append("Часть seed не имеет ребер в наблюдаемой выборке")
    return Dataset(
        nodes=nodes.astype({"gid": "int64", "depth": "int64"}),
        edges=edges.astype({"src": "int64", "dst": "int64", "n_tx": "int64", "depth": "int64"}),
        transactions=transactions,
        warnings=warnings,
    )


def build_graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(int(gid) for gid in nodes.gid)
    for row in edges.sort_values(["src", "dst"]).itertuples(index=False):
        graph.add_edge(int(row.src), int(row.dst), sum_kzt=float(row.sum_kzt), n_tx=int(row.n_tx), depth=int(row.depth))
    return graph


def undirected_projection(graph: nx.DiGraph) -> nx.Graph:
    projection = nx.Graph()
    projection.add_nodes_from(sorted(graph.nodes))
    for src, dst, data in graph.edges(data=True):
        projection.add_edge(src, dst, weight=projection.get_edge_data(src, dst, {}).get("weight", 0.0) + float(data["sum_kzt"]))
    return projection


def _components(graph: nx.DiGraph) -> dict[int, int]:
    groups = sorted((sorted(component) for component in nx.weakly_connected_components(graph)), key=lambda values: values[0])
    return {gid: component_id for component_id, values in enumerate(groups) for gid in values}


def _seed_reach(graph: nx.DiGraph, seeds: Iterable[int]) -> dict[int, set[int]]:
    reached: dict[int, set[int]] = {}
    for seed in sorted(seeds):
        for node, distance in nx.single_source_shortest_path_length(graph, seed, cutoff=4).items():
            if 1 <= distance <= 4:
                reached.setdefault(node, set()).add(seed)
    return reached


def compute_metrics(graph: nx.DiGraph, nodes: pd.DataFrame) -> pd.DataFrame:
    in_deg = dict(graph.in_degree())
    out_deg = dict(graph.out_degree())
    in_kzt = dict(graph.in_degree(weight="sum_kzt"))
    out_kzt = dict(graph.out_degree(weight="sum_kzt"))
    in_tx = dict(graph.in_degree(weight="n_tx"))
    out_tx = dict(graph.out_degree(weight="n_tx"))
    pagerank = nx.pagerank(graph, weight="sum_kzt") if graph.number_of_nodes() else {}
    betweenness = nx.betweenness_centrality(graph, weight=None, normalized=True) if graph.number_of_edges() else {node: 0.0 for node in graph}
    component_id = _components(graph)
    seeds = set(nodes.loc[nodes.is_seed, "gid"].astype("int64"))
    reach = _seed_reach(graph, seeds)
    rows = []
    for row in nodes.sort_values("gid").itertuples(index=False):
        gid = int(row.gid)
        neighbors = set(graph.predecessors(gid)) | set(graph.successors(gid))
        incoming = float(in_kzt.get(gid, 0.0))
        outgoing = float(out_kzt.get(gid, 0.0))
        rows.append({
            "gid": gid, "depth": int(row.depth), "is_seed": bool(row.is_seed),
            "in_deg": int(in_deg.get(gid, 0)), "out_deg": int(out_deg.get(gid, 0)),
            "in_kzt": incoming, "out_kzt": outgoing, "in_tx": int(in_tx.get(gid, 0)), "out_tx": int(out_tx.get(gid, 0)),
            "pagerank": float(pagerank.get(gid, 0.0)), "betweenness": float(betweenness.get(gid, 0.0)),
            "pass_through": outgoing / incoming if incoming > 0 else np.nan,
            "is_frontier_cutoff": bool(int(row.depth) == 4 and out_deg.get(gid, 0) == 0),
            "n_seed_neighbors": len(neighbors & seeds), "component_id": int(component_id[gid]),
            "seed_reach_count": len(reach.get(gid, set())),
        })
    return pd.DataFrame(rows)


def cluster_membership(graph: nx.DiGraph, features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    projection = undirected_projection(graph)
    if projection.number_of_edges():
        groups = nx.community.louvain_communities(projection, weight="weight", seed=42)
    else:
        groups = [{node} for node in sorted(projection.nodes)]
    ordered = sorted((sorted(group) for group in groups), key=lambda values: values[0])
    mapping = {gid: cluster_id for cluster_id, group in enumerate(ordered) for gid in group}
    result = features.copy()
    result["cluster_id"] = result.gid.map(mapping).astype("int64")
    rows = []
    for cluster_id, group in enumerate(ordered):
        members = set(group)
        internal = sum(float(data["sum_kzt"]) for src, dst, data in graph.edges(data=True) if src in members and dst in members)
        subset = result[result.cluster_id == cluster_id]
        rows.append({"cluster_id": cluster_id, "n_nodes": len(group), "n_seed": int(subset.is_seed.sum()), "sum_kzt_internal": round(internal, 2)})
    return result, pd.DataFrame(rows)


def _positive_percentile(series: pd.Series) -> pd.Series:
    output = pd.Series(0.0, index=series.index)
    positive = series > 0
    if positive.any():
        output.loc[positive] = series.loc[positive].rank(method="average", pct=True)
    return output


def thresholds(features: pd.DataFrame) -> dict:
    in_positive = features.loc[features.in_deg > 0, "in_deg"]
    out_positive = features.loc[features.out_deg > 0, "out_deg"]
    bet_positive = features.loc[features.betweenness > 0, "betweenness"]
    return {
        "consolidator_in_deg": max(5, int(np.quantile(in_positive, 0.90))) if len(in_positive) else 5,
        "distributor_out_deg": max(15, int(np.quantile(out_positive, 0.90))) if len(out_positive) else 15,
        "coordinator_betweenness_p95": float(np.quantile(bet_positive, 0.95)) if len(bet_positive) else None,
        "coordinator_seed_neighbors": 2,
        "transit_low": 0.8,
        "transit_high": 1.2,
        "money_tolerance_atol": 0.01,
        "money_tolerance_rtol": 1e-12,
    }


def assign_roles(features: pd.DataFrame, th: dict) -> pd.DataFrame:
    result = features.copy()
    cutoff = th["coordinator_betweenness_p95"]
    roles: list[str] = []
    scores: list[float] = []
    evidences: list[str] = []
    explanations: list[str] = []
    for row in result.itertuples(index=False):
        isolated = row.in_deg == 0 and row.out_deg == 0
        alternatives: list[str] = []
        if row.in_deg >= 3:
            alternatives.append("consolidator")
        if row.out_deg >= 10:
            alternatives.append("distributor")
        if row.in_kzt > 0 and row.out_kzt > 0 and pd.notna(row.pass_through) and th["transit_low"] <= row.pass_through <= th["transit_high"]:
            alternatives.append("transit")
        if isolated:
            role, score, evidence = "peripheral", 0.20, "Наблюдаемых переводов нет; данных для роли недостаточно"
        elif cutoff is not None and row.n_seed_neighbors >= th["coordinator_seed_neighbors"] and row.betweenness >= cutoff:
            role = "coordinator"
            score = min(1.0, 0.5 * min(row.n_seed_neighbors / 4, 1) + 0.5 * row.betweenness / cutoff)
            evidence = f"{row.n_seed_neighbors} seed-соседа; betweenness={row.betweenness:.4f} не ниже p95={cutoff:.4f}; гипотеза связи структур"
        elif row.in_deg >= th["consolidator_in_deg"] and row.in_kzt > 0:
            role = "consolidator"
            score = min(1.0, 0.55 * min(row.in_deg / max(th["consolidator_in_deg"] * 2, 1), 1) + 0.45 * min(row.seed_reach_count / 4, 1))
            evidence = f"получает от {row.in_deg} плательщиков, вход {row.in_kzt:,.0f} KZT"
            if row.is_frontier_cutoff:
                score = min(score, 0.65)
                evidence += "; depth=4, исходящие не наблюдаются"
            if row.is_seed:
                evidence += "; входящие seed неполны"
        elif row.out_deg >= th["distributor_out_deg"]:
            role = "distributor"
            score = min(1.0, 0.55 * min(row.out_deg / max(th["distributor_out_deg"] * 2, 1), 1) + 0.45 * min(row.out_tx / 100, 1))
            evidence = f"исходящий веер на {row.out_deg} получателей, выход {row.out_kzt:,.0f} KZT"
        elif (not row.is_seed and not row.is_frontier_cutoff and row.in_kzt > 0 and row.out_kzt > 0 and pd.notna(row.pass_through) and th["transit_low"] <= row.pass_through <= th["transit_high"]):
            role = "transit"
            score = min(1.0, 1.0 - abs(row.pass_through - 1.0) / 0.4)
            evidence = f"положительные вход/выход; pass-through={row.pass_through:.2f}, это месячное соответствие потоков"
        elif not row.is_seed and row.depth < 4 and row.in_kzt > 0 and row.out_deg == 0:
            role, score = "terminal", min(1.0, 0.55 + 0.45 * min(row.in_kzt / max(features.in_kzt.max(), 1), 1)),
            evidence = f"положительный вход {row.in_kzt:,.0f} KZT, исходящих нет; возможный конечный получатель в выборке"
        else:
            role, score = "peripheral", 0.15
            evidence = f"{row.in_deg} входящих и {row.out_deg} исходящих контрагентов; недостаточно выраженных признаков"
        caveat = "; исходящие за 4-м коленом не наблюдаются" if row.is_frontier_cutoff else ("; входящие seed могут быть неполными" if row.is_seed else "")
        if role == "peripheral" and isolated:
            caveat = ""
        full = f"{role}: {evidence}{caveat}." + (f" Альтернативные сигналы: {', '.join(alternatives)}." if alternatives else "")
        roles.append(role); scores.append(round(float(max(0.0, min(1.0, score))), 6)); evidences.append(full[:200]); explanations.append(full)
    result["role"] = roles; result["role_score"] = scores; result["evidence"] = evidences; result["explanation"] = explanations
    return result


def _minmax(series: pd.Series) -> pd.Series:
    low, high = float(series.min()), float(series.max())
    if not math.isfinite(low) or not math.isfinite(high) or high - low <= 1e-12:
        return pd.Series(0.0, index=series.index)
    return (series - low) / (high - low)


def prioritize(features: pd.DataFrame) -> pd.DataFrame:
    result = features.copy()
    role_support = result.role.map(ROLE_WEIGHTS) * result.role_score
    result["priority_role"] = 0.40 * role_support
    result["priority_volume"] = 0.25 * _minmax(np.log1p(result.in_kzt))
    result["priority_bridge"] = 0.20 * _minmax(result.betweenness)
    result["priority_seed"] = 0.15 * _minmax(result.n_seed_neighbors.clip(upper=5))
    result["priority_score"] = (result.priority_role + result.priority_volume + result.priority_bridge + result.priority_seed).round(6)
    result["why"] = result.apply(lambda row: (f"{row.role}: role={row.priority_role:.3f}, volume={row.priority_volume:.3f}, bridge={row.priority_bridge:.3f}, seed={row.priority_seed:.3f}; {row.evidence}")[:400], axis=1)
    return result


def _cluster_output(features: pd.DataFrame, clusters: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in clusters.itertuples(index=False):
        subset = features[features.cluster_id == row.cluster_id].sort_values(["priority_score", "gid"], ascending=[False, True])
        internal = float(row.sum_kzt_internal)
        rows.append({"cluster_id": int(row.cluster_id), "n_nodes": int(row.n_nodes), "n_seed": int(row.n_seed), "sum_kzt_internal": internal, "top_gids": ";".join(str(int(gid)) for gid in subset.gid.head(5)), "hypothesis": f"Наблюдаемое сообщество из {row.n_nodes} узлов, {row.n_seed} seed, внутренний оборот {internal:,.0f} KZT; структурная гипотеза требует проверки."})
    return pd.DataFrame(rows)


def _validate_outputs(features: pd.DataFrame, clusters: pd.DataFrame, top: pd.DataFrame, nodes: pd.DataFrame) -> None:
    if len(features) != len(nodes) or features.gid.nunique() != len(nodes) or set(features.gid) != set(nodes.gid):
        raise ValidationError("node_metrics_full не покрывает nodes ровно один раз")
    required = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
    if features[required].isna().any().any() or not features.role.isin(ROLES).all():
        raise ValidationError("nodes_roles содержит пропуски или неизвестные роли")
    if not features.role_score.between(0, 1).all() or not features.priority_score.between(0, 1).all() or not features.evidence.str.len().between(1, 200).all():
        raise ValidationError("scores/evidence не проходят диапазоны")
    if int(clusters.n_nodes.sum()) != len(nodes) or features.cluster_id.isna().any():
        raise ValidationError("кластерное покрытие некорректно")
    if len(top) < min(20, len(nodes)) or not top.priority_score.is_monotonic_decreasing:
        raise ValidationError("top_nodes должен содержать минимум 20 узлов и быть отсортирован")


def publish(features: pd.DataFrame, clusters: pd.DataFrame, dataset: Dataset, out_dir: Path, edges_export: Path, metadata: dict) -> None:
    temp = Path(tempfile.mkdtemp(prefix="money-graph-", dir=str(out_dir.parent)))
    try:
        temp_out = temp / "out"
        temp_out.mkdir()
        nodes_roles = features[["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]]
        nodes_roles.to_csv(temp_out / "nodes_roles.csv", index=False, encoding="utf-8")
        cluster_output = _cluster_output(features, clusters, dataset.edges)
        cluster_output.to_csv(temp_out / "clusters.csv", index=False, encoding="utf-8")
        top = features.sort_values(["priority_score", "gid"], ascending=[False, True]).head(min(40, len(features))).copy()
        top.insert(0, "rank", range(1, len(top) + 1))
        top[["rank", "gid", "role", "priority_score", "why"]].to_csv(temp_out / "top_nodes.csv", index=False, encoding="utf-8")
        full_columns = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence", "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx", "pagerank", "betweenness", "pass_through", "is_frontier_cutoff", "n_seed_neighbors", "component_id", "why", "explanation", "priority_role", "priority_volume", "priority_bridge", "priority_seed"]
        features[full_columns].to_csv(temp_out / "node_metrics_full.csv", index=False, encoding="utf-8")
        edges_export_temp = temp / "edges.csv"
        dataset.edges[["src", "dst", "sum_kzt", "n_tx", "depth"]].to_csv(edges_export_temp, index=False, encoding="utf-8")
        metadata["status"] = "success"
        (temp_out / "run_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        _validate_outputs(features, cluster_output, top, dataset.nodes)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        temp_out.rename(out_dir)
        edges_export.parent.mkdir(parents=True, exist_ok=True)
        os.replace(edges_export_temp, edges_export)
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)


def run(data_dir: Path, out_dir: Path, edges_export: Path) -> dict:
    started = time.perf_counter()
    dataset = load(data_dir)
    graph = build_graph(dataset.nodes, dataset.edges)
    features = compute_metrics(graph, dataset.nodes)
    features, clusters = cluster_membership(graph, features)
    th = thresholds(features)
    features = assign_roles(features, th)
    features = prioritize(features)
    elapsed = time.perf_counter() - started
    role_counts = {role: int((features.role == role).sum()) for role in ROLES}
    metadata = {
        "status": "pending", "input_rows": {"nodes": len(dataset.nodes), "edges": len(dataset.edges), "transactions": len(dataset.transactions)},
        "seed_count": int(dataset.nodes.is_seed.sum()), "period_from": dataset.transactions.date.min().strftime("%Y-%m-%d"), "period_to": dataset.transactions.date.max().strftime("%Y-%m-%d"),
        "pipeline_seconds": round(elapsed, 3), "thresholds": th, "method": {"betweenness": "exact directed unweighted Brandes", "communities": "Louvain on undirected projection with reverse weights summed", "priority": "0.40 role + 0.25 log incoming volume + 0.20 bridge + 0.15 seed neighbors", "float_tolerance": "atol=0.01 KZT, rtol=1e-12"}, "warnings": dataset.warnings, "role_counts": role_counts,
    }
    publish(features, clusters, dataset, out_dir, edges_export, metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Граф денег: parquet/CSV -> аналитические выгрузки")
    parser.add_argument("--data", default=None, help="папка data_parquet или data; default: data_parquet")
    parser.add_argument("--out", default=None, help="папка результатов; default: out")
    parser.add_argument("--edges-export", default=None, help="совместимый CSV edges; default: data/edges.csv")
    args = parser.parse_args()
    root = _root()
    default_data = root / "data_parquet"
    if not default_data.exists():
        default_data = root / "data"
    data_dir = _resolve_cli_path(args.data, default_data)
    out_dir = _resolve_cli_path(args.out, root / "out")
    edges_export = _resolve_cli_path(args.edges_export, root / "data" / "edges.csv")
    run(data_dir, out_dir, edges_export)


if __name__ == "__main__":
    main()
