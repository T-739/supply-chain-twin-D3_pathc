"""B2 Slice 2A: SessionEventRecord 1.2 contract pin.

Explicitly asserts the B2 Slice 2A additive bump:

  - ``SessionEventRecord._SESSION_EVENT_RECORD_SCHEMA_VERSION == "1.2"``
  - A default-constructed ``SessionEventRecord`` has
    ``correlation_context is None``.
  - Setting ``correlation_context`` to a well-formed
    ``CorrelationContext`` roundtrips losslessly through
    ``model_dump`` / ``model_validate``.
  - Setting ``correlation_context`` does NOT mutate
    ``baseline_event_result`` or any other field (Path B shadow +
    dual-track invariants hold at the schema layer).
  - All other replan overlay defaults still hold
    (``replan_trace is None``, ``replan_triggers is None``).
"""

from __future__ import annotations

import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from correlator import (  # noqa: E402
    CorrelationContext,
    CorrelationSignal,
)
from session.session_schema import (  # noqa: E402
    _SESSION_EVENT_RECORD_SCHEMA_VERSION,
    EffectiveDecisionRef,
    GovernanceTruthRef,
    SessionEventRecord,
)


def _make_record(**overrides):
    kwargs = dict(
        baseline_event_result={"event_id": "EVT-1", "schema_version": "1.0"},
        session_id="S1",
        mode="BASELINE_STATIC",
        policy_route_source="baseline_static",
        governance_truth=GovernanceTruthRef(
            risk_level="LOW",
            recommended_candidate_type="EXPEDITE",
        ),
        effective_decision=EffectiveDecisionRef(
            effective_risk="LOW",
            final_route="AUTO_EXECUTE",
            action_taken="EXPEDITE",
            execution_status="executed",
        ),
    )
    kwargs.update(overrides)
    return SessionEventRecord(**kwargs)


def test_session_event_record_schema_version_constant_is_1_2():
    assert _SESSION_EVENT_RECORD_SCHEMA_VERSION == "1.2"


def test_session_event_record_default_version_is_1_2():
    rec = _make_record()
    assert rec.schema_version == "1.2"


def test_correlation_context_defaults_to_none():
    rec = _make_record()
    assert rec.correlation_context is None


def test_replan_overlay_defaults_still_hold():
    rec = _make_record()
    assert rec.replan_trace is None
    assert rec.replan_triggers is None


def test_correlation_context_roundtrip_with_signal():
    sig = CorrelationSignal(
        pattern_id="ETA_PATH_COMPOUND",
        triggering_event_id="EVT-D02",
        participant_event_ids=["EVT-D01", "EVT-D02"],
        shared_entities=[],
        window_start_ordinal=0,
        window_end_ordinal=1,
        window_size=3,
        matched_conditions=["SHARED_ETA_PATH"],
    )
    ctx = CorrelationContext(
        signals=[sig],
        window_size=3,
        window_events_considered=2,
    )
    rec = _make_record(correlation_context=ctx)
    assert rec.correlation_context is not None
    assert len(rec.correlation_context.signals) == 1

    dumped = rec.model_dump()
    assert dumped["schema_version"] == "1.2"
    assert dumped["correlation_context"]["signals"][0]["pattern_id"] == (
        "ETA_PATH_COMPOUND"
    )

    rebuilt = SessionEventRecord.model_validate(dumped)
    assert rebuilt.correlation_context is not None
    assert rebuilt.correlation_context.signals[0].triggering_event_id == "EVT-D02"


def test_correlation_context_empty_signals_is_distinct_from_none():
    # Ran-but-empty: CorrelationContext with signals==[]
    ran_empty = CorrelationContext(
        signals=[],
        window_size=3,
        window_events_considered=0,
    )
    rec = _make_record(correlation_context=ran_empty)
    assert rec.correlation_context is not None
    assert rec.correlation_context.signals == []

    # Did-not-run: correlation_context is None
    rec_none = _make_record()
    assert rec_none.correlation_context is None

    # Serialized forms differ so downstream consumers can tell them apart.
    assert rec.model_dump()["correlation_context"] is not None
    assert rec_none.model_dump()["correlation_context"] is None


def test_setting_correlation_context_does_not_mutate_other_fields():
    baseline = {"event_id": "EVT-1", "schema_version": "1.0", "foo": "bar"}
    ctx = CorrelationContext(
        signals=[],
        window_size=3,
        window_events_considered=0,
    )
    rec = _make_record(
        baseline_event_result=dict(baseline),  # defensive copy
        correlation_context=ctx,
    )
    # baseline_event_result equals the input dict verbatim.
    assert rec.baseline_event_result == baseline
    assert rec.governance_truth.risk_level == "LOW"
    assert rec.effective_decision.final_route == "AUTO_EXECUTE"
    assert rec.replan_trace is None
    assert rec.replan_triggers is None


def test_session_event_record_still_forbids_extra_fields():
    with pytest.raises(Exception):
        _make_record(mystery_field=1)
