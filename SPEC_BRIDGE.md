# spec.md

## Task
Design and implement the minimum-viable bridge between the uploaded Scenario Bank / parameterization files and the codebase artifacts needed for **Task 1.2 Create Scenario Configs** and **Task 1.3 Prepare Synthetic Cases with Ground Truth**.

This is a thesis-aligned MVP for a LangGraph-based human-supervised supply chain twin for disruption simulation and fulfillment exception handling.

The immediate goal is **not** to redesign the architecture and **not** to rebuild `twin_state.py`. The goal is to produce a clean, deterministic, code-usable bridge so that:

1. scenario configs can be loaded into the twin layer,
2. case JSON files can be generated from the Scenario Bank,
3. evaluation metrics can be computed deterministically from oracle truth,
4. Streamlit / LangGraph can consume case + scenario data without ambiguity.

---

## Project context

This project must stay aligned with the thesis logic and the course MVP logic:

- Critical path must remain:
  1. Twin State Schema
  2. Synthetic Cases with ground truth
  3. Governance Agent
  4. Streamlit UI
- Numeric truth must be deterministic.
- Oracle action and oracle cost must come from the uploaded case bank, not from LLM inference.
- The revised thesis centers evaluation on:
  - primary behavioral outcome: unnecessary override
  - primary performance outcome: regret
  - secondary outcomes: override effectiveness and total cost
- The codebase already has a TwinState implementation and it must **not** be redesigned in this task.

---

## Current status to assume

Assume the following are already true:

- `src/twin_state.py` exists and has the current entity structure.
- Task 1.1 Twin State schema is treated as implemented enough to anchor downstream contracts.
- Uploaded files already contain strong case-level truth for:
  - case IDs
  - action labels
  - AI correctness
  - oracle action
  - direct / outcome / total costs
  - practice vs main block
  - risk level
  - UI-facing narrative text
- However, the uploaded files do **not** provide a complete code-ready baseline twin state with full entity-level initialization values for every case.

This missing baseline is **not a blocker**. It must be handled via a controlled engineering bridge, not by guessing freely.

---

## Files that are the source of truth

### Authoritative source for case-level oracle and costs
Use these uploaded files as the **authoritative truth** for case-level evaluation values:

1. `TianshiWang_Redesigned_Scenario_Bank_v3.csv`
2. `Integrated_Scenario_Parameterization.xlsx`

These files are the sole source of truth for:

- `case_id`
- `block_type`
- `scenario_type`
- `risk_level`
- `ai_correct`
- `oracle_action_code`
- action labels
- `c_dir_*`
- `c_out_*`
- `c_total_*`
- `oracle_cost`
- ambiguity / gap metadata
- case narrative / UI text fields

### Source of truth for twin / scenario structure
For this task, Claude Code must create the missing engineering bridge artifacts:

- `data/baseline_twin_state.json`
- `data/scenarios/*.json`
- `data/cases/*.json`

These generated artifacts are authoritative for:

- baseline twin initialization
- scenario-level entity deltas
- case-to-scenario structural linkage
- TwinState-compatible initial snapshots

### Non-negotiable policy
If generated scenario or case snapshot values are not fully derivable from the uploaded bank files, Claude must use **explicit deterministic defaults** and document them in metadata / comments. Claude must **not** silently invent business logic and must **not** replace uploaded oracle truth.

---

## What this task must produce

Claude Code must produce the following:

1. `data/baseline_twin_state.json`
2. `data/scenarios/` containing **5 to 8 canonical scenario JSON files**
3. `data/cases/` containing **20 case JSON files** mapped from the uploaded case bank
4. `data/case_summary.csv`
5. `scripts/build_cases_from_bank.py`
6. `src/evaluation.py` implementing the deterministic evaluation contract
7. `tests/test_case_generation.py`
8. `tests/test_evaluation.py`
9. optional: `data/mappings/case_to_scenario_map.json`

Do not create extra frameworks, extra agents, or optimization engines.

