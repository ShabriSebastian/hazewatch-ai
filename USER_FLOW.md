# HazeWatch AI — User Flow

What a person actually sees, decides, and clicks. Companion to `SYSTEM_FLOW.md`, which
covers the machinery underneath.

Legend: `>>` user action · `< >` decision · `[ ]` screen · `═══` state change · `!` note

---

## 1. Who is using this

```
 ┌────────────────────────────────┬────────────────────────────────────────────┐
 │ LITE  —  institution staff     │ PRO  —  regional analyst / disaster officer │
 ├────────────────────────────────┼────────────────────────────────────────────┤
 │ A head teacher at SMK Green    │ An officer at JPBN Sarawak or BPBD          │
 │ Road. A duty nurse at Hospital │ Pontianak watching both sides of the border │
 │ Umum Sarawak.                  │ at once.                                    │
 │                                │                                             │
 │ ONE institution. Their own.    │ ALL SIX institutions, both countries.       │
 │ Question: "do I need to do     │ Question: "where is this going, who is      │
 │ something today?"              │ most exposed, and who do I warn first?"     │
 │                                │                                             │
 │ Wants: a sentence and a        │ Wants: a map, a ranked table, a forecast    │
 │ checklist. Not a chart.        │ band, and the evidence behind the call.     │
 └────────────────────────────────┴────────────────────────────────────────────┘
```

---

## 2. Entry — there is no login

```
 >> opens the URL
        │
        ▼
  ┌───────────────────────────────────────────────────────────┐
  │ No sign-up. No password. No account.                      │
  │ Institution context comes from a SELECTOR in the header.  │
  │ The visitor's replay clock is pinned to `crossborder`.    │
  └───────────────────────────────────────────────────────────┘
        │
        ▼
  < which URL? >
        │
        ├── /                      ──►  [ Lite Overview ]     ◄── default landing
        └── /pro  or  /pro/live-monitor ──►  [ Pro Live Monitor ]
                (/pro redirects)

 ! Consequence of no auth: anyone with the link sees everything, and the
   Confirm & Send button is not access-controlled. This is stated in the UI
   itself — "MVP note: authentication is not implemented."
```

---

## 3. Controls present on every screen

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  HEADER                                                                 │
 │   [🏫 Institution ▼]   ← changes WHO you are looking at. Re-fetches      │
 │                          every panel. Persists across all 8 routes.     │
 │   ● Prototype Active   ← honesty label, not a live status               │
 │   ◷ Scenario replay · 2023-09-02 16:00Z   ← YOUR clock, not the server's│
 │   ✦ Pro Mode → / ✦ Lite Mode →            ← labels the DESTINATION      │
 ├─────────────────────────────────────────────────────────────────────────┤
 │  SIDEBAR — four links, never crosses modes                              │
 │   LITE: Overview · Institution Detail · Alert History · Alert Review    │
 │   PRO : Live Monitor · Institutions · Alert History · Notification Prev.│
 └─────────────────────────────────────────────────────────────────────────┘

 >> changing the institution
        │
        ▼
   all panels re-fetch with the new id, clock stays pinned
        │
        ▼
   ! a school and a hospital in the same city now show the SAME status and the
     SAME lead time. Only the WORDING differs. (It did not always: hospitals
     used to trigger at 28.4 — removed, see SYSTEM_FLOW §2.)
```

---

## 4. Screen map — every route and every link between them

```
                        ┌──────────────────────────┐
                        │   LITE  (institution)    │
                        └──────────────────────────┘

   [ / Overview ]────────────────────────────────────┐
      │  │                                            │
      │  ├─"Review Alert"──────────────┐              │
      │  └─"See details"───────┐       │              │
      │                        ▼       │              │
      │     [ /lite/institution-detail ]              │
      │        │  ▲     │        │                    │
      │        │  │     │        └─"View Alert History"┐
      │        │  │     └─"✉ Review Alert"──┐          │
      │  "← Back to Overview"               │          │
      │        │  │                         │          ▼
      │        │  └──"Back to Institution   │   [ /lite/alert-history ]
      │        │      Detail"───────────┐   │      │        │
      │        ▼                        │   │      │        │
      └─"View all"────────────────────► │   ▼      │        │
                                   [ /lite/alert-review ]   │
                                          ▲   │             │
                                          └───┴─"✉ Review Alert"

                        ┌──────────────────────────┐
                        │   PRO  (regional)        │
                        └──────────────────────────┘

   [ /pro/live-monitor ]
      │   │
      │   ├─"View Affected Institutions →"─┐
      │   └─"Preview Notification →"───────┼───────────────┐
      │                                    ▼               │
      │                        [ /pro/institutions ]       │
      │   ▲                       │    │    │              │
      │   └─"← Regional Overview"─┘    │    └─"View Alert History →"┐
      │                                │                            │
      │                     "Preview Notification"                  ▼
      │                                │              [ /pro/alert-history ]
      │                                ▼                   │         │
      │                   [ /pro/notification-preview ]◄────┘         │
      │                          │        ▲                           │
      │                          │        └───"Preview Notification"──┘
      │                          └─"Back to Alert History"
      │                          └─"View Institution Alert →"
