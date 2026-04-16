"""
outcome_schema.py — D3-Demo Phase 0: Execution outcome contract.

Defines the runtime outcome schema for simulated action execution.
This is a runtime/product artifact — NOT oracle truth, NOT evaluation truth.

Hard boundary:
  - action_taken uses OPERATIONAL layer only (EXPEDITE/TRANSFER/COMPENSATE/NO_ACTION).
  - AI/ALT1/ALT2 (evaluation layer) are explicitly rejected.
  - APPROVE/VERIFY/OVERRIDE (supervision layer) are explicitly rejected.
  - cost_incurred is a runtime deterministic outcome, not oracle cost.

Phase 0 deliverable. Do not add outcome store or execution adapter logic here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Allowed action types — operational layer only
# ---------------------------------------------------------------------------

# Explicit allowlist. This is intentionally a module-level constant,
# not imported from twin_state.py, to avoid coupling the outcome contract
# to the TwinState internal enum. The values must stay in sync by convention.
_OPERATIONAL_ACTIONS = frozenset({"EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"})

# Explicitly forbidden tokens from other layers.
_FORBIDDEN_SUPERVISION = frozenset({"APPROVE", "VERIFY", "OVERRIDE"})
_FORBIDDEN_EVALUATION = frozenset({"AI", "ALT1", "ALT2"})


# ---------------------------------------------------------------------------
# ExecutionOutcome
# ---------------------------------------------------------------------------


class ExecutionOutcome(BaseModel):
    """Structured record of a simulated action execution.

    Produced by execution adapters (Phase 3). Stored in the outcome store.
    Never used as evaluation truth — evaluation reads only from oracle case JSONs.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    action_taken: Literal["EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"]
    cost_incurred: float
    sla_impact: dict[str, Any]
    state_delta: dict[str, Any]
    timestamp: datetime
    status: Literal["EXECUTED", "SKIPPED", "REJECTED"] = "EXECUTED"
    notes: str = ""

    @field_validator("event_id")
    @classmethod
    def event_id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("event_id must be non-empty")
        return v

    @field_validator("cost_incurred")
    @classmethod
    def cost_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"cost_incurred must be >= 0, got {v}")
        return v

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(
                "timestamp must be timezone-aware (e.g. use datetime.timezone.utc)"
            )
        return v

    @field_validator("action_taken")
    @classmethod
    def reject_non_operational_actions(cls, v: str) -> str:
        """Hard guard: only operational-layer action types are accepted."""
        if v in _FORBIDDEN_SUPERVISION:
            raise ValueError(
                f"action_taken='{v}' is a supervision-layer identifier. "
                f"Only operational actions are allowed: {sorted(_OPERATIONAL_ACTIONS)}"
            )
        if v in _FORBIDDEN_EVALUATION:
            raise ValueError(
                f"action_taken='{v}' is an evaluation-layer identifier. "
                f"Only operational actions are allowed: {sorted(_OPERATIONAL_ACTIONS)}"
            )
        return v
