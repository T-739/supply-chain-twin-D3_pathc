"""
event_loop.py — D3-Demo Phase 2+3: Outer event loop orchestrator with
                                     execution + outcome feedback closure.

Processes an ordered list of EventPayload through the reasoning stack:
  for each event:
    1. apply_event_patch on live TwinState (Phase 2)
    2. inject prior outcome_summary into scenario_context (Phase 3 sideband)
    3. run inner reasoning slice (operations → cost → governance → policy gate)
    4. route on policy_decision:
         - AUTO_EXECUTE  → adapter runs, outcome appended, live_state replaced
         - HUMAN_REQUIRED → default: no execution (awaiting_human_review)
                           (auto_approve_escalations=True is a demo-only override)
    5. collect per-event record

This is an OUTER orchestrator around the existing V2 reasoning nodes.
It does NOT rewrite the LangGraph graph into a self-cycling system.

Runtime / Research Core separation — this module does NOT:
  - Import evaluation.py or action_code_mapper.py
  - Read from data/cases/*.json
  - Extend GovernanceOutput schema (summary is injected via scenario_context)
  - Implement adaptive thresholds / replan / learning / correlation (Path C)
"""

from __future__ import annotations

import os
from typing import Any

from event_schema import EventPayload
from event_state_mapper import map_event_to_state
from execution_adapters import (
    ExecutionInfeasibleError,
    GovernanceActionParseError,
    execute_action,
)
from outcome_store import OutcomeStore
from twin_state import TwinState


# ---------------------------------------------------------------------------
# Baseline loader
# ---------------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(os.path.dirname(_BASE_DIR), "data")
_BASELINE_PATH = os.path.join(_DATA_DIR, "configs", "baseline_network.json")


def load_baseline_twin_state(path: str | None = None) -> TwinState:
    """Load baseline TwinState from config JSON.

    Default: data/configs/baseline_network.json.
    Does NOT read from data/cases/*.json.
    """
    return TwinState.initialize_from_config(path or _BASELINE_PATH)


# ---------------------------------------------------------------------------
# Inner reasoning slice — reuses existing graph node functions directly
# ---------------------------------------------------------------------------


