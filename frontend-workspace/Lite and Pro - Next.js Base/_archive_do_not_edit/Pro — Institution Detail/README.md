# HazeWatch AI — Lite frontend base

This implementation contains the shared **App Shell** and the full current **Lite flow**: Overview, Institution Detail, Alert History, and Alert Review, built from the supplied visual references and the frozen API contract.

## Stack
- Next.js 14 (App Router)
- React + TypeScript
- Tailwind CSS
- Lucide icons as temporary UI assets

The HazeWatch logo is intentionally replaceable at:
`src/components/hazewatch/BrandMark.tsx`.

## Implemented routes
- `/` — Lite Institution Overview
- `/lite/institution-detail` — Lite Institution Detail
- `/lite/alert-history` — Lite Alert History
- `/lite/alert-review` — Lite Alert Review + human confirmation flow

## Source of truth
The backend contract is copied into `api_contract/`:
- `CONTRACT.md`
- `openapi.json`

Do not invent backend fields in UI components. If the contract changes additively, regenerate typed OpenAPI definitions with:

```bash
npm run generate:api
```

## Run

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`.

## Data modes

### Offline / recording-safe mock

```bash
NEXT_PUBLIC_HAZE_DATA_MODE=mock
```

Contract-shaped fixtures live in `src/lib/data/mock.ts`. They are isolated from UI components so the data source can be swapped without rebuilding the screens.

### Local FastAPI backend

```bash
NEXT_PUBLIC_HAZE_DATA_MODE=api
NEXT_PUBLIC_HAZE_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_HAZE_INSTITUTION_ID=
```

If no institution id is configured, the data loader requests `/institutions` and chooses the first school/hospital returned.

## Lite state logic
Centralized in `src/lib/ui/status.ts`:

- Safe: 0–12.0 µg/m³
- Watch: 12.1–35.4 µg/m³
- Alert: >=35.5 µg/m³

Alert risk uses `pm25_upper` when available, matching the frozen contract. A backend `alert` object is authoritative Alert state.

### Safe / Watch
- Information only.
- No preparedness checklist.
- No Review Alert / Confirm & Send action.

### Alert
- `Alert.recommended_actions` is rendered verbatim.
- Institution Detail exposes `Review Alert`, not final send.
- Final `Confirm & Send` is available only in Alert Review and only while the state is Alert.

## Institution type awareness
`src/lib/ui/institutionDetailCopy.ts` changes plain-language operational copy for school vs hospital. It does not change thresholds.

## Beyond-training-range
If `forecast.uncertainty.any_point_beyond_training_range` is true, Lite screens show a persistent plain-language reliability notice. They do not expose `model_ceiling_pm25` as a raw decision number.

## Recent alert history
The frozen contract exposes Alert objects but not Safe/Watch transition history. API mode therefore does not fabricate Safe/Watch historical records solely to imitate the reference image.

## Notification flow
Alert Review uses the frozen contract's `POST /notifications/simulate` endpoint after the explicit confirmation modal. In offline mock mode, the same interaction returns a contract-shaped in-memory simulated notification. The UI surfaces simulated-delivery semantics and never implies a real SMS/WhatsApp send.

## UI references
- `public/ui-reference-lite-overview.png`
- `public/ui-reference-lite-institution-detail.png`
- `public/ui-reference-lite-alert-history.png`
- `public/ui-reference-lite-alert-review.png`

They are design references only and are not used at runtime.

## Added screen: Lite Alert History

- Route: `/lite/alert-history`
- Visual reference: `public/ui-reference-lite-alert-history.png`
- Safe/Watch timeline rows in offline mock mode are UI-only fixture snapshots, kept separate from frozen API types.
- In API mode, the timeline falls back to alert records from `GET /alerts?status=all`; it does not invent backend history fields.
- Safe/Watch remain informational only; only Alert exposes `Review Alert`.


## Added screen: Lite Alert Review

- Route: `/lite/alert-review`
- Visual reference: `public/ui-reference-lite-alert-review.png`
- Safe/Watch never expose the actionable review flow.
- The preparedness checklist renders `Alert.recommended_actions` verbatim.
- Channel tabs are restricted to the institution's `contact_channels`.
- `Confirm & Send` first opens a confirmation modal, then calls `POST /notifications/simulate` in API mode.
- A compact reliability indicator sits beside the final action. It uses `Forecast.uncertainty.any_point_beyond_training_range`; it does **not** invent High/Moderate/Low confidence tiers.
- The secondary action is `Back to Institution Detail`, matching the navigation flow from Institution Detail → Review Alert → Alert Review.

## Pro mode integration status

The first Pro screen is now available at:

- `/pro/live-monitor` — regional cross-border Live Haze Monitor

The Pro screen reuses the same data-mode switch as Lite mode:

- `NEXT_PUBLIC_HAZE_DATA_MODE=mock` for deterministic offline recording
- `NEXT_PUBLIC_HAZE_DATA_MODE=api` for the local FastAPI backend

In API mode the Live Monitor consumes `GET /health`, `GET /institutions`, `GET /alerts?status=all`, `GET /hotspots/summary`, and one 12-hour `GET /institutions/{id}/forecast` request per institution. The regional map always renders all institutions returned by the API, so the default view does not hide either West Kalimantan or Sarawak.

The outer shell is intentionally full-bleed/full-width. The old navy device-frame border, large rounded outer frame, max-width cap, and outer page padding were removed from both Lite and Pro shells.

## Pro Institution Detail

Route: `/pro/institutions`

This screen follows the approved Pro Institution Detail visual while keeping the frozen API contract authoritative:
- alert threshold uses the upper prediction band (`pm25_upper >= 35.5`)
- chart renders p10/p50/p90 information when present
- alert-only preparedness actions come from `recommended_actions`
- warning lead time uses `lead_time_hours`
- beyond-training-range becomes a reliability warning rather than a fabricated High/Medium/Low score
- transboundary attribution is sourced from the forecast `attribution` block
