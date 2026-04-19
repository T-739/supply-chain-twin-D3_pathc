"""event_loop_c.py — Path C Phase 1/2 outer orchestrator.

Flow:

  1. Compute deterministic ``session_id`` from
     (seed, config, event stream, initial memory).
  2. Run Path B's ``run_event_loop`` *once*, verbatim, to produce the
     canonical ``baseline_event_result`` series (the Path B shadow).
  3. Based on ``mode``:
     - ``BASELINE_STATIC``: Phase 1 behavior. No adaptive overlay. For
       each event, ``SessionEventRecord.effective_decision`` mirrors
       ``baseline_event_result`` by construction (dual-track rule, §0.3).
     - ``PATH_C_COLD`` / ``PATH_C_WARM``: Phase 2 Path C main path.
       Runs a parallel adaptive orchestration over a fresh live state,
       consults the adaptive policy gate (``decide_policy_adaptive``),
       runs the governance-metadata preflight before every execution,
       and calls ``execute_action(..., require_metadata=True)`` — no
       text fallback on the Path C main path.
  4. In all modes the memory grows by exactly one ``MemoryRecord`` per
     event. In ``PATH_C_*`` modes the record reflects what the Path C
     main path actually did; in ``BASELINE_STATIC`` it reflects the
     Path B shadow.
  5. Assemble a deterministic ``SessionArtifact``.

Determinism rules (Roadmap §1.D + §2.D):
  - No wall-clock input, no uuid4, no hash-seed-dependent iteration.
  - ``baseline_event_result`` is embedded by reference-copy — Path B's
    raw dict is NEVER mutated. Path-C-only statuses (notably
    ``"preflight_failed"``) appear ONLY in ``effective_decision``.
  - ``governance_output`` is NEVER mutated by the adaptive layer.

Truth boundary:
  - does NOT import evaluation or action_code_mapper.
  - does NOT read data/cases/*.json.
  - Path C-min mainline rule stays: learning injection on the
    *policy* path flows exclusively through the adaptive policy
    gate. ``GovernanceOutput`` is never mutated by the adaptive
    layer; the dual-track truth (``GovernanceTruthRef`` /
    ``EffectiveDecisionRef``) is preserved.

B4 agent-visible memory experiment branch (independent of Path
C-min mainline — see docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md):
  - Landed slices: 1 (contracts), 2A (pure builder +
    deterministic renderer), 2B (operations-agent LLM prompt
    seam), 2C (internal caller wiring here), 2D1 (public
    ``run_session(..., agent_memory_config=None)`` kwarg),
    2D1.x (conditional ``agent_memory`` digest fragment),
    2D1.xa (``_SCHEMA_VERSIONS`` audit), 2D2 (scripts /
    harness exposure via the Slice 2D1 public kwarg —
    ``--enable-agent-visible-memory`` on both scripts +
    locked three-variant harness experiment set), 2D3-A
    (compare-only closure: additive
    ``agent_memory_variant_tags`` opt-in kwarg on
    ``session_compare.build_compare_report`` + conditional
    ``agent_memory_experiment_summary`` sibling block;
    harness B4 ON branch now writes ``compare_report.json``
    + ``thesis_report.md`` over the locked triplet through
    that kwarg), 2D3-B (runtime activation seam repair: the
    env-resolved ``operations_mode`` computed here is now
    threaded through the new ``operations_mode`` kwarg on
    ``event_loop._run_reasoning_slice`` into
    ``GraphState["operations_mode"]`` so the operations
    agent dispatch in ``graph.operations_agent_node``
    observes the same env reality the W4 gate observes).
    Under these slices, when and ONLY when every W4
    condition holds (``agent_memory_config`` non-None and
    enabled; ``mode == "PATH_C_WARM"``; operations_mode
    resolves to ``"llm"``; ``"PATH_C_WARM" in allowed_modes``),
    a deterministic memory-derived ``AgentMemoryContext``
    reaches the operations agent's LLM user prompt as a fixed
    ``HISTORICAL_STRUCTURED_MEMORY_CONTEXT`` section AND —
    after Slice 2D3-B — the operations agent dispatch
    actually takes the LLM path so the section is genuinely
    injected end-to-end.
  - B4 is a default-off experiment branch. The master gate
    ``AgentMemoryExperimentConfig.enable_agent_visible_memory``
    defaults to False. ``run_session`` exposes B4 through a
    single additive optional kwarg (D8 / P1 / Slice 2D1);
    there is no second caller path. ``operations_mode`` stays
    env-only (D9 / Slice 2D3-B reconfirmed: the
    env→GraphState propagation is a private internal
    sideband, not a public kwarg).
  - ``session_id`` identity (Slice 2D1.x / F1 / F2):
    ``config_for_digest`` gains an ``agent_memory`` fragment
    exactly when ``agent_memory_config.enable_agent_visible_memory``
    is True. The fragment reflects the public config identity
    only — not the env-resolved operations mode, not the
    runtime W4 gate, not the session mode. Two runs with the
    same enabled config produce the same ``session_id`` even if
    only one of them actually activates B4 at runtime. Runs
    with ``agent_memory_config=None`` or the default
    ``AgentMemoryExperimentConfig()`` (flag False) keep their
    pre-B4 ``session_id`` byte-identical.
  - B4 does NOT touch ``SessionEventRecord`` or
    ``SessionKPIs`` under any landed slice (D6 / RO1 still
    defers the per-event overlay; no B4 KPI under any
    scheduled slice). The compare report gains an additive
    conditional sibling block in Slice 2D3-A, opt-in via
    ``build_compare_report(..., agent_memory_variant_tags=
    ...)``; ``COMPARE_REPORT_SCHEMA_VERSION`` stays
    ``"1.1"``. ``GovernanceTruthRef``,
    ``EffectiveDecisionRef``, ``baseline_event_result`` are
    all byte-unchanged by the injection path (G5 pinned by
    ``tests/test_agent_memory_truth_stability.py`` on the
    real runtime path). Governance agent, cost agent,
    replan, correlator, adaptive policy gate, cumulative
    memory loader, ``llm_meta`` shape, ``_governance_meta``
    shape are structurally untouched.
"""

