"""B3 Slice 2B: bounded growth.

Pins:

  - post-dedupe count at exactly ``config.max_records`` is
    accepted;
  - post-dedupe count one above ``config.max_records`` raises
    ``ValueError``;
  - the hard module cap ``MAX_CUMULATIVE_MEMORY_RECORDS`` is
    enforced even when the caller sets ``max_records`` to the
    module cap; exceeding it raises;
  - the dedupe-equal drop is applied **before** cap checking —
    duplicates never push the count toward the cap;
  - error is clean and deterministic (no soft truncation).
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
    MAX_CUMULATIVE_MEMORY_RECORDS,
    load_cumulative_memory,
)
from learning.memory_schema import MemoryRecord  # noqa: E402


def _rec(i: int, *, sid: str = "S") -> MemoryRecord:
    ts = f"2026-01-01T{(i // 60) % 24:02d}:{i % 60:02d}:00+00:00"
    return MemoryRecord(
        event_id=f"E{i:05d}",
        event_type="CARRIER_DELAY_ESCALATION",
        event_timestamp=ts,
        action_taken="EXPEDITE",
        execution_status="executed",
        final_route="AUTO_EXECUTE",
        cost_incurred=100.0 + i,
        sla_preserved=True,
        risk_level="LOW",
        session_id=sid,
    )


def test_at_exactly_config_max_records_is_accepted():
    rows = [_rec(i) for i in range(5)]
    cfg = CumulativeMemoryConfig(
        prior_session_refs=("r",),
        max_records=5,
    )

    def resolver(_ref: str) -> list[MemoryRecord]:
        return list(rows)

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert len(mem) == 5


def test_one_over_config_max_records_raises_value_error():
    rows = [_rec(i) for i in range(6)]
    cfg = CumulativeMemoryConfig(
        prior_session_refs=("r",),
        max_records=5,
    )

    def resolver(_ref: str) -> list[MemoryRecord]:
        return list(rows)

    with pytest.raises(ValueError) as excinfo:
        load_cumulative_memory(cfg, source_resolver=resolver)
    assert "config.max_records" in str(excinfo.value) or "max_records" in str(
        excinfo.value
    )


def test_dedupe_applied_before_cap_check():
    # 6 resolver rows but 3 are dedupe-equal duplicates of the
    # other 3. Post-dedupe count is 3, which fits in cap=3.
    unique = [_rec(i) for i in range(3)]
    rows = unique + list(unique)  # duplicates appear second pass
    cfg = CumulativeMemoryConfig(prior_session_refs=("r",), max_records=3)

    def resolver(_ref: str) -> list[MemoryRecord]:
        return list(rows)

    mem = load_cumulative_memory(cfg, source_resolver=resolver)
    assert len(mem) == 3


def test_module_hard_cap_enforced_even_when_config_asks_for_it():
    # Config asks for the module cap; resolver attempts to
    # return one more than the module cap. This exceeds the
    # module hard cap regardless of config.
    cfg = CumulativeMemoryConfig(
        prior_session_refs=("r",),
        max_records=MAX_CUMULATIVE_MEMORY_RECORDS,
    )
    over_cap_rows = [_rec(i) for i in range(MAX_CUMULATIVE_MEMORY_RECORDS + 1)]

    def resolver(_ref: str) -> list[MemoryRecord]:
        return list(over_cap_rows)

    with pytest.raises(ValueError) as excinfo:
        load_cumulative_memory(cfg, source_resolver=resolver)
    assert "MAX_CUMULATIVE_MEMORY_RECORDS" in str(excinfo.value)


def test_no_soft_truncation():
    # One over cap — no records must appear partially; it's all
    # rows or hard-error. Since the loader raises, there is no
    # returned memory to inspect — we just confirm the raise path.
    rows = [_rec(i) for i in range(4)]
    cfg = CumulativeMemoryConfig(prior_session_refs=("r",), max_records=3)

    def resolver(_ref: str) -> list[MemoryRecord]:
        return list(rows)

    with pytest.raises(ValueError):
        load_cumulative_memory(cfg, source_resolver=resolver)
