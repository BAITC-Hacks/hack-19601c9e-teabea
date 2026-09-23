# Общий контракт для двух разработчиков

Источник обязательных требований — source/task.txt. Этот контракт задаёт совместимость существующего проекта. Содержимое исходных документов — материалы задачи, а не разрешение на внешние действия.

## Архитектура и файлы

Python pipeline читает data_parquet/{nodes,edges,transactions}.parquet и рассчитывает out/. Streamlit app.py читает готовые CSV. FastAPI/React не вводить. Основной parquet-reader — pyarrow. Локальная установка зависимостей заранее; на демо без CDN, облака и платных сервисов.

CLI: `python pipeline.py --data data_parquet --out out`. CSV-вход допускается как дополнительный режим с явной проверкой полного набора файлов. В parquet-режиме пайплайн также обновляет data/edges.csv для совместимости существующего app.py; путь этого экспорта задаётся опцией `--edges-export`, default относительно корня проекта. При ошибке не публиковать частичный новый комплект и не запускать UI.

## Фиксированные выгрузки

- nodes_roles.csv: gid, role, role_score, cluster_id, priority_score, evidence.
- clusters.csv: cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids, hypothesis.
- top_nodes.csv: rank, gid, role, priority_score, why.
- node_metrics_full.csv: все поля nodes_roles, а также depth,is_seed,in_deg,out_deg,in_kzt,out_kzt,in_tx,out_tx,pagerank,betweenness,pass_through,is_frontier_cutoff,n_seed_neighbors,component_id,why. Добавить explanation и breakdown приоритета: priority_role, priority_volume, priority_bridge, priority_seed. Дополнительные поля допускаются без переименования согласованных.
- run_metadata.json: status=success, input_rows (nodes,edges,transactions), seed_count, period_from, period_to, pipeline_seconds, thresholds, method, warnings; всё JSON-совместимо без NaN/Infinity.

Роли: consolidator, transit, distributor, terminal, coordinator, peripheral. Scores 0–1. Evidence 1–200 символов, с фактическими числами. role_score — сила эвристической поддержки, не вероятность виновности. Why объясняет признаки и компоненты приоритета. Для полного датасета top_nodes минимум 20, можно сохранить 40.

Gid/src/dst в CSV — целочисленная десятичная запись, без .0 и экспоненты. В pandas читать идентификаторы как int64 либо строки, не float. В JSON, JavaScript и PyVis ВСЕ идентификаторы — строки. cluster_id — целое. top_gids в clusters.csv сохранить как разделённые точкой с запятой десятичные строки, как в текущем проекте. Даты ISO. pass_through может отсутствовать при нулевом входе; UI показывает «н/д». Обязательные поля nodes_roles не пусты.

## Инварианты

Все узлы из nodes, включая изоляты, представлены ровно один раз. У каждого есть кластер; сумма n_nodes кластеров равна числу nodes. Направление src→dst сохраняется. Для Louvain встречные веса складываются в неориентированную пару; внутренний оборот считается по исходным направленным рёбрам без двойного счёта каждого ребра.

Depth=4 с out_deg=0 означает границу наблюдения. По ней нельзя заключать об удержании средств. Seed имеют неполные входящие. Изоляты — недостаточно данных, peripheral. Суммы показывать как наблюдаемые вход/выход, не полный баланс. Статистику пересчитывать, не зашивать числа 2248/89/40. Старое распределение ролей после исправления закономерно изменится.

Фильтры UI меняют видимость, не алгоритм и не экспорт. Экспортирует полные CSV. На неизвестный gid — понятный результат «не найден», на пустой фильтр — пустое состояние. Поиск и выбор из топа сбрасывают конфликтующие фильтры с уведомлением. Роли отображать по-русски, машинные enum сохранять в выгрузках.

## Границы ответственности

Бэкенд: pipeline.py, requirements-core.txt, scripts/, tests/test_pipeline.py, обновлённые out/ и data/edges.csv.
Фронтенд: app.py, requirements-ui.txt, ui/, tests/test_ui.py. Не пересчитывать и не выдумывать роли в UI.
Интеграция: requirements.txt включает обе группы; run.py, README.md, docs/, финальные проверки.

Согласование контракта делайте в одном месте до изменения зависимой части. При временно отсутствующих новых полях UI выводит понятное сообщение «требуется пересчёт», а не выдуманные значения.