from __future__ import annotations

from typing import Any, Optional

from event_engine import generate_demo_event_stream
from event_loop import (
    _run_reasoning_slice,
    _twin_state_to_agent_dict,
    load_baseline_twin_state,
    run_event_loop,
)
from event_schema import EventPayload
from event_state_mapper import map_event_to_state
from execution_adapters import (
    ExecutionInfeasibleError,
    GovernanceActionParseError,
    execute_action,
)
from outcome_store import OutcomeStore
from twin_state import TwinState

from adaptive.adaptive_policy_config import (
    AdaptivePolicyGateConfig,
    EventContext,
)
from adaptive.adaptive_policy_gate import decide_policy_adaptive
from adaptive.adaptive_schema import AdaptivePolicyAdjustment
from adaptive.preflight import (
    GovernanceMetaPreflightError,
    validate_governance_meta,
)
from agent_memory.agent_memory_builder import build_agent_memory_context
from agent_memory.agent_memory_config import AgentMemoryExperimentConfig
from agent_memory.agent_memory_schema import AgentMemoryContext
from correlator.correlator_config import CorrelatorConfig
from correlator.correlator_engine import compute_correlation_context
from learning.episodic_memory import EpisodicMemory
from learning.memory_schema import MemoryQuery, MemoryRecord
from replan.replan_config import ReplanConfig
from replan.replan_orchestrator import ReplanCycleResult, run_replan_cycle
from replan.replan_schema import ReplanAttemptRecord, ReplanTriggerRecord
from session.digests import (
    compute_session_id,
    digest_config_dict,
    digest_event_stream,
    digest_memory_records,
    memory_record_id,
)
from session.session_schema import (
    EffectiveDecisionRef,
    GovernanceTruthRef,
    SessionArtifact,
    SessionConfig,
    SessionEventRecord,
    SessionKPIs,
)


SUPPORTED_MODES: tuple[str, ...] = (
    "BASELINE_STATIC", "PATH_C_COLD", "PATH_C_WARM",
)

_ADAPTIVE_MODES: frozenset[str] = frozenset({"PATH_C_COLD", "PATH_C_WARM"})


_SCHEMA_VERSIONS: dict[str, str] = {
    "adaptive_policy_adjustment": "1.0",
    "adjustment_rule_spec": "1.0",
    "effective_decision_ref": "1.0",
    "event_result": "1.0",
    "governance_truth_ref": "1.0",
    "memory_query": "1.0",
    "memory_record": "1.0",
    "memory_summary": "1.0",
    "outcome_summary": "1.0",
    "session_artifact": "1.0",
    "session_config": "1.0",
    "session_event_record": "1.2",
    "session_kpis": "1.1",
    # B1 replan-component versions. These correspond to schemas and
    # config records that appear inside serialized artifacts either
    # directly (as nested fields on ``SessionEventRecord.replan_trace``
    # / ``replan_triggers``) or by reference (``replan_config``
    # digest contribution when replan is enabled). Keys follow the
    # existing snake_case naming convention.
    "expected_outcome_ref": "1.0",
    "replan_trigger_record": "1.0",
    "replan_attempt_record": "1.0",
    "replan_config": "1.1",
    # B2 correlator-component versions. Nested inside
    # ``SessionEventRecord.correlation_context`` only when
    # ``CorrelatorConfig.enable_correlator=True``.
    "correlation_signal": "1.0",
    "correlation_context": "1.0",
    "correlator_config": "1.0",
    # B4 agent-visible memory experiment branch version. Only the
    # config-level schema is registered here, matching the B1
    # ``replan_config`` / B2 ``correlator_config`` precedent: the
    # config participates in ``config_for_digest`` when
    # ``enable_agent_visible_memory`` is True (see
    # ``_agent_memory_config_digest_fragment`` below), so registering
    # its version here lets ``SessionArtifact.schema_versions`` audit
    # which B4 config contract the session ran against.
    #
    # ``AgentMemoryExampleRef`` / ``AgentMemoryContext`` are
    # **deliberately NOT registered** here: unlike B1's
    # ``replan_trigger_record`` / ``replan_attempt_record`` (nested
    # inside ``SessionEventRecord.replan_trace``) and B2's
    # ``correlation_signal`` / ``correlation_context`` (nested inside
    # ``SessionEventRecord.correlation_context``), B4 currently has
    # NO ``SessionEventRecord`` overlay field under any landed slice
    # (D6 / RO1 still defers it). Those two pydantic schemas never
    # appear inside a serialized ``SessionArtifact``; putting their
    # version keys here would pre-announce an artifact contract that
    # does not exist. If RO1 later lands an overlay, add the keys
    # back together with the ``SessionEventRecord`` MINOR bump in
    # the same PR.
    "agent_memory_experiment_config": "1.0",
}


def _correlator_config_digest_fragment(
    correlator_config: CorrelatorConfig,
) -> dict:
    """Per-run config fragment contributed to ``config_for_digest``.

    Included in the session_id digest ONLY when
    ``enable_correlator`` is True. When the correlator is disabled,
    ``session_id`` retains its pre-B2 formula exactly — byte-identity
    is preserved. When enabled, the correlator parameters that
    actually affect behavior (window size + pattern subset) are
    hashed in so reruns with the same inputs remain replay-stable.
    """
    return {
        "enable_correlator": True,
        "window_size": int(correlator_config.window_size),
        "enabled_patterns": sorted(correlator_config.enabled_patterns),
    }


