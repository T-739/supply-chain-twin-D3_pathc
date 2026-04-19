"""
graph.py — LangGraph state contract and graph with D3 Policy Gate.

Defines GraphState (the shared state schema) and the runnable graph.

Flow (D3 Phase 1):
  load_case_or_scenario
       |
  inject_scenario
       |
  ┌────┴────┐
  operations  cost        (fan-out — parallel in future)
  └────┬────┘
       |
  governance_agent_node
       |
  policy_gate_node ──────────────┐
       |                         |
  (HUMAN_REQUIRED)          (AUTO_EXECUTE)
       |                         |
  supervisor_node         auto_approve_shim
       |                         |
  evaluation_node ◄──────────────┘
"""

from __future__ import annotations

import json
import os
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# GraphState — shared state contract for Week 2
# ---------------------------------------------------------------------------


class GraphState(TypedDict, total=False):
    """Shared state flowing through the LangGraph graph.

    All fields use total=False so nodes can populate them incrementally.
    """

    # --- Case & scenario identity ---
    case_id: str
    scenario_id: str
    scenario_context: dict[str, Any]

    # --- Twin state (serialized or object ref) ---
    twin_state: dict[str, Any]

    # --- Operational action menu from case JSON ---
    allowed_operational_actions: list[dict[str, Any]]

    # --- Agent outputs ---
    operations_output: dict[str, Any]
    cost_output: dict[str, Any]
    governance_output: dict[str, Any]

    # --- Governance identity metadata (outside frozen 8-field schema) ---
    _governance_meta: dict[str, Any]

    # --- Supervisor ---
    supervisor_instruction: dict[str, Any]  # injected by caller
    supervisor_output: dict[str, Any]       # structured SupervisorDecision

    # --- Legacy supervisor fields (kept for backward compat) ---
    supervisor_decision: str          # APPROVE / VERIFY / OVERRIDE (supervision layer)
    final_decision_code: str          # same domain (supervision layer)

    # --- Governance mode (Phase 3) ---
    # Optional. "rules" (default) or "llm". Unknown values degrade to "rules".
    governance_mode: str
    # Optional Phase 2 GatewayConfig for the governance LLM call.
    governance_gateway_config: Any

    # --- Operations mode (Phase 4) ---
    # Optional. "rules" (default) or "llm". Unknown values degrade to "rules".
    operations_mode: str
    # Optional Phase 2 GatewayConfig for the operations LLM call.
    operations_gateway_config: Any
    # Operations identity metadata (outside frozen OperationsOutput schema).
    _operations_meta: dict[str, Any]

    # --- Retrieval mode (Phase 6 integration) ---
    # Optional. One of "tfidf_legacy" (default), "dense", "hybrid",
    # "hybrid_rerank". Unknown values degrade to "tfidf_legacy".
    retrieval_mode: str
    retrieval_k: int

    # --- D3 Policy Gate (Phase 1) ---
    # Set policy_gate_enabled=True to activate D3 policy-gated routing.
    # When absent or False, graph behaves identically to V2 (all cases → supervisor).
    policy_gate_enabled: bool
    policy_decision: dict[str, Any]

    # --- Evaluation ---
    evaluation_result: dict[str, Any]

    # --- Audit trail ---
    trace_log: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Node implementations (stubs for Package 1)
# ---------------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(os.path.dirname(_BASE_DIR), "data")


def load_case_or_scenario(state: GraphState) -> GraphState:
    """Load case JSON and populate identity + initial context fields."""
    case_id = state.get("case_id", "")
    case_path = os.path.join(_DATA_DIR, "cases", f"{case_id}.json")

    if os.path.exists(case_path):
        with open(case_path) as f:
            case_data = json.load(f)
        state["scenario_id"] = case_data.get("scenario_id", "")
        state["scenario_context"] = {
            "scenario_type": case_data.get("scenario_type", ""),
            "risk_level": case_data.get("risk_level", ""),
            "exception_description": case_data.get("exception_description", ""),
        }
        state["twin_state"] = case_data.get("initial_state_snapshot", {})
        state["allowed_operational_actions"] = case_data.get("decision_options", [])
    else:
        state["scenario_context"] = {}
        state["twin_state"] = {}
        state["allowed_operational_actions"] = []

    state.setdefault("trace_log", [])
    state["trace_log"].append({"node": "load_case_or_scenario", "status": "done"})
    return state


def inject_scenario(state: GraphState) -> GraphState:
    """Apply scenario entity_patches to twin_state (stub — pass-through)."""
    state.setdefault("trace_log", [])
    state["trace_log"].append({"node": "inject_scenario", "status": "stub"})
    return state


