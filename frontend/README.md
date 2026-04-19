# B5 frontend

Read-only Next.js + TypeScript surface over the B5 bundle contract
(see [`docs/B5_BUNDLE_CONTRACT.md`](../docs/B5_BUNDLE_CONTRACT.md)).

This app is:

- **read-only** — no write routes are exposed, no runtime is triggered
  from the browser;
- **artifact-driven** — every cell comes from a file already under
  `bundles/{bundle_id}/` and served verbatim by the BFF;
- **independent** — it does NOT import from `src/api/*` or `app.py`;
  it talks to the B5 FastAPI BFF (`backend/app.py`) through a single
  adapter (`src/lib/bff.ts`).

## Install

```bash
cd frontend
npm install
```

## Run the dev stack

The frontend talks to the B5 BFF on `http://127.0.0.1:8001` by default.
Start both in parallel:

```bash
# terminal 1 — BFF
python3 -m uvicorn backend.app:app --port 8001

# terminal 2 — frontend
cd frontend
npm run dev   # http://localhost:3000
```

Cross-origin requests are avoided by a Next.js rewrite: every frontend
request to `/api/bff/*` is proxied to the BFF. To point at a different
BFF, set `B5_BFF_BASE_URL` before `npm run dev`.

## Tests

```bash
cd frontend
npm test             # vitest (jsdom) suite
npx tsc --noEmit     # TypeScript typecheck
```

Backend regression tests live in Python:

```bash
python3 -m pytest backend/tests
```

## Page structure

Five tabs, all real as of the B5 closeout:

| Route              | Purpose                                                                                   |
|--------------------|-------------------------------------------------------------------------------------------|
| `/overview`        | System identity, bundle catalog, selected-bundle summary, reproducibility, lineage strip. |
| `/session-runtime` | Per-session event stream + three-layer event detail (Path B raw / Path C overlay / extensions). |
| `/compare-lab`     | Canonical viewer over `compare_report.json` + `thesis_report.md` (KPI matrix, deltas, diverged events, thesis). |
| `/advanced-lenses` | Conditional / observability-only sibling blocks (B1 replan, B2 correlator, B3 cumulative, B4 agent-visible-memory experiment). |
| `/legacy-v2`       | Appendix / baseline-historical page explaining the earlier D3 Path B era. Not an active runtime surface. |

The global shell provides a header (brand + Bundle Selector), a 5-tab
nav, a skip-to-main link, and a footer. The Bundle Selector selection
is mirrored to `localStorage` under `b5.selectedBundleId` so that a
page reload restores the previously chosen bundle iff it still appears
in the BFF index.

## Data flow

```
Browser
  │
  │  GET /api/bff/bundles
  │  GET /api/bff/bundles/{bundle_id}
  │  GET /api/bff/bundles/{bundle_id}/sessions/{variant_tag}
  ▼
Next.js rewrite  →  FastAPI B5 BFF (backend/app.py, GET-only)
                       │
                       ▼
                    bundles/{bundle_id}/
                      metadata.json
                      sessions/{tag}/session_artifact.json
                      sessions/{tag}/memory.jsonl
                      compare_report.json
                      thesis_report.md
```

The BFF is GET-only (enforced by
[`backend/tests/test_route_scan_get_only.py`](../backend/tests/test_route_scan_get_only.py)).
The frontend uses the adapter in [`src/lib/bff.ts`](src/lib/bff.ts)
exclusively — no component ever reads bundle files directly.

## Boundaries

- B4 (agent-visible memory) is always labeled **experiment / default-off
  / compare-only**. It does not appear as a normal per-event overlay
  anywhere in the UI; its only footprint is the compare-report
  `agent_memory_experiment_summary` sibling block, rendered inside an
  isolated panel.
- B3 (cumulative memory) is surfaced as **session / compare-level**
  provenance only. There is no per-event B3 attribution anywhere in
  the UI.
- The Legacy V2 tab is **appendix / baseline / historical** only. It
  does not call into `src/api/*` or revive `app.py`.
- No compare math is recomputed in the frontend. The Compare Lab
  renders the compare artifact verbatim.

## Layout

```
src/
  app/                         # Next.js App Router pages
    layout.tsx                 # root layout + AppShell
    page.tsx                   # redirects to /overview
    overview/                  # real page
    session-runtime/           # real page
    compare-lab/               # real page
    advanced-lenses/           # real page
    legacy-v2/                 # real page
  components/                  # reusable UI
    AppShell.tsx, NavTabs.tsx, BundleSelector.tsx, BundleContext.tsx
    OverviewPage.tsx, SessionRuntimePage.tsx, CompareLabPage.tsx,
      AdvancedLensesPage.tsx, LegacyV2Page.tsx
    compare/, lenses/, common/ # page-family subtrees
    CollapsibleJson.tsx        # shared raw-JSON fallback primitive
  lib/
    bff.ts                     # single BFF adapter
    types.ts                   # hand-maintained mirror of backend models
    constants.ts               # static copy (lineage, labels, appendix)
  __tests__/                   # vitest + React Testing Library
```
