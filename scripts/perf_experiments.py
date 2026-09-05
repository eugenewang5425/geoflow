"""Scalability experiments for the report.

1. Map-task sweep: re-shard the month into K balanced files (14/36/72/144) and
   run the identical streaming job on each. Map tasks == number of files here —
   FileInputFormat ignores mapreduce.job.maps / split.maxsize for files smaller
   than the 16MB block, so the physical layout is the only honest knob.
2. Weak scaling: reuse the 12 monthly pipeline runs (identical config) to plot
   data volume vs runtime.

Writes evidence/perf.json.
"""
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geoflow.config import DATA
from geoflow.io import atomic_json, read_json
from geoflow.runner import linux_path

MONTH = "2025-01"  # smallest month keeps the sweep quick
SWEEP = [14, 36, 72, 144]  # file count == map task count (each file < 16MB block)


def prep_reshard(k):
    """Concatenate the month's shards into k balanced part files, cut at line boundaries."""
    src = DATA / "input" / MONTH
    manifest = read_json(src / "manifest.json")
    shards = [s["name"] for s in manifest["shards"]]
    outdir = DATA / "exp" / str(k)
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("part-*.csv"):
        old.unlink()
    total = sum((src / n).stat().st_size for n in shards)
    target = max(1, total // k)
    idx, size = 0, 0
    fh = (outdir / f"part-{idx:05d}.csv").open("wb")
    newline = b"\n"
    for name in shards:
        blob = (src / name).read_bytes()
        pos = 0
        while pos < len(blob):
            want = max(target - size, 4096)
            chunk = blob[pos:pos + want]
            nl = chunk.rfind(newline)
            take = (nl + 1) if nl != -1 else len(chunk)
            if pos + take >= len(blob):
                take = len(blob) - pos
            fh.write(blob[pos:pos + take])
            pos += take
            size += take
            if size >= target and idx < k - 1 and pos < len(blob):
                fh.close()
                idx += 1
                size = 0
                fh = (outdir / f"part-{idx:05d}.csv").open("wb")
    fh.close()
    return outdir


def sh(*args, timeout=1200):
    # Popen + file redirection: capture_output pipes can hang forever when a
    # wsl.exe grandchild keeps the pipe handle open after bash exits.
    log_path = DATA / "runs" / "sweep-driver.log"
    with log_path.open("w", encoding="utf-8") as lf:
        proc = subprocess.Popen(["wsl", "-d", "Ubuntu-24.04", "--exec", "bash",
                                 linux_path(ROOT / "scripts" / args[0]), *map(str, args[1:])],
                                stdout=lf, stderr=subprocess.STDOUT, cwd=ROOT)
        code = proc.wait(timeout=timeout)
    return code, log_path.read_text(encoding="utf-8", errors="replace")


def task_counts(run_id):
    text = (DATA / "runs" / run_id / "hadoop.log").read_text(encoding="utf-8", errors="replace")
    maps = re.search(r"number of splits:(\d+)", text)
    return int(maps.group(1)) if maps else None


def map_sweep():
    sweep = []
    for k in SWEEP:
        print(f"[perf] map sweep K={k} ...", flush=True)
        outdir = prep_reshard(k)
        print(f"[perf] re-sharded into {len(list(outdir.glob('part-*.csv')))} files", flush=True)
        run_id = f"sweep{k}-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        (DATA / "runs" / run_id).mkdir(parents=True, exist_ok=True)
        code, out = sh("map_sweep.sh", k, run_id, MONTH)
        job_seconds = None
        m = re.search(r"JOB_SECONDS=([\d.]+)", out)
        if m:
            job_seconds = round(float(m.group(1)), 1)
        row = {"target_maps": k, "map_tasks": task_counts(run_id) if code == 0 else None,
               "status": "SUCCEEDED" if code == 0 else "FAILED",
               "job_seconds": job_seconds,
               "error": None if code == 0 else out[-400:]}
        sweep.append(row)
        print(f"[perf] {row}", flush=True)
    return sweep


def scaling_from_history():
    scaling = []
    for path in sorted((DATA / "runs").glob("*/run.json")):
        r = read_json(path)
        if not (r.get("status") == "SUCCEEDED" and r.get("combiner") and r.get("reducers") == 2
                and not r.get("fail_first") and r.get("month") and r.get("elapsed_seconds")):
            continue
        manifest = read_json(DATA / "input" / r["month"] / "manifest.json")
        scaling.append({"month": r["month"], "rows": manifest.get("rows"),
                        "started_at": r.get("started_at"),
                        "elapsed_seconds": r["elapsed_seconds"]})
    scaling.sort(key=lambda x: (x["month"], x["started_at"] or ""))
    first = {}
    for row in scaling:  # earliest run per month = the original pipeline run
        first.setdefault(row["month"], row)
    rows = sorted(first.values(), key=lambda x: x["month"])
    for row in rows:
        row.pop("started_at", None)
    return rows


def main():
    sweep = map_sweep()
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": "Hadoop 3.4.2 / YARN / Streaming",
        "topology": "WSL2, one physical host, two DataNodes and two NodeManagers",
        "map_sweep_month": MONTH,
        "map_sweep": sweep,
        "map_sweep_note": "K 个平衡重分片文件（每个 < 16MB 块）→ Map 任务数 = 文件数；"
                          "FileInputFormat 对小于块大小的文件不生效的 mapreduce.job.maps / "
                          "split.maxsize 提示均无法改变任务数，故用物理布局控制。",
        "scaling": scaling_from_history(),
        "scaling_note": "12 个月独立作业，reducers=2、combiner 开启；耗时取原始管线运行记录",
    }
    atomic_json(ROOT / "evidence" / "perf.json", report)
    print("[perf] written evidence/perf.json", flush=True)


if __name__ == "__main__":
    main()
