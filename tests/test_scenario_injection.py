"""
tests/test_scenario_injection.py
==================================
Runtime tests that prove TwinState.inject_shock() correctly mutates live
entity state when driven by the entity_patches in each scenario JSON file.

These tests:
1. load a real scenario JSON from data/scenarios/
2. initialize TwinState from the canonical baseline config
   (data/configs/baseline_network.json — same path used by all twin_state tests)
3. call inject_shock() with the scenario's entity_patches
4. assert that at least one targeted field changed from baseline

Constraints:
- src/twin_state.py is NOT modified
- oracle costs / case JSON values are NOT read here
- test only runtime state mutation
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Allow imports from src/ without an installed package (matches repo convention)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from twin_state import TwinState

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_CONFIG = str(REPO_ROOT / "data" / "configs" / "baseline_network.json")
SCENARIOS_DIR = REPO_ROOT / "data" / "scenarios"

SCENARIO_IDS_WITH_FILES = [
    "inventory_discrepancy",
    "carrier_disruption",
    "customer_service_recovery",
    "warehouse_capacity_or_equipment_issue",
    "sla_pressure",
    "split_vs_hold",
    "compliance",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _load_scenario(scenario_id: str) -> dict:
    path = SCENARIOS_DIR / f"{scenario_id}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _baseline_state() -> TwinState:
    return TwinState.initialize_from_config(BASELINE_CONFIG)


def _shock_config(scenario_id: str) -> dict:
    """Build an inject_shock-compatible shock_config from scenario JSON."""
    sc = _load_scenario(scenario_id)
    patches = [
        {k: v for k, v in p.items() if not k.startswith("_")}
        for p in sc.get("entity_patches", [])
    ]
    return {
        "scenario_id": scenario_id,
        "entity_patches": patches,
    }


# ---------------------------------------------------------------------------
# T1 — Scenario JSON structure: entity_patches exist and are non-empty
# ---------------------------------------------------------------------------

class TestScenarioJsonStructure:
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS_WITH_FILES)
    def test_scenario_json_exists(self, scenario_id):
        path = SCENARIOS_DIR / f"{scenario_id}.json"
        assert path.exists(), f"Missing: {path}"

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS_WITH_FILES)
    def test_entity_patches_field_present(self, scenario_id):
        sc = _load_scenario(scenario_id)
        assert "entity_patches" in sc, (
            f"{scenario_id}: missing 'entity_patches' field"
        )

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS_WITH_FILES)
    def test_entity_patches_non_empty(self, scenario_id):
        sc = _load_scenario(scenario_id)
        patches = sc["entity_patches"]
        assert len(patches) >= 1, (
            f"{scenario_id}: entity_patches is empty — at least one patch required"
        )

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS_WITH_FILES)
    def test_severity_is_canonical(self, scenario_id):
        sc = _load_scenario(scenario_id)
        allowed = {"low", "medium", "high", "critical"}
        sev = sc.get("severity", "")
        assert sev in allowed, (
            f"{scenario_id}: severity='{sev}' not in {allowed}"
        )

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS_WITH_FILES)
    def test_patches_use_valid_ops(self, scenario_id):
        sc = _load_scenario(scenario_id)
        valid_ops = {"set", "add", "multiply"}
        for patch in sc["entity_patches"]:
            assert patch["op"] in valid_ops, (
                f"{scenario_id}: patch op='{patch['op']}' not in {valid_ops}"
            )

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS_WITH_FILES)
    def test_patches_use_repo_runtime_ids(self, scenario_id):
        """entity_id must use _1/_2 convention, never _A/_B."""
        sc = _load_scenario(scenario_id)
        for patch in sc["entity_patches"]:
            if patch["entity_type"] == "twin":
                continue
            eid = patch["entity_id"]
            assert eid.endswith("_1") or eid.endswith("_2"), (
                f"{scenario_id}: entity_id='{eid}' does not use _1/_2 convention"
            )
            assert not (eid.endswith("_A") or eid.endswith("_B")), (
                f"{scenario_id}: entity_id='{eid}' uses forbidden _A/_B convention"
            )


# ---------------------------------------------------------------------------
# T2 — Runtime injection: inject_shock() changes entity state
# ---------------------------------------------------------------------------

class TestInjectShockChangesState:
    def test_inventory_discrepancy_reduces_wh1_inventory(self):
        """
        inventory_discrepancy patches WH_1.current_inventory add -20.
        Baseline: 120 → expected after shock: 100.
        """
        state = _baseline_state()
        baseline_inv = state.warehouses["WH_1"].current_inventory

        shock = _shock_config("inventory_discrepancy")
        state.inject_shock(shock)

        after_inv = state.warehouses["WH_1"].current_inventory
        assert after_inv < baseline_inv, (
            f"inject_shock did not reduce WH_1.current_inventory: "
            f"{baseline_inv} -> {after_inv}"
        )
        assert after_inv == baseline_inv - 20

    def test_carrier_disruption_increases_cr1_transit_time(self):
        """
        carrier_disruption patches CR_1.transit_time_hours add 12.
        Baseline: 36 → expected after shock: 48.
        """
        state = _baseline_state()
        baseline_tt = state.carriers["CR_1"].transit_time_hours

        shock = _shock_config("carrier_disruption")
        state.inject_shock(shock)

        after_tt = state.carriers["CR_1"].transit_time_hours
        assert after_tt > baseline_tt, (
            f"inject_shock did not increase CR_1.transit_time_hours: "
            f"{baseline_tt} -> {after_tt}"
        )
        assert after_tt == pytest.approx(baseline_tt + 12)

    def test_carrier_disruption_also_increases_cr1_cost(self):
        """
        carrier_disruption also patches CR_1.cost_per_unit add 2.0.
        Baseline: 3.0 → expected after shock: 5.0.
        """
        state = _baseline_state()
        baseline_cost = state.carriers["CR_1"].cost_per_unit

        shock = _shock_config("carrier_disruption")
        state.inject_shock(shock)

        after_cost = state.carriers["CR_1"].cost_per_unit
        assert after_cost == pytest.approx(baseline_cost + 2.0)

    def test_customer_service_recovery_raises_cz1_sla_penalty(self):
        """
        customer_service_recovery patches CZ_1.sla_penalty_per_hour add 2.0.
        Baseline: 5.0 → expected after shock: 7.0.
        """
        state = _baseline_state()
        baseline_penalty = state.customer_zones["CZ_1"].sla_penalty_per_hour

        shock = _shock_config("customer_service_recovery")
        state.inject_shock(shock)

        after_penalty = state.customer_zones["CZ_1"].sla_penalty_per_hour
        assert after_penalty == pytest.approx(baseline_penalty + 2.0)

    def test_warehouse_capacity_issue_reduces_wh1_max_capacity(self):
        """
        warehouse_capacity_or_equipment_issue patches WH_1.max_capacity add -150.
        Baseline: 500 → expected after shock: 350.
        """
        state = _baseline_state()
        baseline_cap = state.warehouses["WH_1"].max_capacity

        shock = _shock_config("warehouse_capacity_or_equipment_issue")
        state.inject_shock(shock)

        after_cap = state.warehouses["WH_1"].max_capacity
        assert after_cap < baseline_cap
        assert after_cap == baseline_cap - 150

    def test_warehouse_capacity_issue_increases_wh1_operating_cost(self):
        """
        warehouse_capacity_or_equipment_issue also patches WH_1.operating_cost_per_unit add 0.5.
        """
        state = _baseline_state()
        baseline_opc = state.warehouses["WH_1"].operating_cost_per_unit

        shock = _shock_config("warehouse_capacity_or_equipment_issue")
        state.inject_shock(shock)

        after_opc = state.warehouses["WH_1"].operating_cost_per_unit
        assert after_opc == pytest.approx(baseline_opc + 0.5)

    def test_sla_pressure_tightens_cz2_deadline(self):
        """
        sla_pressure patches CZ_2.sla_deadline_hours add -4.
        Baseline: 18 → expected after shock: 14.
        """
        state = _baseline_state()
        baseline_dl = state.customer_zones["CZ_2"].sla_deadline_hours

        shock = _shock_config("sla_pressure")
        state.inject_shock(shock)

        after_dl = state.customer_zones["CZ_2"].sla_deadline_hours
        assert after_dl < baseline_dl
        assert after_dl == pytest.approx(baseline_dl - 4)

    def test_split_vs_hold_reduces_wh1_inventory(self):
        """
        split_vs_hold patches WH_1.current_inventory add -30.
        Baseline: 120 → expected after shock: 90.
        """
        state = _baseline_state()
        baseline_inv = state.warehouses["WH_1"].current_inventory

        shock = _shock_config("split_vs_hold")
        state.inject_shock(shock)

        after_inv = state.warehouses["WH_1"].current_inventory
        assert after_inv == baseline_inv - 30

    def test_compliance_disables_cr1(self):
        """
        compliance patches CR_1.available set false.
        Baseline: True → expected after shock: False.
        """
        state = _baseline_state()
        assert state.carriers["CR_1"].available is True

        shock = _shock_config("compliance")
        state.inject_shock(shock)

        assert state.carriers["CR_1"].available is False


# ---------------------------------------------------------------------------
# T3 — Atomicity: failed inject_shock leaves state untouched
# ---------------------------------------------------------------------------

class TestInjectShockAtomicity:
    def test_invalid_patch_leaves_state_unchanged(self):
        """
        A patch that would set current_inventory to a negative value should
        raise and leave the TwinState completely untouched (atomic rollback).
        """
        state = _baseline_state()
        original_inv = state.warehouses["WH_1"].current_inventory

        bad_shock = {
            "scenario_id": "bad_test",
            "entity_patches": [
                {
                    "entity_type": "warehouse",
                    "entity_id": "WH_1",
                    "op": "set",
                    "field": "current_inventory",
                    "value": -999,
                }
            ],
        }
        with pytest.raises((ValueError, Exception)):
            state.inject_shock(bad_shock)

        # State must be untouched
        assert state.warehouses["WH_1"].current_inventory == original_inv
        assert len(state.current_disruptions) == 0


# ---------------------------------------------------------------------------
# T4 — build_snapshot() uses scenario JSON as authoritative source
# ---------------------------------------------------------------------------

class TestBuildSnapshotUsesScenarioJSON:
    """
    Verify that the build_snapshot() function in build_cases_from_bank.py
    embeds entity_patches from the scenario JSON (not from the shim).
    """

    def test_build_snapshot_current_disruptions_contain_entity_patches(self):
        import sys
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from build_cases_from_bank import build_snapshot, load_baseline

        baseline = load_baseline()
        snapshot = build_snapshot(baseline, "inventory_discrepancy")

        disruptions = snapshot.get("current_disruptions", [])
        assert len(disruptions) >= 1, "snapshot must have at least one disruption entry"

        first = disruptions[0]
        assert "entity_patches" in first, (
            "snapshot current_disruptions entry must have 'entity_patches' key"
        )
        assert len(first["entity_patches"]) >= 1, (
            "entity_patches in snapshot must be non-empty for inventory_discrepancy"
        )
        assert first.get("_source", "").endswith("inventory_discrepancy.json"), (
            f"snapshot source should point to scenario JSON, got: {first.get('_source')}"
        )

    def test_build_snapshot_compliance_has_cr1_unavailable_patch(self):
        import sys
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from build_cases_from_bank import build_snapshot, load_baseline

        baseline = load_baseline()
        snapshot = build_snapshot(baseline, "compliance")

        disruptions = snapshot["current_disruptions"]
        assert disruptions, "compliance snapshot must have disruptions"
        patches = disruptions[0]["entity_patches"]

        cr1_patch = next(
            (p for p in patches if p.get("entity_id") == "CR_1" and p.get("field") == "available"),
            None,
        )
        assert cr1_patch is not None, (
            "compliance snapshot must contain entity_patch for CR_1.available"
        )
        assert cr1_patch["value"] is False
