"""Local analytical UI; all roles and explanations come from the pipeline."""
import argparse
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from ui.model import LABELS, COLORS, FILES, load_snapshot, subgraph, graph_html

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--data', type=Path, default=ROOT / 'out')
parser.add_argument('--edges', type=Path, default=ROOT / 'data/edges.csv')
args, _ = parser.parse_known_args()
st.set_page_config(page_title='Граф денег', layout='wide')
st.title('Граф денег')

@st.cache_data
def cached_load(out, edges, signature):
    return load_snapshot(out, edges)

try:
    if (args.data.parent / ('.' + args.data.name + '.publishing')).exists():
        raise ValueError('Публикуются новые результаты; обновите страницу после завершения расчёта')
    paths = [args.data / name for name in FILES] + [args.edges]
    signature = tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    nodes, clusters, top, edges, meta = cached_load(str(args.data), str(args.edges), signature)
except (OSError, ValueError, KeyError) as error:
    st.error(f'Требуется пересчёт: {error}')
    st.code('python pipeline.py --data data_parquet --out out')
    st.stop()

def reset():
    for key, value in dict(roles=list(LABELS), clusters=[], depths=[0,1,2,3,4], seed_only=False, minimum=0.0).items():
        st.session_state[key] = value

def focus(gid):
    reset()
    st.session_state.selected = gid
    st.session_state.mode = 'selected'
    st.session_state.notice = 'Фильтры сброшены для выбранного узла.'

def search():
    gid = st.session_state.query.strip()
    if gid in set(nodes.gid):
        focus(gid)
    else:
        st.session_state.notice = 'Узел не найден: ' + gid

def show_cluster():
    reset()
    st.session_state.clusters = [st.session_state.cluster_choice]
    st.session_state.mode = 'all'

if 'roles' not in st.session_state:
    reset()
for key, default in dict(selected=None, mode='top', notice='').items():
    st.session_state.setdefault(key, default)
st.caption(f"{meta['period_from']} — {meta['period_to']} · Расчёт {meta['pipeline_seconds']:.3f} с · Роли — гипотезы для проверки")
for col, label, value in zip(st.columns(5), ['Узлы', 'Рёбра', 'Транзакции', 'Кластеры', 'Оборот переводов, KZT'],
                            [len(nodes), len(edges), meta['input_rows']['transactions'], len(clusters), f'{edges.sum_kzt.sum():,.2f}']):
    col.metric(label, value)
st.caption('Оборот — сумма наблюдаемых переводов; одни средства могут учитываться несколько раз.')
with st.sidebar:
    st.header('Поиск и фильтры')
    st.text_input('Точный gid', key='query', on_change=search)
    st.button('Найти', on_click=search)
    st.radio('Режим графа', ['top','selected','all'], key='mode', format_func=lambda x: {'top':'Топ + окружение','selected':'Выбранный узел','all':'Вся сеть'}[x])
    st.multiselect('Роли', list(LABELS), key='roles', format_func=LABELS.get)
    st.multiselect('Кластеры', sorted(clusters.cluster_id.tolist()), key='clusters')
    st.multiselect('Глубина', [0,1,2,3,4], key='depths')
    st.checkbox('Только seed', key='seed_only')
    st.number_input('Минимальная сумма ребра, KZT', min_value=0.0, key='minimum')
    hops = st.radio('Шаги от узла', [1,2], horizontal=True)
    st.button('Сбросить фильтры', on_click=reset)
    st.button('Обновить данные', on_click=st.cache_data.clear)
    st.caption('Белая обводка — seed; треугольник — boundary. Размер: 10 + 24 × приоритет.')
    for role in LABELS:
        st.markdown(f'<span style="color:{COLORS[role]}">●</span> {LABELS[role]}', unsafe_allow_html=True)
if st.session_state.notice:
    st.info(st.session_state.notice)
network_tab, top_tab, cluster_tab, export_tab, limits_tab = st.tabs(['Сеть и карточка', 'Глобальный топ-20', 'Кластеры', 'Скачать CSV', 'Ограничения'])
with network_tab:
    visible, links = subgraph(nodes, edges, top, mode=st.session_state.mode, selected=st.session_state.selected,
        roles=st.session_state.roles, clusters=st.session_state.clusters, depths=st.session_state.depths,
        seed_only=st.session_state.seed_only, minimum=st.session_state.minimum, hops=hops)
    st.caption(f'Видно узлов: {len(visible)} · рёбер: {len(links)}')
    graph_col, card = st.columns([2,1])
    with graph_col:
        if visible.empty:
            st.info('Нет узлов после фильтров. Выберите роли или сбросьте фильтры.')
        else:
            components.html(graph_html(visible, links, st.session_state.selected), height=570)
            st.caption('Наведение показывает детали. Для карточки используйте поиск или переход из топа.')
    with card:
        gid = st.session_state.selected
        if gid and gid in set(nodes.gid):
            row = nodes.set_index('gid').loc[gid]
            st.subheader('Карточка узла')
            st.code(gid)
            st.write(LABELS[row.role])
            st.write(f'Поддержка гипотезы: {row.role_score:.4f} · Приоритет: {row.priority_score:.4f}')
            st.write(f'Кластер: {row.cluster_id} · Глубина: {row.depth} · Seed: {row.is_seed}')
            if row.is_seed:
                st.warning('Входящие seed могут быть неполными.')
            if row.is_frontier_cutoff:
                st.warning('Boundary: depth=4; исходящие за границей не наблюдаются. Это не доказательство удержания средств.')
            for prefix, label in [('in','Наблюдаемый вход'), ('out','Наблюдаемый выход')]:
                st.write(f'{label}: {row[prefix+"_deg"]} контрагентов, {row[prefix+"_tx"]} переводов, {row[prefix+"_kzt"]:,.2f} KZT')
            st.write('Pass-through: ' + ('н/д' if pd.isna(row.pass_through) else f'{row.pass_through:.3f}'))
            st.write(row.evidence)
            st.write(row.explanation)
            st.write(row.why)
            st.dataframe(pd.DataFrame({'Вклад': ['Роль','Объём','Посредничество','Seed'], 'Значение': [row['priority_'+k] for k in ['role','volume','bridge','seed']]}), hide_index=True)
        else:
            st.info('Введите gid или выберите узел из глобального топа.')
with top_tab:
    st.caption('Глобальный рейтинг; фильтры графа не изменяют топ и выгрузки.')
    for row in top.head(20).itertuples(index=False):
        with st.container(border=True):
            st.write(f'#{row.rank} · {row.gid} · {LABELS[row.role]} · {row.priority_score:.4f}')
            st.write(row.why)
            st.button('Показать на графе', key='top_'+row.gid, on_click=focus, args=(row.gid,))
with cluster_tab:
    st.dataframe(clusters, hide_index=True)
    st.selectbox('Кластер для перехода', sorted(clusters.cluster_id.tolist()), key='cluster_choice')
    st.button('Показать кластер', on_click=show_cluster)
with export_tab:
    for name in FILES[:3]:
        st.download_button('Скачать '+name, (args.data/name).read_bytes(), file_name=name, mime='text/csv')
with limits_tab:
    st.write('Depth=4 — граница наблюдения. Входящие seed неполны. Переводы ниже 5000 KZT и вне банка отсутствуют. Нет ground truth и клиентских атрибутов. Роль и score — структурная гипотеза, не вероятность виновности. Совпадение входа и выхода за месяц не доказывает движение тех же денег.')
