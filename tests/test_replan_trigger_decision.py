"""B1 Slice 2: trigger decision pure-function tests.

Covers ``src/replan/replan_trigger.py::decide_replan_trigger``.

One-record-per-call contract: a single ``ReplanTriggerRecord`` is
produced with exactly one ``trigger_type``. Priority order tested:
PREFLIGHT_FAILED > EXECUTION_FAILED > COST_DEVIATION >
SLA_DEVIATION > NO_TRIGGER.

The trigger records numeric-only ``deviation_measurement``: these
tests assert the structural shape as well as the decision branch.
"""

from __future__ import annotations

import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from replan import (  # noqa: E402
    ExpectedOutcomeRef,
    KNOWN_TRIGGER_RULE_IDS,
    ReplanConfig,
    decide_replan_trigger,
)


def _expected(min_: float, max_: float, *, sla: bool = True) -> ExpectedOutcomeRef:
    return ExpectedOutcomeRef(
        expected_cost_min=min_,
        expected_cost_max=max_,
        expected_sla_preserved=sla,
        estimator_id="test-estimator",
    )


def _outcome(cost: float, *, sla_preserved: bool = True) -> dict:
    return {
        "cost_incurred": cost,
        "sla_impact": {"preserved": sla_preserved, "late_hours": 0.0},
    }


# ---------------------------------------------------------------------------
# NO_TRIGGER
# ---------------------------------------------------------------------------


def test_no_trigger_when_cost_in_range_and_sla_preserved():
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0, sla=True),
        execution_status="executed",
        execution_outcome=_outcome(100.0, sla_preserved=True),
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "NO_TRIGGER"
    assert rec.trigger_rule_id == "no_trigger_v1"
    assert rec.trigger_rule_id in KNOWN_TRIGGER_RULE_IDS
    assert rec.attempt_index == 0
    assert rec.deviation_measurement == {}
    assert rec.realized_cost == 100.0
    assert rec.realized_sla_preserved is True


def test_no_trigger_when_expected_outcome_absent_and_execution_clean():
    rec = decide_replan_trigger(
        expected_outcome=None,
        execution_status="executed",
        execution_outcome=_outcome(500.0, sla_preserved=True),
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "NO_TRIGGER"


# ---------------------------------------------------------------------------
# COST_DEVIATION
# ---------------------------------------------------------------------------


def test_cost_deviation_when_realized_above_max():
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0, sla=True),
        execution_status="executed",
        execution_outcome=_outcome(180.0, sla_preserved=True),
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "COST_DEVIATION"
    assert rec.trigger_rule_id == "cost_deviation_v1"
    dm = rec.deviation_measurement
    assert dm["realized_cost"] == 180.0
    assert dm["expected_cost_max"] == 120.0
    assert dm["absolute_delta"] == pytest.approx(60.0)
    # relative_delta = 60 / max(1, 120) = 0.5
    assert dm["relative_delta"] == pytest.approx(0.5)
    # Audit fields carried through:
    assert dm["cost_deviation_abs_threshold"] == 50.0
    assert dm["cost_deviation_rel_threshold"] == 0.2
    assert dm["band_abs_used"] == 25.0
    assert dm["band_rel_used"] == 0.1


def test_cost_deviation_when_realized_below_min():
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0, sla=True),
        execution_status="executed",
        execution_outcome=_outcome(5.0, sla_preserved=True),
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "COST_DEVIATION"
    dm = rec.deviation_measurement
    assert dm["absolute_delta"] == pytest.approx(75.0)


def test_cost_deviation_measurement_all_numeric():
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0),
        execution_status="executed",
        execution_outcome=_outcome(200.0),
        attempt_index=0,
        config=ReplanConfig(),
    )
    for k, v in rec.deviation_measurement.items():
        assert isinstance(k, str)
        assert isinstance(v, (float, int, bool)), (
            f"deviation_measurement[{k!r}] must be numeric, got {type(v)}"
        )


# ---------------------------------------------------------------------------
# SLA_DEVIATION
# ---------------------------------------------------------------------------


def test_sla_deviation_when_expected_preserved_but_realized_missed():
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0, sla=True),
        execution_status="executed",
        execution_outcome=_outcome(100.0, sla_preserved=False),
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "SLA_DEVIATION"
    assert rec.trigger_rule_id == "sla_deviation_v1"
    dm = rec.deviation_measurement
    assert dm["expected_sla_preserved"] is True
    assert dm["realized_sla_preserved"] is False


