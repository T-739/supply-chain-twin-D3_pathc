# B5 acceptance checklist

Tick every box before calling B5 "done on this machine". Every
item below is either a deterministic command or a one-click
check against the landed surface running on the committed
fixture bundles.

## Local startup

- [ ] `python3 -m pytest backend/tests` reports **40 passed**.
- [ ] `cd frontend && npm install` completes without errors
      (first time only).
- [ ] `cd frontend && npx tsc --noEmit` exits with 0 errors.
- [ ] `cd frontend && npm test` reports **64 passed** across
      9 test files.
- [ ] `python3 -m uvicorn backend.app:app --port 8001` starts
      and responds `{"status":"ok", …}` on
      `GET http://127.0.0.1:8001/healthz`.
- [ ] `GET http://127.0.0.1:8001/bundles` returns both committed
      fixture bundles:
      - `fixture_default_3mode_v1`
      - `fixture_b4_triplet_v1`
- [ ] `cd frontend && npm run dev` serves http://localhost:3000
      and the root redirects to `/overview`.

## Page-level checks

Run with the BFF up and `fixture_default_3mode_v1` selected
unless otherwise noted.

**Overview (`/overview`)**
- [ ] Header brand reads *Supply-Chain Digital Twin · Read-only
      thesis surface · B5* (not a stale phase marker).
- [ ] Bundle Selector lists both fixture bundles.
- [ ] `System identity`, `Bundle catalog`, `Selected bundle
      summary`, `Reproducibility`, `Repository lineage` all
      render.
- [ ] Lineage shows three nodes:
      `supply-chain-twin` → `supply-chain-twin-D3` →
      `supply-chain-twin-D3_pathc`.

**Session Runtime (`/session-runtime`)**
- [ ] Session focus selector lists the three variant tags for
      the current bundle (default trio) — auto-selects the
      first tag.
- [ ] Event list populates; event 0 is auto-selected.
- [ ] Three-layer detail renders: **Path B raw** /
      **Path C overlay** / **Extensions**.
- [ ] Path C overlay has two distinct tracks: *Governance truth*
      (Tier 1) and *Effective decision* (Overlay).
- [ ] Extensions show each of B1 / B2 / B3 / B4 with clear
      present/absent states.
- [ ] **B3** row is hard-labelled *not surfaced at event level*.
- [ ] **B4** row is hard-labelled *not surfaced at event level*
      AND carries the `experiment / default-off / compare-only`
      labels.
- [ ] Prev / Next nav updates the *Event N of M* heading; Prev is
      disabled at event 0.

**Compare Lab (`/compare-lab`)**
- [ ] Header meta shows bundle id, variant set, compare present,
      thesis present.
- [ ] KPI matrix renders three segmented sections
      (Overall / Cold phase / Warm phase).
- [ ] On the fixture, empty segments render the **honest**
      "No KPI rows present" notice rather than fabricated zeros.
- [ ] Deltas section renders the honest absent state on the
      fixture.
- [ ] Diverged events renders the honest empty state on the
      fixture.
- [ ] Thesis claim support card renders.
- [ ] `thesis_report.md` is rendered verbatim in a preformatted
      block (on the default-trio fixture only — B4 triplet
      omits thesis).
- [ ] **B4 experiment block** is always rendered, even in absent
      state, with the `experiment / default-off / compare-only`
      ribbon visible.
- [ ] Collapsible **Raw compare report** fallback is present.

**Advanced Lenses (`/advanced-lenses`)**
- [ ] Header explains lenses are "supplementary observability
      views".
- [ ] On the fixture, all four lenses render their **honest
      absent state**:
      - B1 replan, B2 correlator, B3 cumulative, B4 agent-visible.
- [ ] **B3 lens** always carries the *session / compare-level*
      scope label and refuses per-event attribution in its copy.
- [ ] **B4 lens** always carries the `experiment / default-off
      / compare-only` ribbon, in both absent and populated states.

**Legacy V2 (`/legacy-v2`)**
- [ ] Header badge ribbon reads `appendix · baseline · historical`.
- [ ] Page renders with no bundle selected (appendix does not
      depend on bundle data).
- [ ] Page contains **zero** `<button>`, `<input>`, `<textarea>`,
      or `<form>` elements.
- [ ] Boundary note reads *"does NOT expose an active legacy
      runtime, does NOT call into `src/api/*` or `app.py`…"*

## Cross-page / shell checks

- [ ] Every tab shows exactly one `<h1>`.
- [ ] No tab carries a "placeholder" badge — all five tabs are
      real.
- [ ] The Bundle Selector value survives tab switching.
- [ ] Reloading the browser preserves the Bundle Selector value
      (mirrored to `localStorage.b5.selectedBundleId`).
- [ ] Tab focus (keyboard) reveals a visible **Skip to main
      content** link in the top-left corner; pressing Enter on it
      moves focus into `#app-main`.
- [ ] At a narrow viewport (≤ 840 px), the header stacks and the
      wide tables scroll horizontally inside their containers
      instead of overflowing the page.

## Boundary checks

- [ ] `grep -R "src/api" backend/ frontend/src/` returns no
      imports (only documentation / test-copy mentions).
- [ ] `backend/tests/test_route_scan_get_only.py` passes (no
      POST / PUT / PATCH / DELETE routes registered).
- [ ] `POST http://127.0.0.1:8001/bundles/fixture_default_3mode_v1`
      returns 404 / 405 (method rejected).
- [ ] Switching to `fixture_b4_triplet_v1` does not surface
      `path_c_cold` as a session tag anywhere:
      - Overview bundle summary tag list;
      - Session Runtime focus selector options;
      - Compare Lab `sessions_compared`;
      - Advanced Lenses per-lens content panels.
- [ ] Legacy V2 stays read-only even as the selected bundle
      changes.
