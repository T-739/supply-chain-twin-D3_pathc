# PATH_C_SCHEMA_REGISTRY.md

Canonical list of all Path C-tracked schemas and their current versions.
Authority: `Path_C_Roadmap_v2_1.docx` §0.2.

Every MINOR or MAJOR bump must update this file in the same PR as the code
change, and update the corresponding fixture under `tests/fixtures/`.

Format: `MAJOR.MINOR`, no `v` prefix, no patch segment.

Phase status: **Phase 0** — shapes frozen, runtime logic deferred.

---

## Tier 1 — Path B records (Phase 0 owner-approved additive)

### `outcome_store.summary()` — 1.0

Path B summary dict. Phase 0 adds the top-level `schema_version` key.

Fields:

- `schema_version: str = "1.0"` (new in Phase 0)
- `outcomes_count: int`
- `total_cost: float` (rounded at serialization)
- `avg_cost: float` (rounded at serialization)
- `action_counts: dict[str, int]`
- `status_counts: dict[str, int]`
- `sla_preserved_count: int`
- `sla_missed_count: int`
- `auto_executed_count: int`
- `human_required_count: int`
- `recent_actions: list[dict]`
- `recent_resolution_patterns: dict[str, int]`

Change history: 1.0 — initial (Phase 0, adds `schema_version`).

### `run_event_loop` per-event record — 1.0

Each item in `event_results`.

Fields:

- `schema_version: str = "1.0"` (new in Phase 0)
- `event_id: str`
- `event_type: str`
- `severity: str`
- `scenario_context: dict`
- `governance_output: dict`
- `policy_decision: dict`
- `execution_status: str`
- `execution_outcome: dict | None`
- `trace_log: list`
- `execution_error: str` (present only on `execution_failed`)

Change history: 1.0 — initial (Phase 0, adds `schema_version`).

---

## Tier 2 — Path C overlay schemas

### `MemoryRecord` — 1.0 (`src/learning/memory_schema.py`)

- `event_id: str`
- `event_type: str`
- `event_timestamp: str`
- `action_taken: str | None`
- `execution_status: str`
- `final_route: str`
- `cost_incurred: float | None`
- `sla_preserved: bool | None`
- `risk_level: str`
- `session_id: str`
- `schema_version: str = "1.0"`

### `MemoryQuery` — 1.0 (`src/learning/memory_schema.py`)

- `event_type: str | None`
- `action_type: str | None`
- `final_route: str | None`
- `recent_n: int | None`
- `schema_version: str = "1.0"`

### `MemorySummary` — 1.0 (`src/learning/memory_schema.py`)

- `matched_records: int`
- `cold_start: bool`
- `auto_execute_success_rate: float | None`
- `sla_preservation_rate: float | None`
- `action_type_distribution: dict[str, int]`
- `avg_cost: float | None`
- `query_signature: str`
- `schema_version: str = "1.0"`

### `AdaptivePolicyAdjustment` — 1.0 (`src/adaptive/adaptive_schema.py`)

- `rule_id: str`
- `adjustment_type: Literal["UPGRADE_ONE_LEVEL", "NO_ADJUSTMENT", "COLD_START_FALLBACK"]`
- `pre_adjustment_risk: Literal["LOW","MEDIUM","HIGH"]`
- `post_adjustment_risk: Literal["LOW","MEDIUM","HIGH"]`
- `query_signature: str`
- `memory_evidence: dict`
- `notes: str`
- `schema_version: str = "1.0"`

### `AdjustmentRuleSpec` — 1.0 (`src/adaptive/adaptive_schema.py`)

- `rule_id: str`
- `description: str`
- `applies_to_event_types: list[str]`
- `schema_version: str = "1.0"`

---

## Tier 2 — Session overlay

### `GovernanceTruthRef` — 1.0 (`src/session/session_schema.py`)

- `risk_level: str`
- `recommended_candidate_type: str`
- `schema_version: str = "1.0"`

### `EffectiveDecisionRef` — 1.0 (`src/session/session_schema.py`)

- `effective_risk: str`
- `final_route: Literal["AUTO_EXECUTE", "HUMAN_REQUIRED"]`
- `action_taken: Literal["EXPEDITE","TRANSFER","COMPENSATE","NO_ACTION"] | None`
- `execution_status: Literal["executed","executed_via_demo_override","awaiting_human_review","execution_failed","unknown_route","preflight_failed"]`
- `schema_version: str = "1.0"`