---

## Scope boundaries

### In scope
- bridge specification and implementation for Task 1.2 and Task 1.3
- baseline twin defaults
- scenario JSON generation
- case JSON generation
- deterministic evaluation logic
- validation and tests

### Out of scope
- redesigning `src/twin_state.py`
- redesigning the cost model used by the case bank
- replacing case-bank oracle logic with simulation logic
- building the full graph / agents / Streamlit UI in this task
- adding new action types beyond the existing three-way decision frame for evaluation
- using LLM-generated numbers for cost truth

---

## Hard constraints

1. **Do not modify `src/twin_state.py`** in this task.
2. **Do not change split-cost logic**.
3. **Do not let TwinState recompute oracle truth**.
4. **Do not let LLM-generated text decide numeric labels or costs**.
5. Prefer the simplest implementation that is demo-stable.
6. Any unresolved ambiguity must be surfaced explicitly in comments / metadata / TODO markers, not hidden.

---

## Design decision that must be implemented

### Required bridge strategy
Use a **hybrid lightweight-state + direct-lookup design**.

That means:

#### A. `initial_state_snapshot`
Generate a **TwinState-compatible lightweight state snapshot** for each case.

Purpose:
- TwinState initialization
- LangGraph shared state input
- prompt context
- Streamlit display
- scenario visualization

It is **not** the authoritative source of numeric oracle truth.

#### B. `cost_ground_truth`
Store case-level direct / outcome / total cost values directly in each case JSON.

Purpose:
- evaluation
- oracle comparison
- regret
- unnecessary override
- override effectiveness

This is the authoritative numeric truth.

### Why this is mandatory
- Full reverse engineering from split costs to a complete supply chain world is under-identified and too risky.
- Pure direct lookup with no TwinState-compatible snapshot would weaken demo completeness.
- Therefore the correct MVP bridge is:
  - lightweight TwinState-compatible snapshot for context
  - direct lookup table for evaluation truth

---

## Canonical action frame

For the evaluation bridge, the action code system is fixed:

- `AI` = approve AI recommendation
- `ALT1` = verify / pause
- `ALT2` = alternative plan

These action codes are the canonical evaluation labels.

### Important distinction
These are **decision codes** for case evaluation.
They are not required to fully equal low-level operational payloads in `TwinState.apply_action()`.

If operational wrappers are needed, use a lightweight wrapper such as:

```json
{
  "action_code": "AI",
  "decision_type": "approve",
  "action_label": "Keep primary carrier and release shipment"
}
```

But under no circumstance should this wrapper be used to overwrite case-bank oracle costs.

---

## Required baseline twin design

Claude must create `data/baseline_twin_state.json`.

This file must define a minimal synthetic network consistent with the project proposal:

- 2 suppliers
- 2 warehouses
- 2 carriers
- 2 customer zones

### Canonical IDs to use
Use these exact canonical IDs unless there is a code-level incompatibility:

- Suppliers: `SUP_A`, `SUP_B`
- Warehouses: `WH_A`, `WH_B`
- Carriers: `CAR_A`, `CAR_B`
- Customer zones: `CZ_A`, `CZ_B`

### Required baseline fields
The baseline file must include at minimum fields compatible with the current TwinState schema expectations:

#### Suppliers
- `id`
- `name`
- `lead_time_days`
- `reliability_score`
- `capacity_units`
- `is_active`

#### Warehouses
- `id`
- `name`
- `location`
- `max_capacity`
- `current_inventory`
- `operating_cost_per_unit`

#### Carriers
- `id`
- `name`
- `available`
- `cost_per_unit`
- `transit_time_hours`
- `capacity_limit`

#### Customer zones
- `id`
- `name`
- `demand_units`
- `sla_deadline_hours`
- `sla_penalty_per_hour`

#### Twin state root
- `timestamp`
- `current_disruptions`

### Default value policy
If exact values are not available from the uploaded files, Claude must use deterministic baseline defaults.

