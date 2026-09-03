import csv
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import DATA, RESULTS, ROOT
from .io import atomic_json, read_json
from .results import summarize
from .runner import run_job

def _reconcile_interrupted():
    """Runs left RUNNING by a dead wrapper/API process can never finish; mark them."""
    for path in sorted((DATA / "runs").glob("*/run.json")):
        record = read_json(path)
        if record.get("status") == "RUNNING":
            record.update(status="FAILED",
                          error="Interrupted by API restart (runner wrapper died)",
                          finished_at=datetime.now(UTC).isoformat())
            atomic_json(path, record)


@asynccontextmanager
async def lifespan(_app):
    _reconcile_interrupted()
    yield


app = FastAPI(title="GeoFlow", description="Hadoop 时空大数据实验平台", version="0.1.0",
              lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
executor = ThreadPoolExecutor(max_workers=1)
job_lock = threading.Lock()
job_state = {"status": "IDLE"}


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")


def latest():
    path = RESULTS / "latest.json"
    if not path.exists():
        raise HTTPException(404, "还没有已完成的分析，请先导入数据并运行 Hadoop 作业。")
    return read_json(path)


@app.get("/api/zones")
def zones():
    path = DATA / "zones.geojson"
    if not path.exists():
        raise HTTPException(404, "请先执行数据导入。")
    return FileResponse(path, media_type="application/geo+json")


def analysis_data(hour, borough):
    features = read_json(DATA / "zones.geojson")["features"]
    info = {x["properties"]["id"]: x["properties"] for x in features}
    if borough and borough not in {v["borough"] for v in info.values()}:
        raise HTTPException(422, "Unknown borough")
    return summarize(latest(), info, hour, borough)


@app.get("/api/analysis")
def analysis(hour: int | None = Query(None, ge=0, le=23), borough: str | None = None):
    return analysis_data(hour, borough)


@app.get("/api/export")
def export(hour: int | None = Query(None, ge=0, le=23), borough: str | None = None):
    data = analysis_data(hour, borough)
    out = io.StringIO()
    fields = ["id", "name", "borough", "trips", "avg_distance_km", "avg_minutes", "avg_amount"]
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data["zones"])
    return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="geoflow-zones.csv"'})


@app.get("/api/cluster")
def cluster():
    result = {"online": False, "physical_hosts": 1, "mode": "WSL 单机多节点", "nodes": []}
    with httpx.Client(timeout=2, trust_env=False) as client:
        try:
            response = client.get("http://127.0.0.1:18088/ws/v1/cluster/metrics")
            response.raise_for_status()
            result["yarn"] = response.json()["clusterMetrics"]
            response = client.get("http://127.0.0.1:18088/ws/v1/cluster/nodes")
            response.raise_for_status()
            result["nodes"] = (response.json().get("nodes") or {}).get("node", [])
            result["online"] = result["yarn"].get("activeNodes", 0) > 0
        except (httpx.HTTPError, KeyError, ValueError):
            result["yarn_error"] = "YARN 不可达或未启动"
        try:
            response = client.get("http://127.0.0.1:19870/jmx",
                                  params={"qry": "Hadoop:service=NameNode,name=FSNamesystemState"})
            response.raise_for_status()
            result["hdfs"] = response.json()["beans"][0]
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            result["hdfs_error"] = "NameNode 不可达或未启动"
    return result


@app.get("/api/runs")
def runs():
    records = []
    for path in sorted((DATA / "runs").glob("*/run.json"), reverse=True)[:30]:
        records.append(read_json(path))
    return {"runs": records, "current": job_state}


class JobRequest(BaseModel):
    month: str = Field(default="2025-01", pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")
    reducers: int = Field(default=2, ge=1, le=8)
    combiner: bool = True


@app.post("/api/jobs", status_code=202)
def submit(payload: JobRequest, request: Request):
    origin = request.headers.get("origin")
    if origin and origin not in ("http://127.0.0.1:8765", "http://localhost:8765"):
        raise HTTPException(403, "Cross-origin job submissions are disabled")
    if not (DATA / "input" / payload.month / "manifest.json").exists():
        raise HTTPException(422, "该月份尚未导入。")
    if not job_lock.acquire(blocking=False):
        raise HTTPException(409, "已有任务正在执行。")
    job_state.clear()
    job_state.update(status="RUNNING")
    def execute():
        try:
            job_state.update(run_job(payload.month, payload.reducers, payload.combiner))
        except Exception as exc:  # noqa: BLE001 - background job boundary must retain the error for polling
            job_state.update(status="FAILED", error=str(exc))
        finally:
            job_lock.release()
    executor.submit(execute)
    return {"status": "RUNNING"}


@app.get("/api/evidence")
def evidence():
    reports = {}
    for name in ("verification", "experiments"):
        path = ROOT / "evidence" / f"{name}.json"
        if path.exists():
            reports[name] = read_json(path)
    return reports


@app.get("/api/health")
def health():
    return {"status": "ok", "has_results": (RESULTS / "latest.json").exists()}
