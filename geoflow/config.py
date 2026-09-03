import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("GEOFLOW_DATA", ROOT / "data"))
RESULTS = DATA / "results"
MONTH = "2025-01"
COLUMNS = ["tpep_pickup_datetime", "tpep_dropoff_datetime", "PULocationID", "DOLocationID",
           "trip_distance", "total_amount"]


def input_path(month):
    return DATA / "input" / month
