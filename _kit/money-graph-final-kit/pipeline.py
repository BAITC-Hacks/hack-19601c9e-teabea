#!/usr/bin/env python3
"""
Граф денег — HackAlem AI. Полный пайплайн: raw CSV (из parquet) -> 3 выгрузки.

    python3 pipeline.py --data ./data --out ./out

Вход:  nodes.csv (gid, depth, is_seed), edges.csv (src, dst, sum_kzt, n_tx, depth),
       transactions.csv (src, dst, date, sum_kzt)
Выход: nodes_roles.csv, clusters.csv, top_nodes.csv
"""
import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx

ROLES = ["consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"]


# ============================================================= загрузка

def load(data_dir: Path):
    edges = pd.read_csv(data_dir / "edges.csv")
    nodes = pd.read_csv(data_dir / "nodes.csv")
    tx = pd.read_csv(data_dir / "transactions.csv", parse_dates=["date"])
    return edges, nodes, tx


def sanity_check(edges, nodes, tx):
    print("=" * 64)
    print("ПРОВЕРКА ДАННЫХ")
    print("=" * 64)
    print(f"  узлов в nodes.csv     : {len(nodes):>6}")
    print(f"  рёбер                 : {len(edges):>6}")
    print(f"  транзакций            : {len(tx):>6}")
    print(f"  seed-клиентов         : {int(nodes.is_seed.sum()):>6}")
    print(f"  оборот, KZT           : {edges.sum_kzt.sum():>14,.0f}")
    print(f"  период                : {tx.date.min().date()} — {tx.date.max().date()}")

    agg = tx.groupby(["src", "dst"]).agg(s=("sum_kzt", "sum"), c=("sum_kzt", "size")).reset_index()
    m = edges.merge(agg, on=["src", "dst"], how="outer", indicator=True)
    assert (m._merge == "both").all(), "edges и transactions не сходятся по парам"
    assert np.allclose(m.sum_kzt, m.s), "суммы edges и transactions расходятся"
    print("  edges == transactions : OK")

    in_edges = set(edges.src) | set(edges.dst)
    orphans = set(nodes.gid) - in_edges
    print(f"  узлов без единого ребра: {len(orphans)}")
    print("=" * 64, "\n")
    return orphans


# ============================================================= граф + метрики

def build_graph(edges: pd.DataFrame) -> nx.DiGraph:
    G = nx.DiGraph()
    for r in edges.itertuples(index=False):
        G.add_edge(r.src, r.dst, sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), depth=int(r.depth))
    return G


def build_undirected_projection(G: nx.DiGraph) -> nx.Graph:
    """Для Louvain и betweenness межкомпонентных мостов: суммируем вес A->B и B->A."""
    UG = nx.Graph()
    for u, v, d in G.edges(data=True):
        w = d["sum_kzt"]
        if UG.has_edge(u, v):
            UG[u][v]["weight"] += w
        else:
            UG.add_edge(u, v, weight=w)
    return UG


