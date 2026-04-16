"""
test_cost_agent.py — Contract tests for the Cost Agent (Package 2C).

Verifies:
  1. Output schema is stable and JSON-serializable
  2. Same input returns same numeric estimates (determinism)
  3. Estimates are produced for all bounded candidate types
  4. Infeasible candidates get null costs and clear explanation
  5. No oracle/evaluation fields appear in output
  6. Real case-driven invocation works
  7. Estimate field naming uses _estimate suffix consistently
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agents.cost_agent import (
    CandidateCostEstimate,
    CostOutput,
    run_cost_agent,
)
from agents.operations_agent import build_operational_candidates
from rag_setup import build_vector_store, reset_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag_built():
    """RAG store needed by operations agent if invoked via graph."""
    reset_store()
    build_vector_store(force_rebuild=True)
    yield
    reset_store()


def _load_case(case_id: str) -> dict:
    path = os.path.join(_DATA_DIR, "cases", f"{case_id}.json")
    with open(path) as f:
        return json.load(f)


def _case_twin_state(case_id: str) -> dict:
    return _load_case(case_id).get("initial_state_snapshot", {})


def _make_candidates(twin_state: dict, order_units: int = 10) -> list[dict]:
    """Build operational candidates from twin_state."""
    return build_operational_candidates(twin_state, order_units=order_units)


# Standard test twin_state with known values
_STANDARD_TS = {
    "carriers": [
        {"id": "CR_1", "name": "Primary", "available": True,
         "cost_per_unit": 5.0, "transit_time_hours": 24, "capacity_limit": 200},
        {"id": "CR_2", "name": "Express", "available": True,
         "cost_per_unit": 12.0, "transit_time_hours": 8, "capacity_limit": 80},
    ],
    "warehouses": [
        {"id": "WH_1", "name": "Primary WH", "location": "A",
         "max_capacity": 1000, "current_inventory": 300,
         "operating_cost_per_unit": 1.0},
        {"id": "WH_2", "name": "Reserve WH", "location": "B",
         "max_capacity": 600, "current_inventory": 150,
         "operating_cost_per_unit": 1.5},
    ],
    "customer_zones": [
        {"id": "CZ_1", "name": "Standard Zone",
         "sla_deadline_hours": 48, "sla_penalty_per_hour": 5.0,
         "demand_units": 20},
    ],
}


# ---------------------------------------------------------------------------
# Output schema tests
# ---------------------------------------------------------------------------


class TestOutputSchema:
    def test_cost_estimate_fields(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        for est in result.cost_estimates:
            assert hasattr(est, "candidate_id")
            assert hasattr(est, "candidate_type")
            assert hasattr(est, "is_feasible")
            assert hasattr(est, "direct_cost_estimate")
            assert hasattr(est, "recovery_cost_estimate")
            assert hasattr(est, "total_cost_estimate")
            assert hasattr(est, "cost_breakdown_explanation")
            assert hasattr(est, "estimation_notes")

    def test_output_metadata(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        assert result.order_units_used > 0
        assert result.planned_eta_used > 0
        assert isinstance(result.cost_policy_used, dict)
        assert "expedite_multiplier" in result.cost_policy_used

    def test_json_serializable(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        d = result.to_dict()
        serialized = json.dumps(d)
        roundtrip = json.loads(serialized)
        assert "cost_estimates" in roundtrip

    def test_to_json_string(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        j = result.to_json()
        parsed = json.loads(j)
        assert len(parsed["cost_estimates"]) == len(candidates)

    def test_estimate_field_naming_uses_estimate_suffix(self):
        """All cost fields must use _estimate suffix."""
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        d = result.to_dict()
        for est in d["cost_estimates"]:
            # These keys must exist
            assert "direct_cost_estimate" in est
            assert "recovery_cost_estimate" in est
            assert "total_cost_estimate" in est
            # These keys must NOT exist
            assert "direct_cost" not in est
            assert "total_cost" not in est
            assert "recovery_cost" not in est


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_output(self):
        candidates = _make_candidates(_STANDARD_TS)
        r1 = run_cost_agent(_STANDARD_TS, candidates)
        r2 = run_cost_agent(_STANDARD_TS, candidates)
        assert r1.to_dict() == r2.to_dict()

    def test_expedite_cost_is_deterministic(self):
        candidates = _make_candidates(_STANDARD_TS)
        expedites = [c for c in candidates if c["candidate_type"] == "EXPEDITE"]
        r1 = run_cost_agent(_STANDARD_TS, expedites)
        r2 = run_cost_agent(_STANDARD_TS, expedites)
        for e1, e2 in zip(r1.cost_estimates, r2.cost_estimates):
            assert e1.total_cost_estimate == e2.total_cost_estimate


# ---------------------------------------------------------------------------
# Candidate type coverage tests
# ---------------------------------------------------------------------------


class TestCandidateTypeCoverage:
    def test_expedite_estimates_present(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        types = {e.candidate_type for e in result.cost_estimates}
        assert "EXPEDITE" in types

    def test_transfer_estimates_present(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        types = {e.candidate_type for e in result.cost_estimates}
        assert "TRANSFER" in types

    def test_compensate_estimate_present(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        types = {e.candidate_type for e in result.cost_estimates}
        assert "COMPENSATE" in types

    def test_no_action_estimate_present(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        types = {e.candidate_type for e in result.cost_estimates}
        assert "NO_ACTION" in types

    def test_one_estimate_per_candidate(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        assert len(result.cost_estimates) == len(candidates)


# ---------------------------------------------------------------------------
# Numeric sanity tests
# ---------------------------------------------------------------------------


class TestNumericSanity:
    def test_expedite_direct_cost_positive(self):
        """EXPEDITE direct cost = units * cost_per_unit * multiplier > 0."""
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        for est in result.cost_estimates:
            if est.candidate_type == "EXPEDITE" and est.is_feasible:
                assert est.direct_cost_estimate > 0

    def test_no_action_direct_cost_zero(self):
        """NO_ACTION direct cost must be 0."""
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        for est in result.cost_estimates:
            if est.candidate_type == "NO_ACTION":
                assert est.direct_cost_estimate == 0.0

    def test_total_equals_direct_plus_recovery(self):
        """total = direct + recovery for feasible candidates."""
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        for est in result.cost_estimates:
            if est.is_feasible:
                expected = round(est.direct_cost_estimate + est.recovery_cost_estimate, 2)
                assert est.total_cost_estimate == expected, (
                    f"{est.candidate_id}: {est.total_cost_estimate} != "
                    f"{est.direct_cost_estimate} + {est.recovery_cost_estimate}"
                )

    def test_recovery_nonnegative(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        for est in result.cost_estimates:
            if est.is_feasible:
                assert est.recovery_cost_estimate >= 0.0

    def test_known_expedite_value(self):
        """CR_1: 10 * 5.0 * 2.0 = 100.0 direct; transit 24h < 48h SLA so recovery=0."""
        candidates = [c for c in _make_candidates(_STANDARD_TS)
                      if c["candidate_id"] == "EXPEDITE_CR_1"]
        result = run_cost_agent(_STANDARD_TS, candidates)
        est = result.cost_estimates[0]
        assert est.direct_cost_estimate == 100.0
        assert est.recovery_cost_estimate == 0.0
        assert est.total_cost_estimate == 100.0

    def test_known_transfer_value(self):
        """WH_1→WH_2: 30 + 10*1.5 + 10*1.5 = 60.0 direct; 36h < 48h so recovery=0."""
        candidates = [c for c in _make_candidates(_STANDARD_TS)
                      if c["candidate_id"] == "TRANSFER_WH_1_to_WH_2"]
        result = run_cost_agent(_STANDARD_TS, candidates)
        est = result.cost_estimates[0]
        assert est.direct_cost_estimate == 60.0
        assert est.recovery_cost_estimate == 0.0
        assert est.total_cost_estimate == 60.0


# ---------------------------------------------------------------------------
# Infeasible candidate tests
# ---------------------------------------------------------------------------


class TestInfeasibleCandidates:
    def test_infeasible_has_null_costs(self):
        ts = {
            "carriers": [
                {"id": "CR_1", "name": "Down", "available": False,
                 "cost_per_unit": 5, "transit_time_hours": 24, "capacity_limit": 200},
            ],
            "warehouses": [],
            "customer_zones": [],
        }
        candidates = _make_candidates(ts)
        result = run_cost_agent(ts, candidates)
        for est in result.cost_estimates:
            if not est.is_feasible:
                assert est.direct_cost_estimate is None
                assert est.recovery_cost_estimate is None
                assert est.total_cost_estimate is None

    def test_infeasible_has_explanation(self):
        ts = {
            "carriers": [
                {"id": "CR_1", "name": "Down", "available": False,
                 "cost_per_unit": 5, "transit_time_hours": 24, "capacity_limit": 200},
            ],
            "warehouses": [],
            "customer_zones": [],
        }
        candidates = _make_candidates(ts)
        result = run_cost_agent(ts, candidates)
        for est in result.cost_estimates:
            if not est.is_feasible:
                assert len(est.cost_breakdown_explanation) > 0
                assert "infeasible" in est.cost_breakdown_explanation.lower() or \
                       "infeasible" in est.estimation_notes.lower()

    def test_infeasible_carrier_capacity_too_small(self):
        ts = {
            "carriers": [
                {"id": "CR_1", "name": "Tiny", "available": True,
                 "cost_per_unit": 5, "transit_time_hours": 24, "capacity_limit": 3},
            ],
            "warehouses": [],
            "customer_zones": [],
        }
        candidates = _make_candidates(ts, order_units=10)
        result = run_cost_agent(ts, candidates)
        exp = [e for e in result.cost_estimates if e.candidate_type == "EXPEDITE"]
        assert len(exp) == 1
        assert exp[0].is_feasible is False
        assert exp[0].total_cost_estimate is None


# ---------------------------------------------------------------------------
# No oracle/evaluation fields
# ---------------------------------------------------------------------------


class TestNoOracleFields:
    """Verify cost agent output never contains evaluation truth fields."""

    _FORBIDDEN_KEYS = {
        "oracle", "ground_truth", "cost_ground_truth",
        "regret", "override", "unnecessary_override",
        "override_effectiveness", "evaluation_verdict",
        "ai_correct", "action_code",
    }

    def test_no_oracle_keys_in_dict(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        d = result.to_dict()
        serialized = json.dumps(d)
        for key in self._FORBIDDEN_KEYS:
            assert f'"{key}"' not in serialized, (
                f"Forbidden evaluation key '{key}' found in cost agent output"
            )

    def test_estimation_notes_mention_not_truth(self):
        candidates = _make_candidates(_STANDARD_TS)
        result = run_cost_agent(_STANDARD_TS, candidates)
        for est in result.cost_estimates:
            if est.is_feasible:
                notes_lower = est.estimation_notes.lower()
                assert "not authoritative" in notes_lower or \
                       "decision-support" in notes_lower


# ---------------------------------------------------------------------------
# Case-driven invocation tests
# ---------------------------------------------------------------------------


class TestCaseDrivenInvocation:
    @pytest.mark.parametrize("case_id", ["M01", "M03", "M05", "M08", "P01"])
    def test_case_produces_valid_cost_output(self, case_id: str):
        ts = _case_twin_state(case_id)
        candidates = _make_candidates(ts)
        result = run_cost_agent(ts, candidates)
        assert len(result.cost_estimates) == len(candidates)
        for est in result.cost_estimates:
            if est.is_feasible:
                assert est.total_cost_estimate is not None
                assert est.total_cost_estimate >= 0
            else:
                assert est.total_cost_estimate is None