def _agent_memory_config_digest_fragment(
    agent_memory_config: AgentMemoryExperimentConfig,
) -> dict:
    """Per-run B4 config fragment contributed to ``config_for_digest``.

    Included in the session_id digest ONLY when
    ``enable_agent_visible_memory`` is True (Slice 2D1.x / F1).
    When the flag is False, or when no ``agent_memory_config`` is
    passed to ``run_session``, ``session_id`` retains its pre-B4
    formula exactly — default-off byte identity is preserved.

    The fragment reflects the **public config identity** only
    (F2): it does not encode ``mode``, the
    ``SUPPLY_CHAIN_TWIN_OPERATIONS_MODE`` env var, the W4
    runtime gate, or memory state. Two runs whose B4 public
    config dicts are equal produce equal fragments even if one
    ran under ``rules`` env and the other under ``llm`` env, or
    one ran under ``PATH_C_WARM`` and the other under
    ``PATH_C_COLD``. This mirrors B1 / B2 / B3 precedent: the
    digest hashes the run configuration identity, not whether a
    particular code branch actually fired.

    Field order is the landed Slice 1 field order; closed-Literal
    singletons (``target_agent``, ``context_source``) are
    recorded explicitly so a future Literal widening shows up as
    a digest change for the already-landed config shape too.
    """
    return {
        "enable_agent_visible_memory": True,
        "target_agent": str(agent_memory_config.target_agent),
        "context_source": str(agent_memory_config.context_source),
        "max_recent_examples": int(agent_memory_config.max_recent_examples),
        "allowed_modes": sorted(agent_memory_config.allowed_modes),
        "schema_version": str(agent_memory_config.schema_version),
    }


def _replan_config_digest_fragment(replan_config: ReplanConfig) -> dict:
    """Per-run config fragment contributed to ``config_for_digest``.

    Included in the session_id digest ONLY when ``enable_replan`` is
    True. When replan is disabled, ``session_id`` retains its pre-B1
    formula exactly — byte-identity is preserved and the digest
    produced by ``digest_config_dict`` is unchanged. When replan is
    enabled, the replan parameters that actually affect behavior are
    hashed in so reruns with the same inputs remain replay-stable.
    """
    return {
        "enable_replan": True,
        "max_replan_attempts": int(replan_config.max_replan_attempts),
        "cost_deviation_abs_threshold": float(
            replan_config.cost_deviation_abs_threshold
        ),
        "cost_deviation_rel_threshold": float(
            replan_config.cost_deviation_rel_threshold
        ),
        "expected_cost_band_abs": float(replan_config.expected_cost_band_abs),
        "expected_cost_band_rel": float(replan_config.expected_cost_band_rel),
        "sla_deviation_enabled": bool(replan_config.sla_deviation_enabled),
        "expected_cost_range_source": str(
            replan_config.expected_cost_range_source
        ),
    }


_VALID_ACTIONS: frozenset[str] = frozenset({"EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"})
_PATH_B_EXECUTION_STATUSES: frozenset[str] = frozenset({
    "executed",
    "executed_via_demo_override",
    "awaiting_human_review",
    "execution_failed",
    "unknown_route",
})
_PATH_C_EXECUTION_STATUSES: frozenset[str] = _PATH_B_EXECUTION_STATUSES | {"preflight_failed"}


# ---------------------------------------------------------------------------
# B4 Slice 2C — internal caller wiring for agent-visible memory.
#
# See docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §12 D1/D4/D5.
# Slice 2C originally lived entirely on the internal caller path:
#   - ``run_session`` public signature did NOT change;
#   - ``SessionEventRecord`` / ``SessionConfig`` / digests / compare
#     were untouched;
#   - the B4 context was reachable only through private helpers
#     that tests could drive directly.
# Slice 2D1 grew ``run_session`` by exactly one optional kwarg
# (``agent_memory_config``); Slice 2D1.x added the conditional
# ``agent_memory`` digest fragment; Slice 2D3-A added the
# additive ``agent_memory_variant_tags`` opt-in kwarg + the
# conditional ``agent_memory_experiment_summary`` sibling block
# on ``session_compare`` (no version bump); Slice 2D3-B threads
# the env-resolved ``operations_mode`` from
# ``_build_path_c_main_records`` into
# ``GraphState["operations_mode"]`` via a new optional kwarg on
# ``event_loop._run_reasoning_slice`` so the operations agent
# dispatch reaches its LLM path under env=``llm``. The actual
# prompt injection happens inside the operations agent LLM path,
# landed in Slice 2B. Slice 2C's job here is to decide WHEN to
# build a context and pass it through.
# ---------------------------------------------------------------------------

#: Env var the operations agent uses to resolve rules-vs-llm mode.
#: Duplicated here (same literal name) rather than imported from
#: ``agents.operations_agent`` so the Path C orchestrator does not
#: reach into the agent module's private surface. Per the closeout
#: memo (B2/B3 §6 "precedent is intentionally minimal"), tiny
#: duplications like this are preferred to premature extraction.
_OPS_MODE_ENV_NAME: str = "SUPPLY_CHAIN_TWIN_OPERATIONS_MODE"
_OPS_MODE_VALID: frozenset[str] = frozenset({"rules", "llm"})


def _resolve_operations_mode_from_env() -> str:
    """Return ``"llm"`` or ``"rules"`` based on the env var.

    Mirrors the ``operations_agent._resolve_ops_mode(None)`` resolution
    path without importing the private helper. Default is ``"rules"``.
    """
    import os as _os

    raw = (_os.environ.get(_OPS_MODE_ENV_NAME) or "").strip().lower()
    if raw in _OPS_MODE_VALID:
        return raw
    return "rules"


def _build_agent_memory_query_for_event(event: EventPayload) -> MemoryQuery:
    """Build the B4 Slice 2C MemoryQuery for one event.

    Locked per W6 to a deterministic event-type-only query:

      - ``event_type`` = current event's type;
      - ``action_type`` = None;
      - ``final_route`` = None;
      - ``recent_n``  = None.

    Pure function. No wall-clock, no uuid, no session-truth reads.
    Future slices may widen this catalog behind an owner-approved
    boundary amendment.
    """
    return MemoryQuery(
        event_type=event.event_type.value,
        action_type=None,
        final_route=None,
        recent_n=None,
    )


