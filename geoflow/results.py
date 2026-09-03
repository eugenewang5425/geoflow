from collections import Counter, defaultdict
from datetime import UTC, datetime

from .config import DATA, RESULTS
from .io import atomic_json, read_json


def parse_output(path):
    rows = {}
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            key, value = line.rstrip("\n").split("\t")
            if key in rows:
                raise ValueError(f"Duplicate reducer key: {key}")
            values = list(map(int, value.split(",")))
            if len(values) != 4:
                raise ValueError("Bad reducer schema")
            rows[key] = values
    return rows


def publish(run_id, metadata):
    path = DATA / "runs" / run_id
    zone_hours, days, od, rejected = [], [], [], {}
    counts = Counter()
    rows = {}
    # Stream the per-(day, zone, hour) dimension into its own file instead of the
    # result JSON: ~195k lines/month keeps metadata small and feeds forecasting.
    with (path / "output.tsv").open(encoding="utf-8") as stream,             (path / "daily.tsv").open("w", encoding="utf-8") as daily_out:
        for line in stream:
            key, value = line.rstrip("\n").split("\t")
            values = list(map(int, value.split(",")))
            if len(values) != 4:
                raise ValueError("Bad reducer schema")
            kind, *parts = key.split("|")
            counts[kind] += values[0]
            if kind == "T":
                daily_out.write(key + "\t" + value + "\n")
                continue
            if key in rows:
                raise ValueError(f"Duplicate reducer key: {key}")
            rows[key] = values
            if kind == "Z":
                zone_hours.append({"zone": int(parts[0]), "hour": int(parts[1]), "values": values})
            elif kind == "D":
                days.append({"day": parts[0], "values": values})
            elif kind == "O":
                od.append({"origin": int(parts[0]), "destination": int(parts[1]), "values": values})
            elif kind == "Q":
                rejected[parts[0]] = values[0]
            else:
                raise ValueError(f"Unknown output type: {kind}")
    manifest = read_json(DATA / "input" / metadata["month"] / "manifest.json")
    if not (counts["Z"] == counts["D"] == counts["O"] == counts["T"]
            and counts["Z"] + counts["Q"] == manifest["rows"]):
        raise ValueError("Conservation check failed; refusing to publish inconsistent results")
    result = {"run_id": run_id, "created_at": datetime.now(UTC).isoformat(),
              "metadata": metadata, "dataset": manifest,
              "valid_rows": counts["Z"], "rejected_rows": counts["Q"], "rejected": rejected,
              "zone_hours": zone_hours, "days": sorted(days, key=lambda x: x["day"]),
              "od": sorted(od, key=lambda x: -x["values"][0]), "conservation_passed": True}
    atomic_json(path / "result.json", result)
    atomic_json(RESULTS / "latest.json", result)
    atomic_json(RESULTS / f"{metadata['month']}.json", result)
    return result


def summarize(result, zone_info, hour=None, borough=None):
    # hour filter applies to zones only: the 24h profile stays city-wide by borough scope
    scope = [r for r in result["zone_hours"]
             if borough is None or zone_info.get(r["zone"], {}).get("borough") == borough]
    selected = [r for r in scope if hour is None or r["hour"] == hour]
    zones = defaultdict(lambda: [0, 0, 0, 0])
    hourly = [0] * 24
    for row in scope:
        hourly[row["hour"]] += row["values"][0]
    for row in selected:
        zones[row["zone"]] = [a + b for a, b in zip(zones[row["zone"]], row["values"])]
    total = [sum(v[i] for v in zones.values()) for i in range(4)]
    def metrics(v):
        n = v[0]
        return {"trips": n, "distance_km": v[1] / 1000 * 1.609344,
                "avg_distance_km": v[1] / 1000 * 1.609344 / n if n else 0,
                "avg_minutes": v[2] / 60 / n if n else 0,
                "avg_amount": v[3] / 100 / n if n else 0}
    by_zone = [{"id": zid, **zone_info.get(zid, {"name": str(zid), "borough": "Unknown"}), **metrics(v)}
               for zid, v in zones.items()]
    return {"run_id": result["run_id"], "month": result["dataset"]["month"],
            "filters": {"hour": hour, "borough": borough}, "summary": metrics(total),
            "zones": sorted(by_zone, key=lambda x: -x["trips"]), "hourly": hourly,
            "quality": {"input": result["dataset"]["rows"], "valid": result["valid_rows"],
                        "rejected": result["rejected_rows"], "reasons": result["rejected"],
                        "scope": "full dataset, independent of filters"},
            "metadata": result["metadata"], "source": result["dataset"]["source"],
            "days": result["days"] if hour is None and borough is None else [],
            "top_od": result["od"][:10] if hour is None and borough is None else []}
