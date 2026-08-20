# Why the 2024 generalization check underperforms the primary validation

**Phase 1 diagnostic — read-only investigation, no modeling change**

| | Primary validation | 2024 generalization check |
|---|---|---|
| Window | 2023-08-16 .. 2023-10-15 | 2024-08-16 .. 2024-10-15 |
| Hit rate | 79.5% | 53.8% |
| False alarm rate | 25.4% | 45.0% |
| Alert episodes | 99 | 63 |
| Artifact | `models/v1/metrics.json` | `models/v1/metrics_by_event.json` |

**Headline: most of this gap is a measurement artifact, not a model regression.**

The two numbers come from two different models scored on two very different events, and
the FAR comparison is invalid on its face — false alarm rate is a precision statistic and
depends on how often the event actually happens. Correcting for the base rate, the model's
false-positive rate is **20.0% in 2023 and 9.8% in 2024**: specificity roughly *doubled*.
Only the hit-rate drop is real, and about half of it is explained by 2024 being an
intrinsically harder window (a model-free persistence baseline degrades by a comparable
factor). One genuine model weakness does survive the analysis — fire-feature extrapolation
with no interannual regime signal — alongside a methodological defect that inflates every
denominator in both runs threefold.

All figures below were computed from `data/processed/features.parquet` and
`models/v1/*.json`. Nothing was retrained; no artifact was written.

---

## 1. Feature inventory

The frozen list is `models/v1/feature_spec.json` — **36 features**, assembled in
`src/haze/features/build.py` and selected by `feature_columns()`
(`src/haze/features/build.py:296-304`).

| Group | Count | Features |
|---|---|---|
| Receptor weather | 7 | `wind_speed_10m`, `wind_direction_10m`, `wind_speed_100m`, `precipitation`, `relative_humidity_2m`, `temperature_2m`, `boundary_layer_height` |
| UFEI fire-exposure kernel | 5 | `ufei_24h`, `ufei_48h`, `ufei_72h`, `ufei_from_ID`, `ufei_from_MY` |
| Direction-blind fire rings | 6 | `hotspots_0_50km`, `frp_0_50km`, `hotspots_50_150km`, `frp_50_150km`, `hotspots_150_400km`, `frp_150_400km` |
| Temporal / derived | 6 | `wind_dir_sin`, `wind_dir_cos`, `precip_24h_sum`, `hour_sin`, `hour_cos` … plus `doy_sin`, `doy_cos` |
| PM2.5 persistence | 6 | `pm25_lag_{1,3,6,12,24}h`, `pm25_roll_24h` |
| Site identity (one-hot) | 6 | `site_id-ptk-sman1`, `site_id-ptk-soedarso`, `site_id-ptk-bpbd`, `site_my-kch-greenroad`, `site_my-kch-hus`, `site_my-kch-jpbn` |

The **attribution** model (`rf.train_attribution`) drops the PM2.5 lags *and* `doy_*`
(`src/haze/models/rf.py:29-59`). The **forecast** model — the one these validation
numbers describe — uses all 36.

### Is FRP used, or only raw hotspot count?

**FRP is used, in two independent ways.**

1. **Directly**, as summed FRP per distance ring (`src/haze/features/build.py:255`):

```python
for a, b in zip(config.RING_EDGES_KM[:-1], config.RING_EDGES_KM[1:]):
    ring = (d24 >= a) & (d24 < b)
    row[f"hotspots_{a}_{b}km"] = float(ring.sum())
    row[f"frp_{a}_{b}km"] = float(np.nansum(f24[ring]))
```

2. **As the weight inside the UFEI transport kernel** (`src/haze/features/build.py:181-187`),
   loaded at `build.py:151` (`self.frp = hotspots["frp"].to_numpy(...)`):

```python
alignment = np.cos(np.radians(bear - (wind_dir + 180.0)))
weights = (
    frp
    * np.clip(alignment, 0.0, None) ** config.UFEI_DIRECTIONAL_POWER
    * np.exp(-dist / config.UFEI_DECAY_KM)
)
```

Raw hotspot counts are carried alongside FRP deliberately, as a direction-blind contrast
to the UFEI (`build.py:249`). Cross-sensor deduplication rounds to ~1 km / 1 h and keeps
the **highest-FRP** detection (`build.py:44-51`), so FRP also drives dedup.

### Is any precipitation / dryness indicator included?

**Precipitation yes; dryness no.**

Present: `precipitation` (instantaneous, from Open-Meteo `WEATHER_VARS`,
`src/haze/ingest/weather.py:30-38`) and `precip_24h_sum`, a 24-hour rolling sum
(`src/haze/features/build.py:274`):

```python
out["precip_24h_sum"] = out["precipitation"].fillna(0).rolling(24, min_periods=1).sum()
```

Absent: there is **no** consecutive-dry-days counter, drought code, KBDI, SPI,
evapotranspiration, or soil-moisture term anywhere in the repository. Confirmed by
repo-wide grep over `src`, `scripts`, and `tests` for
`dry_days|drought|spi_|kbdi|dryness|soil_moisture` — zero matches in feature code.

This matters for the diagnosis. Peat drying in Kalimantan is a multi-week process; a
24-hour precipitation window cannot represent it. The model can see that it is not
raining right now, but not that the landscape has been dry for six weeks — which is
what separates a smouldering peat season from a surface-fire season with identical
hotspot counts.

### Is any ENSO / seasonal regime indicator included?

**No.**

The only seasonality is `doy_sin` / `doy_cos` (`src/haze/features/build.py:280-281`):

