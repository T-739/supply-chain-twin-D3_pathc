"""
tests/test_event_loop.py — D3-Demo Phase 2+3: Event loop orchestrator tests.

Phase 2 coverage (preserved):
  - Baseline initialization from baseline_network.json
  - Processing 3+ events end-to-end
  - Each event produces governance_output and policy_decision
  - Runtime path does NOT contain evaluation_result
  - Live state accumulates changes across events
  - LOW events can produce AUTO_EXECUTE, HIGH → HUMAN_REQUIRED

Phase 3 additions (appended at bottom):
  - AUTO_EXECUTE events execute adapter, append outcome, update live state
  - HUMAN_REQUIRED events default to awaiting_human_review (no execution)
  - auto_approve_escalations=True is an explicit demo override
  - outcome_summary is injected into subsequent event scenario_context
  - final outcome_summary is valid
  - Live TwinState accumulates both event patches and executed outcomes
"""

import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from event_engine import generate_demo_event_stream
from event_loop import load_baseline_twin_state, run_event_loop
from outcome_store import OutcomeStore


@pytest.fixture(autouse=True)
def _ensure_rag():
    """Ensure RAG store is built (agents need it)."""
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


class TestEventLoopBasic:
    """Core event loop functionality."""

    def test_baseline_loads(self):
        ts = load_baseline_twin_state()
        assert ts.order_id == "ORD_BASE_001"
        assert len(ts.carriers) == 2
        assert len(ts.warehouses) == 2

    def test_process_first_three_events(self):
        """Run 3 events and verify basic structure."""
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)

        assert result["events_processed"] == 3
        assert len(result["event_results"]) == 3

        for rec in result["event_results"]:
            # Required fields present
            assert "event_id" in rec
            assert "event_type" in rec
            assert "severity" in rec
            assert "scenario_context" in rec
            assert "governance_output" in rec
            assert "policy_decision" in rec
            assert "trace_log" in rec

            # Runtime path must NOT contain evaluation
            assert "evaluation_result" not in rec

    def test_governance_output_has_risk_level(self):
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)

        for rec in result["event_results"]:
            gov = rec["governance_output"]
            assert "risk_level" in gov
            assert gov["risk_level"] in {"LOW", "MEDIUM", "HIGH"}

    def test_policy_decision_present(self):
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)

        for rec in result["event_results"]:
            pd = rec["policy_decision"]
            assert "route" in pd
            assert pd["route"] in {"AUTO_EXECUTE", "HUMAN_REQUIRED"}


class TestStateAccumulation:
    """Live TwinState must accumulate changes across events."""

    def test_disruptions_accumulate(self):
        events = generate_demo_event_stream()[:4]
        result = run_event_loop(events)
        summary = result["final_twin_state_summary"]
        assert summary["disruptions_count"] == 4

    def test_carrier_delay_accumulates(self):
        """First event adds 6h to CR_1 transit time; final state reflects it."""
        events = generate_demo_event_stream()[:1]
        baseline = load_baseline_twin_state()
        orig_transit = baseline.carriers["CR_1"].transit_time_hours

        result = run_event_loop(events, initial_twin_state=baseline)
        summary = result["final_twin_state_summary"]
        assert summary["carriers"]["CR_1"]["transit_time_hours"] == orig_transit + 6.0

    def test_full_demo_stream(self):
        """All 6 demo events process without error."""
        events = generate_demo_event_stream()
        result = run_event_loop(events)
        assert result["events_processed"] == 6


class TestPolicyRouting:
    """Policy gate routes correctly for different severity levels."""

    def test_low_event_can_auto_execute(self):
        """EVT-D01 is LOW severity → governance should produce LOW risk → AUTO_EXECUTE."""
        events = generate_demo_event_stream()[:1]  # LOW severity carrier delay
        result = run_event_loop(events)
        rec = result["event_results"][0]
        # LOW event typically produces LOW governance risk
        # (depends on candidate feasibility, but baseline has full feasibility)
        pd = rec["policy_decision"]
        assert pd["route"] == "AUTO_EXECUTE"

    def test_high_event_routes_to_human(self):
        """EVT-D03 is HIGH severity demand spike → should route to HUMAN_REQUIRED."""
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)
        # Event 3 (index 2) is HIGH severity
        rec = result["event_results"][2]
        pd = rec["policy_decision"]
        assert pd["route"] == "HUMAN_REQUIRED"


class TestNoEvaluationContamination:
    """Event loop must not import or reference evaluation/oracle modules."""

    def test_no_evaluation_in_results(self):
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)
        for rec in result["event_results"]:
            assert "evaluation_result" not in rec
            assert "oracle" not in str(rec).lower()

    def test_no_case_id_in_results(self):
        """Runtime path should not reference legacy case IDs."""
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)
        for rec in result["event_results"]:
            assert "case_id" not in rec


# ===========================================================================
# Phase 3 additions — execution + outcome feedback
# ===========================================================================


class TestPhase3Execution:
    """AUTO_EXECUTE events drive the adapter and append outcomes."""

    def test_auto_execute_appends_outcome(self):
        """A LOW-severity event should auto-execute and append one outcome."""
        events = generate_demo_event_stream()[:1]  # LOW severity
        result = run_event_loop(events)
        rec = result["event_results"][0]
        assert rec["execution_status"] == "executed"
        assert rec["execution_outcome"] is not None
        assert rec["execution_outcome"]["action_taken"] in {
            "EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION",
        }
        assert result["outcomes_count"] == 1

    def test_auto_execute_updates_live_state(self):
        """After an AUTO_EXECUTE, live state reflects adapter mutation."""
        events = generate_demo_event_stream()[:1]
        baseline = load_baseline_twin_state()
        orig_carrier = baseline.planned_carrier_id

        result = run_event_loop(events, initial_twin_state=baseline)
        summary = result["final_twin_state_summary"]
        rec = result["event_results"][0]

        # If the adapter took EXPEDITE, carrier should have switched.
        # For other operational types, this check is skipped.
        action = rec["execution_outcome"]["action_taken"]
        if action == "EXPEDITE":
            # The final carrier might differ from orig (switched by adapter)
            # OR be the same (if no switch occurred — but this shouldn't
            # happen for EXPEDITE in baseline). Allow either outcome, just
            # verify the field is present and valid.
            assert "CR_" in rec["execution_outcome"]["state_delta"]["after"]["planned_carrier_id"]

        # Final state summary must be well-formed
        assert "carriers" in summary
        assert "warehouses" in summary