```

---

## 5. LITE — the full path with every branch

```
 >> lands on /
        │
        ▼
  [ INSTITUTION OVERVIEW ]
        │
        ▼
  < what did the backend say? >
        │
   ┌────┴─────────────┬──────────────────────┐
   ▼                  ▼                      ▼
 SAFE               WATCH                  ALERT
   │                  │                      │
   ▼                  ▼                      ▼
┌──────────────┐  ┌──────────────────┐  ┌────────────────────────────────────┐
│ "Air quality │  │ "Conditions are  │  │ "Air quality is expected to become │
│  is normal." │  │  being monitored"│  │  unhealthy."                       │
│ "No action   │  │ "No action right │  │ SCHOOL  → activity/closure wording │
│  is needed." │  │  now. We'll      │  │ HOSPITAL→ operational readiness    │
│              │  │  notify you if   │  │ AUTHORITY→ district advisory       │
│              │  │  it rises."      │  │ "Highest impact around 21:00"      │
│              │  │                  │  │ "Forecast peak 38.5 µg/m³ —        │
│              │  │                  │  │  supporting detail, not the        │
│              │  │                  │  │  primary decision cue"             │
│              │  │                  │  │                                    │
│              │  │                  │  │ ┌── WHAT YOU CAN DO NOW ─────────┐│
│              │  │                  │  │ │ 1 Cancel outdoor sports        ││
│              │  │                  │  │ │ 2 Issue N95 masks to students  ││
│              │  │                  │  │ │   with asthma                  ││
│              │  │                  │  │ │ 3 Keep windows closed          ││
│              │  │                  │  │ └────────────────────────────────┘│
│              │  │                  │  │ [Review Alert]  [See details]      │
└──────────────┘  └──────────────────┘  └────────────────────────────────────┘
   │                  │                      │
   └────────┬─────────┘                      │
            ▼                                │
   "Monitoring only —                        │
    no alert is waiting                      │
    for review."                             │
            │                                │
            ▼                                ▼
   ══ DEAD END BY DESIGN ══        >> clicks "Review Alert"
   No checklist. No Confirm                  │
   & Send. Escalation appears                ▼
   only when warranted.            [ ALERT REVIEW ] ── §7
```

### The other two Lite screens

```
 [ /lite/institution-detail ]   "why does it say that?"
    Forecast outlook:  Now  ──►  Alert window  ──►  Later
                       (current   (threshold        (beyond the
                        category)  crossing time)    24h outlook)
    + What this means (type-worded bullets)
    + What should we prepare (recommended_actions, verbatim)
    + Recent alerts  ──► "View all alerts"

 [ /lite/alert-history ]        "has this been building?"
    Current status · Latest change (Clear → Alert) · What this means
    Timeline: 7 samples over 24h, each Alert or Clear
    Escalation ladder: Safe ──► Watch ──► Forecast Alert
                       (current position highlighted)
    ! rows say "Clear", never "Safe"/"Watch" — that distinction was not fetched
```

---

## 6. PRO — the full path

```
 >> lands on /pro/live-monitor
        │
        ▼
  ┌───────────────────────────────────────────────────────────────┐
  │ REGIONAL BANNER    [SAFE | WATCH | ALERT]                     │
  │ "Smoke is arriving from West Kalimantan, Indonesia —          │
  │  about 21h downwind transport."                               │
  │ [View Affected Institutions →]                                │
  ├──────────┬──────────┬────────────┬───────────────────────────┤
  │ Hotspots │ At Risk  │ Highest    │ Haze Movement             │
  │ 1,536    │ 6        │ 57.7 µg/m³ │ West Kalimantan → Sarawak │
  ├──────────┴──────────┴────────────┴───────────────────────────┤
  │ MAP: hotspot cells · 6 institution pins coloured by status   │
  │      · transport arrow · scale 0—12—35.5—55+                 │
  │ TABLE: 6 rows ranked by forecast peak                        │
  │ PRIORITY ALERT card (only when something is alerting)        │
  └───────────────────────────────────────────────────────────────┘
        │
        ├──>> "View Institution →"      ──► [ /pro/institutions ]
        └──>> "Preview Notification →"  ──► [ /pro/notification-preview ]
                                                    │
  [ /pro/institutions ]  ── the evidence            │
     PM2.5 chart: p10–p90 band, p50 line,           │
     reference lines at 12 and 35.5                 │
     Warning lead time · threshold crossing window  │
     Hotspot context · recommended actions          │
        ├──>> "View Alert History →"  ──► [ /pro/alert-history ]
        └──>> "Preview Notification"  ─────────────►│
                                                    │
  [ /pro/alert-history ]                            │
     Episode sparkline with the 35.5 line           │
     Filterable event list + detail pane            │
        └──>> "Preview Notification"  ─────────────►│
                                                    ▼
                                        [ NOTIFICATION PREVIEW ] ── §7
