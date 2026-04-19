# PATH_C_BOUNDARY.md

Status: Phase 0 — Contract Freeze + Baseline Snapshot + Boundary Hardening
Authority: `Path_C_Roadmap_v2_1.docx` (supersedes prior roadmap and vision docs)

This document is enforced by CI tests under `tests/test_path_c_import_topology.py`
and `tests/test_path_c_schema_frozen.py`. Any change to the rules below requires
an owner-approved update to this file *and* the test surface in the same PR.

---

## 1. Non-negotiable principles

1. **Deterministic-first.** No wall-clock input on any Path C path. No
   `datetime.now()`, `datetime.utcnow()`, `time.time()`, `uuid.uuid4()`.
2. **Truth boundary explicit.** `governance_output["risk_level"]`,
   `governance_output["recommended_action"]` and
   `_governance_meta["recommended_candidate_type"]` are the Tier 1 governance
   truth and are never overwritten by Path C. Adaptive overlay truth lives
   exclusively on `SessionEventRecord.effective_decision` and
   `SessionEventRecord.adaptive_adjustment`.
3. **Layer separation explicit.** Path C code never mutates a Path B record.
   `SessionEventRecord.baseline_event_result` is embedded verbatim.
4. **Bounded action set.** `adjustment_type` admits only
   `UPGRADE_ONE_LEVEL`, `NO_ADJUSTMENT`, `COLD_START_FALLBACK`. DOWNGRADE_*
   is permanently out-of-scope for Path C-min.
5. **Auditability / traceability.** Every adjustment carries a structured
   `rule_id`, `query_signature`, and `memory_evidence`. Explainability is a
   *structural* contract, never a string length or fuzzy-match check.
6. **Research Core protected.** `evaluation.py`, `action_code_mapper.py`,
   `data/cases/*.json` are not touched or imported by Path C runtime code.
7. **Additive extension discipline.** Path C appears as new subpackages
   (`src/learning/`, `src/adaptive/`, `src/session/`) and a new outer
   orchestrator (`src/event_loop_c.py`, Phase 1+). Path B modules stay under
   freeze except for the two Phase 0-approved additive `schema_version`
   keys and the deterministic-hardening correction explicitly recorded
   in §8.
8. **No new mutation style.** Path C does not introduce a new TwinState
   mutation primitive. All mutation continues to flow through the existing
   Path B mutation entry points.

## 2. Frozen Path B contracts (Tier 1)

Frozen with no change:

| Record | Owner | Frozen content |
|---|---|---|
| `EventPayload` | `src/event_schema.py` | 6 fields + 6-type `EventType` enum |
| `ExecutionOutcome` | `src/outcome_schema.py` | 8 fields + 4-action Literal |
| `PolicyDecision` | `src/policy_gate.py` | 5 fields |
| `GovernanceOutput` | `src/agents/governance_agent.py` | 8-field schema, shape and semantics |
| `_governance_meta` | graph runtime | 3 fields |
| `data/cases/*.json` | research core | contents and schema |
| `evaluation.py` API | research core | signatures and semantics |
| `action_code_mapper.py` API | research core | signatures and semantics |

Frozen with the single additive key `"schema_version": "1.0"` (Phase 0 owner-approved):

| Record | Phase 0 change |
|---|---|
| `outcome_store.summary()` | returns additional top-level `"schema_version": "1.0"` |
| `event_loop.run_event_loop` event_result | each record gets top-level `"schema_version": "1.0"` |

These are the only *initially* approved Path B edits in Phase 0, plus
the deterministic-hardening correction recorded in §8. All other Path B
files are under freeze.

## 3. Frozen Path C schemas (Tier 2 / Tier 3) — shape only

Defined in Phase 0 as class skeletons, without runtime logic:

| Schema | Module | Initial version |
|---|---|---|
| `MemoryRecord` | `src/learning/memory_schema.py` | 1.0 |
| `MemoryQuery` | `src/learning/memory_schema.py` | 1.0 |
| `MemorySummary` | `src/learning/memory_schema.py` | 1.0 |
| `AdaptivePolicyAdjustment` | `src/adaptive/adaptive_schema.py` | 1.0 |
| `AdjustmentRuleSpec` | `src/adaptive/adaptive_schema.py` | 1.0 |
| `GovernanceTruthRef` | `src/session/session_schema.py` | 1.0 |
| `EffectiveDecisionRef` | `src/session/session_schema.py` | 1.0 |
| `SessionEventRecord` | `src/session/session_schema.py` | 1.0 |
| `SessionConfig` | `src/session/session_schema.py` | 1.0 |
| `SessionKPIs` | `src/session/session_schema.py` | 1.0 |
| `SessionArtifact` | `src/session/session_schema.py` | 1.0 |

