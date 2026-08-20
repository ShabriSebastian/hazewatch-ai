# HazeWatch AI — corrected metrics report

Generated 2026-08-20T13:47:00Z. Model version `1.0.0`, unchanged by this report.

> This supersedes the alert figures in `models/v1/metrics.json`, which is
> left frozen for competition reproducibility and predates the receptor fix.
> Episode counts there are inflated threefold; the counts below are distinct.

## Spatial resolution — what the data can tell apart

**Source:** CAMS reanalysis via Open-Meteo, ~0.4° native.  
**6 institutions resolve to 2 receptors.**

| Receptor | Institutions sharing this grid cell |
|---|---|
| `id-ptk-bpbd` | `id-ptk-bpbd`, `id-ptk-sman1`, `id-ptk-soedarso` |
| `my-kch-greenroad` | `my-kch-greenroad`, `my-kch-hus`, `my-kch-jpbn` |

CAMS global composition is ~0.4 degrees native. The Pontianak institutions sit ~3 km apart, as do the Kuching ones, so each trio shares one grid cell and receives an identical PM2.5 series. Forecasts and alerts are per-locality, not per-institution. Institutions listed together cannot be distinguished by this data source, and no metric here should be read as evidence about one site rather than its locality.

Forecasts and alerts are **per-locality, not per-institution**. Three Pontianak alerts agreeing is one forecast shown three times, not three confirmations.

## Alert performance

Two rates are co-primary. `hit rate` is hour-level; `episode detection` is the share of distinct observed episodes warned about before onset. `specificity` is prevalence-free and is the figure to compare across seasons — `false alarm rate` is 1−precision and moves with the base rate on its own.

| Run | Hit rate (hourly) | Episode detection (95% CI) | Specificity | FAR | Prevalence | Distinct episodes |
|---|---|---|---|---|---|---|
| Primary — served model, Aug–Oct 2023 | 79.5% | 93.9% [80.4%, 98.3%] | 80.0% | 25.4% | 42.5% | 33 |
| Validation model, Aug–Oct 2023 | 76.3% | 93.9% [80.4%, 98.3%] | 79.6% | 26.5% | 42.5% | 33 |
| Validation model, Aug–Oct 2024 | 53.8% | 81.0% [60.0%, 92.3%] | 90.3% | 44.8% | 18.2% | 21 |

Alerts fire on the p90 band at the EPA `UNHEALTHY_SENSITIVE` floor of 35.5 µg/m³.

## Notes

- PM2.5 targets are ECMWF CAMS reanalysis, not ground-station measurements.
- Hotspots are NASA FIRMS detections; this system does not detect fires itself.
- Episode counts are distinct counts. The events_evaluated field in models/v1/metrics.json counts every institution and reports 99 where there are 33; it is superseded, not corrected in place.
- hit_rate is hour-level; episode_detection_rate is episode-level. Both are reported because they answer different questions and differ materially.
- specificity is prevalence-free. false_alarm_rate is 1-precision and is not comparable across seasons with different base rates.