```python
out["doy_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
out["doy_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)
```

These encode *intra*-annual phase and take identical values on the same calendar day of
every year. They carry no information distinguishing a La Niña September from an El Niño
September. There is no ONI, SOI, IOD, or DMI feature, and no per-year regime label.

The only ENSO reference in the entire codebase is free-text prose in a rejection note
(`scripts/06_validate_events.py:84-92`), explaining why the 2022 window was not used as
a validation event. It is a comment, not a feature and not a recorded attribute.

Note the deliberate tension here: `src/haze/models/rf.py:31-35` excludes `doy_*` from the
attribution model precisely because *"the forest learns 'September is smoky', which is
climatology dressed up as attribution."* The forecast model keeps them — so the forecast
model's only notion of fire season is a calendar sinusoid identical in every year of the
archive.

---

## 2. Train/test split methodology

Both runs call the same function, `evaluate.split()`
(`src/haze/models/evaluate.py:42-75`), but with different arguments. **They produce two
different models.** This is the single most important thing to understand about the two
published numbers.

### Primary validation

`scripts/03_train.py:41` — `train, val, test = evaluate.split(df)`, all defaults.

- **Train:** 2022-08-01 .. 2024-12-31 minus the two held-out windows
- **Test:** 2023-08-16 .. 2023-10-15 (`config.TEST_START` / `TEST_END`, `src/haze/config.py:72-73`)
- **Val:** 2024-11-01 .. 2024-12-31 (`config.VAL_START` / `VAL_END`, `src/haze/config.py:74-75`)
- **Embargo:** `embargo_hours=0` (the default)
- Persisted to `models/v1/rf_forecast.joblib`; this is the served model

### 2024 generalization check

`scripts/06_validate_events.py:287-289`:

```python
train, _, test_2023 = evaluate.split(
    df, extra_holdouts=[SECOND_EVENT], embargo_hours=EMBARGO_HOURS
)
```

with `SECOND_EVENT = ("2024-08-16", "2024-10-15")` (`06_validate_events.py:61`) and
`EMBARGO_HOURS = 24` (`06_validate_events.py:55`).

- **Train:** the primary training set *minus* the 2024 fire season *minus* a 24 h embargo
  before every held-out boundary
- **Scored on:** both the 2023 and the 2024 windows
- **Never persisted** — held in memory and discarded (`06_validate_events.py:19-22`)

### Side by side

| | Primary | 2024 check |
|---|---|---|
| Train rows | 109,728 | 100,512 |
| Distinct hours (see §5) | 18,288 | 16,752 |
| Distinct days | 762 | 698 |
| Embargo | **0 h** | **24 h** |
| Complete Aug–Oct fire seasons in train | **2** (2022, 2024) | **1** (2022) |
| Test-window peak PM2.5 | 307.3 µg/m³ | 66.4 µg/m³ |

### Retrained from scratch, or warm-started?

**Retrained from scratch.** `rf.train_forecast` constructs a fresh
`RandomForestRegressor` for every lead time (`src/haze/models/rf.py:113-119`):

```python
for lead in horizons:
    x, y = _xy(train, features, f"target_{lead}h", log=False)
    model = RandomForestRegressor(**RF_PARAMS)
    model.fit(x, y)
```

There is no `warm_start`, no partial fit, and no reload of the served forests. Same
hyperparameters (`random_state=42`), so the run is deterministic and reproducible.

### Correction to the brief: the 2024 model is *not* trained on pre-2024 data only

The brief describes the 2024 check as "a separately retrained model." That is true, but
it is **not** trained on pre-2024 data only. Reconstructing the split month by month:

```
validation model, distinct hours per month:
  2022-08:744 2022-09:720 2022-10:744 2022-11:720 2022-12:744
  2023-01:744 2023-02:672 2023-03:744 2023-04:720 2023-05:744 2023-06:720
  2023-07:744 2023-08:336            2023-10:384 2023-11:720 2023-12:744
  2024-01:744 2024-02:696 2024-03:744 2024-04:720 2024-05:744 2024-06:720
  2024-07:744 2024-08:336            2024-10:360
```

It trains on 2024-01-01 .. 2024-08-15 and 2024-10-16 .. 2024-10-31. It is missing
exactly one thing: the 2024 **fire season**. That is the correct design for the question
being asked, but it means the model is not regime-naive about 2024 in general.

### Temporal leakage

**No material leakage on the Random Forest path.**

- **No scaler is fit anywhere on the RF path.** A Random Forest needs none; there is no
  `StandardScaler`, `fit_transform`, or normalization step in `rf.py` or `03_train.py`.
  The GRU (not served) does normalize, and it fits on the training split only
  (`src/haze/models/gru.py:138-139`): `mean = x_tr.reshape(-1, ...).mean(axis=0)`.
- **All engineered features are causal.** Lags use `shift(+lag)`; rolling windows use
  trailing `rolling(24)`; UFEI windows are trailing slices bounded by
  `now` (`build.py:216-218`). Targets are `shift(-lead)` (`build.py:288-289`), which is
  the intended forward look.
- **Features are built once over the full history**, but every row's features depend only
  on that row's past, so building before splitting introduces nothing.

Two minor items worth recording, neither of which explains the gap:

1. **The served model runs with `embargo_hours=0`.** The 144 rows immediately before each
   held-out boundary carry `target_1h..24h` values that reach *inside* the test window.
   `evaluate.py:27-39` documents this honestly as 0.13% of training rows. It is real, and
   it biases the **primary** number slightly upward — so it *widens* the reported gap
   rather than explaining it. The 2024 check applies the embargo; the primary does not.
   That asymmetry alone makes the two numbers non-comparable at the margin.
