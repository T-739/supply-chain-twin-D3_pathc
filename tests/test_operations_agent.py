"""
test_operations_agent.py — Contract tests for the Operations Agent (Package 2B corrected).

Verifies:
  1. AI/ALT1/ALT2 are never emitted as candidate_type
  2. approve/verify_pause/alternative_plan are never emitted as candidate_type
  3. Ranked candidates come only from {EXPEDITE, TRANSFER, COMPENSATE, NO_ACTION}
  4. Output is structured and stable (OperationsOutput schema)
  5. Rationale includes evidence grounding
  6. Feasibility scores are bounded [0.0, 1.0]
  7. Infeasible candidates are scored 0.0
  8. Real case-driven invocations work
  9. Output is JSON-serializable
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agents.operations_agent import (
    EvidenceRef,
    OperationsOutput,
    RankedCandidate,
    VALID_CANDIDATE_TYPES,
    build_operational_candidates,
    run_operations_agent,
)
from rag_setup import build_vector_store, reset_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag_built():
    """Build the RAG vector store once for the entire test module."""
    reset_store()
    build_vector_store(force_rebuild=True)
    yield
    reset_store()


def _load_case(case_id: str) -> dict:
    path = os.path.join(_DATA_DIR, "cases", f"{case_id}.json")
    with open(path) as f:
        return json.load(f)


def _case_inputs(case_id: str) -> tuple[dict, dict]:
    """Extract twin_state and scenario_context from a case."""
    case = _load_case(case_id)
    twin_state = case.get("initial_state_snapshot", {})
    scenario_context = {
        "scenario_type": case.get("scenario_type", ""),
        "risk_level": case.get("risk_level", ""),
        "exception_description": case.get("exception_description", ""),
    }
    return twin_state, scenario_context


# ---------------------------------------------------------------------------
# Layer separation tests — the core of this corrective patch
# ---------------------------------------------------------------------------


class TestLayerSeparation:
    """Verify operations layer never emits supervision codes."""

    def test_no_ai_alt1_alt2_in_candidate_type(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        for rc in result.ranked_candidates:
            assert rc.candidate_type not in {"AI", "ALT1", "ALT2"}, (
                f"Supervision code '{rc.candidate_type}' leaked into operations layer"
            )

    def test_no_approve_verify_alternative_in_candidate_type(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        for rc in result.ranked_candidates:
            assert rc.candidate_type not in {
                "approve", "verify_pause", "alternative_plan"
            }, (
                f"Decision type '{rc.candidate_type}' leaked into operations layer"
            )

    def test_all_candidates_from_valid_set(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        for rc in result.ranked_candidates:
            assert rc.candidate_type in VALID_CANDIDATE_TYPES, (
                f"Unexpected candidate_type '{rc.candidate_type}'"
            )

    def test_candidate_type_validator_rejects_ai(self):
        with pytest.raises(ValueError, match="supervision code"):
            RankedCandidate(
                candidate_id="bad",
                candidate_type="AI",
                description="test",
                feasibility_score=0.5,
                feasible=True,
                rationale="test",
                evidence_refs=[],
                target_entities={},
            )

    def test_candidate_type_validator_rejects_alt1(self):
        with pytest.raises(ValueError, match="supervision code"):
            RankedCandidate(
                candidate_id="bad",
                candidate_type="ALT1",
                description="test",
                feasibility_score=0.5,
                feasible=True,
                rationale="test",
                evidence_refs=[],
                target_entities={},
            )

    def test_candidate_type_validator_rejects_verify_pause(self):
        with pytest.raises(ValueError, match="decision type"):
            RankedCandidate(
                candidate_id="bad",
                candidate_type="verify_pause",
                description="test",
                feasibility_score=0.5,
                feasible=True,
                rationale="test",
                evidence_refs=[],
                target_entities={},
            )

    def test_candidate_type_validator_rejects_unknown(self):
        with pytest.raises(ValueError, match="must be one of"):
            RankedCandidate(
                candidate_id="bad",
                candidate_type="MAGIC_ACTION",
                description="test",
                feasibility_score=0.5,
                feasible=True,
                rationale="test",
                evidence_refs=[],
                target_entities={},
            )

    @pytest.mark.parametrize("case_id", ["M01", "M03", "M05", "M08", "M12", "P01"])
    def test_no_supervision_codes_across_cases(self, case_id: str):
        ts, sc = _case_inputs(case_id)
        result = run_operations_agent(ts, sc)
        forbidden = {"AI", "ALT1", "ALT2", "approve", "verify_pause", "alternative_plan"}
        for rc in result.ranked_candidates:
            assert rc.candidate_type not in forbidden


# ---------------------------------------------------------------------------
# Candidate bridge tests
# ---------------------------------------------------------------------------


class TestCandidateBridge:
    def test_generates_expedite_candidates(self):
        ts, _ = _case_inputs("M01")
        candidates = build_operational_candidates(ts)
        types = {c["candidate_type"] for c in candidates}
        assert "EXPEDITE" in types

    def test_generates_transfer_candidates(self):
        ts, _ = _case_inputs("M01")
        candidates = build_operational_candidates(ts)
        types = {c["candidate_type"] for c in candidates}
        assert "TRANSFER" in types

    def test_generates_compensate_candidate(self):
        ts, _ = _case_inputs("M01")
        candidates = build_operational_candidates(ts)
        types = {c["candidate_type"] for c in candidates}
        assert "COMPENSATE" in types

    def test_generates_no_action_candidate(self):
        ts, _ = _case_inputs("M01")
        candidates = build_operational_candidates(ts)
        types = {c["candidate_type"] for c in candidates}
        assert "NO_ACTION" in types

    def test_all_candidate_types_valid(self):
        ts, _ = _case_inputs("M01")
        candidates = build_operational_candidates(ts)
        for c in candidates:
            assert c["candidate_type"] in VALID_CANDIDATE_TYPES

    def test_empty_twin_state_produces_baseline_candidates(self):
        candidates = build_operational_candidates({})
        types = {c["candidate_type"] for c in candidates}
        assert "COMPENSATE" in types
        assert "NO_ACTION" in types

    def test_unavailable_carrier_marked_infeasible(self):
        ts = {
            "carriers": [
                {"id": "CR_1", "name": "Down Carrier", "available": False,
                 "cost_per_unit": 5, "transit_time_hours": 24, "capacity_limit": 200},
            ],
            "warehouses": [],
            "customer_zones": [],
        }
        candidates = build_operational_candidates(ts)
        expedites = [c for c in candidates if c["candidate_type"] == "EXPEDITE"]
        assert len(expedites) == 1
        assert expedites[0]["feasible"] is False
        assert "unavailable" in expedites[0]["feasibility_reason"].lower()

    def test_transfer_requires_different_warehouses(self):
        ts, _ = _case_inputs("M01")
        candidates = build_operational_candidates(ts)
        transfers = [c for c in candidates if c["candidate_type"] == "TRANSFER"]
        for t in transfers:
            entities = t["target_entities"]
            assert entities["from_warehouse_id"] != entities["to_warehouse_id"]


# ---------------------------------------------------------------------------
# Output schema tests
# ---------------------------------------------------------------------------


class TestOperationsOutputSchema:
    def test_ranked_candidate_fields(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        for rc in result.ranked_candidates:
            assert hasattr(rc, "candidate_id")
            assert hasattr(rc, "candidate_type")
            assert hasattr(rc, "description")
            assert hasattr(rc, "feasibility_score")
            assert hasattr(rc, "feasible")
            assert hasattr(rc, "rationale")
            assert hasattr(rc, "evidence_refs")
            assert hasattr(rc, "target_entities")

    def test_output_has_metadata(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        assert result.retrieval_query
        assert result.scenario_summary
        assert result.evidence_chunks_used > 0

    def test_json_serializable(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        d = result.to_dict()
        serialized = json.dumps(d)
        roundtrip = json.loads(serialized)
        assert "ranked_candidates" in roundtrip

    def test_to_json_string(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        j = result.to_json()
        parsed = json.loads(j)
        assert len(parsed["ranked_candidates"]) > 0


# ---------------------------------------------------------------------------
# Feasibility score tests
# ---------------------------------------------------------------------------


class TestFeasibilityScores:
    def test_scores_bounded(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        for rc in result.ranked_candidates:
            assert 0.0 <= rc.feasibility_score <= 1.0

    def test_infeasible_candidates_scored_zero(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        for rc in result.ranked_candidates:
            if not rc.feasible:
                assert rc.feasibility_score == 0.0

    def test_feasible_before_infeasible_in_ranking(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        seen_infeasible = False
        for rc in result.ranked_candidates:
            if not rc.feasible:
                seen_infeasible = True
            elif seen_infeasible:
                pytest.fail("Feasible candidate appeared after infeasible")

    def test_score_validation_rejects_out_of_bounds(self):
        with pytest.raises(ValueError, match="feasibility_score"):
            RankedCandidate(
                candidate_id="test",
                candidate_type="EXPEDITE",
                description="Test",
                feasibility_score=1.5,
                feasible=True,
                rationale="test",
                evidence_refs=[],
                target_entities={},
            )


# ---------------------------------------------------------------------------
# Evidence grounding tests
# ---------------------------------------------------------------------------


class TestEvidenceGrounding:
    def test_evidence_refs_present(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        feasible = [rc for rc in result.ranked_candidates if rc.feasible]
        for rc in feasible:
            assert len(rc.evidence_refs) > 0

    def test_evidence_ref_fields(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        ref = result.ranked_candidates[0].evidence_refs[0]
        assert ref.chunk_id
        assert ref.source_doc
        assert isinstance(ref.retrieval_score, float)
        assert ref.excerpt

    def test_rationale_mentions_evidence_source(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        feasible = [rc for rc in result.ranked_candidates if rc.feasible]
        for rc in feasible:
            assert ".md:" in rc.rationale or "evidence" in rc.rationale.lower()

    def test_rationale_mentions_scenario(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        feasible = [rc for rc in result.ranked_candidates if rc.feasible]
        for rc in feasible:
            assert "Inventory Discrepancy" in rc.rationale


# ---------------------------------------------------------------------------
# Cross-case invocation tests
# ---------------------------------------------------------------------------


class TestCrossCaseInvocations:
    @pytest.mark.parametrize("case_id", ["M01", "M03", "M05", "M08", "M12", "P01"])
    def test_case_produces_valid_output(self, case_id: str):
        ts, sc = _case_inputs(case_id)
        result = run_operations_agent(ts, sc)
        assert len(result.ranked_candidates) > 0
        assert result.evidence_chunks_used > 0
        for rc in result.ranked_candidates:
            assert 0.0 <= rc.feasibility_score <= 1.0
            assert rc.candidate_type in VALID_CANDIDATE_TYPES
            assert rc.rationale


# ---------------------------------------------------------------------------
# Order-level feasibility tests (TwinState.apply_action alignment)
# ---------------------------------------------------------------------------


class TestOrderLevelFeasibility:
    """Verify feasibility checks use order_units, not just > 0."""

    def test_expedite_infeasible_when_capacity_lt_order_units(self):
        """Carrier with capacity < order_units must be marked infeasible."""
        ts = {
            "carriers": [
                {"id": "CR_1", "name": "Small Carrier", "available": True,
                 "cost_per_unit": 5, "transit_time_hours": 24, "capacity_limit": 5},
            ],
            "warehouses": [],
            "customer_zones": [],
        }
        # order_units=10 > capacity_limit=5
        candidates = build_operational_candidates(ts, order_units=10)
        expedites = [c for c in candidates if c["candidate_type"] == "EXPEDITE"]
        assert len(expedites) == 1
        assert expedites[0]["feasible"] is False
        assert "capacity" in expedites[0]["feasibility_reason"].lower()
        assert "10" in expedites[0]["feasibility_reason"]

    def test_expedite_feasible_when_capacity_gte_order_units(self):
        """Carrier with capacity >= order_units must be feasible."""
        ts = {
            "carriers": [
                {"id": "CR_1", "name": "Big Carrier", "available": True,
                 "cost_per_unit": 5, "transit_time_hours": 24, "capacity_limit": 200},
            ],
            "warehouses": [],
            "customer_zones": [],
        }
        candidates = build_operational_candidates(ts, order_units=10)
        expedites = [c for c in candidates if c["candidate_type"] == "EXPEDITE"]
        assert expedites[0]["feasible"] is True
        assert expedites[0]["feasibility_reason"] is None

    def test_transfer_infeasible_when_src_inventory_lt_order_units(self):
        """Source warehouse with inventory < order_units must be infeasible."""
        ts = {
            "carriers": [],
            "warehouses": [
                {"id": "WH_1", "name": "Low Stock WH", "location": "A",
                 "max_capacity": 1000, "current_inventory": 5,
                 "operating_cost_per_unit": 1.0},
                {"id": "WH_2", "name": "Target WH", "location": "B",
                 "max_capacity": 1000, "current_inventory": 100,
                 "operating_cost_per_unit": 1.0},
            ],
            "customer_zones": [],
        }
        candidates = build_operational_candidates(ts, order_units=10)
        transfer_1_to_2 = [
            c for c in candidates
            if c["candidate_type"] == "TRANSFER"
            and c["target_entities"]["from_warehouse_id"] == "WH_1"
        ]
        assert len(transfer_1_to_2) == 1
        assert transfer_1_to_2[0]["feasible"] is False
        assert "inventory" in transfer_1_to_2[0]["feasibility_reason"].lower()

    def test_transfer_infeasible_when_dst_headroom_lt_order_units(self):
        """Destination with headroom < order_units must be infeasible."""
        ts = {
            "carriers": [],
            "warehouses": [
                {"id": "WH_1", "name": "Source WH", "location": "A",
                 "max_capacity": 1000, "current_inventory": 500,
                 "operating_cost_per_unit": 1.0},
                {"id": "WH_2", "name": "Full WH", "location": "B",
                 "max_capacity": 100, "current_inventory": 95,
                 "operating_cost_per_unit": 1.0},
            ],
            "customer_zones": [],
        }
        # headroom = 100 - 95 = 5 < order_units=10
        candidates = build_operational_candidates(ts, order_units=10)
        transfer_1_to_2 = [
            c for c in candidates
            if c["candidate_type"] == "TRANSFER"
            and c["target_entities"]["from_warehouse_id"] == "WH_1"
        ]
        assert len(transfer_1_to_2) == 1
        assert transfer_1_to_2[0]["feasible"] is False
        assert "headroom" in transfer_1_to_2[0]["feasibility_reason"].lower()

    def test_transfer_feasible_when_both_constraints_met(self):
        """Transfer feasible when src inv >= units AND dst headroom >= units."""
        ts = {
            "carriers": [],
            "warehouses": [
                {"id": "WH_1", "name": "Good Source", "location": "A",
                 "max_capacity": 1000, "current_inventory": 300,
                 "operating_cost_per_unit": 1.0},
                {"id": "WH_2", "name": "Good Dest", "location": "B",
                 "max_capacity": 600, "current_inventory": 100,
                 "operating_cost_per_unit": 1.0},
            ],
            "customer_zones": [],
        }
        candidates = build_operational_candidates(ts, order_units=10)
        transfer_1_to_2 = [
            c for c in candidates
            if c["candidate_type"] == "TRANSFER"
            and c["target_entities"]["from_warehouse_id"] == "WH_1"
        ]
        assert transfer_1_to_2[0]["feasible"] is True
        assert transfer_1_to_2[0]["feasibility_reason"] is None

    def test_real_case_m01_with_default_order_units(self):
        """M01 baseline: all carriers have capacity >= 10, both WH have inv >= 10."""
        ts, _ = _case_inputs("M01")
        candidates = build_operational_candidates(ts)
        # With baseline order_units=10, all should be feasible for M01
        for c in candidates:
            if c["candidate_type"] in ("EXPEDITE", "TRANSFER"):
                assert c["feasible"] is True, (
                    f"{c['candidate_id']} unexpectedly infeasible: {c['feasibility_reason']}"
                )

    def test_infeasible_expedite_scored_zero_in_full_agent(self):
        """End-to-end: infeasible carrier gets score=0.0 from run_operations_agent."""
        ts = {
            "carriers": [
                {"id": "CR_1", "name": "Tiny Carrier", "available": True,
                 "cost_per_unit": 5, "transit_time_hours": 24, "capacity_limit": 3},
            ],
            "warehouses": [],
            "customer_zones": [],
        }
        sc = {"scenario_type": "Test", "risk_level": "LOW", "exception_description": "test"}
        result = run_operations_agent(ts, sc, order_units=10)
        expedites = [rc for rc in result.ranked_candidates if rc.candidate_type == "EXPEDITE"]
        assert len(expedites) == 1
        assert expedites[0].feasible is False
        assert expedites[0].feasibility_score == 0.0
        assert expedites[0].feasibility_reason is not None


# ---------------------------------------------------------------------------
# Feasibility reason field tests
# ---------------------------------------------------------------------------


class TestFeasibilityReasonField:
    """Verify feasibility_reason is populated correctly."""

    def test_feasible_candidate_has_null_reason(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        for rc in result.ranked_candidates:
            if rc.feasible:
                assert rc.feasibility_reason is None

    def test_infeasible_candidate_has_reason_string(self):
        ts = {
            "carriers": [
                {"id": "CR_1", "name": "Down", "available": False,
                 "cost_per_unit": 5, "transit_time_hours": 24, "capacity_limit": 200},
            ],
            "warehouses": [],
            "customer_zones": [],
        }
        result = run_operations_agent(
            ts,
            {"scenario_type": "Test", "risk_level": "LOW", "exception_description": "test"},
        )
        infeasible = [rc for rc in result.ranked_candidates if not rc.feasible]
        assert len(infeasible) > 0
        for rc in infeasible:
            assert isinstance(rc.feasibility_reason, str)
            assert len(rc.feasibility_reason) > 0

    def test_feasibility_reason_in_json(self):
        ts, sc = _case_inputs("M01")
        result = run_operations_agent(ts, sc)
        d = result.to_dict()
        for rc_dict in d["ranked_candidates"]:
            assert "feasibility_reason" in rc_dict