def compute_metrics(G: nx.DiGraph, nodes: pd.DataFrame) -> pd.DataFrame:
    in_deg = dict(G.in_degree())
    out_deg = dict(G.out_degree())
    in_kzt = dict(G.in_degree(weight="sum_kzt"))
    out_kzt = dict(G.out_degree(weight="sum_kzt"))
    in_tx = dict(G.in_degree(weight="n_tx"))
    out_tx = dict(G.out_degree(weight="n_tx"))

    print("Считаю PageRank...")
    pr = nx.pagerank(G, weight="sum_kzt")

    print("Считаю HITS (hub/authority)...")
    try:
        hubs, authorities = nx.hits(G, max_iter=500)
    except nx.PowerIterationFailedConvergence:
        hubs = {n: 0.0 for n in G.nodes}
        authorities = {n: 0.0 for n in G.nodes}

    UG = build_undirected_projection(G)

    print("Считаю betweenness centrality (направленный граф, вес = 1/сумма как 'стоимость' пути)...")
    # Для betweenness интерпретируем большой перевод как "дешёвый" (более вероятный) путь денег:
    # вес ребра для алгоритма кратчайших путей = 1 / sum_kzt (чем больше сумма, тем короче путь).
    for u, v, d in G.edges(data=True):
        d["dist"] = 1.0 / max(d["sum_kzt"], 1.0)
    n_nodes = G.number_of_nodes()
    if n_nodes > 3000:
        # приближённая версия через k случайных источников — но у нас граф маленький, не требуется
        betw = nx.betweenness_centrality(G, weight="dist", k=min(500, n_nodes), seed=42)
    else:
        betw = nx.betweenness_centrality(G, weight="dist")

    print("Ищу точки сочленения (articulation points) на неориентированной проекции...")
    articulation = set(nx.articulation_points(UG))

    comp_id = {}
    for i, comp in enumerate(nx.weakly_connected_components(G)):
        for n in comp:
            comp_id[n] = i
    # изолированные узлы (без единого ребра) не попадут в G вообще — обработаем отдельно ниже

    df = nodes[["gid", "depth", "is_seed"]].copy()
    df["in_deg"] = df.gid.map(in_deg).fillna(0).astype(int)
    df["out_deg"] = df.gid.map(out_deg).fillna(0).astype(int)
    df["in_kzt"] = df.gid.map(in_kzt).fillna(0.0)
    df["out_kzt"] = df.gid.map(out_kzt).fillna(0.0)
    df["in_tx"] = df.gid.map(in_tx).fillna(0).astype(int)
    df["out_tx"] = df.gid.map(out_tx).fillna(0).astype(int)
    df["pagerank"] = df.gid.map(pr).fillna(0.0)
    df["hub_score"] = df.gid.map(hubs).fillna(0.0)
    df["authority_score"] = df.gid.map(authorities).fillna(0.0)
    df["betweenness"] = df.gid.map(betw).fillna(0.0)
    df["is_articulation"] = df.gid.isin(articulation)

    # компонента: следующий свободный id для узлов без единого ребра (каждый — своя компонента)
    next_comp = max(comp_id.values(), default=-1) + 1
    comps = []
    for gid in df.gid:
        if gid in comp_id:
            comps.append(comp_id[gid])
        else:
            comps.append(next_comp)
            next_comp += 1
    df["component_id"] = comps

    df["pass_through"] = np.where(df.in_kzt > 0, df.out_kzt / df.in_kzt.replace(0, np.nan), np.nan)

    # ЛОВУШКА №1: depth=4 & out_deg=0 — не обязательно "деньги осели", это может быть обрыв обхода.
    df["is_frontier_cutoff"] = (df.depth == 4) & (df.out_deg == 0)

    # число прямых соседей (both directions), являющихся seed-клиентами
    seed_set = set(nodes.loc[nodes.is_seed, "gid"])
    n_seed_neighbors = {}
    for gid in df.gid:
        if gid in G:
            neigh = set(G.predecessors(gid)) | set(G.successors(gid))
        else:
            neigh = set()
        n_seed_neighbors[gid] = len(neigh & seed_set)
    df["n_seed_neighbors"] = df.gid.map(n_seed_neighbors)

    return df


# ============================================================= роли

def compute_thresholds(df: pd.DataFrame) -> dict:
    """Quantile-калибровка порогов по фактическому распределению метрик (без хардкода чисел)."""
    in_pos = df.loc[df.in_deg > 0, "in_deg"]
    out_pos = df.loc[df.out_deg > 0, "out_deg"]
    betw_pos = df.loc[df.betweenness > 0, "betweenness"]

    return {
        "CONS_IN_DEG": max(5, int(np.quantile(in_pos, 0.90))) if len(in_pos) else 5,
        "DIST_OUT_DEG": max(15, int(np.quantile(out_pos, 0.90))) if len(out_pos) else 15,
        "COORD_BETW": float(np.quantile(betw_pos, 0.95)) if len(betw_pos) else 0.0,
        "COORD_SEED_LINKS": 2,
        "TRANSIT_LOW": 0.8,
        "TRANSIT_HIGH": 1.2,
    }


