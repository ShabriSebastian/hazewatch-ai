"""The demo must work with no network. These tests enforce that.

`scripts/05_offline_smoke_test.py` is the interactive version run before
recording; this is the same guarantee wired into `make check`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from haze import config
from haze.api.main import app
from haze.institutions import INSTITUTIONS

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any outbound connection during a test is a failure, not a fallback."""
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("Network access attempted - the demo must run offline")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


def test_health_reports_a_data_source():
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["data_source"] in ("fixtures", "scenario_db")


def test_both_countries_are_represented():
    body = client.get("/api/v1/institutions").json()
    assert body["count"] == len(INSTITUTIONS)
    countries = {i["country"] for i in body["institutions"]}
    assert countries == {"ID", "MY"}, "the transboundary claim needs both sides"


@pytest.mark.parametrize("bookmark", [b["key"] for b in config.BOOKMARKS])
def test_every_bookmark_serves_a_full_dashboard(bookmark):
    assert client.post("/api/v1/replay/seek", json={"bookmark": bookmark}).status_code == 200

    assert client.get("/api/v1/hotspots").status_code == 200
    assert client.get("/api/v1/alerts").status_code == 200
    assert client.get("/api/v1/notifications").status_code == 200

    for inst in INSTITUTIONS:
        forecast = client.get(f"/api/v1/institutions/{inst.id}/forecast")
        assert forecast.status_code == 200, f"{inst.id} at {bookmark}"
        assert forecast.json()["forecast"], f"{inst.id} returned no points at {bookmark}"


def test_crossborder_bookmark_shows_transboundary_attribution():
    """The central claim of the product, asserted rather than hoped for."""
    client.post("/api/v1/replay/seek", json={"bookmark": "crossborder"})

    body = client.get("/api/v1/institutions/my-kch-greenroad/forecast").json()
    attribution = body["attribution"]
    assert attribution["transboundary"] is True
    assert attribution["source_country"] == "ID"

    alerts = client.get("/api/v1/alerts?country=MY").json()
    assert alerts["count"] > 0, "no Malaysian institution alerted at the crossborder bookmark"


def test_notifications_are_flagged_simulated():
    """An honesty requirement: nothing here actually sends a message."""
    client.post("/api/v1/replay/seek", json={"bookmark": "severe"})
    body = client.get("/api/v1/notifications?limit=10").json()
    for notification in body["notifications"]:
        assert notification["simulated"] is True


def test_pm25_provenance_is_labelled():
    """PM2.5 is CAMS reanalysis, not station measurement, and says so."""
    client.post("/api/v1/replay/seek", json={"bookmark": "severe"})
    body = client.get("/api/v1/institutions/id-ptk-sman1/forecast").json()
    assert body["current"]["source"] == "cams_reanalysis"


def test_replay_controls_are_usable_live():
    for path, payload in (
        ("/api/v1/replay/play", {"speed": 120}),
        ("/api/v1/replay/pause", None),
        ("/api/v1/replay/reset", None),
    ):
        response = client.post(path, json=payload) if payload else client.post(path)
        assert response.status_code == 200, path

    state = client.get("/api/v1/replay/state").json()
    assert state["clock"] == config.bookmark(config.DEFAULT_BOOKMARK)["timestamp"]
    assert state["playing"] is False


def test_unknown_institution_and_bookmark_are_404():
    assert client.get("/api/v1/institutions/nope/forecast").status_code == 404
    assert client.post("/api/v1/replay/seek", json={"bookmark": "nope"}).status_code == 404
