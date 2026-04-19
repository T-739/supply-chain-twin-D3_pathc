# B1_REPLAN_BOUNDARY.md

Status: **B1 Slice 1 landed (contracts + frozen tests only). Runtime
logic deferred to Slice 2+.**
Authority: `Path_C_Roadmap_v2_1.docx`, `PATH_C_BOUNDARY.md`, `PATH_C_SCHEMA_REGISTRY.md`,
`B1-B5_Implementation_Roadmap_Report.docx`.

This document is the contract that governs any future B1 (Replan loop)
implementation PR. It does not itself introduce runtime behavior, and it
does not supersede `PATH_C_BOUNDARY.md`; it narrows scope further for B1.

The five decision points §12 D1–D5 are **fixed by the owner** as of
B1 Slice 1 — see §12 below for the locked values and their
structural consequences.

---

## 1. Purpose

Define the boundary within which the B1 *Replan loop* branch may later
be implemented, so that:

- Path C-min (Phases 0–3) remains fully intact and regression-clean.
- B1 code is strictly additive over the existing three-layer separation
  (Path B raw → Path C session overlay → Path C session artifact).
- B1 never becomes a vehicle for rewriting Path C-min, adaptive policy,
  agents, Research Core, or Path B contracts.
- A future reviewer can answer "is this PR inside B1 scope?" from this
  file alone, not from conversation history.

## 2. Why B1 is the next branch now

- Path C-min is the first closed cut. Its three-layer separation, dual
  truth references, metadata-mandatory execution path, KPI calculator,
  and thesis-aligned compare report are in place and regression-tested
  (`tests/test_phase0_baseline_regression_phase1.py`,
  `tests/test_path_c_vs_baseline_divergence.py`,
  `tests/test_replay_byte_identical.py`,
  `tests/test_determinism_stress.py`).
- B1 is the smallest useful extension that exercises the *temporal*
  dimension of calibrated supervision beyond a single decision per event:
  one bounded re-reasoning cycle after an execution attempt whose
  realized structured outcome materially deviates from an expected
  structured estimate.
- B2 (event correlator), B3 (cross-session cumulative memory), B4
  (agent-visible episodic memory), and B5 (React/frontend) are all
  larger-footprint or contract-sensitive branches. B1 is the branch
  that can be designed additively on top of the existing session overlay
  without opening any agent contract.

## 3. In-scope (for the future B1 implementation PR; NOT this turn)

B1 implementation will be allowed to:

1. Add a new Path C subpackage (preferred name: `src/replan/`) that is
   added to the Path-C AST-scan roots in
   `tests/test_path_c_import_topology.py`.
2. Introduce new pydantic schemas for:
   - an *expected structured outcome* reference (cost range, SLA
     preservation expectation), derived deterministically from
     `CostOutput.cost_estimates` (per locked D1 below). Natural-
     language governance fields are **not** a valid source.
   - a *replan trigger decision record* carrying the structured
     deviation measurement (absolute + relative cost; SLA flag);
   - a *replan attempt record* describing one re-reasoning cycle.
3. Extend `SessionEventRecord` *additively* (MINOR bump) with optional
   replan overlay fields with safe defaults. Any such bump must update
   `PATH_C_SCHEMA_REGISTRY.md` and the fixture set in the same PR.
4. Wrap `src/event_loop_c.py::_build_path_c_main_records` from the
   outside (via a new orchestration helper) *only if that is the only
   way to add bounded retry without invasive modification*. Preferred
   pattern is a pure function living in `src/replan/` that
   `event_loop_c` calls at a single, narrow extension point.
5. Extend the eval harness and KPI calculator *additively* to surface
   replan-aware KPIs (e.g. `replan_trigger_rate`,
   `replan_recovery_rate`) without changing the canonical sources for
   existing Phase-3 KPIs.
6. Add new tests under `tests/test_replan_*` covering contract freeze,
   trigger determinism, bounded-retry invariants, and replay byte
   identity.

## 4. Explicit out-of-scope

B1 MUST NOT, in its first implementation PR or any follow-up labelled
B1:

1. Change any field or semantic of `GovernanceOutput`, `_governance_meta`,
   `PolicyDecision`, `ExecutionOutcome`, `EventPayload`, or the Path B
   per-event record shape.
2. Modify any agent prompt, agent module, or agent output schema
   (`src/agents/*`).