def operations_agent_node(state: GraphState) -> GraphState:
    """Operations agent node — produces ranked operational candidates.

    Generates candidates from twin_state entities (EXPEDITE/TRANSFER/
    COMPENSATE/NO_ACTION).  Does NOT consume case decision_options or
    AI/ALT1/ALT2 supervision codes.
    """
    from agents.operations_agent import run_operations_agent_with_meta

    twin_state = state.get("twin_state", {})
    scenario_context = state.get("scenario_context", {})

    state.setdefault("trace_log", [])

    mode = state.get("operations_mode") or "rules"
    gateway_config = state.get("operations_gateway_config")
    retrieval_mode = state.get("retrieval_mode")
    retrieval_k = state.get("retrieval_k") or 4
    # B4 Slice 2C — read the optional sideband threaded through
    # GraphState by ``event_loop._run_reasoning_slice``. Both
    # defaults preserve pre-B4 byte identity; the agent-side
    # ``_b4_should_inject`` predicate (Slice 2B) is the final
    # gate.
    agent_memory_context = state.get("_agent_memory_context")
    agent_memory_config = state.get("_agent_memory_config")
    ops_output, ops_meta = run_operations_agent_with_meta(
        twin_state, scenario_context,
        mode=mode, gateway_config=gateway_config,
        retrieval_mode=retrieval_mode, retrieval_k=int(retrieval_k),
        agent_memory_context=agent_memory_context,
        agent_memory_config=agent_memory_config,
    )
    state["operations_output"] = ops_output.to_dict()
    state["_operations_meta"] = ops_meta

    retrieval_summary = ops_meta.get("retrieval") or {}
    state["trace_log"].append({
        "node": "operations_agent",
        "status": "done",
        "operations_mode": ops_meta.get("mode", "rules"),
        "retrieval_mode": retrieval_summary.get("agent_mode", "tfidf_legacy"),
        "retrieval_candidate_count": retrieval_summary.get("candidate_count"),
        "retrieval_fallback_used": retrieval_summary.get("fallback_used", False),
        "retrieval_reranker_used": retrieval_summary.get("reranker_used", False),
        "retrieval_contextualized": retrieval_summary.get("contextualized", False),
    })
    return state


def cost_agent_node(state: GraphState) -> GraphState:
    """Cost agent node — produces deterministic cost estimates for operational candidates.

    Reads ranked_candidates from operations_output and produces runtime
    decision-support cost estimates.  NOT authoritative evaluation truth.
    """
    from agents.cost_agent import run_cost_agent

    twin_state = state.get("twin_state", {})
    ops_output = state.get("operations_output", {})

    state.setdefault("trace_log", [])

    # Extract candidates from operations output
    candidates = ops_output.get("ranked_candidates", [])
    if not candidates:
        state["cost_output"] = {
            "status": "skipped",
            "reason": "no operational candidates from operations agent",
            "cost_estimates": [],
        }
        state["trace_log"].append({"node": "cost_agent", "status": "skipped"})
        return state

    cost_output = run_cost_agent(twin_state, candidates)
    state["cost_output"] = cost_output.to_dict()
    state["trace_log"].append({"node": "cost_agent", "status": "done"})
    return state


def governance_agent_node(state: GraphState) -> GraphState:
    """Governance agent node — synthesizes GovernanceOutput from ops + cost + scenario.

    Also produces _governance_meta with stable candidate identity mapping
    for the downstream Supervisor node.  Falls back to placeholder if
    upstream outputs are missing.
    """
    from agents.governance_agent import (
        make_placeholder_governance_output,
        run_governance_agent_with_meta,
    )

    state.setdefault("trace_log", [])

    scenario_context = state.get("scenario_context", {})
    ops_output = state.get("operations_output", {})
    cost_output = state.get("cost_output", {})

    # If upstream agents produced usable output, run full synthesis
    if ops_output.get("ranked_candidates"):
        mode = state.get("governance_mode") or "rules"
        gateway_config = state.get("governance_gateway_config")
        gov_output, meta = run_governance_agent_with_meta(
            scenario_context, ops_output, cost_output,
            mode=mode, gateway_config=gateway_config,
        )
        state["governance_output"] = gov_output.to_dict()
        state["_governance_meta"] = meta
        state["trace_log"].append({
            "node": "governance_agent",
            "status": "done",
            "governance_mode": meta.get("mode", "rules"),
        })
    else:
        gov_output = make_placeholder_governance_output()
        state["governance_output"] = gov_output.to_dict()
        state["_governance_meta"] = {
            "recommended_candidate_id": None,
            "recommended_candidate_type": None,
            "alternatives": [],
        }
        state["trace_log"].append({"node": "governance_agent", "status": "placeholder"})

    return state


