"""Merge per-month MapReduce results into year-level artifacts.

Reads the latest SUCCEEDED run of each month, then precomputes every aggregate the
dashboard needs (month x hour heatmap, weekday x hour heatmap, zone-month matrix,
OD flows, airport flows, monthly day curves) into portable JSON files.
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geoflow.config import DATA, RESULTS
from geoflow.io import atomic_json, read_json

AIRPORT_NAMES = ("jfk airport", "laguardia airport", "newark airport")


def latest_run(month):
    best = None
    for path in sorted((DATA / "runs").glob("*/run.json"), reverse=True):
        meta = read_json(path)
        if meta.get("month") == month and meta.get("status") == "SUCCEEDED":
            best = path.parent
            break
    return best


def main():
    zones = read_json(DATA / "zones.geojson")["features"]
    zone_info = {f["properties"]["id"]: f["properties"] for f in zones}
    zone_name = {zid: p["name"] for zid, p in zone_info.items()}
    airports = sorted([zid for zid, p in zone_info.items()
                       if any(k in p["name"].lower() for k in AIRPORT_NAMES)])

    months = sorted(p.name for p in sorted((DATA / "input").glob("20*/")) if (p / "manifest.json").exists())
    month_stats = []
    month_hour = [[0] * 24 for _ in months]
    zone_month = defaultdict(dict)
    zone_year = Counter()
    od_year = Counter()
    month_days = {}
    weekday_hour = Counter()  # (weekday, hour) -> trips
    day_series = defaultdict(dict)  # month -> {day: trips}
    quality = {}
    daily_files = []
    used_runs = []

    for month in months:
        run_dir = latest_run(month)
        if run_dir is None:
            month_stats.append({"month": month, "status": "MISSING"})
            continue
        used_runs.append(str(run_dir.name))
        result = read_json(run_dir / "result.json")
        m = result["metadata"]
        trip_total = result["valid_rows"]
        zone_hours = result["zone_hours"]
        z_h = Counter()
        for row in zone_hours:
            z_h[(row["zone"], row["hour"])] += row["values"][0]
            zone_month[row["zone"]][month] = zone_month[row["zone"]].get(month, 0) + row["values"][0]
            zone_year[row["zone"]] += row["values"][0]
            month_hour[months.index(month)][row["hour"]] += row["values"][0]
        for dayrec in result["days"]:
            month_days.setdefault(month, {})[dayrec["day"]] = dayrec["values"][0]
        for odrec in result["od"]:
            od_year[(odrec["origin"], odrec["destination"])] += odrec["values"][0]

        dist_km = sum(r["values"][1] for r in zone_hours) / 1000 * 1.609344
        amt = sum(r["values"][3] for r in zone_hours) / 100
        month_stats.append({"month": month, "status": "ok", "run_id": run_dir.name,
                            "trips": trip_total, "rejected": result["rejected_rows"],
                            "distance_km": round(dist_km), "revenue_usd": round(amt),
                            "job_id": m.get("job_id"), "elapsed_seconds": m.get("elapsed_seconds"),
                            "job_elapsed_seconds": m.get("job_elapsed_seconds")})
        quality[month] = {"valid": trip_total, "rejected": result["rejected_rows"],
                          "reasons": result["rejected"]}
        # weekday x hour from the daily dimension
        daily = run_dir / "daily.tsv"
        if daily.exists():
            daily_files.append(str(daily))
        # month day series from days
        for d, v in month_days[month].items():
            day_series[month][d] = v

    # weekday x hour: needs every run's daily.tsv
    for dfile in daily_files:
        d = Path(dfile)
        month = d.parent.name
        for line in d.read_text(encoding="utf-8").splitlines():
            key, vals = line.split("\t", 1)
            _, day, _z, hour = key.split("|")
            cnt = int(vals.split(",")[0])
            wd = date.fromisoformat(day).weekday()
            weekday_hour[(wd, int(hour))] += cnt

    year = {
        "months": months, "stats": month_stats, "quality": quality,
        "month_hour": month_hour,
        "weekday_hour": [[weekday_hour[(w, h)] for h in range(24)] for w in range(7)],
        "zone_month": [[zid, month, zone_month[zid].get(month, 0)] for zid in sorted(zone_month)
                       for month in months],
        "zone_year": [{"id": zid, "trips": zone_year[zid]} for zid in sorted(zone_year)],
        "day_curves": {m: sorted(v.items()) for m, v in day_series.items()},
        "airport_zones": {"ids": airports,
                          "names": {str(zid): zone_name[zid] for zid in airports}},
        "generated_at": datetime.now(UTC).isoformat(),
        "runs": used_runs,
    }
    atomic_json(RESULTS / "year.json", year)

    # OD artifacts (kept separate from year.json to bound its size)
    od_pairs = [(o, de, c) for (o, de), c in od_year.items()]
    od_pairs.sort(key=lambda x: -x[2])
    sankey_edges = []
    seen_dirs = set()
    for o, de, c in od_pairs:
        if o == de:
            continue
        # ECharts sankey requires an acyclic graph: keep the larger direction of
        # each unordered pair, then reject any edge that would close a directed cycle.
        if (de, o) in seen_dirs:
            continue
        edges = [(zone_name[o], zone_name[de])]
        if o > de:
            edges.append((zone_name[de], zone_name[o]))
        ok = True
        for src, dst in edges:
            adj = {}
            for s0, d0, _c in sankey_edges:
                adj.setdefault(s0, []).append(d0)
            stack = [src]
            seen = set()
            while stack and ok:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                for nxt in adj.get(cur, []):
                    if nxt == dst:
                        ok = False
                        break
                    stack.append(nxt)
            if not ok:
                break
        if ok:
            seen_dirs.add((o, de))
            seen_dirs.add((de, o))
            sankey_edges.append((zone_name[o], zone_name[de], c))
            if len(sankey_edges) >= 25:
                break
    airport_rows = []
    for aid in airports:
        inbound = sum(c for (o, de), c in od_year.items() if de == aid)
        outbound = sum(c for (o, de), c in od_year.items() if o == aid)
        airport_rows.append({"id": aid, "name": zone_name[aid], "inbound": inbound,
                             "outbound": outbound})
    atomic_json(RESULTS / "od_year.json", {
        "top_od": [{"origin": o, "destination": de, "trips": c} for o, de, c in od_pairs[:200]],
        "sankey": {"names": list(dict.fromkeys([n for e in sankey_edges for n in e[:2]])),
                   "links": sankey_edges},
        "airports": airport_rows,
        "generated_at": datetime.now(UTC).isoformat(),
    })

    evidence = {"months": months, "total_trips": sum(s.get("trips", 0) for s in month_stats),
                "month_stats": month_stats, "runs": used_runs,
                "od_pair_count": len(od_pairs), "airports": airport_rows,
                "generated_at": datetime.now(UTC).isoformat()}
    atomic_json(ROOT / "evidence" / "year.json", evidence)
    print(json.dumps(evidence, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
