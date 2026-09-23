#!/usr/bin/env python3
"""Streamlit UI для анализа графа денежных переводов."""

import json
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from pyvis.network import Network
import streamlit.components.v1 as components

ROLE_COLORS = {
    "consolidator": "#e0554f",
    "distributor": "#3f8efc",
    "coordinator": "#f2b134",
    "transit": "#7fd8be",
    "terminal": "#9a8cff",
    "peripheral": "#5b6472",
}

ROLE_LABELS = {
    "consolidator": "Консолидация",
    "transit": "Транзит",
    "distributor": "Распределение",
    "terminal": "Возможный конечный получатель",
    "coordinator": "Координация — гипотеза",
    "peripheral": "Недостаточно выраженных признаков",
}

st.set_page_config(page_title="Граф денег", layout="wide")


def detect_project_root() -> Path:
    candidates = [Path.cwd(), Path(__file__).resolve().parent]
    for candidate in candidates:
        if (candidate / "out").exists() and (candidate / "data").exists():
            return candidate
    return Path(__file__).resolve().parent


def resolve_cli_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path)


def parse_cli_args() -> tuple[Path, Path, Path]:
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]

    root = detect_project_root()
    out_dir = root / "out"
    edges_path = root / "data" / "edges.csv"

    for i in range(len(argv) - 1):
        if argv[i] == "--data":
            out_dir = resolve_cli_path(root, argv[i + 1])
        elif argv[i] == "--edges":
            edges_path = resolve_cli_path(root, argv[i + 1])
    return root, out_dir, edges_path


def file_signature(paths: list[Path]) -> str:
    import hashlib

    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path).encode("utf-8"))
        if path.exists():
            stat = path.stat()
            digest.update(str(stat.st_mtime_ns).encode("utf-8"))
            digest.update(str(stat.st_size).encode("utf-8"))
        else:
            digest.update(b"missing")
    return digest.hexdigest()


@st.cache_data(show_spinner=False)
def load_results(data_dir: str, edges_path: str, signature: str):
    out_dir = Path(data_dir)
    edges_file = Path(edges_path)

    required_files = [
        out_dir / "nodes_roles.csv",
        out_dir / "clusters.csv",
        out_dir / "top_nodes.csv",
        out_dir / "node_metrics_full.csv",
        edges_file,
    ]
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise FileNotFoundError("; ".join(missing))

    def read_csv(path: Path, kind: str = "generic"):
        dtype = None
        if kind == "nodes":
            dtype = {"gid": "string"}
        elif kind == "edges":
            dtype = {"src": "string", "dst": "string"}
        return pd.read_csv(path, dtype=dtype, low_memory=False)

    nodes = read_csv(out_dir / "node_metrics_full.csv", kind="nodes")
    roles = read_csv(out_dir / "nodes_roles.csv", kind="nodes")
    clusters = read_csv(out_dir / "clusters.csv", low_memory=False)
    top = read_csv(out_dir / "top_nodes.csv", kind="nodes")
    edges = read_csv(edges_file, kind="edges")

    for frame in (nodes, roles, clusters, top, edges):
        if isinstance(frame, pd.DataFrame):
            frame.columns = [str(c).strip() for c in frame.columns]

    if "gid" in nodes.columns:
        nodes["gid"] = nodes["gid"].astype("string").str.strip()
    if "gid" in roles.columns:
        roles["gid"] = roles["gid"].astype("string").str.strip()
    if "gid" in top.columns:
        top["gid"] = top["gid"].astype("string").str.strip()
    if "src" in edges.columns:
        edges["src"] = edges["src"].astype("string").str.strip()
    if "dst" in edges.columns:
        edges["dst"] = edges["dst"].astype("string").str.strip()

    if "gid" in roles.columns and "gid" in nodes.columns:
        roles_by_gid = roles.set_index("gid")
        for column in roles.columns:
            if column == "gid":
                continue
            if column not in nodes.columns:
                nodes[column] = nodes["gid"].map(roles_by_gid[column])

    top = top.copy()
    if "priority_score" in top.columns:
        top["priority_score"] = pd.to_numeric(top["priority_score"], errors="coerce")
    if "rank" in top.columns:
        top["rank"] = pd.to_numeric(top["rank"], errors="coerce")

    clusters = clusters.copy()
    if "cluster_id" in clusters.columns:
        clusters["cluster_id"] = pd.to_numeric(clusters["cluster_id"], errors="coerce")

    return nodes, clusters, top, edges


