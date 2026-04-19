"""
tests/test_event_state_mapper.py — D3-Demo Phase 2: Event-to-state mapping tests.

Covers:
  - Pure function: input twin_state not modified
  - Patched copy correctly reflects event mutation
  - scenario_context contains required fields
  - Invalid patch raises error (not silent fail)
  - All 6 event types produce valid patches
"""

import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from datetime import datetime, timezone

from event_engine import (
    make_carrier_delay_escalation,
    make_compliance_hold,
    make_customer_cancellation,
    make_demand_spike,
    make_inventory_discrepancy,
    make_weather_worsening,
)
from event_schema import EventSeverity
from event_state_mapper import map_event_to_state
from twin_state import TwinState

_TS = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
_BASELINE = os.path.join(_PROJECT_DIR, "data", "configs", "baseline_network.json")


@pytest.fixture
def baseline():
    return TwinState.initialize_from_config(_BASELINE)


class TestPureFunctionGuarantee:
    """Input twin_state must never be modified."""

    def test_input_unchanged_after_mapping(self, baseline):
        original_eta = baseline.planned_eta_hours
        original_cr1_transit = baseline.carriers["CR_1"].transit_time_hours

        event = make_carrier_delay_escalation(
            event_id="X1", carrier_id="CR_1", delta_hours=10.0,
            severity=EventSeverity.LOW, timestamp=_TS,
        )
        patched, ctx = map_event_to_state(event, baseline)

        # Input unchanged
        assert baseline.planned_eta_hours == original_eta
        assert baseline.carriers["CR_1"].transit_time_hours == original_cr1_transit
        # Output changed
        assert patched.carriers["CR_1"].transit_time_hours == original_cr1_transit + 10.0


class TestPatchCorrectness:
    """Each event type produces the expected state mutation."""

    def test_carrier_delay_escalation(self, baseline):
        orig = baseline.carriers["CR_1"].transit_time_hours
        event = make_carrier_delay_escalation(
            event_id="P1", carrier_id="CR_1", delta_hours=8.0,
            severity=EventSeverity.LOW, timestamp=_TS,
        )
        patched, _ = map_event_to_state(event, baseline)
        assert patched.carriers["CR_1"].transit_time_hours == orig + 8.0

    def test_weather_worsening(self, baseline):
        orig = baseline.planned_eta_hours
        event = make_weather_worsening(
            event_id="P2", delta_eta_hours=5.0,
            severity=EventSeverity.MEDIUM, timestamp=_TS,
        )
        patched, _ = map_event_to_state(event, baseline)
        assert patched.planned_eta_hours == orig + 5.0

    def test_demand_spike(self, baseline):
        orig = baseline.customer_zones["CZ_1"].demand_units
        event = make_demand_spike(
            event_id="P3", zone_id="CZ_1", delta_units=5,
            severity=EventSeverity.HIGH, timestamp=_TS,
        )
        patched, _ = map_event_to_state(event, baseline)
        assert patched.customer_zones["CZ_1"].demand_units == orig + 5

    def test_inventory_discrepancy(self, baseline):
        orig = baseline.warehouses["WH_1"].current_inventory
        event = make_inventory_discrepancy(
            event_id="P4", warehouse_id="WH_1", delta_units=-10,
            severity=EventSeverity.MEDIUM, timestamp=_TS,
        )
        patched, _ = map_event_to_state(event, baseline)
        assert patched.warehouses["WH_1"].current_inventory == orig - 10

    def test_customer_cancellation(self, baseline):
        orig = baseline.customer_zones["CZ_2"].demand_units
        event = make_customer_cancellation(
            event_id="P5", zone_id="CZ_2", delta_units=-2,
            severity=EventSeverity.LOW, timestamp=_TS,
        )
        patched, _ = map_event_to_state(event, baseline)
        assert patched.customer_zones["CZ_2"].demand_units == orig - 2

    def test_compliance_hold_carrier(self, baseline):
        assert baseline.carriers["CR_2"].available is True
        event = make_compliance_hold(
            event_id="P6", entity_type="carrier", entity_id="CR_2",
            severity=EventSeverity.HIGH, timestamp=_TS,
        )
        patched, _ = map_event_to_state(event, baseline)
        assert patched.carriers["CR_2"].available is False

    def test_compliance_hold_supplier(self, baseline):
        assert baseline.suppliers["SUP_1"].is_active is True
        event = make_compliance_hold(
            event_id="P7", entity_type="supplier", entity_id="SUP_1",
            severity=EventSeverity.HIGH, timestamp=_TS,
        )
        patched, _ = map_event_to_state(event, baseline)
        assert patched.suppliers["SUP_1"].is_active is False