The defaults should be:
- simple
- plausible
- internally consistent
- stable across runs
- documented in the file metadata or comments

Do not create a highly realistic simulator. Keep it minimal and code-usable.

---

## Required scenario design

Claude must create **5 to 8 canonical scenario JSON files** in `data/scenarios/`.

### Why canonical scenarios instead of 20 scenario files
The roadmap expects a scenario layer and a case layer. Therefore:
- scenarios should represent reusable disruption templates,
- cases should attach to one scenario template plus case-level narrative/cost truth.

### Required canonical scenarios
Create a scenario set aligned with the existing project logic. The recommended canonical scenario families are:

1. `inventory_discrepancy`
2. `carrier_disruption`
3. `demand_surge`
4. `supplier_delay_or_shutdown`
5. `warehouse_capacity_or_equipment_issue`
6. `customer_service_recovery`
7. optional compound scenario: `compound_storm_plus_demand`

### Required scenario JSON fields
Each scenario JSON must contain:

- `scenario_id`
- `name`
- `description`
- `severity`
- `disruption_type`
- `affected_entities`
- `variable_changes`
- `weather_fallback`
- optional `weather_location`
- `difficulty_notes`

### Meaning of fields
- `affected_entities`: list of canonical entity IDs touched by the scenario
- `variable_changes`: deterministic changes applied on top of the baseline twin
- `weather_fallback`: lightweight synthetic weather context if relevant
- `weather_location`: optional metadata only; not required to block case generation

### Weather rule
Weather is **non-blocking** in this task.
If precise coordinates are unavailable:
- include a fallback text payload,
- optionally include city-level labels,
- mark missing coordinates as `TODO_WEATHER_LOCATION`,
- do not block implementation.

---

## Required case-to-scenario mapping

Claude must bridge the 20 case-bank cases to the canonical scenarios.

### Required policy
- There are 20 cases total.
- Use all 20.
- Preserve `block_type` (`practice` / `main`) as case-level metadata.
- Do not create separate scenario families for practice vs main.

### Mapping output
Create one of the following:

- embed mapping directly in each case JSON, and/or
- create `data/mappings/case_to_scenario_map.json`

### Mapping rules
Use deterministic mapping rules from `scenario_type` to canonical scenario family.

Recommended mapping logic:
- `Inventory Discrepancy` -> `inventory_discrepancy`
- `Carrier Disruption` -> `carrier_disruption`
- demand pressure / surge types -> `demand_surge`
- supplier risk / inbound issues -> `supplier_delay_or_shutdown`
- warehouse bottleneck / capacity / picking issue -> `warehouse_capacity_or_equipment_issue`
- customer recovery / appeasement / communication style -> `customer_service_recovery`
- clearly mixed disruptions -> `compound_storm_plus_demand` or another compound template if needed

If a case is ambiguous, use the closest canonical scenario and note the assumption in metadata.

---

## Required entity mapping rules

Because the uploaded files do not provide a full code-ready entity mapping, Claude must use canonical deterministic mapping rules.

### Mapping defaults
Unless case-specific evidence strongly suggests otherwise:

- upstream / inbound / supplier-side issues default to `SUP_A`
- warehouse-side fulfillment issues default to `WH_A`
- primary transportation issues default to `CAR_A`
- customer SLA pressure defaults to `CZ_A`
- backup / alternative resource defaults map to `SUP_B`, `WH_B`, `CAR_B`, or `CZ_B` as appropriate

### Rule purpose
This mapping exists only to create a coherent TwinState-compatible bridge.
It does **not** override cost truth.

---

## Required case JSON schema

Claude must create one JSON file per case in `data/cases/`.

Each case JSON must include the following fields.

