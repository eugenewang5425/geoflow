"""Spark-based ingest for 6 years of TLC data (2019-2024).

Reads 72 Parquet files (yellow_tripdata_YYYY-MM.parquet), applies the same
six-field validation as jobs/mapper.py + geoflow.ingest, partitions the clean
output by year/month, and writes a Parquet archive (smaller than CSV shards,
preserves types, column-pruned reads later).

Output: data/long/parquet/year=YYYY/month=MM/*.parquet
        data/long/manifest.json (counts per month + grand total)
"""
import time
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType, TimestampType

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "long" / "parquet"
OUT.parent.mkdir(parents=True, exist_ok=True)
EVIDENCE = ROOT / "evidence"
EVIDENCE.mkdir(exist_ok=True)

YEARS = list(range(2019, 2025))  # 2019..2024 = 6 years = 72 months

BASE = "https://d37ci6vzurychx.cloudfront.net/trip-data"


def build_spark():
    return SparkSession.builder.appName("GeoFlow-Long-Ingest") \
        .master("local[4]") \
        .config("spark.driver.memory", "4g") \
        .config("spark.sql.shuffle.partitions", "32") \
        .getOrCreate()


def main():
    spark = build_spark()
    sc = spark.sparkContext
    sc.setLogLevel("WARN")

    # Anchor every path to this script's location (avoids Spark worker cwd quirks)
    here = Path(__file__).resolve().parent
    raw = here.parent / "data" / "raw" / "long"
    raw.mkdir(parents=True, exist_ok=True)

    months = [(y, m) for y in YEARS for m in range(1, 13)]
    # Download to local first so Spark re-reads on local FS, not on S3.
    # WSL2 has no httpx in the driver Python; use curl from PATH instead.
    import subprocess
    print(f"downloading {len(months)} parquet files via curl ...", flush=True)
    t0 = time.time()
    paths = []
    for y, m in months:
        for name in (f"yellow_tripdata_{y}-{m:02d}.parquet", f"yellow_tripdata_{y}-{m}.parquet"):
            target = raw / name
            if not target.exists():
                rc = subprocess.run(["curl", "-fsSL", "-o", str(target), f"{BASE}/{name}"],
                                    capture_output=True, check=False).returncode
                if rc != 0:
                    # second filename form; skip if also 404
                    continue
            paths.append(str(target))
            break
    print(f"download done in {time.time() - t0:.1f}s ({len(paths)} files)", flush=True)

    # Read all parquet in one go, normalise schema, filter
    print("reading + normalizing + filtering ...", flush=True)
    t0 = time.time()
    # Read per-year with explicit schema coercion; mergeSchema=false so we
    # can cast incompatible types (TLC switched PULocationID int32->int64
    # around mid-2021).
    rename = {
        "tpep_pickup_datetime": "pickup", "tpep_dropoff_datetime": "dropoff",
        "lpep_pickup_datetime": "pickup", "lpep_dropoff_datetime": "dropoff",
        "PULocationID": "pu", "DOLocationID": "do",
        "trip_distance": "miles", "total_amount": "amount",
    }
    frames = []
    for p in paths:
        df = spark.read.parquet(p)
        # rename columns
        for s, d in rename.items():
            if s in df.columns and d not in df.columns:
                df = df.withColumnRenamed(s, d)
        # missing required cols -> skip the file (older months may differ)
        if not all(c in df.columns for c in ("pickup", "dropoff", "pu", "do", "miles", "amount")):
            continue
        # force types to canonical (int + double + timestamp)
        df = (df.withColumn("pickup", F.col("pickup").cast(TimestampType()))
                .withColumn("dropoff", F.col("dropoff").cast(TimestampType()))
                .withColumn("pu", F.col("pu").cast(IntegerType()))
                .withColumn("do", F.col("do").cast(IntegerType()))
                .withColumn("miles", F.col("miles").cast(DoubleType()))
                .withColumn("amount", F.col("amount").cast(DoubleType())))
        frames.append(df.select("pickup", "dropoff", "pu", "do", "miles", "amount"))
    from functools import reduce
    df = reduce(lambda a, b: a.unionByName(b), frames)
    # Drop nulls + non-finite
    df = df.filter(
        F.col("pickup").isNotNull() & F.col("dropoff").isNotNull() &
        F.col("pu").isNotNull() & F.col("do").isNotNull() &
        F.col("miles").isNotNull() & F.col("amount").isNotNull() &
        F.col("miles").isNotNull() & (F.col("miles") > 0) & (F.col("miles") <= 100) &
        (F.col("amount") >= 0) & (F.col("amount") <= 1000) &
        F.col("pu").between(1, 263) & F.col("do").between(1, 263)
    )
    df = df.withColumn("seconds", F.unix_timestamp("dropoff") - F.unix_timestamp("pickup")) \
           .filter((F.col("seconds") >= 60) & (F.col("seconds") <= 10800))
    # Year/month partitions (skip non-2019..2024)
    df = df.withColumn("year", F.year("pickup")) \
           .filter(F.col("year").between(2019, 2024)) \
           .withColumn("month", F.month("pickup"))
    df = df.withColumn("day", F.date_format("pickup", "yyyy-MM-dd")) \
           .withColumn("hour", F.hour("pickup")) \
           .withColumn("distance_milli_miles", (F.col("miles") * 1000).cast(IntegerType())) \
           .withColumn("cents", (F.col("amount") * 100).cast(IntegerType()))
    # 4 key families: Z, D, O, T (mirroring mapper.emissions)
    z = df.select("year", "month", "day", "hour", "pu", "distance_milli_miles", "seconds", "cents") \
           .withColumnRenamed("pu", "zone")
    d = df.select("year", "month", "day", "distance_milli_miles", "seconds", "cents")
    o = df.select("year", "month", "day", "pu", "do", "distance_milli_miles", "seconds", "cents") \
           .withColumnRenamed("pu", "zone").withColumnRenamed("do", "dest")
    t = df.select("year", "month", "day", "hour", "pu", "distance_milli_miles", "seconds", "cents") \
           .withColumnRenamed("pu", "zone")
    print(f"normalization done in {time.time() - t0:.1f}s", flush=True)

    # Write partitioned parquet (one per year x month)
    print(f"writing {OUT} partitioned by year/month ...", flush=True)
    t0 = time.time()
    # Coalesce per (year,month) before write to avoid tiny files
    for kind, frame in [("Z", z), ("D", d), ("O", o), ("T", t)]:
        out = OUT.parent / "parquet" / f"kind={kind}"
        frame.coalesce(72).write.mode("overwrite").partitionBy("year", "month").parquet(str(out))
    print(f"parquet write done in {time.time() - t0:.1f}s", flush=True)

    # Build manifest by counting rows per (year, month)
    print("computing manifest ...", flush=True)
    totals = z.groupBy("year", "month").count().orderBy("year", "month").collect()
    grand = sum(r["count"] for r in totals)
    manifest = {
        "engine": "Spark 3.5.1 + pyarrow",
        "years": YEARS, "months": 12,
        "source_url_template": f"{BASE}/yellow_tripdata_YYYY-MM.parquet",
        "valid_rows_per_month": [{"year": r["year"], "month": int(r["month"]),
                                  "rows": int(r["count"])} for r in totals],
        "total_valid_rows": int(grand),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    import json
    (ROOT / "data" / "long" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"TOTAL valid rows: {grand:,}", flush=True)
    spark.stop()


if __name__ == "__main__":
    main()
