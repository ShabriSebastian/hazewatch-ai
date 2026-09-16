"""Append one published snapshot to the alert history.

Why this exists
---------------
The dashboard's Alert History screen used to be built by asking the replay
backend for `/alerts` at seven past timestamps. That worked because a replay
clock can be wound backwards. Live data has no past to query: a snapshot is one
observed instant, and `make refresh` overwrote the previous one.

So history has to be *accumulated* rather than queried. This script appends a
compact record per publish. It is called from `scripts/refresh_snapshot.sh`
immediately after a candidate passes the gate, which means the gate's
duplicate-skip (exit 2 when a candidate differs only by timestamps) already
prevents an unchanged snapshot from adding a record.

What it deliberately does NOT do
--------------------------------
It does not manufacture density. Refreshes are manual and irregular (see
DEVELOPMENT.md), so the history is a sparse list of moments someone happened to
publish, not a time series. Each record carries its own `generated_at` so the
dashboard can show the gaps between them honestly. Nothing here interpolates,
resamples or fills.

A full snapshot is ~84 KB and most of it - the 24-point forecast curves, the
hotspot grid, the provenance block - describes a forecast, not an outcome.
Keeping whole snapshots would add ~60 MB a year to the repository for data no
history screen reads, so only the fields the screen uses are retained.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA = 1

# Roughly a year at a couple of refreshes a week, or three months at two a day.
# The cap exists so the file stays reviewable in a git diff and bounded in the
# browser; it is not a statement about how long the data stays interesting.
MAX_RECORDS = 180

# The alert carries ~600 bytes of recommended actions and duplicated institution
# metadata that the history screen never reads. Only these fields are kept.
ALERT_FIELDS = (
    "alert_id",
    "severity",
    "status",
    "triggered_at",
    "forecast_peak_pm25",
    "forecast_peak_at",
    "lead_time_hours",
    "peak_lead_hours",
    "threshold_pm25",
    "threshold_crossed_at",
    "transboundary",
    "source_country",
)


def compact_alert(alert: dict | None) -> dict | None:
    if not alert:
        return None
    return {k: alert.get(k) for k in ALERT_FIELDS if k in alert}


def build_record(snapshot: dict) -> dict:
    institutions = {}
    for inst in snapshot.get("institutions", []):
        peak = inst.get("peak") or {}
        uncertainty = inst.get("uncertainty") or {}
        institutions[inst["institution_id"]] = {
            "observed_pm25": inst.get("observed_pm25"),
            "observed_category": inst.get("observed_category"),
            "peak_pm25_upper": peak.get("pm25_upper") or peak.get("pm25"),
            "peak_at": peak.get("timestamp"),
            "beyond_training_range": bool(
                uncertainty.get("any_point_beyond_training_range")
            ),
            "alert": compact_alert(inst.get("alert")),
        }

    return {
        "generated_at": snapshot["generated_at"],
        "issued_at": snapshot["issued_at"],
        "issued_offset_hours": snapshot.get("issued_offset_hours"),
        "model_version": snapshot.get("model_version"),
        "institutions": institutions,
    }


def load_history(path: Path) -> dict:
    if not path.exists():
        return {"schema": SCHEMA, "max_records": MAX_RECORDS, "records": []}
    with path.open() as fh:
        history = json.load(fh)
    history.setdefault("schema", SCHEMA)
    history.setdefault("max_records", MAX_RECORDS)
    history.setdefault("records", [])
    return history


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", required=True, help="the snapshot being published")
    ap.add_argument("--history", required=True, help="the history file to append to")
    ap.add_argument(
        "--max-records", type=int, default=MAX_RECORDS,
        help=f"retain at most this many records, newest first (default {MAX_RECORDS})",
    )
    args = ap.parse_args()

    snapshot_path, history_path = Path(args.snapshot), Path(args.history)
    with snapshot_path.open() as fh:
        snapshot = json.load(fh)

    if not snapshot.get("generated_at") or not snapshot.get("institutions"):
        print("Snapshot has no generated_at or no institutions. Not appending.")
        return 1

    history = load_history(history_path)
    record = build_record(snapshot)

    # Idempotent: re-running against the same published snapshot must not add a
    # second copy. The gate normally prevents this, but the script is also
    # runnable by hand and should be safe when it is.
    existing = {r.get("generated_at") for r in history["records"]}
    if record["generated_at"] in existing:
        print(f"Already recorded {record['generated_at']}. Nothing appended.")
        return 0

    history["records"].insert(0, record)
    history["records"].sort(key=lambda r: r.get("generated_at", ""), reverse=True)

    dropped = 0
    if len(history["records"]) > args.max_records:
        dropped = len(history["records"]) - args.max_records
        history["records"] = history["records"][: args.max_records]

    history["max_records"] = args.max_records
    history["schema"] = SCHEMA

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2) + "\n")

    alerting = sum(1 for i in record["institutions"].values() if i["alert"])
    span = ""
    if len(history["records"]) > 1:
        span = f", spanning {history['records'][-1]['generated_at']}..{history['records'][0]['generated_at']}"
    print(
        f"Recorded {record['generated_at']} ({alerting}/{len(record['institutions'])} "
        f"alerting). History now holds {len(history['records'])} record(s){span}."
        + (f" Dropped {dropped} past the {args.max_records} cap." if dropped else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