2. **`build.py:112` back-fills the wind grid**
   (`pd.DataFrame(...).ffill().bfill()`), which can pull a later hour into an earlier
   missing cell. It affects only uncached grid cells over water and is negligible, but it
   is the one place in the pipeline where a future value can reach a past row.

---

## 3. Distribution shift — and why the extrapolation hypothesis is rejected

### PM2.5 distributions

| | Validation-model train | 2023 window | 2024 window |
|---|---|---|---|
| n rows | 100,944 | 8,784 | 8,784 |
| Mean | 13.40 | 28.54 | 15.09 |
| Median | 11.40 | 18.50 | 12.30 |
| p90 | 22.90 | 57.88 | 27.00 |
| p99 | 43.40 | 163.00 | 48.50 |
| **Max** | **112.90** | **307.30** | **66.40** |
| Hours ≥ 35.5 µg/m³ | 2.11% | 19.43% | 4.10% |

### Does 2024 contain PM2.5 outside the training range? **No.**

This is the hypothesis the brief flags, and the data rejects it for 2024.

The training **target** maximum is **112.9 µg/m³ for both models** — the served model and
the validation model reach the same ceiling, because the 112.9 peak occurs on
2023-08-14, which falls outside every held-out window in both splits. The 2024 window
peaks at **66.4 µg/m³**, comfortably inside that range. There are only 348 hours above
100 µg/m³ in the entire archive, and all of them are in Feb/Jun/Aug/Sep 2023.

The Random-Forest ceiling is emphatically a *2023* problem — 307.3 vs a 112.9 training
max, already documented at `scripts/03_train.py:130-133` and reflected in
`models/v1/training_ranges.json` (`model_ceiling.mean_upper = 90.1`). It is **not** the
2024 problem. Any Phase-2 experiment aimed at extending the model's upper range will not
move the 2024 numbers.

### The real shift is on the fire side — and it runs opposite to intuition

| Feature | Val-train mean / p99 / max | 2023 mean / p99 / max | 2024 mean / p99 / max |
|---|---|---|---|
| `hotspots_150_400km` | 25.3 / 449 / 1243 | 155.1 / 719 / **983** | 152.1 / 1242 / **1910** |
| `frp_150_400km` | 378 / 7,896 / 21,742 | 2,510 / 13,681 / 23,066 | 2,493 / **23,207** / **33,159** |
| `ufei_48h` | 265 / 5,354 / 15,775 | **2,581** / 9,507 / 12,958 | **1,230** / 12,085 / 24,286 |
| `ufei_from_ID` | 257 / 5,289 / 15,171 | 2,562 / 9,499 / 12,841 | 1,217 / 11,939 / 24,036 |
| `precip_24h_sum` | 15.25 / 87.2 / 199.9 | 16.63 / 101.6 / 149.8 | **10.26** / 55.4 / 77.6 |
| `boundary_layer_height` | 308 / 1,255 / 1,825 | 325 / 1,325 / 1,580 | 324 / 1,665 / **2,225** |

**2024 had more fire than 2023 but far less PM2.5.** Peak upwind hotspot count is 1,910
vs 983; `frp_150_400km` p99 is 23,207 vs 13,681. Yet peak PM2.5 is 66.4 vs 307.3, and
mean `ufei_48h` — the direction-weighted, distance-decayed exposure — is *half* 2023's
(1,230 vs 2,581). The 2024 fires were more numerous and more radiant but less
efficiently connected to the receptors: farther away, spikier, and differently aligned.
The fire → PM2.5 response function is not the same in the two years.

### 2024 *does* push fire features out of the trained range

Fraction of 2024 rows exceeding the validation model's training maximum:

| Feature | Val-train max | 2024 max | Rows above |
|---|---|---|---|
| `frp_150_400km` | 21,741.6 | 33,159.2 | **2.64%** |
| `hotspots_150_400km` | 1,243.0 | 1,910.0 | **1.00%** |
| `boundary_layer_height` | 1,825.0 | 2,225.0 | 0.57% |
| `ufei_from_ID` | 15,171.3 | 24,035.6 | 0.26% |
| `ufei_48h` | 15,775.0 | 24,286.2 | 0.24% |

A Random Forest cannot extrapolate on *inputs* any more than on outputs: past the
trained range it returns the response learned at the edge. For the validation model that
edge was set largely by a weak La Niña season (see §5). So on exactly the hours with the
heaviest upwind fire loading, the forest returns a mild-season answer. This is the one
genuine model weakness in the diagnosis, and it is an *input*-range problem, not the
output-ceiling problem the brief anticipated.

---

## 4. Threshold calibration

### Where the thresholds live

Two independent knobs, applied in different places.

**(a) The concentration threshold, 35.5 µg/m³.** EPA `UNHEALTHY_SENSITIVE` floor, defined
as data in `src/haze/alerts/thresholds.py:14-21` and returned by `alert_threshold()`
(`thresholds.py:81-94`). It is **not tuned** — it is the published EPA breakpoint, and
`institution_type` no longer affects it at all (`thresholds.py:90`, `del institution_type`).
A per-type sensitivity factor was tried and removed, with the reasoning recorded inline at
`thresholds.py:28-44`.

