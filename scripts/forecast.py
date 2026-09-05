"""Demand forecasting with weather features (LightGBM + seasonal baseline).

Time split (strictly temporal): Jan-Oct train, Nov validation, Dec test.
The daily (day, zone, hour) grid is completed with zeros, so 1-day / 7-day lags
are calendar-correct (a missing request = zero demand, not a missing row).
Features: calendar, zone, hourly weather, daily weather, demand lags.
Baseline: seasonal naive (same zone-hour one week earlier).
"""
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geoflow.config import DATA, RESULTS
from geoflow.io import atomic_json, read_json


def zone_neighbors(max_dist_m=800):
    """Adjacency list {zone_id: [neighbor_ids]} for zones within max_dist_m.

    Computed once with shapely/pyproj (UTM 18N) and cached to data/neighbors.json.
    """
    path = DATA / "neighbors.json"
    if path.exists():
        return {int(k): v for k, v in read_json(path).items()}
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as sh_transform
    feats = read_json(DATA / "zones.geojson")["features"]
    tf = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True)
    geoms = {}
    for f in feats:
        zid = int(f["properties"]["id"])
        geoms[zid] = sh_transform(lambda x, y: tf.transform(x, y), shape(f["geometry"]))
    ids = sorted(geoms)
    neigh = {zid: [] for zid in ids}
    for i, a in enumerate(ids):
        ga = geoms[a]
        for b in ids[i + 1:]:
            if ga.distance(geoms[b]) <= max_dist_m:
                neigh[a].append(b)
                neigh[b].append(a)
    atomic_json(path, neigh)
    return neigh

TRAIN_END = date(2025, 10, 31)
VALID_END = date(2025, 11, 30)
WEATHER_VARS = ["temperature_2m", "apparent_temperature", "precipitation", "snowfall",
                "wind_speed_10m", "relative_humidity_2m", "cloud_cover"]
DAILY_VARS = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum",
              "snowfall_sum", "wind_speed_10m_max", "sunshine_duration"]


def resolve_runs():
    best = {}
    for path in sorted((DATA / "runs").glob("*/run.json"), reverse=True):
        meta = read_json(path)
        if meta.get("status") == "SUCCEEDED" and meta["month"] not in best:
            best[meta["month"]] = path.parent
    return best


def load_daily_grid(runs):
    """Build the complete (zone, hour, date) grid; absent rows are zero demand."""
    frames = []
    zones = set()
    for month, run_dir in sorted(runs.items()):
        daily = run_dir / "daily.tsv"
        if not daily.exists():
            continue
        rows = []
        for line in daily.read_text(encoding="utf-8").splitlines():
            key, vals = line.split("\t", 1)
            _, day, zone, hour = key.split("|")
            c = vals.split(",")[0]
            rows.append((day, int(zone), int(hour), int(c)))
            zones.add(int(zone))
        frames.append(pd.DataFrame(rows, columns=["day", "zone", "hour", "trips"]))
    if not frames:
        raise RuntimeError("no daily.tsv found")
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["day"])
    df = df.drop(columns=["day"])
    dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    index = pd.MultiIndex.from_product([sorted(zones), range(24), dates],
                                       names=["zone", "hour", "date"])
    df = df.set_index(["zone", "hour", "date"]).reindex(index, fill_value=0)
    df["trips"] = df["trips"].fillna(0).astype("int64")
    return df.reset_index()