```json
{
  "case_id": "P01",
  "block_type": "practice",
  "recommended_order": 1,
  "scenario_type": "Inventory Discrepancy",
  "scenario_id": "inventory_discrepancy",
  "scenario_config_ref": "data/scenarios/inventory_discrepancy.json",
  "risk_level": "LOW",
  "service_stringency": "Std B2C",
  "ai_correct": true,
  "oracle": {
    "action_code": "AI",
    "action_label": "Approve",
    "cost_total": 80
  },
  "agent_recommendation_action_code": "AI",
  "order_or_shipment_id": "WH-P01-2047",
  "case_title": "Fresh stock record on a standard SKU",
  "exception_description": "Human-readable summary of the exception",
  "layer1_visible": "...",
  "detail_expand": "...",
  "ai_recommendation": "...",
  "decision_options": [
    {
      "action_code": "AI",
      "decision_type": "approve",
      "action_label": "Pack from current pick bin"
    },
    {
      "action_code": "ALT1",
      "decision_type": "verify_pause",
      "action_label": "Pause to check latest inbound/outbound scans"
    },
    {
      "action_code": "ALT2",
      "decision_type": "alternative_plan",
      "action_label": "Pull from reserve location instead"
    }
  ],
  "cost_ground_truth": {
    "AI": {
      "c_direct": 40,
      "c_outcome": 40,
      "c_total": 80
    },
    "ALT1": {
      "c_direct": 140,
      "c_outcome": 60,
      "c_total": 200
    },
    "ALT2": {
      "c_direct": 100,
      "c_outcome": 120,
      "c_total": 220
    }
  },
  "initial_state_snapshot": {
    "timestamp": "2026-03-01T09:00:00Z",
    "suppliers": [],
    "warehouses": [],
    "carriers": [],
    "customer_zones": [],
    "current_disruptions": []
  },
  "evaluation_metadata": {
    "second_best_cost": 200,
    "oracle_gap_points": 120,
    "ambiguity_gap_pct": 1.5,
    "ratio_2nd_best": 2.5
  },
  "traceability_text": {
    "trace_rationale_short": "...",
    "trace_key1": "...",
    "trace_key2": "...",
    "trace_key3": "...",
    "trace_more": "..."
  },
  "feedback_text": {
    "feedback_ai_outcome": "...",
    "feedback_alt1_outcome": "...",
    "feedback_alt2_outcome": "..."
  },
  "metadata": {
    "ground_truth_source": "Scenario Bank + Integrated Parameterization",
    "snapshot_policy": "baseline_plus_scenario_delta",
    "notes": []
  }
}
```

### Notes on the schema
- `initial_state_snapshot` must be fully materialized, not left empty in actual output.
- `agent_recommendation_action_code` defaults to `AI` unless explicit case-level override is intentionally added later.
- `oracle` must come from the uploaded bank, not recomputed from snapshot.

---

## Policy for `initial_state_snapshot`

This is critical.

### What it is
`initial_state_snapshot` is a **TwinState-compatible generated context object**.

### What it is not
It is **not** the numeric oracle generator.

### Required generation rule
For each case:

`initial_state_snapshot = baseline_twin_state + linked_scenario_delta + optional_case_delta`

### Allowed use cases
- initialize twin state
- render context in UI
- feed prompt context to agents
- display affected entities and disruptions

### Forbidden use
- do not use it to overwrite oracle costs
- do not use it to infer alternative costs if case-bank costs already exist
- do not claim that snapshot fully reverse-engineers the original experimental world

---

## Required evaluation contract

Claude must implement `src/evaluation.py` based on case JSON lookup truth.

### Mandatory function signatures
Use these signatures unless the repository style requires minor typing adjustments:

```python
from typing import Literal

ActionCode = Literal["AI", "ALT1", "ALT2"]


def normalize_action_code(action_code: str) -> ActionCode:
    ...


def get_agent_action_code(case: dict) -> ActionCode:
    ...


def get_total_cost(case: dict, action_code: ActionCode) -> float:
    ...


def compute_total_cost(case: dict, action_code: ActionCode) -> float:
    ...


def is_override(case: dict, human_action_code: ActionCode) -> bool:
    ...


def is_unnecessary_override(case: dict, human_action_code: ActionCode) -> bool:
    ...


def compute_override_effectiveness(case: dict, human_action_code: ActionCode) -> str:
    ...


def compute_regret(case: dict, human_action_code: ActionCode) -> float:
    ...
```

