"""B1 Slice 1: replan schema + config contract freeze.

Focused invariants for the B1 subpackage. The broader field-set /
version / roundtrip checks live in
``tests/test_path_c_schema_frozen.py``; this file exercises the
closed-set and validator behaviors that only matter for the B1
contracts and that we want to fail loudly on future drift:

  - ``EXPECTED_COST_RANGE_SOURCE_LITERAL`` is a closed single-value
    ``Literal`` — the D1 provenance rule.
  - ``ReplanTriggerType`` admits exactly five values — the D3 rule.
  - ``KNOWN_TRIGGER_RULE_IDS`` is a non-empty frozenset whose members
    are all non-empty strings.
  - ``MAX_REPLAN_ATTEMPTS == 1`` — the D4 hard cap.
  - ``ReplanConfig`` defaults are runtime-no-op safe
    (``enable_replan=False``) and validator rejects bad values.
  - ``ExpectedOutcomeRef`` rejects negative costs and empty
    ``estimator_id``.
  - ``ReplanAttemptRecord`` rejects unknown action / status literals
    (closed-set enforcement via pydantic).
  - All three new schemas set ``extra='forbid'`` — no silent extra-
    field creep.

No runtime behavior is exercised; the point is to freeze the shape.
"""

from __future__ import annotations

import os
import sys
import typing

import pytest
from pydantic import ValidationError


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from replan import (  # noqa: E402
    EXPECTED_COST_RANGE_SOURCE_LITERAL,
    KNOWN_TRIGGER_RULE_IDS,
    MAX_REPLAN_ATTEMPTS,
    REPLAN_SCHEMA_VERSION,
    ExpectedOutcomeRef,
    ReplanAttemptRecord,
    ReplanConfig,
    ReplanTriggerRecord,
    ReplanTriggerType,
)


# ---------------------------------------------------------------------------
# Closed-set literals
# ---------------------------------------------------------------------------


def test_expected_cost_range_source_is_closed_single_value():
    args = typing.get_args(EXPECTED_COST_RANGE_SOURCE_LITERAL)
    assert args == ("cost_output_derived_overlay",), (
        "D1 provenance must be a closed single-value Literal, got "
        f"{args!r}"
    )


def test_replan_trigger_type_closed_set():
    args = set(typing.get_args(ReplanTriggerType))
    assert args == {
        "NO_TRIGGER",
        "COST_DEVIATION",
        "SLA_DEVIATION",
        "EXECUTION_FAILED",
        "PREFLIGHT_FAILED",
    }


def test_known_trigger_rule_ids_non_empty_strings():
    assert isinstance(KNOWN_TRIGGER_RULE_IDS, frozenset)
    assert KNOWN_TRIGGER_RULE_IDS, "registry must not be empty"
    for rid in KNOWN_TRIGGER_RULE_IDS:
        assert isinstance(rid, str) and rid.strip(), rid


# ---------------------------------------------------------------------------
# Config invariants
# ---------------------------------------------------------------------------


def test_max_replan_attempts_hard_cap_is_one():
    assert MAX_REPLAN_ATTEMPTS == 1


def test_replan_config_defaults_are_runtime_no_op():
    cfg = ReplanConfig()
    assert cfg.enable_replan is False
    assert cfg.max_replan_attempts == MAX_REPLAN_ATTEMPTS
    assert 0.0 <= cfg.cost_deviation_rel_threshold <= 1.0
    assert cfg.cost_deviation_abs_threshold >= 0.0
    assert cfg.sla_deviation_enabled is True
    assert cfg.expected_cost_range_source == "cost_output_derived_overlay"


@pytest.mark.parametrize(
    "kwargs,exc",
    [
        ({"max_replan_attempts": 2}, ValueError),
        ({"max_replan_attempts": -1}, ValueError),
        ({"max_replan_attempts": "1"}, TypeError),
        ({"cost_deviation_abs_threshold": -1.0}, ValueError),
        ({"cost_deviation_rel_threshold": 1.5}, ValueError),
        ({"cost_deviation_rel_threshold": -0.1}, ValueError),
        ({"sla_deviation_enabled": "yes"}, TypeError),
    ],
)
def test_replan_config_validator_rejects_bad_values(kwargs, exc):
    with pytest.raises(exc):
        ReplanConfig(**kwargs)


