"""
test_twin_state_costs.py — Unit tests for TwinState data models, cost formulas,
and runtime behaviour.

All expected numeric values are derived from SPEC.md formulas — no rounding.
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Allow imports from src/ without an installed package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from twin_state import (
    Action,
    ActionType,
    CostPolicy,
    CustomerZone,
    Supplier,
    TwinState,
    Warehouse,
    Carrier,
)

# Canonical baseline location as per SPEC §4
BASELINE_PATH = str(
    Path(__file__).parent.parent / "data" / "configs" / "baseline_network.json"
)

# Expected SPEC §8.2 top-level key order
EXPECTED_PROMPT_KEYS = [
    "timestamp",
    "active_order",
    "current_disruptions",
    "suppliers",
    "warehouses",
    "carriers",
    "customer_zones",
    "cost_policy",
    "allowed_operational_actions",
]

# Oracle fields that must never leak into to_prompt_context()
ORACLE_FIELDS = {
    "oracle_cost",
    "optimal_action",
    "optimal_action_set",
    "ground_truth",
    "ai_correct",
    "c_total",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fresh_state() -> TwinState:
    """Load a fresh TwinState from the canonical baseline config."""
    return TwinState.initialize_from_config(BASELINE_PATH)


# ---------------------------------------------------------------------------
# Baseline initialisation
# ---------------------------------------------------------------------------


def test_init_from_config():
    """Baseline config at data/configs/ loads cleanly with 2/2/2/2 entities."""
    state = fresh_state()
    assert len(state.suppliers) == 2
    assert len(state.warehouses) == 2
    assert len(state.carriers) == 2
    assert len(state.customer_zones) == 2
    assert state.order_id == "ORD_BASE_001"
    assert state.order_units == 10
    assert state.planned_carrier_id == "CR_1"
    assert state.planned_eta_hours == 36.0


def test_invalid_2222():
    """Config with 3 suppliers raises ValueError."""
    bad = {
        "timestamp": "2026-04-01T09:00:00Z",
        "suppliers": [
            {"id": "SUP_1", "name": "A", "lead_time_days": 5,
             "reliability_score": 0.9, "capacity_units": 100, "is_active": True},
            {"id": "SUP_2", "name": "B", "lead_time_days": 5,
             "reliability_score": 0.9, "capacity_units": 100, "is_active": True},
            {"id": "SUP_3", "name": "C", "lead_time_days": 5,
             "reliability_score": 0.9, "capacity_units": 100, "is_active": True},
        ],
        "warehouses": [
            {"id": "WH_1", "name": "W1", "location": "L1", "max_capacity": 500,
             "current_inventory": 100, "operating_cost_per_unit": 0.5},
            {"id": "WH_2", "name": "W2", "location": "L2", "max_capacity": 450,
             "current_inventory": 90, "operating_cost_per_unit": 0.8},
        ],
        "carriers": [
            {"id": "CR_1", "name": "C1", "available": True, "cost_per_unit": 3.0,
             "transit_time_hours": 36, "capacity_limit": 100},
            {"id": "CR_2", "name": "C2", "available": True, "cost_per_unit": 6.0,
             "transit_time_hours": 18, "capacity_limit": 60},
        ],
        "customer_zones": [
            {"id": "CZ_1", "name": "Z1", "demand_units": 10,
             "sla_deadline_hours": 24, "sla_penalty_per_hour": 5.0},
            {"id": "CZ_2", "name": "Z2", "demand_units": 8,
             "sla_deadline_hours": 18, "sla_penalty_per_hour": 8.0},
        ],
        "active_order": {
            "order_id": "ORD_TEST", "order_units": 10,
            "source_warehouse_id": "WH_1", "customer_zone_id": "CZ_1",
            "planned_carrier_id": "CR_1", "planned_eta_hours": 36,
        },
        "cost_policy": {
            "expedite_multiplier": 2.0, "transfer_fixed_fee": 30.0,
            "transfer_unit_cost": 1.5, "default_compensation_per_unit": 4.0,
            "default_penalty_relief_per_hour": 1.5, "verify_review_overhead": 140.0,
        },
        "current_disruptions": [],
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(bad, f)
        tmp = f.name

    with pytest.raises(ValueError, match="suppliers"):
        TwinState.initialize_from_config(tmp)


# ---------------------------------------------------------------------------
# Shock injection
# ---------------------------------------------------------------------------


def test_shock_deterministic():
    """Same shock applied to two independent fresh states produces identical results."""
    shock = {
        "entity_patches": [
            {
                "entity_type": "carrier",
                "entity_id": "CR_1",
                "op": "set",
                "field": "available",
                "value": False,
            }
        ]
    }
    state1 = fresh_state()
    state2 = fresh_state()
    state1.inject_shock(shock)
    state2.inject_shock(shock)

    assert state1.carriers["CR_1"].available is False
    assert state2.carriers["CR_1"].available is False
    assert state1.carriers["CR_1"].available == state2.carriers["CR_1"].available


def test_shock_set_add_multiply():
    """set / add / multiply ops all apply correctly."""
    state = fresh_state()

    # set
    state.inject_shock({
        "entity_patches": [
            {"entity_type": "twin", "op": "set",
             "field": "planned_eta_hours", "value": 20.0}
        ]
    })
    assert state.planned_eta_hours == 20.0

    # add
    state.inject_shock({
        "entity_patches": [
            {"entity_type": "twin", "op": "add",
             "field": "planned_eta_hours", "value": 10.0}
        ]
    })
    assert state.planned_eta_hours == 30.0

    # multiply
    state.inject_shock({
        "entity_patches": [
            {"entity_type": "twin", "op": "multiply",
             "field": "planned_eta_hours", "value": 2.0}
        ]
    })
    assert state.planned_eta_hours == 60.0

    # disruptions log has all three shocks
    assert len(state.current_disruptions) == 3


# ---------------------------------------------------------------------------
# Problem 3 — illegal state via shock must raise
# ---------------------------------------------------------------------------


def test_shock_negative_inventory_raises():
    """inject_shock that sets current_inventory < 0 raises ValueError."""
    state = fresh_state()
    with pytest.raises(ValueError):
        state.inject_shock({
            "entity_patches": [
                {"entity_type": "warehouse", "entity_id": "WH_1",
                 "op": "set", "field": "current_inventory", "value": -5}
            ]
        })
    # State must remain unchanged after the failed shock
    assert state.warehouses["WH_1"].current_inventory == 120


def test_shock_negative_cost_raises():
    """inject_shock that sets cost_per_unit < 0 raises ValueError."""
    state = fresh_state()
    with pytest.raises(ValueError):
        state.inject_shock({
            "entity_patches": [
                {"entity_type": "carrier", "entity_id": "CR_1",
                 "op": "set", "field": "cost_per_unit", "value": -1.0}
            ]
        })
    # State must remain unchanged
    assert state.carriers["CR_1"].cost_per_unit == 3.0


def test_compensate_negative_relief_raises():
    """COMPENSATE with penalty_relief_per_hour < 0 raises ValueError."""
    state = fresh_state()
    action = Action(
        action_id="comp_neg",
        action_type=ActionType.COMPENSATE,
        units=10,
        penalty_relief_per_hour=-1.0,
    )
    with pytest.raises(ValueError, match="penalty_relief"):
        state.apply_action(action)


# ---------------------------------------------------------------------------
# Action validation errors
# ---------------------------------------------------------------------------


def test_carrier_unavailable_raises():
    """EXPEDITE to an unavailable carrier raises ValueError."""
    state = fresh_state()
    state.inject_shock({
        "entity_patches": [
            {"entity_type": "carrier", "entity_id": "CR_2",
             "op": "set", "field": "available", "value": False}
        ]
    })
    action = Action(
        action_id="exp1",
        action_type=ActionType.EXPEDITE,
        units=10,
        target_carrier_id="CR_2",
        eta_adjustment_hours=-18.0,
    )
    with pytest.raises(ValueError, match="not available"):
        state.apply_action(action)


def test_transfer_insufficient_inventory_raises():
    """TRANSFER with more units than source inventory raises ValueError."""
    state = fresh_state()
    state.inject_shock({
        "entity_patches": [
            {"entity_type": "warehouse", "entity_id": "WH_2",
             "op": "set", "field": "current_inventory", "value": 5}
        ]
    })
    action = Action(
        action_id="tr1",
        action_type=ActionType.TRANSFER,
        units=10,
        from_warehouse_id="WH_2",
        to_warehouse_id="WH_1",
        eta_adjustment_hours=0.0,
    )
    with pytest.raises(ValueError, match="[Ii]nsufficien"):
        state.apply_action(action)


def test_transfer_capacity_exceeded_raises():
    """TRANSFER that would overflow destination max_capacity raises ValueError."""
    state = fresh_state()
    state.inject_shock({
        "entity_patches": [
            {"entity_type": "warehouse", "entity_id": "WH_1",
             "op": "set", "field": "current_inventory", "value": 495}
        ]
    })
    action = Action(
        action_id="tr2",
        action_type=ActionType.TRANSFER,
        units=10,
        from_warehouse_id="WH_2",
        to_warehouse_id="WH_1",
        eta_adjustment_hours=0.0,
    )
    with pytest.raises(ValueError, match="[Cc]apacity"):
        state.apply_action(action)


def test_compensation_relief_exceeds_penalty_raises():
    """COMPENSATE with penalty_relief >= sla_penalty_per_hour raises ValueError."""
    state = fresh_state()
    # CZ_1 sla_penalty_per_hour = 5.0; relief = 5.0 (equal) must fail
    action = Action(
        action_id="comp_bad",
        action_type=ActionType.COMPENSATE,
        units=10,
        penalty_relief_per_hour=5.0,
    )
    with pytest.raises(ValueError, match="penalty_relief"):
        state.apply_action(action)


def test_units_mismatch_raises():
    """action.units != order_units raises ValueError."""
    state = fresh_state()
    action = Action(
        action_id="bad_units",
        action_type=ActionType.NO_ACTION,
        units=7,  # order_units = 10
    )
    with pytest.raises(ValueError, match="order_units"):
        state.apply_action(action)


def test_compute_total_cost_requires_action_first():
    """compute_total_cost() before apply_action raises RuntimeError."""
    state = fresh_state()
    with pytest.raises(RuntimeError):
        state.compute_total_cost()


# ---------------------------------------------------------------------------
# Mini Example 1 — EXPEDITE wins (no lateness)
# ---------------------------------------------------------------------------


def test_mini_example_1_expedite():
    """
    q=10, planned_eta=36, sla_deadline=24, carrier cost=3, expedite_mult=2
    EXPEDITE eta_adj=-14  →  eta_after=22, late=0, direct=60, total=60.0
    """
    state = fresh_state()
    action = Action(
        action_id="mini1",
        action_type=ActionType.EXPEDITE,
        units=10,
        target_carrier_id="CR_1",
        eta_adjustment_hours=-14.0,
    )
    state.apply_action(action)
    total = state.compute_total_cost()

    assert total == 60.0
    bd = state.last_cost_breakdown
    assert bd["eta_after_action"] == 22.0
    assert bd["late_hours"] == 0.0
    assert bd["direct_action_cost"] == 60.0
    assert bd["sla_lateness_penalty"] == 0.0


# ---------------------------------------------------------------------------
# Mini Example 2 — TRANSFER, still late
# ---------------------------------------------------------------------------


def test_mini_example_2_transfer():
    """
    q=10, planned_eta=36, sla_deadline=24, sla_penalty=5
    TRANSFER WH_2→WH_1, eta_adj=-8  →  eta=28, late=4, direct=50, penalty=200, total=250.0
    """
    state = fresh_state()
    action = Action(
        action_id="mini2",
        action_type=ActionType.TRANSFER,
        units=10,
        from_warehouse_id="WH_2",
        to_warehouse_id="WH_1",
        eta_adjustment_hours=-8.0,
    )
    state.apply_action(action)
    total = state.compute_total_cost()

    assert total == 250.0
    bd = state.last_cost_breakdown
    assert bd["eta_after_action"] == 28.0
    assert bd["late_hours"] == 4.0
    assert bd["direct_action_cost"] == 50.0
    assert bd["sla_lateness_penalty"] == 200.0


# ---------------------------------------------------------------------------
# Mini Example 3 — COMPENSATE beats NO_ACTION
# ---------------------------------------------------------------------------


def test_mini_example_3_compensate():
    """
    q=10, planned_eta=30, sla_deadline=24, sla_penalty=5
    COMPENSATE comp=4, relief=1.5  →  direct=40, penalty=210, total=250.0
    NO_ACTION under same state  →  direct=0, penalty=300, total=300.0
    Assert COMPENSATE < NO_ACTION.
    """
    # --- COMPENSATE ---
    state_comp = fresh_state()
    state_comp.inject_shock({
        "entity_patches": [
            {"entity_type": "twin", "op": "set",
             "field": "planned_eta_hours", "value": 30.0}
        ]
    })
    action_comp = Action(
        action_id="mini3_comp",
        action_type=ActionType.COMPENSATE,
        units=10,
        compensation_per_unit=4.0,
        penalty_relief_per_hour=1.5,
    )
    state_comp.apply_action(action_comp)
    cost_comp = state_comp.compute_total_cost()

    assert cost_comp == 250.0
    bd = state_comp.last_cost_breakdown
    assert bd["eta_after_action"] == 30.0
    assert bd["late_hours"] == 6.0
    assert bd["direct_action_cost"] == 40.0
    assert bd["sla_lateness_penalty"] == 210.0

    # --- NO_ACTION reference ---
    state_no = fresh_state()
    state_no.inject_shock({
        "entity_patches": [
            {"entity_type": "twin", "op": "set",
             "field": "planned_eta_hours", "value": 30.0}
        ]
    })
    action_no = Action(
        action_id="mini3_no",
        action_type=ActionType.NO_ACTION,
        units=10,
    )
    state_no.apply_action(action_no)
    cost_no = state_no.compute_total_cost()

    assert cost_no == 300.0
    assert cost_comp < cost_no


# ---------------------------------------------------------------------------
# Problem 2 — to_prompt_context() exact SPEC §8 contract
# ---------------------------------------------------------------------------


def test_to_prompt_context_exact_top_level_keys():
    """Top-level key order must match SPEC §8.2 exactly."""
    state = fresh_state()
    ctx = json.loads(state.to_prompt_context())
    assert list(ctx.keys()) == EXPECTED_PROMPT_KEYS


def test_to_prompt_context_no_oracle_fields():
    """No oracle or hidden-cost fields must appear anywhere in the output."""
    state = fresh_state()
    raw = state.to_prompt_context()
    for field in ORACLE_FIELDS:
        assert field not in raw, f"Oracle field '{field}' found in prompt context"


def test_to_prompt_context_default_allowed_operational_actions_empty():
    """allowed_operational_actions defaults to [] when not provided."""
    state = fresh_state()
    ctx = json.loads(state.to_prompt_context())
    assert ctx["allowed_operational_actions"] == []


def test_to_prompt_context_passthrough_actions():
    """Provided actions are included verbatim under allowed_operational_actions."""
    state = fresh_state()
    actions = [
        {"action_id": "A1", "action_type": "NO_ACTION", "units": 10,
         "eta_adjustment_hours": 0.0, "description": "Keep plan"}
    ]
    ctx = json.loads(state.to_prompt_context(allowed_operational_actions=actions))
    assert ctx["allowed_operational_actions"] == actions


def test_to_prompt_context_entity_lists_sorted_by_id():
    """Suppliers, warehouses, carriers, customer_zones are sorted by id."""
    state = fresh_state()
    ctx = json.loads(state.to_prompt_context())
    for key in ("suppliers", "warehouses", "carriers", "customer_zones"):
        ids = [e["id"] for e in ctx[key]]
        assert ids == sorted(ids), f"{key} not sorted by id"


def test_to_prompt_context_active_order_fields():
    """active_order block contains all expected order fields."""
    state = fresh_state()
    ctx = json.loads(state.to_prompt_context())
    ao = ctx["active_order"]
    assert ao["order_id"] == "ORD_BASE_001"
    assert ao["order_units"] == 10
    assert ao["planned_carrier_id"] == "CR_1"
    assert ao["planned_eta_hours"] == 36.0


def test_to_prompt_context_cost_policy_omits_verify_overhead():
    """cost_policy in prompt must NOT include verify_review_overhead."""
    state = fresh_state()
    ctx = json.loads(state.to_prompt_context())
    assert "verify_review_overhead" not in ctx["cost_policy"]
    # But the five visible fields must be present
    for key in (
        "expedite_multiplier", "transfer_fixed_fee", "transfer_unit_cost",
        "default_compensation_per_unit", "default_penalty_relief_per_hour",
    ):
        assert key in ctx["cost_policy"]


# ---------------------------------------------------------------------------
# Problem A — inject_shock atomicity
# ---------------------------------------------------------------------------


def test_inject_shock_atomic_rollback_on_second_patch_failure():
    """When the second patch in a shock is illegal, the first patch must also
    be rolled back and current_disruptions must not grow."""
    state = fresh_state()
    original_eta = state.planned_eta_hours                          # 36.0
    original_inventory = state.warehouses["WH_1"].current_inventory  # 120
    original_disruptions = len(state.current_disruptions)            # 0

    bad_shock = {
        "entity_patches": [
            # Patch 1 — valid: add 5 hours to ETA
            {"entity_type": "twin", "op": "add",
             "field": "planned_eta_hours", "value": 5.0},
            # Patch 2 — invalid: negative inventory → should trigger rollback
            {"entity_type": "warehouse", "entity_id": "WH_1",
             "op": "set", "field": "current_inventory", "value": -1},
        ]
    }

    with pytest.raises(ValueError):
        state.inject_shock(bad_shock)

    # First patch must NOT have been committed
    assert state.planned_eta_hours == original_eta, (
        f"ETA should still be {original_eta}, got {state.planned_eta_hours}"
    )
    # Entity field must also be unchanged
    assert state.warehouses["WH_1"].current_inventory == original_inventory
    # No disruption entry must have been appended
    assert len(state.current_disruptions) == original_disruptions


def test_inject_shock_atomic_success_commits_all_changes():
    """When all patches are valid, all changes are committed and one disruption
    entry is appended."""
    state = fresh_state()

    good_shock = {
        "entity_patches": [
            # Patch 1 — add 5 hours to ETA
            {"entity_type": "twin", "op": "add",
             "field": "planned_eta_hours", "value": 5.0},
            # Patch 2 — mark CR_1 unavailable
            {"entity_type": "carrier", "entity_id": "CR_1",
             "op": "set", "field": "available", "value": False},
        ]
    }

    state.inject_shock(good_shock)

    assert state.planned_eta_hours == 41.0          # 36 + 5
    assert state.carriers["CR_1"].available is False
    assert len(state.current_disruptions) == 1
