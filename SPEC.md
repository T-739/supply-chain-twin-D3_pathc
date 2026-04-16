# Supply Chain Twin MVP — Final Engineering SPEC

## 1. Objective

This document is the final implementation-ready specification for the Twin State layer and deterministic cost logic of the supply chain twin MVP.

It is designed to support the project critical path:
1. Twin State Schema
2. Synthetic Cases with ground truth
3. Governance Agent
4. Streamlit UI

This spec intentionally keeps the MVP small and deterministic:
- 2 suppliers
- 2 warehouses
- 2 carriers
- 2 customer zones
- linear cost logic only
- no optimization engine
- no stochastic simulation
- Twin State must be a real object, not a prompt blob

This spec also resolves four blocking gaps identified during cross-check:
1. canonical `baseline_network.json` values are now locked
2. `eta_adjustment_hours` requirements are now grounded with complete translation examples
3. `to_prompt_context()` output is now fixed to an exact JSON string schema
4. oracle tie-breaking is now explicitly defined

---

## 2. Verdict on the Four Reported Gaps

### Gap 1 — `baseline_network.json` parameters were missing
**Verdict: real and must be fixed.**

Without locked baseline numeric values, `compute_total_cost()` cannot produce stable ground truth across cases, and `oracle_cost` cannot be generated deterministically.

### Gap 2 — `eta_adjustment_hours` per case/action was not grounded
**Verdict: real and must be fixed.**

`eta_adjustment_hours` is a direct input to lateness cost. If it is left for Claude to invent case by case, oracle costs will drift.

### Gap 3 — `to_prompt_context()` output format was not fixed
**Verdict: real and should be fixed.**

The previous version specified required content but not exact structure. That is enough for human reading, but not stable enough for agent orchestration. A fixed JSON string schema is required.

### Gap 4 — tie-breaking for equal-cost oracle actions was undefined
**Verdict: real and must be fixed.**

If two actions have identical total cost, a single `optimal_action` label becomes ambiguous unless the tie rule is fixed. This affects strict action-accuracy reporting.

---

## 3. MVP Scope Boundaries

### In scope
- initialization from baseline config
- deterministic shock injection
- deterministic operational action application
- deterministic cost computation
- deterministic prompt serialization
- case translation from narrative cases into canonical runtime inputs

### Out of scope
- optimization engines
- strategic planning layer
- multi-SKU inventory model
- stochastic lead time distributions
- route optimization
- multi-hop replenishment
- autonomous action generation beyond predefined action set

---

## 4. Canonical Baseline Configuration

The following is the canonical baseline network. It must be saved as:

`data/configs/baseline_network.json`

```json
{
  "timestamp": "2026-04-01T09:00:00Z",
  "suppliers": [
    {
      "id": "SUP_1",
      "name": "Shenzhen Apparel Co.",
      "lead_time_days": 5,
      "reliability_score": 0.95,
      "capacity_units": 400,
      "is_active": true
    },
    {
      "id": "SUP_2",
      "name": "Guangzhou Backup Co.",
      "lead_time_days": 8,
      "reliability_score": 0.88,
      "capacity_units": 250,
      "is_active": true
    }
  ],
  "warehouses": [
    {
      "id": "WH_1",
      "name": "Montreal DC",
      "location": "Montreal",
      "max_capacity": 500,
      "current_inventory": 120,
      "operating_cost_per_unit": 0.5
    },
    {
      "id": "WH_2",
      "name": "Toronto DC",
      "location": "Toronto",
      "max_capacity": 450,
      "current_inventory": 90,
      "operating_cost_per_unit": 0.8
    }
  ],
  "carriers": [
    {
      "id": "CR_1",
      "name": "StandardGround",
      "available": true,
      "cost_per_unit": 3.0,
      "transit_time_hours": 36,
      "capacity_limit": 100
    },
    {
      "id": "CR_2",
      "name": "ExpressAir",
      "available": true,
      "cost_per_unit": 6.0,
      "transit_time_hours": 18,
      "capacity_limit": 60
    }
  ],
  "customer_zones": [
    {
      "id": "CZ_1",
      "name": "Quebec Urban",
      "demand_units": 10,
      "sla_deadline_hours": 24,
      "sla_penalty_per_hour": 5.0
    },
    {
      "id": "CZ_2",
      "name": "Ontario Key Accounts",
      "demand_units": 8,
      "sla_deadline_hours": 18,
      "sla_penalty_per_hour": 8.0
    }
  ],
  "active_order": {
    "order_id": "ORD_BASE_001",
    "order_units": 10,
    "source_warehouse_id": "WH_1",
    "customer_zone_id": "CZ_1",
    "planned_carrier_id": "CR_1",
    "planned_eta_hours": 36
  },
  "cost_policy": {
    "expedite_multiplier": 2.0,
    "transfer_fixed_fee": 30.0,
    "transfer_unit_cost": 1.5,
    "default_compensation_per_unit": 4.0,
    "default_penalty_relief_per_hour": 1.5,
    "verify_review_overhead": 140.0
  },
  "current_disruptions": []
}
```

