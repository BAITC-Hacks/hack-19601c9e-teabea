import pandas as pd
import pytest

from pipeline import ValidationError, assign_roles, build_graph, cluster_membership, compute_metrics, load, prioritize, thresholds


def row(gid, *, depth=1, seed=False, in_deg=0, out_deg=0, in_kzt=0.0, out_kzt=0.0, betweenness=0.0, seed_neighbors=0):
    return {"gid": gid, "depth": depth, "is_seed": seed, "in_deg": in_deg, "out_deg": out_deg, "in_kzt": in_kzt, "out_kzt": out_kzt, "in_tx": in_deg, "out_tx": out_deg, "pagerank": 0.0, "betweenness": betweenness, "pass_through": out_kzt / in_kzt if in_kzt else float("nan"), "is_frontier_cutoff": depth == 4 and out_deg == 0, "n_seed_neighbors": seed_neighbors, "component_id": 0, "seed_reach_count": 0}


def classify(frame, **overrides):
    values = frame.copy()
    for index, changes in overrides.items():
        values.loc[index, list(changes)] = list(changes.values())
    result = assign_roles(values, {"consolidator_in_deg": 5, "distributor_out_deg": 15, "coordinator_betweenness_p95": 0.005, "coordinator_seed_neighbors": 2, "transit_low": 0.8, "transit_high": 1.2})
    return result


def test_isolate_is_peripheral_with_explicit_evidence():
    result = classify(pd.DataFrame([row(10)]))
    assert result.iloc[0].role == "peripheral"
    assert "Наблюдаемых переводов нет" in result.iloc[0].evidence


def test_terminal_requires_positive_incoming_and_not_seed_or_frontier():
    result = classify(pd.DataFrame([row(10, depth=2, in_deg=1, in_kzt=1000)]))
    assert result.iloc[0].role == "terminal"
    assert classify(pd.DataFrame([row(10, depth=2, seed=True, in_deg=1, in_kzt=1000)])).iloc[0].role == "peripheral"
    assert classify(pd.DataFrame([row(10, depth=4, in_deg=1, in_kzt=1000)])).iloc[0].role != "terminal"


def test_transit_consolidator_distributor_and_coordinator_rules():
    frame = pd.DataFrame([
        row(1, in_deg=2, out_deg=1, in_kzt=1000, out_kzt=1000),
        row(2, in_deg=5, in_kzt=1000),
        row(3, out_deg=15, out_kzt=1000),
        row(4, in_deg=2, out_deg=1, in_kzt=1000, out_kzt=1000, betweenness=0.01, seed_neighbors=2),
        row(5, in_deg=2, out_deg=1, in_kzt=1000, out_kzt=1000, betweenness=0.001, seed_neighbors=2),
    ])
    result = classify(frame)
    assert result.set_index("gid").loc[1, "role"] == "transit"
    assert result.set_index("gid").loc[2, "role"] == "consolidator"
    assert result.set_index("gid").loc[3, "role"] == "distributor"
    assert result.set_index("gid").loc[4, "role"] == "coordinator"
    assert result.set_index("gid").loc[5, "role"] != "coordinator"


def test_empty_graph_and_reverse_weights_are_stable():
    nodes = pd.DataFrame({"gid": pd.Series([10**18, 10**18 + 1], dtype="int64"), "depth": [0, 1], "is_seed": [True, False]})
    edges = pd.DataFrame({"src": pd.Series([], dtype="int64"), "dst": pd.Series([], dtype="int64"), "sum_kzt": [], "n_tx": pd.Series([], dtype="int64"), "depth": pd.Series([], dtype="int64")})
    graph = build_graph(nodes, edges)
    features = compute_metrics(graph, nodes)
    clustered, clusters = cluster_membership(graph, features)
    assert set(clustered.gid) == {10**18, 10**18 + 1}
    assert clusters.n_nodes.sum() == 2
    assert len(clusters) == 2


def test_invalid_transaction_count_is_rejected(tmp_path):
    nodes = pd.DataFrame({"gid": pd.Series([1, 2], dtype="int64"), "depth": pd.Series([0, 1], dtype="int64"), "is_seed": [True, False]})
    edges = pd.DataFrame({"src": pd.Series([1], dtype="int64"), "dst": pd.Series([2], dtype="int64"), "sum_kzt": [10.0], "n_tx": pd.Series([2], dtype="int64"), "depth": pd.Series([1], dtype="int64")})
    transactions = pd.DataFrame({"src": pd.Series([1], dtype="int64"), "dst": pd.Series([2], dtype="int64"), "date": ["2026-07-01"], "sum_kzt": [10.0]})
    nodes.to_parquet(tmp_path / "nodes.parquet"); edges.to_parquet(tmp_path / "edges.parquet"); transactions.to_parquet(tmp_path / "transactions.parquet")
    with pytest.raises(ValidationError, match="n_tx"):
        load(tmp_path)


def test_priority_breakdown_sums_to_score():
    features = assign_roles(pd.DataFrame([row(1, in_deg=5, in_kzt=1000)]), {"consolidator_in_deg": 5, "distributor_out_deg": 15, "coordinator_betweenness_p95": None, "coordinator_seed_neighbors": 2, "transit_low": 0.8, "transit_high": 1.2})
    result = prioritize(features)
    assert abs(result.iloc[0].priority_score - sum(result.iloc[0][column] for column in ["priority_role", "priority_volume", "priority_bridge", "priority_seed"])) < 1e-6
