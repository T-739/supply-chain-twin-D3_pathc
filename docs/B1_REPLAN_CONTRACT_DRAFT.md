# B1_REPLAN_CONTRACT_DRAFT.md

Status: **Slice 1 landed. Decisions D1–D5 in §7 are LOCKED. Runtime
logic for the estimator, trigger, and orchestration is deferred to
Slice 2+.**
Authority: `docs/B1_REPLAN_BOUNDARY.md`, `PATH_C_BOUNDARY.md`,
`PATH_C_SCHEMA_REGISTRY.md`.

This document originally enumerated candidate designs for the
structured contracts B1 would require. As of B1 Slice 1, the
owner-fixed decisions are:

- **D1** `expected_cost_range` is a `cost_output_derived_overlay` —
  produced by a deterministic projection over
  `CostOutput.cost_estimates` (the Cost Agent's structured output),
  NOT from TwinState, NOT from `_governance_meta`, and NEVER from
  natural-language governance fields. This is the ONLY admitted
  `range_source`; the closed Literal
  `EXPECTED_COST_RANGE_SOURCE_LITERAL` enforces it structurally.
- **D2** Placement A — `SessionEventRecord` gains optional
  `replan_trace` and `replan_triggers` fields with `None` defaults.
  MINOR bump 1.0 → 1.1. No sibling artifact.
- **D3** Both absolute and relative cost-deviation thresholds are
  carried on `ReplanConfig`, plus an independent
  `sla_deviation_enabled` gate. Trigger *decision* logic is NOT in
  Slice 1.
- **D4** `MAX_REPLAN_ATTEMPTS = 1`, hard cap, enforced both as a
  module constant and via `ReplanConfig.__post_init__`.
- **D5** The second cycle is a **full reasoning cycle**
  (operations → cost → governance → adaptive policy gate →
  preflight → `execute_action`). Memory stays **final-attempt-only**;
  no per-attempt `MemoryRecord`; no mid-event memory read.

Historical alternative analysis is preserved below for audit; the
option tables are no longer live design surface. Treat this file as
**read-only history** from here on — schema truth lives in
`src/replan/replan_schema.py` and `PATH_C_SCHEMA_REGISTRY.md`.

---

## 1. `expected_cost_range` — candidate design

### 1.1 Why this has to exist as a structured value

The replan trigger compares an **expected** structured outcome to the
**realized** structured outcome. Today the only candidates in the
codebase for "expected" are:

- `GovernanceOutput.cost_summary` — **string**, human-readable
  (`src/agents/governance_agent.py:77`). Explicitly forbidden as
  numeric truth (see §4).
- `GovernanceOutput.confidence_note`, `rationale_trace`,
  `situational_explanation`, `alternative_actions[*].description` —
  all natural language. Forbidden.
- `ExecutionOutcome.cost_incurred` — realized, not expected.
- `ExecutionOutcome.sla_impact` — realized, not expected.
- `_governance_meta` — currently carries operational identity
  (`recommended_candidate_type`, `recommended_candidate_id`), not a
  cost range. See `src/adaptive/preflight.py`.

None of the existing structured fields carries an expected numeric
range. B1 must introduce one, without extending any frozen Path B
contract.

### 1.2 Candidate sources (⟨D1⟩ — **LOCKED: cost_output-derived overlay**)

> **Locked.** The resolved D1 source is a deterministic projection
> over `CostOutput.cost_estimates` (the Cost Agent's structured
> output) keyed by the governance operational identity. Options A,
> B, C below are retained for audit only and are no longer admissible
> B1 designs. In particular Option A (TwinState-based estimator) is
> **NOT** the chosen source — the estimator's input surface is the
> Cost Agent's already-structured output, not TwinState.

**Option A — Deterministic estimator over TwinState + operational identity** (historical; NOT selected)

A new pure function, e.g. `src/replan/expected_outcome.py::estimate_expected_outcome(state, governance_meta) -> ExpectedOutcomeRef`,
computes the expected cost range and SLA preservation flag from:

- `TwinState` at the moment governance is consulted (carrier costs,
  inventory, zone SLA deadline, planned ETA).
- `governance_meta.recommended_candidate_type` (operational identity,
  one of `EXPEDITE / TRANSFER / COMPENSATE / NO_ACTION`).
- `governance_meta.recommended_candidate_id` (carrier / warehouse
  target hint where applicable).

Pros: no Path B contract change; matches the existing pattern in
`src/execution_adapters.py` (`_pick_alternate_carrier`,
`_build_sla_impact`); deterministic by construction; lives entirely
inside the new `src/replan/` subpackage.

Cons: duplicates a small amount of logic already present inside the
adapters. Mitigation: share a pure helper module, do NOT share
mutation code.

**Option B — Extend `_governance_meta` with an expected-cost block**

Add a structured block (e.g. `_governance_meta["expected_outcome"]`
with numeric fields) produced by the governance agent.

Pros: governance agent is the most natural authority on "what I
expect this to do".

Cons: `_governance_meta` is listed in `PATH_C_BOUNDARY.md` §2 under
Tier 1 frozen contracts (3 fields). Extending it is a frozen-contract
bump, touches an agent, and re-opens a Path C-min design decision.
Violates B1 boundary §4.1 and §7.

**Option C — Carry expected values on a new sibling overlay field only,
filled from the deterministic estimator** (preferred in combination
with Option A)

Expected values land only on the B1 overlay, never inside
`GovernanceOutput` or `_governance_meta`.

### 1.3 Draft shape (non-final)

```
class ExpectedOutcomeRef(BaseModel):
    # Cost expectation as a closed range. Both endpoints required.
    expected_cost_min: float            # >= 0
    expected_cost_max: float            # >= expected_cost_min
    # Boolean SLA preservation expectation (matches sla_impact.preserved domain).
    expected_sla_preserved: bool
    # Provenance for audit: who/what produced this estimate.
    estimator_id: str                   # e.g. "replan_expected_v1"
    estimator_signature: str            # pure digest of structured inputs
    schema_version: str = "1.0"
```

Determinism: `(cost_output, governance_meta, replan_config)` → same
`ExpectedOutcomeRef` byte-for-byte. The landed estimator
(`src/replan/expected_outcome.py::estimate_expected_outcome`) derives
the expected cost range from the Cost Agent's structured
`cost_output` entries, keyed by the governance operational identity
(`_governance_meta.recommended_candidate_id` →
`CandidateCostEstimate.candidate_id` structural match). TwinState is
not a direct input to the estimator. No rounding inside arithmetic;
rounding only at the serialization boundary, consistent with
`PATH_C_BOUNDARY.md` §5.

### 1.4 What `expected_cost_range` will be compared against

The realized structured outcome is `ExecutionOutcome.cost_incurred`
(float, `src/outcome_schema.py:54`) and `sla_impact.preserved` (bool,
produced by `_build_sla_impact`, `src/execution_adapters.py:213`).
Both are structured, both already present per Path C-min. No
extraction from natural language.

---

## 2. `expected_outcome_range` — needed or deferred?

### 2.1 Minimal-B1 proposal (preferred)

Limit the expected-outcome surface in B1 to:

- `expected_cost_min`, `expected_cost_max` (closed interval, float)
- `expected_sla_preserved` (bool)

Rationale: these two fields alone are sufficient to express the
operational deviation patterns the Roadmap mentions ("realized cost
materially exceeds expected range" and "expected SLA preserved but
realized SLA missed"). Adding more dimensions without a concrete
deviation rule multiplies schema surface for no behavioral gain.

### 2.2 Fields explicitly deferred out of B1

- Expected ETA window (hours). Defer: `sla_impact.preserved` already
  captures whether the ETA breached SLA; a numeric ETA window invites
  rounding rules that aren't needed for a bounded-retry trigger.
- Expected inventory state. Defer: not relevant to the replan trigger
  rule set proposed here.
- Expected auto-execute success probability. Defer: would require a
  memory read and cross into Path-C-min policy-only learning-injection
  territory.

### 2.3 Trigger granularity (LOCKED per D3)

Both dimensions are carried on `ReplanConfig`:

- `cost_deviation_abs_threshold: float`  (>= 0)
- `cost_deviation_rel_threshold: float`  (in `[0.0, 1.0]`)

plus an independent SLA gate:

- `sla_deviation_enabled: bool`

The Slice 2 trigger rule treats any realized cost outside the closed
range `[expected_cost_min, expected_cost_max]` as `COST_DEVIATION`;
the two threshold fields are reported in
`ReplanTriggerRecord.deviation_measurement` for audit and are
reserved for a future secondary-gate refinement. `relative_delta`
uses the deterministic safe denominator `max(1.0, expected_cost_max)`
so the ratio is stable even when the expected max is very small.

---

## 3. Replan trigger decision record — candidate design

### 3.1 Purpose

A structured, auditable record that captures *why* a replan did or did
not fire, produced once per execution attempt. Parallel to
`AdaptivePolicyAdjustment` but orthogonal to it (the adaptive layer
stays untouched).

### 3.2 Draft shape (non-final)

```
ReplanTriggerType = Literal[
    "NO_TRIGGER",              # rule evaluated, no replan
    "COST_DEVIATION",          # realized cost outside expected range
    "SLA_DEVIATION",           # expected preserved, realized missed
    "EXECUTION_FAILED",        # execute_action raised
    "PREFLIGHT_FAILED",        # preflight rejected the attempt
]

class ReplanTriggerRecord(BaseModel):
    trigger_rule_id: str                   # e.g. "cost_deviation_v1"
    trigger_type: ReplanTriggerType
    attempt_index: int                     # 0 for first attempt, 1 for replan
    # Structured deviation measurement — never natural language.
    deviation_measurement: dict[str, float | bool | int]
    # Structured references to the inputs that produced this decision.
    expected_outcome_ref: ExpectedOutcomeRef | None
    realized_cost: float | None
    realized_sla_preserved: bool | None
    notes: str = ""                        # short, non-authoritative audit
    schema_version: str = "1.0"
```

`deviation_measurement` carries numeric facts only:

```
{
  "realized_cost": 412.5,
  "expected_cost_max": 310.0,
  "absolute_delta": 102.5,
  "relative_delta": 0.3306,
  "cost_rule_threshold_abs": 50.0,
  "cost_rule_threshold_rel": 0.2,
  "sla_deviation": false
}
```

### 3.3 Trigger rule surface

A *closed* set of trigger rules, registered in a module-level tuple
analogous to `adaptive.adaptive_policy_config.DEFAULT_RULES`:

```
REPLAN_TRIGGER_RULES: tuple[TriggerFn, ...] = (
    _cost_deviation_rule,     # fires COST_DEVIATION
    _sla_deviation_rule,      # fires SLA_DEVIATION
    # Note: EXECUTION_FAILED / PREFLIGHT_FAILED are surfaced by the
    # orchestration wrapper, not by a rule — they are already
    # structured facts in the existing EffectiveDecisionRef status set.
)
```

Every fired `trigger_rule_id` must live in a `KNOWN_TRIGGER_RULE_IDS`
frozenset, checked by an audit-trail test in the spirit of
`tests/test_adaptive_audit_trail.py`.

### 3.4 Bounded retry invariant

```
MAX_REPLAN_ATTEMPTS: Final[int] = 1   # ⟨D4⟩ Roadmap: "one bounded cycle"
```

Hard rule: the orchestrator emits at most `MAX_REPLAN_ATTEMPTS + 1`
`ReplanTriggerRecord`s per event (attempt_index in `{0, 1}` only).
Exceeding the cap is a raised exception, not a silent degrade.

---

## 4. Replan attempts representation (without mutating Path B raw record)

### 4.1 Non-negotiable: `baseline_event_result` is never touched

`SessionEventRecord.baseline_event_result` is the Path B shadow,
embedded verbatim (`src/event_loop_c.py:222` and
`session_schema.py:91`). Replan attempts do NOT write into it, do NOT
replace it, do NOT wrap it.

### 4.2 Candidate placements

**Placement A — extend `SessionEventRecord` (MINOR bump)** (preferred)

Add optional overlay fields with safe defaults:

```
class SessionEventRecord(BaseModel):
    # ... existing fields unchanged ...
    replan_trace: Optional[list[ReplanAttemptRecord]] = None
    replan_triggers: Optional[list[ReplanTriggerRecord]] = None
```

`ReplanAttemptRecord` describes one attempt:

```
class ReplanAttemptRecord(BaseModel):
    attempt_index: int                          # 0-based
    effective_decision: EffectiveDecisionRef    # per-attempt effective truth
    execution_outcome: dict[str, Any] | None    # structured outcome, may be None
    adaptive_adjustment: AdaptivePolicyAdjustment | None
    expected_outcome: ExpectedOutcomeRef | None
    trigger: ReplanTriggerRecord                # why this attempt ended
    notes: str = ""
    schema_version: str = "1.0"
```

The *primary* `effective_decision` on `SessionEventRecord` always
reflects the **final** attempt (the one actually used for KPI
canonical-source reads). Per-attempt intermediate effective decisions
live inside `replan_trace[i].effective_decision`.

Pros: keeps everything on a single event record; simplest replay
semantics; no new top-level artifact; MINOR schema bump only.

Cons: slightly fattens `SessionEventRecord` even when replan is off
(mitigated by `None` default).

**Placement B — sibling artifact** (historical, NOT selected)

A separate `replan_trace.jsonl` file inside the session output
directory, indexed by `(session_id, event_id)`.

Pros: would keep `SessionEventRecord` untouched.

Cons: a separate index with its own replay invariants; complicates
`save_session` / `load_session` / `replay_session_bytes`; replay
byte-identity test has to cover two files. Adds more surface than it
saves.

**Locked per D2: Placement A.** `SessionEventRecord` MINOR-bumped
1.0 → 1.1 with additive optional `replan_trace` / `replan_triggers`
fields (default `None`). Landed in Slice 1 and wired in Slice 3;
Placement B is not reachable inside B1.

### 4.3 Rule: attempt records never collide with `MemoryRecord` (LOCKED per D5)

`MemoryRecord` is keyed canonically by `(event_timestamp, event_id)`
(`src/learning/episodic_memory.py:55`). Writing multiple records per
event would break the ordering invariant.

B1 therefore **must NOT** append a `MemoryRecord` per replan attempt,
and **must NOT** read memory mid-event (between attempts). The
memory append for an event happens at most once, and describes the
**final** attempt's outcome, matching the current Phase-1/2 behavior
(`src/event_loop_c.py:387`). Replan attempts are captured in the
session overlay only — via `replan_trace[i]` on the primary
`SessionEventRecord`.

### 4.4 Deterministic replan attempt identity

Each `ReplanAttemptRecord` carries an `attempt_index` only; no UUID,
no wall-clock. The `(session_id, event_id, attempt_index)` triple is
the canonical attempt identity — derivable, pure, replay-safe.

---

## 5. Forbidden truth sources

This section is normative. B1 implementation MUST enforce it via a
source-level test (§G3 in `docs/B1_REPLAN_BOUNDARY.md`).

### 5.1 Banned as numeric trigger truth

The following fields are **natural-language** by schema and MUST NOT
appear in any part of the B1 trigger / expected-outcome / attempt
code:

- `GovernanceOutput.cost_summary`
  — string (`src/agents/governance_agent.py:77`).
- `GovernanceOutput.confidence_note`
  — string.
- `GovernanceOutput.rationale_trace`
  — string.
- `GovernanceOutput.situational_explanation`
  — string.
- `GovernanceOutput.alternative_actions[*].description`,
  `alternative_actions[*].estimated_risk`
  — strings.
- `ExecutionOutcome.notes`
  — string; includes `[parse=text_fallback]` audit prefix, never
  execution-critical.
- `AdaptivePolicyAdjustment.notes`
  — string, audit-only.
- Any agent free-text field introduced in the future.

### 5.2 Allowed structured sources (non-exhaustive)

- `TwinState` fields (numeric cost policy, capacities, ETAs, zone
  SLAs) — structured.
- `_governance_meta["recommended_candidate_type"]` — literal.
- `_governance_meta["recommended_candidate_id"]` — string id, used
  as a structured pointer only (not parsed for meaning).
- `ExecutionOutcome.cost_incurred` — float.
- `ExecutionOutcome.sla_impact.preserved` — bool.
- `ExecutionOutcome.state_delta.*` — structured dict.
- `PolicyDecision.route` — literal.
- `AdaptivePolicyAdjustment.adjustment_type`,
  `pre_adjustment_risk`, `post_adjustment_risk`,
  `memory_evidence` (numeric fields only).
- `ExpectedOutcomeRef.*` (defined by B1 itself).

### 5.3 Enforcement mechanism (for the future PR)

- A source-scan test in `tests/test_replan_no_nl_fields.py` that walks
  every file under `src/replan/` and fails on a literal occurrence of
  any banned field name as an attribute access or a string constant
  in a comparison/arithmetic expression.
- AST-level check is sufficient; a purely grep-level check is also
  acceptable and simpler to implement. Pick the simplest that
  prevents regressions.

---

## 6. Preservation guarantees (restated as testable rules)

### 6.1 `baseline_event_result` untouched

- Rule: in every code path under `src/replan/`, any assignment whose
  LHS dereferences `baseline_event_result` is forbidden.
- Test (mechanical): AST scan for `Attribute` / `Subscript` targets
  ending in `baseline_event_result`.
- Test (behavioral): for a fixed seed, the Path B shadow bytes
  (serialized `baseline_event_result` list) are byte-identical
  between `enable_replan=False` and `enable_replan=True` runs.

### 6.2 `GovernanceTruthRef` vs `EffectiveDecisionRef` dual-track rule

- Rule: a replan cycle does not modify `GovernanceTruthRef`. The
  initial governance identity computed before the first attempt is the
  `GovernanceTruthRef` for the entire event, regardless of whether a
  replan reruns adaptive policy / execution.
- Rule: the `EffectiveDecisionRef` on `SessionEventRecord` reflects the
  **final** attempt (the observable system behavior). Per-attempt
  intermediate effective decisions live inside
  `replan_trace[i].effective_decision` only.
- Test: for a synthetic event that triggers replan, assert
  `governance_truth` matches the pre-replan governance output and
  `effective_decision` matches the final attempt.

### 6.3 Deterministic replay

- Rule: `session_id` stays a pure function of
  `(seed, config_digest, event_stream_digest, initial_memory_digest)`.
  If B1 adds a new digestable config input (e.g. `enable_replan`,
  `max_replan_attempts`), it is appended to the config digest in a
  documented, fixed order and registered in
  `PATH_C_SCHEMA_REGISTRY.md`.
- Rule: `canonical_json` output for the replan-enabled artifact is
  byte-identical across a fresh-process rerun with the same inputs.
- Test: `tests/test_replay_byte_identical.py` extended to cover
  replan-enabled sessions.
- Test: `tests/test_determinism_stress.py` extended to include at
  least one replan-triggering scenario.

### 6.4 Policy-only learning injection (LOCKED per D5; Slice 3 landed)

Memory invariants that MUST hold under a fired replan, matching the
Slice 3 implementation in `src/replan/replan_orchestrator.py` and
`src/event_loop_c.py`:

- **No mid-event memory append.** The orchestrator never calls
  `memory.append(...)`. Exactly one `MemoryRecord` is appended per
  event by `event_loop_c`, after the FINAL attempt, from the
  final attempt's governance/route/outcome — identical memory-append
  cadence to pre-B1.
- **No per-attempt `MemoryRecord`.** Neither attempt 0 nor attempt 1
  writes its own record. Per-attempt state is carried only on
  `ReplanAttemptRecord` inside `SessionEventRecord.replan_trace`.
- **No read-back of attempt-0 memory inside the same event.** Because
  attempt 0 does not append, there is no new record for the second
  cycle to read. The attempt-1 adaptive gate call is passed the
  *same* `EpisodicMemory` object as attempt 0 — the snapshot is
  unchanged between attempts.
- **Memory snapshot IS consulted by the second cycle's adaptive
  gate, unchanged.** The orchestrator forwards the caller's
  ``memory`` argument into the existing
  ``decide_policy_adaptive(...)`` call without modification. This is
  the same adaptive-gate path attempt 0 used; no new read surface is
  introduced. Policy-only learning injection remains the sole
  memory-influence point.
- **No learning-module imports inside the trigger / estimator.**
  `src/replan/expected_outcome.py` and
  `src/replan/replan_trigger.py` contain no imports from
  `learning.*`. Enforced by the source AST scan in
  `tests/test_replan_trigger_purity.py`. (The orchestrator is
  intentionally excluded from that scan because it is a runtime
  wrapper, not a pure function; its memory reference is a pass-through
  into the existing adaptive gate only — not a new read surface.)

---

## 7. Owner-fixed decisions (LOCKED as of B1 Slice 1)

| ID | Question | **LOCKED answer** | Structural enforcement |
|---|---|---|---|
| D1 | Where does the expected-cost structured estimate come from? | **`cost_output_derived_overlay`** — a deterministic projection over `CostOutput.cost_estimates` keyed by governance identity. Never TwinState, never `_governance_meta`, never NL governance fields. | Closed Literal `EXPECTED_COST_RANGE_SOURCE_LITERAL`; source-scan `tests/test_replan_contract_no_nl_truth.py`. |
| D2 | `SessionEventRecord` extension vs sibling artifact for replan trace? | **Placement A.** `SessionEventRecord` MINOR bump 1.0 → 1.1 with optional `replan_trace` / `replan_triggers` (default `None`). | `SessionEventRecord` 1.1 in `PATH_C_SCHEMA_REGISTRY.md`; frozen-field test in `tests/test_path_c_schema_frozen.py`. |
| D3 | Cost deviation as absolute, relative, or both? | **Both**, plus independent SLA gate. `ReplanConfig` carries `cost_deviation_abs_threshold` (>= 0), `cost_deviation_rel_threshold` ∈ [0, 1], and `sla_deviation_enabled: bool`. Trigger decision logic NOT in Slice 1. | `ReplanConfig.__post_init__` validators; `tests/test_replan_schema_frozen.py`. |
| D4 | `MAX_REPLAN_ATTEMPTS` value? | **1.** Hard cap. Exceeding is an error, not a soft degrade. | Module constant + `__post_init__` rejection of `max_replan_attempts > 1`. |
| D5 | Second cycle: re-invoke adaptive policy gate, or execution dispatcher only? And memory behavior? | **Full reasoning cycle** (operations → cost → governance → adaptive gate → preflight → execute). Memory **final-attempt-only** — no per-attempt `MemoryRecord`, no mid-event memory read. | Per-attempt Literals on `ReplanAttemptRecord` mirror the full operational domain exactly. |

These are not reopen-able inside B1. A future change to any locked
answer is an owner-approved, separately-labelled design change —
not a B1 follow-up slice.

---

## 8. Schema version table (as landed in B1 Slices 1–2)

| Schema | Module | Version | Status |
|---|---|---|---|
| `ExpectedOutcomeRef` | `src/replan/replan_schema.py` | 1.0 | **landed (Slice 1)** |
| `ReplanTriggerRecord` | `src/replan/replan_schema.py` | 1.0 | **landed (Slice 1)** |
| `ReplanAttemptRecord` | `src/replan/replan_schema.py` | 1.0 | **landed (Slice 1)** |
| `ReplanConfig` (dataclass) | `src/replan/replan_config.py` | 1.1 | **Slice 2 additive bump** — adds `expected_cost_band_abs`, `expected_cost_band_rel`. |
| `SessionEventRecord` | `src/session/session_schema.py` | 1.1 | **landed (Slice 1, MINOR bump)** — adds `replan_trace`, `replan_triggers`, both optional with `None` defaults. |
| `SessionKPIs` | `src/session/session_schema.py` | 1.1 | **Slice 4 additive bump** — five replan-aware KPI fields (`replan_events_observed`, `replan_fire_count`, `replan_trigger_rate`, `replan_success_count`, `replan_recovery_rate`) with safe defaults. |

Slice 2 additionally adds two pure modules:

| Module | Entry point | Purity |
|---|---|---|
| `src/replan/expected_outcome.py` | `estimate_expected_outcome(*, cost_output, governance_meta, config) -> ExpectedOutcomeRef` | pure; fails closed |
| `src/replan/replan_trigger.py` | `decide_replan_trigger(*, expected_outcome, execution_status, execution_outcome, attempt_index, config) -> ReplanTriggerRecord` | pure |

Neither is wired into `event_loop_c` in this slice. The Slice 2
delivery remains runtime-no-op.

### Slice 4 analytics landing (KPI / compare / report visibility)

Slice 4 is additive-only at the analytics layer — no runtime
semantics change.

- `SessionKPIs` MINOR bump 1.0 → 1.1 with five safe-default replan
  KPI fields. Pre-B1 artifacts validate unchanged; non-replan
  sessions keep the new fields at zero / None.
- `src/session/kpi_calculator.py` gains `REPLAN_KPI_KEYS`,
  `compute_replan_kpis(records)`, and `is_replan_success(record)`.
  The replan-success rule is an explicit any-of over three narrow
  structural dimensions — documented in-module and in the new
  `tests/test_replan_kpi_calculator.py`.
- `compute_session_kpi_report` attaches a sibling `"replan"` block
  (with per-segment replan KPIs) only when the artifact has at
  least one event with `replan_trace is not None`. Pre-B1 /
  replan-disabled reports retain pre-B1 byte identity.
- `src/session/session_compare.py` adds a conditional
  `replan_trace_summary` sibling block (trigger-type counts,
  recovered-event counts, per-mode replan KPIs) — emitted only when
  at least one compared artifact has replan traces. Non-replan
  compares retain pre-B1 shape exactly.
- `render_thesis_markdown` appends a "Bounded-replan behavior (B1)"
  section only when `replan_trace_summary` is present. The existing
  thesis, deltas, and diverged-events sections are unchanged.

Existing Phase-3 KPIs are not redefined. Their canonical sources,
denominators, and zero-denominator policy stay exactly as they were
on `main` before Slice 4.

`PATH_C_SCHEMA_REGISTRY.md` is the authoritative record. If this
table and the registry disagree, the registry wins.
