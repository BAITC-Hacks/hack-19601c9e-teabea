from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: dict[str, str]


class NodeSummary(BaseModel):
    gid: str
    role: str
    role_score: float
    cluster_id: int
    priority_score: float
    evidence: str
    depth: int
    is_seed: bool
    truncated_by_depth: bool
    in_deg: int
    out_deg: int
    in_kzt: float
    out_kzt: float
    in_tx: int
    out_tx: int
    pagerank: float
    pass_through: float | None


class Edge(BaseModel):
    src: str; dst: str; sum_kzt: float; n_tx: int; depth: int
