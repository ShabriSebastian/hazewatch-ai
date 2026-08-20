# HazeWatch AI — End-to-End System Flow

Transboundary haze early-warning for institutions in West Kalimantan (Indonesia) and
Sarawak (Malaysia). This document traces one path from raw satellite data to a human
pressing **Confirm & Send**.

Legend: `[ ]` process · `< >` decision · `( )` data store · `>>` user action · `!` honesty guardrail

---

## 0. The whole system at a glance

```
   PUBLIC DATA            OFFLINE PIPELINE           FROZEN API            BROWSER
  ┌───────────┐          ┌────────────────┐        ┌───────────┐        ┌──────────┐
  │ NASA FIRMS│          │ features ─ train│        │ 18 paths  │        │  Lite    │
  │ ECMWF CAMS│ ───────► │ validate ─ scen.│ ─────► │ /api/v1   │ ─────► │  Pro     │
  │ ERA5 wind │          │ contract export │        │ replay clk│        │ 8 routes │
  └───────────┘          └────────────────┘        └───────────┘        └──────────┘
       raw                  build once              read-only             human
    observations          (make data..validate)      + `?at=`           decides
```

---

## 1. Offline pipeline — run once, before any user arrives

```
 (NASA FIRMS hotspots)   (ECMWF CAMS PM2.5)   (ERA5 wind/weather)
          │                      │                     │
          └──────────┬───────────┴──────────┬──────────┘
                     ▼                      │
        [ 01_download.py ] ─── cached to (data/raw/)
                     ▼
        [ 02_build_features.py ]
           • upwind fire exposure index (UFEI) per institution
           • distance + wind bearing to each hotspot cluster
           • PM2.5 lags, calendar, met covariates
                     ▼
          (data/processed/features.parquet)  127,296 rows
```

**Spatial resolution.** UFEI and the hotspot geometry really are per-institution —
they depend on each site's own coordinates. The **PM2.5 target does not.** CAMS is
~0.4° native, and the three Pontianak institutions sit ~3 km apart, as do the three
Kuching ones, so each trio shares one grid cell and receives a byte-identical PM2.5
series. Forecasts and alerts are therefore **per-locality**: six institutions resolve
to two receptors. Three Pontianak alerts agreeing is one forecast shown three times,
not three confirmations. Recovering finer detail would need a different PM2.5 source
(ground stations), not a code change.

```
                     ▼
        [ 03_train.py ]  ── split: train ──────── test held out entirely
           │                (2023-08-16 .. 2023-10-15 excluded from training)
           ├─► RF-forecast   24 separate lead times (+1h … +24h)
           │     └─ prediction band = percentiles ACROSS 300 TREES
           │          p10 = pm25_lower · p50 = pm25_p50 · p90 = pm25_upper
           ├─► RF-attribution  fire+weather only, no PM2.5 lags → "is it transboundary?"
           └─► GRU  ..........  trained, LOST on held-out data (+24h MAE 13.68 vs 13.03)
                                 ! rejected model is REPORTED, not hidden
                     ▼
          (models/v1/*.joblib) + (metrics.json) + (training_ranges.json)
                     ▼
        [ 06_validate_events.py ]  second independent event (Sept 2024)
           ! retrains its own forests; refuses to touch served artifacts
                     ▼
        [ 04_precompute_scenario.py ] ──► (scenario_2023_sept.sqlite)
           every hour of the episode precomputed: observations, forecasts,
           alert states, notifications  → demo runs with no network, no GPU
                     ▼
        [ 05_offline_smoke_test.py ]  123 checks, Wi-Fi OFF  ── "safe to record"
        [ 00_export_contract.py ]     openapi.json — 18 paths, 43 schemas, FROZEN
```

---

## 2. The alert rule — one decision, applied identically everywhere