Applied at:
- `src/haze/models/evaluate.py:168` — scoring (`threshold = thresholds.alert_threshold(inst.type).pm25`)
- `src/haze/alerts/rules.py:119` — live alert construction
- `src/haze/pipeline/precompute.py:278` — scenario precompute
- `src/haze/alerts/thresholds.py:64-69` (`categorise`) — Safe/Watch/Alert labelling for display

**(b) The trigger percentile, p90.** `src/haze/config.py:93`
(`ALERT_TRIGGER_PERCENTILE = 90`). Alerts fire on the p90 upper band across trees rather
than the point forecast (`rf.predict_with_spread`, `src/haze/models/rf.py:167-181`;
consumed at `03_train.py:86` and `06_validate_events.py:182`).

### Was the operating point tuned on primary validation data only? **Yes.**

The sweep recorded in the config comment (`src/haze/config.py:86-92`):

```
#   p75 -> hit 58.2% / FAR 14.6%      p90 -> hit 79.5% / FAR 25.4%   <- chosen
#   p80 -> hit 63.4% / FAR 17.1%      p95 -> hit 90.1% / FAR 33.6%
#   p85 -> hit 69.8% / FAR 20.8%
# p90 is the most aggressive setting that still keeps false alarms under 30%.
```

These are verbatim the `trigger_sweep` block in `models/v1/metrics.json` — i.e. the 2023
held-out window, scored with the served model. The selection rule ("keep FAR under 30%")
was applied to 2023 alone. To the project's credit the sweep is recomputed and published
on every run rather than frozen, but the *choice* of p90 was never revisited against 2024.

### Does recalibrating on 2024 alone change FAR / hit rate meaningfully? **No.**

The 2024 sweep already exists in `models/v1/metrics_by_event.json` — no retraining
needed to answer this:

| Percentile | 2023 hit / FAR | 2024 hit / FAR |
|---|---|---|
| p75 | 57.7% / 13.8% | 27.5% / 29.7% |
| p80 | 61.2% / 16.1% | 32.7% / 33.1% |
| p85 | 66.9% / 20.7% | 40.2% / 37.8% |
| **p90** | **75.9% / 26.5%** | **53.8% / 45.0%** |
| p95 | 90.3% / 33.7% | 71.6% / 54.1% |

(2023 column is the *validation* model, the like-for-like comparison.)

At matched FAR (~30%, p75) the 2024 hit rate is 27.5% — *worse* than at p90. At matched
hit rate (~79%) 2024 would need beyond p95, with FAR above 54%. **The entire
precision-recall curve is displaced, not the operating point on it.** Moving the
percentile trades along the 2024 curve; it cannot reach the 2023 curve. Recalibration is
not the fix.

### But the FAR comparison is invalid in the first place

As implemented (`src/haze/models/evaluate.py:188-190`), false alarm rate is

```python
false_alarms / (hits + false_alarms)
```

which is **1 − precision**. Precision depends on how often the event actually occurs.
The alertable-hour base rate — the fraction of issuance hours where observed PM2.5
breaches 35.5 within the 24 h horizon — differs sharply between the windows:

- **2023: 42.55%** (3,738 of 8,784 hours)
- **2024: 18.20%** (1,599 of 8,784 hours)

Inverting each published (hit rate, FAR, prevalence) triple back to a prevalence-free
false-positive rate, FPR = FP / (1 − π):

| Run | Prevalence π | Hit rate | FAR | **Implied FPR** |
|---|---|---|---|---|
| 2023, served model | 0.4255 | 79.5% | 25.4% | **20.0%** |
| 2023, validation model | 0.4255 | 75.9% | 26.5% | **20.2%** |
| 2024, validation model | 0.1820 | 53.8% | 45.0% | **9.8%** |

**The model's false-positive rate halved in 2024.** Its specificity went from 80.0% to
90.2%.

The counterfactual makes the point sharper. Hold the 2023 model's sensitivity *and*
specificity completely fixed and change only the base rate to 2024's:

> hit 79.5%, FPR 20.0%, π = 0.182 → **FAR = 53.1%**

That is *worse* than the 45.0% actually observed. A model performing identically well in
both years would have reported a bigger FAR degradation than the one being investigated.

**The FAR regression should be retracted as a finding.** It is a base-rate artifact of a
precision metric compared across windows with a 2.3× difference in prevalence. Only the
hit-rate drop is a real signal.

---

## 5. Training data volume, ENSO phase, and the denominator defect

### Volume and fire-season coverage

| | Served / primary model | Validation model |
|---|---|---|
| Train rows | 109,728 | 100,512 |
| Distinct hours | 18,288 | 16,752 |
| Distinct days | **762** | **698** |
| Aug 1 – Oct 31 2022 in train | 92.0 d | 92.0 d |
| Aug 1 – Oct 31 2023 in train | 31.0 d | 30.0 d |
| Aug 1 – Oct 31 2024 in train | **92.0 d** | **29.0 d** |
| **Complete fire seasons** | **2** | **1** |

The primary model has two complete fire seasons; the 2024-check model has one. The
archive itself is the binding constraint: CAMS PM2.5 via Open-Meteo begins ~Aug 2022
(`src/haze/config.py:66-67`, "verified: 2019/2021 return nulls") and the FIRMS 2025
country archive was still unpublished (`config.py:57-58`, "verified 404"). So the whole
project has **three** fire seasons to work with, and any leave-one-season-out design
leaves at most two.

### ENSO phase — not documented anywhere

There is no ENSO phase recorded in code, config, features, or any model artifact. The
only mention in the repository is prose in the 2022 rejection note
(`scripts/06_validate_events.py:88-91`):

