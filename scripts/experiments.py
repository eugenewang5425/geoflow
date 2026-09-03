"""Run the GeoFlow experiment matrix and capture exact-match evidence.

Matrix: reducers {1,2,4} x combiner {on,off}, plus one task-failure recovery run
(fail_first=1 forces the first attempt of mapper 000000 to fail, exercising
YARN retry). Every run is compared key-by-key against an independent sequential
aggregation computed once for the month.
"""
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geoflow.config import DATA, MONTH
from geoflow.io import atomic_json, read_json
from geoflow.results import parse_output
from geoflow.runner import run_job
from jobs.mapper import parse_trip


def reference_totals(month):
    """Independent sequential aggregation with identical validation rules."""
    manifest = read_json(DATA / "input" / month / "manifest.json")
    totals = defaultdict(lambda: [0, 0, 0, 0])
    count = 0
    for shard in manifest["shards"]:
        with (DATA / "input" / month / shard["name"]).open(encoding="utf-8", newline="") as stream:
            for row in csv.reader(stream):
                count += 1
                trip, reason = parse_trip(row, month)
                if reason:
                    totals[f"Q|{reason}"][0] += 1
                    continue
                for key in (f"Z|{trip['zone']:03d}|{trip['hour']:02d}", f"D|{trip['day']}",
                            f"O|{trip['zone']:03d}|{trip['dest']:03d}"):
                    v = totals[key]
                    v[0] += 1
                    v[1] += trip["distance_milli_miles"]
                    v[2] += trip["seconds"]
                    v[3] += trip["cents"]
    return count, totals


def main():
    combos = [{"reducers": r, "combiner": c} for r in (1, 2, 4) for c in (True, False)]
    combos.append({"reducers": 2, "combiner": True, "fail_first": True})
    started = time.perf_counter()
    count, ref = reference_totals(MONTH)
    reference_seconds = round(time.perf_counter() - started, 3)
    runs = []
    for combo in combos:
        label = f"reducers={combo['reducers']} combiner={combo['combiner']} fail_first={combo.get('fail_first', False)}"
        print(f"[experiments] {label} ...", flush=True)
        try:
            meta = run_job(MONTH, combo["reducers"], combo["combiner"],
                           combo.get("fail_first", False))
            actual = parse_output(DATA / "runs" / meta["run_id"] / "output.tsv")
            runs.append({
                **combo, "run_id": meta["run_id"], "status": meta["status"],
                "job_id": meta.get("job_id"), "application_id": meta.get("application_id"),
                "elapsed_seconds": meta.get("elapsed_seconds"),
                "job_elapsed_seconds": meta.get("job_elapsed_seconds"),
                "exact_match": actual == ref,
                "compared_keys": len(ref),
                "input_rows": count,
            })
            print(f"[experiments] {label}: OK exact_match={runs[-1]['exact_match']}", flush=True)
        except Exception as exc:  # noqa: BLE001 - record failures in the experiment report
            runs.append({**combo, "run_id": None, "status": "FAILED", "error": str(exc)[:400]})
            print(f"[experiments] {label}: FAILED {exc}", flush=True)
    report = {
        "engine": "Hadoop 3.4.2 / YARN / Streaming",
        "topology": "WSL2, one physical host, two DataNodes and two NodeManagers",
        "month": MONTH, "input_rows": count,
        "reference_seconds": reference_seconds,
        "runs": runs, "generated_at": datetime.now(UTC).isoformat(),
        "scope": ("Same shards for every run; per-run output compared key-by-key with the "
                  "independent sequential aggregation; all sums are integer fixed-point."),
    }
    atomic_json(ROOT / "evidence" / "experiments.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
