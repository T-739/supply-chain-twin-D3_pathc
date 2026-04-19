"""adaptive_schema.py — Path C Phase 0 schema skeletons.

Classes only. No decide_policy_adaptive, no rule registry, no cold-start
logic, no preflight validator. All runtime behavior lives in Phase 2.

Adjustment direction rule (frozen here by field type, enforced by rule
registry in Phase 2): ``adjustment_type`` admits only
UPGRADE_ONE_LEVEL / NO_ADJUSTMENT / COLD_START_FALLBACK. DOWNGRADE_* is
out-of-scope for Path C-min.

This module does NOT:
  - Import evaluation.py or action_code_mapper.py
  - Read or write data/cases/*.json
  - Call datetime.now / utcnow / time.time / uuid.uuid4
  - Mutate governance_output or any Path B contract
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


_ADAPTIVE_SCHEMA_VERSION = "1.0"


AdjustmentType = Literal[
    "UPGRADE_ONE_LEVEL",
    "NO_ADJUSTMENT",
    "COLD_START_FALLBACK",
]

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


class AdaptivePolicyAdjustment(BaseModel):
    """Structured record of one adaptive adjustment attempt.

    Phase 0 freezes the shape; Phase 2 fills it. Explainability is a
    structural contract (owner point 7): ``rule_id``, ``query_signature``
    and ``memory_evidence`` are mandatory carriers, not decorative.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    adjustment_type: AdjustmentType
    pre_adjustment_risk: RiskLevel
    post_adjustment_risk: RiskLevel
    query_signature: str = ""
    memory_evidence: dict = Field(default_factory=dict)
    notes: str = ""
    schema_version: str = Field(default=_ADAPTIVE_SCHEMA_VERSION)


class AdjustmentRuleSpec(BaseModel):
    """Declarative description of one adjustment rule (Phase 2 consumer).

    Phase 0 freezes the shape. The rule function itself is NOT stored
    here; the Phase 2 rule registry maps rule_id -> callable.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    description: str = ""
    applies_to_event_types: list[str] = Field(default_factory=list)
    schema_version: str = Field(default=_ADAPTIVE_SCHEMA_VERSION)
