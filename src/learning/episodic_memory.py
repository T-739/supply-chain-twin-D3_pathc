"""learning/episodic_memory.py — Path C Phase 1 append-only memory core.

This module provides the EpisodicMemory substrate. Memory is:
  - append-only (no delete / update / replace)
  - deterministic: observable order is always
    ``sorted(records, key=(event_timestamp, event_id))``
  - pure in-process state; persistence is the caller's concern (the
    Phase 1 JSONL store lives in ``outcome_persistence/jsonl_store.py``).

Phase 1 end-state: memory is populated but NOT consumed. No code path
in Phase 1 reads a MemorySummary and branches on it. The learning
consumer (adaptive policy gate) arrives in Phase 2.

This module:
  - does NOT import evaluation.py or action_code_mapper.py
  - does NOT read data/cases/*.json
  - does NOT use datetime.now / utcnow / time.time / uuid.uuid4
"""

from __future__ import annotations

from typing import Optional

from learning.memory_schema import MemoryQuery, MemoryRecord, MemorySummary
from learning.memory_summarizer import summarize_records


class EpisodicMemory:
    """Append-only, deterministic in-memory record store."""

    def __init__(self, records: Optional[list[MemoryRecord]] = None) -> None:
        self._records: list[MemoryRecord] = []
        if records:
            for r in records:
                self.append(r)

    # ------------------------------------------------------------------
    # Append (only mutation surface)
    # ------------------------------------------------------------------

    def append(self, record: MemoryRecord) -> None:
        if not isinstance(record, MemoryRecord):
            raise TypeError(
                f"expected MemoryRecord, got {type(record).__name__}"
            )
        self._records.append(record)

    def __len__(self) -> int:
        return len(self._records)

    # ------------------------------------------------------------------
    # Read / query / snapshot
    # ------------------------------------------------------------------

    def _canonical_order(self) -> list[MemoryRecord]:
        """Records in deterministic observable order: (event_timestamp, event_id)."""
        return sorted(
            self._records,
            key=lambda r: (r.event_timestamp, r.event_id),
        )

    def records(self) -> list[MemoryRecord]:
        """A copy of the canonical-order records (live objects; do not mutate)."""
        return list(self._canonical_order())

    def query(self, q: MemoryQuery) -> list[MemoryRecord]:
        """Return records matching q. Deterministic order.

        Matching rules:
          - event_type filter: r.event_type == q.event_type
          - action_type filter: r.action_taken == q.action_type
          - final_route filter: r.final_route == q.final_route
        None filter values act as wildcards.

        If q.recent_n is set, the *last* N rows of the filtered list (in
        canonical order) are returned. Otherwise all filtered rows are
        returned.
        """
        matched: list[MemoryRecord] = []
        for r in self._canonical_order():
            if q.event_type is not None and r.event_type != q.event_type:
                continue
            if q.action_type is not None and r.action_taken != q.action_type:
                continue
            if q.final_route is not None and r.final_route != q.final_route:
                continue
            matched.append(r)

        if q.recent_n is not None:
            n = int(q.recent_n)
            if n <= 0:
                return []
            matched = matched[-n:]
        return matched

    def summarize(
        self,
        q: MemoryQuery,
        *,
        threshold: int,
    ) -> MemorySummary:
        """Query, then summarize. Threshold is supplied by caller."""
        return summarize_records(self.query(q), q, threshold=threshold)

    def snapshot(self) -> dict:
        """Deterministic plain-dict snapshot of the entire memory.

        Shape::

            {"records": [...], "schema_version": "1.0"}

        The ``records`` list is in canonical order and each element is
        a ``MemoryRecord.model_dump()``.
        """
        return {
            "records": [r.model_dump() for r in self._canonical_order()],
            "schema_version": "1.0",
        }