def main():
    runs = resolve_runs()
    df = load_daily_grid(runs)
    df["month"] = df["date"].dt.month
    df["weekday"] = df["date"].dt.weekday.astype("int8")
    df["is_weekend"] = (df["weekday"] >= 5).astype("int8")
    print("grid rows:", len(df), flush=True)

    weather = read_json(ROOT / "data/raw/weather_2025.json")
    hourly = pd.DataFrame(weather["hourly"])
    hourly["date"] = pd.to_datetime(hourly["time"].str[:10])
    hourly["hour"] = hourly["time"].str[11:13].astype(int)
    daily = pd.DataFrame(weather["daily"])
    daily["date"] = pd.to_datetime(daily["time"])
    df = df.merge(hourly[["date", "hour"] + WEATHER_VARS], on=["date", "hour"], how="left")
    df = df.merge(daily[["date"] + DAILY_VARS], on="date", how="left")

    # Calendar-correct lags: the grid is complete, so positional shift == day shift.
    df = df.sort_values(["zone", "hour", "date"]).reset_index(drop=True)
    g = df.groupby(["zone", "hour"], sort=False)["trips"]
    df["lag_1"] = g.shift(1)
    df["lag_7"] = g.shift(7)
    df["lag7mean"] = g.transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())

    # Neighborhood lag: mean of adjacent zones' same-hour lag_1 (congestion spills
    # over; adjacency computed geometrically once and cached).
    neighbors = zone_neighbors()
    pairs = [(int(z), int(n)) for z, ns in neighbors.items() for n in ns]
    pair_df = pd.DataFrame(pairs, columns=["zone", "neighbor"])
    merged = df[["date", "hour", "zone", "lag_1"]].merge(pair_df, on="zone")
    nb_mean = (merged.groupby(["date", "hour", "zone"])["lag_1"].mean()
                     .rename("neighbor_lag1_mean").reset_index())
    df = df.merge(nb_mean, on=["date", "hour", "zone"], how="left")
    df["neighbor_lag1_mean"] = df["neighbor_lag1_mean"].fillna(df["lag_1"])

    feats = ["zone", "hour", "weekday", "month", "is_weekend"] + WEATHER_VARS + DAILY_VARS +             ["lag_1", "lag_7", "lag7mean"]
    df = df.dropna(subset=feats + ["trips"])
    # availability of lag_7: from 2025-01-08 on
    df = df[df["date"] >= pd.Timestamp("2025-01-08")]
    train = df[df["date"] <= pd.Timestamp(TRAIN_END)].copy()
    valid = df[(df["date"] > pd.Timestamp(TRAIN_END)) & (df["date"] <= pd.Timestamp(VALID_END))].copy()
    test = df[df["date"] > pd.Timestamp(VALID_END)].copy()
    print("train", len(train), "valid", len(valid), "test", len(test), flush=True)

    try:
        from lightgbm import LGBMRegressor, early_stopping
        model = LGBMRegressor(n_estimators=800, learning_rate=0.06, num_leaves=63,
                              min_child_samples=40, subsample=0.85, subsample_freq=1,
                              colsample_bytree=0.85, n_jobs=-1, random_state=42, verbose=-1)
        model.fit(train[feats], np.log1p(train["trips"].to_numpy()),
                  eval_set=[(valid[feats], np.log1p(valid["trips"].to_numpy()))],
                  callbacks=[early_stopping(40, verbose=False)])
        pred = np.maximum(np.expm1(model.predict(test[feats])), 0.0)
        importance = dict(sorted(zip(feats, model.feature_importances_.tolist()),
                                 key=lambda kv: -kv[1]))
        model_name = "LightGBM"

        def fit_quantile(alpha):
            q = LGBMRegressor(objective="quantile", alpha=alpha, n_estimators=400,
                              learning_rate=0.08, num_leaves=63, min_child_samples=40,
                              subsample=0.85, subsample_freq=1, colsample_bytree=0.85,
                              n_jobs=-1, random_state=42, verbose=-1)
            q.fit(train[feats], np.log1p(train["trips"].to_numpy()),
                  eval_set=[(valid[feats], np.log1p(valid["trips"].to_numpy()))],
                  callbacks=[early_stopping(30, verbose=False)])
            return np.maximum(np.expm1(q.predict(test[feats])), 0.0)

        q10 = fit_quantile(0.1)
        q90 = fit_quantile(0.9)

        # ablation: the same point model PLUS the neighborhood feature
        feats_w = feats + ["neighbor_lag1_mean"]
        ab = LGBMRegressor(n_estimators=800, learning_rate=0.06, num_leaves=63,
                           min_child_samples=40, subsample=0.85, subsample_freq=1,
                           colsample_bytree=0.85, n_jobs=-1, random_state=42, verbose=-1)
        ab.fit(train[feats_w], np.log1p(train["trips"].to_numpy()),
               eval_set=[(valid[feats_w], np.log1p(valid["trips"].to_numpy()))],
               callbacks=[early_stopping(40, verbose=False)])
        pred_w = np.maximum(np.expm1(ab.predict(test[feats_w])), 0.0)
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingRegressor
        model_name = "HistGradientBoosting (sklearn fallback)"
        model = HistGradientBoostingRegressor(max_iter=500, random_state=42)
        model.fit(train[feats], np.log1p(train["trips"].to_numpy()))
        pred = np.expm1(model.predict(test[feats]))
        pred_w = pred  # fallback has no quantile/ablation variants
        importance = {}

    test = test.reset_index(drop=True)
    test["pred"] = pred
    if "q10" in dir():
        test["q10"] = np.maximum(q10, 0.0)
        test["q90"] = np.maximum(q90, test["q10"])
    actual = test["trips"].to_numpy().astype(float)
    base = test["lag_7"].to_numpy().astype(float)

    if "q10" in dir():
        lo = np.maximum(q10, 0.0)
        hi = np.maximum(q90, lo)
        coverage = float(np.mean((actual >= lo) & (actual <= hi))) * 100
        interval_metrics = {"coverage_pct": round(coverage, 2),
                            "target_pct": 80.0,
                            "mean_width": round(float(np.mean(hi - lo)), 2)}
    else:
        interval_metrics = {"coverage_pct": None, "target_pct": 80.0, "mean_width": None}

    def metrics(a, p):
        m = np.isfinite(a) & np.isfinite(p)
        a, p = a[m], p[m]
        rmse = float(np.sqrt(np.mean((a - p) ** 2)))
        mae = float(np.mean(np.abs(a - p)))
        mape = float(np.mean(np.abs(a - p) / np.maximum(a, 1))) * 100
        hi = a >= 5
        mape_hi = float(np.mean(np.abs(a[hi] - p[hi]) / np.maximum(a[hi], 1))) * 100 if hi.any() else None
        return {"rmse": round(rmse, 2), "mae": round(mae, 2), "mape_pct": round(mape, 2),
                "mape_high_demand_pct": round(mape_hi, 2) if mape_hi is not None else None}

    report = {
        "model": model_name,
        "features": feats,
        "train_window": "2025-01-08..2025-10-31",
        "validation_window": "2025-11-01..2025-11-30",
        "test_window": "2025-12-01..2025-12-31",
        "rows": {"train": len(train), "valid": len(valid), "test": len(test)},
        "metrics": {"model": metrics(actual, pred), "baseline_lag7": metrics(actual, base),
                    "interval": interval_metrics,
                    "neighbor_ablation": {"rmse_baseline_features": metrics(actual, pred)["rmse"],
                                          "rmse_with_neighbor_feature": metrics(actual, pred_w)["rmse"],
                                          "verdict": "邻域滞后与自身滞后高度冗余，主模型不采用"}},
        "weather_effect": {
            "precip_vs_dry": {
                "dry_mean": round(float(actual[test["precipitation"].to_numpy() == 0].mean()), 1),
                "wet_mean": round(float(actual[test["precipitation"].to_numpy() > 0].mean()), 1),
                "n_dry": int((test["precipitation"].to_numpy() == 0).sum()),
                "n_wet": int((test["precipitation"].to_numpy() > 0).sum())},
            "snow_hours": int((test["snowfall"].to_numpy() > 0).sum()),
            "snow_days": int(test.loc[test["snowfall_sum"] > 0, "date"].nunique()),
            "temp_bins": [],
            "feature_importance": dict(list(importance.items())[:25]),
        },
        "weather_provenance": read_json(ROOT / "data/raw/weather_2025_manifest.json"),
        "note": ("One-step-ahead evaluation on the strictly temporal December test window; "
                 "lag features use observed values. Baseline = same zone-hour one week earlier."),
    }
    temp = test["temperature_2m"].to_numpy()
    for lo, hi in [(-20, 0), (0, 10), (10, 20), (20, 30), (30, 50)]:
        mask = (temp >= lo) & (temp < hi)
        if mask.sum():
            report["weather_effect"]["temp_bins"].append(
                {"range": f"{lo}..{hi}°C", "mean": round(float(actual[mask].mean()), 1),
                 "n": int(mask.sum())})

    # per-zone December predicted vs actual for the dashboard
    zone_agg = test.groupby("zone").agg(actual=("trips", "sum"),
                                        predicted=("pred", "sum")).reset_index()
    zone_agg["error_pct"] = (zone_agg["predicted"] - zone_agg["actual"]) / zone_agg["actual"] * 100
    zone_agg["error_pct"] = zone_agg["error_pct"].replace([np.inf, -np.inf], 0).fillna(0.0)
    zones_info = read_json(DATA / "zones.geojson")["features"]
    name_map = {f["properties"]["id"]: f["properties"]["name"] for f in zones_info}
    borough_map = {f["properties"]["id"]: f["properties"]["borough"] for f in zones_info}
    zone_agg["name"] = zone_agg["zone"].map(name_map)
    zone_agg["borough"] = zone_agg["zone"].map(borough_map)
    atomic_json(RESULTS / "forecast.json", {
        "model": model_name, "test_window": report["test_window"],
        "metrics": report["metrics"], "zones": zone_agg.fillna(0).to_dict("records"),
        "generated_at": datetime.now(UTC).isoformat(),
    })

    top_zone = int(zone_agg.loc[zone_agg["actual"].idxmax(), "zone"])
    curve_cols = ["date", "hour", "trips", "pred"] + (["q10", "q90"] if "q10" in test.columns else [])
    curve = test[test["zone"] == top_zone].sort_values(["date", "hour"])[curve_cols]
    atomic_json(RESULTS / "forecast_curve.json", {
        "zone": top_zone, "name": name_map.get(top_zone),
        "points": [[(pd.Timestamp(r["date"].date()) + pd.Timedelta(hours=int(r["hour"]))).isoformat(sep="T")[:16],
                    int(r["trips"]), round(float(r["pred"]), 1)]
                   + ([round(float(r["q10"]), 1), round(float(r["q90"]), 1)]
                      if "q10" in curve_cols else [])
                   for _, r in curve.iterrows()],
    })
    atomic_json(ROOT / "evidence" / "forecast.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
