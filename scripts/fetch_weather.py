"""Download 2025 hourly NYC weather (Open-Meteo Archive API) as prediction features.

Source: Open-Meteo historical archive for Central Park (40.7812, -73.9665).
Free for non-commercial use; attribution: Open-Meteo (https://open-meteo.com/).
Saves the raw JSON plus a provenance manifest with SHA-256.
"""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://archive-api.open-meteo.com/v1/archive"
COORDS = {"latitude": 40.7812, "longitude": -73.9665}
HOURLY = ("temperature_2m,apparent_temperature,precipitation,snowfall,"
          "wind_speed_10m,relative_humidity_2m,cloud_cover,visibility")
DAILY = ("temperature_2m_max,temperature_2m_min,precipitation_sum,"
         "snowfall_sum,wind_speed_10m_max,sunshine_duration")
ARGS = {"start_date": "2025-01-01", "end_date": "2025-12-31",
        "hourly": HOURLY, "daily": DAILY, "timezone": "America/New_York"}


def main():
    target = ROOT / "data" / "raw" / "weather_2025.json"
    manifest_path = ROOT / "data" / "raw" / "weather_2025_manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(BASE, params={**COORDS, **ARGS})
        response.raise_for_status()
        payload = response.json()
    raw = json.dumps(payload, ensure_ascii=False)
    tmp = target.with_suffix(".json.partial")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(target)
    manifest = {
        "source": "Open-Meteo Archive API (historical weather)",
        "url": str(response.url),
        "license": "Open-Meteo: CC-BY 4.0 attribution; free for non-commercial use",
        "station": "Central Park, NYC (40.7812, -73.9665)",
        "period": ARGS["start_date"] + ".." + ARGS["end_date"],
        "timezone": ARGS["timezone"],
        "hourly_variables": [v.strip() for v in HOURLY.split(",")],
        "daily_variables": [v.strip() for v in DAILY.split(",")],
        "fetched_at": datetime.now(UTC).isoformat(),
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "rows_hourly": len(payload.get("hourly", {}).get("time", [])),
        "rows_daily": len(payload.get("daily", {}).get("time", [])),
    }
    (manifest_path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
