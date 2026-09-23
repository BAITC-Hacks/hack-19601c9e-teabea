import csv
import json
import shutil
from pathlib import Path

import pandas as pd


def publish(features: pd.DataFrame, clusters: pd.DataFrame, edges: pd.DataFrame, tx: pd.DataFrame, summary: dict, daily: dict, out_dir: Path) -> None:
    temp = out_dir.with_name(out_dir.name + ".tmp")
    if temp.exists(): shutil.rmtree(temp)
    temp.mkdir(parents=True)
    roles = features[["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]].copy()
    roles.to_csv(temp / "nodes_roles.csv", index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)
    clusters.to_csv(temp / "clusters.csv", index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)
    top = features.sort_values(["priority_score", "gid"], ascending=[False, True]).head(max(20, min(100, len(features))))
    top[["gid", "role", "priority_score", "why"]].assign(rank=range(1, len(top) + 1))[["rank", "gid", "role", "priority_score", "why"]].to_csv(temp / "top_nodes.csv", index=False, encoding="utf-8")
    node_records = json.loads(features.to_json(orient="records"))
    for row in node_records:
        row["gid"] = str(int(row["gid"])); row["cluster_id"] = int(row["cluster_id"]); row["is_seed"] = bool(row["is_seed"])
    snapshot = {"summary": summary, "warnings": summary.get("warnings", []), "nodes": node_records,
                "edges": [{"src": str(int(r.src)), "dst": str(int(r.dst)), "sum_kzt": float(r.sum_kzt), "n_tx": int(r.n_tx), "depth": int(r.depth)} for r in edges.itertuples(index=False)],
                "clusters": json.loads(clusters.to_json(orient="records")), "daily": {str(k): v for k, v in daily.items()}}
    (temp / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (temp / "config.json").write_text(json.dumps({"priority_weights": {"in_deg": .30, "in_kzt": .20, "seed_reach_count": .20, "betweenness": .15, "out_deg": .15}, "float_tolerance_kzt": .01}, ensure_ascii=False, indent=2), encoding="utf-8")
    if out_dir.exists(): shutil.rmtree(out_dir)
    temp.rename(out_dir)