Full field lists are maintained in `PATH_C_SCHEMA_REGISTRY.md`.

## 4. Versioning policy

- Format: `MAJOR.MINOR`, no `v` prefix, no patch segment.
- MINOR bump: new optional field with a safe default.
- MAJOR bump: new required field, removal, rename, semantic change, type /
  Literal change, tighter validator.
- No bump: cosmetic documentation only.
- Every bump updates `PATH_C_SCHEMA_REGISTRY.md` in the same PR and refreshes
  affected fixtures under `tests/fixtures/`.

## 5. Determinism boundary (precision rule)

- Internal arithmetic (cost aggregation, memory summaries, rule evaluation)
  uses full Python float precision.
- `round(x, 4)` is applied **only at the serialization / reporting boundary**:
  `SessionKPIs` numeric fields at artifact write, `MemorySummary` numeric
  fields at summary emit, `outcome_store.summary()` at summary emit (already
  the case in Path B).
- Adaptive decision branches and cold-start comparisons read un-rounded
  values.

## 6. Forbidden imports / APIs on Path C code paths

Enforced by `tests/test_path_c_import_topology.py` (AST scan, with
positive / negative self-tests included in the same file so the guard's
coverage is itself verified on every CI run).

Exact rules — the AST scan will fail the build on any of:

- `import evaluation`, `from evaluation import ...`
- `import action_code_mapper`, `from action_code_mapper import ...`
- `uuid.uuid4(...)` *or* a bare `uuid4(...)` call (regardless of import
  style)
- `time.time(...)`
- `datetime.now(...)`, `datetime.utcnow(...)`
- `datetime(...)` construction without a `tzinfo=` keyword
- Any Research-Core case path access, in any syntactic form:
  - string literal `"data/cases/..."` (forward- or back-slash) appearing
    as a Call argument (so `open("data/cases/...")`, `json.loads(open(
    "data/cases/...").read())`, `Path("data/cases/...")`, etc. all
    trigger);
  - `os.path.join(..., "data", ..., "cases", ...)` segment chains
    (including nested `os.path.join` calls);
  - `Path(...)` construction with a literal that embeds `data/cases`, or
    a `Path(...) / "data" / "cases"` `/`-chain;
  - attribute IO calls (`.open()`, `.read_text()`, `.read_bytes()`,
    `.write_text()`, `.write_bytes()`) whose receiver subtree references
    `data/cases` in any of the above forms.

The scan targets every Path C source file — as Phase 0 shipped this was
`src/learning/`, `src/adaptive/`, `src/session/`; Phase 1 additively
widens it to include `src/outcome_persistence/` and the top-level Path C
orchestrator `src/event_loop_c.py`. Path B remains outside the scan (it
has pre-existing, intentional uses of some of these APIs — e.g.
`graph.load_case_or_scenario` reads case JSONs by design — which are
not in scope for Path C).

Limitations (documented honestly, not hidden):

- The guard is syntactic, not a static-proof system. A highly obfuscated
  access (e.g. reconstructing the string `"data/cases"` at runtime from
  non-literal pieces, or reading through a Research-Core re-export that
  does not itself mention `data/cases`) can bypass it. Any such
  construction in Path C is a review-level offense, not a test-level
  one.
- The scan does not recurse into import graphs — it only inspects the
  source of files under the three Path C roots.

## 7. Phase 0 out-of-scope (not a partial implementation — deliberately absent)

Memory write/read logic, adaptive policy logic, session orchestrator logic,
persistence implementation, CLI, frontend, agent-visible memory, replan,
correlator, cross-session cumulative memory.

## 8. Rollback clause and deterministic-hardening record

If adding `"schema_version": "1.0"` to `outcome_store.summary()` or to
`event_loop.run_event_loop` event_result breaks a Path B test that cannot be
trivially updated, revert the additive change and relocate the version
injection into `src/event_loop_c.py` (Phase 1 wrapper). Phase 0 still ships
with schemas, boundary, registry and snapshot test — no scope loss.

Phase 0 correction pass (deterministic hardening): in addition to the
two additive `schema_version` keys, one further Path B change was
required and applied:

- `src/agents/governance_agent.py` — the `rationale_trace` builder
  previously deduplicated `evidence_refs[:3]` source documents via a
  set comprehension (`list({ref[...] for ref in ...})`). Set iteration
  order depends on Python's hash randomization, producing divergent
  `rationale_trace` strings across fresh processes. The set
  comprehension was replaced by an order-preserving first-seen dedup
  over the same 3-element slice. No business semantics change: same
  input evidence_refs still produces the same 3 source documents, now
  emitted in first-seen insertion order. This change is in scope for
  Phase 0 under Roadmap §0.E's "deterministic by construction"
  acceptance criterion.