```

---

## 7. Confirm & Send — the one place a human commits (identical in both modes)

```
  arrives at  /lite/alert-review   or   /pro/notification-preview
        │
        ▼
  < is this institution alerting? >
        │
   ┌────┴────┐
  NO        YES
   │         │
   ▼         ▼
┌─────────────────────────┐   ┌──────────────────────────────────────────────┐
│ EMPTY STATE             │   │ ┌── PREPARED MESSAGE ──────────────────────┐ │
│ "No alert requires      │   │ │ [WhatsApp] [SMS]   ← from contact_channels│ │
│  review"                │   │ │ (Pro also: language id / ms / en)        │ │
│ "<name> is in an        │   │ │ ┌──────────────────────────────────────┐ │ │
│  informational Safe or  │   │ │ │ ⚠ HAZE ALERT                         │ │ │
│  Watch state. Confirm & │   │ │ │ Air quality around SMK Green Road is  │ │ │
│  Send is available only │   │ │ │ expected to worsen.                   │ │ │
│  when the forecast      │   │ │ │ Highest impact around 21:00, about    │ │ │
│  reaches Alert."        │   │ │ │ 17 hours from now.                    │ │ │
│                         │   │ │ │ ─────────────────                     │ │ │
│ [Back to Inst. Detail]  │   │ │ │ Preview · not yet sent                │ │ │
└─────────────────────────┘   │ │ └──────────────────────────────────────┘ │ │
   ══ no way to send ══       │ └──────────────────────────────────────────┘ │
                              │ ┌── BEFORE YOU SEND ───┐ ┌── ALERT DETAILS ─┐│
                              │ │ recommended_actions, │ │ Institution      ││
                              │ │ verbatim, as a       │ │ Expected peak    ││
                              │ │ checklist            │ │ Lead time 17h    ││
                              │ └──────────────────────┘ │ Status: prepared ││
                              │                          └──────────────────┘│
                              │ [amber caveat IF beyond the trained range]   │
                              │                                              │
                              │ [Back]              [ Confirm & Send ]       │
                              └──────────────────────────────────────────────┘
                                             │
                                    >> clicks Confirm & Send
                                             │
                                             ▼
                              ┌──────────────────────────────┐
                              │ MODAL — Confirm alert        │
                              │ delivery?                    │
                              │  Channel:   WhatsApp         │
                              │  Recipient: Verified         │
                              │             institution      │
                              │             admin contact    │
                              │  Prototype: Simulated only   │
                              │  [Cancel]      [Confirm]     │
                              └──────────────────────────────┘
                                    │              │
                                >> Cancel      >> Confirm
                                    │              │
                                    ▼              ▼
                              back to        ╔══════════════════════════════╗
                              "prepared",    ║ NO NETWORK REQUEST.          ║
                              nothing        ║ Local React state only.      ║
                              changed        ║ Works with the backend off.  ║
                                             ╚══════════════════════════════╝
                                                    │
                                                    ▼
                          ═══════════ STATE CHANGES ═══════════
                            button   → "✓ Confirmed", disabled
                                       (cannot double-send)
                            preview  → "Simulated · not actually sent"
                            details  → "Confirmed · simulated delivery"
                            banner   → "Confirmation recorded. No external
                                        SMS or WhatsApp was sent."
                            feed     → "Sent to: SMK Green Road admin
                                        contact — 14:32 · WHATSAPP ·
                                        simulated: true"

 ! The recipient is ALWAYS framed as a verified institution admin contact.
   Never a parent list, never a community broadcast, never a public number.
   Footer on every screen repeats it.