3. Modify `evaluation.py`, `action_code_mapper.py`, or `data/cases/*.json`.
4. Collapse `GovernanceTruthRef` and `EffectiveDecisionRef` into a single
   effective truth. Dual-track stays dual-track.
5. Mutate `SessionEventRecord.baseline_event_result` in any way, at any
   time, for any reason.
6. Introduce a natural-language field as authoritative numerical truth
   for the replan trigger (see §8).
7. Cross into any of B2–B5 — no correlator, no cross-session memory,
   no agent-visible memory, no frontend. A B1 PR that incidentally
   touches those is out-of-scope.
8. Re-open Path C-min design decisions (bounded adjustment set,
   cold-start semantics, three-layer separation, adaptive-only policy
   learning injection). B1 lives *beside* the adaptive layer, not
   inside it.
9. Introduce unbounded or input-derived-unbounded retry. The retry cap
   is a compile-time constant (or a deterministic session-config
   integer), never data-dependent.
10. Introduce new wall-clock, `uuid4`, or `data/cases` access.

## 5. Preserved invariants (non-negotiable)

All invariants from `PATH_C_BOUNDARY.md` §1 stand unchanged under B1.
B1 additionally preserves:

- **Path B shadow integrity.** The Path B `run_event_loop` shadow in
  `src/event_loop_c.py` remains a *single-pass* run whose outputs are
  embedded verbatim as `baseline_event_result`. Replan cycles operate
  only on the Path C main-path state, never on the shadow run.
- **Dual-track rule.** `GovernanceTruthRef` and `EffectiveDecisionRef`
  remain the only two truth references per event. A replan cycle
  produces at most one *final* `EffectiveDecisionRef`; per-attempt
  intermediate state is carried in a separate replan-overlay structure,
  not by rewriting the primary truth references.
- **Policy-only learning injection.** Memory influences behavior
  exclusively via the adaptive policy gate. A replan cycle does NOT
  read memory mid-event, and does NOT append a per-attempt
  `MemoryRecord`. Memory write, as always, happens once per event and
  reflects only the **final** attempt. The trigger is a pure function
  of (expected structured estimate, realized structured outcome).
  Any future memory-aware replan variant is a *separate* branch.
- **Deterministic-first.** The trigger function is pure. The bounded
  retry count is a constant or a deterministic config integer. The
  digest pipeline in `src/session/digests.py` is extended — if at all —
  by appending new structured inputs in a fixed, documented order so
  that `session_id` remains a pure function of inputs.
- **Bounded action set.** The replan cycle does not expand the
  adjustment set and does not introduce `DOWNGRADE_*`. A replan may
  re-invoke the adaptive policy gate with an updated structured
  context, but it may not ask the gate to emit an adjustment outside
  `UPGRADE_ONE_LEVEL / NO_ADJUSTMENT / COLD_START_FALLBACK`.
- **Structural explainability.** Every replan trigger carries a
  structured `trigger_rule_id`, a structured `deviation_measurement`,
  and a pointer to the originating attempt — parallel to the
  adaptive layer's `rule_id` / `query_signature` / `memory_evidence`
  contract.

## 6. Allowed files to touch later (B1 PR allowlist)

The future B1 PR may *create* files under:

- `src/replan/` (new subpackage; expected members in
  `docs/B1_REPLAN_FILE_MAP.md`)
- `tests/test_replan_*.py`
- `tests/fixtures/replan_*` (if fixture-based snapshots are needed)

The future B1 PR may *additively* modify, but must not rewrite or
repurpose:

- `src/session/session_schema.py` — add optional replan fields with
  safe defaults (MINOR bump).
- `src/session/kpi_calculator.py` — add new KPI keys with
  zero-denominator-returns-None policy; existing keys unchanged.
- `src/session/session_compare.py` — extend `diverged_events` and/or
  add a sibling `replan_trace_summary` block. Existing fields unchanged.
- `PATH_C_SCHEMA_REGISTRY.md` — register new/bumped schemas.
- `tests/test_path_c_import_topology.py` — extend scan roots.
- `tests/test_path_c_schema_frozen.py` — add frozen assertions for the
  new schemas.
- `scripts/session_eval_harness.py` / `scripts/run_session.py` — add a
  `--enable-replan` flag; default OFF.
- `docs/path_c_thesis_alignment.md` — append a "B1 addendum" section.

