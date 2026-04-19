"""B3 Slice 2B: dedupe determinism.

Pins:

  - duplicate-equal rows (same triple, byte-equal content)
    dedupe to a single kept row;
  - non-duplicated rows all survive;
  - rows from distinct sessions with the same
    ``(event_timestamp, event_id)`` but different ``session_id``
    are preserved (cross-session union).
  - row ordering is the canonical EpisodicMemory order
    ``(event_timestamp, event_id)`` — loader does NOT invent a
    new ordering;
  - ordering is stable across swapped resolver-returned
    duplicate lists.
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


def test_duplicate_equal_rows_deduped_to_one():
    row = _rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1")
    # Same ref listed twice; same row content both times.
    cfg = CumulativeMemoryConfig(prior_session_refs=("s1", "s1"))

    def resolver(_ref: str) -> list[MemoryRecord]:
        return [row]

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert len(mem) == 1
    assert mem.records()[0].event_id == "E1"


def test_all_non_duplicated_rows_preserved():
    rows_a = [
        _rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1"),
        _rec(sid="S1", ts="2026-01-01T11:00:00+00:00", eid="E2"),
    ]
    rows_b = [
        _rec(sid="S2", ts="2026-01-02T10:00:00+00:00", eid="E3"),
    ]
    cfg = CumulativeMemoryConfig(prior_session_refs=("a", "b"))

    def resolver(ref: str) -> list[MemoryRecord]:
        return list(rows_a if ref == "a" else rows_b)

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert [r.event_id for r in mem.records()] == ["E1", "E2", "E3"]


def test_different_session_same_event_id_preserved():
    # Same (event_timestamp, event_id) but distinct session_id —
    # the triple key includes session_id, so these are two
    # different records and both must survive.
    ts = "2026-01-01T10:00:00+00:00"
    rows_a = [_rec(sid="S1", ts=ts, eid="E1")]
    rows_b = [_rec(sid="S2", ts=ts, eid="E1")]
    cfg = CumulativeMemoryConfig(prior_session_refs=("a", "b"))

    def resolver(ref: str) -> list[MemoryRecord]:
        return list(rows_a if ref == "a" else rows_b)

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert len(mem) == 2
    sids = sorted(r.session_id for r in mem.records())
    assert sids == ["S1", "S2"]


def test_canonical_ordering_on_output():
    # Out-of-order inputs; EpisodicMemory's canonical sort by
    # (event_timestamp, event_id) must be what the loader
    # observably produces.
    rows = [
        _rec(sid="S1", ts="2026-01-03T10:00:00+00:00", eid="E3"),
        _rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1"),
        _rec(sid="S1", ts="2026-01-02T10:00:00+00:00", eid="E2"),
    ]
    cfg = CumulativeMemoryConfig(prior_session_refs=("a",))

    def resolver(_ref: str) -> list[MemoryRecord]:
        return list(rows)

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert [r.event_id for r in mem.records()] == ["E1", "E2", "E3"]


def test_dedupe_order_stable_regardless_of_resolver_duplicate_placement():
    # Shared row duplicated in three different resolver-return
    # positions; all three invocations produce equal snapshots
    # because dedupe-union is associative / commutative on equal
    # rows.
    shared = _rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1")
    other = _rec(sid="S1", ts="2026-01-02T10:00:00+00:00", eid="E2")
    cfg = CumulativeMemoryConfig(prior_session_refs=("a", "b", "c"))

    def resolver_dup_first(ref: str) -> list[MemoryRecord]:
        return {
            "a": [shared, other],
            "b": [shared],
            "c": [],
        }[ref]

    def resolver_dup_middle(ref: str) -> list[MemoryRecord]:
        return {
            "a": [other],
            "b": [shared, shared],
            "c": [],
        }[ref]

    def resolver_dup_last(ref: str) -> list[MemoryRecord]:
        return {
            "a": [other],
            "b": [],
            "c": [shared, shared, shared],
        }[ref]

    s1 = load_cumulative_memory(cfg, source_resolver=resolver_dup_first).snapshot()
    s2 = load_cumulative_memory(cfg, source_resolver=resolver_dup_middle).snapshot()
    s3 = load_cumulative_memory(cfg, source_resolver=resolver_dup_last).snapshot()
    assert s1 == s2 == s3


def test_empty_resolver_returns_means_zero_rows():
    cfg = CumulativeMemoryConfig(prior_session_refs=("a",))

    def resolver(_ref: str) -> list[MemoryRecord]:
        return []

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert len(mem) == 0
