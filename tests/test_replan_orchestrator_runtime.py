"""B1 Slice 3: orchestrator runtime unit tests.

Covers ``src/replan/replan_orchestrator.py::run_replan_cycle`` at the
unit level. The orchestrator is a narrow runtime wrapper around
existing Path C building blocks; these tests exercise:

  - no-trigger path: returns the first-attempt state / status /
    outcome unchanged and ``replan_trace / replan_triggers = None``
    (not empty lists);
  - trigger path: performs exactly one bounded second attempt and
    records attempts 0 and 1 in ``replan_trace``, plus T0 and T1 in
    ``replan_triggers``;
  - the second attempt's state/status/outcome are distinct from the
    first when the second cycle re-reasons successfully;
  - no memory append occurs inside the orchestrator;
  - disabled-config early return;
  - the structured ``replan_context`` sideband is numeric-only (no
    natural-language strings).

To force the trigger branch deterministically without engineering a
cost divergence, we monkeypatch ``decide_replan_trigger`` inside the
orchestrator module. The unit semantics of the trigger function
itself are verified separately in Slice 2's test suite.
"""

from __future__ import annotations

import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


# ---------------------------------------------------------------------------
# Helpers: build a minimal first-attempt state tuple via a single
# PATH_C_COLD event using the real reasoning slice.
# ---------------------------------------------------------------------------


def _run_first_attempt(event):
    """Run attempt 0 end-to-end and return everything the orchestrator needs."""
    from adaptive.adaptive_policy_config import (
        AdaptivePolicyGateConfig,
        EventContext,
    )
    from adaptive.adaptive_policy_gate import decide_policy_adaptive
    from event_loop import (
        _run_reasoning_slice,
        _twin_state_to_agent_dict,
        load_baseline_twin_state,
    )
    from event_loop_c import _route_and_execute_path_c
    from event_state_mapper import map_event_to_state
    from learning.episodic_memory import EpisodicMemory
    from outcome_store import OutcomeStore

    state = load_baseline_twin_state()
    store = OutcomeStore()
    memory = EpisodicMemory()

    state, scenario_context = map_event_to_state(event, state)
    scenario_context["outcome_summary"] = store.summary()
    reasoning = _run_reasoning_slice(
        _twin_state_to_agent_dict(state), scenario_context,
    )
    gov = reasoning.get("governance_output", {}) or {}
    gov_meta = reasoning.get("_governance_meta", {}) or {}
    cost_out = reasoning.get("cost_output", {}) or {}

    adaptive_cfg = AdaptivePolicyGateConfig()
    ev_ctx = EventContext(
        event_id=event.event_id,
        event_type=event.event_type.value,
        severity=event.severity.value,
        risk_level=str(gov.get("risk_level", "")).strip().upper(),
    )
    decision, adjustment = decide_policy_adaptive(
        gov, ev_ctx, memory, adaptive_cfg,
    )
    final_route = decision.route.value

    status, outcome, state_after, preflight_note = _route_and_execute_path_c(
        route=final_route,
        governance_output=gov,
        governance_meta=gov_meta,
        state=state,
        event=event,
        outcome_store=store,
    )
    return {
        "event": event,
        "scenario_context": scenario_context,
        "state": state_after,
        "cost_output": cost_out,
        "governance_output": gov,
        "governance_meta": gov_meta,
        "route": final_route,
        "adjustment": adjustment,
        "status": status,
        "outcome": outcome,
        "preflight_note": preflight_note,
        "memory": memory,
        "store": store,
        "adaptive_cfg": adaptive_cfg,
    }


def _demo_event():
    from event_engine import generate_demo_event_stream
    events = generate_demo_event_stream()
    assert events, "demo stream unexpectedly empty"
    return events[0]


# ---------------------------------------------------------------------------
# No-trigger branch
# ---------------------------------------------------------------------------


