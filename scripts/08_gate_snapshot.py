"""Decide whether a freshly generated snapshot is fit to publish.

The circuit breaker for the scheduled job. A snapshot is published only if it
passes every gate; otherwise the previously published file stays exactly where
it is and keeps being served. The fallback is therefore the *absence* of an
action rather than a recovery path that itself has to work.

    python scripts/08_gate_snapshot.py --candidate new.json --published latest.json

Exit codes are what the workflow branches on:

    0  publish      candidate passed and differs meaningfully
    2  no-op        candidate passed but is unchanged; skip the commit, not a failure
    1  reject       candidate failed a gate; do not publish

The distinction between 1 and 2 matters. A no-op is the normal outcome when the
upstream fire data has not refreshed yet, and treating it as failure would make
a healthy system look broken every other run.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_INSTITUTIONS = 6
EXPECTED_LEADS = 24
MAX_PLAUSIBLE_PM25 = 1000.0
# How far in the past `generated_at` may sit before we assume the file is not
# actually from this run - generous, because a runner can be slow.
MAX_GENERATED_AGE_HOURS = 3.0

REQUIRED_TOP = ("data_source", "generated_at", "issued_at", "institutions")
REQUIRED_INST = (
    "institution_id", "institution_name", "observed_pm25", "forecast", "peak",
)


class Rejected(Exception):
    """A gate failed. The message is what gets printed to the workflow log."""


def _parse_iso(value: str, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        raise Rejected(f"{label} is not an ISO-8601 UTC timestamp: {value!r}")


def _finite(value, label: str) -> float:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Rejected(f"{label} is not a number: {value!r}")
    if math.isnan(value) or math.isinf(value):
        raise Rejected(f"{label} is NaN or infinite")
    return float(value)


def check_shape(snap: dict) -> None:
    for key in REQUIRED_TOP:
        if key not in snap:
            raise Rejected(f"missing top-level key {key!r}")

    if snap.get("data_source") != "live_nrt":
        raise Rejected(f"data_source is {snap.get('data_source')!r}, expected 'live_nrt'")

    institutions = snap["institutions"]
    if not isinstance(institutions, list) or len(institutions) != EXPECTED_INSTITUTIONS:
        raise Rejected(
            f"expected {EXPECTED_INSTITUTIONS} institutions, got "
            f"{len(institutions) if isinstance(institutions, list) else type(institutions)}"
        )

    seen: set[str] = set()
    for inst in institutions:
        for key in REQUIRED_INST:
            if key not in inst:
                raise Rejected(f"institution missing key {key!r}")
        iid = inst["institution_id"]
        if iid in seen:
            raise Rejected(f"duplicate institution {iid!r}")
        seen.add(iid)

        if len(inst["forecast"]) != EXPECTED_LEADS:
            raise Rejected(
                f"{iid}: expected {EXPECTED_LEADS} forecast points, got {len(inst['forecast'])}"
            )


def check_sanity(snap: dict, now: datetime) -> None:
    generated = _parse_iso(snap["generated_at"], "generated_at")
    age_h = (now - generated).total_seconds() / 3600.0
    if age_h > MAX_GENERATED_AGE_HOURS:
        raise Rejected(f"generated_at is {age_h:.1f}h old - not from this run")
    if age_h < -0.5:
        raise Rejected(f"generated_at is {-age_h:.1f}h in the future - clock problem")

    _parse_iso(snap["issued_at"], "issued_at")

    for inst in snap["institutions"]:
        iid = inst["institution_id"]
        observed = _finite(inst["observed_pm25"], f"{iid}.observed_pm25")
        if not 0.0 <= observed <= MAX_PLAUSIBLE_PM25:
            raise Rejected(f"{iid}: observed_pm25 {observed} outside 0..{MAX_PLAUSIBLE_PM25}")

        for point in inst["forecast"]:
            lead = point.get("lead_hours")
            pm25 = _finite(point.get("pm25"), f"{iid}+{lead}h pm25")
            if not 0.0 <= pm25 <= MAX_PLAUSIBLE_PM25:
                raise Rejected(f"{iid}+{lead}h: pm25 {pm25} outside 0..{MAX_PLAUSIBLE_PM25}")
            # The band may legitimately be absent, but if present it must be ordered:
            # a crossed band still draws a convincing chart, so nothing downstream
            # would catch it.
            lo, up = point.get("pm25_lower"), point.get("pm25_upper")
            if lo is not None and up is not None:
                lo_f = _finite(lo, f"{iid}+{lead}h pm25_lower")
                up_f = _finite(up, f"{iid}+{lead}h pm25_upper")
                if lo_f > up_f:
                    raise Rejected(f"{iid}+{lead}h: band crossed ({lo_f} > {up_f})")

    # A run where every site reads exactly zero is far more likely to be an
    # upstream outage returning empty series than genuinely clean air across
    # two countries during a haze event.
    if all(_finite(i["observed_pm25"], "observed") == 0.0 for i in snap["institutions"]):
        raise Rejected("every institution reports 0.0 - upstream data is probably empty")


def check_freshness(candidate: dict, published: dict | None) -> None:
    """A newer run must not publish an older forecast."""
    if published is None:
        return
    new_issued = _parse_iso(candidate["issued_at"], "candidate issued_at")
    try:
        old_issued = _parse_iso(published["issued_at"], "published issued_at")
    except Rejected:
        return  # published file is malformed; replacing it is an improvement
    if new_issued < old_issued:
        raise Rejected(
            f"candidate issued_at {candidate['issued_at']} is older than published "
            f"{published['issued_at']} - refusing to move the snapshot backwards"
        )


def _comparable(snap: dict) -> str:
    """The snapshot minus fields that change on every run regardless of data."""
    clone = json.loads(json.dumps(snap))
    clone.pop("generated_at", None)
    prov = clone.get("provenance")
    if isinstance(prov, dict):
        weather = prov.get("weather")
        if isinstance(weather, dict):
            weather.pop("window", None)
    return json.dumps(clone, sort_keys=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate", required=True, type=Path)
    ap.add_argument("--published", type=Path, default=None)
    args = ap.parse_args()

    try:
        candidate = json.loads(args.candidate.read_text())
    except Exception as exc:
        print(f"REJECT: candidate is not readable JSON: {exc}")
        return 1

    published = None
    if args.published and args.published.exists():
        try:
            published = json.loads(args.published.read_text())
        except Exception:
            print("note: published snapshot is unreadable; treating as absent")

    try:
        check_shape(candidate)
        check_sanity(candidate, datetime.now(timezone.utc))
        check_freshness(candidate, published)
    except Rejected as exc:
        print(f"REJECT: {exc}")
        print("The previously published snapshot stays in place and keeps being served.")
        return 1

    alerting = sum(1 for i in candidate["institutions"] if i.get("alert"))
    print(
        f"PASS: {len(candidate['institutions'])} institutions, "
        f"{EXPECTED_LEADS} leads each, {alerting} alerting, "
        f"issued {candidate['issued_at']}"
    )

    if published is not None and _comparable(candidate) == _comparable(published):
        print("NO-OP: identical to the published snapshot apart from timestamps.")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