### `SessionEventRecord` — 1.2 (`src/session/session_schema.py`)

- `baseline_event_result: dict`     (embedded Path B record, verbatim)
- `session_id: str`
- `mode: Literal["BASELINE_STATIC","PATH_C_COLD","PATH_C_WARM"]`
- `policy_route_source: Literal["baseline_static","adaptive_adjusted","cold_start_fallback"]`
- `adaptive_adjustment: AdaptivePolicyAdjustment | None`
- `governance_truth: GovernanceTruthRef`
- `effective_decision: EffectiveDecisionRef`
- `memory_record_id: str | None`
- `replan_trace: list[ReplanAttemptRecord] | None`    (new in 1.1, B1 Slice 1)
- `replan_triggers: list[ReplanTriggerRecord] | None` (new in 1.1, B1 Slice 1)
- `correlation_context: CorrelationContext | None`    (new in 1.2, B2 Slice 2A)
- `notes: str`
- `schema_version: str = "1.2"`

Change history:
- 1.0 — initial (Phase 0).
- 1.1 — additive B1 Slice 1: `replan_trace`, `replan_triggers` optional
  with `None` defaults. Semantics: `effective_decision` still reflects
  the **final** attempt (dual-track unchanged); when `replan_trace is
  None`, no replan cycle ran and the record is semantically equivalent
  to 1.0. Runtime paths only populate these fields if
  `ReplanConfig.enable_replan=True`.
- 1.2 — additive B2 Slice 2A: `correlation_context` optional with
  `None` default. Semantics: `None` means the correlator did not run;
  a present `CorrelationContext` with empty `signals` means the
  correlator ran and found no matches. Observability-only overlay —
  `effective_decision`, `adaptive_adjustment`, and every replan
  field are untouched by correlator output. Runtime paths only
  populate this field if `CorrelatorConfig.enable_correlator=True`.

---

## Tier 3 — Session artifact

### `SessionConfig` — 1.0 (`src/session/session_schema.py`)

- `seed: int`
- `mode: Literal["BASELINE_STATIC","PATH_C_COLD","PATH_C_WARM"]`
- `events_source: str`
- `initial_memory_digest: str`
- `schema_version: str = "1.0"`

### `SessionKPIs` — 1.1 (`src/session/session_schema.py`)

- `events_observed: int`
- `events_with_outcome: int`
- `events_skipped: int`
- `events_failed: int`
- `events_processed: int`
- `auto_execute_success_rate: float | None`
- `sla_preservation_rate: float | None`
- `total_cost: float`
- `avg_cost: float | None`
- `known_outcome_coverage: float | None`
- `replan_events_observed: int`          (new in 1.1, B1 Slice 4)
- `replan_fire_count: int`               (new in 1.1, B1 Slice 4)
- `replan_trigger_rate: float | None`    (new in 1.1, B1 Slice 4; zero-denominator → None)
- `replan_success_count: int`            (new in 1.1, B1 Slice 4)
- `replan_recovery_rate: float | None`   (new in 1.1, B1 Slice 4; zero-denominator → None)
- `schema_version: str = "1.1"`

Change history:
- 1.0 — initial (Phase 0).
- 1.1 — additive B1 Slice 4: five replan-aware KPI fields with safe
  defaults (zero-count ints, None rates). Pre-B1 artifacts that
  supplied only the old fields validate unchanged; non-replan
  sessions keep the new fields at their safe defaults
  (zero/None) — the zero-denominator rule ensures no misleading
  synthetic rates appear.

### `SessionArtifact` — 1.0 (`src/session/session_schema.py`)

- `session_id: str`
- `config: SessionConfig`
- `event_records: list[SessionEventRecord]`
- `memory_snapshot: dict`
- `kpis: SessionKPIs`
- `schema_versions: dict[str, str]`
- `notes: str`
- `schema_version: str = "1.0"`

---

## Tier 2 — B1 Replan overlay (Slice 1: contracts only)

Owner-fixed decisions (see `docs/B1_REPLAN_CONTRACT_DRAFT.md §7`):

- **D1** expected cost range is a `cost_output`-derived overlay — the
  closed provenance literal `"cost_output_derived_overlay"`. Natural-
  language governance fields are **not** admissible.
