"""replan/replan_trigger.py — B1 Slice 2 pure trigger.

Decides whether a replan is warranted after a single execution
attempt and produces a structured ``ReplanTriggerRecord``. Pure and
deterministic: no I/O, no wall-clock, no randomness, no mutation of
its inputs; no memory read, no learning import, no orchestration.

Priority order (single record per call — exactly one ``trigger_type``
is emitted):

    1. PREFLIGHT_FAILED   — ``execution_status == "preflight_failed"``
    2. EXECUTION_FAILED   — hard failure of the execution path:
                             - ``execution_status`` is
                               ``"execution_failed"`` or
                               ``"unknown_route"``, OR
                             - ``execution_status`` is an executed
                               variant (``"executed"`` /
                               ``"executed_via_demo_override"``) but
                               ``execution_outcome`` is missing.
    3. COST_DEVIATION     — realized cost outside the expected closed
                             range. Requires ``expected_outcome`` and
                             a numeric ``cost_incurred``.
    4. SLA_DEVIATION      — ``expected_outcome.expected_sla_preserved``
                             is True AND the realized
                             ``sla_impact.preserved`` is False.
                             Gated by ``config.sla_deviation_enabled``.
    5. NO_TRIGGER         — otherwise.

Range rule for COST_DEVIATION:

    breach_magnitude = max(0.0,
                           expected_cost_min - realized_cost,
                           realized_cost - expected_cost_max)
    absolute_delta   = breach_magnitude
    relative_delta   = absolute_delta / max(1.0, expected_cost_max)

    The ``cost_deviation_abs_threshold`` /
    ``cost_deviation_rel_threshold`` values from ``ReplanConfig`` are
    recorded in ``deviation_measurement`` for audit; they do NOT gate
    the decision in Slice 2 (the range is the gate).

``deviation_measurement`` carries numeric facts only (float | int |
bool), matching the schema contract. Natural language never enters.
"""

from __future__ import annotations

from typing import Any

from replan.replan_config import KNOWN_TRIGGER_RULE_IDS, ReplanConfig
from replan.replan_schema import ExpectedOutcomeRef, ReplanTriggerRecord


# Rule-id pins. Must remain members of KNOWN_TRIGGER_RULE_IDS —
# asserted below.
_RULE_NO_TRIGGER: str = "no_trigger_v1"
_RULE_COST_DEVIATION: str = "cost_deviation_v1"
_RULE_SLA_DEVIATION: str = "sla_deviation_v1"
_RULE_EXECUTION_FAILED: str = "execution_failed_v1"
_RULE_PREFLIGHT_FAILED: str = "preflight_failed_v1"

for _rid in (
    _RULE_NO_TRIGGER,
    _RULE_COST_DEVIATION,
    _RULE_SLA_DEVIATION,
    _RULE_EXECUTION_FAILED,
    _RULE_PREFLIGHT_FAILED,
):
    assert _rid in KNOWN_TRIGGER_RULE_IDS, (
        f"replan_trigger: rule id {_rid!r} missing from "
        f"KNOWN_TRIGGER_RULE_IDS"
    )


_EXECUTED_STATUSES = frozenset({"executed", "executed_via_demo_override"})
_HARD_FAIL_STATUSES = frozenset({"execution_failed", "unknown_route"})


def _extract_realized_cost(execution_outcome: dict[str, Any] | None) -> float | None:
    if not isinstance(execution_outcome, dict):
        return None
    v = execution_outcome.get("cost_incurred")
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _extract_realized_sla_preserved(
    execution_outcome: dict[str, Any] | None,
) -> bool | None:
    if not isinstance(execution_outcome, dict):
        return None
    sla_impact = execution_outcome.get("sla_impact")
    if not isinstance(sla_impact, dict):
        return None
    v = sla_impact.get("preserved")
    if isinstance(v, bool):
        return v
    return None


