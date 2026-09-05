"""Engine comparison: Hadoop MapReduce Streaming vs Apache Spark (local[2]).

Same input (HDFS month shards), same validation rules, same four-key additive
aggregation. MR timings come from the original monthly pipeline run record;
Spark runs spark_od.py twice (cold JVM + warm) and reports wall/compute times.
Writes evidence/spark.json.
"""
import hashlib
import re
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geoflow.config import DATA, RESULTS
from geoflow.io import atomic_json, read_json
from geoflow.runner import linux_path

MONTH = "2025-01"
SPARK_VERSION = "3.5.1"
TGZ = ROOT / ".runtime" / "downloads" / f"spark-{SPARK_VERSION}-bin-hadoop3.tgz"
URLS = [
    f"https://archive.apache.org/dist/spark/spark-{SPARK_VERSION}/spark-{SPARK_VERSION}-bin-hadoop3.tgz",
    f"https://dlcdn.apache.org/spark/spark-{SPARK_VERSION}/spark-{SPARK_VERSION}-bin-hadoop3.tgz",
]


def ensure_tarball():
    if TGZ.exists() and TGZ.stat().st_size > 100_000_000:
        print("[spark] tarball present", flush=True)
        return
    TGZ.parent.mkdir(parents=True, exist_ok=True)
    for url in URLS:
        try:
            print(f"[spark] downloading {url} ...", flush=True)
            with httpx.stream("GET", url, timeout=60, follow_redirects=True) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                done = 0
                with TGZ.open("wb") as fh:
                    for chunk in resp.iter_bytes(1 << 20):
                        fh.write(chunk)
                        done += len(chunk)
                        if total and done % (50 << 20) < (1 << 20):
                            print(f"[spark] {done >> 20}/{total >> 20} MB", flush=True)
            print(f"[spark] downloaded {done >> 20} MB", flush=True)
            return
        except httpx.HTTPError as exc:
            print(f"[spark] {url} failed: {exc}", flush=True)
    raise RuntimeError("no mirror reachable")


def ensure_extract():
    target = ROOT / ".runtime" / f"spark-{SPARK_VERSION}-bin-hadoop3"
    if (target / "bin" / "spark-submit").exists():
        return target
    print("[spark] extracting ...", flush=True)
    with tarfile.open(TGZ, "r:gz") as tar:
        tar.extractall(target.parent)
    return target


def mr_baseline():
    best = None
    for path in sorted((DATA / "runs").glob("*/run.json")):
        r = read_json(path)
        if (r.get("status") == "SUCCEEDED" and r.get("month") == MONTH
                and r.get("reducers") == 2 and r.get("combiner") and not r.get("fail_first")
                and r.get("started_at") and r.get("elapsed_seconds")
                and (best is None or r["started_at"] < best["started_at"])):
            best = r
    if best is None:
        raise RuntimeError("no MR baseline run found for " + MONTH)
    return {"job_elapsed_seconds": best.get("job_elapsed_seconds"),
            "total_elapsed_seconds": best["elapsed_seconds"],
            "run_id": best["run_id"]}


def hdfs_glob():
    manifest_bytes = (DATA / "input" / MONTH / "manifest.json").read_bytes()
    fingerprint = hashlib.sha256(manifest_bytes).hexdigest()
    return f"hdfs://127.0.0.1:19000/geoflow/raw/{MONTH}/{fingerprint}/part-*.csv"


def run_spark(glob):
    started = time.perf_counter()
    proc = subprocess.run(["wsl", "-d", "Ubuntu-24.04", "--exec", "bash",
                           linux_path(ROOT / "scripts" / "spark_run.sh"), MONTH, glob],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=ROOT, timeout=900, check=False)
    wall = round(time.perf_counter() - started, 3)
    keys = re.search(r"RESULT_KEYS\t(\d+)", proc.stdout)
    rows = re.search(r"VALID_ROWS\t(\d+)", proc.stdout)
    compute = re.search(r"COMPUTE_SECONDS\t([\d.]+)", proc.stdout)
    if proc.returncode != 0:
        raise RuntimeError("spark failed: " + (proc.stdout + proc.stderr)[-1200:])
    return {"wall_seconds": wall,
            "compute_seconds": float(compute.group(1)) if compute else None,
            "result_keys": int(keys.group(1)) if keys else None,
            "valid_rows": int(rows.group(1)) if rows else None}


def main():
    ensure_tarball()
    ensure_extract()
    baseline = mr_baseline()
    manifest = read_json(DATA / "input" / MONTH / "manifest.json")
    glob = hdfs_glob()
    cold = run_spark(glob)
    warm = run_spark(glob)
    mr_job = baseline["job_elapsed_seconds"] or baseline["total_elapsed_seconds"]
    results_path = RESULTS / f"{MONTH}.json"
    mr_valid_rows = read_json(results_path).get("valid_rows") if results_path.exists() else None
    consistent = (mr_valid_rows is not None and warm.get("valid_rows") == mr_valid_rows)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "month": MONTH,
        "input_rows": manifest.get("rows"),
        "spark_master": "local[2] (与 MR 相同的 2 个 reduce 并行度口径)",
        "spark_version": SPARK_VERSION,
        "mapreduce": {"engine": "Hadoop Streaming (python mapper/reducer, combiner on)",
                      "job_elapsed_seconds": baseline["job_elapsed_seconds"],
                      "total_elapsed_seconds": baseline["total_elapsed_seconds"],
                      "run_id": baseline["run_id"]},
        "spark": {"engine": "PySpark RDD aggregateByKey (map-side combine)",
                  "cold_wall_seconds": cold["wall_seconds"],
                  "warm_wall_seconds": warm["wall_seconds"],
                  "warm_compute_seconds": warm["compute_seconds"],
                  "result_keys": warm["result_keys"],
                  "valid_rows": warm["valid_rows"]},
        "mr_results_valid_rows": mr_valid_rows,
        "consistent_with_mapreduce_output": consistent,
        "speedup_job_vs_warm": round(mr_job / warm["wall_seconds"], 2) if warm["wall_seconds"] else None,
        "note": "MR 基线为原始管线运行记录；Spark 冷启动含 JVM/Context 引导，"
                "与 MR 的 ApplicationMaster + JVM 任务启动开销同一量级，故对比墙钟时间。",
    }
    atomic_json(ROOT / "evidence" / "spark.json", report)
    print(f"[spark] MR job={mr_job}s | spark warm wall={warm['wall_seconds']}s", flush=True)
    print("[spark] written evidence/spark.json", flush=True)


if __name__ == "__main__":
    main()
