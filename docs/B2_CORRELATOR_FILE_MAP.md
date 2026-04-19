# B2_CORRELATOR_FILE_MAP.md

Status: **B2 Slice 1 draft.** Decisions D1–D5 (see
`docs/B2_CORRELATOR_BOUNDARY.md §12`) are proposed. The file map
below partitions the repo for the Slice 1 PR
(schemas + frozen tests, no runtime wiring yet).
Authority: `docs/B2_CORRELATOR_BOUNDARY.md`,
`docs/B2_CORRELATOR_CONTRACT_DRAFT.md`, `PATH_C_BOUNDARY.md`.

This document maps B2 (Event correlator) against the current repo
layout so the Slice 1 implementation PR can proceed without
surprises. Every entry is grounded in the state of the repo at the
time of writing.

Slice 1 delta (not yet on `main`):
- Create `src/correlator/__init__.py`, `correlator_schema.py`,
  `correlator_config.py`, `correlator_patterns.py` (module shell,
  closed Literals, frozen pydantic skeletons, module constants —
  **no match function yet**).
- `src/session/session_schema.py` — `SessionEventRecord` MINOR
  bump `1.1 → 1.2`, one optional `correlation_context: Optional[
  CorrelationContext] = None` with `None` default.
- `PATH_C_SCHEMA_REGISTRY.md` — three B2 schemas registered at
  1.0; `SessionEventRecord` bumped to 1.2.
- `tests/test_path_c_import_topology.py` — `src/correlator/`
  added to scan roots.
- `tests/test_path_c_schema_frozen.py` + fixture — extended for
  the new schemas and `SessionEventRecord` 1.2 defaults.
- `tests/test_correlator_schema_frozen.py`,
  `tests/test_correlator_no_nl_truth.py`,
  `tests/test_correlator_observability_only.py` — added.

---

## 1. Files expected to stay untouched (frozen under B2)

These files MUST NOT be modified by any PR labelled B2 Slice 1.

### Path B runtime core (frozen Tier 1)

- `src/event_schema.py` — `EventPayload`, `EventType`,
  `EventSeverity`, `AffectedEntityRef`.
- `src/outcome_schema.py` — `ExecutionOutcome`.
- `src/policy_gate.py` — `PolicyDecision`, `decide_policy`.
- `src/agents/governance_agent.py` — `GovernanceOutput`.
- `src/agents/cost_agent.py`, `src/agents/operations_agent.py`.
- `src/execution_adapters.py`.
- `src/twin_state.py`.
- `src/event_loop.py`.
- `src/graph.py`.
- `src/outcome_store.py`.

### Research Core (frozen)

- `src/evaluation.py`
- `src/action_code_mapper.py`
- `data/cases/*.json`

### Path C-min adaptive / memory / preflight

- `src/adaptive/adaptive_policy_gate.py`.
- `src/adaptive/adaptive_policy_config.py`.
- `src/adaptive/adaptive_schema.py`.
- `src/adaptive/cold_start.py`.
- `src/adaptive/preflight.py`.
- `src/learning/memory_schema.py`.
- `src/learning/memory_summarizer.py`.
- `src/learning/episodic_memory.py` — append-only; correlator
  never writes memory.

### B1 replan layer

- `src/replan/__init__.py`, `replan_schema.py`, `replan_config.py`,
  `replan_trigger.py`, `replan_orchestrator.py`,
  `expected_outcome.py` — unchanged. Correlator does not couple to
  replan in Slice 1.

### Path C-min session core

- `src/session/digests.py` — correlator does **not** participate
  in `session_id` in Slice 1 (correlator output is derived from
  the already-finalized record stream; including it in the digest
  would be redundant). If a future slice opts to include it, it
  must append to the canonical config dict, not redefine the hash.
- `src/session/session_manager.py` — save/load/replay unchanged.
  The new optional field rides along automatically through the
  pydantic serializer; no changes needed as long as serializer
  uses model-level canonical JSON.

### KPI layer — explicitly frozen for Slice 1

- `src/session/kpi_calculator.py` — **frozen for Slice 1** (D3).
  Correlator-aware KPIs are a later-slice concern.

### Tests that must continue to pass byte-for-byte