The future B1 PR may *not* additively modify:

- `src/event_loop_c.py` in a way that changes the Phase 1/2 flow for
  `enable_replan=False`. Wrapping is allowed; default behavior change
  is not.
- `src/learning/episodic_memory.py` ownership rules. If a replan
  attempt needs to be remembered, the record goes into a sibling
  `ReplanAttemptRecord`, not a mutated `MemoryRecord`.
- `src/adaptive/*` — no new `adjustment_type` values, no rule-registry
  semantic change.

## 7. Forbidden files / forbidden modifications

B1 MUST NOT touch, in any PR:

- `src/agents/**` — any agent, any agent output schema.
- `src/policy_gate.py` — `PolicyDecision` and `decide_policy` stay
  frozen.
- `src/outcome_schema.py` — `ExecutionOutcome` stays frozen. In
  particular, do not add an `expected_cost_*` field to
  `ExecutionOutcome`.
- `src/event_schema.py` — `EventPayload` and `EventType` stay frozen.
- `src/evaluation.py`, `src/action_code_mapper.py` — Research Core.
- `data/cases/*.json` — Research Core data.
- `src/graph.py` node wiring — the LangGraph flow stays frozen.
- `src/execution_adapters.py` — no new adapter, no new branch in
  `execute_action`; replan re-invokes the same dispatcher with updated
  structured inputs.
- `src/event_loop.py` (Path B core).

Forbidden modification classes:

- Any change that would cause `BASELINE_STATIC` mode to produce a byte
  non-equal `SessionArtifact` for a given seed/event stream.
- Any change that would cause `PATH_C_COLD` / `PATH_C_WARM` with
  `enable_replan=False` to diverge from current behavior.
- Any change to the canonical JSON byte layout of Phase-3 compare
  reports under the current CLI defaults.

## 8. Replan-specific risks (and their mitigations)

| # | Risk | Mitigation (mandatory for B1 implementation PR) |
|---|---|---|
| R1 | Using `GovernanceOutput.cost_summary`, `confidence_note`, or `rationale_trace` as numeric trigger truth | Expected cost/SLA must be produced by a new deterministic estimator that reads only structured fields (`TwinState`, the operational identity in `_governance_meta`, `ExecutionOutcome`). Test asserts the trigger function never imports or strings-parses those three fields. |
| R2 | Unbounded or data-dependent retry | Maximum attempts is a compile-time constant (suggested: `MAX_REPLAN_ATTEMPTS = 1`, matching Roadmap wording "one bounded re-reasoning cycle"). Exceeding the cap is a hard error, not a soft degrade. |
| R3 | `baseline_event_result` mutation | Replan operates on a separate Path C live state only; the shadow run is untouched. AST scan is extended if needed to forbid `baseline_event_result` as an assignment target anywhere in `src/replan/`. |
| R4 | Collapse of dual-track truth | `GovernanceTruthRef` and `EffectiveDecisionRef` builders remain the only two truth reference constructors. Replan attempt records live on a new optional field and cannot substitute for them. |
| R5 | Nondeterminism via wall-clock in retry | Replan inherits `event.timestamp`. It does NOT call `datetime.now()`. The AST scan already enforces this for Path C roots; `src/replan/` must be inside those roots. |
| R6 | Learning-injection creep | The trigger function does not read `EpisodicMemory`. If a future variant does, it is a new branch label (not B1), with its own boundary doc. |
| R7 | KPI denominator drift | New KPIs add new denominators; existing Phase-3 KPIs (`sla_preservation_rate`, `avg_cost_per_event`, `calibrated_autonomy_score`, `human_escalation_rate`, `auto_execute_rate`, `known_outcome_coverage`) keep their exact current canonical source and denominator semantics. |
| R8 | Replay byte drift from new overlay fields | `SessionEventRecord` MINOR bump uses safe defaults (`replan_trace=None` or `replan_trace=[]`). `test_replay_byte_identical` is extended to cover both enable_replan=True and =False sessions. |
| R9 | Forbidden-token contamination | The operational identity used by the expected-outcome estimator re-enters `execute_action` via the same `governance_meta` path, which already rejects supervision-/evaluation-layer tokens. Replan never invents a new operational identifier. |
| R10 | B1 drifts into B2 correlator territory | The trigger is local to a single event. No cross-event state. A deviation computed against peer events is out-of-scope for B1 and belongs to B2. |

