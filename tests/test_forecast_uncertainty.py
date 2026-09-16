"""The forecast band, and the flag that says when the band has run out of range.

The model cannot predict above its own structural ceiling - each tree returns an
average of training targets in a leaf, so no leaf offers an extreme. During the
September 2023 Pontianak episode the air reached 307 ug/m3 and the forecast tops
out near 90. That is a known limit, not a bug, and these tests pin the two things
the frontend needs in order to say so: a band derived from the trees, and a
boolean that is honest about when the number has become a floor.

The interesting assertions are the *pair*. A flag that is always true is useless,
and so is one that is always false. So the quiet bookmarks are checked as
carefully as the severe one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from haze import config
from haze.api.main import app
from haze.institutions import INSTITUTIONS
from haze.models import extrapolation

client = TestClient(app)

# The episode's worst moment, and the three institutions inside it.
SEVERE = "severe"
PONTIANAK = [i.id for i in INSTITUTIONS if i.country == "ID"]
KUCHING = [i.id for i in INSTITUTIONS if i.country == "MY"]

# Bookmarks where the air is ordinary and the model is comfortably in range.
CALM_BOOKMARKS = ["calm", "first_warning", "crossborder"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any outbound connection during a test is a failure, not a fallback."""
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("Network access attempted - the demo must run offline")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


def forecast_at(bookmark: str, institution_id: str, **params) -> dict:
    assert client.post("/api/v1/replay/seek", json={"bookmark": bookmark}).status_code == 200
    response = client.get(f"/api/v1/institutions/{institution_id}/forecast", params=params)
    assert response.status_code == 200, f"{institution_id} at {bookmark}"
    return response.json()


# --------------------------------------------------------------------------
# The band itself
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bookmark", [b["key"] for b in config.BOOKMARKS])
def test_band_is_ordered_at_every_point(bookmark):
    """p10 <= p50 <= p90, and the point forecast sits inside its own band.

    Percentiles that cross would mean the band was assembled wrongly - by far
    the most likely way this feature breaks silently, since a reversed band still
    renders as a perfectly plausible-looking chart.
    """
    for inst in INSTITUTIONS:
        body = forecast_at(bookmark, inst.id)
        for point in body["forecast"]:
            lower, median, upper = (
                point["pm25_lower"],
                point["pm25_p50"],
                point["pm25_upper"],
            )
            if lower is None or upper is None:
                continue
            where = f"{inst.id} at {bookmark} +{point['lead_hours']}h"
            assert lower <= upper, f"{where}: band inverted"
            if median is not None:
                assert lower <= median <= upper, f"{where}: p50 {median} outside band"
            assert lower <= point["pm25"] <= upper, f"{where}: point forecast outside band"


def test_band_semantics_are_published_not_assumed():
    """The frontend must not have to guess which percentiles the band is."""
    body = forecast_at(SEVERE, PONTIANAK[0])
    uncertainty = body["uncertainty"]
    assert uncertainty is not None, "no uncertainty block - was `make scenario` re-run?"

    assert uncertainty["method"] == extrapolation.METHOD
    assert uncertainty["lower_percentile"] == config.BAND_LOWER_PERCENTILE
    assert uncertainty["upper_percentile"] == config.ALERT_TRIGGER_PERCENTILE
    assert uncertainty["n_estimators"] == config.RF_N_ESTIMATORS
    assert uncertainty["note"].strip(), "the note is meant to be rendered as-is"


def test_published_ceilings_match_the_measured_model():
    """The API's ceilings are the ones measured off the served forest."""
    ranges = extrapolation.load_training_ranges()
    if ranges is None:
        pytest.skip("no training_ranges.json - run scripts/04_precompute_scenario.py")

    uncertainty = forecast_at(SEVERE, PONTIANAK[0])["uncertainty"]
    assert uncertainty["training_target_max_pm25"] == ranges["target_max_pm25"]
    assert uncertainty["model_ceiling_pm25"] == ranges["model_ceiling"]["mean_upper"]

    # The bound that actually binds is the model's, and it is the lower of the
    # two. If this ever inverts, the saturation rule is measuring the wrong thing.
    assert uncertainty["model_ceiling_pm25"] < uncertainty["training_target_max_pm25"]


# --------------------------------------------------------------------------
# Normal range: the flag must stay quiet
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bookmark", CALM_BOOKMARKS)
def test_ordinary_conditions_are_not_flagged(bookmark):
    """A flag that fires on ordinary air would train the frontend to ignore it."""
    for inst in INSTITUTIONS:
        body = forecast_at(bookmark, inst.id)
        flagged = [p for p in body["forecast"] if p["beyond_training_range"]]
        assert not flagged, (
            f"{inst.id} at {bookmark}: {len(flagged)} points flagged during "
            f"ordinary conditions"
        )
        for point in body["forecast"]:
            assert point["extrapolation_reason"] is None
        if body["uncertainty"]:
            assert body["uncertainty"]["any_point_beyond_training_range"] is False
            assert body["uncertainty"]["beyond_training_range_from_lead_hours"] is None


def test_normal_range_band_stays_well_below_the_ceiling():
    """At a calm moment the band should be nowhere near where the model gives out."""
    body = forecast_at("calm", KUCHING[0])
    uncertainty = body["uncertainty"]
    if uncertainty is None:
        pytest.skip("no uncertainty block - run scripts/04_precompute_scenario.py")

    widest = max(p["pm25_upper"] for p in body["forecast"])
    assert widest < 0.5 * uncertainty["model_ceiling_pm25"], (
        f"calm-air upper band reached {widest}, over half the model ceiling"
    )


