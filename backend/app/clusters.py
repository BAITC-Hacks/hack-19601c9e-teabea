import json

import networkx as nx
import pandas as pd


def compute_clusters(graph: nx.DiGraph, features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    projection = nx.Graph()
    projection.add_nodes_from(graph.nodes)
    for src, dst, data in graph.edges(data=True):
        projection.add_edge(src, dst, weight=projection.get_edge_data(src, dst, {}).get("weight", 0.0) + float(data["sum_kzt"]))
    if projection.number_of_edges():
        groups = nx.community.louvain_communities(projection, weight="weight", seed=42)
    else:
        groups = [{node} for node in projection]
    ordered = sorted((sorted(group) for group in groups), key=lambda group: (group[0], len(group)))
    mapping = {node: cluster_id for cluster_id, group in enumerate(ordered) for node in group}
    features["cluster_id"] = features.gid.map(mapping).astype(int)
    seed_by_node = features.set_index("gid").is_seed.to_dict()
    priority_by_node = features.set_index("gid").priority_score.to_dict()
    records = []
    for cluster_id, group in enumerate(ordered):
        members = set(group)
        internal = sum(float(data["sum_kzt"]) for src, dst, data in graph.edges(data=True) if src in members and dst in members)
        top_gids = [str(int(gid)) for gid in sorted(group, key=lambda node: (-priority_by_node.get(node, 0.0), node))[:5]]
        n_seed = sum(bool(seed_by_node.get(node, False)) for node in group)
        records.append({"cluster_id": cluster_id, "n_nodes": len(group), "n_seed": n_seed,
                        "sum_kzt_internal": internal, "top_gids": json.dumps(top_gids, ensure_ascii=False),
                "hypothesis": f"Наблюдаемое сообщество из {len(group)} узлов; {n_seed} seed, внутренний оборот {internal:,.0f} KZT; требует проверки."})
    return features, pd.DataFrame(records)