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
| Pontianak, West Kalimantan (ID) | 307.3 µg/m³ | Hazardous |
| Kuching, Sarawak (MY) | 53.0 µg/m³ | Unhealthy for Sensitive Groups |

(Kuching was previously listed here as 59 µg/m³ / "Unhealthy". That value matches no
window in the archive — the measured peak is 53.0 over the demo window and over the wider
validation window alike, which falls in the *Unhealthy for Sensitive Groups* band, not
*Unhealthy*. The alert threshold this system fires on, 35.5, is the floor of that same
band, so the corrected figure is the one consistent with everything else here.)

West Kalimantan hotspot counts rose **729 → 953 → 1,100 detections over 1–3 September** —
FIRMS detections inside the source region, deduplicated across MODIS and VIIRS, which is the
same count the exposure kernel is built on.

Daily source-region detections do correlate with daily receptor PM2.5 over this window, but
**the lag structure is not the tidy story an earlier revision of this README told.** That
revision claimed `r = +0.52` at a one-day lag, with "Kuching's correlation peaks at 1 day,
Pontianak's at 3, consistent with transport distance". None of those three numbers was
computed anywhere in this repository. Measured now, over the held-out 2023 window:

| Lag | 0 d | 1 d | 2 d | 3 d | 4 d | 5 d |
|---|---|---|---|---|---|---|
| Kuching (≈400 km downwind) | **+0.59** | +0.56 | +0.45 | +0.28 | +0.14 | +0.02 |
| Pontianak (fires are local) | −0.16 | +0.11 | +0.31 | **+0.53** | +0.47 | +0.33 |

Kuching peaks at **zero lag**, not one day, and the r = +0.52 does not reproduce at any lag
in any window. The peak ordering also runs *opposite* to the physical expectation: the
receptor with the fires on its doorstep peaks three days out while the one across the border
peaks same-day. That is unexplained and is reported rather than smoothed over — a daily
correlation cannot separate transport time from the fact that fires and haze are both driven
by the same dry spell, so this profile is weaker evidence for a transport mechanism than the
sentence it replaces implied. The whole profile is published rather than its peak, because a
maximum read off six correlated numbers is not much evidence on its own.

Computed by `scripts/14_daily_attribution.py` into `diagnostics/daily_attribution.json`,
which also carries the full-archive and 2024 profiles.

**The demo window is held out of training entirely.** Forecasts over it are out-of-sample.

---

## Modelling

### Upwind Fire Exposure Index

The feature that makes cross-border *attribution* work — measured, not assumed; the
ablation below shows it earns its place in the attribution model and **not** in the
forecast model, and this heading used to overclaim by saying it made cross-border
prediction possible. Counting fires within a radius is blind to whether the wind is even
pointing at you, so each detection is weighted by three physically meaningful terms:

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
| Episode detection | **93.9%** of 33 episodes (95% CI 80.4–98.3%) |
| Hit rate (hour-level) | **79.5%** |
| Specificity | **80.0%** |
| False alarm rate | 25.4% |
| Median warning lead time | **24 h** — of which **64.5% sit on the 24 h ceiling** |
| Distinct episodes evaluated | **33** |

Four of those rows need their definitions stated, because each is easy to misread:

- **Two rates are co-primary.** *Episode detection* is what a head teacher means by
  "did you warn me about this episode" — of the distinct observed episodes, how many
  carried a warning before onset. *Hit rate* is hour-level: of the issuance hours with
  a breach coming, how many warned. They differ materially (93.9% against 79.5%);
  quoting only the first flatters the system and only the second understates it.
- **33 episodes, not 99.** Six institutions resolve to **two** receptors: CAMS is
  ~0.4° native, and each city's trio shares one grid cell and receives an identical
  PM2.5 series. Scoring all six tripled every count without adding information. The
  frozen `metrics.json` still reports 99 under `events_evaluated` and is deliberately
  left as published; `alerts_corrected` in the API response is the corrected count and
  is the one to quote.
- **Specificity, not false alarm rate, is what compares across seasons.** False alarm
  rate is 1 − precision, so it moves with how often the event happens even when the
  model has not changed. That is exactly what made the 2024 comparison below look like
  a regression when specificity had in fact improved.
- **The median lead time is censored, and the ceiling share says how badly.** The
  search window for a warning is exactly as wide as the forecast horizon, so no episode
  can record a lead above 24 h and the median rests on its own bound. It reads 24.0 at
  every trigger percentile from p75 to p95 while the hit rate moves 58% → 90% — the
  signature of a statistic against a ceiling. **64.5% of episodes sit exactly on it.**
  The true median is ≥ 24 h and unmeasured; only widening the search window past the
  horizon would turn it into an estimate.

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

#### Does the physical weighting actually earn its place?

