"""Phase 3: kpi_calculator deterministic KPI tests.

Hand-constructed SessionEventRecord sequences produce exact KPI values.
Zero-denominator returns None. Cold/warm segmentation honored.
Rounding is a serialization-boundary concern only.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from session.kpi_calculator import (
    PHASE_KPI_KEYS,
    _round_phase_kpis,
    compute_phase_kpis,
    compute_session_kpi_report,
    round_kpi_report,
    segment_records,
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
    event_id: str = "EVT",
    route: str = "AUTO_EXECUTE",
    action: Optional[str] = "EXPEDITE",
    status: str = "executed",
    cost: Optional[float] = 100.0,
    preserved: Optional[bool] = True,
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
        session_id="S1",
        mode="BASELINE_STATIC",
        policy_route_source="baseline_static",
        adaptive_adjustment=None,
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


class TestCounts:
    def test_counts_on_mixed_session(self):
        records = [
            _ser(event_id="A", route="AUTO_EXECUTE", status="executed", action="EXPEDITE", preserved=True, cost=100.0),
            _ser(event_id="B", route="AUTO_EXECUTE", status="executed", action="TRANSFER", preserved=False, cost=200.0),
            _ser(event_id="C", route="HUMAN_REQUIRED", status="awaiting_human_review", action=None, preserved=None, cost=None),
            _ser(event_id="D", route="AUTO_EXECUTE", status="preflight_failed", action=None, preserved=None, cost=None),
            _ser(event_id="E", route="AUTO_EXECUTE", status="execution_failed", action=None, preserved=None, cost=None),
        ]
        k = compute_phase_kpis(records)
        assert k["events_observed"] == 5
        assert k["events_with_outcome"] == 2
        assert k["events_skipped"] == 1
        assert k["events_failed"] == 2
        assert k["events_processed"] == 3
        # invariant from §3.D
        assert k["events_observed"] == (
            k["events_with_outcome"] + k["events_skipped"] + k["events_failed"]
        )


class TestRatesExact:
    def test_sla_preservation_rate_exact(self):
        records = [
            _ser(event_id="A", preserved=True, cost=100.0),
            _ser(event_id="B", preserved=False, cost=200.0),
            _ser(event_id="C", preserved=True, cost=300.0),
        ]
        k = compute_phase_kpis(records)
        assert k["sla_preservation_rate"] == pytest.approx(2.0 / 3.0)

    def test_avg_cost_per_event_exact(self):
        records = [
            _ser(event_id="A", preserved=True, cost=100.0),
            _ser(event_id="B", preserved=True, cost=200.0),
            _ser(event_id="C", preserved=True, cost=300.0),
        ]
        k = compute_phase_kpis(records)
        assert k["avg_cost_per_event"] == pytest.approx(200.0)

    def test_calibrated_autonomy_score_exact(self):
        records = [
            _ser(event_id="A", route="AUTO_EXECUTE", preserved=True, cost=100.0),
            _ser(event_id="B", route="AUTO_EXECUTE", preserved=False, cost=200.0),
            _ser(event_id="C", route="AUTO_EXECUTE", preserved=True, cost=300.0),
            # HUMAN_REQUIRED route does not enter CAS denominator.
            _ser(event_id="D", route="HUMAN_REQUIRED", action=None,
                 status="awaiting_human_review", preserved=None, cost=None),
        ]
        k = compute_phase_kpis(records)
        assert k["calibrated_autonomy_score"] == pytest.approx(2.0 / 3.0)

    def test_auto_execute_and_human_escalation_rate(self):
        records = [
            _ser(event_id="A", route="AUTO_EXECUTE"),
            _ser(event_id="B", route="HUMAN_REQUIRED", action=None,
                 status="awaiting_human_review", preserved=None, cost=None),
            _ser(event_id="C", route="HUMAN_REQUIRED", action=None,
                 status="awaiting_human_review", preserved=None, cost=None),
            _ser(event_id="D", route="AUTO_EXECUTE"),
        ]
        k = compute_phase_kpis(records)
        assert k["auto_execute_rate"] == 0.5
        assert k["human_escalation_rate"] == 0.5
        # Their sum = 1.0 since every record has one of the two routes.
        assert pytest.approx(k["auto_execute_rate"] + k["human_escalation_rate"]) == 1.0

    def test_known_outcome_coverage(self):
        records = [
            _ser(event_id="A"),  # with_outcome
            _ser(event_id="B", route="HUMAN_REQUIRED", action=None,
                 status="awaiting_human_review", preserved=None, cost=None),
        ]
        k = compute_phase_kpis(records)
        assert k["known_outcome_coverage"] == 0.5


class TestZeroDenominator:
    def test_empty_segment_all_rates_none(self):
        k = compute_phase_kpis([])
        assert k["events_observed"] == 0
        for name in (
            "sla_preservation_rate",
            "avg_cost_per_event",
            "calibrated_autonomy_score",
            "human_escalation_rate",
            "auto_execute_rate",
            "known_outcome_coverage",
        ):
            assert k[name] is None

    def test_no_with_outcome_events_sla_and_cost_none(self):
        records = [
            _ser(event_id="A", route="HUMAN_REQUIRED", action=None,
                 status="awaiting_human_review", preserved=None, cost=None),
            _ser(event_id="B", route="AUTO_EXECUTE", status="preflight_failed",
                 action=None, preserved=None, cost=None),
        ]
        k = compute_phase_kpis(records)
        assert k["sla_preservation_rate"] is None
        assert k["avg_cost_per_event"] is None
        # CAS denominator is AUTO_EXECUTE ∩ with_outcome → 0
        assert k["calibrated_autonomy_score"] is None
        # Observed > 0 → auto/human rates defined (both rates exist as counts).
        assert k["auto_execute_rate"] == 0.5
        assert k["human_escalation_rate"] == 0.5
        assert k["known_outcome_coverage"] == 0.0


class TestSegmentation:
    def _build_artifact(self, n_records: int) -> SessionArtifact:
        records = [_ser(event_id=f"E{i}", cost=10.0 * (i + 1)) for i in range(n_records)]
        return SessionArtifact(
            session_id="S1",
            config=SessionConfig(
                seed=1, mode="PATH_C_COLD", events_source="demo_stream",
            ),
            event_records=records,
            memory_snapshot={"records": [], "schema_version": "1.0"},
            kpis=SessionKPIs(events_observed=n_records),
            schema_versions={},
            notes="",
        )

    def test_cold_warm_split_by_min_records_for_shift(self):
        artifact = self._build_artifact(6)
        report = compute_session_kpi_report(artifact, min_records_for_shift=3)
        assert report["cold_phase"]["events_observed"] == 3
        assert report["warm_phase"]["events_observed"] == 3
        assert report["overall"]["events_observed"] == 6

    def test_segmentation_parameterized(self):
        artifact = self._build_artifact(10)
        for n in (0, 1, 3, 5, 10, 20):
            report = compute_session_kpi_report(artifact, min_records_for_shift=n)
            assert report["cold_phase"]["events_observed"] == min(n, 10)
            assert report["warm_phase"]["events_observed"] == max(0, 10 - n)

    def test_segment_records_helper(self):
        rs = [_ser(event_id=f"E{i}") for i in range(5)]
        cold, warm = segment_records(rs, min_records_for_shift=2)
        assert len(cold) == 2
        assert len(warm) == 3


class TestRoundingOnlyAtSerialization:
    def test_raw_rate_is_unrounded(self):
        records = [
            _ser(event_id="A", preserved=True),
            _ser(event_id="B", preserved=True),
            _ser(event_id="C", preserved=False),
        ]
        k = compute_phase_kpis(records)
        # 2/3 is not a nice round number; must NOT be rounded here
        assert k["sla_preservation_rate"] != round(2.0 / 3.0, 4)
        assert k["sla_preservation_rate"] == pytest.approx(2.0 / 3.0)

    def test_round_phase_kpis_rounds_only_rates(self):
        records = [
            _ser(event_id="A", preserved=True),
            _ser(event_id="B", preserved=True),
            _ser(event_id="C", preserved=False),
        ]
        k_raw = compute_phase_kpis(records)
        k_rounded = _round_phase_kpis(k_raw)
        # Count fields unchanged
        assert k_rounded["events_observed"] == k_raw["events_observed"]
        # Rates rounded to 4 decimals
        assert k_rounded["sla_preservation_rate"] == 0.6667


class TestPhaseKPIKeyOrder:
    def test_every_key_present_in_report(self):
        records = [_ser(event_id="A")]
        k = compute_phase_kpis(records)
        assert set(k.keys()) == set(PHASE_KPI_KEYS)
