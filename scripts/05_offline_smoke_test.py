#!/usr/bin/env python3
"""Pre-recording gate. Run this with Wi-Fi physically OFF before every take.

Blocks all network access at the socket layer, then exercises every endpoint at
every bookmark and asserts the demo's key claims still hold. If this passes with
the network disabled, the recorded demo cannot fail because of connectivity.

    python scripts/05_offline_smoke_test.py
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class NetworkBlocked(RuntimeError):
    pass


def _block_network() -> None:
    """Any outbound connection from here on is a bug, not a fallback."""

    def deny(*args, **kwargs):
        raise NetworkBlocked(
            "The demo attempted a network call. It must run entirely from "
            "precomputed data."
        )

    socket.socket.connect = deny  # type: ignore[method-assign]
    socket.create_connection = deny  # type: ignore[assignment]
    socket.getaddrinfo = deny  # type: ignore[assignment]


_block_network()

from fastapi.testclient import TestClient  # noqa: E402

from haze import config  # noqa: E402
from haze.api.main import app  # noqa: E402
from haze.institutions import INSTITUTIONS  # noqa: E402

MY_IDS = [i.id for i in INSTITUTIONS if i.country == "MY"]

client = TestClient(app)

failures: list[str] = []
checks = 0


def check(condition: bool, label: str) -> bool:
    global checks
    checks += 1
    if not condition:
        failures.append(label)
        print(f"    FAIL  {label}")
        return False
    return True


def get(path: str):
    response = client.get(path)
    check(response.status_code == 200, f"GET {path} -> {response.status_code}")
    return response.json() if response.status_code == 200 else {}


def check_warning_was_verified(institution_id: str, issued_at: str, label: str) -> None:
    """A warning shown on camera must be one that observation later confirmed.

    Without this the demo could headline a lead time that was simply a false
    alarm nobody checked - impressive on screen, indefensible under a question.
    """
    from datetime import timedelta

    from haze.alerts.thresholds import alert_threshold
    from haze.institutions import get as get_institution

    issued = config.parse_ts(issued_at)
    threshold = alert_threshold(get_institution(institution_id).type).pm25

    observed_peak = 0.0
    for lead in range(1, 25):
        at = config.iso(issued + timedelta(hours=lead))
        point = client.get(
            f"/api/v1/institutions/{institution_id}/observation?at={at}"
        )
        if point.status_code == 200:
            observed_peak = max(observed_peak, point.json()["pm25"])

    print(
        f"    observation confirms {observed_peak} ug/m3 within 24h "
        f"(threshold {threshold})"
    )
    check(
        observed_peak >= threshold,
        f"{label}: the warning must be one observation later confirmed "
        f"(peak {observed_peak} vs threshold {threshold})",
    )


def main() -> int:
    print("Network disabled. Running offline smoke test.\n")

    health = get("/api/v1/health")
    print(f"  mode={health.get('mode')}  data_source={health.get('data_source')}")
    if health.get("data_source") == "fixtures":
        print("  NOTE: serving fixtures, not the precomputed scenario.")
        print("        Run scripts/04_precompute_scenario.py before recording.\n")

    institutions = get("/api/v1/institutions")
    check(institutions.get("count") == len(INSTITUTIONS), "institution count")
    countries = {i["country"] for i in institutions.get("institutions", [])}
    check(countries == {"ID", "MY"}, f"both countries present (got {countries})")

    for bookmark in config.BOOKMARKS:
        key = bookmark["key"]
        print(f"\n  bookmark: {key}  ({bookmark['timestamp']})")
        response = client.post("/api/v1/replay/seek", json={"bookmark": key})
        if not check(response.status_code == 200, f"seek {key}"):
            continue

        hotspots = get("/api/v1/hotspots")
        print(f"    hotspots        {hotspots.get('total_available', 0):,} available")

        alerts = get("/api/v1/alerts")
        by_country: dict[str, int] = {}
        for alert in alerts.get("alerts", []):
            by_country[alert["country"]] = by_country.get(alert["country"], 0) + 1
        print(f"    active alerts   {alerts.get('count', 0)}  {by_country}")

        notifications = get("/api/v1/notifications?limit=5")
        print(f"    notifications   {notifications.get('count', 0)}")
        for n in notifications.get("notifications", [])[:1]:
            check(n.get("simulated") is True, "notifications flagged simulated")

        flagged_here = []
        for inst in INSTITUTIONS:
            forecast = get(f"/api/v1/institutions/{inst.id}/forecast")
            points = forecast.get("forecast", [])
            check(len(points) > 0, f"{inst.id} has forecast points at {key}")

            # The prediction band must be ordered wherever it is present. A
            # crossed band still draws a convincing-looking chart, so nothing
            # downstream would catch it.
            ordered = all(
                p["pm25_lower"] <= p["pm25"] <= p["pm25_upper"]
                and (p.get("pm25_p50") is None
                     or p["pm25_lower"] <= p["pm25_p50"] <= p["pm25_upper"])
                for p in points
                if p.get("pm25_lower") is not None and p.get("pm25_upper") is not None
            )
            check(ordered, f"{inst.id}: p10 <= p50/point <= p90 at {key}")

            if any(p.get("beyond_training_range") for p in points):
                flagged_here.append(inst.id)

        # Each bookmark makes a specific claim on camera. Assert the claim, not
        # merely that the endpoint returned something.
        if key == "calm":
            check(
                alerts.get("count", 0) == 0,
                "calm: baseline must be clear of alerts",
            )
            # A caveat that shows during clean air teaches the viewer to ignore
            # it, and by the severe bookmark it would carry no information.
            check(
                not flagged_here,
                f"calm: nothing beyond trained range (flagged {flagged_here})",
            )

        if key == "first_warning":
            my_alerts = get("/api/v1/alerts?country=MY")
            id_alerts = get("/api/v1/alerts?country=ID")
            check(
                my_alerts.get("count", 0) == 3,
                f"first_warning: all 3 Sarawak sites alerted (got {my_alerts.get('count')})",
            )
            check(
                id_alerts.get("count", 0) == 0,
                "first_warning: the point is that Sarawak is alerted and Indonesia is not",
            )
            transboundary = [a for a in my_alerts.get("alerts", []) if a["transboundary"]]
            check(
                len(transboundary) == 3,
                "first_warning: all Sarawak alerts attributed across the border",
            )
            check_warning_was_verified("my-kch-greenroad", bookmark["timestamp"], key)

        if key == "crossborder":
            kuching = get("/api/v1/institutions/my-kch-greenroad/forecast")
            attribution = kuching.get("attribution", {})
            peak = kuching.get("peak", {})
            print(
                f"    Kuching peak    {peak.get('pm25')} ug/m3 "
                f"({peak.get('aqi_category')}), transboundary="
                f"{attribution.get('transboundary')}, "
                f"source={attribution.get('source_country')}"
            )
            check(
                attribution.get("transboundary") is True,
                "crossborder: Kuching forecast is attributed across the border",
            )
            check(
                attribution.get("source_country") == "ID",
                "crossborder: source country is Indonesia",
            )
            check(
                by_country.get("ID", 0) > 0 and by_country.get("MY", 0) > 0,
                f"crossborder: both countries must be alerting (got {by_country})",
            )
            my_alerts = get("/api/v1/alerts?country=MY")
            if my_alerts.get("alerts"):
                lead = my_alerts["alerts"][0]["lead_time_hours"]
                print(f"    warning lead    {lead} h")
                check(lead >= 6, f"crossborder: lead time {lead}h is at least 6h")
            check_warning_was_verified("my-kch-greenroad", bookmark["timestamp"], key)

        if key == "severe":
            id_alerts = get("/api/v1/alerts?country=ID")
            check(
                id_alerts.get("count", 0) >= 3,
                "severe: all Pontianak institutions alerted",
            )
            worst = max(
                (a["forecast_peak_pm25"] for a in id_alerts.get("alerts", [])), default=0
            )
            print(f"    Pontianak peak  {worst} ug/m3")
            check(worst >= 55.5, f"severe: forecast reaches UNHEALTHY (got {worst})")
            # No lead-time assertion here. By this point Pontianak is inside the
            # episode, so the threshold crossing is imminent and a short lead is
            # the correct answer. This bookmark's claim is severity; lead time is
            # asserted on the two warning bookmarks, where it is the point.
            my_alerts = get("/api/v1/alerts?country=MY")
            check(
                my_alerts.get("count", 0) > 0,
                "severe: Sarawak is still alerted while Pontianak peaks",
            )

            # The honest caveat for the moment the demo is most exposed. Observed
            # PM2.5 reached 307 ug/m3 here and the forecast cannot say so, so the
            # payload must flag it rather than present a confident-looking number.
            pontianak = get("/api/v1/institutions/id-ptk-sman1/forecast")
            uncertainty = pontianak.get("uncertainty") or {}
            check(
                uncertainty.get("any_point_beyond_training_range") is True,
                "severe: Pontianak forecast flagged as beyond the trained range",
            )
            ceiling = uncertainty.get("model_ceiling_pm25")
            print(
                f"    model ceiling   {ceiling} ug/m3 "
                f"(training max {uncertainty.get('training_target_max_pm25')})"
            )
            band_peak = max(
                (p["pm25_upper"] for p in pontianak.get("forecast", [])), default=0
            )
            check(
                ceiling is not None and band_peak <= ceiling * 1.05,
                f"severe: upper band {band_peak} stays under the {ceiling} ceiling",
            )
            check(
                "id-ptk-sman1" in flagged_here and not (set(flagged_here) & set(MY_IDS)),
                f"severe: flag is specific to Pontianak (flagged {flagged_here})",
            )

    # Replay controls used live on camera.
    print("\n  replay controls")
    for path, payload in (
        ("/api/v1/replay/play", {"speed": 120}),
        ("/api/v1/replay/pause", None),
        ("/api/v1/replay/reset", None),
    ):
        response = client.post(path, json=payload) if payload else client.post(path)
        check(response.status_code == 200, f"POST {path}")

    response = client.post(
        "/api/v1/notifications/simulate", json={"institution_id": "my-kch-greenroad"}
    )
    check(response.status_code == 200, "POST /notifications/simulate")

    print(f"\n{'=' * 60}")
    if failures:
        print(f"FAILED: {len(failures)} of {checks} checks")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"PASSED: all {checks} checks, with no network access.")
    print("Safe to record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
