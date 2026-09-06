"""Cross-year aggregates on the long-form Parquet archive.

Reads data/long/parquet/kind=Z and produces:
- 6-year month x hour heatmap (long form, pivotable to a year x month grid)
- 6-year month x weekday x hour demand (for the 6-year version of the year-view)
- 6-year same-month comparison (January 2019 vs ... vs 2024 monthly totals)
- 2020 pandemic timeline (monthly totals 2019-2021)
Writes data/long/year_aggregate.json + evidence/year_long.json.
"""
import json
import time
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
PARQUET = ROOT / "data" / "long" / "parquet" / "kind=T"
OUT = ROOT / "data" / "long" / "year_aggregate.json"
EVIDENCE = ROOT / "evidence" / "year_long.json"
EVIDENCE.parent.mkdir(exist_ok=True)


def build_spark():
    return SparkSession.builder.appName("GeoFlow-Year-Long") \
        .master("local[2]") \
        .config("spark.driver.memory", "2g") \
        .getOrCreate()


def main():
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")
    df = spark.read.parquet(str(PARQUET))
    print(f"rows in Z kind: {df.count():,}", flush=True)
    df = df.withColumn("weekday", F.dayofweek("day"))  # 1=Sun, 7=Sat

    # 1. monthly totals (6 years)
    monthly = (df.groupBy("year", "month")
                 .agg(F.count("*").alias("trips"),
                      F.round(F.sum("distance_milli_miles") / 1000 / 1000, 1).alias("distance_MM"),
                      F.round(F.sum("cents") / 100 / 1e6, 2).alias("amount_MUSD"))
                 .orderBy("year", "month")
                 .collect())
    monthly_rows = [{"year": int(r["year"]), "month": int(r["month"]),
                     "trips": int(r["trips"]),
                     "distance_MM": float(r["distance_MM"] or 0),
                     "amount_MUSD": float(r["amount_MUSD"] or 0)} for r in monthly]

    # 2. hour x month (averaged across 6 years for the same calendar month)
    by_hour_month = (df.groupBy("month", "hour")
                       .agg(F.count("*").alias("trips"))
                       .orderBy("month", "hour")
                       .collect())
    by_hour_month_rows = [{"month": int(r["month"]), "hour": int(r["hour"]),
                           "avg_trips": int(r["trips"])} for r in by_hour_month]

    # 3. weekday x hour (averaged)
    by_weekday_hour = (df.groupBy("weekday", "hour")
                         .agg(F.count("*").alias("trips"))
                         .orderBy("weekday", "hour")
                         .collect())
    by_weekday_hour_rows = [{"weekday": int(r["weekday"]), "hour": int(r["hour"]),
                              "avg_trips": int(r["trips"])} for r in by_weekday_hour]

    # 4. year totals
    yearly = (df.groupBy("year").agg(F.count("*").alias("trips"))
                .orderBy("year").collect())
    yearly_rows = [{"year": int(r["year"]), "trips": int(r["trips"])} for r in yearly]

    # 5. pandemic timeline (2019-2021 monthly)
    pandemic = [r for r in monthly_rows if r["year"] in (2019, 2020, 2021)]
    base_2019 = sum(r["trips"] for r in pandemic if r["year"] == 2019)
    base_2019_5 = base_2019 / 12.0
    for r in pandemic:
        r["pct_of_2019"] = round(r["trips"] / base_2019_5 * 100, 1)

    report = {
        "engine": "Spark 3.5.1 (local[2])",
        "source": str(PARQUET),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "yearly_totals": yearly_rows,
        "monthly_totals": monthly_rows,
        "pandemic_timeline_2019_2021": pandemic,
        "by_hour_month": by_hour_month_rows,
        "by_weekday_hour": by_weekday_hour_rows,
        "note": "6-year averages per (month, hour) and (weekday, hour); pandemic timeline shows absolute trips + % of 2019 monthly mean."
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(monthly_rows)} months, {len(yearly_rows)} years)", flush=True)
    spark.stop()


if __name__ == "__main__":
    main()