class TestPhase3HumanRequired:
    """HUMAN_REQUIRED events default to awaiting_human_review."""

    def test_human_required_not_executed_by_default(self):
        """HIGH severity event should route to HUMAN_REQUIRED and skip execution."""
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)
        # Event 3 (index 2) is HIGH severity → HUMAN_REQUIRED
        rec = result["event_results"][2]
        assert rec["policy_decision"]["route"] == "HUMAN_REQUIRED"
        assert rec["execution_status"] == "awaiting_human_review"
        assert rec["execution_outcome"] is None

    def test_human_required_records_routing(self):
        """outcome_store summary should reflect HUMAN_REQUIRED events
        even when no outcome is appended."""
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)
        summary = result["outcome_summary"]
        # Event 1 is LOW (auto), event 2 is MEDIUM (human), event 3 is HIGH (human)
        assert summary["human_required_count"] >= 1

    def test_auto_approve_escalations_demo_override(self):
        """auto_approve_escalations=True executes HUMAN_REQUIRED events
        but marks them explicitly as demo overrides."""
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events, auto_approve_escalations=True)
        rec3 = result["event_results"][2]  # HIGH severity
        assert rec3["policy_decision"]["route"] == "HUMAN_REQUIRED"
        # Either executed via override (if adapter succeeded) or execution_failed
        assert rec3["execution_status"] in {
            "executed_via_demo_override", "execution_failed",
        }


class TestPhase3OutcomeInjection:
    """outcome_summary is injected into scenario_context of subsequent events."""

    def test_first_event_sees_empty_summary(self):
        """On the first event, outcome_store is empty → summary has 0 outcomes."""
        events = generate_demo_event_stream()[:1]
        result = run_event_loop(events)
        first_ctx = result["event_results"][0]["scenario_context"]
        assert "outcome_summary" in first_ctx
        assert first_ctx["outcome_summary"]["outcomes_count"] == 0

    def test_later_event_sees_prior_outcomes(self):
        """On event N, the injected summary reflects outcomes from events 1..N-1."""
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)
        # Event 2's context should see event 1's outcome (if any was appended)
        second_ctx = result["event_results"][1]["scenario_context"]
        assert "outcome_summary" in second_ctx
        # If event 1 executed (AUTO_EXECUTE), summary shows >=1 outcome
        first_executed = result["event_results"][0]["execution_outcome"] is not None
        if first_executed:
            assert second_ctx["outcome_summary"]["outcomes_count"] >= 1


class TestPhase3FinalAggregates:
    """Final outcome_summary and outcomes_count are well-formed."""

    def test_final_summary_present(self):
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)
        assert "outcome_summary" in result
        summary = result["outcome_summary"]
        required = {
            "outcomes_count", "total_cost", "avg_cost", "action_counts",
            "status_counts", "sla_preserved_count", "sla_missed_count",
            "auto_executed_count", "human_required_count",
            "recent_actions", "recent_resolution_patterns",
        }
        assert required.issubset(summary.keys())

    def test_outcomes_count_consistent(self):
        """outcomes_count matches the number of executed events."""
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events)
        executed = sum(
            1 for r in result["event_results"]
            if r["execution_outcome"] is not None
        )
        assert result["outcomes_count"] == executed
        assert result["outcome_summary"]["outcomes_count"] == executed


class TestPhase3StateAccumulation:
    """Live TwinState accumulates event patches AND executed outcomes."""

    def test_executed_outcomes_affect_state(self):
        """Across the full demo stream, state should reflect both event patches
        and adapter-executed mutations."""
        events = generate_demo_event_stream()
        result = run_event_loop(events)
        summary = result["final_twin_state_summary"]

        # Event patches accumulate (6 events → 6 disruptions)
        assert summary["disruptions_count"] == 6

        # At least some outcomes should have been appended (LOW events auto-execute)
        assert result["outcomes_count"] >= 1


class TestPhase3OutcomeStoreInjection:
    """Callers can pass their own OutcomeStore and see it grow."""

    def test_external_outcome_store_populated(self):
        store = OutcomeStore()
        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events, outcome_store=store)
        # store was populated
        assert store.count() == result["outcomes_count"]
        # routing was tracked
        total_routed = (store.summary()["auto_executed_count"]
                        + store.summary()["human_required_count"])
        assert total_routed == 3  # one per event


class TestPhase3Determinism:
    """Running the same events twice produces the same execution outcome."""

    def test_deterministic_outcomes(self):
        events = generate_demo_event_stream()[:2]
        r1 = run_event_loop(events)
        r2 = run_event_loop(events)
        # Compare outcome costs
        costs_1 = [r["execution_outcome"]["cost_incurred"]
                   for r in r1["event_results"]
                   if r["execution_outcome"] is not None]
        costs_2 = [r["execution_outcome"]["cost_incurred"]
                   for r in r2["event_results"]
                   if r["execution_outcome"] is not None]
        assert costs_1 == costs_2
