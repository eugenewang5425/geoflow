"""Cross-year forecast: train LightGBM on 2019-2024, test on 2025.

The dataset is too large to merge in pandas (2.5e8 rows × 8760 hours = OOM).
Strategy: aggregate to (date, hour, zone) once in Spark (small, ~5e5 rows),
then train in pandas. Weather is only available for 2025; prior years are NaN,
which LightGBM handles natively.
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(r"D:\项目\云计算")
T_PARQUET = ROOT / "data" / "long" / "parquet" / "kind=T"
EVIDENCE = ROOT / "evidence" / "forecast_long.json"
EVIDENCE.parent.mkdir(exist_ok=True)

TRAIN_END = date(2024, 12, 31)
WEATHER_VARS = ["temperature_2m", "apparent_temperature", "precipitation", "snowfall",
                "wind_speed_10m", "relative_humidity_2m", "cloud_cover"]
DAILY_VARS = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum",
              "snowfall_sum", "wind_speed_10m_max", "sunshine_duration"]


def main():
    sys.path.insert(0, str(ROOT))
    t0 = time.time()
    # T parquet is already (zone, hour, day) with one row per demand triple.
    print("loading T parquet ...", flush=True)
    df = pq.read_table(T_PARQUET).to_pandas()
    print(f"loaded {len(df):,} (zone, hour, day) cells in {time.time() - t0:.1f}s", flush=True)
    df["trips"] = 1
    df["date"] = pd.to_datetime(df["day"])
    df["zone"] = df["zone"].astype(int)
    df["hour"] = df["hour"].astype(int)
    df["month"] = df["date"].dt.month
    df["weekday"] = df["date"].dt.weekday.astype("int8")
    df["is_weekend"] = (df["weekday"] >= 5).astype("int8")
    df["year"] = df["date"].dt.year

    # Build full (date, hour, zone) grid (so NaN is 0 demand)
    full_dates = pd.date_range("2019-01-01", "2025-12-31", freq="D")
    full_grid = pd.MultiIndex.from_product(
        [full_dates, range(24), sorted(df["zone"].unique())],
        names=["date", "hour", "zone"]).to_frame(index=False)
    full_grid = full_grid.merge(
        df.groupby(["date", "hour", "zone"]).agg(
            trips=("trips", "sum"),
            month=("month", "first"),
            weekday=("weekday", "first"),
            is_weekend=("is_weekend", "first"),
            year=("year", "first"),
        ).reset_index(),
        on=["date", "hour", "zone"], how="left")
    full_grid["trips"] = full_grid["trips"].fillna(0).astype("int64")
    full_grid["year"] = full_grid["date"].dt.year
    full_grid["month"] = full_grid["date"].dt.month
    full_grid["weekday"] = full_grid["date"].dt.weekday.astype("int8")
    full_grid["is_weekend"] = (full_grid["weekday"] >= 5).astype("int8")
    print(f"grid ready: {len(full_grid):,} cells ({time.time() - t0:.1f}s)", flush=True)

    # Attach 2025 weather (only year with weather)
    weather = json.loads((ROOT / "data" / "raw" / "weather_2025.json").read_text())
    hourly = pd.DataFrame(weather["hourly"])
    hourly["date"] = pd.to_datetime(hourly["time"].str[:10])
    hourly["hour"] = hourly["time"].str[11:13].astype(int)
    daily = pd.DataFrame(weather["daily"])
    daily["date"] = pd.to_datetime(daily["time"])
    full_grid = full_grid.merge(hourly[["date", "hour"] + WEATHER_VARS], on=["date", "hour"], how="left")
    full_grid = full_grid.merge(daily[["date"] + DAILY_VARS], on="date", how="left")

    # Lags (positional shift = day shift, since grid is complete)
    full_grid = full_grid.sort_values(["zone", "hour", "date"]).reset_index(drop=True)
    g = full_grid.groupby(["zone", "hour"], sort=False)["trips"]
    full_grid["lag_1"] = g.shift(1)
    full_grid["lag_7"] = g.shift(7)
    full_grid["lag7mean"] = g.transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())

    feats = ["zone", "hour", "weekday", "month", "is_weekend", "year"] + WEATHER_VARS + DAILY_VARS + \
            ["lag_1", "lag_7", "lag7mean"]
    # Drop only when core columns are missing (NaN in weather is OK — LightGBM handles it)
    must_have = ["trips", "lag_1", "lag_7", "lag7mean", "zone", "hour", "weekday", "month", "year"]
    full_grid = full_grid.dropna(subset=must_have)
    full_grid = full_grid[full_grid["date"] >= pd.Timestamp("2019-01-08")]

    train = full_grid[full_grid["date"] <= pd.Timestamp(TRAIN_END)].copy()
    test = full_grid[full_grid["date"] > pd.Timestamp(TRAIN_END)].copy()
    print(f"train: {len(train):,} cells (2019-2024) | test (2025): {len(test):,}", flush=True)

    from lightgbm import LGBMRegressor, early_stopping
    val = train[train["date"] >= pd.Timestamp("2024-01-01")]
    fit_train = train[train["date"] < pd.Timestamp("2024-01-01")]
    model = LGBMRegressor(n_estimators=800, learning_rate=0.06, num_leaves=63,
                          min_child_samples=40, subsample=0.85, subsample_freq=1,
                          colsample_bytree=0.85, n_jobs=-1, random_state=42, verbose=-1)
    model.fit(fit_train[feats], np.log1p(fit_train["trips"].to_numpy()),
              eval_set=[(val[feats], np.log1p(val["trips"].to_numpy()))],
              callbacks=[early_stopping(40, verbose=False)])
    pred = np.maximum(np.expm1(model.predict(test[feats])), 0.0)
    importance = dict(sorted(zip(feats, model.feature_importances_.tolist()),
                            key=lambda kv: -kv[1]))

    actual = test["trips"].to_numpy().astype(float)
    base = test["lag_7"].to_numpy().astype(float)
    rmse = float(np.sqrt(np.mean((actual - pred) ** 2)))
    base_rmse = float(np.sqrt(np.mean((actual - base) ** 2)))
    mape = float(np.mean(np.abs(actual - pred) / np.maximum(actual, 1))) * 100
    hi = actual >= 5
    mape_hi = float(np.mean(np.abs(actual[hi] - pred[hi]) / np.maximum(actual[hi], 1))) * 100

    by_year_metrics = []
    for yr in sorted(test["date"].dt.year.unique()):
        mask = (test["date"].dt.year == yr).to_numpy()
        if mask.sum() == 0: continue
        a = actual[mask]; p = pred[mask]
        by_year_metrics.append({
            "year": int(yr),
            "cells": int(mask.sum()),
            "rmse": round(float(np.sqrt(np.mean((a - p) ** 2))), 2),
            "mape_pct": round(float(np.mean(np.abs(a - p) / np.maximum(a, 1))) * 100, 2),
        })

    report = {
        "engine": "LightGBM + 6-year long archive (2019-2024 train, 2025 test)",
        "rows": {"train_2019_2023": len(fit_train),
                 "val_2024": len(val),
                 "test_2025": len(test)},
        "features": feats,
        "metrics": {"model": {"rmse": round(rmse, 2), "mape_pct": round(mape, 2),
                                 "mape_high_demand_pct": round(mape_hi, 2)},
                    "baseline_lag7": {"rmse": round(base_rmse, 2)},
                    "model_vs_baseline": {"rmse_improvement_pct": round((1 - rmse/base_rmse) * 100, 1)}},
        "by_year_test": by_year_metrics,
        "feature_importance": dict(list(importance.items())[:10]),
        "note": "The crucial cross-year generalisation test. 2019-2024 includes the COVID dip (2020-04 = 3.3% of 2019 avg). The model is asked to forecast 2025 without ever seeing it."
    }
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {EVIDENCE} (RMSE 2025={rmse:.2f}, baseline={base_rmse:.2f}, improvement={(1-rmse/base_rmse)*100:.1f}%)", flush=True)


if __name__ == "__main__":
    main()
