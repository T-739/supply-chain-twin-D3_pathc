"""
cost_agent.py — Deterministic Cost Agent for the supply chain twin.

Produces runtime decision-support cost estimates for bounded operational
candidates (EXPEDITE, TRANSFER, COMPENSATE, NO_ACTION).

IMPORTANT — This is NOT evaluation truth.
  - Estimates use the same deterministic formulas as TwinState.compute_total_cost()
    but applied as standalone calculations on snapshot entity data.
  - These are runtime decision-support estimates for the Governance Agent.
  - Authoritative evaluation truth comes only from case JSON cost_ground_truth,
    resolved by src/evaluation.py.  This module never reads or produces oracle,
    ground_truth, regret, override, or evaluation verdict fields.

All numeric fields are deterministic for the same input.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Baseline defaults (from data/configs/baseline_network.json)
# ---------------------------------------------------------------------------
# Used when twin_state snapshot does not include cost_policy or active_order.

_DEFAULT_COST_POLICY = {
    "expedite_multiplier": 2.0,
    "transfer_fixed_fee": 30.0,
    "transfer_unit_cost": 1.5,
    "default_compensation_per_unit": 4.0,
    "default_penalty_relief_per_hour": 1.5,
}

_DEFAULT_ORDER_UNITS: int = 10
_DEFAULT_PLANNED_ETA_HOURS: float = 36.0
_DEFAULT_CUSTOMER_ZONE_ID: str = "CZ_1"


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class CandidateCostEstimate(BaseModel):
    """Cost estimate for a single operational candidate.

    All cost fields use the _estimate suffix to distinguish from
    evaluation truth (which lives in src/evaluation.py).

    For infeasible candidates:
      is_feasible = False
      direct_cost_estimate = None
      recovery_cost_estimate = None
      total_cost_estimate = None
    """

    candidate_id: str
    candidate_type: str
    is_feasible: bool
    direct_cost_estimate: float | None
    recovery_cost_estimate: float | None
    total_cost_estimate: float | None
    cost_breakdown_explanation: str
    estimation_notes: str


class CostOutput(BaseModel):
    """Structured output contract for the Cost Agent.

    cost_estimates contains one entry per operational candidate.
    This output is runtime decision-support, NOT authoritative evaluation truth.
    """

    cost_estimates: list[CandidateCostEstimate]
    order_units_used: int
    planned_eta_used: float
    cost_policy_used: dict[str, float]

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Context resolution helpers
# ---------------------------------------------------------------------------


def _resolve_cost_policy(twin_state: dict[str, Any]) -> dict[str, float]:
    """Extract cost_policy from twin_state or use baseline defaults."""
    cp = twin_state.get("cost_policy")
    if isinstance(cp, dict) and cp:
        return {k: float(cp.get(k, v)) for k, v in _DEFAULT_COST_POLICY.items()}
    return dict(_DEFAULT_COST_POLICY)


def _resolve_order_units(twin_state: dict[str, Any]) -> int:
    """Extract order_units from twin_state.active_order or use baseline default."""
    ao = twin_state.get("active_order", {})
    if isinstance(ao, dict) and ao.get("order_units", 0) > 0:
        return int(ao["order_units"])
    return _DEFAULT_ORDER_UNITS


def _resolve_planned_eta(twin_state: dict[str, Any]) -> float:
    """Extract planned_eta_hours from twin_state.active_order or use baseline default."""
    ao = twin_state.get("active_order", {})
    if isinstance(ao, dict) and "planned_eta_hours" in ao:
        return float(ao["planned_eta_hours"])
    return _DEFAULT_PLANNED_ETA_HOURS


def _resolve_customer_zone(
    twin_state: dict[str, Any],
) -> dict[str, Any]:
    """Resolve the primary customer zone from twin_state.

    Uses active_order.customer_zone_id if available, otherwise first zone.
    Returns a dict with sla_deadline_hours, sla_penalty_per_hour.
    Falls back to conservative defaults.
    """
    zones = twin_state.get("customer_zones", [])
    ao = twin_state.get("active_order", {})
    target_id = ao.get("customer_zone_id", _DEFAULT_CUSTOMER_ZONE_ID) if isinstance(ao, dict) else _DEFAULT_CUSTOMER_ZONE_ID

    # Try to find matching zone
    for z in zones:
        if isinstance(z, dict) and z.get("id") == target_id:
            return z

    # Fall back to first zone if available
    if zones and isinstance(zones[0], dict):
        return zones[0]

    # Conservative defaults
    return {
        "id": "CZ_UNKNOWN",
        "sla_deadline_hours": 48.0,
        "sla_penalty_per_hour": 5.0,
    }


def _find_carrier(twin_state: dict[str, Any], carrier_id: str) -> dict[str, Any] | None:
    """Find a carrier by ID in twin_state.carriers."""
    for c in twin_state.get("carriers", []):
        if isinstance(c, dict) and c.get("id") == carrier_id:
            return c
    return None


def _find_warehouse(twin_state: dict[str, Any], wh_id: str) -> dict[str, Any] | None:
    """Find a warehouse by ID in twin_state.warehouses."""
    for w in twin_state.get("warehouses", []):
        if isinstance(w, dict) and w.get("id") == wh_id:
            return w
    return None


# ---------------------------------------------------------------------------
# Per-candidate cost estimation
# ---------------------------------------------------------------------------


def _estimate_expedite(
    candidate: dict[str, Any],
    twin_state: dict[str, Any],
    order_units: int,
    planned_eta: float,
    policy: dict[str, float],
    zone: dict[str, Any],
) -> CandidateCostEstimate:
    """Estimate cost for an EXPEDITE candidate.

    Formula (aligned with TwinState.compute_total_cost EXPEDITE branch):
      direct = order_units * carrier.cost_per_unit * expedite_multiplier
      recovery = late_hours * order_units * sla_penalty_per_hour
        where late_hours = max(0, carrier.transit_time_hours - sla_deadline)
        (uses carrier transit time as post-expedite ETA estimate)
    """
    carrier_id = candidate.get("target_entities", {}).get("carrier_id", "")
    carrier = _find_carrier(twin_state, carrier_id)

    if carrier is None:
        return CandidateCostEstimate(
            candidate_id=candidate["candidate_id"],
            candidate_type="EXPEDITE",
            is_feasible=False,
            direct_cost_estimate=None,
            recovery_cost_estimate=None,
            total_cost_estimate=None,
            cost_breakdown_explanation=f"Carrier {carrier_id} not found in twin state.",
            estimation_notes="Infeasible: target carrier entity missing.",
        )

    cost_per_unit = float(carrier.get("cost_per_unit", 0))
    transit_hours = float(carrier.get("transit_time_hours", planned_eta))
    multiplier = policy["expedite_multiplier"]
    sla_deadline = float(zone.get("sla_deadline_hours", 48))
    sla_penalty = float(zone.get("sla_penalty_per_hour", 0))

    direct = order_units * cost_per_unit * multiplier
    late_hours = max(0.0, transit_hours - sla_deadline)
    recovery = late_hours * order_units * sla_penalty
    total = direct + recovery

    return CandidateCostEstimate(
        candidate_id=candidate["candidate_id"],
        candidate_type="EXPEDITE",
        is_feasible=True,
        direct_cost_estimate=round(direct, 2),
        recovery_cost_estimate=round(recovery, 2),
        total_cost_estimate=round(total, 2),
        cost_breakdown_explanation=(
            f"direct = {order_units} units × ${cost_per_unit}/unit "
            f"× {multiplier} expedite multiplier = ${direct:.2f}; "
            f"recovery = max(0, {transit_hours}h − {sla_deadline}h SLA) "
            f"× {order_units} × ${sla_penalty}/h = ${recovery:.2f}"
        ),
        estimation_notes=(
            "Runtime decision-support estimate using TwinState-aligned "
            "EXPEDITE formula. Not authoritative evaluation truth."
        ),
    )


def _estimate_transfer(
    candidate: dict[str, Any],
    twin_state: dict[str, Any],
    order_units: int,
    planned_eta: float,
    policy: dict[str, float],
    zone: dict[str, Any],
) -> CandidateCostEstimate:
    """Estimate cost for a TRANSFER candidate.

    Formula (aligned with TwinState.compute_total_cost TRANSFER branch):
      direct = transfer_fixed_fee + order_units * transfer_unit_cost
               + order_units * dest_wh.operating_cost_per_unit
      recovery = late_hours * order_units * sla_penalty_per_hour
        where late_hours = max(0, planned_eta - sla_deadline)
    """
    entities = candidate.get("target_entities", {})
    dst_id = entities.get("to_warehouse_id", "")
    dst_wh = _find_warehouse(twin_state, dst_id)

    if dst_wh is None:
        return CandidateCostEstimate(
            candidate_id=candidate["candidate_id"],
            candidate_type="TRANSFER",
            is_feasible=False,
            direct_cost_estimate=None,
            recovery_cost_estimate=None,
            total_cost_estimate=None,
            cost_breakdown_explanation=f"Destination warehouse {dst_id} not found.",
            estimation_notes="Infeasible: destination warehouse entity missing.",
        )

    fixed_fee = policy["transfer_fixed_fee"]
    unit_cost = policy["transfer_unit_cost"]
    dest_op_cost = float(dst_wh.get("operating_cost_per_unit", 0))
    sla_deadline = float(zone.get("sla_deadline_hours", 48))
    sla_penalty = float(zone.get("sla_penalty_per_hour", 0))

    direct = fixed_fee + order_units * unit_cost + order_units * dest_op_cost
    late_hours = max(0.0, planned_eta - sla_deadline)
    recovery = late_hours * order_units * sla_penalty
    total = direct + recovery

    return CandidateCostEstimate(
        candidate_id=candidate["candidate_id"],
        candidate_type="TRANSFER",
        is_feasible=True,
        direct_cost_estimate=round(direct, 2),
        recovery_cost_estimate=round(recovery, 2),
        total_cost_estimate=round(total, 2),
        cost_breakdown_explanation=(
            f"direct = ${fixed_fee} fixed + {order_units} × ${unit_cost}/unit "
            f"+ {order_units} × ${dest_op_cost}/unit op cost = ${direct:.2f}; "
            f"recovery = max(0, {planned_eta}h − {sla_deadline}h SLA) "
            f"× {order_units} × ${sla_penalty}/h = ${recovery:.2f}"
        ),
        estimation_notes=(
            "Runtime decision-support estimate using TwinState-aligned "
            "TRANSFER formula. Not authoritative evaluation truth."
        ),
    )


def _estimate_compensate(
    candidate: dict[str, Any],
    order_units: int,
    planned_eta: float,
    policy: dict[str, float],
    zone: dict[str, Any],
) -> CandidateCostEstimate:
    """Estimate cost for a COMPENSATE candidate.

    Formula (aligned with TwinState.compute_total_cost COMPENSATE branch):
      direct = order_units * default_compensation_per_unit
      recovery = late_hours * order_units * (sla_penalty - penalty_relief)
    """
    comp_per_unit = policy["default_compensation_per_unit"]
    relief = policy["default_penalty_relief_per_hour"]
    sla_deadline = float(zone.get("sla_deadline_hours", 48))
    sla_penalty = float(zone.get("sla_penalty_per_hour", 0))

    direct = order_units * comp_per_unit
    late_hours = max(0.0, planned_eta - sla_deadline)
    effective_rate = sla_penalty - relief
    recovery = late_hours * order_units * effective_rate
    total = direct + recovery

    return CandidateCostEstimate(
        candidate_id=candidate["candidate_id"],
        candidate_type="COMPENSATE",
        is_feasible=True,
        direct_cost_estimate=round(direct, 2),
        recovery_cost_estimate=round(recovery, 2),
        total_cost_estimate=round(total, 2),
        cost_breakdown_explanation=(
            f"direct = {order_units} × ${comp_per_unit}/unit compensation "
            f"= ${direct:.2f}; "
            f"recovery = max(0, {planned_eta}h − {sla_deadline}h SLA) "
            f"× {order_units} × (${sla_penalty} − ${relief} relief)/h "
            f"= ${recovery:.2f}"
        ),
        estimation_notes=(
            "Runtime decision-support estimate using TwinState-aligned "
            "COMPENSATE formula. Not authoritative evaluation truth."
        ),
    )


def _estimate_no_action(
    candidate: dict[str, Any],
    order_units: int,
    planned_eta: float,
    zone: dict[str, Any],
) -> CandidateCostEstimate:
    """Estimate cost for a NO_ACTION candidate.

    Formula (aligned with TwinState.compute_total_cost NO_ACTION branch):
      direct = 0
      recovery = late_hours * order_units * sla_penalty_per_hour
    """
    sla_deadline = float(zone.get("sla_deadline_hours", 48))
    sla_penalty = float(zone.get("sla_penalty_per_hour", 0))

    direct = 0.0
    late_hours = max(0.0, planned_eta - sla_deadline)
    recovery = late_hours * order_units * sla_penalty
    total = direct + recovery

    return CandidateCostEstimate(
        candidate_id=candidate["candidate_id"],
        candidate_type="NO_ACTION",
        is_feasible=True,
        direct_cost_estimate=round(direct, 2),
        recovery_cost_estimate=round(recovery, 2),
        total_cost_estimate=round(total, 2),
        cost_breakdown_explanation=(
            f"direct = $0.00 (no action); "
            f"recovery = max(0, {planned_eta}h − {sla_deadline}h SLA) "
            f"× {order_units} × ${sla_penalty}/h = ${recovery:.2f}"
        ),
        estimation_notes=(
            "Runtime decision-support estimate using TwinState-aligned "
            "NO_ACTION formula. Not authoritative evaluation truth."
        ),
    )


def _estimate_infeasible(
    candidate: dict[str, Any],
) -> CandidateCostEstimate:
    """Return a null-cost estimate for an infeasible candidate."""
    reason = candidate.get("feasibility_reason") or "Constraint violation."
    return CandidateCostEstimate(
        candidate_id=candidate["candidate_id"],
        candidate_type=candidate["candidate_type"],
        is_feasible=False,
        direct_cost_estimate=None,
        recovery_cost_estimate=None,
        total_cost_estimate=None,
        cost_breakdown_explanation=f"Infeasible: {reason}",
        estimation_notes=(
            "No cost estimate produced. Candidate failed operational "
            "feasibility checks in the Operations Agent."
        ),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_cost_agent(
    twin_state: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> CostOutput:
    """Run the Cost Agent and produce deterministic cost estimates.

    Parameters
    ----------
    twin_state:
        Serialized twin state context (initial_state_snapshot from case JSON).
    candidates:
        List of operational candidate dicts from the Operations Agent
        (typically from OperationsOutput.ranked_candidates serialized).
        Each must have candidate_id, candidate_type, feasible/is_feasible,
        and target_entities.

    Returns
    -------
    CostOutput
        Deterministic cost estimates for all candidates.
    """
    policy = _resolve_cost_policy(twin_state)
    order_units = _resolve_order_units(twin_state)
    planned_eta = _resolve_planned_eta(twin_state)
    zone = _resolve_customer_zone(twin_state)

    estimates: list[CandidateCostEstimate] = []
    for cand in candidates:
        # Normalize feasibility field (Operations Agent uses "feasible",
        # serialized dicts may use either)
        is_feasible = cand.get("feasible", cand.get("is_feasible", False))

        if not is_feasible:
            estimates.append(_estimate_infeasible(cand))
            continue

        ctype = cand.get("candidate_type", "")

        if ctype == "EXPEDITE":
            estimates.append(_estimate_expedite(
                cand, twin_state, order_units, planned_eta, policy, zone,
            ))
        elif ctype == "TRANSFER":
            estimates.append(_estimate_transfer(
                cand, twin_state, order_units, planned_eta, policy, zone,
            ))
        elif ctype == "COMPENSATE":
            estimates.append(_estimate_compensate(
                cand, order_units, planned_eta, policy, zone,
            ))
        elif ctype == "NO_ACTION":
            estimates.append(_estimate_no_action(
                cand, order_units, planned_eta, zone,
            ))
        else:
            # Unknown type — treat as infeasible
            estimates.append(CandidateCostEstimate(
                candidate_id=cand.get("candidate_id", "?"),
                candidate_type=ctype,
                is_feasible=False,
                direct_cost_estimate=None,
                recovery_cost_estimate=None,
                total_cost_estimate=None,
                cost_breakdown_explanation=f"Unknown candidate_type '{ctype}'.",
                estimation_notes="No estimation formula available for this type.",
            ))

    return CostOutput(
        cost_estimates=estimates,
        order_units_used=order_units,
        planned_eta_used=planned_eta,
        cost_policy_used=policy,
    )
