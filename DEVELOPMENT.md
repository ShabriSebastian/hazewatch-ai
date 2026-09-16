# Development notes

## Refresh cadence is manual, and that is deliberate

`make refresh` is run by hand. There is no scheduler, and there is no self-hosted
runner. This is a decision, not an outstanding task.

`.github/workflows/live-snapshot.yml` still carries a `workflow_dispatch` trigger, but
its `schedule:` block is commented out. The reason is recorded at the top of that file
and is worth repeating here, because it is not a problem more configuration can solve:
GitHub-hosted runners cannot reliably reach NASA FIRMS. Across four snapshot runs and
two probes, FIRMS failed from Azure IPs at the TCP layer — connect timeout, `rc=124` —
more often than it succeeded, while the same files download in about three seconds from
a residential connection. DNS, IPv6, User-Agent and file size were each tested and ruled
out. The most likely explanation is NASA throttling cloud egress.

So the publish path is: someone on a residential connection runs `make refresh`, which
generates a candidate, gates it, and commits `data/live/latest.json` to `main`.

### What this obliges the UI to do

The dashboard shows whatever was last published by hand. It is not a live feed, and it
must never imply that it is. Every surface that displays snapshot-derived data must make
the age of that data visible and unmissable:

- `generated_at` is shown prominently, not tucked into a footnote.
- Data older than `STALE_AFTER_HOURS` (6) is flagged explicitly, not merely displayed.
- Forecasts are issued for `now - issued_offset_hours` (default 12h), because the
  trailing hours of the satellite fire field are only partly populated. The UI says so.
- A missing or unreadable snapshot renders an explicit "data unavailable" state. It must
  never render blank — see the note on `fetchSnapshot` below.

This honesty is the product's framing, not a disclaimer bolted onto one panel. It was
already the treatment used by the below-fold `ProLiveSnapshot` panel; retiring the
replay promotes it app-wide.

### If this is ever revisited

Restoring an automated cadence needs the FIRMS fetch to run from a non-cloud IP — a
self-hosted runner, or a VPS in a residential range. Re-enabling the cron is a two-line
change in the workflow file once that host exists. Until then, assume manual.

## Mock mode has been removed

`NEXT_PUBLIC_HAZE_DATA_MODE=mock` and the three fixture modules behind it
(`lib/data/mock.ts`, `proMock.ts`, `proAlertHistoryMock.ts`) are gone.

It existed so the demo would survive the backend being asleep or unreachable on
a free tier. That failure mode retired with the backend: the dashboard now reads
one static file from a CDN. Keeping three fixture sets in step with a schema
that has to mirror the entire dashboard was a standing cost with no consumer —
mock mode was a build-time switch, never a fallback, so nothing in production
ever reached it.

`createLocalNotification` was the one thing in those modules that ran in every
mode, because Confirm & Send is simulated locally regardless of data source. It
now lives in `lib/data/notification.ts`.

For local work, generate a snapshot and point the app at it:

```bash
python scripts/07_live_snapshot.py --out frontend/public/dev-snapshot.json
echo 'NEXT_PUBLIC_HAZE_SNAPSHOT_URL=/dev-snapshot.json' > frontend/.env.local
cd frontend && npm run dev
```

Both that file and `.env.local` are gitignored.

## Alert history is accumulated, not queried

`data/live/history.json` holds one compact record per published snapshot,
appended by `scripts/09_append_history.py` from the publish stage of
`scripts/refresh_snapshot.sh`.

It works this way because there is no alternative. The replay backend could be
asked for `/alerts` at any past timestamp, so Alert History was built by firing
seven requests at seven offsets. Live data has no past to query — a snapshot is
one observed instant, and the refresh used to overwrite the previous one. So the
history has to be accumulated as it happens.

Two consequences the UI is required to honour:

- **The record is sparse and irregular.** Refreshes are manual. Two records may
  be twenty minutes or three weeks apart. Every entry carries its own
  `generated_at`, and the dashboard renders the interval between entries rather
  than letting adjacent rows imply continuity.
- **A gap is not "no alert".** It means nobody published then. The Alert History
  screen says this in as many words, because the alternative is a reader
  inferring calm air from an absence of entries.

Retention is the newest 180 records (`--max-records`), which keeps the file
reviewable in a diff and bounded in the browser. Records hold only the fields
the history screen reads — a full snapshot is ~84 KB, most of it forecast curves
and hotspot geometry that describe a prediction rather than an outcome.

The publish gate (`scripts/08_gate_snapshot.py`) exits 2 when a candidate
differs from the published one only by timestamps, so an unchanged snapshot
never reaches the append step. The appender is also idempotent by
`generated_at`, so running it by hand cannot double-record.

### Only published snapshots may be recorded

