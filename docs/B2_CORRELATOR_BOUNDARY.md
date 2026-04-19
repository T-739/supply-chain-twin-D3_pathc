# B2_CORRELATOR_BOUNDARY.md

Status: **B2 Slice 1 draft (boundary only). No runtime logic, no
schema files, no test additions yet.**
Authority: `Path_C_Roadmap_v2_1.docx`, `PATH_C_BOUNDARY.md`,
`PATH_C_SCHEMA_REGISTRY.md`, `B1-B5_Implementation_Roadmap_Report.docx`,
`docs/B1_REPLAN_BOUNDARY.md` (for the additive-subpackage precedent).

This document is the contract that governs any future B2 (Event
correlator) implementation PR. It does not itself introduce runtime
behavior, and it does not supersede `PATH_C_BOUNDARY.md`; it narrows
scope further for B2 and locks the five Slice 1 decisions in §12.

---

## 1. Purpose

Define the boundary within which the B2 *Event correlator* branch may
later be implemented, so that:

- Path C-min (Phases 0–3) and B1 (Replan, Slice 1 landed) remain fully
  intact and regression-clean.
- B2 code is strictly additive over the existing three-layer separation
  (Path B raw → Path C session overlay → Path C session artifact),
  matching the additive pattern used by `src/replan/`.
- B2 never becomes a vehicle for extending `EventType`, expanding
  agent contracts, rewriting Path C-min, or generalizing into
  cross-session or cross-agent correlation.
- A future reviewer can answer "is this PR inside B2 Slice 1 scope?"
  from this file alone, not from conversation history.

## 2. Why B2 is the next branch now

- Path C-min closes the single-event decision loop and B1 closes the
  bounded *temporal* extension within a single event (one replan
  cycle). B2 is the smallest useful extension that exercises the
  *cross-event* dimension: recognizing that two or more *recent*
  events in the same session stream together describe a compound
  disruption the system can observe but does not have to act on.
- B2 stops at **observability**. It emits a structured
  `correlation_context` that downstream tooling (compare report,
  thesis report, future policy-layer consumers) can read. It does
  not feed the policy gate in Slice 1.
- B3 (cross-session cumulative memory), B4 (agent-visible memory),
  and B5 (React/frontend) are all larger-footprint or contract-
  sensitive branches. B2 is the branch that can be designed purely
  as a sideband overlay on an already-materialized per-event stream,
  without opening any agent contract, any EventType surface, or any
  truth-reference layer.

## 3. In-scope (for the future B2 implementation PR; NOT this turn)

B2 implementation (across slices) will be allowed to:

1. Add a new Path C subpackage (preferred name: `src/correlator/`)
   that is added to the Path-C AST-scan roots in
   `tests/test_path_c_import_topology.py`.
2. Introduce new pydantic schemas for:
   - a *correlation signal* — the evidence record for a single matched
     compound pattern (pattern_id, participant event ids, shared
     entity refs, window metadata, structured matched conditions);
   - a *correlation context* — the per-event sideband carrying the
     list of correlation signals that involve this event;
   - a *correlator config* — window size (in event-stream ordinals),
     enabled pattern ids, and the closed pattern catalog constants.
3. Extend `SessionEventRecord` *additively* (MINOR bump 1.1 → 1.2)
   with a single optional field `correlation_context` with a safe
   `None` default. Any such bump must update
   `PATH_C_SCHEMA_REGISTRY.md` and the fixture set in the same PR.
4. Wire a single narrow extension point inside
   `src/event_loop_c.py` that, **after** the per-event
   `SessionEventRecord` is fully assembled (Path B shadow +
   Path C overlay + B1 replan overlay), calls into the correlator
   to produce a `correlation_context` from a deterministic
   sliding window over already-finalized records, and writes it
   back via an immutable copy (`model_copy`) — never an in-place
   mutation.
5. Extend `src/session/session_compare.py` *additively* with a
   sibling `correlation_summary` block that counts fires per
   `pattern_id` and lists participating events. Existing
   `kpi_matrix`, `deltas`, `diverged_events`,
   `thesis_claim_support`, `replan_trace_summary` stay unchanged
   in shape.
