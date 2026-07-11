# ISAAC local UI frontend (`apps/web`)

A **local-first, synthetic-only** React + Vite + TypeScript frontend over `apps/api`. It renders
the deterministic core's state (draft, evidence, validation, audit, advisory warnings) — it makes
no validity decisions itself; every verdict comes live from the backend.

## Run

```bash
npm install
npm run dev     # http://localhost:5173 — requires apps/api running on 127.0.0.1:8000
```

## Test and build

```bash
npm test        # vitest
npm run build   # tsc -b && vite build
```

## Notes

- CORS-restricted to talk only to `http://127.0.0.1:8000`; no other backend is supported.
- Real/private file upload is not wired here — the on-ramp calls the backend's governance seam,
  which always refuses (`403`).
- The assistant panel shows static, source-labeled sample answers; freeform chat is not wired.

See **[`../../docs/ui-local-dev.md`](../../docs/ui-local-dev.md)** for the full setup guide and
browser demo walkthrough.
