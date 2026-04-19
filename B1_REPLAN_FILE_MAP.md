# B1_REPLAN_FILE_MAP.md

Status: **Slice 1 landed.** D1–D5 (see `B1_REPLAN_BOUNDARY.md §12`)
are LOCKED. The file map below partitions the repo for the remaining
B1 slices (estimator / trigger / orchestration).
Authority: `docs/B1_REPLAN_BOUNDARY.md`,
`docs/B1_REPLAN_CONTRACT_DRAFT.md`, `PATH_C_BOUNDARY.md`.

This document maps B1 (Replan loop) against the current repo layout so
a future implementation PR can proceed without surprises. Every entry
is grounded in the state of the repo at the time of writing.

Slice 1 delta (already on `main`):
- `src/replan/__init__.py`, `replan_schema.py`, `replan_config.py` —
  created.
- `src/session/session_schema.py` — `SessionEventRecord` MINOR bump
  1.0 → 1.1, optional `replan_trace` / `replan_triggers` with
  `None` defaults.
- `PATH_C_SCHEMA_REGISTRY.md` — three B1 schemas + `ReplanConfig`
  registered at 1.0; `SessionEventRecord` at 1.1.
- `tests/test_path_c_import_topology.py` — `src/replan/` added to
  scan roots.
- `tests/test_path_c_schema_frozen.py` + fixture — extended for the
  new schemas and the `SessionEventRecord` 1.1 defaults.
- `tests/test_replan_schema_frozen.py`,
  `tests/test_replan_contract_no_nl_truth.py` — added.

---

## 1. Files expected to stay untouched (frozen under B1)

These files MUST NOT be modified by any PR labelled B1.

### Path B runtime core (frozen Tier 1)

- `src/event_schema.py` — `EventPayload`, `EventType`.
- `src/outcome_schema.py` — `ExecutionOutcome` (8 fields, 4-action Literal).
- `src/policy_gate.py` — `PolicyDecision`, `decide_policy`.
- `src/agents/governance_agent.py` — `GovernanceOutput`, 8-field schema.
- `src/agents/cost_agent.py`, `src/agents/operations_agent.py` — agents.
- `src/execution_adapters.py` — four adapters + `execute_action` dispatcher.
  (The `require_metadata=True` contract stays exactly as-is; replan
  re-invokes the same dispatcher with updated structured inputs.)
- `src/twin_state.py` — `TwinState`, mutation primitives.
- `src/event_loop.py` — Path B core.
- `src/graph.py` — LangGraph wiring.
- `src/outcome_store.py` — `OutcomeStore.summary()` stays stable.

### Research Core (frozen)

- `src/evaluation.py`
- `src/action_code_mapper.py`
- `data/cases/*.json`

### Path C-min adaptive / memory / preflight

- `src/adaptive/adaptive_policy_gate.py` — `decide_policy_adaptive` stays
  as-is; replan may re-invoke it but must not modify it.
- `src/adaptive/adaptive_policy_config.py` — `DEFAULT_RULES`,
  `KNOWN_RULE_IDS`, `AdaptivePolicyGateConfig` unchanged.
- `src/adaptive/adaptive_schema.py` — `AdaptivePolicyAdjustment`,
  `AdjustmentRuleSpec`, adjustment Literal unchanged.
- `src/adaptive/cold_start.py` — unchanged.
- `src/adaptive/preflight.py` — unchanged.
- `src/learning/memory_schema.py` — `MemoryRecord`, `MemoryQuery`,
  `MemorySummary` unchanged.
- `src/learning/memory_summarizer.py` — unchanged.
- `src/learning/episodic_memory.py` — append-only semantics unchanged;
  no per-attempt records.

### Path C-min session core

- `src/session/digests.py` — digest functions stay as-is. New digest
  inputs (if any) are added by *appending* to the existing canonical
  config dict, not by redefining the hash.
- `src/session/session_manager.py` — save/load/replay unchanged unless
  a new sibling artifact is chosen for replan trace (currently not
  recommended; see Placement A).

### Tests that must continue to pass byte-for-byte

