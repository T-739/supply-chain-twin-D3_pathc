# B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md

Status: **B4 Slices 1, 2A, 2B, 2C, 2D1, 2D1.x, 2D1.xa, 2D2,
2D3-A, 2D3-B all landed.** The contract skeleton, the pure
builder + deterministic renderer, the operations-agent
single-point LLM prompt seam, the ``event_loop_c.py`` internal
caller wiring, the public ``run_session(..., agent_memory_config=
None)`` kwarg, the conditional ``agent_memory`` digest fragment,
the ``_SCHEMA_VERSIONS`` audit, the scripts / harness CLI
exposure, the **compare-only closure** (additive
``agent_memory_experiment_summary`` sibling block on
``session_compare.py`` plus harness compare/thesis emission for
the locked B4 triplet — Slice 2D3-A), and the **runtime
activation seam repair** (env-resolved ``operations_mode``
threaded through ``GraphState`` so the operations agent dispatch
observes the same env reality the W4 gate observes — Slice
2D3-B) are all on ``main``. Next deferred step is Slice 2D4 —
optional ``SessionEventRecord.agent_memory_context`` overlay
(RO1) and any future runtime observability marker (RO9). No
``SessionEventRecord`` overlay, no ``COMPARE_REPORT_SCHEMA_
VERSION`` bump, no KPI, no ``llm_meta.trace`` change has been
added in any landed slice — B4 remains a default-off experiment
branch whose end-to-end activation requires
``enable_agent_visible_memory=True`` on the public kwarg (or
the equivalent ``--enable-agent-visible-memory`` CLI flag) AND
``SUPPLY_CHAIN_TWIN_OPERATIONS_MODE=llm`` in the env (the W4
gate's operations_mode requirement, env-only per D9).

Slice ladder summary — **Slices 1 / 2A / 2B / 2C / 2D0 / 2D1 /
2D1.x / 2D1.xa / 2D2 / 2D3-A / 2D3-B all landed** in this
order. Details below; full per-slice checklist in §13.

Slice ladder (landed in order):
- **Slice 1** (contracts): ``AgentMemoryExampleRef`` 1.0,
  ``AgentMemoryContext`` 1.0, ``AgentMemoryExperimentConfig``
  1.0 + frozen tests; ``PATH_C_SCHEMA_REGISTRY.md`` entry;
  ``PATH_C_BOUNDARY.md §9`` cross-reference.
- **Slice 2A** (pure functions): ``build_agent_memory_context``,
  ``render_agent_memory_context``; subprocess-level
  PYTHONHASHSEED determinism tests; no runtime caller yet.
- **Slice 2B** (single-agent prompt seam): one additive hunk
  inside ``_build_ops_llm_user_prompt`` gated by
  ``_b4_should_inject``; two kwarg-only optional parameters
  threaded through ``_enrich_ops_with_llm`` /
  ``run_operations_agent_llm`` / ``run_operations_agent_modeful``
  / ``run_operations_agent_with_meta``. Rules-mode path and
  every other agent module unchanged.
- **Slice 2C** (internal caller wiring):
  ``_build_agent_memory_query_for_event`` (event-type-only
  ``MemoryQuery``), ``_maybe_build_agent_memory_context`` (five-
  condition W4 gate), one optional ``agent_memory_config`` kwarg
  on ``_build_path_c_main_records``; private-surface threading
  of an ``agent_memory_context`` / ``agent_memory_config``
  sideband through ``_run_reasoning_slice`` →
  ``operations_agent_node``. ``run_session`` public signature
  unchanged.
- **Slice 2D3-A** (compare-only closure): additive
  ``agent_memory_variant_tags: Optional[Sequence[str]] = None``
  opt-in kwarg on ``session_compare.build_compare_report``
  + a conditional ``agent_memory_experiment_summary`` sibling
  block (variant tags, session_ids, diverged-event ids
  restricted to the policy-only ↔ agent-visible warm pair,
  fixed informational notes; no KPI math, no NL paraphrase).
  ``COMPARE_REPORT_SCHEMA_VERSION`` stays ``"1.1"``; the
  block is omitted when the kwarg is omitted, so every
  pre-2D3 caller is byte-identical. Harness B4 ON branch
  now emits ``compare_report.json`` + ``thesis_report.md``
  over the locked triplet, opting in via
  ``_B4_EXPERIMENT_VARIANT_TAGS``.
- **Slice 2D3-B** (runtime activation seam repair): the
  env-resolved ``operations_mode`` already computed in
  ``event_loop_c._build_path_c_main_records`` is now threaded
  through a new optional ``operations_mode`` kwarg on
  ``event_loop._run_reasoning_slice`` and written into
  ``GraphState["operations_mode"]``. Closes the gap where W4
  fired on env=``llm`` but the operations agent dispatch still
  short-circuited to rules — under
  env=``llm`` + PATH_C_WARM + B4-enabled config the operations
  agent now actually reaches its LLM path and the prompt
  seam injects the ``HISTORICAL_STRUCTURED_MEMORY_CONTEXT``
  section for real. Path B and env-unset Path C-min stay
  byte-identical (Path B never passes the kwarg; env-unset
  Path C-min writes ``"rules"`` into a key the graph node
  was already treating identically to its absent default).

Previous status markers kept for archival reference: Slice 0
(docs-only candidate axes C1–C7 / open questions Q1–Q10) →
Slice 1 (D1–D7 locked) → **Slice 2C (D8–D11 locked below)**.

Authority: `Path_C_Roadmap_v2_1.docx`, `PATH_C_BOUNDARY.md`,
`PATH_C_SCHEMA_REGISTRY.md`, `B1-B5_Implementation_Roadmap_Report.docx`,
`docs/B1_REPLAN_BOUNDARY.md` (additive-subpackage precedent),
`docs/B2_CORRELATOR_BOUNDARY.md` (additive-sibling precedent),
`docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md` (caller-side workflow-rule
precedent + the explicit §9 agent-isolation separator that B4
legitimately crosses).

This document is the contract that governs any future B4
(Agent-visible memory experiment) implementation PR. It does not
itself introduce runtime behavior, and it does not supersede
`PATH_C_BOUNDARY.md`; it narrows scope further for B4.

§12 now carries the owner-locked D1–D7 for B4 Slice 1, parallel
in force to `docs/B1_REPLAN_BOUNDARY.md §12` / `B2 §12` / `B3
§12`. The residual unresolved items — mostly runtime-scope
questions that cannot be answered before the contract ships —
are collected in §15 as a narrow open-question set, not as
re-negotiable design axes.

---

## 1. Purpose

Define the boundary within which the B4 *Agent-visible memory*
experiment branch may later be implemented, so that:

- Path C-min (Phases 0–3), B1 (Replan), B2 (Event correlator),
  and B3 (Cross-session cumulative memory) remain fully intact
  and regression-clean.
- B4 code is strictly additive over the existing three-layer
  separation (Path B raw → Path C session overlay → Path C
  session artifact), matching the additive pattern used by
  `src/replan/`, `src/correlator/`, and
  `src/learning/cumulative_memory.py`.
- B4 never becomes a vehicle for rewriting Path C-min, rewriting
  B3 loader semantics, expanding the adaptive-gate consumer
  surface, widening any agent output schema, elevating
  natural-language memory summaries to authoritative truth, or
  smuggling memory into the `baseline_event_result` shadow.
- B4 is framed and reviewed as an **experiment branch**, not as
  the "next mainline phase" of Path C-min. A future decision to
  promote B4 findings onto the mainline is an owner call made
  *after* experiment data exists — not implicit in landing B4.
- A future reviewer can answer "is this PR inside B4 Slice N
  scope?" from this file alone, not from conversation history.

## 2. Why B4 is next, and why it is a separate experiment branch

Path C-min closes the single-session decision loop.
B1 closes bounded temporal replanning within a single event.
B2 closes same-session compound-pattern observability.
B3 closes cross-session legitimate memory reuse **behind the
adaptive policy gate** — the adaptive gate is still the one and
only consumer of `MemoryRecord` rows.

B4 is the first branch that **intentionally crosses the
agent-prompt boundary that B1/B2/B3 all structurally preserved**.
Until B4, no `MemoryRecord`, no `MemorySummary`, no
`correlation_context`, and no cumulative memory row has ever
been visible to an agent prompt; `src/agents/*` has never
imported from `src/learning/*`, `src/correlator/*`,
`src/replan/*`, or any overlay layer. B3 §9 names this
separator explicitly:

> B3 = what the *adaptive policy gate* sees as its historical
> row set can legitimately come from prior sessions.
> B4 = what an *agent prompt* sees can include memory-derived
> content.

This separator is structural, not cosmetic. Crossing it has
three properties that make it incompatible with a "small follow-
on slice to B3" framing:

1. **New consumer layer.** Agents consume text; memory is
   structured. B4 must *interpret* memory into a prompt-shaped
   artifact. That interpretation is a new code surface with its
   own contract, not an extension of B3's loader.
2. **New truth-leakage surface.** Once memory is visible to an
   agent prompt, the agent can paraphrase it, generalize it, or
   misquote it in `GovernanceOutput.cost_summary /
   confidence_note / rationale_trace / situational_explanation`.
   Those are already the five forbidden-as-truth natural-
   language fields the existing B2/B3 no-NL-truth scans guard
   against. B4 adds upstream pressure on them.
3. **New comparability surface.** A B4-enabled run is not
   directly comparable to a B4-disabled run at the governance-
   output layer, because the agent's inputs differ. The compare
   surface must be extended *explicitly* (new third variant) —
   not by overwriting existing baselines.

Because of (1)–(3), B4 is an **independent, additive experiment
branch beside Path C-min**, not a B3 follow-on. It has its own
boundary doc (this file), its own contract draft
(`docs/B4_AGENT_VISIBLE_MEMORY_CONTRACT_DRAFT.md`), its own file
map (`docs/B4_AGENT_VISIBLE_MEMORY_FILE_MAP.md`), its own
forbidden-modification list, its own AST-scan additions, and
its own acceptance gates. It does NOT "consolidate" with
B1/B2/B3.

Equally: calling B4 a "small tweak to the operations agent" or
"a prompt-engineering pass" is a framing error that the owner
has already rejected (see closeout memo §7 point 5). B4 is a
deliberate experiment that introduces one new crossing in one
controlled location, and any PR that smuggles additional
crossings under the B4 label is out-of-scope.

## 3. In-scope (across the B4 slice ladder)

B4 implementation is allowed to do the following. Items marked
**[landed]** are on ``main`` under the slice indicated in §13;
items marked **[deferred]** are scoped to named future slices
and are subject to the D8–D11 ordering. "Candidate" framings
from the Slice 0 draft have been replaced by landed reality
below.

1. **[landed, Slice 1 + 2A]** A new Path C subpackage
   ``src/agent_memory/`` — a memory-to-prompt adaptation layer
   that consumes ``EpisodicMemory`` / ``MemoryRecord`` rows and
   produces a prompt-shaped artifact. It adds no second memory
   consumer for the adaptive gate and never writes memory.
2. **[landed, Slice 1]** Three new schemas local to that
   subpackage: ``AgentMemoryExampleRef`` 1.0,
   ``AgentMemoryContext`` 1.0, ``AgentMemoryExperimentConfig``
   1.0. Registered in ``PATH_C_SCHEMA_REGISTRY.md``. Fields
   listed in ``docs/B4_AGENT_VISIBLE_MEMORY_CONTRACT_DRAFT.md
   §9``. ``MemoryRecord`` / ``MemoryQuery`` / ``MemorySummary``
   stay at 1.0; B4 adds no ``cross_session_origin`` flag or any
   other field to those schemas.
3. **[landed, Slice 2B]** One narrow, gated injection point in
   the operations agent's LLM prompt path. The injection is a
   single additive hunk inside ``_build_ops_llm_user_prompt``
   guarded by the five-condition ``_b4_should_inject``
   predicate. The governance agent module is not touched under
   any slice; D1 locks operations as the sole target.
4. **[landed, Slice 1]** The experiment configuration surface
   ``AgentMemoryExperimentConfig`` — a frozen dataclass
   parallel to ``ReplanConfig`` / ``CorrelatorConfig`` /
   ``CumulativeMemoryConfig`` carrying the injection gate, the
   closed-Literal target-agent / context-source selectors, the
   ``max_recent_examples`` bound, and the closed
   ``allowed_modes`` set. ``enable_agent_visible_memory: bool =
   False`` is the hard default. Full field list in §9.1 of the
   contract draft.
5. **[deferred, RO1 candidate window = Slice 2D4]** An optional
   additive ``SessionEventRecord`` overlay field (e.g.,
   ``agent_memory_context: Optional[AgentMemoryContext] =
   None``) behind a MINOR bump 1.2 → 1.3. D6 still defers this
   decision; no landed slice adds the overlay. Slice 2D3-A took
   the **compare-only** path (D7's three-variant compare
   surface plus an additive sibling block on the compare
   report) and demonstrated it is sufficient to interpret
   experiment results without a per-event overlay; RO1 stays
   open as a future call only if compare-only proves
   insufficient. If sufficient, no ``SessionEventRecord``
   bump ever happens.
6. **[landed, Slice 2D3-A]** An additive, conditional
   ``agent_memory_experiment_summary`` sibling block on
   ``src/session/session_compare.py``, opt-in via the
   ``agent_memory_variant_tags: Optional[Sequence[str]] = None``
   kwarg on ``build_compare_report``. No
   ``COMPARE_REPORT_SCHEMA_VERSION`` bump — conditional-sibling-
   block pattern as in B1 / B2 / B3. Block contents are
   structural-only (variant tags, session_ids, warm-pair
   diverged event ids, fixed notes); no KPI math, no NL
   paraphrase. Harness B4 ON branch emits
   ``compare_report.json`` + ``thesis_report.md`` over the
   locked triplet through this kwarg.
7. **[landed, ongoing]** Tests under ``tests/test_agent_memory_*``
   covering default-off invariance, byte-identity with the flag
   OFF, no-truth-leakage scans, single-agent isolation,
   deterministic replay, compare-surface stability, no reverse
   imports into the adaptive gate, and no writes into
   ``baseline_event_result``. Slice 2D3-A added
   ``tests/test_agent_memory_compare_block.py`` + the harness
   compare/thesis pin flips. Slice 2D3-B added
   ``tests/test_agent_memory_truth_stability.py`` (G5
   exercised-path stability) and
   ``tests/test_agent_memory_runtime_activation.py`` (regression
   pin against the env→GraphState wiring closing again).
   Current test ledger in §13.
8. **[landed, Slice 2D2]** Additive CLI / harness flags
   (``--enable-agent-visible-memory``) guarded by default-off,
   with ``PATH_C_WARM``-only enforcement at the script layer
   (mirrors B3's workflow rule). The flag reaches B4 through
   the public ``run_session(..., agent_memory_config=None)``
   kwarg landed by Slice 2D1 (D8) — **not** by calling private
   helpers directly.
9. **[landed, Slice 2D3-B]** A narrow internal-sideband seam
   on ``src/event_loop.py::_run_reasoning_slice`` (one new
   ``operations_mode: Any = None`` optional kwarg) plus a
   single-line forward in ``event_loop_c._build_path_c_main_
   records``. Path B's call site does not pass the kwarg →
   Path B byte identity preserved. Default-off Path C-min
   (env unset) writes ``"rules"`` into ``GraphState
   ["operations_mode"]`` which the graph node was already
   treating identically to its absent default → no
   downstream byte change. No public surface change, no
   ``operations_mode`` publicization (D9 still holds).

## 4. Explicit out-of-scope

B4 MUST NOT, in any PR labelled B4 Slice 0 / Slice 1 / Slice 2:

1. Modify Path B Tier 1 contracts. `EventPayload`, `EventType`,
   `EventSeverity`, `AffectedEntityRef` (`src/event_schema.py`),
   `ExecutionOutcome` (`src/outcome_schema.py`), `PolicyDecision`
   (`src/policy_gate.py`) stay frozen.
2. Modify Research Core. `src/evaluation.py`,
   `src/action_code_mapper.py`, `data/cases/*.json` stay frozen.
3. Modify any agent **output** schema. `GovernanceOutput`
   (`src/agents/governance_agent.py`), `OperationsOutput`
   (`src/agents/operations_agent.py`), cost-agent outputs, and
   `_governance_meta` shape are all frozen. B4 may extend an
   agent's *input* prompt; it does NOT add fields to the output.
4. Rewrite, refactor, consolidate, "clean up", or otherwise
   modify B1 (`src/replan/*`), B2 (`src/correlator/*`), or B3
   (`src/learning/cumulative_memory.py`,
   `src/learning/episodic_memory.py`,
   `src/learning/memory_schema.py`). A B4 PR that touches any of
   these is out-of-scope regardless of label.
5. Modify any existing B1/B2/B3 test. B4 adds its own test
   files under `tests/test_agent_memory_*` and optionally adds
   parametrizations to `tests/test_replay_byte_identical.py` /
   `tests/test_determinism_stress.py`. It does NOT edit
   existing assertions in those files — only append new cases.
6. Default the experiment ON. `enable_agent_visible_memory`
   defaults to `False` at every surface (module default, dataclass
   default, CLI default, harness default, test-helper default).
   A default-on variant is out-of-scope for B4 — the experiment
   is always opt-in.
7. Inject memory into multiple agents simultaneously in the
   first experiment slice. Dual-agent injection multiplies
   confounds; a single-agent-first experiment is a hard
   boundary (see §8 R4; locked as D1).
8. Introduce multiple injection points inside a single agent's
   prompt (e.g., both system prompt *and* user prompt) in the
   first experiment slice. One injection point at a time.
9. Inject multiple input surfaces simultaneously. The closed
   Literal ``context_source ==
   "structured_summary_plus_recent_examples"`` admits exactly
   one surface (D3). A second surface is a boundary amendment,
   not a slice.
10. Treat an agent's paraphrase of memory as a new truth source.
    `GovernanceTruthRef` / `EffectiveDecisionRef` continue to be
    the only two truth references per event. Any prompt-side
    memory text is input, not authority. The dual-track rule
    holds.
11. Write any memory-derived content into
    `SessionEventRecord.baseline_event_result`. The Path B raw
    shadow is verbatim; B4 adds optional overlay fields only,
    via `model_copy(update=...)` — never in-place.
12. Elevate natural-language `MemorySummary` text (if any B4
    surface produces one) to an authoritative numeric or factual
    claim. A B4 summary, if introduced, is a **prompt-shaped
    artifact** — a hint to an agent, never a KPI input and never
    a truth field.
13. Change `AdaptivePolicyGateConfig` / `decide_policy_adaptive`.
    The adaptive gate is still the only memory consumer on the
    policy path. B4 adds a **second, independent** memory
    consumer on the **agent-prompt** path — these two consumers
    share no code, no config, and no output surface.
14. Read or write `correlation_context` inside the new B4
    subpackage. B4 consumes memory; it does not consume B2's
    correlator sideband. If a later slice wants to surface
    correlator findings to an agent, that is a separate branch
    (not B4, not B2).
15. Add a `session_id`-aware filter inside the adaptive gate,
    or re-plumb B3's loader output through any path other than
    the existing `run_session(initial_memory=...)` seam. The B3
    invariant "loader produces, adaptive consumes" stays.
16. Modify `src/session/digests.py`. `compute_session_id`,
    `digest_memory_records`, `memory_record_id` formulas are
    frozen. If B4 needs a digest fragment, it lives inside the
    existing `config_for_digest` payload as a conditional entry
    (mirroring B1/B2/B3), not as a formula change.
17. Modify `src/session/kpi_calculator.py`. No B4 KPI in any
    slice. Experiment surfacing is structural (sibling block,
    not KPI fields).
18. Introduce wall-clock, `uuid4`, or `data/cases` access
    anywhere inside the new B4 subpackage or its tests.

## 5. Preserved invariants (non-negotiable)

All invariants from `PATH_C_BOUNDARY.md §1`,
`docs/B1_REPLAN_BOUNDARY.md §5`,
`docs/B2_CORRELATOR_BOUNDARY.md §5`, and
`docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §5` stand unchanged under
B4. B4 additionally preserves:

- **Path B raw shadow integrity.**
  `SessionEventRecord.baseline_event_result` remains the
  verbatim Path B record. B4's overlay (if any) is attached via
  `model_copy(update=...)` at a post-finalization seam,
  identically to B2's correlator attach pattern. No in-place
  mutation, no rewrite.
- **Dual-track truth.** `GovernanceTruthRef` +
  `EffectiveDecisionRef` remain the only two truth references
  per event. Any agent-visible memory text is a prompt input,
  not a truth reference.
- **Policy-only learning injection on the gate path.** The
  adaptive policy gate remains the one and only memory
  consumer on the policy path. B4 adds an independent consumer
  on the **agent-prompt path**; it does not widen the gate's
  consumer surface.
- **Deterministic-first.** B4's prompt-builder is a pure
  function of `(EpisodicMemory snapshot, AgentMemoryExperiment
  Config)`. No wall-clock. No `uuid4`. No hash-seed-dependent
  iteration order. No `data/cases` access. Where canonical
  ordering is needed, it uses the existing `(event_timestamp,
  event_id)` sort order.
- **Bounded action set.** B4 does not expand
  `AdaptivePolicyAdjustment.adjustment_type`. `UPGRADE_ONE_LEVEL
  / NO_ADJUSTMENT / COLD_START_FALLBACK` remains the closed set.
- **Structural explainability.** If B4 records what the agent
  was shown, the record is a **structured artifact** (record
  ids, counts, derived structured fields) — not a free-text
  recap. Free-text prompt content may be emitted *to the agent*
  but is not stored verbatim as authoritative session-artifact
  evidence.
- **Feature-flag OFF = pre-B4 byte identity.** When
  `enable_agent_visible_memory=False`, every
  `SessionArtifact.json`, every compare report, every agent
  prompt, every governance output, and every session bytes are
  byte-identical to pre-B4 `main`. This is the load-bearing
  invariant for the whole branch.
- **Compare / report / replay stability.** Pre-B4 compare
  report top-level key set stays byte-identical when the B4
  flag is OFF. New sibling blocks appear only when the B4
  flag is ON. Replay byte identity via `save_session →
  load_session → replay_session_bytes` holds for all mode ×
  B4-flag combinations that are tested.
- **Path C-min identity.** Path C-min remains the mainline.
  B4 is an experiment running alongside it. Merging B4 into
  mainline is not automatic and not implied by landing Slice 1.

## 6. Allowed files to touch (cumulative B4 allowlist)

**Landed in Slices 1 / 2A / 2B / 2C** — the following files are
on ``main``:

- ``src/agent_memory/__init__.py``,
  ``src/agent_memory/agent_memory_schema.py``,
  ``src/agent_memory/agent_memory_config.py``,
  ``src/agent_memory/agent_memory_builder.py``,
  ``src/agent_memory/agent_memory_renderer.py`` — new
  subpackage; see file-map §3.
- ``PATH_C_SCHEMA_REGISTRY.md`` — registered
  ``AgentMemoryExampleRef`` 1.0, ``AgentMemoryContext`` 1.0,
  ``AgentMemoryExperimentConfig`` 1.0. No other bump.
- ``PATH_C_BOUNDARY.md §9`` — B4 cross-reference line added
  alongside B1 / B2 / B3. §1–§8 text unchanged.
- ``tests/test_path_c_import_topology.py`` — scan root
  extended with ``src/agent_memory/``.
- ``tests/test_path_c_schema_frozen.py`` — frozen assertions
  appended for the two new pydantic schemas.
- ``src/agents/operations_agent.py`` (Slice 2B) — single
  additive hunk inside ``_build_ops_llm_user_prompt`` +
  kwarg-only optional parameter threading. Rules-mode
  entry unchanged. Governance / cost agent modules
  untouched.
- ``src/event_loop_c.py`` (Slice 2C) — three private
  helpers + one optional kwarg on
  ``_build_path_c_main_records``; ``run_session`` public
  signature unchanged.
- ``src/event_loop.py::_run_reasoning_slice`` — two
  kwarg-only optional ``Any``-typed parameters threaded
  via ``GraphState`` sideband keys.
- ``src/graph.py::operations_agent_node`` — reads the
  sideband and forwards to ``run_operations_agent_with_meta``.
- ``tests/fixtures/path_c_schema_samples_1_0.json`` +
  ``tests/test_agent_memory_*`` test family +
  ``tests/test_operations_agent_agent_memory_seam.py`` +
  ``tests/test_event_loop_c_agent_memory_internal_wiring.py``.

**Landed in Slice 2D1 (public ``run_session`` exposure —
the one and only D8-admitted path):**

- ``src/event_loop_c.py::run_session`` — gained exactly one
  additive optional kwarg ``agent_memory_config:
  Optional[AgentMemoryExperimentConfig] = None`` (default
  ``None``), threaded into the already-present
  ``_build_path_c_main_records`` kwarg. Default-off byte
  identity for every pre-B4 test combination held. There is
  no parallel caller-layer exposure path: private helpers
  are not a public surface (D8, D10).

**Landed in Slice 2D2 (scripts / harness / CLI):**

- ``scripts/run_session.py``, ``scripts/session_eval_harness.py``
  — single additive ``--enable-agent-visible-memory`` flag
  each, default-off, with ``PATH_C_WARM``-only enforcement at
  the script layer (mirrors B3 D7). The harness emits three
  comparable artifacts (``baseline_static`` /
  ``path_c_warm_policy_only`` /
  ``path_c_warm_agent_visible_memory``) per D7 / H4. The flag
  reaches B4 through the Slice 2D1 public kwarg — **not** by
  calling private helpers directly.

**Landed in Slice 2D3-A (compare-only closure):**

- ``src/session/session_compare.py`` — additive optional
  ``agent_memory_variant_tags: Optional[Sequence[str]] = None``
  kwarg on ``build_compare_report``; conditional
  ``agent_memory_experiment_summary`` sibling block emitted
  iff every named tag is present in ``artifacts``. Mirror
  conditional section in ``render_thesis_markdown``. No
  ``COMPARE_REPORT_SCHEMA_VERSION`` bump.
- ``scripts/session_eval_harness.py`` — B4 ON branch now
  passes ``_B4_EXPERIMENT_VARIANT_TAGS`` to
  ``build_compare_report`` and writes ``compare_report.json``
  + ``thesis_report.md`` over the locked triplet. Caller-side
  opt-in only; no harness-internal compare logic.
- ``tests/test_agent_memory_compare_block.py`` — new file,
  13 tests pinning the conditional-block contract.

**Landed in Slice 2D3-B (runtime activation seam repair):**

- ``src/event_loop.py::_run_reasoning_slice`` — one new
  optional ``operations_mode: Any = None`` kwarg; when
  non-None it is written into ``GraphState["operations_mode"]``.
  Path B's call site does not pass it → Path B byte
  identity preserved.
- ``src/event_loop_c.py::_build_path_c_main_records`` — single
  additional line that forwards the already-resolved
  ``operations_mode`` into the new kwarg. Default-off
  Path C-min (env unset → resolved to ``"rules"``) writes a
  string the graph node was already treating identically to
  its absent default → no downstream byte change.
- ``tests/test_agent_memory_runtime_activation.py`` — new
  file, 3 tests pinning the env→GraphState wiring AND
  guarding against unintended widening of the LLM-dispatch
  surface (env-unset PATH_C_WARM must NOT call the LLM
  gateway).
- ``tests/test_agent_memory_truth_stability.py`` — new
  file, 1 G5 exercised-path stability test that depends on
  the 2D3-B seam being intact (no test-side
  ``_resolve_ops_mode`` monkeypatch).

**Scheduled for Slice 2D4 (optional persisted overlay) —
deferred behind RO1; runs only if compare-only proves
insufficient:**

- ``src/session/session_schema.py`` — optional additive
  ``agent_memory_context: Optional[AgentMemoryContext] = None``
  on ``SessionEventRecord``, MINOR bump 1.2 → 1.3.
- ``docs/path_c_thesis_alignment.md`` — optional B4 addendum.

The future B4 PR may *not* additively modify:

- `src/event_schema.py`, `src/outcome_schema.py`,
  `src/policy_gate.py` — frozen Tier 1.
- `src/learning/memory_schema.py`, `src/learning/episodic_
  memory.py`, `src/learning/cumulative_memory.py` —
  B3's frozen surfaces stay unchanged.
- `src/adaptive/*` — no consumer change on the policy-gate
  path. B4 does not teach the gate a new rule.
- `src/replan/*` — no coupling.
- `src/correlator/*` — no coupling.
- `src/session/session_schema.py` beyond at most one optional
  additive field (see §3 point 5).
- `src/session/kpi_calculator.py` — no B4 KPI.
- `src/session/digests.py` — no digest formula change.
- Any existing agent's **output schema** (`GovernanceOutput`,
  `OperationsOutput`, cost-agent output). B4 modifies prompt
  *input*, not agent *output*.

## 7. Forbidden files / forbidden modifications

B4 MUST NOT touch, in any PR:

- `src/evaluation.py`, `src/action_code_mapper.py`,
  `data/cases/*.json` — Research Core.
- `src/event_schema.py` — `EventPayload`, `EventType`,
  `EventSeverity`, `AffectedEntityRef`.
- `src/outcome_schema.py` — `ExecutionOutcome`.
- `src/policy_gate.py` — `PolicyDecision`, `decide_policy`.
- `src/execution_adapters.py`.
- `src/event_loop.py` (Path B core) — Slices 2C and 2D3-B
  added one and one optional ``Any``-typed kwarg respectively
  to ``_run_reasoning_slice`` (``agent_memory_context`` /
  ``agent_memory_config`` in 2C; ``operations_mode`` in
  2D3-B); each is written into ``GraphState`` only when
  non-None. Path B's call site at ``run_event_loop`` passes
  none of them → Path B byte identity preserved. Beyond
  these three additive optional kwargs, ``event_loop.py``
  is otherwise frozen for B4.
- `src/graph.py` node wiring — Slice 2C added a
  ``GraphState`` sideband read inside ``operations_agent_node``
  (``_agent_memory_context`` / ``_agent_memory_config``);
  the existing ``state.get("operations_mode") or "rules"``
  read is the surface 2D3-B exploits without modification.
  Beyond the 2C sideband read, ``graph.py`` is otherwise
  frozen for B4.
- `src/outcome_store.py`.
- `src/learning/memory_schema.py` — `MemoryRecord`,
  `MemoryQuery`, `MemorySummary` stay at 1.0.
- `src/learning/episodic_memory.py` — append-only + canonical
  order stay exactly as today.
- `src/learning/cumulative_memory.py` — B3 loader stays
  untouched. B4 may *read* from its output but does not modify
  its body, its signature, or its digest contribution.
- `src/correlator/*` — every file, unchanged.
- `src/replan/*` — every file, unchanged.
- `src/adaptive/*` — every file, unchanged.
- `src/session/session_schema.py` beyond at most one optional
  additive field (if needed).
- `src/session/digests.py`.
- `src/session/kpi_calculator.py`.
- The **output schemas** of any agent — `GovernanceOutput`,
  `OperationsOutput`, and any cost-agent output class stay
  frozen.

For the single agent module B4 eventually modifies (one of
`src/agents/operations_agent.py` or
`src/agents/governance_agent.py`), the modification must be:

- Confined to the existing `_build_..._prompt` helper (or its
  equivalent user/system prompt builder).
- A single additive hunk guarded by an explicit `if
  config.enable_agent_visible_memory:` check.
- A no-op producing byte-identical prompt text when the flag is
  OFF — pinned by a test that captures the full prompt-input
  sequence under `enable_agent_visible_memory={False,True}`.

Forbidden modification classes (byte-level):

- Any change that causes `BASELINE_STATIC` mode to produce a
  byte non-equal `SessionArtifact` for a given seed/event
  stream, under any B4 flag combination.
- Any change that causes `PATH_C_COLD` / `PATH_C_WARM` with
  `enable_agent_visible_memory=False` to diverge from current
  behavior byte-for-byte, under any other-feature flag
  combination (including B1 replan, B2 correlator, B3
  cumulative memory).
- Any change to the canonical JSON byte layout of Phase-3
  compare reports under default harness flags (default =
  `enable_agent_visible_memory=False`).
- Any change to an existing agent's **output** bytes under
  `enable_agent_visible_memory=False`.
- Any change to `_governance_meta` shape or semantics.
- Any change to `MemoryRecord` observable field set or order.

## 8. B4-specific risks (and their mitigations)

| # | Risk | Mitigation (mandatory for B4 implementation PR) |
|---|---|---|
| R1 | **Policy-only boundary pollution.** B4's prompt-builder drifts into also mutating adaptive-gate behavior (e.g., sharing a summary cache, reusing a filter), widening the single-consumer rule. | New B4 subpackage is a **separate** consumer layer. AST scan asserts `src/adaptive/*` does not import the B4 subpackage and the B4 subpackage does not import `src/adaptive/*`. The adaptive gate's input surface (`memory`, `query`) is not edited. |
| R2 | **Truth leakage via NL summary.** Agent paraphrases B4 memory context and the paraphrase appears in `GovernanceOutput.cost_summary / confidence_note / rationale_trace / situational_explanation / alternative_actions` as if authoritative. | B4 treats any summary text as **input hint only**, never stored as truth. A test asserts `GovernanceTruthRef` / `EffectiveDecisionRef` bytes are unchanged across `enable_agent_visible_memory={False,True}` on a *controlled* input set (governance-truth invariance on identical underlying facts). The five NL governance fields remain under the existing no-NL-truth discipline. |
| R3 | **Comparability loss.** Turning B4 on for `PATH_C_WARM` invalidates the existing 2-way baseline vs path_c_warm compare. | The harness is extended to emit **three** comparable artifacts: `baseline_static`, `path_c_warm` (policy-only, B4 OFF), `path_c_warm` (B4 ON). The pre-B4 2-way compare stays byte-identical when B4 is OFF. See §6 of the contract draft for the 3-variant compare surface. |
| R4 | **Multi-variable experiment contamination.** A slice ships dual-agent injection, dual-input-surface, or dual-gating-axes simultaneously; results become uninterpretable. | Single-agent, single-input-surface, single-injection-point are hard boundaries enforced by D1 (operations-only), D3 (one closed ``context_source``), D4 (single additive hunk in one prompt builder). Expanding any axis is a separate owner-approved boundary amendment. |
| R5 | **Workflow rule drift.** B4 is turned on for `BASELINE_STATIC` or `PATH_C_COLD`, or for a mode that didn't receive cumulative memory, contaminating the thesis-comparability invariant established by B3. | Mode gating is a caller-layer workflow rule (parallel to B3 D7): harness attaches B4 only to the variant it is experimenting on; other modes receive the B4-OFF path. Enforced at script layer, not inside `run_session`. |
| R6 | **Replay / determinism breakage.** Non-deterministic iteration, wall-clock use, or `uuid4` in the prompt-builder or the experiment-summary builder causes replay byte drift. | The B4 subpackage is under the Path C AST scan. Window / ordering math uses existing canonical sort keys. The prompt-builder is a pure function of `(EpisodicMemory snapshot, AgentMemoryExperimentConfig)`. Subprocess-level PYTHONHASHSEED determinism tests are added for every B4 surface that emits bytes. |
| R7 | **Digest drift under flag OFF.** B4 accidentally contributes to `config_for_digest` even when disabled, changing `session_id` on pre-B4 inputs. | Any B4 `config_for_digest` fragment is emitted **only** when `enable_agent_visible_memory=True` AND the config is actually non-default (conditional-fragment pattern from B1/B2/B3). A test asserts `session_id` bytes are unchanged on pre-B4 inputs when B4 flag is OFF, across all other flag combinations. |
| R8 | **Silent shadow mutation.** The prompt-builder accidentally receives a mutable `SessionEventRecord` and writes into `baseline_event_result`. | B4 reads `EpisodicMemory` and (if enabled) optional overlay fields via **by-value** access; any overlay attachment uses `model_copy(update=...)`. A test asserts `baseline_event_result` bytes are byte-identical across `enable_agent_visible_memory={False,True}`. |
| R9 | **Agent-output schema creep.** A B4 reviewer argues for "just one field on `GovernanceOutput`" to record the experiment outcome. | Agent output schemas are on the forbidden-modification list (§7). The experiment outcome, if recorded, lives on a new optional B4 overlay field on `SessionEventRecord` (1.2 → 1.3 only if needed), not on any agent output. |
| R10 | **B4 drifts into B5 / frontend.** A B4 PR adds a React or API surface for agent-visible memory. | No FastAPI, no React, no `app.py`, no `src/api/*` changes under B4. Surfacing is via the compare report sibling block only. |
| R11 | **Cross-branch coupling.** B4 imports from `src/correlator/` or `src/replan/` to co-surface findings in the agent prompt. | AST scan asserts the B4 subpackage does not import from `src/correlator/`, `src/replan/`, or `src/session/session_compare.py`. Surfacing correlator or replan findings to agents is a separate branch requiring its own boundary doc. |
| R12 | **"Quiet promotion."** B4 lands with default-on for a particular mode ("because the experiment showed it helps"), bypassing the experiment framing. | Default-off is a hard invariant for B4 across all surfaces. Promoting B4 findings onto the mainline is a separate owner decision made *after* experiment data exists, not a B4 slice. |

## 9. How B4 stays separate from B3 and B5

Structural separators, enforced by tests:

- **B4 vs B3.** B3's loader produces `EpisodicMemory` consumed
  exclusively by the adaptive gate. B4's prompt-builder
  consumes `EpisodicMemory` (possibly augmented by B3) and
  produces a prompt-shaped artifact for **one** agent.
  - The B4 subpackage does NOT import
    `src/learning/cumulative_memory.py` directly. It receives
    an already-assembled `EpisodicMemory` via its caller (same
    shape B3's adaptive-gate path receives). This keeps B3
    loader semantics unchanged and keeps B4 independent of how
    the memory was assembled.
  - The B4 subpackage does NOT import `src/agents/*` types for
    the purpose of rewriting agent outputs. It emits a
    prompt-shaped artifact consumed by the single B4-modified
    agent's `_build_..._prompt` helper.
- **B4 vs B5 (frontend).** B4 produces a compare-report sibling
  block. It does NOT add React components, FastAPI routes, or
  visualization code. Any user-facing visualization of
  agent-visible memory is B5 territory.
- **B4 vs B2 / B1.** B4 does not read `correlation_context` or
  `replan_trace` / `replan_triggers`. If a later experiment
  wants to compose B2 or B1 findings into an agent prompt,
  that is a separate branch under its own boundary doc.

A B4 PR that enables any cross-branch import, second-agent
injection, default-on behavior, or agent-output schema change
is out-of-scope regardless of label.

## 10. Rollback rules

If the first B4 implementation PR, or any follow-up, causes any
of the following, it MUST be reverted (not patched forward):

- A Path C-min / B1 / B2 / B3 test regresses: any test
  currently passing on `main` in the files listed under
  `docs/B3_CUMULATIVE_MEMORY_FILE_MAP.md §1` plus every
  `tests/test_replan_*.py`, `tests/test_correlator_*.py`, and
  `tests/test_cumulative_memory_*.py`.
- `BASELINE_STATIC` session-artifact bytes change for any seed
  that passed before, under any B4 flag combination.
- `PATH_C_COLD` / `PATH_C_WARM` session-artifact bytes change
  for any seed that passed before, when
  `enable_agent_visible_memory=False`, under any other-feature
  flag combination.
- Canonical JSON of the existing Phase-3 compare report
  changes under default harness flags (default =
  `enable_agent_visible_memory=False`).
- Any agent's prompt-input bytes change, or any agent's
  output bytes change, when `enable_agent_visible_memory=False`.
- The AST import-topology scan gains a new allowed import or a
  new exception. New forbidden imports are permitted;
  weakening the scan is not.
- `GovernanceTruthRef` / `EffectiveDecisionRef` bytes change
  on a controlled input set across
  `enable_agent_visible_memory={False,True}` — this would
  indicate truth leakage via NL summary.

Partial B4 landings must be rolled back as a whole — no
half-landed prompt-builder, no "docs landed but schema not",
no "schema landed but scan not".

## 11. Acceptance gates for future implementation

The first B4 runtime PR (Slice 1+) will be considered
acceptable only if ALL of the following hold simultaneously.
These gates translate the invariants in §5 and the risks in §8
into test-surface obligations.

**Status legend:** [exercised] = the gate has at least one
landed-slice test asserting it on ``main``; [exercised, see
…] = additionally pinned by the named test family.

- **G1 Contracts first.** Any new B4 schema lands as a frozen
  shape with frozen tests before any runtime logic. Registered
  in `PATH_C_SCHEMA_REGISTRY.md`.
- **G2 Default-off byte identity.** When
  `enable_agent_visible_memory=False`, `SessionArtifact.json`,
  compare report JSON, and every agent's full prompt-input
  sequence are byte-identical to pre-B4 `main` across all seed
  × mode × other-flag combinations currently tested.
- **G3 Single-agent injection.** A test asserts that exactly one
  agent module reads from the B4 subpackage (or receives a B4
  prompt-shaped artifact). No dual-agent injection in Slice 1.
- **G4 Single-surface injection.** The landed input surface
  is ``"structured_summary_plus_recent_examples"`` (closed
  Literal; see §12 D3). A test asserts
  ``AgentMemoryExperimentConfig.context_source`` admits
  exactly that one value and that
  ``KNOWN_AGENT_MEMORY_CONTEXT_SOURCES`` is the matching
  one-element frozenset. Opening the Literal is a boundary
  amendment, not a config tweak.
- **G5 No truth leakage.** [exercised, see
  ``tests/test_agent_memory_truth_stability.py``] A test
  asserts `GovernanceTruthRef` and `EffectiveDecisionRef`
  bytes are unchanged across
  `enable_agent_visible_memory={False,True}` on a controlled
  input set where the underlying operational facts are the
  same, with the operations agent actually reaching its LLM
  path under env=``llm`` (so the seam genuinely fires; the
  2D3-B repair is a precondition for this gate to be
  meaningful — without it the test would be trivially passing
  on a rules-only path). (If the flag *does* change those
  bytes, that must be a consequence of a changed policy
  decision upstream, not a paraphrase appearing in a truth
  field.)
- **G6 No shadow mutation.** A test asserts
  `SessionEventRecord.baseline_event_result` bytes are
  unchanged across `enable_agent_visible_memory={False,True}`.
- **G7 Deterministic prompt-builder.** Subprocess-level
  PYTHONHASHSEED determinism test asserts a B4-enabled session
  produces a byte-identical prompt-input sequence and
  byte-identical `SessionArtifact.json` across fresh processes.
- **G8 No reverse adaptive-gate coupling.** AST scan asserts
  `src/adaptive/*` does not import the B4 subpackage and the
  B4 subpackage does not import `src/adaptive/*`.
- **G9 No cross-branch coupling.** AST scan asserts the B4
  subpackage does not import `src/correlator/*`,
  `src/replan/*`, `src/learning/cumulative_memory.py`, or
  `src/session/session_compare.py`. (It may use
  `src/learning/memory_schema.py` read-only for types.)
- **G10 No agent-output schema change.** AST / source scan
  asserts `GovernanceOutput`, `OperationsOutput`, any
  cost-agent output, and `_governance_meta` shape are
  unchanged.
- **G11 Replay byte identity.** `test_replay_byte_identical`
  passes for every tested combination of
  `enable_agent_visible_memory={False,True}` ×
  `enable_replan={False,True}` ×
  `enable_correlator={False,True}` × cumulative memory
  present/absent.
- **G12 Compare-report surface stability.** [exercised, see
  ``tests/test_agent_memory_compare_block.py``] The pre-B4
  compare report top-level key set stays byte-identical when
  the new ``agent_memory_variant_tags`` opt-in kwarg is
  omitted. A new `agent_memory_experiment_summary` sibling
  block appears only when the kwarg is supplied AND every
  named tag is present in ``artifacts``.
  `COMPARE_REPORT_SCHEMA_VERSION` stays `"1.1"`.
- **G13 3-variant comparability.** [exercised, see
  ``tests/test_session_eval_harness_agent_memory.py``] The
  harness emits three comparable artifacts (`baseline_static`,
  `path_c_warm_policy_only`,
  `path_c_warm_agent_visible_memory`) under the B4 ON branch.
  Pre-B4 2-way compare (default 3-mode set) stays
  byte-identical when B4 is OFF.
- **G14 Honesty rule.** If enabling B4 degrades the thesis
  claim on the target agent, the report reports it honestly.
  No code branch suppresses a negative finding. (Matches B2
  G14 / B3 G12.)

No gate may be waived. A single failing gate blocks the B4
runtime PR.

---

## 12. Owner-fixed decisions for B4 Slice 1 (locked for this turn)

Parallel in force to `docs/B1_REPLAN_BOUNDARY.md §12`,
`docs/B2_CORRELATOR_BOUNDARY.md §12`, and
`docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12`. Structural
consequences are enforced by the Slice 1 frozen tests
(`tests/test_agent_memory_schema_frozen.py`,
`tests/test_agent_memory_contract_no_truth_write.py`) plus the
widened `tests/test_path_c_schema_frozen.py` and
`tests/test_path_c_import_topology.py`. These decisions are
**not renegotiable** as part of B4 Slice 1. A future design that
needs to relax any one of them is a separate, owner-approved
boundary amendment, not a B4 in-scope change.

- **D1 — First experiment target is the operations agent only.**
  B4 v1 touches at most one agent module; that module is
  `src/agents/operations_agent.py`. `src/agents/governance_
  agent.py` is not a B4 target in any Slice 1 or Slice 2 PR.
  Rationale: the operations agent's output schema
  `OperationsOutput` carries no free-text truth-adjacent field,
  so the truth-leakage pressure (R2) is structurally lower; the
  governance agent remains the downstream truth producer and
  therefore stays unchanged so governance-truth invariance (G5)
  on identical facts is tractable to test. Enforced structurally
  by `AgentMemoryExperimentConfig.target_agent: Literal[
  "operations"] = "operations"` and the closed
  `KNOWN_AGENT_MEMORY_TARGETS = frozenset({"operations"})`.

- **D2 — `AgentMemoryContext` is the single B4 agent-visible
  contract surface.** No free-text summary surface; no raw
  `MemoryRecord` list passed into the prompt; no direct
  exposure of the B3 cumulative-memory loader's semantics.
  Enforced by `tests/test_agent_memory_contract_no_truth_write.py`
  (AST scan forbids imports from `agents.*`,
  `session.session_schema`, `correlator.*`, `replan.*`,
  `learning.cumulative_memory` inside `src/agent_memory/`; plus
  `extra='forbid'` on both B4 schemas).

- **D3 — `AgentMemoryContext` shape = aggregate summary +
  capped `recent_examples`.** Aggregate fields mirror
  `MemorySummary` 1.0 shape names (`matched_records`,
  `cold_start`, `auto_execute_success_rate`,
  `sla_preservation_rate`, `action_type_distribution`,
  `avg_cost`, `query_signature`) for readability, but
  `AgentMemoryContext` **does not inherit** from
  `MemorySummary` — the two serve different consumers
  (adaptive gate vs. agent prompt). `recent_examples` is
  capped at `MAX_AGENT_MEMORY_EXAMPLES = 3`; empty list is
  valid (captures cold-start / no-match case structurally).
  No free-text `rationale` / `explanation` / `confidence` /
  `summary_paragraph` field; no LLM-written memory summary.

- **D4 — Placement is the new subpackage
  `src/agent_memory/`.** Slice 1 ships the contract skeleton
  (`agent_memory_schema.py`, `agent_memory_config.py`, and an
  `__init__.py` re-export surface). **Slice 1 does NOT touch
  `src/agents/operations_agent.py`.** The single future
  operations-agent injection seam, when it lands in a later
  slice, is admissible **only** as one additive hunk inside
  the existing `_build_..._prompt` helper guarded by
  `if config.enable_agent_visible_memory:`; the modification
  must produce byte-identical prompt text when the flag is
  OFF.

- **D5 — Gating via `AgentMemoryExperimentConfig`.**
  `enable_agent_visible_memory: bool = False` is a hard
  default. `target_agent: Literal["operations"]`,
  `context_source: Literal["structured_summary_plus_recent_
  examples"]`, `allowed_modes: frozenset[str] = frozenset(
  {"PATH_C_WARM"})` are all closed sets in Slice 1.
  `__post_init__` enforces closed-set membership and the
  `1 <= max_recent_examples <= MAX_AGENT_MEMORY_EXAMPLES`
  range. Mode-gating itself (the caller refusing to attach a
  non-default config to a mode outside `allowed_modes`) is a
  future runtime slice's responsibility; Slice 1 freezes the
  allowed values only. Slice 1 does NOT add a CLI flag and
  does NOT wire anything into the harness.

- **D6 — No `SessionEventRecord` bump in Slice 1.** The
  per-event overlay field `agent_memory_context` is **not**
  added in Slice 1. `SessionEventRecord` stays at 1.2.
  Compare-report visibility is also deferred;
  `COMPARE_REPORT_SCHEMA_VERSION` stays at `"1.1"`; no B4
  KPI is added, `SessionKPIs` stays at 1.1. The B4 contracts
  stand alone so a later slice owns the audit-surface wiring
  decision without blocking Slice 1's freeze.

- **D7 — Future compare surface is three variants.**
  When the eventual Slice ≥ 2 compare-visibility / harness
  work lands, the harness will emit three independently
  comparable artifacts: `baseline_static`, `path_c_warm`
  (policy-only, B4 OFF), and `path_c_warm` + agent-visible
  memory experiment (B4 ON). Pre-B4 2-way compare stays
  byte-identical when B4 is OFF. This decision is locked at
  the docs / contract layer in Slice 1; no `session_compare`
  code is edited in Slice 1.

These seven decisions close the Slice 0 candidate-axes surface
(C1 → D2+D3; C2 → D4; C3 → D1; C5 → D5; C6 → D7; C4 deferred
via D6; C7 deferred — see §15). Future slices inherit the locks
unchanged.

---

### D8–D11 — public exposure shape (locked in Slice 2D0, docs-only)

The runtime slices 2A / 2B / 2C landed B4 as an **internal**
experiment branch: reachable only through the private kwarg on
``_build_path_c_main_records`` and through direct test drivers.
D8–D11 fix the shape of the next step, where B4 becomes
reachable through the Path C public surface.

- **D8 — Public exposure goes through a single additive
  optional kwarg on ``run_session(...)``.**
  The next-slice public signature will be:
  ```python
  def run_session(
      *,
      seed, mode,
      events=..., events_source="demo_stream",
      initial_twin_state=None, initial_memory=None,
      adaptive_config=None, replan_config=None,
      correlator_config=None,
      agent_memory_config: Optional[AgentMemoryExperimentConfig] = None,
  ) -> SessionArtifact
  ```
  The default stays ``None`` (master gate still OFF). No other
  alternative is admissible — specifically NOT:
    - ``scripts/*`` / harness / CLI calling ``_build_path_c_
      main_records`` directly (private helpers are not a
      stable caller surface);
    - a CLI-only side channel that never reaches
      ``run_session`` (breaks replay / determinism story);
    - a second ``run_session``-like public entry point.
  Rationale: B4 must be a reviewable experiment branch, not
  an escape hatch reachable only from tests or from one script.
  The single-additive-kwarg shape mirrors the precedent set by
  ``replan_config`` (B1) and ``correlator_config`` (B2).

- **D9 — operations_mode stays env-only under B4.**
  ``run_session`` will NOT grow an ``operations_mode`` public
  kwarg as part of B4. The existing
  ``SUPPLY_CHAIN_TWIN_OPERATIONS_MODE`` env var continues to be
  the sole configuration surface for rules-vs-llm operations
  dispatch. Rationale: B4's public exposure must stay **one
  additive kwarg** (D8); adding a second unrelated publicizer
  would widen the B4 diff into an "operations mode
  publicization" line of work that has not been owner-approved.
  This is not a permanent ban — a later boundary amendment
  may publicize ``operations_mode`` if a non-B4 owner need
  arises — but it is explicitly out of scope for every B4
  slice.

- **D10 — scripts / harness / CLI exposure is a separate
  downstream slice after D8 lands.**
  Strict ordering:
    1. Boundary lock (this slice, 2D0).
    2. Public ``run_session(..., agent_memory_config=None)``
       wiring (next slice, 2D1-equivalent).
    3. Harness + ``scripts/run_session.py`` + ``scripts/
       session_eval_harness.py`` additive flags (subsequent
       slice, 2D2-equivalent).
  Merging steps 2 and 3 into one PR is out of scope. The
  harness / CLI slice may introduce ``--enable-agent-visible-
  memory`` and friends only after ``run_session`` has already
  grown the kwarg. Default-off byte identity is a hard
  invariant at every step.

- **D11 — Slice 2D0 is docs + header comments only.**
  This slice updates the B4 boundary / contract / file-map
  documents and the design-anchor docstring in
  ``src/event_loop_c.py``. No function signature changes, no
  runtime behavior changes, no test additions or modifications,
  no registry changes, no ``PATH_C_BOUNDARY.md`` changes, no
  new public kwarg. The next slice (D10 step 2) is the first
  slice permitted to touch ``run_session``'s public signature
  for B4.

D8–D11 close the residual questions RO11 (public exposure
shape) and RO12 (operations_mode scope). They are not
renegotiable as part of the next-slice work: any PR that
publicizes B4 through a path other than the single optional
kwarg on ``run_session`` is out-of-scope regardless of label.

---

## 13. Slice delivery ledger (cumulative, Slice 1 → 2C)

Each slice landed as a separate PR on `main`. Rows marked [x]
are landed; no row has been rolled back.

**Slice 1 — contracts + frozen tests:**
- [x] `src/agent_memory/__init__.py`,
      `agent_memory_schema.py`, `agent_memory_config.py`.
- [x] `AgentMemoryExampleRef` (1.0) + `AgentMemoryContext`
      (1.0) registered in `PATH_C_SCHEMA_REGISTRY.md`.
- [x] `AgentMemoryExperimentConfig` (1.0 dataclass contract)
      registered in `PATH_C_SCHEMA_REGISTRY.md`.
- [x] `SessionEventRecord` unchanged at 1.2 (D6).
- [x] `SessionKPIs` unchanged at 1.1 (D6).
- [x] `COMPARE_REPORT_SCHEMA_VERSION` unchanged at `"1.1"`
      (D6).
- [x] `PATH_C_BOUNDARY.md §9` gains the B4 cross-reference.
- [x] `tests/fixtures/path_c_schema_samples_1_0.json`
      extended.
- [x] `tests/test_path_c_schema_frozen.py` extended.
- [x] `tests/test_path_c_import_topology.py` extended with
      `src/agent_memory/` in the scan roots.
- [x] `tests/test_agent_memory_schema_frozen.py`,
      `tests/test_agent_memory_contract_no_truth_write.py`,
      `tests/test_agent_memory_reverse_import_forbidden.py`
      added.

**Slice 2A — pure builder + deterministic renderer:**
- [x] `src/agent_memory/agent_memory_builder.py`
      (`build_agent_memory_context`, pure function; R3 cold-
      start semantic; R4 selected-tail ordering).
- [x] `src/agent_memory/agent_memory_renderer.py`
      (`render_agent_memory_context`, pure; R5 / R6 locked
      format; config argument accepted for signature
      symmetry but intentionally unread).
- [x] `tests/test_agent_memory_builder.py`,
      `tests/test_agent_memory_renderer.py` (subprocess-
      level PYTHONHASHSEED determinism pinned).
- [x] No runtime caller yet.

**Slice 2B — operations-agent single-point prompt seam:**
- [x] `src/agents/operations_agent.py` — single additive
      hunk inside `_build_ops_llm_user_prompt` gated by
      `_b4_should_inject`; `_B4_SECTION_HEADER` /
      `_B4_SECTION_FOOTER` module constants; two kwarg-only
      optional parameters threaded through
      `_enrich_ops_with_llm`, `run_operations_agent_llm`,
      `run_operations_agent_modeful`,
      `run_operations_agent_with_meta`.
- [x] Rules-mode path (`run_operations_agent`) signature
      unchanged; governance / cost agent modules unchanged.
- [x] `tests/test_operations_agent_agent_memory_seam.py`,
      `tests/test_agent_memory_single_agent_injection.py`
      added.

**Slice 2C — event_loop_c internal caller wiring:**
- [x] `src/event_loop_c.py` gained
      `_build_agent_memory_query_for_event` (W6 event-type-
      only query), `_maybe_build_agent_memory_context` (W4
      five-condition gate), `_resolve_operations_mode_from_env`
      (env-only dispatch, D9), and one optional
      `agent_memory_config` kwarg on
      `_build_path_c_main_records`.
- [x] `src/event_loop.py::_run_reasoning_slice` gained two
      optional kwarg-only parameters typed `Any` that
      thread via `GraphState["_agent_memory_context"]` /
      `["_agent_memory_config"]` sideband keys (absent when
      OFF).
- [x] `src/graph.py::operations_agent_node` reads the
      sideband and passes it to
      `run_operations_agent_with_meta`.
- [x] `run_session(...)` public signature UNCHANGED;
      `SessionConfig` UNCHANGED; `SessionEventRecord`
      UNCHANGED; no digest fragment.
- [x] `tests/test_event_loop_c_agent_memory_internal_wiring.py`
      added (W5 pre-current-event memory, W4 gate matrix,
      W3 public-API-unchanged pin, env-resolver behavior,
      spy-based kwarg verification, no-side-effect scans).

**Slice 2D0 — boundary amendment + landed-status docs patch
(docs-only):**
- [x] D8 / D9 / D10 / D11 locked in §12 above.
- [x] RO7 / RO11 / RO12 closed in §15 below.
- [x] ``src/event_loop_c.py`` module-level docstring
      updated to reflect B4 2B/2C reality (B4 does reach an
      agent prompt; Path C-min mainline policy-only-injection
      statement rewritten to be accurate under both layers).
- [x] No runtime / signature / test change.

**Slice 2D1 — public ``run_session`` kwarg (LANDED):**
- [x] ``run_session`` gained exactly one additive optional
      kwarg ``agent_memory_config: Optional[AgentMemoryExperiment
      Config] = None`` (D8 / P1).
- [x] Forwarded as a single line into the existing
      ``_build_path_c_main_records(..., agent_memory_config=
      ...)`` kwarg (P3). No second caller path.
- [x] ``operations_mode`` stayed env-only; no public kwarg
      for it (D9 / P2).
- [x] ``SessionConfig`` / ``SessionEventRecord`` /
      ``session_compare`` / ``SessionKPIs`` / ``digests``
      untouched (P6).
- [x] Scripts / harness / CLI untouched (P7).
- [x] ``tests/test_run_session_agent_memory_public_kwarg.py``
      added (default-off artifact equivalence; B4 activation
      only under the full W4 gate; public→internal
      forwarding; signature closed to a single kwarg;
      scripts left untouched).
- [x] Slice 2C's W3 "public signature unchanged" pin
      superseded by the 2D1 single-kwarg pin in
      ``tests/test_event_loop_c_agent_memory_internal_
      wiring.py``.

**Slice 2D1.x — conditional ``agent_memory`` digest fragment
(LANDED, this slice):**
- [x] New private helper
      ``_agent_memory_config_digest_fragment(config)`` (F1 /
      F3), parallel to ``_replan_config_digest_fragment`` /
      ``_correlator_config_digest_fragment``.
- [x] ``config_for_digest["agent_memory"]`` emitted iff
      ``agent_memory_config is not None and
      agent_memory_config.enable_agent_visible_memory``
      (F1). Default-off runs keep their pre-B4
      ``session_id`` byte-identical.
- [x] Fragment content (F3): ``enable_agent_visible_memory`` /
      ``target_agent`` / ``context_source`` /
      ``max_recent_examples`` / ``allowed_modes`` (sorted
      list) / ``schema_version``.
- [x] Fragment is env- and mode-insensitive (F2): the same
      enabled config produces the same fragment regardless
      of ``SUPPLY_CHAIN_TWIN_OPERATIONS_MODE`` or whether
      the session mode is ``PATH_C_WARM`` vs ``PATH_C_COLD``.
- [x] ``AgentMemoryExampleRef`` / ``AgentMemoryContext`` /
      ``AgentMemoryExperimentConfig`` added to
      ``_SCHEMA_VERSIONS`` dict in ``event_loop_c.py`` so
      ``SessionArtifact.schema_versions`` audits the B4
      contract a session ran against.
- [x] RO2 closed (see §15).
- [x] Docs (boundary / contract draft / file map) and
      ``event_loop_c.py`` module docstring +
      ``tests/test_event_loop_c_agent_memory_internal_
      wiring.py`` top-of-file note synced.

**Slice 2D1.xa — ``_SCHEMA_VERSIONS`` artifact-registry audit
(LANDED, corrective patch on 2D1.x):**
- [x] Removed ``agent_memory_example_ref`` and
      ``agent_memory_context`` from
      ``event_loop_c._SCHEMA_VERSIONS`` per C1: neither schema
      appears inside a serialized ``SessionArtifact`` under any
      landed slice (D6 / RO1 still defers the overlay).
- [x] Retained ``agent_memory_experiment_config`` per C2
      (B1/B2 precedent: config-level keys that contribute to
      ``config_for_digest`` stay in the artifact-level
      registry).
- [x] ``tests/test_run_session_agent_memory_public_kwarg.py``
      §9 added: 7 tests pinning default-off
      ``schema_versions`` identity, C1 exclusion of
      artifact-nested schemas, C2 retention of the config-level
      key, and precedent symmetry with ``replan_config`` /
      ``correlator_config``.

**Slice 2D2 — scripts + harness exposure (LANDED, this slice):**
- [x] ``scripts/run_session.py`` — new CLI flag
      ``--enable-agent-visible-memory`` (H1). When set, the CLI
      enforces ``PATH_C_WARM`` at the script layer via
      ``parser.error(...)`` (H2) and builds exactly
      ``AgentMemoryExperimentConfig(enable_agent_visible_memory=True)``
      (H3). Forwarded through the Slice 2D1 public kwarg
      (P3). No target / input-surface / operations-mode CLI
      flags exposed (H1 / H5).
- [x] ``scripts/session_eval_harness.py`` — new CLI flag
      ``--enable-agent-visible-memory`` + additive optional
      ``enable_agent_visible_memory: bool = False`` kwarg on
      ``run_eval_harness(...)``. Default OFF keeps the pre-2D2
      3-mode harness behavior (``baseline_static`` /
      ``path_c_cold`` / ``path_c_warm`` + compare / thesis
      reports) byte-identical. ON switches to the locked
      three-variant experiment set (H4): ``baseline_static`` /
      ``path_c_warm_policy_only`` /
      ``path_c_warm_agent_visible_memory``, tags exposed as
      the module constant ``_B4_EXPERIMENT_VARIANT_TAGS``. Only
      the third variant receives an enabled
      ``AgentMemoryExperimentConfig``. Operations-mode stays
      env-only (H5).
- [x] Compare-report / thesis-report emission deliberately
      skipped in B4 experiment mode (H6 — superseded in
      Slice 2D3-A; see ledger entry below). The returned
      dict at the time of 2D2 omitted ``compare_report`` /
      ``thesis_report`` fields; Slice 2D3-A restored them via
      the ``agent_memory_variant_tags`` opt-in kwarg without
      touching ``COMPARE_REPORT_SCHEMA_VERSION``.
- [x] Scripts reach B4 exclusively through the public
      ``run_session(..., agent_memory_config=...)`` kwarg. No
      private-helper bypass; pinned by the harness /
      ``_build_path_c_main_records`` spy test.
- [x] ``tests/test_run_session_script_agent_memory_cli.py``
      (11 tests: parser accepts flag, mode-validation matrix,
      config forwarding, no-bypass spy, CLI surface
      constraints).
- [x] ``tests/test_session_eval_harness_agent_memory.py``
      (13 tests: default-OFF preserved, three-variant set in
      ON mode, only third variant gets config, no
      private-helper bypass, no compare-report coupling, no
      operations_mode publicization).
- [x] Slice 2D1's §8 "scripts untouched" pins flipped into
      "scripts reference only the approved B4 flag" pins —
      H1 / H5 authorize this flip.
- [x] No ``SessionEventRecord`` overlay, no
      ``session_compare.py`` edit, no new KPI, no
      ``operations_mode`` publicization.

**Slice 2D3-A — compare-only closure (LANDED):**
- [x] ``src/session/session_compare.py`` — additive
      ``agent_memory_variant_tags: Optional[Sequence[str]] =
      None`` kwarg on ``build_compare_report``. When
      supplied AND every named tag is present in
      ``artifacts``, emits a conditional
      ``agent_memory_experiment_summary`` sibling block;
      omitted otherwise. Block contents are structural-only:
      ``schema_version`` ("1.0"), ``variant_tags``,
      ``session_ids_by_variant``,
      ``agent_visible_vs_policy_only_diverged_event_ids``
      (extracted from ``diverged_events`` and restricted to
      the policy-only ↔ agent-visible warm pair), and a
      fixed ``notes`` string. No KPI math, no NL paraphrase,
      no agent-output read.
- [x] Mirror conditional section in
      ``render_thesis_markdown`` (heading "Agent-visible
      memory experiment (B4)" with variant table + diverged
      event ids); rendered iff the block is present.
- [x] ``COMPARE_REPORT_SCHEMA_VERSION`` UNCHANGED at
      ``"1.1"``; conditional-sibling-block precedent from
      B1 / B2 / B3 applied.
- [x] ``scripts/session_eval_harness.py`` — B4 ON branch now
      passes ``_B4_EXPERIMENT_VARIANT_TAGS`` to
      ``build_compare_report`` and writes
      ``compare_report.json`` + ``thesis_report.md`` over
      the locked triplet. CLI help text updated. The H6
      "no compare/thesis under B4 ON" pin from Slice 2D2
      flipped (with explicit slice-closeout authorization)
      into "B4 ON emits compare + thesis through the
      ``agent_memory_variant_tags`` opt-in" pins.
- [x] ``tests/test_agent_memory_compare_block.py`` (new,
      13 tests): default 3-mode compare omits the block;
      no kwarg → byte-identical; full triplet → block
      present with locked shape; partial triplet → block
      omitted; empty tag list → block omitted; warm-pair
      diverged-event-ids extraction; markdown renderer
      conditional section + pure-function determinism;
      no KPI / NL leakage in the block.
- [x] ``tests/test_session_eval_harness_agent_memory.py``
      — three pins flipped (was: "ON returns no compare /
      thesis"; "harness source has no
      ``agent_memory_experiment_summary`` reference";
      "session_compare source has no ``agent_memory``
      reference") → now: emits compare + thesis; compare
      report carries the block; harness reaches block via
      the public kwarg (spy on
      ``mod.build_compare_report``).
- [x] ``tests/test_event_loop_c_agent_memory_internal_
      wiring.py`` — Slice 2C "no ``agent_memory`` in
      session_compare source" pin replaced with a
      structural pin asserting
      ``agent_memory_variant_tags`` exists, defaults to
      ``None``, and ``COMPARE_REPORT_SCHEMA_VERSION ==
      "1.1"``.
- [x] ``tests/test_run_session_agent_memory_public_kwarg
      .py`` — Slice 2D1 P6 pin replaced with a structural
      pin asserting no field on ``SessionEventRecord`` /
      ``SessionKPIs`` and no schema-version bump.
- [x] No ``SessionEventRecord`` overlay (D6 / RO1 still
      defers); no ``SessionKPIs`` field; no
      ``operations_mode`` publicization.

**Slice 2D3-B — runtime activation seam repair (LANDED):**
- [x] ``src/event_loop.py::_run_reasoning_slice`` gained
      one optional kwarg-only ``operations_mode: Any =
      None``. When non-None, written into
      ``GraphState["operations_mode"]``; when None
      (Path B's default), the key stays absent → Path B
      byte identity preserved.
- [x] ``src/event_loop_c.py::_build_path_c_main_records``
      now forwards the already-resolved
      ``operations_mode`` (computed at the top of the
      function via ``_resolve_operations_mode_from_env``)
      into the new ``_run_reasoning_slice`` kwarg. Single
      additive line.
- [x] Closes the wiring gap where W4 (in
      ``_maybe_build_agent_memory_context``) fired on
      env=``llm`` and built an ``AgentMemoryContext`` but
      ``graph.operations_agent_node`` defaulted
      ``state.get("operations_mode") or "rules"`` and
      ``_resolve_ops_mode("rules")`` short-circuited the
      env. The operations agent now actually takes the
      LLM path under env=``llm`` + PATH_C_WARM +
      enabled config; the prompt seam injects
      ``HISTORICAL_STRUCTURED_MEMORY_CONTEXT`` for real.
- [x] Default-off Path C-min (env unset) writes
      ``"rules"`` into ``GraphState["operations_mode"]``,
      a string the graph node was already treating
      identically to its absent default → no downstream
      byte change.
- [x] No public surface change. ``operations_mode`` stays
      env-only (D9 still holds). No ``run_session``
      signature change. No CLI / harness / agent-module
      / schema / KPI change.
- [x] ``tests/test_agent_memory_runtime_activation.py``
      (new, 3 tests): under env=``llm`` + PATH_C_WARM +
      enabled config, asserts the operations LLM gateway
      is invoked AND at least one captured prompt
      carries the section header — explicitly without
      monkeypatching ``_resolve_ops_mode``, so a future
      regression of the env→GraphState wiring trips the
      pin. Mirror "B4 OFF + env=``llm``" pin: LLM seam
      called but no header. "Env unset" pin: LLM gateway
      never invoked (the sideband does not widen
      LLM-dispatch reach beyond the env-opt-in surface).
- [x] ``tests/test_agent_memory_truth_stability.py``
      (new, 1 test): G5 exercised-path stability with
      env=``llm``, deterministic LLM gateway spy, and a
      fixed warm-seed memory. Asserts per-event
      ``governance_truth`` / ``effective_decision`` /
      ``baseline_event_result`` bytes are equal across
      B4 OFF vs ON, with the operations seam genuinely
      firing on the ON run (header present in ≥1
      prompt). The 2D3-A version of this test depended
      on a test-side ``_resolve_ops_mode`` monkeypatch;
      the 2D3-B repair removed that dependency.
- [x] Stale-comment hygiene in
      ``scripts/session_eval_harness.py`` (two H6
      deferred-emission comments) — no logic change.

**Next slice (deferred, Slice 2D4 — conditional on RO1):**
Optional ``SessionEventRecord.agent_memory_context``
overlay (MINOR bump 1.2 → 1.3). Lands ONLY if compare-only
(2D3-A) is judged insufficient against actual experiment
data; D6 currently still defers. ``COMPARE_REPORT_SCHEMA_
VERSION`` stays ``"1.1"`` regardless;
``SessionKPIs`` stays at ``1.1`` (no B4 KPI under any
landed or scheduled slice); ``llm_meta.trace`` stays
unchanged (RO9 still open).

## 14. Default-off byte identity — what the landed slices preserve

Slices 2A / 2B / 2C / 2D1 / 2D1.x / 2D2 / 2D3-A / 2D3-B ship
runtime code including the public
``run_session(..., agent_memory_config=None)`` kwarg, the
harness's ``--enable-agent-visible-memory`` flag + locked
triplet, the conditional ``agent_memory_experiment_summary``
compare block, and the env→GraphState ``operations_mode``
sideband repair. Default-off byte identity is pinned on the
following surfaces (``agent_memory_config`` is ``None`` **or**
is a default ``AgentMemoryExperimentConfig()`` with flag
False; ``agent_memory_variant_tags`` kwarg is omitted on
``build_compare_report``; harness flag is OFF):

- ``SessionArtifact.json`` under every tested mode × flag
  combination reachable from ``run_session``.
- Every agent's full prompt-input sequence when reached
  through ``run_session``.
- Every agent's output bytes under the same condition.
- ``SessionEventRecord.baseline_event_result`` verbatim
  (no B4 overlay field exists in any landed slice).
- ``GovernanceTruthRef`` / ``EffectiveDecisionRef`` bytes
  (dual-track truth unchanged by B4 — pinned by the
  exercised-path G5 test in
  ``tests/test_agent_memory_truth_stability.py``).
- Canonical JSON bytes of the Phase-3 compare report when
  the new ``agent_memory_variant_tags`` opt-in kwarg is
  omitted (the conditional sibling block does NOT appear).
- ``session_id`` bytes (default-off does NOT emit the
  ``agent_memory`` digest fragment; see §12 D8+F1).
- ``SessionEventRecord``, ``SessionKPIs``, ``SessionArtifact``,
  ``SessionConfig`` schema versions (no bump).
- ``COMPARE_REPORT_SCHEMA_VERSION`` stays ``"1.1"`` (no
  bump in 2D3-A; conditional-sibling-block precedent from
  B1 / B2 / B3).
- ``GraphState["operations_mode"]`` (Slice 2D3-B): Path B's
  ``run_event_loop`` does not pass the new
  ``operations_mode`` kwarg → key stays absent → graph node
  on the pre-2D3-B "rules" default. Path C-min with env
  unset writes ``"rules"`` into the key, which the graph
  node was already treating identically to the absent
  default → no downstream byte change.

When a caller drives B4 through the public kwarg with
``enable_agent_visible_memory=True``, three things
legitimately change:

1. If AND ONLY IF the full W4 runtime gate is satisfied
   (``mode == "PATH_C_WARM"``; operations_mode resolves to
   ``"llm"`` from the env; the config flag is True;
   ``"PATH_C_WARM" in allowed_modes``), the operations
   agent's LLM user-prompt bytes extend with the fixed
   ``HISTORICAL_STRUCTURED_MEMORY_CONTEXT`` section AND
   the operations agent dispatch actually reaches its LLM
   path (Slice 2D3-B made this end-to-end; before 2D3-B
   the W4 gate fired but the dispatch silently fell back
   to rules). Operations-output / governance-output bytes
   may then legitimately differ from the OFF run because
   the agent saw a different prompt — but the dual-track
   truth references stay stable on identical underlying
   facts (G5 / R2).
2. ``session_id`` shifts, because ``config_for_digest``
   now contains a deterministic ``agent_memory`` fragment
   (Slice 2D1.x / F1). Per F2, that shift depends ONLY on
   the public config identity — not on the env / mode /
   runtime-gate state. Two runs whose public configs are
   equal produce equal ``session_id``s even when only one
   of them actually activates B4 at runtime. This is the
   B1 / B2 / B3 fragment precedent applied to B4.
3. When the caller (e.g. the B4 ON branch of
   ``session_eval_harness.run_eval_harness``) opts into
   the compare block by passing ``agent_memory_variant_
   tags`` to ``build_compare_report`` AND every named tag
   is present in ``artifacts``, the compare report gains
   the additive ``agent_memory_experiment_summary``
   sibling block. The block is structural-only and
   does NOT bump ``COMPARE_REPORT_SCHEMA_VERSION``.

Neither (1) nor (2) nor (3) touches ``SessionEventRecord``
overlay fields or ``SessionKPIs`` — both would require a
separate owner-approved boundary amendment (see RO1 for
overlay, RO9 for meta).

## 15. Residual open questions (for future B4 slices)

**Closed by Slice 2C / D7–D11 / Slice 2D1.x:**
RO7 (builder-flag-gating) / RO11 (public exposure shape) /
RO12 (operations_mode scope) / **RO2 (digest fragment)**.

**Closed by Slice 2D3-A (compare-only closure):** RO1 took
the **compare-only** path for the current decision window —
the conditional ``agent_memory_experiment_summary`` sibling
block on the compare report (driven by the
``agent_memory_variant_tags`` opt-in kwarg) supersedes the
candidate ``SessionEventRecord.agent_memory_context``
overlay; the overlay stays deferred behind a future Slice
2D4 only if compare-only is judged insufficient.

**Closed by Slice 2D3-B (runtime activation seam repair):**
RO3 — the controlled-facts G5 test
(``tests/test_agent_memory_truth_stability.py``) is now
exercised on the real runtime path under env=``llm`` +
PATH_C_WARM, with a deterministic LLM gateway spy and a
fixed warm-seed memory; per-event ``GovernanceTruthRef`` /
``EffectiveDecisionRef`` / ``baseline_event_result`` bytes
are pinned equal across B4 OFF vs ON. The test pair
``tests/test_agent_memory_runtime_activation.py`` +
``tests/test_agent_memory_truth_stability.py`` is a
regression net against the env→GraphState wiring closing
again.

**Still deferred (no near-term landing):**

- **RO1 (re-stated as "future overlay window" — Slice
  2D4).** Whether to add
  ``SessionEventRecord.agent_memory_context`` (MINOR bump
  1.2 → 1.3) to record what the agent was shown per-event.
  Compare-only (2D3-A) is the current call; the overlay
  lands ONLY if real experiment data shows compare-only
  cannot answer audit questions. D6 still defers.
- **RO4 — B4 × B3 interaction at runtime.** Slice 2C's spy
  tests confirmed ``event_loop_c.py`` does not import
  ``learning.cumulative_memory`` and consumes whatever
  ``EpisodicMemory`` the caller assembled. The Slice 2D3-B
  runtime activation does not change this contract.
  Confirm-or-amend at the next experiment-data review.
- **RO5 — Renderer determinism contract.** The Slice 2A
  renderer is already PYTHONHASHSEED-deterministic, sorts
  ``action_type_distribution`` lexicographically, and
  formats rates via ``str(round(x, 4))``. Whether a future
  slice allows a config-driven renderer variant needs an
  explicit boundary amendment; by default the current
  invariants are load-bearing.
- **RO6 — Shared summarizer contract.** The B4 builder
  passes ``threshold=1`` into
  ``learning.memory_summarizer.summarize_records`` purely
  to satisfy the helper's required argument and then
  overrides ``cold_start`` per R3. If the summarizer
  signature ever changes, the B4 builder must be re-
  examined. Recorded as a stability obligation on
  ``summarize_records``.
- **RO8 — B4 section position inside the operations user
  prompt.** Slice 2B appends at the end of the Facts block.
  If the operations user-prompt structure evolves, the
  boundary doc should lock whether B4 stays "end of
  prompt" or "immediately after Facts".
- **RO9 — B4-injected marker in ``llm_meta.trace`` /
  runtime observability marker.** Slice 2B deliberately does
  NOT record whether a given LLM call carried the B4
  section, to keep the meta shape unchanged (S6). Slice
  2D3-A confirmed this stays the call: the compare block
  is the current observability surface; no
  ``llm_meta.trace`` field, no session-level overlay, no
  meta-shape change. The decision is still "meta field
  (breaks shape)" vs "session-level overlay (triggers
  RO1)" vs "neither (current state)" — current state
  remains "neither".
- **RO10 — boundary-doc landed-status maintenance.** Each
  runtime slice must continue to update §13 + §14 + §15
  in the same PR (or in an immediate docs-sync slice
  like this one), or a drift gap will reopen. Slice
  2D3-A's pin-flips and Slice 2D3-B's wiring repair
  reopened the gap; this docs-sync slice closes it.

## 16. Non-goals for B4 (reminder)

- Default-on agent-visible memory in any mode.
- Dual-agent injection in a single B4 PR.
- Multiple simultaneous input surfaces in a single B4 PR.
- Modifying any existing agent's output schema.
- Modifying any Path B Tier 1 contract.
- Modifying any B1/B2/B3 file or test.
- Treating an agent paraphrase as a truth source.
- KPI-level summarization of the experiment
  (`SessionKPIs` stays unchanged).
- `COMPARE_REPORT_SCHEMA_VERSION` bump.
- Frontend visualization of agent-visible memory (B5).
- Promotion of B4 findings to Path C-min mainline (separate
  owner decision, separate slice, separate boundary update).
