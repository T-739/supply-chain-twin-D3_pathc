"""B3 Slice 2B: EpisodicMemory append-only rule preserved.

Pins:

  - the loader returns a **fresh** ``EpisodicMemory`` — not a
    reference to a caller-supplied one, and not a cached
    instance;
  - resolver-returned lists are not mutated in place by the
    loader;
  - resolver-returned ``MemoryRecord`` field values are
    unchanged post-load (no accidental mutation);
  - a pre-existing ``EpisodicMemory`` object constructed
    separately is not mutated by a subsequent loader call.
"""

from __future__ import annotations

import copy
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
    *, sid: str, ts: str, eid: str, cost: float = 100.0,
) -> MemoryRecord:
    return MemoryRecord(
        event_id=eid,
        event_type="CARRIER_DELAY_ESCALATION",
        event_timestamp=ts,
        action_taken="EXPEDITE",
        execution_status="executed",
        final_route="AUTO_EXECUTE",
        cost_incurred=cost,
        sla_preserved=True,
        risk_level="LOW",
        session_id=sid,
    )


def test_loader_returns_fresh_episodic_memory():
    cfg = CumulativeMemoryConfig(prior_session_refs=("a",))

    def resolver(_ref: str) -> list[MemoryRecord]:
        return [_rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1")]

    a = load_cumulative_memory(cfg, source_resolver=resolver)
    b = load_cumulative_memory(cfg, source_resolver=resolver)
    assert isinstance(a, EpisodicMemory) and isinstance(b, EpisodicMemory)
    assert a is not b


def test_resolver_returned_list_is_not_mutated_in_place():
    cfg = CumulativeMemoryConfig(prior_session_refs=("a",))
    returned_list = [
        _rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1"),
        _rec(sid="S1", ts="2026-01-01T11:00:00+00:00", eid="E2"),
    ]
    before = [r.model_dump() for r in returned_list]

    def resolver(_ref: str) -> list[MemoryRecord]:
        return returned_list

    load_cumulative_memory(cfg, source_resolver=resolver)

    after = [r.model_dump() for r in returned_list]
    assert before == after
    # length unchanged
    assert len(returned_list) == 2


def test_resolver_returned_record_field_values_unchanged():
    cfg = CumulativeMemoryConfig(prior_session_refs=("a",))
    row = _rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1")
    snapshot_before = row.model_dump()

    def resolver(_ref: str) -> list[MemoryRecord]:
        return [row]

    load_cumulative_memory(cfg, source_resolver=resolver)

    assert row.model_dump() == snapshot_before


def test_preexisting_episodic_memory_unchanged_by_loader_call():
    # Build a standalone EpisodicMemory the caller already owns.
    standalone = EpisodicMemory(
        records=[
            _rec(sid="S0", ts="2025-12-31T10:00:00+00:00", eid="old"),
        ],
    )
    standalone_snapshot_before = standalone.snapshot()

    cfg = CumulativeMemoryConfig(prior_session_refs=("a",))

    def resolver(_ref: str) -> list[MemoryRecord]:
        return [_rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1")]

    loader_result = load_cumulative_memory(cfg, source_resolver=resolver)

    # Loader returned a distinct memory; the caller's standalone
    # memory is untouched.
    assert loader_result is not standalone
    assert standalone.snapshot() == standalone_snapshot_before


def test_loader_output_decoupled_from_caller_row_mutations():
    """Slice 2B.5 alias-safety pin: mutating the caller's original
    ``MemoryRecord`` after load must NOT mutate the returned
    ``EpisodicMemory``'s view of the row. The loader now takes a
    defensive ``model_copy()`` of every kept row; this test pins
    that the copy actually isolates the two object graphs."""
    cfg = CumulativeMemoryConfig(prior_session_refs=("a",))
    row = _rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1")
    snapshot_before = row.model_dump()

    def resolver(_ref: str) -> list[MemoryRecord]:
        return [row]

    mem = load_cumulative_memory(cfg, source_resolver=resolver)

    # Mutate the caller's original row (MemoryRecord is
    # frozen=False in its pydantic config). Using setattr so the
    # assignment doesn't trip mypy inside the test; runtime
    # behavior is what matters.
    object.__setattr__(row, "risk_level", "HIGH")

    # Caller's row reflects the mutation.
    assert row.risk_level == "HIGH"
    # Loaded memory does NOT — the defensive copy held its own
    # attribute storage.
    loaded = mem.records()[0]
    assert loaded.risk_level == "LOW"
    # Full snapshot equals the pre-mutation state.
    assert loaded.model_dump() == snapshot_before


def test_loader_output_identity_distinct_from_caller_rows():
    """Slice 2B.5 alias-safety pin: kept rows in the returned
    ``EpisodicMemory`` are fresh instances, not references to the
    caller's originals."""
    cfg = CumulativeMemoryConfig(prior_session_refs=("a",))
    rows = [
        _rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1"),
        _rec(sid="S1", ts="2026-01-01T11:00:00+00:00", eid="E2"),
    ]

    def resolver(_ref: str) -> list[MemoryRecord]:
        return list(rows)

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    caller_ids = {id(r) for r in rows}
    loaded_ids = {id(r) for r in mem.records()}
    assert caller_ids.isdisjoint(loaded_ids), (
        "loaded memory rows share object identity with caller's "
        "originals — alias-safety hardening regressed"
    )


def test_loader_result_memory_does_not_share_internal_list_with_resolver_return():
    cfg = CumulativeMemoryConfig(prior_session_refs=("a",))
    returned_list = [_rec(sid="S1", ts="2026-01-01T10:00:00+00:00", eid="E1")]

    def resolver(_ref: str) -> list[MemoryRecord]:
        return returned_list

    mem = load_cumulative_memory(cfg, source_resolver=resolver)

    # Mutating the caller's original list post-load must not affect
    # the returned memory's view of the world. (This is a structural
    # test; it exercises the EpisodicMemory constructor's defensive
    # append semantics plus the loader's use of a fresh dict.)
    extra = _rec(sid="S2", ts="2026-02-02T10:00:00+00:00", eid="extra")
    returned_list.append(extra)

    observed_event_ids = [r.event_id for r in mem.records()]
    assert "extra" not in observed_event_ids