6. Add new tests under `tests/test_correlator_*` covering contract
   freeze, pattern-match determinism, window determinism,
   observability-only invariants, shadow/overlay non-mutation,
   and replay byte identity.

## 4. Explicit out-of-scope

B2 MUST NOT, in its first implementation PR or any follow-up labelled
B2 Slice 1:

1. Extend `EventType` or add any "compound" / "synthetic"
   `EventType` value. The 6-value enum in `src/event_schema.py` stays
   closed.
2. Change any field or semantic of `EventPayload`,
   `GovernanceOutput`, `_governance_meta`, `PolicyDecision`,
   `ExecutionOutcome`, or the Path B per-event record shape.
3. Modify any agent prompt, agent module, or agent output schema
   (`src/agents/*`). Correlation results NEVER enter an agent prompt.
4. Modify `evaluation.py`, `action_code_mapper.py`, or
   `data/cases/*.json`.
5. Collapse `GovernanceTruthRef` and `EffectiveDecisionRef`, or
   cause either to be recomputed. `correlation_context` is a third,
   strictly additive sideband — never a truth reference.
6. Mutate `SessionEventRecord.baseline_event_result` or any other
   already-finalized overlay field. The correlator attaches
   `correlation_context` by producing a new `SessionEventRecord`
   via `model_copy(update={"correlation_context": ...})`.
7. Influence policy routing, adaptive adjustments, or execution
   outcomes in any way, at any time, in Slice 1.
   `decide_policy_adaptive`, `validate_governance_meta`, and
   `execute_action` neither read nor are passed any correlator
   output.
8. Influence replan trigger decisions. `src/replan/` does NOT import
   from `src/correlator/` in Slice 1.
9. Append a per-event `MemoryRecord` variant that reflects
   correlation. Memory semantics are unchanged from Path C-min / B1:
   one append per event, reflecting only the final operational
   attempt.
10. Cross into B3–B5: no cross-session correlator state, no
    agent-visible correlation, no frontend visualization. A B2 PR
    that incidentally touches those is out-of-scope.
11. Re-open Path C-min or B1 design decisions (bounded adjustment
    set, cold-start semantics, dual-track rule, replan D1–D5).
12. Introduce a generic graph algorithm, a generic rule engine, a
    DSL, or a dynamically loaded pattern set. Slice 1 ships with a
    **small, closed, hand-enumerated pattern catalog** (see §12 D5).
13. Introduce wall-clock input, `uuid4`, or `data/cases` access
    anywhere under `src/correlator/`.

## 5. Preserved invariants (non-negotiable)

All invariants from `PATH_C_BOUNDARY.md` §1 and
`docs/B1_REPLAN_BOUNDARY.md` §5 stand unchanged under B2. B2
additionally preserves:

- **Path B shadow integrity.** The Path B `run_event_loop` shadow
  remains untouched. `baseline_event_result` is verbatim. The
  correlator never receives it as a mutable reference.
- **Dual-track rule + replan overlay rule.** `GovernanceTruthRef`
  and `EffectiveDecisionRef` stay as the only two truth references
  per event. `replan_trace` / `replan_triggers` stay as the bounded
  replan overlay. `correlation_context` is a third, observability-only
  overlay that is **never** read as truth.
- **Policy-only learning injection.** Memory influences behavior
  exclusively via the adaptive policy gate. Correlator output is
  **not** memory, is **not** read by the policy gate in Slice 1, and
  is **not** surfaced to any agent prompt.
- **Deterministic-first.** The correlator is a pure function of
  `(finalized SessionEventRecord sequence so far, correlator config)`.
  Window semantics are expressed as *event-stream ordinal counts*
  (e.g. "the last N records in session order"), never as wall-clock
  durations. No `datetime.now()`. No `uuid4()`. No hash-seed-dependent
  iteration. Pattern-match iteration order is the deterministic
  registration order of the pattern catalog.
