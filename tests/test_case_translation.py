"""
test_case_translation.py — Tests for deterministic oracle selection and
SPEC §11 T1/T2/T3 translation examples.

All expected costs are derived from SPEC §11 hand-checkable math — no rounding.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from twin_state import ActionType, SupervisorDecisionType
from case_translation import compute_candidate_costs, select_optimal_action

BASELINE_PATH = str(
    Path(__file__).parent.parent / "data" / "configs" / "baseline_network.json"
)


# ---------------------------------------------------------------------------
# SPEC §11 Example T1 — AI no-action is optimal (no delay risk)
# ---------------------------------------------------------------------------

T1_PATCHES = [
    {"entity_type": "twin", "op": "set", "field": "order_id",    "value": "ORD_T1"},
    {"entity_type": "twin", "op": "set", "field": "order_units", "value": 10},
    {"entity_type": "twin", "op": "set", "field": "customer_zone_id",    "value": "CZ_1"},
    {"entity_type": "twin", "op": "set", "field": "source_warehouse_id", "value": "WH_1"},
    {"entity_type": "twin", "op": "set", "field": "planned_carrier_id",  "value": "CR_1"},
    {"entity_type": "twin", "op": "set", "field": "planned_eta_hours",   "value": 20},
]

T1_ACTIONS = {
    "ai": {
        "action_id": "T1_AI",
        "action_type": "NO_ACTION",
        "units": 10,
        "eta_adjustment_hours": 0.0,
        "description": "Keep current plan",
    },
    "alt1": {
        "action_id": "T1_ALT1",
        "action_type": "TRANSFER",
        "units": 10,
        "from_warehouse_id": "WH_2",
        "to_warehouse_id": "WH_1",
        "eta_adjustment_hours": 4.0,
        "description": "Pull reserve stock even though no delay risk exists",
    },
    "alt2": {
        "action_id": "T1_ALT2",
        "action_type": "COMPENSATE",
        "units": 10,
        "compensation_per_unit": 6.0,
        "penalty_relief_per_hour": 1.0,
        "description": "Offer compensation even though order is on time",
    },
}

# SPEC §11 T1 expected costs
T1_EXPECTED = {"ai": 0.0, "alt1": 50.0, "alt2": 60.0}


def test_translate_t1_matches_expected_costs():
    """T1: AI no-action is cheapest; TRANSFER=50, COMPENSATE=60. oracle=0.0."""
    records = compute_candidate_costs(BASELINE_PATH, T1_PATCHES, T1_ACTIONS)

    assert records["ai"]["total_cost"] == T1_EXPECTED["ai"]
    assert records["alt1"]["total_cost"] == T1_EXPECTED["alt1"]
    assert records["alt2"]["total_cost"] == T1_EXPECTED["alt2"]

    optimal_set, optimal_action = select_optimal_action(records)
    assert optimal_set == ["ai"]
    assert optimal_action == "ai"


# ---------------------------------------------------------------------------
# SPEC §11 Example T2 — EXPEDITE is oracle after carrier disruption
# ---------------------------------------------------------------------------

T2_PATCHES = [
    {"entity_type": "twin",    "op": "set", "field": "order_id",            "value": "ORD_T2"},
    {"entity_type": "twin",    "op": "set", "field": "order_units",          "value": 10},
    {"entity_type": "twin",    "op": "set", "field": "customer_zone_id",     "value": "CZ_1"},
    {"entity_type": "twin",    "op": "set", "field": "source_warehouse_id",  "value": "WH_1"},
    {"entity_type": "twin",    "op": "set", "field": "planned_carrier_id",   "value": "CR_1"},
    {"entity_type": "twin",    "op": "set", "field": "planned_eta_hours",    "value": 38},
    {"entity_type": "carrier", "entity_id": "CR_1", "op": "set",
     "field": "available", "value": False},
]

T2_ACTIONS = {
    "ai": {
        "action_id": "T2_AI",
        "action_type": "NO_ACTION",
        "units": 10,
        "eta_adjustment_hours": 0.0,
        "description": "Accept current delayed trajectory",
    },
    "alt1": {
        "action_id": "T2_ALT1",
        "action_type": "EXPEDITE",
        "units": 10,
        "target_carrier_id": "CR_2",
        "eta_adjustment_hours": -18.0,
        "description": "Switch to ExpressAir",
    },
    "alt2": {
        "action_id": "T2_ALT2",
        "action_type": "COMPENSATE",
        "units": 10,
        "compensation_per_unit": 4.0,
        "penalty_relief_per_hour": 1.5,
        "description": "Offer compensation but do not accelerate shipment",
    },
}

# SPEC §11 T2 expected costs
T2_EXPECTED = {"ai": 700.0, "alt1": 120.0, "alt2": 530.0}


def test_translate_t2_matches_expected_costs():
    """T2: EXPEDITE=120 is oracle; NO_ACTION=700, COMPENSATE=530."""
    records = compute_candidate_costs(BASELINE_PATH, T2_PATCHES, T2_ACTIONS)

    assert records["ai"]["total_cost"]   == T2_EXPECTED["ai"]
    assert records["alt1"]["total_cost"] == T2_EXPECTED["alt1"]
    assert records["alt2"]["total_cost"] == T2_EXPECTED["alt2"]

    optimal_set, optimal_action = select_optimal_action(records)
    assert optimal_set == ["alt1"]
    assert optimal_action == "alt1"


# ---------------------------------------------------------------------------
# SPEC §11 Example T3 — legacy VERIFY case; EXPEDITE is oracle
# ---------------------------------------------------------------------------

T3_PATCHES = [
    {"entity_type": "twin", "op": "set", "field": "order_id",            "value": "ORD_T3"},
    {"entity_type": "twin", "op": "set", "field": "order_units",          "value": 8},
    {"entity_type": "twin", "op": "set", "field": "customer_zone_id",     "value": "CZ_1"},
    {"entity_type": "twin", "op": "set", "field": "source_warehouse_id",  "value": "WH_1"},
    {"entity_type": "twin", "op": "set", "field": "planned_carrier_id",   "value": "CR_1"},
    {"entity_type": "twin", "op": "set", "field": "planned_eta_hours",    "value": 30},
]

T3_ACTIONS = {
    "ai": {
        "action_id": "T3_AI",
        "action_type": "NO_ACTION",
        "units": 8,
        "eta_adjustment_hours": 0.0,
        "description": "Trust current location sync and proceed",
    },
    "alt1_verify_resolved_action": {
        "action_id": "T3_ALT1_RESOLVED",
        "action_type": "TRANSFER",
        "units": 8,
        "from_warehouse_id": "WH_2",
        "to_warehouse_id": "WH_1",
        "eta_adjustment_hours": -4.0,
        "description": "After verification, pull from reserve stock",
    },
    "alt2": {
        "action_id": "T3_ALT2",
        "action_type": "EXPEDITE",
        "units": 8,
        "target_carrier_id": "CR_2",
        "eta_adjustment_hours": -12.0,
        "description": "Expedite immediately without checking",
    },
}

# SPEC §11 T3 expected operational costs (supervisor overhead excluded)
T3_EXPECTED = {"ai": 240.0, "alt1_verify_resolved_action": 126.0, "alt2": 96.0}

# T3 supervisor metadata (VERIFY label lives here, NOT in ActionType)
T3_SUPERVISOR_METADATA = {
    "legacy_alt1_label": "VERIFY",
    "preferred_supervisor_mode": "VERIFY",
    "verify_review_overhead": 140.0,
    "verify_resolved_action_key": "alt1_verify_resolved_action",
}


def test_translate_t3_matches_expected_costs():
    """T3: EXPEDITE=96 is oracle; TRANSFER=126, NO_ACTION=240."""
    records = compute_candidate_costs(BASELINE_PATH, T3_PATCHES, T3_ACTIONS)

    assert records["ai"]["total_cost"]                       == T3_EXPECTED["ai"]
    assert records["alt1_verify_resolved_action"]["total_cost"] == T3_EXPECTED["alt1_verify_resolved_action"]
    assert records["alt2"]["total_cost"]                     == T3_EXPECTED["alt2"]

    optimal_set, optimal_action = select_optimal_action(records)
    assert optimal_set == ["alt2"]
    assert optimal_action == "alt2"


# ---------------------------------------------------------------------------
# VERIFY must remain in supervisor_metadata only
# ---------------------------------------------------------------------------


def test_verify_stays_in_supervisor_metadata_only():
    """VERIFY must NOT exist in ActionType; it lives only in supervisor metadata."""
    # Confirm VERIFY is absent from operational ActionType
    action_values = {a.value for a in ActionType}
    assert "VERIFY" not in action_values

    # Confirm VERIFY IS accessible via SupervisorDecisionType
    assert SupervisorDecisionType.VERIFY.value == "VERIFY"

    # Confirm T3 supervisor_metadata carries the VERIFY label cleanly
    assert T3_SUPERVISOR_METADATA["preferred_supervisor_mode"] == "VERIFY"
    assert T3_SUPERVISOR_METADATA["verify_resolved_action_key"] == "alt1_verify_resolved_action"

    # And the resolved operational action key does NOT contain "VERIFY"
    resolved_key = T3_SUPERVISOR_METADATA["verify_resolved_action_key"]
    resolved_action = T3_ACTIONS[resolved_key]
    assert resolved_action["action_type"] != "VERIFY"
    assert resolved_action["action_type"] in action_values


# ---------------------------------------------------------------------------
# Tie-breaking — SPEC §9.3 all four levels
# ---------------------------------------------------------------------------


def test_tie_breaking_returns_optimal_action_set_and_single_optimal_action():
    """Two actions with equal total_cost: tie broken by sla_lateness_penalty."""
    records = {
        "a_compensate": {
            "action_key": "a_compensate",
            "action_type": ActionType.COMPENSATE.value,
            "total_cost": 100.0,
            "sla_lateness_penalty": 60.0,   # higher penalty
            "direct_action_cost": 40.0,
        },
        "b_expedite": {
            "action_key": "b_expedite",
            "action_type": ActionType.EXPEDITE.value,
            "total_cost": 100.0,
            "sla_lateness_penalty": 0.0,    # lower penalty → wins
            "direct_action_cost": 100.0,
        },
    }
    optimal_set, optimal_action = select_optimal_action(records)

    assert set(optimal_set) == {"a_compensate", "b_expedite"}
    assert optimal_action == "b_expedite"   # lower sla_lateness_penalty


def test_tie_breaking_level3_direct_cost():
    """Equal total and penalty: tie broken by direct_action_cost."""
    records = {
        "c1": {
            "action_key": "c1",
            "action_type": ActionType.TRANSFER.value,
            "total_cost": 50.0,
            "sla_lateness_penalty": 0.0,
            "direct_action_cost": 50.0,   # higher direct → loses
        },
        "c2": {
            "action_key": "c2",
            "action_type": ActionType.NO_ACTION.value,
            "total_cost": 50.0,
            "sla_lateness_penalty": 0.0,
            "direct_action_cost": 30.0,   # lower direct → wins here (before type priority)
        },
    }
    optimal_set, optimal_action = select_optimal_action(records)
    assert set(optimal_set) == {"c1", "c2"}
    assert optimal_action == "c2"


def test_tie_breaking_level4_action_type_priority():
    """Equal total, penalty, and direct cost: EXPEDITE beats NO_ACTION."""
    records = {
        "d_no_action": {
            "action_key": "d_no_action",
            "action_type": ActionType.NO_ACTION.value,
            "total_cost": 0.0,
            "sla_lateness_penalty": 0.0,
            "direct_action_cost": 0.0,
        },
        "d_expedite": {
            "action_key": "d_expedite",
            "action_type": ActionType.EXPEDITE.value,
            "total_cost": 0.0,
            "sla_lateness_penalty": 0.0,
            "direct_action_cost": 0.0,
        },
        "d_transfer": {
            "action_key": "d_transfer",
            "action_type": ActionType.TRANSFER.value,
            "total_cost": 0.0,
            "sla_lateness_penalty": 0.0,
            "direct_action_cost": 0.0,
        },
        "d_compensate": {
            "action_key": "d_compensate",
            "action_type": ActionType.COMPENSATE.value,
            "total_cost": 0.0,
            "sla_lateness_penalty": 0.0,
            "direct_action_cost": 0.0,
        },
    }
    optimal_set, optimal_action = select_optimal_action(records)

    # All four are co-optimal
    assert set(optimal_set) == {
        "d_no_action", "d_expedite", "d_transfer", "d_compensate"
    }
    # EXPEDITE wins on priority
    assert optimal_action == "d_expedite"


# ---------------------------------------------------------------------------
# Problem B — infeasible action handling
# ---------------------------------------------------------------------------


def test_compute_candidate_costs_skips_infeasible_action_and_keeps_feasible_ones():
    """One feasible and one infeasible action: function returns both records
    without raising; infeasible record carries feasible=False and an error string."""
    # T2 state has CR_1 unavailable; EXPEDITE to CR_1 is therefore infeasible.
    patches = T2_PATCHES
    actions = {
        "feasible_no_action": {
            "action_id": "F_NO",
            "action_type": "NO_ACTION",
            "units": 10,
            "eta_adjustment_hours": 0.0,
        },
        "infeasible_expedite_cr1": {
            "action_id": "INF_EXP",
            "action_type": "EXPEDITE",
            "units": 10,
            "target_carrier_id": "CR_1",   # unavailable after patches
            "eta_adjustment_hours": 0.0,
        },
    }

    # Must NOT raise
    records = compute_candidate_costs(BASELINE_PATH, patches, actions)

    assert len(records) == 2

    feas = records["feasible_no_action"]
    assert feas["feasible"] is True
    assert feas["error"] is None
    assert feas["total_cost"] is not None

    infeas = records["infeasible_expedite_cr1"]
    assert infeas["feasible"] is False
    assert infeas["error"] is not None and len(infeas["error"]) > 0
    assert infeas["total_cost"] is None
    assert infeas["sla_lateness_penalty"] is None
    assert infeas["direct_action_cost"] is None


def test_select_optimal_action_ignores_infeasible_records():
    """Oracle selection must skip infeasible records even if they dominate on cost."""
    records = {
        "good": {
            "action_key": "good",
            "action_type": ActionType.NO_ACTION.value,
            "feasible": True,
            "error": None,
            "total_cost": 100.0,
            "sla_lateness_penalty": 100.0,
            "direct_action_cost": 0.0,
        },
        "bad": {
            "action_key": "bad",
            "action_type": ActionType.EXPEDITE.value,
            "feasible": False,
            "error": "Carrier not available",
            "total_cost": None,
            "sla_lateness_penalty": None,
            "direct_action_cost": None,
        },
    }

    optimal_set, optimal_action = select_optimal_action(records)

    assert optimal_set == ["good"]
    assert optimal_action == "good"


def test_select_optimal_action_raises_if_all_infeasible():
    """select_optimal_action raises ValueError when every record is infeasible."""
    records = {
        "bad1": {
            "action_key": "bad1",
            "action_type": ActionType.EXPEDITE.value,
            "feasible": False,
            "error": "Carrier unavailable",
            "total_cost": None,
            "sla_lateness_penalty": None,
            "direct_action_cost": None,
        },
        "bad2": {
            "action_key": "bad2",
            "action_type": ActionType.TRANSFER.value,
            "feasible": False,
            "error": "Insufficient inventory",
            "total_cost": None,
            "sla_lateness_penalty": None,
            "direct_action_cost": None,
        },
    }

    with pytest.raises(ValueError, match="[Nn]o feasible"):
        select_optimal_action(records)