def decide_replan_trigger(
    *,
    expected_outcome: ExpectedOutcomeRef | None,
    execution_status: str,
    execution_outcome: dict[str, Any] | None,
    attempt_index: int,
    config: ReplanConfig,
) -> ReplanTriggerRecord:
    """Return a structured ``ReplanTriggerRecord`` for one attempt.

    Pure function. Does NOT read memory, does NOT call any agent,
    does NOT invoke ``execute_action``, does NOT mutate its inputs.

    Parameters
    ----------
    expected_outcome
        Structured expected outcome for the recommended candidate.
        May be ``None`` when the estimator could not produce one
        (in which case cost / SLA deviation cannot fire, but failure
        rules still can).
    execution_status
        The Path C / Path B execution-status literal for the attempt.
    execution_outcome
        The executed outcome dict, or ``None`` for non-execute
        statuses.
    attempt_index
        0-based attempt index carried on the record.
    config
        Replan configuration (used for: ``sla_deviation_enabled``,
        and for carrying the abs/rel thresholds into the audit
        measurement).

    Returns
    -------
    ReplanTriggerRecord
        Exactly one record, with exactly one ``trigger_type``.
    """
    if not isinstance(attempt_index, int) or attempt_index < 0:
        raise ValueError(
            f"decide_replan_trigger: attempt_index must be a "
            f"non-negative int, got {attempt_index!r}"
        )

    realized_cost = _extract_realized_cost(execution_outcome)
    realized_sla_preserved = _extract_realized_sla_preserved(execution_outcome)

    # 1. PREFLIGHT_FAILED
    if execution_status == "preflight_failed":
        return ReplanTriggerRecord(
            trigger_rule_id=_RULE_PREFLIGHT_FAILED,
            trigger_type="PREFLIGHT_FAILED",
            attempt_index=attempt_index,
            deviation_measurement={},
            expected_outcome_ref=expected_outcome,
            realized_cost=realized_cost,
            realized_sla_preserved=realized_sla_preserved,
            notes="preflight rejected attempt",
        )

    # 2. EXECUTION_FAILED
    missing_outcome_for_executed = (
        execution_status in _EXECUTED_STATUSES and execution_outcome is None
    )
    if execution_status in _HARD_FAIL_STATUSES or missing_outcome_for_executed:
        return ReplanTriggerRecord(
            trigger_rule_id=_RULE_EXECUTION_FAILED,
            trigger_type="EXECUTION_FAILED",
            attempt_index=attempt_index,
            deviation_measurement={},
            expected_outcome_ref=expected_outcome,
            realized_cost=realized_cost,
            realized_sla_preserved=realized_sla_preserved,
            notes=(
                "missing execution_outcome for executed status"
                if missing_outcome_for_executed
                else f"hard failure status: {execution_status}"
            ),
        )

    # 3. COST_DEVIATION — needs both expected range and realized cost.
    if expected_outcome is not None and realized_cost is not None:
        expected_min = float(expected_outcome.expected_cost_min)
        expected_max = float(expected_outcome.expected_cost_max)
        breach = max(
            0.0,
            expected_min - realized_cost,
            realized_cost - expected_max,
        )
        if breach > 0.0:
            relative_delta = breach / max(1.0, expected_max)
            deviation: dict[str, float | int | bool] = {
                "realized_cost": float(realized_cost),
                "expected_cost_min": expected_min,
                "expected_cost_max": expected_max,
                "absolute_delta": float(breach),
                "relative_delta": float(relative_delta),
                "cost_deviation_abs_threshold": float(
                    config.cost_deviation_abs_threshold
                ),
                "cost_deviation_rel_threshold": float(
                    config.cost_deviation_rel_threshold
                ),
                "band_abs_used": float(config.expected_cost_band_abs),
                "band_rel_used": float(config.expected_cost_band_rel),
            }
            return ReplanTriggerRecord(
                trigger_rule_id=_RULE_COST_DEVIATION,
                trigger_type="COST_DEVIATION",
                attempt_index=attempt_index,
                deviation_measurement=deviation,
                expected_outcome_ref=expected_outcome,
                realized_cost=realized_cost,
                realized_sla_preserved=realized_sla_preserved,
                notes="realized cost outside expected range",
            )

    # 4. SLA_DEVIATION — gated by config; requires expected_sla_preserved=True
    #    and a realized preserved=False.
    if (
        config.sla_deviation_enabled
        and expected_outcome is not None
        and expected_outcome.expected_sla_preserved is True
        and realized_sla_preserved is False
    ):
        deviation_sla: dict[str, float | int | bool] = {
            "expected_sla_preserved": True,
            "realized_sla_preserved": False,
        }
        if realized_cost is not None:
            deviation_sla["realized_cost"] = float(realized_cost)
        return ReplanTriggerRecord(
            trigger_rule_id=_RULE_SLA_DEVIATION,
            trigger_type="SLA_DEVIATION",
            attempt_index=attempt_index,
            deviation_measurement=deviation_sla,
            expected_outcome_ref=expected_outcome,
            realized_cost=realized_cost,
            realized_sla_preserved=realized_sla_preserved,
            notes="expected SLA preserved but realized preserved==False",
        )

    # 5. NO_TRIGGER
    return ReplanTriggerRecord(
        trigger_rule_id=_RULE_NO_TRIGGER,
        trigger_type="NO_TRIGGER",
        attempt_index=attempt_index,
        deviation_measurement={},
        expected_outcome_ref=expected_outcome,
        realized_cost=realized_cost,
        realized_sla_preserved=realized_sla_preserved,
        notes="",
    )