> *"Upwind fire activity is roughly a sixth of 2024's, consistent with the third year of a
> triple-dip La Nina suppressing Indonesian burning."*

From the historical record, and consistent with what the data shows:

| Year | ENSO phase | Aug–Oct evidence in this dataset |
|---|---|---|
| 2022 | La Niña (3rd year, triple-dip) | Pontianak peak 82.4; Kuching peak 31.7, **never** crosses 35.5; 18 observed episodes |
| 2023 | Strong El Niño onset | Pontianak peak 307.3; Kuching peak 53.0; 150 observed episodes |
| 2024 | El Niño decay → neutral | Pontianak peak 66.4; Kuching peak 54.1; 81 observed episodes |

(Figures from the `reconnaissance` block of `models/v1/metrics_by_event.json`, computed
fresh on each run by `06_validate_events.py:99-152`.)

**This is the core of the one genuine model weakness.** The validation model's single
complete fire season is 2022 — the *weakest* regime in the archive, with roughly a sixth
of 2024's upwind fire activity — and it is asked to forecast an El Niño-decay season it
has never seen. It has no feature that could tell it which regime it is in: `doy_*` is
identical every year, and there is no dryness or ENSO term (§1).

### The denominator defect — affects both numbers equally

The six institutions are not six independent receptors.

The three Pontianak sites sit within ~3 km of each other (`src/haze/institutions.py:73-74,
88-89, 103-104`), as do the three Kuching sites (`institutions.py:136-137, 151-152,
166-167`) — well inside a CAMS reanalysis grid cell. Their series are **bit-identical**:

```
PM2.5 pairwise correlation
                  id-ptk-bpbd  id-ptk-sman1  id-ptk-soedarso  my-kch-greenroad  my-kch-hus  my-kch-jpbn
id-ptk-bpbd            1.0000        1.0000           1.0000            0.2292      0.2292       0.2292
id-ptk-sman1           1.0000        1.0000           1.0000            0.2292      0.2292       0.2292
id-ptk-soedarso        1.0000        1.0000           1.0000            0.2292      0.2292       0.2292
my-kch-greenroad       0.2292        0.2292           0.2292            1.0000      1.0000       1.0000
my-kch-hus             0.2292        0.2292           0.2292            1.0000      1.0000       1.0000
my-kch-jpbn            0.2292        0.2292           0.2292            1.0000      1.0000       1.0000
```

An exact-equality check confirms it is identity, not merely correlation ~1.

> **Corrected in Phase 2A.** This paragraph originally claimed that receptor weather is
> identical within *each* trio. That is true of Pontianak but wrong for Kuching: ERA5 is
> finer than CAMS and resolves `my-kch-jpbn` to its own cell, so the weather features form
> **three** distinct series (Pontianak trio; `greenroad`+`hus`; `jpbn`) against PM2.5's
> **two**. Episode counts below are unaffected, because episodes are defined on observed
> PM2.5. See §Phase 2 Results.

Receptor weather (`wind_speed_10m`, `relative_humidity_2m`, `boundary_layer_height`,
`temperature_2m`) is identical across all three Pontianak sites and across
`my-kch-greenroad` / `my-kch-hus`, with `my-kch-jpbn` distinct. Only the fire-geometry features differ
at all, and only trivially — the ~3 km coordinate offsets make `ufei_48h` numerically
distinct on ~96% of hours but with a **median relative difference of 0.48%** (Pontianak)
and **0.26%** (Kuching), while the ring counts `hotspots_150_400km` / `frp_150_400km` are
outright identical on 87% of hours within the Pontianak trio and 66% within the Kuching
trio. The targets are identical everywhere.

Three consequences:

1. **Six "sites" are two.** Effective training sample is ~1/3 of the stated row count:
   18,288 distinct hours, not 109,728 rows.
2. **The six `site_*` one-hot features are near-noise.** The forest can only tell the
   members of a trio apart through UFEI differences present on ~4% of hours, and their
   targets are identical anyway.
3. **Every episode count is inflated 3×.** Recomputing `evaluate._exceedance_events`
   per *city* rather than per institution:

| Window | Reported episodes | Distinct episodes |
|---|---|---|
| 2023 | 99 | **33** (Pontianak 15, Kuching 18) |
| 2024 | 63 | **21** (Pontianak 5, Kuching 16) |

The 2024 hit rate of 53.8% rests on 21 distinct observed episodes, not 63. The published
per-country breakdown `ID: hit 42.7%, 15 episodes` for 2024 rests on **five** distinct
episodes. At that sample size the difference between 75.9% and 53.8% is well inside
sampling noise, and no confidence interval computed from n=63 is valid.

### 2024 events are marginal, and the window is intrinsically harder

| | 2023 window | 2024 window |
|---|---|---|
| Hours ≥ 35.5 | 1,707 (19.43%) | 360 (4.10%) |
| Median exceedance value | 58.8 | **41.7** |
| Share of exceedances in [35.5, 45) | 30.1% | **65.0%** |
| Alertable hours with 24 h peak < 55.4 | 48.2% | **94.7%** |
| Median 24 h peak among alertable hours | 68.5 | **44.2** |

Two-thirds of 2024's exceedances sit within 10 µg/m³ of the threshold, and 94.7% of its
alertable hours never reach even the next EPA category. At +24 h the model's MAE on the
2024 window is 5.47 µg/m³ — genuinely good, and better in absolute terms than the 13.28
on 2023 — but an error of 5.47 flips the classification of an event whose true peak is
41.7. Marginal events are where a good regressor makes a bad classifier.