```

---

## 8. What each screen shows in each state

```
 ┌────────────────────────┬─────────────┬─────────────┬────────────────────────┐
 │ SCREEN                 │ SAFE        │ WATCH       │ ALERT                  │
 ├────────────────────────┼─────────────┼─────────────┼────────────────────────┤
 │ Lite Overview          │ one line    │ one line    │ + peak time            │
 │                        │ "Monitoring │ "Monitoring │ + peak value           │
 │                        │  only" card │  only" card │ + 3-item checklist     │
 │                        │             │             │ + Review Alert         │
 ├────────────────────────┼─────────────┼─────────────┼────────────────────────┤
 │ Lite Institution Detail│ green panel │ amber panel │ red FORECAST ALERT     │
 │                        │ outlook     │ outlook     │ + what this means      │
 │                        │             │             │ + what to prepare      │
 ├────────────────────────┼─────────────┼─────────────┼────────────────────────┤
 │ Lite Alert History     │ timeline + ladder, both   │ + latest alert details │
 │                        │ "no alert requires review"│ + Review Alert         │
 ├────────────────────────┼─────────────┼─────────────┼────────────────────────┤
 │ Lite Alert Review      │ EMPTY STATE, no send path │ full review + confirm  │
 ├────────────────────────┼─────────────┼─────────────┼────────────────────────┤
 │ Pro Live Monitor       │ green banner│ amber banner│ red banner + priority  │
 │                        │ map + table always shown  │ alert card             │
 ├────────────────────────┼─────────────┼─────────────┼────────────────────────┤
 │ Pro Institution Detail │ chart always shown        │ + actions + lead time  │
 ├────────────────────────┼─────────────┼─────────────┼────────────────────────┤
 │ Pro Alert History      │ timeline; empty if no events recorded              │
 ├────────────────────────┼─────────────┼─────────────┼────────────────────────┤
 │ Pro Notif. Preview     │ EMPTY STATE, no send path │ full preview + confirm │
 └────────────────────────┴─────────────┴─────────────┴────────────────────────┘

 ! The invariant across all eight: no checklist and no Confirm & Send outside
   Alert. Safe and Watch are informational only.
```

---

## 9. Non-happy paths

```
 >> first load on a sleeping free-tier host
        ▼
   "Loading institution overview…
    The first request can take up to a minute if the demo server
    is waking from idle."          ← not a spinner that looks hung

 >> backend unreachable
        ▼
   ┌──────────────────────────────────────────────────┐
   │ Could not load Institution Overview.             │
   │ <the actual error>                               │
   │ For an offline demo, set                         │
   │ NEXT_PUBLIC_HAZE_DATA_MODE=mock                  │
   └──────────────────────────────────────────────────┘
        │
        ▼
   >> switch to mock  ──► identical screens, contract-shaped fixtures,
                          zero network. Recording-safe.

 >> two people open the link at once
        ▼
   Nothing happens to each other. Each browser pins its own `?at=`.
   The shared server clock is never mutated.

 >> forecast leaves the model's trained range (the `severe` bookmark)
        ▼
   amber caveat appears, text rendered verbatim from the API:
   "From +1h this forecast is beyond the model's trained range…"
   ! and NO green "high confidence" badge in the other direction —
     absence of a warning is not a positive signal

 >> institution has no alert but user navigates directly to a review URL
        ▼
   EMPTY STATE + [Back to Institution Detail]. Never a broken screen.
```

---

## 10. Gaps a user can hit today

```
 ┌───────────────────────────────────────────────────────────────────────────┐
 │ 1. NO BOOKMARK SWITCHER IN THE UI.                                        │
 │    The clock opens pinned to `crossborder` and stays there. Seeing `calm`, │
 │    `first_warning` or `severe` means changing DEFAULT_BOOKMARK_KEY in      │
 │    lib/replay/clock.ts. The four bookmarks are fetched from the API and    │
 │    ready to drive buttons — the buttons just do not exist yet.             │
 ├───────────────────────────────────────────────────────────────────────────┤
 │ 2. THE SELECTOR ONLY OFFERS SCHOOLS AND HOSPITALS.                         │
 │    The two `authority` institutions (BPBD Pontianak, JPBN Sarawak) are     │
 │    filtered out — they are not an institution-staff audience — but they    │
 │    DO appear in Pro's regional map and table, and the backend raises real  │
 │    alerts for them. Deliberate. Type-aware copy now handles `authority`    │
 │    explicitly, so enabling them in the selector is safe.                   │
 ├───────────────────────────────────────────────────────────────────────────┤
 │ 3. CONFIRM & SEND IS NOT ACCESS-CONTROLLED.                               │
 │    No auth exists, so anyone with the link can press it. Harmless today    │
 │    because it only writes to local state — but it is the first thing to    │
 │    gate if this ever becomes real.                                        │
 └───────────────────────────────────────────────────────────────────────────┘
```

---

## 11. The shortest path to the point

```
 >> open /
 >> read one sentence:  "Air quality is expected to become unhealthy."
 >> read three actions: cancel outdoor sports · issue N95 · close windows
 >> click Review Alert
 >> read the message that would go out
 >> click Confirm & Send

 Six actions. The air outside still reads 12.8 µg/m³ and looks fine.
 Seventeen hours later it reaches 49.2.

 That gap — between what the sky looks like and what the school already
 knew — is the entire product.
```
