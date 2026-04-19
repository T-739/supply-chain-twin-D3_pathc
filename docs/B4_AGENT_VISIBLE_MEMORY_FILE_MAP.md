# B4_AGENT_VISIBLE_MEMORY_FILE_MAP.md

Status: **Slices 1, 2A, 2B, 2C, 2D1, 2D1.x, 2D1.xa, 2D2,
2D3-A, 2D3-B all landed — D1–D11 locked + RO2 / RO3 closed +
the compare-block dimension of RO1 closed via compare-only
closure** (see `docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §12 /
§15`). The map below reflects the current landed runtime
surface: contracts, pure builder / renderer, operations-agent
single-point prompt seam, ``event_loop_c`` internal caller
wiring, public ``run_session(..., agent_memory_config=None)``
kwarg, conditional ``agent_memory`` digest fragment,
``_SCHEMA_VERSIONS`` audit, the ``--enable-agent-visible-
memory`` flag on both scripts with the locked three-variant
harness experiment set, the additive
``agent_memory_variant_tags`` opt-in kwarg + conditional
``agent_memory_experiment_summary`` sibling block on
``session_compare.py`` (Slice 2D3-A), B4 ON harness emission
of ``compare_report.json`` + ``thesis_report.md`` over the
locked triplet, and the env→GraphState ``operations_mode``
sideband repair on ``event_loop._run_reasoning_slice`` (Slice
2D3-B) that lets the operations agent dispatch actually take
the LLM path under env=``llm`` + PATH_C_WARM + B4-enabled
config. Slice 2D4 (conditional on RO1 — optional
``SessionEventRecord`` overlay) remains forward-looking,
guarded by RO1 / RO4 / RO5 / RO6 / RO8 / RO9 / RO10 and the
D10 ordering.

Authority: `docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md`,
`docs/B4_AGENT_VISIBLE_MEMORY_CONTRACT_DRAFT.md`,
`PATH_C_BOUNDARY.md`.

This document maps B4 (Agent-visible memory experiment) against
the current repo layout so Slice 2D1+ wiring work can proceed
without surprises. Every entry is grounded in the state of the
repo at
the time of writing.

Slice 0 delta (previous turn, already on `main`): three docs
under `docs/` (boundary, contract draft, file map).

Slice 1 delta (this turn, now landed):
- **New subpackage:** `src/agent_memory/` — `__init__.py`,
  `agent_memory_schema.py` (`AgentMemoryExampleRef` 1.0 +
  `AgentMemoryContext` 1.0), `agent_memory_config.py`
  (`AgentMemoryExperimentConfig` 1.0 + module constants
  `MAX_AGENT_MEMORY_EXAMPLES=3`, `KNOWN_AGENT_MEMORY_TARGETS`,
  `KNOWN_AGENT_MEMORY_CONTEXT_SOURCES`).
- **Registry:** `PATH_C_SCHEMA_REGISTRY.md` gains the B4 Slice 1
  section registering the three contracts at 1.0. No bump on
  any other entry.
- **Boundary:** `PATH_C_BOUNDARY.md §9` gains one B4
  cross-reference line alongside B1/B2/B3. §1–§8 unchanged.
- **Path C scan roots:** `tests/test_path_c_import_topology.py`
  adds `src/agent_memory/` to `_PATH_C_ROOTS`.
- **Frozen-shape test:** `tests/test_path_c_schema_frozen.py`
  gains `AgentMemoryExampleRef` + `AgentMemoryContext`
  assertions (both at `schema_version == "1.0"`).
- **New fixture rows:** `tests/fixtures/path_c_schema_samples_
  1_0.json` gains canonical samples for the two new pydantic
  schemas; other rows byte-unchanged.
- **Two new test files:**
  `tests/test_agent_memory_schema_frozen.py` (config
  defaults, closed Literals, roundtrip, cap, reject smuggled
  tokens), `tests/test_agent_memory_contract_no_truth_write.py`
  (schema-level + AST-level + behavioral no-truth-write guard
  with positive / negative self-tests).

Slice 1 is **contracts only**. No runtime, no agent-module
edit, no `event_loop_c` change, no session-schema bump, no
compare-report edit, no CLI / harness edit, no KPI change.
Default-off byte identity is therefore trivially preserved:
the B4 runtime path does not exist yet.

Slice 2+ delta (future, guarded by boundary §15 / draft §11):
- Locked in Slice 1 and therefore no longer candidate:
  target agent (operations), placement (new subpackage +
  future single additive hunk in the operations prompt
  builder), context shape (aggregate summary + capped
  examples), gating (default-off + `allowed_modes=
  {"PATH_C_WARM"}`), compare-variant count (three).
- Still residual for later slices: C4 overlay vs. no overlay
  on `SessionEventRecord` (RO1); digest fragment contribution
  (RO2); governance-truth-invariance test input set (RO3);
  B3-interaction confirmation (RO4); renderer determinism
  contract (RO5).

---

## 1. Files expected to stay untouched under B4

These files MUST NOT be modified by any PR labelled B4 Slice 0
/ Slice 1 / Slice 2, unless an explicit, owner-approved
boundary amendment moves them off this list.

### 1.1 Path B runtime core (frozen Tier 1)

- `src/event_schema.py` — `EventPayload`, `EventType`,
  `EventSeverity`, `AffectedEntityRef`.
- `src/outcome_schema.py` — `ExecutionOutcome`.
- `src/policy_gate.py` — `PolicyDecision`, `decide_policy`.
- `src/execution_adapters.py`.
- `src/event_loop.py` (Path B core).
- `src/graph.py` — node wiring.
- `src/outcome_store.py`.
- `src/twin_state.py`.

### 1.2 Research Core (frozen)

- `src/evaluation.py`
- `src/action_code_mapper.py`
- `data/cases/*.json`

### 1.3 Path C-min adaptive / preflight (frozen under B4)

- `src/adaptive/adaptive_policy_gate.py`.
- `src/adaptive/adaptive_policy_config.py`.
- `src/adaptive/adaptive_schema.py`.
- `src/adaptive/cold_start.py`.
- `src/adaptive/preflight.py`.

The adaptive gate is the Path C-min policy-side memory
consumer. B4 introduces a second, independent agent-prompt-
side consumer; it does NOT widen the adaptive gate's consumer
surface. `src/adaptive/*` does not import from the new B4
subpackage, and the new B4 subpackage does not import from
`src/adaptive/*`. Enforced by the AST scan at Slice 1.

### 1.4 Learning (memory core + B3 loader)

- `src/learning/memory_schema.py` — `MemoryRecord`,
  `MemoryQuery`, `MemorySummary` stay at 1.0. **No new field.**
- `src/learning/episodic_memory.py` — append-only + canonical
  order stay exactly as today.
- `src/learning/memory_summarizer.py` — unchanged.
- `src/learning/cumulative_memory.py` — B3 Slice 2A/2B surface
  frozen under B4. B4 does NOT import this module directly.
  It receives an already-assembled `EpisodicMemory` from the
  caller layer (the same shape the adaptive gate's path
  receives today).

### 1.5 B1 replan layer

- `src/replan/*` — every file, unchanged. Replan does not
  couple to agent-visible memory under B4.

### 1.6 B2 correlator layer

- `src/correlator/*` — every file, unchanged. The correlator
  does not couple to agent-visible memory under B4. A later
  experiment that surfaces `correlation_context` to an agent
  is a separate branch, not a B4 slice.

### 1.7 Path C-min session core (frozen under every landed slice)

