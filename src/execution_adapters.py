"""
execution_adapters.py — D3-Demo Phase 3: Deterministic execution adapters.

Four adapters corresponding to the four operational action types:
  execute_expedite / execute_transfer / execute_compensate / execute_no_action

Plus a unified dispatcher:
  execute_action(governance_output, twin_state, event_id, ...) ->
      (mutated TwinState, ExecutionOutcome)

All adapters are deterministic, grounded in TwinState.apply_action() +
compute_total_cost(), and produce ExecutionOutcome records.

Hard boundaries:
  - No imports from evaluation.py or action_code_mapper.py
  - No LLM calls, no stochastic behavior, no external system calls
  - No reading data/cases/*.json
  - ExecutionOutcome.action_taken uses ONLY operational-layer identifiers
  - GovernanceOutput schema is NOT extended
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from outcome_schema import ExecutionOutcome
from twin_state import Action, ActionType, TwinState


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ExecutionInfeasibleError(RuntimeError):
    """Adapter cannot execute the requested action under current state."""


class GovernanceActionParseError(ValueError):
    """Could not parse an operational action type from governance output."""


# ---------------------------------------------------------------------------
# Operational action type constants
# ---------------------------------------------------------------------------

_OPERATIONAL_PREFIXES = ("EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION")

# Forbidden identifier tokens from other layers — never accept these as
# an operational action type even if they sneak into governance output.
_FORBIDDEN_SUPERVISION = frozenset({"APPROVE", "VERIFY", "OVERRIDE"})
_FORBIDDEN_EVALUATION = frozenset({"AI", "ALT1", "ALT2"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_operational_type(
    governance_output: dict[str, Any],
    governance_meta: dict[str, Any] | None = None,
    *,
    require_metadata: bool = False,
) -> tuple[str, str]:
    """Parse operational action type from governance output. Metadata-first.

    Returns
    -------
    (action_type, parse_source)
        action_type  : one of EXPEDITE / TRANSFER / COMPENSATE / NO_ACTION
        parse_source : "metadata" if resolved via governance_meta,
                       "text_fallback" if resolved via recommended_action text.

    Strict metadata-first rule:
      - If ``governance_meta["recommended_candidate_type"]`` is a non-empty
        string, it MUST be one of the four operational identifiers. Any
        other value (forbidden layer, unknown token) raises
        GovernanceActionParseError. We do NOT silently fall through on
        malformed metadata — that would hide contract drift.
      - Only when the metadata field is absent / None / empty string do we
        attempt ``recommended_action`` text prefix parsing as an explicit,
        audited fallback.

    ``require_metadata`` flag (Phase 2 / Roadmap §2.B, owner point 6):
      - Default ``False`` preserves the Path B behavior above (including
        the text fallback branch) so existing tests and callers are not
        disturbed.
      - ``True`` forbids the text fallback: if
        ``governance_meta.recommended_candidate_type`` is absent, empty,
        or non-string, raise ``GovernanceActionParseError``. This is the
        Path C main path execution contract.

    Both paths explicitly reject supervision-layer (APPROVE/VERIFY/OVERRIDE)
    and evaluation-layer (AI/ALT1/ALT2) identifiers. The text fallback
    requires the operational prefix to be followed by end-of-string, ':',
    or ' ' so that "EXPEDITELY" does not match "EXPEDITE".
    """
    # --- 1. Metadata-first path ---
    if governance_meta:
        t = governance_meta.get("recommended_candidate_type")
        if isinstance(t, str) and t.strip():
            t_up = t.strip().upper()
            if t_up in _FORBIDDEN_SUPERVISION or t_up in _FORBIDDEN_EVALUATION:
                raise GovernanceActionParseError(
                    f"recommended_candidate_type='{t}' is not an operational-layer "
                    f"identifier (operational layer is EXPEDITE/TRANSFER/"
                    f"COMPENSATE/NO_ACTION)"
                )
            if t_up in _OPERATIONAL_PREFIXES:
                return t_up, "metadata"
            # Non-empty metadata that matches nothing known — FAIL CLOSED.
            raise GovernanceActionParseError(
                f"recommended_candidate_type='{t}' is not a recognized "
                f"operational action type"
            )
        # t is None / missing / empty string / not a string → fall through

    # Path C main path forbids text fallback.
    if require_metadata:
        raise GovernanceActionParseError(
            "require_metadata=True: governance_meta.recommended_candidate_type "
            "is missing, empty, or non-string. Path C main path forbids "
            "recommended_action text fallback."
        )

    # --- 2. Text fallback path (explicit, audited) ---
    rec = governance_output.get("recommended_action", "")
    if isinstance(rec, str) and rec.strip():
        rec_up = rec.strip().upper()

        # Explicit rejection of non-operational layer tokens appearing as a prefix
        for forbidden in list(_FORBIDDEN_SUPERVISION) + list(_FORBIDDEN_EVALUATION):
            if rec_up.startswith(forbidden):
                nxt = rec_up[len(forbidden):len(forbidden) + 1]
                if nxt in ("", ":", " "):
                    raise GovernanceActionParseError(
                        f"recommended_action starts with non-operational "
                        f"identifier '{forbidden}'; refusing to execute"
                    )

        for prefix in _OPERATIONAL_PREFIXES:
            if rec_up.startswith(prefix):
                nxt = rec_up[len(prefix):len(prefix) + 1]
                if nxt in ("", ":", " "):
                    return prefix, "text_fallback"

    raise GovernanceActionParseError(
        f"Could not parse operational action type from governance output "
        f"(recommended_action={governance_output.get('recommended_action')!r})"
    )


def _pick_alternate_carrier(
    state: TwinState, hint_id: str | None = None,
) -> str | None:
    """Pick the first available carrier that is NOT the planned carrier
    and has sufficient capacity for order_units. Deterministic (sorted ids).

    If hint_id is provided and matches a valid alternate, it is preferred.
    """
    current = state.planned_carrier_id
    required = state.order_units

    # Prefer hint if it names a valid alternate
    if hint_id:
        for cid in sorted(state.carriers.keys()):
            if cid == current:
                continue
            if cid in hint_id:  # substring match covers "EXPEDITE_CR_2"
                c = state.carriers[cid]
                if c.available and c.capacity_limit >= required:
                    return cid

    # Fallback: deterministic scan
    for cid in sorted(state.carriers.keys()):
        if cid == current:
            continue
        c = state.carriers[cid]
        if c.available and c.capacity_limit >= required:
            return cid
    return None


def _pick_transfer_destination(state: TwinState) -> str | None:
    """Pick the first warehouse (not the source) that can receive order_units
    without exceeding max_capacity, and where source has sufficient inventory.
    Deterministic (sorted ids).
    """
    src_id = state.source_warehouse_id
    src = state.warehouses.get(src_id)
    if src is None or src.current_inventory < state.order_units:
        return None
    for wid in sorted(state.warehouses.keys()):
        if wid == src_id:
            continue
        w = state.warehouses[wid]
        if w.current_inventory + state.order_units <= w.max_capacity:
            return wid
    return None


def _resolve_timestamp(ts: datetime | None) -> datetime:
    """Return a tz-aware UTC timestamp for the outcome."""
    if ts is not None:
        if ts.tzinfo is None or ts.utcoffset() is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts
    return datetime.now(tz=timezone.utc)


def _build_sla_impact(state: TwinState) -> dict[str, Any]:
    """Deterministic SLA impact summary based on the current state."""
    zone = state.customer_zones.get(state.customer_zone_id)
    if zone is None:
        return {
            "preserved": False,
            "late_hours": 0.0,
            "deadline_hours": 0.0,
            "eta_after_action": float(state.planned_eta_hours),
            "note": "unknown customer zone",
        }
    eta = max(0.0, float(state.planned_eta_hours))
    late = max(0.0, eta - float(zone.sla_deadline_hours))
    return {
        "preserved": late == 0.0,
        "late_hours": float(late),
        "deadline_hours": float(zone.sla_deadline_hours),
        "eta_after_action": eta,
    }


# ---------------------------------------------------------------------------
# Adapter: EXPEDITE
# ---------------------------------------------------------------------------


def execute_expedite(
    twin_state: TwinState,
    *,
    event_id: str,
    timestamp: datetime | None = None,
    governance_meta: dict[str, Any] | None = None,
) -> tuple[TwinState, ExecutionOutcome]:
    """EXPEDITE: switch planned_carrier to an available alternate carrier."""
    new_state = twin_state.model_copy(deep=True)

    hint_id = None
    if governance_meta:
        hint = governance_meta.get("recommended_candidate_id")
        if isinstance(hint, str):
            hint_id = hint

    target = _pick_alternate_carrier(new_state, hint_id=hint_id)
    if target is None:
        raise ExecutionInfeasibleError(
            f"EXPEDITE infeasible: no alternate available carrier with "
            f"capacity >= {new_state.order_units} "
            f"(current planned={new_state.planned_carrier_id})"
        )

    old_carrier_id = new_state.planned_carrier_id
    old_eta = float(new_state.planned_eta_hours)
    new_carrier = new_state.carriers[target]
    new_eta = float(new_carrier.transit_time_hours)
    eta_adj = new_eta - old_eta

    action = Action(
        action_id=f"exec-expedite-{event_id}",
        action_type=ActionType.EXPEDITE,
        units=new_state.order_units,
        target_carrier_id=target,
        eta_adjustment_hours=eta_adj,
    )
    new_state.apply_action(action)
    total = new_state.compute_total_cost()

    state_delta = {
        "action_type": "EXPEDITE",
        "patches": [
            {"entity_type": "twin", "op": "set",
             "field": "planned_carrier_id", "value": target},
            {"entity_type": "twin", "op": "set",
             "field": "planned_eta_hours",
             "value": float(new_state.planned_eta_hours)},
        ],
        "before": {"planned_carrier_id": old_carrier_id, "planned_eta_hours": old_eta},
        "after": {"planned_carrier_id": target,
                  "planned_eta_hours": float(new_state.planned_eta_hours)},
    }

    outcome = ExecutionOutcome(
        event_id=event_id,
        action_taken="EXPEDITE",
        cost_incurred=float(total),
        sla_impact=_build_sla_impact(new_state),
        state_delta=state_delta,
        timestamp=_resolve_timestamp(timestamp),
        status="EXECUTED",
        notes=f"Switched planned carrier {old_carrier_id} -> {target}.",
    )
    return new_state, outcome


# ---------------------------------------------------------------------------
# Adapter: TRANSFER
# ---------------------------------------------------------------------------


def execute_transfer(
    twin_state: TwinState,
    *,
    event_id: str,
    timestamp: datetime | None = None,
    governance_meta: dict[str, Any] | None = None,
) -> tuple[TwinState, ExecutionOutcome]:
    """TRANSFER: move order_units inventory to an alternate warehouse."""
    new_state = twin_state.model_copy(deep=True)

    src_id = new_state.source_warehouse_id
    dst_id = _pick_transfer_destination(new_state)
    if dst_id is None:
        raise ExecutionInfeasibleError(
            f"TRANSFER infeasible: no alternate warehouse with sufficient "
            f"capacity, or source has insufficient inventory "
            f"(src={src_id}, units={new_state.order_units})"
        )

    src_before = new_state.warehouses[src_id].current_inventory
    dst_before = new_state.warehouses[dst_id].current_inventory
    eta_before = float(new_state.planned_eta_hours)

    action = Action(
        action_id=f"exec-transfer-{event_id}",
        action_type=ActionType.TRANSFER,
        units=new_state.order_units,
        from_warehouse_id=src_id,
        to_warehouse_id=dst_id,
        eta_adjustment_hours=0.0,
    )
    new_state.apply_action(action)
    total = new_state.compute_total_cost()

    src_after = new_state.warehouses[src_id].current_inventory
    dst_after = new_state.warehouses[dst_id].current_inventory

    state_delta = {
        "action_type": "TRANSFER",
        "patches": [
            {"entity_type": "warehouse", "entity_id": src_id, "op": "set",
             "field": "current_inventory", "value": src_after},
            {"entity_type": "warehouse", "entity_id": dst_id, "op": "set",
             "field": "current_inventory", "value": dst_after},
        ],
        "before": {
            f"warehouse[{src_id}].current_inventory": src_before,
            f"warehouse[{dst_id}].current_inventory": dst_before,
            "planned_eta_hours": eta_before,
        },
        "after": {
            f"warehouse[{src_id}].current_inventory": src_after,
            f"warehouse[{dst_id}].current_inventory": dst_after,
            "planned_eta_hours": float(new_state.planned_eta_hours),
        },
    }

    outcome = ExecutionOutcome(
        event_id=event_id,
        action_taken="TRANSFER",
        cost_incurred=float(total),
        sla_impact=_build_sla_impact(new_state),
        state_delta=state_delta,
        timestamp=_resolve_timestamp(timestamp),
        status="EXECUTED",
        notes=f"Transferred {action.units} units {src_id} -> {dst_id}.",
    )
    return new_state, outcome


# ---------------------------------------------------------------------------
# Adapter: COMPENSATE
# ---------------------------------------------------------------------------


def execute_compensate(
    twin_state: TwinState,
    *,
    event_id: str,
    timestamp: datetime | None = None,
    governance_meta: dict[str, Any] | None = None,
) -> tuple[TwinState, ExecutionOutcome]:
    """COMPENSATE: issue customer compensation; logistics state unchanged."""
    new_state = twin_state.model_copy(deep=True)

    carrier_before = new_state.planned_carrier_id
    eta_before = float(new_state.planned_eta_hours)

    # Use CostPolicy defaults; apply_action / compute_total_cost handle math
    action = Action(
        action_id=f"exec-compensate-{event_id}",
        action_type=ActionType.COMPENSATE,
        units=new_state.order_units,
        compensation_per_unit=None,
        penalty_relief_per_hour=None,
    )
    new_state.apply_action(action)
    total = new_state.compute_total_cost()

    state_delta = {
        "action_type": "COMPENSATE",
        "patches": [],  # no physical state mutation
        "before": {"planned_carrier_id": carrier_before,
                   "planned_eta_hours": eta_before},
        "after": {"planned_carrier_id": carrier_before,
                  "planned_eta_hours": eta_before},
        "note": "Compensation issued; no physical logistics change.",
    }

    outcome = ExecutionOutcome(
        event_id=event_id,
        action_taken="COMPENSATE",
        cost_incurred=float(total),
        sla_impact=_build_sla_impact(new_state),
        state_delta=state_delta,
        timestamp=_resolve_timestamp(timestamp),
        status="EXECUTED",
        notes="Compensation applied; no physical logistics change.",
    )
    return new_state, outcome


# ---------------------------------------------------------------------------
# Adapter: NO_ACTION
# ---------------------------------------------------------------------------


def execute_no_action(
    twin_state: TwinState,
    *,
    event_id: str,
    timestamp: datetime | None = None,
    governance_meta: dict[str, Any] | None = None,
) -> tuple[TwinState, ExecutionOutcome]:
    """NO_ACTION: no mitigation; accept current lateness penalty."""
    new_state = twin_state.model_copy(deep=True)

    action = Action(
        action_id=f"exec-noaction-{event_id}",
        action_type=ActionType.NO_ACTION,
        units=new_state.order_units,
    )
    new_state.apply_action(action)
    total = new_state.compute_total_cost()

    state_delta = {
        "action_type": "NO_ACTION",
        "patches": [],  # explicit empty: no state mutation
        "note": "No operational mitigation taken.",
    }

    outcome = ExecutionOutcome(
        event_id=event_id,
        action_taken="NO_ACTION",
        cost_incurred=float(total),
        sla_impact=_build_sla_impact(new_state),
        state_delta=state_delta,
        timestamp=_resolve_timestamp(timestamp),
        status="EXECUTED",
        notes="No mitigation; current lateness penalty accepted.",
    )
    return new_state, outcome


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


_DISPATCH = {
    "EXPEDITE": execute_expedite,
    "TRANSFER": execute_transfer,
    "COMPENSATE": execute_compensate,
    "NO_ACTION": execute_no_action,
}


def execute_action(
    governance_output: dict[str, Any],
    twin_state: TwinState,
    *,
    event_id: str,
    governance_meta: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
    require_metadata: bool = False,
) -> tuple[TwinState, ExecutionOutcome]:
    """Parse operational action type from governance output and dispatch.

    Parameters
    ----------
    governance_output : dict
        GovernanceOutput serialized as dict (8 frozen fields).
    twin_state : TwinState
        Current runtime state. NOT modified; a deep copy is mutated.
    event_id : str
        The triggering event id (recorded on the outcome).
    governance_meta : dict or None
        Optional identity metadata (recommended_candidate_type, _id).
        Read-only; improves routing determinism.
    timestamp : datetime or None
        Optional tz-aware timestamp for the outcome record.
    require_metadata : bool
        Phase 2 / Roadmap §2.B. Default ``False`` preserves Path B
        regression (text fallback allowed). ``True`` (used exclusively
        on the Path C main path) forbids the text fallback and raises
        ``GovernanceActionParseError`` when the structured metadata is
        missing or invalid.

    Returns
    -------
    (TwinState, ExecutionOutcome)
        Mutated state and structured outcome record.

    Raises
    ------
    GovernanceActionParseError
        When the operational action type cannot be parsed.
    ExecutionInfeasibleError
        When the adapter cannot execute given the current state.
    """
    action_type, parse_source = _parse_operational_type(
        governance_output, governance_meta,
        require_metadata=require_metadata,
    )
    adapter = _DISPATCH.get(action_type)
    if adapter is None:  # defensive — should be unreachable
        raise GovernanceActionParseError(
            f"No adapter registered for action_type={action_type!r}"
        )
    new_state, outcome = adapter(
        twin_state,
        event_id=event_id,
        timestamp=timestamp,
        governance_meta=governance_meta,
    )
    # Audit annotation: record parse source in outcome.notes so downstream
    # audit / replay can tell whether the action came from machine-friendly
    # metadata or from a natural-language recommendation text fallback.
    if parse_source == "text_fallback":
        outcome = outcome.model_copy(update={
            "notes": f"[parse=text_fallback] {outcome.notes}".rstrip(),
        })
    return new_state, outcome
