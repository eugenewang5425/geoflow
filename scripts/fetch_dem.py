"""Fetch NYC terrain DEM from public terrain tiles (Mapbox terrain-RGB, terrarium encoding).

Tiles: https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png
Elevation (terrarium): e = (R*256 + G + B/256) - 32768  (meters, SRTM-based).
Output: data/results/dem_grid.json (bbox-aligned block-mean grid for the 3D dashboard).
Attribution: Mapbox / OpenStreetMap contributors (terrain tiles).
"""
import io
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium"
Z = 11
TILE = 256
# NYC metro bounding box
LON_MIN, LON_MAX = -74.28, -73.62
LAT_MIN, LAT_MAX = 40.47, 40.95
GRID = 160  # final grid resolution (nx x ny)


def lon_to_x(lon, z):
    return int((lon + 180.0) / 360.0 * (1 << z))


def lat_to_y(lat, z):
    rad = math.radians(lat)
    return int((1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * (1 << z))


def lon_to_px(lon):
    """Global Web-Mercator pixel column at zoom Z."""
    return (lon + 180.0) / 360.0 * (1 << Z) * TILE


def lat_to_px(lat):
    """Global Web-Mercator pixel row at zoom Z (0 at north)."""
    rad = math.radians(lat)
    return (1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * (1 << Z) * TILE


def decode(img):
    import numpy as np
    arr = np.asarray(img.convert("RGBA"), dtype=float)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    return r * 256.0 + g + b / 256.0 - 32768.0


def main():
    x0, x1 = lon_to_x(LON_MIN, Z), lon_to_x(LON_MAX, Z)
    y0, y1 = lat_to_y(LAT_MAX, Z), lat_to_y(LAT_MIN, Z)
    tile_w = (x1 - x0 + 1) * 256
    tile_h = (y1 - y0 + 1) * 256
    canvas = Image.new("RGB", (tile_w, tile_h))
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                resp = client.get(f"{BASE}/{Z}/{x}/{y}.png")
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                canvas.paste(img, ((x - x0) * 256, (y - y0) * 256))
    elev = decode(canvas)
    # grid cells span the full bbox in degree space; canvas rows run north->south,
    # so a cell's pixel rect must be derived via Web Mercator, not by uniform stepping
    nx, ny = GRID, GRID
    lon_edges = [LON_MIN + (LON_MAX - LON_MIN) * k / nx for k in range(nx + 1)]
    lat_edges = [LAT_MIN + (LAT_MAX - LAT_MIN) * k / ny for k in range(ny + 1)]
    off_x, off_y = x0 * TILE, y0 * TILE

    def cell_cols(lon_lo, lon_hi):
        left = min(tile_w - 1, max(0, int(lon_to_px(lon_lo)) - off_x))
        right = min(tile_w, max(left + 1, int(lon_to_px(lon_hi)) - off_x))
        return left, right

    def cell_rows(lat_lo, lat_hi):  # north edge -> smaller canvas y
        top = min(tile_h - 1, max(0, int(lat_to_px(lat_hi)) - off_y))
        bottom = min(tile_h, max(top + 1, int(lat_to_px(lat_lo)) - off_y))
        return top, bottom

    grid = []
    for j in range(ny):  # rows follow lats, south -> north
        top, bottom = cell_rows(lat_edges[j], lat_edges[j + 1])
        row = []
        for i in range(nx):
            left, right = cell_cols(lon_edges[i], lon_edges[i + 1])
            v = float(elev[top:bottom, left:right].mean())
            row.append(round(max(0.0, v), 1))
        grid.append(row)
    lons = [round((lon_edges[i] + lon_edges[i + 1]) / 2, 4) for i in range(nx)]
    lats = [round((lat_edges[j] + lat_edges[j + 1]) / 2, 4) for j in range(ny)]
    out = {
        "source": "Mapbox terrain-RGB tiles (AWS elevation-tiles-prod, terrarium encoding)",
        "attribution": "© Mapbox © OpenStreetMap contributors",
        "z": Z, "tiles": [x0, x1, y0, y1],
        "bbox": [LON_MIN, LAT_MIN, LON_MAX, LAT_MAX],
        "nx": nx, "ny": ny, "lons": lons, "lats": lats,
        "grid": grid,
        "fetched_at": datetime.now(UTC).isoformat(),
    }
    target = ROOT / "data" / "results" / "dem_grid.json"
    target.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    provenance = {k: v for k, v in out.items() if k not in ("grid",)}
    provenance["grid_size_kb"] = round(target.stat().st_size / 1024, 1)
    (ROOT / "evidence" / "dem_provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    elev_min = min(min(r) for r in grid)
    elev_max = max(max(r) for r in grid)
    print(f"DEM ok: {nx}x{ny}, elev {elev_min}m..{elev_max}m, tiles={len(out['tiles'])}, grid_size_kb={provenance['grid_size_kb']}")


if __name__ == "__main__":
    main()
