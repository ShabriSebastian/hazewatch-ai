"""Generate the dashboard's coastline from Natural Earth.

Why this exists
---------------
The regional map used to draw real data — institution markers and gridded hotspot
cells, both placed by `project()` — on top of a basemap that was two CSS blobs and
four text labels positioned by eye. The two layers had no relationship to each
other, which is why hotspots appeared to sit in the sea: the sea was a rounded div.
Kuching's label sat 37 points from where its own coordinates project to.

This script replaces that basemap with the real coastline, run through the same
projection the data uses, so there is exactly one coordinate system on the map.

Data source
-----------
`ne_10m_land.geojson` from the official Natural Earth vector repository,
https://github.com/nvkelso/natural-earth-vector (1:10m physical, "land").

Natural Earth is **public domain** — no permission needed, no attribution legally
required. Their terms ask only that they not be held liable and that the
contributors be credited where practical, which the generated file's header does.

Filled polygons rather than `ne_10m_coastline`, which is linestrings: the map needs
a landmass to fill, not an outline to stroke.

What it does NOT do
-------------------
No geo library. The venv has no shapely, geopandas, fiona or pyproj, and adding
~200 MB of dependencies for one build-time script is not worth it when the two
algorithms needed are short and exact for this case:

  * clipping is Sutherland–Hodgman, which is correct for any convex clip region,
    and a bounding box is convex;
  * simplification is Douglas–Peucker.

Nothing ships to the browser but a path string. There is no runtime GeoJSON
parsing and no map library in the bundle.

    python scripts/15_build_basemap.py
    python scripts/15_build_basemap.py --tolerance 0.01 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haze import config  # noqa: E402
from haze.institutions import INSTITUTIONS  # noqa: E402

SOURCES = {
    "land": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson",
    "minor_islands": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_minor_islands.geojson",
}

# The true combined extent of the two regions the map claims to show:
# West Kalimantan reaches lat -3.05 (Ketapang and the southern peatlands) and
# Sarawak reaches lon 115.5 (Limbang) and lat 5.0. The previous box stopped at
# 108.4..113.2 / -1.0..3.3 and cut all three.
BBOX = (108.0, -3.05, 115.5, 5.0)  # lon_min, lat_min, lon_max, lat_max

# A ring smaller than this (in square degrees) is a speck at render size. Dropping
# them is most of the vertex saving and none of the recognisability.
MIN_RING_AREA = 0.0008

OUT_TS = Path("frontend/src/lib/ui/basemap.generated.ts")
CACHE = config.DATA / "raw" / "naturalearth"


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------
def fetch(name: str, url: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.geojson"
    if not path.exists():
        print(f"  downloading {name} ({url.rsplit('/', 1)[-1]}) …")
        req = urllib.request.Request(url, headers={"User-Agent": "hazewatch-basemap/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r, path.open("wb") as fh:
            fh.write(r.read())
    size = path.stat().st_size / 1_048_576
    print(f"  {name:14} {size:6.1f} MB  (cached at {path.relative_to(config.ROOT)})")
    with path.open() as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------
def rings_of(geometry: dict):
    """Every exterior ring in a Polygon or MultiPolygon.

    Interior rings (holes) are dropped: at this bbox and render size they are
    inland lakes a few pixels across, and keeping them would mean emitting a path
    with fill-rule handling for no visible gain.
    """
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind == "Polygon":
        yield coords[0]
    elif kind == "MultiPolygon":
        for poly in coords:
            yield poly[0]


def clip_to_bbox(ring, bbox):
    """Sutherland–Hodgman against a rectangle.

    Exact for a convex clip region. Clips against each of the four edges in turn;
    a ring entirely outside any edge disappears, which is what we want for the
    thousands of rings elsewhere in the world.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    edges = (
        ("x", lon_min, True), ("x", lon_max, False),
        ("y", lat_min, True), ("y", lat_max, False),
    )

    out = list(ring)
    for axis, bound, keep_greater in edges:
        if not out:
            return []
        idx = 0 if axis == "x" else 1
        inside = (lambda p: p[idx] >= bound) if keep_greater else (lambda p: p[idx] <= bound)

        clipped = []
        for i, curr in enumerate(out):
            prev = out[i - 1]
            curr_in, prev_in = inside(curr), inside(prev)
            if curr_in != prev_in:
                # Parametric intersection with the clip line.
                d = curr[idx] - prev[idx]
                t = 0.0 if d == 0 else (bound - prev[idx]) / d
                clipped.append((
                    prev[0] + t * (curr[0] - prev[0]),
                    prev[1] + t * (curr[1] - prev[1]),
                ))
            if curr_in:
                clipped.append((curr[0], curr[1]))
        out = clipped
    return out


