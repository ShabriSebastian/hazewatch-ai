#!/usr/bin/env python3
"""Build the hourly feature matrix from cached raw data. Runs offline.

    python scripts/02_build_features.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haze.features import build  # noqa: E402


def main() -> int:
    df = build.build_all()
    build.save(df)

    # A quick look at whether the signal we are betting on is actually present.
    import pandas as pd

    print("\nCorrelation of upwind fire exposure with PM2.5, by institution:")
    for inst_id, group in df.groupby("institution_id"):
        sub = group[["ufei_48h", "pm25"]].dropna()
        if len(sub) < 100:
            print(f"  {inst_id:20s} insufficient data")
            continue
        r = pd.Series(sub["ufei_48h"]).corr(pd.Series(sub["pm25"]))
        country = group["country"].iloc[0]
        print(f"  [{country}] {inst_id:20s} r = {r:+.3f}  (n={len(sub):,})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
