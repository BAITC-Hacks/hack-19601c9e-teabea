#!/usr/bin/env python3
"""
Конвертер parquet -> CSV на чистом Python, без pyarrow/fastparquet.

Нужен только в окружениях без сети/пакетов (как этот контейнер). Если у вас
есть pyarrow, конвертация не требуется — pipeline.py и так прочитает CSV,
которые вы получите либо отсюда, либо напрямую через pd.read_parquet.

Поддерживает: PLAIN и RLE_DICTIONARY энкодинги, кодеки UNCOMPRESSED/ZSTD/GZIP/
SNAPPY, колонки REQUIRED и OPTIONAL (без null-значений — если встретит NULL,
кинет NotImplementedError, см. README раздел "Известные ограничения парсера").
ZSTD декодируется через системную libzstd.so.1 (ctypes) — сборка/pip не нужны.

Запуск:
    python3 convert.py --in ./data_parquet --out ./data
    (ожидает в --in файлы nodes.parquet, edges.parquet, transactions.parquet)
"""
import argparse
import csv
import datetime
from pathlib import Path

from pqmini.pqread import read_parquet


def convert_nodes(src: Path, dst: Path):
    result, _ = read_parquet(src)
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["gid", "depth", "is_seed"])
        for row in zip(result["gid"], result["depth"], result["is_seed"]):
            w.writerow(row)


def convert_edges(src: Path, dst: Path):
    result, _ = read_parquet(src)
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["src", "dst", "sum_kzt", "n_tx", "depth"])
        for row in zip(result["src"], result["dst"], result["sum_kzt"], result["n_tx"], result["depth"]):
            w.writerow(row)


def convert_transactions(src: Path, dst: Path):
    result, _ = read_parquet(src)
    epoch = datetime.date(1970, 1, 1)
    dates = [(epoch + datetime.timedelta(days=int(d))).isoformat() for d in result["date"]]
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["src", "dst", "date", "sum_kzt"])
        for row in zip(result["src"], result["dst"], dates, result["sum_kzt"]):
            w.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", required=True, help="папка с *.parquet")
    ap.add_argument("--out", dest="out_dir", required=True, help="куда писать *.csv")
    a = ap.parse_args()

    in_dir, out_dir = Path(a.in_dir), Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    convert_nodes(in_dir / "nodes.parquet", out_dir / "nodes.csv")
    convert_edges(in_dir / "edges.parquet", out_dir / "edges.csv")
    convert_transactions(in_dir / "transactions.parquet", out_dir / "transactions.csv")
    print(f"Готово: {out_dir}/nodes.csv, edges.csv, transactions.csv")


if __name__ == "__main__":
    main()