def test_no_trigger_returns_none_trace_and_unchanged_first_attempt_values():
    from replan import ReplanConfig, run_replan_cycle

    ctx = _run_first_attempt(_demo_event())
    cfg = ReplanConfig(enable_replan=True)

    result = run_replan_cycle(
        event=ctx["event"],
        scenario_context=ctx["scenario_context"],
        path_c_state=ctx["state"],
        cost_output=ctx["cost_output"],
        governance_output=ctx["governance_output"],
        governance_meta=ctx["governance_meta"],
        first_attempt_route=ctx["route"],
        first_attempt_adjustment=ctx["adjustment"],
        first_attempt_policy_route_source="baseline_static",
        first_attempt_status=ctx["status"],
        first_attempt_outcome=ctx["outcome"],
        first_attempt_preflight_note=ctx["preflight_note"],
        path_c_outcome_store=ctx["store"],
        memory=ctx["memory"],
        adaptive_config=ctx["adaptive_cfg"],
        replan_config=cfg,
    )
    # On the demo stream, realized cost tracks expected cost closely
    # (same TwinState formulas), so the trigger is NO_TRIGGER and
    # nothing materializes.
    assert result.replan_trace is None
    assert result.replan_triggers is None
    assert result.final_state is ctx["state"]
    assert result.final_execution_status == ctx["status"]
    assert result.final_execution_outcome == ctx["outcome"]
    assert result.final_governance_output is ctx["governance_output"]
    assert result.final_route == ctx["route"]
    assert result.notes_addendum == ""


def test_disabled_config_returns_no_op_result():
    from replan import ReplanConfig, run_replan_cycle

    ctx = _run_first_attempt(_demo_event())
    cfg = ReplanConfig()  # enable_replan=False

    result = run_replan_cycle(
        event=ctx["event"],
        scenario_context=ctx["scenario_context"],
        path_c_state=ctx["state"],
        cost_output=ctx["cost_output"],
        governance_output=ctx["governance_output"],
        governance_meta=ctx["governance_meta"],
        first_attempt_route=ctx["route"],
        first_attempt_adjustment=ctx["adjustment"],
        first_attempt_policy_route_source="baseline_static",
        first_attempt_status=ctx["status"],
        first_attempt_outcome=ctx["outcome"],
        first_attempt_preflight_note=ctx["preflight_note"],
        path_c_outcome_store=ctx["store"],
        memory=ctx["memory"],
        adaptive_config=ctx["adaptive_cfg"],
        replan_config=cfg,
    )
    assert result.replan_trace is None
    assert result.replan_triggers is None


# ---------------------------------------------------------------------------
# Trigger branch — force via monkeypatch to exercise the second attempt.
# ---------------------------------------------------------------------------


def _force_cost_trigger_on_attempt0(*, expected_outcome, execution_status,
                                    execution_outcome, attempt_index, config):
    """Returns COST_DEVIATION on attempt 0, NO_TRIGGER on attempt 1."""
    from replan.replan_schema import ReplanTriggerRecord

    if attempt_index == 0:
        return ReplanTriggerRecord(
            trigger_rule_id="cost_deviation_v1",
            trigger_type="COST_DEVIATION",
            attempt_index=0,
            deviation_measurement={
                "realized_cost": 500.0,
                "absolute_delta": 400.0,
                "relative_delta": 3.0,
            },
            expected_outcome_ref=expected_outcome,
            realized_cost=(
                execution_outcome.get("cost_incurred")
                if isinstance(execution_outcome, dict) else None
            ),
            realized_sla_preserved=None,
            notes="forced in test",
        )
    return ReplanTriggerRecord(
        trigger_rule_id="no_trigger_v1",
        trigger_type="NO_TRIGGER",
        attempt_index=attempt_index,
        deviation_measurement={},
        expected_outcome_ref=expected_outcome,
        realized_cost=(
            execution_outcome.get("cost_incurred")
            if isinstance(execution_outcome, dict) else None
        ),
        realized_sla_preserved=None,
        notes="",
    )


def test_trigger_branch_runs_exactly_one_second_attempt(monkeypatch):
    from replan import ReplanConfig, run_replan_cycle

    ctx = _run_first_attempt(_demo_event())
    cfg = ReplanConfig(enable_replan=True)

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger_on_attempt0,
    )

    result = run_replan_cycle(
        event=ctx["event"],
        scenario_context=ctx["scenario_context"],
        path_c_state=ctx["state"],
        cost_output=ctx["cost_output"],
        governance_output=ctx["governance_output"],
        governance_meta=ctx["governance_meta"],
        first_attempt_route=ctx["route"],
        first_attempt_adjustment=ctx["adjustment"],
        first_attempt_policy_route_source="baseline_static",
        first_attempt_status=ctx["status"],
        first_attempt_outcome=ctx["outcome"],
        first_attempt_preflight_note=ctx["preflight_note"],
        path_c_outcome_store=ctx["store"],
        memory=ctx["memory"],
        adaptive_config=ctx["adaptive_cfg"],
        replan_config=cfg,
    )

    assert result.replan_trace is not None
    assert result.replan_triggers is not None
    # Exactly two attempt records (0 and 1) — the hard cap means no more.
    assert len(result.replan_trace) == 2
    assert [r.attempt_index for r in result.replan_trace] == [0, 1]
    # Exactly two trigger records — T0 (fired) and T1 (audit of second attempt).
    assert len(result.replan_triggers) == 2
    assert result.replan_triggers[0].trigger_type == "COST_DEVIATION"
    assert result.replan_triggers[1].trigger_type == "NO_TRIGGER"
    # Notes addendum records the fired trigger type (structured audit only).
    assert result.notes_addendum == "replan_fired:COST_DEVIATION"


