#!/usr/bin/env python3
"""Download and cache every external input. The only network-dependent step.

Run once. Everything afterwards - feature building, training, scenario
precompute, the demo itself - reads from the local cache and works offline.

    python scripts/01_download.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haze import config  # noqa: E402
from haze.ingest import firms, weather  # noqa: E402
from haze.institutions import INSTITUTIONS  # noqa: E402


def download_hotspots() -> None:
    print("== FIRMS hotspot archives (no API key required) ==")
    ok = fail = 0
    for sensor in config.FIRMS_SENSORS:
        for year in config.FIRMS_YEARS:
            for country in config.FIRMS_COUNTRIES:
                got = firms.download(sensor, year, country)
                mark = "ok " if got else "FAIL"
                size = ""
                if got:
                    path = firms.local_path(sensor, year, country)
                    size = f"{path.stat().st_size / 1e6:.1f} MB"
                    ok += 1
                else:
                    fail += 1
                print(f"  [{mark}] {sensor:11s} {year} {country:10s} {size}")
    print(f"  -> {ok} archives cached, {fail} unavailable")


def download_point_series() -> None:
    print("\n== Open-Meteo: ERA5 weather + CAMS PM2.5 at institutions ==")
    for inst in INSTITUTIONS:
        w = weather.weather(inst.lat, inst.lon, config.HISTORY_START, config.HISTORY_END)
        a = weather.air_quality(inst.lat, inst.lon, config.HISTORY_START, config.HISTORY_END)
        pm = a["pm2_5"].dropna() if "pm2_5" in a else []
        coverage = f"{len(pm)} PM2.5 hours" if len(pm) else "NO PM2.5"
        peak = f", peak {pm.max():.0f} ug/m3" if len(pm) else ""
        print(f"  {inst.id:20s} {len(w):6d} weather hours, {coverage}{peak}")


def download_wind_grid() -> None:
    points = weather.wind_grid_points()
    print(f"\n== Open-Meteo: ERA5 wind on {len(points)} grid points over the fire domain ==")
    print("   (wind at the fires, not only at the receptor - needed by the UFEI kernel)")
    for i, (lat, lon) in enumerate(points, 1):
        weather.weather(lat, lon, config.HISTORY_START, config.HISTORY_END)
        if i % 20 == 0 or i == len(points):
            print(f"   {i}/{len(points)} cached")


def main() -> int:
    config.RAW_FIRMS.mkdir(parents=True, exist_ok=True)
    config.RAW_METEO.mkdir(parents=True, exist_ok=True)

    download_hotspots()
    download_point_series()
    download_wind_grid()

    print("\nAll inputs cached under data/raw/. The pipeline is now offline-capable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
