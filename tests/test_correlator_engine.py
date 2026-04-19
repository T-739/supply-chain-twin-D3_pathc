"""B2 Slice 2B: correlator engine pattern-matching unit tests.

Exercises ``compute_correlation_context`` on hand-built event
streams to pin:

  - disabled correlator returns ``None``;
  - enabled correlator with no matches returns a
    ``CorrelationContext`` with empty ``signals`` (ran-but-found-
    nothing), distinct from the disabled case;
  - P1 ``ETA_PATH_COMPOUND`` fires deterministically on a carrier-
    delay + weather-worsening pair inside the window;
  - P1 does NOT fire if only one of the two types is present;
  - P1 does NOT fire if the counterpart is outside the window;
  - P3 ``CARRIER_DOUBLE_HIT`` fires on delay+hold sharing the same
    carrier id inside the window;
  - P3 does NOT fire if the delay and hold target different carrier
    ids;
  - ``STREAM_ADJACENT`` is emitted iff the participating ordinals
    are exactly consecutive;
  - ``SEVERITY_HIGH_CONCURRENCE`` is emitted iff every participant
    has severity in {MEDIUM, HIGH};
  - ``triggering_event_id`` is always the current event's id, and
    always appears in ``participant_event_ids``;
  - pattern-catalog iteration order is stable
    (P1 before P3 whenever both fire).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from event_schema import (  # noqa: E402
    AffectedEntityRef,
    EventPayload,
    EventSeverity,
    EventType,
)

from correlator.correlator_config import CorrelatorConfig  # noqa: E402
from correlator.correlator_engine import (  # noqa: E402
    compute_correlation_context,
)


_T0 = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)


def _ev(
    *,
    event_id: str,
    event_type: EventType,
    severity: EventSeverity = EventSeverity.MEDIUM,
    entities: list[AffectedEntityRef] | None = None,
    ordinal: int = 0,
) -> EventPayload:
    """Build a minimal, deterministic EventPayload."""
    from datetime import timedelta

    if entities is None:
        entities = [AffectedEntityRef(entity_type="twin", entity_id="planned_eta")]
    return EventPayload(
        event_id=event_id,
        event_type=event_type,
        severity=severity,
        affected_entities=entities,
        timestamp=_T0 + timedelta(minutes=30 * ordinal),
    )


def _carrier_delay(event_id: str, carrier_id: str, ordinal: int, sev=EventSeverity.HIGH):
    return _ev(
        event_id=event_id,
        event_type=EventType.CARRIER_DELAY_ESCALATION,
        severity=sev,
        entities=[
            AffectedEntityRef(
                entity_type="carrier",
                entity_id=carrier_id,
                field="transit_time_hours",
            )
        ],
        ordinal=ordinal,
    )


def _weather(event_id: str, ordinal: int, sev=EventSeverity.MEDIUM):
    return _ev(
        event_id=event_id,
        event_type=EventType.WEATHER_WORSENING,
        severity=sev,
        entities=[AffectedEntityRef(entity_type="twin", entity_id="planned_eta")],
        ordinal=ordinal,
    )


def _compliance_hold(event_id: str, carrier_id: str, ordinal: int, sev=EventSeverity.HIGH):
    return _ev(
        event_id=event_id,
        event_type=EventType.COMPLIANCE_HOLD,
        severity=sev,
        entities=[
            AffectedEntityRef(entity_type="carrier", entity_id=carrier_id)
        ],
        ordinal=ordinal,
    )


def _demand_spike(event_id: str, zone_id: str, ordinal: int, sev=EventSeverity.HIGH):
    return _ev(
        event_id=event_id,
        event_type=EventType.DEMAND_SPIKE,
        severity=sev,
        entities=[
            AffectedEntityRef(
                entity_type="customer_zone",
                entity_id=zone_id,
                field="demand_units",
            )
        ],
        ordinal=ordinal,
    )


# ---------------------------------------------------------------------------
# Gate: disabled vs enabled-but-empty
# ---------------------------------------------------------------------------


def test_disabled_correlator_returns_none():
    events = [_weather("E0", 0), _carrier_delay("E1", "CR_1", 1)]
    cfg = CorrelatorConfig()  # enable_correlator defaults False
    assert cfg.enable_correlator is False
    assert compute_correlation_context(events=events, current_index=1, config=cfg) is None


def test_enabled_but_no_match_returns_empty_context():
    # Single weather event, no counterpart — P1 cannot fire; P3 cannot
    # fire either (no carrier delay and no compliance hold).
    events = [_weather("E0", 0)]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    ctx = compute_correlation_context(events=events, current_index=0, config=cfg)
    assert ctx is not None
    assert ctx.signals == []
    assert ctx.window_size == 3
    assert ctx.window_events_considered == 1


# ---------------------------------------------------------------------------
# P1 — ETA_PATH_COMPOUND
# ---------------------------------------------------------------------------


def test_p1_fires_on_carrier_then_weather_current_weather():
    events = [_carrier_delay("E0", "CR_1", 0), _weather("E1", 1)]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    ctx = compute_correlation_context(events=events, current_index=1, config=cfg)
    assert ctx is not None and len(ctx.signals) == 1
    sig = ctx.signals[0]
    assert sig.pattern_id == "ETA_PATH_COMPOUND"
    assert sig.triggering_event_id == "E1"
    assert sig.participant_event_ids == ["E0", "E1"]
    assert sig.window_start_ordinal == 0
    assert sig.window_end_ordinal == 1
    assert sig.window_size == 3
    assert "SHARED_ETA_PATH" in sig.matched_conditions
    assert "STREAM_ADJACENT" in sig.matched_conditions
    assert "SEVERITY_HIGH_CONCURRENCE" in sig.matched_conditions
    assert sig.shared_entities == []  # P1 is entity-free


def test_p1_fires_on_weather_then_carrier_current_carrier():
    events = [_weather("E0", 0), _carrier_delay("E1", "CR_1", 1)]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    ctx = compute_correlation_context(events=events, current_index=1, config=cfg)
    assert ctx is not None and len(ctx.signals) == 1
    sig = ctx.signals[0]
    assert sig.pattern_id == "ETA_PATH_COMPOUND"
    assert sig.triggering_event_id == "E1"
    assert sig.participant_event_ids == ["E0", "E1"]


def test_p1_only_emits_once_at_the_second_participant():
    # At the first event (weather alone) the pattern has not yet
    # seen both types — no emission.
    events = [_weather("E0", 0), _carrier_delay("E1", "CR_1", 1)]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    ctx0 = compute_correlation_context(events=events, current_index=0, config=cfg)
    assert ctx0 is not None and ctx0.signals == []
    ctx1 = compute_correlation_context(events=events, current_index=1, config=cfg)
    assert ctx1 is not None and len(ctx1.signals) == 1


def test_p1_does_not_fire_with_single_type_only():
    events = [_weather("E0", 0), _weather("E1", 1)]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    for i in range(2):
        ctx = compute_correlation_context(events=events, current_index=i, config=cfg)
        assert ctx is not None and ctx.signals == []


def test_p1_counterpart_outside_window_does_not_fire():
    # Window size 2. Carrier-delay at ordinal 0, weather at ordinal 3.
    # At ordinal 3 the window includes ordinals [2, 3] so the carrier
    # event is outside — P1 must NOT fire.
    events = [
        _carrier_delay("E0", "CR_1", 0),
        _demand_spike("E1", "CZ_1", 1),
        _demand_spike("E2", "CZ_1", 2),
        _weather("E3", 3),
    ]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=2)
    ctx = compute_correlation_context(events=events, current_index=3, config=cfg)
    assert ctx is not None and ctx.signals == []


def test_p1_stream_adjacent_absent_when_separated():
    # Carrier ordinal 0, demand spike ordinal 1, weather ordinal 2.
    # P1 participants have ordinals [0, 2], not contiguous, so
    # STREAM_ADJACENT is NOT emitted. SHARED_ETA_PATH still is.
    events = [
        _carrier_delay("E0", "CR_1", 0),
        _demand_spike("E1", "CZ_1", 1),
        _weather("E2", 2),
    ]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    ctx = compute_correlation_context(events=events, current_index=2, config=cfg)
    assert ctx is not None and len(ctx.signals) == 1
    sig = ctx.signals[0]
    assert "SHARED_ETA_PATH" in sig.matched_conditions
    assert "STREAM_ADJACENT" not in sig.matched_conditions


def test_p1_severity_concurrence_absent_when_any_low():
    events = [
        _carrier_delay("E0", "CR_1", 0, sev=EventSeverity.LOW),
        _weather("E1", 1, sev=EventSeverity.MEDIUM),
    ]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    ctx = compute_correlation_context(events=events, current_index=1, config=cfg)
    assert ctx is not None and len(ctx.signals) == 1
    sig = ctx.signals[0]
    assert "SHARED_ETA_PATH" in sig.matched_conditions
    assert "SEVERITY_HIGH_CONCURRENCE" not in sig.matched_conditions


# ---------------------------------------------------------------------------
# P3 — CARRIER_DOUBLE_HIT
# ---------------------------------------------------------------------------


def test_p3_fires_on_delay_then_hold_same_carrier():
    events = [
        _carrier_delay("E0", "CR_1", 0),
        _compliance_hold("E1", "CR_1", 1),
    ]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    ctx = compute_correlation_context(events=events, current_index=1, config=cfg)
    assert ctx is not None and len(ctx.signals) == 1
    sig = ctx.signals[0]
    assert sig.pattern_id == "CARRIER_DOUBLE_HIT"
    assert sig.triggering_event_id == "E1"
    assert sig.participant_event_ids == ["E0", "E1"]
    assert "SAME_ENTITY_ID" in sig.matched_conditions
    assert "STREAM_ADJACENT" in sig.matched_conditions
    assert "SEVERITY_HIGH_CONCURRENCE" in sig.matched_conditions
    # shared_entities must include exactly the shared carrier.
    assert len(sig.shared_entities) == 1
    assert sig.shared_entities[0].entity_type == "carrier"
    assert sig.shared_entities[0].entity_id == "CR_1"


def test_p3_fires_on_hold_then_delay_same_carrier():
    events = [
        _compliance_hold("E0", "CR_1", 0),
        _carrier_delay("E1", "CR_1", 1),
    ]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    ctx = compute_correlation_context(events=events, current_index=1, config=cfg)
    assert ctx is not None and len(ctx.signals) == 1
    sig = ctx.signals[0]
    assert sig.pattern_id == "CARRIER_DOUBLE_HIT"
    assert sig.triggering_event_id == "E1"


def test_p3_does_not_fire_different_carriers():
    events = [
        _carrier_delay("E0", "CR_1", 0),
        _compliance_hold("E1", "CR_2", 1),
    ]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    ctx = compute_correlation_context(events=events, current_index=1, config=cfg)
    assert ctx is not None and ctx.signals == []


def test_p3_emits_one_signal_per_carrier_in_window():
    # The current event is a compliance hold that targets BOTH
    # CR_1 and CR_2 simultaneously, and each has a matching prior
    # carrier-delay inside the window. Expect two P3 signals,
    # ordered by entity_id ascending, each anchored at the current
    # event.
    events = [
        _carrier_delay("E0", "CR_1", 0),
        _carrier_delay("E1", "CR_2", 1),
        _ev(
            event_id="E2",
            event_type=EventType.COMPLIANCE_HOLD,
            severity=EventSeverity.HIGH,
            entities=[
                AffectedEntityRef(entity_type="carrier", entity_id="CR_1"),
                AffectedEntityRef(entity_type="carrier", entity_id="CR_2"),
            ],
            ordinal=2,
        ),
    ]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    ctx = compute_correlation_context(events=events, current_index=2, config=cfg)
    assert ctx is not None
    p3_signals = [s for s in ctx.signals if s.pattern_id == "CARRIER_DOUBLE_HIT"]
    assert len(p3_signals) == 2
    assert [s.shared_entities[0].entity_id for s in p3_signals] == ["CR_1", "CR_2"]
    # All P3 signals share the same triggering event (current).
    assert all(s.triggering_event_id == "E2" for s in p3_signals)


# ---------------------------------------------------------------------------
# P1 + P3 joint firing — catalog order
# ---------------------------------------------------------------------------


def test_both_patterns_fire_p1_before_p3():
    # Window covers: carrier delay (CR_1), weather, compliance hold (CR_1).
    # At current=2 (compliance_hold CR_1): both patterns fire:
    #  - P1 because carrier_delay + weather are inside the window AND
    #    current is ... actually current is COMPLIANCE_HOLD, not one of
    #    the P1-required types, so P1 does NOT anchor here.
    # Rework: put compliance_hold first so ordering exercises the
    # "both fire at the same index" property naturally.
    events = [
        _compliance_hold("E0", "CR_1", 0),
        _weather("E1", 1),
        _carrier_delay("E2", "CR_1", 2),
    ]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    # At current=2 (CARRIER_DELAY_ESCALATION, CR_1):
    #  - P1 fires: current is carrier-delay, weather in window.
    #  - P3 fires: current is carrier-delay, hold CR_1 in window.
    ctx = compute_correlation_context(events=events, current_index=2, config=cfg)
    assert ctx is not None and len(ctx.signals) == 2
    # Pattern-catalog order: P1 first, P3 second.
    assert ctx.signals[0].pattern_id == "ETA_PATH_COMPOUND"
    assert ctx.signals[1].pattern_id == "CARRIER_DOUBLE_HIT"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_engine_rejects_empty_events():
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    with pytest.raises(ValueError):
        compute_correlation_context(events=[], current_index=0, config=cfg)


def test_engine_rejects_out_of_range_index():
    events = [_weather("E0", 0)]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    with pytest.raises(ValueError):
        compute_correlation_context(events=events, current_index=1, config=cfg)
    with pytest.raises(ValueError):
        compute_correlation_context(events=events, current_index=-1, config=cfg)


def test_disabled_pattern_does_not_fire():
    # Enable only P3; P1 ingredients are present but P1 is filtered out.
    events = [_carrier_delay("E0", "CR_1", 0), _weather("E1", 1)]
    cfg = CorrelatorConfig(
        enable_correlator=True,
        window_size=3,
        enabled_patterns=frozenset({"CARRIER_DOUBLE_HIT"}),
    )
    ctx = compute_correlation_context(events=events, current_index=1, config=cfg)
    assert ctx is not None and ctx.signals == []