### Mandatory evaluation rules

#### Rule 1: `compute_total_cost`
Must read from:

`case["cost_ground_truth"][action_code]["c_total"]`

It must **not** call TwinState cost recomputation for authoritative evaluation.

#### Rule 2: agent recommendation
Default:

`case["agent_recommendation_action_code"] == "AI"`

unless the case JSON explicitly sets otherwise.

#### Rule 3: `is_unnecessary_override`
Logic:

```python
human_action != agent_action and agent_action == oracle_action
```

#### Rule 4: `compute_override_effectiveness`
Compare human chosen cost vs agent recommended cost.
Return one of:

- `"cost_reducing"`
- `"cost_increasing"`
- `"neutral"`
- `"no_override"`

#### Rule 5: `compute_regret`
Logic:

```python
chosen_cost - oracle_cost
```

where:
- `chosen_cost` comes from `cost_ground_truth`
- `oracle_cost` comes from `case["oracle"]["cost_total"]`

### Optional but recommended helper functions
Implement:

```python
def validate_split_cost(case: dict) -> None:
    ...


def validate_oracle_consistency(case: dict) -> None:
    ...
```

---

## Validation rules that must be implemented

Claude must implement validation during generation and/or in tests.

### Mandatory validations
1. `c_total == c_direct + c_outcome` for `AI`, `ALT1`, `ALT2`
2. `oracle_cost == cost_ground_truth[oracle_action_code].c_total`
3. every case has exactly one oracle action code
4. all action codes are one of `AI`, `ALT1`, `ALT2`
5. every case has a valid `scenario_id`
6. every `scenario_id` resolves to a real scenario config file
7. every case has a fully materialized `initial_state_snapshot`
8. every snapshot uses canonical entity IDs only
9. `agent_recommendation_action_code` defaults to `AI` if missing
10. generated `case_summary.csv` matches case JSON values

### Strongly recommended validations
11. if `ai_correct == true`, then `oracle_action_code == "AI"`
12. if `oracle_action_code != "AI"`, the case is flagged as a candidate for future “AI suboptimal” behavior testing
13. ambiguity / gap metadata is preserved from the uploaded bank

---

## Build script requirements

Claude must implement `scripts/build_cases_from_bank.py`.

### Script responsibilities
- load `TianshiWang_Redesigned_Scenario_Bank_v3.csv`
- optionally load `Integrated_Scenario_Parameterization.xlsx` for cross-checks and metadata support
- generate the baseline twin if absent
- generate scenario JSON files if absent
- generate case JSON files
- generate `case_summary.csv`
- run validation

### Script behavior
The script must be deterministic and rerunnable.
If outputs already exist, it may overwrite them cleanly or update them consistently.

### Logging
Script should print a concise build summary such as:
- number of scenarios written
- number of cases written
- validation status
- any explicit TODO assumptions

---

## Tests that must be implemented

### `tests/test_case_generation.py`
At minimum test:
- all 20 cases are generated
- all case JSON files parse successfully
- all cost formulas validate
- all scenario refs resolve
- snapshots are non-empty and structurally valid

### `tests/test_evaluation.py`
At minimum test these behaviors:

#### Case 1: unnecessary override
If a case has:
- agent action = `AI`
- oracle action = `AI`
- human action = `ALT1`

then:
- `is_unnecessary_override == True`

#### Case 2: regret positive
If oracle is `AI` and human action is `ALT2` with higher cost:
- `compute_regret > 0`

#### Case 3: regret zero
If human action equals oracle action:
- `compute_regret == 0`

#### Case 4: override effectiveness
If human override cost < agent cost:
- `compute_override_effectiveness == "cost_reducing"`

---

## File modification policy

