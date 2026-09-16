"""The forecast band, and the flag that says when the band has run out of range.

The model cannot predict above its own structural ceiling - each tree returns an
average of training targets in a leaf, so no leaf offers an extreme. During the
September 2023 Pontianak episode the air reached 307 ug/m3 and the forecast tops
out near 90. That is a known limit, not a bug, and these tests pin the two things
the dashboard needs in order to say so: a band derived from the trees, and a
boolean that is honest about when the number has become a floor.

The interesting assertions are the *pair*. A flag that is always true is useless,
and so is one that is always false. So the in-range case is checked as carefully
as the saturated one.

**Rewritten when the replay backend was retired.** These tests used to drive
`GET /institutions/{id}/forecast` at named scenario bookmarks - the severe
Pontianak moment for the flag firing, the calm ones for it staying quiet. Both
the API and the scenario database are gone, so the same behaviour is now
exercised two ways:

  * against `extrapolation.summarise()` directly, which is the function that
    actually decides all of this and is now load-bearing for the live pipeline -
    `scripts/07_live_snapshot.py` calls it to build the `uncertainty` block that
    every reliability surface in the dashboard renders;
  * against `tests/fixtures/live_snapshot.json`, a real published snapshot,
    which pins the shape the dashboard consumes.

The severe-episode fixture could not survive the scenario database, so the
saturated case is now constructed by pressing synthetic points against the
measured ceiling. That tests the rule rather than one recorded afternoon, which
is the part that has to keep working.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from haze import config
from haze.models import extrapolation

FIXTURE = Path(__file__).parent / "fixtures" / "live_snapshot.json"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any outbound connection during a test is a failure, not a fallback.

    Kept from the retired offline suite. The pipeline reaches the network by
    design, but nothing under test here may, and a test that quietly fetched
    live data would be non-deterministic rather than merely slow.
    """
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("Network access attempted - these tests must run offline")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


@pytest.fixture(scope="module")
def snapshot() -> dict:
    assert FIXTURE.exists(), f"missing fixture {FIXTURE}"
    with FIXTURE.open() as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def ranges() -> dict:
    loaded = extrapolation.load_training_ranges()
    if not loaded:
        pytest.skip("no training_ranges.json - run scripts/03_train.py")
    return loaded


def points_pressed_to_ceiling(ranges: dict, from_lead: int = 6) -> list[dict]:
    """A forecast whose band climbs into the ceiling from `from_lead` onwards.

    Replaces the severe-bookmark fixture. Saturation is defined relative to the
    measured ceiling, so the points are built from that same measurement rather
    than from a hardcoded number that could drift away from the served forest.
    """
    from haze.pipeline import precompute

    built = []
    for lead in range(1, config.FORECAST_HORIZON_HOURS + 1):
        saturation = extrapolation.saturation_threshold(ranges, lead)
        assert saturation is not None, "no measured ceiling for this lead"
        if lead >= from_lead:
            upper = saturation * 1.02
            saturated = True
        else:
            upper = saturation * 0.25
            saturated = False
        beyond, reason = extrapolation.combine(saturated, novel=False)
        built.append(
            precompute._point(
                "2026-09-15T12:00:00Z",
                lead,
                pm25=upper * 0.6,
                lower=upper * 0.3,
                upper=upper,
                median=upper * 0.55,
                beyond_training_range=beyond,
                extrapolation_reason=reason,
            )
        )
    return built


# --------------------------------------------------------------------------
# The band itself
# --------------------------------------------------------------------------
def test_band_is_ordered_at_every_point(snapshot):
    """p10 <= p50 <= p90, and the point forecast sits inside its own band.

    Percentiles that cross would mean the band was assembled wrongly - by far
    the most likely way this feature breaks silently, since a reversed band still
    renders as a perfectly plausible-looking chart.
    """
    for record in snapshot["institutions"]:
        for point in record["forecast"]:
            lower, median, upper = (
                point["pm25_lower"],
                point["pm25_p50"],
                point["pm25_upper"],
            )
            if lower is None or upper is None:
                continue
            where = f"{record['institution_id']} +{point['lead_hours']}h"
            assert lower <= upper, f"{where}: band inverted"
            if median is not None:
                assert lower <= median <= upper, f"{where}: p50 {median} outside band"
            assert lower <= point["pm25"] <= upper, f"{where}: point forecast outside band"


def test_band_semantics_are_published_not_assumed(snapshot):
    """The dashboard must not have to guess which percentiles the band is."""
    for record in snapshot["institutions"]:
        uncertainty = record["uncertainty"]
        assert uncertainty, f"{record['institution_id']} carries no uncertainty block"

        assert uncertainty["method"] == extrapolation.METHOD
        assert uncertainty["lower_percentile"] == config.BAND_LOWER_PERCENTILE
        assert uncertainty["upper_percentile"] == config.ALERT_TRIGGER_PERCENTILE
        assert uncertainty["n_estimators"] == config.RF_N_ESTIMATORS
        assert uncertainty["note"].strip(), "the note is meant to be rendered as-is"