### Notes on baseline usage
- This baseline is the single numeric source of truth for the runtime twin.
- Individual cases may patch these values.
- The uploaded scenario bank remains useful as a narrative case source and sanity-check source, but runtime ground truth must be generated from this baseline plus deterministic case patches.

---

## 5. Recommended Python Data Model

Use **Pydantic v2**.

### 5.1 Supplier

```python
class Supplier(BaseModel):
    id: str
    name: str
    lead_time_days: int
    reliability_score: float
    capacity_units: int
    is_active: bool = True
```

### 5.2 Warehouse

```python
class Warehouse(BaseModel):
    id: str
    name: str
    location: str
    max_capacity: int
    current_inventory: int
    operating_cost_per_unit: float
```

### 5.3 Carrier

```python
class Carrier(BaseModel):
    id: str
    name: str
    available: bool
    cost_per_unit: float
    transit_time_hours: float
    capacity_limit: int
```

### 5.4 CustomerZone

```python
class CustomerZone(BaseModel):
    id: str
    name: str
    demand_units: int
    sla_deadline_hours: float
    sla_penalty_per_hour: float
```

### 5.5 CostPolicy

```python
class CostPolicy(BaseModel):
    expedite_multiplier: float = 2.0
    transfer_fixed_fee: float = 30.0
    transfer_unit_cost: float = 1.5
    default_compensation_per_unit: float = 4.0
    default_penalty_relief_per_hour: float = 1.5
    verify_review_overhead: float = 140.0
```

### 5.6 ActionType

```python
class ActionType(str, Enum):
    EXPEDITE = "EXPEDITE"
    TRANSFER = "TRANSFER"
    COMPENSATE = "COMPENSATE"
    NO_ACTION = "NO_ACTION"
```

### 5.7 Operational Action

```python
class Action(BaseModel):
    action_id: str
    action_type: ActionType
    units: int

    target_carrier_id: str | None = None
    from_warehouse_id: str | None = None
    to_warehouse_id: str | None = None

    eta_adjustment_hours: float = 0.0
    compensation_per_unit: float | None = None
    penalty_relief_per_hour: float | None = None

    description: str | None = None
```

### 5.8 SupervisorDecisionType

This is not part of TwinState operational logic, but it is required to preserve the legacy case bank semantics.

```python
class SupervisorDecisionType(str, Enum):
    APPROVE = "APPROVE"
    VERIFY = "VERIFY"
    OVERRIDE = "OVERRIDE"
```

### 5.9 TwinState