def assign_role(row, th: dict):
    """Возвращает (role, role_score 0..1, evidence_text <=200 симв.).
    Иерархия проверки (if/elif) намеренная — см. README, раздел «Критерии ролей»:
      1. coordinator  — связывает разные части сети (несколько seed-соседей ИЛИ высокая
                          betweenness / точка сочленения). Проверяется первой, т.к. структурная
                          роль «моста» важнее локального объёма денег — такой узел кандидат
                          в организаторы независимо от того, много ли он аккумулирует сам.
      2. consolidator — аккумулирует от многих плательщиков больше, чем раздаёт.
      3. distributor  — веерно раздаёт многим, больше чем получает.
      4. transit      — получает и отдаёт почти всё (pass_through ~1). Для seed-узлов пропускается:
                          у них in_kzt занижен (граф собран ОТ seed), pass_through не показателен.
      5. out_deg == 0 — терминальная ветка: настоящий terminal, если это НЕ артефакт обрыва на
                          4 колене; иначе (frontier cutoff) — peripheral, если только не видно
                          сильного входящего сигнала (тогда это тоже consolidator).
      6. peripheral   — всё остальное: не выявлено выраженного паттерна.
    """
    in_deg, out_deg = row.in_deg, row.out_deg
    pass_through = row.pass_through
    betw = row.betweenness
    n_seed_neigh = row.n_seed_neighbors
    is_bridge = row.is_articulation
    depth = row.depth
    is_seed = row.is_seed
    is_frontier = row.is_frontier_cutoff
    in_kzt, out_kzt = row.in_kzt, row.out_kzt

    # 1. coordinator
    if n_seed_neigh >= th["COORD_SEED_LINKS"] or (is_bridge and betw >= th["COORD_BETW"]):
        score = min(1.0, 0.4 + 0.15 * n_seed_neigh + (betw / max(th["COORD_BETW"], 1e-9)) * 0.2)
        ev = f"связан с {n_seed_neigh} seed-клиентами напрямую, betweenness={betw:.3f}"
        if is_bridge:
            ev += ", точка сочленения сети"
        return "coordinator", round(min(score, 1.0), 3), ev[:200]

    # 2. consolidator
    if in_deg >= th["CONS_IN_DEG"] and in_deg > out_deg:
        pt_txt = f"{pass_through*100:.0f}%" if pd.notna(pass_through) else "н/д"
        score = min(1.0, in_deg / (th["CONS_IN_DEG"] * 2))
        ev = f"получает от {in_deg} разных плательщиков ({in_kzt:,.0f} KZT), отдаёт дальше {pt_txt} полученного".replace(",", " ")
        return "consolidator", round(score, 3), ev[:200]

    # 3. distributor
    if out_deg >= th["DIST_OUT_DEG"] and out_deg > in_deg:
        score = min(1.0, out_deg / (th["DIST_OUT_DEG"] * 2))
        ev = f"рассылает {out_kzt:,.0f} KZT на {out_deg} разных получателей".replace(",", " ")
        return "distributor", round(score, 3), ev[:200]

    # 4. transit (не для seed — у них искусственно завышен pass_through из-за занижённого in_kzt)
    if (not is_seed) and in_deg > 0 and out_deg > 0 and pd.notna(pass_through) \
            and th["TRANSIT_LOW"] <= pass_through <= th["TRANSIT_HIGH"]:
        score = round(1.0 - abs(pass_through - 1.0), 3)
        ev = f"получает от {in_deg}, передаёт {out_deg}; pass-through {pass_through:.2f} — деньги не задерживаются"
        return "transit", max(score, 0.5), ev[:200]

    # 5. терминальная ветка
    if out_deg == 0:
        if not is_frontier:
            ev = f"получил {in_kzt:,.0f} KZT от {in_deg} плательщиков, исходящих переводов нет (глубина {depth}<4)".replace(",", " ")
            return "terminal", 0.8, ev[:200]
        else:
            if in_deg >= th["CONS_IN_DEG"]:
                pt_txt = "н/д (seed)" if is_seed else (f"{pass_through*100:.0f}%" if pd.notna(pass_through) else "н/д")
                ev = f"получает от {in_deg} плательщиков, исходящих в выборке нет, но узел на 4 колене — обрыв обхода, не факт что деньги осели"
                return "consolidator", 0.5, ev[:200]
            ev = f"узел на 4-м колене без исходящих — вероятный артефакт обрыва обхода, не подтверждённый terminal (in_deg={in_deg})"
            return "peripheral", 0.2, ev[:200]

    # 6. peripheral — по умолчанию
    ev = f"низкая активность: {in_deg} вх./{out_deg} исх. плательщиков/получателей, без выраженного паттерна"
    return "peripheral", 0.15, ev[:200]