```
        forecast points (+1h … +24h)
                    │
                    ▼
   < is pm25_upper (p90) >= 35.5 µg/m³ at any point? >
                    │
        ┌───────────┴───────────┐
       NO                      YES
        │                       │
        ▼                       ▼
   no alert row        [ raise Alert ]
                          ├─ severity        = category of the PEAK UPPER value
                          ├─ lead_time_hours = hours to FIRST crossing   ◄── headline
                          ├─ peak_lead_hours = hours to WORST point      ◄── not headlined
                          ├─ threshold_pm25  = 35.5   (same for every institution type)
                          └─ recommended_actions = tailored to type + severity

   ! WHY p90 AND NOT THE CENTRAL FORECAST
     A missed episode and a false alarm are not equally costly. Triggering on the
     upper band buys lead time and accepts more false alarms — deliberately.
     The full trade-off curve is published, not just the chosen point:

        p75  58.2% hit / 14.6% false     p90  79.5% hit / 25.4% false  ◄── chosen
        p80  63.4% hit / 17.1% false     p95  90.1% hit / 33.6% false
        p85  69.8% hit / 20.9% false          (p95 breaches the 30% false-alarm cap)

   ! ONE THRESHOLD FOR EVERY INSTITUTION TYPE
     35.5 is the floor of EPA "Unhealthy for Sensitive Groups" — the category named
     for exactly the population a hospital serves. An earlier build discounted it to
     28.4 for hospitals; that double-counted the same allowance and emitted 96 alerts
     labelled MODERATE. Removed. Institution type now changes only WORDING.
```

---

## 3. Serving layer — the frozen contract

```
  GET  /api/v1/health ................ mode, data_source, clock
  GET  /api/v1/model/metrics ......... honest held-out skill (503 before training)
  GET  /api/v1/institutions .......... 6 sites, 3 per country
  GET  /api/v1/institutions/{id}
  GET  /api/v1/hotspots .............. raw FIRMS detections
  GET  /api/v1/hotspots/summary ...... gridded for map rendering
  GET  /api/v1/institutions/{id}/forecast     ?horizon_hours= ?at=
  GET  /api/v1/institutions/{id}/observation  ?at=
  GET  /api/v1/institutions/{id}/alert        ?at=      alert=null when clear
  GET  /api/v1/alerts ................ ?status= ?country= ?transboundary= ?at=
  GET  /api/v1/notifications ......... simulated last-mile feed, newest first
  POST /api/v1/notifications/simulate  ◄── EXISTS, deliberately UNUSED by the UI
  GET  /api/v1/replay/state .......... clock + the 4 bookmarks
  GET  /api/v1/scenarios
  POST /api/v1/replay/{seek,play,pause,reset}  ◄── UNUSED in deployment (see §4)

  THE SIX INSTITUTIONS  (2 school · 2 hospital · 2 authority, 3 per country)
    id-ptk-sman1     school     Pontianak  ID      1,080 students     ~
    id-ptk-soedarso  hospital   Pontianak  ID      4,200 patients     ~
    id-ptk-bpbd      authority  Pontianak  ID    682,900 residents    ✔ BPS 2024
    my-kch-greenroad school     Kuching    MY      1,240 students     ~
    my-kch-hus       hospital   Kuching    MY      6,800 patients     ~
    my-kch-jpbn      authority  Kuching    MY  2,539,800 residents    ✔ DOSM 2026

    ✔ sourced and cited inline in institutions.py (agency, figure, reference
      year, retrieval date). ~ illustrative, uncited — do not quote as evidence.

  ! JPBN Sarawak is the STATE Disaster Management Committee, so its remit is
    all of Sarawak, not Kuching. An earlier city-scale 617,900 understated it
    roughly fourfold.
```

---

## 4. The replay clock — why every read carries `?at=`

```
   PROBLEM                                   SOLUTION
   ┌────────────────────────────┐            ┌────────────────────────────────┐
   │ Server holds ONE in-process│            │ Browser holds its OWN clock.   │
   │ clock, shared by everyone. │            │ Sends ?at=<ISO> on every read. │
   │ /replay/play mutates it    │  ────────► │ /replay/* POSTs never called.  │
   │ with no auth. Judge A      │            │ Each visitor fully independent.│
   │ moves it under Judge B.    │            │ lib/replay/clock.ts            │
   └────────────────────────────┘            └────────────────────────────────┘

   BOOKMARKS (fetched from /replay/state — never hardcoded)
   ┌──────────────┬────────────────────┬──────────────────────────────────────┐
   │ calm         │ 2023-08-28T09:00Z  │ 0/6 alerting. Baseline is clean.     │
   │ first_warning│ 2023-08-30T19:00Z  │ 3/6 — all Sarawak, 18h ahead, while  │
   │              │                    │ Indonesia is clear. The cross-border │
   │              │                    │ claim in its purest form.            │
   │ crossborder  │ 2023-09-02T16:00Z  │ 6/6 across BOTH countries at once.   │
   │              │                    │ Kuching warned 17h ahead while its   │
   │              │                    │ air still reads 12.8 (MODERATE);     │
   │              │                    │ observation later confirms 49.2.     │
   │ severe       │ 2023-09-04T21:00Z  │ 6/6. Pontianak forecast 86 vs        │
   │              │                    │ observed 307 → beyond-range flag ON. │
   └──────────────┴────────────────────┴──────────────────────────────────────┘
                        ▲
                 opens here by default

   ! /hotspots/summary accepts no ?at=, so the client sends explicit start/end
     derived from its own clock — otherwise the map alone would drift to the
     shared server clock while every other panel stayed pinned.
```

