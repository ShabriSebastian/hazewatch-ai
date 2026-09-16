# HazeWatch AI — frontend

The Next.js dashboard for the transboundary haze early-warning system. It serves both
modes of the product from one app: the **Lite** flow for a single institution, and the
**Pro** flow for regional cross-border monitoring.

It reads one published file — there is no backend. The pipeline at the repository root
writes `data/live/latest.json`; see [`../DEVELOPMENT.md`](../DEVELOPMENT.md) for how
that is produced, why the refresh is manual, and what the retired API used to do.

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

## Where the data comes from

One published snapshot, `data/live/latest.json`, fetched once per session and shared
by every screen. There is no backend: the FastAPI service and the September 2023
replay it served were retired — see `DEVELOPMENT.md` for why and what went with them.

```bash
# generate one locally and serve it from the app itself
python scripts/07_live_snapshot.py --out frontend/public/dev-snapshot.json
echo 'NEXT_PUBLIC_HAZE_SNAPSHOT_URL=/dev-snapshot.json' > frontend/.env.local
```

`src/lib/live/snapshot.ts` fetches and validates it, then re-shapes it into the types
in `src/lib/api/types.ts`. Validation is strict: a snapshot missing the blocks the main
body needs is rejected rather than half-rendered, and every screen shows an explicit
"no data to show" state with the reason. Nothing renders blank.

`src/lib/live/history.ts` reads the accumulated alert history beside it. A missing
history is not fatal — Alert History says it has a single observation.

**The refresh is manual.** The snapshot shows whatever was last published by hand, so
every screen surfaces `generated_at` and flags anything older than six hours. That
honesty is a requirement, not decoration; see `DEVELOPMENT.md`.

There is no mock mode. It existed so the demo would survive an unreachable backend,
and retired with the backend.

## State logic

Centralized in `src/lib/ui/status.ts`:

- Safe: 0–12.0 µg/m³
- Watch: 12.1–35.4 µg/m³
- Alert: >= 35.5 µg/m³

Alert risk uses `pm25_upper` when available. The `alert` object carried in the
snapshot is authoritative for Alert state — it is not recomputed in the UI.

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
