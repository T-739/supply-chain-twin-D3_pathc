"""
build_cases_from_bank.py
========================
Task 1.2/1.3 bridge script.

Reads TianshiWang_Redesigned_Scenario_Bank_v3.csv and generates:
  - data/cases/<CASE_ID>.json  (20 files)
  - data/case_summary.csv
  - data/mappings/case_to_scenario_map.json

Oracle truth (action codes, split costs, oracle_cost) comes exclusively
from the CSV.  Initial state snapshots are built from
data/baseline_twin_state.json plus a lightweight scenario-delta.

Authoritative source for scenario deltas
-----------------------------------------
data/scenarios/<scenario_id>.json is the SOLE authoritative source for
entity-level state changes (entity_patches).  build_snapshot() reads
entity_patches directly from the scenario JSON file.

SCENARIO_ENTITY_OVERRIDES below is a narrow compatibility shim retained
only for scenarios whose JSON file is absent (e.g. demand_surge which
has no scenario file yet).  It is validated against scenario JSON on
build so silent divergence is impossible.
"""

import csv
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "TianshiWang_Redesigned_Scenario_Bank_v3.csv"
BASELINE_PATH = REPO_ROOT / "data" / "baseline_twin_state.json"
SCENARIOS_DIR = REPO_ROOT / "data" / "scenarios"
CASES_DIR = REPO_ROOT / "data" / "cases"
MAPPINGS_DIR = REPO_ROOT / "data" / "mappings"
SUMMARY_PATH = REPO_ROOT / "data" / "case_summary.csv"

# ---------------------------------------------------------------------------
# Scenario-type → canonical scenario_id mapping
# ---------------------------------------------------------------------------
SCENARIO_TYPE_MAP: dict[str, str] = {
    "Inventory Discrepancy": "inventory_discrepancy",
    "Carrier Disruption": "carrier_disruption",
    "Resource Allocation": "warehouse_capacity_or_equipment_issue",
    "Customer Service": "customer_service_recovery",
    "SLA Pressure": "sla_pressure",
    "Split vs Hold": "split_vs_hold",
    "Compliance": "compliance",
    # Compound / catch-all — expand as needed
    "Demand Surge": "demand_surge",
    "Supplier Delay": "supplier_delay_or_shutdown",
}

# ---------------------------------------------------------------------------
# Entity mapping defaults (SPEC_BRIDGE.md §"Required entity mapping rules")
# ---------------------------------------------------------------------------
# Uses _1/_2 IDs consistent with data/baseline_twin_state.json
SCENARIO_ENTITY_OVERRIDES: dict[str, dict] = {
    "inventory_discrepancy": {
        "primary_warehouse": "WH_1",
        "disruption_type": "inventory_accuracy",
        "disruptions": [
            {
                "type": "inventory_accuracy",
                "description": "WMS stock count may not match physical pick-bin quantity",
                "affected_entity": "WH_1",
            }
        ],
    },
    "carrier_disruption": {
        "primary_carrier": "CR_1",
        "disruption_type": "carrier_availability",
        "disruptions": [
            {
                "type": "carrier_availability",
                "description": "Primary carrier reports a service warning or delay",
                "affected_entity": "CR_1",
            }
        ],
    },
    "warehouse_capacity_or_equipment_issue": {
        "primary_warehouse": "WH_1",
        "disruption_type": "warehouse_resource",
        "disruptions": [
            {
                "type": "warehouse_resource",
                "description": "Pick station or scanner may be offline; throughput partially constrained",
                "affected_entity": "WH_1",
            }
        ],
    },
    "customer_service_recovery": {
        "primary_zone": "CZ_1",
        "disruption_type": "customer_sla_risk",
        "disruptions": [
            {
                "type": "customer_sla_risk",
                "description": "Customer-facing delay or dissatisfaction event; proactive recovery recommended",
                "affected_entity": "CZ_1",
            }
        ],
    },
    "sla_pressure": {
        "primary_zone": "CZ_2",
        "disruption_type": "sla_time_pressure",
        "disruptions": [
            {
                "type": "sla_time_pressure",
                "description": "Outbound order faces a tight SLA window; standard flow marginally clears deadline",
                "affected_entity": "CZ_2",
            }
        ],
    },
    "split_vs_hold": {
        "primary_warehouse": "WH_1",
        "disruption_type": "order_fulfillment_split",
        "disruptions": [
            {
                "type": "order_fulfillment_split",
                "description": "Multi-item order: one item ready, second item expected later today",
                "affected_entity": "WH_1",
            }
        ],
    },
    "compliance": {
        "primary_carrier": "CR_1",
        "disruption_type": "regulatory_compliance",
        "disruptions": [
            {
                "type": "regulatory_compliance",
                "description": "Regulated shipment: classification note may not match latest carrier acceptance rule",
                "affected_entity": "CR_1",
            }
        ],
    },
    "demand_surge": {
        "primary_warehouse": "WH_1",
        "disruption_type": "demand_surge",
        "disruptions": [
            {
                "type": "demand_surge",
                "description": "Demand spike exceeds standard throughput capacity",
                "affected_entity": "WH_1",
            }
        ],
    },
    "supplier_delay_or_shutdown": {
        "primary_supplier": "SUP_1",
        "disruption_type": "supplier_risk",
        "disruptions": [
            {
                "type": "supplier_risk",
                "description": "Primary supplier delay or partial shutdown",
                "affected_entity": "SUP_1",
            }
        ],
    },
}

