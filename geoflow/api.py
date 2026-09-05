import csv
import io
import json
import subprocess
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
from .runner import run_job, script_command


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
    threading.Thread(target=_build_live_index, daemon=True).start()
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


def latest(month: str | None = None):
    path = RESULTS / f"{month}.json" if month else RESULTS / "latest.json"
    if not path.exists():
        raise HTTPException(404, "还没有该月份的分析，请先导入数据并运行 Hadoop 作业。")
    return read_json(path)


@app.get("/api/zones")
def zones():
    path = DATA / "zones.geojson"
    if not path.exists():
        raise HTTPException(404, "请先执行数据导入。")
    return FileResponse(path, media_type="application/geo+json")


def analysis_data(hour, borough, month=None):
    features = read_json(DATA / "zones.geojson")["features"]
    info = {x["properties"]["id"]: x["properties"] for x in features}
    if borough and borough not in {v["borough"] for v in info.values()}:
        raise HTTPException(422, "Unknown borough")
    return summarize(latest(month), info, hour, borough)


@app.get("/api/analysis")
def analysis(hour: int | None = Query(None, ge=0, le=23), borough: str | None = None,
             month: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")):
    return analysis_data(hour, borough, month)


@app.get("/api/export")
def export(hour: int | None = Query(None, ge=0, le=23), borough: str | None = None,
           month: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")):
    data = analysis_data(hour, borough, month)
    out = io.StringIO()
    fields = ["id", "name", "borough", "trips", "avg_distance_km", "avg_minutes", "avg_amount"]
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data["zones"])
    return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="geoflow-zones.csv"'})


WORKER_PORTS = {"19866": "worker1", "19876": "worker2", "18041": "worker1", "18051": "worker2"}


@app.get("/api/cluster")
def cluster():
    result = {"online": False, "physical_hosts": 1, "mode": "WSL 单机多节点",
              "nodes": [], "datanodes": [], "apps": [], "action": cluster_action}
    with httpx.Client(timeout=2, trust_env=False) as client:
        try:
            response = client.get("http://127.0.0.1:18088/ws/v1/cluster/metrics")
            response.raise_for_status()
            result["yarn"] = response.json()["clusterMetrics"]
            response = client.get("http://127.0.0.1:18088/ws/v1/cluster/nodes")
            response.raise_for_status()
            result["nodes"] = [{**n, "worker": WORKER_PORTS.get(str(n.get("id", "")).rsplit(":", 1)[-1], "?")}
                               for n in (response.json().get("nodes") or {}).get("node", [])]
            result["online"] = result["yarn"].get("activeNodes", 0) > 0
            response = client.get("http://127.0.0.1:18088/ws/v1/cluster/apps",
                                  params={"states": "RUNNING,ACCEPTED,SUBMITTED"})
            response.raise_for_status()
            apps = (response.json().get("apps") or {}).get("app", []) or []
            result["apps"] = sorted(apps, key=lambda a: a.get("startTime", 0))[-8:]
        except (httpx.HTTPError, KeyError, ValueError):
            result["yarn_error"] = "YARN 不可达或未启动"
        try:
            response = client.get("http://127.0.0.1:19870/jmx",
                                  params={"qry": "Hadoop:service=NameNode,name=FSNamesystemState"})
            response.raise_for_status()
            result["hdfs"] = response.json()["beans"][0]
            response = client.get("http://127.0.0.1:19870/jmx",
                                  params={"qry": "Hadoop:service=NameNode,name=NameNodeInfo"})
            response.raise_for_status()
            live = json.loads(response.json()["beans"][0].get("LiveNodes") or "{}")
            result["datanodes"] = [{
                "worker": WORKER_PORTS.get(str(info.get("name") or key).rsplit(":", 1)[-1], key),
                "host": (info.get("name") or key).split(":")[0],
                "state": info.get("adminState", "NORMAL"),
                "capacity": info.get("capacity", 0),
                "used": info.get("used", 0),
                "remaining": info.get("remaining", 0),
                "last_contact": info.get("lastContact", -1),
            } for key, info in live.items()]
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            result["hdfs_error"] = "NameNode 不可达或未启动"
    return result


cluster_action = {"action": None, "status": "IDLE", "detail": "",
                  "started_at": None, "finished_at": None}
_action_lock = threading.Lock()
cluster_executor = ThreadPoolExecutor(max_workers=1)


class ClusterAction(BaseModel):
    action: str = Field(pattern="^(start|stop|start-node|stop-node)$")
    node: str | None = Field(None, pattern="^worker[12]$")


def _run_cluster_action(action: str, node: str | None):
    args = (action, node) if node else (action,)
    try:
        proc = subprocess.run(script_command("hadoop.sh", *args), capture_output=True,
                              text=True, cwd=ROOT, timeout=420, check=False)
        ok = proc.returncode == 0
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-12:])
        cluster_action.update(status="SUCCEEDED" if ok else "FAILED",
                              finished_at=datetime.now(UTC).isoformat(),
                              detail=tail.strip()[-1200:])
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        cluster_action.update(status="FAILED", finished_at=datetime.now(UTC).isoformat(),
                              detail=str(exc))