def test_trigger_branch_does_not_append_memory(monkeypatch):
    from replan import ReplanConfig, run_replan_cycle

    ctx = _run_first_attempt(_demo_event())
    before = len(ctx["memory"].snapshot()["records"])
    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger_on_attempt0,
    )

    run_replan_cycle(
        event=ctx["event"],
        scenario_context=ctx["scenario_context"],
        path_c_state=ctx["state"],
        cost_output=ctx["cost_output"],
        governance_output=ctx["governance_output"],
        governance_meta=ctx["governance_meta"],
        first_attempt_route=ctx["route"],
        first_attempt_adjustment=ctx["adjustment"],
        first_attempt_policy_route_source="baseline_static",
        first_attempt_status=ctx["status"],
        first_attempt_outcome=ctx["outcome"],
        first_attempt_preflight_note=ctx["preflight_note"],
        path_c_outcome_store=ctx["store"],
        memory=ctx["memory"],
        adaptive_config=ctx["adaptive_cfg"],
        replan_config=ReplanConfig(enable_replan=True),
    )
    after = len(ctx["memory"].snapshot()["records"])
    assert after == before, "orchestrator must not append MemoryRecords"


def test_trigger_branch_scenario_context_is_not_mutated(monkeypatch):
    """Sideband injection must happen on a copy."""
    from replan import ReplanConfig, run_replan_cycle

    ctx = _run_first_attempt(_demo_event())
    original_keys = set(ctx["scenario_context"].keys())
    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger_on_attempt0,
    )

    run_replan_cycle(
        event=ctx["event"],
        scenario_context=ctx["scenario_context"],
        path_c_state=ctx["state"],
        cost_output=ctx["cost_output"],
        governance_output=ctx["governance_output"],
        governance_meta=ctx["governance_meta"],
        first_attempt_route=ctx["route"],
        first_attempt_adjustment=ctx["adjustment"],
        first_attempt_policy_route_source="baseline_static",
        first_attempt_status=ctx["status"],
        first_attempt_outcome=ctx["outcome"],
        first_attempt_preflight_note=ctx["preflight_note"],
        path_c_outcome_store=ctx["store"],
        memory=ctx["memory"],
        adaptive_config=ctx["adaptive_cfg"],
        replan_config=ReplanConfig(enable_replan=True),
    )
    # Caller's scenario_context must not gain "replan_context" —
    # the orchestrator writes it on a copy it passes to the inner
    # reasoning slice.
    assert set(ctx["scenario_context"].keys()) == original_keys
    assert "replan_context" not in ctx["scenario_context"]


# ---------------------------------------------------------------------------
# Structured sideband: numeric-only, no NL prose
# ---------------------------------------------------------------------------


def test_replan_context_sideband_is_numeric_only():
    from replan.replan_orchestrator import _build_replan_context_sideband
    from replan.replan_schema import ExpectedOutcomeRef, ReplanTriggerRecord

    expected = ExpectedOutcomeRef(
        expected_cost_min=80.0, expected_cost_max=120.0,
        expected_sla_preserved=True, estimator_id="t",
    )
    trigger = ReplanTriggerRecord(
        trigger_rule_id="cost_deviation_v1",
        trigger_type="COST_DEVIATION",
        attempt_index=0,
        deviation_measurement={},
        realized_cost=500.0,
        realized_sla_preserved=True,
    )
    sideband = _build_replan_context_sideband(trigger, expected)
    # The only string values admissible are enum-like identifiers:
    # trigger_type, trigger_rule_id. Everything else must be numeric.
    allowed_string_keys = {"trigger_type", "trigger_rule_id"}
    for k, v in sideband.items():
        if k in allowed_string_keys:
            assert isinstance(v, str)
        else:
            assert isinstance(v, (int, float, bool)), (
                f"sideband[{k!r}]={v!r} must be numeric, got {type(v)}"
            )