- **D3** both absolute and relative cost-deviation thresholds are
  carried on `ReplanConfig`; trigger logic deferred to Slice 2+.
- **D4** `MAX_REPLAN_ATTEMPTS = 1`. Hard cap.
- **D5** B1's second cycle is a full reasoning cycle (operations →
  cost → governance → adaptive gate → preflight → execute). Memory
  remains final-attempt-only; no per-attempt `MemoryRecord`.

### `ExpectedOutcomeRef` — 1.0 (`src/replan/replan_schema.py`)

- `expected_cost_min: float` (>= 0)
- `expected_cost_max: float` (>= expected_cost_min)
- `expected_sla_preserved: bool`
- `range_source: Literal["cost_output_derived_overlay"]` (closed set)
- `estimator_id: str` (non-empty)
- `estimator_signature: str`
- `schema_version: str = "1.0"`

Change history: 1.0 — initial (B1 Slice 1, contract only).

### `ReplanTriggerRecord` — 1.0 (`src/replan/replan_schema.py`)

- `trigger_rule_id: str` (non-empty; ∈ `KNOWN_TRIGGER_RULE_IDS`)
- `trigger_type: Literal["NO_TRIGGER","COST_DEVIATION","SLA_DEVIATION","EXECUTION_FAILED","PREFLIGHT_FAILED"]`
- `attempt_index: int` (>= 0)
- `deviation_measurement: dict[str, float | int | bool]` (numeric-only;
  no natural-language values)
- `expected_outcome_ref: ExpectedOutcomeRef | None`
- `realized_cost: float | None`
- `realized_sla_preserved: bool | None`
- `notes: str`
- `schema_version: str = "1.0"`

Change history: 1.0 — initial (B1 Slice 1, contract only).

### `ReplanAttemptRecord` — 1.0 (`src/replan/replan_schema.py`)

- `attempt_index: int` (>= 0)
- `attempt_final_route: Literal["AUTO_EXECUTE","HUMAN_REQUIRED"]`
- `attempt_action_taken: Literal["EXPEDITE","TRANSFER","COMPENSATE","NO_ACTION"] | None`
- `attempt_execution_status: Literal["executed","executed_via_demo_override","awaiting_human_review","execution_failed","unknown_route","preflight_failed"]`
- `execution_outcome: dict | None`
- `adaptive_adjustment: AdaptivePolicyAdjustment | None`
- `expected_outcome: ExpectedOutcomeRef | None`
- `trigger: ReplanTriggerRecord`
- `notes: str`
- `schema_version: str = "1.0"`

Per-attempt Literals for route / action / execution_status are
**redefined locally** in `replan_schema.py` to break a circular
import with `session.session_schema`. Their domains mirror the
Path B / Path C values exactly.

Change history: 1.0 — initial (B1 Slice 1, contract only).

### `ReplanConfig` — 1.1 (dataclass) (`src/replan/replan_config.py`)

Not a pydantic schema; listed here because it is a Path C contract.

- `enable_replan: bool = False`       (master gate, OFF by default)
- `max_replan_attempts: int = 1`      (hard cap; `__post_init__` rejects > `MAX_REPLAN_ATTEMPTS`)
- `cost_deviation_abs_threshold: float = 50.0` (>= 0; Slice 2 audit-only)
- `cost_deviation_rel_threshold: float = 0.2`  (in `[0.0, 1.0]`; Slice 2 audit-only)
- `expected_cost_band_abs: float = 25.0`       (>= 0; Slice 2, band floor)
- `expected_cost_band_rel: float = 0.1`        (in `[0.0, 1.0]`; Slice 2, band slope)
- `sla_deviation_enabled: bool = True`
- `expected_cost_range_source: Literal["cost_output_derived_overlay"] = "cost_output_derived_overlay"`

Also exported: `MAX_REPLAN_ATTEMPTS: Final[int] = 1`,
`KNOWN_TRIGGER_RULE_IDS: frozenset[str]`.

Band projection rule (consumed by
`src/replan/expected_outcome.py::estimate_expected_outcome`):

    band = max(expected_cost_band_abs,
               point_estimate * expected_cost_band_rel)
    expected_cost_min = max(0.0, point_estimate - band)
    expected_cost_max = point_estimate + band

