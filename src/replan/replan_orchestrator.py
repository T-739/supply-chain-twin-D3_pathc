"""replan/replan_orchestrator.py — B1 Slice 3 narrow runtime wrapper.

One bounded second reasoning cycle over exactly one Path C event,
built as a thin orchestration layer on top of existing building
blocks (no new agent logic, no new adapter). Pure-ish: the only
state change this module performs is calling building blocks that
already carry their own side-effects (``_route_and_execute_path_c``
appends to the outcome_store when attempt 1 executes).

Locked constraints preserved here:

  - MAX_REPLAN_ATTEMPTS = 1 (hard cap, enforced structurally by the
    fact that the orchestrator only runs a *single* attempt 1 branch
    — there is no loop).
  - Second cycle is a FULL reasoning cycle (operations → cost →
    governance → adaptive policy gate → preflight → execute_action).
    First-cycle outputs are NEVER reused as a fake retry; the second
    cycle re-runs ``_run_reasoning_slice`` on the post-attempt-0
    Path C state.
  - No agent / GovernanceOutput / _governance_meta changes. The
    structured replan sideband is carried via
    ``scenario_context["replan_context"]`` additively; it is visible
    to any future agent that wants to consume it, but no existing
    agent is required to read it.
  - No mid-event memory read; no per-attempt ``MemoryRecord`` append.
    Memory append for the event stays the caller's responsibility
    and occurs exactly once, after the FINAL attempt.
  - ``baseline_event_result`` (Path B shadow) is never touched.
  - ``GovernanceTruthRef`` semantics are owned by the caller — the
    orchestrator never mutates the first-attempt governance identity.

No-trigger-trace semantics: if attempt 0's trigger is ``NO_TRIGGER``,
``replan_trace`` and ``replan_triggers`` are returned as ``None`` (not
empty lists) — so a bounded-replan-not-fired event remains
byte-structurally equivalent to a pre-B1 session event.

Imports of ``_run_reasoning_slice``, ``_route_and_execute_path_c``,
and ``_twin_state_to_agent_dict`` are deferred to call time to avoid
an import-graph cycle between ``event_loop_c`` and ``replan``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from adaptive.adaptive_policy_config import (
    AdaptivePolicyGateConfig,
    EventContext,
)
from adaptive.adaptive_schema import AdaptivePolicyAdjustment

from replan.expected_outcome import estimate_expected_outcome
from replan.replan_config import MAX_REPLAN_ATTEMPTS, ReplanConfig
from replan.replan_schema import (
    ExpectedOutcomeRef,
    ReplanAttemptRecord,
    ReplanTriggerRecord,
)
from replan.replan_trigger import decide_replan_trigger


_VALID_ACTIONS: frozenset[str] = frozenset(
    {"EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"}
)


@dataclass(frozen=True)
class ReplanCycleResult:
    """Structured return of :func:`run_replan_cycle`.

    Carries everything the caller needs to finalize a
    ``SessionEventRecord`` when a bounded second attempt happened,
    without losing the first-attempt governance identity (dual-track
    preservation remains the caller's responsibility).

    When ``replan_trace is None`` and ``replan_triggers is None``, no
    trigger fired and the caller should build the record from its
    first-attempt values exactly as pre-B1.
    """

    final_state: Any  # TwinState — typed as Any to avoid circular import
    final_execution_status: str
    final_execution_outcome: Optional[dict[str, Any]]
    final_governance_output: dict[str, Any]
    final_governance_meta: dict[str, Any]
    final_route: str
    final_adaptive_adjustment: Optional[AdaptivePolicyAdjustment]
    final_policy_route_source: str
    final_preflight_note: Optional[str]
    replan_trace: Optional[list[ReplanAttemptRecord]]
    replan_triggers: Optional[list[ReplanTriggerRecord]]
    notes_addendum: str


def _no_replan_result(
    *,
    first_state: Any,
    first_status: str,
    first_outcome: Optional[dict[str, Any]],
    first_governance_output: dict[str, Any],
    first_governance_meta: dict[str, Any],
    first_route: str,
    first_adjustment: Optional[AdaptivePolicyAdjustment],
    first_policy_route_source: str,
    first_preflight_note: Optional[str],
) -> ReplanCycleResult:
    """Result helper for the "no second attempt occurred" branch."""
    return ReplanCycleResult(
        final_state=first_state,
        final_execution_status=first_status,
        final_execution_outcome=first_outcome,
        final_governance_output=first_governance_output,
        final_governance_meta=first_governance_meta,
        final_route=first_route,
        final_adaptive_adjustment=first_adjustment,
        final_policy_route_source=first_policy_route_source,
        final_preflight_note=first_preflight_note,
        replan_trace=None,
        replan_triggers=None,
        notes_addendum="",
    )


def _build_replan_context_sideband(
    trigger: ReplanTriggerRecord,
    expected: Optional[ExpectedOutcomeRef],
) -> dict[str, Any]:
    """Structured, numeric-only replan sideband for the second cycle.

    Placed on ``scenario_context["replan_context"]`` additively. No
    natural-language content. Future agents may consume this; current
    agents ignore it (no prompt change required).
    """
    sideband: dict[str, Any] = {
        "prior_attempt_index": int(trigger.attempt_index),
        "trigger_type": str(trigger.trigger_type),
        "trigger_rule_id": str(trigger.trigger_rule_id),
    }
    if trigger.realized_cost is not None:
        sideband["realized_cost"] = float(trigger.realized_cost)
    if trigger.realized_sla_preserved is not None:
        sideband["realized_sla_preserved"] = bool(trigger.realized_sla_preserved)
    if expected is not None:
        sideband["expected_cost_min"] = float(expected.expected_cost_min)
        sideband["expected_cost_max"] = float(expected.expected_cost_max)
        sideband["expected_sla_preserved"] = bool(expected.expected_sla_preserved)
    return sideband


def _derive_policy_route_source(
    adjustment: Optional[AdaptivePolicyAdjustment],
) -> str:
    """Mirror of ``event_loop_c._derive_policy_route_source``.

    Redefined here (not imported) to avoid a circular import with
    ``event_loop_c``. Keep in sync by convention.
    """
    if adjustment is None:
        return "baseline_static"
    t = adjustment.adjustment_type
    if t == "UPGRADE_ONE_LEVEL":
        return "adaptive_adjusted"
    if t == "COLD_START_FALLBACK":
        return "cold_start_fallback"
    return "baseline_static"


def _try_estimate_expected(
    *,
    cost_output: dict[str, Any],
    governance_meta: dict[str, Any],
    config: ReplanConfig,
) -> Optional[ExpectedOutcomeRef]:
    """Best-effort expected-outcome estimation. Returns None on any
    structural fail-closed in the estimator — the bounded trigger
    layer must never raise out of the orchestrator.
    """
    try:
        return estimate_expected_outcome(
            cost_output=cost_output,
            governance_meta=governance_meta,
            config=config,
        )
    except ValueError:
        return None


def _action_taken_from_outcome(
    outcome: Optional[dict[str, Any]],
) -> Optional[str]:
    if isinstance(outcome, dict):
        a = outcome.get("action_taken")
        if a in _VALID_ACTIONS:
            return a
    return None


def _build_attempt_record(
    *,
    attempt_index: int,
    route: str,
    status: str,
    outcome: Optional[dict[str, Any]],
    adjustment: Optional[AdaptivePolicyAdjustment],
    expected: Optional[ExpectedOutcomeRef],
    trigger: ReplanTriggerRecord,
    notes: str,
) -> ReplanAttemptRecord:
    action_taken = _action_taken_from_outcome(outcome)
    return ReplanAttemptRecord(
        attempt_index=attempt_index,
        attempt_final_route=route,  # type: ignore[arg-type]
        attempt_action_taken=action_taken,  # type: ignore[arg-type]
        attempt_execution_status=status,  # type: ignore[arg-type]
        execution_outcome=outcome,
        adaptive_adjustment=adjustment,
        expected_outcome=expected,
        trigger=trigger,
        notes=notes,
    )


def run_replan_cycle(
    *,
    event: Any,
    scenario_context: dict[str, Any],
    path_c_state: Any,
    cost_output: dict[str, Any],
    governance_output: dict[str, Any],
    governance_meta: dict[str, Any],
    first_attempt_route: str,
    first_attempt_adjustment: Optional[AdaptivePolicyAdjustment],
    first_attempt_policy_route_source: str,
    first_attempt_status: str,
    first_attempt_outcome: Optional[dict[str, Any]],
    first_attempt_preflight_note: Optional[str],
    path_c_outcome_store: Any,
    memory: Any,  # EpisodicMemory — typed Any to keep replan/ import-topology clean
    adaptive_config: AdaptivePolicyGateConfig,
    replan_config: ReplanConfig,
) -> ReplanCycleResult:
    """Run at most one bounded second reasoning cycle for one event.

    Pure-ish orchestrator: no new agent logic, no adapter changes,
    no memory append. If no trigger fires on attempt 0 the function
    returns the unchanged first-attempt values and
    ``replan_trace / replan_triggers = None``.

    Parameters
    ----------
    event, scenario_context, path_c_state
        The per-event context at the end of attempt 0. ``path_c_state``
        reflects any state change from attempt 0's execute_action.
    cost_output, governance_output, governance_meta
        Attempt 0's structured reasoning outputs, carried in as
        attempt-local values (no global side channel).
    first_attempt_route, first_attempt_adjustment,
    first_attempt_policy_route_source, first_attempt_status,
    first_attempt_outcome, first_attempt_preflight_note
        Attempt 0's adaptive-policy outputs and execution outcome.
    path_c_outcome_store
        The Path C outcome store. A successful attempt 1 appends via
        the existing ``_route_and_execute_path_c`` helper.
    memory, adaptive_config, replan_config
        Passed through to the attempt-1 adaptive gate call.
        ``memory`` is NOT read or written by this orchestrator; it is
        only forwarded to the existing adaptive gate for consistency
        with attempt 0's control flow.

    Returns
    -------
    ReplanCycleResult
        Carries attempt-1's effective_state/status/outcome/gov_output/
        meta/route/adjustment plus the structured trace and triggers.
    """
    if not replan_config.enable_replan:
        # Defensive: callers are expected to short-circuit before
        # invoking the orchestrator. Return a clean no-op either way.
        return _no_replan_result(
            first_state=path_c_state,
            first_status=first_attempt_status,
            first_outcome=first_attempt_outcome,
            first_governance_output=governance_output,
            first_governance_meta=governance_meta,
            first_route=first_attempt_route,
            first_adjustment=first_attempt_adjustment,
            first_policy_route_source=first_attempt_policy_route_source,
            first_preflight_note=first_attempt_preflight_note,
        )

    # --- (1) structural expected-outcome estimate for attempt 0 ---
    expected_attempt0 = _try_estimate_expected(
        cost_output=cost_output,
        governance_meta=governance_meta,
        config=replan_config,
    )

    # --- (2) decide whether a replan is warranted ---
    trigger0 = decide_replan_trigger(
        expected_outcome=expected_attempt0,
        execution_status=first_attempt_status,
        execution_outcome=first_attempt_outcome,
        attempt_index=0,
        config=replan_config,
    )

    if trigger0.trigger_type == "NO_TRIGGER":
        return _no_replan_result(
            first_state=path_c_state,
            first_status=first_attempt_status,
            first_outcome=first_attempt_outcome,
            first_governance_output=governance_output,
            first_governance_meta=governance_meta,
            first_route=first_attempt_route,
            first_adjustment=first_attempt_adjustment,
            first_policy_route_source=first_attempt_policy_route_source,
            first_preflight_note=first_attempt_preflight_note,
        )

    # A trigger fired — bounded second attempt below.
    #
    # Hard cap: MAX_REPLAN_ATTEMPTS == 1 means there is exactly one
    # attempt 1 branch. No loop, no re-entry.
    assert MAX_REPLAN_ATTEMPTS == 1, (
        "replan_orchestrator: MAX_REPLAN_ATTEMPTS invariant violated — "
        f"expected 1, got {MAX_REPLAN_ATTEMPTS}"
    )

    # --- (3) deferred imports: break event_loop_c ↔ replan cycle ---
    from event_loop import _run_reasoning_slice, _twin_state_to_agent_dict
    from event_loop_c import _route_and_execute_path_c
    from adaptive.adaptive_policy_gate import decide_policy_adaptive

    # --- (4) structured replan sideband (numeric-only, additive) ---
    sideband = _build_replan_context_sideband(trigger0, expected_attempt0)
    # Copy scenario_context shallowly to avoid mutating the caller's
    # dict; keep the original keys in place (outcome_summary from the
    # pre-event snapshot is retained — see module docstring rationale).
    scenario_context_v2: dict[str, Any] = dict(scenario_context)
    scenario_context_v2["replan_context"] = sideband

    # --- (5) FULL second reasoning cycle on post-attempt-0 state ---
    twin_dict_v2 = _twin_state_to_agent_dict(path_c_state)
    reasoning_v2 = _run_reasoning_slice(twin_dict_v2, scenario_context_v2)
    gov_output_v2: dict[str, Any] = reasoning_v2.get("governance_output", {}) or {}
    gov_meta_v2: dict[str, Any] = reasoning_v2.get("_governance_meta", {}) or {}
    cost_output_v2: dict[str, Any] = reasoning_v2.get("cost_output", {}) or {}

    # --- (6) adaptive policy gate on attempt 1 ---
    event_context_v2 = EventContext(
        event_id=event.event_id,
        event_type=event.event_type.value,
        severity=event.severity.value,
        risk_level=str(gov_output_v2.get("risk_level", "")).strip().upper(),
    )
    adaptive_decision_v2, adjustment_v2 = decide_policy_adaptive(
        gov_output_v2, event_context_v2, memory, adaptive_config,
    )
    route_v2 = adaptive_decision_v2.route.value
    policy_route_source_v2 = _derive_policy_route_source(adjustment_v2)

    # --- (7) preflight + execute (reuses Path C hardening as-is) ---
    exec_status_v2, outcome_v2, state_v2, preflight_note_v2 = (
        _route_and_execute_path_c(
            route=route_v2,
            governance_output=gov_output_v2,
            governance_meta=gov_meta_v2,
            state=path_c_state,
            event=event,
            outcome_store=path_c_outcome_store,
        )
    )

    # --- (8) attempt-1 audit (re-estimate expected for audit, if possible) ---
    expected_attempt1 = _try_estimate_expected(
        cost_output=cost_output_v2,
        governance_meta=gov_meta_v2,
        config=replan_config,
    )
    trigger1 = decide_replan_trigger(
        expected_outcome=expected_attempt1,
        execution_status=exec_status_v2,
        execution_outcome=outcome_v2,
        attempt_index=1,
        config=replan_config,
    )

    # --- (9) assemble replan_trace + replan_triggers ---
    attempt0_record = _build_attempt_record(
        attempt_index=0,
        route=first_attempt_route,
        status=first_attempt_status,
        outcome=first_attempt_outcome,
        adjustment=first_attempt_adjustment,
        expected=expected_attempt0,
        trigger=trigger0,
        notes=first_attempt_preflight_note or "",
    )
    attempt1_record = _build_attempt_record(
        attempt_index=1,
        route=route_v2,
        status=exec_status_v2,
        outcome=outcome_v2,
        adjustment=adjustment_v2,
        expected=expected_attempt1,
        trigger=trigger1,
        notes=preflight_note_v2 or "",
    )

    return ReplanCycleResult(
        final_state=state_v2,
        final_execution_status=exec_status_v2,
        final_execution_outcome=outcome_v2,
        final_governance_output=gov_output_v2,
        final_governance_meta=gov_meta_v2,
        final_route=route_v2,
        final_adaptive_adjustment=adjustment_v2,
        final_policy_route_source=policy_route_source_v2,
        final_preflight_note=preflight_note_v2,
        replan_trace=[attempt0_record, attempt1_record],
        replan_triggers=[trigger0, trigger1],
        notes_addendum=f"replan_fired:{trigger0.trigger_type}",
    )