def _run_reasoning_slice(
    twin_state_dict: dict[str, Any],
    scenario_context: dict[str, Any],
    *,
    agent_memory_context: Any = None,
    agent_memory_config: Any = None,
    operations_mode: Any = None,
) -> dict[str, Any]:
    """Run the inner reasoning slice: ops → cost → governance → policy gate.

    Reuses existing node functions from graph.py but does NOT invoke the
    full compiled graph (which includes load_case, supervisor, evaluation).
    This keeps the event-driven runtime path separate from the Research Core.

    Parameters
    ----------
    twin_state_dict : dict
        Serialized TwinState for agent consumption.
    scenario_context : dict
        Event-derived scenario context.
    agent_memory_context, agent_memory_config
        B4 Slice 2C optional internal-only wiring. Both default
        to ``None``; when non-None they are plumbed into the
        ``operations_agent_node`` via the ``GraphState`` dict and
        reach ``run_operations_agent_with_meta`` through the
        agent module's Slice 2B kwargs. Typed as ``Any`` here to
        avoid a hard import dependency on the ``agent_memory``
        subpackage from Path B runtime code; the shape contract
        is enforced by the agent module itself.
    operations_mode
        B4 Slice 2D3-B optional internal-only wiring. When the
        Path C orchestrator has already resolved the operations
        agent's dispatch mode (env-driven via
        ``SUPPLY_CHAIN_TWIN_OPERATIONS_MODE`` per D9), it threads
        the resolved string here so ``operations_agent_node``
        observes the same mode reality the W4 gate observed.
        Without this seam, ``graph.operations_agent_node`` falls
        back to its ``state.get("operations_mode") or "rules"``
        default and the operations agent's own
        ``_resolve_ops_mode("rules")`` short-circuits the env —
        leaving B4 with a built ``AgentMemoryContext`` that is
        threaded through the sideband but never injected into an
        actual LLM prompt. Default ``None`` preserves Path B byte
        identity (Path B never sets this kwarg).
    """
    from graph import (
        GraphState,
        cost_agent_node,
        governance_agent_node,
        operations_agent_node,
        policy_gate_node,
    )

    # Build a minimal GraphState-compatible dict
    state: GraphState = {
        "twin_state": twin_state_dict,
        "scenario_context": scenario_context,
        "trace_log": [],
        "policy_gate_enabled": True,
    }
    # B4 Slice 2C — internal sideband on GraphState. Keys are
    # read by ``graph.operations_agent_node`` and nowhere else;
    # the OFF path (both keys absent) preserves pre-B4 byte
    # identity end-to-end.
    if agent_memory_context is not None:
        state["_agent_memory_context"] = agent_memory_context
    if agent_memory_config is not None:
        state["_agent_memory_config"] = agent_memory_config
    # B4 Slice 2D3-B — propagate the caller-resolved operations
    # dispatch mode into GraphState so ``operations_agent_node``
    # uses the same env reality the W4 gate used. Only set when
    # caller supplied a value; absent key leaves the graph node
    # on its pre-2D3-B "rules" default → Path B byte identity is
    # preserved when this kwarg is omitted.
    if operations_mode is not None:
        state["operations_mode"] = operations_mode

    # Sequential: operations → cost → governance → policy_gate
    state = operations_agent_node(state)
    state = cost_agent_node(state)
    state = governance_agent_node(state)
    state = policy_gate_node(state)

    return state


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_event_loop(
    events: list[EventPayload],
    initial_twin_state: TwinState | None = None,
    outcome_store: OutcomeStore | None = None,
    auto_approve_escalations: bool = False,
) -> dict[str, Any]:
    """Run the D3 event loop over a list of events (Phase 3 closed loop).

    For each event:
      1. Patch live TwinState via event_state_mapper (pure, on a copy).
      2. Inject prior outcome_store.summary() into scenario_context
         (sideband — not a GovernanceOutput extension).
      3. Run inner reasoning slice (ops → cost → governance → policy gate).
      4. Route on policy_decision:
         - AUTO_EXECUTE:   execute adapter, append outcome, update live state
         - HUMAN_REQUIRED: default = skip (awaiting_human_review)
                           auto_approve_escalations=True = demo-only override
      5. Collect per-event record.

    Parameters
    ----------
    events : list[EventPayload]
        Ordered event stream. Processed sequentially.
    initial_twin_state : TwinState or None
        Starting state. If None, loads baseline_network.json.
    outcome_store : OutcomeStore or None
        Append-only store. A fresh one is created if None.
    auto_approve_escalations : bool
        Demo-only: if True, HUMAN_REQUIRED events also execute (marked as
        a demo override in the record notes and execution_status). Default
        False — HUMAN_REQUIRED events are skipped with execution_status
        "awaiting_human_review". This preserves the semantic of the
        policy gate even in an automated demo.

    Returns
    -------
    dict with keys:
        event_results : list[dict]       per-event records
        events_processed : int
        outcomes_count : int
        outcome_summary : dict           final outcome_store summary
        final_twin_state_summary : dict

    Each event record contains:
        event_id, event_type, severity
        scenario_context            (includes injected outcome_summary)
        governance_output
        policy_decision
        execution_status           ("executed" / "awaiting_human_review" /
                                    "executed_via_demo_override" /
                                    "execution_failed" / "unknown_route")
        execution_outcome          (dict or None)
        execution_error            (present only on execution_failed)
        trace_log
    """
    if initial_twin_state is None:
        initial_twin_state = load_baseline_twin_state()
    if outcome_store is None:
        outcome_store = OutcomeStore()

    live_state = initial_twin_state
    event_results: list[dict[str, Any]] = []

    for event in events:
        # 1. Patch live state via pure mapper
        patched_state, scenario_context = map_event_to_state(event, live_state)
        live_state = patched_state

        # 2. Inject PRIOR outcome_summary into scenario_context (sideband)
        #    Note: reflects outcomes strictly before the current event.
        scenario_context["outcome_summary"] = outcome_store.summary()

        # 3. Run reasoning slice
        twin_dict = _twin_state_to_agent_dict(live_state)
        reasoning_result = _run_reasoning_slice(twin_dict, scenario_context)

        gov = reasoning_result.get("governance_output", {})
        gov_meta = reasoning_result.get("_governance_meta", {}) or {}
        policy = reasoning_result.get("policy_decision", {}) or {}
        route = policy.get("route")

        # 4. Route to execution or skip
        execution_status, outcome_dict, execution_error, live_state = _route_and_execute(
            route=route,
            governance_output=gov,
            governance_meta=gov_meta,
            live_state=live_state,
            event=event,
            outcome_store=outcome_store,
            auto_approve_escalations=auto_approve_escalations,
        )

        # 5. Collect record
        record: dict[str, Any] = {
            "schema_version": "1.0",
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "scenario_context": scenario_context,
            "governance_output": gov,
            "policy_decision": policy,
            "execution_status": execution_status,
            "execution_outcome": outcome_dict,
            "trace_log": reasoning_result.get("trace_log", []),
        }
        if execution_error is not None:
            record["execution_error"] = execution_error
        event_results.append(record)

    return {
        "event_results": event_results,
        "events_processed": len(event_results),
        "outcomes_count": outcome_store.count(),
        "outcome_summary": outcome_store.summary(),
        "final_twin_state_summary": _build_twin_summary(live_state),
    }


# ---------------------------------------------------------------------------
# Routing + execution (Phase 3)
# ---------------------------------------------------------------------------


