"""B1 Slice 4: replan-aware KPI calculator tests.

Covers additive functions in ``src/session/kpi_calculator.py``:

  - ``REPLAN_KPI_KEYS``
  - ``is_replan_success``
  - ``compute_replan_kpis``
  - ``compute_session_kpi_report`` attaches a ``replan`` sibling block
    only when at least one event has ``replan_trace is not None``.

Existing Phase-3 KPIs are NOT redefined here; they stay the way the
Slice 0/Phase-3 tests already verify them. These tests only check
the new surface.
"""

from __future__ import annotations

import copy
import os
import sys
from datetime import datetime, timezone

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from adaptive.adaptive_schema import AdaptivePolicyAdjustment  # noqa: E402
from replan.replan_schema import (  # noqa: E402
    ExpectedOutcomeRef,
    ReplanAttemptRecord,
    ReplanTriggerRecord,
)
from session.kpi_calculator import (  # noqa: E402
    REPLAN_KPI_KEYS,
    compute_phase_kpis,
    compute_replan_kpis,
    compute_session_kpi_report,
    is_replan_success,
)
from session.session_schema import (  # noqa: E402
    EffectiveDecisionRef,
    GovernanceTruthRef,
    SessionArtifact,
    SessionConfig,
    SessionEventRecord,
    SessionKPIs,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _trigger(ttype: str, attempt_index: int = 0) -> ReplanTriggerRecord:
    return ReplanTriggerRecord(
        trigger_rule_id={
            "NO_TRIGGER": "no_trigger_v1",
            "COST_DEVIATION": "cost_deviation_v1",
            "SLA_DEVIATION": "sla_deviation_v1",
            "EXECUTION_FAILED": "execution_failed_v1",
            "PREFLIGHT_FAILED": "preflight_failed_v1",
        }[ttype],
        trigger_type=ttype,
        attempt_index=attempt_index,
        deviation_measurement={},
    )


def _attempt(
    *,
    attempt_index: int,
    status: str,
    route: str = "AUTO_EXECUTE",
    action: str | None = "EXPEDITE",
    sla_preserved: bool | None = True,
    cost_incurred: float | None = 100.0,
    trigger_type: str = "NO_TRIGGER",
) -> ReplanAttemptRecord:
    outcome: dict | None = None
    if status in {"executed", "executed_via_demo_override"}:
        outcome = {
            "cost_incurred": cost_incurred if cost_incurred is not None else 0.0,
            "sla_impact": {
                "preserved": bool(sla_preserved) if sla_preserved is not None else False,
            },
            "action_taken": action,
        }
    return ReplanAttemptRecord(
        attempt_index=attempt_index,
        attempt_final_route=route,  # type: ignore[arg-type]
        attempt_action_taken=action if action in {
            "EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"
        } else None,  # type: ignore[arg-type]
        attempt_execution_status=status,  # type: ignore[arg-type]
        execution_outcome=outcome,
        trigger=_trigger(trigger_type, attempt_index=attempt_index),
    )


def _ser(
    *,
    event_id: str = "E1",
    exec_status: str = "executed",
    action: str | None = "EXPEDITE",
    route: str = "AUTO_EXECUTE",
    cost: float = 100.0,
    sla_preserved: bool = True,
    replan_trace: list[ReplanAttemptRecord] | None = None,
    replan_triggers: list[ReplanTriggerRecord] | None = None,
) -> SessionEventRecord:
    baseline_outcome: dict | None = None
    if exec_status in {"executed", "executed_via_demo_override"}:
        baseline_outcome = {
            "cost_incurred": cost,
            "sla_impact": {"preserved": sla_preserved},
        }
    return SessionEventRecord(
        baseline_event_result={
            "event_id": event_id,
            "event_type": "CARRIER_DELAY",
            "policy_decision": {"route": route},
            "execution_status": exec_status,
            "execution_outcome": baseline_outcome,
        },
        session_id="S1",
        mode="PATH_C_WARM",
        policy_route_source="baseline_static",
        governance_truth=GovernanceTruthRef(
            risk_level="LOW",
            recommended_candidate_type=action if action else "NO_ACTION",
        ),
        effective_decision=EffectiveDecisionRef(
            effective_risk="LOW",
            final_route=route,  # type: ignore[arg-type]
            action_taken=action if action in {
                "EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"
            } else None,
            execution_status=exec_status,  # type: ignore[arg-type]
        ),
        replan_trace=replan_trace,
        replan_triggers=replan_triggers,
    )


# ---------------------------------------------------------------------------
# is_replan_success rule
# ---------------------------------------------------------------------------


def test_no_trace_returns_false():
    rec = _ser(replan_trace=None, replan_triggers=None)
    assert is_replan_success(rec) is False


def test_empty_trace_returns_false():
    rec = _ser(replan_trace=[], replan_triggers=[])
    assert is_replan_success(rec) is False


def test_rule1_failure_to_executed():
    a0 = _attempt(
        attempt_index=0, status="execution_failed", action=None,
        trigger_type="EXECUTION_FAILED",
    )
    a1 = _attempt(attempt_index=1, status="executed", trigger_type="NO_TRIGGER")
    rec = _ser(replan_trace=[a0, a1], replan_triggers=[a0.trigger, a1.trigger])
    assert is_replan_success(rec) is True


def test_rule2_sla_missed_to_preserved():
    a0 = _attempt(
        attempt_index=0, status="executed", sla_preserved=False,
        trigger_type="SLA_DEVIATION",
    )
    a1 = _attempt(
        attempt_index=1, status="executed", sla_preserved=True,
        trigger_type="NO_TRIGGER",
    )
    rec = _ser(replan_trace=[a0, a1], replan_triggers=[a0.trigger, a1.trigger])
    assert is_replan_success(rec) is True


def test_rule3_cost_deviation_to_no_trigger():
    a0 = _attempt(
        attempt_index=0, status="executed", cost_incurred=500.0,
        trigger_type="COST_DEVIATION",
    )
    a1 = _attempt(
        attempt_index=1, status="executed", cost_incurred=100.0,
        trigger_type="NO_TRIGGER",
    )
    rec = _ser(replan_trace=[a0, a1], replan_triggers=[a0.trigger, a1.trigger])
    assert is_replan_success(rec) is True


def test_no_recovery_when_both_attempts_still_cost_deviate():
    a0 = _attempt(
        attempt_index=0, status="executed", cost_incurred=500.0,
        trigger_type="COST_DEVIATION",
    )
    a1 = _attempt(
        attempt_index=1, status="executed", cost_incurred=500.0,
        trigger_type="COST_DEVIATION",
    )
    rec = _ser(replan_trace=[a0, a1], replan_triggers=[a0.trigger, a1.trigger])
    assert is_replan_success(rec) is False


def test_no_recovery_when_both_attempts_fail():
    a0 = _attempt(
        attempt_index=0, status="execution_failed", action=None,
        trigger_type="EXECUTION_FAILED",
    )
    a1 = _attempt(
        attempt_index=1, status="execution_failed", action=None,
        trigger_type="EXECUTION_FAILED",
    )
    rec = _ser(replan_trace=[a0, a1], replan_triggers=[a0.trigger, a1.trigger])
    assert is_replan_success(rec) is False


# ---------------------------------------------------------------------------
# compute_replan_kpis — counts, rates, zero-denominator policy
# ---------------------------------------------------------------------------


def test_empty_records_all_none_rates_zero_counts():
    k = compute_replan_kpis([])
    assert k["replan_events_observed"] == 0
    assert k["replan_fire_count"] == 0
    assert k["replan_trigger_rate"] is None
    assert k["replan_success_count"] == 0
    assert k["replan_recovery_rate"] is None


def test_no_replan_records_yield_zero_counts_and_zero_trigger_rate():
    # events_observed > 0, but no replan traces.
    rs = [_ser(event_id=f"E{i}") for i in range(4)]
    k = compute_replan_kpis(rs)
    assert k["replan_events_observed"] == 0
    assert k["replan_fire_count"] == 0
    # events_observed=4 > 0 → rate is 0/4 = 0.0, not None.
    assert k["replan_trigger_rate"] == 0.0
    # replan_fire_count=0 → recovery rate stays None (zero denominator).
    assert k["replan_recovery_rate"] is None


def _replanned(
    *,
    event_id: str,
    a0_status: str,
    a0_sla: bool | None,
    a0_cost: float,
    a0_trigger: str,
    a1_status: str,
    a1_sla: bool | None,
    a1_cost: float,
    a1_trigger: str,
) -> SessionEventRecord:
    a0 = _attempt(
        attempt_index=0, status=a0_status, sla_preserved=a0_sla,
        cost_incurred=a0_cost, trigger_type=a0_trigger,
    )
    a1 = _attempt(
        attempt_index=1, status=a1_status, sla_preserved=a1_sla,
        cost_incurred=a1_cost, trigger_type=a1_trigger,
    )
    return _ser(
        event_id=event_id,
        exec_status=a1_status,
        sla_preserved=bool(a1_sla) if a1_sla is not None else True,
        cost=a1_cost,
        replan_trace=[a0, a1],
        replan_triggers=[a0.trigger, a1.trigger],
    )


def test_replan_rates_are_exact():
    rs = [
        _ser(event_id="N0"),
        _ser(event_id="N1"),
        _replanned(
            event_id="R0",
            a0_status="executed", a0_sla=True, a0_cost=500.0,
            a0_trigger="COST_DEVIATION",
            a1_status="executed", a1_sla=True, a1_cost=100.0,
            a1_trigger="NO_TRIGGER",
        ),
        _replanned(
            event_id="R1",
            a0_status="execution_failed", a0_sla=None, a0_cost=0.0,
            a0_trigger="EXECUTION_FAILED",
            a1_status="execution_failed", a1_sla=None, a1_cost=0.0,
            a1_trigger="EXECUTION_FAILED",
        ),
    ]
    k = compute_replan_kpis(rs)
    assert k["replan_events_observed"] == 2
    assert k["replan_fire_count"] == 2
    # 2 replan events out of 4 observed.
    assert k["replan_trigger_rate"] == pytest.approx(0.5)
    # R0 recovers (rule R3); R1 does not.
    assert k["replan_success_count"] == 1
    assert k["replan_recovery_rate"] == pytest.approx(0.5)


def test_all_keys_always_present():
    k = compute_replan_kpis([])
    assert set(k.keys()) == set(REPLAN_KPI_KEYS)


# ---------------------------------------------------------------------------
# compute_session_kpi_report — conditional "replan" sibling block
# ---------------------------------------------------------------------------


def _artifact(records: list[SessionEventRecord]) -> SessionArtifact:
    return SessionArtifact(
        session_id="S1",
        config=SessionConfig(
            seed=1, mode="PATH_C_COLD", events_source="demo_stream",
        ),
        event_records=records,
        memory_snapshot={"records": [], "schema_version": "1.0"},
        kpis=SessionKPIs(events_observed=len(records)),
        schema_versions={},
        notes="",
    )


def test_report_omits_replan_block_when_no_trace():
    rs = [_ser(event_id=f"E{i}") for i in range(3)]
    report = compute_session_kpi_report(_artifact(rs), min_records_for_shift=1)
    assert "replan" not in report
    # Existing keys unchanged.
    assert set(report.keys()) == {
        "schema_version", "session_id", "mode", "min_records_for_shift",
        "cold_phase", "warm_phase", "overall",
    }


def test_report_includes_replan_block_when_any_trace():
    rs = [
        _ser(event_id="E0"),
        _replanned(
            event_id="E1",
            a0_status="executed", a0_sla=True, a0_cost=500.0,
            a0_trigger="COST_DEVIATION",
            a1_status="executed", a1_sla=True, a1_cost=100.0,
            a1_trigger="NO_TRIGGER",
        ),
    ]
    report = compute_session_kpi_report(_artifact(rs), min_records_for_shift=1)
    assert "replan" in report
    assert set(report["replan"].keys()) == {"cold_phase", "warm_phase", "overall"}
    assert report["replan"]["overall"]["replan_fire_count"] == 1
    assert report["replan"]["overall"]["replan_success_count"] == 1
    # cold_phase=events[:1]=[E0] — no replan. warm_phase=[E1] — has replan.
    assert report["replan"]["cold_phase"]["replan_events_observed"] == 0
    assert report["replan"]["warm_phase"]["replan_events_observed"] == 1


# ---------------------------------------------------------------------------
# Existing Phase-3 KPIs unchanged in presence of replan records
# ---------------------------------------------------------------------------


def test_phase_kpis_unchanged_by_replan_fields():
    """compute_phase_kpis must not read replan_trace / replan_triggers."""
    rs_a = [_ser(event_id=f"E{i}") for i in range(4)]
    rs_b = [
        _replanned(
            event_id=f"E{i}",
            a0_status="executed", a0_sla=True, a0_cost=100.0,
            a0_trigger="COST_DEVIATION",
            a1_status="executed", a1_sla=True, a1_cost=100.0,
            a1_trigger="NO_TRIGGER",
        )
        for i in range(4)
    ]
    # Both sets have identical baseline_event_result / effective_decision
    # shapes; only replan_trace differs. Phase KPIs must be identical.
    k_a = compute_phase_kpis(rs_a)
    k_b = compute_phase_kpis(rs_b)
    assert k_a == k_b