**A model-free baseline confirms the window is harder.** Scoring the same
`evaluate.alert_metrics` with pure persistence (current PM2.5 carried to all 24 leads,
zero model skill):

| Window | Persistence hit rate | Persistence FAR |
|---|---|---|
| 2023 | **44.1%** | 3.3% |
| 2024 | **20.1%** | 10.8% |

Persistence loses 54% of its hit rate moving from 2023 to 2024, before any model is
involved. The Random Forest loses 29% (75.9 → 53.8) on the like-for-like comparison. By
that yardstick the model degrades *less* than the trivial baseline does.

---

## 6. Ranked root causes

Ranked by contribution to the observed gap, not by how interesting they are to fix.

### 1. The FAR comparison is a base-rate artifact — the finding should be retracted

**Evidence:** §4. FAR = 1 − precision; prevalence is 42.55% vs 18.20%. Implied FPR is
20.0% (2023) vs 9.8% (2024). Holding 2023's sensitivity and specificity fixed and moving
only to 2024's base rate predicts FAR = 53.1%, worse than the 45.0% observed.

**Effort:** none — documentation only. Report FPR (or specificity) alongside FAR in
`evaluate.alert_metrics`, and state prevalence next to every FAR.

**Expected impact:** eliminates ~20 points of apparent degradation. The honest statement
is that specificity *improved* by roughly a factor of two.

### 2. Two different models are being compared as if they were one

**Evidence:** §2. The primary number comes from a model with two complete fire seasons
and no embargo; the 2024 number from a model with one season and a 24 h embargo. The
same-model, same-event control already exists in `metrics_by_event.json`: the validation
model scores **75.9%** on the 2023 window vs the served model's 79.5%. Withholding the
2024 season costs 3.7 points on an event neither model has seen.

**Effort:** none for framing; medium (one retraining run, several hours) for a proper
leave-one-season-out protocol with matched embargo.

**Expected impact:** ~4 points of the hit-rate gap. The correct like-for-like comparison
is 75.9% → 53.8%, not 79.5% → 53.8%.

### 3. Event difficulty — 2024's exceedances are marginal

**Evidence:** §5. 65.0% of 2024 exceedances lie in [35.5, 45) vs 30.1% in 2023; median
exceedance 41.7 vs 58.8; 94.7% of alertable hours peak below 55.4. Persistence alerting
degrades 44.1% → 20.1% across the same two windows with no model involved.

**Effort:** none for framing; medium to add a severity-stratified hit rate (hit rate on
episodes peaking above 55.4 vs below) to `evaluate.alert_metrics`.

**Expected impact:** explains most of the residual hit-rate drop. Expect the
severity-stratified number to show 2024 performance on non-marginal episodes far closer
to 2023's.

### 4. One weak fire season in training, and no interannual regime signal — the real weakness

**Evidence:** §1 (no ENSO, no dryness beyond 24 h), §3 (2.64% of 2024 rows past the
trained `frp_150_400km` range; more fire but less PM2.5 than 2023), §5 (the validation
model's only complete season is 2022, a triple-dip La Niña with ~1/6 of 2024's fire
activity). `doy_*` is identical every year and cannot carry regime information.

**Effort:**
- *Low* (~half a day in `src/haze/features/build.py`) for a monthly ONI index joined on
  date, plus a consecutive-dry-days counter derived from the `precipitation` column
  already present. Both are additive and require no new data source for the dry-days term.
- *High* / blocked for more training seasons: CAMS via Open-Meteo starts Aug 2022
  (`config.py:66`) and the FIRMS 2025 archive was 404 (`config.py:57-58`). Three seasons
  is the ceiling until the 2025 archive publishes.

**Expected impact:** modest but real hit-rate gain on out-of-regime seasons — plausibly a
few points, concentrated on the high-fire hours where the forest currently saturates.
Will not close the gap on its own, because most of the gap is not a model deficiency.
This is nonetheless the item worth actually building.

### 5. Duplicate receptor series inflate every denominator 3×

**Evidence:** §5. PM2.5 and all receptor weather are bit-identical within each city trio;
99 episodes are 33 distinct, 63 are 21 distinct; the 2024 Indonesian hit rate rests on 5
distinct episodes.

**Effort:** low to score honestly — deduplicate to one receptor per city before computing
metrics, and report distinct-episode counts. Medium to fix structurally: drop to two
receptors, or source genuinely distinct PM2.5 series (ground stations rather than a
~40 km reanalysis grid) if per-institution resolution is required by the product.

**Expected impact:** rates barely move (the trios are near-duplicates, so pooled rates
already approximate the 2-site rates). What changes is *confidence*: at 21 distinct
episodes, the 53.8% figure carries a very wide interval, and much of the 75.9% → 53.8%
difference may be sampling noise. This should be quantified before any modeling effort is
justified by it.

### 6. Hygiene: p90 tuned on 2023 only, and the served split runs with no embargo

**Evidence:** §4 (`config.py:86-92` reproduces the 2023 sweep verbatim), §2
(`03_train.py:41` uses the default `embargo_hours=0`).

**Effort:** low. Set `embargo_hours=24` in the served split for symmetry; re-select the
operating point against pooled multi-season data once more than one season is scorable.

**Expected impact:** small. The 2024 sweep shows no percentile recovers 2023-like
performance, and the embargo affects 0.13% of training rows. Record as hygiene, not as a
cause.

---

## 7. Suggested Phase-2 experiments

Not run. Ordered by information gained per hour of work.