def policy_gate_node(state: GraphState) -> GraphState:
    """D3 Phase 1 — Policy gate routing based on governance risk_level.

    Only activates when ``policy_gate_enabled`` is True in state.
    When disabled, acts as a pass-through — all cases route to supervisor
    (preserving V2 behavior exactly).

    Reads governance_output, calls decide_policy(), writes policy_decision
    to state.  Pure deterministic routing — no LLM, no cost magnitude,
    no confidence_note.
    """
    state.setdefault("trace_log", [])

    if not state.get("policy_gate_enabled"):
        # V2 compat: silent pass-through, no trace entry, no policy decision.
        # All cases route to supervisor via _policy_gate_route fallback.
        return state

    from policy_gate import PolicyGateConfig, decide_policy

    governance_output = state.get("governance_output", {})
    decision = decide_policy(governance_output, PolicyGateConfig())

    state["policy_decision"] = decision.model_dump(mode="json")
    state["trace_log"].append({
        "node": "policy_gate",
        "status": "done",
        "route": decision.route.value,
        "risk_level": decision.risk_level.value,
        "reason": decision.reason,
    })
    return state


def _policy_gate_route(state: GraphState) -> str:
    """Route after policy gate: auto → auto_approve_shim, human → supervisor.

    When policy_gate_enabled is not set, always routes to supervisor
    (V2 backward-compatible behavior).
    """
    pd = state.get("policy_decision", {})
    if pd.get("route") == "AUTO_EXECUTE":
        return "auto"
    return "human"


def auto_approve_shim(state: GraphState) -> GraphState:
    """Minimal shim: synthesize a supervisor_output for the auto-execute path.

    This exists solely so evaluation_node (which reads supervisor_output)
    can run on auto-executed cases without modification.

    The shim produces a supervisor_output equivalent to APPROVE with
    the governance-recommended candidate, clearly labeled as auto-approved.
    This node does NOT import or call supervisor.py.
    """
    state.setdefault("trace_log", [])

    governance_meta = state.get("_governance_meta", {})
    rec_id = governance_meta.get("recommended_candidate_id")
    rec_type = governance_meta.get("recommended_candidate_type")
    risk_level = state.get("governance_output", {}).get("risk_level", "LOW")

    # Minimal supervisor_output-compatible dict — same shape as
    # SupervisorDecision.to_dict() without importing supervisor.py.
    state["supervisor_output"] = {
        "supervisor_decision_type": "APPROVE",
        "selected_candidate_id": rec_id,
        "selected_candidate_type": rec_type,
        "decision_rationale": (
            f"Auto-approved by policy gate ({risk_level} risk). "
            f"Supervisor was not invoked."
        ),
        "review_requested": False,
        "review_focus": "",
        "override_from_recommendation": False,
    }
    # Legacy compat fields
    state["supervisor_decision"] = "APPROVE"
    state["final_decision_code"] = "APPROVE"

    state["trace_log"].append({
        "node": "auto_approve_shim",
        "status": "done",
        "note": "policy_gate AUTO_EXECUTE; supervisor bypassed",
    })
    return state


def _supervisor_route(state: GraphState) -> str:
    """Route based on supervisor decision — all paths go to evaluation for now."""
    return "evaluate"


def supervisor_node(state: GraphState) -> GraphState:
    """Supervisor node — consumes governance output and records a supervision decision.

    Reads supervisor_instruction from state (injected by caller).
    Defaults to APPROVE if no instruction is provided.
    """
    from supervisor import run_supervisor

    state.setdefault("trace_log", [])

    governance_output = state.get("governance_output", {})
    governance_meta = state.get("_governance_meta", {})
    instruction = state.get("supervisor_instruction")

    decision = run_supervisor(governance_output, governance_meta, instruction)
    state["supervisor_output"] = decision.to_dict()

    # Populate legacy fields for backward compatibility
    state["supervisor_decision"] = decision.supervisor_decision_type
    state["final_decision_code"] = decision.supervisor_decision_type

    state["trace_log"].append({
        "node": "supervisor",
        "status": "done",
        "decision_type": decision.supervisor_decision_type,
    })
    return state