def test_sla_deviation_suppressed_when_expected_preserved_false():
    # Expected not-preserved; realized not-preserved is NOT a deviation.
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0, sla=False),
        execution_status="executed",
        execution_outcome=_outcome(100.0, sla_preserved=False),
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "NO_TRIGGER"


def test_sla_deviation_gated_by_config():
    cfg = ReplanConfig(sla_deviation_enabled=False)
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0, sla=True),
        execution_status="executed",
        execution_outcome=_outcome(100.0, sla_preserved=False),
        attempt_index=0,
        config=cfg,
    )
    assert rec.trigger_type == "NO_TRIGGER"


# ---------------------------------------------------------------------------
# EXECUTION_FAILED / PREFLIGHT_FAILED
# ---------------------------------------------------------------------------


def test_preflight_failed():
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0),
        execution_status="preflight_failed",
        execution_outcome=None,
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "PREFLIGHT_FAILED"
    assert rec.trigger_rule_id == "preflight_failed_v1"
    assert rec.deviation_measurement == {}


def test_execution_failed_hard_status():
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0),
        execution_status="execution_failed",
        execution_outcome=None,
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "EXECUTION_FAILED"
    assert rec.trigger_rule_id == "execution_failed_v1"


def test_execution_failed_unknown_route():
    rec = decide_replan_trigger(
        expected_outcome=None,
        execution_status="unknown_route",
        execution_outcome=None,
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "EXECUTION_FAILED"


def test_execution_failed_when_executed_but_outcome_missing():
    # Anomalous: status says executed but no outcome captured.
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0),
        execution_status="executed",
        execution_outcome=None,
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "EXECUTION_FAILED"


def test_awaiting_human_review_not_a_failure():
    # Human-review route is not an execution failure — no terminal execution.
    # Without realized cost/sla, nothing to compare against → NO_TRIGGER.
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0),
        execution_status="awaiting_human_review",
        execution_outcome=None,
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "NO_TRIGGER"


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


def test_preflight_beats_everything():
    # Even with a cost / sla deviation present in the outcome, preflight wins.
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0, sla=True),
        execution_status="preflight_failed",
        execution_outcome=_outcome(500.0, sla_preserved=False),
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "PREFLIGHT_FAILED"


def test_cost_beats_sla_when_both_fire():
    # Cost is outside range AND SLA missed. Cost wins per priority order.
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0, sla=True),
        execution_status="executed",
        execution_outcome=_outcome(500.0, sla_preserved=False),
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "COST_DEVIATION"


# ---------------------------------------------------------------------------
# attempt_index carry-through
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ai", [0, 1])
def test_attempt_index_is_recorded(ai):
    rec = decide_replan_trigger(
        expected_outcome=_expected(80.0, 120.0),
        execution_status="executed",
        execution_outcome=_outcome(100.0, sla_preserved=True),
        attempt_index=ai,
        config=ReplanConfig(),
    )
    assert rec.attempt_index == ai


def test_negative_attempt_index_rejected():
    with pytest.raises(ValueError, match="attempt_index"):
        decide_replan_trigger(
            expected_outcome=None,
            execution_status="executed",
            execution_outcome=_outcome(100.0),
            attempt_index=-1,
            config=ReplanConfig(),
        )


# ---------------------------------------------------------------------------
# trigger_rule_id always registered
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["no_trigger", "cost", "sla", "exec", "preflight"])
def test_emitted_rule_id_is_in_known_registry(scenario):
    expected = _expected(80.0, 120.0, sla=True)
    cfg = ReplanConfig()
    if scenario == "no_trigger":
        rec = decide_replan_trigger(
            expected_outcome=expected, execution_status="executed",
            execution_outcome=_outcome(100.0), attempt_index=0, config=cfg,
        )
    elif scenario == "cost":
        rec = decide_replan_trigger(
            expected_outcome=expected, execution_status="executed",
            execution_outcome=_outcome(500.0), attempt_index=0, config=cfg,
        )
    elif scenario == "sla":
        rec = decide_replan_trigger(
            expected_outcome=expected, execution_status="executed",
            execution_outcome=_outcome(100.0, sla_preserved=False),
            attempt_index=0, config=cfg,
        )
    elif scenario == "exec":
        rec = decide_replan_trigger(
            expected_outcome=None, execution_status="execution_failed",
            execution_outcome=None, attempt_index=0, config=cfg,
        )
    elif scenario == "preflight":
        rec = decide_replan_trigger(
            expected_outcome=None, execution_status="preflight_failed",
            execution_outcome=None, attempt_index=0, config=cfg,
        )
    assert rec.trigger_rule_id in KNOWN_TRIGGER_RULE_IDS