Feature importance shows the forest *splits* on UFEI. It does not show that a forest denied
UFEI would do worse — importance is measured against the model's own splits, never against
an alternative. So UFEI was removed and both models retrained, with the pass criterion
registered in the script before the run (`scripts/13_ablations.py`, output in
`diagnostics/ablations_no_ufei.json`; the control arm reproduces the published baseline to
within 0.00000, so the harness itself is not moving results).

Removing UFEI is **not** removing fire information. Raw hotspot counts and summed FRP in
0–50 / 50–150 / 150–400 km rings stay in the feature set. This is physical weighting
(bearing alignment × FRP × distance decay) against *counting fires in a radius* — 37
features versus 32.

**The answer differs by model, and both halves are reported.**

*Forecasting and alerting — UFEI earns nothing.*

| | Episode detection | Hit rate | Specificity |
|---|---|---|---|
| 2023, with UFEI | 93.9% of 33 | 76.3% | 79.6% |
| 2023, without | 93.9% of 33 | 74.2% | **82.2%** |
| 2024, with UFEI | 81.0% of 21 | 53.8% | **90.3%** |
| 2024, without | 81.0% of 21 | 53.1% | 89.8% |

Episode detection is *identical* on both seasons — the same episodes caught and the same
ones missed, **0 net episodes** on the paired McNemar comparison, p = 1.000 on both windows.
Specificity is slightly *better* without UFEI on 2023. On the numbers a head teacher acts
on, the physical weighting buys nothing over ring counts. The likely reason is structural:
RF-forecast carries PM2.5 lags and leans heavily on persistence, so no fire feature has much
variance left to explain.

*Attribution — UFEI earns its place clearly.*

| Held-out window | R² (log) with UFEI | without UFEI |
|---|---|---|
| 2023 | **−0.027** | −0.172 |
| 2024 | **+0.220** | +0.160 |

RF-attribution carries no PM2.5 lags and must explain concentration from fire and weather
alone — and it is *its* importances the transboundary claim rests on. There UFEI helps
consistently, on both seasons. Denied it, the model falls back on `frp_50_150km`,
`frp_150_400km` and `hotspots_50_150km`: the naive ring features step straight into the top
ranks and do the job worse.

**So the honest claim is narrower than "UFEI is what makes cross-border prediction
possible."** It earns its place in the model that attributes smoke to a source; it does not
earn it in the model that issues the alerts.

⚠️ Those attribution R² values come from the **validation model**, which withholds both fire
seasons. They are not comparable with the `r2_attribution = 0.032` in `metrics.json`, which
belongs to the **served model** and a larger training set. Two artifacts, two sets of
numbers — they are never mixed in one row here.

**The GRU lost.** It trained cleanly and beat persistence (+10.1% at 24h), but its +24h MAE
of 13.68 µg/m³ did not beat the Random Forest's 13.03, so the Random Forest is what gets
served. That result is recorded in `metrics.json` rather than quietly dropped.

### The second held-out event: 16 Aug – 15 Oct 2024

One held-out episode shows the model was not fitted to its own test set. It does not
show the result survives a different year — and a reviewer is entitled to suspect a
single validation event of being the flattering one. So a **second model is trained
with both seasons withheld** (100,512 rows, 9,216
fewer than the served model, plus a 24h embargo either side) and each
season is scored with the identical metric code. The served model is a separate artifact
and is not modified; `scripts/06_validate_events.py` re-checksums it and fails if it moved.

The 2024 window is the *same calendar span* as the 2023 one, so the choice of dates
involves no selection. 2022 was scanned and rejected — Kuching never crosses 35.5 µg/m³
that year, so the transboundary claim cannot be tested at all — and the evidence for that
rejection is recomputed on every run rather than asserted.

Forecast skill on 2024 (mean absolute error, µg/m³):

| Lead | Model | Persistence | Climatology | Improvement |
|---|---|---|---|---|
| +6h | 4.71 | 5.79 | 8.28 | **+18.7%** |
| +12h | 5.29 | 7.48 | 8.27 | **+29.3%** |
| +24h | 5.47 | 6.40 | 8.22 | **+14.6%** |

**Skill generalises.** Improvement over persistence is, if anything, better than on 2023.

⚠️ **The absolute MAEs are not comparable between the two years.** 2024 peaked at
66 µg/m³ against 2023's 307.
The 2024 errors are smaller because the season was cleaner, not because the model is
better on it. The `Improvement` column is the only one that compares across years.

Alerting, both seasons scored by the same validation model:

| Metric | 2023 | 2024 |
|---|---|---|
| Episode detection (95% CI) | **93.9% of 33 (80.4%–98.3%)** | **81.0% of 21 (60.0%–92.3%)** |
| Hit rate (hour-level) | 76.3% | 53.8% |
| Specificity | 79.6% | 90.3% |
| False alarm rate | 26.5% | 44.8% |
| Alertable-hour prevalence | 42.5% | 18.2% |
| Median lead (share at 24 h ceiling) | 24 h (64.5%) | 24 h (70.6%) |

**Read plainly: alerting is weaker on 2024.** Episode detection falls from
93.9% to 81.0%. That is the
headline and it is not reframed away.