# ---------------------------------------------------------------------------
# ExpectedOutcomeRef
# ---------------------------------------------------------------------------


def test_expected_outcome_ref_rejects_negative_cost_min():
    with pytest.raises(ValidationError):
        ExpectedOutcomeRef(
            expected_cost_min=-1.0,
            expected_cost_max=10.0,
            expected_sla_preserved=True,
            estimator_id="EST-1",
        )


def test_expected_outcome_ref_rejects_empty_estimator_id():
    with pytest.raises(ValidationError):
        ExpectedOutcomeRef(
            expected_cost_min=0.0,
            expected_cost_max=10.0,
            expected_sla_preserved=True,
            estimator_id="   ",
        )


def test_expected_outcome_ref_forbids_extra_fields():
    with pytest.raises(ValidationError):
        ExpectedOutcomeRef(
            expected_cost_min=0.0,
            expected_cost_max=10.0,
            expected_sla_preserved=True,
            estimator_id="EST-1",
            extra_field="nope",
        )


def test_expected_outcome_ref_default_range_source_is_closed():
    obj = ExpectedOutcomeRef(
        expected_cost_min=0.0,
        expected_cost_max=10.0,
        expected_sla_preserved=True,
        estimator_id="EST-1",
    )
    assert obj.range_source == "cost_output_derived_overlay"
    with pytest.raises(ValidationError):
        ExpectedOutcomeRef(
            expected_cost_min=0.0,
            expected_cost_max=10.0,
            expected_sla_preserved=True,
            estimator_id="EST-1",
            range_source="natural_language_governance",
        )


# ---------------------------------------------------------------------------
# ReplanTriggerRecord / ReplanAttemptRecord literal closure
# ---------------------------------------------------------------------------


def test_replan_trigger_record_rejects_unknown_type():
    with pytest.raises(ValidationError):
        ReplanTriggerRecord(
            trigger_rule_id="no_trigger_v1",
            trigger_type="COST_EXPLOSION",  # not in closed set
            attempt_index=0,
        )


def test_replan_trigger_record_rejects_empty_rule_id():
    with pytest.raises(ValidationError):
        ReplanTriggerRecord(
            trigger_rule_id="",
            trigger_type="NO_TRIGGER",
            attempt_index=0,
        )


def _make_trigger() -> ReplanTriggerRecord:
    return ReplanTriggerRecord(
        trigger_rule_id="no_trigger_v1",
        trigger_type="NO_TRIGGER",
        attempt_index=0,
    )


def test_replan_attempt_record_rejects_unknown_route():
    with pytest.raises(ValidationError):
        ReplanAttemptRecord(
            attempt_index=0,
            attempt_final_route="SKIP",  # not in closed set
            attempt_execution_status="executed",
            trigger=_make_trigger(),
        )


def test_replan_attempt_record_rejects_unknown_action():
    with pytest.raises(ValidationError):
        ReplanAttemptRecord(
            attempt_index=0,
            attempt_final_route="AUTO_EXECUTE",
            attempt_action_taken="CANCEL",  # not in closed set
            attempt_execution_status="executed",
            trigger=_make_trigger(),
        )


def test_replan_attempt_record_rejects_unknown_status():
    with pytest.raises(ValidationError):
        ReplanAttemptRecord(
            attempt_index=0,
            attempt_final_route="AUTO_EXECUTE",
            attempt_execution_status="half_executed",  # not in closed set
            trigger=_make_trigger(),
        )


def test_replan_attempt_record_forbids_extra_fields():
    with pytest.raises(ValidationError):
        ReplanAttemptRecord(
            attempt_index=0,
            attempt_final_route="AUTO_EXECUTE",
            attempt_execution_status="executed",
            trigger=_make_trigger(),
            mystery_field=1,
        )


# ---------------------------------------------------------------------------
# Version pin
# ---------------------------------------------------------------------------


def test_replan_schema_version_pin():
    assert REPLAN_SCHEMA_VERSION == "1.0"