---

## 9. Cross-references to branch-level extensions

Path C-min remains the mainline. The following branch-level
extensions live **beside** Path C-min and are governed by their
own boundary documents:

- **B1 Replan** — bounded second reasoning cycle.
  Boundary: `docs/B1_REPLAN_BOUNDARY.md`.
  Contract draft: `docs/B1_REPLAN_CONTRACT_DRAFT.md`.
  File map: `docs/B1_REPLAN_FILE_MAP.md`.
  Adds: `src/replan/` subpackage; additive
  `SessionEventRecord.replan_trace` / `replan_triggers` (1.0 → 1.1);
  additive `SessionKPIs` replan-aware fields (1.0 → 1.1).

- **B2 Event correlator** — same-session compound-pattern
  observability sideband.
  Boundary: `docs/B2_CORRELATOR_BOUNDARY.md`.
  Contract draft: `docs/B2_CORRELATOR_CONTRACT_DRAFT.md`.
  File map: `docs/B2_CORRELATOR_FILE_MAP.md`.
  Adds (Slice 2A): `src/correlator/` subpackage with frozen
  schemas (`CorrelationSignal`, `CorrelationContext`,
  `CorrelatorConfig`) and closed pattern-catalog declarations
  (P1 `ETA_PATH_COMPOUND`, P3 `CARRIER_DOUBLE_HIT`; P2 deferred);
  additive `SessionEventRecord.correlation_context` (1.1 → 1.2).
  Slice 2A is observability-only — no routing, no policy
  feedback, no replan coupling, no agent-visible output.

- **B3 Cross-session cumulative memory** — cross-session
  legitimate memory reuse into a later session's
  ``initial_memory``.
  Boundary: `docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md`.
  Contract draft: `docs/B3_CUMULATIVE_MEMORY_CONTRACT_DRAFT.md`.
  File map: `docs/B3_CUMULATIVE_MEMORY_FILE_MAP.md`.
  Adds (Slice 2A): `src/learning/cumulative_memory.py` module
  with a frozen `CumulativeMemoryConfig` dataclass, the closed
  dedupe-policy Literal (`drop_equal_raise_mismatch`), the
  `MAX_CUMULATIVE_MEMORY_RECORDS` hard cap, and a loader
  signature (body deferred to Slice 2B). No new pydantic
  schema — raw `MemoryRecord` union is sufficient because
  `MemoryRecord.session_id` already carries per-row provenance.
  `PATH_C_WARM`-only attachment is a caller-side workflow rule;
  the core `run_session(initial_memory=...)` API is unchanged.
  No KPI, no compare-report block, no CLI work in Slice 2A.

- **B4 Agent-visible memory experiment** — independent
  additive experiment branch that, for the first time,
  exposes memory-derived content to an agent prompt.
  Boundary: `docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md`.
  Contract draft: `docs/B4_AGENT_VISIBLE_MEMORY_CONTRACT_DRAFT.md`.
  File map: `docs/B4_AGENT_VISIBLE_MEMORY_FILE_MAP.md`.
  Adds (Slice 1): `src/agent_memory/` subpackage with frozen
  schemas (`AgentMemoryExampleRef`, `AgentMemoryContext`) and a
  frozen configuration dataclass (`AgentMemoryExperimentConfig`)
  with closed Literals (`target_agent="operations"`,
  `context_source="structured_summary_plus_recent_examples"`,
  `allowed_modes=frozenset({"PATH_C_WARM"})`); exported constants
  (`MAX_AGENT_MEMORY_EXAMPLES=3`, `KNOWN_AGENT_MEMORY_TARGETS`,
  `KNOWN_AGENT_MEMORY_CONTEXT_SOURCES`). Slice 1 is
  **contracts-only** — no runtime behavior, no builder, no
  renderer, no prompt assembly, no modification of
  `src/agents/*`, no new `SessionEventRecord` field, no
  compare-report block, no KPI, no CLI / harness flag. B4 is
  framed as an **independent experiment branch beside Path
  C-min**, not a mainline continuation. `enable_agent_visible_
  memory=False` is a hard default; default-off byte identity
  is load-bearing. The policy-only learning injection rule
  stays: the adaptive policy gate remains the single memory
  consumer on the policy path. Runtime integration is
  deferred to a later slice.

Neither B1 nor B2 nor B3 nor B4 weakens this boundary. Each
extension maintains the same deterministic-first / truth-
boundary / Path-B-shadow / dual-track invariants. A PR that
labels itself B1, B2, B3, or B4 but reaches outside its own
boundary doc's allowlist is out-of-scope and must be reverted,
not patched forward.
