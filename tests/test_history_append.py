"""The alert history appender.

The history is the only record of what the system said at moments that have
passed, so a record that misstates one is worse than no record at all. These
tests pin the two properties that matter: a record says what the snapshot said,
and appending the same snapshot twice does not invent a second observation.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "09_append_history.py"


def load_appender():
    spec = importlib.util.spec_from_file_location("append_history", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


appender = load_appender()


def institution(beyond_points: int, uncertainty: dict | None, total: int = 24) -> dict:
    return {
        "institution_id": "id-ptk-sman1",
        "observed_pm25": 50.3,
        "observed_category": "UNHEALTHY_SENSITIVE",
        "peak": {"pm25_upper": 68.2, "pm25": 45.9, "timestamp": "2026-09-15T13:00:00Z"},
        "forecast": [
            {"lead_hours": n + 1, "beyond_training_range": n < beyond_points}
            for n in range(total)
        ],
        "uncertainty": uncertainty,
        "alert": None,
    }


def snapshot(institutions: list[dict]) -> dict:
    return {
        "generated_at": "2026-09-16T00:45:54Z",
        "issued_at": "2026-09-15T12:00:00Z",
        "issued_offset_hours": -12,
        "model_version": "1.0.0",
        "institutions": institutions,
    }


# --------------------------------------------------------------------------
# beyond_training_range must not be a silent false negative
# --------------------------------------------------------------------------
def test_summary_block_is_used_when_present():
    inst = institution(24, {"any_point_beyond_training_range": True})
    assert appender.beyond_training_range(inst) is True


def test_falls_back_to_the_points_when_there_is_no_summary_block():
    """A snapshot published before the `uncertainty` block existed still carries
    the per-point flags. Reading only the summary recorded `false` for a forecast
    whose every point was flagged, which is the exact false negative this history
    must never contain.
    """
    inst = institution(24, uncertainty=None)
    assert appender.beyond_training_range(inst) is True

    inst_empty_block = institution(24, uncertainty={})
    assert appender.beyond_training_range(inst_empty_block) is True


def test_an_in_range_forecast_is_not_flagged_either_way():
    assert appender.beyond_training_range(institution(0, None)) is False
    assert appender.beyond_training_range(
        institution(0, {"any_point_beyond_training_range": False})
    ) is False


def test_one_flagged_point_is_enough():
    assert appender.beyond_training_range(institution(1, None)) is True


def test_the_summary_block_wins_when_the_two_disagree():
    """The block is rebuilt from the points it describes, so if it says `false`
    while a point says `true`, the points belong to a different horizon. Trust
    the block, which is what the dashboard renders.
    """
    inst = institution(24, {"any_point_beyond_training_range": False})
    assert appender.beyond_training_range(inst) is False


# --------------------------------------------------------------------------
# Records describe the snapshot, and only the snapshot
# --------------------------------------------------------------------------
def test_record_carries_the_snapshot_identity(tmp_path):
    record = appender.build_record(snapshot([institution(0, None)]))
    assert record["generated_at"] == "2026-09-16T00:45:54Z"
    assert record["issued_at"] == "2026-09-15T12:00:00Z"
    assert set(record["institutions"]) == {"id-ptk-sman1"}


def test_build_record_applies_the_fallback_not_just_the_helper():
    """`build_record` must reach the fallback, not merely be able to.

    `beyond_training_range` is tested directly above, but a regression that
    inlined the old summary-only lookup back into `build_record` would leave that
    test passing. This asserts the record itself, from a constructed snapshot
    with flagged points and no `uncertainty` block.

    Constructed rather than borrowed from `data/live/latest.json`: the published
    snapshot happens to predate the block today, so it would cover this path by
    accident — and stop the moment it is refreshed.
    """
    record = appender.build_record(snapshot([institution(24, uncertainty=None)]))
    assert record["institutions"]["id-ptk-sman1"]["beyond_training_range"] is True


def test_build_record_handles_a_mix_of_old_and_new_institutions():
    """Each institution is resolved on its own terms.

    A snapshot can carry both shapes - anything hand-assembled, or a future
    pipeline that emits the block only where it has one - and one institution's
    missing block must not decide another's answer.
    """
    with_block = dict(institution(0, {"any_point_beyond_training_range": True}))
    with_block["institution_id"] = "my-kch-greenroad"
    without_block = dict(institution(24, uncertainty=None))
    without_block["institution_id"] = "id-ptk-sman1"
    in_range = dict(institution(0, uncertainty=None))
    in_range["institution_id"] = "my-kch-hus"

    record = appender.build_record(snapshot([with_block, without_block, in_range]))
    states = record["institutions"]

    assert states["my-kch-greenroad"]["beyond_training_range"] is True, "summary block ignored"
    assert states["id-ptk-sman1"]["beyond_training_range"] is True, "fallback not applied"
    assert states["my-kch-hus"]["beyond_training_range"] is False, "flagged without cause"


def test_append_preserves_the_fallback_end_to_end(monkeypatch, tmp_path):
    """The whole path: a snapshot file with no `uncertainty` block, through the
    script's entry point, into the written history.

    This is the shape `refresh_snapshot.sh` invokes, so it is the one that has to
    hold. Asserted against the file on disk rather than a return value, because
    the file is what ships.
    """
    history = tmp_path / "history.json"
    snap = tmp_path / "snap.json"
    body = snapshot([institution(24, uncertainty=None)])
    assert body["institutions"][0]["uncertainty"] is None, "fixture must carry no block"
    assert all(p["beyond_training_range"] for p in body["institutions"][0]["forecast"])
    snap.write_text(json.dumps(body))

    assert run(monkeypatch, snap, history) == 0

    written = json.loads(history.read_text())["records"][0]
    assert written["institutions"]["id-ptk-sman1"]["beyond_training_range"] is True, (
        "a forecast flagged on every point was written to history as in-range"
    )


def run(monkeypatch, snapshot_path: Path, history_path: Path, max_records: int | None = None):
    """Drive the script's real entry point, as refresh_snapshot.sh does."""
    argv = ["09_append_history.py", "--snapshot", str(snapshot_path),
            "--history", str(history_path)]
    if max_records is not None:
        argv += ["--max-records", str(max_records)]
    monkeypatch.setattr("sys.argv", argv)
    return appender.main()


