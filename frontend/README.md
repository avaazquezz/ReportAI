# ReportAI frontend

Nuxt 4, Pinia, Vuetify + Tailwind together (Vuetify owns the CSS reset and complex
components, Tailwind is layout/spacing utilities only — `preflight` disabled in
`tailwind.config.ts` so the two don't fight over base styles).

Two areas share this single project: the public marketing landing (`/`) and the
authenticated app shell (`/login`, `/dashboard` — guarded by `middleware/auth.ts`).
The admin panel proper (tenant management, templates, channels, recipients, report
history, usage dashboard) is not built yet — `/dashboard` is a placeholder.

## Setup

```bash
cp .env.example .env   # NUXT_PUBLIC_API_BASE defaults to http://localhost:8000
npm install
npm run dev
```

## Scripts

- `npm run dev` — dev server on `http://localhost:3000`
- `npm run lint` — ESLint
- `npm run typecheck` — `nuxi typecheck`
- `npm run build` — production build
