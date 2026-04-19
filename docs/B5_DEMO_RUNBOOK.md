# B5 demo runbook (5–8 min)

A short, tested walk-through of the five-tab B5 surface. Assumes
the viewer has never seen the app before. Designed to run on the
committed fixture bundles so no harness run is required.

## Pre-demo

Two supported bring-up paths. Either works for the runbook
below; pick whichever fits the machine.

### Option A — Docker Compose (one command)

```bash
docker compose up --build
```

Builds the two local-demo images the first time, then starts:

- frontend → <http://localhost:3000>
- BFF (GET-only) → <http://localhost:8001>

The `bundles/` directory on the host is bind-mounted read-only
into the BFF container, so any bundles you generate on the host
(fixture, showcase, or a future harness run) appear in the app
on the next request without rebuilding. Stop the stack with
`Ctrl-C` or `docker compose down`.

See the **Deployment** section at the end of this runbook for
configuration details and validation steps.

### Option B — local processes (two terminals)

```bash
# terminal 1 — B5 BFF (GET-only, port 8001)
python3 -m uvicorn backend.app:app --port 8001

# terminal 2 — frontend (port 3000)
cd frontend
npm install   # first time only
npm run dev
```

Open <http://localhost:3000> in a browser. The root redirects
to `/overview`.

## Recommended demo bundle map

Two tiers — prefer the **showcase** bundles for live
presentations; the **fixture** bundles remain the canonical
structural / contract coverage.

| Role                                  | Bundle                             |
|---------------------------------------|------------------------------------|
| Default-trio mainline demo            | `demo_showcase_default_trio_v1`    |
| B4 compare-only supplement            | `demo_showcase_b4_triplet_v1`      |
| Contract / smoke (fallback)           | `fixture_default_3mode_v1`         |
| B4 contract / smoke (fallback)        | `fixture_b4_triplet_v1`            |

Generate / regenerate the showcase bundles with:

```bash
PYTHONPATH=. python3 -m tools.bundler.showcase_builder \
    --bundles-root bundles
```

**Honesty caveat — read this out loud if asked.** The showcase
bundles are **curated deterministic demo outputs**: every field
shape matches `src/session/session_schema.py` and
`src/session/session_compare.py` exactly, but the values are
hand-picked to tell a coherent demo story rather than drawn
from a live harness run. They are stable across machines and
carry no dependency on LLM keys / RAG setup. The older
*fixture* bundles remain the canonical *structural* coverage
used by the automated tests.

**Tip.** Open the Bundle Selector once at the top of the demo and
switch to `demo_showcase_default_trio_v1`. The selection is
mirrored to `localStorage` so it survives any navigation during
the walkthrough.

## 1. Overview (~1.5 min)

1. Land on `/overview`. Point out the global shell:
   - top-left brand (*Supply-Chain Digital Twin · Read-only thesis
     surface · B5*);
   - top-right **Bundle Selector** — pre-selected because the
     provider auto-picks the first bundle;
   - five-tab nav, footer ribbon.
2. Scroll through the page:
   - **System identity** — three cards (Path B · Path C · dual-track
     contract). Note the lede: "The runtime is deterministic and
     lives outside this surface."
   - **Bundle catalog** — shows both committed fixture bundles
     with variant-set labels (*default trio* vs *B4 triplet*).
   - **Selected bundle summary** — variant tags, session table,
     warnings list; use this to show how B4 triplet's warnings
     explicitly say *"path_c_cold variant intentionally absent"*.
   - **Reproducibility** — four cards covering deterministic
     construction, frozen schemas, read-only surface, bundle
     contract.
   - **Repository lineage** — three nodes from
     `supply-chain-twin` → `supply-chain-twin-D3` →
     `supply-chain-twin-D3_pathc`.

**Say:** "Every cell you'll see across the five tabs comes from
a file under `bundles/{bundle_id}/`. The frontend never calls a
runtime."

## 2. Session Runtime (~2 min)

1. Click the **Session Runtime** tab.
2. Point out the **Session focus selector** — driven by the
   selected bundle's variant tags. On the default trio it lists
   all three modes.
3. Select `path_c_warm`. The page auto-selects event 0.
4. Walk the session summary strip: mode, events_observed,
   route/action mix, schema_versions.
5. Walk the **three-layer event detail**:
   - **Path B raw** — collapsible `baseline_event_result` JSON,
     rendered verbatim.
   - **Path C overlay** — two side-by-side tracks (Tier 1 *Governance
     truth* and Overlay *Effective decision*). Call out the
     *aligned* / *diverged* pill. Note the *Adaptive adjustment*
     sub-panel ("None on this event").
   - **Extensions** — B1 replan (absent on fixture) · B2
     correlation (absent) · **B3 locked at "not surfaced at event
     level"** · **B4 locked at "not surfaced at event level" plus
     the experiment ribbon**.