---

## 5. Frontend shell — shared by both modes

```
   >> visitor opens the app
              │
              ▼
   [ initialiseClock() ] ── GET /replay/state ── pin `at` = crossborder bookmark
              │
              ├── GET /health          (no ?at= — endpoint has none)
              ├── GET /institutions    (static records, no ?at=)
              │
              ▼
   < NEXT_PUBLIC_HAZE_DATA_MODE >
        │                    │
      "api"                "mock"
        │                    └──► contract-shaped fixtures, zero network
        ▼                         (recording-safe fallback)
   live backend
        │
        ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ HEADER   [institution ▼]  [Scope]  [Forecast]  [clock chip] │
   │          no login — institution context comes from a         │
   │          selector, persisted in React context across routes  │
   ├──────────┬──────────────────────────────────────────────────┤
   │ SIDEBAR  │  LITE  → / · /lite/institution-detail            │
   │          │          /lite/alert-history · /lite/alert-review│
   │          │  PRO   → /pro (→ live-monitor) · /pro/institutions│
   │          │          /pro/alert-history · /pro/notification- │
   │          │          preview                                 │
   └──────────┴──────────────────────────────────────────────────┘

   ! Cold start: free-tier hosts sleep after ~15 min and take 30–60s to wake.
     Every loading state says so rather than showing a spinner that looks hung.
```

---

## 6. Status derivation — the client never re-implements alerting

```
                    forecast + alert response
                              │
                              ▼
              < did the BACKEND raise an alert? >
                              │
              ┌───────────────┴───────────────┐
             YES                             NO
              │                               │
              ▼                               ▼
          ┌───────┐              < current aqi_category == GOOD? >
          │ ALERT │                     │              │
          └───────┘                    YES             NO
                                        ▼              ▼
                                    ┌──────┐      ┌───────┐
                                    │ SAFE │      │ WATCH │
                                    └──────┘      └───────┘

   ! The client holds NO copy of 35.5 for decisions. Alert = the backend said so.
     Safe/Watch = aqi_category, which already encodes the EPA breakpoints.

   ! TRAP AVOIDED: reading `peak.aqi_category` instead looks equivalent and is not.
     That field categorises the CENTRAL estimate while alerting fires on the UPPER
     band. At `crossborder` both Kuching and Pontianak read MODERATE on it while
     actively alerting (upper band 38.5 and 57.7).

   ! Safe means "air is normal right now, nothing forecast to trigger". Requiring
     all 24 forecast points to be GOOD makes Safe unreachable — regional baseline
     is ~18 µg/m³, already MODERATE. A sweep of the whole scenario returned 0 Safe.
```

---

## 7. LITE journey — institution staff (a head teacher, a duty nurse)

