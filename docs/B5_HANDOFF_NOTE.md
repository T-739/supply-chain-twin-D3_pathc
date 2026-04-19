# B5 handoff note

Short, read-once note for anyone picking up the B5 surface after
the closeout.

## B5 completion summary

All five tabs of the B5 full-stack surface are landed as real pages.
The surface ships as an independent Next.js frontend + FastAPI BFF
pair, consumes the on-disk `bundles/{bundle_id}/` contract defined
in [`docs/B5_BUNDLE_CONTRACT.md`](B5_BUNDLE_CONTRACT.md), and does
not modify any runtime-producing file (`src/`, `scripts/`,
`app.py`, `src/api/*`).

Phases shipped:

| Phase | Scope                                                 |
|-------|-------------------------------------------------------|
| 1     | Foundation: bundle contract, bundler, BFF scaffold, fixture bundles |
| 2     | Overview & Catalog                                    |
| 3A    | Session Runtime walking skeleton                      |
| 3B    | Session Runtime overlay/extensions deepening          |
| 4A    | Compare Lab canonical viewer                          |
| 5A    | Advanced Lenses (B1/B2/B3/B4 sibling-block viewers)   |
| 6A    | Legacy V2 appendix page                               |
| Closeout | App-wide polish (a11y, responsive, continuity, docs) |

Test counts at closeout: **40 backend pytest** (incl. GET-only
route guard) + **64 frontend vitest** + `tsc --noEmit` clean.

## What B5 is

- A **read-only, artifact-driven** surface over the evaluation
  bundles that `scripts/session_eval_harness.py` produces.
- An **independent** frontend and FastAPI BFF — they do not import
  from `src/api/*`, do not revive `app.py`, do not touch runtime
  modules.
- A **GET-only** HTTP surface (enforced by
  `backend/tests/test_route_scan_get_only.py`).
- A **canonical viewer**: every compare/KPI/thesis cell is
  rendered verbatim from the bundle; no recomputation happens in
  the frontend or the BFF.
- A **five-tab** information architecture:
  - `/overview`        — system identity + bundle catalog
  - `/session-runtime` — per-session three-layer event detail
  - `/compare-lab`     — canonical viewer over `compare_report.json` + `thesis_report.md`
  - `/advanced-lenses` — conditional sibling blocks (B1/B2/B3/B4)
  - `/legacy-v2`       — appendix / baseline / historical

## What B5 is NOT

- **Not a runtime.** It does not execute the twin, does not run
  agents, does not drive any policy gate.
- **Not a write surface.** No POST / PUT / PATCH / DELETE routes.
  The bundler is also read-only in intent: it repackages existing
  harness output and never mutates session artifacts.
- **Not a compare engine.** KPI matrix cells, deltas, and the
  `supports_claim` verdict are rendered exactly as
  `src/session/session_compare.py` committed to them.
- **Not a thesis writer.** `thesis_report.md` is displayed
  verbatim; nothing is paraphrased.
- **Not a legacy front-end.** `/legacy-v2` is explanatory appendix
  material. It does not revive `src/api/*` or `app.py`.

## Key boundaries

- **B4** (agent-visible memory experiment) is always labelled
  *experiment / default-off / compare-only* and is rendered inside
  an isolated panel. It never appears as a per-event overlay and
  never merges into the mainline KPI / delta / thesis view.
- **B3** (cumulative memory) is always labelled *session /
  compare-level*. No per-event B3 attribution is synthesized.
- **`path_c_cold` is not assumed.** Every page that iterates a
  variant set reads `variant_tags` from the artifact and never
  indexes by name; B4 triplet bundles (no `path_c_cold`) render
  cleanly.
- **No compare math recomputation.** Null deltas render literally
  as `null`. Missing sibling blocks show honest absent states.
- **Selection persistence is cosmetic.** The selected bundle id is
  mirrored to `localStorage.b5.selectedBundleId` so a browser
  reload keeps your place; stale ids that no longer appear in the
  index are dropped on the next load.

## Where to start

- Frontend install / run: [`frontend/README.md`](../frontend/README.md)
- Bundle contract: [`docs/B5_BUNDLE_CONTRACT.md`](B5_BUNDLE_CONTRACT.md)
- Demo walk-through: [`docs/B5_DEMO_RUNBOOK.md`](B5_DEMO_RUNBOOK.md)
- Acceptance gate: [`docs/B5_ACCEPTANCE_CHECKLIST.md`](B5_ACCEPTANCE_CHECKLIST.md)
- Problem triage: [`docs/B5_TROUBLESHOOTING.md`](B5_TROUBLESHOOTING.md)

## Demo vs fixture bundles

Two tiers ship in `bundles/`:

- **Showcase bundles** — `demo_showcase_default_trio_v1` and
  `demo_showcase_b4_triplet_v1`. Curated deterministic demo
  outputs with populated event streams, KPI matrix, deltas,
  diverged events, thesis report, and (on the default trio) B1
  replan / B2 correlation / B3 cumulative sibling blocks. Use
  these for live presentations. Regenerate with
  `PYTHONPATH=. python3 -m tools.bundler.showcase_builder
  --bundles-root bundles`.
- **Fixture bundles** — `fixture_default_3mode_v1` and
  `fixture_b4_triplet_v1`. Structurally minimal; the backend
  contract tests and the frontend route tests drive off these.
  Regenerate with `PYTHONPATH=. python3 -m
  tools.bundler.fixture_builder --bundles-root bundles`.