6. Click **Next →** in the detail header to move to event 1; the
   "Event N of M" label updates.

**Say:** "Dual-track truth is always visible. B3 and B4 are
boundary-labelled here so they don't get mistaken for per-event
overlays."

## 3. Compare Lab (~1.5 min)

1. Click the **Compare Lab** tab.
2. Header shows the bundle id, variant set (`default_3_mode`),
   compare report present, thesis report present.
3. Walk the sections:
   - **Bundle compare summary** — sessions_compared,
     baseline_mode, schema_version (v1.1 on the showcase bundle).
   - **KPI matrix** — three segmented tables (Overall / Cold phase
     / Warm phase). On the showcase bundle, the Overall segment
     has eleven populated KPI rows with real numeric cells.
   - **Deltas** — two tables:
     `path_c_cold_minus_baseline_static` (zeros — honest) and
     `path_c_warm_minus_baseline_static` (positive SLA, positive
     calibrated-autonomy, non-increasing cost).
   - **Diverged events** — one entry (`EV-003`) with a structured
     `adjustment_ref` (`R-AUTOEXPEDITE-LOW / UPGRADE_ONE_LEVEL,
     MEDIUM → LOW`).
   - **Thesis** — *Thesis claim support* card reads
     `supports_claim: **true**`; thesis_report.md renders verbatim
     with canonical KPI tables and the deltas-vs-baseline section.
   - **B4 agent-visible memory experiment (compare-only)** — on
     the default trio, this block is in its *absent* state. Note
     the `experiment / default-off / compare-only` ribbon is
     still visible.
4. Expand **Raw compare report** at the bottom to show the
   verbatim JSON fallback.

**Say:** "Compare Lab is a viewer, not a compare engine. Null
deltas render literally as `null`. If the artifact didn't commit
to it, we don't show it."

## 4. Advanced Lenses (~1 min)

1. Click the **Advanced Lenses** tab.
2. The page explains that lenses are *supplementary observability
   views over conditional sibling blocks*.
3. On the showcase default-trio bundle, three lenses light up and
   one stays in its absent state:
   - **B1 · Replan** — `sessions_with_replan: path_c_warm`,
     `total_replan_events: 1`, a per-mode rates table
     (`replan_trigger_rate: 0.1429`, `replan_recovery_rate:
     1.0`), and a trigger-type counts matrix
     (`COST_DEVIATION: 1`).
   - **B2 · Correlator** — two sessions with correlation data
     (`path_c_cold`, `path_c_warm`), `ETA_PATH_COMPOUND: 2`
     overall, `EV-004` in the correlated-event-ids union.
   - **B3 · Cumulative memory** — `sessions_with_cumulative_
     memory: path_c_warm`, per-session row counts
     (`self_session_row_count: 2`, `cumulative_row_count: 3`),
     and a prior-session provenance table
     (`PRIOR-SESSION-A: 2`, `PRIOR-SESSION-B: 1`). Scope label
     stays **session / compare-level**.
   - **B4 · Agent-visible memory (experiment)** — absent state;
     isolated warn-coloured ribbon with the three experiment
     labels.

**Say:** "No B3 per-event semantics are invented here. No B4
promotion into a normal feature."

## 5. Switch bundles: B4 triplet (~1 min)

1. Return to the top-right **Bundle Selector** and switch to
   `demo_showcase_b4_triplet_v1`.
2. Go back to **Compare Lab**:
   - variant_set reads `b4_experiment_triplet`;
   - `sessions_compared` lists `baseline_static /
     path_c_warm_agent_visible_memory / path_c_warm_policy_only`
     — no `path_c_cold` anywhere in the page;
   - thesis report: absent (metadata is honest about it;
     `thesis_claim_support.supports_claim` is null, with an
     explanatory note explaining why there is no canonical warm
     mode to compare against);
   - **B4 compare-only block is populated**: schema v1.0, variant
     tags, session-id map, and a diverged event id
     (`EV-006`) where the agent-visible variant chose
     `COMPENSATE` vs policy-only's `TRANSFER`.
3. Go to **Advanced Lenses**. The B4 lens shows the populated
   experiment summary; B1 / B2 / B3 render their honest absent
   states (B4 triplet does not carry those sibling blocks).
4. Go to **Session Runtime**. The focus selector lists the B4
   triplet. Select `path_c_warm_agent_visible_memory` — the B4
   extension label stays at *"not surfaced at event level"* even
   on the variant that actually diverges in Compare Lab.

**Say:** "B4 is an experiment branch. Its footprint is visible
only in Compare Lab's B4 block and the Advanced Lenses B4
panel — even on the agent-visible variant, the UI never promotes
B4 into a normal per-event layer. And nothing assumes
`path_c_cold` exists."

## 6. Legacy V2 (~1 min)

