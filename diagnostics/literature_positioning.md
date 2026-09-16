# Positioning memo: what "forecast-to-alert" can and cannot claim

Written 2026-09-01. Internal. Nothing in this repository currently makes a novelty or
priority claim — the phrase "forecast-to-alert" appears nowhere in the code, the README,
`SYSTEM_FLOW.md`, `USER_FLOW.md`, or the frontend. This memo exists because the claim
lives in external pitch material, and the caveat needs to travel with it.

**Bottom line: do not claim to be first. The defensible claim is narrower, and it survives
scrutiny; the broad one does not.**

---

## 1. What was searched, and what was not

A targeted search, September 2026, in English only:

| Query theme | Purpose |
|---|---|
| transboundary haze PM2.5 forecasting early-warning ML Southeast Asia | academic state of the art |
| ASMC / institution-level / last-mile haze alerting | operational regional infrastructure |
| forecast-driven vs observed-threshold alerting, school closure decisions | the specific mechanism claimed |
| transboundary attribution, Kalimantan → Sarawak prototypes | the specific corridor |

**Not covered, and this is the boundary of the claim:**

- Indonesian- and Malay-language literature, which is where BMKG, BPBD, NREB Sarawak and
  DOE Malaysia operational documentation would live. This is the largest gap: a system
  built by a national agency for its own institutions would most likely be documented in
  the national language and not indexed by an English query.
- Grey literature — agency internal tooling, NGO pilots, donor-funded prototypes,
  university projects without publication.
- Patents.
- Anything behind a paywall not surfaced by the search.
- Systematic database querying (Scopus, Web of Science) with recorded result counts. This
  was a search, not a systematic review, and it should never be described as one.

---

## 2. What already exists

**Regional forecast + alerting: occupied, at regional scale.**
The ASEAN Specialised Meteorological Centre (ASMC) is mandated to provide early warning of
transboundary haze, issues advisories on a three-tier scale (green/amber/red), updates
twice daily, and explicitly accounts for hotspot counts, forecast rainfall and prevailing
winds. During the 2026 season it raised the southern-ASEAN alert to Level 3 for haze from
Kalimantan hotspots. It has also issued corridor-specific warnings for exactly this
corridor — an ASMC warning of elevated transboundary haze risk *between West Kalimantan
and Sarawak* was reported in September 2023.

This matters: **the "West Kalimantan → Sarawak" transboundary framing is not new, and ASMC
already forecasts and warns on it.** What ASMC does not do is resolve to a named school.

**Institution-level thresholds: occupied, but reactive.**
Malaysian protocols suspend outdoor activities when the API exceeds 100 and close schools,
kindergartens and nurseries when it exceeds 200. These are institution-level and
consequential — but they trigger on the *observed* index, not on a forecast. The head
teacher acts when the air is already bad.

**Academic PM2.5 forecasting: crowded.**
Many published ML forecasters for Southeast Asian receptors — Bangkok, Hat Yai, Ho Chi Minh
City, Penang, upper northern Thailand, Malaysia-wide from a global model. Several
explicitly frame 1–7 day skill as adequate for early-warning use, and at least one makes
recommendations on integrating global forecast models into Malaysian early-warning systems.
Reported skill is broadly comparable to ours (e.g. Ho Chi Minh City: MAE 5.38 µg/m³,
R² 0.68 — on a different receptor and season, so not directly comparable).
**The forecasting is not the contribution.** These papers generally stop at the forecast
and do not build the alerting, attribution and last-mile layer on top.

**A recognised gap, named by others.**
RFMRC-SEA argues a dedicated regional haze centre is "critically needed for the Borneo
region" to close the geographical distance "in real-time and granular terms". That is
useful and double-edged: it corroborates that Borneo-specific granular warning is missing,
and it proves the gap is already publicly identified. **Identifying it is not novel.**

---

## 3. What is actually defensible

Not "the first forecast-to-alert system". Three things are each individually occupied —
forecasting (academic literature), transboundary attribution (ASMC), and institution-level
thresholds (national protocols). The candidate contribution is the **coupling**:

> a site-level forecast, attributed to a source region across a national border, driving an
> institution-level alert with an explicit warning lead time — for named institutions on
> both sides of the Indonesia–Malaysia border in Borneo.