1. **Severity-stratified hit rate** (no retraining — rescore existing predictions).
   Split 2024 episodes at 55.4 µg/m³ and report separately. Directly tests root cause 3.
2. **Deduplicated rescoring** (no retraining). Recompute all published metrics on one
   receptor per city, with distinct-episode counts and bootstrap intervals. Tests root
   cause 5 and tells us how much of the gap is noise.
3. **Report FPR / specificity alongside FAR** in `evaluate.alert_metrics`. Two lines of
   code; permanently prevents root cause 1 from recurring.
4. **Leave-one-season-out with matched embargo** (one retraining run). Train three
   models, each missing one Aug–Oct season, and score each on its held-out season with
   identical settings. The only genuinely like-for-like generalization protocol available
   with three seasons.
5. **ONI + consecutive-dry-days ablation** (feature build + one retraining run). Tests
   root cause 4 directly. Compare against the current feature set on the leave-one-season-out
   protocol from (4), not against the existing numbers.

---

## Scope note

This was a read-only investigation. No model training code, feature pipeline, threshold,
or deployment path was modified; `data/replay/` and the demo scenario were not touched.
The only file created is this report. Every number above is reproducible from
`data/processed/features.parquet` and the committed `models/v1/*.json` artifacts without
retraining.

---
---

# Phase 2 Results

**Branch `phase2-generalization-fixes`. Phase 2A only — stopped at the review checkpoint.**

Artifacts: `scripts/09_rescore_dedup.py` (new), `diagnostics/dedup_rescore.json` (new),
one helper and one optional parameter added to `src/haze/models/evaluate.py`.
`models/v1/`, `data/replay/`, `frontend/`, and every deploy path are byte-unchanged.

## 2A.1 Root cause — there is no join/broadcast bug

Phase 2A was briefed on the hypothesis that "a join/broadcast step assigns one city-level
value to all institutions in that city instead of per-institution estimation." **That
hypothesis is wrong, and the code exonerates itself.**

`src/haze/features/build.py:137` calls `weather.air_quality(inst.lat, inst.lon, ...)` once
per institution. `weather._cache_path` (`src/haze/ingest/weather.py:40-43`) keys the cache
on `(kind, lat, lon, start, end, variables)`, so the six institutions produce six distinct
cache keys, six distinct files on disk, and six separate HTTP requests that were actually
made. Nothing broadcasts anything.

The duplication arrives **from CAMS**. Reading the echoed grid coordinates and hashing the
`pm2_5` arrays in the six cached payloads:

| Institution | Requested | Echoed CAMS cell | `pm2_5` SHA-256 (16) |
|---|---|---|---|
| id-ptk-sman1 | (-0.0263, 109.3425) | (0.0, 109.30002) | `d82d5744d791ff99` |
| id-ptk-bpbd | (-0.0349, 109.3300) | (0.0, 109.30002) | `d82d5744d791ff99` |
| id-ptk-soedarso | (-0.0554, 109.3389) | (-0.099998, 109.30002) | `d82d5744d791ff99` |
| my-kch-hus | (1.5350, 110.3480) | (1.5, 110.30002) | `6c0e10c200a595da` |
| my-kch-greenroad | (1.5385, 110.3560) | (1.5, 110.399994) | `6c0e10c200a595da` |
| my-kch-jpbn | (1.5533, 110.3592) | (1.5999985, 110.399994) | `6c0e10c200a595da` |

**Five distinct grid cells returned two distinct PM2.5 series.** Open-Meteo accepts and
echoes a 0.1° display lattice, but CAMS global atmospheric composition is ~0.4° native, so
neighbouring cells serve identical underlying data. The institutions are ~3 km apart. No
code change can recover detail the product never contained.

By contrast **ERA5 is finer and does resolve them**: `my-kch-jpbn` maps to its own cell
(1.5817, 110.3249) with a different wind series. So receptor weather forms **three**
distinct series while PM2.5 forms **two**.

> **Correction to Phase 1.** §5 originally stated that receptor weather is identical within
> each trio. That holds for Pontianak but not Kuching. Corrected in place above, and flagged
> here rather than changed silently. Episode counts are unaffected — episodes are defined on
> observed PM2.5, which remains two distinct series.

## 2A.2 What was changed instead

Per the checkpoint decision, the fix is at the **metrics layer**: stop the numbers claiming
six independent receptors, rather than fabricating per-site variation.

- **`evaluate.distinct_receptors(df)`** — clusters institutions by equality of their observed
  PM2.5 series and returns one representative each. It clusters on the *data*, not on `city`,
  so it detects duplication instead of assuming it and becomes a no-op automatically if the
  PM2.5 source is ever upgraded. Returns `['id-ptk-bpbd', 'my-kch-greenroad']`.
- **`evaluate.alert_metrics(..., receptors=None)`** — optional filter on the existing
  per-institution loop. Default `None` preserves current behaviour exactly; verified by
  43/43 tests passing and by an assertion that `receptors=None` returns a dict identical
  to the default call.

Neither `scripts/03_train.py` nor `scripts/06_validate_events.py` was modified.

## 2A.3 Recomputed metrics — old vs new (guardrail 4)

`scripts/09_rescore_dedup.py` loads the served model for the primary run and retrains the
throwaway validation model exactly as `06_validate_events.py` does (`random_state=42`,
24 h embargo, both events withheld), then scores each window twice.

**The as-published column reproduces the published figures exactly.** That was the
precondition for trusting anything else here, and it held: 79.5 / 25.4 / 99 and
53.8 / 45.0 / 63 came back identical.

