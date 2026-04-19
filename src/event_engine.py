"""
event_engine.py — D3-Demo Phase 2: Deterministic event generation.

Generates ordered EventPayload sequences for the D3 event loop.
All output is deterministic by default — no randomness unless an
explicit seed is provided.  Events target the 2x2x2x2 baseline
network entity IDs (SUP_1/2, WH_1/2, CR_1/2, CZ_1/2).

This module generates events only.  It does NOT:
  - Patch TwinState (event_state_mapper does that)
  - Execute actions (Phase 3 adapters do that)
  - Read oracle cases or evaluation truth
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from event_schema import AffectedEntityRef, EventPayload, EventSeverity, EventType


# ---------------------------------------------------------------------------
# Single-event factory helpers
# ---------------------------------------------------------------------------


def make_carrier_delay_escalation(
    *,
    event_id: str,
    carrier_id: str,
    delta_hours: float,
    severity: EventSeverity,
    timestamp: datetime,
) -> EventPayload:
    """Create a CARRIER_DELAY_ESCALATION event."""
    return EventPayload(
        event_id=event_id,
        event_type=EventType.CARRIER_DELAY_ESCALATION,
        severity=severity,
        affected_entities=[
            AffectedEntityRef(
                entity_type="carrier",
                entity_id=carrier_id,
                field="transit_time_hours",
            ),
        ],
        timestamp=timestamp,
        parameters={"delta_hours": delta_hours},
    )


def make_weather_worsening(
    *,
    event_id: str,
    delta_eta_hours: float,
    severity: EventSeverity,
    timestamp: datetime,
) -> EventPayload:
    """Create a WEATHER_WORSENING event."""
    return EventPayload(
        event_id=event_id,
        event_type=EventType.WEATHER_WORSENING,
        severity=severity,
        affected_entities=[
            AffectedEntityRef(entity_type="twin", entity_id="planned_eta"),
        ],
        timestamp=timestamp,
        parameters={"delta_eta_hours": delta_eta_hours},
    )


def make_demand_spike(
    *,
    event_id: str,
    zone_id: str,
    delta_units: int,
    severity: EventSeverity,
    timestamp: datetime,
) -> EventPayload:
    """Create a DEMAND_SPIKE event."""
    return EventPayload(
        event_id=event_id,
        event_type=EventType.DEMAND_SPIKE,
        severity=severity,
        affected_entities=[
            AffectedEntityRef(
                entity_type="customer_zone",
                entity_id=zone_id,
                field="demand_units",
            ),
        ],
        timestamp=timestamp,
        parameters={"delta_units": delta_units},
    )


def make_inventory_discrepancy(
    *,
    event_id: str,
    warehouse_id: str,
    delta_units: int,
    severity: EventSeverity,
    timestamp: datetime,
) -> EventPayload:
    """Create an INVENTORY_DISCREPANCY event."""
    return EventPayload(
        event_id=event_id,
        event_type=EventType.INVENTORY_DISCREPANCY,
        severity=severity,
        affected_entities=[
            AffectedEntityRef(
                entity_type="warehouse",
                entity_id=warehouse_id,
                field="current_inventory",
            ),
        ],
        timestamp=timestamp,
        parameters={"delta_units": delta_units},
    )


def make_customer_cancellation(
    *,
    event_id: str,
    zone_id: str,
    delta_units: int,
    severity: EventSeverity,
    timestamp: datetime,
) -> EventPayload:
    """Create a CUSTOMER_CANCELLATION event."""
    return EventPayload(
        event_id=event_id,
        event_type=EventType.CUSTOMER_CANCELLATION,
        severity=severity,
        affected_entities=[
            AffectedEntityRef(
                entity_type="customer_zone",
                entity_id=zone_id,
                field="demand_units",
            ),
        ],
        timestamp=timestamp,
        parameters={"delta_units": delta_units},
    )


def make_compliance_hold(
    *,
    event_id: str,
    entity_type: str,
    entity_id: str,
    severity: EventSeverity,
    timestamp: datetime,
) -> EventPayload:
    """Create a COMPLIANCE_HOLD event."""
    return EventPayload(
        event_id=event_id,
        event_type=EventType.COMPLIANCE_HOLD,
        severity=severity,
        affected_entities=[
            AffectedEntityRef(entity_type=entity_type, entity_id=entity_id),
        ],
        timestamp=timestamp,
        parameters={},
    )


# ---------------------------------------------------------------------------
# Demo event stream — deterministic, targeting baseline 2x2x2x2 network
# ---------------------------------------------------------------------------

_BASELINE_T0 = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)


def generate_demo_event_stream(
    *,
    t0: datetime = _BASELINE_T0,
    interval_minutes: int = 30,
) -> list[EventPayload]:
    """Generate a fixed, deterministic demo event stream.

    Returns 6 events (one per event type), targeting baseline entity IDs.
    Timestamps are strictly increasing, spaced by ``interval_minutes``.

    Parameters
    ----------
    t0 : datetime
        Base timestamp for the first event.  Default: 2026-04-01T10:00:00Z.
    interval_minutes : int
        Minutes between consecutive events.  Default: 30.

    Returns
    -------
    list[EventPayload]
        Ordered event stream.  Deterministic — same inputs always produce
        the same output.
    """
    delta = timedelta(minutes=interval_minutes)

    return [
        # Event 1: Carrier delay escalation on CR_1 (LOW severity)
        make_carrier_delay_escalation(
            event_id="EVT-D01",
            carrier_id="CR_1",
            delta_hours=6.0,
            severity=EventSeverity.LOW,
            timestamp=t0,
        ),
        # Event 2: Weather worsening adds ETA pressure (MEDIUM severity)
        make_weather_worsening(
            event_id="EVT-D02",
            delta_eta_hours=4.0,
            severity=EventSeverity.MEDIUM,
            timestamp=t0 + delta,
        ),
        # Event 3: Demand spike on CZ_1 (HIGH severity)
        make_demand_spike(
            event_id="EVT-D03",
            zone_id="CZ_1",
            delta_units=5,
            severity=EventSeverity.HIGH,
            timestamp=t0 + delta * 2,
        ),
        # Event 4: Inventory discrepancy at WH_1 (MEDIUM severity)
        make_inventory_discrepancy(
            event_id="EVT-D04",
            warehouse_id="WH_1",
            delta_units=-15,
            severity=EventSeverity.MEDIUM,
            timestamp=t0 + delta * 3,
        ),
        # Event 5: Customer cancellation on CZ_2 (LOW severity)
        make_customer_cancellation(
            event_id="EVT-D05",
            zone_id="CZ_2",
            delta_units=-2,
            severity=EventSeverity.LOW,
            timestamp=t0 + delta * 4,
        ),
        # Event 6: Compliance hold on CR_2 (HIGH severity)
        make_compliance_hold(
            event_id="EVT-D06",
            entity_type="carrier",
            entity_id="CR_2",
            severity=EventSeverity.HIGH,
            timestamp=t0 + delta * 5,
        ),
    ]
