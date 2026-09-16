# HazeWatch AI — Lite Overview base frontend

This is the first implementation slice: **App Shell + Lite Mode / Institution Overview**, built from the supplied UI reference and the frozen API contract.

## Stack
- Next.js 14 (App Router)
- React + TypeScript
- Tailwind CSS
- Lucide icons (temporary UI assets)

The HazeWatch logo is intentionally a replaceable placeholder component at:
`src/components/hazewatch/BrandMark.tsx`.

## Source of truth
The backend contract is copied into `api_contract/`:
- `CONTRACT.md`
- `openapi.json`

Do not invent API fields in components. If the contract changes additively, regenerate types with:

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
`.env.local`:

```bash
NEXT_PUBLIC_HAZE_DATA_MODE=mock
```

Mock data lives in `src/lib/data/mock.ts` and uses contract-shaped objects. It is isolated from UI components and can be swapped without rewriting the page.

### Local FastAPI backend

```bash
NEXT_PUBLIC_HAZE_DATA_MODE=api
NEXT_PUBLIC_HAZE_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_HAZE_INSTITUTION_ID=
```

If no institution id is configured, the app requests `/institutions` and chooses the first school/hospital returned.

## Lite state logic

The agreed product mapping is centralized in `src/lib/ui/status.ts`:

- Safe: 0–12.0 µg/m³
- Watch: 12.1–35.4 µg/m³
- Alert: >=35.5 µg/m³

When available, alert risk uses `pm25_upper`, matching the frozen contract. A backend `alert` object is also treated as authoritative Alert state.

### Safe / Watch
No checklist and no alert review action. One plain-language monitoring message only.

### Alert
- `recommended_actions` rendered verbatim from the backend `Alert` object.
- Alert Review CTA appears.
- No auto-send is implemented on this screen.

## Beyond-training-range
If `forecast.uncertainty.any_point_beyond_training_range` is true, Lite Overview displays a persistent plain-language reliability notice. It does not expose `model_ceiling_pm25` as a raw user-facing decision number.

## Recent alerts
The current contract does not provide Safe/Watch transition history. Therefore the overview reads actual Alert objects from `GET /alerts?status=all` and does **not** fabricate Safe/Watch historical rows just to match the visual reference.

## Notifications
`Confirm & Send` belongs on the later Alert Review screen. The frozen API provides `POST /notifications/simulate`; that route will be wired when the Alert Review screen is implemented. It must remain simulated and never imply a real external WhatsApp/SMS send.

## UI reference
`public/ui-reference-lite-overview.png` is included only as a design reference for the developer.