| Run | Metric | **Published (old)** | **Deduplicated (new)** |
|---|---|---|---|
| Primary — served model, 2023 | Hit rate | **79.5%** | **79.5%** |
| | False alarm rate | **25.4%** | **25.4%** |
| | Episodes | **99** | **33** |
| Validation model, 2023 | Hit rate | 75.9% | 76.3% |
| | False alarm rate | 26.5% | 26.5% |
| | Episodes | 99 | **33** |
| Validation model, 2024 | Hit rate | **53.8%** | **53.8%** |
| | False alarm rate | **45.0%** | **44.8%** |
| | Episodes | **63** | **21** |

**Only the episode counts materially change.** Rates move by at most 0.45 pt (the validation
model's 2023 hit rate, 75.87% → 76.32%), because the trio members carry slightly different
UFEI features and therefore slightly different predictions — the copies are near-identical
but not quite identical. Median lead time is 24 h in every case, unchanged.

So: **the published rates are sound; the sample size behind them was overstated threefold.**

## 2A.4 Truly independent episodes, and what they support

| Window | Reported | Distinct | Breakdown |
|---|---|---|---|
| 2023 | 99 | **33** | Pontianak 15, Kuching 18 |
| 2024 | 63 | **21** | Pontianak 5, Kuching 16 |

The per-country figure published for 2024 (`ID: hit 42.7%, 15 episodes`) rests on **five**
distinct episodes and should not be quoted.

Two things become visible once the counts are honest.

**(a) The hour-level hit rate is not the episode-level detection rate.** `alert_metrics`
reports an hour-level statistic: of issuance hours with a breach coming, how many carried a
warning. That is not the same as "of the episodes that happened, how many did we warn about."
Computing the second directly over distinct episodes:

| Window | Hour-level hit rate | **Episode detection rate** | 95% CI (bootstrap, distinct episodes) |
|---|---|---|---|
| 2023 (served) | 79.5% | **93.9%** of 33 | [84.9%, 100.0%] |
| 2023 (validation model) | 76.3% | **93.9%** of 33 | [84.9%, 100.0%] |
| 2024 (validation model) | 53.8% | **81.0%** of 21 | [61.9%, 95.2%] |

At the level a head teacher would recognise — *did the system warn me about this episode* —
the gap is **93.9% → 81.0%**, and the intervals overlap heavily. That is a very different
story from 79.5% → 53.8%. Both are legitimate statistics; only one of them was being quoted.

Only the episode-level rate carries an interval. Issuance hours within an episode are
strongly autocorrelated, so a naive interval on the hour-level hit rate would be far too
narrow, and with two receptors there is no honest way to widen it.

**(b) The Phase 1 base-rate explanation is confirmed from predictions, not by inversion.**
Phase 1 derived the false-positive rate algebraically from published rates. This run computes
it directly:

| Window | Prevalence | **Specificity** | FPR |
|---|---|---|---|
| 2023 (served) | 42.55% | **80.0%** | 20.0% |
| 2023 (validation model) | 42.55% | 79.6% | 20.4% |
| 2024 (validation model) | 18.20% | **90.3%** | 9.7% |

Phase 1 predicted 20.0% and 9.8% by inversion; direct computation gives 20.0% and 9.7%. The
FAR "regression" remains a base-rate artifact, and it survives deduplication unchanged.

## Consequence to decide at this checkpoint

`tests/test_metrics.py:69` asserts `events_evaluated >= 50`. Deduplicated, 2023 has **33**
distinct episodes, so that gate **would fail** if `models/v1/metrics.json` were ever
regenerated with `receptors=distinct_receptors(df)`. It passes today only because
`models/v1/` was deliberately left frozen. This needs a decision — relax the gate to a
distinct-episode threshold, or keep publishing inflated counts — and it is a decision, not
a workaround to apply quietly.

## Guardrail notes

- **Guardrail 3 (FIRMS):** Phase 2A required no new FIRMS data and made no network call.
  Looking ahead to 2D.4, the answer is already on disk and needs no pull: **three** fire
  seasons exist locally (2022, 2023, 2024 — `config.FIRMS_YEARS`), all three are already used
  in feature building, and no further season is obtainable — the FIRMS 2025 country archive
  returns 404 (`config.py:57-58`) and CAMS PM2.5 via Open-Meteo begins ~Aug 2022
  (`config.py:66-67`). More seasons would require new data acquisition, so per guardrail 3
  this is flagged, not attempted.
- **Guardrail 5 (Section 7 ordering):** Section 7 ranked severity-stratified hit rate #1 and
  deduplicated rescoring #2; the brief put dedup first. I followed the **brief's** order,
  because deduplication changes the denominators that severity-stratification would be
  computed on — running severity first would have meant redoing it. This is a deviation from
  Section 7 that strictly reduces total work rather than reordering priorities.

## Recommendation

**Keep** the `distinct_receptors` / `receptors=` change. It is opt-in, costs nothing when
unused, and self-disables if the data source improves.

**Report episode detection rate alongside the hour-level hit rate.** It is the metric that
matches how the product is described, and it narrows the apparent 2024 gap from 25.7 points
to 12.9 with overlapping confidence intervals.

**Do not restate the 2024 result as a 53.8%-vs-79.5% failure.** On the evidence now
available it is: same specificity story inverted (80.0% → 90.3%), episode detection
93.9% → 81.0% on 21 independent episodes, and confidence intervals that overlap.

**Still open before 2B–2D:** whether to regenerate `models/v1/` with deduplicated counts and
adjust the test gate.
