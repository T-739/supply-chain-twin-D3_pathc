"""B1 Slice 4: replan-aware session compare tests.

Covers the ``replan_trace_summary`` conditional sibling block added
to ``build_compare_report`` and the shape-preservation guarantee
that reports for non-replan sessions retain pre-B1 surface exactly.
"""

from __future__ import annotations

import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from replan.replan_schema import (  # noqa: E402
    ReplanAttemptRecord,
    ReplanTriggerRecord,
)
from session.session_compare import build_compare_report  # noqa: E402
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


_EXISTING_TOP_LEVEL_KEYS = {
    "schema_version", "sessions_compared", "baseline_mode",
    "min_records_for_shift", "per_session_kpi_report",
    "kpi_matrix", "deltas", "diverged_events", "thesis_claim_support",
}


def _trig(ttype: str, attempt_index: int = 0) -> ReplanTriggerRecord:
    rule = {
        "NO_TRIGGER": "no_trigger_v1",
        "COST_DEVIATION": "cost_deviation_v1",
        "SLA_DEVIATION": "sla_deviation_v1",
        "EXECUTION_FAILED": "execution_failed_v1",
        "PREFLIGHT_FAILED": "preflight_failed_v1",
    }[ttype]
    return ReplanTriggerRecord(
        trigger_rule_id=rule,
        trigger_type=ttype,
        attempt_index=attempt_index,
        deviation_measurement={},
    )


def _attempt(
    *,
    attempt_index: int,
    status: str,
    sla_preserved: bool = True,
    cost: float = 100.0,
    trigger_type: str = "NO_TRIGGER",
) -> ReplanAttemptRecord:
    outcome: dict | None = None
    if status in {"executed", "executed_via_demo_override"}:
        outcome = {
            "cost_incurred": cost,
            "sla_impact": {"preserved": sla_preserved},
            "action_taken": "EXPEDITE",
        }
    return ReplanAttemptRecord(
        attempt_index=attempt_index,
        attempt_final_route="AUTO_EXECUTE",
        attempt_action_taken="EXPEDITE",
        attempt_execution_status=status,  # type: ignore[arg-type]
        execution_outcome=outcome,
        trigger=_trig(trigger_type, attempt_index=attempt_index),
    )


def _ser(event_id: str, *, replan: bool = False,
         trigger_type: str = "COST_DEVIATION",
         recover: bool = True) -> SessionEventRecord:
    trace = None
    triggers = None
    if replan:
        a0 = _attempt(
            attempt_index=0, status="executed",
            cost=500.0 if trigger_type == "COST_DEVIATION" else 100.0,
            sla_preserved=False if trigger_type == "SLA_DEVIATION" else True,
            trigger_type=trigger_type,
        )
        a1 = _attempt(
            attempt_index=1,
            status="executed",
            cost=100.0 if recover else 500.0,
            sla_preserved=True,
            trigger_type="NO_TRIGGER" if recover else trigger_type,
        )
        trace = [a0, a1]
        triggers = [a0.trigger, a1.trigger]

    return SessionEventRecord(
        baseline_event_result={
            "event_id": event_id,
            "event_type": "CARRIER_DELAY",
            "policy_decision": {"route": "AUTO_EXECUTE"},
            "execution_status": "executed",
            "execution_outcome": {
                "cost_incurred": 100.0,
                "sla_impact": {"preserved": True},
            },
        },
        session_id="S",
        mode="PATH_C_WARM",
        policy_route_source="baseline_static",
        governance_truth=GovernanceTruthRef(
            risk_level="LOW", recommended_candidate_type="EXPEDITE",
        ),
        effective_decision=EffectiveDecisionRef(
            effective_risk="LOW",
            final_route="AUTO_EXECUTE",
            action_taken="EXPEDITE",
            execution_status="executed",
        ),
        replan_trace=trace,
        replan_triggers=triggers,
    )


def _artifact(mode: str, records: list[SessionEventRecord]) -> SessionArtifact:
    return SessionArtifact(
        session_id=f"S-{mode}",
        config=SessionConfig(
            seed=1, mode="PATH_C_WARM", events_source="demo_stream",
        ),
        event_records=records,
        memory_snapshot={"records": [], "schema_version": "1.0"},
        kpis=SessionKPIs(events_observed=len(records)),
        schema_versions={},
        notes="",
    )


# ---------------------------------------------------------------------------
# (1) No replan traces → compare surface unchanged
# ---------------------------------------------------------------------------


def test_no_replan_traces_keeps_pre_b1_top_level_shape():
    arts = {
        "baseline_static": _artifact("baseline", [_ser("E1"), _ser("E2")]),
        "path_c_cold": _artifact("cold", [_ser("E1"), _ser("E2")]),
    }
    report = build_compare_report(
        arts, baseline_mode="baseline_static", min_records_for_shift=1,
    )
    assert set(report.keys()) == _EXISTING_TOP_LEVEL_KEYS
    # No per-session replan block either.
    for kr in report["per_session_kpi_report"].values():
        assert "replan" not in kr


