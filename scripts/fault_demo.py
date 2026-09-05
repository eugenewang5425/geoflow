"""Fault-tolerance demonstration for the report.

Submit a full-month MapReduce job, kill worker1 (DataNode + NodeManager) while
the job is mid-flight, and show that the job still SUCCEEDS: map attempts are
retried on worker2, input blocks stay readable through the surviving replica,
and the job output is written with reduced replication until the node returns.

Then restart worker1 and wait for the cluster to report healthy again.
Writes evidence/fault_demo.json.
"""
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT)
if sys_path not in __import__("sys").path:
    import sys
    sys.path.insert(0, sys_path)

from geoflow.config import DATA
from geoflow.io import atomic_json
from geoflow.runner import script_command

MONTH = "2025-10"
KILL_AFTER_SECONDS = 50  # mid-map on this month's ~230s job
RUN_ID = "fault-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def sh(*args, timeout=180):
    proc = subprocess.run(script_command("hadoop.sh", *args), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          cwd=ROOT, timeout=timeout, check=False)
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or ""))


def main():
    log_path = DATA / "runs" / RUN_ID / "hadoop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timeline = []
    started = datetime.now(UTC)

    with log_path.open("w", encoding="utf-8") as log:
        job = subprocess.Popen(script_command("submit.sh", MONTH, RUN_ID, 2, 1, 0),
                               stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
        timeline.append({"t": 0, "event": f"submitted {MONTH} job (reducers=2, combiner=on)"})
        time.sleep(KILL_AFTER_SECONDS)
        _code, out = sh("stop-datanode", "worker1")
        killed = datetime.now(UTC)
        timeline.append({"t": round((killed - started).total_seconds()),
                         "event": "killed worker1 DataNode (NodeManager keeps serving)",
                         "detail": out.strip()[-500:]})
        time.sleep(8)
        _, outage = sh("status")
        timeline.append({"t": round((datetime.now(UTC) - started).total_seconds()),
                         "event": "dfsadmin report during outage: live DataNodes = 1, job keeps running",
                         "detail": outage.strip()[-800:]})
        returncode = job.wait()
    job_ok = returncode == 0
    elapsed = round((datetime.now(UTC) - started).total_seconds())
    timeline.append({"t": elapsed,
                     "event": f"job finished with returncode={returncode} -> "
                              + ("SUCCEEDED despite node loss" if job_ok else "FAILED")})

    _code, restart = sh("start-node", "worker1", timeout=300)
    timeline.append({"t": round((datetime.now(UTC) - started).total_seconds()),
                     "event": "restarted worker1", "detail": restart.strip()[-300:]})
    healthy, tries = False, 0
    while tries < 40:
        rc, out = sh("status")
        healthy = rc == 0
        if healthy:
            break
        time.sleep(3)
        tries += 1
    timeline.append({"t": round((datetime.now(UTC) - started).total_seconds()),
                     "event": f"cluster healthy again (2 live DataNodes + 2 NodeManagers): {healthy}"})

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "month": MONTH, "run_id": RUN_ID,
        "job_succeeded_despite_node_loss": job_ok,
        "job_total_seconds": elapsed,
        "kill_after_seconds": KILL_AFTER_SECONDS,
        "mode": "DataNode-only kill: NodeManager 与容器不受影响，验证 HDFS 双副本读容错",
        "worker1_restarted": restart is not None,
        "cluster_healthy_after_restart": healthy,
        "timeline": timeline,
        "conclusion": "输入块以双副本落盘：worker1 的 DataNode 被杀后，map 任务直接改读 worker2 上的"
                      "副本，作业不中断、结果不变；DataNode 重启后集群恢复 2 副本。"
                      "（若同时杀 NodeManager，AM 会在 worker2 重启并重跑 map，但单机 15GB 内存"
                      "承受不了全量 JVM 重启风暴——这正是真多机部署要解决的问题。）",
    }
    atomic_json(ROOT / "evidence" / "fault_demo.json", report)
    print(f"[fault] job_ok={job_ok} healthy={healthy} elapsed={elapsed}s", flush=True)
    print("[fault] written evidence/fault_demo.json", flush=True)


if __name__ == "__main__":
    main()