Change history:
- 1.0 — initial (B1 Slice 1, contract only).
- 1.1 — additive B1 Slice 2: `expected_cost_band_abs`,
  `expected_cost_band_rel` added with non-breaking defaults.
  `cost_deviation_abs_threshold` / `cost_deviation_rel_threshold`
  are recorded in the Slice 2 trigger's `deviation_measurement`
  for audit but do NOT gate the decision (the range is the gate).

### `CorrelationSignal` — 1.0 (`src/correlator/correlator_schema.py`)

Evidence record for one matched compound pattern. B2 Slice 2A
adds this as a new Tier 2 schema.

- `pattern_id: Literal["ETA_PATH_COMPOUND","CARRIER_DOUBLE_HIT"]`
- `triggering_event_id: str`              (non-empty; must be in `participant_event_ids`)
- `participant_event_ids: list[str]`      (len >= 2; all non-empty)
- `shared_entities: list[AffectedEntityRef]` (may be empty only for patterns that declare `allow_empty_shared_entities=True` — P1 ETA-path)
- `window_start_ordinal: int`             (>= 0)
- `window_end_ordinal: int`               (>= `window_start_ordinal`)
- `window_size: int`                      (>= 1; carried for audit)
- `matched_conditions: list[Literal["SHARED_ETA_PATH","SAME_ENTITY_ID","STREAM_ADJACENT","SEVERITY_HIGH_CONCURRENCE"]]` (non-empty)
- `schema_version: str = "1.0"`

Invariants enforced at construction:
`len(participant_event_ids) >= 2`,
`triggering_event_id in participant_event_ids`,
`window_end_ordinal - window_start_ordinal + 1 <= window_size`,
`matched_conditions` non-empty.

Explicitly NOT on this schema: free-text explanation,
confidence/probability, cost/SLA outcome fields. Opening the
pattern-id or matched-condition Literal is a MINOR bump.

Change history: 1.0 — initial (B2 Slice 2A, contract only).

### `CorrelationContext` — 1.0 (`src/correlator/correlator_schema.py`)

Per-event sideband carrying the correlator's findings for one
stream position. Attached optionally on `SessionEventRecord`.

- `signals: list[CorrelationSignal]`      (may be empty; ordered by pattern-catalog declaration order then `window_start_ordinal`)
- `window_size: int`                       (>= 1)
- `window_events_considered: int`          (>= 0; <= `window_size`)
- `schema_version: str = "1.0"`

Semantic distinction (see `SessionEventRecord` 1.2):
- `correlation_context = None` — correlator did not run.
- `CorrelationContext(signals=[], ...)` — correlator ran and found nothing.

Change history: 1.0 — initial (B2 Slice 2A, contract only).

### `CorrelatorConfig` — 1.0 (dataclass) (`src/correlator/correlator_config.py`)

Not a pydantic schema; listed here because it is a Path C contract.

- `enable_correlator: bool = False`       (master gate, OFF by default)
- `window_size: int = 3`                  (in `[1, MAX_CORRELATOR_WINDOW]`; `__post_init__` enforces)
- `enabled_patterns: frozenset[str]`      (default = `KNOWN_CORRELATOR_PATTERN_IDS`; members must be in the known set)
- `schema_version: str = "1.0"`

Also exported: `MAX_CORRELATOR_WINDOW: Final[int] = 6`,
`KNOWN_CORRELATOR_PATTERN_IDS: frozenset[str]`.

Slice 2A ships two patterns: `ETA_PATH_COMPOUND` and
`CARRIER_DOUBLE_HIT`. Slice 2A explicitly defers
`SUPPLY_DEMAND_MISMATCH` (would require a fragile static
zone↔warehouse topology table — see
`docs/B2_CORRELATOR_BOUNDARY.md §12 D5`).

Change history: 1.0 — initial (B2 Slice 2A, contract only).

### `CumulativeMemoryConfig` — 1.0 (dataclass) (`src/learning/cumulative_memory.py`)

Not a pydantic schema; listed here because it is a Path C
contract. B3 Slice 2A adds this as a new Tier 2 contract
entry. No pydantic `MemoryRecord` / `MemoryQuery` /
`MemorySummary` shape is touched — raw `MemoryRecord` union is
sufficient because `MemoryRecord.session_id` already carries
per-row provenance.