def ring_area(ring) -> float:
    """Shoelace, absolute. Square degrees — only ever compared against itself."""
    if len(ring) < 3:
        return 0.0
    s = sum(ring[i][0] * ring[i - 1][1] - ring[i - 1][0] * ring[i][1]
            for i in range(len(ring)))
    return abs(s) / 2.0


def simplify(points, tolerance: float):
    """Douglas–Peucker, iterative so a long coastline cannot blow the stack."""
    if len(points) < 3:
        return list(points)

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        ax, ay = points[first]
        bx, by = points[last]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5

        worst_i, worst_d = -1, 0.0
        for i in range(first + 1, last):
            px, py = points[i]
            if norm == 0:
                d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:
                d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if d > worst_d:
                worst_i, worst_d = i, d

        if worst_d > tolerance:
            keep[worst_i] = True
            stack.append((first, worst_i))
            stack.append((worst_i, last))

    return [p for p, k in zip(points, keep) if k]


# --------------------------------------------------------------------------
# Projection — the SAME maths the component uses
# --------------------------------------------------------------------------
def project(lon: float, lat: float):
    """Equirectangular into 0..100 percentage space.

    Must stay identical to `project()` in frontend/src/lib/ui/basemap.ts. The whole
    point of this script is that the coastline, the hotspot cells, the institution
    markers and the labels all come out of one projection.
    """
    lon_min, lat_min, lon_max, lat_max = BBOX
    x = (lon - lon_min) / (lon_max - lon_min) * 100.0
    y = (1.0 - (lat - lat_min) / (lat_max - lat_min)) * 100.0
    return x, y


