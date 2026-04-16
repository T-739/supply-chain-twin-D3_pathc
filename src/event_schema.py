"""
event_schema.py — D3-Demo Phase 0: Event contract definitions.

Defines the minimal event payload schema for the D3 event-driven loop.
This file defines contracts only — no event engine logic, no patch DSL,
no runtime behavior.

Phase 0 deliverable. Do not add event generation or processing logic here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    """Six canonical disruption event types for D3-Demo."""

    CARRIER_DELAY_ESCALATION = "CARRIER_DELAY_ESCALATION"
    WEATHER_WORSENING = "WEATHER_WORSENING"
    DEMAND_SPIKE = "DEMAND_SPIKE"
    INVENTORY_DISCREPANCY = "INVENTORY_DISCREPANCY"
    CUSTOMER_CANCELLATION = "CUSTOMER_CANCELLATION"
    COMPLIANCE_HOLD = "COMPLIANCE_HOLD"


class EventSeverity(str, Enum):
    """Event severity levels — mirrors risk taxonomy but belongs to event layer."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ---------------------------------------------------------------------------
# Supporting models
# ---------------------------------------------------------------------------


class AffectedEntityRef(BaseModel):
    """Reference to a TwinState entity affected by an event.

    entity_type: e.g. "carrier", "warehouse", "supplier", "customer_zone"
    entity_id:   e.g. "carrier_a", "wh_1"
    field:       optional — specific field affected (e.g. "transit_time_hours")
    """

    model_config = ConfigDict(frozen=True)

    entity_type: str
    entity_id: str
    field: str | None = None

    @field_validator("entity_type")
    @classmethod
    def entity_type_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("entity_type must be non-empty")
        return v

    @field_validator("entity_id")
    @classmethod
    def entity_id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("entity_id must be non-empty")
        return v


# ---------------------------------------------------------------------------
# EventPayload — the core event contract
# ---------------------------------------------------------------------------


class EventPayload(BaseModel):
    """Immutable event record emitted by the Event Engine.

    parameters is a free dict — no per-event-type discriminator in Phase 0.
    Future phases may add typed sub-schemas keyed by event_type.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: EventType
    severity: EventSeverity
    affected_entities: list[AffectedEntityRef]
    timestamp: datetime
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id")
    @classmethod
    def event_id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("event_id must be non-empty")
        return v

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError(
                "timestamp must be timezone-aware with a resolvable utcoffset "
                "(e.g. use datetime.timezone.utc)"
            )
        return v