`data/live/history.json` is the record of what the dashboard actually showed.
Nothing else belongs in it — not a synthetic record, not a local pipeline run
that was never published, not a back-dated entry created to exercise the UI.

`tests/test_history_append.py::test_committed_history_matches_the_published_snapshot`
enforces this: the newest record must equal a record derived from
`data/live/latest.json`, records must be newest-first, and no `generated_at` may
repeat. A synthetic or unpublished entry fails the suite.

Two related things that are *not* history and must not be confused with it:

- `tests/fixtures/live_snapshot.json` — genuine pipeline output, trimmed to two
  institutions, **never published**. A test fixture pinning the shape the
  dashboard consumes.
- `frontend/public/dev-snapshot.json` and `dev-history.json` — local development
  files, gitignored, never committed or deployed. A back-dated record here is
  fine and expected: it is how the sparse-history UI gets exercised without
  waiting weeks for real gaps to accumulate.

## The API and its contract were retired

Much of the older documentation in this repository — `README.md`,
`SYSTEM_FLOW.md`, `USER_FLOW.md`, the diagnostics reports — describes a FastAPI
service, a frozen OpenAPI contract, and a September 2023 replay. None of those
exist any more. This section records why, because the volume of writing about
them would otherwise suggest they were lost rather than removed.

### What went

| Removed | What it was |
|---|---|
| `src/haze/api/` | 19 routes over the scenario database |
| `src/haze/replay/` | the SQLite store and the virtual replay clock |
| `data/replay/scenario_2023_sept.sqlite` | 11 MB, 288 hours × 6 institutions, precomputed |
| `api_contract/` | the frozen `openapi.json`, its changelog, and `CONTRACT.md` |
| `Dockerfile`, `DEPLOYMENT.md`, `.dockerignore` | how to deploy the API |
| `tests/test_contract.py`, `tests/test_offline.py` | 17 tests guarding the contract and the offline promise |
| `scripts/00_export_contract.py`, `scripts/05_offline_smoke_test.py` | contract export and the pre-recording gate |
| `scripts/04_precompute_scenario.py` | built the scenario database |
| `precompute.write_scenario`, `_notification`, `_epoch` | wrote rows into that database |
| Makefile `serve`, `contract`, `offline`, `scenario` | targets for all of the above |
| `fastapi`, `uvicorn`, `pydantic`, `httpx`, `openapi-typescript` | dependencies of a service that no longer exists |

### Why, rather than keeping it alongside live data

The backend could not have served live data. It was a read-only row server over
a precomputed scenario: it loaded no model, opened no socket, and the install
deliberately excluded `pandas`, `scikit-learn`, `pyarrow` and `joblib` so the
image stayed small. Offline-ness was enforced in CI. Pointing it at live data
would have meant reversing both of those guarantees and re-implementing, inside
a web service, the model run that `scripts/07_live_snapshot.py` already performs
offline. The architecture that survived — pipeline runs the model, publishes an
artifact, dashboard reads it — was already how the live path worked.

There was a designed seam for the alternative (`Store`, a five-method Protocol
in the retired `src/haze/api/store.py`). It went unused: every method was keyed
by a timestamp, so implementing it honestly would have required the very alert
history the replay could fake and live data cannot.

### What survived, and what it cost

`src/haze/pipeline/`, `models/`, `ingest/`, `features/` and `alerts/` are
untouched — `scripts/07_live_snapshot.py` depends on all of them.
`src/haze/pipeline/precompute.py` keeps its name but is now only the shared
builders for a forecast point and an attribution block.

The test suite went from 72 tests to 50. `tests/test_metrics.py` (38) was
unaffected. `tests/test_forecast_uncertainty.py` was **rewritten rather than
deleted**: it drove the retired forecast endpoint at scenario bookmarks, but the
code it covers — `extrapolation.summarise()` — became *more* load-bearing in the
move, since it now builds the `uncertainty` block every reliability surface in
the dashboard renders. It runs against `tests/fixtures/live_snapshot.json` and
against the summariser directly.

One assertion changed meaning in that rewrite and is worth knowing about. The
old test asserted a calm-air band stays below half the model ceiling, which held
only because it read a bookmark chosen for being calm. It is not the rule:
saturation fires at `EXTRAPOLATION_SATURATION_FRACTION` (0.85) of the measured
ceiling, and a band can sit well above half of it while honestly in range — the
committed fixture reaches 72% with the flag correctly quiet. The test now
asserts the actual invariant, in both directions, and holds for any snapshot.

The offline guarantee is **retired, not silently broken**. It protected a served
API that must never reach the network. The pipeline reaches the network by
design, so there is nothing left for that gate to assert. `make check` no longer
runs it. `tests/test_forecast_uncertainty.py` keeps the socket-denying fixture
for its own tests, so nothing under test there can quietly fetch live data.