def _maybe_build_agent_memory_context(
    memory: EpisodicMemory,
    event: EventPayload,
    *,
    mode: str,
    operations_mode: str,
    agent_memory_config: Optional[AgentMemoryExperimentConfig],
) -> Optional[AgentMemoryContext]:
    """B4 Slice 2C caller-side gating (W4).

    Returns a populated ``AgentMemoryContext`` iff all five W4
    conditions hold:

      1. ``agent_memory_config is not None``
      2. ``agent_memory_config.enable_agent_visible_memory is True``
      3. ``mode == "PATH_C_WARM"``
      4. ``operations_mode == "llm"``
      5. ``"PATH_C_WARM" in agent_memory_config.allowed_modes``

    Otherwise returns ``None``. The ``memory`` snapshot read here
    is the pre-current-event memory (W5): the caller in
    ``_build_path_c_main_records`` invokes this helper BEFORE
    appending the current event's ``MemoryRecord``.

    This helper is pure: no mutation, no wall-clock, no
    cross-branch imports.
    """
    if agent_memory_config is None:
        return None
    if not agent_memory_config.enable_agent_visible_memory:
        return None
    if mode != "PATH_C_WARM":
        return None
    if operations_mode != "llm":
        return None
    if "PATH_C_WARM" not in agent_memory_config.allowed_modes:
        return None
    query = _build_agent_memory_query_for_event(event)
    return build_agent_memory_context(memory, query, agent_memory_config)


# ---------------------------------------------------------------------------
# Phase 1 compatibility: metadata-only governance truth shim
# ---------------------------------------------------------------------------


class GovernanceTruthShimError(ValueError):
    """Phase 1 metadata-only shim failed to extract a governance action prefix."""


def _recommended_candidate_type_shim(governance_output: dict) -> str:
    """Phase 1 metadata-only, read-only shim.

    Path B's ``event_result`` does not expose ``_governance_meta``, so
    ``GovernanceTruthRef.recommended_candidate_type`` is sourced by
    parsing the ``recommended_action`` prefix. Metadata-only: never
    read by a decision path. Phase 2 Path C main path uses the true
    ``_governance_meta`` side-channel directly (no shim).
    """
    recommended = governance_output.get("recommended_action")
    if not isinstance(recommended, str) or not recommended:
        raise GovernanceTruthShimError(
            f"governance_output.recommended_action missing or non-string: "
            f"{recommended!r}"
        )
    prefix = recommended.split(":", 1)[0].strip()
    if prefix not in _VALID_ACTIONS:
        raise GovernanceTruthShimError(
            f"governance_output.recommended_action prefix={prefix!r} is not "
            f"one of {_VALID_ACTIONS} (full value: {recommended!r})"
        )
    return prefix


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_session(
    *,
    seed: int,
    mode: str,
    events: Optional[list[EventPayload]] = None,
    events_source: str = "demo_stream",
    initial_twin_state: Optional[TwinState] = None,
    initial_memory: Optional[EpisodicMemory] = None,
    adaptive_config: Optional[AdaptivePolicyGateConfig] = None,
    replan_config: Optional[ReplanConfig] = None,
    correlator_config: Optional[CorrelatorConfig] = None,
    agent_memory_config: Optional[AgentMemoryExperimentConfig] = None,
) -> SessionArtifact:
    """Run one Path C session and produce a deterministic SessionArtifact.

    ``BASELINE_STATIC`` is Phase-1-equivalent behavior.
    ``PATH_C_COLD`` / ``PATH_C_WARM`` drive the Phase 2 Path C main
    path with adaptive policy gate + preflight + metadata-mandatory
    execution.

    The adaptive layer is consulted only in ``PATH_C_*`` modes. In
    ``PATH_C_COLD`` with empty seed memory, the first
    ``min_records_for_shift`` events are cold-start fallbacks
    (decision-byte-identical to baseline). Warm events may diverge.

    ``agent_memory_config`` is the B4 agent-visible memory experiment
    branch's optional public kwarg (Slice 2D1 / D8 / P1). Default is
    ``None``; default-off byte identity is a hard invariant. When
    supplied with ``enable_agent_visible_memory=True``, the B4
    caller-side gate inside ``_build_path_c_main_records`` (W4) only
    fires when all five conditions hold simultaneously: mode is
    ``"PATH_C_WARM"``, operations-agent dispatch resolves to
    ``"llm"`` (env-only per D9; Slice 2D3-B propagates that env
    reality into ``GraphState["operations_mode"]`` via an
    internal sideband so the operations agent dispatch actually
    takes the LLM path), the config flag is on, and
    ``"PATH_C_WARM"`` is in ``allowed_modes``. Outside that gate,
    the kwarg is a no-op. Slice 2D1.x landed a conditional
    ``agent_memory`` fragment in ``config_for_digest`` driven by
    public config identity (RO2 closed); ``session_id`` bytes
    therefore shift exactly when the public config has B4 enabled,
    not when the runtime gate fires. Slice 2D1 added no
    ``SessionEventRecord`` overlay, no KPI; CLI / harness wiring
    landed in Slice 2D2; the conditional
    ``agent_memory_experiment_summary`` sibling block on
    ``session_compare`` (opt-in via ``agent_memory_variant_tags``)
    landed in Slice 2D3-A without bumping
    ``COMPARE_REPORT_SCHEMA_VERSION``.
    """
    if mode not in SUPPORTED_MODES:
        raise ValueError(
            f"Phase 2 supports mode in {SUPPORTED_MODES}, got {mode!r}"
        )
    if events is None:
        if events_source != "demo_stream":
            raise ValueError(
                "events must be provided when events_source is not 'demo_stream'"
            )
        events = generate_demo_event_stream()

    if adaptive_config is None:
        adaptive_config = AdaptivePolicyGateConfig()

    if replan_config is None:
        replan_config = ReplanConfig()

    if correlator_config is None:
        correlator_config = CorrelatorConfig()

    # --- 1. deterministic session_id ---
    config_for_digest: dict = {
        "seed": int(seed),
        "mode": str(mode),
        "events_source": str(events_source),
        "min_records_for_shift": int(adaptive_config.min_records_for_shift),
    }
    # Only contribute replan parameters to the session_id digest when
    # replan is actually enabled. This preserves byte-identity of
    # session_id for pre-B1 configurations (enable_replan=False).
    if replan_config.enable_replan:
        config_for_digest["replan"] = _replan_config_digest_fragment(
            replan_config,
        )
    # Only contribute correlator parameters to the session_id digest
    # when the correlator is actually enabled. Preserves byte-
    # identity for pre-B2 configurations (enable_correlator=False).
    if correlator_config.enable_correlator:
        config_for_digest["correlator"] = _correlator_config_digest_fragment(
            correlator_config,
        )
    # B4 Slice 2D1.x — only contribute agent-memory parameters to the
    # session_id digest when ``enable_agent_visible_memory`` is True.
    # Preserves byte-identity for every pre-B4 configuration and for
    # every B4-OFF run (F1). The fragment is driven by the public
    # config object alone, not by env / mode / runtime-gate state
    # (F2), so two runs with the same public config produce the same
    # session_id even if only one of them actually activates B4 at
    # runtime.
    if (
        agent_memory_config is not None
        and agent_memory_config.enable_agent_visible_memory
    ):
        config_for_digest["agent_memory"] = (
            _agent_memory_config_digest_fragment(agent_memory_config)
        )
    initial_memory_records: list[dict] = (
        list(initial_memory.snapshot()["records"])
        if initial_memory is not None
        else []
    )
    config_digest = digest_config_dict(config_for_digest)
    event_stream_digest = digest_event_stream(events)
    initial_memory_digest = digest_memory_records(initial_memory_records)
    session_id = compute_session_id(
        seed=seed,
        config_digest=config_digest,
        event_stream_digest=event_stream_digest,
        initial_memory_digest=initial_memory_digest,
    )

    # --- 2. Path B shadow run (always) — produces baseline_event_result ---
    baseline_shadow = run_event_loop(events, initial_twin_state=initial_twin_state)
    baseline_event_results = baseline_shadow["event_results"]

    if len(baseline_event_results) != len(events):
        raise RuntimeError(
            f"run_event_loop produced {len(baseline_event_results)} records "
            f"for {len(events)} events — Path B contract drift"
        )

    # --- 3. Build session records per mode ---
    memory = _seed_memory(initial_memory)

    if mode == "BASELINE_STATIC":
        session_records = _build_baseline_static_records(
            events=events,
            baseline_event_results=baseline_event_results,
            memory=memory,
            session_id=session_id,
            mode=mode,
        )
    else:
        session_records = _build_path_c_main_records(
            events=events,
            baseline_event_results=baseline_event_results,
            memory=memory,
            session_id=session_id,
            mode=mode,
            adaptive_config=adaptive_config,
            initial_twin_state=initial_twin_state,
            replan_config=replan_config,
            agent_memory_config=agent_memory_config,
        )

    # --- 3.b2 B2 correlator attach pass (observability-only) ---
    #
    # When enable_correlator=False (default), this branch is a no-op
    # and the records list is passed through unchanged — every
    # SessionEventRecord keeps correlation_context=None. When enabled,
    # we compute a CorrelationContext per event from the already-
    # finalized event stream and attach it via model_copy — never an
    # in-place mutation. The attach point runs AFTER both Phase 2
    # Path C main-path state and any B1 replan overlay have been
    # settled into session_records, so observability-only is
    # structural: downstream state has nowhere left to change.
    if correlator_config.enable_correlator:
        session_records = _attach_correlation_contexts(
            session_records=session_records,
            events=events,
            correlator_config=correlator_config,
        )

    # --- 4. KPIs (events_observed only in Phase 2 — full KPIs land in Phase 3) ---
    kpis = SessionKPIs(events_observed=len(session_records))

    artifact = SessionArtifact(
        session_id=session_id,
        config=SessionConfig(
            seed=int(seed),
            mode=mode,
            events_source=events_source,
            initial_memory_digest=initial_memory_digest,
        ),
        event_records=session_records,
        memory_snapshot=memory.snapshot(),
        kpis=kpis,
        schema_versions=dict(_SCHEMA_VERSIONS),
        notes="",
    )
    return artifact