@app.post("/api/cluster/action")
def cluster_action_endpoint(payload: ClusterAction):
    if payload.action in ("start-node", "stop-node") and not payload.node:
        raise HTTPException(422, "节点操作需要指定 worker1 或 worker2")
    with _action_lock:
        if cluster_action["status"] == "RUNNING":
            raise HTTPException(409, "已有集群指令在执行中，请等待完成")
        cluster_executor.submit(_run_cluster_action, payload.action, payload.node)
        cluster_action.update(action=payload.action + (" " + payload.node if payload.node else ""),
                              status="RUNNING", detail="",
                              started_at=datetime.now(UTC).isoformat(), finished_at=None)
    return {"accepted": True, "action": cluster_action["action"]}


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
    job_state.update(status="RUNNING", started_at=datetime.now(UTC).isoformat())
    def execute():
        try:
            job_state.update(run_job(payload.month, payload.reducers, payload.combiner))
        except Exception as exc:  # noqa: BLE001 - background job boundary must retain the error for polling
            job_state.update(status="FAILED", error=str(exc), finished_at=datetime.now(UTC).isoformat())
        finally:
            job_lock.release()
    executor.submit(execute)
    return {"status": "RUNNING"}


@app.get("/api/year")
def year():
    path = RESULTS / "year.json"
    if not path.exists():
        raise HTTPException(404, "年度合并尚未生成，请先完成全年作业并运行 merge_year.py。")
    return FileResponse(path, media_type="application/json", headers={"Cache-Control": "no-store"})


@app.get("/api/od")
def od():
    path = RESULTS / "od_year.json"
    if not path.exists():
        raise HTTPException(404, "OD 聚合尚未生成。")
    return FileResponse(path, media_type="application/json", headers={"Cache-Control": "no-store"})


@app.get("/api/forecast")
def forecast():
    path = RESULTS / "forecast.json"
    if not path.exists():
        raise HTTPException(404, "预测尚未生成，请运行 forecast.py。")
    return FileResponse(path, media_type="application/json", headers={"Cache-Control": "no-store"})


@app.get("/api/forecast-curve")
def forecast_curve():
    path = RESULTS / "forecast_curve.json"
    if not path.exists():
        raise HTTPException(404, "预测曲线尚未生成。")
    return FileResponse(path, media_type="application/json", headers={"Cache-Control": "no-store"})


@app.get("/api/months")
def months():
    records = []
    for path in sorted((DATA / "input").glob("20*")):
        if not (path / "manifest.json").exists():
            continue
        manifest = read_json(path / "manifest.json")
        records.append({"month": path.name, "rows": manifest["rows"],
                        "source_rows": manifest["source_rows"],
                        "created_at": manifest.get("created_at")})
    return {"months": records}


@app.get("/api/dem")
def dem():
    path = RESULTS / "dem_grid.json"
    if not path.exists():
        raise HTTPException(404, "DEM 尚未生成，请运行 fetch_dem.py。")
    return FileResponse(path, media_type="application/json", headers={"Cache-Control": "no-store"})


@app.get("/api/evidence")
def evidence():
    reports = {}
    for name in ("verification", "experiments", "perf", "spark", "fault_demo", "year", "forecast"):
        path = ROOT / "evidence" / f"{name}.json"
        if path.exists():
            reports[name] = read_json(path)
    return reports


@app.get("/api/health")
def health():
    return {"status": "ok", "has_results": (RESULTS / "latest.json").exists()}


# ---- live replay: December trips re-streamed minute by minute -----------------
_LIVE = {"index": None, "building": False}
_live_lock = threading.Lock()
LIVE_MINUTES = 31 * 1440  # December: 31 days of minute-of-day slots


def _build_live_index():
    """Index December pickups by minute-of-day once; cached pickle afterwards."""
    with _live_lock:
        if _LIVE["index"] is not None or _LIVE["building"]:
            return
        _LIVE["building"] = True
    try:
        import pickle

        import pandas as pd
        cache = DATA / "live_dec.pkl"
        if cache.exists():
            with cache.open("rb") as fh:
                _LIVE["index"] = pickle.load(fh)
            return
        files = sorted((DATA / "input" / "2025-12").glob("part-*.csv"))
        frames = [pd.read_csv(f, header=None, usecols=[0, 2], names=["start", "pu"])
                  for f in files]
        df = pd.concat(frames, ignore_index=True)
        starts = pd.to_datetime(df["start"])
        # true timeline slot: (day of month - 1) * 1440 + minute of day, so the
        # replay follows the real month (including the Dec 31 New Year spike)
        slot = ((starts.dt.day - 1) * 1440 + starts.dt.hour * 60 + starts.dt.minute).astype("int32")
        counts = df.assign(slot=slot).groupby(["slot", "pu"]).size()
        index = {}
        for (m, z), c in counts.items():
            index.setdefault(int(m), {})[str(int(z))] = int(c)
        assert len(index) > 40000, "live index unexpectedly sparse"
        with cache.open("wb") as fh:
            pickle.dump(index, fh, protocol=pickle.HIGHEST_PROTOCOL)
        _LIVE["index"] = index
    except Exception as exc:  # noqa: BLE001 - surfaced to the live view
        _LIVE["error"] = str(exc)[:300]
    finally:
        _LIVE["building"] = False


@app.get("/api/live/meta")
def live_meta():
    built = _LIVE["index"] is not None
    peak = max((sum(v.values()) for v in _LIVE["index"].values()), default=0) if built else 0
    return {"built": built, "building": _LIVE["building"], "error": _LIVE.get("error"),
            "minutes": LIVE_MINUTES, "peak_minute_total": peak,
            "source": "2025-12 全量出行按原始时间戳回放"}


@app.get("/api/live/frame")
def live_frame(m: int, span: int = Query(1, ge=1, le=60)):
    if _LIVE["index"] is None:
        raise HTTPException(503, "实时索引构建中，请稍候（首次约 1 分钟）")
    counts = {}
    base = m % LIVE_MINUTES
    for step in range(span):
        for z, c in _LIVE["index"].get((base + step) % LIVE_MINUTES, {}).items():
            counts[z] = counts.get(z, 0) + c
    return {"m": base, "span": span, "total": sum(counts.values()), "counts": counts}