- `tests/test_phase0_baseline_regression_phase1.py`
- `tests/test_path_c_vs_baseline_divergence.py`
- `tests/test_replay_byte_identical.py` (new cases additive only)
- `tests/test_determinism_stress.py` (new cases additive only)
- `tests/test_kpi_calculator.py`
- `tests/test_session_compare.py`
- `tests/test_adaptive_audit_trail.py`
- `tests/test_cold_start_behavior.py`
- `tests/test_adjustment_rules.py`
- `tests/test_adaptive_policy_gate.py`
- `tests/test_governance_meta_preflight.py`
- `tests/test_execution_metadata_mandatory.py`
- `tests/test_event_loop_c_wrapping.py`
- `tests/test_session_manager.py`
- `tests/test_thesis_report_generation.py`
- Every `tests/test_replan_*.py` currently on `main`.

---

## 2. Files extendable additively under B2 Slice 1

### Session overlay (one MINOR bump only)

- `src/session/session_schema.py` — add optional field:
  - `SessionEventRecord.correlation_context: Optional[CorrelationContext] = None`.
  - Bump `_SESSION_EVENT_RECORD_SCHEMA_VERSION` constant
    `"1.1" → "1.2"`.
  - No changes to `GovernanceTruthRef`, `EffectiveDecisionRef`,
    `SessionConfig`, `SessionKPIs`, `SessionArtifact`,
    `SessionMode`, `PolicyRouteSource`, `FinalRoute`,
    `ActionTaken`, `ExecutionStatus`.

### Registry / boundary docs

- `PATH_C_SCHEMA_REGISTRY.md` — register `CorrelationSignal`,
  `CorrelationContext`, `CorrelatorConfig` at 1.0; bump
  `SessionEventRecord` entry to 1.2 with a change-history line
  "1.2 — additive optional `correlation_context`
  (B2 Slice 1)".
- `PATH_C_BOUNDARY.md` — append a cross-reference to
  `docs/B2_CORRELATOR_BOUNDARY.md` alongside the B1 reference.
  Existing §1–§8 text unchanged.
- `docs/path_c_thesis_alignment.md` — optional B2 addendum only
  if the thesis section calls it out; not required in Slice 1.

### Test-infrastructure

- `tests/test_path_c_import_topology.py` — add `src/correlator/`
  to `_PATH_C_ROOTS` (or equivalent). Positive/negative self-tests
  already exercise the scan.
- `tests/test_path_c_schema_frozen.py` — add frozen assertions
  for the three new schemas, update the assertion for bumped
  `SessionEventRecord`.
- `tests/fixtures/` — add fixture entries for the new schemas and
  a 1.2-shaped `SessionEventRecord` with
  `correlation_context=None`. Keep existing 1.1-shaped fixtures
  where they are explicitly version-scoped; otherwise regenerate
  with the new default.

### Explicitly NOT modified in Slice 1

- `src/event_loop_c.py` — the narrow integration point is
  **reserved for Slice 2**. Slice 1 does not wire the correlator
  into the orchestrator; the schemas land independent of runtime.
- `src/session/session_compare.py` — reserved for Slice 2.
  The optional `correlation_summary` block lands with the match
  function, not with the schema skeletons.
- `scripts/session_eval_harness.py`, `scripts/run_session.py` —
  no `--enable-correlator` flag in Slice 1. The flag lands with
  the Slice 2 wiring.

This mirrors the B1 pattern: Slice 1 is contracts + frozen tests
only; runtime + wiring arrives in Slice 2+.

---

## 3. Likely new files for B2 Slice 1

### 3.1 New subpackage: `src/correlator/`

Recommended minimum set:

- `src/correlator/__init__.py` — re-exports the public schema
  types (`CorrelationSignal`, `CorrelationContext`,
  `CorrelatorConfig`) and the closed Literals
  (`CORRELATOR_PATTERN_ID`, `CORRELATOR_MATCHED_CONDITION`).
- `src/correlator/correlator_schema.py`
  — `CorrelationSignal`, `CorrelationContext`,
    `CorrelatorConfig`, closed Literals, schema-version constant.
    **No match logic. No imports from `adaptive/`, `replan/`,
    `learning/`, `session/` (except the `AffectedEntityRef`
    type from `event_schema`).**