- `src/session/session_schema.py` — **no new field added by
  any landed slice**; ``SessionEventRecord`` stays at 1.2.
  An optional additive field (``agent_memory_context:
  Optional[AgentMemoryContext] = None``, MINOR bump 1.2 →
  1.3) is scheduled for Slice 2D3 only if RO1 resolves to
  "yes add overlay". No earlier slice may add it.
- `src/session/digests.py` — ``digest_memory_records``,
  ``compute_session_id``, ``memory_record_id`` formulas stay
  untouched under every B4 slice.
- `src/session/session_manager.py` — ``save_session``,
  ``load_session``, ``replay_session_bytes`` stay untouched.
- `src/session/kpi_calculator.py` — **frozen for every B4
  slice.** No B4 KPI.
- `src/session/session_compare.py` — Slice 2D3-A landed an
  additive optional ``agent_memory_variant_tags:
  Optional[Sequence[str]] = None`` kwarg on
  ``build_compare_report`` plus a conditional
  ``agent_memory_experiment_summary`` sibling block emitted
  iff the kwarg is supplied AND every named tag is present
  in ``artifacts``. Mirror conditional section in
  ``render_thesis_markdown``. ``COMPARE_REPORT_SCHEMA_
  VERSION`` stays ``"1.1"`` (no bump — B1/B2/B3 conditional-
  sibling-block precedent). Block is structural-only (no
  KPI math, no NL paraphrase, no agent-output read).
  Default callers (no kwarg) get byte-identical output.

### 1.8 Agent modules (one landed edit on operations_agent.py)

- `src/agents/__init__.py` — no change.
- `src/agents/cost_agent.py` — no change.
- `src/agents/governance_agent.py` — **no change in any
  landed slice**; locked by D1. Enforced by
  ``tests/test_agent_memory_single_agent_injection.py``.
- `src/agents/operations_agent.py` — Slice 2B landed a single
  additive hunk inside ``_build_ops_llm_user_prompt`` plus two
  kwarg-only optional parameters (defaulted to ``None``)
  threaded through ``_enrich_ops_with_llm``,
  ``run_operations_agent_llm``, ``run_operations_agent_modeful``,
  ``run_operations_agent_with_meta``. Rules-mode entry
  ``run_operations_agent`` signature is unchanged. Output
  schemas (``OperationsOutput`` + meta dict key set) are
  structurally unchanged.
- The **output schemas** of all three agents —
  ``GovernanceOutput``, ``OperationsOutput``, and any
  cost-agent output class — stay frozen. B4 adds no fields to
  any agent output. ``_governance_meta`` shape is frozen.

### 1.9 Orchestration

- `src/event_loop_c.py` — Slice 2C landed three private
  helpers (``_resolve_operations_mode_from_env``,
  ``_build_agent_memory_query_for_event``,
  ``_maybe_build_agent_memory_context``) plus one optional
  ``agent_memory_config: Optional[AgentMemoryExperimentConfig]
  = None`` kwarg on ``_build_path_c_main_records``.
  ``run_session(...)`` public signature is byte-unchanged;
  this is the core invariant the next-slice D10-step-2
  amendment will flip (single additive kwarg added to
  ``run_session``). Slice 2D0 updates only the module-level
  docstring to reflect current reality (B4 now legitimately
  reaches an agent prompt under the W4 gate) — no logic
  change.
- `src/event_loop.py` — Slice 2C extended
  ``_run_reasoning_slice`` with two kwarg-only optional
  ``Any``-typed parameters (``agent_memory_context`` /
  ``agent_memory_config``). Slice 2D3-B added a third
  optional kwarg (``operations_mode: Any = None``); when
  non-None it is written into
  ``GraphState["operations_mode"]``, which lets the
  operations agent dispatch in ``operations_agent_node``
  observe the same env reality the W4 gate observes.
  Path B's ``run_event_loop`` does not pass any of the
  three kwargs → keys stay absent → Path B byte identity
  preserved.
- `src/graph.py` — ``operations_agent_node`` reads the
  Slice 2C ``_agent_memory_*`` sideband keys from
  GraphState and forwards them to
  ``run_operations_agent_with_meta``. The pre-existing
  ``state.get("operations_mode") or "rules"`` read is
  the surface Slice 2D3-B exploits without modification.
  Default-off behavior is preserved by construction
  (sideband keys absent or set to ``"rules"``, both of
  which yield ``"rules"`` after the ``or`` default).

### 1.10 Scripts (Slice 2D2 + Slice 2D3-A landed)

- `scripts/run_session.py` — Slice 2D2 added the single
  additive ``--enable-agent-visible-memory`` CLI flag with
  ``PATH_C_WARM``-only enforcement at the script layer.
  Threads the resulting config through the Slice 2D1
  public ``run_session(..., agent_memory_config=...)``
  kwarg. No private-helper bypass.
- `scripts/session_eval_harness.py` — Slice 2D2 added the
  same flag + the locked three-variant experiment set
  (``baseline_static`` / ``path_c_warm_policy_only`` /
  ``path_c_warm_agent_visible_memory``). Slice 2D3-A
  restored ``compare_report.json`` + ``thesis_report.md``
  emission in the B4 ON branch via the new
  ``agent_memory_variant_tags`` opt-in kwarg on
  ``build_compare_report`` (kwarg value =
  ``_B4_EXPERIMENT_VARIANT_TAGS``). Default-OFF behavior
  (3-mode + compare + thesis) is byte-identical to
  pre-2D3-A.

### 1.11 Tests that must continue to pass byte-for-byte

Every test currently passing on `main` in the lists below must
stay green, byte-identical, across all B4 flag combinations
that preserve flag-OFF invariance. B4 adds new test files; it
does NOT edit existing assertions.

- `tests/test_phase0_baseline_regression_phase1.py`
- `tests/test_path_c_vs_baseline_divergence.py`
- `tests/test_replay_byte_identical.py` (additive new cases
  allowed; no edits to existing assertions)
- `tests/test_determinism_stress.py` (additive new cases
  allowed; no edits to existing assertions)
- `tests/test_kpi_calculator.py`
- `tests/test_session_compare.py`
- `tests/test_adaptive_audit_trail.py`
- `tests/test_cold_start_behavior.py`
- `tests/test_adjustment_rules.py`
- `tests/test_adaptive_policy_gate.py`
- `tests/test_governance_meta_preflight.py`
- `tests/test_execution_metadata_mandatory.py`
- `tests/test_event_loop_c_wrapping.py`
- `tests/test_session_manager.py` (additive cases allowed)
- `tests/test_thesis_report_generation.py`
- `tests/test_path_c_import_topology.py` — only the scan roots
  list is extended additively in Slice 1; the positive /
  negative self-tests stay intact.
- `tests/test_path_c_schema_frozen.py` — only new-class
  frozen assertions may be appended.
- Every `tests/test_replan_*.py` currently on `main`.
- Every `tests/test_correlator_*.py` currently on `main`.
- Every `tests/test_cumulative_memory_*.py` currently on
  `main`.

---

## 2. Files extendable additively under B4

### 2.1 Slice 0 (docs only — previous turn, already on `main`)

- `docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md` — created.
- `docs/B4_AGENT_VISIBLE_MEMORY_CONTRACT_DRAFT.md` — created.
- `docs/B4_AGENT_VISIBLE_MEMORY_FILE_MAP.md` — this file.

### 2.2 Slice 1 contracts + frozen tests (this turn, LANDED)

