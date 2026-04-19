"""Phase 3: session_compare report tests."""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from adaptive.adaptive_schema import AdaptivePolicyAdjustment
from session.session_compare import (
    COMPARE_REPORT_SCHEMA_VERSION,
    build_compare_report,
    render_thesis_markdown,
)
from session.session_schema import (
    EffectiveDecisionRef,
    GovernanceTruthRef,
    SessionArtifact,
    SessionConfig,
    SessionEventRecord,
    SessionKPIs,
)


def _ser(
    *,
    event_id: str,
    route: str = "AUTO_EXECUTE",
    action: Optional[str] = "EXPEDITE",
    status: str = "executed",
    cost: Optional[float] = 100.0,
    preserved: Optional[bool] = True,
    adjustment: Optional[AdaptivePolicyAdjustment] = None,
    policy_route_source: str = "baseline_static",
    mode: str = "BASELINE_STATIC",
) -> SessionEventRecord:
    outcome: Optional[dict[str, Any]]
    if cost is None and preserved is None:
        outcome = None
    else:
        outcome = {
            "action_taken": action,
            "cost_incurred": cost,
            "sla_impact": {"preserved": preserved},
        }
    return SessionEventRecord(
        baseline_event_result={
            "event_id": event_id,
            "execution_outcome": outcome,
            "policy_decision": {"route": route},
            "execution_status": status,
        },
        session_id=f"SID-{mode}",
        mode=mode,
        policy_route_source=policy_route_source,
        adaptive_adjustment=adjustment,
        governance_truth=GovernanceTruthRef(
            risk_level="LOW", recommended_candidate_type="EXPEDITE",
        ),
        effective_decision=EffectiveDecisionRef(
            effective_risk="LOW",
            final_route=route,
            action_taken=action if action in ("EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION") else None,
            execution_status=status,
        ),
    )


def _artifact(mode_name: str, mode_value: str, records: list[SessionEventRecord]) -> SessionArtifact:
    return SessionArtifact(
        session_id=f"SID-{mode_name}",
        config=SessionConfig(
            seed=42, mode=mode_value, events_source="demo_stream",
        ),
        event_records=records,
        memory_snapshot={"records": [], "schema_version": "1.0"},
        kpis=SessionKPIs(events_observed=len(records)),
        schema_versions={},
        notes="",
    )


class TestCompareToSelf:
    def test_all_deltas_zero_no_divergence(self):
        records = [_ser(event_id=f"E{i}", cost=100.0) for i in range(6)]
        baseline = _artifact("baseline_static", "BASELINE_STATIC", records)
        report = build_compare_report(
            {"baseline_static": baseline},
            baseline_mode="baseline_static",
            min_records_for_shift=3,
        )
        assert report["sessions_compared"] == ["baseline_static"]
        assert report["deltas"] == {}
        assert report["diverged_events"] == []
        # thesis_claim_support says None when no warm session
        assert report["thesis_claim_support"]["supports_claim"] is None

    def test_two_modes_same_records_all_deltas_zero(self):
        records_a = [_ser(event_id=f"E{i}", cost=100.0) for i in range(5)]
        records_b = [_ser(event_id=f"E{i}", cost=100.0) for i in range(5)]
        a = _artifact("baseline_static", "BASELINE_STATIC", records_a)
        b = _artifact("path_c_cold", "PATH_C_COLD", records_b)
        report = build_compare_report(
            {"baseline_static": a, "path_c_cold": b},
            baseline_mode="baseline_static",
            min_records_for_shift=3,
        )
        assert report["diverged_events"] == []
        for _, block in report["deltas"].items():
            for v in block.values():
                assert v == 0.0 or v is None