def assign_all_roles(df: pd.DataFrame, th: dict) -> pd.DataFrame:
    roles, scores, evs = [], [], []
    for row in df.itertuples():
        role, score, ev = assign_role(row, th)
        roles.append(role)
        scores.append(score)
        evs.append(ev)
    df = df.copy()
    df["role"] = roles
    df["role_score"] = scores
    df["evidence"] = evs
    return df


# ============================================================= кластеризация

def cluster_and_hypothesize(G: nx.DiGraph, df: pd.DataFrame):
    UG = build_undirected_projection(G)
    print("Louvain community detection (на неориентированной проекции, вес = сумма KZT)...")
    communities = nx.community.louvain_communities(UG, weight="weight", seed=42)

    cluster_of = {}
    for cid, comm in enumerate(communities):
        for n in comm:
            cluster_of[n] = cid

    # изолированные узлы (не попавшие в G совсем) получают собственный кластер
    next_cid = len(communities)
    for gid in df.gid:
        if gid not in cluster_of:
            cluster_of[gid] = next_cid
            next_cid += 1

    df = df.copy()
    df["cluster_id"] = df.gid.map(cluster_of)

    rows = []
    for cid, sub in df.groupby("cluster_id"):
        gids = set(sub.gid)
        n_nodes = len(sub)
        n_seed = int(sub.is_seed.sum())
        internal_sum = 0.0
        for u, v, d in G.edges(data=True):
            if u in gids and v in gids:
                internal_sum += d["sum_kzt"]
        top_gids = sub.sort_values(["role_score", "in_deg"], ascending=False).head(5).gid.tolist()
        role_counts = sub.role.value_counts().to_dict()

        cons = sub[sub.role == "consolidator"].sort_values("role_score", ascending=False)
        coord = sub[sub.role == "coordinator"].sort_values("role_score", ascending=False)
        dist = sub[sub.role == "distributor"].sort_values("role_score", ascending=False)

        parts = [f"кластер из {n_nodes} узлов"]
        if n_seed:
            parts.append(f"{n_seed} seed-клиент(ов)")
        if len(coord):
            parts.append(f"явный coordinator (gid={coord.iloc[0].gid}) — вероятный организатор/связка ячеек")
        if len(cons):
            parts.append(f"явный consolidator (gid={cons.iloc[0].gid}) — вероятная точка сбора средств")
        if len(dist):
            parts.append(f"явный distributor (gid={dist.iloc[0].gid}) — вероятная точка раздачи")
        if not len(coord) and not len(cons) and not len(dist):
            parts.append("явных организаторов не выявлено, вероятно периферийная цепочка/курьеры")
        hypothesis = ", ".join(parts) + "."

        rows.append({
            "cluster_id": cid,
            "n_nodes": n_nodes,
            "n_seed": n_seed,
            "sum_kzt_internal": round(internal_sum, 2),
            "top_gids": ";".join(str(g) for g in top_gids),
            "hypothesis": hypothesis,
        })

    clusters_df = pd.DataFrame(rows).sort_values("cluster_id").reset_index(drop=True)
    return df, clusters_df