```python
class TwinState(BaseModel):
    timestamp: datetime

    suppliers: dict[str, Supplier]
    warehouses: dict[str, Warehouse]
    carriers: dict[str, Carrier]
    customer_zones: dict[str, CustomerZone]

    current_disruptions: list[dict]

    order_id: str
    order_units: int
    source_warehouse_id: str
    customer_zone_id: str
    planned_carrier_id: str
    planned_eta_hours: float

    cost_policy: CostPolicy

    last_applied_action: Action | None = None
    last_cost_breakdown: dict | None = None
```

---

## 6. Required Methods

### 6.1 `initialize_from_config(path)`

**Goal**: load a canonical baseline config and construct a valid `TwinState`.

**Requirements**:
- must validate schema using Pydantic
- must fail fast if counts are not exactly 2 suppliers / 2 warehouses / 2 carriers / 2 customer zones for MVP mode
- must populate active order fields onto `TwinState`

### 6.2 `inject_shock(shock_config)`

**Goal**: apply deterministic scenario patches.

**Allowed patch operations**:
- `set`
- `add`
- `multiply`

**Recommended patch format**:

```json
{
  "scenario_id": "storm_qc",
  "description": "CR_1 unavailable and ETA +24h",
  "entity_patches": [
    {"entity_type": "carrier", "entity_id": "CR_1", "op": "set", "field": "available", "value": false},
    {"entity_type": "twin", "op": "add", "field": "planned_eta_hours", "value": 24}
  ]
}
```

### 6.3 `apply_action(action)`

**Goal**: validate and mutate the state using a canonical operational action.

**Rules by action type**:

#### EXPEDITE
- `target_carrier_id` is required
- target carrier must exist and be available
- target carrier capacity must be >= `units`
- `planned_carrier_id` becomes `target_carrier_id`
- `planned_eta_hours += eta_adjustment_hours`

#### TRANSFER
- `from_warehouse_id` and `to_warehouse_id` are required
- source warehouse must have enough inventory
- destination warehouse must not exceed `max_capacity`
- deduct from source inventory
- add to destination inventory
- `planned_eta_hours += eta_adjustment_hours`

#### COMPENSATE
- does not change inventory or carrier
- may set `compensation_per_unit`
- may set `penalty_relief_per_hour`
- `planned_eta_hours` usually unchanged

#### NO_ACTION
- does not change inventory or carrier
- `planned_eta_hours` usually unchanged

### 6.4 `compute_total_cost()`

**Goal**: compute deterministic total cost after an action has been applied.

Must return a numeric `float`, and also write a debug-friendly breakdown into `last_cost_breakdown`.

Required breakdown keys:

```python
{
    "direct_action_cost": ...,
    "sla_lateness_penalty": ...,
    "total_cost": ...,
    "eta_after_action": ...,
    "late_hours": ...
}
```

### 6.5 `to_prompt_context()`

**Goal**: return a stable JSON string for agents.

This is a serialization method only. It must not leak oracle labels or precomputed hidden outcomes.

---

## 7. Deterministic Cost Logic

### 7.1 Shared symbols

Let:
- `q = state.order_units`
- `zone = state.customer_zones[state.customer_zone_id]`
- `eta_after = max(0, state.planned_eta_hours)`
- `late_hours = max(0, eta_after - zone.sla_deadline_hours)`

### 7.2 EXPEDITE direct cost

```text
direct_expedite_cost = q * selected_carrier.cost_per_unit * cost_policy.expedite_multiplier
```

### 7.3 TRANSFER direct cost

```text
direct_transfer_cost = cost_policy.transfer_fixed_fee
                     + q * cost_policy.transfer_unit_cost
                     + q * destination_warehouse.operating_cost_per_unit
```

### 7.4 COMPENSATE direct cost

```text
direct_compensation_cost = q * compensation_per_unit
```

If `compensation_per_unit` is not provided, use `cost_policy.default_compensation_per_unit`.

### 7.5 NO_ACTION direct cost

```text
direct_no_action_cost = 0
```

