"""Streamlit interface, adapted from the supplied final-kit app.py."""
import argparse
import importlib
import inspect
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ui.data import EXPORTS, ROLE_COLORS, ROLE_LABELS, load_results, select_graph, signature
from ui import graph as graph_ui
from ui.source import source_panel

ROOT = Path(__file__).resolve().parent

# A running Streamlit process can rerun app.py while retaining an older imported
# graph module. Reload that module only when its public API is incompatible.
if not {'full_network', 'observation'} <= set(inspect.signature(graph_ui.render_graph_html).parameters):
    importlib.invalidate_caches()
    importlib.reload(graph_ui)


@st.cache_data(show_spinner=False)
def cached_results(out, edges, fingerprint):
    return load_results(out, edges)


def main():
    st.set_page_config(page_title="Граф денег", layout="wide")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(ROOT / "out"))
    parser.add_argument("--edges", default=str(ROOT / "data/edges.csv"))
    args, _ = parser.parse_known_args()
    out, edges_path = ROOT / args.data, ROOT / args.edges
    st.markdown('<style>' + (ROOT / 'ui/style.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)
    st.title("Граф денег")
    st.caption('Наблюдаемые переводы · объяснимые роли · приоритет проверки')
    source = source_panel(out, edges_path)
    if source is None:
        st.stop()
    out, edges_path = source
    try:
        nodes, clusters, top, edges, meta = cached_results(str(out), str(edges_path), signature(out, edges_path))
    except (OSError, ValueError, AssertionError, KeyError) as exc:
        st.error(f"Требуется пересчёт: {exc}")
        st.code(f'python "{ROOT / "pipeline.py"}" --data "{ROOT / "data_parquet"}" --out "{out}" --edges-export "{edges_path}"')
        st.stop()
    roles = list(ROLE_LABELS)
    defaults = dict(selected_gid=None, graph_mode="top", role_filter=roles, cluster_filter=[], depth_filter=[], seed_only=False, min_edge_sum=0.0, hops=1)
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    state = st.session_state
    observation = meta.get('observation', dict(source='hackathon', max_depth=4, seed_incomplete=True, minimum_amount=5000, bank_scope='Только внутрибанковские', notes='Нет ground truth'))

    def reset():
        for key in ("role_filter", "cluster_filter", "depth_filter", "seed_only", "min_edge_sum"):
            state[key] = defaults[key]

    def focus(gid):
        if gid not in set(nodes.gid):
            state.notice = "Узел не найден: " + gid
            return
        reset()
        state.selected_gid, state.graph_mode = gid, "selected"
        state.notice = "Узел выбран. Фильтры сброшены для показа его окружения."

    def open_cluster():
        reset()
        state.cluster_filter = [state.cluster_choice]
        state.graph_mode = "all"
        state.selected_gid = None

    def all_graph():
        reset()
        state.graph_mode = 'all'
        state.selected_gid = None

    st.caption(f"Период: {meta['period_from']} — {meta['period_to']} · расчёт: {meta['pipeline_seconds']:.3f} с")
    st.button('Показать весь граф', on_click=all_graph)
    columns = st.columns(5)
    for col, label, value in zip(columns, ["Узлы", "Рёбра", "Транзакции", "Кластеры", "Сумма переводов, KZT"], [len(nodes), len(edges), int(edges.n_tx.sum()), len(clusters), f"{edges.sum_kzt.sum():,.0f}"]):
        col.metric(label, value)
    st.caption("Сумма переводов по рёбрам: одни и те же деньги могут учитываться на нескольких шагах.")
    with st.sidebar:
        st.header("Поиск и фильтры")
        st.text_input("Точный gid", key="search_gid")
        st.button("Найти по gid", on_click=lambda: focus(state.search_gid.strip()))
        st.radio("Режим графа", ["top", "selected", "all"], key="graph_mode", format_func=lambda v: dict(top="Топ + окружение", selected="Выбранный узел", all="Вся сеть")[v])
        st.select_slider("Шагов окружения", [1, 2], key="hops")
        st.multiselect("Роли", roles, key="role_filter", format_func=ROLE_LABELS.get)
        st.multiselect("Кластеры", sorted(clusters.cluster_id.tolist()), key="cluster_filter")
        st.multiselect("Глубина", sorted(nodes.depth.unique().tolist()), key="depth_filter")
        st.checkbox("Только seed", key="seed_only")
        st.number_input("Минимальная сумма ребра, KZT", min_value=0.0, step=5000.0, key="min_edge_sum")
        st.button("Сбросить фильтры", on_click=reset)
        st.button("Обновить данные", on_click=cached_results.clear)
        st.caption("Цвет — роль · размер — priority_score (10–34 px). Золотая обводка — seed, пунктирная обводка — boundary. Все узлы круглые.")
        for role, color in ROLE_COLORS.items():
            st.markdown(f'<span style="color:{color}">●</span> {ROLE_LABELS[role]}', unsafe_allow_html=True)
    if "notice" in state:
        st.info(state.pop("notice"))
    graph_tab, top_tab, cluster_tab, export_tab, limits_tab = st.tabs(["Граф и карточка", "Глобальный топ-20", "Кластеры", "Скачать CSV", "Ограничения"])
    with graph_tab:
        visible, links = select_graph(nodes, edges, top, mode=state.graph_mode, selected=state.selected_gid, roles=state.role_filter, clusters=state.cluster_filter, depths=state.depth_filter, seed_only=state.seed_only, minimum=state.min_edge_sum, hops=state.hops)
        st.caption(f"Видимые узлы: {len(visible)} · видимые рёбра: {len(links)}. Стрелки: плательщик → получатель.")
        left, right = st.columns([3, 2])
        with left:
            if visible.empty:
                st.info("Нет узлов для выбранного режима и фильтров. Выберите gid или сбросьте фильтры.")
            else:
                components.html(graph_ui.render_graph_html(visible, links, state.selected_gid, full_network=state.graph_mode == 'all', observation=observation), height=680, scrolling=False)
        with right:
            selected = nodes[nodes.gid == state.selected_gid]
            if selected.empty:
                st.info("Выберите узел поиском или кнопкой глобального топа. Клик по графу открывает подробности внутри графа.")
            else:
                r = selected.iloc[0]
                st.subheader("Карточка узла")
                st.code(r.gid, language=None)
                st.write(f"**{ROLE_LABELS[r.role]}**")
                st.write(f"Поддержка гипотезы: **{r.role_score:.4f}** · приоритет: **{r.priority_score:.4f}**")
                st.caption(f"Кластер {r.cluster_id} · depth {r.depth} · seed {'да' if r.is_seed else 'нет'}")
                if r.is_seed:
                    completeness = observation.get('seed_incomplete')
                    st.warning('Seed: ' + ('наблюдаемый вход неполон.' if completeness is True else ('полнота входящих неизвестна.' if completeness is None else 'входящие заявлены полными в рамках набора.')))
                if r.is_frontier_cutoff:
                    st.warning(f"Boundary: depth={observation.get('max_depth')}. Отсутствие исходящих не доказывает удержание денег.")
                st.dataframe(pd.DataFrame({"Поток": ["Вход", "Выход"], "Контрагенты": [r.in_deg, r.out_deg], "KZT": [r.in_kzt, r.out_kzt], "Переводы": [r.in_tx, r.out_tx]}), hide_index=True)
                st.write("Pass-through: " + ("н/д" if pd.isna(r.pass_through) else f"{r.pass_through:.4f}"))
                st.write(r.evidence)
                with st.expander("Полное объяснение и вклад в приоритет", expanded=True):
                    st.write(r.explanation)
                    st.write(r.why)
                    st.json({label: float(r[key]) for label, key in zip(["Роль", "Входящий объём", "Посредничество", "Соседи seed"], ["priority_role", "priority_volume", "priority_bridge", "priority_seed"])})
    with top_tab:
        st.caption("Глобальный рейтинг из CSV; фильтры графа его не меняют.")
        for r in top.head(20).itertuples(index=False):
            with st.container(border=True):
                st.write(f"**#{r.rank} · {r.gid}** · {ROLE_LABELS[r.role]} · {r.priority_score:.4f}")
                st.write(r.why)
                st.button("Показать на графе", key=f"top_{r.gid}", on_click=focus, args=(str(r.gid),))
        st.caption("После выбора откройте вкладку «Граф и карточка».")
    with cluster_tab:
        st.dataframe(clusters, hide_index=True)
        st.selectbox("Кластер для просмотра", sorted(clusters.cluster_id.tolist()), key="cluster_choice")
        st.button("Показать кластер на графе", on_click=open_cluster)
        st.caption("После выбора откройте вкладку «Граф и карточка».")
    with export_tab:
        st.write("Полные исходные выгрузки текущего расчёта. Фильтры не изменяют CSV.")
        for name in EXPORTS:
            st.download_button(f"Скачать {name}", (out / name).read_bytes(), file_name=name, mime="text/csv")
    with limits_tab:
        st.write(f"В текущем расчёте: {int(nodes.is_seed.sum())} seed, {int(nodes.is_frontier_cutoff.sum())} boundary, {int(((nodes.in_deg == 0) & (nodes.out_deg == 0)).sum())} изолятов.")
        st.write('Предельная глубина обхода: ', observation.get('max_depth') if observation.get('max_depth') is not None else 'неизвестна; terminal не назначается для собственного набора')
        st.write('Порог выгрузки, KZT: ', observation.get('minimum_amount') if observation.get('minimum_amount') is not None else 'неизвестен')
        st.write('Охват: ', observation.get('bank_scope', 'Неизвестно'))
        st.write('Дополнительные ограничения: ', observation.get('notes') or 'не указаны')
        st.info("Наблюдаемые суммы не являются полным балансом. Роли — эвристические гипотезы, role_score не вероятность виновности. Максимальная глубина в файле сама по себе не подтверждает границу наблюдения.")
        for warning in meta["warnings"]:
            st.warning(warning)


if __name__ == "__main__":
    main()
