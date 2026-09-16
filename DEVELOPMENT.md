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