def _route_and_execute(
    *,
    route: str | None,
    governance_output: dict[str, Any],
    governance_meta: dict[str, Any],
    live_state: TwinState,
    event: EventPayload,
    outcome_store: OutcomeStore,
    auto_approve_escalations: bool,
) -> tuple[str, dict[str, Any] | None, str | None, TwinState]:
    """Route a policy decision and (maybe) execute the corresponding adapter.

    Returns (execution_status, outcome_dict_or_None, error_str_or_None, new_state).
    ``new_state`` equals the input ``live_state`` if nothing was executed.
    """
    if route == "AUTO_EXECUTE":
        outcome_store.record_routing("AUTO_EXECUTE")
        return _try_execute(
            governance_output=governance_output,
            governance_meta=governance_meta,
            live_state=live_state,
            event=event,
            outcome_store=outcome_store,
            status_on_success="executed",
        )

    if route == "HUMAN_REQUIRED":
        outcome_store.record_routing("HUMAN_REQUIRED")
        if auto_approve_escalations:
            # Demo-only override: do NOT silently treat escalations as auto.
            return _try_execute(
                governance_output=governance_output,
                governance_meta=governance_meta,
                live_state=live_state,
                event=event,
                outcome_store=outcome_store,
                status_on_success="executed_via_demo_override",
            )
        return "awaiting_human_review", None, None, live_state

    # Unknown / missing route — fail-closed: do not execute.
    # This path is a contract-drift signal (policy_gate should always emit
    # AUTO_EXECUTE or HUMAN_REQUIRED when policy_gate_enabled=True). The
    # execution_error field documents the anomaly for audit.
    return (
        "unknown_route",
        None,
        f"policy_decision.route={route!r} is not recognized; no execution performed",
        live_state,
    )


def _try_execute(
    *,
    governance_output: dict[str, Any],
    governance_meta: dict[str, Any],
    live_state: TwinState,
    event: EventPayload,
    outcome_store: OutcomeStore,
    status_on_success: str,
) -> tuple[str, dict[str, Any] | None, str | None, TwinState]:
    """Attempt execution; convert errors into a degraded record (no raise).

    On success: appends outcome to store and returns updated state.
    On failure: returns ``execution_failed`` with an error string; state
    unchanged; nothing appended to store.

    When ``status_on_success == "executed_via_demo_override"``, prepends an
    explicit ``[DEMO_OVERRIDE]`` marker to outcome.notes so the audit trail
    clearly reflects that a HUMAN_REQUIRED event was executed only because
    of the demo-only override flag — never silently.
    """
    try:
        new_state, outcome = execute_action(
            governance_output=governance_output,
            twin_state=live_state,
            event_id=event.event_id,
            governance_meta=governance_meta,
            timestamp=event.timestamp,
        )
    except (ExecutionInfeasibleError, GovernanceActionParseError) as exc:
        return (
            "execution_failed",
            None,
            f"{type(exc).__name__}: {exc}",
            live_state,
        )

    # Audit-annotate demo overrides at the outcome level (not only the record).
    if status_on_success == "executed_via_demo_override":
        outcome = outcome.model_copy(update={
            "notes": f"[DEMO_OVERRIDE on HUMAN_REQUIRED] {outcome.notes}".rstrip(),
        })

    outcome_store.append(outcome)
    return status_on_success, outcome.model_dump(mode="json"), None, new_state


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _twin_state_to_agent_dict(ts: TwinState) -> dict[str, Any]:
    """Serialize TwinState to the dict format expected by graph node functions.

    Agents expect the case JSON snapshot format:
      - entities as lists of dicts (not dict-of-dicts)
      - active_order as a nested dict
      - top-level fields for timestamp, current_disruptions, cost_policy

    This mirrors the structure produced by load_case_or_scenario from case JSONs.
    """
    return {
        "timestamp": ts.timestamp.isoformat(),
        "suppliers": [s.model_dump() for s in ts.suppliers.values()],
        "warehouses": [w.model_dump() for w in ts.warehouses.values()],
        "carriers": [c.model_dump() for c in ts.carriers.values()],
        "customer_zones": [z.model_dump() for z in ts.customer_zones.values()],
        "current_disruptions": ts.current_disruptions,
        "cost_policy": ts.cost_policy.model_dump(),
        "active_order": {
            "order_id": ts.order_id,
            "order_units": ts.order_units,
            "source_warehouse_id": ts.source_warehouse_id,
            "customer_zone_id": ts.customer_zone_id,
            "planned_carrier_id": ts.planned_carrier_id,
            "planned_eta_hours": ts.planned_eta_hours,
        },
        # Top-level copies for agents that read flat keys
        "order_id": ts.order_id,
        "order_units": ts.order_units,
        "source_warehouse_id": ts.source_warehouse_id,
        "customer_zone_id": ts.customer_zone_id,
        "planned_carrier_id": ts.planned_carrier_id,
        "planned_eta_hours": ts.planned_eta_hours,
    }


def _build_twin_summary(ts: TwinState) -> dict[str, Any]:
    """Build a lightweight summary of the current TwinState."""
    return {
        "timestamp": ts.timestamp.isoformat(),
        "planned_eta_hours": ts.planned_eta_hours,
        "order_id": ts.order_id,
        "order_units": ts.order_units,
        "disruptions_count": len(ts.current_disruptions),
        "carriers": {
            cid: {"available": c.available, "transit_time_hours": c.transit_time_hours}
            for cid, c in ts.carriers.items()
        },
        "warehouses": {
            wid: {"current_inventory": w.current_inventory}
            for wid, w in ts.warehouses.items()
        },
        "customer_zones": {
            zid: {"demand_units": z.demand_units}
            for zid, z in ts.customer_zones.items()
        },
    }
