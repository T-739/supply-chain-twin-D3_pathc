"""
event_sequence.py — D3-Demo Phase 1: Sequential case replay runner.

Processes a list of case_ids through the compiled LangGraph graph
in sequence.  This is a Phase 1 / Path A fallback — NOT a true event
engine.  No EventPayload, no TwinState patching, no execution adapters,
no outcome store, no cross-case learning.

Usage:
    from event_sequence import run_case_sequence
    results = run_case_sequence(["M01", "M02", "P01"])
"""

from __future__ import annotations

from typing import Any


def run_case_sequence(
    case_ids: list[str],
    *,
    supervisor_instruction: dict[str, Any] | None = None,
    graph: Any | None = None,
) -> list[dict[str, Any]]:
    """Run a sequence of cases through the graph and collect results.

    Parameters
    ----------
    case_ids : list[str]
        Ordered list of case IDs to process sequentially.
    supervisor_instruction : dict or None
        Supervisor instruction injected into every case run.
        Defaults to ``{"mode": "approve"}`` if None.
        Only applies to cases that are routed to the supervisor
        (HUMAN_REQUIRED); auto-executed cases bypass the supervisor.
    graph : compiled graph or None
        Pre-compiled LangGraph runnable.  If None, compiles a fresh one.

    Returns
    -------
    list[dict]
        One summary dict per case, in input order.
    """
    if graph is None:
        from graph import compile_graph
        graph = compile_graph()

    if supervisor_instruction is None:
        supervisor_instruction = {"mode": "approve"}

    summaries: list[dict[str, Any]] = []

    for case_id in case_ids:
        result = graph.invoke({
            "case_id": case_id,
            "supervisor_instruction": supervisor_instruction,
            "policy_gate_enabled": True,
        })
        summaries.append(_extract_summary(case_id, result))

    return summaries


def _extract_summary(case_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Extract a compact summary from a graph result."""
    gov = result.get("governance_output", {})
    policy = result.get("policy_decision", {})
    sup = result.get("supervisor_output", {})
    ev = result.get("evaluation_result", {})

    route = policy.get("route", "UNKNOWN")
    supervisor_used = route == "HUMAN_REQUIRED"

    return {
        "case_id": case_id,
        "risk_level": gov.get("risk_level", "UNKNOWN"),
        "policy_route": route,
        "supervisor_used": supervisor_used,
        "supervisor_decision_type": sup.get("supervisor_decision_type"),
        "evaluation_status": ev.get("status", "missing"),
        "regret": ev.get("regret"),
        "chosen_cost": ev.get("chosen_cost"),
        "oracle_cost": ev.get("oracle_cost"),
    }
