"""
twin_state.py — Supply Chain Twin MVP: data models and TwinState runtime object.

All models use Pydantic v2. TwinState is a real object, not a prompt blob.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


# ---------------------------------------------------------------------------
# Entity models
# ---------------------------------------------------------------------------


class Supplier(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str
    name: str
    lead_time_days: int
    reliability_score: float
    capacity_units: int
    is_active: bool = True

    @field_validator("reliability_score")
    @classmethod
    def check_reliability_score(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"reliability_score must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("lead_time_days", "capacity_units")
    @classmethod
    def check_non_negative_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"Value must be >= 0, got {v}")
        return v


class Warehouse(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str
    name: str
    location: str
    max_capacity: int
    current_inventory: int
    operating_cost_per_unit: float

    @field_validator("max_capacity", "current_inventory")
    @classmethod
    def check_non_negative_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"Value must be >= 0, got {v}")
        return v

    @field_validator("operating_cost_per_unit")
    @classmethod
    def check_non_negative_float(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"operating_cost_per_unit must be >= 0, got {v}")
        return v


class Carrier(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str
    name: str
    available: bool
    cost_per_unit: float
    transit_time_hours: float
    capacity_limit: int

    @field_validator("cost_per_unit", "transit_time_hours")
    @classmethod
    def check_non_negative_float(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"Value must be >= 0, got {v}")
        return v

    @field_validator("capacity_limit")
    @classmethod
    def check_non_negative_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"capacity_limit must be >= 0, got {v}")
        return v


class CustomerZone(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str
    name: str
    demand_units: int
    sla_deadline_hours: float
    sla_penalty_per_hour: float

    @field_validator("demand_units")
    @classmethod
    def check_demand_units(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"demand_units must be >= 0, got {v}")
        return v

    @field_validator("sla_deadline_hours", "sla_penalty_per_hour")
    @classmethod
    def check_non_negative_float(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"Value must be >= 0, got {v}")
        return v


class CostPolicy(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    expedite_multiplier: float = 2.0
    transfer_fixed_fee: float = 30.0
    transfer_unit_cost: float = 1.5
    default_compensation_per_unit: float = 4.0
    default_penalty_relief_per_hour: float = 1.5
    verify_review_overhead: float = 140.0

    @field_validator(
        "expedite_multiplier",
        "transfer_fixed_fee",
        "transfer_unit_cost",
        "default_compensation_per_unit",
        "default_penalty_relief_per_hour",
        "verify_review_overhead",
    )
    @classmethod
    def check_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"CostPolicy fields must be > 0, got {v}")
        return v


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    EXPEDITE = "EXPEDITE"
    TRANSFER = "TRANSFER"
    COMPENSATE = "COMPENSATE"
    NO_ACTION = "NO_ACTION"


class SupervisorDecisionType(str, Enum):
    """Supervisor-layer decision type. NOT an operational action; lives outside TwinState."""

    APPROVE = "APPROVE"
    VERIFY = "VERIFY"
    OVERRIDE = "OVERRIDE"


# ---------------------------------------------------------------------------
# Action model
# ---------------------------------------------------------------------------


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

    @field_validator("units")
    @classmethod
    def check_units_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"units must be > 0, got {v}")
        return v


# ---------------------------------------------------------------------------
# Module-level patch helper (used by TwinState.inject_shock for atomicity)
# ---------------------------------------------------------------------------


def _run_patches(state: TwinState, patches: list[dict]) -> None:
    """Apply *patches* to *state* in-place, in input order.

    Raises ``ValueError`` on unknown op, missing entity, or constraint violation.
    Does NOT touch ``state.current_disruptions``; that is the caller's job.
    Defined at module level so ``inject_shock`` can call it on both a deep-copy
    draft (validation phase) and on ``self`` (commit phase).
    """
    entity_map: dict = {
        "supplier": state.suppliers,
        "warehouse": state.warehouses,
        "carrier": state.carriers,
        "customer_zone": state.customer_zones,
    }
    for patch in patches:
        entity_type: str = patch["entity_type"]
        op: str = patch["op"]
        field: str = patch["field"]
        value = patch["value"]

        if op not in ("set", "add", "multiply"):
            raise ValueError(
                f"Unknown op '{op}'. Must be one of: set, add, multiply."
            )

        if entity_type == "twin":
            current = getattr(state, field)
            new_value = (
                value
                if op == "set"
                else (current + value if op == "add" else current * value)
            )
            try:
                setattr(state, field, new_value)
            except ValidationError as exc:
                raise ValueError(
                    f"Patch twin.{field}={new_value} violates constraints: {exc}"
                ) from exc
        else:
            entity_store = entity_map.get(entity_type)
            if entity_store is None:
                raise ValueError(f"Unknown entity_type '{entity_type}'")
            entity_id: str = patch["entity_id"]
            if entity_id not in entity_store:
                raise KeyError(
                    f"{entity_type} '{entity_id}' not found in state"
                )
            entity = entity_store[entity_id]
            current = getattr(entity, field)
            new_value = (
                value
                if op == "set"
                else (current + value if op == "add" else current * value)
            )
            try:
                setattr(entity, field, new_value)
            except ValidationError as exc:
                raise ValueError(
                    f"Patch {entity_type}.{entity_id}.{field}={new_value} "
                    f"violates constraints: {exc}"
                ) from exc


# ---------------------------------------------------------------------------
# TwinState
# ---------------------------------------------------------------------------


class TwinState(BaseModel):
    """Runtime supply chain twin. All mutations go through apply_action / inject_shock."""

    model_config = ConfigDict(validate_assignment=True)

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

    @field_validator("order_units")
    @classmethod
    def check_order_units(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"order_units must be > 0, got {v}")
        return v

    @field_validator("planned_eta_hours")
    @classmethod
    def check_planned_eta_hours(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"planned_eta_hours must be >= 0, got {v}")
        return v

    # ------------------------------------------------------------------
    # Class-level factory
    # ------------------------------------------------------------------

    @classmethod
    def initialize_from_config(cls, path: str) -> "TwinState":
        """Load a canonical baseline config JSON and construct a valid TwinState.

        MVP enforcement: raises ValueError if there are not exactly
        2 suppliers / 2 warehouses / 2 carriers / 2 customer zones.
        """
        with open(path, "r") as f:
            data = json.load(f)

        MVP_COUNTS = [
            ("suppliers", 2),
            ("warehouses", 2),
            ("carriers", 2),
            ("customer_zones", 2),
        ]
        for key, required in MVP_COUNTS:
            actual = len(data[key])
            if actual != required:
                raise ValueError(
                    f"MVP requires exactly {required} {key}, got {actual}"
                )

        suppliers = {s["id"]: Supplier(**s) for s in data["suppliers"]}
        warehouses = {w["id"]: Warehouse(**w) for w in data["warehouses"]}
        carriers = {c["id"]: Carrier(**c) for c in data["carriers"]}
        customer_zones = {z["id"]: CustomerZone(**z) for z in data["customer_zones"]}
        cost_policy = CostPolicy(**data["cost_policy"])

        order = data["active_order"]

        return cls(
            timestamp=datetime.fromisoformat(
                data["timestamp"].replace("Z", "+00:00")
            ),
            suppliers=suppliers,
            warehouses=warehouses,
            carriers=carriers,
            customer_zones=customer_zones,
            current_disruptions=list(data.get("current_disruptions", [])),
            order_id=order["order_id"],
            order_units=order["order_units"],
            source_warehouse_id=order["source_warehouse_id"],
            customer_zone_id=order["customer_zone_id"],
            planned_carrier_id=order["planned_carrier_id"],
            planned_eta_hours=float(order["planned_eta_hours"]),
            cost_policy=cost_policy,
        )

    # ------------------------------------------------------------------
    # Shock injection
    # ------------------------------------------------------------------

    def inject_shock(self, shock_config: dict) -> None:
        """Apply deterministic patches atomically from shock_config["entity_patches"].

        Atomicity guarantee
        -------------------
        All patches are first validated on a deep-copy draft.  Only when every
        patch succeeds are the changes committed to ``self``.  If any patch
        fails, ``self`` is left completely unchanged (no partial state, no
        disruption appended).

        Supported ops: ``set``, ``add``, ``multiply``.
        Supported entity_types: ``supplier``, ``warehouse``, ``carrier``,
        ``customer_zone``, ``twin``.
        """
        patches = shock_config.get("entity_patches", [])

        # ── Validation phase ──────────────────────────────────────────────
        # Apply every patch to a deep-copy draft.  If any patch raises,
        # self is untouched (draft is discarded automatically).
        draft = self.model_copy(deep=True)
        _run_patches(draft, patches)

        # ── Commit phase ──────────────────────────────────────────────────
        # All patches are known-good; apply to self (same starting state,
        # same deterministic ops → guaranteed to succeed).
        _run_patches(self, patches)
        self.current_disruptions.append(shock_config)

    # ------------------------------------------------------------------
    # Action application
    # ------------------------------------------------------------------

    def apply_action(self, action: Action) -> None:
        """Validate feasibility and mutate state for the given operational action.

        Raises ValueError on any constraint violation.
        Records self.last_applied_action on success.
        """
        if action.units != self.order_units:
            raise ValueError(
                f"action.units ({action.units}) must equal "
                f"order_units ({self.order_units})"
            )

        if action.action_type == ActionType.EXPEDITE:
            if action.target_carrier_id is None:
                raise ValueError("EXPEDITE requires target_carrier_id")
            if action.target_carrier_id not in self.carriers:
                raise ValueError(
                    f"Carrier '{action.target_carrier_id}' not found"
                )
            carrier = self.carriers[action.target_carrier_id]
            if not carrier.available:
                raise ValueError(
                    f"Carrier '{action.target_carrier_id}' is not available"
                )
            if carrier.capacity_limit < action.units:
                raise ValueError(
                    f"Carrier capacity_limit ({carrier.capacity_limit}) "
                    f"< required units ({action.units})"
                )
            self.planned_carrier_id = action.target_carrier_id
            self.planned_eta_hours = max(
                0.0, self.planned_eta_hours + action.eta_adjustment_hours
            )

        elif action.action_type == ActionType.TRANSFER:
            if action.from_warehouse_id is None or action.to_warehouse_id is None:
                raise ValueError(
                    "TRANSFER requires from_warehouse_id and to_warehouse_id"
                )
            if action.from_warehouse_id == action.to_warehouse_id:
                raise ValueError(
                    "TRANSFER from_warehouse_id and to_warehouse_id must differ"
                )
            if action.from_warehouse_id not in self.warehouses:
                raise ValueError(
                    f"Warehouse '{action.from_warehouse_id}' not found"
                )
            if action.to_warehouse_id not in self.warehouses:
                raise ValueError(
                    f"Warehouse '{action.to_warehouse_id}' not found"
                )
            src = self.warehouses[action.from_warehouse_id]
            dst = self.warehouses[action.to_warehouse_id]
            if src.current_inventory < action.units:
                raise ValueError(
                    f"Insufficient inventory in '{action.from_warehouse_id}': "
                    f"{src.current_inventory} < {action.units}"
                )
            if dst.current_inventory + action.units > dst.max_capacity:
                raise ValueError(
                    f"Transfer would exceed max_capacity of "
                    f"'{action.to_warehouse_id}': "
                    f"{dst.current_inventory + action.units} > {dst.max_capacity}"
                )
            src.current_inventory -= action.units
            dst.current_inventory += action.units
            self.planned_eta_hours = max(
                0.0, self.planned_eta_hours + action.eta_adjustment_hours
            )

        elif action.action_type == ActionType.COMPENSATE:
            zone = self.customer_zones[self.customer_zone_id]
            relief = (
                action.penalty_relief_per_hour
                if action.penalty_relief_per_hour is not None
                else self.cost_policy.default_penalty_relief_per_hour
            )
            # SPEC §7.6: 0 <= penalty_relief_per_hour < zone.sla_penalty_per_hour
            if relief < 0 or relief >= zone.sla_penalty_per_hour:
                raise ValueError(
                    f"penalty_relief_per_hour ({relief}) must satisfy "
                    f"0 <= relief < sla_penalty_per_hour ({zone.sla_penalty_per_hour})"
                )
            # No inventory, carrier, or ETA changes.

        elif action.action_type == ActionType.NO_ACTION:
            pass  # intentional no-op

        self.last_applied_action = action

    # ------------------------------------------------------------------
    # Cost computation
    # ------------------------------------------------------------------

    def compute_total_cost(self) -> float:
        """Compute deterministic total cost for the last applied action.

        Raises RuntimeError if called before apply_action.
        Writes breakdown into self.last_cost_breakdown.
        Returns total as float.
        """
        if self.last_applied_action is None:
            raise RuntimeError(
                "compute_total_cost() must be called after apply_action()"
            )

        action = self.last_applied_action
        q = self.order_units
        zone = self.customer_zones[self.customer_zone_id]
        policy = self.cost_policy
        eta_after = max(0.0, self.planned_eta_hours)
        late_hours = max(0.0, eta_after - zone.sla_deadline_hours)

        if action.action_type == ActionType.EXPEDITE:
            carrier = self.carriers[self.planned_carrier_id]
            direct = q * carrier.cost_per_unit * policy.expedite_multiplier
            penalty = late_hours * q * zone.sla_penalty_per_hour

        elif action.action_type == ActionType.TRANSFER:
            dest_wh = self.warehouses[action.to_warehouse_id]
            direct = (
                policy.transfer_fixed_fee
                + q * policy.transfer_unit_cost
                + q * dest_wh.operating_cost_per_unit
            )
            penalty = late_hours * q * zone.sla_penalty_per_hour

        elif action.action_type == ActionType.COMPENSATE:
            comp = (
                action.compensation_per_unit
                if action.compensation_per_unit is not None
                else policy.default_compensation_per_unit
            )
            relief = (
                action.penalty_relief_per_hour
                if action.penalty_relief_per_hour is not None
                else policy.default_penalty_relief_per_hour
            )
            direct = q * comp
            effective_rate = zone.sla_penalty_per_hour - relief
            penalty = late_hours * q * effective_rate

        else:  # NO_ACTION
            direct = 0.0
            penalty = late_hours * q * zone.sla_penalty_per_hour

        total = direct + penalty

        self.last_cost_breakdown = {
            "action_type": action.action_type.value,
            "direct_action_cost": direct,
            "sla_lateness_penalty": penalty,
            "total_cost": total,
            "eta_after_action": eta_after,
            "late_hours": late_hours,
        }

        return float(total)

    # ------------------------------------------------------------------
    # Prompt serialization — SPEC §8 exact schema
    # ------------------------------------------------------------------

    def to_prompt_context(
        self, allowed_operational_actions: list[dict] | None = None
    ) -> str:
        """Serialize TwinState to a stable JSON string for agent consumption.

        Output follows SPEC §8 exact JSON schema — fixed key order, entities
        sorted by id. Does NOT include oracle fields or precomputed cost labels.
        Uses json.dumps(ensure_ascii=False, indent=2).
        """
        # Timestamp as UTC ISO string
        ts_str = self.timestamp.isoformat().replace("+00:00", "Z")

        # Active order block
        active_order = {
            "order_id": self.order_id,
            "order_units": self.order_units,
            "source_warehouse_id": self.source_warehouse_id,
            "customer_zone_id": self.customer_zone_id,
            "planned_carrier_id": self.planned_carrier_id,
            "planned_eta_hours": self.planned_eta_hours,
        }

        # Entity lists sorted by id, all fields via model_dump()
        suppliers_list = sorted(
            [s.model_dump() for s in self.suppliers.values()],
            key=lambda x: x["id"],
        )
        warehouses_list = sorted(
            [w.model_dump() for w in self.warehouses.values()],
            key=lambda x: x["id"],
        )
        carriers_list = sorted(
            [c.model_dump() for c in self.carriers.values()],
            key=lambda x: x["id"],
        )
        customer_zones_list = sorted(
            [z.model_dump() for z in self.customer_zones.values()],
            key=lambda x: x["id"],
        )

        # cost_policy: omit verify_review_overhead (not exposed to agents)
        cost_policy_block = {
            "expedite_multiplier": self.cost_policy.expedite_multiplier,
            "transfer_fixed_fee": self.cost_policy.transfer_fixed_fee,
            "transfer_unit_cost": self.cost_policy.transfer_unit_cost,
            "default_compensation_per_unit": self.cost_policy.default_compensation_per_unit,
            "default_penalty_relief_per_hour": self.cost_policy.default_penalty_relief_per_hour,
        }

        # Fixed top-level key order per SPEC §8.2
        payload = {
            "timestamp": ts_str,
            "active_order": active_order,
            "current_disruptions": self.current_disruptions,
            "suppliers": suppliers_list,
            "warehouses": warehouses_list,
            "carriers": carriers_list,
            "customer_zones": customer_zones_list,
            "cost_policy": cost_policy_block,
            "allowed_operational_actions": (
                allowed_operational_actions
                if allowed_operational_actions is not None
                else []
            ),
        }

        return json.dumps(payload, ensure_ascii=False, indent=2)