### 7.6 SLA lateness penalty

For `EXPEDITE`, `TRANSFER`, and `NO_ACTION`:

```text
sla_penalty = late_hours * q * zone.sla_penalty_per_hour
```

For `COMPENSATE`:

```text
effective_penalty_rate = zone.sla_penalty_per_hour - penalty_relief_per_hour
sla_penalty = late_hours * q * effective_penalty_rate
```

Validation rule:

```text
0 <= penalty_relief_per_hour < zone.sla_penalty_per_hour
```

If `penalty_relief_per_hour` is omitted, use `cost_policy.default_penalty_relief_per_hour`.

### 7.7 Total cost

```text
total_cost = direct_action_cost + sla_lateness_penalty
```

### 7.8 Important modeling clarification about `VERIFY`

`VERIFY` is **not** an operational action and must **not** be added to `ActionType`.

To preserve compatibility with the uploaded case bank where some legacy oracle labels are `Verify`:
- `VERIFY` remains a **supervisor-layer decision**
- if a user chooses `VERIFY`, a fixed review overhead may be added at the experiment/UI layer:

```text
review_overhead = cost_policy.verify_review_overhead = 140.0
```

- after verification, the workflow must resolve to one canonical operational action (`EXPEDITE`, `TRANSFER`, `COMPENSATE`, or `NO_ACTION`)
- TwinState only applies the resolved operational action

This keeps the runtime twin clean while still allowing the old case bank to be translated.

---

## 8. Exact `to_prompt_context()` Output Contract

### 8.1 Return type
Return a **JSON string**.

### 8.2 Serialization rules
- top-level keys must appear in the exact order shown below
- entity lists must be sorted by `id`
- `allowed_operational_actions` must be included if provided by caller; otherwise use an empty list
- do not include any oracle fields
- do not include any hidden cost labels from the uploaded spreadsheets

### 8.3 Exact JSON schema

```json
{
  "timestamp": "2026-04-01T09:00:00Z",
  "active_order": {
    "order_id": "ORD_BASE_001",
    "order_units": 10,
    "source_warehouse_id": "WH_1",
    "customer_zone_id": "CZ_1",
    "planned_carrier_id": "CR_1",
    "planned_eta_hours": 36
  },
  "current_disruptions": [],
  "suppliers": [
    {
      "id": "SUP_1",
      "name": "Shenzhen Apparel Co.",
      "lead_time_days": 5,
      "reliability_score": 0.95,
      "capacity_units": 400,
      "is_active": true
    },
    {
      "id": "SUP_2",
      "name": "Guangzhou Backup Co.",
      "lead_time_days": 8,
      "reliability_score": 0.88,
      "capacity_units": 250,
      "is_active": true
    }
  ],
  "warehouses": [
    {
      "id": "WH_1",
      "name": "Montreal DC",
      "location": "Montreal",
      "max_capacity": 500,
      "current_inventory": 120,
      "operating_cost_per_unit": 0.5
    },
    {
      "id": "WH_2",
      "name": "Toronto DC",
      "location": "Toronto",
      "max_capacity": 450,
      "current_inventory": 90,
      "operating_cost_per_unit": 0.8
    }
  ],
  "carriers": [
    {
      "id": "CR_1",
      "name": "StandardGround",
      "available": true,
      "cost_per_unit": 3.0,
      "transit_time_hours": 36,
      "capacity_limit": 100
    },
    {
      "id": "CR_2",
      "name": "ExpressAir",
      "available": true,
      "cost_per_unit": 6.0,
      "transit_time_hours": 18,
      "capacity_limit": 60
    }
  ],
  "customer_zones": [
    {
      "id": "CZ_1",
      "name": "Quebec Urban",
      "demand_units": 10,
      "sla_deadline_hours": 24,
      "sla_penalty_per_hour": 5.0
    },
    {
      "id": "CZ_2",
      "name": "Ontario Key Accounts",
      "demand_units": 8,
      "sla_deadline_hours": 18,
      "sla_penalty_per_hour": 8.0
    }
  ],
  "cost_policy": {
    "expedite_multiplier": 2.0,
    "transfer_fixed_fee": 30.0,
    "transfer_unit_cost": 1.5,
    "default_compensation_per_unit": 4.0,
    "default_penalty_relief_per_hour": 1.5
  },
  "allowed_operational_actions": [
    {
      "action_id": "A1",
      "action_type": "NO_ACTION",
      "units": 10,
      "eta_adjustment_hours": 0.0,
      "description": "Keep current plan"
    },
    {
      "action_id": "A2",
      "action_type": "EXPEDITE",
      "units": 10,
      "target_carrier_id": "CR_2",
      "eta_adjustment_hours": -18.0,
      "description": "Switch to ExpressAir"
    }
  ]
}
```