- `src/correlator/correlator_config.py`
  — `CorrelatorConfig` (if kept separate from schema), plus
    `MAX_CORRELATOR_WINDOW`, `KNOWN_CORRELATOR_PATTERN_IDS`,
    validation hooks. May be merged into `correlator_schema.py`
    if small (follow B1's `replan_config.py` split precedent).
- `src/correlator/correlator_patterns.py`
  — declaration-only: the closed tuple of `PATTERN_DECLARATIONS`
    enumerating `pattern_id`, required event types, the static
    zone↔warehouse topology table for P2, and the severity
    threshold constant for `SEVERITY_HIGH_CONCURRENCE`. **No
    match function in Slice 1.** (The match function is a
    Slice 2 deliverable that imports this declaration table.)

### 3.2 New tests: `tests/test_correlator_*.py`

Minimum set, matching the acceptance gates
(`docs/B2_CORRELATOR_BOUNDARY.md §10`):

- `tests/test_correlator_schema_frozen.py` — G1. Asserts
  `extra='forbid'`, closed-Literal membership, min-participant
  invariant, `schema_version` values. Mirrors
  `tests/test_replan_schema_frozen.py`.
- `tests/test_correlator_no_nl_truth.py` — G7. Source-scan of
  `src/correlator/` for the five forbidden NL field names. Mirrors
  `tests/test_replan_contract_no_nl_truth.py`.
- `tests/test_correlator_ast_scan_roots.py` — G12. Asserts
  `src/correlator/` is in the import-topology scan roots.
- `tests/test_correlator_reverse_import_forbidden.py` — G13.
  Asserts `src/adaptive/`, `src/replan/`, `src/policy_gate.py`,
  `src/execution_adapters.py`, `src/learning/`, `src/agents/` do
  not import from `src/correlator/`.
- `tests/test_session_event_record_schema_1_2.py` — explicit
  assertion that `SessionEventRecord._SESSION_EVENT_RECORD_SCHEMA_VERSION
  == "1.2"` and that default `correlation_context is None`.

Tests deferred to Slice 2 (match function lands then):

- `tests/test_correlator_window_determinism.py` — G2.
- `tests/test_correlator_observability_only.py` — G3, G4, G5
  (listed in the boundary doc's Slice 1 checklist; the
  *determinism* half lands with the match function — the
  *non-mutation* half can land in Slice 1 using a no-op
  correlator stub).
- `tests/test_correlator_evidence_chain.py` — G6.
- `tests/test_correlator_replay_byte_identical.py` — G8.
- `tests/test_correlator_determinism_stress.py` — G9.
- `tests/test_correlator_phase3_kpi_invariance.py` — G10.
- `tests/test_correlator_compare_report_stability.py` — G11.

Of the boundary-doc checklist, the minimum Slice 1 set is the
first four files plus `test_session_event_record_schema_1_2.py`.
The rest land with Slice 2's match function.

### 3.3 Files not needed in Slice 1

- No `src/correlator/correlator_engine.py` (match function) —
  deferred to Slice 2.
- No changes to `src/session/session_compare.py`.
- No changes to `scripts/*`.
- No new CLI surface, no new API route, no new RAG wiring.

---

## 4. Recommended layering

Clean, non-circular, additive:

```
         ┌─────────────────────────────────────────────┐
         │  Contract layer                             │
         │  src/correlator/correlator_schema.py        │
         │  src/correlator/correlator_config.py        │
         │  src/correlator/correlator_patterns.py      │
         │  (pydantic models + closed Literals +       │
         │   declaration table only, no behavior)      │
         └──────────────────────┬──────────────────────┘
                                │ (Slice 2 adds)
         ┌──────────────────────┴──────────────────────┐
         │  Match layer (pure) — Slice 2               │
         │  src/correlator/correlator_engine.py        │
         │  (pure function over a frozen record list   │
         │   + config → CorrelationContext)            │
         └──────────────────────┬──────────────────────┘
                                │ (Slice 2 adds)
         ┌──────────────────────┴──────────────────────┐
         │  Integration layer — Slice 2                │
         │  src/event_loop_c.py  (narrow post-record   │
         │  attach point using model_copy)             │
         │  src/session/session_compare.py             │
         │  (+ optional correlation_summary block)     │
         └──────────────────────┬──────────────────────┘
                                │
         ┌──────────────────────┴──────────────────────┐
         │  Tests                                      │
         │  tests/test_correlator_*.py                 │
         └─────────────────────────────────────────────┘
```

Import direction: always top-to-bottom. No upward import, no
cycle. In particular:

- `src/correlator/` does NOT import from `src/adaptive/`,
  `src/replan/`, `src/learning/`, `src/session/` (except the
  read-only use of `AffectedEntityRef` from
  `src/event_schema.py`, which is already the canonical reference
  for shared entities).
- `src/adaptive/`, `src/replan/`, `src/learning/`,
  `src/agents/`, `src/policy_gate.py`, `src/execution_adapters.py`
  do NOT import from `src/correlator/`. This is tested
  structurally (G13).

---

## 5. Preferred placement if a new correlator subpackage is created

**Preferred: new top-level subpackage `src/correlator/`.**

Rationale (mirrors B1's):

1. Matches the additive-subpackage pattern already used by
   `src/learning/`, `src/adaptive/`, `src/session/`,
   `src/outcome_persistence/`, `src/replan/` — consistent with
   `PATH_C_BOUNDARY.md` §1.7.
2. Adds a single new root to
   `tests/test_path_c_import_topology.py`, mirroring the B1
   precedent that added `src/replan/`.
3. Keeps compound-pattern semantics logically discoverable and
   prevents accidental mixing with adaptive-policy learning or
   replan trigger logic.

**Rejected alternatives:**

- Placing correlator inside `src/learning/` — misleading; the
  correlator is not memory, does not persist across sessions,
  does not feed agent prompts.
- Placing correlator inside `src/session/` — session layer is
  for overlay and artifacts, not detection; would tangle
  responsibilities.
- Placing correlator inside `src/adaptive/` — policy-only-
  learning-injection rule would be weakened; adaptive is the
  *policy* layer, not the *observation* layer.
- Putting correlator helpers directly into `src/event_loop_c.py`
  — violates the "narrow extension point" rule; makes the
  orchestrator non-trivially rewrite-prone.

---

## 6. Narrow extension point inside `event_loop_c.py` (Slice 2; not Slice 1)

A single change, when the B2 Slice 2 implementation PR lands:

```
# After the per-event SessionEventRecord has been fully assembled
# (Path B shadow embed + Path C overlay + B1 replan overlay),
# and ONLY if correlator is enabled:
#
# (pseudocode; NOT to be committed in Slice 1)
if correlator_config.enable_correlator:
    context = compute_correlation_context(
        finalized_records=tuple(session_records),  # includes the
                                                   # current record
        config=correlator_config,
    )
    session_records[-1] = session_records[-1].model_copy(
        update={"correlation_context": context}
    )
# else: correlation_context stays None (default)
```

With `enable_correlator=False`, this branch is a no-op and all
existing tests pass unchanged. No other line in `event_loop_c.py`
changes.

This pseudocode is **illustrative only**; it is NOT to be written
into the codebase in Slice 1.

---

## 7. Interfaces B2 depends on but must not modify

- `EventPayload` / `EventType` / `EventSeverity` / `AffectedEntityRef`
  (`src/event_schema.py`) — read-only reference types.
- `SessionEventRecord` (`src/session/session_schema.py`) — gains
  one optional field; shape is otherwise unchanged.
- `canonical_json(...)` (used by session save) — unchanged.
  Pydantic's model_dump will serialize the new optional field
  with `None` default preserved.

## 8. What does *not* need a file change in B2 Slice 1

- `app.py` — no FastAPI surface change.
- `src/api/*` — no route change.
- `src/llm_backend.py`, `src/llm_providers/*` — no new prompt.
- `src/retrieval.py`, `src/rag_setup.py` — correlator does not
  consult RAG.
- `src/supervisor.py` — supervision is orthogonal.
- `src/outcome_persistence/*` — persistence semantics unchanged.

---

## 9. Summary of open decisions before Slice 2

Matches `docs/B2_CORRELATOR_BOUNDARY.md §12` and
`docs/B2_CORRELATOR_CONTRACT_DRAFT.md §9`:

- ⟨O1⟩ `SessionEventRecord` version: 1.2 bump (default) vs stay
  at 1.1 with version nested inside `CorrelationContext`.
- ⟨O2⟩ Fourth pattern `CANCELLATION_AFTER_SPIKE`: ship in Slice 1
  vs defer (default: defer).
- ⟨O3⟩ Topology source for P2: static table (default) vs read
  from `TwinState` at detection time.
- ⟨O4⟩ `correlation_summary` compare-report block shape:
  per-pattern map (default) vs flat list.
- ⟨O5⟩ Harness flag ergonomics in Slice 2: minimal
  `--enable-correlator` (default) vs richer CLI.

None of these decisions is made in this doc. Each resolution is
an input to the subsequent "B2 Slice 1 PR" turn.
