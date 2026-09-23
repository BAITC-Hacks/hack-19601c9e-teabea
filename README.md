# Граф денег

Локальное приложение для анализа наблюдаемой сети переводов. Backend рассчитывает роли, кластеры и приоритеты; React-интерфейс показывает настоящий API-граф, карточку узла, top-20 и выгрузки.

## Первоначальная установка Windows

Проверено: Python 3.13.12, Node.js 22.22.2, npm 10.9.7.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
```

## Запуск

Полный запуск с пересчётом parquet и API/UI:

```powershell
.venv\Scripts\python.exe pipeline.py --data data_parquet --out out
.venv\Scripts\python.exe run.py
```

Откройте http://127.0.0.1:8000. Основная команда backend: `.venv\Scripts\python.exe pipeline.py --data data_parquet --out out --edges-export data\edges.csv`.

CSV находятся в `out/nodes_roles.csv`, `out/clusters.csv`, `out/top_nodes.csv`, расширенные метрики — в `out/node_metrics_full.csv`, метаданные — в `out/run_metadata.json`.

## Фактически проверено

Расчёт от исходных parquet: 2 248 узлов, 3 119 рёбер, 4 840 транзакций, 91 кластер, 19 изолятов, 444 boundary-узла, 4.325 секунды. Повторный запуск дал побайтно одинаковые три обязательных CSV. Пройдены 9 backend-тестов и контрактная проверка выгрузок: gid-покрытие, scores 0–1, evidence 1–200, cluster sum, top sorting, priority breakdown и исправление изолятов.

Координатор назначается только при одновременных `n_seed_neighbors >= 2` и betweenness не ниже 95-го перцентиля положительных значений. Изолят — всегда консервативная `peripheral`; `terminal` требует положительный наблюдаемый вход, `depth < 4`, не-seed и `out_deg == 0`. Приоритет: `0.40*role_support + 0.25*log_volume + 0.20*bridge + 0.15*seed_neighbors`.

Критерии ролей, формула приоритета, ограничения и масштабирование до 1 млн узлов описаны в [backend/README.md](backend/README.md). Архитектура и сценарий демо: [docs/architecture.md](docs/architecture.md), [docs/demo.md](docs/demo.md).