def role_label(name: str) -> str:
    return ROLE_LABELS.get(str(name).strip(), str(name).strip() or "н/д")


def render_graph_html(nodes: pd.DataFrame, edges: pd.DataFrame, selected_gid: str | None, graph_mode: str, top_nodes: pd.DataFrame, role_filter: list[str], cluster_filter: list[str], depth_filter: list[str], min_edge_sum: float, seed_only: bool):
    if not role_filter:
        return "<div style='padding:16px;color:#d1d5db;'>Пустой набор ролей: показывается пустой граф.</div>"

    visible_nodes = nodes.copy()
    if role_filter:
        visible_nodes = visible_nodes[visible_nodes["role"].astype(str).isin(role_filter)]
    if cluster_filter:
        visible_nodes = visible_nodes[visible_nodes["cluster_id"].astype(str).isin(cluster_filter)]
    if depth_filter:
        visible_nodes = visible_nodes[visible_nodes["depth"].astype(str).isin(depth_filter)]
    if seed_only and "is_seed" in visible_nodes.columns:
        visible_nodes = visible_nodes[visible_nodes["is_seed"].fillna(False).astype(bool)]

    if visible_nodes.empty:
        return "<div style='padding:16px;color:#d1d5db;'>Нет узлов после фильтров. Сбросьте фильтры или выберите другую роль.</div>"

    visible_ids = set(visible_nodes["gid"].astype(str))

    if graph_mode == "top":
        top_ids = set(top_nodes["gid"].astype(str).head(20).tolist()) & visible_ids
        if not top_ids:
            top_ids = set(visible_ids)
        neighbor_ids = set(edges.loc[(edges["src"].isin(top_ids)) | (edges["dst"].isin(top_ids)), "src"].astype(str))
        neighbor_ids |= set(edges.loc[(edges["src"].isin(top_ids)) | (edges["dst"].isin(top_ids)), "dst"].astype(str))
        selected_ids = top_ids | (neighbor_ids & visible_ids)
    elif graph_mode == "selected":
        if selected_gid and selected_gid in visible_ids:
            selected_ids = {selected_gid}
            neighbor_ids = set(edges.loc[(edges["src"] == selected_gid) | (edges["dst"] == selected_gid), "src"].astype(str))
            neighbor_ids |= set(edges.loc[(edges["src"] == selected_gid) | (edges["dst"] == selected_gid), "dst"].astype(str))
            selected_ids |= neighbor_ids & visible_ids
        else:
            selected_ids = set(visible_ids)
    else:
        selected_ids = set(visible_ids)

    selected_ids = {gid for gid in selected_ids if gid in visible_ids}
    if not selected_ids:
        return "<div style='padding:16px;color:#d1d5db;'>Пустое состояние после применения фильтров.</div>"

    edge_df = edges.copy()
    edge_df["src"] = edge_df["src"].astype(str)
    edge_df["dst"] = edge_df["dst"].astype(str)
    if "sum_kzt" in edge_df.columns:
        edge_df["sum_kzt"] = pd.to_numeric(edge_df["sum_kzt"], errors="coerce").fillna(0.0)
        edge_df = edge_df[(edge_df["src"].isin(selected_ids)) & (edge_df["dst"].isin(selected_ids)) & (edge_df["sum_kzt"] >= min_edge_sum)]
    else:
        edge_df = edge_df[(edge_df["src"].isin(selected_ids)) & (edge_df["dst"].isin(selected_ids))]

    net = Network(height="720px", width="100%", directed=True, bgcolor="#111827", font_color="#f3f4f6", notebook=False, cdn_resources="in_line")
    net.set_options(json.dumps({
        "interaction": {"hover": True, "multiselect": False},
        "physics": {
            "enabled": True,
            "barnesHut": {"gravitationalConstant": -20000, "centralGravity": 0.2, "springLength": 110, "springConstant": 0.08, "damping": 0.09},
            "maxVelocity": 35,
        },
        "layout": {"improvedLayout": True},
        "edges": {"smooth": {"enabled": True, "type": "dynamic", "forceDirection": "none"}, "arrowStrikethrough": False, "color": {"color": "#9ca3af", "highlight": "#7dd3fc"}},
        "nodes": {"borderWidth": 1, "borderWidthSelected": 3, "font": {"size": 12, "color": "#f3f4f6"}, "shadow": True},
    }))

    nodes_to_draw = visible_nodes[visible_nodes["gid"].astype(str).isin(selected_ids)].copy()
    for row in nodes_to_draw.itertuples(index=False):
        gid = str(row.gid)
        role = str(getattr(row, "role", "peripheral"))
        role_color = ROLE_COLORS.get(role, "#5b6472")
        base_size = 12.0
        priority = float(getattr(row, "priority_score", 0.0) or 0.0)
        size = base_size + priority * 20.0 + (float(getattr(row, "in_deg", 0) or 0) / 8.0)
        size = min(size, 45.0)

        node_title = (
            f"gid: {gid}<br/>"
            f"роль: {role_label(role)}<br/>"
            f"priority_score: {priority:.4f}<br/>"
            f"cluster_id: {getattr(row, 'cluster_id', 'н/д')}<br/>"
            f"evidence: {getattr(row, 'evidence', 'н/д')}"
        )

        node_style = {"color": role_color, "size": size, "title": node_title, "label": gid[-8:]}
        if getattr(row, "is_seed", False):
            node_style["shape"] = "diamond"
            node_style["borderWidth"] = 3
        if getattr(row, "is_frontier_cutoff", False):
            node_style["shape"] = "dot"
            node_style["borderWidth"] = 2
        if selected_gid and gid == selected_gid:
            node_style["borderWidth"] = 4
            node_style["color"] = "#ffffff"
            node_style["font"] = {"color": "#fef3c7", "face": "sans-serif"}

        net.add_node(gid, **node_style)

    for row in edge_df.itertuples(index=False):
        src = str(row.src)
        dst = str(row.dst)
        if src not in selected_ids or dst not in selected_ids:
            continue
        sum_kzt = float(getattr(row, "sum_kzt", 0.0) or 0.0)
        tx_count = int(getattr(row, "n_tx", 0) or 0)
        net.add_edge(src, dst, value=max(1.0, min(sum_kzt / 200000.0, 8.0)), title=f"{sum_kzt:,.0f} KZT / {tx_count} тр.", arrows="to")

    html = net.generate_html(notebook=False, cdn_resources="in_line")
    html = re.sub(r"<script[^>]*src=[^>]+></script>", "", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<link[^>]*href=[^>]+>", "", html, flags=re.IGNORECASE | re.DOTALL)
    return html


root, out_dir, edges_path = parse_cli_args()
required_files = [out_dir / "nodes_roles.csv", out_dir / "clusters.csv", out_dir / "top_nodes.csv", out_dir / "node_metrics_full.csv", edges_path]
if not all(path.exists() for path in required_files):
    st.set_page_config(layout="wide")
    st.title("Граф денег")
    st.error("Отсутствуют обязательные CSV-выгрузки. Сначала выполните пересчёт данных.")
    st.code("python pipeline.py --data data_parquet --out out")
    st.stop()

cache_key = file_signature(required_files)
nodes, clusters, top_nodes, edges = load_results(str(out_dir), str(edges_path), cache_key)

nodes = nodes.copy()
if "gid" in nodes.columns:
    nodes["gid"] = nodes["gid"].astype("string")
if "role" in nodes.columns:
    nodes["role"] = nodes["role"].astype("string")
if "cluster_id" in nodes.columns:
    nodes["cluster_id"] = pd.to_numeric(nodes["cluster_id"], errors="coerce")
if "depth" in nodes.columns:
    nodes["depth"] = pd.to_numeric(nodes["depth"], errors="coerce")
if "is_seed" in nodes.columns:
    nodes["is_seed"] = nodes["is_seed"].fillna(False).astype(str).str.lower().isin(["true", "1", "yes", "y"])

if "gid" in nodes.columns and "gid" in top_nodes.columns:
    top_nodes = top_nodes.merge(nodes[["gid", "role"]].drop_duplicates(), on="gid", how="left")

nodes_by_gid = nodes.set_index("gid", drop=False)
role_values = sorted(nodes["role"].dropna().astype(str).unique().tolist())
cluster_values = sorted(nodes["cluster_id"].dropna().astype(str).unique().tolist())
depth_values = sorted(nodes["depth"].dropna().astype(int).astype(str).unique().tolist())

if "stated" not in st.session_state:
    st.session_state.stated = {}

if "selected_gid" not in st.session_state:
    st.session_state.selected_gid = None
if "graph_mode" not in st.session_state:
    st.session_state.graph_mode = "top"
if "role_filter" not in st.session_state:
    st.session_state.role_filter = role_values[:]
if "cluster_filter" not in st.session_state:
    st.session_state.cluster_filter = []
if "depth_filter" not in st.session_state:
    st.session_state.depth_filter = []
if "seed_only" not in st.session_state:
    st.session_state.seed_only = False
if "min_edge_sum" not in st.session_state:
    st.session_state.min_edge_sum = 0.0
if "search_gid" not in st.session_state:
    st.session_state.search_gid = ""

st.title("Граф денег")
meta = {
    "nodes": int(len(nodes)),
    "edges": int(len(edges)),
    "transactions": int(edges["n_tx"].sum()) if "n_tx" in edges.columns else 0,
    "clusters": int(nodes["cluster_id"].nunique()) if "cluster_id" in nodes.columns else 0,
    "sum_kzt": float(edges["sum_kzt"].sum()) if "sum_kzt" in edges.columns else 0.0,
}

c1, c2, c3, c4 = st.columns(4)
c1.metric("Узлов", meta["nodes"])
c2.metric("Рёбер", meta["edges"])
c3.metric("Кластеры", meta["clusters"])
c4.metric("Оборот по рёбрам, KZT", f"{meta['sum_kzt']:,.0f}".replace(",", " "))

st.sidebar.header("Поиск и фильтры")
search_value = st.sidebar.text_input("Точный gid", key="search_gid")
if st.sidebar.button("Найти по gid"):
    cleaned = str(search_value or "").strip()
    if not cleaned:
        st.sidebar.warning("Введите gid для поиска.")
    elif cleaned not in set(nodes["gid"].astype(str)):
        st.sidebar.warning("Неизвестный gid: узел не найден в текущем наборе данных.")
    else:
        st.session_state.selected_gid = cleaned
        st.session_state.graph_mode = "selected"
        st.session_state.role_filter = []
        st.session_state.cluster_filter = []
        st.session_state.depth_filter = []
        st.session_state.seed_only = False
        st.toast("Сброшены конфликтующие фильтры для выбранного gid.")

st.sidebar.radio("Режим графа", ["top", "selected", "all"], index=0, key="graph_mode", format_func=lambda x: {"top": "Топ + окружение", "selected": "Выбранный узел", "all": "Вся сеть"}[x])

st.sidebar.multiselect("Роли", options=role_values, default=st.session_state.role_filter, key="role_filter")
st.sidebar.multiselect("Кластеры", options=cluster_values, default=st.session_state.cluster_filter, key="cluster_filter")
st.sidebar.multiselect("Depth", options=depth_values, default=st.session_state.depth_filter, key="depth_filter")
st.sidebar.checkbox("Только seed", key="seed_only")
st.sidebar.slider("Минимальная сумма ребра, KZT", min_value=0.0, max_value=500000.0, step=500.0, key="min_edge_sum")

if st.sidebar.button("Сбросить фильтры"):
    st.session_state.role_filter = role_values[:]
    st.session_state.cluster_filter = []
    st.session_state.depth_filter = []
    st.session_state.seed_only = False
    st.session_state.min_edge_sum = 0.0
    st.session_state.selected_gid = None
    st.session_state.graph_mode = "top"
    st.rerun()

if st.sidebar.button("Обновить данные"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("### Легенда")
for role, color in ROLE_COLORS.items():
    st.sidebar.markdown(f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};margin-right:8px;'></span>{role_label(role)}", unsafe_allow_html=True)

with st.expander("Дополнительно: состояние и CSV", expanded=False):
    st.write("Выбранный gid:", st.session_state.selected_gid or "не выбран")
    st.write("Режим:", st.session_state.graph_mode)
    st.write("Фильтры ролей:", st.session_state.role_filter)
    st.download_button("Скачать nodes_roles.csv", data=(out_dir / "nodes_roles.csv").read_bytes(), file_name="nodes_roles.csv", mime="text/csv")
    st.download_button("Скачать clusters.csv", data=(out_dir / "clusters.csv").read_bytes(), file_name="clusters.csv", mime="text/csv")
    st.download_button("Скачать top_nodes.csv", data=(out_dir / "top_nodes.csv").read_bytes(), file_name="top_nodes.csv", mime="text/csv")

if not role_values:
    st.warning("Нет доступных ролей в данных; требуется пересчёт.")
    st.stop()

filtered_nodes = nodes.copy()
if st.session_state.role_filter:
    filtered_nodes = filtered_nodes[filtered_nodes["role"].astype(str).isin(st.session_state.role_filter)]
else:
    filtered_nodes = filtered_nodes.iloc[0:0]
if st.session_state.cluster_filter:
    filtered_nodes = filtered_nodes[filtered_nodes["cluster_id"].astype(str).isin(st.session_state.cluster_filter)]
if st.session_state.depth_filter:
    filtered_nodes = filtered_nodes[filtered_nodes["depth"].astype(str).isin(st.session_state.depth_filter)]
if st.session_state.seed_only and "is_seed" in filtered_nodes.columns:
    filtered_nodes = filtered_nodes[filtered_nodes["is_seed"].fillna(False).astype(bool)]

left, right = st.columns([3, 1])
with left:
    st.caption(f"Показаны {len(filtered_nodes)} узлов после фильтрации; видимые рёбра ограничены по sum_kzt >= {st.session_state.min_edge_sum:,.0f} KZT")
    graph_html = render_graph_html(filtered_nodes, edges, st.session_state.selected_gid, st.session_state.graph_mode, top_nodes, st.session_state.role_filter, st.session_state.cluster_filter, st.session_state.depth_filter, st.session_state.min_edge_sum, st.session_state.seed_only)
    components.html(graph_html, height=760, scrolling=False)

with right:
    st.subheader("Топ-20")
    top_table = top_nodes.head(20).copy()
    top_table["role"] = top_table.get("role", pd.Series(["н/д"] * len(top_table))).astype(str)
    for row in top_table.itertuples(index=False):
        gid = str(row.gid)
        with st.container(border=True):
            st.markdown(f"#{row.rank} · {gid}")
            st.caption(f"{role_label(row.role)} · priority {float(row.priority_score or 0):.4f}")
            st.write(str(getattr(row, "why", ""))[:180])
            if st.button("Показать", key=f"top_{gid}"):
                st.session_state.selected_gid = gid
                st.session_state.graph_mode = "selected"
                st.rerun()

    if st.session_state.selected_gid:
        selected_gid = str(st.session_state.selected_gid)
        node = nodes_by_gid.get(selected_gid)
        if node is None:
            st.warning("Выбранный gid отсутствует в наборе. Проверьте фильтры или поиск.")
        else:
            node = node.to_dict()
            st.subheader(f"Карточка gid {selected_gid}")
            st.markdown(f"**Роль:** {role_label(node.get('role', 'peripheral'))}")
            st.markdown(f"**role_score:** {float(node.get('role_score', 0.0) or 0) :.4f} · поддержку гипотезы")
            st.markdown(f"**priority_score:** {float(node.get('priority_score', 0.0) or 0):.4f}")
            st.markdown(f"**cluster_id:** {node.get('cluster_id', 'н/д')}")
            st.markdown(f"**depth:** {node.get('depth', 'н/д')}")
            st.markdown(f"**seed:** {node.get('is_seed', False)}")
            if node.get('is_seed'):
                st.warning("Seed-узел: ограниченный входящий поток может быть неполным.")
            if node.get('is_frontier_cutoff'):
                st.warning("Boundary: достигнут предел глубины; это не доказательство удержания средств.")

            if "in_deg" in node or "out_deg" in node or "in_tx" in node or "out_tx" in node:
                in_deg = node.get('in_deg', 'н/д')
                out_deg = node.get('out_deg', 'н/д')
                in_kzt = node.get('in_kzt', 'н/д')
                out_kzt = node.get('out_kzt', 'н/д')
                in_tx = node.get('in_tx', 'н/д')
                out_tx = node.get('out_tx', 'н/д')
                st.write(f"Вход: {in_deg} контрагентов, {in_kzt} KZT, {in_tx} транзакций")
                st.write(f"Выход: {out_deg} контрагентов, {out_kzt} KZT, {out_tx} транзакций")

            evidence = node.get('evidence', 'н/д')
            explanation = node.get('why', node.get('explanation', 'н/д'))
            st.write("**evidence:**", evidence if str(evidence).strip() else "н/д")
            st.write("**explanation:**", explanation if str(explanation).strip() else "н/д")
            if 'breakdown' in node and node['breakdown'] not in (None, ''):
                st.write("**breakdown:**", node['breakdown'])

st.markdown("---")
cluster_tab, limitations_tab = st.tabs(["Кластеры", "Ограничения"])
with cluster_tab:
    st.dataframe(clusters[[c for c in clusters.columns if c not in ["top_gids"]]].copy(), use_container_width=True, hide_index=True)
    for row in clusters.head(8).itertuples(index=False):
        cluster_id = getattr(row, "cluster_id")
        with st.expander(f"Кластер {cluster_id}"):
            st.write(f"Размер: {getattr(row, 'n_nodes', 'н/д')}")
            st.write(f"Seed: {getattr(row, 'n_seed', 'н/д')}")
            st.write(f"Внутренний оборот: {float(getattr(row, 'sum_kzt_internal', 0.0) or 0):,.0f} KZT")
            st.write(f"Гипотеза: {getattr(row, 'hypothesis', 'н/д')}")
            if st.button("Показать кластер на графе", key=f"cluster_{cluster_id}"):
                st.session_state.graph_mode = "all"
                st.session_state.cluster_filter = [str(cluster_id)]
                st.session_state.role_filter = role_values[:]
                st.rerun()

with limitations_tab:
    st.info("Depth=4; неполный вход; порог 5000 KZT; внутрибанковские переводы; нет ground truth. Все предупреждения привязаны к данным текущего расчёта.")
    st.markdown("- Depth=4 — граница наблюдения, а не доказательство конца потока.")
    st.markdown("- Неполный вход: в выборке видны только исходящие переводы от seed.")
    st.markdown("- Порог 5000 KZT: крупные и средние переводы могут быть скрыты фрагментацией.")
    st.markdown("- Нет ground truth: роль — гипотеза на основе наблюдаемой сети, а не факт юридической принадлежности.")