```
 >> lands on  /
      │
      ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ INSTITUTION OVERVIEW                                             │
 │  name · type · city, region, country                             │
 │  ┌────────────────────────────────────────────────────────────┐  │
 │  │ [SAFE] / [WATCH] / [ALERT]  ← §6                           │  │
 │  │ plain-language line, worded by institution type:            │  │
 │  │   school   → activity / closure language                    │  │
 │  │   hospital → operational-readiness language                 │  │
 │  │ "Smoke is arriving from West Kalimantan, Indonesia —        │  │
 │  │  about 21h downwind transport."   ← attribution block       │  │
 │  └────────────────────────────────────────────────────────────┘  │
 └──────────────────────────────────────────────────────────────────┘
      │
      ▼
 < status? >
   │      │
 SAFE/  ALERT
 WATCH    │
   │      ▼
   │   ┌────────────────────────────────────────────────────────┐
   │   │ + "Highest impact expected around 21:00"               │
   │   │ + "Forecast peak 38.5 µg/m³ — supporting detail, not   │
   │   │    the primary decision cue"                           │
   │   │ + WHAT YOU CAN DO NOW  (recommended_actions, VERBATIM) │
   │   │     1 Cancel outdoor sports and morning assembly       │
   │   │     2 Issue N95 masks to students with asthma          │
   │   │     3 Keep windows closed; run indoor filtration       │
   │   │ + [Review Alert] button                                │
   │   └────────────────────────────────────────────────────────┘
   │      │
   ▼      │
 one-line │   ! Safe/Watch get NO checklist and NO Confirm & Send.
 message  │     Escalation appears only when it is warranted.
 only     │
          ▼
 >> clicks "Review Alert"  ──►  /lite/alert-review
                                      │
                                      ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ ALERT REVIEW                                                     │
 │  Current forecast status · Delivery target · What this means     │
 │  ┌── PREPARED MESSAGE ─────────┐  ┌── BEFORE YOU SEND ────────┐  │
 │  │ [WhatsApp] [SMS] toggle     │  │ checklist, verbatim again │  │
 │  │ ┌─────────────────────────┐ │  ├── ALERT DETAILS ─────────┤  │
 │  │ │ ⚠ HAZE ALERT            │ │  │ Institution · Peak time   │  │
 │  │ │ Air quality around      │ │  │ Warning lead time: 17h    │  │
 │  │ │ SMK Green Road is       │ │  │ Message status: prepared  │  │
 │  │ │ expected to worsen...   │ │  └───────────────────────────┘  │
 │  │ │ Preview · not yet sent  │ │                                 │
 │  │ └─────────────────────────┘ │  [amber caveat IF the forecast  │
 │  └─────────────────────────────┘   is beyond the trained range]  │
 │                                                                  │
 │  [Back to Institution Detail]            [ Confirm & Send ]      │
 └──────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                            >> clicks Confirm & Send
                                      │
                                      ▼
                            ┌─────────────────────┐
                            │ CONFIRMATION MODAL  │
                            │ channel · recipient │
                            │ "Simulated delivery │
                            │  only"              │
                            │ [Cancel] [Confirm]  │
                            └─────────────────────┘
                                      │
                                      ▼
          ╔═══════════════════════════════════════════════════════╗
          ║ NO NETWORK REQUEST IS MADE.                           ║
          ║ Local React state only. Works with the backend off.   ║
          ║ `apiPost` does not exist in the client.               ║
          ╚═══════════════════════════════════════════════════════╝
                                      │
                                      ▼
     "Sent to: SMK Green Road admin contact — 14:32 · WHATSAPP · simulated: true"

 >> other Lite routes
    /lite/institution-detail  forecast outlook (Now / Alert window / Later),
                              what this means, what to prepare, recent alerts
    /lite/alert-history       reconstructed timeline + escalation ladder
```

---

## 8. PRO journey — regional analyst / disaster-management officer

```
 >> lands on  /pro/live-monitor
      │
      ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │ REGIONAL BANNER   [SAFE|WATCH|ALERT]                               │
 │ "Smoke is arriving from West Kalimantan, Indonesia — about 21h..." │
 ├──────────────┬──────────────┬───────────────┬─────────────────────┤
 │ Active       │ Institutions │ Highest       │ Haze Movement       │
 │ Hotspots     │ at Risk      │ Forecast PM2.5│ W.Kalimantan →      │
 │ 1,536        │ 6            │ 57.7 µg/m³    │ Sarawak             │
 │ (FIRMS)      │ (both ctry)  │ (p90, 12h)    │ (from attribution)  │
 ├──────────────┴──────────────┴───────────────┴─────────────────────┤
 │ ┌── REGIONAL MAP ──────────────┐  ┌── NEXT 12 HOURS ────────────┐ │
 │ │ WEST KALIMANTAN ~~~►SARAWAK  │  │ Source · Highest · Most     │ │
 │ │  ● hotspot cells (gridded)   │  │ affected                    │ │
 │ │  ▣ institution pins, coloured│  ├── INSTITUTIONS AT RISK ─────┤ │
 │ │    by Safe/Watch/Alert       │  │ sortable table, 6 rows:     │ │
 │ │  ══► transport arrow         │  │ current · peak(lead) · state│ │
 │ │  scale 0 ─ 12 ─ 35.5 ─ 55+   │  ├── PRIORITY ALERT ──────────┤ │
 │ └──────────────────────────────┘  │ [View Institution]          │ │
 │                                    │ [Preview Notification]      │ │
 │ ┌── HOW HAZEWATCH GENERATES AN ALERT ───────────────────────────┐ │
 │ │ Satellite ─► Wind/Distance ─► Random Forest ─► Range Check    │ │
 │ │           ─► HUMAN CONFIRMATION ─► Verified Contact           │ │
 │ └───────────────────────────────────────────────────────────────┘ │
 └────────────────────────────────────────────────────────────────────┘
      │
      ├──►  /pro/institutions  ── INSTITUTION DETAIL
      │       • PM2.5 forecast chart: p10–p90 band, p50 line,
      │         reference lines at 12 and 35.5
      │       • warning lead time · threshold crossing window
      │       • hotspot context · recommended actions
      │
      ├──►  /pro/alert-history  ── timeline + sparkline of the episode,
      │       event detail pane, filterable, 35.5 reference line
      │
      └──►  /pro/notification-preview  ── ALERT REVIEW (Pro)
              • channel + language selector (id / ms / en)
              • full message preview, copy-to-clipboard
              • source area, affected area, expected window
              • [ Confirm & Send ] ──► identical local-only simulation as §7
```

