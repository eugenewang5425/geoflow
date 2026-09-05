"""Spark re-implementation of the GeoFlow monthly aggregation.

Uses the exact validation rules of jobs/mapper.py and emits the same four key
families; aggregateByKey performs a map-side combine, mirroring the MR combiner.
Usage: spark-submit spark_od.py <month> <hdfs-input-glob>
"""
import csv
import math
import sys
import time
from datetime import datetime

from pyspark.sql import SparkSession


def main():
    month = sys.argv[1]
    hdfs_glob = sys.argv[2]

    def parse_emit(line):
        try:
            row = next(csv.reader([line]))
        except (csv.Error, StopIteration):
            return []
        if len(row) != 6:
            return []
        try:
            start = datetime.fromisoformat(row[0])
            end = datetime.fromisoformat(row[1])
            pu, do = float(row[2]), float(row[3])
            miles, amount = float(row[4]), float(row[5])
        except (ValueError, TypeError):
            return []
        if any(not math.isfinite(x) for x in (pu, do, miles, amount)):
            return []
        if start.strftime("%Y-%m") != month:
            return []
        if not (pu.is_integer() and do.is_integer() and 1 <= pu <= 263 and 1 <= do <= 263):
            return []
        seconds = (end - start).total_seconds()
        if not 60 <= seconds <= 10800:
            return []
        if not 0 < miles <= 100:
            return []
        if not 0 <= amount <= 1000:
            return []
        zone, dest, hour, day = int(pu), int(do), start.hour, start.strftime("%Y-%m-%d")
        value = (1, round(miles * 1000), round(seconds), round(amount * 100))
        return [(f"Z|{zone:03d}|{hour:02d}", value), (f"D|{day}", value),
                (f"O|{zone:03d}|{dest:03d}", value), (f"T|{day}|{zone:03d}|{hour:02d}", value)]

    spark = SparkSession.builder.appName(f"GeoFlow-Spark-{month}").getOrCreate()
    sc = spark.sparkContext
    t0 = time.perf_counter()
    result = (sc.textFile(hdfs_glob)
                .flatMap(parse_emit)
                .aggregateByKey((0, 0, 0, 0),
                                lambda a, b: tuple(x + y for x, y in zip(a, b)),
                                lambda a, b: tuple(x + y for x, y in zip(a, b)))
                .collect())
    compute_seconds = round(time.perf_counter() - t0, 3)
    valid_rows = sum(v[0] for _, v in result) // 4  # each trip emitted 4 keys
    print(f"RESULT_KEYS\t{len(result)}")
    print(f"VALID_ROWS\t{valid_rows}")
    print(f"COMPUTE_SECONDS\t{compute_seconds}")
    spark.stop()


if __name__ == "__main__":
    main()