# --------------------------------------------------------------------------
# The known extreme: Pontianak, September 2023
# --------------------------------------------------------------------------
@pytest.mark.parametrize("institution_id", PONTIANAK)
def test_pontianak_peak_is_flagged_as_beyond_the_trained_range(institution_id):
    """The case that motivated all of this.

    Observed PM2.5 reached 307 ug/m3. The forecast cannot say so, and the payload
    must admit it rather than presenting a confident-looking number.
    """
    body = forecast_at(SEVERE, institution_id)
    uncertainty = body["uncertainty"]
    assert uncertainty is not None, "no uncertainty block - was `make scenario` re-run?"

    assert uncertainty["any_point_beyond_training_range"] is True
    from_lead = uncertainty["beyond_training_range_from_lead_hours"]
    assert from_lead is not None and 1 <= from_lead <= config.FORECAST_HORIZON_HOURS

    flagged = [p for p in body["forecast"] if p["beyond_training_range"]]
    assert flagged, "expected the Pontianak peak to be flagged"
    assert all(p["extrapolation_reason"] is not None for p in flagged)

    # The band has to be pressed against the ceiling, which is what "saturated"
    # means. Anything much below it and the rule is firing for the wrong reason.
    ceiling = uncertainty["model_ceiling_pm25"]
    worst = max(p["pm25_upper"] for p in flagged)
    assert worst >= config.EXTRAPOLATION_SATURATION_FRACTION * ceiling * 0.95, (
        f"flagged points top out at {worst}, not near the {ceiling} ceiling"
    )

    # And the ceiling really is a ceiling: nothing may exceed it.
    assert worst <= ceiling * 1.05, f"upper band {worst} exceeded the model ceiling {ceiling}"


def test_the_flag_marks_a_floor_not_a_failure():
    """Alerting still works at the moment the forecast magnitude gives out.

    This is the whole argument of limitation #7: the model under-reads severity
    during extreme episodes but still crosses the alert threshold on time. If
    this ever fails, the flag has stopped being a caveat and become an excuse.
    """
    body = forecast_at(SEVERE, PONTIANAK[0])
    assert body["uncertainty"]["any_point_beyond_training_range"] is True

    alert = client.get(f"/api/v1/institutions/{PONTIANAK[0]}/alert").json()["alert"]
    assert alert is not None, "flagged as beyond range but raised no alert"
    assert alert["severity"] in ("UNHEALTHY_SENSITIVE", "UNHEALTHY", "VERY_UNHEALTHY",
                                "HAZARDOUS")


# An issuance during the run-up where the band climbs into saturation only at the
# very end of the horizon. Chosen because the inputs are still in range there, so
# it isolates the saturation signal from the feature-novelty one.
LATE_ONSET_AT = "2023-09-04T01:00:00Z"


def test_saturation_alone_can_raise_the_flag():
    """The two signals are independent, and this issuance exercises only one.

    At the severe bookmark the inputs are themselves unprecedented, so novelty
    fires and masks everything else. Here the inputs are ordinary and the band
    simply climbs into the ceiling near the end of the horizon.
    """
    body = client.get(
        f"/api/v1/institutions/{PONTIANAK[0]}/forecast", params={"at": LATE_ONSET_AT}
    ).json()
    flagged = [p for p in body["forecast"] if p["beyond_training_range"]]
    assert flagged, f"expected a late-horizon flag at {LATE_ONSET_AT}"
    assert all(p["extrapolation_reason"] == "band_saturated" for p in flagged)
    assert body["uncertainty"]["beyond_training_range_from_lead_hours"] > 1


def test_truncated_horizon_does_not_claim_saturation_it_did_not_return():
    """Asking for +12h must not inherit a flag earned at +24h.

    The stored block describes the full 24-hour issuance, so a shorter request
    has to have its summary rebuilt - otherwise the banner contradicts the points
    actually on the chart.
    """
    params = {"at": LATE_ONSET_AT}
    full = client.get(
        f"/api/v1/institutions/{PONTIANAK[0]}/forecast", params=params
    ).json()
    from_lead = full["uncertainty"]["beyond_training_range_from_lead_hours"]
    assert from_lead and from_lead > 1, "fixture no longer has a late-onset flag"

    short = client.get(
        f"/api/v1/institutions/{PONTIANAK[0]}/forecast",
        params={**params, "horizon_hours": from_lead - 1},
    ).json()
    assert short["uncertainty"]["any_point_beyond_training_range"] is False
    assert short["uncertainty"]["beyond_training_range_from_lead_hours"] is None
    assert not any(p["beyond_training_range"] for p in short["forecast"])
    assert "stays inside" in short["uncertainty"]["note"]


# --------------------------------------------------------------------------
# Contract shape
# --------------------------------------------------------------------------
def test_every_point_carries_the_new_keys():
    """Additive fields are only useful if they are always present to read."""
    body = forecast_at(SEVERE, PONTIANAK[0])
    required = {"pm25_p50", "beyond_training_range", "extrapolation_reason"}
    for point in [*body["forecast"], body["peak"]]:
        assert required <= set(point), f"missing {required - set(point)}"
    assert isinstance(body["peak"]["beyond_training_range"], bool)
