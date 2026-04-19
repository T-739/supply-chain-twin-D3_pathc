"""B1 Slice 3: event_loop_c integration tests.

Covers the narrow delegation point added to
``src/event_loop_c.py::_build_path_c_main_records``.

Invariants tested:

  - When ``enable_replan=False`` (or ``replan_config`` is omitted),
    ``run_session`` produces a byte-identical artifact to pre-B1
    behavior in all supported modes. We express this by comparing
    ``enable_replan=False`` against the default (no replan_config
    passed) — both should serialize identically.
  - When ``enable_replan=True`` and a forced trigger fires on an
    event, that event's ``SessionEventRecord`` carries non-None
    ``replan_trace`` / ``replan_triggers``; ``effective_decision``
    reflects the final attempt; and ``baseline_event_result`` is
    byte-equal to the Path B shadow.
  - Memory length remains exactly one record per event regardless
    of replan firing.
  - BASELINE_STATIC is untouched by ``enable_replan=True``.
  - The session is replay-stable: two fresh-process-equivalent
    ``run_session`` calls with the same inputs produce byte-identical
    ``SessionArtifact`` bytes.
"""

from __future__ import annotations

import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


def _force_cost_trigger(*, expected_outcome, execution_status,
                        execution_outcome, attempt_index, config):
    from replan.replan_schema import ReplanTriggerRecord

    if attempt_index == 0:
        return ReplanTriggerRecord(
            trigger_rule_id="cost_deviation_v1",
            trigger_type="COST_DEVIATION",
            attempt_index=0,
            deviation_measurement={
                "realized_cost": 500.0,
                "absolute_delta": 400.0,
                "relative_delta": 3.0,
            },
            expected_outcome_ref=expected_outcome,
            realized_cost=(
                execution_outcome.get("cost_incurred")
                if isinstance(execution_outcome, dict) else None
            ),
            notes="forced in test",
        )
    return ReplanTriggerRecord(
        trigger_rule_id="no_trigger_v1",
        trigger_type="NO_TRIGGER",
        attempt_index=attempt_index,
        deviation_measurement={},
        expected_outcome_ref=expected_outcome,
        realized_cost=(
            execution_outcome.get("cost_incurred")
            if isinstance(execution_outcome, dict) else None
        ),
    )


# ---------------------------------------------------------------------------
# (1) enable_replan=False preserves byte identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode", ["BASELINE_STATIC", "PATH_C_COLD", "PATH_C_WARM"],
)
def test_enable_replan_false_is_byte_identical_to_default(mode):
    from event_loop_c import run_session
    from replan import ReplanConfig
    from session.digests import canonical_json

    a = run_session(seed=42, mode=mode)
    b = run_session(seed=42, mode=mode, replan_config=ReplanConfig())
    assert canonical_json(a.model_dump()) == canonical_json(b.model_dump())
    assert a.session_id == b.session_id


# ---------------------------------------------------------------------------
# (2) enable_replan=True with forced trigger materializes replan trace
# ---------------------------------------------------------------------------


def test_enabled_replan_with_forced_trigger_materializes_trace(monkeypatch):
    from event_loop_c import run_session
    from replan import ReplanConfig

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    artifact = run_session(
        seed=42,
        mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=True),
    )

    has_replan = [
        r for r in artifact.event_records if r.replan_trace is not None
    ]
    # Every PATH_C_* event triggers under the forced patch, so every
    # record should have a replan_trace populated.
    assert len(has_replan) == len(artifact.event_records)
    for rec in has_replan:
        assert rec.replan_triggers is not None
        assert len(rec.replan_trace) == 2
        assert [r.attempt_index for r in rec.replan_trace] == [0, 1]
        assert rec.replan_triggers[0].trigger_type == "COST_DEVIATION"


def test_enabled_replan_baseline_static_is_unaffected(monkeypatch):
    """BASELINE_STATIC never consults the orchestrator."""
    from event_loop_c import run_session
    from replan import ReplanConfig

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    artifact = run_session(
        seed=42,
        mode="BASELINE_STATIC",
        replan_config=ReplanConfig(enable_replan=True),
    )
    for rec in artifact.event_records:
        assert rec.replan_trace is None
        assert rec.replan_triggers is None


# ---------------------------------------------------------------------------
# (3) effective_decision reflects the FINAL attempt
# ---------------------------------------------------------------------------


