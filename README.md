# Transboundary Haze Early-Warning System

Backend for a short-horizon PM2.5 forecasting and last-mile alerting service covering
institutions on both sides of the Indonesia–Malaysia border in Borneo.

Built for the Oxford Saïd Global Climate Tech Challenge 2026.

---

## The problem

Fires in Sumatra and Kalimantan send smoke across national borders every dry season.
Regional infrastructure — the ASEAN Specialised Meteorological Centre, NASA FIRMS —
already detects *where the fires are*, at regional scale, for expert audiences.

What does not exist is the last mile: nobody tells the head teacher at a specific school
in Kuching that the air at *their* school will be dangerous tomorrow morning, early enough
to cancel outdoor assembly.

## What this system does

1. **Consumes** existing public hotspot detections (NASA FIRMS) and reanalysis weather.
2. **Forecasts** PM2.5 up to 24 hours ahead at named institutions — schools, hospitals and
   disaster-management offices — in West Kalimantan (Indonesia) and Sarawak (Malaysia).
3. **Attributes** each forecast to a source region, and flags when the smoke driving it
   crossed a national border.
4. **Triggers** alerts with an explicit warning lead time, and generates the last-mile
   messages that would reach parents, patients and the public.

## What it does not do

- **It does not detect fires.** It consumes NASA FIRMS detections as input. No CNN over
  raw satellite imagery is involved, by design.
- **It does not send messages.** The notification feed is simulated. Every notification
  the API returns carries `"simulated": true`.
- **Its PM2.5 values are not ground-station measurements.** They come from the ECMWF CAMS
  reanalysis and are labelled `"source": "cams_reanalysis"` throughout.

---

## Quick start

```bash
make venv          # create .venv, install dependencies
make data          # download and cache all inputs (network required, once, ~10 min)
make demo          # features -> train -> precompute scenario (offline)
make serve         # API on http://localhost:8000  (docs at /docs)
```

Before recording a demo:

```bash
make offline       # run with Wi-Fi physically OFF
```

## The data

| Input | Source | Key required |
|---|---|---|
| Fire hotspots | NASA FIRMS country-year archives, VIIRS S-NPP + MODIS, 2022–2024 | **No** |
| Weather | Open-Meteo ERA5 reanalysis, hourly | **No** |
| PM2.5 | Open-Meteo CAMS reanalysis, hourly | **No** |

The FIRMS *country archive* files are used rather than the `/api/area/` endpoint
specifically because they need no API key — a demo that depends on a key somebody has to
provision is a demo that can fail.

CAMS PM2.5 coverage begins around August 2022, which is why the training window starts
there and why the demo event is 2023 rather than the more famous 2019 haze season: for
2019 there is no gridded PM2.5 to train against.

## The demo event: 28 Aug – 8 Sep 2023

A real, documented transboundary episode:

| Site | Peak PM2.5 | Category |
|---|---|---|
| Pontianak, West Kalimantan (ID) | 307 µg/m³ | Hazardous |
| Kuching, Sarawak (MY) | 59 µg/m³ | Unhealthy |

West Kalimantan hotspot counts rose 1,002 → 1,054 → 1,329 detections over 1–3 September.
Daily hotspot counts there correlate with Kuching PM2.5 at **r = +0.52 at a one-day lag** —
and the lag structure is physically right: Kuching's correlation peaks at 1 day, Pontianak's
at 3, consistent with transport distance.

**The demo window is held out of training entirely.** Forecasts over it are out-of-sample.

---

## Modelling

### Upwind Fire Exposure Index

The feature that makes cross-border prediction possible. Counting fires within a radius is
blind to whether the wind is even pointing at you, so each detection is weighted by three
physically meaningful terms:

```
alignment = cos( bearing(fire → receptor) − wind_direction_at_fire )
weight    = FRP · max(0, alignment)^2 · exp(−distance / 300km)
```

A fire counts only to the extent that it is intense, close, and genuinely upwind. Summed
over 24/48/72-hour trailing windows, and split by the country each fire sits in — which is
what turns "transboundary" from an assertion into a measured quantity.

### Models

| Model | Purpose |
|---|---|
| **RF-attribution** | Trained *without* PM2.5 lags, so it cannot lean on persistence and must explain concentration from fire and weather alone. Its feature importances are the evidence for the transboundary claim. |
| **RF-forecast** | Direct prediction at every lead time 1–24h. Prediction bands come from spread across trees. |
| **GRU** | Sequence model over a 48-hour window, direct 24-hour multi-horizon head, `log1p` target, Huber loss, trained jointly across all six sites. Promoted to serving only if it beats the alternatives on held-out data. |

