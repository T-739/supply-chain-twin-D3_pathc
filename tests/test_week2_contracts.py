"""
test_week2_contracts.py — Minimal tests for Week 2 Package 1 deliverables.

Verifies:
  1. GovernanceOutput contains all 8 required fields
  2. RiskLevel enum validation works (valid + invalid)
  3. GovernanceOutput is JSON-serializable
  4. GraphState can be instantiated with placeholder data
  5. Graph skeleton imports and compiles cleanly
"""

from __future__ import annotations

import json
import sys
import os

import pytest

# Ensure src/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agents.governance_agent import (
    AlternativeAction,
    EvidenceSource,
    GovernanceOutput,
    RiskLevel,
    make_placeholder_governance_output,
)
from graph import GraphState, build_graph, compile_graph


# ---------------------------------------------------------------------------
# GovernanceOutput contract tests
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "risk_level",
    "situational_explanation",
    "recommended_action",
    "evidence_sources",
    "cost_summary",
    "confidence_note",
    "rationale_trace",
    "alternative_actions",
}


class TestGovernanceOutputContract:
    """Verify the frozen governance output schema."""

    def test_all_8_fields_present(self):
        out = make_placeholder_governance_output()
        dumped = out.to_dict()
        assert REQUIRED_FIELDS == set(dumped.keys())

    def test_risk_level_valid_values(self):
        for level in ("LOW", "MEDIUM", "HIGH"):
            out = make_placeholder_governance_output()
            out_dict = out.to_dict()
            out_dict["risk_level"] = level
            parsed = GovernanceOutput(**out_dict)
            assert parsed.risk_level == RiskLevel(level)

    def test_risk_level_case_insensitive(self):
        out_dict = make_placeholder_governance_output().to_dict()
        out_dict["risk_level"] = "low"
        parsed = GovernanceOutput(**out_dict)
        assert parsed.risk_level == RiskLevel.LOW

    def test_risk_level_invalid_rejected(self):
        out_dict = make_placeholder_governance_output().to_dict()
        out_dict["risk_level"] = "CRITICAL"
        with pytest.raises(ValueError):
            GovernanceOutput(**out_dict)

    def test_json_serializable(self):
        out = make_placeholder_governance_output()
        json_str = out.to_json()
        roundtrip = json.loads(json_str)
        assert set(roundtrip.keys()) == REQUIRED_FIELDS

    def test_evidence_sources_must_be_nonempty(self):
        out_dict = make_placeholder_governance_output().to_dict()
        out_dict["evidence_sources"] = []
        with pytest.raises(ValueError, match="at least one"):
            GovernanceOutput(**out_dict)

    def test_evidence_source_is_structured(self):
        out = make_placeholder_governance_output()
        src = out.evidence_sources[0]
        assert hasattr(src, "source_type")
        assert hasattr(src, "field_or_key")
        assert hasattr(src, "value")
        assert hasattr(src, "relevance")

    def test_alternative_actions_schema(self):
        alt = AlternativeAction(
            action_label="Switch carrier",
            description="Use backup carrier CR_2",
            estimated_risk="Moderate — higher cost",
        )
        assert alt.action_label == "Switch carrier"


# ---------------------------------------------------------------------------
# GraphState tests
# ---------------------------------------------------------------------------


class TestGraphState:
    """Verify GraphState can be instantiated and used."""

    def test_instantiate_empty(self):
        state: GraphState = {}
        assert isinstance(state, dict)

    def test_instantiate_with_placeholder_data(self):
        state: GraphState = {
            "case_id": "M01",
            "scenario_id": "inventory_discrepancy",
            "scenario_context": {"risk_level": "LOW"},
            "twin_state": {},
            "allowed_operational_actions": [],
            "operations_output": {},
            "cost_output": {},
            "governance_output": {},
            "supervisor_decision": "AI",
            "final_decision_code": "AI",
            "evaluation_result": {},
            "trace_log": [],
        }
        assert state["case_id"] == "M01"
        assert state["supervisor_decision"] == "AI"

    def test_trace_log_appendable(self):
        state: GraphState = {"trace_log": []}
        state["trace_log"].append({"node": "test", "status": "ok"})
        assert len(state["trace_log"]) == 1


# ---------------------------------------------------------------------------
# Graph skeleton tests
# ---------------------------------------------------------------------------


class TestGraphSkeleton:
    """Verify graph builds and compiles without errors."""

    def test_build_graph(self):
        g = build_graph()
        assert g is not None

    def test_compile_graph(self):
        runnable = compile_graph()
        assert runnable is not None

    def test_graph_has_expected_nodes(self):
        g = build_graph()
        expected_nodes = {
            "load_case_or_scenario",
            "inject_scenario",
            "operations_agent",
            "cost_agent",
            "governance_agent",
            "supervisor",
            "evaluation",
        }
        # StateGraph stores nodes in .nodes dict
        assert expected_nodes.issubset(set(g.nodes.keys()))

    def test_invoke_with_case_id(self):
        """Run the full stub graph with a real case ID to verify end-to-end flow."""
        runnable = compile_graph()
        result = runnable.invoke({"case_id": "M01"})
        assert result["case_id"] == "M01"
        assert result["scenario_id"] == "inventory_discrepancy"
        assert "governance_output" in result
        assert result["governance_output"]["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
        # Supervisor now produces APPROVE/VERIFY/OVERRIDE (supervision layer)
        assert result["supervisor_decision"] in {"APPROVE", "VERIFY", "OVERRIDE"}
        assert "supervisor_output" in result
        assert len(result["trace_log"]) == 7  # one per node
