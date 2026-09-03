"""Independent in-process aggregation, checked against every Hadoop output key."""
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from geoflow.io import atomic_json, read_json
from geoflow.results import parse_output
from jobs.mapper import parse_trip


def main():
    result = read_json(ROOT / "data/results/latest.json")
    month = result["dataset"]["month"]
    folder = ROOT / "data/input" / month
    manifest = read_json(folder / "manifest.json")
    totals = defaultdict(lambda: [0, 0, 0, 0])
    count = 0
    started = time.perf_counter()
    # Same explicit validation policy; independent grouping implementation (no reducer/combiner reuse).
    for shard in manifest["shards"]:
        with (folder / shard["name"]).open(encoding="utf-8", newline="") as stream:
            for row in csv.reader(stream):
                count += 1
                trip, reason = parse_trip(row, month)
                if reason:
                    totals[f"Q|{reason}"][0] += 1
                    continue
                keys = [f"Z|{trip['zone']:03d}|{trip['hour']:02d}", f"D|{trip['day']}",
                        f"O|{trip['zone']:03d}|{trip['dest']:03d}",
                        f"T|{trip['day']}|{trip['zone']:03d}|{trip['hour']:02d}"]
                for key in keys:
                    v = totals[key]
                    v[0] += 1
                    v[1] += trip["distance_milli_miles"]
                    v[2] += trip["seconds"]
                    v[3] += trip["cents"]
    actual = parse_output(ROOT / "data/runs" / result["run_id"] / "output.tsv")
    report = {"run_id": result["run_id"], "input_rows": count, "compared_keys": len(totals),
              "exact_match": dict(totals) == actual,
              "reference_seconds": round(time.perf_counter() - started, 3),
              "hadoop_end_to_end_seconds": result["metadata"]["elapsed_seconds"],
              "hadoop_job_seconds": result["metadata"].get("job_elapsed_seconds"),
              "scope": "Identical validation rules, independent sequential aggregation; all integer sums exact"}
    atomic_json(ROOT / "evidence/verification.json", report)
    print(json.dumps(report, indent=2))
    if not report["exact_match"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
