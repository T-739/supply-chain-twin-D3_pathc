"""
test_governance_synthesis.py — Tests for Governance Agent synthesis (Package 2D).

Verifies:
  1. GovernanceOutput 8 required fields present and well-formed
  2. recommended_action refers to operational candidate, never AI/ALT1/ALT2
  3. alternative_actions exclude the recommended candidate
  4. evidence_sources structured with required sub-fields
  5. cost_summary uses estimate language, never claims evaluation truth
  6. No oracle/evaluation fields in output
  7. Case-driven end-to-end invocation through full graph
  8. Determinism: same inputs produce same output
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agents.governance_agent import (
    AlternativeAction,
    EvidenceSource,
    GovernanceOutput,
    RiskLevel,
    run_governance_agent,
)
from agents.operations_agent import build_operational_candidates, run_operations_agent
from agents.cost_agent import run_cost_agent
from rag_setup import build_vector_store, reset_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag_built():
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


# Standard test twin_state with known values (same as cost_agent tests)
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

_STANDARD_SCENARIO = {
    "scenario_type": "carrier_delay",
    "risk_level": "MEDIUM",
    "exception_description": "Primary carrier delayed; shipment at risk of SLA breach.",
}


def _make_synthesis_inputs(
    twin_state: dict = None,
    scenario_context: dict = None,
):
    """Produce (scenario_context, ops_output_dict, cost_output_dict) for synthesis."""
    ts = twin_state or _STANDARD_TS
    sc = scenario_context or _STANDARD_SCENARIO

    ops_out = run_operations_agent(ts, sc)
    ops_dict = ops_out.to_dict()

    candidates = ops_dict["ranked_candidates"]
    cost_out = run_cost_agent(ts, candidates)
    cost_dict = cost_out.to_dict()

    return sc, ops_dict, cost_dict


# ---------------------------------------------------------------------------
# Output schema tests
# ---------------------------------------------------------------------------


class TestGovernanceOutputSchema:
    def test_all_8_fields_present(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        assert isinstance(result.risk_level, RiskLevel)
        assert isinstance(result.situational_explanation, str) and len(result.situational_explanation) > 0
        assert isinstance(result.recommended_action, str) and len(result.recommended_action) > 0
        assert isinstance(result.evidence_sources, list) and len(result.evidence_sources) >= 1
        assert isinstance(result.cost_summary, str) and len(result.cost_summary) > 0
        assert isinstance(result.confidence_note, str) and len(result.confidence_note) > 0
        assert isinstance(result.rationale_trace, str) and len(result.rationale_trace) > 0
        assert isinstance(result.alternative_actions, list)

    def test_json_serializable(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        d = result.to_dict()
        serialized = json.dumps(d)
        roundtrip = json.loads(serialized)
        assert "risk_level" in roundtrip
        assert "recommended_action" in roundtrip
        assert "evidence_sources" in roundtrip

    def test_to_json_roundtrip(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        j = result.to_json()
        parsed = json.loads(j)
        assert len(parsed["evidence_sources"]) >= 1

    def test_evidence_sources_have_required_subfields(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        for es in result.evidence_sources:
            assert isinstance(es, EvidenceSource)
            assert es.source_type
            assert es.field_or_key
            assert es.relevance


# ---------------------------------------------------------------------------
# Layer separation tests
# ---------------------------------------------------------------------------


class TestLayerSeparation:
    """recommended_action must be operational, never AI/ALT1/ALT2."""

    _FORBIDDEN = {"AI", "ALT1", "ALT2"}

    def test_recommended_action_not_supervision_code(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        action = result.recommended_action
        # The recommended_action string should not be just a supervision code
        assert action not in self._FORBIDDEN

    def test_recommended_action_is_operational_type(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        action = result.recommended_action.upper()
        # Must contain one of the operational types
        operational_types = {"EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"}
        assert any(ot in action for ot in operational_types), (
            f"recommended_action '{result.recommended_action}' "
            f"does not reference an operational type"
        )

    def test_alternative_labels_not_supervision_codes(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        for alt in result.alternative_actions:
            assert alt.action_label not in self._FORBIDDEN


# ---------------------------------------------------------------------------
# Alternative actions tests
# ---------------------------------------------------------------------------


class TestAlternativeActions:
    def test_alternatives_exclude_recommended(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        rec = result.recommended_action
        for alt in result.alternative_actions:
            # The alt label should not be the same as recommended
            assert alt.action_label != rec

    def test_alternatives_have_required_fields(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        for alt in result.alternative_actions:
            assert isinstance(alt, AlternativeAction)
            assert alt.action_label
            assert alt.description
            assert alt.estimated_risk

    def test_alternatives_capped_at_4(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        assert len(result.alternative_actions) <= 4


# ---------------------------------------------------------------------------
# Cost summary language tests
# ---------------------------------------------------------------------------


class TestCostSummaryLanguage:
    def test_cost_summary_uses_estimate_language(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        lower = result.cost_summary.lower()
        assert "estimate" in lower, (
            "cost_summary must use estimate-oriented language"
        )

    def test_cost_summary_disclaims_evaluation_truth(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        lower = result.cost_summary.lower()
        assert "not authoritative" in lower or "decision-support" in lower, (
            "cost_summary must disclaim being evaluation truth"
        )


# ---------------------------------------------------------------------------
# No oracle fields tests
# ---------------------------------------------------------------------------


class TestNoOracleFields:
    _FORBIDDEN_KEYS = {
        "oracle", "ground_truth", "cost_ground_truth",
        "regret", "override", "unnecessary_override",
        "override_effectiveness", "evaluation_verdict",
        "ai_correct", "action_code",
    }

    def test_no_oracle_keys_in_serialized_output(self):
        sc, ops, cost = _make_synthesis_inputs()
        result = run_governance_agent(sc, ops, cost)
        serialized = json.dumps(result.to_dict())
        for key in self._FORBIDDEN_KEYS:
            assert f'"{key}"' not in serialized, (
                f"Forbidden evaluation key '{key}' found in governance output"
            )


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_output(self):
        sc, ops, cost = _make_synthesis_inputs()
        r1 = run_governance_agent(sc, ops, cost)
        r2 = run_governance_agent(sc, ops, cost)
        assert r1.to_dict() == r2.to_dict()


# ---------------------------------------------------------------------------
# Risk level tests
# ---------------------------------------------------------------------------


class TestRiskLevel:
    def test_high_risk_scenario_produces_high(self):
        high_scenario = dict(_STANDARD_SCENARIO, risk_level="HIGH")
        sc, ops, cost = _make_synthesis_inputs(scenario_context=high_scenario)
        result = run_governance_agent(sc, ops, cost)
        assert result.risk_level == RiskLevel.HIGH

    def test_low_risk_scenario_not_escalated_unnecessarily(self):
        low_scenario = dict(_STANDARD_SCENARIO, risk_level="LOW")
        sc, ops, cost = _make_synthesis_inputs(scenario_context=low_scenario)
        result = run_governance_agent(sc, ops, cost)
        assert result.risk_level in {RiskLevel.LOW, RiskLevel.MEDIUM}


# ---------------------------------------------------------------------------
# Case-driven end-to-end tests
# ---------------------------------------------------------------------------


class TestCaseDrivenEndToEnd:
    @pytest.mark.parametrize("case_id", ["M01", "M03", "M05", "M08", "P01"])
    def test_case_produces_valid_governance_output(self, case_id: str):
        case = _load_case(case_id)
        ts = case.get("initial_state_snapshot", {})
        sc = {
            "scenario_type": case.get("scenario_type", ""),
            "risk_level": case.get("risk_level", ""),
            "exception_description": case.get("exception_description", ""),
        }

        ops_out = run_operations_agent(ts, sc)
        ops_dict = ops_out.to_dict()
        candidates = ops_dict["ranked_candidates"]
        cost_out = run_cost_agent(ts, candidates)
        cost_dict = cost_out.to_dict()

        result = run_governance_agent(sc, ops_dict, cost_dict)

        # All 8 fields present and non-empty
        assert result.risk_level in RiskLevel
        assert len(result.situational_explanation) > 0
        assert len(result.recommended_action) > 0
        assert len(result.evidence_sources) >= 1
        assert len(result.cost_summary) > 0
        assert len(result.confidence_note) > 0
        assert len(result.rationale_trace) > 0
        # alternative_actions can be empty if only 1 feasible candidate


# ---------------------------------------------------------------------------
# Full graph integration test
# ---------------------------------------------------------------------------


class TestGraphIntegration:
    def test_graph_invocation_produces_governance_output(self):
        """Run the full graph with a case and verify governance_output is synthesized."""
        from graph import compile_graph

        graph = compile_graph()
        result = graph.invoke({"case_id": "M01"})

        gov = result.get("governance_output", {})
        assert gov.get("risk_level") in {"LOW", "MEDIUM", "HIGH"}
        assert len(gov.get("recommended_action", "")) > 0
        assert len(gov.get("evidence_sources", [])) >= 1
        assert len(gov.get("cost_summary", "")) > 0
        assert len(gov.get("rationale_trace", "")) > 0

        # Verify trace log shows governance as done, not placeholder
        trace = result.get("trace_log", [])
        gov_entries = [t for t in trace if t.get("node") == "governance_agent"]
        assert any(t["status"] == "done" for t in gov_entries)

    def test_graph_governance_node_not_placeholder(self):
        """Confirm the governance node produces real synthesis, not the stub."""
        from graph import compile_graph

        graph = compile_graph()
        result = graph.invoke({"case_id": "M03"})

        gov = result.get("governance_output", {})
        # Placeholder uses "Placeholder" in situational_explanation
        assert "Placeholder" not in gov.get("situational_explanation", "")
        assert "stub" not in gov.get("rationale_trace", "").lower()