- **Bounded action set.** Correlator output does not expand the
  adjustment set, does not introduce new actions, does not interact
  with `DOWNGRADE_*`, and does not re-invoke the adaptive policy
  gate. Slice 1 is pure observability.
- **Structural explainability.** Every emitted `CorrelationSignal`
  carries a structured `pattern_id`, the full list of participating
  `event_id`s, the shared `AffectedEntityRef` set (or
  `shared_entities=[]` if the pattern is entity-free), the window
  bounds (`window_start_ordinal`, `window_end_ordinal`,
  `window_size`), and a closed-set `matched_conditions` list. No
  free-text explanation field is admissible as authoritative.

## 6. Allowed files to touch later (B2 PR allowlist)

The future B2 PR may *create* files under:

- `src/correlator/` (new subpackage; expected members in
  `docs/B2_CORRELATOR_FILE_MAP.md`)
- `tests/test_correlator_*.py`
- `tests/fixtures/correlator_*` (if fixture-based snapshots are
  needed)

The future B2 PR may *additively* modify, but must not rewrite or
repurpose:

- `src/session/session_schema.py` — add one optional
  `correlation_context: Optional[CorrelationContext] = None` field
  on `SessionEventRecord` (MINOR bump 1.1 → 1.2).
- `src/event_loop_c.py` — one narrow post-record-assembly extension
  point; see §6 of the file map.
- `src/session/session_compare.py` — add an optional sibling block
  `correlation_summary`. Existing blocks unchanged.
- `PATH_C_SCHEMA_REGISTRY.md` — register new schemas and bump
  `SessionEventRecord` to 1.2.
- `PATH_C_BOUNDARY.md` — append a B2 cross-reference pointing at
  `docs/B2_CORRELATOR_BOUNDARY.md`. Existing §1–§8 text unchanged.
- `tests/test_path_c_import_topology.py` — add `src/correlator/` to
  the scan roots.
- `tests/test_path_c_schema_frozen.py` — add frozen assertions for
  the new schemas and the bumped `SessionEventRecord`.
- `scripts/session_eval_harness.py` / `scripts/run_session.py` —
  add a `--enable-correlator` flag; default OFF.
- `docs/path_c_thesis_alignment.md` — optional B2 addendum.

The future B2 PR may *not* additively modify:

- `src/event_schema.py` — `EventPayload`, `EventType` stay frozen.
- `src/session/kpi_calculator.py` — **no KPI changes in Slice 1**
  (see §12 D3). KPIs that summarize correlator output are deferred
  to a later B2 slice or B5 reporting work.
- `src/replan/*` — replan does not depend on correlator in Slice 1.
- `src/adaptive/*` — correlator does not feed adaptive policy in
  Slice 1.
- `src/learning/*` — correlator is not memory.
- `src/agents/*` — correlator output is not prompt input.

## 7. Forbidden files / forbidden modifications

B2 MUST NOT touch, in any PR:

- `src/agents/**` — any agent, any agent output schema.
- `src/policy_gate.py` — `PolicyDecision` and `decide_policy` stay
  frozen.
- `src/outcome_schema.py` — `ExecutionOutcome` stays frozen.
- `src/event_schema.py` — `EventPayload`, `EventType`,
  `EventSeverity`, `AffectedEntityRef` stay frozen.
- `src/evaluation.py`, `src/action_code_mapper.py` — Research Core.
- `data/cases/*.json` — Research Core data.
- `src/graph.py` node wiring.
- `src/execution_adapters.py` — no new adapter, no new dispatcher
  branch.
- `src/event_loop.py` (Path B core).
- `src/replan/*` — replan stays unaware of correlation in Slice 1.
- `src/adaptive/*` — adaptive stays unaware of correlation in
  Slice 1.

Forbidden modification classes:

- Any change that would cause `BASELINE_STATIC` mode to produce a
  byte non-equal `SessionArtifact` for a given seed/event stream.
- Any change that would cause `PATH_C_COLD` / `PATH_C_WARM` with
  `enable_correlator=False` to diverge from current behavior (with
  `enable_replan=False` **or** `enable_replan=True`).