## 9. Rollback rules

If the first B1 implementation PR, or any follow-up, causes any of the
following, it MUST be reverted (not patched forward):

- A Path C-min test regresses: any test currently passing on `main` in
  `tests/test_phase0_baseline_regression_phase1.py`,
  `tests/test_path_c_vs_baseline_divergence.py`,
  `tests/test_replay_byte_identical.py`,
  `tests/test_determinism_stress.py`,
  `tests/test_kpi_calculator.py`,
  `tests/test_session_compare.py`,
  `tests/test_adaptive_audit_trail.py`,
  `tests/test_cold_start_behavior.py`,
  `tests/test_governance_meta_preflight.py`,
  `tests/test_execution_metadata_mandatory.py`.
- `BASELINE_STATIC` session artifact bytes change for any seed that
  passed before.
- `PATH_C_COLD` / `PATH_C_WARM` session artifact bytes change for any
  seed that passed before, when `enable_replan=False`.
- Canonical JSON of the existing Phase-3 compare report changes under
  default harness flags.
- The AST import-topology scan grows a new allowed import or a new
  exception. (New forbidden imports are permitted; weakening the scan
  is not.)

If a partial B1 landing needs to be rolled back, roll back the entire
B1 slice; do not leave half-implemented replan surfaces on `main`.

## 10. Acceptance gates for future implementation

The B1 implementation PR will be considered acceptable only if ALL of
the following hold simultaneously:

- **G1 Contracts first.** New pydantic models land as schema skeletons
  with frozen tests (in the spirit of Phase 0), before any runtime
  logic. Matching entries exist in `PATH_C_SCHEMA_REGISTRY.md`.
- **G2 Trigger purity.** `src/replan/replan_trigger.py` (or whichever
  module owns the trigger decision) is a pure function of structured
  inputs: `TwinState` reference, structured `ExecutionOutcome`,
  structured expected-outcome reference, config. No LLM call, no I/O,
  no memory read.
- **G3 Forbidden-truth assertion.** A test imports the trigger module
  and asserts that at no source line does it reference
  `cost_summary`, `confidence_note`, `rationale_trace`,
  `situational_explanation`, or `alternative_actions` (the five
  natural-language fields of `GovernanceOutput`).
- **G4 Bounded retry.** A test drives a synthetic deviation and
  asserts the attempt count strictly satisfies
  `attempts <= MAX_REPLAN_ATTEMPTS`. A separate test asserts the cap
  is a module constant, not read from event/governance payloads.
- **G5 Shadow untouched.** A test compares Path B shadow bytes before
  and after a replan-enabled run on the same inputs and asserts
  byte-equality.
- **G6 Dual-track preserved.** A test constructs an event that triggers
  replan and asserts that `GovernanceTruthRef` reflects the *original*
  governance identity and `EffectiveDecisionRef` reflects the *final*
  replan outcome, with both present and distinct when the replan
  changed behavior.
- **G7 Replay byte identity.** `test_replay_byte_identical` passes for
  both `enable_replan=False` and `enable_replan=True` sessions.
- **G8 Determinism stress.** A fresh-process rerun of a
  replan-enabled session produces byte-identical
  `SessionArtifact.json`.
- **G9 Phase-3 KPI invariance.** For `enable_replan=False`, every
  existing KPI value matches pre-B1 `main` to the 4-decimal
  serialization boundary.
- **G10 Compare report surface stability.** For `enable_replan=False`,
  the Phase-3 `compare_report.json` is byte-identical to pre-B1
  `main`. New fields appear only when replan is enabled.
- **G11 AST scan covers new module.** `src/replan/` is in the
  Path C AST scan roots. The scan's positive/negative self-tests pass.
- **G12 Honesty rule.** If enabling replan degrades the thesis claim
  under evaluation, the thesis report reports it honestly. There is
  no code branch that suppresses a negative result.

No gate may be waived. A single failing gate blocks the B1 PR.

---

## 11. Non-goals for B1 (reminder)

- Memory-informed replan (a future branch, not B1).
- Multi-attempt replan beyond the bounded cap.
- Cross-event correlation (B2).
- Agent re-prompting (would cross into agent contracts).
- UI visualization of replan traces (B5).

## 12. Owner-fixed decisions (locked; do not renegotiate in B1)