def evaluation_node(state: GraphState) -> GraphState:
    """Evaluation node — Phase 1 bridge to deterministic evaluation truth.

    Reads the authoritative case JSON (cost_ground_truth, oracle,
    agent_recommendation_action_code), maps the supervisor decision into an
    evaluation action code via src/action_code_mapper.py, and calls the
    frozen helpers in src/evaluation.py.

    Never reads runtime cost estimates as evaluation truth.
    Degrades cleanly (status="skipped") if the supervisor didn't run.
    """
    from action_code_mapper import (
        ActionCodeMappingError,
        map_supervisor_to_action_code,
    )
    from evaluation import (
        compute_override_effectiveness,
        compute_regret,
        get_agent_action_code,
        get_total_cost,
        is_override,
        is_unnecessary_override,
    )

    state.setdefault("trace_log", [])

    # Load authoritative case JSON (NOT runtime twin_state)
    case_id = state.get("case_id", "")
    case_path = os.path.join(_DATA_DIR, "cases", f"{case_id}.json")
    if not os.path.exists(case_path):
        state["evaluation_result"] = {
            "status": "skipped",
            "reason": f"case file not found: {case_id}",
        }
        state["trace_log"].append({"node": "evaluation", "status": "skipped"})
        return state

    with open(case_path) as f:
        case_data = json.load(f)

    sup_out = state.get("supervisor_output") or {}
    if not sup_out:
        state["evaluation_result"] = {
            "status": "skipped",
            "reason": "supervisor_output missing; evaluation requires a supervision decision",
        }
        state["trace_log"].append({"node": "evaluation", "status": "skipped"})
        return state

    # Attach override target label (if caller provided one) so the mapper
    # can match an OVERRIDE selection back to the case's decision_options.
    instruction = state.get("supervisor_instruction") or {}
    sup_for_mapping = dict(sup_out)
    if instruction.get("mode") == "override":
        sup_for_mapping["_override_target_label"] = instruction.get(
            "target_action_label", "",
        )

    try:
        human_code = map_supervisor_to_action_code(sup_for_mapping, case_data)
    except ActionCodeMappingError as exc:
        state["evaluation_result"] = {
            "status": "error",
            "reason": f"action code mapping failed: {exc}",
        }
        state["trace_log"].append({"node": "evaluation", "status": "error"})
        return state

    # Compute deterministic evaluation metrics from case JSON truth.
    agent_code = get_agent_action_code(case_data)
    oracle_code = str(case_data["oracle"]["action_code"])
    oracle_cost = float(case_data["oracle"]["cost_total"])
    chosen_cost = get_total_cost(case_data, human_code)

    state["evaluation_result"] = {
        "status": "ok",
        "case_id": case_id,
        "supervisor_decision_type": sup_out.get("supervisor_decision_type"),
        "human_action_code": human_code,
        "agent_action_code": agent_code,
        "oracle_action_code": oracle_code,
        "chosen_cost": chosen_cost,
        "oracle_cost": oracle_cost,
        "regret": compute_regret(case_data, human_code),
        "is_override": is_override(case_data, human_code),
        "is_unnecessary_override": is_unnecessary_override(case_data, human_code),
        "override_effectiveness": compute_override_effectiveness(
            case_data, human_code,
        ),
    }
    state["trace_log"].append({"node": "evaluation", "status": "done"})
    return state


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """Assemble the graph with D3 Phase 1 Policy Gate routing.

    Flow:
      load_case → inject → operations → cost → governance → policy_gate
        → AUTO_EXECUTE:    auto_approve_shim → evaluation → END
        → HUMAN_REQUIRED:  supervisor → evaluation → END
    """
    graph = StateGraph(GraphState)

    # Add nodes (existing + D3 Phase 1 additions)
    graph.add_node("load_case_or_scenario", load_case_or_scenario)
    graph.add_node("inject_scenario", inject_scenario)
    graph.add_node("operations_agent", operations_agent_node)
    graph.add_node("cost_agent", cost_agent_node)
    graph.add_node("governance_agent", governance_agent_node)
    graph.add_node("policy_gate", policy_gate_node)          # D3 Phase 1
    graph.add_node("auto_approve_shim", auto_approve_shim)   # D3 Phase 1
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("evaluation", evaluation_node)

    # Edges — sequential up to governance
    graph.set_entry_point("load_case_or_scenario")
    graph.add_edge("load_case_or_scenario", "inject_scenario")
    graph.add_edge("inject_scenario", "operations_agent")
    graph.add_edge("operations_agent", "cost_agent")
    graph.add_edge("cost_agent", "governance_agent")

    # D3 Phase 1: governance → policy_gate → conditional routing
    graph.add_edge("governance_agent", "policy_gate")
    graph.add_conditional_edges(
        "policy_gate",
        _policy_gate_route,
        {"auto": "auto_approve_shim", "human": "supervisor"},
    )

    # Auto path: shim → evaluation
    graph.add_edge("auto_approve_shim", "evaluation")

    # Human path: supervisor → evaluation (preserving existing conditional)
    graph.add_conditional_edges(
        "supervisor",
        _supervisor_route,
        {"evaluate": "evaluation"},
    )

    graph.add_edge("evaluation", END)

    return graph


def compile_graph():
    """Build and compile the graph, returning a runnable."""
    return build_graph().compile()