def test_published_ceilings_match_the_measured_model(snapshot, ranges):
    """The published ceilings are the ones measured off the served forest."""
    uncertainty = snapshot["institutions"][0]["uncertainty"]
    assert uncertainty["training_target_max_pm25"] == round(ranges["target_max_pm25"], 1)
    assert uncertainty["model_ceiling_pm25"] == ranges["model_ceiling"]["mean_upper"]

    # The bound that actually binds is the model's, and it is the lower of the
    # two. If this ever inverts, the saturation rule is measuring the wrong thing.
    assert uncertainty["model_ceiling_pm25"] < uncertainty["training_target_max_pm25"]


# --------------------------------------------------------------------------
# Normal range: the flag must stay quiet
# --------------------------------------------------------------------------
def test_ordinary_conditions_are_not_flagged(snapshot):
    """A flag that fires on ordinary air would train the reader to ignore it.

    The committed snapshot was taken on an ordinary day. If a future refresh of
    this fixture lands during a genuine extreme, this asserts the two halves
    agree rather than asserting the day was calm.
    """
    for record in snapshot["institutions"]:
        flagged = [p for p in record["forecast"] if p["beyond_training_range"]]
        uncertainty = record["uncertainty"]

        assert uncertainty["any_point_beyond_training_range"] is bool(flagged), (
            f"{record['institution_id']}: summary and points disagree"
        )
        if not flagged:
            assert all(p["extrapolation_reason"] is None for p in record["forecast"])
            assert uncertainty["beyond_training_range_from_lead_hours"] is None
            assert "stays inside" in uncertainty["note"]


def test_unflagged_points_are_genuinely_below_the_saturation_threshold(snapshot, ranges):
    """An unflagged point must actually be clear of the ceiling, not just called clear.

    The version of this test that ran against the replay asserted the band stayed
    under half the model ceiling, which held only because it read a bookmark
    chosen for being calm. It is not the rule: saturation fires at
    `EXTRAPOLATION_SATURATION_FRACTION` of the measured ceiling, and a band can
    sit well above half of it while still being honestly in range - the Pontianak
    record in this fixture reaches 72% of the ceiling with the flag correctly
    quiet.

    So this asserts the rule itself, which holds for any snapshot: every point
    the payload leaves unflagged is below the threshold for its own lead hour,
    and every point above it is flagged.
    """
    for record in snapshot["institutions"]:
        for point in record["forecast"]:
            threshold = extrapolation.saturation_threshold(ranges, point["lead_hours"])
            if threshold is None or point["pm25_upper"] is None:
                continue
            where = f"{record['institution_id']} +{point['lead_hours']}h"
            if point["pm25_upper"] >= threshold:
                assert point["beyond_training_range"], (
                    f"{where}: upper band {point['pm25_upper']} reached the "
                    f"{threshold:.1f} saturation threshold but was not flagged"
                )
            elif point["extrapolation_reason"] == "band_saturated":
                pytest.fail(
                    f"{where}: flagged as saturated at {point['pm25_upper']}, "
                    f"below the {threshold:.1f} threshold"
                )


# --------------------------------------------------------------------------
# The known extreme, reconstructed against the measured ceiling
# --------------------------------------------------------------------------
def test_saturated_band_is_flagged_as_beyond_the_trained_range(ranges):
    """The case that motivated all of this.

    Observed PM2.5 reached 307 ug/m3 during the September 2023 Pontianak episode.
    The forecast cannot say so, and the payload must admit it rather than
    presenting a confident-looking number.
    """
    points = points_pressed_to_ceiling(ranges, from_lead=6)
    uncertainty = extrapolation.summarise(points, ranges)

    assert uncertainty["any_point_beyond_training_range"] is True
    assert uncertainty["beyond_training_range_from_lead_hours"] == 6

    flagged = [p for p in points if p["beyond_training_range"]]
    assert flagged, "expected the saturated points to be flagged"
    assert all(p["extrapolation_reason"] == "band_saturated" for p in flagged)

    # The band has to be pressed against the ceiling, which is what "saturated"
    # means. Anything much below it and the rule is firing for the wrong reason.
    ceiling = uncertainty["model_ceiling_pm25"]
    worst = max(p["pm25_upper"] for p in flagged)
    assert worst >= config.EXTRAPOLATION_SATURATION_FRACTION * ceiling * 0.95, (
        f"flagged points top out at {worst}, not near the {ceiling} ceiling"
    )