# ---------------------------------------------------------------------------
# BASELINE_STATIC path (Phase 1 equivalent)
# ---------------------------------------------------------------------------


def _build_baseline_static_records(
    *,
    events: list[EventPayload],
    baseline_event_results: list[dict[str, Any]],
    memory: EpisodicMemory,
    session_id: str,
    mode: str,
) -> list[SessionEventRecord]:
    records: list[SessionEventRecord] = []
    for event, event_result in zip(events, baseline_event_results):
        mem_record = _build_memory_record_from_event_result(
            event, event_result, session_id,
        )
        memory.append(mem_record)
        records.append(
            _build_session_event_record(
                event=event,
                baseline_event_result=event_result,
                session_id=session_id,
                mode=mode,
                policy_route_source="baseline_static",
                adaptive_adjustment=None,
                effective_governance_output=event_result.get("governance_output") or {},
                effective_execution_status=str(event_result.get("execution_status", "")),
                effective_action_taken=_action_taken_from_outcome(
                    event_result.get("execution_outcome")
                ),
                effective_route=(event_result.get("policy_decision") or {}).get("route"),
                mem_record=mem_record,
                notes="",
            )
        )
    return records


# ---------------------------------------------------------------------------
# Path C main path (Phase 2)
# ---------------------------------------------------------------------------


