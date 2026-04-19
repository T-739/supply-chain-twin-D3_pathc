"""B1 Slice 3: dual-track preservation under a fired replan.

Locked invariant (``docs/B1_REPLAN_CONTRACT_DRAFT.md §6.2``,
``docs/B1_REPLAN_BOUNDARY.md §5``): under a replan-fired event,

  - ``GovernanceTruthRef`` continues to reflect the FIRST-attempt
    governance identity — it is not rewritten when a second reasoning
    cycle produces different governance outputs.
  - ``EffectiveDecisionRef`` reflects the FINAL attempt's
    route/status/action and effective_risk.
  - The two refs are both present, independent, and never collapsed
    into a single value.
  - Per-attempt intermediate state is carried in ``replan_trace``
    only, not by mutating the primary truth refs.
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
        )
    return ReplanTriggerRecord(
        trigger_rule_id="no_trigger_v1",
        trigger_type="NO_TRIGGER",
        attempt_index=attempt_index,
        deviation_measurement={},
        expected_outcome_ref=expected_outcome,
    )


def _first_attempt_governance(artifact):
    """Map each event_id to its first-attempt (attempt 0) governance
    identity, recovered from the replan_trace.
    """
    out: dict[str, tuple[str, str]] = {}
    for rec in artifact.event_records:
        if rec.replan_trace is None:
            continue
        attempt0 = rec.replan_trace[0]
        assert attempt0.attempt_index == 0
        # attempt0 carries the route/action of the first attempt; the
        # first-attempt governance identity is reconstructed by comparing
        # to governance_truth below — which is the whole point of this
        # test: governance_truth must equal the first-attempt identity.
        out[rec.baseline_event_result["event_id"]] = (
            attempt0.attempt_final_route,
            attempt0.attempt_execution_status,
        )
    return out


def test_governance_truth_does_not_change_between_attempts(monkeypatch):
    """governance_truth should mirror the first-attempt governance
    identity, identical to what a no-replan run produces for the same
    event — even if the second cycle reports a different governance.
    """
    from event_loop_c import run_session
    from replan import ReplanConfig

    # Baseline: run PATH_C_COLD without replan. The governance_truth
    # for each event is the first-attempt (and only) governance identity.
    baseline = run_session(seed=42, mode="PATH_C_COLD")
    baseline_truth_by_event = {
        r.baseline_event_result["event_id"]: (
            r.governance_truth.risk_level,
            r.governance_truth.recommended_candidate_type,
        )
        for r in baseline.event_records
    }

    # Replan-enabled: every event fires the forced trigger, so every
    # event runs a second cycle. governance_truth must be unchanged.
    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    replanned = run_session(
        seed=42, mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=True),
    )
    for rec in replanned.event_records:
        event_id = rec.baseline_event_result["event_id"]
        assert (
            rec.governance_truth.risk_level,
            rec.governance_truth.recommended_candidate_type,
        ) == baseline_truth_by_event[event_id], (
            f"governance_truth for {event_id} diverged after replan — "
            "dual-track rule violated"
        )


def test_effective_decision_tracks_final_attempt(monkeypatch):
    from event_loop_c import run_session
    from replan import ReplanConfig

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    artifact = run_session(
        seed=42, mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=True),
    )
    for rec in artifact.event_records:
        if rec.replan_trace is None:
            continue
        final = rec.replan_trace[-1]
        assert rec.effective_decision.execution_status == final.attempt_execution_status
        assert rec.effective_decision.final_route == final.attempt_final_route
        # action_taken on EffectiveDecisionRef can be None when the
        # final attempt didn't execute; match that too.
        assert rec.effective_decision.action_taken == final.attempt_action_taken


def test_refs_are_both_present_and_independent(monkeypatch):
    """Dual-track means both refs are always present. They can differ,
    but they must never collapse to the same object or be omitted."""
    from event_loop_c import run_session
    from replan import ReplanConfig

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    artifact = run_session(
        seed=42, mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=True),
    )
    for rec in artifact.event_records:
        assert rec.governance_truth is not None
        assert rec.effective_decision is not None
        # Independent objects — mutating one must not affect the other.
        assert rec.governance_truth is not rec.effective_decision


def test_replan_trace_carries_attempt_level_state_separately(monkeypatch):
    """Per-attempt records live on replan_trace — not absorbed into
    the primary truth refs."""
    from event_loop_c import run_session
    from replan import ReplanConfig

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger",
        _force_cost_trigger,
    )
    artifact = run_session(
        seed=42, mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=True),
    )
    for rec in artifact.event_records:
        if rec.replan_trace is None:
            continue
        # replan_trace has per-attempt records; the primary refs do not
        # recursively contain these (they are flat, single-value refs).
        assert len(rec.replan_trace) == 2
        # The refs themselves only carry flat scalar fields.
        for field_name in ("effective_risk", "final_route",
                            "action_taken", "execution_status",
                            "schema_version"):
            val = getattr(rec.effective_decision, field_name)
            assert val is None or isinstance(val, str)
        for field_name in ("risk_level", "recommended_candidate_type",
                            "schema_version"):
            val = getattr(rec.governance_truth, field_name)
            assert isinstance(val, str)