### 8.4 Implementation rule
`to_prompt_context()` must produce a JSON string using a fixed dict layout and `json.dumps(..., ensure_ascii=False, indent=2)`.

---

## 9. Oracle Definition and Tie-Breaking

### 9.1 Primary rule
For any case, compute all candidate action total costs.

```text
oracle_cost = minimum(total_cost over all feasible candidate operational actions)
```

### 9.2 Co-optimal set
If more than one feasible action has the same minimum total cost, store:

```text
optimal_action_set = all actions with total_cost == oracle_cost
```

### 9.3 Single canonical `optimal_action`
To keep downstream dashboards simple, also store one single canonical `optimal_action` using this deterministic sequence:

1. lowest `total_cost`
2. if tied, lowest `sla_lateness_penalty`
3. if tied, lowest `direct_action_cost`
4. if still tied, fixed priority order:
   - `EXPEDITE`
   - `TRANSFER`
   - `COMPENSATE`
   - `NO_ACTION`

### 9.4 Evaluation usage
- **Regret** uses `oracle_cost`
- **Cost-optimality check** may treat any member of `optimal_action_set` as correct
- **Strict action-match accuracy** uses single `optimal_action`

This removes ambiguity while avoiding unfair penalization for equal-cost alternatives.

---

## 10. Legacy Case Translation Rules

The uploaded CSV is useful, but it is not a runtime twin-state file. It is a narrative case bank.

### 10.1 What the translation step must do
For each legacy case, generate a canonical translated case object containing:
- `case_id`
- `baseline_path`
- `state_patches`
- `candidate_operational_actions`
- optional `supervisor_metadata`
- `oracle_cost`
- `optimal_action_set`
- `optimal_action`

### 10.2 Translation rules

#### Rule A — legacy `Approve`
Translate into one operational action, usually the AI-recommended domain action.

#### Rule B — legacy `Alternative`
Translate into one explicit operational override action.

#### Rule C — legacy `Verify`
Do **not** place `VERIFY` inside TwinState.
Instead store:
- `preferred_supervisor_mode = "VERIFY"`
- `verify_review_overhead = 140.0`
- `verify_resolved_action = {canonical operational action}`

At runtime:
- TwinState applies only `verify_resolved_action`
- if the UI experiment is enabled, the outer workflow may add review overhead

### 10.3 Required translated fields per action
Each translated action record must include:
- `action_id`
- `action_type`
- `units`
- `eta_adjustment_hours`
- if `EXPEDITE`: `target_carrier_id`
- if `TRANSFER`: `from_warehouse_id`, `to_warehouse_id`
- if `COMPENSATE`: `compensation_per_unit`, `penalty_relief_per_hour`
- `description`

---

## 11. Three Complete Translation Examples

These are reference examples for `case_translation.py`. Claude must follow this exact field style.

### Example T1 — AI-correct no-action case