Every metric is reported against **persistence** and **climatology** baselines. PM2.5 is
strongly autocorrelated, so a model that merely repeats the current value already scores
well — quoting an R² in isolation would be meaningless.

### Measured results on the held-out event

Forecast skill (mean absolute error, µg/m³):

| Lead | Model | Persistence | Climatology | Improvement |
|---|---|---|---|---|
| +6h | 12.02 | 13.76 | 17.67 | **+12.7%** |
| +12h | 12.89 | 17.02 | 17.56 | **+24.2%** |
| +24h | 13.03 | 15.27 | 17.36 | **+14.7%** |

Alert performance — the numbers a head teacher can actually act on:

| Metric | Value |
|---|---|
| Hit rate | **79.5%** |
| False alarm rate | **25.4%** |
| Median warning lead time | **24 h** |
| Episodes evaluated | 99 |

Every institution alerts at the same 35.5 µg/m³, the floor of the EPA "Unhealthy for
Sensitive Groups" band. An earlier revision discounted that to 28.4 for hospitals; it was
removed, because 35.5 is already the sensitive-groups number and the extra lead time it was
reaching for is what the p90 band below already provides. These figures are measured at the
single threshold.

Alerts fire on the 90th-percentile prediction band rather than the point forecast. Missing
an episode and raising a false alarm are not equally costly, so the operating point is
chosen from a sweep recomputed on every training run (`metrics.json` -> `trigger_sweep`):

| Trigger | Hit rate | False alarms |
|---|---|---|
| p75 | 58.2% | 14.6% |
| p80 | 63.4% | 17.1% |
| p85 | 69.8% | 20.9% |
| **p90** | **79.5%** | **25.4%** |
| p95 | 90.1% | 33.6% |

The choice moves when the model changes — compacting the forests narrowed the prediction
spread and shifted the optimum from p85 to p90 — so it is re-derived and published rather
than fixed once. `tests/test_metrics.py` fails if the configured trigger is no longer the
best available under the 30% false-alarm cap.

The top drivers the attribution model learned, in order: 24-hour precipitation (rain
scavenges aerosol), **`ufei_72h`**, boundary-layer height, **`ufei_48h`**, hour-of-day, and
**`ufei_from_ID`** — the explicitly cross-border exposure term. Three of the top six are
upwind fire exposure, which is the transboundary claim quantified by the model rather than
asserted in a slide. `tests/test_metrics.py` fails if those features stop ranking.

**The GRU lost.** It trained cleanly and beat persistence (+10.1% at 24h), but its +24h MAE
of 13.68 µg/m³ did not beat the Random Forest's 13.03, so the Random Forest is what gets
served. That result is recorded in `metrics.json` rather than quietly dropped.

See `GET /api/v1/model/metrics` for all of the above, served live to the dashboard.

---

## API

Base path `/api/v1`. The contract is frozen in [`api_contract/openapi.json`](api_contract/openapi.json);
see [`api_contract/CONTRACT.md`](api_contract/CONTRACT.md) for the frontend-facing guide.

| Group | Endpoints |
|---|---|
| Institutions | `GET /institutions`, `GET /institutions/{id}` |
| Hotspots | `GET /hotspots`, `GET /hotspots/summary` |
| Forecast | `GET /institutions/{id}/forecast`, `GET /institutions/{id}/observation` |
| Alerts | `GET /alerts`, `GET /institutions/{id}/alert` |
| Notifications | `GET /notifications`, `POST /notifications/simulate` |
| Replay | `GET/POST /replay/*`, `GET /scenarios` |
| Meta | `GET /health`, `GET /model/metrics` |

Changes after freezing are additive only. `tests/test_contract.py` fails the build on any
breaking change.

## Replay mode

The demo must be reproducible on every take of a recording, so the API does not use
wall-clock time. It holds a **virtual clock** inside the scenario window, and every
endpoint answers "as of" that instant.

Everything is precomputed into `data/replay/scenario_2023_sept.sqlite`: hotspots,
observations, a full 24-hour forecast issued at every hour, alert state, and the
notification feed. At demo time there is **no network call and no model inference**.

