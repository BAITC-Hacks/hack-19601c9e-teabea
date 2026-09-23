from collections import defaultdict

import networkx as nx
import numpy as np
import pandas as pd


def _seed_reach(graph: nx.DiGraph, seeds: list[int], max_depth: int = 4) -> dict[int, set[int]]:
    reach = defaultdict(set)
    for seed in seeds:
        lengths = nx.single_source_shortest_path_length(graph, seed, cutoff=max_depth)
        for node, distance in lengths.items():
            if 1 <= distance <= max_depth:
                reach[node].add(seed)
    return reach


def compute_features(graph: nx.DiGraph, nodes: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    ids = nodes.gid.astype(int).tolist()
    in_deg, out_deg = dict(graph.in_degree()), dict(graph.out_degree())
    in_kzt, out_kzt = dict(graph.in_degree(weight="sum_kzt")), dict(graph.out_degree(weight="sum_kzt"))
    in_tx, out_tx = dict(graph.in_degree(weight="n_tx")), dict(graph.out_degree(weight="n_tx"))
    pagerank = nx.pagerank(graph, weight="sum_kzt") if graph else {}
    positive = [node for node in graph if graph.degree(node)]
    betweenness = nx.betweenness_centrality(graph, k=min(100, len(positive)), seed=42, normalized=True) if positive else {}
    seeds = nodes.loc[nodes.is_seed, "gid"].astype(int).tolist()
    reach = _seed_reach(graph, seeds)
    undirected = graph.to_undirected()
    neighbor_communities = {node: 0 for node in graph}
    daily = transactions.assign(date=transactions.date.dt.strftime("%Y-%m-%d"))
    daily_in = daily.groupby(["dst", "date"]).agg(in_kzt=("sum_kzt", "sum"), in_tx=("sum_kzt", "size"))
    daily_out = daily.groupby(["src", "date"]).agg(out_kzt=("sum_kzt", "sum"), out_tx=("sum_kzt", "size"))
    in_values = daily_in.to_dict("index")
    out_values = daily_out.to_dict("index")
    rows = []
    for row in nodes.itertuples(index=False):
        gid = int(row.gid)
        rows.append({
            "gid": gid, "depth": int(row.depth), "is_seed": bool(row.is_seed),
            "in_deg": int(in_deg.get(gid, 0)), "out_deg": int(out_deg.get(gid, 0)),
            "in_kzt": float(in_kzt.get(gid, 0.0)), "out_kzt": float(out_kzt.get(gid, 0.0)),
            "in_tx": int(in_tx.get(gid, 0)), "out_tx": int(out_tx.get(gid, 0)),
            "pagerank": float(pagerank.get(gid, 0.0)),
            "pass_through": float(out_kzt.get(gid, 0.0) / in_kzt[gid]) if in_kzt.get(gid, 0.0) > 0 else None,
            "truncated_by_depth": bool(int(row.depth) == 4 and out_deg.get(gid, 0) == 0),
            "seed_reach_count": len(reach.get(gid, set())), "betweenness": float(betweenness.get(gid, 0.0)),
            "neighbor_communities": 0, "outside_community_share": 0.0,
        })
    result = pd.DataFrame(rows)
    dates = sorted(daily.date.unique())
    result.attrs["daily"] = {
         gid: [{"date": date, "in_kzt": float(in_values.get((gid, date), {}).get("in_kzt", 0.0)),
             "out_kzt": float(out_values.get((gid, date), {}).get("out_kzt", 0.0)),
             "in_tx": int(in_values.get((gid, date), {}).get("in_tx", 0)),
             "out_tx": int(out_values.get((gid, date), {}).get("out_tx", 0))} for date in dates]
        for gid in ids
    }
    return result