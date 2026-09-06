#!/usr/bin/env python3
"""Pure-stdlib streaming mapper. stdout=data, stderr=Hadoop counters."""
import csv
import math
import os
import sys
from collections import Counter
from datetime import datetime


def parse_trip(row, month):
    if len(row) != 6:
        return None, "Malformed"
    try:
        start = datetime.fromisoformat(row[0])
        end = datetime.fromisoformat(row[1])
        pu, do = float(row[2]), float(row[3])
        miles, amount = float(row[4]), float(row[5])
    except (ValueError, TypeError):
        return None, "Malformed"
    if any(not math.isfinite(x) for x in (pu, do, miles, amount)):
        return None, "NonFinite"
    if start.strftime("%Y-%m") != month:
        return None, "OutsideMonth"
    if not (pu.is_integer() and do.is_integer() and 1 <= pu <= 263 and 1 <= do <= 263):
        return None, "UnknownZone"
    seconds = (end - start).total_seconds()
    if not 60 <= seconds <= 10800:
        return None, "InvalidDuration"
    if not 0 < miles <= 100:
        return None, "InvalidDistance"
    if not 0 <= amount <= 1000:
        return None, "InvalidAmount"
    # Integer fixed-point sums are associative: exact agreement with any combiner tree.
    return {"zone": int(pu), "dest": int(do), "hour": start.hour, "day": start.strftime("%Y-%m-%d"),
            "distance_milli_miles": round(miles * 1000), "seconds": round(seconds),
            "cents": round(amount * 100)}, None


def emissions(trip):
    values = f"1,{trip['distance_milli_miles']},{trip['seconds']},{trip['cents']}"
    yield f"Z|{trip['zone']:03d}|{trip['hour']:02d}", values
    yield f"D|{trip['day']}", values
    yield f"O|{trip['zone']:03d}|{trip['dest']:03d}", values
    yield f"T|{trip['day']}|{trip['zone']:03d}|{trip['hour']:02d}", values


def main():
    month = os.environ.get("GEOFLOW_MONTH", "2025-01")
    counters = Counter()
    # Optional, explicit failure experiment: only the first attempt of mapper 000000 fails.
    attempt = os.environ.get("mapreduce_task_attempt_id", os.environ.get("mapred_task_id", ""))
    if os.environ.get("GEOFLOW_FAIL_FIRST") == "1" and "_m_000000_0" in attempt:
        print("Intentional first-attempt failure for the recovery experiment", file=sys.stderr)
        sys.exit(42)
    for row in csv.reader(sys.stdin):
        counters["InputRows"] += 1
        trip, reason = parse_trip(row, month)
        if reason:
            counters[reason] += 1
            print(f"Q|{reason}\t1,0,0,0")
            continue
        counters["ValidRows"] += 1
        for key, value in emissions(trip):
            print(f"{key}\t{value}")
    for key, value in counters.items():
        print(f"reporter:counter:GeoFlow,{key},{value}", file=sys.stderr)


if __name__ == "__main__":
    main()
