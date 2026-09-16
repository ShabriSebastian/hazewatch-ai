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
