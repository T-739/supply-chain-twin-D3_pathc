"""
tests/test_execution_adapters.py — D3-Demo Phase 3: Execution adapter tests.

Covers:
  - Each of the 4 adapters produces a valid ExecutionOutcome
  - Deterministic: same input → same output
  - action_taken only in the operational layer
  - Dispatcher routes correctly
  - Invalid / missing governance action raises GovernanceActionParseError
  - Infeasible execution raises ExecutionInfeasibleError
  - apply_action_outcome re-applies state_delta atomically
"""

import os
import sys
from datetime import datetime, timezone

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from execution_adapters import (
    ExecutionInfeasibleError,
    GovernanceActionParseError,
    execute_action,
    execute_compensate,
    execute_expedite,
    execute_no_action,
    execute_transfer,
)
from outcome_schema import ExecutionOutcome
from twin_state import TwinState

_TS = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
_BASELINE = os.path.join(_PROJECT_DIR, "data", "configs", "baseline_network.json")


@pytest.fixture
def baseline():
    return TwinState.initialize_from_config(_BASELINE)


# ===========================================================================
# Per-adapter tests
# ===========================================================================


class TestExpedite:
    def test_basic_expedite(self, baseline):
        new_state, outcome = execute_expedite(
            baseline, event_id="E1", timestamp=_TS,
        )
        assert isinstance(outcome, ExecutionOutcome)
        assert outcome.action_taken == "EXPEDITE"
        assert outcome.status == "EXECUTED"
        assert outcome.cost_incurred >= 0
        assert outcome.event_id == "E1"
        # Carrier should have switched (baseline planned=CR_1, so now CR_2)
        assert new_state.planned_carrier_id != baseline.planned_carrier_id
        # Input unchanged
        assert baseline.planned_carrier_id == "CR_1"

    def test_deterministic(self, baseline):
        a = execute_expedite(baseline, event_id="E1", timestamp=_TS)[1]
        b = execute_expedite(baseline, event_id="E1", timestamp=_TS)[1]
        assert a.cost_incurred == b.cost_incurred
        assert a.action_taken == b.action_taken
        assert a.state_delta == b.state_delta

    def test_infeasible_when_no_alternate_carrier(self, baseline):
        # Disable CR_2 so no alternate exists
        baseline.carriers["CR_2"].available = False
        with pytest.raises(ExecutionInfeasibleError, match="no alternate"):
            execute_expedite(baseline, event_id="E1", timestamp=_TS)

    def test_state_delta_has_patches(self, baseline):
        _, outcome = execute_expedite(baseline, event_id="E1", timestamp=_TS)
        assert outcome.state_delta["action_type"] == "EXPEDITE"
        patches = outcome.state_delta.get("patches", [])
        fields = {p["field"] for p in patches}
        assert "planned_carrier_id" in fields
        assert "planned_eta_hours" in fields


class TestTransfer:
    def test_basic_transfer(self, baseline):
        new_state, outcome = execute_transfer(
            baseline, event_id="E2", timestamp=_TS,
        )
        assert outcome.action_taken == "TRANSFER"
        assert outcome.status == "EXECUTED"
        # Inventory moved WH_1 → WH_2
        src_before = baseline.warehouses["WH_1"].current_inventory
        dst_before = baseline.warehouses["WH_2"].current_inventory
        units = baseline.order_units
        assert new_state.warehouses["WH_1"].current_inventory == src_before - units
        assert new_state.warehouses["WH_2"].current_inventory == dst_before + units
        # Input unchanged
        assert baseline.warehouses["WH_1"].current_inventory == src_before

    def test_deterministic(self, baseline):
        a = execute_transfer(baseline, event_id="E2", timestamp=_TS)[1]
        b = execute_transfer(baseline, event_id="E2", timestamp=_TS)[1]
        assert a.cost_incurred == b.cost_incurred
        assert a.state_delta == b.state_delta

    def test_infeasible_when_source_empty(self, baseline):
        # Reduce source inventory below order_units
        baseline.warehouses["WH_1"].current_inventory = 0
        with pytest.raises(ExecutionInfeasibleError, match="TRANSFER infeasible"):
            execute_transfer(baseline, event_id="E2", timestamp=_TS)


class TestCompensate:
    def test_basic_compensate(self, baseline):
        new_state, outcome = execute_compensate(
            baseline, event_id="E3", timestamp=_TS,
        )
        assert outcome.action_taken == "COMPENSATE"
        assert outcome.status == "EXECUTED"
        # Logistics unchanged
        assert new_state.planned_carrier_id == baseline.planned_carrier_id
        assert new_state.planned_eta_hours == baseline.planned_eta_hours
        # No physical patches
        assert outcome.state_delta["patches"] == []

    def test_deterministic(self, baseline):
        a = execute_compensate(baseline, event_id="E3", timestamp=_TS)[1]
        b = execute_compensate(baseline, event_id="E3", timestamp=_TS)[1]
        assert a.cost_incurred == b.cost_incurred


class TestNoAction:
    def test_basic_no_action(self, baseline):
        new_state, outcome = execute_no_action(
            baseline, event_id="E4", timestamp=_TS,
        )
        assert outcome.action_taken == "NO_ACTION"
        assert outcome.status == "EXECUTED"
        assert outcome.cost_incurred >= 0
        assert outcome.state_delta["patches"] == []

    def test_deterministic(self, baseline):
        a = execute_no_action(baseline, event_id="E4", timestamp=_TS)[1]
        b = execute_no_action(baseline, event_id="E4", timestamp=_TS)[1]
        assert a.cost_incurred == b.cost_incurred


# ===========================================================================
# Dispatcher tests
# ===========================================================================


