"""
tests/test_outcome_store.py — D3-Demo Phase 3: OutcomeStore tests.

Covers:
  - append / all / count / latest
  - append-only behavior (no delete / update APIs)
  - summary aggregates correct on populated store
  - empty store summary is valid
  - recent_actions capped deterministically
  - record_routing tracks AUTO/HUMAN counts separately
  - type guard rejects non-ExecutionOutcome inputs
"""

import os
import sys
from datetime import datetime, timezone

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from outcome_schema import ExecutionOutcome
from outcome_store import OutcomeStore

_TS = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_outcome(
    event_id: str = "E1",
    action: str = "EXPEDITE",
    cost: float = 100.0,
    preserved: bool = True,
    status: str = "EXECUTED",
) -> ExecutionOutcome:
    return ExecutionOutcome(
        event_id=event_id,
        action_taken=action,
        cost_incurred=cost,
        sla_impact={"preserved": preserved, "late_hours": 0.0 if preserved else 5.0},
        state_delta={"patches": []},
        timestamp=_TS,
        status=status,
        notes="",
    )


# ===========================================================================
# Basic append / read
# ===========================================================================


class TestAppendAndRead:
    def test_empty_store_defaults(self):
        s = OutcomeStore()
        assert s.count() == 0
        assert s.all() == []
        assert s.latest() is None

    def test_append_single(self):
        s = OutcomeStore()
        s.append(_make_outcome("A1"))
        assert s.count() == 1
        assert s.latest().event_id == "A1"
        assert len(s.all()) == 1

    def test_append_multiple_preserves_order(self):
        s = OutcomeStore()
        for i in range(5):
            s.append(_make_outcome(f"E{i}"))
        ids = [o.event_id for o in s.all()]
        assert ids == ["E0", "E1", "E2", "E3", "E4"]
        assert s.latest().event_id == "E4"

    def test_append_rejects_non_outcome(self):
        s = OutcomeStore()
        with pytest.raises(TypeError):
            s.append({"event_id": "x"})
        with pytest.raises(TypeError):
            s.append(None)

    def test_all_returns_copy(self):
        """Mutating the returned list must not affect internal state."""
        s = OutcomeStore()
        s.append(_make_outcome("A1"))
        external = s.all()
        external.clear()
        assert s.count() == 1


class TestAppendOnly:
    def test_no_delete_method(self):
        s = OutcomeStore()
        assert not hasattr(s, "delete")
        assert not hasattr(s, "remove")
        assert not hasattr(s, "pop")
        assert not hasattr(s, "clear")


# ===========================================================================
# Summary aggregates
# ===========================================================================


class TestSummary:
    def test_empty_summary_valid(self):
        s = OutcomeStore()
        summary = s.summary()
        assert summary["outcomes_count"] == 0
        assert summary["total_cost"] == 0.0
        assert summary["avg_cost"] == 0.0
        assert summary["sla_preserved_count"] == 0
        assert summary["sla_missed_count"] == 0
        assert summary["auto_executed_count"] == 0
        assert summary["human_required_count"] == 0
        assert summary["recent_actions"] == []
        assert isinstance(summary["action_counts"], dict)
        assert summary["action_counts"]["EXPEDITE"] == 0

    def test_populated_summary_aggregates(self):
        s = OutcomeStore()
        s.append(_make_outcome("E1", "EXPEDITE", cost=100.0, preserved=True))
        s.append(_make_outcome("E2", "TRANSFER", cost=50.0, preserved=True))
        s.append(_make_outcome("E3", "COMPENSATE", cost=30.0, preserved=False))
        s.append(_make_outcome("E4", "NO_ACTION", cost=20.0, preserved=False))

        summary = s.summary()
        assert summary["outcomes_count"] == 4
        assert summary["total_cost"] == 200.0
        assert summary["avg_cost"] == 50.0
        assert summary["action_counts"]["EXPEDITE"] == 1
        assert summary["action_counts"]["TRANSFER"] == 1
        assert summary["action_counts"]["COMPENSATE"] == 1
        assert summary["action_counts"]["NO_ACTION"] == 1
        assert summary["sla_preserved_count"] == 2
        assert summary["sla_missed_count"] == 2

    def test_recent_actions_capped(self):
        s = OutcomeStore()
        for i in range(10):
            s.append(_make_outcome(f"R{i}"))
        summary = s.summary(recent_n=3)
        assert len(summary["recent_actions"]) == 3
        # Most recent is R9
        assert summary["recent_actions"][-1]["event_id"] == "R9"

    def test_status_counts(self):
        s = OutcomeStore()
        s.append(_make_outcome("E1", status="EXECUTED"))
        s.append(_make_outcome("E2", status="EXECUTED"))
        s.append(_make_outcome("E3", status="SKIPPED"))
        summary = s.summary()
        assert summary["status_counts"]["EXECUTED"] == 2
        assert summary["status_counts"]["SKIPPED"] == 1
        assert summary["status_counts"]["REJECTED"] == 0

    def test_resolution_patterns(self):
        s = OutcomeStore()
        s.append(_make_outcome("E1", "EXPEDITE", status="EXECUTED"))
        s.append(_make_outcome("E2", "EXPEDITE", status="EXECUTED"))
        s.append(_make_outcome("E3", "TRANSFER", status="EXECUTED"))
        patterns = s.summary()["recent_resolution_patterns"]
        assert patterns["EXPEDITE:EXECUTED"] == 2
        assert patterns["TRANSFER:EXECUTED"] == 1


# ===========================================================================
# Routing counts
# ===========================================================================


class TestRouting:
    def test_record_routing_counts(self):
        s = OutcomeStore()
        s.record_routing("AUTO_EXECUTE")
        s.record_routing("AUTO_EXECUTE")
        s.record_routing("HUMAN_REQUIRED")
        summary = s.summary()
        assert summary["auto_executed_count"] == 2
        assert summary["human_required_count"] == 1

    def test_record_routing_ignores_empty(self):
        s = OutcomeStore()
        s.record_routing("")
        s.record_routing(None)  # type: ignore[arg-type]
        summary = s.summary()
        assert summary["auto_executed_count"] == 0
        assert summary["human_required_count"] == 0

    def test_routing_independent_of_outcomes(self):
        """record_routing doesn't create outcomes; append doesn't bump routing."""
        s = OutcomeStore()
        s.append(_make_outcome("E1"))
        assert s.count() == 1
        summary = s.summary()
        # No record_routing called
        assert summary["auto_executed_count"] == 0
        assert summary["human_required_count"] == 0


# ===========================================================================
# Determinism / stability
# ===========================================================================


class TestStability:
    def test_summary_stable_between_calls(self):
        s = OutcomeStore()
        s.append(_make_outcome("E1"))
        s.append(_make_outcome("E2", action="TRANSFER"))
        a = s.summary()
        b = s.summary()
        assert a == b