These were deferred decisions in the original boundary draft. They
were locked by the owner before B1 Slice 1. Structural consequences
are enforced by tests and the schema registry.

- **D1 — Expected-cost-range provenance: `cost_output_derived_overlay`.**
  The expected-cost range is produced by a deterministic overlay
  projection over `CostOutput.cost_estimates` (the Cost Agent's
  structured output), keyed by the governance identity
  (`recommended_candidate_type` / `recommended_candidate_id`).
  It is NEVER parsed from `GovernanceOutput.cost_summary`,
  `confidence_note`, `rationale_trace`, `situational_explanation`,
  or the `alternative_actions` descriptions. The closed Literal
  `EXPECTED_COST_RANGE_SOURCE_LITERAL = "cost_output_derived_overlay"`
  structurally enforces this. The guard
  `tests/test_replan_contract_no_nl_truth.py` scans `src/replan/`
  source for the five forbidden NL field names.

- **D2 — Placement A: additive on `SessionEventRecord`.**
  Replan trace lives inline on the primary `SessionEventRecord` via
  two optional fields (`replan_trace`, `replan_triggers`), not in a
  sibling artifact. `SessionEventRecord` is MINOR-bumped to 1.1.
  Other schemas remain at 1.0. When replan is disabled, both fields
  are `None` — consumers observe no behavioral change.

- **D3 — Trigger carries BOTH absolute and relative cost deviation,
  SLA separately.** `ReplanConfig` exposes
  `cost_deviation_abs_threshold: float` and
  `cost_deviation_rel_threshold: float ∈ [0.0, 1.0]`, plus an
  independent `sla_deviation_enabled: bool`. The trigger *decision*
  function is NOT implemented in Slice 1 — only the config shape
  and the `ReplanTriggerType` closed set are frozen.

- **D4 — `MAX_REPLAN_ATTEMPTS = 1`. Hard cap.**
  `ReplanConfig.__post_init__` rejects any
  `max_replan_attempts > MAX_REPLAN_ATTEMPTS` at construction time,
  so the cap is enforceable both at the module-constant layer and
  at the config-instance layer.

- **D5 — Second cycle is a FULL reasoning cycle.**
  B1's replan second attempt, when wired in Slice 2+, will re-invoke
  operations → cost → governance → adaptive policy gate → preflight
  → `execute_action` with updated structured context. It does NOT
  bypass any of those layers. The per-attempt route / action /
  execution_status domains on `ReplanAttemptRecord` therefore mirror
  the full operational-outcome Literals from `session_schema.py`
  exactly.

These decisions are not renegotiable as part of any B1 slice. A
future design that needs to relax them (for example, an additional
expected-cost provenance source) is a separate, owner-approved
MINOR bump of the relevant Literal and registry entry, not a B1
in-scope change.

---

## 13. B1 Slice 1 delivery checklist (satisfied on `main`)

This section records what Slice 1 landed, so a future reviewer can
check the base before reviewing Slice 2+.

- [x] `src/replan/__init__.py`, `replan_schema.py`, `replan_config.py`.
- [x] `SessionEventRecord` 1.0 → 1.1 (additive,
      `replan_trace` / `replan_triggers` optional None-defaulted).
- [x] `PATH_C_SCHEMA_REGISTRY.md` updated: `ExpectedOutcomeRef`,
      `ReplanTriggerRecord`, `ReplanAttemptRecord`, `ReplanConfig`
      registered at 1.0; `SessionEventRecord` bumped to 1.1.
- [x] `tests/fixtures/path_c_schema_samples_1_0.json` updated with
      new schema samples and the 1.1 `SessionEventRecord`.
- [x] `tests/test_path_c_schema_frozen.py` extended (new classes,
      per-class expected schema_version).
- [x] `tests/test_path_c_import_topology.py` extended with
      `src/replan/`.
- [x] `tests/test_replan_schema_frozen.py` added (D1 closed Literal,
      D3 config invariants, D4 hard cap, closed literal sets on
      `ReplanAttemptRecord` fields, `extra='forbid'` enforcement).
- [x] `tests/test_replan_contract_no_nl_truth.py` added (D1
      structural guard — AST scan of `src/replan/`).
- [x] Full suite (`pytest -q`) green on `main`.

Slice 2+ is free to wire the estimator, trigger, and orchestration;
it is NOT free to re-open D1–D5.
