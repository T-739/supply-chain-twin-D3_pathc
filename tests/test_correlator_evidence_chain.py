"""B2 Slice 2B: structural evidence-chain invariants.

For every emitted ``CorrelationSignal`` (collected across an
end-to-end run of the demo stream with correlator enabled), pin
the structural invariants that define "explainable by evidence":

  - ``pattern_id`` is a member of the closed catalog;
  - every ``matched_conditions`` entry is a member of the closed
    condition vocabulary;
  - ``participant_event_ids`` has length >= 2;
  - ``triggering_event_id`` appears in ``participant_event_ids``;
  - participant ids are non-empty, non-duplicated strings;
  - ordinal invariants:
      start >= 0
      end >= start
      (end - start + 1) <= window_size
  - ``shared_entities`` is either non-empty OR the pattern's
    declaration sets ``allow_empty_shared_entities=True``.
  - every participant id is the ``event_id`` of some event in the
    original demo stream (no phantom references);
  - ``triggering_event_id`` is the id of the event at the
    sideband's owning stream position (the last-ordinal event
    whose record carries the context).
"""

from __future__ import annotations

import os
import sys
import typing

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from correlator.correlator_config import CorrelatorConfig  # noqa: E402
from correlator.correlator_schema import (  # noqa: E402
    CORRELATOR_MATCHED_CONDITION,
    CORRELATOR_PATTERN_ID,
)
from correlator.correlator_patterns import PATTERN_DECLARATIONS  # noqa: E402
from event_engine import generate_demo_event_stream  # noqa: E402
from event_loop_c import run_session  # noqa: E402


_VALID_PATTERN_IDS = set(typing.get_args(CORRELATOR_PATTERN_ID))
_VALID_CONDITIONS = set(typing.get_args(CORRELATOR_MATCHED_CONDITION))

_PATTERN_ALLOW_EMPTY = {
    d.pattern_id: d.allow_empty_shared_entities for d in PATTERN_DECLARATIONS
}


def _all_signals_for(mode: str, *, window_size: int = 6):
    art = run_session(
        seed=42,
        mode=mode,
        correlator_config=CorrelatorConfig(
            enable_correlator=True, window_size=window_size,
        ),
    )
    out = []
    events = generate_demo_event_stream()
    for idx, rec in enumerate(art.event_records):
        if rec.correlation_context is None:
            continue
        for sig in rec.correlation_context.signals:
            out.append((idx, events[idx].event_id, sig))
    return out


@pytest.mark.parametrize("mode", ["BASELINE_STATIC", "PATH_C_COLD", "PATH_C_WARM"])
def test_evidence_chain_invariants(mode):
    rows = _all_signals_for(mode)
    # The default demo stream contains a carrier delay (E0) and a
    # weather event (E1) — P1 must fire at least once. Adding or
    # removing demo events is a contract shift caught here.
    assert rows, f"expected at least one correlation signal in mode={mode}"

    demo_event_ids = {ev.event_id for ev in generate_demo_event_stream()}

    for owning_idx, owning_event_id, sig in rows:
        # Pattern id and conditions are members of closed sets.
        assert sig.pattern_id in _VALID_PATTERN_IDS
        for cond in sig.matched_conditions:
            assert cond in _VALID_CONDITIONS
        assert sig.matched_conditions, "matched_conditions must be non-empty"

        # Participant invariants.
        assert len(sig.participant_event_ids) >= 2
        assert sig.triggering_event_id in sig.participant_event_ids
        assert len(set(sig.participant_event_ids)) == len(
            sig.participant_event_ids
        ), "participant ids must not duplicate"
        for pid in sig.participant_event_ids:
            assert isinstance(pid, str) and pid.strip()
            assert pid in demo_event_ids, (
                f"phantom participant id {pid!r} not in demo stream"
            )

        # Ordinal invariants.
        assert sig.window_start_ordinal >= 0
        assert sig.window_end_ordinal >= sig.window_start_ordinal
        span = sig.window_end_ordinal - sig.window_start_ordinal + 1
        assert span <= sig.window_size

        # Shared-entities invariant: empty is allowed iff the
        # pattern declares allow_empty_shared_entities=True.
        if _PATTERN_ALLOW_EMPTY[sig.pattern_id]:
            pass  # empty allowed, anything goes
        else:
            assert sig.shared_entities, (
                f"pattern {sig.pattern_id} must have non-empty shared_entities"
            )

        # triggering_event_id equals the id of the event at the
        # sideband's owning stream position.
        assert sig.triggering_event_id == owning_event_id


def test_demo_stream_fires_p1_eta_path_compound():
    # The demo stream has CARRIER_DELAY_ESCALATION at ordinal 0
    # (event_id=EVT-D01) and WEATHER_WORSENING at ordinal 1
    # (event_id=EVT-D02). With any reasonable window (>= 2), P1
    # must fire at ordinal 1 anchored at EVT-D02.
    art = run_session(
        seed=42,
        mode="BASELINE_STATIC",
        correlator_config=CorrelatorConfig(enable_correlator=True, window_size=3),
    )
    ctx_1 = art.event_records[1].correlation_context
    assert ctx_1 is not None
    p1s = [s for s in ctx_1.signals if s.pattern_id == "ETA_PATH_COMPOUND"]
    assert len(p1s) == 1
    sig = p1s[0]
    assert sig.triggering_event_id == "EVT-D02"
    assert "EVT-D01" in sig.participant_event_ids
    assert "EVT-D02" in sig.participant_event_ids
    assert "SHARED_ETA_PATH" in sig.matched_conditions