```json
{
  "case_id": "T1_LOW_NO_ACTION",
  "baseline_path": "data/configs/baseline_network.json",
  "state_patches": [
    {"entity_type": "twin", "op": "set", "field": "order_id", "value": "ORD_T1"},
    {"entity_type": "twin", "op": "set", "field": "order_units", "value": 10},
    {"entity_type": "twin", "op": "set", "field": "customer_zone_id", "value": "CZ_1"},
    {"entity_type": "twin", "op": "set", "field": "source_warehouse_id", "value": "WH_1"},
    {"entity_type": "twin", "op": "set", "field": "planned_carrier_id", "value": "CR_1"},
    {"entity_type": "twin", "op": "set", "field": "planned_eta_hours", "value": 20}
  ],
  "candidate_operational_actions": {
    "ai": {
      "action_id": "T1_AI",
      "action_type": "NO_ACTION",
      "units": 10,
      "eta_adjustment_hours": 0,
      "description": "Keep current plan"
    },
    "alt1": {
      "action_id": "T1_ALT1",
      "action_type": "TRANSFER",
      "units": 10,
      "from_warehouse_id": "WH_2",
      "to_warehouse_id": "WH_1",
      "eta_adjustment_hours": 4,
      "description": "Pull reserve stock even though no delay risk exists"
    },
    "alt2": {
      "action_id": "T1_ALT2",
      "action_type": "COMPENSATE",
      "units": 10,
      "eta_adjustment_hours": 0,
      "compensation_per_unit": 6.0,
      "penalty_relief_per_hour": 1.0,
      "description": "Offer compensation even though order is on time"
    }
  },
  "expected_costs": {
    "ai": 0.0,
    "alt1": 50.0,
    "alt2": 60.0
  },
  "oracle_cost": 0.0,
  "optimal_action_set": ["ai"],
  "optimal_action": "ai"
}
```

**Check math**
- AI: no delay, no direct cost => `0`
- ALT1 transfer: `30 + 10*1.5 + 10*0.5 = 50`
- ALT2 compensate: `10*6 = 60`

### Example T2 — expedite oracle after carrier disruption

```json
{
  "case_id": "T2_STORM_EXPEDITE",
  "baseline_path": "data/configs/baseline_network.json",
  "state_patches": [
    {"entity_type": "twin", "op": "set", "field": "order_id", "value": "ORD_T2"},
    {"entity_type": "twin", "op": "set", "field": "order_units", "value": 10},
    {"entity_type": "twin", "op": "set", "field": "customer_zone_id", "value": "CZ_1"},
    {"entity_type": "twin", "op": "set", "field": "source_warehouse_id", "value": "WH_1"},
    {"entity_type": "twin", "op": "set", "field": "planned_carrier_id", "value": "CR_1"},
    {"entity_type": "twin", "op": "set", "field": "planned_eta_hours", "value": 38},
    {"entity_type": "carrier", "entity_id": "CR_1", "op": "set", "field": "available", "value": false}
  ],
  "candidate_operational_actions": {
    "ai": {
      "action_id": "T2_AI",
      "action_type": "NO_ACTION",
      "units": 10,
      "eta_adjustment_hours": 0,
      "description": "Accept current delayed trajectory"
    },
    "alt1": {
      "action_id": "T2_ALT1",
      "action_type": "EXPEDITE",
      "units": 10,
      "target_carrier_id": "CR_2",
      "eta_adjustment_hours": -18,
      "description": "Switch to ExpressAir"
    },
    "alt2": {
      "action_id": "T2_ALT2",
      "action_type": "COMPENSATE",
      "units": 10,
      "eta_adjustment_hours": 0,
      "compensation_per_unit": 4.0,
      "penalty_relief_per_hour": 1.5,
      "description": "Offer compensation but do not accelerate shipment"
    }
  },
  "expected_costs": {
    "ai": 700.0,
    "alt1": 120.0,
    "alt2": 530.0
  },
  "oracle_cost": 120.0,
  "optimal_action_set": ["alt1"],
  "optimal_action": "alt1"
}
```

