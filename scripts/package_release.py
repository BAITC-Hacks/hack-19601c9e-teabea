"""Build a local hackathon handoff with an explicit file allowlist."""
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def main():
    report = json.loads((ROOT / 'verification/report.json').read_text(encoding='utf-8'))
    docs = ROOT / 'docs'
    docs.mkdir(exist_ok=True)
    (docs / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    freeze = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True)
    (docs / 'tested-environment.txt').write_text(f"Python {report['python']} / Windows x64\n" + freeze, encoding='utf-8')
    example = report['examples']
    demo = f'''# Демо: 5 минут

Сценарий использует gid, выбранные программно из текущего расчёта, а не из классификатора.
Перед показом установите зависимости. Запуск: `.venv\\Scripts\\python.exe run.py`.
Откройте http://127.0.0.1:8501. Подготовьте второе окно с README и CSV.

| Время | Действие и объяснение |
|---|---|
| 0:00 | Аналитик получает сеть наблюдаемых переводов и объяснимый приоритет проверки. Роли — гипотезы. |
| 0:30 | Запустите run.py. Измеренные полные прогоны parquet → CSV: {report['wall_seconds'][0]} и {report['wall_seconds'][1]} с. Покажите период и фактические размеры. |
| 1:15 | Откройте глобальный топ и нажмите «Показать на графе» для {example['top']}. Перейдите в «Граф и карточка», прочитайте evidence и четыре вклада приоритета. |
| 2:15 | Найдите консолидацию {example['consolidator']}, затем транзит {example['transit']}. Сравните наблюдаемый вход и выход, не делайте вывод о движении тех же денег. |
| 3:00 | Поиск произвольного {example['arbitrary']}. Выберите два шага. Покажите изолят {example['isolate']} — одна точка и отсутствие данных для роли. |
| 3:40 | Найдите boundary {example['boundary']}. Прочитайте предупреждение depth=4. Покажите фильтры, пустой список ролей, сброс, режим всей сети и выбор кластера. |
| 4:20 | Скачайте три CSV. Покажите архитектуру, воспроизводимость и план масштабирования. |

Клик по графу открывает подробности внутри iframe. Карточка Streamlit выбирается поиском или топом.
Проверка сценария через AppTest отражена в verification.md; визуальная браузерная проверка отдельно не подтверждена.
'''
    (docs / 'demo.md').write_text(demo, encoding='utf-8')
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    archive = release / 'graf-deneg-submission.zip'
    files = [ROOT / n for n in ['app.py', 'pipeline.py', 'run.py', 'README.md', 'requirements.txt', 'requirements-core.txt', 'requirements-ui.txt', 'requirements-dev.txt']]
    for folder in ['ui', 'tests', 'scripts', 'docs', '.streamlit', 'data_parquet']:
        files += [p for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    with ZipFile(archive, 'w', ZIP_DEFLATED) as z:
        for path in sorted(set(files)):
            z.write(path, path.relative_to(ROOT).as_posix())
        for path in (ROOT / 'verification/run1').iterdir():
            z.write(path, 'out/' + path.name)
        z.write(ROOT / 'verification/edges1.csv', 'data/edges.csv')
        z.write(ROOT / '_kit/money-graph-final-kit/viewer_original.html', 'reference/viewer_original.html')
    with ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(not any(part in p.split('/') for part in ['.git', '.venv', '.venv-ui', '__pycache__']) for p in z.namelist())
        assert not any(p.startswith(('frontend/', 'backend/')) for p in z.namelist())
        for name, expected in report['csv_sha256'].items():
            import hashlib
            assert hashlib.sha256(z.read('out/' + name)).hexdigest() == expected
        import ast
        for name in z.namelist():
            if name.endswith('.py'):
                ast.parse(z.read(name).decode('utf-8-sig'), filename=name)
    print(archive)


if __name__ == '__main__':
    main()
