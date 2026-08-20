# API Contract — Transboundary Haze Early-Warning

**Status: FROZEN.** Changes after this point are additive only — new optional fields, new
endpoints. No renames, no type changes, no removals. `tests/test_contract.py` fails the
build if `openapi.json` drifts.

- Base URL (dev): `http://localhost:8000`
- API base path: `/api/v1`
- Machine-readable spec: [`openapi.json`](./openapi.json) — 18 paths, 43 schemas
- Change history: [`CHANGELOG.md`](./CHANGELOG.md)
- Interactive docs: `http://localhost:8000/docs`
- CORS: all origins permitted in dev

**Conventions**
- All timestamps are ISO-8601 UTC with a trailing `Z` (`2023-09-02T04:00:00Z`)
- All PM2.5 concentrations are µg/m³
- Bounding boxes are `lon_min,lat_min,lon_max,lat_max`
- Every read endpoint accepts `?at=<ISO-8601>` to override the replay clock

**Generate a typed client:**
```bash
npx openapi-typescript api_contract/openapi.json -o src/api/types.ts
```

---

## Enums — safe to hardcode

```ts
type AqiCategory = "GOOD" | "MODERATE" | "UNHEALTHY_SENSITIVE"
                 | "UNHEALTHY" | "VERY_UNHEALTHY" | "HAZARDOUS";
type InstitutionType = "school" | "hospital" | "authority";
type Role            = "source_region" | "affected_region";
type AlertStatus     = "active" | "pending" | "resolved";
type Channel         = "sms" | "whatsapp";
type DeliveryStatus  = "queued" | "sent" | "delivered" | "failed";
type Pm25Source      = "cams_reanalysis" | "model_forecast" | "ground_station";
```

**Category boundaries (µg/m³)** — US EPA PM2.5 breakpoints:

| Category | Range | Suggested colour |
|---|---|---|
| `GOOD` | ≤ 12.0 | green |
| `MODERATE` | 12.1 – 35.4 | yellow |
| `UNHEALTHY_SENSITIVE` | 35.5 – 55.4 | orange |
| `UNHEALTHY` | 55.5 – 150.4 | red |
| `VERY_UNHEALTHY` | 150.5 – 250.4 | purple |
| `HAZARDOUS` | > 250.4 | maroon |

**The alert threshold is 35.5 µg/m³, for every institution type.** It is the floor of
`UNHEALTHY_SENSITIVE` — the category named for precisely the population a hospital serves —
and it is reported per alert as `Alert.threshold_pm25`, where it is always this value.

A school and a hospital alert on the same air. Institution type changes only the *wording* of
`recommended_actions`; it never changes the number, and a client must not apply a
type-dependent threshold of its own. Prefer reading `threshold_pm25` over hardcoding 35.5, so
a future change reaches you through the payload.

Earlier warning for vulnerable populations comes from *what* the alert triggers on, not from a
lower bar: alerting fires on the p90 upper prediction band rather than the central forecast
(see `ModelMetrics.alert_trigger_percentile`), which buys lead time for every institution
alike.

---

## Endpoints

### Meta
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Status, mode, current replay clock, data source |
| `GET` | `/api/v1/model/metrics` | Held-out performance for on-screen display. **503 until training has run.** |

### Institutions
| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/institutions` | `?country=MY` `?type=school` |
| `GET` | `/api/v1/institutions/{id}` | |

Six institutions, three in each country. `country` is ISO-3166-1 alpha-2; `role`
distinguishes the source region (West Kalimantan) from the affected region (Sarawak).

### Hotspots
| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/hotspots` | `?start= &end= &bbox= &min_frp= &limit=` (default 5000) |
| `GET` | `/api/v1/hotspots/summary` | `?grid=0.25` — gridded aggregation for map rendering |

Use `/summary` for anything zoomed out. A full season is tens of thousands of points and
will stall a map if drawn individually. `total_available` tells you how many matched
before `limit` was applied.