- Any change to the canonical JSON byte layout of Phase-3 compare
  reports under current CLI defaults.
- Any change to the pattern catalog that is not a MINOR version bump
  on the catalog module *and* a registry update in the same PR.

## 8. Correlator-specific risks (and their mitigations)

| # | Risk | Mitigation (mandatory for B2 implementation PR) |
|---|---|---|
| R1 | Extending `EventType` to carry compound-event markers | `EventType` is in the forbidden-modification list; all compound semantics live under `pattern_id` in a new closed Literal local to `src/correlator/`. |
| R2 | Runtime complexity blow-up from generic correlation | Window is bounded by a config integer (suggested default: 3). Pattern catalog is a closed Literal set (2–4 entries in Slice 1). Per-event work is O(window × \|catalog\|). |
| R3 | Implicit inference without structured evidence chain | Every `CorrelationSignal` must carry participant `event_id`s, shared `AffectedEntityRef` set, `window_*` ordinals, and a closed-set `matched_conditions` list. An AST-/source-scan test asserts the correlator module does not use `GovernanceOutput` NL fields (`cost_summary`, `confidence_note`, `rationale_trace`, `situational_explanation`, `alternative_actions`) anywhere. |
| R4 | Silent mutation of finalized `SessionEventRecord` | The correlator returns new records via `model_copy(update=...)`. An invariant test asserts the pre-correlator list is not modified in place (object identity + deep-equal check on serialized bytes). |
| R5 | Wall-clock leakage via event timestamps | Window math is ordinal-based, not timestamp-based. `event.timestamp` may be copied into the evidence payload as a reference-only field, but is never used for window thresholds. The Path-C AST scan already forbids `datetime.now()` / `time.time()` under `src/correlator/`. |
| R6 | Policy / adaptive contamination | Correlator output is written only into `SessionEventRecord.correlation_context`. An AST scan asserts `src/adaptive/`, `src/replan/`, `src/policy_gate.py`, and `src/execution_adapters.py` do not import from `src/correlator/` in Slice 1. |
| R7 | Scope creep into B3 | Correlator state is session-local. It does not read or write `src/learning/episodic_memory.py` or any cross-session store. An import-level test asserts `src/correlator/` does not import `EpisodicMemory`. |
| R8 | Replay byte drift from the new overlay field | `SessionEventRecord` MINOR bump uses a safe default (`correlation_context=None`). `test_replay_byte_identical` is extended to cover `enable_correlator={False,True}` × `enable_replan={False,True}` sessions. With `enable_correlator=False`, byte identity versus pre-B2 `main` holds. |
| R9 | KPI denominator drift | Slice 1 **adds no KPIs**. The KPI calculator module is on the forbidden-modification list for Slice 1. Future KPI integration is a separate slice. |
| R10 | B2 drifts into B4 agent-visible territory | Correlator output is a session-artifact-only sideband. It never appears in a prompt, never in a `GovernanceOutput`, never in `_governance_meta`. An integration test asserts agent inputs are byte-identical with and without `enable_correlator=True`. |

## 9. Rollback rules

If the first B2 implementation PR, or any follow-up, causes any of the
following, it MUST be reverted (not patched forward):

- A Path C-min or B1 test regresses: any test currently passing on
  `main` in the files listed under
  `docs/B1_REPLAN_BOUNDARY.md §9` **plus** every `test_replan_*.py`
  test.
- `BASELINE_STATIC` session-artifact bytes change for any seed that
  passed before.
- `PATH_C_COLD` / `PATH_C_WARM` session-artifact bytes change for any
  seed that passed before, when `enable_correlator=False`
  (independent of `enable_replan`).
- Canonical JSON of the existing Phase-3 compare report changes under
  default harness flags (default = `enable_correlator=False`).
- The AST import-topology scan grows a new allowed import or a new
  exception. New forbidden imports are permitted; weakening the scan
  is not.
- Agent prompts or agent outputs change in any byte-observable way.