# ---------------------------------------------------------------------------
# (2) At least one replan trace → replan_trace_summary appears
# ---------------------------------------------------------------------------


def test_replan_present_attaches_replan_trace_summary():
    arts = {
        "baseline_static": _artifact("baseline", [_ser("E1"), _ser("E2")]),
        "path_c_warm": _artifact(
            "warm",
            [_ser("E1", replan=True, recover=True),
             _ser("E2", replan=True, recover=False)],
        ),
    }
    report = build_compare_report(
        arts, baseline_mode="baseline_static", min_records_for_shift=1,
    )
    assert "replan_trace_summary" in report
    rts = report["replan_trace_summary"]
    assert rts["sessions_with_replan"] == ["path_c_warm"]
    assert rts["total_replan_events"] == 2
    # Trigger counts: both events fired COST_DEVIATION.
    assert rts["trigger_type_counts"]["path_c_warm"]["COST_DEVIATION"] == 2
    assert rts["trigger_type_counts"]["path_c_warm"]["NO_TRIGGER"] == 0
    # Recovered: one event (E1) recovers; E2 does not.
    assert rts["recovered_events_count"]["path_c_warm"] == 1
    # by_mode carries KPIs.
    assert (
        rts["by_mode"]["path_c_warm"]["replan_kpis_overall"]["replan_fire_count"]
        == 2
    )
    assert (
        rts["by_mode"]["path_c_warm"]["replan_kpis_overall"]["replan_success_count"]
        == 1
    )


def test_per_session_replan_block_only_on_replan_session():
    arts = {
        "baseline_static": _artifact("baseline", [_ser("E1"), _ser("E2")]),
        "path_c_warm": _artifact(
            "warm",
            [_ser("E1", replan=True, recover=True),
             _ser("E2", replan=True, recover=False)],
        ),
    }
    report = build_compare_report(
        arts, baseline_mode="baseline_static", min_records_for_shift=1,
    )
    assert "replan" not in report["per_session_kpi_report"]["baseline_static"]
    assert "replan" in report["per_session_kpi_report"]["path_c_warm"]


# ---------------------------------------------------------------------------
# (3) Existing compare blocks still behave correctly
# ---------------------------------------------------------------------------


def test_existing_blocks_still_present_and_well_formed():
    arts = {
        "baseline_static": _artifact("baseline", [_ser("E1"), _ser("E2")]),
        "path_c_warm": _artifact(
            "warm",
            [_ser("E1", replan=True, recover=True),
             _ser("E2", replan=True, recover=False)],
        ),
    }
    report = build_compare_report(
        arts, baseline_mode="baseline_static", min_records_for_shift=1,
    )
    # Core blocks present and shaped as pre-B1.
    for key in _EXISTING_TOP_LEVEL_KEYS:
        assert key in report
    assert report["sessions_compared"] == ["baseline_static", "path_c_warm"]
    assert report["baseline_mode"] == "baseline_static"
    assert set(report["kpi_matrix"].keys()) == {
        "cold_phase", "warm_phase", "overall",
    }
    assert "path_c_warm_minus_baseline_static" in report["deltas"]


def test_compare_to_self_no_divergence_when_no_replan():
    arts = {
        "baseline_static": _artifact("baseline", [_ser("E1"), _ser("E2")]),
    }
    report = build_compare_report(
        arts, baseline_mode="baseline_static", min_records_for_shift=1,
    )
    assert "replan_trace_summary" not in report
    assert report["diverged_events"] == []


# ---------------------------------------------------------------------------
# (4) Rounding preserved for replan rates in by_mode
# ---------------------------------------------------------------------------


def test_replan_rates_rounded_in_by_mode():
    # 3 replan events, 1 recovery → trigger_rate=1.0, recovery_rate=0.3333...
    records = [
        _ser("E1", replan=True, recover=True),
        _ser("E2", replan=True, recover=False),
        _ser("E3", replan=True, recover=False),
    ]
    arts = {
        "baseline_static": _artifact("baseline", [_ser("B1"), _ser("B2"), _ser("B3")]),
        "path_c_warm": _artifact("warm", records),
    }
    report = build_compare_report(
        arts, baseline_mode="baseline_static", min_records_for_shift=1,
    )
    rk = report["replan_trace_summary"]["by_mode"]["path_c_warm"][
        "replan_kpis_overall"
    ]
    # replan_fire_count=3 out of events_observed=3 → 1.0
    assert rk["replan_trigger_rate"] == 1.0
    # replan_success_count=1 / 3 → 0.3333 rounded at serialization boundary.
    assert rk["replan_recovery_rate"] == pytest.approx(0.3333, abs=1e-9)
