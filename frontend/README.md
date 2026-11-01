# SecQA Hub — web UI

React 18 + TypeScript + Vite single-page app for the SecQA Hub. The production build is written to
`../src/secqa/hub/static/` and served by the FastAPI Hub itself, so end users never need Node.

## Develop

```bash
# terminal 1 — the Hub API on :8787 (from the repo root)
secqa hub serve --port 8787

# terminal 2 — Vite dev server on :5173, proxies /api to :8787
cd frontend
npm ci
npm run dev
```

## Scripts

| Script              | What it does                                              |
|---------------------|-----------------------------------------------------------|
| `npm run dev`       | Vite dev server with HMR                                  |
| `npm run build`     | Type-check (`tsc -b`) and build into `src/secqa/hub/static` |
| `npm run typecheck` | TypeScript only                                           |
| `npm run lint`      | ESLint (typescript-eslint + react-hooks)                  |

## Conventions

- API types in `src/api/types.ts` mirror `src/secqa/hub/schemas.py` — update both together.
- All data fetching goes through React Query hooks in `src/api/hooks.ts`; mutations invalidate the affected keys.
- UI strings live in `src/lib/i18n.ts` (EN + ES; the ES dictionary is type-checked for completeness).
- Tool output (descriptions, evidence) is always rendered as text. `dangerouslySetInnerHTML` is banned by lint.