- `prior_session_refs: tuple[str, ...]` (ordered; each entry is a
  canonical prior-session `session_id` string or an equivalent
  content-addressed reference; **raw filesystem paths are NOT
  admitted** — see `docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12 D5`)
- `dedupe_policy: Literal["drop_equal_raise_mismatch"] = "drop_equal_raise_mismatch"`
  (closed set in Slice 2A; opening is a MINOR bump)
- `max_records: int = MAX_CUMULATIVE_MEMORY_RECORDS` (must satisfy
  `1 <= max_records <= MAX_CUMULATIVE_MEMORY_RECORDS`; `__post_init__`
  enforces)
- `schema_version: str = "1.0"`

Also exported from `src/learning/cumulative_memory.py`:
`MAX_CUMULATIVE_MEMORY_RECORDS: Final[int] = 1000`,
`KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES: frozenset[str]`,
`CumulativeMemoryCollisionError` (raised by the Slice 2B
loader on same-triple non-equal collisions),
`CumulativeMemorySourceResolver = Callable[[str], list[MemoryRecord]]`
(exported type alias for the kwarg-only resolver callable; per
D10 the loader never reads the filesystem itself — concrete
resolvers are supplied by the caller: CLI in Slice 2D, test
fixtures in Slice 2B/2B.5),
`load_cumulative_memory(config, *, source_resolver) -> EpisodicMemory`
(signature only in Slice 2A; body lands in Slice 2B.
`source_resolver` is kwarg-only and required per D10 — see
`docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12 D10`).

Dedupe key (Slice 2B semantics):
`(session_id, event_timestamp, event_id)` — matches the triple
already used by `session.digests.memory_record_id(...)`.
Same triple + equal row → silently drop.
Same triple + non-equal row → raise `CumulativeMemoryCollisionError`.

Digest contribution principle (see
`docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12 D5`): the existing
`initial_memory_digest` input to `session_id` already captures
the post-dedupe content fingerprint. A later slice MAY add a
conditional `cumulative_memory` fragment to `config_for_digest`
encoding ordered prior `session_id` strings or per-file content
digests — NEVER filesystem paths.

Change history: 1.0 — initial (B3 Slice 2A, contract only).

---

## Tier 2 — B4 Agent-visible memory experiment (Slice 1: contracts only)

Owner-fixed decisions (see `docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §12`):

- **D1** first experiment target is ``operations`` agent only;
  governance agent is not touched in B4 v1.
- **D2** ``AgentMemoryContext`` is the single agent-visible contract
  surface. No free-text surfaces; raw ``MemoryRecord`` dumps and
  direct cumulative-memory loader outputs are not admissible.
- **D3** ``AgentMemoryContext`` = aggregate summary fields + capped
  ``recent_examples``; cap is ``MAX_AGENT_MEMORY_EXAMPLES=3``.
- **D4** placement is new subpackage ``src/agent_memory/``; Slice 1
  ships contracts only. The future operations-agent injection seam
  is out-of-scope here.
- **D5** gating via ``AgentMemoryExperimentConfig``;
  ``enable_agent_visible_memory=False`` hard default;
  ``target_agent="operations"`` only;
  ``allowed_modes=frozenset({"PATH_C_WARM"})``;
  ``context_source="structured_summary_plus_recent_examples"``.
- **D6** no ``SessionEventRecord`` bump in Slice 1; no
  compare-report block; no KPI.
- **D7** future compare surface = three variants
  (``baseline_static`` / ``path_c_warm`` policy-only / ``path_c_warm``
  + agent-visible memory experiment); docs-only in Slice 1.

### `AgentMemoryExampleRef` — 1.0 (`src/agent_memory/agent_memory_schema.py`)

Structured reference to one historical memory row included in an
``AgentMemoryContext`` as a ``recent_examples`` entry. No free text,
no confidence, no governance NL fields. Closed Literals for action /
route / status are redefined locally to avoid a circular import with
``session.session_schema`` — same workaround used by
``replan.replan_schema``.

- `event_id: str` (non-empty)
- `event_type: str` (non-empty)
- `source_session_id: str` (non-empty; mirrors
  `MemoryRecord.session_id`)