- `PATH_C_SCHEMA_REGISTRY.md` — registered
  `AgentMemoryExampleRef` 1.0, `AgentMemoryContext` 1.0,
  `AgentMemoryExperimentConfig` 1.0. No other bump.
- `PATH_C_BOUNDARY.md §9` — appended a B4 cross-reference line
  alongside B1 / B2 / B3. §1–§8 text byte-unchanged.
- `tests/test_path_c_import_topology.py` — added
  `src/agent_memory/` to `_PATH_C_ROOTS` and the module-list
  docstring.
- `tests/test_path_c_schema_frozen.py` — added
  `AgentMemoryExampleRef` + `AgentMemoryContext` into the
  expected-field map, class map, and roundtrip test.
- `tests/fixtures/path_c_schema_samples_1_0.json` — added
  samples for the two new schemas; other samples byte-unchanged.

The three Slice 0 docs above are updated in this turn to
reflect the D1–D7 lock; their file names are unchanged.

### 2.3 Slice 2A — pure builder + deterministic renderer (LANDED)

- ``src/agent_memory/agent_memory_builder.py`` —
  ``build_agent_memory_context(memory, query, config) ->
  AgentMemoryContext``. Pure function. R3 cold-start semantic
  (``matched_records == 0``). R4 selected-tail ordering
  (``matched[-cap:]`` preserving canonical
  ``(event_timestamp, event_id)`` order). Delegates aggregate
  fields to ``learning.memory_summarizer.summarize_records``
  with ``threshold=1`` placeholder; overrides
  ``cold_start`` per R3.
- ``src/agent_memory/agent_memory_renderer.py`` —
  ``render_agent_memory_context(context, config) -> str``.
  Pure. Fixed header ``AGENT_MEMORY_CONTEXT``. R6 locked
  format (``None`` → ``n/a``; ``round(x, 4)``;
  ``action_type_distribution`` sorted lexicographically;
  ``recent_examples: none`` for empty list; numbered examples
  for non-empty). ``config`` argument accepted for signature
  symmetry but unread — pinned by
  ``test_renderer_ignores_config_values_for_output_bytes``.
- ``src/agent_memory/__init__.py`` — re-exports both public
  functions.
- Tests — ``tests/test_agent_memory_builder.py``,
  ``tests/test_agent_memory_renderer.py``. Subprocess-level
  PYTHONHASHSEED determinism pinned on the renderer.

### 2.4 Slice 2B — operations-agent prompt seam (LANDED)

- ``src/agents/operations_agent.py`` — single additive hunk
  inside ``_build_ops_llm_user_prompt`` gated by
  ``_b4_should_inject`` (five S3 conditions). Fixed section
  delimiters ``_B4_SECTION_HEADER = "HISTORICAL_STRUCTURED_
  MEMORY_CONTEXT"`` + ``_B4_SECTION_FOOTER = "END_HISTORICAL_
  STRUCTURED_MEMORY_CONTEXT"``. Two kwarg-only optional
  parameters threaded through ``_enrich_ops_with_llm``,
  ``run_operations_agent_llm``, ``run_operations_agent_modeful``,
  ``run_operations_agent_with_meta``. Rules-mode entry
  ``run_operations_agent`` signature unchanged.
- Tests — ``tests/test_operations_agent_agent_memory_seam.py``
  (17 tests: OFF invariance, ON injection, rules-mode
  untouched, output schema unchanged, no builder call,
  determinism); ``tests/test_agent_memory_single_agent_
  injection.py`` (16 tests: allowlist-enforced import
  guard; governance / cost agents pinned as non-importers).

### 2.5 Slice 2C — event_loop_c internal caller wiring (LANDED)

- ``src/event_loop_c.py`` — imports
  ``AgentMemoryContext``, ``AgentMemoryExperimentConfig``,
  ``build_agent_memory_context``, ``MemoryQuery``. New
  private helpers ``_OPS_MODE_ENV_NAME`` / ``_OPS_MODE_VALID``
  / ``_resolve_operations_mode_from_env``,
  ``_build_agent_memory_query_for_event`` (W6 event-type-only
  ``MemoryQuery``), ``_maybe_build_agent_memory_context``
  (W4 five-condition gate). ``_build_path_c_main_records``
  gained one optional ``agent_memory_config`` kwarg (default
  ``None``). Per-event B4 context built BEFORE
  ``_run_reasoning_slice`` so the builder sees pre-current-
  event memory (W5).
- ``src/event_loop.py::_run_reasoning_slice`` — two
  kwarg-only optional parameters typed ``Any`` that pass
  B4 context through a GraphState sideband
  (``state["_agent_memory_context"]`` /
  ``state["_agent_memory_config"]``). Keys absent on the OFF
  path preserve pre-B4 byte identity end-to-end.
- ``src/graph.py::operations_agent_node`` — reads the
  sideband and forwards to ``run_operations_agent_with_meta``.
- ``run_session(...)`` public signature **unchanged**.
  ``SessionConfig`` / ``SessionEventRecord`` / digests /
  compare-report / KPIs all **unchanged**.
- Tests —
  ``tests/test_event_loop_c_agent_memory_internal_wiring.py``
  (24 tests: query builder contract, W4 gate matrix, W5
  pre-current-event memory via spy-monkeypatch, W3 public
  signature pin, env resolver cases, ON/OFF/rules spy
  observations, no-side-effects scans).

### 2.6 Slice 2D0 — boundary amendment + docs patch (LANDED, this slice)

- ``docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md`` — status →
  "Slices 1 / 2A / 2B / 2C landed"; §12 gains D8–D11; §13
  restructured into a cumulative slice ledger; §14 rewritten
  to describe default-off byte identity under the landed
  runtime; §15 updated (RO7 / RO11 / RO12 closed, RO1 / RO2 /
  RO3 / RO4 / RO5 / RO6 / RO8 / RO9 / RO10 carried forward).
- ``docs/B4_AGENT_VISIBLE_MEMORY_CONTRACT_DRAFT.md`` — each
  candidate section (§3 / §4 / §5 / §6 / §7) annotated with a
  "Landed" line pointing at its slice; §9.1 / §9.2 marked
  LOCKED at 1.0; §9.3 marked DEFERRED (RO1 still open);
  §11 updated to match the boundary's residual list.
- ``docs/B4_AGENT_VISIBLE_MEMORY_FILE_MAP.md`` — this file;
  updated to reflect current landed surface.
- ``src/event_loop_c.py`` — module-level docstring only:
  the outdated "no memory ever touches an agent prompt"
  sentence is replaced by an accurate two-layer description
  (Path C-min mainline = policy-only injection; B4 = default-
  off experiment branch that DOES reach the operations-agent
  LLM user prompt under the W4 gate, without touching
  governance truth / compare / artifact schema). **No
  function signature change, no logic change, no test change.**

### 2.7 Slice 2D1 — public ``run_session`` kwarg (LANDED)

- ``src/event_loop_c.py::run_session`` gained exactly one
  additive optional kwarg
  ``agent_memory_config: Optional[AgentMemoryExperimentConfig]
  = None`` (D8 / P1), forwarded as a single line into the
  existing ``_build_path_c_main_records`` kwarg (P3).
- ``operations_mode`` stays env-only; no public kwarg
  added for it (D9 / P2).
- ``SessionConfig`` / ``SessionEventRecord`` /
  ``session_compare`` / ``SessionKPIs`` / ``digests.py``
  untouched (P6).