If a partial B2 landing needs to be rolled back, roll back the entire
B2 slice; do not leave half-implemented correlator surfaces on
`main`.

## 10. Acceptance gates for future implementation

The B2 Slice 1 implementation PR will be considered acceptable only
if ALL of the following hold simultaneously:

- **G1 Contracts first.** New pydantic models land as schema
  skeletons with frozen tests, before any runtime logic. Matching
  entries exist in `PATH_C_SCHEMA_REGISTRY.md`.
- **G2 Window / pattern determinism.** A test drives a fixed
  synthetic event stream (with canonical ordering) twice under a
  fresh process and asserts byte-identical
  `list[CorrelationSignal]` output.
- **G3 Observability-only.** A test constructs a session whose
  Path-C main-path route would be `HUMAN_REQUIRED` and asserts that
  the same session with `enable_correlator=True` produces the
  identical `EffectiveDecisionRef` and the identical adaptive /
  replan overlay for every event. Correlation changes `correlation_
  context` only.
- **G4 Shadow + overlay untouched.** A test compares
  `baseline_event_result`, `governance_truth`, `effective_decision`,
  `adaptive_adjustment`, `replan_trace`, and `replan_triggers` across
  runs with `enable_correlator={False,True}` on the same inputs and
  asserts byte-equality for each of those fields.
- **G5 No-agent-contamination.** A test captures the full sequence
  of agent prompt inputs under `enable_correlator=False` and under
  `enable_correlator=True` on the same inputs and asserts byte-
  equality.
- **G6 Evidence-chain enforcement.** A test asserts every emitted
  `CorrelationSignal` has ≥ 2 distinct participant `event_id`s, a
  non-null `pattern_id` from the closed catalog Literal, a non-empty
  `matched_conditions` list from the closed condition Literal, and
  well-formed `window_*` ordinals with `window_end_ordinal -
  window_start_ordinal + 1 <= window_size`.
- **G7 No-NL-truth scan.** A source-scan test asserts
  `src/correlator/` does not reference `cost_summary`,
  `confidence_note`, `rationale_trace`, `situational_explanation`,
  or `alternative_actions`.
- **G8 Replay byte identity.** `test_replay_byte_identical` passes
  for all 4 combinations in `enable_correlator={False,True}` ×
  `enable_replan={False,True}`.
- **G9 Determinism stress.** A fresh-process rerun of a
  correlator-enabled session produces byte-identical
  `SessionArtifact.json`.
- **G10 Phase-3 KPI invariance.** Slice 1 adds no KPIs. For any
  combination of flags, every existing KPI value matches
  pre-B2 `main` to the 4-decimal serialization boundary.
- **G11 Compare report surface stability.** With
  `enable_correlator=False`, the Phase-3 `compare_report.json` is
  byte-identical to pre-B2 `main`. A new `correlation_summary`
  block appears only when correlator is enabled.
- **G12 AST scan covers new module.** `src/correlator/` is in the
  Path C AST scan roots. The scan's positive/negative self-tests
  pass.
- **G13 No reverse imports.** `src/adaptive/`, `src/replan/`,
  `src/policy_gate.py`, `src/execution_adapters.py`,
  `src/learning/`, and `src/agents/` do not import from
  `src/correlator/`. Tested structurally.
- **G14 Honesty rule.** If enabling correlator reveals an
  uncomfortable pattern in the session (e.g. a "compound" marker
  that the system did NOT act on), the thesis report reports it
  honestly. There is no code branch that suppresses a negative
  finding.

No gate may be waived. A single failing gate blocks the B2 PR.

---

## 11. Non-goals for B2 Slice 1 (reminder)

- Policy-feeding correlator (future B2 slice; not Slice 1).
- Correlator-informed replan (would couple to B1; not Slice 1).
- Cross-session correlation (B3, not B2).
- Agent-visible correlation (B4, not B2).
- Frontend visualization of correlation signals (B5).
- Generic graph-based detection algorithms.
- Dynamic / user-loadable pattern catalogs.