**Check math**
- AI no action: `late_hours = 38 - 24 = 14`; `14 * 10 * 5 = 700`
- ALT1 expedite: `10 * 6 * 2 = 120`; ETA `20`; late `0`; total `120`
- ALT2 compensate: direct `10*4 = 40`; penalty rate `5 - 1.5 = 3.5`; penalty `14*10*3.5 = 490`; total `530`

### Example T3 — legacy verify case translated cleanly

This example shows how to preserve a legacy `Verify` choice without polluting the TwinState action schema.

```json
{
  "case_id": "T3_VERIFY_LEGACY",
  "baseline_path": "data/configs/baseline_network.json",
  "state_patches": [
    {"entity_type": "twin", "op": "set", "field": "order_id", "value": "ORD_T3"},
    {"entity_type": "twin", "op": "set", "field": "order_units", "value": 8},
    {"entity_type": "twin", "op": "set", "field": "customer_zone_id", "value": "CZ_1"},
    {"entity_type": "twin", "op": "set", "field": "source_warehouse_id", "value": "WH_1"},
    {"entity_type": "twin", "op": "set", "field": "planned_carrier_id", "value": "CR_1"},
    {"entity_type": "twin", "op": "set", "field": "planned_eta_hours", "value": 30}
  ],
  "candidate_operational_actions": {
    "ai": {
      "action_id": "T3_AI",
      "action_type": "NO_ACTION",
      "units": 8,
      "eta_adjustment_hours": 0,
      "description": "Trust current location sync and proceed"
    },
    "alt1_verify_resolved_action": {
      "action_id": "T3_ALT1_RESOLVED",
      "action_type": "TRANSFER",
      "units": 8,
      "from_warehouse_id": "WH_2",
      "to_warehouse_id": "WH_1",
      "eta_adjustment_hours": -4,
      "description": "After verification, pull from reserve stock"
    },
    "alt2": {
      "action_id": "T3_ALT2",
      "action_type": "EXPEDITE",
      "units": 8,
      "target_carrier_id": "CR_2",
      "eta_adjustment_hours": -12,
      "description": "Expedite immediately without checking"
    }
  },
  "supervisor_metadata": {
    "legacy_alt1_label": "VERIFY",
    "preferred_supervisor_mode": "VERIFY",
    "verify_review_overhead": 140.0,
    "verify_resolved_action_key": "alt1_verify_resolved_action"
  },
  "expected_operational_costs_only": {
    "ai": 240.0,
    "alt1_verify_resolved_action": 126.0,
    "alt2": 96.0
  },
  "oracle_cost": 96.0,
  "optimal_action_set": ["alt2"],
  "optimal_action": "alt2"
}
```

**Check math**
- AI no action: `late_hours = 30 - 24 = 6`; `6 * 8 * 5 = 240`
- ALT1 resolved transfer: direct `30 + 8*1.5 + 8*0.5 = 46`; ETA `26`; penalty `2*8*5 = 80`; total `126`
- ALT2 expedite: direct `8 * 6 * 2 = 96`; ETA `18`; penalty `0`; total `96`

**Important interpretation**
- In twin runtime mode, compare the operational actions only.
- In survey/UI experiment mode, if the human literally clicks `VERIFY`, the outer layer may optionally add `140.0` review overhead on top of the resolved operational path.

---

## 12. Edge Cases

1. `EXPEDITE` selected but carrier unavailable -> raise validation error
2. `TRANSFER` source inventory insufficient -> raise validation error
3. `TRANSFER` destination capacity exceeded -> raise validation error
4. `COMPENSATE` relief rate >= zone penalty rate -> raise validation error
5. `compute_total_cost()` called before any action is applied -> raise runtime error
6. `eta_after_action < 0` -> clamp to `0`
7. duplicate shock patches on same field -> apply sequentially and log them
8. non-MVP config counts (not 2/2/2/2) in MVP mode -> initialization failure
9. `action.units != state.order_units` -> reject in MVP v1
10. negative unit counts or negative costs -> reject at validation time

