# HazeWatch AI — frontend

The Next.js dashboard for the transboundary haze early-warning system. It serves both
modes of the product from one app: the **Lite** flow for a single institution, and the
**Pro** flow for regional cross-border monitoring.

The Python backend that this app reads lives at the repository root; see
[`../api_contract/CONTRACT.md`](../api_contract/CONTRACT.md) for the contract it is
written against.

## Stack
- Next.js 14 (App Router)
- React + TypeScript
- Tailwind CSS
- Lucide icons as temporary UI assets

The HazeWatch logo is intentionally replaceable at
`src/components/hazewatch/BrandMark.tsx`.

## Routes

| Route | Screen |
| --- | --- |
| `/` | Lite Institution Overview |
| `/lite/institution-detail` | Lite Institution Detail |
| `/lite/alert-history` | Lite Alert History |
| `/lite/alert-review` | Lite Alert Review + human confirmation flow |
| `/pro` | Redirect to `/pro/live-monitor` — Pro has no landing screen of its own |
| `/pro/live-monitor` | Regional cross-border Live Haze Monitor |
| `/pro/institutions` | Pro Institution Detail |
| `/pro/alert-history` | Pro Alert History (status filter + selected-event details) |
| `/pro/notification-preview` | Pro Notification Preview / Alert Review |

## Run

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`.

`.env.example` documents every supported variable. `.env.production` holds the
build-time values for the deployed site and is committed deliberately — every value is
a `NEXT_PUBLIC_*` variable that Next.js inlines into the client bundle, so none of them
are secrets. See the comment at the top of that file before changing it.

## Data modes

`NEXT_PUBLIC_HAZE_DATA_MODE` switches the whole app between two sources.

### `mock` — offline / recording-safe

Contract-shaped fixtures live in `src/lib/data/`. They are isolated from UI components
so the data source can be swapped without rebuilding the screens.

### `api` — FastAPI backend

```bash
NEXT_PUBLIC_HAZE_DATA_MODE=api
NEXT_PUBLIC_HAZE_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_HAZE_INSTITUTION_ID=
```

If no institution id is configured, the data loader requests `/institutions` and chooses
the first school/hospital returned.

## Source of truth

The backend contract is copied into `api_contract/`:
- `CONTRACT.md`
- `openapi.json`

Do not invent backend fields in UI components. If the contract changes additively,
regenerate typed OpenAPI definitions with:

```bash
npm run generate:api
```

## State logic

Centralized in `src/lib/ui/status.ts`:

- Safe: 0–12.0 µg/m³
- Watch: 12.1–35.4 µg/m³
- Alert: >= 35.5 µg/m³

Alert risk uses `pm25_upper` when available, matching the frozen contract. A backend
`alert` object is authoritative Alert state.

**Safe / Watch**
- Information only.
- No preparedness checklist.
- No Review Alert / Confirm & Send action.

**Alert**
- `Alert.recommended_actions` is rendered verbatim.
- Institution Detail exposes `Review Alert`, not final send.
- Final `Confirm & Send` is available only in the review screens, and only while the
  state is Alert.

### Institution type awareness

`src/lib/ui/institutionDetailCopy.ts` changes plain-language operational copy for school
vs hospital. It does not change thresholds.

### Beyond training range

If `forecast.uncertainty.any_point_beyond_training_range` is true, the screens show a
persistent plain-language reliability notice. They do not expose `model_ceiling_pm25` as
a raw decision number, and they do not invent High/Moderate/Low confidence tiers.

### Alert history

The frozen contract exposes Alert objects but not Safe/Watch transition history. API
mode therefore does not fabricate Safe/Watch historical records solely to imitate the
reference images: the timeline falls back to alert records from `GET /alerts?status=all`.
Safe/Watch timeline rows exist only in the swappable demo fixtures.

## Notification flow

The review screens call the frozen contract's `POST /notifications/simulate` after an
explicit confirmation modal. In mock mode the same interaction returns a contract-shaped
in-memory simulated notification. The UI surfaces simulated-delivery semantics and never
implies a real SMS/WhatsApp send.

Delivery targets are verified institution contacts only. Channel choices come from
`Institution.contact_channels`, preview language from `Institution.languages`, and the
forecast trigger peak from the Alert payload (`forecast_peak_pm25`, derived from the
upper prediction band).

## Screen notes

### Pro Live Monitor
In API mode it consumes `GET /health`, `GET /institutions`, `GET /alerts?status=all`,
`GET /hotspots/summary`, and one 12-hour `GET /institutions/{id}/forecast` request per
institution. The regional map always renders every institution returned by the API, so
the default view does not hide either West Kalimantan or Sarawak.

The outer shell is intentionally full-bleed/full-width in both Lite and Pro.

### Pro Institution Detail
Follows the approved Pro visual while keeping the frozen contract authoritative:
- alert threshold uses the upper prediction band (`pm25_upper >= 35.5`)
- the chart renders p10/p50/p90 information when present
- alert-only preparedness actions come from `recommended_actions`
- warning lead time uses `lead_time_hours`
- transboundary attribution is sourced from the forecast `attribution` block

## UI references

`public/ui-reference-*.png` are design references only. They are not used at runtime.
