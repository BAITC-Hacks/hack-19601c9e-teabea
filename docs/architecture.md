# Архитектура

```mermaid
flowchart LR
  A[data/*.parquet] --> B[Загрузка и валидация]
  B --> C[Направленный граф<br/>метрики и BFS reachability]
  C --> D[Неориентированная проекция<br/>Louvain-кластеры]
  C --> E[Объяснимые роли<br/>role_score]
  D --> F[Priority score и evidence]
  E --> F
  F --> G[Три CSV + snapshot.json]
  G --> H[FastAPI /api]
  H --> I[React + Cytoscape UI]
```

Вычисления выполняются один раз CLI-пайплайном. HTTP-запросы читают готовый snapshot и не пересчитывают граф. UI использует тот же origin в production; при разработке Vite проксирует `/api` на порт 8000.