class TestDispatcher:
    def test_dispatch_via_meta(self, baseline):
        """governance_meta takes priority for routing."""
        gov = {"recommended_action": "some text"}
        meta = {"recommended_candidate_type": "EXPEDITE",
                "recommended_candidate_id": "EXPEDITE_CR_2"}
        _, outcome = execute_action(
            gov, baseline, event_id="E5", governance_meta=meta, timestamp=_TS,
        )
        assert outcome.action_taken == "EXPEDITE"

    def test_dispatch_via_recommended_action_prefix(self, baseline):
        gov = {"recommended_action": "TRANSFER: Move to WH_2"}
        _, outcome = execute_action(
            gov, baseline, event_id="E6", timestamp=_TS,
        )
        assert outcome.action_taken == "TRANSFER"

    def test_dispatch_no_action(self, baseline):
        gov = {"recommended_action": "NO_ACTION"}
        _, outcome = execute_action(
            gov, baseline, event_id="E7", timestamp=_TS,
        )
        assert outcome.action_taken == "NO_ACTION"

    def test_parse_error_on_missing_action(self, baseline):
        with pytest.raises(GovernanceActionParseError):
            execute_action({}, baseline, event_id="E8", timestamp=_TS)

    def test_parse_error_on_unknown_action(self, baseline):
        gov = {"recommended_action": "ESCALATE_TO_CEO"}
        with pytest.raises(GovernanceActionParseError):
            execute_action(gov, baseline, event_id="E9", timestamp=_TS)

    def test_parse_error_rejects_supervision_layer(self, baseline):
        """APPROVE/VERIFY/OVERRIDE are not operational; must be rejected."""
        meta = {"recommended_candidate_type": "APPROVE"}
        with pytest.raises(GovernanceActionParseError, match="operational-layer"):
            execute_action({}, baseline, event_id="E10",
                           governance_meta=meta, timestamp=_TS)

    def test_parse_error_rejects_evaluation_layer(self, baseline):
        """AI/ALT1/ALT2 are evaluation identifiers; must be rejected."""
        meta = {"recommended_candidate_type": "AI"}
        with pytest.raises(GovernanceActionParseError, match="operational-layer"):
            execute_action({}, baseline, event_id="E11",
                           governance_meta=meta, timestamp=_TS)


# ===========================================================================
# Layer-separation guarantee
# ===========================================================================


class TestLayerSeparation:
    def test_action_taken_is_operational_only(self, baseline):
        """ExecutionOutcome.action_taken uses only operational-layer identifiers."""
        operational = {"EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"}
        for adapter, eid in [
            (execute_expedite, "L1"),
            (execute_transfer, "L2"),
            (execute_compensate, "L3"),
            (execute_no_action, "L4"),
        ]:
            _, outcome = adapter(baseline.model_copy(deep=True),
                                 event_id=eid, timestamp=_TS)
            assert outcome.action_taken in operational


# ===========================================================================
# apply_action_outcome (narrow utility)
# ===========================================================================


class TestApplyActionOutcome:
    def test_apply_expedite_outcome_patches(self, baseline):
        """Applying an EXPEDITE outcome's patches to a fresh baseline should
        produce a state consistent with the adapter's post-condition."""
        # Generate an outcome from baseline
        _, outcome = execute_expedite(baseline, event_id="O1", timestamp=_TS)

        # Apply outcome.state_delta to a fresh baseline
        fresh = TwinState.initialize_from_config(_BASELINE)
        fresh.apply_action_outcome(outcome)

        # Carrier should now match the outcome's "after"
        assert fresh.planned_carrier_id == outcome.state_delta["after"]["planned_carrier_id"]
        assert fresh.planned_eta_hours == outcome.state_delta["after"]["planned_eta_hours"]

    def test_apply_no_patches_is_noop(self, baseline):
        """COMPENSATE outcome has empty patches; apply is a safe no-op."""
        _, outcome = execute_compensate(baseline, event_id="O2", timestamp=_TS)

        fresh = TwinState.initialize_from_config(_BASELINE)
        before_carrier = fresh.planned_carrier_id
        before_eta = fresh.planned_eta_hours
        fresh.apply_action_outcome(outcome)
        assert fresh.planned_carrier_id == before_carrier
        assert fresh.planned_eta_hours == before_eta

    def test_apply_invalid_delta_raises(self, baseline):
        """Non-dict state_delta should raise ValueError."""
        from pydantic import ValidationError
        # We can't easily construct an ExecutionOutcome with bad state_delta
        # due to schema, but we can construct a fake object:
        class _FakeOutcome:
            state_delta = "not-a-dict"
        with pytest.raises(ValueError, match="state_delta must be a dict"):
            baseline.apply_action_outcome(_FakeOutcome())

    def test_atomic_on_invalid_patch(self, baseline):
        """If any patch is invalid, the whole application is rolled back."""
        # Build an outcome with one valid patch + one invalid patch
        valid_outcome = execute_expedite(baseline, event_id="O3", timestamp=_TS)[1]
        bad_delta = {
            "patches": [
                *valid_outcome.state_delta["patches"],
                {"entity_type": "twin", "op": "set",
                 "field": "planned_eta_hours", "value": -999.0},  # violates ≥0
            ],
        }

        class _FakeOutcome:
            state_delta = bad_delta

        before_carrier = baseline.planned_carrier_id
        before_eta = baseline.planned_eta_hours
        with pytest.raises(ValueError):
            baseline.apply_action_outcome(_FakeOutcome())
        # Unchanged (atomic rollback)
        assert baseline.planned_carrier_id == before_carrier
        assert baseline.planned_eta_hours == before_eta