### Forecast — the core endpoint
| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/institutions/{id}/forecast` | `?horizon_hours=24` |
| `GET` | `/api/v1/institutions/{id}/observation` | Current PM2.5 only |

The `attribution` block is what makes this a *transboundary* system rather than a generic
air-quality widget — surface it in the UI:

```json
"attribution": {
  "upwind_fire_exposure_index": 0.83,
  "transboundary": true,
  "source_country": "ID",
  "dominant_source_region": "West Kalimantan, Indonesia",
  "estimated_transport_hours": 32,
  "contributing_hotspot_count": 486,
  "top_feature_contributions": [
    {"feature": "upwind_fire_exposure_48h", "contribution": 0.41}
  ]
}
```

When `transboundary` is `true` for a Malaysian institution, the smoke driving that
forecast originated in Indonesia. That is the headline claim of the product.

#### The prediction band, and where the model gives out

`pm25_lower` / `pm25_upper` are nullable — render a band only when both are present.
They are **percentiles across the 300 trees of the forest**, not a fitted confidence
interval: `pm25_lower` is p10, `pm25_upper` is p90, and `pm25` is the mean. `pm25_p50`
is the median, so the full band is p10/p50/p90. Note that **alerting triggers on
`pm25_upper`, not on `pm25`** — a missed episode and a false alarm are not equally costly.

The forecast has a hard ceiling, and the payload tells you where it is. Each tree returns
an average of training targets in a leaf, so the ensemble **cannot output a value above
~90 µg/m³** however bad the air actually gets. During the September 2023 Pontianak peak
the observed reading was 307 µg/m³ and the forecast reads 86. That is a structural limit,
not a model failure — and if you draw the raw number next to ground truth without saying
so, it will look like one.

Two additive fields exist so you can say so:

- **`ForecastPoint.beyond_training_range`** (boolean, per point) — style the marker or
  segment differently and label it "beyond the model's trained range". The value is a
  **floor**, not a severity estimate.
- **`Forecast.uncertainty`** (object, once per response) — drive a banner off
  `any_point_beyond_training_range`, and render `note` verbatim if you want the
  explanation written for you. It also carries `lower_percentile` / `upper_percentile` /
  `n_estimators` so you need not hardcode what the band means, plus both ceilings:
  `training_target_max_pm25` (112.9 — the largest value ever seen in training) and
  `model_ceiling_pm25` (~90.1 — the largest the forest can actually emit, which is the
  one that binds).

```json
"uncertainty": {
  "method": "random_forest_tree_quantiles",
  "lower_percentile": 10,
  "upper_percentile": 90,
  "n_estimators": 300,
  "training_target_max_pm25": 112.9,
  "model_ceiling_pm25": 90.1,
  "any_point_beyond_training_range": true,
  "beyond_training_range_from_lead_hours": 1,
  "note": "From +1h this forecast is beyond the model's trained range. …"
}
```

`extrapolation_reason` says which signal fired: `band_saturated` (the band has reached the
forest's structural ceiling), `feature_out_of_range` (an input was outside anything seen in
training — during the episode, local fire radiative power and the PM2.5 lag features), or
`both`. It is `null` when the point is in range.

Both fields are optional and default to `false` / `null`, so a client that ignores them
behaves exactly as before. `uncertainty` is `null` when the server is on fixtures or on a
scenario database built before these fields existed.

### Alerts
| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/alerts` | `?status=active` `?country=MY` `?transboundary=true` |
| `GET` | `/api/v1/institutions/{id}/alert` | `alert` is `null` when clear |

`lead_time_hours` is the headline number: hours between the alert firing and conditions
being expected to **cross the threshold** — the time the recipient has to act. Display it
prominently. `peak_lead_hours` reports when conditions are expected to be *worst*, which is
later; do not headline that one, it overstates the warning.

`forecast_peak_pm25` is the peak of the value the alert triggered on (the upper prediction
band), and `severity` is derived from it, so the two always agree. The central estimate
lives in the forecast endpoint and will read lower — that is expected, not a mismatch.

`recommended_actions` is already tailored to institution type and severity. Render it
verbatim as a checklist; do not synthesise your own copy. This is the *only* thing
institution type changes — the threshold that produced the alert is 35.5 µg/m³ regardless
(see `threshold_pm25` above), so a hospital and a school in the same city alert together and
report the same `lead_time_hours`.

