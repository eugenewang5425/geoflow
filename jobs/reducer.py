#!/usr/bin/env python3
"""Streaming sum reducer, also valid as a combiner; never average partition averages."""
import sys


def reduce_lines(lines):
    current, total = None, [0, 0, 0, 0]
    for line in lines:
        key, raw = line.rstrip("\n").split("\t", 1)
        values = [int(x) for x in raw.split(",")]
        if len(values) != 4:
            raise ValueError("Expected four additive statistics")
        if current is not None and key < current:
            raise ValueError("Reducer input must be sorted by key")
        if key != current:
            if current is not None:
                yield current, total
            current, total = key, [0, 0, 0, 0]
        total = [a + b for a, b in zip(total, values)]
    if current is not None:
        yield current, total


if __name__ == "__main__":
    for key, values in reduce_lines(sys.stdin):
        print(key + "\t" + ",".join(map(str, values)))