## 12. Owner-fixed decisions for B2 Slice 1 (locked for this turn)

These are the five decisions this slice closes. Structural
consequences are enforced by tests and the schema registry once the
implementation PR lands.

- **D1 — First cut uses the `correlation_context` sideband.** No
  `EventType` extension; no synthetic compound event; no agent-
  contract expansion. Correlator output is reached **only** via
  `SessionEventRecord.correlation_context`. Enforced by G5, G13,
  and the forbidden-modification rules on `src/event_schema.py`
  and `src/agents/*`.

- **D2 — Placement A: additive on `SessionEventRecord` only.**
  `SessionEventRecord` MINOR-bumps 1.1 → 1.2, gaining one optional
  field `correlation_context: Optional[CorrelationContext] = None`.
  No sibling artifact. All other schemas keep their current
  versions (`SessionKPIs` stays at 1.1 for Slice 1 — see D3).

- **D3 — Slice 1 is observability-only; no KPI bump.**
  `SessionKPIs` is **not** modified in Slice 1.
  `src/session/kpi_calculator.py` is on the forbidden-modification
  list. A correlation-aware KPI surface (e.g. `compound_event_rate`,
  `cascade_coverage`) is deferred to a separate slice after the
  owner has seen real runs and chosen which counts are meaningful.

- **D4 — Window is a deterministic event-stream ordinal window.**
  `CorrelatorConfig.window_size: int` defines the maximum number of
  most-recent finalized `SessionEventRecord`s (including the current
  one) available to the match function. No wall-clock window, no
  `datetime.now()`, no dynamic resizing. `max_window_size` is a
  module constant (suggested: 6, matching the demo stream length).
  `ReplanConfig.__post_init__`-style validation rejects
  out-of-range values at construction time.

- **D5 — Closed pattern catalog, 2–4 entries in Slice 1.**
  Pattern ids are declared as a closed Literal
  (`CORRELATOR_PATTERN_ID`) inside a new module
  `src/correlator/correlator_patterns.py`. The Slice 1 catalog is
  exactly the set enumerated in
  `docs/B2_CORRELATOR_CONTRACT_DRAFT.md §5`. No generic graph
  algorithm; each pattern is a pure function over a bounded window
  with a closed-set `matched_conditions` output. Adding a pattern
  is a MINOR bump on the Literal and a same-PR registry update.

These decisions are not renegotiable as part of B2 Slice 1. A
future design that needs to relax them (for example, a generic
pattern-DSL, or a correlator that feeds the policy gate) is a
separate, owner-approved branch label with its own boundary doc.

---

## 13. B2 Slice 1 delivery checklist (to satisfy in the implementation PR)

- [ ] `src/correlator/__init__.py`,
      `correlator_schema.py`, `correlator_config.py`,
      `correlator_patterns.py`.
- [ ] `SessionEventRecord` 1.1 → 1.2 (additive,
      `correlation_context` optional None-defaulted).
- [ ] `PATH_C_SCHEMA_REGISTRY.md` updated:
      `CorrelationSignal`, `CorrelationContext`, `CorrelatorConfig`
      registered at 1.0; `SessionEventRecord` bumped to 1.2.
- [ ] `tests/fixtures/path_c_schema_samples_*.json` updated for
      the new schemas and the 1.2 `SessionEventRecord`.
- [ ] `tests/test_path_c_schema_frozen.py` extended (new classes,
      per-class expected schema_version).
- [ ] `tests/test_path_c_import_topology.py` extended with
      `src/correlator/`.
- [ ] `tests/test_correlator_schema_frozen.py` added (closed
      Literals, `extra='forbid'`, min-participant invariant).
- [ ] `tests/test_correlator_no_nl_truth.py` added (source-scan).
- [ ] `tests/test_correlator_observability_only.py` added
      (G3 / G4 / G5 invariants).
- [ ] Full suite (`pytest -q`) green on `main`.

Slice 2+ is free to wire policy or replan consumption of
correlation signals; it is NOT free to re-open D1–D5.
