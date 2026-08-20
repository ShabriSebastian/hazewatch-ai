# API Changelog

Every entry here is additive. Nothing is renamed, retyped, or removed after the contract
was frozen — `tests/test_contract.py` fails the build otherwise.

---

## 2026-08-13 — one alert threshold for every institution type

**No schema change.** 18 paths, 43 schemas, byte-identical structure — the only difference
in `openapi.json` is a new `description` on `Alert.threshold_pm25`. Verified: the two files
are identical once descriptions are stripped.

### What changed in behaviour

Hospitals previously alerted at **28.4 µg/m³** while schools and authorities alerted at
**35.5**. The value came from an undocumented per-type sensitivity factor of 0.8 applied to
the `UNHEALTHY_SENSITIVE` floor. **It has been removed. `threshold_pm25` is now always 35.5.**

The factor was wrong on three counts:

1. 35.5 is already the floor of "Unhealthy for *Sensitive Groups*" — the category named for
   the population a hospital serves. Discounting it applied the same allowance twice.
2. Earlier warning for vulnerable populations already comes from triggering on the p90 upper
   prediction band rather than the central forecast, which is documented and applies to
   every institution.
3. 28.4 sits inside `MODERATE`, so hospitals were served **96 alerts carrying
   `severity: "MODERATE"`** alongside `UNHEALTHY_SENSITIVE` respiratory-surge actions. An
   alert can no longer carry `GOOD` or `MODERATE` severity at all.

### What a client should do

Nothing is required. If you hardcoded a per-type threshold, delete it; prefer reading
`threshold_pm25` from the payload. Clients that already derive status from `alert !== null`
are unaffected.

### Effect on the demo bookmarks

`crossborder` still alerts **all six institutions across both countries** — both hospitals
peak well above 35.5 (57.7 and 38.5), so no alert disappears. `calm` (0 alerts) and `severe`
(6 alerts) are unchanged. At `first_warning` all three Sarawak sites now report an **18 h**
lead time; previously the hospital reported 1 h, which contradicted this document's own
description of that bookmark.

### Effect on published metrics

Metrics were always computed with the per-type threshold, so the headline figures moved:

| Metric | Was | Now |
|---|---|---|
| Hit rate | 83.5% | **79.5%** |
| False alarm rate | 25.6% | **25.4%** |
| Median lead time | 24 h | **24 h** |
| Episodes evaluated | 118 | **99** |

Forecast skill is unchanged — MAE does not depend on the alert threshold.

---

## 2026-08-12 — forecast uncertainty band and extrapolation flag

**Nothing breaks. If you ignore this entry, your integration behaves exactly as before.**
Every new field is optional with a safe default, no existing field changed name, type, or
value, and no field was added to any `required` list. `openapi.json` goes from 41 to 43
schemas; all 18 paths are unchanged.

### Why

The model under-reads severity during extreme episodes, and we would rather you knew from
the payload than discovered it on the demo video. A random forest predicts an average of
training targets in each leaf, so it cannot output a value above roughly **90 µg/m³** no
matter how bad the air gets. At the September 2023 Pontianak peak the observed reading was
**307 µg/m³** and the forecast reads **86**. Alerting is unaffected — it depends on crossing
35.5 µg/m³ and does that on time — but a raw point forecast drawn next to ground truth
looks like a broken model when it is actually a known structural limit.

### New — `ForecastPoint` (also applies to `Forecast.peak`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `pm25_p50` | `float \| null` | `null` | Median across the forest's trees. Completes the p10/p50/p90 band. |
| `beyond_training_range` | `bool` | `false` | This point has left the range the model was trained on. |
| `extrapolation_reason` | `enum \| null` | `null` | `band_saturated`, `feature_out_of_range`, or `both`. |

### New — `Forecast`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `uncertainty` | `Uncertainty \| null` | `null` | One block per response: what the band is, and where the model runs out of range. |

`Uncertainty` carries `method`, `lower_percentile` (10), `upper_percentile` (90),
`n_estimators` (300), `training_target_max_pm25` (112.9), `model_ceiling_pm25` (90.1),
`any_point_beyond_training_range`, `beyond_training_range_from_lead_hours`, and a `note`
string written to be rendered to a user verbatim.

### Clarified, not changed

`pm25_lower` and `pm25_upper` have always been **p10 and p90 across the 300 trees**, and
`pm25` has always been the tree mean. That was never written down; it is now, in the field
descriptions and in `uncertainty`. **The values themselves are byte-identical** to the
previous scenario database — verified by diffing every pre-existing column and every alert
payload before and after the rebuild.

Worth re-reading if you missed it: **alerting triggers on `pm25_upper`, not `pm25`.**

### What to do with it

Minimum: branch on `uncertainty.any_point_beyond_training_range` to show a caveat, and
render `uncertainty.note`. Better: style flagged points differently on the chart so the
caveat lands on the part of the curve it applies to. The `severe` bookmark is the case that
matters — all three Pontianak institutions flag, all three Kuching ones do not.

`uncertainty` is `null` when the server is running on fixtures, so keep the null check.