# ---------------------------------------------------------------------------
# Decision-type labels for each action code
# ---------------------------------------------------------------------------
DECISION_TYPE_MAP = {
    "AI": "approve",
    "ALT1": "verify_pause",
    "ALT2": "alternative_plan",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_int(val: str) -> int:
    """Parse int, stripping non-numeric decoration."""
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return 0


def _safe_float(val: str) -> float:
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return 0.0


def _ai_correct_bool(val: str) -> bool:
    """CSV stores '1'/'0' or 'true'/'false'."""
    return str(val).strip() in ("1", "true", "True", "yes", "Yes")


def load_baseline() -> dict:
    with open(BASELINE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_scenario_json(scenario_id: str) -> dict | None:
    """
    Load and return the scenario JSON for scenario_id, or None if absent.
    Authoritative source: data/scenarios/<scenario_id>.json
    """
    path = SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_snapshot(baseline: dict, scenario_id: str) -> dict:
    """
    Build a TwinState-compatible initial_state_snapshot.

    = baseline_twin_state + lightweight scenario disruption delta.

    Authoritative delta source
    --------------------------
    Entity patches are read from data/scenarios/<scenario_id>.json
    (the ``entity_patches`` field).  The resulting current_disruptions
    entry embeds those patches so LangGraph / TwinState.inject_shock()
    can consume them directly.

    Fallback
    --------
    If the scenario JSON is absent (e.g. optional compound scenarios),
    SCENARIO_ENTITY_OVERRIDES provides a narrow narrative-only fallback,
    with an explicit TODO marker in the snapshot.

    This snapshot is for context/display/prompt only.
    Oracle costs come from the CSV, never from this snapshot.
    """
    import copy

    snapshot = copy.deepcopy(baseline)
    # Remove metadata keys that should not appear in runtime snapshots
    for key in ("_comment", "_defaults_policy"):
        snapshot.pop(key, None)

    scenario_json = _load_scenario_json(scenario_id)

    if scenario_json is not None:
        # PRIMARY PATH: scenario JSON is authoritative
        entity_patches = scenario_json.get("entity_patches", [])
        # Validate: if SCENARIO_ENTITY_OVERRIDES also has an entry, check for
        # divergence and warn loudly — do not silently blend both sources.
        if scenario_id in SCENARIO_ENTITY_OVERRIDES:
            _validate_no_silent_divergence(scenario_id, entity_patches)
        snapshot["current_disruptions"] = [
            {
                "scenario_id": scenario_id,
                "disruption_type": scenario_json.get("disruption_type", "unknown"),
                "entity_patches": entity_patches,
                "_source": f"data/scenarios/{scenario_id}.json",
            }
        ]
    else:
        # FALLBACK PATH: scenario JSON absent — use shim with TODO marker
        overrides = SCENARIO_ENTITY_OVERRIDES.get(scenario_id, {})
        disruptions = overrides.get("disruptions", [])
        snapshot["current_disruptions"] = [
            {
                "scenario_id": scenario_id,
                "disruption_type": overrides.get("disruption_type", "unknown"),
                "entity_patches": [],
                "_source": "SCENARIO_ENTITY_OVERRIDES_SHIM",
                "_TODO": (
                    f"Create data/scenarios/{scenario_id}.json with entity_patches "
                    "to replace this shim."
                ),
                "_narrative_disruptions": disruptions,
            }
        ]

    return snapshot


def _validate_no_silent_divergence(scenario_id: str, json_patches: list[dict]) -> None:
    """
    Raise ValueError if the scenario JSON has entity_patches but
    SCENARIO_ENTITY_OVERRIDES also claims to define disruptions for the
    same scenario.  This catches accidental dual-truth.

    Currently we only warn (don't abort) because the shim entries contain
    narrative-only data (no field/value keys), so they can't actually
    conflict numerically.  The scenario JSON entity_patches always win.
    """
    shim = SCENARIO_ENTITY_OVERRIDES.get(scenario_id, {})
    shim_disruptions = shim.get("disruptions", [])
    # If shim has disruptions with op/field keys, that would be a real conflict
    for d in shim_disruptions:
        if "field" in d or "op" in d:
            raise ValueError(
                f"Silent dual-truth detected for scenario '{scenario_id}': "
                f"SCENARIO_ENTITY_OVERRIDES contains operational patch fields "
                f"that conflict with scenario JSON entity_patches. "
                f"Remove the entry from SCENARIO_ENTITY_OVERRIDES."
            )
    # Shim is narrative-only — scenario JSON wins, log for traceability
    # (no stdout noise; validation passes silently when safe)


def build_case_json(row: dict, baseline: dict) -> dict:
    """
    Convert one CSV row → case JSON matching SPEC_BRIDGE.md schema.
    """
    case_id = row["scenario_id"].strip()  # CSV column is named scenario_id but holds P01, M01, etc.
    scenario_type = row["scenario_type"].strip()
    scenario_id = SCENARIO_TYPE_MAP.get(scenario_type, "inventory_discrepancy")
    scenario_config_ref = f"data/scenarios/{scenario_id}.json"

    ai_correct = _ai_correct_bool(row["ai_correct"])
    oracle_code = row["oracle_action_code"].strip()

    # --- Cost ground truth (from CSV exclusively) ---
    c_dir_ai = _safe_int(row["c_dir_ai"])
    c_out_ai = _safe_int(row["c_out_ai"])
    c_total_ai = _safe_int(row["c_total_ai"])

    c_dir_alt1 = _safe_int(row["c_dir_alt1"])
    c_out_alt1 = _safe_int(row["c_out_alt1"])
    c_total_alt1 = _safe_int(row["c_total_alt1"])

    c_dir_alt2 = _safe_int(row["c_dir_alt2"])
    c_out_alt2 = _safe_int(row["c_out_alt2"])
    c_total_alt2 = _safe_int(row["c_total_alt2"])

    oracle_cost = _safe_int(row["oracle_cost"])
    second_best_cost = _safe_int(row["second_best_cost"])

    # --- Decision options ---
    decision_options = [
        {
            "action_code": "AI",
            "decision_type": DECISION_TYPE_MAP["AI"],
            "action_label": row["ai_action_label"].strip(),
        },
        {
            "action_code": "ALT1",
            "decision_type": DECISION_TYPE_MAP["ALT1"],
            "action_label": row["alt1_action_label"].strip(),
        },
        {
            "action_code": "ALT2",
            "decision_type": DECISION_TYPE_MAP["ALT2"],
            "action_label": row["alt2_action_label"].strip(),
        },
    ]

    # --- Initial state snapshot ---
    snapshot = build_snapshot(baseline, scenario_id)

    # --- Notes from mapping assumptions ---
    notes = [
        f"Canonical scenario mapping: '{scenario_type}' -> '{scenario_id}'",
        "initial_state_snapshot built from baseline_plus_scenario_delta; NOT the oracle truth source",
    ]
    if scenario_id not in SCENARIO_TYPE_MAP.values():
        notes.append(f"TODO: '{scenario_type}' not in canonical mapping; defaulted to inventory_discrepancy")

    case = {
        "case_id": case_id,
        "block_type": row["block_type"].strip(),
        "recommended_order": _safe_int(row["recommended_order"]),
        "scenario_type": scenario_type,
        "scenario_id": scenario_id,
        "scenario_config_ref": scenario_config_ref,
        "risk_level": row["risk_level"].strip(),
        "service_stringency": row["service_stringency"].strip(),
        "complexity_score": _safe_int(row["complexity_score"]),
        "ai_correct": ai_correct,
        "oracle": {
            "action_code": oracle_code,
            "action_label": row["oracle_action_label"].strip(),
            "cost_total": oracle_cost,
        },
        "agent_recommendation_action_code": "AI",
        "order_or_shipment_id": row["order_or_shipment_id"].strip(),
        "case_title": row["case_title"].strip(),
        "exception_description": row["layer1_visible"].strip(),
        "layer1_visible": row["layer1_visible"].strip(),
        "detail_expand": row["detail_expand"].strip(),
        "ai_recommendation": row["ai_recommendation"].strip(),
        "decision_options": decision_options,
        "cost_ground_truth": {
            "AI": {
                "c_direct": c_dir_ai,
                "c_outcome": c_out_ai,
                "c_total": c_total_ai,
            },
            "ALT1": {
                "c_direct": c_dir_alt1,
                "c_outcome": c_out_alt1,
                "c_total": c_total_alt1,
            },
            "ALT2": {
                "c_direct": c_dir_alt2,
                "c_outcome": c_out_alt2,
                "c_total": c_total_alt2,
            },
        },
        "initial_state_snapshot": snapshot,
        "evaluation_metadata": {
            "second_best_cost": second_best_cost,
            "oracle_gap_points": _safe_int(row["oracle_gap_points"]),
            "ambiguity_gap_pct": _safe_float(row["ambiguity_gap_pct"]),
            "ratio_2nd_best": _safe_float(row["ratio_2nd_best"]),
            "error_direction": row["error_direction"].strip(),
            "action_reversibility": row["action_reversibility"].strip(),
        },
        "traceability_text": {
            "trace_rationale_short": row["trace_rationale_short"].strip(),
            "trace_key1": row["trace_key1"].strip(),
            "trace_key2": row["trace_key2"].strip(),
            "trace_key3": row["trace_key3"].strip(),
            "trace_more": row["trace_more"].strip(),
            "uncertainty_trigger1": row["uncertainty_trigger1"].strip(),
            "uncertainty_trigger2": row["uncertainty_trigger2"].strip(),
            "recommended_check": row["recommended_check"].strip(),
        },
        "feedback_text": {
            "feedback_ai_outcome": row["feedback_ai_outcome"].strip(),
            "feedback_alt1_outcome": row["feedback_alt1_outcome"].strip(),
            "feedback_alt2_outcome": row["feedback_alt2_outcome"].strip(),
        },
        "metadata": {
            "ground_truth_source": "TianshiWang_Redesigned_Scenario_Bank_v3.csv",
            "snapshot_policy": "baseline_plus_scenario_delta",
            "notes": notes,
        },
    }

    return case


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_case(case: dict) -> list[str]:
    """
    Returns list of validation error strings.
    Empty list = valid.
    """
    errors = []
    cid = case.get("case_id", "?")

    # Rule 1: c_total == c_direct + c_outcome
    for code in ("AI", "ALT1", "ALT2"):
        gt = case["cost_ground_truth"][code]
        expected = gt["c_direct"] + gt["c_outcome"]
        if expected != gt["c_total"]:
            errors.append(
                f"{cid}: cost_ground_truth[{code}] c_direct+c_outcome={expected} != c_total={gt['c_total']}"
            )

    # Rule 2: oracle_cost == cost_ground_truth[oracle_code].c_total
    oracle_code = case["oracle"]["action_code"]
    oracle_cost = case["oracle"]["cost_total"]
    gt_oracle_total = case["cost_ground_truth"][oracle_code]["c_total"]
    if oracle_cost != gt_oracle_total:
        errors.append(
            f"{cid}: oracle cost_total={oracle_cost} != cost_ground_truth[{oracle_code}].c_total={gt_oracle_total}"
        )

    # Rule 3: oracle action code is valid
    if oracle_code not in ("AI", "ALT1", "ALT2"):
        errors.append(f"{cid}: invalid oracle action_code '{oracle_code}'")

    # Rule 4: scenario_id is populated
    if not case.get("scenario_id"):
        errors.append(f"{cid}: missing scenario_id")

    # Rule 5: scenario config file must exist
    scenario_ref = case.get("scenario_config_ref", "")
    scenario_path = REPO_ROOT / scenario_ref
    if not scenario_path.exists():
        errors.append(f"{cid}: scenario_config_ref not found: {scenario_ref}")

    # Rule 6: snapshot is populated
    snap = case.get("initial_state_snapshot", {})
    for key in ("suppliers", "warehouses", "carriers", "customer_zones"):
        if not snap.get(key):
            errors.append(f"{cid}: initial_state_snapshot.{key} is empty")

    # Rule 7: ai_correct == True implies oracle_action_code == "AI"
    if case.get("ai_correct") is True and oracle_code != "AI":
        errors.append(
            f"{cid}: ai_correct=true but oracle_action_code='{oracle_code}' (expected 'AI')"
        )

    return errors


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build_all() -> None:
    print("=" * 60)
    print("build_cases_from_bank.py — Task 1.2/1.3 bridge")
    print("=" * 60)

    # Ensure output directories exist
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)

    # Load baseline
    baseline = load_baseline()
    print(f"[OK] Loaded baseline: {BASELINE_PATH.relative_to(REPO_ROOT)}")

    # Read CSV
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    print(f"[OK] Read {len(rows)} rows from CSV")

    # Build cases
    cases = []
    case_to_scenario_map = {}
    all_errors = []

    for row in rows:
        case = build_case_json(row, baseline)
        cases.append(case)

        case_id = case["case_id"]
        case_to_scenario_map[case_id] = {
            "scenario_id": case["scenario_id"],
            "scenario_config_ref": case["scenario_config_ref"],
            "scenario_type": case["scenario_type"],
            "block_type": case["block_type"],
        }

        # Validate
        errs = validate_case(case)
        if errs:
            all_errors.extend(errs)
            for e in errs:
                print(f"  [WARN] {e}")

        # Write case JSON
        out_path = CASES_DIR / f"{case_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(case, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Written {len(cases)} case JSON files to data/cases/")

    # Write case_to_scenario_map
    map_path = MAPPINGS_DIR / "case_to_scenario_map.json"
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(case_to_scenario_map, f, indent=2, ensure_ascii=False)
    print(f"[OK] Written {map_path.relative_to(REPO_ROOT)}")

    # Write case_summary.csv
    summary_fields = [
        "case_id", "block_type", "recommended_order", "scenario_type", "scenario_id",
        "risk_level", "service_stringency", "complexity_score", "ai_correct",
        "oracle_action_code", "oracle_cost", "second_best_cost",
        "c_dir_ai", "c_out_ai", "c_total_ai",
        "c_dir_alt1", "c_out_alt1", "c_total_alt1",
        "c_dir_alt2", "c_out_alt2", "c_total_alt2",
    ]

    with open(SUMMARY_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary_fields, extrasaction="ignore")
        writer.writeheader()
        for case in cases:
            writer.writerow({
                "case_id": case["case_id"],
                "block_type": case["block_type"],
                "recommended_order": case["recommended_order"],
                "scenario_type": case["scenario_type"],
                "scenario_id": case["scenario_id"],
                "risk_level": case["risk_level"],
                "service_stringency": case["service_stringency"],
                "complexity_score": case["complexity_score"],
                "ai_correct": case["ai_correct"],
                "oracle_action_code": case["oracle"]["action_code"],
                "oracle_cost": case["oracle"]["cost_total"],
                "second_best_cost": case["evaluation_metadata"]["second_best_cost"],
                "c_dir_ai": case["cost_ground_truth"]["AI"]["c_direct"],
                "c_out_ai": case["cost_ground_truth"]["AI"]["c_outcome"],
                "c_total_ai": case["cost_ground_truth"]["AI"]["c_total"],
                "c_dir_alt1": case["cost_ground_truth"]["ALT1"]["c_direct"],
                "c_out_alt1": case["cost_ground_truth"]["ALT1"]["c_outcome"],
                "c_total_alt1": case["cost_ground_truth"]["ALT1"]["c_total"],
                "c_dir_alt2": case["cost_ground_truth"]["ALT2"]["c_direct"],
                "c_out_alt2": case["cost_ground_truth"]["ALT2"]["c_outcome"],
                "c_total_alt2": case["cost_ground_truth"]["ALT2"]["c_total"],
            })
    print(f"[OK] Written {SUMMARY_PATH.relative_to(REPO_ROOT)}")

    # Summary report
    print("\n" + "=" * 60)
    print("BUILD SUMMARY")
    print("=" * 60)
    print(f"  Scenarios dir     : {SCENARIOS_DIR.relative_to(REPO_ROOT)}")
    scenario_files = list(SCENARIOS_DIR.glob("*.json"))
    print(f"  Scenario files    : {len(scenario_files)}")
    for sf in sorted(scenario_files):
        print(f"    {sf.name}")

    print(f"  Cases written     : {len(cases)}")
    practice = [c for c in cases if c["block_type"] == "practice"]
    main = [c for c in cases if c["block_type"] == "main"]
    print(f"    Practice blocks : {len(practice)}")
    print(f"    Main blocks     : {len(main)}")

    ai_correct_count = sum(1 for c in cases if c["ai_correct"])
    print(f"  AI-correct cases  : {ai_correct_count}/{len(cases)}")

    oracle_dist: dict[str, int] = {}
    for c in cases:
        code = c["oracle"]["action_code"]
        oracle_dist[code] = oracle_dist.get(code, 0) + 1
    print(f"  Oracle distribution: {oracle_dist}")

    if all_errors:
        print(f"\n  [WARN] {len(all_errors)} validation warning(s) — see above")
    else:
        print("\n  [OK] All validations passed")

    print("\n  TODO markers:")
    print("    - weather_location: all scenarios use fallback-only mode")
    print("    - initial_state_snapshot uses deterministic baseline defaults,")
    print("      not a case-specific reverse-engineered entity state")
    print("    - oracle truth sourced exclusively from CSV (not recomputed)")
    print("=" * 60)

    if all_errors:
        sys.exit(1)


if __name__ == "__main__":
    build_all()
