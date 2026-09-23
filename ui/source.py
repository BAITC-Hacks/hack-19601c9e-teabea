from pathlib import Path

import streamlit as st
from ui.uploads import EXECUTOR, calculate, fingerprint, preview, read_upload, validate_frames

RESET_KEYS = ('selected_gid', 'graph_mode', 'role_filter', 'cluster_filter', 'depth_filter', 'seed_only', 'min_edge_sum', 'cluster_choice', 'search_gid')


def reset_selection():
    for key in RESET_KEYS:
        st.session_state.pop(key, None)


@st.cache_data(show_spinner=False)
def checked_uploads(files, observation):
    frames = {name: read_upload(name, filename, content) for name, filename, content in files}
    validate_frames(frames, observation)
    return frames


@st.fragment(run_every=1)
def progress():
    future = st.session_state.upload_job
    if future.done():
        try:
            st.session_state.upload_result = future.result()
            st.session_state.result_fingerprint = st.session_state.job_fingerprint
            st.session_state.upload_error = None
            reset_selection()
        except Exception as exc:
            st.session_state.upload_error = f'Расчёт не завершён: {exc}'
            st.session_state.upload_result = None
        del st.session_state.upload_job
        st.rerun()
    st.info('Идёт расчёт нового графа… Повторный запуск заблокирован. Результат появится после завершения.')


def source_panel(default_out, default_edges):
    state = st.session_state
    busy = 'upload_job' in state
    def example():
        state.source_mode = 'Пример хакатона'
        reset_selection()
    with st.container(border=True):
        st.radio('Источник данных', ['Пример хакатона', 'Свои данные'], key='source_mode', horizontal=True, disabled=busy, on_change=reset_selection)
        st.button('Открыть пример хакатона', on_click=example, disabled=busy)
        if state.source_mode == 'Пример хакатона':
            return default_out, default_edges
        st.caption('Три файла одного набора. Можно сочетать CSV и Parquet. Данные организаторов не изменяются. Предпросмотр: первые 20 строк.')
        files = []
        for name in ('nodes', 'edges', 'transactions'):
            file = st.file_uploader(name, type=['csv', 'parquet'], key=f'upload_{name}', disabled=busy)
            if file is not None:
                files.append((name, file.name, file.getvalue()))
        with st.expander('Границы наблюдения собственного набора', expanded=True):
            known = st.checkbox('Известна предельная глубина обхода', key='depth_known', disabled=busy)
            depth = st.number_input('Предельная глубина', min_value=1, value=4, step=1, disabled=busy or not known)
            seed = st.selectbox('Входящие seed', ['Неизвестно', 'Неполные', 'Полные в рамках набора'], disabled=busy)
            threshold_known = st.checkbox('Известен порог суммы выгрузки', disabled=busy)
            minimum = st.number_input('Порог выгрузки, KZT', min_value=0.0, step=100.0, disabled=busy or not threshold_known)
            scope = st.selectbox('Охват переводов', ['Неизвестно', 'Только внутрибанковские', 'Включает межбанковские'], disabled=busy)
            notes = st.text_input('Дополнительные ограничения набора', disabled=busy)
        observation = dict(source='custom', max_depth=int(depth) if known else None, seed_incomplete={'Неизвестно': None, 'Неполные': True, 'Полные в рамках набора': False}[seed], minimum_amount=minimum if threshold_known else None, bank_scope=scope, notes=notes)
        if busy:
            st.button('Рассчитать новый граф', disabled=True)
            progress()
            return None
        if len(files) != 3:
            st.info('Файлы не загружены: выберите nodes, edges и transactions.')
            st.button('Рассчитать новый граф', disabled=True)
            return None
        token = fingerprint(files, observation)
        if token != state.get('draft_fingerprint'):
            state.draft_fingerprint = token
            state.upload_error = None
        try:
            with st.spinner('Проверка столбцов, типов, gid и соответствия транзакций связям…'):
                frames = checked_uploads(tuple(files), observation)
            for name, frame in frames.items():
                with st.expander(f'{name} · {len(frame):,} строк'):
                    st.dataframe(preview(frame), hide_index=True, width='stretch')
        except Exception as exc:
            st.error(f'Ошибка проверки: {exc}')
            st.button('Рассчитать новый граф', disabled=True)
            return None
        st.success('Проверка пройдена: схема, ссылки, суммы и число транзакций согласованы.')
        if observation['max_depth'] is None:
            st.caption('Граница неизвестна: максимальный depth в файле не считается границей. Гипотеза terminal консервативно отключена.')
        if st.button('Рассчитать новый граф', type='primary'):
            state.upload_result = None
            state.upload_error = None
            state.job_fingerprint = token
            state.upload_job = EXECUTOR.submit(calculate, frames, observation)
            reset_selection()
            st.rerun()
        if state.get('upload_error'):
            st.error(state.upload_error)
        if state.get('upload_result') and state.get('result_fingerprint') == token:
            st.success('Расчёт завершён. Ниже показан загруженный набор.')
            return tuple(Path(p) for p in state.upload_result)
        st.info('Новый набор ещё не рассчитан. Предыдущие результаты скрыты.')
        return None