Even this should be stated as *"we did not find"*, never *"there is no"*. Given the
un-searched Indonesian/Malay-language and grey literature, absence of evidence here is
weak evidence of absence — and the national agencies are precisely the actors most likely
to have built something like this without an English-language paper.

---

## 4. Recommended wording

**Use this (narrowed, defensible):**

> Regional infrastructure already forecasts transboundary haze and warns on it — the ASEAN
> Specialised Meteorological Centre issues tiered haze advisories twice daily, including
> for the West Kalimantan–Sarawak corridor specifically. National protocols already act at
> institution level, but on *observed* air quality: Malaysian schools close when the API
> passes 200. What we did not find in a targeted English-language search is the coupling of
> the two — a forecast, attributed across the border, driving a named institution's alert
> with an explicit lead time, before the air degrades. We make no priority claim: our
> search did not cover Indonesian- or Malay-language sources, agency grey literature, or
> patents, and national agencies are exactly where comparable work would most likely sit.

**Do not use:**

- "The first system to go from forecast to alert." Unsupported, and ASMC is a
  counterexample at regional scale.
- "Nobody warns institutions about haze." False — API-threshold school closures do exactly
  that, and are the status quo this should be positioned *against*, not as if absent.
- "We identified a gap nobody has noticed." RFMRC-SEA published the same observation.
- Any framing that drops the "targeted, not exhaustive" caveat into a footnote. In a
  spoken pitch the caveat must be in the same breath as the claim, because that is the
  sentence a judge will quote back.

---

## 5. The strongest honest framing

The competitive advantage to lead with is **not** novelty. It is the honesty apparatus,
which is unusual and is verifiable on the spot:

- baseline-relative reporting everywhere, never a bare R² or MAE;
- a second held-out season published *because* it is weaker (episode detection 93.9% → 81.0%);
- a censored statistic labelled as censored, with the ceiling share measured (64.5%);
- a retracted claim left visible in the README rather than deleted (the daily-correlation
  refit came back null and says so);
- tests that fail the build when a published number stops being true.

"We tested our own headline claim and it lost" is a stronger thing to say to a judge than
"we are first", and unlike "we are first" it cannot be falsified by one better-informed
person in the room.

---

## Sources

- [ASMC — Regional Haze Situation](https://asmc.asean.org/home/) and [ASMC Alerts](https://asmc.asean.org/asmc-alerts/)
- [ASMC warns of elevated risk of transboundary haze between West Kalimantan and Sarawak (Malay Mail, 2023)](https://www.malaymail.com/news/malaysia/2023/09/04/asmc-warns-of-elevated-risk-of-transboundary-haze-between-west-kalimantan-sarawak/88907)
- [The Role of the ASEAN Specialised Meteorological Centre (ASMC) to Be Expanded](https://weather.ou.edu/~spark/AMON/v1_n2/ASMC.html)
- [Assessment of Malaysia-wide PM2.5 Forecasts from a Global Model (AAQR)](https://aaqr.org/articles/aaqr-22-12-oa-0444)
- [PM2.5 Forecast System Using Machine Learning and WRF, Ho Chi Minh City (AAQR)](https://aaqr.org/articles/aaqr-21-05-oa-0108)
- [Deep learning and statistical approaches for area-based PM2.5 forecasting in Hat Yai, Thailand (J. Big Data)](https://link.springer.com/article/10.1186/s40537-025-01079-9)
- [Long-Term Retrospective Predicted Concentration of PM2.5 in Upper Northern Thailand (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11946178/)
- [Comparative analysis of ML models for PM10 and PM2.5 in Pulau Pinang, Malaysia (AQAH)](https://link.springer.com/article/10.1007/s11869-026-01915-8)
- [Solving transboundary haze — RFMRC-SEA](https://rfmrc-sea.org/solving-transboundary-haze/)
- [Extinguishing a Point of Contention: Examining Transboundary Haze in Southeast Asia (CSIS)](https://www.csis.org/blogs/new-perspectives-asia/extinguishing-point-contention-examining-transboundary-haze-southeast)
- [Transboundary Air Quality Alert: Kuching, Malaysia most polluted major city (IQAir)](https://www.iqair.com/newsroom/transboundary-air-quality-alert-kuching-malaysia-most-polluted-major-city)
