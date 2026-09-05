import os
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime

import httpx

from .config import DATA, ROOT
from .io import atomic_json
from .results import publish


def linux_path(path):
    if os.name == "nt":
        resolved = path.resolve()
        drive = resolved.drive[0].lower()
        return f"/mnt/{drive}/" + "/".join(resolved.parts[1:])
    return str(path)


def script_command(script, *args):
    path = ROOT / "scripts" / script
    prefix = ["wsl", "-d", "Ubuntu-24.04", "--exec"] if os.name == "nt" else []
    return prefix + ["bash", linux_path(path), *map(str, args)]


def run_job(month="2025-01", reducers=2, combiner=True, fail_first=False, run_id=None, map_tasks=0):
    if DATA.resolve() != (ROOT / "data").resolve():
        raise ValueError("WSL runner currently requires the project data/ directory")
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    folder = DATA / "runs" / run_id
    folder.mkdir(parents=True, exist_ok=False)
    meta = {"run_id": run_id, "month": month, "reducers": reducers, "combiner": combiner,
            "fail_first": fail_first, "engine": "Hadoop 3.4.2 / YARN / Streaming",
            "topology": "WSL2, one physical host, two DataNodes and two NodeManagers",
            "status": "RUNNING", "started_at": datetime.now(UTC).isoformat()}
    atomic_json(folder / "run.json", meta)
    started = time.perf_counter()
    try:
        command = script_command("submit.sh", month, run_id, reducers, int(combiner), int(fail_first))
        with (folder / "driver.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, cwd=ROOT, timeout=1800)
        meta["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        output = (folder / "hadoop.log").read_text(encoding="utf-8", errors="replace")
        jobs = re.findall(r"job_\d+_\d+", output)
        apps = re.findall(r"application_\d+_\d+", output)
        meta["job_id"] = jobs[-1] if jobs else None
        meta["application_id"] = apps[-1] if apps else None
        meta["status"] = "SUCCEEDED"
        # History service may publish a few seconds after job completion.
        if meta["job_id"]:
            for _ in range(8):
                try:
                    base = f"http://127.0.0.1:19888/ws/v1/history/mapreduce/jobs/{meta['job_id']}"
                    with httpx.Client(timeout=5, trust_env=False) as client:
                        job = client.get(base)
                        job.raise_for_status()
                        counters = client.get(base + "/counters")
                        counters.raise_for_status()
                        tasks = client.get(base + "/tasks")
                        tasks.raise_for_status()
                    atomic_json(folder / "history-job.json", job.json())
                    atomic_json(folder / "history-counters.json", counters.json())
                    atomic_json(folder / "history-tasks.json", tasks.json())
                    jbody = job.json()["job"]
                    elapsed_ms = jbody.get("elapsedTime") or (jbody.get("finishTime", 0) - jbody.get("startTime", 0))
                    meta["job_elapsed_seconds"] = elapsed_ms / 1000
                    meta["history_saved"] = True
                    break
                except (httpx.HTTPError, KeyError):
                    time.sleep(2)
        result = publish(run_id, meta)
        atomic_json(folder / "run.json", meta)
        return {"run_id": run_id, "valid_rows": result["valid_rows"], "rejected_rows": result["rejected_rows"],
                **meta}
    except Exception as exc:
        meta.update(status="FAILED", error=str(exc), elapsed_seconds=round(time.perf_counter() - started, 3))
        atomic_json(folder / "run.json", meta)
        raise
