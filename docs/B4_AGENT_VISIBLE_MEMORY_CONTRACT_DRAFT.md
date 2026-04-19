# B4_AGENT_VISIBLE_MEMORY_CONTRACT_DRAFT.md

Status: **B4 Slices 1, 2A, 2B, 2C, 2D0, 2D1, 2D1.x, 2D1.xa,
2D2, 2D3-A, 2D3-B all landed. D1–D11 are owner-locked** (see
`docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §12`). This draft
carries the structural rationale the D-list took as input,
kept for review / audit. §3 / §4 / §5 / §6 / §7 were
candidate-heavy in Slice 0; below they are re-framed with a
"**Landed in:**" line per section that points at the
corresponding runtime slice, so a reader can tell at a glance
what is still a candidate discussion and what is a historical
record of how the locked decisions were reached.

§9's "Tentative schema surface (NOT locked)" is similarly
annotated — every candidate in §9.1 and §9.2 is now locked at
1.0 and registered in ``PATH_C_SCHEMA_REGISTRY.md``; §9.3
(optional per-event overlay on ``SessionEventRecord``) stays
explicitly open under D6 + RO1.

§11 carries only the narrow residual open questions that
concern future B4 slices, mirrored from boundary §15.

Previous status markers:
- Slice 0 draft (candidate-heavy, no owner-locked decisions).
- Slice 1 landed (D1–D7 locked).
- Slice 2C landed + Slice 2D0 amendment (D8–D11 locked;
  RO7 / RO11 / RO12 closed).
- **Slice 2D1 landed** (public
  ``run_session(..., agent_memory_config=None)`` kwarg).
- Slice 2D1.x landed (conditional ``agent_memory``
  ``config_for_digest`` fragment; RO2 closed).
- Slice 2D1.xa landed (``_SCHEMA_VERSIONS`` audit —
  artifact-nested schemas removed from the registry; only
  ``agent_memory_experiment_config`` retained per B1/B2
  precedent).
- Slice 2D2 landed (scripts + harness exposure via the
  Slice 2D1 public kwarg; single ``--enable-agent-visible-
  memory`` flag on both scripts; harness emits the locked
  three-variant experiment set under H4).
- **Slice 2D3-A landed** (compare-only closure: additive
  ``agent_memory_variant_tags`` opt-in kwarg on
  ``build_compare_report`` + conditional
  ``agent_memory_experiment_summary`` sibling block;
  ``COMPARE_REPORT_SCHEMA_VERSION`` unchanged at ``"1.1"``;
  harness B4 ON branch now writes ``compare_report.json`` +
  ``thesis_report.md`` over the locked triplet through the
  opt-in kwarg).
- **Slice 2D3-B landed** (runtime activation seam repair:
  env-resolved ``operations_mode`` threaded from
  ``event_loop_c._build_path_c_main_records`` through a new
  optional ``operations_mode`` kwarg on
  ``event_loop._run_reasoning_slice`` into
  ``GraphState["operations_mode"]``; closes the gap where
  W4 fired but the operations agent dispatch silently fell
  back to rules. RO3 (G5 controlled-facts test exercised
  on the real runtime path) closed by
  ``tests/test_agent_memory_truth_stability.py`` +
  ``tests/test_agent_memory_runtime_activation.py``).

Authority: `docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md`,
`PATH_C_BOUNDARY.md`, `PATH_C_SCHEMA_REGISTRY.md`,
`docs/B1_REPLAN_CONTRACT_DRAFT.md`,
`docs/B2_CORRELATOR_CONTRACT_DRAFT.md`,
`docs/B3_CUMULATIVE_MEMORY_CONTRACT_DRAFT.md`.

This document is the historical + residual-open-question
record for the B4 contract. Schema shapes are locked at 1.0
(see §9) and registered in ``PATH_C_SCHEMA_REGISTRY.md``;
design axes C1–C7 are closed by D1–D11; the sections below
preserve the rationale for each lock so a future reviewer can
understand WHY without re-deriving it. The document is
deliberately NOT a pure current-state spec — that role belongs
to the registry + boundary doc. This draft carries the
"because of tradeoff X we picked Y" narrative.

Sections §3 / §4 / §5 / §6 / §7 retain their original
exploratory framing with a "**Landed:**" lead line pinning the
current reality. §9 mirrors the registered schemas. §11 carries
the residual-open questions that future slices will close.

---

## 1. Why B4 needs its own memory-to-agent contract

Until B4, every branch has structurally preserved
"memory consumers = {adaptive policy gate}". B1 / B2 / B3 each
added new layers (replan overlay, correlator sideband,
cumulative-memory loader) without extending that set. The
adaptive gate is a **structured consumer**: it reads
`MemoryRecord` rows by structural query and produces a
`MemorySummary` — never free text.

B4 introduces a **second, fundamentally different consumer**:
an agent prompt. Agent prompts consume *text*, and the agent
then produces *text* (including the five existing natural-
language governance fields). The two properties that made the
adaptive gate a safe memory consumer — structured query,
structured output — are absent in an agent prompt context.

A separate contract is therefore necessary because:

1. **The input to the consumer is not a `MemoryRecord`.** It is
   a *prompt-shaped artifact*: a derived, structured-or-text
   representation produced from memory. The contract must name
   this artifact and bound its shape before any runtime lands.