- Scripts / harness / CLI untouched (P7).
- Tests — ``tests/test_run_session_agent_memory_public_
  kwarg.py`` added (default-off artifact equivalence; B4
  activation only under full W4 gate; public→internal
  forwarding; signature closed to a single kwarg;
  scripts left untouched). Slice 2C's W3 "no B4 kwargs"
  pin in
  ``tests/test_event_loop_c_agent_memory_internal_wiring.py``
  superseded by a single-kwarg pin authorized by D8 / P1.

### 2.7.1 Slice 2D1.x — conditional ``agent_memory`` digest fragment (LANDED)

- ``src/event_loop_c.py`` gained
  ``_agent_memory_config_digest_fragment(config) -> dict``,
  parallel to ``_replan_config_digest_fragment`` /
  ``_correlator_config_digest_fragment``.
- ``run_session`` now emits
  ``config_for_digest["agent_memory"] =
  _agent_memory_config_digest_fragment(agent_memory_config)``
  iff ``agent_memory_config is not None and
  agent_memory_config.enable_agent_visible_memory`` (F1).
- Fragment content is locked by F3 (see boundary §12 F3).
- Fragment depends ONLY on public config identity (F2); env
  / mode / runtime-gate state are NOT digest inputs.
- ``_SCHEMA_VERSIONS`` dict in ``event_loop_c.py`` extended
  with ``agent_memory_example_ref`` / ``agent_memory_context``
  / ``agent_memory_experiment_config`` at 1.0 so
  ``SessionArtifact.schema_versions`` audits the B4 contract.
- Docs sync — boundary §13 ledger + §14 byte-identity chapter
  + §15 residual-RO list; contract draft §10 locked; file
  map (this doc); ``event_loop_c.py`` module docstring;
  Slice 2C test file top-of-file note.
- No overlay / compare block / KPI / CLI / scripts /
  ``session_schema`` / ``session_compare`` change.
- RO2 closed.

### 2.7.2 Slice 2D1.xa — ``_SCHEMA_VERSIONS`` audit (LANDED)

- ``event_loop_c._SCHEMA_VERSIONS`` lost
  ``agent_memory_example_ref`` / ``agent_memory_context``
  keys per C1 (neither appears inside a serialized
  ``SessionArtifact`` under any landed slice).
- ``agent_memory_experiment_config`` retained per C2
  (B1/B2 precedent — config schemas that contribute to
  ``config_for_digest`` stay in the artifact-level
  registry).
- Tests:
  ``tests/test_run_session_agent_memory_public_kwarg.py``
  §9 adds 7 pins: default-OFF ``schema_versions``
  identity across no-kwarg / None / default config;
  enabled-config ``schema_versions`` identity; exclusion
  of artifact-nested schemas; retention of the
  config-level key; keyspace-closed-to-one; precedent
  symmetry with ``replan_config`` / ``correlator_config``.
- No runtime behavior change.

### 2.7.3 Slice 2D2 — scripts + harness exposure (LANDED)

- ``scripts/run_session.py`` — new CLI flag
  ``--enable-agent-visible-memory`` (H1). PATH_C_WARM-only
  enforcement at the script layer via ``parser.error(...)``
  (H2). When set, the CLI builds exactly
  ``AgentMemoryExperimentConfig(enable_agent_visible_memory=
  True)`` (H3) and threads it through the Slice 2D1 public
  kwarg. No target / input-surface / operations-mode CLI
  flags exposed (H1 / H5).
- ``scripts/session_eval_harness.py`` — new CLI flag
  ``--enable-agent-visible-memory`` + additive optional
  ``enable_agent_visible_memory: bool = False`` kwarg on
  ``run_eval_harness(...)``. Default OFF keeps pre-2D2
  harness behavior (3-mode set +
  ``compare_report`` + ``thesis_report``) byte-identical.
  ON switches to the locked three-variant B4 experiment
  set (H4): ``baseline_static`` /
  ``path_c_warm_policy_only`` /
  ``path_c_warm_agent_visible_memory``. Only the third
  variant receives an enabled
  ``AgentMemoryExperimentConfig``. B4 mode deliberately
  skips compare / thesis report emission (H6) so
  ``session_compare.py`` stays untouched.
  ``_B4_EXPERIMENT_VARIANT_TAGS`` module constant
  exposes the tag list.
- Tests:
  ``tests/test_run_session_script_agent_memory_cli.py``
  (11 tests) +
  ``tests/test_session_eval_harness_agent_memory.py``
  (13 tests). Slice 2D1 §8 "scripts untouched" pins
  flipped into "scripts reference only the approved B4
  flag" pins per H1 / H5 authorization.
- No ``session_compare.py`` / ``session_schema.py`` /
  KPI / ``operations_mode`` surface change.

### 2.7.4 Slice 2D3-A — compare-only closure (LANDED)

- ``src/session/session_compare.py`` — additive optional
  ``agent_memory_variant_tags: Optional[Sequence[str]] =
  None`` kwarg on ``build_compare_report``. When supplied
  AND every named tag is present in ``artifacts``, emits
  the conditional ``agent_memory_experiment_summary``
  sibling block (``schema_version`` "1.0",
  ``variant_tags``, ``session_ids_by_variant``,
  ``agent_visible_vs_policy_only_diverged_event_ids``,
  fixed ``notes``). Block is structural-only: no KPI math,
  no NL paraphrase, no agent-output read; diverged-event
  extraction is restricted to the
  ``path_c_warm_policy_only`` ↔
  ``path_c_warm_agent_visible_memory`` pair so baseline-
  vs-warm divergence does not contaminate the experiment
  delta. Mirror conditional section in
  ``render_thesis_markdown``.
  ``COMPARE_REPORT_SCHEMA_VERSION`` UNCHANGED at ``"1.1"``.
- ``scripts/session_eval_harness.py`` — B4 ON branch now
  passes ``_B4_EXPERIMENT_VARIANT_TAGS`` to
  ``build_compare_report`` and writes
  ``compare_report.json`` + ``thesis_report.md`` over the
  locked triplet. CLI help text updated.
