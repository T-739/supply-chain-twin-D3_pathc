"""
evaluation.py
=============
Deterministic evaluation contract for the supply chain twin thesis project.

All numeric truth is read from case JSON cost_ground_truth tables.
TwinState cost recomputation is NOT used for authoritative evaluation.

Action code system (SPEC_BRIDGE.md §"Canonical action frame"):
  AI   = approve AI recommendation
  ALT1 = verify / pause
  ALT2 = alternative plan

compute_total_cost — semantic disambiguation
--------------------------------------------
This module exposes ``compute_total_cost(case, action_code)``.
It is intentionally named differently from TwinState.compute_total_cost():

  evaluation.compute_total_cost(case, action_code)
      → reads case["cost_ground_truth"][action_code]["c_total"]
      → source: CSV oracle truth embedded in case JSON
      → used for: regret, unnecessary override, override effectiveness
      → does NOT call TwinState or run any simulation

  TwinState.compute_total_cost()  (src/twin_state.py)
      → computes runtime simulation cost from the live entity graph
      → source: current entity fields (costs, ETAs, penalties)
      → used for: action selection during simulation, live cost estimation
      → does NOT read from case JSON or CSV

These two functions serve different layers and must never be substituted
for each other.  Evaluation always uses lookup truth; simulation uses
runtime recomputation.
"""

from __future__ import annotations

from typing import Literal

ActionCode = Literal["AI", "ALT1", "ALT2"]

_VALID_ACTION_CODES: frozenset[str] = frozenset({"AI", "ALT1", "ALT2"})


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def normalize_action_code(action_code: str) -> ActionCode:
    """
    Normalise a raw action code string to a canonical ActionCode.

    Raises ValueError for unrecognised codes.

    Parameters
    ----------
    action_code:
        Raw string from CSV, UI input, or agent output.

    Returns
    -------
    ActionCode
        One of "AI", "ALT1", "ALT2".
    """
    code = str(action_code).strip().upper()
    if code not in _VALID_ACTION_CODES:
        raise ValueError(
            f"Unknown action code '{action_code}'. "
            f"Expected one of {sorted(_VALID_ACTION_CODES)}."
        )
    return code  # type: ignore[return-value]


def get_agent_action_code(case: dict) -> ActionCode:
    """
    Return the agent's recommended action code for a case.

    Defaults to "AI" if the case JSON does not override
    ``agent_recommendation_action_code``.

    Parameters
    ----------
    case:
        Parsed case JSON dict.
    """
    raw = case.get("agent_recommendation_action_code", "AI")
    return normalize_action_code(raw)


def get_total_cost(case: dict, action_code: ActionCode) -> float:
    """
    Look up the total cost for a given action code from cost_ground_truth.

    This is the authoritative path for evaluation; it never recomputes
    cost via TwinState simulation.

    Parameters
    ----------
    case:
        Parsed case JSON dict.
    action_code:
        Canonical action code ("AI", "ALT1", "ALT2").

    Returns
    -------
    float
        c_total for the requested action code.
    """
    code = normalize_action_code(action_code)
    try:
        return float(case["cost_ground_truth"][code]["c_total"])
    except KeyError as exc:
        raise KeyError(
            f"cost_ground_truth missing for action_code='{code}' in case '{case.get('case_id', '?')}'"
        ) from exc


def compute_total_cost(case: dict, action_code: ActionCode) -> float:
    """
    Return the total cost for a given action code from the case JSON.

    Semantic distinction — read before using
    -----------------------------------------
    This function reads from ``case["cost_ground_truth"][action_code]["c_total"]``.
    It is the authoritative evaluation path for regret, unnecessary override,
    and override effectiveness metrics.

    It does NOT call TwinState.compute_total_cost() and does NOT recompute
    cost from the live entity graph.

    TwinState.compute_total_cost() (src/twin_state.py) performs runtime
    simulation cost calculation and serves a completely different purpose.
    These two functions must never be substituted for each other.

    Parameters
    ----------
    case:
        Parsed case JSON dict.
    action_code:
        Canonical action code ("AI", "ALT1", "ALT2").

    Returns
    -------
    float
        c_total from cost_ground_truth for the requested action code.
    """
    return get_total_cost(case, action_code)


# ---------------------------------------------------------------------------
# Override detection
# ---------------------------------------------------------------------------


def is_override(case: dict, human_action_code: ActionCode) -> bool:
    """
    Return True if the human's chosen action differs from the agent's recommendation.

    Parameters
    ----------
    case:
        Parsed case JSON dict.
    human_action_code:
        The action code chosen by the human.
    """
    human = normalize_action_code(human_action_code)
    agent = get_agent_action_code(case)
    return human != agent