2. **The output pressure differs.** The adaptive gate produces
   `AdaptivePolicyAdjustment` (closed-Literal fields). An
   agent produces free text that could paraphrase memory into
   an authoritative-looking claim. The contract must explicitly
   forbid that paraphrase path.
3. **The gating surface differs.** The adaptive gate's
   "enable" surface is the existence of memory rows. B4's
   enable surface is a dedicated feature flag whose default-off
   state must preserve byte identity at every layer, including
   the agent's full prompt-input bytes.
4. **The comparability surface differs.** Two runs that differ
   only on "adaptive gate saw N memory rows vs. M" stay
   comparable through `SessionKPIs` and the existing compare
   report. Two runs that differ on "agent saw B4 content vs.
   not" differ at the prompt-input level, which the existing
   compare surface does not distinguish. A new compare
   variant is required.

This draft structures each of those four points as a candidate
axis below.

## 2. Available inputs vs. what cannot be elevated to agent truth

The repo already contains several memory-like / memory-derived
artifacts. B4 should consider them as **candidate inputs**
(§3 below) but must never elevate any of them to authoritative
truth inside an agent output.

Repo-grounded inventory (archival — Slice 1 picked the
``MemoryRecord`` row set as the only admitted input; other
candidates stayed forbidden or deferred):