1. Click the **Legacy V2** tab.
2. Header badges: `appendix` · `baseline` · `historical`.
3. Walk the five sections quickly: identity, why V2 still matters
   (three cards), evolution (the same three-node lineage), V2
   capability appendix, and the dashed **Boundary note**.
4. Point out: no buttons, no forms. Read the boundary note aloud:
   *"This page is explanatory appendix material. It does NOT
   expose an active legacy runtime…"*

**Say:** "Legacy V2 is a document, not a second product."

## Close (~30 s)

- Reload the page. Show the selected bundle survives the reload
  (mirrored to `localStorage.b5.selectedBundleId`).
- Tab into the viewport — the `Skip to main content` link
  becomes visible.

**Close with:** "Five tabs, one read-only surface, one bundle
contract, zero runtime assumptions."

---

## Deployment (minimal local compose)

A small Docker Compose setup ships in the repo root for
one-command local bring-up. It is explicitly for local demo
/ handoff, **not** production hardening — no TLS, no auth, no
horizontal scale, no database (there isn't one), no logging
stack.

### Files

| File | Role |
|---|---|
| `docker-compose.yml`    | Two services: `backend` (BFF) and `frontend` (Next.js). |
| `backend/Dockerfile`    | Python 3.12 + pinned BFF deps; runs `uvicorn backend.app:app`. |
| `backend/requirements.txt` | Pinned `fastapi`, `uvicorn[standard]`, `pydantic`. |
| `frontend/Dockerfile`   | Two-stage Node 20: `npm ci` + `npm run build`, then `next start`. |
| `.dockerignore` + per-dir `.dockerignore` | Keep build contexts small. |

### Bring up

```bash
docker compose up --build
```

First run takes a few minutes (npm ci + next build). Subsequent
runs start in seconds.

### Expected local URLs

| URL | Served by |
|---|---|
| <http://localhost:3000>               | frontend shell (redirects to `/overview`) |
| <http://localhost:3000/overview>      | Overview tab |
| <http://localhost:3000/session-runtime> | Session Runtime tab |
| <http://localhost:3000/compare-lab>   | Compare Lab tab |
| <http://localhost:3000/advanced-lenses> | Advanced Lenses tab |
| <http://localhost:3000/legacy-v2>     | Legacy V2 appendix |
| <http://localhost:8001/healthz>       | BFF health probe |
| <http://localhost:8001/bundles>       | Bundle index (JSON) |

The frontend proxies every `/api/bff/*` request to the backend
service over the compose network, so no CORS config is required.

### Required env vars

Both services run with sane defaults; the compose file sets
what matters. Override with `docker compose --env-file …` or
`docker compose -e VAR=…` if needed.

| Var | Default | Role |
|---|---|---|
| `B5_BUNDLES_ROOT` | `/app/bundles` (in container) | Path the BFF scans for `bundles/{bundle_id}/` trees. Compose bind-mounts the host `./bundles/` here read-only. |
| `B5_BFF_BASE_URL` | `http://backend:8001` (in container) | Target for the Next.js `/api/bff/*` rewrite. Override to point the frontend at a BFF elsewhere. |

### Bundles

The BFF reads bundles from `/app/bundles` in-container, which is
a read-only bind mount of the host's `bundles/` directory. Add
bundles on the host (`tools/bundler/showcase_builder.py`,
`tools/bundler/fixture_builder.py`, or a real harness run +
`tools/bundler/__main__.py`) and they become visible to the BFF
on the next HTTP request — no container rebuild required.

### Validation

```bash
# 1. stack comes up cleanly
docker compose up --build -d
docker compose ps            # both services: "Up" / healthy

# 2. BFF surface responds
curl -s http://localhost:8001/healthz        # {"status":"ok", …}
curl -s http://localhost:8001/bundles | jq '.bundles | length'
                                             # >= 1 on a populated repo

# 3. frontend shell responds
curl -sI http://localhost:3000 | head -n1    # 200 OK (after redirect)
curl -s http://localhost:3000/overview | head -n5
                                             # HTML with <html lang="en">

# 4. write-path rejection (belt-and-suspenders)
curl -s -o /dev/null -w '%{http_code}\n' \
    -X POST http://localhost:8001/bundles    # 405 (or 404)

# 5. stop
docker compose down
```

### Deployment remains read-only and GET-only

- No write routes are exposed. The route-scan guard in
  [`backend/tests/test_route_scan_get_only.py`](../backend/tests/test_route_scan_get_only.py)
  fails if any non-GET method is ever registered; the compose
  image is built from that same codebase.
- The bundles directory is mounted with `:ro`, so even if the
  BFF process attempted a write it would fail at the
  filesystem layer.
- Both containers run as a non-root user.
- No database, no secrets, no admin / refresh / generation
  route. Updating the surface = regenerating a bundle on the
  host; there is no in-app mutation path.
