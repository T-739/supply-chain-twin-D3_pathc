"""
test_supervisor.py — Tests for the Supervisor node (approve / verify / override).

Verifies:
  1. APPROVE selects the recommended operational candidate
  2. VERIFY sets review_requested=True and does not become an operational action
  3. OVERRIDE selects one alternative operational candidate
  4. Supervisor never emits AI/ALT1/ALT2 as candidate identities
  5. SupervisorDecision has all required fields
  6. Determinism: same input gives same output
  7. End-to-end graph invocation for all 3 modes
  8. Layer separation maintained
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from supervisor import (
    SupervisorDecision,
    SupervisorDecisionType,
    SupervisorInstruction,
    build_governance_meta,
    run_supervisor,
)
from agents.governance_agent import run_governance_agent_with_meta
from agents.operations_agent import run_operations_agent
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


# Standard test twin_state
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


def _make_supervisor_inputs(twin_state=None, scenario_context=None):
    """Build (governance_output_dict, governance_meta_dict) for supervisor tests."""
    ts = twin_state or _STANDARD_TS
    sc = scenario_context or _STANDARD_SCENARIO

    ops = run_operations_agent(ts, sc)
    ops_d = ops.to_dict()
    candidates = ops_d["ranked_candidates"]
    cost = run_cost_agent(ts, candidates)
    cost_d = cost.to_dict()

    gov, meta = run_governance_agent_with_meta(sc, ops_d, cost_d)
    return gov.to_dict(), meta


# ---------------------------------------------------------------------------
# Instruction validation tests
# ---------------------------------------------------------------------------


class TestSupervisorInstruction:
    def test_valid_modes(self):
        for mode in ("approve", "verify", "override"):
            inst = SupervisorInstruction(mode=mode)
            assert inst.mode == mode

    def test_case_insensitive_mode(self):
        inst = SupervisorInstruction(mode="APPROVE")
        assert inst.mode == "approve"

    def test_invalid_mode_rejected(self):
        with pytest.raises(Exception):
            SupervisorInstruction(mode="AI")

    def test_invalid_mode_alt1(self):
        with pytest.raises(Exception):
            SupervisorInstruction(mode="ALT1")


# ---------------------------------------------------------------------------
# APPROVE path tests
# ---------------------------------------------------------------------------


class TestApprovePath:
    def test_approve_selects_recommended(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "approve"})
        assert decision.supervisor_decision_type == SupervisorDecisionType.APPROVE
        assert decision.selected_candidate_id == meta["recommended_candidate_id"]
        assert decision.selected_candidate_type == meta["recommended_candidate_type"]

    def test_approve_no_override(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "approve"})
        assert decision.override_from_recommendation is False

    def test_approve_no_review(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "approve"})
        assert decision.review_requested is False

    def test_approve_default_when_no_instruction(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, None)
        assert decision.supervisor_decision_type == SupervisorDecisionType.APPROVE

    def test_approve_has_rationale(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "approve"})
        assert len(decision.decision_rationale) > 0
        assert "approve" in decision.decision_rationale.lower()


# ---------------------------------------------------------------------------
# VERIFY path tests
# ---------------------------------------------------------------------------


class TestVerifyPath:
    def test_verify_sets_review_requested(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "verify"})
        assert decision.supervisor_decision_type == SupervisorDecisionType.VERIFY
        assert decision.review_requested is True

    def test_verify_preserves_recommendation(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "verify"})
        # VERIFY keeps the current recommendation provisionally
        assert decision.selected_candidate_id == meta["recommended_candidate_id"]
        assert decision.selected_candidate_type == meta["recommended_candidate_type"]

    def test_verify_no_override(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "verify"})
        assert decision.override_from_recommendation is False

    def test_verify_has_review_focus(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "verify"})
        assert len(decision.review_focus) > 0

    def test_verify_custom_focus(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {
            "mode": "verify",
            "review_focus": "Confirm carrier availability with dispatch.",
        })
        assert "carrier availability" in decision.review_focus.lower()

    def test_verify_is_not_operational_action(self):
        """VERIFY is a supervision decision, not an operational candidate type."""
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "verify"})
        # The decision type is VERIFY (supervision layer)
        assert decision.supervisor_decision_type.value == "VERIFY"
        # It does NOT change the candidate_type to VERIFY
        assert decision.selected_candidate_type != "VERIFY"


# ---------------------------------------------------------------------------
# OVERRIDE path tests
# ---------------------------------------------------------------------------


class TestOverridePath:
    def test_override_selects_alternative(self):
        gov_d, meta = _make_supervisor_inputs()
        assert len(meta["alternatives"]) > 0, "Need alternatives for override test"
        decision = run_supervisor(gov_d, meta, {"mode": "override"})
        assert decision.supervisor_decision_type == SupervisorDecisionType.OVERRIDE
        assert decision.override_from_recommendation is True
        # Selected candidate must differ from recommendation
        assert decision.selected_candidate_id != meta["recommended_candidate_id"]

    def test_override_picks_named_target(self):
        gov_d, meta = _make_supervisor_inputs()
        # Pick a specific alternative by label
        target_label = meta["alternatives"][0]["action_label"]
        target_id = meta["alternatives"][0]["candidate_id"]
        decision = run_supervisor(gov_d, meta, {
            "mode": "override",
            "target_action_label": target_label,
        })
        assert decision.selected_candidate_id == target_id

    def test_override_by_candidate_id(self):
        gov_d, meta = _make_supervisor_inputs()
        target_id = meta["alternatives"][0]["candidate_id"]
        decision = run_supervisor(gov_d, meta, {
            "mode": "override",
            "target_action_label": target_id,
        })
        assert decision.selected_candidate_id == target_id

    def test_override_falls_back_to_first_alt(self):
        gov_d, meta = _make_supervisor_inputs()
        # No target_action_label → picks first alternative
        decision = run_supervisor(gov_d, meta, {
            "mode": "override",
            "target_action_label": "",
        })
        assert decision.selected_candidate_id == meta["alternatives"][0]["candidate_id"]

    def test_override_selects_operational_candidate_type(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "override"})
        valid_types = {"EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"}
        assert decision.selected_candidate_type in valid_types

    def test_override_no_alternatives_falls_back_to_approve(self):
        """When no alternatives exist, override falls back to approve."""
        gov_d, meta = _make_supervisor_inputs()
        meta_no_alts = dict(meta, alternatives=[])
        decision = run_supervisor(gov_d, meta_no_alts, {"mode": "override"})
        # Falls back to APPROVE since override is impossible
        assert decision.supervisor_decision_type == SupervisorDecisionType.APPROVE
        assert decision.override_from_recommendation is False

    def test_override_has_rationale(self):
        gov_d, meta = _make_supervisor_inputs()
        decision = run_supervisor(gov_d, meta, {"mode": "override"})
        assert len(decision.decision_rationale) > 0
        assert "override" in decision.decision_rationale.lower()


# ---------------------------------------------------------------------------
# Layer separation tests
# ---------------------------------------------------------------------------


class TestLayerSeparation:
    """Supervisor must never emit AI/ALT1/ALT2 as candidate identities."""

    _FORBIDDEN = {"AI", "ALT1", "ALT2"}

    def test_approve_no_forbidden_ids(self):
        gov_d, meta = _make_supervisor_inputs()
        d = run_supervisor(gov_d, meta, {"mode": "approve"})
        assert d.selected_candidate_id not in self._FORBIDDEN
        assert d.selected_candidate_type not in self._FORBIDDEN

    def test_verify_no_forbidden_ids(self):
        gov_d, meta = _make_supervisor_inputs()
        d = run_supervisor(gov_d, meta, {"mode": "verify"})
        assert d.selected_candidate_id not in self._FORBIDDEN
        assert d.selected_candidate_type not in self._FORBIDDEN

    def test_override_no_forbidden_ids(self):
        gov_d, meta = _make_supervisor_inputs()
        d = run_supervisor(gov_d, meta, {"mode": "override"})
        assert d.selected_candidate_id not in self._FORBIDDEN
        assert d.selected_candidate_type not in self._FORBIDDEN

    def test_decision_type_is_supervision_not_operational(self):
        """APPROVE/VERIFY/OVERRIDE are supervision types, not EXPEDITE etc."""
        gov_d, meta = _make_supervisor_inputs()
        for mode in ("approve", "verify", "override"):
            d = run_supervisor(gov_d, meta, {"mode": mode})
            assert d.supervisor_decision_type.value in {"APPROVE", "VERIFY", "OVERRIDE"}
            # Not operational types
            assert d.supervisor_decision_type.value not in {
                "EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"
            }

    def test_pydantic_rejects_forbidden_candidate_id(self):
        with pytest.raises(Exception):
            SupervisorDecision(
                supervisor_decision_type=SupervisorDecisionType.APPROVE,
                selected_candidate_id="AI",
                selected_candidate_type="EXPEDITE",
                decision_rationale="test",
                review_requested=False,
                review_focus="",
                override_from_recommendation=False,
            )

    def test_pydantic_rejects_forbidden_candidate_type(self):
        with pytest.raises(Exception):
            SupervisorDecision(
                supervisor_decision_type=SupervisorDecisionType.APPROVE,
                selected_candidate_id="CR_1",
                selected_candidate_type="ALT2",
                decision_rationale="test",
                review_requested=False,
                review_focus="",
                override_from_recommendation=False,
            )


# ---------------------------------------------------------------------------
# Output schema tests
# ---------------------------------------------------------------------------


class TestOutputSchema:
    def test_all_fields_present(self):
        gov_d, meta = _make_supervisor_inputs()
        d = run_supervisor(gov_d, meta, {"mode": "approve"})
        assert hasattr(d, "supervisor_decision_type")
        assert hasattr(d, "selected_candidate_id")
        assert hasattr(d, "selected_candidate_type")
        assert hasattr(d, "decision_rationale")
        assert hasattr(d, "review_requested")
        assert hasattr(d, "review_focus")
        assert hasattr(d, "override_from_recommendation")

    def test_json_serializable(self):
        gov_d, meta = _make_supervisor_inputs()
        d = run_supervisor(gov_d, meta, {"mode": "approve"})
        serialized = json.dumps(d.to_dict())
        roundtrip = json.loads(serialized)
        assert "supervisor_decision_type" in roundtrip

    def test_to_json_roundtrip(self):
        gov_d, meta = _make_supervisor_inputs()
        d = run_supervisor(gov_d, meta, {"mode": "override"})
        parsed = json.loads(d.to_json())
        assert parsed["override_from_recommendation"] is True

    def test_no_oracle_fields(self):
        forbidden = {
            "oracle", "ground_truth", "cost_ground_truth",
            "regret", "unnecessary_override", "override_effectiveness",
            "evaluation_verdict", "ai_correct", "action_code",
        }
        gov_d, meta = _make_supervisor_inputs()
        for mode in ("approve", "verify", "override"):
            d = run_supervisor(gov_d, meta, {"mode": mode})
            serialized = json.dumps(d.to_dict())
            for key in forbidden:
                assert f'"{key}"' not in serialized


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_output(self):
        gov_d, meta = _make_supervisor_inputs()
        r1 = run_supervisor(gov_d, meta, {"mode": "approve"})
        r2 = run_supervisor(gov_d, meta, {"mode": "approve"})
        assert r1.to_dict() == r2.to_dict()

    def test_override_deterministic(self):
        gov_d, meta = _make_supervisor_inputs()
        r1 = run_supervisor(gov_d, meta, {"mode": "override"})
        r2 = run_supervisor(gov_d, meta, {"mode": "override"})
        assert r1.to_dict() == r2.to_dict()


# ---------------------------------------------------------------------------
# Governance meta tests
# ---------------------------------------------------------------------------


class TestGovernanceMeta:
    def test_meta_has_recommended_identity(self):
        gov_d, meta = _make_supervisor_inputs()
        assert meta["recommended_candidate_id"] is not None
        assert meta["recommended_candidate_type"] is not None

    def test_meta_alternatives_have_identity(self):
        gov_d, meta = _make_supervisor_inputs()
        for alt in meta["alternatives"]:
            assert "candidate_id" in alt
            assert "candidate_type" in alt
            assert "action_label" in alt

    def test_meta_alternatives_exclude_recommended(self):
        gov_d, meta = _make_supervisor_inputs()
        rec_id = meta["recommended_candidate_id"]
        for alt in meta["alternatives"]:
            assert alt["candidate_id"] != rec_id


# ---------------------------------------------------------------------------
# End-to-end graph integration tests
# ---------------------------------------------------------------------------


class TestGraphIntegration:
    def test_graph_approve(self):
        from graph import compile_graph
        graph = compile_graph()
        result = graph.invoke({
            "case_id": "M01",
            "supervisor_instruction": {"mode": "approve"},
        })

        sup = result.get("supervisor_output", {})
        assert sup["supervisor_decision_type"] == "APPROVE"
        assert sup["selected_candidate_id"] is not None
        assert sup["override_from_recommendation"] is False

        trace = result.get("trace_log", [])
        sup_entries = [t for t in trace if t["node"] == "supervisor"]
        assert any(t["status"] == "done" for t in sup_entries)

    def test_graph_verify(self):
        from graph import compile_graph
        graph = compile_graph()
        result = graph.invoke({
            "case_id": "M01",
            "supervisor_instruction": {
                "mode": "verify",
                "review_focus": "Check carrier capacity.",
            },
        })

        sup = result.get("supervisor_output", {})
        assert sup["supervisor_decision_type"] == "VERIFY"
        assert sup["review_requested"] is True
        assert "carrier capacity" in sup["review_focus"].lower()

    def test_graph_override(self):
        from graph import compile_graph
        graph = compile_graph()
        result = graph.invoke({
            "case_id": "M01",
            "supervisor_instruction": {"mode": "override"},
        })

        sup = result.get("supervisor_output", {})
        assert sup["supervisor_decision_type"] == "OVERRIDE"
        assert sup["override_from_recommendation"] is True
        # Selected candidate must be an operational type
        assert sup["selected_candidate_type"] in {
            "EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"
        }

    def test_graph_default_approve_no_instruction(self):
        """Without supervisor_instruction, defaults to APPROVE."""
        from graph import compile_graph
        graph = compile_graph()
        result = graph.invoke({"case_id": "M01"})

        sup = result.get("supervisor_output", {})
        assert sup["supervisor_decision_type"] == "APPROVE"

    def test_graph_trace_log_complete(self):
        from graph import compile_graph
        graph = compile_graph()
        result = graph.invoke({
            "case_id": "M03",
            "supervisor_instruction": {"mode": "approve"},
        })

        trace = result.get("trace_log", [])
        node_names = [t["node"] for t in trace]
        assert "load_case_or_scenario" in node_names
        assert "operations_agent" in node_names
        assert "cost_agent" in node_names
        assert "governance_agent" in node_names
        assert "supervisor" in node_names
        assert "evaluation" in node_names


# ---------------------------------------------------------------------------
# Case-driven tests across different risk profiles
# ---------------------------------------------------------------------------


class TestCaseDriven:
    @pytest.mark.parametrize("case_id", ["M01", "M05", "P01"])
    def test_approve_across_cases(self, case_id: str):
        case = _load_case(case_id)
        ts = case.get("initial_state_snapshot", {})
        sc = {
            "scenario_type": case.get("scenario_type", ""),
            "risk_level": case.get("risk_level", ""),
            "exception_description": case.get("exception_description", ""),
        }

        ops = run_operations_agent(ts, sc)
        ops_d = ops.to_dict()
        cost = run_cost_agent(ts, ops_d["ranked_candidates"])
        cost_d = cost.to_dict()

        from agents.governance_agent import run_governance_agent_with_meta
        gov, meta = run_governance_agent_with_meta(sc, ops_d, cost_d)
        gov_d = gov.to_dict()

        decision = run_supervisor(gov_d, meta, {"mode": "approve"})
        assert decision.supervisor_decision_type == SupervisorDecisionType.APPROVE
        assert decision.selected_candidate_id == meta["recommended_candidate_id"]

    @pytest.mark.parametrize("case_id", ["M01", "M05", "P01"])
    def test_override_across_cases(self, case_id: str):
        case = _load_case(case_id)
        ts = case.get("initial_state_snapshot", {})
        sc = {
            "scenario_type": case.get("scenario_type", ""),
            "risk_level": case.get("risk_level", ""),
            "exception_description": case.get("exception_description", ""),
        }

        ops = run_operations_agent(ts, sc)
        ops_d = ops.to_dict()
        cost = run_cost_agent(ts, ops_d["ranked_candidates"])
        cost_d = cost.to_dict()

        from agents.governance_agent import run_governance_agent_with_meta
        gov, meta = run_governance_agent_with_meta(sc, ops_d, cost_d)
        gov_d = gov.to_dict()

        decision = run_supervisor(gov_d, meta, {"mode": "override"})
        if meta["alternatives"]:
            assert decision.supervisor_decision_type == SupervisorDecisionType.OVERRIDE
            assert decision.selected_candidate_id != meta["recommended_candidate_id"]
        else:
            # No alternatives → falls back to approve
            assert decision.supervisor_decision_type == SupervisorDecisionType.APPROVE
