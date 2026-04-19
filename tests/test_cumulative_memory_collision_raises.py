"""B3 Slice 2B: dedupe collision raises.

Pins:

  - same ``(session_id, event_timestamp, event_id)`` triple with
    byte-non-equal row content raises
    ``CumulativeMemoryCollisionError``;
  - the error carries enough structural context (the triple) to
    diagnose the source;
  - a resolver returning a non-list or a non-``MemoryRecord``
    entry raises ``TypeError`` (clear, deterministic error
    surfaces rather than silently accepting bad input).
"""

from __future__ import annotations

import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from learning.cumulative_memory import (  # noqa: E402
    CumulativeMemoryCollisionError,
    CumulativeMemoryConfig,
    load_cumulative_memory,
)
from learning.memory_schema import MemoryRecord  # noqa: E402


def _rec(
    *, sid: str, ts: str, eid: str, action: str = "EXPEDITE",
    cost: float = 100.0,
) -> MemoryRecord:
    return MemoryRecord(
        event_id=eid,
        event_type="CARRIER_DELAY_ESCALATION",
        event_timestamp=ts,
        action_taken=action,
        execution_status="executed",
        final_route="AUTO_EXECUTE",
        cost_incurred=cost,
        sla_preserved=True,
        risk_level="LOW",
        session_id=sid,
    )


def test_same_triple_different_content_raises():
    ts = "2026-01-01T10:00:00+00:00"
    a = _rec(sid="S1", ts=ts, eid="E1", cost=100.0)
    b = _rec(sid="S1", ts=ts, eid="E1", cost=999.0)  # different cost
    cfg = CumulativeMemoryConfig(prior_session_refs=("ra", "rb"))

    def resolver(ref: str) -> list[MemoryRecord]:
        return [a] if ref == "ra" else [b]

    with pytest.raises(CumulativeMemoryCollisionError) as excinfo:
        load_cumulative_memory(cfg, source_resolver=resolver)
    msg = str(excinfo.value)
    assert "S1" in msg
    assert "E1" in msg
    assert ts in msg


def test_same_triple_different_action_raises():
    ts = "2026-01-01T10:00:00+00:00"
    a = _rec(sid="S1", ts=ts, eid="E1", action="EXPEDITE")
    b = _rec(sid="S1", ts=ts, eid="E1", action="TRANSFER")
    cfg = CumulativeMemoryConfig(prior_session_refs=("r",))

    def resolver(_ref: str) -> list[MemoryRecord]:
        return [a, b]

    with pytest.raises(CumulativeMemoryCollisionError):
        load_cumulative_memory(cfg, source_resolver=resolver)


def test_collision_error_is_value_error_subclass():
    # Sanity pin inherited from Slice 2A — runtime raise goes
    # through the same subclass so callers catching ValueError
    # still catch it.
    assert issubclass(CumulativeMemoryCollisionError, ValueError)


def test_resolver_returning_non_list_raises_type_error():
    cfg = CumulativeMemoryConfig(prior_session_refs=("r",))

    def resolver(_ref: str) -> list[MemoryRecord]:
        # Tuples are NOT lists; reject clearly rather than
        # silently iterating.
        return ( _rec(sid="S", ts="2026-01-01T10:00:00+00:00", eid="e"),)  # type: ignore[return-value]

    with pytest.raises(TypeError):
        load_cumulative_memory(cfg, source_resolver=resolver)


def test_resolver_returning_non_memory_record_raises_type_error():
    cfg = CumulativeMemoryConfig(prior_session_refs=("r",))

    def resolver(_ref: str) -> list[MemoryRecord]:
        return [
            _rec(sid="S", ts="2026-01-01T10:00:00+00:00", eid="e"),
            {"event_id": "not-a-record"},  # type: ignore[list-item]
        ]

    with pytest.raises(TypeError):
        load_cumulative_memory(cfg, source_resolver=resolver)


def test_duplicate_equal_rows_do_not_raise():
    # Regression-pin: only NON-EQUAL same-triple rows raise.
    # Equal duplicates must silently drop without error.
    row = _rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1")
    cfg = CumulativeMemoryConfig(prior_session_refs=("ra", "rb"))

    def resolver(_ref: str) -> list[MemoryRecord]:
        return [row]

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert len(mem) == 1
