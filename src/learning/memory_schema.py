"""memory_schema.py — Path C Phase 0 schema skeletons.

Classes only. No runtime logic, no persistence, no summarizer, no query
execution. This module is part of the Phase 0 contract freeze: the shape
and field set of each class below become v1.0 and are tracked in
PATH_C_SCHEMA_REGISTRY.md.

Runtime behavior (EpisodicMemory, memory_summarizer, JSONL persistence)
lands in Phase 1 and is deliberately NOT implemented here.

This module does NOT:
  - Import evaluation.py or action_code_mapper.py
  - Read or write data/cases/*.json
  - Call datetime.now / utcnow / time.time / uuid.uuid4
  - Mutate any Path B contract
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


_MEMORY_SCHEMA_VERSION = "1.0"


class MemoryRecord(BaseModel):
    """One episodic memory row. Written by Phase 1 EpisodicMemory.append.

    Phase 0 freezes the shape only. No instance is ever constructed inside
    Path B runtime. Field ordering and default rules are defined in
    PATH_C_SCHEMA_REGISTRY.md.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    event_id: str
    event_type: str
    event_timestamp: str
    action_taken: Optional[str] = None
    execution_status: str
    final_route: str
    cost_incurred: Optional[float] = None
    sla_preserved: Optional[bool] = None
    risk_level: str
    session_id: str
    schema_version: str = Field(default=_MEMORY_SCHEMA_VERSION)


class MemoryQuery(BaseModel):
    """Structured, deterministic query against EpisodicMemory.

    Semantics land in Phase 1; Phase 0 freezes the shape.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: Optional[str] = None
    action_type: Optional[str] = None
    final_route: Optional[str] = None
    recent_n: Optional[int] = None
    schema_version: str = Field(default=_MEMORY_SCHEMA_VERSION)


class MemorySummary(BaseModel):
    """Deterministic summary of a MemoryQuery result. Phase 1 populates.

    ``cold_start`` is defined as ``matched_records < threshold``, where the
    threshold is a caller-supplied parameter owned by
    ``AdaptivePolicyGateConfig.min_records_for_shift`` (Phase 2). Phase 0
    only freezes the field set.
    """

    model_config = ConfigDict(extra="forbid")

    matched_records: int = 0
    cold_start: bool = True
    auto_execute_success_rate: Optional[float] = None
    sla_preservation_rate: Optional[float] = None
    action_type_distribution: dict[str, int] = Field(default_factory=dict)
    avg_cost: Optional[float] = None
    query_signature: str = ""
    schema_version: str = Field(default=_MEMORY_SCHEMA_VERSION)
