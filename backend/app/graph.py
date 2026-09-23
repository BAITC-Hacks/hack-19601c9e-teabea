import networkx as nx
import pandas as pd


def build_graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(int(gid) for gid in nodes.gid)
    for row in edges.itertuples(index=False):
        graph.add_edge(int(row.src), int(row.dst), sum_kzt=float(row.sum_kzt), n_tx=int(row.n_tx), depth=int(row.depth))
    return graph


def graph_summary(graph: nx.DiGraph) -> dict:
    return {
        "weak_components_with_isolates": nx.number_weakly_connected_components(graph),
        "isolates": sum(1 for node in graph if graph.degree(node) == 0),
        "weak_components_without_isolates": sum(1 for component in nx.weakly_connected_components(graph) if len(component) > 1),
    }