import pandas as pd

from backend.app.clusters import compute_clusters
from backend.app.graph import build_graph, graph_summary


def test_graph_keeps_isolated_nodes_and_reports_components():
    nodes = pd.DataFrame({"gid": [1, 2, 3], "depth": [0, 1, 0], "is_seed": [True, False, True]})
    edges = pd.DataFrame({"src": [1], "dst": [2], "sum_kzt": [10.0], "n_tx": [1], "depth": [1]})
    graph = build_graph(nodes, edges)
    assert set(graph.nodes) == {1, 2, 3}
    assert graph_summary(graph)["isolates"] == 1


def test_louvain_projection_sums_reverse_edges():
    nodes = pd.DataFrame({"gid": [1, 2], "depth": [0, 1], "is_seed": [True, False]})
    edges = pd.DataFrame({"src": [1, 2], "dst": [2, 1], "sum_kzt": [10.0, 7.0], "n_tx": [1, 1], "depth": [1, 1]})
    graph = build_graph(nodes, edges)
    features = pd.DataFrame({"gid": [1, 2], "is_seed": [True, False], "priority_score": [0.2, 0.8]})
    _, clusters = compute_clusters(graph, features)
    assert len(clusters) == 1
    assert clusters.iloc[0].sum_kzt_internal == 17.0
    assert clusters.iloc[0].n_nodes == 2


def test_empty_edge_graph_gets_one_cluster_per_node():
    nodes = pd.DataFrame({"gid": [1, 2], "depth": [0, 0], "is_seed": [True, True]})
    graph = build_graph(nodes, pd.DataFrame(columns=["src", "dst", "sum_kzt", "n_tx", "depth"]))
    features = pd.DataFrame({"gid": [1, 2], "is_seed": [True, True], "priority_score": [0.0, 0.0]})
    _, clusters = compute_clusters(graph, features)
    assert len(clusters) == 2
    assert clusters.n_nodes.sum() == 2