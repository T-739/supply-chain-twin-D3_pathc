"""B3 Slice 2B: loader purity & determinism.

Pins:

  - same (config, resolver) → same ``EpisodicMemory.snapshot()``
    output on repeated same-process invocations;
  - resolver called exactly once per ref, in declared order;
  - resolver NOT called for refs outside the iteration range
    (no hidden retries, no pre-fetch);
  - empty config + any resolver → empty memory, resolver never
    invoked;
  - loader returns a new ``EpisodicMemory`` object, not a
    reference to any caller-supplied structure.

No filesystem I/O, no subprocess stress — those land in Slice 2B.5.
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
from learning.episodic_memory import EpisodicMemory  # noqa: E402
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


def test_empty_refs_returns_empty_memory_without_calling_resolver():
    cfg = CumulativeMemoryConfig()
    calls: list[str] = []

    def resolver(ref: str) -> list[MemoryRecord]:
        calls.append(ref)
        return []

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert isinstance(mem, EpisodicMemory)
    assert len(mem) == 0
    assert calls == []


def test_resolver_called_once_per_ref_in_declared_order():
    cfg = CumulativeMemoryConfig(
        prior_session_refs=("sess_A", "sess_B", "sess_C"),
    )

    calls: list[str] = []
    rows_by_ref = {
        "sess_A": [_rec(sid="A", ts="2026-01-01T10:00:00+00:00", eid="EA1")],
        "sess_B": [_rec(sid="B", ts="2026-01-02T10:00:00+00:00", eid="EB1")],
        "sess_C": [],
    }

    def resolver(ref: str) -> list[MemoryRecord]:
        calls.append(ref)
        return list(rows_by_ref[ref])

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert calls == ["sess_A", "sess_B", "sess_C"]
    assert len(mem) == 2


def test_repeated_invocations_same_snapshot():
    cfg = CumulativeMemoryConfig(prior_session_refs=("s1", "s2"))
    rows_by_ref = {
        "s1": [_rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="e0")],
        "s2": [
            _rec(sid="S2", ts="2026-01-01T10:30:00+00:00", eid="e1"),
            _rec(sid="S2", ts="2026-01-01T11:00:00+00:00", eid="e2"),
        ],
    }

    def resolver(ref: str) -> list[MemoryRecord]:
        return list(rows_by_ref[ref])

    snap_1 = load_cumulative_memory(cfg, source_resolver=resolver).snapshot()
    snap_2 = load_cumulative_memory(cfg, source_resolver=resolver).snapshot()
    snap_3 = load_cumulative_memory(cfg, source_resolver=resolver).snapshot()
    assert snap_1 == snap_2 == snap_3


def test_loader_returns_a_new_episodic_memory_instance_each_call():
    cfg = CumulativeMemoryConfig(prior_session_refs=("s1",))
    rows = [_rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="e0")]

    def resolver(_ref: str) -> list[MemoryRecord]:
        return list(rows)

    a = load_cumulative_memory(cfg, source_resolver=resolver)
    b = load_cumulative_memory(cfg, source_resolver=resolver)
    assert a is not b
    assert a.snapshot() == b.snapshot()


def test_loader_does_not_consult_anything_outside_resolver():
    """Pure-function proof: a resolver that returns an empty list
    on every ref produces an empty memory, regardless of how many
    refs are declared. The loader does not fall back to any global
    state, filesystem, or cached prior sessions."""
    cfg = CumulativeMemoryConfig(
        prior_session_refs=("a", "b", "c", "d"),
    )

    def resolver(_ref: str) -> list[MemoryRecord]:
        return []

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert len(mem) == 0
