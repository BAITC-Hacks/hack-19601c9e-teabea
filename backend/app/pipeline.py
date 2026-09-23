import argparse
import json
import time
from pathlib import Path

from .clusters import compute_clusters
from .exports import publish
from .features import compute_features
from .graph import build_graph, graph_summary
from .load_validate import load_validate
from .roles import assign_roles


def run(data_dir: Path, out_dir: Path) -> dict:
    started = time.perf_counter()
    dataset = load_validate(data_dir)
    graph = build_graph(dataset.nodes, dataset.edges)
    features = compute_features(graph, dataset.nodes, dataset.transactions)
    daily = features.attrs.pop("daily")
    features = assign_roles(features)
    features, clusters = compute_clusters(graph, features)
    # Communities are assigned before role scoring; recompute coordinator signal from adjacent cluster ids.
    cluster_by_node = features.set_index("gid").cluster_id.to_dict()
    for index, row in features.iterrows():
        neighbors = {cluster_by_node.get(int(neighbor)) for neighbor in graph.neighbors(int(row.gid))} | {cluster_by_node.get(int(neighbor)) for neighbor in graph.predecessors(int(row.gid))}
        features.at[index, "neighbor_communities"] = len(neighbors - {int(row.cluster_id)})
    features = assign_roles(features)
    summary = {"n_nodes": len(dataset.nodes), "n_edges": len(dataset.edges), "n_transactions": len(dataset.transactions), "n_seed": int(dataset.nodes.is_seed.sum()), "n_clusters": len(clusters), "n_truncated": int(features.truncated_by_depth.sum()), "total_edge_kzt": float(dataset.edges.sum_kzt.sum()), "date_from": dataset.transactions.date.min().strftime("%Y-%m-%d"), "date_to": dataset.transactions.date.max().strftime("%Y-%m-%d"), "pipeline_seconds": round(time.perf_counter() - started, 3), "warnings": dataset.warnings, **graph_summary(graph)}
    publish(features, clusters, dataset.edges, dataset.transactions, summary, daily, out_dir)
    (out_dir / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Готово за {summary['pipeline_seconds']:.3f} с: {out_dir.resolve()}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data")
    parser.add_argument("--out", default="out")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    run((root / args.data).resolve() if not Path(args.data).is_absolute() else Path(args.data), (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out))


if __name__ == "__main__":
    main()