---

## 13. Acceptance Criteria

### Schema level
- `initialize_from_config()` loads `baseline_network.json` without errors
- all models validate via Pydantic
- MVP entity counts are enforced

### Shock level
- `inject_shock()` applies deterministic patches correctly
- repeated run with same baseline and same shock yields same state

### Action level
- infeasible actions raise explicit errors
- `EXPEDITE`, `TRANSFER`, `COMPENSATE`, `NO_ACTION` each mutate only the fields they are allowed to mutate

### Cost level
- same state + same action always returns same total cost
- the three translation examples above reproduce their expected numeric totals exactly
- `last_cost_breakdown` is present and readable

### Prompt level
- `to_prompt_context()` returns a JSON string with the exact fixed structure in Section 8
- no oracle fields are leaked

### Evaluation level
- tie-breaking always produces both `optimal_action_set` and single `optimal_action`
- regret is computed from `oracle_cost`

---

## 14. Three Hand-Checkable Mini Examples

These are mandatory unit tests.

### Mini Example 1 — EXPEDITE wins cleanly
- `q = 10`
- `planned_eta_hours = 36`
- `sla_deadline_hours = 24`
- `selected_carrier.cost_per_unit = 3`
- action = `EXPEDITE`
- `eta_adjustment_hours = -14`

Expected:
- `eta_after = 22`
- `late_hours = 0`
- direct = `10 * 3 * 2 = 60`
- penalty = `0`
- total = `60`

### Mini Example 2 — TRANSFER is cheaper than doing nothing, but still late
- `q = 10`
- `planned_eta_hours = 36`
- `sla_deadline_hours = 24`
- `sla_penalty_per_hour = 5`
- destination warehouse `operating_cost_per_unit = 0.5`
- action = `TRANSFER`
- `eta_adjustment_hours = -8`

Expected:
- `eta_after = 28`
- `late_hours = 4`
- direct = `30 + 10*1.5 + 10*0.5 = 50`
- penalty = `4 * 10 * 5 = 200`
- total = `250`

### Mini Example 3 — COMPENSATE beats NO_ACTION when delay is unavoidable
- `q = 10`
- `planned_eta_hours = 30`
- `sla_deadline_hours = 24`
- `sla_penalty_per_hour = 5`
- action = `COMPENSATE`
- `compensation_per_unit = 4`
- `penalty_relief_per_hour = 1.5`

Expected:
- `eta_after = 30`
- `late_hours = 6`
- direct = `10 * 4 = 40`
- effective penalty rate = `3.5`
- penalty = `6 * 10 * 3.5 = 210`
- total = `250`

Reference `NO_ACTION` total under same state:
- direct = `0`
- penalty = `6 * 10 * 5 = 300`
- total = `300`

---

## 15. Handoff Note for Claude Implementation

Claude should implement in this order:

1. `data/configs/baseline_network.json`
2. `src/twin_state.py`
3. `tests/test_twin_state_costs.py`
4. `src/case_translation.py`

### Required deliverables in `src/twin_state.py`
- `Supplier`
- `Warehouse`
- `Carrier`
- `CustomerZone`
- `CostPolicy`
- `ActionType`
- `Action`
- `SupervisorDecisionType`
- `TwinState`

### Required tests
At minimum:
- test baseline config load
- test one shock injection
- test each action type once
- test all 3 mini examples exactly
- test tie-breaking rule
- test `to_prompt_context()` exact schema keys and order

### Final implementation rule
Do not use the uploaded CSV `c_total_*` columns as runtime truth.
Use them only as narrative reference or sanity-check reference.
Runtime truth must always come from:

```text
baseline_network.json + case state patches + canonical operational action + deterministic cost function
```