def to_path(rings, decimals: int = 2) -> str:
    parts = []
    for ring in rings:
        pts = [project(lon, lat) for lon, lat in ring]
        head = f"M{pts[0][0]:.{decimals}f},{pts[0][1]:.{decimals}f}"
        tail = "".join(f"L{x:.{decimals}f},{y:.{decimals}f}" for x, y in pts[1:])
        parts.append(head + tail + "Z")
    return "".join(parts)


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tolerance", type=float, default=0.012,
                    help="Douglas-Peucker tolerance in degrees (default 0.012)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report counts without writing the .ts file")
    args = ap.parse_args()

    print("HazeWatch basemap")
    print("=" * 64)
    print("\nSource (Natural Earth 1:10m, public domain):")
    collections = {name: fetch(name, url) for name, url in SOURCES.items()}

    print(f"\nClipping to bbox lon {BBOX[0]}..{BBOX[2]}, lat {BBOX[1]}..{BBOX[3]}")
    raw_vertices = kept_rings = dropped_specks = 0
    clipped = []

    for name, fc in collections.items():
        before = len(clipped)
        for feature in fc["features"]:
            for ring in rings_of(feature["geometry"]):
                # Cheap reject: skip rings whose own extent misses the bbox entirely.
                lons = [p[0] for p in ring]
                lats = [p[1] for p in ring]
                if max(lons) < BBOX[0] or min(lons) > BBOX[2]:
                    continue
                if max(lats) < BBOX[1] or min(lats) > BBOX[3]:
                    continue

                raw_vertices += len(ring)
                cut = clip_to_bbox(ring, BBOX)
                if len(cut) < 3:
                    continue
                if ring_area(cut) < MIN_RING_AREA:
                    dropped_specks += 1
                    continue
                clipped.append(cut)
        print(f"  {name:14} contributed {len(clipped) - before} ring(s)")

    kept_rings = len(clipped)
    clipped_vertices = sum(len(r) for r in clipped)
    print(f"\n  rings kept            {kept_rings}")
    print(f"  specks dropped        {dropped_specks}  (area < {MIN_RING_AREA} sq deg)")
    print(f"  vertices before clip  {raw_vertices:,}")
    print(f"  vertices after clip   {clipped_vertices:,}")

    simplified = []
    for ring in clipped:
        s = simplify(ring, args.tolerance)
        if len(s) >= 3 and ring_area(s) >= MIN_RING_AREA:
            simplified.append(s)

    final_vertices = sum(len(r) for r in simplified)
    print(f"  vertices after simplify {final_vertices:,}  (tolerance {args.tolerance} deg)")
    print(f"  reduction               {100 * (1 - final_vertices / max(1, clipped_vertices)):.1f}%")

    # `ne_10m_land` and `ne_10m_minor_islands` overlap: several small islands are
    # carried by both, and drawing a ring twice is wasted bytes at best and a
    # visible seam where the strokes double up at worst.
    seen, deduped = set(), []
    for ring in simplified:
        key = tuple(round(c, 4) for p in ring for c in p)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ring)
    if len(deduped) != len(simplified):
        print(f"  duplicate rings dropped  {len(simplified) - len(deduped)}"
              f"  (islands carried by both source layers)")
    simplified = deduped
    final_vertices = sum(len(r) for r in simplified)

    simplified.sort(key=ring_area, reverse=True)
    path = to_path(simplified)
    print(f"\n  path length           {len(path):,} chars")

    # -- labels ------------------------------------------------------------
    by_city = {}
    for inst in INSTITUTIONS:
        by_city.setdefault(inst.city, []).append(inst)

    cities = {}
    for city, members in by_city.items():
        lat = sum(i.lat for i in members) / len(members)
        lon = sum(i.lon for i in members) / len(members)
        cities[city] = (lon, lat)

    # Interior points for the two region labels. Chosen inland rather than as a
    # true centroid: a centroid of West Kalimantan lands near the coast, and a
    # label there collides with the city markers.
    regions = {
        "WEST KALIMANTAN": (111.0, -1.4),
        "SARAWAK": (113.4, 2.6),
    }

    print("\nProjected label points (percentage space):")
    for name, (lon, lat) in {**regions, **{k: v for k, v in cities.items()}}.items():
        x, y = project(lon, lat)
        print(f"  {name:16} lon {lon:8.4f} lat {lat:7.4f}  ->  x {x:5.1f}%  y {y:5.1f}%")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    # -- emit --------------------------------------------------------------
    def ts_points(d):
        return "\n".join(
            f'  {json.dumps(k)}: {{ lon: {v[0]}, lat: {v[1]}, '
            f'x: {project(*v)[0]:.2f}, y: {project(*v)[1]:.2f} }},'
            for k, v in d.items()
        )

    aspect = f'{(BBOX[2] - BBOX[0]) * 1000:.0f}/{(BBOX[3] - BBOX[1]) * 1000:.0f}'
    bbox = BBOX
    ts = f'''// GENERATED by scripts/15_build_basemap.py — do not edit by hand.
//
// Coastline derived from Natural Earth 1:10m "land" (ne_10m_land), from
// https://github.com/nvkelso/natural-earth-vector
//
// Natural Earth is in the public domain: no permission is required and no
// attribution is legally required. Credited here because the project asks that
// its contributors be acknowledged where practical, and because a reader should
// be able to see where the geometry came from.
//
// Clipped to lon {BBOX[0]}..{BBOX[2]}, lat {BBOX[1]}..{BBOX[3]} and simplified
// (Douglas-Peucker, {args.tolerance} deg) from {clipped_vertices:,} vertices to
// {final_vertices:,} across {len(simplified)} ring(s).
//
// Coordinates are percentages of the map box, produced by the same projection as
// `project()` in ./basemap.ts. Regenerate with:  make basemap

/**
 * The map's bounding box: the true combined extent of West Kalimantan and
 * Sarawak. Emitted here rather than written in basemap.ts so the coastline and
 * the projection cannot drift apart - this file and the path below come from
 * the same run of the same script.
 */
export const MAP_BBOX = {{
  lonMin: {bbox[0]},
  latMin: {bbox[1]},
  lonMax: {bbox[2]},
  latMax: {bbox[3]},
}} as const;

/**
 * Width / height the map container must have for the projection to be
 * undistorted. At this latitude a degree of longitude and a degree of latitude
 * are the same distance, so the box's own ratio is the one to render at.
 */
export const MAP_ASPECT = "{aspect}";

/** Every landmass ring inside the map's bounding box, as one SVG path. */
export const COASTLINE_PATH =
  "{path}";

/** Label anchors, projected identically to the coastline and the data. */
export const REGION_LABELS = {{
{ts_points(regions)}
}} as const;

export const CITY_LABELS = {{
{ts_points(cities)}
}} as const;
'''

    out = config.ROOT / OUT_TS
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ts)
    print(f"\nWrote {OUT_TS}  ({len(ts):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
