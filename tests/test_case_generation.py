"""
tests/test_case_generation.py
==============================
Validates the output of scripts/build_cases_from_bank.py.

Tests cover:
- all 20 case JSON files are present and parse correctly
- cost formula integrity: c_direct + c_outcome == c_total for AI/ALT1/ALT2
- oracle truth consistency: oracle_cost == cost_ground_truth[oracle_code].c_total
- scenario references resolve to real files
- initial_state_snapshots are fully populated
- case_summary.csv exists and matches case JSON values
- ai_correct=True implies oracle_action_code=="AI"
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = REPO_ROOT / "data" / "cases"
SCENARIOS_DIR = REPO_ROOT / "data" / "scenarios"
SUMMARY_PATH = REPO_ROOT / "data" / "case_summary.csv"
MAP_PATH = REPO_ROOT / "data" / "mappings" / "case_to_scenario_map.json"

EXPECTED_CASE_IDS = [
    "P01", "P02", "P03", "P04", "P05", "P06",
    "M01", "M02", "M03", "M04", "M05",
    "M06", "M07", "M08", "M09", "M10",
    "M11", "M12", "M13", "M14",
]

VALID_ACTION_CODES = {"AI", "ALT1", "ALT2"}
VALID_BLOCK_TYPES = {"practice", "main"}
SNAPSHOT_ENTITY_KEYS = ("suppliers", "warehouses", "carriers", "customer_zones")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def all_cases() -> dict[str, dict]:
    """Load all case JSON files into a dict keyed by case_id."""
    cases = {}
    for case_id in EXPECTED_CASE_IDS:
        path = CASES_DIR / f"{case_id}.json"
        assert path.exists(), f"Missing case file: {path}"
        with open(path, encoding="utf-8") as f:
            cases[case_id] = json.load(f)
    return cases


@pytest.fixture(scope="module")
def summary_rows() -> list[dict]:
    """Load case_summary.csv rows."""
    assert SUMMARY_PATH.exists(), f"Missing summary CSV: {SUMMARY_PATH}"
    with open(SUMMARY_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# T1 — File existence and count
# ---------------------------------------------------------------------------

class TestFilePresence:
    def test_all_20_case_files_exist(self):
        for case_id in EXPECTED_CASE_IDS:
            path = CASES_DIR / f"{case_id}.json"
            assert path.exists(), f"Missing: {path.name}"

    def test_exactly_20_case_files(self):
        case_files = list(CASES_DIR.glob("*.json"))
        assert len(case_files) == 20, (
            f"Expected 20 case files, found {len(case_files)}: "
            f"{[f.name for f in case_files]}"
        )

    def test_case_summary_csv_exists(self):
        assert SUMMARY_PATH.exists()

    def test_case_to_scenario_map_exists(self):
        assert MAP_PATH.exists()


# ---------------------------------------------------------------------------
# T2 — JSON parse and schema correctness
# ---------------------------------------------------------------------------

class TestCaseSchema:
    REQUIRED_TOP_LEVEL_KEYS = [
        "case_id", "block_type", "recommended_order", "scenario_type",
        "scenario_id", "scenario_config_ref", "risk_level", "ai_correct",
        "oracle", "agent_recommendation_action_code",
        "order_or_shipment_id", "case_title",
        "layer1_visible", "detail_expand", "ai_recommendation",
        "decision_options", "cost_ground_truth", "initial_state_snapshot",
        "evaluation_metadata", "traceability_text", "feedback_text", "metadata",
    ]

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_required_keys_present(self, case_id, all_cases):
        case = all_cases[case_id]
        for key in self.REQUIRED_TOP_LEVEL_KEYS:
            assert key in case, f"{case_id}: missing top-level key '{key}'"

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_block_type_valid(self, case_id, all_cases):
        block = all_cases[case_id]["block_type"]
        assert block in VALID_BLOCK_TYPES, f"{case_id}: block_type='{block}' not in {VALID_BLOCK_TYPES}"

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_oracle_action_code_valid(self, case_id, all_cases):
        code = all_cases[case_id]["oracle"]["action_code"]
        assert code in VALID_ACTION_CODES, f"{case_id}: oracle action_code='{code}'"

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_agent_recommendation_defaults_to_ai(self, case_id, all_cases):
        code = all_cases[case_id].get("agent_recommendation_action_code", "AI")
        assert code in VALID_ACTION_CODES

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_decision_options_have_three_entries(self, case_id, all_cases):
        opts = all_cases[case_id]["decision_options"]
        assert len(opts) == 3, f"{case_id}: expected 3 decision options, got {len(opts)}"
        codes = {o["action_code"] for o in opts}
        assert codes == VALID_ACTION_CODES, f"{case_id}: decision_options codes={codes}"


# ---------------------------------------------------------------------------
# T3 — Cost formula integrity
# ---------------------------------------------------------------------------

class TestCostFormulas:
    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    @pytest.mark.parametrize("code", ["AI", "ALT1", "ALT2"])
    def test_c_total_equals_c_direct_plus_c_outcome(self, case_id, code, all_cases):
        gt = all_cases[case_id]["cost_ground_truth"][code]
        expected = gt["c_direct"] + gt["c_outcome"]
        assert expected == gt["c_total"], (
            f"{case_id}[{code}]: c_direct({gt['c_direct']}) + "
            f"c_outcome({gt['c_outcome']}) = {expected} != c_total({gt['c_total']})"
        )


# ---------------------------------------------------------------------------
# T4 — Oracle truth consistency
# ---------------------------------------------------------------------------

class TestOracleTruth:
    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_oracle_cost_matches_cost_ground_truth(self, case_id, all_cases):
        case = all_cases[case_id]
        oracle_code = case["oracle"]["action_code"]
        oracle_cost = case["oracle"]["cost_total"]
        gt_total = case["cost_ground_truth"][oracle_code]["c_total"]
        assert oracle_cost == gt_total, (
            f"{case_id}: oracle cost_total={oracle_cost} != "
            f"cost_ground_truth[{oracle_code}].c_total={gt_total}"
        )

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_ai_correct_implies_oracle_is_ai(self, case_id, all_cases):
        case = all_cases[case_id]
        if case["ai_correct"]:
            assert case["oracle"]["action_code"] == "AI", (
                f"{case_id}: ai_correct=True but oracle='{case['oracle']['action_code']}'"
            )

    def test_p01_exact_ground_truth(self, all_cases):
        """P01 reference check from SPEC_BRIDGE.md."""
        case = all_cases["P01"]
        assert case["case_id"] == "P01"
        assert case["block_type"] == "practice"
        assert case["scenario_type"] == "Inventory Discrepancy"
        assert case["risk_level"] == "LOW"
        assert case["ai_correct"] is True
        assert case["oracle"]["action_code"] == "AI"
        assert case["oracle"]["cost_total"] == 80
        gt = case["cost_ground_truth"]
        assert gt["AI"] == {"c_direct": 40, "c_outcome": 40, "c_total": 80}
        assert gt["ALT1"] == {"c_direct": 140, "c_outcome": 60, "c_total": 200}
        assert gt["ALT2"] == {"c_direct": 100, "c_outcome": 120, "c_total": 220}


# ---------------------------------------------------------------------------
# T5 — Scenario references resolve
# ---------------------------------------------------------------------------

class TestScenarioRefs:
    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_scenario_config_ref_exists(self, case_id, all_cases):
        ref = all_cases[case_id]["scenario_config_ref"]
        full_path = REPO_ROOT / ref
        assert full_path.exists(), (
            f"{case_id}: scenario_config_ref='{ref}' — file not found at {full_path}"
        )

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_scenario_config_parses(self, case_id, all_cases):
        ref = all_cases[case_id]["scenario_config_ref"]
        full_path = REPO_ROOT / ref
        with open(full_path, encoding="utf-8") as f:
            sc = json.load(f)
        assert "scenario_id" in sc
        assert "disruption_type" in sc

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_scenario_id_matches_config(self, case_id, all_cases):
        case = all_cases[case_id]
        ref = case["scenario_config_ref"]
        full_path = REPO_ROOT / ref
        with open(full_path, encoding="utf-8") as f:
            sc = json.load(f)
        assert sc["scenario_id"] == case["scenario_id"], (
            f"{case_id}: case.scenario_id='{case['scenario_id']}' != "
            f"config.scenario_id='{sc['scenario_id']}'"
        )


# ---------------------------------------------------------------------------
# T6 — Initial state snapshots
# ---------------------------------------------------------------------------

class TestSnapshots:
    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_snapshot_not_empty(self, case_id, all_cases):
        snap = all_cases[case_id]["initial_state_snapshot"]
        assert isinstance(snap, dict), f"{case_id}: snapshot is not a dict"
        assert snap, f"{case_id}: snapshot is empty"

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_snapshot_entity_lists_populated(self, case_id, all_cases):
        snap = all_cases[case_id]["initial_state_snapshot"]
        for key in SNAPSHOT_ENTITY_KEYS:
            val = snap.get(key)
            assert val, f"{case_id}: snapshot.{key} is empty or missing"
            assert isinstance(val, list), f"{case_id}: snapshot.{key} is not a list"

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_snapshot_has_timestamp(self, case_id, all_cases):
        snap = all_cases[case_id]["initial_state_snapshot"]
        assert "timestamp" in snap, f"{case_id}: snapshot missing 'timestamp'"

    @pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
    def test_snapshot_entity_ids_use_canonical_convention(self, case_id, all_cases):
        """Entity IDs should use _1/_2 suffix convention."""
        snap = all_cases[case_id]["initial_state_snapshot"]
        all_ids = (
            [s["id"] for s in snap.get("suppliers", [])]
            + [w["id"] for w in snap.get("warehouses", [])]
            + [c["id"] for c in snap.get("carriers", [])]
            + [z["id"] for z in snap.get("customer_zones", [])]
        )
        for entity_id in all_ids:
            assert "_" in entity_id, (
                f"{case_id}: entity id '{entity_id}' does not use canonical _N convention"
            )


# ---------------------------------------------------------------------------
# T7 — case_summary.csv integrity
# ---------------------------------------------------------------------------

class TestCaseSummaryCSV:
    def test_summary_has_20_rows(self, summary_rows):
        assert len(summary_rows) == 20, f"Expected 20 rows, got {len(summary_rows)}"

    def test_summary_contains_all_case_ids(self, summary_rows):
        ids = {r["case_id"] for r in summary_rows}
        assert ids == set(EXPECTED_CASE_IDS), (
            f"Summary missing: {set(EXPECTED_CASE_IDS) - ids}"
        )

    def test_summary_oracle_costs_match_case_jsons(self, summary_rows, all_cases):
        for row in summary_rows:
            cid = row["case_id"]
            case = all_cases[cid]
            expected = str(case["oracle"]["cost_total"])
            assert row["oracle_cost"] == expected, (
                f"{cid}: summary oracle_cost='{row['oracle_cost']}' != case oracle cost_total='{expected}'"
            )

    def test_summary_c_total_ai_matches_case_jsons(self, summary_rows, all_cases):
        for row in summary_rows:
            cid = row["case_id"]
            case = all_cases[cid]
            expected = str(case["cost_ground_truth"]["AI"]["c_total"])
            assert row["c_total_ai"] == expected, (
                f"{cid}: summary c_total_ai='{row['c_total_ai']}' != case c_total='{expected}'"
            )


# ---------------------------------------------------------------------------
# T8 — Block distribution
# ---------------------------------------------------------------------------

class TestBlockDistribution:
    def test_six_practice_cases(self, all_cases):
        practice = [c for c in all_cases.values() if c["block_type"] == "practice"]
        assert len(practice) == 6, f"Expected 6 practice cases, got {len(practice)}"

    def test_fourteen_main_cases(self, all_cases):
        main = [c for c in all_cases.values() if c["block_type"] == "main"]
        assert len(main) == 14, f"Expected 14 main cases, got {len(main)}"
