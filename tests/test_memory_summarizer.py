"""Phase 1: memory_summarizer pure-function tests."""

from __future__ import annotations

import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from learning.memory_schema import MemoryQuery, MemoryRecord
from learning.memory_summarizer import query_signature, summarize_records


def _rec(
    *,
    action="EXPEDITE",
    route="AUTO_EXECUTE",
    status="executed",
    cost=100.0,
    sla=True,
    event_id="E",
    ts="2026-04-01T10:00:00+00:00",
) -> MemoryRecord:
    return MemoryRecord(
        event_id=event_id,
        event_type="CARRIER_DELAY_ESCALATION",
        event_timestamp=ts,
        action_taken=action,
        execution_status=status,
        final_route=route,
        cost_incurred=cost,
        sla_preserved=sla,
        risk_level="LOW",
        session_id="S1",
    )


class TestColdStartBoundary:
    def test_below_threshold_is_cold(self):
        rows = [_rec(event_id=f"E{i}") for i in range(4)]
        s = summarize_records(rows, MemoryQuery(), threshold=5)
        assert s.matched_records == 4
        assert s.cold_start is True

    def test_at_threshold_is_not_cold(self):
        rows = [_rec(event_id=f"E{i}") for i in range(5)]
        s = summarize_records(rows, MemoryQuery(), threshold=5)
        assert s.matched_records == 5
        assert s.cold_start is False

    @pytest.mark.parametrize("threshold", [1, 3, 5, 10])
    def test_parametric_threshold(self, threshold):
        rows = [_rec(event_id=f"E{i}") for i in range(threshold - 1)]
        s = summarize_records(rows, MemoryQuery(), threshold=threshold)
        assert s.cold_start is True

        rows = [_rec(event_id=f"E{i}") for i in range(threshold)]
        s = summarize_records(rows, MemoryQuery(), threshold=threshold)
        assert s.cold_start is False


class TestZeroDenominator:
    def test_no_auto_rows_yields_none_rate(self):
        rows = [_rec(route="HUMAN_REQUIRED", status="awaiting_human_review", action=None, cost=None, sla=None)]
        s = summarize_records(rows, MemoryQuery(), threshold=3)
        assert s.auto_execute_success_rate is None

    def test_no_sla_signal_yields_none_rate(self):
        rows = [_rec(sla=None)]
        s = summarize_records(rows, MemoryQuery(), threshold=3)
        assert s.sla_preservation_rate is None

    def test_no_cost_yields_none_avg(self):
        rows = [_rec(cost=None)]
        s = summarize_records(rows, MemoryQuery(), threshold=3)
        assert s.avg_cost is None


class TestRatesAndDistribution:
    def test_auto_success_rate(self):
        rows = [
            _rec(route="AUTO_EXECUTE", status="executed", event_id="A"),
            _rec(route="AUTO_EXECUTE", status="executed_via_demo_override", event_id="B"),
            _rec(route="AUTO_EXECUTE", status="execution_failed", event_id="C"),
            _rec(route="HUMAN_REQUIRED", status="awaiting_human_review", event_id="D"),
        ]
        s = summarize_records(rows, MemoryQuery(), threshold=3)
        assert s.auto_execute_success_rate == pytest.approx(2.0 / 3.0)

    def test_sla_rate(self):
        rows = [
            _rec(sla=True, event_id="A"),
            _rec(sla=False, event_id="B"),
            _rec(sla=None, event_id="C"),
        ]
        s = summarize_records(rows, MemoryQuery(), threshold=3)
        assert s.sla_preservation_rate == 0.5

    def test_action_type_distribution_keys_sorted(self):
        rows = [
            _rec(action="TRANSFER", event_id="A"),
            _rec(action="COMPENSATE", event_id="B"),
            _rec(action="EXPEDITE", event_id="C"),
            _rec(action="TRANSFER", event_id="D"),
        ]
        s = summarize_records(rows, MemoryQuery(), threshold=3)
        assert list(s.action_type_distribution.keys()) == sorted(s.action_type_distribution.keys())
        assert s.action_type_distribution == {
            "COMPENSATE": 1, "EXPEDITE": 1, "TRANSFER": 2,
        }

    def test_none_action_bucketed(self):
        rows = [_rec(action=None, route="HUMAN_REQUIRED", status="awaiting_human_review", cost=None, sla=None)]
        s = summarize_records(rows, MemoryQuery(), threshold=3)
        assert s.action_type_distribution == {"NONE": 1}


class TestFullPrecision:
    def test_avg_cost_not_rounded(self):
        rows = [_rec(cost=1.0), _rec(cost=2.0), _rec(cost=2.0)]
        s = summarize_records(rows, MemoryQuery(), threshold=3)
        # (1 + 2 + 2) / 3 = 1.6666... — summarizer keeps full precision
        assert s.avg_cost == pytest.approx(5.0 / 3.0)


class TestQuerySignature:
    def test_signature_stable_across_seeds(self):
        q = MemoryQuery(event_type="CARRIER_DELAY_ESCALATION", action_type="EXPEDITE", recent_n=5)
        a = query_signature(q)
        b = query_signature(q)
        assert a == b
        # keys must appear in sorted order
        assert a.startswith("MemoryQuery(action_type=")

    def test_signature_distinguishes_queries(self):
        a = query_signature(MemoryQuery(event_type="CARRIER_DELAY_ESCALATION"))
        b = query_signature(MemoryQuery(event_type="WEATHER_WORSENING"))
        assert a != b
