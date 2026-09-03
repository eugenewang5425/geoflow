import os
import random
import subprocess
import sys

import pytest

from jobs.mapper import emissions, parse_trip
from jobs.reducer import reduce_lines


def trip(**updates):
    values = {"start": "2025-01-02 12:00:00", "end": "2025-01-02 12:10:00", "pu": "161", "do": "162",
              "miles": "2.50", "amount": "12.34"}
    values.update(updates)
    return list(values.values())


def test_known_trip_units_and_keys():
    value, reason = parse_trip(trip(), "2025-01")
    assert reason is None
    assert value["distance_milli_miles"] == 2500
    assert value["seconds"] == 600
    assert value["cents"] == 1234
    assert list(emissions(value)) == [("Z|161|12", "1,2500,600,1234"),
                                      ("D|2025-01-02", "1,2500,600,1234"),
                                      ("O|161|162", "1,2500,600,1234"),
                                      ("T|2025-01-02|161|12", "1,2500,600,1234")]


@pytest.mark.parametrize("updates,reason", [
    ({"pu": "264"}, "UnknownZone"), ({"pu": "1.5"}, "UnknownZone"),
    ({"miles": "nan"}, "NonFinite"), ({"amount": "inf"}, "NonFinite"),
    ({"end": "2025-01-02 11:00:00"}, "InvalidDuration"),
    ({"end": "2025-01-02 12:00:59"}, "InvalidDuration"),
    ({"miles": "0"}, "InvalidDistance"), ({"amount": "-1"}, "InvalidAmount"),
    ({"start": "2024-12-31 23:59:00"}, "OutsideMonth"), ({"start": ""}, "Malformed"),
])
def test_quality_rules(updates, reason):
    assert parse_trip(trip(**updates), "2025-01")[1] == reason


def test_combiner_arbitrary_partitioning_exactly_preserves_sums():
    rng = random.Random(42)
    records = [(f"Z|{rng.randrange(7)}", [1, rng.randrange(10000), rng.randrange(10000), rng.randrange(10000)])
               for _ in range(400)]
    def encode(pairs):
        return [k + "\t" + ",".join(map(str, v)) for k, v in sorted(pairs)]
    expected = dict(reduce_lines(encode(records)))
    combined = []
    for start in range(0, len(records), 13):
        combined.extend(reduce_lines(encode(records[start:start+13])))
    assert dict(reduce_lines(encode(combined))) == expected


def test_reducer_rejects_unsorted_input():
    with pytest.raises(ValueError, match="sorted"):
        list(reduce_lines(["b\t1,0,0,0", "a\t1,0,0,0"]))


def test_real_streaming_protocol_and_quality_counters():
    data = ",".join(trip()) + "\n" + ",".join(trip(pu="265")) + "\n"
    process = subprocess.run([sys.executable, "jobs/mapper.py"], input=data, text=True, capture_output=True,
                             check=True, env={**os.environ, "GEOFLOW_MONTH": "2025-01"})
    assert "reporter:counter:GeoFlow,InputRows,2" in process.stderr
    assert "reporter:counter:GeoFlow,ValidRows,1" in process.stderr
    assert "reporter:" not in process.stdout
    result = dict(reduce_lines(sorted(process.stdout.splitlines())))
    assert result["Q|UnknownZone"][0] == 1
    assert result["Z|161|12"][0] == 1
    assert result["T|2025-01-02|161|12"][0] == 1