Because `severity` is derived from a value that by construction reached 35.5, **an alert is
never `GOOD` or `MODERATE`** — the lowest severity an alert can carry is
`UNHEALTHY_SENSITIVE`. Those two categories appear only on forecast and observation points.

### Notifications (mocked last-mile)
| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/notifications` | `?institution_id= &country= &limit=50`, newest first |
| `POST` | `/api/v1/notifications/simulate` | Body: `{institution_id, channel?, language?}` |

Messages are written in the recipients' language (`id` for West Kalimantan, `ms` for
Sarawak). **Every notification carries `simulated: true`** — no real SMS or WhatsApp
integration exists. Show that flag in the UI; it is an honesty requirement, not an
oversight.

### Replay control
| Method | Path | Body |
|---|---|---|
| `GET` | `/api/v1/replay/state` | — |
| `POST` | `/api/v1/replay/seek` | `{"bookmark":"crossborder"}` or `{"timestamp":"..."}` |
| `POST` | `/api/v1/replay/play` | `{"speed":120}` |
| `POST` | `/api/v1/replay/pause` | — |
| `POST` | `/api/v1/replay/reset` | Back to the opening bookmark, paused |
| `GET` | `/api/v1/scenarios` | — |

**Bookmarks** — build these as one-click buttons; they are the demo's chapter markers.
Fetch them from `GET /replay/state` rather than hardcoding; each carries a `label` and
`description` written for on-screen use.

| Key | Clock | What it shows |
|---|---|---|
| `calm` | 2023-08-28T09:00Z | No active alerts anywhere. |
| `first_warning` | 2023-08-30T19:00Z | All 3 Sarawak sites alerted 18h ahead while no Indonesian site is alerted. Air reads 27 µg/m³; observation later confirms 53 µg/m³. |
| `crossborder` | 2023-09-02T16:00Z | **All 6 institutions alerted at once, across both countries.** Kuching warned 18h ahead while its air reads 13 µg/m³ (good); observation later confirms 49 µg/m³. |
| `severe` | 2023-09-04T21:00Z | Pontianak forecast 86 µg/m³ (unhealthy), Sarawak simultaneously alerted. |

All endpoints answer relative to the virtual clock, so seeking updates the entire
dashboard at once. `POST /replay/play` advances it at `speed`× real time.

---

## Errors

Standard FastAPI shape: `{"detail": "..."}`.

| Code | Meaning |
|---|---|
| `404` | Unknown institution or bookmark |
| `422` | Malformed bbox, timestamp, or missing seek target |
| `503` | `/model/metrics` before training has run |

---

## Notes for the frontend

1. **`data_source` in `/health`** reads `fixtures` before the pipeline has run and
   `scenario_db` afterwards. Payload shapes are identical; only the numbers change. You
   can build fully against fixtures.
2. **Poll `/replay/state`** while playing (1–2 s) to keep the clock display in sync.
3. **`population_served`** is the indirect-beneficiary count — students, patients, or
   residents protected by decisions at that site. Worth surfacing: it is the impact number.
4. **Label PM2.5 provenance.** The `source` field says `cams_reanalysis`. These are
   reanalysis values, not ground-station measurements, and the UI should not imply
   otherwise.
5. **`GET /model/metrics` carries the honest numbers** — held-out skill against
   persistence and climatology, hit rate, false alarm rate, median lead time, and a
   `notes` array of stated limitations. If you show performance anywhere in the UI, show
   it from here rather than hardcoding a flattering figure.
6. **Forecast magnitude understates extreme episodes.** The model cannot predict above its
   training maximum, so during the most severe hours the forecast reads far below the
   observed value (86 vs 307 µg/m³ at the Pontianak peak). Alert *categories* and timing
   are reliable; treat the forecast number as "at least this bad", not a severity
   estimate. `GET /institutions/{id}/observation` carries the actual reading.
7. **You do not have to detect note 6 yourself.** `beyond_training_range` on each forecast
   point and the `uncertainty` block on the response say exactly when the forecast has left
   the range the model was trained on, and `uncertainty.note` is written to be rendered to
   a user as-is. This matters most in the `severe` bookmark, where all three Pontianak
   institutions are flagged and the Kuching ones are not. Showing a bare number there is
   the one thing that makes a known, explainable limit look like a broken model.