- `tests/test_phase0_baseline_regression_phase1.py`
- `tests/test_path_c_vs_baseline_divergence.py`
- `tests/test_replay_byte_identical.py` (additive new cases allowed)
- `tests/test_determinism_stress.py` (additive new cases allowed)
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

---

## 2. Files extendable additively under B1

### Session overlay (MINOR bumps only)

- `src/session/session_schema.py` — add optional fields:
  - `SessionEventRecord.replan_trace: Optional[list[ReplanAttemptRecord]] = None`
  - `SessionEventRecord.replan_triggers: Optional[list[ReplanTriggerRecord]] = None`
  - Optional new `SessionKPIs` fields with `None`/`0` defaults.
- `src/session/kpi_calculator.py` — append replan-aware KPIs to
  `PHASE_KPI_KEYS`. Keep `None`-on-zero-denominator rule. Do not
  retouch any existing KPI's canonical source.
- `src/session/session_compare.py` — optional sibling block
  `replan_trace_summary`. Existing `kpi_matrix`, `deltas`,
  `diverged_events`, `thesis_claim_support` unchanged in shape;
  values may include new KPI keys only when replan is enabled.

### Orchestration boundary (narrow extension point)

- `src/event_loop_c.py` — one narrow extension point where the
  orchestrator consults `src/replan/` after the first execution
  attempt. The change must be a single-line delegation when
  `enable_replan=False` (returning today's record unchanged) and only
  activates extra work when `enable_replan=True`. **No refactor of
  `_build_path_c_main_records` beyond this delegation.**

### Eval / scripts

- `scripts/session_eval_harness.py` — add `--enable-replan` flag
  (default OFF). Only when enabled are replan-aware KPIs surfaced.
- `scripts/run_session.py` — same flag pass-through.
- `scripts/generate_thesis_report.py` — optional addendum rendering
  when replan block is present in the compare report.

### Registry / boundary docs

- `PATH_C_SCHEMA_REGISTRY.md` — register new schemas and bump
  `SessionEventRecord` / `SessionKPIs` to 1.1.
- `PATH_C_BOUNDARY.md` — append a B1 cross-reference pointing at
  `docs/B1_REPLAN_BOUNDARY.md`. Existing §1–§8 text unchanged.
- `docs/path_c_thesis_alignment.md` — optional B1 addendum.

### Test-infrastructure

- `tests/test_path_c_import_topology.py` — add `src/replan/` to
  `_PATH_C_ROOTS` (or equivalent). The positive/negative self-tests
  already exercise the scan.
- `tests/test_path_c_schema_frozen.py` — add frozen assertions for
  new schemas; update assertions for bumped `SessionEventRecord` /
  `SessionKPIs`.
- `tests/fixtures/` — new/updated fixture files matching the
  schema version bumps. Keep old fixtures for the unbumped shapes
  where relevant.

---

## 3. Likely new files for B1

Grouped by layer. Naming is a *suggestion*; finalized in the
implementation PR.

### 3.1 New subpackage: `src/replan/`

Recommended minimum set:

- `src/replan/__init__.py`
- `src/replan/replan_schema.py`
  — `ExpectedOutcomeRef`, `ReplanTriggerRecord`, `ReplanAttemptRecord`,
    `ReplanTriggerType` Literal, schema-version constant.
- `src/replan/expected_outcome.py`
  — `estimate_expected_outcome(state, governance_meta, config) ->
    ExpectedOutcomeRef`. Pure, deterministic, reads only structured
    fields. May share numeric helpers with `execution_adapters.py`
    via a new tiny pure-helper module if needed (see §7).
- `src/replan/replan_trigger.py`
  — `decide_replan(...) -> ReplanTriggerRecord`. Pure function.
    Imports only from: `replan_schema`, `execution_adapters`-typed
    helpers (*read-only*), `adaptive.adaptive_schema` (Literal
    imports only), `session.session_schema` (`EffectiveDecisionRef`
    read-only). Does NOT import `episodic_memory` /
    `memory_summarizer` / `memory_schema.MemorySummary`.
- `src/replan/replan_orchestrator.py`
  — `run_replan_cycle(event, state, governance_output, governance_meta,
    first_attempt, memory, adaptive_config, config) ->
    (final_state, final_execution_status, final_outcome,
    list[ReplanAttemptRecord], list[ReplanTriggerRecord])`.
    Wraps exactly one bounded retry. Does NOT touch
    `baseline_event_result` (by construction — it never receives it).
- `src/replan/replan_config.py`
  — `ReplanConfig` dataclass frozen with `enable_replan: bool`,
    `max_replan_attempts: Final[int] = 1`, `cost_deviation_abs`,
    `cost_deviation_rel`, `trigger_rules`, `sla_deviation_enabled`.
    `KNOWN_TRIGGER_RULE_IDS` frozenset lives here.

### 3.2 New tests: `tests/test_replan_*.py`

Minimum set, matching the acceptance gates (`docs/B1_REPLAN_BOUNDARY.md` §10):

- `tests/test_replan_schema_frozen.py` — G1.
- `tests/test_replan_trigger_purity.py` — G2 (function-level purity).
- `tests/test_replan_no_nl_fields.py` — G3 (source-scan for banned
  natural-language field names).
- `tests/test_replan_bounded_retry.py` — G4.
- `tests/test_replan_path_b_shadow_untouched.py` — G5.
- `tests/test_replan_dual_track_preserved.py` — G6.
- `tests/test_replan_replay_byte_identical.py` — G7 (extends
  `test_replay_byte_identical` coverage).
- `tests/test_replan_determinism_stress.py` — G8 (extends
  `test_determinism_stress` coverage).
- `tests/test_replan_phase3_kpi_invariance.py` — G9, G10.
- `tests/test_replan_ast_scan_roots.py` — G11 (asserts `src/replan/`
  is in the scan roots list).
- `tests/test_replan_audit_trail.py` — parallel to
  `tests/test_adaptive_audit_trail.py`: fired
  `trigger_rule_id` ∈ `KNOWN_TRIGGER_RULE_IDS`.

### 3.3 Optional supporting files (only if proven needed)

- `src/replan/numeric_helpers.py` — pure, if the expected-outcome
  estimator needs to reuse (not duplicate) cost/SLA computations
  currently inside `execution_adapters.py`. If it is cleaner to let
  the estimator re-derive from `TwinState` without a shared helper,
  skip this file.

---

## 4. Recommended layering

Clean, non-circular, additive:

```
         ┌─────────────────────────────────────────────┐
         │  Contract layer                             │
         │  src/replan/replan_schema.py                │
         │  (pydantic models only, no behavior)        │
         └──────────────────────┬──────────────────────┘
                                │
         ┌──────────────────────┴──────────────────────┐
         │  Trigger layer (pure)                       │
         │  src/replan/replan_trigger.py               │
         │  src/replan/expected_outcome.py             │
         │  src/replan/replan_config.py                │
         │  (pure functions; no I/O; no LLM; no mem)   │
         └──────────────────────┬──────────────────────┘
                                │
         ┌──────────────────────┴──────────────────────┐
         │  Orchestration wrapper layer                │
         │  src/replan/replan_orchestrator.py          │
         │  (bounded retry; re-invokes existing        │
         │   adaptive gate + execute_action)           │
         └──────────────────────┬──────────────────────┘
                                │
         ┌──────────────────────┴──────────────────────┐
         │  Session overlay / reporting layer          │
         │  src/session/session_schema.py   (+fields)  │
         │  src/session/kpi_calculator.py   (+KPIs)    │
         │  src/session/session_compare.py  (+block)   │
         └──────────────────────┬──────────────────────┘
                                │
         ┌──────────────────────┴──────────────────────┐
         │  Tests                                      │
         │  tests/test_replan_*.py                     │
         └─────────────────────────────────────────────┘
```

Import direction: always top-to-bottom in this diagram. No upward
import, no cycle. The orchestrator layer is the *only* layer that
talks to `event_loop_c.py`; the contract/trigger layers remain
event_loop-agnostic so they stay trivially testable in isolation.

---

## 5. Preferred placement if a new replan subpackage is created

**Preferred: new top-level subpackage `src/replan/`.**

Rationale:

1. Matches the additive-subpackage pattern already used by
   `src/learning/`, `src/adaptive/`, `src/session/`,
   `src/outcome_persistence/` — consistent with
   `PATH_C_BOUNDARY.md` §1.7 ("Path C appears as new subpackages").
2. Adds a single new root to
   `tests/test_path_c_import_topology.py`, mirroring the Phase 1
   widening that added `outcome_persistence` and `event_loop_c.py`.
3. Keeps the trigger / orchestrator logically discoverable and
   prevents accidental mixing with adaptive-policy learning injection.

**Rejected alternatives:**

- Placing replan inside `src/adaptive/` — violates the
  policy-only-learning-injection separation; `src/adaptive/` is the
  home of adaptive *policy*, not retry orchestration.
- Placing replan inside `src/session/` — session layer is for overlay
  and artifacts, not for execution orchestration; would tangle
  responsibilities.
- Placing replan inside `src/learning/` — memory is not consulted by
  B1's trigger; co-location would mislead future readers.
- Putting replan helpers directly into `src/event_loop_c.py` —
  violates the "narrow extension point" rule; makes the orchestrator
  non-trivially rewrite-prone.

---

## 6. Narrow extension point inside `event_loop_c.py` (future; not this turn)

A single change, when the B1 implementation PR lands:

```
# After: execution_status, outcome, path_c_state, preflight_note = (
#   _route_and_execute_path_c(...)
# )
# ADD (pseudocode, not to be committed in this turn):
if replan_config.enable_replan:
    (path_c_state, execution_status, outcome,
     replan_attempts, replan_triggers) = run_replan_cycle(
        event=event,
        state=path_c_state,
        governance_output=governance_output,
        governance_meta=governance_meta,
        first_attempt_status=execution_status,
        first_attempt_outcome=outcome,
        memory=memory,
        adaptive_config=adaptive_config,
        replan_config=replan_config,
    )
else:
    replan_attempts = None
    replan_triggers = None
```

With `enable_replan=False`, this branch is a no-op and all existing
tests pass unchanged. No other line in `event_loop_c.py` changes.

This pseudocode is **illustrative only**; it is NOT to be written into
the codebase in this boundary-setup turn.

---

## 7. Interfaces B1 depends on but must not modify

- `execute_action(governance_output, state, *, event_id, governance_meta,
  timestamp, require_metadata=True)` — called as-is on a replan
  attempt.
- `decide_policy_adaptive(governance_output, event_context, memory,
  config)` — called as-is on a replan attempt (⟨D5⟩ pending).
- `validate_governance_meta(governance_meta)` — called as-is inside
  the replan orchestrator's per-attempt preflight.
- `EpisodicMemory.append(record)` — called exactly once per event
  (for the final attempt), unchanged from Phase 1/2 semantics.
- `canonical_json(...)` — used by the session save path unchanged.

---

## 8. What does *not* need a file change in B1

- `app.py` — no FastAPI surface change is required by B1 itself.
- `src/api/*` — no route change.
- `src/llm_backend.py`, `src/llm_providers/*` — no new prompt.
- `src/retrieval.py`, `src/rag_setup.py` — replan does not consult RAG.
- `src/supervisor.py` — supervision layer is orthogonal to the
  operational replan loop.

---

## 9. Summary of open decisions that gate the first B1 code PR

Matches `docs/B1_REPLAN_BOUNDARY.md` §12 and
`docs/B1_REPLAN_CONTRACT_DRAFT.md` §7:

- ⟨D1⟩ Expected-cost source: deterministic estimator vs
  `_governance_meta` extension vs overlay-only.
- ⟨D2⟩ Replan trace placement: `SessionEventRecord` MINOR bump vs
  sibling artifact.
- ⟨D3⟩ Cost deviation granularity: absolute, relative, or both.
- ⟨D4⟩ `MAX_REPLAN_ATTEMPTS` value (Roadmap reads as 1).
- ⟨D5⟩ Replan re-invocation target: adaptive policy gate + executor,
  or executor alone.

None of these decisions is made in this doc. Each resolution is an
input to the subsequent "B1 Slice 1: contract models + frozen tests"
turn.