class TestKnownDivergence:
    def test_warm_divergence_with_adjustment_link(self):
        # Baseline: all AUTO_EXECUTE executed.
        base_records = [_ser(event_id=f"E{i}") for i in range(5)]

        adj = AdaptivePolicyAdjustment(
            rule_id="poor_sla_upgrade_v1",
            adjustment_type="UPGRADE_ONE_LEVEL",
            pre_adjustment_risk="LOW",
            post_adjustment_risk="MEDIUM",
            query_signature="MemoryQuery(event_type='CARRIER_DELAY_ESCALATION')",
            memory_evidence={"matched_records": 10, "sla_preservation_rate": 0.1},
        )

        # Warm session: event E2 routed HUMAN_REQUIRED via adaptive UPGRADE.
        warm_records = [
            _ser(event_id="E0"),
            _ser(event_id="E1"),
            _ser(event_id="E2", route="HUMAN_REQUIRED",
                 action=None, status="awaiting_human_review",
                 cost=None, preserved=None,
                 adjustment=adj, policy_route_source="adaptive_adjusted",
                 mode="PATH_C_WARM"),
            _ser(event_id="E3"),
            _ser(event_id="E4"),
        ]

        baseline = _artifact("baseline_static", "BASELINE_STATIC", base_records)
        warm = _artifact("path_c_warm", "PATH_C_WARM", warm_records)

        report = build_compare_report(
            {"baseline_static": baseline, "path_c_warm": warm},
            baseline_mode="baseline_static",
            min_records_for_shift=3,
        )

        # Divergence identified
        assert len(report["diverged_events"]) == 1
        d = report["diverged_events"][0]
        assert d["event_id"] == "E2"
        assert d["routes"]["baseline_static"] == "AUTO_EXECUTE"
        assert d["routes"]["path_c_warm"] == "HUMAN_REQUIRED"
        # Adjustment linkage
        assert d["adjustment_ref"] is not None
        assert d["adjustment_ref"]["rule_id"] == "poor_sla_upgrade_v1"
        assert d["adjustment_ref"]["adjustment_type"] == "UPGRADE_ONE_LEVEL"

        # Deltas reflect the shift: human_escalation_rate up in warm
        delta_key = "path_c_warm_minus_baseline_static"
        assert delta_key in report["deltas"]
        warm_delta_hr = report["deltas"][delta_key]["human_escalation_rate"]
        assert warm_delta_hr is not None and warm_delta_hr > 0

    def test_thesis_claim_support_false_when_warm_cost_worse(self):
        # Warm session has same SLA but higher cost → supports_claim False.
        base_records = [_ser(event_id=f"E{i}", cost=100.0) for i in range(5)]
        warm_records = [_ser(event_id=f"E{i}", cost=200.0) for i in range(5)]
        baseline = _artifact("baseline_static", "BASELINE_STATIC", base_records)
        warm = _artifact("path_c_warm", "PATH_C_WARM", warm_records)

        report = build_compare_report(
            {"baseline_static": baseline, "path_c_warm": warm},
            baseline_mode="baseline_static",
            min_records_for_shift=3,
        )
        t = report["thesis_claim_support"]
        assert t["warm_cost_delta"] is not None and t["warm_cost_delta"] > 0
        assert t["supports_claim"] is False


class TestReportShape:
    def test_schema_and_required_blocks(self):
        records = [_ser(event_id=f"E{i}") for i in range(3)]
        a = _artifact("baseline_static", "BASELINE_STATIC", records)
        report = build_compare_report(
            {"baseline_static": a},
            baseline_mode="baseline_static",
            min_records_for_shift=3,
        )
        assert report["schema_version"] == COMPARE_REPORT_SCHEMA_VERSION
        for k in (
            "sessions_compared", "kpi_matrix", "deltas",
            "diverged_events", "thesis_claim_support",
            "per_session_kpi_report", "baseline_mode",
            "min_records_for_shift",
        ):
            assert k in report, f"missing block: {k}"

    def test_rendered_markdown_contains_expected_sections(self):
        records = [_ser(event_id=f"E{i}") for i in range(4)]
        a = _artifact("baseline_static", "BASELINE_STATIC", records)
        b = _artifact("path_c_cold", "PATH_C_COLD", records)
        report = build_compare_report(
            {"baseline_static": a, "path_c_cold": b},
            baseline_mode="baseline_static",
            min_records_for_shift=3,
        )
        md = render_thesis_markdown(report)
        for phrase in (
            "# Path C Phase 3 — Thesis-Aligned Session Compare Report",
            "## Overall KPIs",
            "## Cold-phase KPIs",
            "## Warm-phase KPIs",
            "## Deltas vs baseline",
            "## Diverged events",
            "## Relation to calibrated supervision thesis",
            "supports_claim",
        ):
            assert phrase in md, f"thesis markdown missing section: {phrase!r}"

    def test_rendered_markdown_is_pure_function(self):
        records = [_ser(event_id=f"E{i}") for i in range(4)]
        a = _artifact("baseline_static", "BASELINE_STATIC", records)
        b = _artifact("path_c_cold", "PATH_C_COLD", records)
        report = build_compare_report(
            {"baseline_static": a, "path_c_cold": b},
            baseline_mode="baseline_static",
            min_records_for_shift=3,
        )
        md1 = render_thesis_markdown(report)
        md2 = render_thesis_markdown(report)
        assert md1 == md2