def test_final_effective_decision_status_matches_final_attempt(monkeypatch):
    from event_loop_c import run_session
    from replan import ReplanConfig

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    artifact = run_session(
        seed=42,
        mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=True),
    )
    for rec in artifact.event_records:
        if rec.replan_trace is None:
            continue
        final_attempt = rec.replan_trace[-1]
        assert rec.effective_decision.execution_status == (
            final_attempt.attempt_execution_status
        ), (
            "effective_decision.execution_status must track the final "
            "ReplanAttemptRecord's attempt_execution_status"
        )
        assert rec.effective_decision.final_route == (
            final_attempt.attempt_final_route
        )


# ---------------------------------------------------------------------------
# (4) baseline_event_result byte-equal to Path B shadow (shadow not mutated)
# ---------------------------------------------------------------------------


def test_baseline_event_result_untouched_when_replan_fires(monkeypatch):
    from event_loop import run_event_loop
    from event_loop_c import run_session
    from event_engine import generate_demo_event_stream
    from replan import ReplanConfig
    from session.digests import canonical_json

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    events = generate_demo_event_stream()
    shadow = run_event_loop(events)["event_results"]
    artifact = run_session(
        seed=42,
        mode="PATH_C_COLD",
        events=events,
        replan_config=ReplanConfig(enable_replan=True),
    )
    for rec, shadow_er in zip(artifact.event_records, shadow):
        assert canonical_json(rec.baseline_event_result) == canonical_json(shadow_er)


# ---------------------------------------------------------------------------
# (5) memory append invariant: exactly one record per event
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("enable_replan", [False, True])
def test_memory_count_equals_event_count(monkeypatch, enable_replan):
    from event_loop_c import run_session
    from replan import ReplanConfig

    if enable_replan:
        monkeypatch.setattr(
            "replan.replan_orchestrator.decide_replan_trigger",
            _force_cost_trigger,
        )
    artifact = run_session(
        seed=42,
        mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=enable_replan),
    )
    mem_records = artifact.memory_snapshot["records"]
    assert len(mem_records) == len(artifact.event_records)


def test_memory_record_reflects_final_attempt_outcome(monkeypatch):
    """For replanned events, the memory record's cost/sla/route must
    match the FINAL attempt, not attempt 0."""
    from event_loop_c import run_session
    from replan import ReplanConfig

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    artifact = run_session(
        seed=42,
        mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=True),
    )
    records_by_event = {
        r["event_id"]: r for r in artifact.memory_snapshot["records"]
    }
    for rec in artifact.event_records:
        if rec.replan_trace is None:
            continue
        final_attempt = rec.replan_trace[-1]
        mem = records_by_event[rec.baseline_event_result["event_id"]]
        assert mem["final_route"] == final_attempt.attempt_final_route
        assert mem["execution_status"] == final_attempt.attempt_execution_status


# ---------------------------------------------------------------------------
# (6) Replay stability with replan enabled
# ---------------------------------------------------------------------------


def test_two_runs_with_replan_are_byte_identical(monkeypatch):
    from event_loop_c import run_session
    from replan import ReplanConfig
    from session.digests import canonical_json

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    cfg = ReplanConfig(enable_replan=True)
    a = run_session(seed=42, mode="PATH_C_COLD", replan_config=cfg)
    b = run_session(seed=42, mode="PATH_C_COLD", replan_config=cfg)
    assert canonical_json(a.model_dump()) == canonical_json(b.model_dump())
    assert a.session_id == b.session_id


def test_save_load_replay_byte_identical_with_replan(monkeypatch, tmp_path):
    """save_session → load_session → replay_session_bytes roundtrips
    byte-for-byte even when replan_trace / replan_triggers are
    populated."""
    from event_loop_c import run_session
    from replan import ReplanConfig
    from session.session_manager import (
        ARTIFACT_FILENAME,
        load_session,
        replay_session_bytes,
        save_session,
    )

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    cfg = ReplanConfig(enable_replan=True)
    artifact = run_session(seed=42, mode="PATH_C_COLD", replan_config=cfg)
    save_session(artifact, tmp_path)
    with open(tmp_path / ARTIFACT_FILENAME, "r") as f:
        saved = f.read()
    loaded = load_session(tmp_path)
    replayed = replay_session_bytes(loaded)
    assert replayed == saved


def test_replan_changes_session_id_when_enabled():
    """enable_replan contributes to session_id digest only when True —
    so enabling replan with the same inputs must change session_id,
    while disabling it keeps session_id pinned to the pre-B1 value.
    """
    from event_loop_c import run_session
    from replan import ReplanConfig

    a_off = run_session(seed=42, mode="PATH_C_COLD")
    a_on = run_session(
        seed=42, mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=True),
    )
    assert a_off.session_id != a_on.session_id