def _build_path_c_main_records(
    *,
    events: list[EventPayload],
    baseline_event_results: list[dict[str, Any]],
    memory: EpisodicMemory,
    session_id: str,
    mode: str,
    adaptive_config: AdaptivePolicyGateConfig,
    initial_twin_state: Optional[TwinState],
    replan_config: ReplanConfig,
    agent_memory_config: Optional[AgentMemoryExperimentConfig] = None,
) -> list[SessionEventRecord]:
    """Run the Path C main path over its own fresh live state.

    The Path B shadow has already been computed in ``run_session``; its
    per-event records are passed in here and embedded verbatim as
    ``baseline_event_result``.

    ``agent_memory_config`` is the B4 Slice 2C internal-only
    wiring parameter. It is NOT reachable through ``run_session``'s
    public signature by design (W3). Tests drive it by calling
    ``_build_path_c_main_records`` directly.
    """
    path_c_state: TwinState = (
        initial_twin_state.model_copy(deep=True)
        if initial_twin_state is not None
        else load_baseline_twin_state()
    )
    path_c_outcome_store = OutcomeStore()

    # B4 Slice 2C — resolve operations_mode once per session. The
    # result feeds the W4 gate for every event; this avoids a
    # per-event env read and keeps gating deterministic across the
    # event stream.
    operations_mode = _resolve_operations_mode_from_env()

    records: list[SessionEventRecord] = []

    for event, baseline_er in zip(events, baseline_event_results):
        # --- (a) map event onto Path C state and run inner reasoning slice ---
        patched_state, scenario_context = map_event_to_state(event, path_c_state)
        path_c_state = patched_state
        scenario_context["outcome_summary"] = path_c_outcome_store.summary()
        twin_dict = _twin_state_to_agent_dict(path_c_state)

        # --- (a.b4) B4 Slice 2C — build agent-visible memory context
        # BEFORE the reasoning slice runs so the query sees only
        # rows from prior events + initial_memory (W5). The
        # current event's ``mem_record`` is not appended until
        # step (e) below. When B4 is OFF, this helper returns
        # ``None`` and the reasoning slice runs byte-identically
        # to pre-B4.
        agent_memory_context = _maybe_build_agent_memory_context(
            memory,
            event,
            mode=mode,
            operations_mode=operations_mode,
            agent_memory_config=agent_memory_config,
        )
        reasoning = _run_reasoning_slice(
            twin_dict,
            scenario_context,
            agent_memory_context=agent_memory_context,
            agent_memory_config=(
                agent_memory_config if agent_memory_context is not None else None
            ),
            # B4 Slice 2D3-B — propagate the env-resolved operations
            # mode into GraphState so the operations agent dispatch
            # uses the same mode reality the W4 gate used. Without
            # this thread, ``graph.operations_agent_node`` would
            # fall back to its ``state.get("operations_mode") or
            # "rules"`` default and short-circuit the env in
            # ``_resolve_ops_mode("rules")`` — meaning B4 would
            # build an ``AgentMemoryContext`` (W4 fires on env=llm)
            # but the operations agent would still take the rules
            # path and never inject the prompt section. Default-off
            # PATH_C runs (env unset → operations_mode="rules")
            # remain byte-identical because the graph node already
            # treats "rules" the same as the absent-key default.
            operations_mode=operations_mode,
        )
        governance_output = reasoning.get("governance_output", {}) or {}
        governance_meta = reasoning.get("_governance_meta", {}) or {}
        cost_output = reasoning.get("cost_output", {}) or {}

        # --- (b) adaptive policy gate ---
        event_context = EventContext(
            event_id=event.event_id,
            event_type=event.event_type.value,
            severity=event.severity.value,
            risk_level=str(governance_output.get("risk_level", "")).strip().upper(),
        )
        adaptive_decision, adjustment = decide_policy_adaptive(
            governance_output, event_context, memory, adaptive_config,
        )
        final_route = adaptive_decision.route.value

        # --- (c) route + execute with Path C hardening ---
        execution_status, outcome, path_c_state, preflight_note = _route_and_execute_path_c(
            route=final_route,
            governance_output=governance_output,
            governance_meta=governance_meta,
            state=path_c_state,
            event=event,
            outcome_store=path_c_outcome_store,
        )

        # --- (d) policy_route_source derivation (first attempt) ---
        first_policy_route_source = _derive_policy_route_source(adjustment)

        # --- (d.b1) B1 delegation: bounded second reasoning cycle ---
        #
        # When enable_replan=False (default) we take the early-return
        # branch and behavior remains byte-identical to pre-B1.
        #
        # When enable_replan=True and the Slice 2 trigger fires on
        # attempt 0, ``run_replan_cycle`` re-runs the full inner
        # reasoning slice + adaptive gate + preflight + execute on
        # post-attempt-0 state and returns the attempt-1 outputs.
        # GovernanceTruthRef stays pinned to the first-attempt
        # governance identity; EffectiveDecisionRef below is built
        # from the final-attempt outputs (dual-track preserved).
        replan_trace: Optional[list[ReplanAttemptRecord]] = None
        replan_triggers: Optional[list[ReplanTriggerRecord]] = None
        notes_addendum = ""
        if replan_config.enable_replan:
            cycle: ReplanCycleResult = run_replan_cycle(
                event=event,
                scenario_context=scenario_context,
                path_c_state=path_c_state,
                cost_output=cost_output,
                governance_output=governance_output,
                governance_meta=governance_meta,
                first_attempt_route=final_route,
                first_attempt_adjustment=adjustment,
                first_attempt_policy_route_source=first_policy_route_source,
                first_attempt_status=execution_status,
                first_attempt_outcome=outcome,
                first_attempt_preflight_note=preflight_note,
                path_c_outcome_store=path_c_outcome_store,
                memory=memory,
                adaptive_config=adaptive_config,
                replan_config=replan_config,
            )
            # Final (effective) attempt fields come from the cycle result.
            path_c_state = cycle.final_state
            execution_status = cycle.final_execution_status
            outcome = cycle.final_execution_outcome
            effective_governance_output = cycle.final_governance_output
            effective_governance_meta = cycle.final_governance_meta
            effective_route = cycle.final_route
            effective_adjustment = cycle.final_adaptive_adjustment
            effective_policy_route_source = cycle.final_policy_route_source
            preflight_note = cycle.final_preflight_note
            replan_trace = cycle.replan_trace
            replan_triggers = cycle.replan_triggers
            notes_addendum = cycle.notes_addendum
        else:
            # enable_replan=False — first attempt IS the final attempt.
            effective_governance_output = governance_output
            effective_governance_meta = governance_meta
            effective_route = final_route
            effective_adjustment = adjustment
            effective_policy_route_source = first_policy_route_source

        # --- (e) append memory (from FINAL attempt's outcome) ---
        mem_record = _build_memory_record_from_path_c(
            event=event,
            governance_output=effective_governance_output,
            final_route=effective_route,
            execution_status=execution_status,
            outcome=outcome,
            session_id=session_id,
        )
        memory.append(mem_record)

        # --- (f) SessionEventRecord ---
        base_notes = preflight_note or ""
        if notes_addendum:
            notes = f"{base_notes}{' | ' if base_notes else ''}{notes_addendum}"
        else:
            notes = base_notes
        records.append(
            _build_session_event_record(
                event=event,
                baseline_event_result=baseline_er,
                session_id=session_id,
                mode=mode,
                policy_route_source=effective_policy_route_source,
                adaptive_adjustment=effective_adjustment,
                effective_governance_output=effective_governance_output,
                effective_execution_status=execution_status,
                effective_action_taken=_action_taken_from_outcome(outcome),
                effective_route=effective_route,
                mem_record=mem_record,
                notes=notes,
                governance_meta=effective_governance_meta,
                # B1 additive:
                truth_governance_output=governance_output,
                truth_governance_meta=governance_meta,
                replan_trace=replan_trace,
                replan_triggers=replan_triggers,
            )
        )

    return records


