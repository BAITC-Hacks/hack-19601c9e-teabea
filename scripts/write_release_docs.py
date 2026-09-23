"""Write documentation examples from the verified current snapshot."""
import json
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT/'docs/verification.json').read_text(encoding='utf-8'))
meta = json.loads((ROOT/'out/run_metadata.json').read_text(encoding='utf-8'))
examples = report['examples']
diagram = '''```mermaid
flowchart LR
  A[Три parquet] --> B[Валидация схем и агрегатов]
  B --> C[Направленный граф и признаки]
  C --> D[Louvain и шесть ролей]
  D --> E[Приоритет и объяснения]
  E --> F[CSV и metadata]
  F --> G[Streamlit и PyVis]
```'''
readme = r'''# Граф денег

Локальный инструмент для аналитика: читает наблюдаемую сеть переводов, рассчитывает структурные роли, сообщества и приоритет проверки, показывает связи и численные объяснения. Роли — гипотезы без размеченной истины; score не означает вероятность виновности.

## Установка и один запуск (Windows)

Проверено на Python 3.12.14 / Windows 11. Установите Python 3.12, распакуйте архив и откройте PowerShell в папке `money-graph`. Активация окружения не нужна:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

Откройте **http://127.0.0.1:8501**. `run.py` сначала пересчитывает исходные `data_parquet/{nodes,edges,transactions}.parquet` тем же Python, ждёт успешного завершения и запускает Streamlit. Ошибка расчёта останавливает запуск. Ctrl+C завершает дочерний процесс; фактическая проверка клавиши в Windows остаётся в чек-листе. Для стандартного Python в PATH достаточно `python run.py`.

Интернет нужен для установки. Приложение слушает только localhost, telemetry отключена, vis встроен в HTML. Браузерная проверка offline в этой сессии недоступна — см. [протокол](docs/verification.md).

Прямые зависимости закреплены в `requirements-core.txt` и `requirements-ui.txt`, объединены корневым `requirements.txt`; полный проверенный состав — `requirements-lock.txt` (его можно установить вместо корневого файла).

## CLI и результаты

```powershell
.venv\Scripts\python.exe pipeline.py --data data_parquet --out out --edges-export data\edges.csv
.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 -- --data out --edges data\edges.csv
```

Default-пути считаются от файла проекта, явно переданные пути — от текущего каталога. `run.py` передаёт абсолютные пути. CSV-вход допустим только полным набором тех же трёх таблиц; основной reader — pyarrow. Проверяются типы, ссылки, дубликаты, depth, даты, суммы (`atol=0.01 KZT`, `rtol=1e-12`) и точное число транзакций по паре.

| Файл | Содержание |
|---|---|
| `out/nodes_roles.csv` | gid, role, role_score, cluster_id, priority_score, evidence |
| `out/clusters.csv` | cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids, hypothesis |
| `out/top_nodes.csv` | rank, gid, role, priority_score, why; глобальный топ-40 |
| `out/node_metrics_full.csv` | Полные метрики, explanation и четыре вклада в приоритет |
| `out/run_metadata.json` | Объём входа, период, пороги, методы, время, предупреждения |
| `data/edges.csv` | Направленные рёбра для интерфейса |

Каждый входной gid представлен ровно один раз; изоляты сохранены и получают отдельные кластеры. gid — int64 в расчёте, десятичная запись в CSV, строки в UI/JavaScript. Встречные веса суммируются для неориентированной проекции Louvain (`seed=42`), внутренний оборот считается по исходным направленным рёбрам. Кластеры нумеруются по минимальному gid. Топ сортируется по убыванию приоритета и числовому gid при равенстве.

## Роли и поддержка гипотезы

Обозначения: `I/O` — входящие/исходящие контрагенты; `V` — наблюдаемый вход; `T` — число исходящих транзакций; `S` — прямые seed-соседи; `R` — число seed, от которых узел достижим за 1–4 направленных шага; `B` — точная направленная невзвешенная betweenness. PageRank взвешен суммой переводов и показан как метрика, но не входит в priority. `clip(x)=min(1,max(0,x))`.

Пороги: `Ci=max(5,int(q90(I>0)))`, `Co=max(15,int(q90(O>0)))`, `Cb=q95(B>0)`. Если положительных B нет, координатор отключён. В текущем прогоне Ci=5, Co=15, Cb=0.0013361804.

Сначала изоляты, затем первое сработавшее правило в порядке таблицы. Пересекающиеся сигналы консолидации, распределения и транзита сохранены в explanation; это не дополнительная независимая классификация.

| Роль | Условие | role_score |
|---|---|---|
| Изолят → peripheral | I=O=0 | 0.20, данных недостаточно |
| coordinator | S≥2 и B≥Cb>0 | clip(0.5·min(S/4,1)+0.5·B/Cb) |
| consolidator | I≥Ci и V>0 | clip(0.55·min(I/(2Ci),1)+0.45·min(R/4,1)); у boundary максимум 0.65 |
| distributor | O≥Co | clip(0.55·min(O/(2Co),1)+0.45·min(T/100,1)) |
| transit | не seed, не boundary, вход/выход положительны, p=out_kzt/in_kzt в [0.8,1.2] | clip(1−abs(p−1)/0.4) |
| terminal | не seed, depth<4, V>0, O=0 | 0.55+0.45·min(V/max(max(V),1),1) |
| peripheral | остальные | 0.15 |

Boundary означает `depth=4 AND out_deg=0`, поэтому консолидация на границе допускается, но отсутствие выхода не доказывает удержание. У seed входящие неполны. Отношение месячного выхода к входу не доказывает транзит тех же денег.

## Приоритет

```
priority = 0.40 × weight(role) × role_score
         + 0.25 × minmax(log1p(in_kzt))
         + 0.20 × minmax(betweenness)
         + 0.15 × minmax(min(n_seed_neighbors, 5))
```

Веса: coordinator 1.0, consolidator 0.9, distributor 0.75, transit 0.35, terminal 0.25, peripheral 0.10. Minmax считается по всему набору; константный признак даёт 0. Итог округлён до шести знаков; сумма четырёх сохранённых вкладов совпадает с ним с допуском 1e-6. Приоритет зависит от эвристической роли и состава выборки; между разными выгрузками он не калиброван.

## Интерфейс

Поиск точного gid и кнопка в глобальном топе выбирают карточку и сбрасывают фильтры с сообщением. Карточка находится во вкладке «Сеть и карточка». Наведение на узел графа показывает детали; клик внутри PyVis не переключает Python-карточку. Режим полной сети сохраняется, пустой список ролей/глубин даёт пустой граф. Доступны кластер, seed, сумма ребра и 1–2 шага в обе стороны при сохранении направления стрелок. Фильтры влияют только на видимость; скачиваются полные три CSV. Кэш учитывает mtime и размер результатов, есть ручное обновление.

## Фактическая проверка

REPORT_PLACEHOLDER

Проверено 15 тестов; `pip check` не нашёл конфликтов. Выполнен реальный `run.py`, Streamlit AppTest и проверка HTML. **Визуальный браузерный прогон, экран 1280×720, скачивания в браузере, сетевой offline-тест и физический Ctrl+C не проверены**: браузеры недоступны инструментам сессии. Подробности и точные границы проверки — [verification.md](docs/verification.md), машинный отчёт — [verification.json](docs/verification.json).

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe scripts/verify_release.py
.venv\Scripts\python.exe scripts/package_release.py
```

## Архитектура и демо

DIAGRAM_PLACEHOLDER

[Схема решения](docs/architecture.md), [SVG для одного слайда](docs/architecture.svg), [пятиминутное демо](docs/demo.md). Архив создаётся в `dist/money-graph-submission.zip`; данные включены только для предусмотренной передачи организаторам хакатона. Не публикуйте архив и данные в открытом доступе.

## Ограничения и миллион узлов

Наблюдаются только внутрибанковские переводы от seed на четыре колена, с порогом 5000 KZT. Нет полного баланса, внешних входов, клиентских атрибутов и ground truth. Нельзя сообщать accuracy или делать юридические выводы. Оборот может многократно учитывать одни средства.

На миллионе узлов нужно заменить объекты NetworkX компактным CSR/компилируемым графом, использовать Arrow/Polars для колоночных агрегатов, приблизительную центральность с фиксированной выборкой, пакетную кластеризацию и отдачу выбранных подграфов/агрегатов в UI. Глобальные PageRank/betweenness зависят от удалённых изменений графа: точное обновление только ближайших соседей не гарантируется. Такой масштаб здесь не тестировался.

## Сохранённые исходники

В рабочем репозитории `backend/` и `frontend/` — прежний вариант API/React, не участвующий в новом запуске и не включённый в архив. Их исторические проверки не засчитываются в текущий протокол. Исходный `_kit/` сохранён отдельно.

`_kit/money-graph-final-kit/pqmini` — ограниченный Linux fallback из исходного комплекта, с жёсткой зависимостью от libzstd. Он не используется основным CLI, не проверялся здесь и не включён в архив. Поддержка произвольного parquet им не заявляется.
'''
counts = ', '.join(f'{k}: {v}' for k,v in report['role_counts'].items())
summary = f"Исходные parquet: {report['input_rows']['nodes']} узлов, {report['input_rows']['edges']} рёбер, {report['input_rows']['transactions']} транзакций; {meta['seed_count']} seed, {report['clusters']} кластер, {report['isolates']} изолятов, {report['boundary']} boundary. Период {meta['period_from']} — {meta['period_to']}. CLI wall time: **{' / '.join(map(str, report['cli_wall_seconds']))} с**; три обязательных CSV побайтно воспроизводимы. Распределение: {counts}."
(ROOT/'README.md').write_text(readme.replace('REPORT_PLACEHOLDER',summary).replace('DIAGRAM_PLACEHOLDER',diagram), encoding='utf-8')
(ROOT/'docs/architecture.md').write_text('# Архитектура\n\n'+diagram+'''

`run.py` последовательно вызывает `pipeline.py` и Streamlit через `sys.executable`, передаёт абсолютные пути и не запускает UI при ошибке расчёта. API/Node-сервер не нужен.

Валидация проверяет весь набор входов, int64 идентификаторы, ссылки, суммы и количества. Граф содержит все узлы до расчёта метрик. Louvain работает по неориентированной проекции с суммой встречных весов; роли и приоритет считаются по направленным признакам.

Результаты готовятся во временном каталоге, проверяются и публикуются с резервным комплектом для отката. Маркер публикации останавливает загрузку UI во время замены файлов. Это локальный последовательный запуск, а не многопользовательская транзакционная БД; одновременные пересчёты в один out не поддерживаются.

Интерфейс читает CSV, не пересчитывает роли; gid передаётся в PyVis строками. Inline vis исключает CDN-скрипты; визуальная и сетевая проверка браузером остаются открытыми.

[SVG 1600×900 для слайда](architecture.svg). [Протокол проверки](verification.md).
''', encoding='utf-8')
demo = f'''# Демо — 5 минут

Примеры ниже выбраны программно из текущего результата скриптом `scripts/verify_release.py`. Это сценарий живого показа, не запись выполненного браузерного демо. Перед показом пройти оставшийся чек-лист из `verification.md`.

| Время | Действие и объяснение |
|---|---|
| 0:00–0:30 | Аналитику нужно быстро выбрать узлы для проверки и объяснить решение. Здесь роли — структурные гипотезы, без утверждения виновности. |
| 0:30–1:15 | Запустить `.venv\\Scripts\\python.exe run.py`. Показать пересчёт из трёх parquet и http://127.0.0.1:8501. Измеренные CLI-прогоны: {report['cli_wall_seconds'][0]} и {report['cli_wall_seconds'][1]} с; на другой машине время изменится. |
| 1:15–2:15 | «Глобальный топ-20» → первый узел `{examples['first_top']}` → «Показать на графе» → «Сеть и карточка». Разобрать seed-соседей, betweenness и четыре численных вклада. Это гипотеза координации по двум сигналам. |
| 2:15–3:00 | Найти консолидацию `{examples['consolidator']}`. Сравнить входящий веер, роль и приоритет с предыдущим узлом. Альтернатива: транзит `{examples['transit']}`; отношение месячных сумм не доказывает движение тех же средств. |
| 3:00–3:40 | Ввести произвольный gid жюри; запасной пример `{examples['arbitrary']}`. Затем изолят `{examples['isolate']}`: одна точка, 0 связей, peripheral, pass-through «н/д». Неизвестный gid даёт явное сообщение. |
| 3:40–4:20 | Найти boundary `{examples['boundary']}`. Показать depth=4 и предупреждение; отсутствие выхода не означает удержание. У seed вход неполон, переводы ниже порога не видны. |
| 4:20–5:00 | Показать «Кластеры», перейти к выбранному кластеру; скачать три полных CSV. Открыть architecture.svg. Для миллиона узлов: компактный граф, приближённая центральность, колоночные агрегаты и подграфы в UI. |

В «Вся сеть» доступны все узлы без скрытого сэмплирования. Смена фильтров сохраняет режим, пустые роли показывают пустой результат. Подсказка графа доступна наведением; выбор карточки делается поиском/топом. Завершить консоль Ctrl+C и проверить освобождение порта.
'''
(ROOT/'docs/demo.md').write_text(demo, encoding='utf-8')
blocks = [('01','PARQUET','nodes · edges · transactions'),('02','ВАЛИДАЦИЯ','Схемы · ссылки · суммы · n_tx'),('03','ГРАФ И ПРИЗНАКИ','Направления · все узлы · метрики'),('04','LOUVAIN И РОЛИ','Сообщества · 6 гипотез'),('05','ПРИОРИТЕТ И CSV','Четыре вклада · объяснения'),('06','STREAMLIT / PYVIS','Поиск · связи · карточка · экспорт')]
svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900"><rect width="1600" height="900" fill="#101827"/><g font-family="Arial, sans-serif"><text x="80" y="105" fill="white" font-size="48">Граф денег</text><text x="80" y="158" fill="#a8b8ce" font-size="26">От наблюдаемых переводов к объяснимому приоритету проверки</text>']
for i,(num,title,subtitle) in enumerate(blocks):
    x=80+(i%3)*510; y=235+(i//3)*250
    svg.append(f'<rect x="{x}" y="{y}" width="450" height="180" rx="16" fill="#1e2c41" stroke="#59d5bd"/><text x="{x+25}" y="{y+42}" fill="#59d5bd" font-size="23">{num}</text><text x="{x+25}" y="{y+91}" fill="white" font-size="27">{escape(title)}</text><text x="{x+25}" y="{y+139}" fill="#c0ccdd" font-size="21">{escape(subtitle)}</text>')
    if i%3<2:
        svg.append(f'<path d="M {x+457} {y+90} h 40 m -12 -9 l 12 9 -12 9" fill="none" stroke="#59d5bd" stroke-width="3"/>')
svg.append('<path d="M 1500 415 V 445 H 55 V 575 H 73 m -12 -9 l 12 9 -12 9" fill="none" stroke="#59d5bd" stroke-width="3"/><text x="80" y="765" fill="#59d5bd" font-size="25">Один запуск: python run.py   •   Локально: 127.0.0.1:8501</text><text x="80" y="822" fill="#a8b8ce" font-size="23">Роли — гипотезы. Depth=4 — граница наблюдения. Входящие seed неполны.</text></g></svg>')
(ROOT/'docs/architecture.svg').write_text(''.join(svg), encoding='utf-8')
