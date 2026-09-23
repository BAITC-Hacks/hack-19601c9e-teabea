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
.venv\Scripts\python.exe run.py
```

Откройте http://127.0.0.1:8000. Для отдельного пересчёта: `python -m backend.app.pipeline --data data --out out`. Для API без запуска UI: `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`.

CSV находятся в `out/nodes_roles.csv`, `out/clusters.csv`, `out/top_nodes.csv`.

## Фактически проверено

Расчёт на предоставленных данных: 2 248 узлов, 3 119 рёбер, 4 840 транзакций, 91 кластер, 19 изолятов, 444 boundary-узла, около 3.4 секунды. Повторный запуск даёт побайтно одинаковые три CSV. Пройдены pytest, TypeScript/build, summary/nodes/node/graph/clusters/top, неизвестный gid, скачивание всех CSV и строковые gid.

Критерии ролей, формула приоритета, ограничения и масштабирование до 1 млн узлов описаны в [backend/README.md](backend/README.md). Архитектура и сценарий демо: [docs/architecture.md](docs/architecture.md), [docs/demo.md](docs/demo.md).