def write_snapshot(path: Path, generated_at: str) -> Path:
    body = snapshot([institution(0, None)])
    body["generated_at"] = generated_at
    path.write_text(json.dumps(body))
    return path


def test_appending_the_same_snapshot_twice_records_it_once(monkeypatch, tmp_path):
    """Publishing is gated on a snapshot having changed, but the appender is
    runnable by hand and must not be able to invent an observation.
    """
    history = tmp_path / "history.json"
    snap = write_snapshot(tmp_path / "snap.json", "2026-09-16T00:45:54Z")

    assert run(monkeypatch, snap, history) == 0
    assert run(monkeypatch, snap, history) == 0
    assert run(monkeypatch, snap, history) == 0

    records = json.loads(history.read_text())["records"]
    assert len(records) == 1, "the same publication was recorded more than once"
    assert records[0]["generated_at"] == "2026-09-16T00:45:54Z"


def test_distinct_publications_accumulate_newest_first(monkeypatch, tmp_path):
    history = tmp_path / "history.json"
    for stamp in ("2026-09-14T00:00:00Z", "2026-09-16T00:00:00Z", "2026-09-15T00:00:00Z"):
        run(monkeypatch, write_snapshot(tmp_path / f"{stamp}.json", stamp), history)

    stamps = [r["generated_at"] for r in json.loads(history.read_text())["records"]]
    assert stamps == [
        "2026-09-16T00:00:00Z",
        "2026-09-15T00:00:00Z",
        "2026-09-14T00:00:00Z",
    ]


def test_retention_drops_the_oldest(monkeypatch, tmp_path):
    history = tmp_path / "history.json"
    for stamp in ("2026-09-14T00:00:00Z", "2026-09-15T00:00:00Z", "2026-09-16T00:00:00Z"):
        run(monkeypatch, write_snapshot(tmp_path / f"{stamp}.json", stamp), history, max_records=2)

    stamps = [r["generated_at"] for r in json.loads(history.read_text())["records"]]
    assert stamps == ["2026-09-16T00:00:00Z", "2026-09-15T00:00:00Z"]


def test_a_snapshot_with_no_institutions_is_refused(monkeypatch, tmp_path):
    """Refusing to record is the right failure: refresh_snapshot.sh treats a
    non-zero exit as a reason not to commit anything at all.
    """
    history = tmp_path / "history.json"
    snap = tmp_path / "empty.json"
    snap.write_text(json.dumps({"generated_at": "2026-09-16T00:00:00Z", "institutions": []}))

    assert run(monkeypatch, snap, history) == 1
    assert not history.exists()


# --------------------------------------------------------------------------
# The committed history must describe real publications
# --------------------------------------------------------------------------
def test_committed_history_matches_the_published_snapshot():
    """Every record in the shipped history must correspond to a published
    snapshot, and the newest must match the snapshot currently published.

    This is the guard against a synthetic or unpublished record reaching the
    repository: the dashboard's whole premise is that it shows only what was
    genuinely recorded.
    """
    history_path = ROOT / "data" / "live" / "history.json"
    latest_path = ROOT / "data" / "live" / "latest.json"
    if not history_path.exists() or not latest_path.exists():
        pytest.skip("no published snapshot or history in this checkout")

    history = json.loads(history_path.read_text())
    latest = json.loads(latest_path.read_text())

    assert history["records"], "history is present but empty"
    newest = history["records"][0]
    assert newest["generated_at"] == latest["generated_at"], (
        "the newest history record does not match the published snapshot - a "
        "record was appended for a snapshot that was never published"
    )

    expected = appender.build_record(latest)
    assert newest["institutions"] == expected["institutions"], (
        "the newest record disagrees with the snapshot it claims to describe"
    )

    stamps = [r["generated_at"] for r in history["records"]]
    assert stamps == sorted(stamps, reverse=True), "records are not newest-first"
    assert len(set(stamps)) == len(stamps), "duplicate observations recorded"
