import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"
app = FastAPI(title="Money Graph API", version="1.0")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    error = detail.get("error", detail)
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": error.get("code", "HTTP_ERROR"), "message": error.get("message", "Ошибка запроса")}})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "INVALID_REQUEST", "message": "Некорректные параметры запроса"}})


def snapshot() -> dict:
    path = OUT / "snapshot.json"
    if not path.exists():
        raise HTTPException(status_code=503, detail={"error": {"code": "DATA_NOT_READY", "message": "Расчёт ещё не опубликован"}})
    return json.loads(path.read_text(encoding="utf-8"))


def error_response(request, exc):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=422, content={"error": {"code": "INVALID_REQUEST", "message": str(exc)}})


@app.get("/health")
def health():
    return {"status": "ok", "data_ready": (OUT / "snapshot.json").exists()}


@app.get("/api/summary")
def summary(): return snapshot()["summary"]


@app.get("/api/nodes")
def nodes(gid: str | None = None, role: str | None = None, cluster_id: int | None = None, depth: int | None = None, is_seed: bool | None = None, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    items = snapshot()["nodes"]
    if gid is not None: items = [x for x in items if x["gid"] == gid]
    if role is not None: items = [x for x in items if x["role"] == role]
    if cluster_id is not None: items = [x for x in items if x["cluster_id"] == cluster_id]
    if depth is not None: items = [x for x in items if x["depth"] == depth]
    if is_seed is not None: items = [x for x in items if x["is_seed"] == is_seed]
    items.sort(key=lambda x: (-x["priority_score"], int(x["gid"])))
    return {"items": items[offset:offset + limit], "total": len(items)}


@app.get("/api/nodes/{gid}")
def node(gid: str):
    data = snapshot(); item = next((x for x in data["nodes"] if x["gid"] == gid), None)
    if item is None: raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "gid не найден"}})
    return {"node": item, "explanation": item["explanation"], "warnings": data["warnings"], "daily_flows": data["daily"].get(gid, [])}


@app.get("/api/clusters")
def clusters(): return {"items": snapshot()["clusters"]}


@app.get("/api/top")
def top(limit: int = Query(20, ge=20, le=100)):
    data = snapshot(); ordered = sorted(data["nodes"], key=lambda x: (-x["priority_score"], int(x["gid"])))[:limit]
    return {"items": [{"rank": i, "gid": x["gid"], "role": x["role"], "priority_score": x["priority_score"], "why": x["why"]} for i, x in enumerate(ordered, 1)]}


@app.get("/api/graph")
def graph(gid: str | None = None, hops: int = Query(1, ge=1, le=2), cluster_id: int | None = None, role: str | None = None, depth: int | None = None, is_seed: bool | None = None, min_sum_kzt: float = Query(0, ge=0)):
    data = snapshot(); all_nodes = {x["gid"]: x for x in data["nodes"]}; edges = data["edges"]
    visible = set(all_nodes)
    if gid is not None:
        if gid not in all_nodes: raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "gid не найден"}})
        visible = {gid}; changed = True
        for _ in range(hops):
            visible |= {e["src"] for e in edges if e["dst"] in visible} | {e["dst"] for e in edges if e["src"] in visible}
    def matches(item): return (cluster_id is None or item["cluster_id"] == cluster_id) and (role is None or item["role"] == role) and (depth is None or item["depth"] == depth) and (is_seed is None or item["is_seed"] == is_seed)
    filtered = {key for key in visible if matches(all_nodes[key])}
    if gid is not None: filtered.add(gid)
    selected_edges = [e for e in edges if e["src"] in filtered and e["dst"] in filtered and e["sum_kzt"] >= min_sum_kzt]
    return {"nodes": [all_nodes[key] for key in sorted(filtered, key=int)], "edges": selected_edges, "scope": "neighborhood" if gid else "full", "total_nodes": len(filtered), "total_edges": len(selected_edges)}


@app.get("/api/exports/{filename}")
def exports(filename: str):
    if filename not in {"nodes_roles.csv", "clusters.csv", "top_nodes.csv"}: raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "Выгрузка не найдена"}})
    path = OUT / filename
    if not path.exists(): raise HTTPException(503, detail={"error": {"code": "DATA_NOT_READY", "message": "Расчёт ещё не опубликован"}})
    return FileResponse(path, media_type="text/csv; charset=utf-8", filename=filename)


FRONTEND_DIST = ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")