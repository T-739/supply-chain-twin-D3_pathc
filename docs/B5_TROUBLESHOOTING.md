# B5 troubleshooting

Short triage guide for the common states a new viewer hits when
bringing up the B5 surface locally. Each entry names a symptom,
an explanation, and the smallest fix.

## 1. Frontend up, backend down

**Symptom.** The app shell renders, but the Bundle Selector is
disabled and reads *"Loading…"* or *"No bundles available"*.
Overview's Bundle Catalog shows the error row
`Could not load bundle index: BFF GET /bundles failed: …`.

**Cause.** The frontend's `/api/bff/*` proxy is pointing at a
BFF that is not running (default: `http://127.0.0.1:8001`).

**Fix.**

```bash
python3 -m uvicorn backend.app:app --port 8001
```

Then refresh the browser. Alternative: set `B5_BFF_BASE_URL`
before `npm run dev` to point at a running BFF elsewhere.

The UI keeps rendering through this state — the error is
surfaced in place, not thrown. Overview, Legacy V2 static copy,
and the five-tab nav remain usable without a BFF.

## 2. Compare absent

**Symptom.** Compare Lab renders its header and bundle summary,
then shows an amber notice:

> This bundle does not carry a `compare_report.json`. Compare
> surfaces below are omitted…

or

> Bundle metadata claims a compare report, but the backend could
> not deliver `compare_report_raw` at load time.

**Cause.** Either the bundle metadata says `has_compare_report:
false` (nothing to show) or the file is listed in metadata but
unreadable at load time (inconsistency, surfaced explicitly).

**Fix.** Nothing on the B5 side to fix — this is the canonical
honest state. Produce a bundle that actually has
`compare_report.json` (run `scripts/session_eval_harness.py`
then repackage with `tools/bundler/`), or pick a different
bundle from the selector.

Note: the committed fixture bundles DO ship with a
`compare_report.json`, but it is intentionally sparse
(empty `kpi_matrix`, empty `deltas`, no B1/B2/B3/B4 sibling
blocks). That is expected — Compare Lab will render the
compare envelope but the per-section notices will say
"no rows present". See the demo runbook's **honesty caveat**.

## 3. No bundle selected

**Symptom.** Session Runtime / Compare Lab / Advanced Lenses each
show their *no-bundle* notice:

> No bundle is currently selected. Pick one from the bundle
> selector in the app header to populate this page.

**Cause.** Either the index is empty (nothing under the
BFF's `bundles/` root, or the root doesn't exist), or the last
selection was for a bundle that is no longer present.

**Fix.** Produce or commit at least one bundle:

```bash
# fastest: re-emit the committed fixture bundles
PYTHONPATH=. python3 -m tools.bundler.fixture_builder \
    --bundles-root bundles

# production: repackage a harness run
python3 -m tools.bundler \
    --harness-dir runs/phase3_demo \
    --bundles-root bundles \
    --bundle-id <your_bundle_id>
```

Reload the frontend. The Bundle Provider auto-selects the first
available bundle on index load; stale ids from a previous
session are dropped if they no longer appear.

Overview and Legacy V2 remain useful without a selection — they
render their static explanatory content regardless.

## 4. B4 triplet: "why is `path_c_cold` missing?"

**Symptom.** With `fixture_b4_triplet_v1` (or any B4 triplet
bundle) selected, the Session Runtime focus selector lists only
`baseline_static`, `path_c_warm_policy_only`, and
`path_c_warm_agent_visible_memory`. `path_c_cold` is not
available. Compare Lab's `sessions_compared` does not contain
`path_c_cold` either.

**Cause.** This is by design. The B4 experiment triplet
deliberately omits `path_c_cold`; the bundle's `metadata.json`
makes this explicit in its `warnings` list:

> path_c_cold variant intentionally absent (B4 experiment triplet).

**Fix.** None — the B5 surface never assumes `path_c_cold`
exists and renders the triplet cleanly. If a demo needs
`path_c_cold`, switch to a default-trio bundle
(`fixture_default_3mode_v1`).

## 5. B4 block looks empty on the B4 triplet

**Symptom.** On `/compare-lab` or `/advanced-lenses` with the B4
triplet bundle selected, the B4 agent-visible memory experiment
block is rendered inside its dashed warn-coloured panel but
shows the *absent* state copy:

> This compare report does not carry the
> `agent_memory_experiment_summary` sibling block…

**Cause.** The committed fixture bundle's
`compare_report.json` does NOT include the B4
`agent_memory_experiment_summary` sibling block — the fixture
builder emits a structural compare envelope only. The UI is
telling the truth.

**Fix.** For a populated B4 block, produce a real harness run
with `--enable-agent-visible-memory` and repackage with
`tools/bundler/`. The compare artifact will then include
`agent_memory_experiment_summary` and the B4 block will populate
its structural fields.

The `experiment / default-off / compare-only` ribbon remains
visible in both states — this is the canonical framing.

## 6. Placeholder badge shows up again

**Symptom.** A nav tab renders a "placeholder" badge next to its
label.

**Cause.** Someone flipped a tab back to `enabled: false` in
`frontend/src/lib/constants.ts`, or added a new route without
marking it enabled.

**Fix.** All five B5 tabs are real at closeout. The closeout
test suite
(`frontend/src/__tests__/closeout.test.tsx`) asserts no tab
carries a placeholder badge; running `npm test` will surface the
regression.

## 7. Bundle Selector value doesn't persist after a reload

**Symptom.** Reloading the browser clears the Bundle Selector
back to the first available bundle, even though you picked a
specific one.

**Cause.** `localStorage` is disabled (Safari private mode, some
corporate environments) or the app is running in an iframe with
storage blocked.

**Fix.** Expected behaviour in that environment. The Bundle
Provider falls back to auto-selecting the first bundle from the
index; no error is thrown. Selection still persists in-memory
while the tab is open.

## 8. `npm test` fails with unexpected `localStorage` errors

**Symptom.** Vitest reports `localStorage.setItem is not a
function` or similar.

**Cause.** A custom test is writing to `localStorage` directly,
after the shared `test-setup.ts` `afterEach` has already
cleaned it up for the next test.

**Fix.** Prefer the public seam — pass
`initialSelectedBundleId` on `<AppShell>` to simulate a stored
selection, rather than poking `window.localStorage` from test
code. `test-setup.ts` clears `localStorage` between tests on
purpose so test ordering never leaks state.