---

## 9. Honesty guardrails — the parts most likely to be asked about

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │ GUARDRAIL              WHERE IT SURFACES                                │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ Forecast has a hard   │ A tree ensemble averages training targets in a  │
 │ ceiling (~90 µg/m³)   │ leaf, so it CANNOT emit above ~90 however bad   │
 │                       │ the air gets. At the Pontianak peak: forecast   │
 │                       │ 86 vs observed 307.                            │
 │                       │ → `beyond_training_range` per point             │
 │                       │ → `uncertainty.note` rendered VERBATIM          │
 │                       │ → amber caveat, shown ONLY when the flag is set │
 │                       │ ! no green "high confidence" badge — the absence│
 │                       │   of a warning is not a positive signal, and no │
 │                       │   confidence scale was ever defined             │
 ├───────────────────────┼─────────────────────────────────────────────────┤
 │ Nothing is ever sent  │ Every notification carries `simulated: true`,   │
 │                       │ shown in the UI. Recipient is always framed as  │
 │                       │ a VERIFIED INSTITUTION ADMIN CONTACT — never a  │
 │                       │ community or public broadcast.                  │
 ├───────────────────────┼─────────────────────────────────────────────────┤
 │ Not ground truth      │ PM2.5 is CAMS reanalysis, not ground-station    │
 │                       │ measurement. Labelled in the UI, stated in the  │
 │                       │ contract, repeated in metrics `notes`.          │
 ├───────────────────────┼─────────────────────────────────────────────────┤
 │ No fabricated history │ The contract has NO alert-history endpoint —    │
 │                       │ `/alerts` returns only the latest state per     │
 │                       │ institution. Timelines are reconstructed by     │
 │                       │ sampling `/alerts?at=` at 7 past offsets.       │
 │                       │ Non-alert samples read "Clear", not Safe/Watch, │
 │                       │ because that distinction was not fetched.       │
 ├───────────────────────┼─────────────────────────────────────────────────┤
 │ Performance is quoted │ 79.5% hit · 25.4% false alarm · 24h median lead │
 │ from one place        │ · 99 episodes — served by /model/metrics,       │
 │                       │ never hardcoded in the UI.                      │
 ├───────────────────────┼─────────────────────────────────────────────────┤
 │ "Median lead" is a    │ alert_metrics searches a window of exactly      │
 │ capped maximum, not   │ `horizon` hours before each onset, so per-      │
 │ an unbounded median   │ episode lead cannot exceed 24 and the median    │
 │                       │ sits on its bound. It reads 24.0 at EVERY       │
 │                       │ trigger percentile from p75 to p95 while hit    │
 │                       │ rate moves 58% → 90% — the signature of a       │
 │                       │ statistic against its ceiling. True median is   │
 │                       │ ≥24h and unmeasured; widening the window is     │
 │                       │ what would turn it into an estimate.            │
 └─────────────────────────────────────────────────────────────────────────┘
```

---

## 10. The claim, in one line

```
  FIRMS hotspot in West Kalimantan
            │
            ▼  (wind, distance, 21h transport)
  upwind fire exposure index rises for a Kuching school
            │
            ▼  Random Forest, p90 upper band
  forecast crosses 35.5 µg/m³ in 17 hours
            │
            ▼  alert raised, actions attached
  a head teacher sees it while the air outside still reads 12.8
            │
            ▼  HUMAN reviews and confirms
  message prepared for a verified admin contact
            │
            ▼  (17 hours later)
  observation confirms 49.2 µg/m³ — the warning was right,
  and the school had a day to act on it.
```