class TestScenarioContext:
    """scenario_context must contain all required fields."""

    def test_required_fields_present(self, baseline):
        event = make_carrier_delay_escalation(
            event_id="C1", carrier_id="CR_1", delta_hours=2.0,
            severity=EventSeverity.LOW, timestamp=_TS,
        )
        _, ctx = map_event_to_state(event, baseline)

        assert ctx["scenario_type"] == "event_runtime"
        assert ctx["event_id"] == "C1"
        assert ctx["event_type"] == "CARRIER_DELAY_ESCALATION"
        assert ctx["risk_level"] == "LOW"
        assert isinstance(ctx["exception_description"], str)
        assert len(ctx["exception_description"]) > 10
        assert isinstance(ctx["affected_entities"], list)
        assert len(ctx["affected_entities"]) >= 1
        assert isinstance(ctx["event_parameters"], dict)

    def test_high_severity_maps_to_high_risk(self, baseline):
        event = make_demand_spike(
            event_id="C2", zone_id="CZ_1", delta_units=3,
            severity=EventSeverity.HIGH, timestamp=_TS,
        )
        _, ctx = map_event_to_state(event, baseline)
        assert ctx["risk_level"] == "HIGH"

    def test_medium_severity_maps_to_med_risk(self, baseline):
        event = make_weather_worsening(
            event_id="C3", delta_eta_hours=2.0,
            severity=EventSeverity.MEDIUM, timestamp=_TS,
        )
        _, ctx = map_event_to_state(event, baseline)
        assert ctx["risk_level"] == "MEDIUM"


class TestErrorHandling:
    """Invalid patches must raise, not silently fail."""

    def test_inventory_below_zero_raises(self, baseline):
        """Reducing inventory below 0 must raise, not silently clamp."""
        event = make_inventory_discrepancy(
            event_id="E1", warehouse_id="WH_1", delta_units=-9999,
            severity=EventSeverity.HIGH, timestamp=_TS,
        )
        with pytest.raises((ValueError, KeyError)):
            map_event_to_state(event, baseline)

    def test_nonexistent_carrier_raises(self, baseline):
        event = make_carrier_delay_escalation(
            event_id="E2", carrier_id="NONEXISTENT", delta_hours=5.0,
            severity=EventSeverity.LOW, timestamp=_TS,
        )
        with pytest.raises((ValueError, KeyError)):
            map_event_to_state(event, baseline)

    def test_missing_delta_hours_raises(self, baseline):
        """CARRIER_DELAY_ESCALATION without delta_hours must raise."""
        from event_schema import AffectedEntityRef, EventPayload, EventType

        event = EventPayload(
            event_id="E3",
            event_type=EventType.CARRIER_DELAY_ESCALATION,
            severity=EventSeverity.LOW,
            affected_entities=[
                AffectedEntityRef(entity_type="carrier", entity_id="CR_1"),
            ],
            timestamp=_TS,
            parameters={},  # missing delta_hours
        )
        with pytest.raises(ValueError, match="delta_hours"):
            map_event_to_state(event, baseline)

    def test_atomicity_on_failure(self, baseline):
        """If patch fails, input state must be completely unchanged."""
        orig_inventory = baseline.warehouses["WH_1"].current_inventory
        event = make_inventory_discrepancy(
            event_id="E4", warehouse_id="WH_1", delta_units=-9999,
            severity=EventSeverity.HIGH, timestamp=_TS,
        )
        with pytest.raises((ValueError, KeyError)):
            map_event_to_state(event, baseline)
        # Input state unchanged
        assert baseline.warehouses["WH_1"].current_inventory == orig_inventory