def _route_and_execute_path_c(
    *,
    route: str,
    governance_output: dict[str, Any],
    governance_meta: dict[str, Any],
    state: TwinState,
    event: EventPayload,
    outcome_store: OutcomeStore,
) -> tuple[str, Optional[dict[str, Any]], TwinState, Optional[str]]:
    """Route + execute on the Path C main path.

    Returns (execution_status, outcome_dict_or_None, new_state, note_or_None).
    On ``preflight_failed`` or ``execution_failed`` the state is left
    unchanged and ``note`` carries a diagnostic string for the overlay.
    """
    if route == "AUTO_EXECUTE":
        outcome_store.record_routing("AUTO_EXECUTE")

        # Step 1: preflight validator (structural explainability, §2.D).
        try:
            validate_governance_meta(governance_meta)
        except GovernanceMetaPreflightError as exc:
            return (
                "preflight_failed",
                None,
                state,
                f"GovernanceMetaPreflightError: {exc}",
            )

        # Step 2: metadata-mandatory execution (no text fallback).
        try:
            new_state, outcome = execute_action(
                governance_output,
                state,
                event_id=event.event_id,
                governance_meta=governance_meta,
                timestamp=event.timestamp,
                require_metadata=True,
            )
        except (ExecutionInfeasibleError, GovernanceActionParseError) as exc:
            return (
                "execution_failed",
                None,
                state,
                f"{type(exc).__name__}: {exc}",
            )

        outcome_store.append(outcome)
        return "executed", outcome.model_dump(mode="json"), new_state, None

    if route == "HUMAN_REQUIRED":
        outcome_store.record_routing("HUMAN_REQUIRED")
        return "awaiting_human_review", None, state, None

    # Fail-closed: unknown route
    return (
        "unknown_route",
        None,
        state,
        f"policy_decision.route={route!r} is not recognized",
    )


def _derive_policy_route_source(
    adjustment: Optional[AdaptivePolicyAdjustment],
) -> str:
    if adjustment is None:
        return "baseline_static"
    t = adjustment.adjustment_type
    if t == "UPGRADE_ONE_LEVEL":
        return "adaptive_adjusted"
    if t == "COLD_START_FALLBACK":
        return "cold_start_fallback"
    # NO_ADJUSTMENT recorded but no behavioral change
    return "baseline_static"


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------


def _seed_memory(initial_memory: Optional[EpisodicMemory]) -> EpisodicMemory:
    if initial_memory is None:
        return EpisodicMemory()
    records = [
        MemoryRecord.model_validate(r)
        for r in initial_memory.snapshot()["records"]
    ]
    return EpisodicMemory(records)


def _action_taken_from_outcome(outcome: Any) -> Optional[str]:
    if isinstance(outcome, dict):
        a = outcome.get("action_taken")
        if a in _VALID_ACTIONS:
            return a
    return None


def _build_memory_record_from_event_result(
    event: EventPayload,
    event_result: dict[str, Any],
    session_id: str,
) -> MemoryRecord:
    gov = event_result.get("governance_output") or {}
    policy = event_result.get("policy_decision") or {}
    outcome = event_result.get("execution_outcome")

    if isinstance(outcome, dict):
        sla = outcome.get("sla_impact") or {}
        action_taken = outcome.get("action_taken")
        cost = outcome.get("cost_incurred")
        cost_incurred = float(cost) if cost is not None else None
        sla_preserved = sla.get("preserved") if isinstance(sla, dict) else None
    else:
        action_taken = None
        cost_incurred = None
        sla_preserved = None

    return MemoryRecord(
        event_id=event.event_id,
        event_type=str(event_result.get("event_type", "")),
        event_timestamp=event.timestamp.isoformat(),
        action_taken=action_taken if action_taken in _VALID_ACTIONS else None,
        execution_status=str(event_result.get("execution_status", "")),
        final_route=str(policy.get("route", "")),
        cost_incurred=cost_incurred,
        sla_preserved=sla_preserved if isinstance(sla_preserved, bool) else None,
        risk_level=str(gov.get("risk_level", "")),
        session_id=session_id,
    )


def _build_memory_record_from_path_c(
    *,
    event: EventPayload,
    governance_output: dict[str, Any],
    final_route: str,
    execution_status: str,
    outcome: Optional[dict[str, Any]],
    session_id: str,
) -> MemoryRecord:
    action_taken: Optional[str] = None
    cost_incurred: Optional[float] = None
    sla_preserved: Optional[bool] = None
    if isinstance(outcome, dict):
        a = outcome.get("action_taken")
        if a in _VALID_ACTIONS:
            action_taken = a
        cost = outcome.get("cost_incurred")
        cost_incurred = float(cost) if cost is not None else None
        sla = outcome.get("sla_impact") or {}
        if isinstance(sla, dict):
            preserved = sla.get("preserved")
            if isinstance(preserved, bool):
                sla_preserved = preserved

    return MemoryRecord(
        event_id=event.event_id,
        event_type=event.event_type.value,
        event_timestamp=event.timestamp.isoformat(),
        action_taken=action_taken,
        execution_status=execution_status,
        final_route=final_route,
        cost_incurred=cost_incurred,
        sla_preserved=sla_preserved,
        risk_level=str(governance_output.get("risk_level", "")),
        session_id=session_id,
    )