# ============================================================= приоритизация

def norm01(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if hi - lo < 1e-12:
        return pd.Series(0.0, index=s.index)
    return (s - lo) / (hi - lo)


ROLE_BASE_WEIGHT = {
    "coordinator": 1.0,
    "consolidator": 0.9,
    "distributor": 0.75,
    "transit": 0.35,
    "terminal": 0.25,
    "peripheral": 0.10,
}


def compute_priority(df: pd.DataFrame, clusters_df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["role_weight"] = df.role.map(ROLE_BASE_WEIGHT)
    log_in_kzt = np.log1p(df.in_kzt)
    norm_volume = norm01(log_in_kzt)
    norm_betw = norm01(df.betweenness)
    norm_seed_links = norm01(df.n_seed_neighbors.clip(upper=5))

    # priority = 0.40*роль + 0.25*объём денег (лог, норм.) + 0.20*посредничество + 0.15*связь с seed
    df["priority_score"] = (
        0.40 * df.role_weight * df.role_score
        + 0.25 * norm_volume
        + 0.20 * norm_betw
        + 0.15 * norm_seed_links
    ).round(4)

    cluster_seed = clusters_df.set_index("cluster_id").n_seed.to_dict()

    whys = []
    for row in df.itertuples():
        base = row.evidence
        cl_seed = cluster_seed.get(row.cluster_id, 0)
        extra = f" Кластер {row.cluster_id} ({cl_seed} seed), объём входящих {row.in_kzt:,.0f} KZT.".replace(",", " ")
        whys.append((base + extra)[:400])
    df["why"] = whys
    return df


# ============================================================= выгрузки

def write_outputs(df: pd.DataFrame, clusters_df: pd.DataFrame, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    nodes_roles = df[["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]].copy()
    assert len(nodes_roles) == len(df)
    assert nodes_roles.isna().sum().sum() == 0, "есть NaN в обязательных колонках nodes_roles.csv"
    nodes_roles.to_csv(out_dir / "nodes_roles.csv", index=False)

    clusters_df.to_csv(out_dir / "clusters.csv", index=False)

    top = df.sort_values("priority_score", ascending=False).head(max(20, min(40, len(df)))).copy()
    top = top.reset_index(drop=True)
    top.insert(0, "rank", top.index + 1)
    top_nodes = top[["rank", "gid", "role", "priority_score", "why"]]
    top_nodes.to_csv(out_dir / "top_nodes.csv", index=False)

    print(f"\nВыгрузки записаны в {out_dir}/")
    print(f"  nodes_roles.csv : {len(nodes_roles)} строк")
    print(f"  clusters.csv    : {len(clusters_df)} строк")
    print(f"  top_nodes.csv   : {len(top_nodes)} строк")
    print("\nРаспределение ролей:")
    print(df.role.value_counts().to_string())


# ============================================================= main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="./data")
    ap.add_argument("--out", default="./out")
    a = ap.parse_args()

    data_dir = Path(a.data)
    edges, nodes, tx = load(data_dir)
    sanity_check(edges, nodes, tx)

    G = build_graph(edges)
    df = compute_metrics(G, nodes)

    th = compute_thresholds(df)
    print("Калиброванные пороги (по квантилям реальных данных):", th, "\n")

    df = assign_all_roles(df, th)
    df, clusters_df = cluster_and_hypothesize(G, df)
    df = compute_priority(df, clusters_df)

    write_outputs(df, clusters_df, Path(a.out))

    # полный датафрейм пригодится фронту / для отладки
    df.to_csv(Path(a.out) / "node_metrics_full.csv", index=False)


if __name__ == "__main__":
    main()
