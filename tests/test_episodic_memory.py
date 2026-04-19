"""Phase 1: EpisodicMemory substrate tests."""

from __future__ import annotations

import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from learning.episodic_memory import EpisodicMemory
from learning.memory_schema import MemoryQuery, MemoryRecord


def _rec(
    event_id: str = "EVT-1",
    *,
    event_type: str = "CARRIER_DELAY_ESCALATION",
    ts: str = "2026-04-01T10:00:00+00:00",
    action: str | None = "EXPEDITE",
    route: str = "AUTO_EXECUTE",
    status: str = "executed",
    cost: float | None = 100.0,
    sla: bool | None = True,
    risk: str = "LOW",
    session: str = "S1",
) -> MemoryRecord:
    return MemoryRecord(
        event_id=event_id,
        event_type=event_type,
        event_timestamp=ts,
        action_taken=action,
        execution_status=status,
        final_route=route,
        cost_incurred=cost,
        sla_preserved=sla,
        risk_level=risk,
        session_id=session,
    )


class TestAppendOnly:
    def test_append_stores_record(self):
        m = EpisodicMemory()
        m.append(_rec("EVT-1"))
        assert len(m) == 1

    def test_no_delete_or_update_surface(self):
        m = EpisodicMemory()
        for forbidden in ("delete", "remove", "pop", "update", "replace"):
            assert not hasattr(m, forbidden), (
                f"EpisodicMemory must not expose {forbidden!r} — append-only"
            )

    def test_append_rejects_non_record(self):
        m = EpisodicMemory()
        with pytest.raises(TypeError):
            m.append({"event_id": "x"})  # dict is not a MemoryRecord


class TestDeterministicOrder:
    def test_snapshot_sorted_by_timestamp_then_event_id(self):
        m = EpisodicMemory()
        # Append in reverse order.
        m.append(_rec("EVT-3", ts="2026-04-01T10:10:00+00:00"))
        m.append(_rec("EVT-1", ts="2026-04-01T10:00:00+00:00"))
        m.append(_rec("EVT-2", ts="2026-04-01T10:05:00+00:00"))

        ids = [r["event_id"] for r in m.snapshot()["records"]]
        assert ids == ["EVT-1", "EVT-2", "EVT-3"]

    def test_same_timestamp_breaks_tie_on_event_id(self):
        m = EpisodicMemory()
        ts = "2026-04-01T10:00:00+00:00"
        m.append(_rec("EVT-B", ts=ts))
        m.append(_rec("EVT-A", ts=ts))

        ids = [r["event_id"] for r in m.snapshot()["records"]]
        assert ids == ["EVT-A", "EVT-B"]


class TestQuery:
    def _populated(self) -> EpisodicMemory:
        m = EpisodicMemory()
        for i, (etype, action, route, ts) in enumerate([
            ("CARRIER_DELAY_ESCALATION", "EXPEDITE", "AUTO_EXECUTE", "2026-04-01T10:00:00+00:00"),
            ("CARRIER_DELAY_ESCALATION", "TRANSFER", "AUTO_EXECUTE", "2026-04-01T10:05:00+00:00"),
            ("WEATHER_WORSENING",        None,        "HUMAN_REQUIRED", "2026-04-01T10:10:00+00:00"),
            ("CARRIER_DELAY_ESCALATION", "EXPEDITE", "HUMAN_REQUIRED", "2026-04-01T10:15:00+00:00"),
        ]):
            m.append(_rec(f"EVT-{i}", event_type=etype, action=action, route=route, ts=ts))
        return m

    def test_filter_by_event_type(self):
        m = self._populated()
        res = m.query(MemoryQuery(event_type="CARRIER_DELAY_ESCALATION"))
        assert [r.event_id for r in res] == ["EVT-0", "EVT-1", "EVT-3"]

    def test_filter_by_action_type(self):
        m = self._populated()
        res = m.query(MemoryQuery(action_type="EXPEDITE"))
        assert [r.event_id for r in res] == ["EVT-0", "EVT-3"]

    def test_filter_by_final_route(self):
        m = self._populated()
        res = m.query(MemoryQuery(final_route="AUTO_EXECUTE"))
        assert [r.event_id for r in res] == ["EVT-0", "EVT-1"]

    def test_combined_filters(self):
        m = self._populated()
        res = m.query(MemoryQuery(
            event_type="CARRIER_DELAY_ESCALATION",
            action_type="EXPEDITE",
            final_route="AUTO_EXECUTE",
        ))
        assert [r.event_id for r in res] == ["EVT-0"]

    def test_recent_n_returns_tail(self):
        m = self._populated()
        res = m.query(MemoryQuery(event_type="CARRIER_DELAY_ESCALATION", recent_n=2))
        assert [r.event_id for r in res] == ["EVT-1", "EVT-3"]

    def test_recent_n_zero_returns_empty(self):
        m = self._populated()
        assert m.query(MemoryQuery(recent_n=0)) == []


class TestSummary:
    def test_empty_summary_is_valid_and_cold_start(self):
        m = EpisodicMemory()
        s = m.summarize(MemoryQuery(), threshold=3)
        assert s.matched_records == 0
        assert s.cold_start is True
        assert s.auto_execute_success_rate is None
        assert s.sla_preservation_rate is None
        assert s.avg_cost is None
        assert s.action_type_distribution == {}