def test_the_flag_marks_a_floor_not_a_failure(ranges):
    """Alerting still works at the moment the forecast magnitude gives out.

    This is the whole argument of limitation #7: the model under-reads severity
    during extreme episodes but still crosses the alert threshold on time. If
    this ever fails, the flag has stopped being a caveat and become an excuse.

    Driven through `rules.evaluate` rather than the retired alert endpoint - the
    same function the live pipeline calls.
    """
    from datetime import datetime, timezone

    from haze.alerts import rules
    from haze.institutions import INSTITUTIONS

    inst = next(i for i in INSTITUTIONS if i.country == "ID")
    points = points_pressed_to_ceiling(ranges, from_lead=6)

    assert extrapolation.summarise(points, ranges)["any_point_beyond_training_range"]

    alert = rules.evaluate(inst, datetime(2026, 9, 15, 12, tzinfo=timezone.utc), points, None)
    assert alert is not None, "flagged as beyond range but raised no alert"
    assert alert["severity"] in (
        "UNHEALTHY_SENSITIVE", "UNHEALTHY", "VERY_UNHEALTHY", "HAZARDOUS",
    )


def test_saturation_alone_can_raise_the_flag(ranges):
    """The two signals are independent, and this case exercises only one.

    During a genuine extreme the inputs are themselves unprecedented, so feature
    novelty fires and masks everything else. Here the inputs are ordinary and the
    band simply climbs into the ceiling near the end of the horizon.
    """
    points = points_pressed_to_ceiling(ranges, from_lead=20)
    uncertainty = extrapolation.summarise(points, ranges)

    flagged = [p for p in points if p["beyond_training_range"]]
    assert flagged, "expected a late-horizon flag"
    assert all(p["extrapolation_reason"] == "band_saturated" for p in flagged)
    assert uncertainty["beyond_training_range_from_lead_hours"] == 20


def test_truncated_horizon_does_not_claim_saturation_it_did_not_return(ranges):
    """Summarising +12h must not inherit a flag earned at +24h.

    A block describing the full 24-hour issuance has to be rebuilt for a shorter
    window - otherwise the banner contradicts the points actually on the chart.
    This is why `summarise` is called on the points being returned rather than
    stored once and reused.
    """
    points = points_pressed_to_ceiling(ranges, from_lead=20)
    full = extrapolation.summarise(points, ranges)
    from_lead = full["beyond_training_range_from_lead_hours"]
    assert from_lead and from_lead > 1, "fixture no longer has a late-onset flag"

    short = extrapolation.summarise(points[: from_lead - 1], ranges)
    assert short["any_point_beyond_training_range"] is False
    assert short["beyond_training_range_from_lead_hours"] is None
    assert "stays inside" in short["note"]


def test_novelty_and_saturation_combine_distinctly():
    """`combine` is what decides which reason a point carries."""
    assert extrapolation.combine(False, False) == (False, None)
    assert extrapolation.combine(True, False)[1] == "band_saturated"
    assert extrapolation.combine(False, True)[1] == "feature_out_of_range"
    assert extrapolation.combine(True, True)[1] == "both"
    assert all(extrapolation.combine(s, n)[0] for s, n in
               [(True, False), (False, True), (True, True)])


# --------------------------------------------------------------------------
# The shape the dashboard consumes
# --------------------------------------------------------------------------
def test_every_point_carries_the_keys_the_dashboard_reads(snapshot):
    """Additive fields are only useful if they are always present to read."""
    required = {"pm25_p50", "beyond_training_range", "extrapolation_reason"}
    for record in snapshot["institutions"]:
        for point in [*record["forecast"], record["peak"]]:
            assert required <= set(point), f"missing {required - set(point)}"
        assert isinstance(record["peak"]["beyond_training_range"], bool)


def test_snapshot_carries_what_the_reliability_surfaces_render(snapshot):
    """The blocks the dashboard needs, on every institution.

    These moved into the snapshot when the API was retired; without them every
    main-body reliability surface silently renders nothing, which is the failure
    this asserts against.
    """
    for record in snapshot["institutions"]:
        where = record["institution_id"]
        assert record["uncertainty"], f"{where}: no uncertainty block"
        assert "any_point_beyond_training_range" in record["uncertainty"], where
        assert record["attribution"], f"{where}: no attribution block"
        assert record["current"]["pm25"] is not None, f"{where}: no current observation"
        assert isinstance(record["institution"]["lat"], (int, float)), f"{where}: no lat"
        assert isinstance(record["institution"]["lon"], (int, float)), f"{where}: no lon"
        # The map projects from these, and the full record is also the only
        # source of admin_region / languages / recipient_group now.
        for field in ("admin_region", "languages", "recipient_group"):
            assert record["institution"].get(field), f"{where}: no {field}"
