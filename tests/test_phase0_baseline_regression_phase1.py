"""Phase 1: Phase 0 snapshot fixtures must still pass when reached through
``event_loop_c.run_session(mode=BASELINE_STATIC)``.

This is the "Phase 0's fixture still byte-identical when reproduced via
event_loop_c.run_session(mode=BASELINE_STATIC)" acceptance criterion
from Roadmap §1.E.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from event_loop_c import run_session

_PHASE0_DEMO_STREAM_FIXTURE = os.path.join(
    _PROJECT_DIR, "tests", "fixtures", "d3_baseline_v1_demo_stream.json"
)


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


def test_phase0_demo_stream_still_byte_identical_via_event_loop_c():
    """Each baseline_event_result embedded in the session must match the
    Phase 0 demo-stream fixture element-by-element.
    """
    with open(_PHASE0_DEMO_STREAM_FIXTURE, "r") as f:
        expected = json.load(f)

    artifact = run_session(seed=42, mode="BASELINE_STATIC")

    expected_event_results = expected["event_results"]
    assert len(artifact.event_records) == len(expected_event_results)

    for ser, er in zip(artifact.event_records, expected_event_results):
        assert ser.baseline_event_result == er, (
            "baseline_event_result drifted from the Phase 0 snapshot. "
            "event_loop_c must wrap run_event_loop without mutation."
        )


def test_phase0_outcome_summary_schema_version_still_1_0():
    """outcome_summary v1.0 is a Tier 1 Phase 0 contract; Phase 1 must
    not bump it."""
    with open(_PHASE0_DEMO_STREAM_FIXTURE, "r") as f:
        expected = json.load(f)
    assert expected["outcome_summary"]["schema_version"] == "1.0"