| Candidate | Where | Admissible as B4 input? | Admissible as truth? |
|---|---|---|---|
| `MemoryRecord` row set | `src/learning/episodic_memory.py` via `EpisodicMemory` | Yes (structured; already the adaptive gate's input) | **No** — never as `GovernanceTruthRef` / `EffectiveDecisionRef` content |
| `MemorySummary` | `src/learning/memory_schema.py` (1.0) | Conditional — the current `MemorySummary` is produced by and for the adaptive gate; B4 reusing it risks coupling. A **new** B4-local summary type is preferred over reusing this class directly. | **No** |
| Cumulative memory rows (B3) | `src/learning/cumulative_memory.py` output (`EpisodicMemory`) | Yes, but only indirectly — B4 receives the already-assembled `EpisodicMemory` and does not re-import cumulative_memory.py. The content distinction is carried by `MemoryRecord.session_id`. | **No** |
| `correlation_context` (B2 sideband) | `SessionEventRecord.correlation_context` | **Candidate but NOT in Slice 1.** Ties B4 to B2. If a later slice wants it, that is a separate branch. | **No** |
| `replan_trace` / `replan_triggers` (B1) | `SessionEventRecord.replan_trace` / `replan_triggers` | **Candidate but NOT in Slice 1.** Ties B4 to B1. | **No** |
| Full `SessionEventRecord` overlay (adaptive adjustment, effective decision, etc.) | `src/session/session_schema.py` | Read-only reference for building structured summaries. **Must not be paraphrased back into the agent output.** | **No** |
| Research Core cases / evaluation fixtures | `src/evaluation.py`, `data/cases/*.json` | **NO.** Research Core is forbidden for every Path C code path, including B4. | N/A |
| Natural-language governance fields (`cost_summary`, `confidence_note`, `rationale_trace`, `situational_explanation`, `alternative_actions`) | `GovernanceOutput` | **NO.** These are prior agent *outputs*; feeding them back into memory and then back into a later agent prompt is a truth-collapse vector. Forbidden under the no-NL-truth discipline already asserted in B2's `test_correlator_no_nl_truth.py` (which B4 must mirror with `tests/test_agent_memory_no_nl_truth.py`). | **NO** |
| Twin state / operational context | `src/twin_state.py`, existing agent prompt inputs | Already provided to the prompt; B4 does not re-inject or duplicate it. | N/A (existing rules apply) |

The two "NO truth" columns together define the no-truth-
elevation rule that B4 must enforce regardless of which input
candidate is chosen in §3.

## 3. Candidate input surface (§C1 from the boundary doc)

**Landed:** ``AgentMemoryContext`` = structured aggregate
summary + capped ``recent_examples`` (hard cap 3). Choice (a)
+ (b) fused into one locked shape by D2 + D3. Landed in
Slice 1 contracts + Slice 2A builder. Candidate (c) and (d)
are explicitly out of scope for every B4 slice unless a
separate owner-approved boundary amendment reopens the set.

- **(a) Structured memory summary.** A new B4-local
  prompt-shaped type (candidate name: `AgentMemoryContext`)
  carrying structured derivations — e.g., `match_count` over
  an event_type, success rate for an action_type, SLA
  preservation rate. Modelled on `MemorySummary` but NOT the
  same class (reusing `MemorySummary` 1.0 would couple the
  adaptive gate's summary surface to an agent-visible surface).
  Rendered to prompt text by a dedicated, deterministic
  formatter inside the new B4 subpackage.

  Pros: structured, no per-row leakage, easy to bound size,
    natural parallel to how the adaptive gate consumes memory.
  Cons: the agent cannot "point at" a specific past event —
    only at aggregate stats.

- **(b) Selected memory records.** A deterministic pick of
  ≤ N `MemoryRecord` rows matching a structured query
  (query shape candidate: `MemoryQuery` 1.0, or a new B4-local
  query type). Rendered to prompt text as structured fields,
  never as free-text paraphrase.

  Pros: concrete past-event grounding; easy to audit which
    rows the agent saw.
  Cons: larger prompt footprint; harder to bound; higher
    risk of the agent copy-pasting a row into an output NL
    field and thereby paraphrasing memory as truth
    (mitigated by the no-NL-truth scan, but stronger in shape
    (a)).

- **(c) Cumulative-memory-derived excerpt.** Same as (a) or (b)
  but filtered to rows where `MemoryRecord.session_id` differs
  from the current session — i.e., explicitly cross-session.
  Ties B4's experiment to whether B3 is also enabled;
  structurally awkward because B4 would need to re-query the
  received `EpisodicMemory` by `session_id`. **Not the first
  experiment target.**

- **(d) `correlation_context` excerpt.** Use B2's correlator
  sideband as agent input. Structurally ties B4 to B2 and to
  `src/session/session_schema.py`. **Explicitly NOT B4 Slice 1.**

Constraint: **one surface in Slice 1.** Adding a second is a
later slice with its own boundary amendment (see boundary §4
point 9).

## 4. Candidate placement (§C2 from the boundary doc)

**Landed:** combination (b) + (c) — a pre-agent assembler
(``build_agent_memory_context``) in the new
``src/agent_memory/`` subpackage produces the structured
artifact; a single additive hunk inside
``_build_ops_llm_user_prompt`` in
``src/agents/operations_agent.py`` appends the fixed
``HISTORICAL_STRUCTURED_MEMORY_CONTEXT`` section to the user
prompt, guarded by ``_b4_should_inject``. Landed in Slice 2A +
2B. No agent-wrapper layer was introduced.

Where does the B4 content reach the agent?

- **(a) Agent wrapper layer.** A new `src/agent_memory/`
  function wraps `run_operations_agent` / `run_governance_agent`,
  modifying the agent's input before the existing helper is
  called. The agent module itself is untouched.

  Pros: smallest diff on the agent module (zero).
  Cons: the wrapper must duplicate some of the agent's input
    assembly; the actual prompt-builder helper would not see
    the B4 artifact directly; harder to prove the B4 artifact
    becomes part of the prompt text without reading the
    wrapper and the builder together.

- **(b) Prompt-builder seam.** An additive hunk inside the
  existing `_build_..._prompt` helper, guarded by the B4 flag,
  that consumes a prompt-shaped artifact passed in as an
  argument and appends it to the prompt in a structured-text
  block.

  Pros: the prompt-builder remains the single source of truth
    for what the agent sees; the B4 hunk is a single
    reviewable block; a "flag-OFF byte-identical" test can
    capture the full prompt string across flag toggles.
  Cons: requires a one-line modification in one agent module
    (inside the private builder), bounded by the boundary
    doc's "single additive hunk" rule.

- **(c) Pre-agent context assembler.** A new
  `src/agent_memory/` function produces the prompt-shaped
  artifact from memory + config, and is consumed by (b)'s
  additive hunk. This is not an *alternative* to (b) — it is a
  layering choice below (b): (c) produces the artifact, (b)
  threads it in.

The boundary doc's preferred starting point is **(b) + (c)**.
That keeps the agent module's diff minimal (one hunk), while
the derivation logic lives in its own testable subpackage.
Planning turn may overrule.

## 5. Candidate initial target agent (§C3 from the boundary doc)

**Landed:** operations agent (``src/agents/operations_agent.py``)
is the single B4 target for all current slices. Governance and
cost agent modules are structurally untouched. Locked by D1
and enforced by ``tests/test_agent_memory_single_agent_injection.py``.

Only one agent is modified in Slice 1. Repo-grounded
comparison:

- **`src/agents/operations_agent.py`.**
  - Output schema: `OperationsOutput` (ranked
    `RankedCandidate` list + structured evidence refs). No
    free-text truth-adjacent fields.
  - Prompt builder: `_build_ops_llm_system_prompt` /
    `_build_ops_llm_user_prompt`.
  - Memory-relevance: operations agent picks candidates; past
    operational outcomes are directly relevant to that pick
    (which expediter worked last time on a similar event).
  - Truth-leakage risk (R2): **lower** — output carries no NL
    field that could paraphrase memory as authority.
  - Governance still scores whatever the operations agent
    produces, so governance-truth invariance on *identical
    facts* is easier to assert.

- **`src/agents/governance_agent.py`.**
  - Output schema: `GovernanceOutput` with
    `cost_summary`, `confidence_note`, `rationale_trace`,
    `situational_explanation`, `alternative_actions` — five
    NL fields.
  - Prompt builder: `_build_llm_system_prompt` /
    `_build_llm_user_prompt`.
  - Memory-relevance: memory as governance evidence
    (how often did this action succeed in similar events).
  - Truth-leakage risk (R2): **higher** — the five NL fields
    are the exact surface where memory paraphrase could be
    mistaken for ground truth. Requires the no-NL-truth
    guard plus a stricter governance-truth-invariance test.

**Locked starting point:** operations agent, per D1. The
governance-agent alternative was considered and explicitly
rejected for every landed slice; reopening it requires an
owner-approved boundary amendment on the ``target_agent``
closed Literal.

## 6. Candidate compare surface (§C6 / boundary §8 R3)

**Landed:** three-variant contract, docs-only. Locked by D7.
The actual harness code that emits the three variants is
deferred to a later slice past D10 step 3 (scripts / harness
additive flags). The current landed slices do not emit a
``session_compare`` sibling block for B4 — that sits behind
RO1 / RO9.

The existing harness emits comparable artifacts for up to
three modes (`BASELINE_STATIC`, `PATH_C_COLD`, `PATH_C_WARM`).
Under B4, `PATH_C_WARM` becomes the candidate variant whose
content depends on the B4 flag.

Minimum compare surface required to interpret B4 results:

- **Variant 1 — `baseline_static`.** Pre-B4 baseline, B4 has
  no reachable path here (mode-gating rule). Byte-identical
  to pre-B4 `main`.
- **Variant 2 — `path_c_warm` (policy-only, B4 OFF).**
  Equivalent to today's `PATH_C_WARM` run (with or without
  B3 cumulative memory, per the harness's pre-existing
  choice). Byte-identical to pre-B4 `main`.
- **Variant 3 — `path_c_warm` (B4 ON).** Same inputs as
  Variant 2, but `enable_agent_visible_memory=True`. This is
  the experiment variant.

The three variants share `baseline_event_result` bytes
(Path B raw shadow), share `MemoryRecord` bytes (memory is
append-only and does not depend on what the agent saw on the
*prompt* path), but can legitimately differ on agent prompt
inputs, agent outputs, and — downstream — `EffectiveDecision
Ref` bytes.

The harness must keep Variants 1 and 2 byte-identical to
pre-B4 `main` (that's G13 in the boundary doc). A new compare
block (`agent_memory_experiment_summary`) surfaces when
Variant 3 is present. `COMPARE_REPORT_SCHEMA_VERSION` stays
at `"1.1"` (mirroring B2 / B3 Slice 2C discipline).

Why at least three variants are necessary:

- Variant 2 vs. Variant 3 is the direct measurement of what
  B4 does (same B3 memory, different agent visibility).
- Variant 1 vs. Variant 2 preserves the existing pre-B4 claim
  (Path C-min adaptive-gate path), unchanged by B4.
- A 2-variant comparison (1 vs. 3) would confound "policy-
  only effect" with "agent-visible effect". The 3-variant
  form separates them.

## 7. Candidate gating model (§C5 from the boundary doc)

**Landed:** (b) feature flag + closed ``allowed_modes =
frozenset({"PATH_C_WARM"})``. Locked by D5 at the config layer
and by W4 at the caller layer (Slice 2C
``_maybe_build_agent_memory_context``). Caller owns flag
gating; builder is a pure function of its inputs (W7 /
RO7 — closed). Operations-mode dispatch continues to be
env-only under D9 — no ``operations_mode`` public kwarg is
added by B4.

**Caller-side responsibility split, landed in Slice 2C:**

- ``event_loop_c._build_path_c_main_records`` is the single
  caller site that invokes ``_maybe_build_agent_memory_context``
  before ``_run_reasoning_slice``, so the builder receives
  pre-current-event memory (W5 — closed).
- The query shape is event-type-only (W6 — closed):
  ``MemoryQuery(event_type=event.event_type.value,
  action_type=None, final_route=None, recent_n=None)``.
  This is the runtime-locked form; future slices widening the
  query shape need an owner-approved boundary amendment.
- The builder itself does NOT check the flag — by design
  (W7). Flag-gating lives entirely at the caller layer, so
  the builder can be tested / reused / driven from any
  future caller without duplicate gating.

Gate surfaces to decide between:

- **(a) Feature flag only.** `AgentMemoryExperimentConfig.
  enable_agent_visible_memory: bool = False`. Mode-agnostic.
  Reachable from any mode; caller decides when to attach.
- **(b) Feature flag + mode-gating.** Same as (a), plus a
  caller-layer rule attaching the config only for
  `PATH_C_WARM`. Mirrors B3 D7. `BASELINE_STATIC` and
  `PATH_C_COLD` always receive the B4-OFF path.
- **(c) Feature flag + variant selector.** Not landed. A
  ``context_source`` Literal was envisioned here as a
  multi-value selector; Slice 1 instead locked it as a
  single-value closed Literal
  (``"structured_summary_plus_recent_examples"``). A later
  boundary amendment could open the Literal to add a second
  surface, but no landed slice does so.

**Default-off is an invariant across (a) / (b) / (c).**
Landed choice: **(b)** — mode-gating via
``allowed_modes = frozenset({"PATH_C_WARM"})``. The
``_maybe_build_agent_memory_context`` caller gate in
``event_loop_c.py`` enforces this structurally for the
internal wiring; Slice 2D1's public ``run_session`` kwarg
must preserve the same gating at the caller boundary. D9
additionally pins that operations-mode dispatch is not
publicized alongside B4.

## 8. Forbidden truth moves (hard rules)

These rules are unconditional — they apply to every B4
slice regardless of future variant work.

1. **No memory-derived text written back to
   `GovernanceTruthRef` or `EffectiveDecisionRef`.**
   A test asserts the bytes of these two fields are unchanged
   across `enable_agent_visible_memory={False,True}` on a
   controlled input set.
2. **No memory-derived text written into
   `baseline_event_result`.** Path B raw stays verbatim.
3. **No modification of B3 loader semantics.** B4's
   subpackage does not import
   `src/learning/cumulative_memory.py` and does not
   reinterpret what `EpisodicMemory` rows mean. It consumes
   rows through the read-only
   `src/learning/memory_schema.py` / `episodic_memory.py`
   shapes.
4. **No treatment of free-text governance output as
   authoritative.** The five NL fields on `GovernanceOutput`
   (`cost_summary`, `confidence_note`, `rationale_trace`,
   `situational_explanation`, `alternative_actions`) are
   never consumed by B4 as truth for a downstream prompt.
   Source scan asserts no reference to these five field names
   inside the new B4 subpackage. Mirrors B2's
   `test_correlator_no_nl_truth.py` pattern.
5. **No addition of fields to any agent output schema.**
   `GovernanceOutput`, `OperationsOutput`, any cost-agent
   output class, and `_governance_meta` shape stay frozen.
6. **No writing of a B4 experiment artifact into memory.** B4
   does not produce `MemoryRecord` rows. The adaptive gate's
   consumer-side memory remains the output of the existing
   `_build_memory_record_from_*` helpers in
   `src/event_loop_c.py`.
7. **No overloading of `MemorySummary` 1.0.** If B4 produces
   a structured summary for the agent, it is a **new B4-local
   type**, not a variant of `MemorySummary`.
8. **No paraphrase of `MemoryRecord` rows into natural-
   language strings inside the B4 subpackage for
   truth-adjacent purposes.** Prompt rendering may emit
   structured text; the structured text is an *input hint* to
   the agent, not an output that appears elsewhere as
   evidence.

## 9. Schema surface

All three B4-owned schemas are **landed at 1.0 in Slice 1** and
registered in ``PATH_C_SCHEMA_REGISTRY.md`` (B4 section). The
field lists below mirror the actual frozen shapes in
``src/agent_memory/agent_memory_schema.py`` and
``src/agent_memory/agent_memory_config.py`` byte-for-byte.
§9.3 (optional per-event overlay on ``SessionEventRecord``)
stays **explicitly deferred** under D6 + RO1.

### 9.1 `AgentMemoryExperimentConfig` — LOCKED at 1.0 (Slice 1)

Frozen dataclass parallel to ``ReplanConfig`` /
``CorrelatorConfig`` / ``CumulativeMemoryConfig``. Not pydantic.
Lives in ``src/agent_memory/agent_memory_config.py``.

Fields (landed):

- ``enable_agent_visible_memory: bool = False`` — master gate
  (D5). Hard default; load-bearing for default-off byte
  identity.
- ``target_agent: Literal["operations"] = "operations"`` —
  closed Literal (D1). Paired with module-level
  ``KNOWN_AGENT_MEMORY_TARGETS = frozenset({"operations"})``.
- ``context_source: Literal["structured_summary_plus_recent_examples"]
  = "structured_summary_plus_recent_examples"`` — closed
  Literal (D3 / D5). Paired with module-level
  ``KNOWN_AGENT_MEMORY_CONTEXT_SOURCES =
  frozenset({"structured_summary_plus_recent_examples"})``.
- ``max_recent_examples: int = MAX_AGENT_MEMORY_EXAMPLES``
  (landed value ``3`` via the module constant). ``__post_init__``
  enforces ``1 <= max_recent_examples <=
  MAX_AGENT_MEMORY_EXAMPLES``.
- ``allowed_modes: frozenset[str] =
  frozenset({"PATH_C_WARM"})`` — closed set (D5). ``__post_init__``
  rejects any member not in that set and rejects empty.
- ``schema_version: str = "1.0"``.

Module-level constants (exported):

- ``MAX_AGENT_MEMORY_EXAMPLES: Final[int] = 3``.
- ``KNOWN_AGENT_MEMORY_TARGETS: frozenset[str] =
  frozenset({"operations"})``.
- ``KNOWN_AGENT_MEMORY_CONTEXT_SOURCES: frozenset[str] =
  frozenset({"structured_summary_plus_recent_examples"})``.

Invariants (tested by
``tests/test_agent_memory_schema_frozen.py`` and
``tests/test_agent_memory_contract_no_truth_write.py``):

- Strict ``bool`` on ``enable_agent_visible_memory``.
- Closed-Literal membership on ``target_agent`` and
  ``context_source``.
- Range + type check on ``max_recent_examples``.
- ``allowed_modes`` normalization + closed-set membership.
- ``schema_version`` pinned to ``"1.0"``.

### 9.2 `AgentMemoryContext` — LOCKED at 1.0 (Slice 1)

Pydantic schema (``model_config = ConfigDict(extra='forbid')``)
parallel to ``CorrelationContext``. The single B4 agent-visible
artifact (D2). Built by
``agent_memory.agent_memory_builder.build_agent_memory_context``
and consumed by the operations-agent prompt seam landed in
Slice 2B.

Fields (landed):

- ``matched_records: int`` (>= 0).
- ``cold_start: bool``.
- ``query_signature: str`` (non-empty; content-addressed, never
  a free-text rationale).
- ``auto_execute_success_rate: Optional[float]`` (in
  ``[0.0, 1.0]`` when set).
- ``sla_preservation_rate: Optional[float]`` (in
  ``[0.0, 1.0]`` when set).
- ``avg_cost: Optional[float]``.
- ``action_type_distribution: dict[str, int]`` (non-empty
  string keys; non-negative int counts).
- ``recent_examples: list[AgentMemoryExampleRef]``
  (length ``0 <= L <= MAX_AGENT_MEMORY_EXAMPLES``; empty list
  is valid under cold-start).
- ``schema_version: str = "1.0"``.

Explicitly NOT on this schema (``extra='forbid'`` rejects all
of the following, enforced by
``tests/test_agent_memory_contract_no_truth_write.py``):

- Free-text ``rationale`` / ``rationale_trace`` /
  ``explanation`` / ``situational_explanation`` /
  ``summary_paragraph``.
- ``confidence`` / ``confidence_note``.
- ``cost_summary`` / ``alternative_actions``.
- Cross-layer overlay names: ``correlation_context``,
  ``baseline_event_result``, ``replan_trace`` /
  ``replan_triggers``.
- Governance truth names: ``risk_level``,
  ``recommended_action``, ``recommended_candidate_type``,
  ``governance_truth``, ``effective_decision``.

### 9.2.1 `AgentMemoryExampleRef` — LOCKED at 1.0 (Slice 1)

Pydantic schema (``extra='forbid'``) for one
``recent_examples`` entry on an ``AgentMemoryContext``.
Structured reference to a historical memory row — never a
free-text recap, never a confidence scalar. Closed Literals
for ``action_taken`` / ``final_route`` / ``execution_status``
are **locally redefined** inside
``src/agent_memory/agent_memory_schema.py`` to avoid a
circular import with ``session.session_schema``, matching
the precedent in ``replan.replan_schema``.

Fields (landed):

- ``event_id: str`` (non-empty).
- ``event_type: str`` (non-empty).
- ``source_session_id: str`` (non-empty; mirrors
  ``MemoryRecord.session_id`` so cross-session provenance
  from B3 flows through verbatim).
- ``action_taken: Literal["EXPEDITE","TRANSFER","COMPENSATE",
  "NO_ACTION"] | None``.
- ``final_route: Literal["AUTO_EXECUTE","HUMAN_REQUIRED"]``.
- ``execution_status: Literal["executed",
  "executed_via_demo_override","awaiting_human_review",
  "execution_failed","unknown_route","preflight_failed"]``.
- ``cost_incurred: Optional[float]``.
- ``sla_preserved: Optional[bool]``.
- ``schema_version: str = "1.0"``.

### 9.3 Optional `SessionEventRecord` overlay — DEFERRED (RO1 still open)

No landed slice adds this overlay. D6 continues to defer it.
If a future slice decides the experiment needs a per-event
record of what the agent was shown, the candidate is:

- Field name: ``agent_memory_context:
  Optional[AgentMemoryContext] = None``.
- MINOR bump on ``SessionEventRecord``: 1.2 → 1.3.
- ``None`` means B4 did not run (flag OFF or mode-gated out).
- Populated means B4 ran and attached the exact artifact the
  agent saw.

If the compare-report sibling block (D7; candidate name
``agent_memory_experiment_summary``) is judged sufficient, the
overlay never lands and ``SessionEventRecord`` stays at 1.2.
The decision window is Slice 2D3 (see boundary §6).

## 10. Digest-contribution policy (LANDED — Slice 2D1.x / F1–F3)

**Landed:** option (b) — conditional fragment. The two
candidates below are kept for archival rationale.

Archival candidates:
- **(a) No digest fragment.** Tracks the B4 experiment
  structurally but not in ``session_id``. Rejected because
  two differently-configured B4 runs would share a
  ``session_id``, undermining replay / compare / audit.
- **(b) Conditional fragment.** When
  ``enable_agent_visible_memory=True``, emit a fragment into
  ``config_for_digest["agent_memory"]`` encoding the B4
  config identity. Mirrors the B1 / B2 / B3
  conditional-fragment pattern.

Landed behavior (Slice 2D1.x):

- ``agent_memory_config is None`` → no fragment.
- ``agent_memory_config.enable_agent_visible_memory is
  False`` → no fragment.
- ``agent_memory_config.enable_agent_visible_memory is
  True`` → emit a deterministic ``agent_memory`` fragment
  into ``config_for_digest`` whose content is locked by
  F3: ``{"enable_agent_visible_memory": True,
  "target_agent", "context_source", "max_recent_examples",
  "allowed_modes" (sorted list), "schema_version"}``.
- Fragment is driven **only** by the public config object
  (F2): env ``SUPPLY_CHAIN_TWIN_OPERATIONS_MODE``, session
  ``mode``, and the runtime W4 gate are NOT digest inputs.
- Default-off byte identity is preserved: any run with no
  kwarg, with a default config, or with a disabled config
  produces a pre-B4-identical ``session_id``.

Pinned by
``tests/test_run_session_agent_memory_public_kwarg.py``
§6 (six tests covering stability, shift-on-enable,
env-insensitivity, mode-insensitive fragment, and F3
shape).

## 11. Residual open questions (for future B4 slices)

Slices 1 / 2A / 2B / 2C / 2D0 / 2D1 / 2D1.x / 2D1.xa / 2D2 /
2D3-A / 2D3-B have closed RO2 / RO3 / RO7 / RO11 / RO12, plus
C1 / C2 / C3 / C5 / C6 / Q1–Q10 from the Slice 0 draft, plus
the compare-block dimension of RO1. The remaining open items
below are mirrored from the boundary doc's §15.

- **RO1 (re-stated as the future-overlay window — Slice 2D4).**
  Slice 2D3-A took the **compare-only** path: the conditional
  ``agent_memory_experiment_summary`` sibling block on the
  compare report (driven by the
  ``agent_memory_variant_tags`` opt-in kwarg) supersedes the
  candidate ``SessionEventRecord.agent_memory_context``
  overlay. The overlay (MINOR bump 1.2 → 1.3) lands ONLY if
  real experiment data shows compare-only cannot answer
  audit questions. D6 still defers.
- **RO4 (= Q10).** Confirm B4 × B3 interaction stays "caller
  assembles, B4 consumes" at public-kwarg landing. Slice
  2D3-B's runtime activation does not change this contract;
  re-confirm at the next experiment-data review.
- **RO5.** Renderer determinism already landed
  (subprocess-level PYTHONHASHSEED test pinned in
  ``tests/test_agent_memory_renderer.py``); the remaining
  question is whether a future slice allows a config-driven
  renderer variant — by default the current invariants stay.
- **RO6.** Record the B4 builder's ``threshold=1`` coupling
  to ``summarize_records`` as a stability obligation on the
  summarizer.
- **RO8.** Lock B4 section's relative position inside the
  operations user prompt (currently "end of prompt after
  Facts block").
- **RO9.** Decide whether ``llm_meta.trace`` records a
  B4-injected flag (meta-shape change) vs RO1 overlay vs
  neither. Slice 2D3-A confirmed this stays "neither" for
  the current decision window: the compare block IS the
  current observability surface.
- **RO10.** Maintenance note — future runtime slices must
  update boundary §13 / §14 / §15 in the same PR (or in an
  immediate docs-sync slice) so the landed-status gap does
  not reopen.

Closed (no longer open):
- **C1 / Q1** → D2 + D3 (``AgentMemoryContext`` = aggregate
  summary + capped recent examples; landed in Slice 1 + 2A).
- **C2 / Q2** → D4 (new subpackage + pre-agent assembler +
  single additive hunk in operations prompt builder;
  landed in 2A + 2B).
- **C3 / Q3** → D1 (operations agent only; enforced by
  Slice 2B's single-agent-injection test).
- **C5 / Q5 / Q9** → D5 (default-off + ``allowed_modes =
  {"PATH_C_WARM"}``; landed in Slice 1, enforced by Slice 2C
  W4 gate).
- **C6 / Q6** → D7 (three-variant compare surface; docs
  lock landed in Slice 1; harness code landed in Slice
  2D2; compare-block code landed in Slice 2D3-A).
- **RO7** → W7 (builder is pure; flag gating lives at caller;
  landed in Slice 2C ``_maybe_build_agent_memory_context``).
- **RO11** → D8 (public exposure via
  ``run_session(..., agent_memory_config=None)``; locked in
  Slice 2D0 docs amendment, implemented in Slice 2D1).
- **RO12** → D9 (``operations_mode`` stays env-only under
  B4; locked in Slice 2D0, pinned by Slice 2D1 public-API
  tests; reconfirmed by Slice 2D3-B which threads the
  env-resolved mode through a private internal sideband
  only — no public ``operations_mode`` kwarg added).
- **RO2** → Slice 2D1.x F1 / F2 / F3 (conditional
  ``agent_memory`` fragment in ``config_for_digest``;
  public-config-identity only, not runtime-gate activation).
- **RO3** → Slice 2D3-B
  (``tests/test_agent_memory_truth_stability.py`` exercises
  G5 on the real runtime path under env=``llm`` +
  PATH_C_WARM with a deterministic LLM gateway spy; per-event
  ``GovernanceTruthRef`` / ``EffectiveDecisionRef`` /
  ``baseline_event_result`` bytes pinned equal across
  B4 OFF vs ON, with the operations seam genuinely firing on
  the ON run as confirmed by
  ``tests/test_agent_memory_runtime_activation.py``).
- **Compare-block dimension of RO1** → Slice 2D3-A
  (additive opt-in ``agent_memory_experiment_summary``
  sibling block on ``build_compare_report``; harness B4 ON
  branch emits compare + thesis through the kwarg).

## 12. Version-bump table (cumulative through Slice 2C + 2D0 + 2D1 + 2D1.x)

| Record | Old | New | Nature |
|---|---|---|---|
| `AgentMemoryExampleRef` | — | `1.0` | New pydantic schema (B4 Slice 1, contract only). |
| `AgentMemoryContext` | — | `1.0` | New pydantic schema (B4 Slice 1, contract only). |
| `AgentMemoryExperimentConfig` | — | `1.0` | New frozen dataclass contract (B4 Slice 1). |
| `MemoryRecord` | `1.0` | `1.0` | **No bump.** |
| `MemoryQuery` | `1.0` | `1.0` | **No bump.** |
| `MemorySummary` | `1.0` | `1.0` | **No bump.** |
| `SessionEventRecord` | `1.2` | `1.2` | **No bump** (D6). |
| `SessionConfig` | `1.0` | `1.0` | **No bump.** |
| `SessionKPIs` | `1.1` | `1.1` | **No bump.** (No B4 KPI.) |
| `SessionArtifact` | `1.0` | `1.0` | **No bump.** |
| `COMPARE_REPORT_SCHEMA_VERSION` | `1.1` | `1.1` | **No bump** (D6 / D7). |
| `GovernanceOutput` | frozen | frozen | **No change.** |
| `OperationsOutput` | frozen | frozen | **No change.** |

## 13. Why D1–D11 are locked (cumulative closeout rationale)

The Slice 0 draft deferred the D-list because the owner had not
yet chosen among the coupled axes (input surface / placement /
target agent / overlay / gating / digest / compare shape). That
choice has been made (see boundary §12). Slice 2D0 extends the
lock with D8–D11 which fix the shape of the next public
exposure step:

- **D8** — public exposure via a single additive optional
  ``run_session(..., agent_memory_config=None)`` kwarg. No
  scripts / harness / CLI bypass; no parallel public
  entrypoint. Rationale in boundary §12 D8: private helpers
  are not a stable caller surface and B4 must be reviewable
  as a proper experiment branch.
- **D9** — ``operations_mode`` stays env-only under B4. The
  B4 public diff must be a single additive kwarg; a second
  publicizer for operations_mode is a separate line of work
  that has not been owner-approved and would widen the B4
  diff past the "one kwarg" invariant.
- **D10** — strict ordering: boundary lock (Slice 2D0) →
  public kwarg wiring (next slice) → scripts / harness / CLI
  exposure (subsequent slice). Merging steps is out of scope.
- **D11** — Slice 2D0 is docs + header comments only. No
  signature changes, no runtime behavior changes, no tests.

The locks are tight enough to make the contract useful for an
experiment, and narrow enough to leave each subsequent slice
a simple, reviewable wiring job.

Why these seven locks are safe to freeze now:

- **D1 (operations-only target)** — the operations agent's
  `OperationsOutput` has no free-text truth-adjacent fields,
  so truth-leakage pressure on the B4 surface is structurally
  minimal. Governance remains the downstream truth producer.
- **D2+D3 (`AgentMemoryContext` = summary + capped examples)**
  — the narrowest agent-visible surface that still lets the
  experiment say "you have seen this historical pattern
  before". No free text, no confidence, no paraphrase.
- **D4 (subpackage placement)** — `src/agent_memory/` sits
  beside `src/correlator/` / `src/learning/cumulative_memory.py`
  as a sibling additive subpackage. The future single
  additive hunk inside the operations prompt-builder is
  reviewable as a single diff.
- **D5 (default-off + closed `allowed_modes` + closed
  `context_source`)** — every dimension of the experiment's
  gating is a closed Literal in Slice 1. Opening any of them
  requires a boundary amendment, not a config tweak.
- **D6 (no `SessionEventRecord` bump; no compare block; no
  KPI)** — keeps the Slice 1 freeze narrow, and lets the
  owner decide RO1 after seeing runtime data rather than
  guessing.
- **D7 (three-variant compare surface)** — the only way to
  separate "policy-only effect" from "agent-visible effect"
  without confounding them with the baseline-vs-C-min delta.

The residual open questions in §11 are runtime-surface
choices that a later slice can resolve without re-opening any
of D1–D7.

### 13.1 Slice 2D3-A and 2D3-B — closeout rationale

**Why compare-only (2D3-A), not overlay-first.** D6's
"defer overlay until experiment data" call held: a
``SessionEventRecord.agent_memory_context`` overlay would
add a ``"agent_memory_context": null`` key on every
event record in every mode (BASELINE_STATIC included)
because pydantic ``model_dump()`` emits ``None``-defaulted
fields, requiring a 1.2 → 1.3 bump and rebaselining of
several pinned tests for a feature that is still default-
off and still an experiment. Slice 2D3-A instead added a
strictly opt-in compare-report sibling block driven by
the new ``agent_memory_variant_tags`` kwarg. The block is
structural-only (variant tags, session_ids, warm-pair
diverged-event ids) and bumps no schema version.
``COMPARE_REPORT_SCHEMA_VERSION`` stays ``"1.1"``, mirroring
the B1 / B2 / B3 conditional-sibling-block pattern. RO1's
overlay candidate stays deferred behind a future Slice 2D4
to be re-opened only if real experiment data shows the
compare block is insufficient.

**Why a runtime activation seam repair (2D3-B).** Before
2D3-B, ``event_loop_c`` resolved ``operations_mode`` from
the env and used it for the W4 gate, but
``event_loop._run_reasoning_slice`` never wrote that value
into ``GraphState``. The graph node defaulted
``state.get("operations_mode") or "rules"`` and
``agents.operations_agent._resolve_ops_mode("rules")``
short-circuited the env (because the explicit truthy
``"rules"`` arg wins over ``os.environ``). Net: under
env=``llm`` + PATH_C_WARM + B4-enabled config, W4 fired
and built an ``AgentMemoryContext``, but the operations
agent dispatched to rules and never reached
``_enrich_ops_with_llm`` — the prompt seam never injected.
The harness's third "agent-visible" variant produced no
agent-visible signal. 2D3-B threads the already-resolved
``operations_mode`` into a new optional ``Any``-typed
kwarg on ``_run_reasoning_slice`` which writes it into
``GraphState["operations_mode"]``; Path B (no kwarg)
stays byte-identical, env-unset Path C-min writes
``"rules"`` (treated identically to absent). No public
surface change, no agent-module change, no graph-node
change.

**Why no observability marker (RO9 stays deferred).**
Adding an ``llm_meta.trace`` field that records "this LLM
call carried the B4 section" would change ``_governance_
meta`` shape (forbidden by §7) for governance, or extend
``llm_meta`` for operations (a meta-shape break). Either
choice forces a re-baselining of every existing
``llm_meta``-pinned test. The compare-only block in
2D3-A is the current observability surface; that sufficed
for the controlled-facts G5 test to be meaningful (the
test directly observes the operations LLM prompt via a
gateway spy and asserts the locked section header is
present). RO9 may reopen if a future audit need cannot
be satisfied by either compare-only OR a per-event
overlay (RO1).