Bookmarks — the presenter's chapter markers. Each was selected by querying the precomputed
scenario for what the system actually produces, and every figure below is asserted by
`scripts/05_offline_smoke_test.py`:

| Key | Clock | What it shows |
|---|---|---|
| `calm` | 2023-08-28T09:00Z | No active alerts anywhere. |
| `first_warning` | 2023-08-30T19:00Z | All three Sarawak institutions alerted **18 hours ahead** while no Indonesian site is alerted at all — the smoke is already crossing the border. Air outside reads 27 µg/m³. Observation later confirms **53 µg/m³**. |
| `crossborder` | 2023-09-02T16:00Z | All six institutions alerted across both countries. Kuching warned **18 hours ahead while its air reads 13 µg/m³ — good, nothing visibly wrong**. Observation later confirms **49 µg/m³**. |
| `severe` | 2023-09-04T21:00Z | Pontianak forecast to 86 µg/m³ (unhealthy), Sarawak simultaneously alerted. |

Every figure above is asserted by `scripts/05_offline_smoke_test.py`, including that
observation later confirmed each warning — a lead time nobody checked against what
actually happened would be a false alarm dressed up as a success.

```bash
curl -X POST localhost:8000/api/v1/replay/seek -d '{"bookmark":"crossborder"}' \
     -H 'Content-Type: application/json'
```

---

## Limitations

Stated plainly, because a reviewer will find them anyway and they are more damaging
discovered than disclosed.

1. **PM2.5 labels are CAMS reanalysis, not measurements.** The model is trained to
   reproduce a physical reanalysis, not ground truth. A production deployment would ingest
   ground stations; CAMS is what is publicly and reliably available for this region and
   period. Every value is labelled with its provenance.
2. **Fire detection is not ours.** NASA FIRMS does it. This system adds forecasting and
   alerting on top.
3. **Notifications are simulated.** No SMS or WhatsApp integration exists.
4. **Six institutions, one region pair.** Real places with approximate published
   coordinates; the users are illustrative and no personal data is involved.
5. **The dispersion kernel is not a dispersion model.** UFEI is a source-receptor
   approximation, not HYSPLIT. It is cheap enough to run for three years of hourly data on
   a laptop, and it is honest about being an approximation.
6. **2019 is context, not input.** The 2019 haze disaster motivates the work; the model is
   trained on 2022–2024. These are never conflated.
7. **The model under-predicts the most extreme hours.** The held-out episode peaks at
   307 µg/m³; nothing in the training window exceeds 112.9. A tree ensemble predicts an
   average of training targets within each leaf, so it structurally cannot output a value
   above its training maximum — and in practice the bound is tighter still. Measured
   directly off the persisted forests, the highest upper-band value any of them can emit
   is **90.1 µg/m³**, because `min_samples_leaf=20` means every leaf averages at least
   twenty rows and none is a pure extreme. The Pontianak forecast tops out at 86 against
   an observed 307. This does not affect alerting, which depends on crossing the
   35.5 µg/m³ threshold and gets that right 79.5% of the time, but it does mean the
   forecast magnitude should not be read as a severity estimate during extreme episodes.
   Rather than leave that in a README where a user will never see it, the API says so per
   forecast point: `beyond_training_range` and the `uncertainty` block mark exactly where
   the number becomes a floor (see `api_contract/CHANGELOG.md`). The honest fix is still
   more training data covering severe seasons, not a different loss function.
8. **Attribution R² is low.** The fire-and-weather-only model reaches R² = 0.03 in log
   space on held-out hourly data. The relationship this system rests on is much stronger
   at daily resolution (r = +0.52 between West Kalimantan hotspot counts and Kuching
   PM2.5 at a one-day lag) than hour to hour, where boundary-layer dynamics and
   background aerosol dominate. The UFEI features rank among the top drivers, but they
   explain a modest share of hourly variance and the figure is reported as measured.

## Layout

```
src/haze/
  config.py          domains, windows, thresholds, scenario definition
  institutions.py    the six demo institutions
  ingest/            FIRMS + Open-Meteo, all cached to disk
  features/          UFEI kernel and the hourly feature matrix
  models/            RF, GRU, baselines, evaluation
  alerts/            thresholds, rules, multilingual message templates
  pipeline/          scenario precompute
  replay/            virtual clock, SQLite scenario store
  api/               FastAPI app, schemas, routers
scripts/             00 contract, 01 download, 02 features, 03 train,
                     04 precompute, 05 offline smoke test
```
