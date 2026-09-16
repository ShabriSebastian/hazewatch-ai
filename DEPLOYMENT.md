# Deployment

The API is a read-only service over a precomputed scenario. It loads no model, opens no
socket to anything external, and answers a forecast in about a millisecond. That makes it
cheap to host — but there are three things that will bite if they are missed, so they are
first.

## Three things that matter

**1. The scenario database must ship with the image.** `data/replay/scenario_2023_sept.sqlite`
(11.7 MB) is tracked in git deliberately. If it is missing, the API still boots and still
returns well-formed responses — but they are *synthetic fixture curves*, not the precomputed
2023 event. Since the shapes are realistic, this is not obvious by eye.

Check after every deploy:

```bash
curl -s https://<host>/api/v1/health | jq .data_source
# "scenario_db"  <- correct
# "fixtures"     <- the database did not ship; the numbers on screen are invented
```

The container logs an ERROR on fallback, and the Docker build fails outright if the file is
absent from the context.

**2. Set `HAZE_ROOT`.** A normal `pip install` puts the package in `site-packages`, where the
default path resolution walks up into `lib/pythonX.Y/` and never finds `data/`. The Dockerfile
sets `HAZE_ROOT=/app`. Any other deployment method must set it too, or you get case 1.

**3. Run exactly one worker.** The replay clock is in-process state. A second worker gives
some visitors a different clock than others. The Dockerfile pins `--workers 1`.

## Running it

```bash
docker build -t haze-api .
docker run --rm -p 8000:8000 -e PORT=8000 haze-api
curl -s localhost:8000/api/v1/health | jq
```

Without Docker:

```bash
pip install .                       # serving deps only (~71 MB)
HAZE_ROOT=$(pwd) uvicorn haze.api.main:app --host 0.0.0.0 --port $PORT --workers 1
```

`pip install .` deliberately does **not** pull pandas, scikit-learn, pyarrow or joblib — the
serving path never imports them. To rebuild the demo from raw data you need the pipeline
extra: `pip install -e ".[dev,pipeline]"`, which is what `make venv` does.

### The frontend

The dashboard in `frontend/` is a separate deploy with its own lifecycle. It is not built
by pushing to `main` — publish it explicitly from that directory:

```bash
cd frontend
vercel --prod
```

Build-time configuration is committed in `frontend/.env.production`, not held in the host's
dashboard; the comment at the top of that file explains why.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `HAZE_ROOT` | walks up from the source file | Repository root holding `data/` and `models/`. **Required for non-editable installs.** |
| `HAZE_ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins. |
| `HAZE_REPLAY_MODE` | `true` | Serve against the virtual clock. |
| `PORT` | `8000` | Listen port. |

On CORS: the `*` default is correct for a public read-only demo, not merely convenient. There
are no cookies and no auth, and `allow_credentials` is `False` — which is the condition under
which browsers accept a wildcard. Narrow it to the dashboard origin once the domain is known:

```bash
HAZE_ALLOWED_ORIGINS=https://haze-dashboard.example.com
```

## Notes for the frontend team

**Pass `?at=` on every read request.** This is the important one. The server holds a *single*
replay clock shared by every visitor, and `/replay/seek|play|pause|reset` mutate it without
authentication. With two judges on the link at once, one pressing play moves the clock under
the other mid-session.

Every read endpoint already accepts `?at=<ISO-8601 UTC>` — it is in the contract and unchanged.
Hold the clock in frontend state, drive the scrubber and bookmark buttons locally, and send
`at` on every call. Each visitor is then fully independent, and the `/replay/*` POST endpoints
are simply unused in the public deployment. Bookmark timestamps come from
`GET /api/v1/replay/state` (or `/scenarios`), so no timestamps need hardcoding.

A malformed `at` now returns `422 {"detail": "at must be ISO-8601 UTC, …"}` rather than a 500.

**Expect a slow first request on free tiers.** The app itself starts in ~370 ms and answers a
warm forecast in ~1 ms, but free-tier hosts sleep after ~15 minutes idle and take 30–60 s to
wake. Show a loading state on the first request rather than a spinner that looks hung, and
consider a `/api/v1/health` ping on page load to start the wake early.

**Keep the "simulated" label visible.** Institution names are real public organisations, and
notifications carry `status: "delivered"`. Every notification also carries `simulated: true`,
and nothing is ever sent. The UI should say so, so a viewer cannot read the feed as evidence
of a live partnership.

## What deployment does not change

No model, metric, or served artifact is touched, and `api_contract/openapi.json` is byte-
identical — verified by checksum and by `scripts/00_export_contract.py` reporting "Contract
unchanged". Existing integrations need no changes at all; the `?at=` guidance above is a
robustness measure available in the contract as already published.