- `action_taken: Literal["EXPEDITE","TRANSFER","COMPENSATE","NO_ACTION"] | None`
- `final_route: Literal["AUTO_EXECUTE","HUMAN_REQUIRED"]`
- `execution_status: Literal["executed","executed_via_demo_override","awaiting_human_review","execution_failed","unknown_route","preflight_failed"]`
- `cost_incurred: float | None`
- `sla_preserved: bool | None`
- `schema_version: str = "1.0"`

Change history: 1.0 — initial (B4 Slice 1, contract only).

### `AgentMemoryContext` — 1.0 (`src/agent_memory/agent_memory_schema.py`)

The single B4 agent-visible contract surface (D2). Aggregate
summary fields mirror `MemorySummary` 1.0 shape names for
auditability but **do not inherit** from it — the two serve
different consumers (adaptive policy gate vs. agent prompt) and
must be able to evolve independently under their own boundary
rules.

- `matched_records: int` (>= 0)
- `cold_start: bool`
- `query_signature: str` (non-empty; content-addressed — never
  a free-text rationale)
- `auto_execute_success_rate: float | None` (in `[0.0, 1.0]` if set)
- `sla_preservation_rate: float | None` (in `[0.0, 1.0]` if set)
- `avg_cost: float | None`
- `action_type_distribution: dict[str, int]` (non-negative int
  counts; non-empty string keys)
- `recent_examples: list[AgentMemoryExampleRef]` (length `0 <= L <=
  MAX_AGENT_MEMORY_EXAMPLES`; empty list is valid for cold-start)
- `schema_version: str = "1.0"`

Invariants enforced at construction:
`0 <= len(recent_examples) <= MAX_AGENT_MEMORY_EXAMPLES`,
`matched_records >= 0`, rate fields bounded in `[0.0, 1.0]`,
`query_signature` non-empty.

Explicitly NOT on this schema (enforced via `extra='forbid'` and
the B4 no-truth-write test): `rationale` / `rationale_trace` /
`explanation` / `confidence` / `confidence_note` / `cost_summary` /
`situational_explanation` / `alternative_actions` /
`correlation_context` / `baseline_event_result` / `risk_level` /
`recommended_action`.

Change history: 1.0 — initial (B4 Slice 1, contract only).

### `AgentMemoryExperimentConfig` — 1.0 (dataclass) (`src/agent_memory/agent_memory_config.py`)

Not a pydantic schema; listed here because it is a Path C
contract. Frozen dataclass parallel to `ReplanConfig` /
`CorrelatorConfig` / `CumulativeMemoryConfig`. No pydantic
schema change on `MemoryRecord` / `MemoryQuery` / `MemorySummary`
/ `SessionEventRecord` is required by B4 Slice 1.

- `enable_agent_visible_memory: bool = False` (hard default; D5)
- `target_agent: Literal["operations"] = "operations"` (closed
  set `KNOWN_AGENT_MEMORY_TARGETS`; D1)
- `context_source: Literal["structured_summary_plus_recent_examples"]
  = "structured_summary_plus_recent_examples"` (closed set
  `KNOWN_AGENT_MEMORY_CONTEXT_SOURCES`; D3 / D5)
- `max_recent_examples: int = MAX_AGENT_MEMORY_EXAMPLES` (must
  satisfy `1 <= max_recent_examples <= MAX_AGENT_MEMORY_EXAMPLES`;
  `__post_init__` enforces)
- `allowed_modes: frozenset[str] = frozenset({"PATH_C_WARM"})`
  (closed subset; non-empty; every member must be in
  `{"PATH_C_WARM"}` in Slice 1; D5)
- `schema_version: str = "1.0"`

Also exported from `src/agent_memory/agent_memory_config.py`:
`MAX_AGENT_MEMORY_EXAMPLES: Final[int] = 3`,
`KNOWN_AGENT_MEMORY_TARGETS: frozenset[str] = frozenset({"operations"})`,
`KNOWN_AGENT_MEMORY_CONTEXT_SOURCES: frozenset[str] = frozenset({
"structured_summary_plus_recent_examples"})`.

Slice 1 deliberately does NOT bump `SessionEventRecord`; any
per-event overlay recording what the agent was shown is deferred
to a later slice (see boundary §12 D6). The compare-report
visibility block and the CLI / harness integration are also
deferred; `COMPARE_REPORT_SCHEMA_VERSION` stays at `"1.1"`.

Change history: 1.0 — initial (B4 Slice 1, contract only).
