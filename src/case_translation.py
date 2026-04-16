"""
case_translation.py — Deterministic oracle selection and SPEC §9 tie-breaking.

Minimal scope: only the functions needed for Task 1.1 ground-truth generation.
No CSV parsing, no LLM, no stochastic logic.
"""

from __future__ import annotations

from twin_state import Action, ActionType, TwinState

# ---------------------------------------------------------------------------
# Tie-breaking priority (SPEC §9.3 step 4)
# ---------------------------------------------------------------------------

_ACTION_PRIORITY: dict[str, int] = {
    ActionType.EXPEDITE.value: 0,
    ActionType.TRANSFER.value: 1,
    ActionType.COMPENSATE.value: 2,
    ActionType.NO_ACTION.value: 3,
}


# ---------------------------------------------------------------------------
# Cost computation for a set of candidate actions
# ---------------------------------------------------------------------------


def compute_candidate_costs(
    baseline_path: str,
    state_patches: list[dict],
    candidate_operational_actions: dict[str, dict],
) -> dict[str, dict]:
    """Load baseline, apply state_patches, then compute cost for each candidate action.

    Each candidate action is evaluated in an isolated deep copy of the patched state
    so that actions do not interfere with one another.

    Infeasible actions (those that raise during ``apply_action`` or construction)
    are recorded with ``feasible=False`` and ``error=<message>`` rather than
    raising and aborting the entire evaluation.  Only feasible records participate
    in oracle selection via ``select_optimal_action``.

    Parameters
    ----------
    baseline_path:
        Path to the canonical baseline_network.json.
    state_patches:
        List of individual patch dicts (entity_patches items), applied as a
        single shock before evaluating actions.  Pass [] for no patches.
    candidate_operational_actions:
        Dict mapping action_key -> Action kwargs dict.

    Returns
    -------
    dict[action_key, cost_record]
        Each cost_record always contains ``action_key``, ``action_type``,
        ``feasible`` (bool), and ``error`` (str | None).
        Feasible records additionally contain ``total_cost``,
        ``sla_lateness_penalty``, and ``direct_action_cost``.
        Infeasible records set those three fields to ``None``.
    """
    base_state = TwinState.initialize_from_config(baseline_path)
    if state_patches:
        base_state.inject_shock({"entity_patches": state_patches})

    results: dict[str, dict] = {}
    for action_key, action_kwargs in candidate_operational_actions.items():
        state_copy = base_state.model_copy(deep=True)
        try:
            action = Action(**action_kwargs)
            state_copy.apply_action(action)
            total = state_copy.compute_total_cost()
            bd = state_copy.last_cost_breakdown
            results[action_key] = {
                "action_key": action_key,
                "action_type": action_kwargs["action_type"],
                "feasible": True,
                "error": None,
                "total_cost": total,
                "sla_lateness_penalty": bd["sla_lateness_penalty"],
                "direct_action_cost": bd["direct_action_cost"],
            }
        except (ValueError, RuntimeError) as exc:
            results[action_key] = {
                "action_key": action_key,
                "action_type": action_kwargs["action_type"],
                "feasible": False,
                "error": str(exc),
                "total_cost": None,
                "sla_lateness_penalty": None,
                "direct_action_cost": None,
            }

    return results


# ---------------------------------------------------------------------------
# Oracle selection with SPEC §9 tie-breaking
# ---------------------------------------------------------------------------


def select_optimal_action(
    cost_records: dict[str, dict],
) -> tuple[list[str], str]:
    """Apply SPEC §9.1–§9.3 tie-breaking to select the canonical optimal action.

    Only feasible records participate.  A record is considered feasible when its
    ``feasible`` field is ``True``, or when the field is absent (backward-compatible
    with hand-crafted records that pre-date the feasibility flag).

    Parameters
    ----------
    cost_records:
        Dict returned by ``compute_candidate_costs`` (or any dict mapping
        action_key -> record with keys: total_cost, sla_lateness_penalty,
        direct_action_cost, action_type, and optionally feasible / error).

    Returns
    -------
    (optimal_action_set, optimal_action)
        optimal_action_set: all feasible keys whose total_cost equals the minimum.
        optimal_action: single canonical best, resolved by:
          1. lowest total_cost
          2. lowest sla_lateness_penalty
          3. lowest direct_action_cost
          4. EXPEDITE > TRANSFER > COMPENSATE > NO_ACTION

    Raises
    ------
    ValueError
        If cost_records is empty or all records are infeasible.
    """
    if not cost_records:
        raise ValueError("cost_records must contain at least one entry")

    # Filter to feasible records only; records without the key default to feasible.
    feasible = [r for r in cost_records.values() if r.get("feasible", True)]
    if not feasible:
        raise ValueError(
            "No feasible actions found in cost_records; cannot select oracle."
        )

    min_cost = min(r["total_cost"] for r in feasible)

    optimal_set = [
        r["action_key"] for r in feasible if r["total_cost"] == min_cost
    ]

    # Sort tied records by the full tie-breaking key
    tied = [r for r in feasible if r["total_cost"] == min_cost]
    tied.sort(
        key=lambda r: (
            r["total_cost"],
            r["sla_lateness_penalty"],
            r["direct_action_cost"],
            _ACTION_PRIORITY.get(r["action_type"], 99),
        )
    )

    return optimal_set, tied[0]["action_key"]