def _build_session_event_record(
    *,
    event: EventPayload,
    baseline_event_result: dict[str, Any],
    session_id: str,
    mode: str,
    policy_route_source: str,
    adaptive_adjustment: Optional[AdaptivePolicyAdjustment],
    effective_governance_output: dict[str, Any],
    effective_execution_status: str,
    effective_action_taken: Optional[str],
    effective_route: Optional[str],
    mem_record: MemoryRecord,
    notes: str,
    governance_meta: Optional[dict[str, Any]] = None,
    truth_governance_output: Optional[dict[str, Any]] = None,
    truth_governance_meta: Optional[dict[str, Any]] = None,
    replan_trace: Optional[list[ReplanAttemptRecord]] = None,
    replan_triggers: Optional[list[ReplanTriggerRecord]] = None,
) -> SessionEventRecord:
    # B1 dual-track preservation: ``truth_governance_output`` and
    # ``truth_governance_meta``, when provided, carry the FIRST-attempt
    # governance identity and are used only to build
    # ``GovernanceTruthRef``. ``effective_governance_output`` and
    # ``governance_meta`` carry the FINAL-attempt identity and are
    # used only for ``EffectiveDecisionRef`` and its effective_risk.
    # When the replan path did not run (or isn't enabled), truth and
    # effective are the same dict — behavior is unchanged.
    if truth_governance_output is None:
        truth_governance_output = effective_governance_output
    if truth_governance_meta is None:
        truth_governance_meta = governance_meta
    # ---- strict contract checks on Path B shadow ----
    baseline_policy = baseline_event_result.get("policy_decision") or {}
    baseline_route = baseline_policy.get("route")
    if baseline_route not in ("AUTO_EXECUTE", "HUMAN_REQUIRED"):
        raise RuntimeError(
            f"Path B policy_decision.route={baseline_route!r} violates frozen contract"
        )
    baseline_exec_status = baseline_event_result.get("execution_status")
    if baseline_exec_status not in _PATH_B_EXECUTION_STATUSES:
        raise RuntimeError(
            f"Path B execution_status={baseline_exec_status!r} violates frozen contract"
        )

    # ---- governance truth: reflects FIRST-attempt governance identity ----
    truth_risk = str(truth_governance_output.get("risk_level", "")).strip().upper()
    if truth_governance_meta and isinstance(
        truth_governance_meta.get("recommended_candidate_type"), str,
    ):
        truth_recommended = str(
            truth_governance_meta["recommended_candidate_type"]
        ).strip().upper()
        if truth_recommended not in _VALID_ACTIONS:
            # Fallback to shim if meta malformed but still a string (preserves audit).
            truth_recommended = _recommended_candidate_type_shim(truth_governance_output)
    else:
        truth_recommended = _recommended_candidate_type_shim(truth_governance_output)

    governance_truth = GovernanceTruthRef(
        risk_level=truth_risk,
        recommended_candidate_type=truth_recommended,
    )

    # ---- effective decision: reflects FINAL-attempt outputs ----
    if effective_route not in ("AUTO_EXECUTE", "HUMAN_REQUIRED"):
        raise RuntimeError(
            f"Adaptive final_route={effective_route!r} violates frozen contract"
        )
    if effective_execution_status not in _PATH_C_EXECUTION_STATUSES:
        raise RuntimeError(
            f"Effective execution_status={effective_execution_status!r} "
            f"violates Path C overlay contract"
        )

    effective_gov_risk = str(
        effective_governance_output.get("risk_level", "")
    ).strip().upper()
    effective_risk = (
        adaptive_adjustment.post_adjustment_risk
        if (adaptive_adjustment is not None
            and adaptive_adjustment.adjustment_type == "UPGRADE_ONE_LEVEL")
        else effective_gov_risk
    )

    effective = EffectiveDecisionRef(
        effective_risk=effective_risk,
        final_route=effective_route,
        action_taken=(
            effective_action_taken if effective_action_taken in _VALID_ACTIONS else None
        ),
        execution_status=effective_execution_status,
    )

    return SessionEventRecord(
        baseline_event_result=dict(baseline_event_result),
        session_id=session_id,
        mode=mode,
        policy_route_source=policy_route_source,
        adaptive_adjustment=adaptive_adjustment,
        governance_truth=governance_truth,
        effective_decision=effective,
        memory_record_id=memory_record_id(
            session_id, mem_record.event_timestamp, mem_record.event_id,
        ),
        replan_trace=replan_trace,
        replan_triggers=replan_triggers,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# B2 correlator attach pass (post-finalization, observability-only)
# ---------------------------------------------------------------------------


def _attach_correlation_contexts(
    *,
    session_records: list[SessionEventRecord],
    events: list[EventPayload],
    correlator_config: CorrelatorConfig,
) -> list[SessionEventRecord]:
    """Return a new list of records with ``correlation_context`` set.

    Pure, deterministic, post-finalization. The input ``session_records``
    list is NOT mutated in place; each record is replaced by an
    immutable copy produced via ``model_copy(update=...)``. The Path B
    shadow (``baseline_event_result``), dual-track governance
    references (``governance_truth`` / ``effective_decision``),
    adaptive adjustment, and any replan overlay fields are left
    untouched.

    Preconditions:
      - ``len(session_records) == len(events)`` (one record per event)
      - ``correlator_config.enable_correlator is True``
    """
    if len(session_records) != len(events):
        raise RuntimeError(
            f"session_records length ({len(session_records)}) does not "
            f"match events length ({len(events)}) — correlator attach "
            f"requires one record per event"
        )
    updated: list[SessionEventRecord] = []
    for idx, record in enumerate(session_records):
        ctx = compute_correlation_context(
            events=events,
            current_index=idx,
            config=correlator_config,
        )
        # compute_correlation_context returns None only when disabled,
        # but we already checked the gate at the call site. Guard
        # defensively — if future refactors change the contract, we
        # prefer a hard error over silent no-op.
        if ctx is None:
            raise RuntimeError(
                "compute_correlation_context returned None with "
                "enable_correlator=True — contract violation"
            )
        updated.append(record.model_copy(update={"correlation_context": ctx}))
    return updated