Three things qualify it, none of which rescue it:

1. **The confidence intervals overlap** (80.4%–98.3%
   against 60.0%–92.3%).
   With 21 distinct episodes the gap is suggestive, not established.
2. **The false-alarm gap is largely a base-rate artifact.** Prevalence falls from
   42.5% to 18.2%, and
   false alarm rate moves with prevalence on its own. Specificity — which does not —
   *improved*, 79.6% → 90.3%.
3. **2024's exceedances are marginal.** Its peak barely clears twice the alert threshold,
   so episodes cross and re-cross 35.5 µg/m³ where 2023's sat far above it.

What is left after those three is real and is a **data ceiling, not a modelling gap**: the
training set contains exactly one strong fire season, and nothing in the feature set tells
one season from another. Dryness and ENSO-regime features were tested as isolated
ablations and both came back null. The full investigation is in
`diagnostics/2024_generalization_gap_report.md`; the honest fix is more training data
covering severe seasons.

See `GET /api/v1/model/metrics` for all of the above, served live to the dashboard —
including `validation_events` (both held-out seasons) and `alerts_corrected` (the served
model's own figures on distinct receptors). The frozen `alerts` block is retained
unchanged beside them rather than silently rewritten.

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
| `crossborder` | 2023-09-02T16:00Z | All six institutions alerted across both countries. Kuching warned **17 hours ahead while its air reads 12.8 µg/m³ — good, nothing visibly wrong**. Observation later confirms **49.2 µg/m³**. |
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
   reproduce a physical reanalysis, not ground truth. Every value is labelled with its
   provenance.

   This is a real limitation and not one we can close here, but the claim that CAMS is
   what is *available* is measured rather than assumed. Checked against the OpenAQ v3 API
   in August 2026 — the principal open air-quality archive — there is **no station within
   300 km of either receptor for either validation window**. Of the 68 Indonesian and
   Malaysian stations OpenAQ carries, exactly one lies anywhere on Borneo (Tambulaung,
   Sabah, 116.45°E — roughly 700 km from Kuching), and its record begins 2025-03-16,
   seventeen months after the September 2023 event and five after the 2024 comparison
   window. The nearest station to Pontianak with any data at all is 606 km away in
   Palembang, Sumatra, first reporting 2025-10-22; the nearest to Kuching is 801 km. A
   25 km radius query around each receptor returns zero. Indonesian coverage is
   concentrated on Java, Malaysian coverage on the Klang Valley; Sarawak's NREB network
   and Indonesia's ISPU stations do not federate to OpenAQ.

   So there is no public ground truth to validate against for these receptors in these
   years — which is *why* CAMS is used, and why every PM2.5 value in this system says so
   rather than implying measurement. A production deployment would ingest the national
   networks directly, which is an access and agreement problem rather than a modelling
   one.
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
8. **Attribution R² is low, and refitting at daily resolution does not rescue it.** The
   fire-and-weather-only model reaches R² = 0.03 in log space on held-out hourly data.

   An earlier revision of this README set that beside a daily correlation and invited the
   reader to conclude the relationship is "much stronger at daily resolution". That was a
   juxtaposition, not a test. It has now been tested, and **as a claim about the model it
   is false** — held-out 2023, log space:

   | | R² |
   |---|---|
   | Hourly attribution model | **+0.03** |
   | Daily attribution model | **−0.07** |
   | Daily persistence (yesterday's mean) | +0.43 |
   | Daily climatology | −0.94 |

   Refitting at daily resolution makes the model *worse*, not better, and it loses heavily
   to simply repeating yesterday's daily mean. The result survives the obvious objection:
   daily aggregation leaves 1,396 training days against ~110k hourly rows, so the fit was
   repeated at a leaf size suited to the smaller sample, and the null held (−0.13 → −0.07).
   The more favourable setting is the one quoted above.

   What is true is narrower, and worth keeping: the **bivariate correlation** between
   source-region fire counts and receptor PM2.5 is stronger at daily resolution
   (r ≈ +0.44 to +0.59) than the hourly model's R² would suggest. A marginal association
   becoming clearer after averaging is not the same thing as a fitted attribution model
   doing better, and the two are no longer presented as if they were. Hour to hour,
   boundary-layer dynamics and background aerosol dominate; day to day, the fitted model
   still cannot beat persistence.

   The UFEI features rank among the top drivers, but they explain a modest share of hourly
   variance, and that figure is reported as measured.
   See `scripts/14_daily_attribution.py` and `diagnostics/daily_attribution.json`.

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
                     04 precompute, 05 offline smoke test,
                     06 validate held-out events, 07 live snapshot,
                     08 gate snapshot, 09 rescore/dedup,
                     10 corrected metrics + calibration,
                     12 saturation diagnostic, 13 feature ablations
frontend/            Next.js dashboard — Lite and Pro screens, deployed
                     separately from the API (see DEPLOYMENT.md)
```