- New tests: ``tests/test_agent_memory_compare_block.py``
  (13 tests). Three pins flipped in
  ``tests/test_session_eval_harness_agent_memory.py`` (was:
  "ON returns no compare/thesis"; "harness source has no
  ``agent_memory_experiment_summary`` reference";
  "session_compare source has no ``agent_memory``
  reference") and one each in
  ``tests/test_event_loop_c_agent_memory_internal_wiring.py``
  + ``tests/test_run_session_agent_memory_public_kwarg.py``
  (no-`agent_memory`-in-session_compare-source pins
  replaced with structural opt-in-shape pins).
- ``SessionEventRecord`` UNCHANGED (no overlay added; D6
  / RO1 still defers). ``SessionKPIs`` UNCHANGED at
  ``"1.1"`` (no B4 KPI).

### 2.7.5 Slice 2D3-B — runtime activation seam repair (LANDED)

- ``src/event_loop.py::_run_reasoning_slice`` — gained
  one optional kwarg-only ``operations_mode: Any = None``;
  when non-None, written into
  ``GraphState["operations_mode"]``. Path B's call site
  does not pass it → key absent → Path B byte identity
  preserved.
- ``src/event_loop_c.py::_build_path_c_main_records`` —
  one new line that forwards the already-resolved
  ``operations_mode`` (from
  ``_resolve_operations_mode_from_env`` at the top of the
  function) into the new ``_run_reasoning_slice`` kwarg.
- Closes the wiring gap where W4 fired on env=``llm`` but
  ``graph.operations_agent_node`` defaulted
  ``state.get("operations_mode") or "rules"`` and
  ``_resolve_ops_mode("rules")`` short-circuited the env.
  After 2D3-B, env=``llm`` + PATH_C_WARM + B4-enabled
  config genuinely takes the operations LLM path and the
  prompt seam injects ``HISTORICAL_STRUCTURED_MEMORY_
  CONTEXT`` for real.
- New tests:
  ``tests/test_agent_memory_runtime_activation.py`` (3
  tests, no ``_resolve_ops_mode`` monkeypatch — would
  mask the gap). ``tests/test_agent_memory_truth_
  stability.py`` (1 test) updated to drop its previous
  ``_resolve_ops_mode`` monkeypatch (no longer needed
  after 2D3-B).
- Stale-comment hygiene in
  ``scripts/session_eval_harness.py`` (two H6 deferred-
  emission comments) — no logic change.
- Default-off Path C-min (env unset) writes ``"rules"``
  into ``GraphState["operations_mode"]``, a string the
  graph node was already treating identically to its
  absent default → no downstream byte change.
- No public surface change. ``operations_mode`` stays
  env-only (D9 still holds). No ``run_session``
  signature change. No CLI / harness / agent-module /
  schema / KPI change.

### 2.7.6 Slice 2D4 — optional persisted overlay (DEFERRED)

Conditional on RO1; runs only if compare-only (Slice
2D3-A) is judged insufficient against actual experiment
data.

- ``src/session/session_schema.py`` —
  ``SessionEventRecord.agent_memory_context:
  Optional[AgentMemoryContext] = None``; MINOR bump 1.2 →
  1.3. Only lands if RO1 resolves "yes add overlay".
- ``SessionKPIs`` stays at ``1.1`` (no B4 KPI under any
  scheduled slice).
- ``COMPARE_REPORT_SCHEMA_VERSION`` stays ``"1.1"``.

### 2.8 Explicitly NOT modified by any landed B4 slice

The following are off-limits for every landed slice and stay
off-limits for Slice 2D1+ unless an explicit owner-approved
boundary amendment moves them off this list:

- ``src/event_schema.py``, ``src/outcome_schema.py``,
  ``src/policy_gate.py`` — Path B Tier 1; frozen.
- ``src/learning/memory_schema.py``,
  ``src/learning/episodic_memory.py``,
  ``src/learning/cumulative_memory.py`` — frozen.
- ``src/adaptive/*`` — frozen.
- ``src/replan/*`` — frozen.
- ``src/correlator/*`` — frozen.
- ``src/session/digests.py`` — digest formulas frozen.
- ``src/session/kpi_calculator.py`` — frozen.
- Agent **output** schemas (``GovernanceOutput``,
  ``OperationsOutput``, any cost-agent output,
  ``_governance_meta`` shape) — frozen.
- Research Core (``evaluation.py``, ``action_code_mapper.py``,
  ``data/cases/*.json``) — frozen.
- ``app.py``, ``src/api/*`` — no FastAPI surface change under
  B4 (that's B5).
- ``src/agents/governance_agent.py``,
  ``src/agents/cost_agent.py`` — frozen (D1 locks operations
  as the sole B4 target).

This mirrors the B1 / B2 / B3 discipline: docs first; contracts
+ frozen tests in a separate slice; runtime + wiring next;
optional compare / report visibility after that; optional CLI
last. At each step the default-off invariant (boundary G2)
stays intact.

---

## 3. Landed B4 files (source + tests)

### 3.1 Landed subpackage — ``src/agent_memory/``

The subpackage is on ``main``. Name, structure, and public
surface are all landed reality; they are NOT candidate.

Module layout:

- ``src/agent_memory/__init__.py`` — re-exports
  ``AgentMemoryExampleRef``, ``AgentMemoryContext``,
  ``AgentMemoryExperimentConfig``, ``MAX_AGENT_MEMORY_EXAMPLES``,
  ``KNOWN_AGENT_MEMORY_TARGETS``,
  ``KNOWN_AGENT_MEMORY_CONTEXT_SOURCES``,
  ``AGENT_MEMORY_SCHEMA_VERSION``,
  ``build_agent_memory_context``,
  ``render_agent_memory_context``.
- ``src/agent_memory/agent_memory_schema.py`` (Slice 1) —
  ``AgentMemoryExampleRef`` + ``AgentMemoryContext`` pydantic
  classes, locally redefined closed Literals for action /
  route / status (to avoid circular import with
  ``session.session_schema``), ``AGENT_MEMORY_SCHEMA_VERSION
  = "1.0"``.
- ``src/agent_memory/agent_memory_config.py`` (Slice 1) —
  ``AgentMemoryExperimentConfig`` frozen dataclass +
  ``MAX_AGENT_MEMORY_EXAMPLES = 3``,
  ``KNOWN_AGENT_MEMORY_TARGETS = frozenset({"operations"})``,
  ``KNOWN_AGENT_MEMORY_CONTEXT_SOURCES =
  frozenset({"structured_summary_plus_recent_examples"})``.
- ``src/agent_memory/agent_memory_builder.py`` (Slice 2A) —
  ``build_agent_memory_context(memory, query, config) ->
  AgentMemoryContext``. Pure function. Delegates aggregate
  fields to ``learning.memory_summarizer.summarize_records``;
  overrides ``cold_start`` per R3.
- ``src/agent_memory/agent_memory_renderer.py`` (Slice 2A) —
  ``render_agent_memory_context(context, config) -> str``.
  Pure function. Fixed ``AGENT_MEMORY_CONTEXT`` header; R6
  locked format; ``config`` arg accepted for signature
  symmetry, unread.

Module placement rationale (historical):

1. Symmetric with ``src/correlator/`` and
   ``src/learning/cumulative_memory.py`` — sibling additive
   subpackage.
2. Keeps B4 separable from B3 (the subpackage does not live
   under ``src/learning/``).
3. Keeps B4 separable from ``src/agents/*`` — the subpackage
   is consumed by one agent module but is not itself an agent.

### 3.2 Landed tests

On ``main``, grouped by acceptance gate:

- ``tests/test_agent_memory_schema_frozen.py`` (Slice 1) —
  G1. Field sets, closed Literals, ``__post_init__`` rejection,
  ``AGENT_MEMORY_SCHEMA_VERSION == "1.0"``, recent_examples
  cap, default-off config.
- ``tests/test_agent_memory_contract_no_truth_write.py``
  (Slice 1) — G2 / G10 guard rails. Schema-level + AST-level
  + behavioral scans for forbidden NL / truth / overlay
  tokens. Includes parametrized bad-sample + good-sample
  self-tests.
- ``tests/test_agent_memory_reverse_import_forbidden.py``
  (Slice 1) — G8 reverse direction: ``src/adaptive/*`` does
  not import ``src/agent_memory/*``.
- ``tests/test_agent_memory_builder.py`` (Slice 2A) — R1 /
  R3 / R4 semantics, purity, no mutation, no forbidden
  imports (AST source scan on the builder file).
- ``tests/test_agent_memory_renderer.py`` (Slice 2A) — R5 /
  R6 format, ``n/a`` / rounding / lexicographic distribution,
  empty-list marker, subprocess-level PYTHONHASHSEED
  determinism, forbidden-narrative-token scan
  (no ``therefore`` / ``recommend`` / ``because`` /
  ``confidence``).
- ``tests/test_operations_agent_agent_memory_seam.py``
  (Slice 2B) — G3 / G10 on the operations-agent seam:
  flag-OFF prompt-byte invariance, fixed-section injection,
  rules-mode untouched, output schema unchanged, no builder
  call, determinism.
- ``tests/test_agent_memory_single_agent_injection.py``
  (Slice 2B) — G3 single-agent allowlist: only
  ``operations_agent.py`` imports from ``agent_memory``;
  governance / cost agents pinned as non-importers.
- ``tests/test_event_loop_c_agent_memory_internal_wiring.py``
  (Slice 2C) — query builder contract, W4 five-condition
  gate matrix, W5 pre-current-event memory via spy, W3
  public-signature pin, env resolver cases, spy-based ON /
  OFF / rules observations, no-side-effect scans. Slice
  2D3-A flipped one anti-coupling pin (was: "no
  ``agent_memory`` in session_compare source") into a
  structural opt-in-shape pin
  (``test_session_compare_b4_block_is_opt_in_only``).
- ``tests/test_run_session_agent_memory_public_kwarg.py``
  (Slice 2D1 + 2D1.x + 2D1.xa) — single-kwarg signature
  pin, default-off artifact equivalence, B4 activation
  only under full W4 gate, public→internal forwarding,
  digest-fragment behavior, ``_SCHEMA_VERSIONS`` audit.
  Slice 2D3-A flipped one P6 anti-coupling pin into a
  structural "no record/KPI field, no version bump" pin.
- ``tests/test_run_session_script_agent_memory_cli.py``
  (Slice 2D2) — parser accepts flag, mode-validation
  matrix, config forwarding, no-bypass spy, CLI surface
  constraints.
- ``tests/test_session_eval_harness_agent_memory.py``
  (Slice 2D2 + 2D3-A) — default-OFF preserved,
  three-variant set in ON mode, only third variant gets
  config, no private-helper bypass, no
  ``operations_mode`` publicization. Slice 2D3-A flipped
  three H6 deferred-emission pins into "ON emits compare
  + thesis" / "compare report carries the block" /
  "harness reaches block via the public kwarg" pins.
- ``tests/test_agent_memory_compare_block.py`` (Slice
  2D3-A, NEW) — 13 tests pinning the
  ``agent_memory_variant_tags`` opt-in kwarg + the
  conditional ``agent_memory_experiment_summary`` sibling
  block. Default 3-mode compare omits the block; no kwarg
  → byte-identical; full triplet → block present with
  locked shape; partial triplet → block omitted; empty
  tag list → block omitted; warm-pair diverged-event-ids
  extraction; markdown renderer conditional section +
  pure-function determinism; no KPI / NL leakage in the
  block.
- ``tests/test_agent_memory_runtime_activation.py`` (Slice
  2D3-B, NEW) — 3 tests pinning the env→GraphState
  ``operations_mode`` sideband repair. Under env=``llm``
  + PATH_C_WARM + enabled config, asserts the operations
  LLM gateway is invoked AND at least one captured
  prompt carries the section header (no
  ``_resolve_ops_mode`` monkeypatch — would mask the
  gap). Mirror "B4 OFF + env=``llm``" pin: LLM seam
  called but no header. "Env unset" pin: LLM gateway
  never invoked (the sideband does not widen
  LLM-dispatch reach beyond the env-opt-in surface).
- ``tests/test_agent_memory_truth_stability.py`` (Slice
  2D3-A → 2D3-B, NEW) — 1 G5 exercised-path stability
  test: env=``llm``, deterministic LLM gateway spy,
  fixed warm-seed memory; per-event ``governance_truth`` /
  ``effective_decision`` / ``baseline_event_result`` bytes
  pinned equal across B4 OFF vs ON, with the seam
  genuinely firing on the ON run (header present in ≥1
  prompt). The 2D3-A original needed a test-side
  ``_resolve_ops_mode`` monkeypatch to exercise the seam;
  Slice 2D3-B's wiring repair removed that dependency.

### 3.3 Tests scheduled for Slice 2D4+ (not yet landed)

These map to acceptance gates that depend on the deferred
``SessionEventRecord`` overlay (RO1):

- Per-event audit-surface overlay invariants
  (``baseline_event_result`` byte identity AND
  ``agent_memory_context`` overlay equality on identical
  inputs) — Slice 2D4 only if RO1 resolves "yes add
  overlay".

Every other acceptance gate (G1–G14) is now exercised by
at least one landed-slice test on ``main``.

---

## 4. Expected test surface across the B4 slice ladder

This section names the **test families** B4 needs. Items
exercised by the current landed slices are marked
**[landed]** with a reference to §3.2; items still owed are
marked **[owed, Slice 2Dx]** pointing at the slice that
introduces the ability to exercise them.

- **Default-off invariance.** [partially landed,
  §3.2 / owed end-to-end via public kwarg in Slice 2D1]
  Byte-identity of ``SessionArtifact.json``, compare report
  JSON, every agent's prompt-input sequence, and every
  agent's output bytes when
  ``enable_agent_visible_memory=False``. Pinned for the
  prompt-seam layer (Slice 2B spy tests); end-to-end via
  ``run_session`` will be added in Slice 2D1.
- **No baseline mutation.** [landed at seam level, §3.2]
  ``SessionEventRecord.baseline_event_result`` bytes
  unchanged across flag={False,True}; no overlay field
  exists in any landed slice.
- **No truth collapse.** [partially landed, §3.2 /
  owed G5 run in Slice 2D1 on controlled-facts input set
  (RO3)] Structural NL-truth-leak AST scan on
  ``src/agent_memory/*`` is landed; behavioral
  ``GovernanceTruthRef`` / ``EffectiveDecisionRef``
  invariance on a fixed seed set is owed to 2D1.
- **Deterministic replay invariance.** [partially landed —
  renderer subprocess-level PYTHONHASHSEED test in §3.2;
  ``save_session`` → ``load_session`` →
  ``replay_session_bytes`` parametrized by B4 flag is
  owed to Slice 2D1].
- **Compare surface stability.** [owed, Slice 2D3] Pre-B4
  compare report byte-identical when flag=False; new
  sibling block appears only under flag=True.
  ``COMPARE_REPORT_SCHEMA_VERSION`` stays ``"1.1"``.
- **Single-agent-only experiment isolation.** [landed,
  §3.2] Exactly one agent module imports from
  ``src/agent_memory/``; other agents pinned as
  non-importers.
- **No reverse coupling.** [landed, §3.2] AST scans
  covering ``src/adaptive/*``, ``src/correlator/*``,
  ``src/replan/*``, ``src/learning/cumulative_memory.py``,
  ``src/session/session_compare.py`` — none imports the
  B4 subpackage.
- **No agent-output schema change.** [landed, §3.2]
  Structural assertion that ``GovernanceOutput``,
  ``OperationsOutput``, any cost-agent output, and
  ``_governance_meta`` shape are unchanged.
- **Bounded-growth.** [landed, §3.2] Builder respects the
  landed cap ``MAX_AGENT_MEMORY_EXAMPLES = 3`` and the
  config-level ``max_recent_examples`` range check. Context
  schema also enforces ``len(recent_examples) <=
  MAX_AGENT_MEMORY_EXAMPLES`` at construction.
- **Digest discipline.** [owed, Slice 2D1] When flag=False,
  ``session_id`` bytes unchanged across all other flag
  combinations. Behavior under flag=True depends on RO2 —
  either no fragment or a conditional content-addressed
  fragment in ``config_for_digest``. Either choice preserves
  flag-OFF byte identity.
- **CLI plumbing / mode-gating.** [owed, Slice 2D2]
  ``--enable-agent-visible-memory`` rejects non-``PATH_C_WARM``
  modes at the script layer per D5. Exact flag set may grow
  with owner approval; default-off is load-bearing.

---

## 5. Landed layering (current architecture)

Clean, non-circular, additive. Mirrors the B2 / B3 layering.
The diagram below reflects what is on ``main`` after Slices
1 / 2A / 2B / 2C plus the scheduled Slice 2D1+ surface.

```
┌─────────────────────────────────────────────────────┐
│  Contract layer — Slice 1 (LANDED)                  │
│  src/agent_memory/agent_memory_schema.py            │
│  src/agent_memory/agent_memory_config.py            │
│  AgentMemoryExampleRef / AgentMemoryContext /       │
│  AgentMemoryExperimentConfig; closed Literals;      │
│  MAX_AGENT_MEMORY_EXAMPLES = 3;                     │
│  AGENT_MEMORY_SCHEMA_VERSION = "1.0".               │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│  Pure builder + renderer — Slice 2A (LANDED)        │
│  src/agent_memory/agent_memory_builder.py           │
│  src/agent_memory/agent_memory_renderer.py          │
│  build_agent_memory_context(memory, query, config)  │
│      → AgentMemoryContext                           │
│  render_agent_memory_context(context, config)       │
│      → structured text                              │
│  (pure; no wall-clock; no uuid4; no data/cases;     │
│   canonical sort order only; renderer ignores       │
│   config for output bytes)                          │
└──────────────────────┬──────────────────────────────┘
                       │ (single additive hunk)
┌──────────────────────┴──────────────────────────────┐
│  Operations-agent prompt seam — Slice 2B (LANDED)   │
│  src/agents/operations_agent.py                     │
│  _build_ops_llm_user_prompt gains a guarded hunk    │
│  that appends a fixed                               │
│  HISTORICAL_STRUCTURED_MEMORY_CONTEXT section when  │
│  _b4_should_inject(ctx, cfg) is True. Rules-mode    │
│  entry unchanged.                                   │
└──────────────────────┬──────────────────────────────┘
                       │ (internal caller wiring)
┌──────────────────────┴──────────────────────────────┐
│  event_loop_c caller — Slice 2C (LANDED)            │
│  src/event_loop_c.py                                │
│  _build_agent_memory_query_for_event (W6)           │
│  _maybe_build_agent_memory_context (W4 gate)        │
│  _build_path_c_main_records gained                  │
│    agent_memory_config: Optional[...] = None        │
│  Sideband threaded through                          │
│    event_loop._run_reasoning_slice                  │
│    graph.operations_agent_node                      │
│  run_session public signature UNCHANGED.            │
└──────────────────────┬──────────────────────────────┘
                       │ (Slice 2D1, DEFERRED)
┌──────────────────────┴──────────────────────────────┐
│  Public run_session kwarg — Slice 2D1               │
│  src/event_loop_c.py::run_session                   │
│  adds agent_memory_config: Optional[...] = None     │
│  threaded into the existing                         │
│  _build_path_c_main_records kwarg. Default-off      │
│  byte identity is the hard gate. RO2 digest policy  │
│  resolved in this slice.                            │
└──────────────────────┬──────────────────────────────┘
                       │ (Slice 2D2, DEFERRED)
┌──────────────────────┴──────────────────────────────┐
│  CLI / harness — Slice 2D2                          │
│  scripts/run_session.py,                            │
│  scripts/session_eval_harness.py                    │
│  additive default-off flags; PATH_C_WARM-only at    │
│  the script layer; three-variant compare artifacts  │
│  per D7.                                            │
└──────────────────────┬──────────────────────────────┘
                       │ (Slice 2D3, DEFERRED, conditional)
┌──────────────────────┴──────────────────────────────┐
│  Session-compare visibility + optional overlay —    │
│  Slice 2D3                                          │
│  src/session/session_compare.py                     │
│  conditional agent_memory_experiment_summary        │
│  sibling block (structural only; no NL recap;       │
│   no COMPARE_REPORT_SCHEMA_VERSION bump).           │
│  src/session/session_schema.py                      │
│  adds SessionEventRecord.agent_memory_context       │
│  overlay ONLY if RO1 resolves "yes".                │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│  Tests                                              │
│  tests/test_agent_memory_*.py                       │
│  tests/test_operations_agent_agent_memory_seam.py   │
│  tests/test_event_loop_c_agent_memory_internal_     │
│    wiring.py                                        │
└─────────────────────────────────────────────────────┘
```

Import direction: always top-to-bottom. No upward import, no
cycle.

- `src/agent_memory/` imports: `src/learning/memory_schema.py`
  (read-only types), `src/learning/episodic_memory.py`
  (read-only access to rows). It does NOT import
  `src/adaptive/*`, `src/replan/*`, `src/correlator/*`,
  `src/learning/cumulative_memory.py`, `src/session/*`
  (except possibly read-only helpers from
  `src/session/digests.py` if a digest fragment is emitted),
  or `src/agents/*`.
- `src/adaptive/*`, `src/replan/*`, `src/correlator/*`,
  `src/learning/*`, `src/session/*` do NOT import from
  `src/agent_memory/`.
- Exactly one agent module imports from `src/agent_memory/`
  in Slice 1, and only to receive an `AgentMemoryContext`
  into its prompt-builder helper. The other two agent
  modules do not import from `src/agent_memory/`.

---

## 6. Where B4 logic lives (landed)

Locked and landed: **``src/agent_memory/``**.

Alternatives considered and rejected:

- **`src/learning/`** — would tangle the memory-core layer
  (source of truth for memory shapes) with a consumer layer
  (agent-prompt derivation). Even B3's loader
  (`cumulative_memory.py`) sits at the edge of that layer
  because it produces an `EpisodicMemory`. B4 produces a
  *prompt-shaped* artifact, which is structurally further from
  `src/learning/`'s responsibility.
- **`src/agents/`** — would structurally declare B4 as part of
  the agent layer, which makes it too easy for future PRs to
  widen agent output schemas "because the helper is already in
  the agent folder". Keeping B4 as a sibling subpackage makes
  the agent module's single additive hunk visible as a diff.
- **`src/session/`** — session layer owns overlay / artifact
  / compare / save / load. Agent-prompt derivation is not a
  session concern.
- **`src/adaptive/`** — explicitly forbidden by the boundary
  doc's §7. Placing the B4 logic here would structurally
  invite the adaptive gate to grow a second consumer surface.
- **A new top-level `src/experiments/`** — premature;
  overgeneralizes. B4 is one experiment; if further experiment
  branches appear, a future boundary amendment can create a
  shared root.

---

## 7. Where CLI / harness work will attach (Slice 2D2, deferred)

A single additive change on each script, landing **only after
Slice 2D1 adds the public ``agent_memory_config`` kwarg to
``run_session``** (D8 / D10 ordering).

### ``scripts/run_session.py``

- New flags (landed names):
  - ``--enable-agent-visible-memory``
  - Additional flags may be added with owner approval, but
    the only config fields currently variable at the CLI
    layer are ``enable_agent_visible_memory`` and
    ``max_recent_examples``; ``target_agent`` and
    ``context_source`` are closed Literals (D1 / D3) and
    therefore not CLI-configurable.
- Default OFF. When set:
  1. Build an ``AgentMemoryExperimentConfig`` from the flags.
  2. Enforce ``PATH_C_WARM``-only at this boundary (the script
     raises / ``parser.error(...)`` when the flag is supplied
     under a non-``PATH_C_WARM`` mode). Mirrors B3's
     ``run_session.py`` enforcement.
  3. Pass the config through the D8-landed
     ``run_session(..., agent_memory_config=...)`` kwarg —
     NOT through any private helper and NOT through any
     caller-side wrapper.
- No change to ``run_session``'s public contract beyond the
  single D8 kwarg.

### `scripts/session_eval_harness.py`

- Mirror the same flags. Add matching kwargs to
  `run_eval_harness(...)`.
- When enabled, attach the B4 config only to the
  `PATH_C_WARM` `run_session(...)` call. The other two modes
  (`BASELINE_STATIC`, `PATH_C_COLD`) receive the flag-OFF
  path unchanged.
- Emit three comparable artifacts per the contract draft §6:
  `baseline_static` (pre-B4 identical),
  `path_c_warm` policy-only (pre-B4 identical for the
  appropriate B3 setting), and
  `path_c_warm` + B4 (experiment variant).

### Slice precedent

This layout mirrors B3 Slice 2D (`--prior-session-dir` +
`--cumulative-dedupe-policy` + `PATH_C_WARM`-only script
guard) and B2 Slice 2D (`--enable-correlator` +
`--correlator-window-size` + `--correlator-pattern`). Do NOT
extract shared helpers across `run_session.py` /
`session_eval_harness.py` just because three branches now
duplicate similar flag-building code — per the closeout memo
§6, "the precedent is intentionally minimal".

---

## 8. Interfaces B4 depends on but must not modify

- `EpisodicMemory(records=...)` constructor
  (`src/learning/episodic_memory.py`) — read-only use.
  B4 receives an already-assembled `EpisodicMemory` and does
  not mutate it.
- ``EpisodicMemory.query(...)`` — read-only use; the builder
  calls this to get the matched row set per event.
- ``MemoryRecord`` pydantic class
  (``src/learning/memory_schema.py``) — validation /
  read-only typing. No schema change.
- ``MemoryQuery`` 1.0 — landed as the query shape for the B4
  builder (W6 event-type-only). No ``MemoryQuery`` schema
  change; ``event_loop_c._build_agent_memory_query_for_event``
  constructs instances with the closed shape.
- ``learning.memory_summarizer.summarize_records(records,
  query, threshold=...)`` — landed dependency. The builder
  passes ``threshold=1`` as a placeholder and overrides
  ``cold_start`` per R3. Recorded as a stability obligation
  in RO6.
- ``canonical_json(...)`` (``src/session/digests.py``) —
  available for caller-level helpers when Slice 2D1 decides
  RO2 (whether to hash a conditional B4 digest fragment).
- ``src/agents/operations_agent.py`` — the landed B4 agent.
  The seam is inside ``_build_ops_llm_user_prompt``. Do NOT
  modify its output schema ``OperationsOutput`` or the meta
  dict key set.

## 9. What does *not* need a file change in B4

- `app.py` — no FastAPI surface change. B4 does not add
  endpoints.
- `src/api/*` — no route change. The `agent_memory_experiment
  _summary` compare block, if added, is consumed by the
  existing compare-report path; no new API needed.
- `src/llm_backend.py`, `src/llm_providers/*` — no new
  provider, no new LLM call shape. B4 threads a *prompt-
  shaped artifact* into an existing LLM call inside the
  single modified agent; the LLM backend contract is
  unchanged.
- `src/retrieval.py`, `src/rag_setup.py` — agent-visible
  memory does not consult RAG. The operations agent's
  existing RAG retrieval is untouched.
- `src/supervisor.py` — orthogonal.
- `src/outcome_persistence/*` — persistence semantics
  unchanged; B4 does not write memory and does not write
  outcomes.
- `data/phase6_eval/*` — evaluation artifacts; B4 does not
  edit fixture JSONs.
- `docs/path_c_thesis_alignment.md` — optional addendum in a
  later slice. Slice 0 does not touch it.

---

## 10. Summary of open decisions that gate the next B4 slice

Matches ``docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §15`` and
``docs/B4_AGENT_VISIBLE_MEMORY_CONTRACT_DRAFT.md §11``.

**Closed** by Slices 1 / 2A / 2B / 2C / 2D0 / 2D1 / 2D1.x /
2D1.xa / 2D2 / 2D3-A / 2D3-B:

- Input surface (D2 + D3), placement (D4), target agent (D1),
  gating model (D5), compare-variant count (D7), allowed modes
  (D5) — closed by Slice 1.
- Builder flag-gating responsibility (W7 / RO7) — closed by
  Slice 2C (caller owns gating; builder is pure).
- Public-exposure shape (RO11) — locked as **D8** in Slice
  2D0 and implemented in Slice 2D1: single additive optional
  kwarg on ``run_session``.
- ``operations_mode`` scope (RO12) — locked as **D9** in
  Slice 2D0 and pinned by Slice 2D1 tests: env-only under
  B4; no ``run_session`` kwarg for it. **Slice 2D3-B
  reconfirmed** — the env-resolved value is now propagated
  into ``GraphState`` via a private internal sideband only;
  no public ``operations_mode`` kwarg added.
- Digest-fragment policy (RO2) — closed by **Slice 2D1.x**
  (F1 / F2 / F3): conditional ``agent_memory`` fragment in
  ``config_for_digest`` driven by public config identity
  only, preserving flag-OFF byte identity.
- Compare-block dimension of RO1 — closed by **Slice 2D3-A**
  (compare-only closure): additive
  ``agent_memory_variant_tags`` opt-in kwarg on
  ``build_compare_report`` + conditional
  ``agent_memory_experiment_summary`` sibling block;
  ``COMPARE_REPORT_SCHEMA_VERSION`` UNCHANGED at ``"1.1"``.
  Harness B4 ON branch emits compare + thesis through the
  kwarg.
- Controlled-facts G5 test (RO3) — closed by **Slice 2D3-B**
  (``tests/test_agent_memory_truth_stability.py`` exercises
  G5 on the real runtime path under env=``llm`` +
  PATH_C_WARM with a deterministic LLM gateway spy;
  ``tests/test_agent_memory_runtime_activation.py`` is the
  regression net guarding the env→GraphState wiring from
  closing again).

**Residual open** — deferred:

- ⟨RO1⟩ Per-event persisted overlay on
  ``SessionEventRecord`` (``agent_memory_context`` 1.2 →
  1.3). D6 still defers; landing candidate window is now
  Slice 2D4, conditional on real experiment data showing
  compare-only (Slice 2D3-A) cannot answer audit questions.
- ⟨RO4⟩ B4 × B3 interaction at runtime. Slice 2C's test
  surface confirmed ``event_loop_c.py`` does not import
  ``learning.cumulative_memory``; Slice 2D3-B's runtime
  activation does not change this contract. Confirm-or-
  amend at the next experiment-data review.
- ⟨RO5⟩ Renderer determinism already landed; the remaining
  question is whether a future slice allows a config-driven
  renderer variant. Current default: renderer ignores
  config.
- ⟨RO6⟩ ``summarize_records`` shared-helper stability
  obligation — record in boundary doc.
- ⟨RO8⟩ B4 section's relative position inside the operations
  user prompt (end-of-prompt vs immediately-after-Facts).
- ⟨RO9⟩ Whether ``llm_meta.trace`` records a B4-injected
  flag. Slice 2D3-A confirmed this stays "neither" for the
  current decision window: the compare block is the
  current observability surface; no ``llm_meta`` /
  ``_governance_meta`` shape change.
- ⟨RO10⟩ Maintenance note — future runtime slices must
  update boundary §13–§15 in the same PR (or in an
  immediate docs-sync slice). This sync slice closes the
  gap reopened by Slice 2D3-A and 2D3-B.
