"""Public TLC Parquet -> bounded-size, headerless CSV shards for Hadoop Streaming."""
import csv
import re
import zipfile
from datetime import UTC, datetime

import httpx
import pyarrow.parquet as pq
import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

from .config import COLUMNS, DATA, input_path
from .io import atomic_json, read_json, sha256

BASE = "https://d37ci6vzurychx.cloudfront.net"


def download(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    tmp = target.with_suffix(target.suffix + ".partial")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        with tmp.open("wb") as out:
            for chunk in response.iter_bytes(1024 * 1024):
                out.write(chunk)
    tmp.replace(target)


def zones():
    raw = DATA / "raw"
    target = DATA / "zones.geojson"
    if target.exists():
        return
    download(f"{BASE}/misc/taxi_zones.zip", raw / "taxi_zones.zip")
    download(f"{BASE}/misc/taxi_zone_lookup.csv", raw / "taxi_zone_lookup.csv")
    # Read members directly: no extraction of untrusted archive paths.
    with zipfile.ZipFile(raw / "taxi_zones.zip") as archive:
        members = {s: next(n for n in archive.namelist() if n.endswith(s))
                   for s in (".shp", ".shx", ".dbf", ".prj")}
        crs = CRS.from_wkt(archive.read(members[".prj"]).decode())
        project = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
        with archive.open(members[".shp"]) as shp, archive.open(members[".shx"]) as shx, \
                archive.open(members[".dbf"]) as dbf:
            reader = shapefile.Reader(shp=shp, shx=shx, dbf=dbf)
            features = []
            for record in reader.iterShapeRecords():
                props = record.record.as_dict()
                # Simplification is in source CRS (US survey feet), before reprojection.
                geom = transform(project, shape(record.shape.__geo_interface__).simplify(30))
                features.append({"type": "Feature", "geometry": mapping(geom), "properties": {
                    "id": int(props["LocationID"]), "name": props["zone"], "borough": props["borough"]
                }})
    atomic_json(target, {"type": "FeatureCollection", "features": features})


def ingest(month="2025-01", rows=0, shard_rows=100_000):
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", month):
        raise ValueError("month must be YYYY-MM")
    if rows < 0 or shard_rows < 1:
        raise ValueError("rows >= 0 and shard_rows >= 1 required")
    folder = input_path(month)
    manifest = folder / "manifest.json"
    if manifest.exists():
        old = read_json(manifest)
        if old["requested_rows"] != rows or old["shard_rows"] != shard_rows:
            raise ValueError("Existing dataset has a different size. Use another GEOFLOW_DATA directory.")
        for shard in old["shards"]:
            if sha256(folder / shard["name"]) != shard["sha256"]:
                raise ValueError(f"Shard corrupted: {shard['name']}")
        return old
    zones()
    url = f"{BASE}/trip-data/yellow_tripdata_{month}.parquet"
    raw = DATA / "raw" / f"yellow_tripdata_{month}.parquet"
    download(url, raw)
    table = pq.ParquetFile(raw)
    folder.mkdir(parents=True, exist_ok=True)
    shards, total = [], 0
    for idx, batch in enumerate(table.iter_batches(batch_size=shard_rows, columns=COLUMNS)):
        if rows and total >= rows:
            break
        if rows:
            batch = batch.slice(0, min(len(batch), rows - total))
        target = folder / f"part-{idx:05d}.csv"
        frame = batch.to_pandas()
        frame.to_csv(target, index=False, header=False, date_format="%Y-%m-%d %H:%M:%S",
                     quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        total += len(frame)
        shards.append({"name": target.name, "rows": len(frame), "sha256": sha256(target)})
    result = {"month": month, "source": url, "source_rows": table.metadata.num_rows,
              "source_bytes": raw.stat().st_size, "source_sha256": sha256(raw),
              "rows": total, "requested_rows": rows, "shard_rows": shard_rows, "shards": shards,
              "columns": COLUMNS, "sampling": "full month" if rows == 0 else "first N rows, not random",
              "created_at": datetime.now(UTC).isoformat()}
    atomic_json(manifest, result)
    return result
