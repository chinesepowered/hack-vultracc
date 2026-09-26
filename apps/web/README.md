# Tieout web app

Vite, React 19, TypeScript (strict), Tailwind CSS 4, shadcn/ui-style components on Radix, React Router, TanStack Query, lucide icons. The API contract it builds against is `docs/API.md`.

## Run it

```bash
pnpm install
pnpm dev          # http://127.0.0.1:5173, proxies /api to http://127.0.0.1:8000 (override with API_URL=...)
pnpm dev:mock     # same, but every /api call is served in the browser from recorded fixtures (VITE_MOCK=1)
pnpm build        # type-checks, then writes static files to dist/ (base "/"; the API or Caddy serves them with SPA fallback)
pnpm typecheck    # tsc --noEmit
pnpm e2e          # Playwright demo-flow checks against a mock dev server it starts on :5174
```

`pnpm e2e` uses the preinstalled Chromium (Playwright 1.56 matches build 1194). Set `SHOTS_DIR=/some/dir` to save screenshots, or `PW_CHROMIUM=/path/to/chromium` to use another browser binary.

## Mock mode

`VITE_MOCK=1` is compiled in as `__MOCK__`, so production builds contain no mock code or fixture data. In mock mode `src/mocks/mockApi.ts` implements the whole API in the browser:

- Data comes from real recordings in `src/mocks/fixtures/` (copies of `docs/fixtures`). Blue Harbor and Cedar Ridge are the real runs; the other ten clients reuse one of them as a template with names swapped and line counts scaled (Ironwood has 588 bank lines, for the matching-view performance check).
- Close September replays the recorded events for 12 clients over about 20 seconds. The simulation is a function of wall-clock time and only decisions (batches, approvals, replays, re-runs, kill switch, session) are stored in `localStorage`, so reloading mid-close continues where it left off. Add `?mockReset=1` to any URL to start clean.
- Supported: demo-account sign-in and role switching, close, live tiles over a simulated stream, run detail, approve or reject with maker-checker, AJE CSV only after approval, replay with matching hashes, re-run of stopped clients, ground truth, previous closes, admin console with kill switch (auto-resumes after 15 minutes), health.
- Mock downloads: the AJE CSV matches the real format; the workpaper and evidence pack are placeholders (CSV summary, JSON manifest).

## Layout

```
src/api/          types.ts (from docs/API.md), real.ts (fetch + EventSource), index.ts (real or mock)
src/mocks/        mockApi.ts, data.ts, fixtures/
src/hooks/        queries.ts: React Query hooks, SSE subscriptions with polling fallbacks
src/components/   ui/ (shadcn primitives), layout/, dashboard/, run/ (timeline, matching view, blast radius, review, replay, tabs)
src/pages/        Login, Dashboard, Run, Admin, How it works
e2e/              demo-flow.spec.ts
```

## Test hooks

The `data-testid` attributes used by the demo scripts (for example `close-period-button`, `client-tile-{client_id}` with `data-status` and `data-recon`, `timeline-step-{n}`, `blast-radius`, `approve-button`, `reproducible-badge`, `kill-switch`) are listed in the task brief and exercised by `e2e/demo-flow.spec.ts`. The finish step of the timeline is `timeline-step-finish`.
