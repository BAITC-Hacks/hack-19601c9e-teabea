"""Validated CSV snapshot and a fully inline PyVis graph."""
import json
import re
from html import escape
from pathlib import Path

import pandas as pd
from pyvis.network import Network

LABELS = dict(consolidator='Консолидация', transit='Транзит', distributor='Распределение',
              terminal='Возможный конечный получатель', coordinator='Координация — гипотеза',
              peripheral='Недостаточно выраженных признаков')
COLORS = dict(zip(LABELS, ['#ef7770', '#59d5bd', '#659fff', '#af9aff', '#f2ba55', '#8290a6']))
FILES = ['nodes_roles.csv', 'clusters.csv', 'top_nodes.csv', 'node_metrics_full.csv', 'run_metadata.json']
FIELDS = set('gid role role_score cluster_id priority_score evidence depth is_seed in_deg out_deg in_kzt out_kzt in_tx out_tx pagerank betweenness pass_through is_frontier_cutoff n_seed_neighbors component_id why explanation priority_role priority_volume priority_bridge priority_seed'.split())


def load_snapshot(out, edges_path):
    out = Path(out)
    frames = [pd.read_csv(out / name, dtype={'gid': 'string', 'top_gids': 'string'}) for name in FILES[:4]]
    roles, clusters, top, nodes = frames
    edges = pd.read_csv(edges_path, dtype={'src': 'string', 'dst': 'string'})
    metadata = json.loads((out / FILES[4]).read_text(encoding='utf-8'))
    for frame, required in [(nodes, FIELDS), (roles, set('gid role role_score cluster_id priority_score evidence'.split())),
                            (top, set('rank gid role priority_score why'.split())),
                            (clusters, set('cluster_id n_nodes n_seed sum_kzt_internal top_gids hypothesis'.split())),
                            (edges, set('src dst sum_kzt n_tx'.split()))]:
        if required - set(frame):
            raise ValueError(f'Отсутствуют поля: {sorted(required - set(frame))}')
    ids = set(nodes.gid)
    if nodes.gid.duplicated().any() or roles.gid.duplicated().any() or ids != set(roles.gid):
        raise ValueError('Несогласованный набор gid')
    if not set(top.gid) <= ids or not (set(edges.src) | set(edges.dst)) <= ids:
        raise ValueError('Ссылки на неизвестный gid')
    if not nodes.role.isin(LABELS).all() or metadata['status'] != 'success':
        raise ValueError('Требуется успешный пересчёт')
    if int(clusters.n_nodes.sum()) != len(nodes):
        raise ValueError('Несогласованное покрытие кластеров')
    for col in ['is_seed', 'is_frontier_cutoff']:
        nodes[col] = nodes[col].astype(str).str.lower().isin(['true', '1'])
    return nodes, clusters, top, edges, metadata


def subgraph(nodes, edges, top, *, mode, selected, roles, clusters, depths, seed_only, minimum, hops):
    visible = nodes[nodes.role.isin(roles) & nodes.depth.isin(depths)]
    if clusters:
        visible = visible[visible.cluster_id.isin(clusters)]
    if seed_only:
        visible = visible[visible.is_seed]
    links = edges[edges.sum_kzt >= minimum]
    ids = set(visible.gid)
    if mode != 'all':
        focus = {selected} if mode == 'selected' and selected else set(top.gid.head(20)) if mode == 'top' else set()
        for _ in range(hops if mode == 'selected' else 1):
            neighbors = links[links.src.isin(focus) | links.dst.isin(focus)]
            focus |= set(neighbors.src) | set(neighbors.dst)
        ids &= focus
    return visible[visible.gid.isin(ids)], links[links.src.isin(ids) & links.dst.isin(ids)]


def graph_html(nodes, edges, selected=None):
    net = Network(height='550px', width='100%', directed=True, bgcolor='#111827', font_color='#ffffff', cdn_resources='in_line')
    net.set_options(json.dumps({'layout': {'randomSeed': 42, 'improvedLayout': False},
        'physics': {'stabilization': {'iterations': 100}, 'solver': 'barnesHut'},
        'interaction': {'hover': True}, 'edges': {'smooth': False},
        'nodes': {'font': {'size': 13}}}))
    for row in nodes.itertuples(index=False):
        title = escape(f'{row.gid}\n{LABELS[row.role]}\nКластер {row.cluster_id}; приоритет {row.priority_score:.4f}\n{row.explanation}')
        net.add_node(str(row.gid), label=str(row.gid) if row.gid == selected else '', title=title,
                     color={'background': COLORS[row.role], 'border': '#ffffff' if row.is_seed else COLORS[row.role]},
                     borderWidth=4 if row.is_seed else 1, shape='triangle' if row.is_frontier_cutoff else 'dot',
                     size=10 + 24 * row.priority_score)
    for row in edges.itertuples(index=False):
        net.add_edge(str(row.src), str(row.dst), arrows='to', title=f'{row.sum_kzt:,.2f} KZT; {row.n_tx} переводов')
    html = net.generate_html()
    # PyVis bundles vis inline, but its default template also includes unused Bootstrap CDN tags.
    html = re.sub(r'<script[^>]+src=[^>]*>\s*</script>', '', html, flags=re.I)
    html = re.sub(r'<link[^>]+href=[^>]*>', '', html, flags=re.I)
    return html.replace('</body>', '<script>network.once("stabilized",()=>network.setOptions({physics:false}));setTimeout(()=>network.setOptions({physics:false}),4000);</script></body>')