### Allowed files to modify
- `data/baseline_twin_state.json`
- `data/scenarios/*`
- `data/cases/*`
- `data/case_summary.csv`
- `data/mappings/*` (optional)
- `scripts/build_cases_from_bank.py`
- `src/evaluation.py`
- `tests/test_case_generation.py`
- `tests/test_evaluation.py`

### Do not touch
- `src/twin_state.py`
- any agent files
- graph files
- Streamlit files
- unrelated repository structure

If a tiny compatibility helper is absolutely necessary, keep it isolated and justify it clearly. Do not perform opportunistic refactors.

---

## Assumption policy

When information is missing, use this strict hierarchy:

### Level 1: uploaded case bank truth
If available there, use it.

### Level 2: deterministic canonical mapping rule
If not available directly, apply a fixed mapping rule described in this spec.

### Level 3: documented deterministic default
If still unavailable, use a minimal fixed default and log it.

### Forbidden behavior
- no silent guessing
- no LLM-generated numeric truth
- no changing oracle labels to make simulation look cleaner

---

## Required metadata / TODO markers

If any scenario or snapshot field cannot be strongly grounded, Claude must preserve a note in metadata, for example:

```json
{
  "notes": [
    "Used canonical entity mapping: carrier issue -> CAR_A",
    "Weather coordinates unavailable; fallback-only mode used"
  ]
}
```

This is required transparency, not optional verbosity.

---

## P01 example that must work exactly

Use P01 as a reference example to ensure the pipeline is correct.

P01 must preserve these truths:

- `case_id = P01`
- `block_type = practice`
- `scenario_type = Inventory Discrepancy`
- `risk_level = LOW`
- `ai_correct = true`
- `oracle_action_code = AI`
- `c_dir_ai = 40`
- `c_out_ai = 40`
- `c_total_ai = 80`
- `c_dir_alt1 = 140`
- `c_out_alt1 = 60`
- `c_total_alt1 = 200`
- `c_dir_alt2 = 100`
- `c_out_alt2 = 120`
- `c_total_alt2 = 220`
- `oracle_cost = 80`

If the generated P01 does not preserve these values exactly, the bridge is wrong.

---

## Implementation order Claude must follow

Claude must work in this order and stop scope expansion:

1. inspect uploaded CSV/XLSX schema
2. create baseline twin defaults
3. create canonical scenario JSON files
4. create case-to-scenario mapping rules
5. generate case JSON files
6. generate case summary CSV
7. implement evaluation contract
8. implement tests
9. run validations
10. report assumptions and changed files

Do not jump ahead to agent, UI, or graph work.

---

## Output reporting format required from Claude

At the end of implementation, Claude must report:

1. files created / modified
2. mapping strategy used
3. baseline defaults used
4. validation results
5. remaining TODO markers, if any
6. confirmation that:
   - oracle truth comes from uploaded bank
   - TwinState was not redesigned
   - evaluation uses lookup truth, not simulation recomputation

---

## Acceptance criteria

This task is complete only if all of the following are true:

1. `data/baseline_twin_state.json` exists and is usable
2. `data/scenarios/` contains 5 to 8 reusable scenario configs
3. `data/cases/` contains 20 valid case JSON files
4. all case files preserve uploaded oracle and split-cost truth
5. every case has a populated `initial_state_snapshot`
6. every case has a valid `scenario_config_ref`
7. `src/evaluation.py` computes regret and unnecessary override from case lookup truth
8. tests pass
9. no changes were made to `src/twin_state.py`
10. no numeric ground truth was invented by LLM logic

---

## Final reminder

This is an MVP bridge task.

The purpose is not to make the twin perfectly realistic.
The purpose is to make the project **structurally complete, deterministic, thesis-aligned, and demo-safe**.

If there is tension between realism and stability, choose stability.
If there is tension between simulation elegance and oracle determinism, choose oracle determinism.
If there is tension between cleverness and scope discipline, choose scope discipline.