def is_unnecessary_override(case: dict, human_action_code: ActionCode) -> bool:
    """
    Return True if the human overrode a correct agent recommendation.

    Logic:
        human_action != agent_action  AND  agent_action == oracle_action

    An override is *unnecessary* when the agent was already recommending
    the oracle-optimal action and the human deviated from it.

    Parameters
    ----------
    case:
        Parsed case JSON dict.
    human_action_code:
        The action code chosen by the human.
    """
    human = normalize_action_code(human_action_code)
    agent = get_agent_action_code(case)
    oracle = normalize_action_code(case["oracle"]["action_code"])
    return human != agent and agent == oracle


# ---------------------------------------------------------------------------
# Override effectiveness
# ---------------------------------------------------------------------------


def compute_override_effectiveness(case: dict, human_action_code: ActionCode) -> str:
    """
    Characterise the cost impact of the human's override relative to the
    agent's recommendation.

    Returns
    -------
    str
        One of:
        - "no_override"      — human chose the same action as the agent
        - "cost_reducing"    — human override decreased cost vs agent cost
        - "cost_increasing"  — human override increased cost vs agent cost
        - "neutral"          — human override had no cost impact

    Parameters
    ----------
    case:
        Parsed case JSON dict.
    human_action_code:
        The action code chosen by the human.
    """
    human = normalize_action_code(human_action_code)
    agent = get_agent_action_code(case)

    if human == agent:
        return "no_override"

    human_cost = get_total_cost(case, human)
    agent_cost = get_total_cost(case, agent)

    if human_cost < agent_cost:
        return "cost_reducing"
    elif human_cost > agent_cost:
        return "cost_increasing"
    else:
        return "neutral"


# ---------------------------------------------------------------------------
# Regret
# ---------------------------------------------------------------------------


def compute_regret(case: dict, human_action_code: ActionCode) -> float:
    """
    Compute the regret for a human decision.

    Regret = chosen_cost - oracle_cost

    A positive regret means the human paid more than the optimal action.
    Zero regret means the human chose the oracle-optimal action.
    Negative regret is impossible given the oracle definition (oracle
    minimises cost); if it occurs it indicates a data inconsistency.

    Parameters
    ----------
    case:
        Parsed case JSON dict.
    human_action_code:
        The action code chosen by the human.

    Returns
    -------
    float
        Regret value (≥ 0 under well-formed data).
    """
    human = normalize_action_code(human_action_code)
    chosen_cost = get_total_cost(case, human)
    oracle_cost = float(case["oracle"]["cost_total"])
    return chosen_cost - oracle_cost


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_split_cost(case: dict) -> None:
    """
    Assert that c_direct + c_outcome == c_total for every action code.

    Raises AssertionError with details on the first violation found.

    Parameters
    ----------
    case:
        Parsed case JSON dict.
    """
    cid = case.get("case_id", "?")
    for code in ("AI", "ALT1", "ALT2"):
        gt = case["cost_ground_truth"][code]
        expected = gt["c_direct"] + gt["c_outcome"]
        if expected != gt["c_total"]:
            raise AssertionError(
                f"Case {cid}: [{code}] c_direct({gt['c_direct']}) + "
                f"c_outcome({gt['c_outcome']}) = {expected} "
                f"!= c_total({gt['c_total']})"
            )


def validate_oracle_consistency(case: dict) -> None:
    """
    Assert that oracle cost_total matches cost_ground_truth for the oracle action.

    Also verifies that if ai_correct == True, the oracle action code is "AI".

    Raises AssertionError with details on any violation.

    Parameters
    ----------
    case:
        Parsed case JSON dict.
    """
    cid = case.get("case_id", "?")
    oracle_code = normalize_action_code(case["oracle"]["action_code"])
    oracle_cost = float(case["oracle"]["cost_total"])
    gt_total = float(case["cost_ground_truth"][oracle_code]["c_total"])

    if oracle_cost != gt_total:
        raise AssertionError(
            f"Case {cid}: oracle cost_total={oracle_cost} != "
            f"cost_ground_truth[{oracle_code}].c_total={gt_total}"
        )

    ai_correct = case.get("ai_correct", False)
    if ai_correct and oracle_code != "AI":
        raise AssertionError(
            f"Case {cid}: ai_correct=True but oracle_action_code='{oracle_code}' (expected 'AI')"
        )
