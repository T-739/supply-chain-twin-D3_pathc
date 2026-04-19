"""
tests/test_event_engine.py — D3-Demo Phase 2: Event engine tests.

Covers:
  - Demo stream returns valid EventPayload list
  - All 6 event types present
  - Timestamps strictly increasing
  - Deterministic output (same inputs → same output)
  - Factory helpers produce valid events
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
    generate_demo_event_stream,
    make_carrier_delay_escalation,
    make_compliance_hold,
    make_customer_cancellation,
    make_demand_spike,
    make_inventory_discrepancy,
    make_weather_worsening,
)
from event_schema import EventPayload, EventSeverity, EventType


class TestDemoEventStream:
    """Tests for the default demo event stream."""

    def test_returns_list_of_event_payloads(self):
        events = generate_demo_event_stream()
        assert isinstance(events, list)
        assert len(events) > 0
        for e in events:
            assert isinstance(e, EventPayload)

    def test_all_six_event_types_present(self):
        events = generate_demo_event_stream()
        types = {e.event_type for e in events}
        assert types == {
            EventType.CARRIER_DELAY_ESCALATION,
            EventType.WEATHER_WORSENING,
            EventType.DEMAND_SPIKE,
            EventType.INVENTORY_DISCREPANCY,
            EventType.CUSTOMER_CANCELLATION,
            EventType.COMPLIANCE_HOLD,
        }

    def test_timestamps_strictly_increasing(self):
        events = generate_demo_event_stream()
        for i in range(1, len(events)):
            assert events[i].timestamp > events[i - 1].timestamp

    def test_deterministic_default(self):
        """Same inputs produce identical output."""
        stream_a = generate_demo_event_stream()
        stream_b = generate_demo_event_stream()
        assert len(stream_a) == len(stream_b)
        for a, b in zip(stream_a, stream_b):
            assert a.event_id == b.event_id
            assert a.event_type == b.event_type
            assert a.severity == b.severity
            assert a.timestamp == b.timestamp
            assert a.parameters == b.parameters

    def test_deterministic_with_custom_t0(self):
        t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        stream_a = generate_demo_event_stream(t0=t0, interval_minutes=15)
        stream_b = generate_demo_event_stream(t0=t0, interval_minutes=15)
        for a, b in zip(stream_a, stream_b):
            assert a.event_id == b.event_id
            assert a.timestamp == b.timestamp

    def test_event_ids_unique(self):
        events = generate_demo_event_stream()
        ids = [e.event_id for e in events]
        assert len(ids) == len(set(ids))

    def test_all_events_have_affected_entities(self):
        events = generate_demo_event_stream()
        for e in events:
            assert len(e.affected_entities) >= 1


class TestFactoryHelpers:
    """Tests for individual event factory functions."""

    _TS = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_carrier_delay(self):
        e = make_carrier_delay_escalation(
            event_id="T1", carrier_id="CR_1", delta_hours=5.0,
            severity=EventSeverity.LOW, timestamp=self._TS,
        )
        assert e.event_type == EventType.CARRIER_DELAY_ESCALATION
        assert e.parameters["delta_hours"] == 5.0

    def test_weather_worsening(self):
        e = make_weather_worsening(
            event_id="T2", delta_eta_hours=3.0,
            severity=EventSeverity.MEDIUM, timestamp=self._TS,
        )
        assert e.event_type == EventType.WEATHER_WORSENING
        assert e.parameters["delta_eta_hours"] == 3.0

    def test_demand_spike(self):
        e = make_demand_spike(
            event_id="T3", zone_id="CZ_1", delta_units=10,
            severity=EventSeverity.HIGH, timestamp=self._TS,
        )
        assert e.event_type == EventType.DEMAND_SPIKE
        assert e.parameters["delta_units"] == 10

    def test_inventory_discrepancy(self):
        e = make_inventory_discrepancy(
            event_id="T4", warehouse_id="WH_1", delta_units=-5,
            severity=EventSeverity.MEDIUM, timestamp=self._TS,
        )
        assert e.event_type == EventType.INVENTORY_DISCREPANCY
        assert e.parameters["delta_units"] == -5

    def test_customer_cancellation(self):
        e = make_customer_cancellation(
            event_id="T5", zone_id="CZ_2", delta_units=-3,
            severity=EventSeverity.LOW, timestamp=self._TS,
        )
        assert e.event_type == EventType.CUSTOMER_CANCELLATION
        assert e.parameters["delta_units"] == -3

    def test_compliance_hold(self):
        e = make_compliance_hold(
            event_id="T6", entity_type="carrier", entity_id="CR_1",
            severity=EventSeverity.HIGH, timestamp=self._TS,
        )
        assert e.event_type == EventType.COMPLIANCE_HOLD
        assert e.affected_entities[0].entity_type == "carrier"
