"""
event_state_mapper.py — D3-Demo Phase 2: Event-to-TwinState mapping.

Pure function: given an EventPayload and a TwinState, returns a deep-copy
patched TwinState and a scenario_context dict suitable for the reasoning
agents.

This module does NOT:
  - Mutate the input twin_state (works on a deep copy)
  - Import evaluation.py or action_code_mapper.py
  - Read from data/cases/*.json
  - Write outcomes or touch the outcome store
  - Extend GovernanceOutput schema (context goes through scenario_context sideband)
"""

from __future__ import annotations

from typing import Any

from event_schema import EventPayload, EventSeverity
from twin_state import TwinState


# ---------------------------------------------------------------------------
# Severity → risk_level mapping (deterministic, 1:1)
# ---------------------------------------------------------------------------

_SEVERITY_TO_RISK: dict[EventSeverity, str] = {
    EventSeverity.LOW: "LOW",
    EventSeverity.MEDIUM: "MEDIUM",
    EventSeverity.HIGH: "HIGH",
}


# ---------------------------------------------------------------------------
# Exception description templates (deterministic, per event type)
# ---------------------------------------------------------------------------

_DESCRIPTION_TEMPLATES: dict[str, str] = {
    "CARRIER_DELAY_ESCALATION": (
        "Carrier delay escalation: {entities} transit time increased by "
        "{delta_hours}h.  Potential SLA impact for downstream customer zones."
    ),
    "WEATHER_WORSENING": (
        "Weather worsening: planned ETA extended by {delta_eta_hours}h.  "
        "Shipment delivery may breach SLA deadline."
    ),
    "DEMAND_SPIKE": (
        "Demand spike: {entities} demand increased by {delta_units} units.  "
        "Inventory and carrier capacity may be insufficient."
    ),
    "INVENTORY_DISCREPANCY": (
        "Inventory discrepancy: {entities} inventory adjusted by "
        "{delta_units} units.  Available stock may be below fulfillment threshold."
    ),
    "CUSTOMER_CANCELLATION": (
        "Customer cancellation: {entities} demand reduced by "
        "{abs_delta_units} units.  Reallocation of capacity may be possible."
    ),
    "COMPLIANCE_HOLD": (
        "Compliance hold: {entities} placed on hold.  "
        "Affected entity is unavailable until hold is lifted."
    ),
}


def _build_exception_description(event: EventPayload) -> str:
    """Generate a short deterministic text description from event data."""
    entities_str = ", ".join(
        f"{ref.entity_type}:{ref.entity_id}" for ref in event.affected_entities
    )
    params = event.parameters
    template = _DESCRIPTION_TEMPLATES.get(event.event_type.value, "")

    return template.format(
        entities=entities_str,
        delta_hours=params.get("delta_hours", "?"),
        delta_eta_hours=params.get("delta_eta_hours", "?"),
        delta_units=params.get("delta_units", "?"),
        abs_delta_units=abs(params.get("delta_units", 0)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def map_event_to_state(
    event: EventPayload,
    twin_state: TwinState,
) -> tuple[TwinState, dict[str, Any]]:
    """Map an event into a patched TwinState copy and a scenario_context.

    This is a **pure function**: the input ``twin_state`` is never modified.
    A deep copy is made and ``apply_event_patch(event)`` is called on the copy.

    Parameters
    ----------
    event : EventPayload
        Immutable event record.
    twin_state : TwinState
        Current live twin state.  NOT modified.

    Returns
    -------
    tuple[TwinState, dict[str, Any]]
        (patched_twin, scenario_context)

    Raises
    ------
    ValueError / KeyError
        Propagated from ``apply_event_patch`` if the patch is invalid.
    """
    # Deep copy — input twin_state is never mutated
    patched = twin_state.model_copy(deep=True)
    patched.apply_event_patch(event)

    # Build scenario_context for reasoning agents
    scenario_context: dict[str, Any] = {
        "scenario_type": "event_runtime",
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "risk_level": _SEVERITY_TO_RISK.get(event.severity, "MEDIUM"),
        "exception_description": _build_exception_description(event),
        "affected_entities": [
            {
                "entity_type": ref.entity_type,
                "entity_id": ref.entity_id,
                "field": ref.field,
            }
            for ref in event.affected_entities
        ],
        "event_parameters": dict(event.parameters),
    }

    return patched, scenario_context
