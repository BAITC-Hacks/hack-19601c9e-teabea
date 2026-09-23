import numpy as np
import pandas as pd


PRIORITY_COLUMNS = ["in_deg", "in_kzt", "seed_reach_count", "betweenness", "out_deg"]


def _percentile(series: pd.Series) -> pd.Series:
    positive = series > 0
    result = pd.Series(0.0, index=series.index)
    if positive.any():
        result.loc[positive] = series.loc[positive].rank(method="average", pct=True)
    return result


def assign_roles(features: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    for column in PRIORITY_COLUMNS:
        df[f"p_{column}"] = _percentile(df[column])
    df["priority_score"] = (0.30 * df.p_in_deg + 0.20 * df.p_in_kzt + 0.20 * df.p_seed_reach_count + 0.15 * df.p_betweenness + 0.15 * df.p_out_deg).clip(0, 1)
    positive_b = df.loc[df.betweenness > 0, "betweenness"]
    coordinator_cutoff = positive_b.quantile(0.90) if not positive_b.empty else np.inf
    roles, scores, evidence, explanations = [], [], [], []
    for row in df.itertuples(index=False):
        support = []
        if row.seed_reach_count >= 2 and row.betweenness > 0 and row.betweenness >= coordinator_cutoff and row.neighbor_communities >= 2:
            role = "coordinator"
            score = min(1.0, 0.35 * min(row.seed_reach_count / 5, 1) + 0.35 * (row.betweenness / coordinator_cutoff) + 0.30 * min(row.neighbor_communities / 4, 1))
            support.append("достижим от нескольких seed и связывает сообщества")
        elif row.out_deg >= 10:
            role = "distributor"; score = min(1.0, 0.55 * min(row.out_deg / 20, 1) + 0.45 * row.p_out_deg); support.append(f"веер на {row.out_deg} получателей")
        elif row.in_deg >= 3 and row.in_kzt > 0:
            role = "consolidator"; score = min(1.0, 0.55 * min(row.in_deg / 10, 1) + 0.45 * min(row.seed_reach_count / 4, 1)); support.append(f"получает от {row.in_deg} плательщиков")
        elif (not row.is_seed and not row.truncated_by_depth and row.in_kzt > 0 and row.out_deg > 0 and row.pass_through is not None and 0.8 <= row.pass_through <= 1.2):
            role = "transit"; score = min(1.0, 1 - abs(row.pass_through - 1) / 0.4); support.append(f"наблюдаемый pass-through {row.pass_through:.2f}")
        elif not row.is_seed and row.depth < 4 and row.in_kzt > 0 and row.out_deg == 0:
            role = "terminal"; score = min(1.0, 0.55 + 0.45 * row.p_in_kzt); support.append("возможный конечный получатель в наблюдаемом графе")
        else:
            role = "peripheral"; score = min(1.0, 0.35 + 0.25 * (row.in_deg == 0) + 0.25 * (row.out_deg == 0)); support.append("недостаточно наблюдаемых связей")
        alternatives = []
        if row.in_deg >= 3: alternatives.append("consolidator")
        if row.out_deg >= 10: alternatives.append("distributor")
        if row.out_deg and row.in_kzt > 0 and row.pass_through is not None and 0.8 <= row.pass_through <= 1.2: alternatives.append("transit")
        caveat = " исходящие за 4-м коленом не наблюдаются." if row.truncated_by_depth else (" входящие seed могут быть неполными." if row.is_seed else "")
        if role == "peripheral" and row.in_deg == 0 and row.out_deg == 0: caveat = " ноль наблюдаемых связей."
        text = f"{role}: " + "; ".join(support) + f"; in/out {row.in_kzt:,.0f}/{row.out_kzt:,.0f} KZT." + caveat
        roles.append(role); scores.append(round(float(score), 6)); evidence.append(text[:200]); explanations.append(text + (f" Альтернативные сигналы: {', '.join(alternatives)}." if alternatives else ""))
    df["role"], df["role_score"], df["evidence"], df["explanation"] = roles, scores, evidence, explanations
    df["why"] = df.apply(lambda row: f"{row.role}: {row.evidence} Приоритет {row.priority_score:.3f} (in_deg {row.p_in_deg:.2f}, in_kzt {row.p_in_kzt:.2f}, seed reach {row.p_seed_reach_count:.2f}, betweenness {row.p_betweenness:.2f}, out_deg {row.p_out_deg:.2f}).", axis=1)
    return df