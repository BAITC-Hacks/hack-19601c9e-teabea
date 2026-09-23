"""PyVis graph with only bundled, inline resources."""
import html
import json
from pathlib import Path

from pyvis.network import Network
from jinja2 import ChoiceLoader, PackageLoader
from ui.data import ROLE_COLORS, ROLE_LABELS


def render_graph_html(nodes, edges, selected=None):
    net = Network(height="460px", width="100%", directed=True, cdn_resources="in_line")
    net.set_template_dir(str(Path(__file__).parent), "graph.html")
    net.templateEnv.loader = ChoiceLoader([net.templateEnv.loader, PackageLoader("pyvis", "templates")])
    net.set_options(json.dumps({
        "layout": {"randomSeed": 42, "improvedLayout": False},
        "interaction": {"hover": True},
        "physics": {"solver": "barnesHut", "stabilization": {"enabled": True, "iterations": 120}, "maxVelocity": 25},
        "nodes": {"font": {"color": "#e9eef3"}},
        "edges": {"smooth": False, "color": {"color": "#526578", "highlight": "#48d5bd"}, "arrows": "to"},
    }))
    for r in nodes.itertuples(index=False):
        detail = f"gid: {r.gid}\n{ROLE_LABELS[r.role]}\nПоддержка гипотезы: {r.role_score:.4f}; приоритет: {r.priority_score:.4f}\nКластер: {r.cluster_id}; depth: {r.depth}; seed: {r.is_seed}\nВход: {r.in_deg} контрагентов / {r.in_kzt:,.0f} KZT / {r.in_tx} переводов\nВыход: {r.out_deg} контрагентов / {r.out_kzt:,.0f} KZT / {r.out_tx} переводов\n{r.explanation}\n{r.why}"
        if r.is_frontier_cutoff:
            detail += "\nBoundary: исходящие за границей наблюдения неизвестны."
        if r.is_seed:
            detail += "\nSeed: входящие неполны."
        net.add_node(str(r.gid), label=str(r.gid) if r.gid == selected else "", title=html.escape(detail), detail=detail,
                     size=10 + 24 * r.priority_score, shape="triangle" if r.is_frontier_cutoff else "dot",
                     borderWidth=4 if r.is_seed or r.gid == selected else 1,
                     color={"background": ROLE_COLORS[r.role], "border": "#ffffff" if r.gid == selected else ("#efbf58" if r.is_seed else ROLE_COLORS[r.role])})
    for r in edges.itertuples(index=False):
        net.add_edge(str(r.src), str(r.dst), title=f"{r.sum_kzt:,.0f} KZT / {r.n_tx} переводов", width=1.2)
    return net.generate_html()
