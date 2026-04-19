"""learning/memory_summarizer.py — Path C Phase 1 pure summarizer.

Pure functions: ``(records, MemoryQuery, threshold) -> MemorySummary``.
No I/O, no random input, no wall-clock, no mutation.

Threshold ownership note (Roadmap §1.D, owner point v2.1-D):
    The canonical owner of ``min_records_for_shift`` is
    ``AdaptivePolicyGateConfig`` (Phase 2). In Phase 1 there is no
    consumer, so callers pass the placeholder default of 3. This module
    stores no threshold constant of its own.

Rounding rule (Roadmap §1.D):
    MemorySummary numeric fields are computed in full Python float
    precision. Rounding is applied only at the serialization boundary
    by the reporting layer (Phase 3). This module therefore does NOT
    round — it returns raw floats.
"""

from __future__ import annotations

from typing import Optional

from learning.memory_schema import MemoryQuery, MemoryRecord, MemorySummary


_AUTO_SUCCESS_STATUSES = ("executed", "executed_via_demo_override")


def query_signature(query: MemoryQuery) -> str:
    """Canonical, deterministic string form of a MemoryQuery.

    Excludes ``schema_version`` — the signature describes the *logical*
    query, not its schema version. Keys are sorted so the signature is
    stable across Python hash seeds.
    """
    payload = query.model_dump(exclude={"schema_version"})
    parts = [f"{k}={payload[k]!r}" for k in sorted(payload.keys())]
    return "MemoryQuery(" + ",".join(parts) + ")"


def summarize_records(
    records: list[MemoryRecord],
    query: MemoryQuery,
    *,
    threshold: int,
) -> MemorySummary:
    """Summarize a list of MemoryRecord into a MemorySummary.

    Inputs are *already filtered* by the caller (typically
    ``EpisodicMemory.query``). This function does not re-filter.
    """
    threshold = int(threshold)
    matched_records = len(records)
    cold_start = matched_records < threshold

    # auto_execute_success_rate: of rows with final_route=AUTO_EXECUTE,
    # fraction with a successful execution_status.
    auto_rows = [r for r in records if r.final_route == "AUTO_EXECUTE"]
    if auto_rows:
        ok = sum(1 for r in auto_rows if r.execution_status in _AUTO_SUCCESS_STATUSES)
        auto_execute_success_rate: Optional[float] = ok / len(auto_rows)
    else:
        auto_execute_success_rate = None

    # sla_preservation_rate: fraction of rows where sla_preserved is True,
    # over rows where sla_preserved is not None. None-denominator → None.
    sla_rows = [r for r in records if r.sla_preserved is not None]
    if sla_rows:
        ok = sum(1 for r in sla_rows if r.sla_preserved is True)
        sla_preservation_rate: Optional[float] = ok / len(sla_rows)
    else:
        sla_preservation_rate = None

    # action_type_distribution: deterministic sorted dict.
    dist: dict[str, int] = {}
    for r in records:
        key = r.action_taken if r.action_taken is not None else "NONE"
        dist[key] = dist.get(key, 0) + 1
    dist_sorted = {k: dist[k] for k in sorted(dist)}

    # avg_cost over rows with non-None cost_incurred.
    cost_rows = [r for r in records if r.cost_incurred is not None]
    if cost_rows:
        avg_cost: Optional[float] = sum(float(r.cost_incurred) for r in cost_rows) / len(cost_rows)
    else:
        avg_cost = None

    return MemorySummary(
        matched_records=matched_records,
        cold_start=cold_start,
        auto_execute_success_rate=auto_execute_success_rate,
        sla_preservation_rate=sla_preservation_rate,
        action_type_distribution=dist_sorted,
        avg_cost=avg_cost,
        query_signature=query_signature(query),
    )
