"""Phase 1: event_loop_c wraps Path B without behavioral change.

Core invariants verified here (Roadmap §1.F acceptance):

  - SessionEventRecord.baseline_event_result is BYTE-EQUAL to the
    corresponding item from a direct run_event_loop call.
  - BASELINE_STATIC and PATH_C_COLD produce the same baseline_event_result
    series (they differ only in Path C overlay fields).
  - memory appends exactly one record per event.
  - Path B behavior is unchanged.
"""

from __future__ import annotations

import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from event_engine import generate_demo_event_stream
from event_loop import run_event_loop
from event_loop_c import run_session


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


def test_baseline_static_embeds_path_b_verbatim():
    events = generate_demo_event_stream()
    direct = run_event_loop(events)
    artifact = run_session(seed=42, mode="BASELINE_STATIC")

    assert len(artifact.event_records) == len(direct["event_results"])
    for ser, er in zip(artifact.event_records, direct["event_results"]):
        assert ser.baseline_event_result == er


def test_path_c_cold_embeds_path_b_verbatim():
    events = generate_demo_event_stream()
    direct = run_event_loop(events)
    artifact = run_session(seed=42, mode="PATH_C_COLD")

    for ser, er in zip(artifact.event_records, direct["event_results"]):
        assert ser.baseline_event_result == er


def test_baseline_static_vs_path_c_cold_decision_identical():
    baseline = run_session(seed=42, mode="BASELINE_STATIC")
    cold = run_session(seed=42, mode="PATH_C_COLD")

    assert len(baseline.event_records) == len(cold.event_records)
    for b, c in zip(baseline.event_records, cold.event_records):
        assert b.baseline_event_result == c.baseline_event_result
        # Overlay decision fields must also agree in Phase 1 (no adaptive yet).
        assert b.effective_decision.final_route == c.effective_decision.final_route
        assert b.effective_decision.action_taken == c.effective_decision.action_taken
        assert b.effective_decision.execution_status == c.effective_decision.execution_status


def test_one_memory_record_per_event():
    artifact = run_session(seed=42, mode="PATH_C_COLD")
    records = artifact.memory_snapshot["records"]
    assert len(records) == len(artifact.event_records)
    assert len(records) == len(generate_demo_event_stream())


def test_baseline_static_policy_route_source_is_baseline_static():
    """BASELINE_STATIC never invokes the adaptive gate; every record is baseline."""
    artifact = run_session(seed=42, mode="BASELINE_STATIC")
    for ser in artifact.event_records:
        assert ser.policy_route_source == "baseline_static"
        assert ser.adaptive_adjustment is None


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        run_session(seed=42, mode="UNKNOWN_MODE")


_VALID_ACTIONS = {"EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"}


def test_governance_truth_recommended_candidate_type_populated_and_valid():
    """Phase 1 cleanup: metadata-only shim must produce a non-empty
    operational literal for every SessionEventRecord.
    """
    artifact = run_session(seed=42, mode="BASELINE_STATIC")
    for ser in artifact.event_records:
        value = ser.governance_truth.recommended_candidate_type
        assert value, "recommended_candidate_type must not be empty in Phase 1"
        assert value in _VALID_ACTIONS, (
            f"recommended_candidate_type={value!r} must be one of "
            f"{_VALID_ACTIONS}"
        )


def test_governance_truth_shim_raises_on_unrecognized_prefix():
    """Shim must fail explicitly on a malformed recommended_action,
    never silently fall back to an empty string.
    """
    from event_loop_c import (
        GovernanceTruthShimError,
        _recommended_candidate_type_shim,
    )

    # Valid prefix
    assert _recommended_candidate_type_shim(
        {"recommended_action": "EXPEDITE: expedite via ExpressAir (18h)"}
    ) == "EXPEDITE"

    # Missing
    with pytest.raises(GovernanceTruthShimError):
        _recommended_candidate_type_shim({})

    # Non-operational prefix (e.g. a supervision or evaluation token)
    with pytest.raises(GovernanceTruthShimError):
        _recommended_candidate_type_shim({"recommended_action": "APPROVE: xyz"})

    with pytest.raises(GovernanceTruthShimError):
        _recommended_candidate_type_shim({"recommended_action": "AI: no colon segment here meaningfully valid"})


def test_memory_record_fields_sourced_from_event_result():
    artifact = run_session(seed=42, mode="PATH_C_COLD")
    records = artifact.memory_snapshot["records"]
    # Each record must carry the session_id for traceability.
    for r in records:
        assert r["session_id"] == artifact.session_id
    # Sorted by (event_timestamp, event_id).
    ts_ids = [(r["event_timestamp"], r["event_id"]) for r in records]
    assert ts_ids == sorted(ts_ids)
