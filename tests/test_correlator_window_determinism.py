"""B2 Slice 2B: window / pattern determinism.

Pins that ``compute_correlation_context`` is a pure function of
(events, current_index, config) — no hidden state, no wall-clock
dependence, no hash-randomized iteration. Every run on the same
inputs produces byte-identical serialized output.

Exercised:

  - repeated invocations on the same inputs within one process
    return equal objects;
  - a fresh subprocess produces the same serialized output (defeats
    hash-randomization of dict/set iteration);
  - the matcher does not mutate its inputs (events list and
    individual EventPayloads stay equal pre- vs post-call).
"""

from __future__ import annotations

import json
import os
import subprocess
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


def _stream() -> list[EventPayload]:
    from datetime import timedelta

    t0 = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)

    def at(i):
        return t0 + timedelta(minutes=30 * i)

    return [
        EventPayload(
            event_id="E0",
            event_type=EventType.CARRIER_DELAY_ESCALATION,
            severity=EventSeverity.HIGH,
            affected_entities=[
                AffectedEntityRef(
                    entity_type="carrier",
                    entity_id="CR_1",
                    field="transit_time_hours",
                )
            ],
            timestamp=at(0),
        ),
        EventPayload(
            event_id="E1",
            event_type=EventType.WEATHER_WORSENING,
            severity=EventSeverity.MEDIUM,
            affected_entities=[
                AffectedEntityRef(entity_type="twin", entity_id="planned_eta"),
            ],
            timestamp=at(1),
        ),
        EventPayload(
            event_id="E2",
            event_type=EventType.COMPLIANCE_HOLD,
            severity=EventSeverity.HIGH,
            affected_entities=[
                AffectedEntityRef(entity_type="carrier", entity_id="CR_1"),
            ],
            timestamp=at(2),
        ),
    ]


def test_repeated_same_process_invocations_are_equal():
    events = _stream()
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    outs = [
        compute_correlation_context(events=events, current_index=i, config=cfg)
        for _ in range(5)
        for i in range(len(events))
    ]
    # Group by current_index and assert all are equal.
    per_index = {i: [] for i in range(len(events))}
    for run in range(5):
        for i in range(len(events)):
            per_index[i].append(outs[run * len(events) + i])
    for i, lst in per_index.items():
        dumps = [x.model_dump() for x in lst]
        first = dumps[0]
        for d in dumps[1:]:
            assert d == first, f"determinism drift at index {i}"


def test_matcher_does_not_mutate_inputs():
    events = _stream()
    events_before = [e.model_dump() for e in events]
    cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
    for i in range(len(events)):
        compute_correlation_context(events=events, current_index=i, config=cfg)
    events_after = [e.model_dump() for e in events]
    assert events_after == events_before


def test_fresh_process_byte_identical():
    """Run the matcher in a subprocess and compare serialized JSON."""
    inline_script = r"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.join(_PROJECT_DIR, "src"))

from event_schema import (
    AffectedEntityRef,
    EventPayload,
    EventSeverity,
    EventType,
)
from correlator.correlator_config import CorrelatorConfig
from correlator.correlator_engine import compute_correlation_context

t0 = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
def at(i):
    return t0 + timedelta(minutes=30 * i)

events = [
    EventPayload(
        event_id="E0",
        event_type=EventType.CARRIER_DELAY_ESCALATION,
        severity=EventSeverity.HIGH,
        affected_entities=[
            AffectedEntityRef(
                entity_type="carrier",
                entity_id="CR_1",
                field="transit_time_hours",
            )
        ],
        timestamp=at(0),
    ),
    EventPayload(
        event_id="E1",
        event_type=EventType.WEATHER_WORSENING,
        severity=EventSeverity.MEDIUM,
        affected_entities=[
            AffectedEntityRef(entity_type="twin", entity_id="planned_eta"),
        ],
        timestamp=at(1),
    ),
    EventPayload(
        event_id="E2",
        event_type=EventType.COMPLIANCE_HOLD,
        severity=EventSeverity.HIGH,
        affected_entities=[
            AffectedEntityRef(entity_type="carrier", entity_id="CR_1"),
        ],
        timestamp=at(2),
    ),
]
cfg = CorrelatorConfig(enable_correlator=True, window_size=3)
out = [
    compute_correlation_context(events=events, current_index=i, config=cfg).model_dump(mode="json")
    for i in range(len(events))
]
sys.stdout.write(json.dumps(out, sort_keys=True))
"""
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    res0 = subprocess.run(
        [sys.executable, "-c", inline_script],
        cwd=_PROJECT_DIR,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    env["PYTHONHASHSEED"] = "random"
    res1 = subprocess.run(
        [sys.executable, "-c", inline_script],
        cwd=_PROJECT_DIR,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert res0.stdout == res1.stdout, (
        "correlation output differs across PYTHONHASHSEED values — "
        "determinism violation"
    )
