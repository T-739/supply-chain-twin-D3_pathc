"""Tests for src/action_code_mapper.py (Phase 1 hardened evaluation bridge)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from action_code_mapper import (
    ActionCodeMappingError,
    find_override_target_label,
    map_supervisor_to_action_code,
)


def _case_fixture() -> dict:
    """Case skeleton mirroring real case JSON structure (M01)."""
    return {
        "case_id": "T01",
        "agent_recommendation_action_code": "AI",
        "oracle": {"action_code": "AI", "cost_total": 100},
        "decision_options": [
            {"action_code": "AI", "decision_type": "approve",
             "action_label": "Pack from current pick face"},
            {"action_code": "ALT1", "decision_type": "verify_pause",
             "action_label": "Pause to review latest inbound/outbound scans"},
            {"action_code": "ALT2", "decision_type": "alternative_plan",
             "action_label": "Pick from reserve location instead"},
        ],
    }


# -------------------------------------------------------------------------
# APPROVE / VERIFY
# -------------------------------------------------------------------------

def test_approve_maps_to_ai():
    case = _case_fixture()
    assert map_supervisor_to_action_code(
        {"supervisor_decision_type": "APPROVE"}, case) == "AI"


def test_verify_maps_to_alt1():
    case = _case_fixture()
    assert map_supervisor_to_action_code(
        {"supervisor_decision_type": "VERIFY"}, case) == "ALT1"


def test_verify_without_verify_option_raises():
    case = _case_fixture()
    case["decision_options"] = [
        o for o in case["decision_options"] if o["decision_type"] != "verify_pause"
    ]
    with pytest.raises(ActionCodeMappingError):
        map_supervisor_to_action_code(
            {"supervisor_decision_type": "VERIFY"}, case)


# -------------------------------------------------------------------------
# OVERRIDE — strict, exact, fail-loud
# -------------------------------------------------------------------------

def test_override_with_exact_label_maps_to_alt2():
    case = _case_fixture()
    sup = {
        "supervisor_decision_type": "OVERRIDE",
        "_override_target_label": "Pick from reserve location instead",
    }
    assert map_supervisor_to_action_code(sup, case) == "ALT2"


def test_override_is_case_insensitive_exact():
    case = _case_fixture()
    sup = {
        "supervisor_decision_type": "OVERRIDE",
        "_override_target_label": "  PICK FROM RESERVE LOCATION INSTEAD  ",
    }
    assert map_supervisor_to_action_code(sup, case) == "ALT2"


def test_override_without_target_label_raises():
    """A real-override code path must never silently succeed without a label."""
    case = _case_fixture()
    with pytest.raises(ActionCodeMappingError, match="requires an explicit"):
        map_supervisor_to_action_code(
            {"supervisor_decision_type": "OVERRIDE"}, case)


def test_override_with_empty_string_label_raises():
    case = _case_fixture()
    with pytest.raises(ActionCodeMappingError):
        map_supervisor_to_action_code(
            {"supervisor_decision_type": "OVERRIDE",
             "_override_target_label": "   "},
            case,
        )


def test_override_substring_match_is_rejected():
    """Substring/partial matching is disabled; only exact labels resolve."""
    case = _case_fixture()
    sup = {
        "supervisor_decision_type": "OVERRIDE",
        "_override_target_label": "reserve location",
    }
    with pytest.raises(ActionCodeMappingError, match="not found"):
        map_supervisor_to_action_code(sup, case)


def test_override_ambiguous_label_raises():
    """Two decision_options sharing an action_label → ambiguous → error."""
    case = _case_fixture()
    case["decision_options"].append({
        "action_code": "ALT1",
        "decision_type": "verify_pause",
        "action_label": "Pick from reserve location instead",  # duplicate label
    })
    sup = {
        "supervisor_decision_type": "OVERRIDE",
        "_override_target_label": "Pick from reserve location instead",
    }
    with pytest.raises(ActionCodeMappingError, match="ambiguous"):
        map_supervisor_to_action_code(sup, case)


def test_override_target_pointing_at_approve_is_rejected():
    """Exact label of the approve option must raise, not silently return AI."""
    case = _case_fixture()
    sup = {
        "supervisor_decision_type": "OVERRIDE",
        "_override_target_label": "Pack from current pick face",  # AI / approve
    }
    with pytest.raises(ActionCodeMappingError, match="approve"):
        map_supervisor_to_action_code(sup, case)


def test_override_target_with_ai_action_code_is_rejected():
    """Defense in depth: even if decision_type is mis-labeled, action_code=AI rejected."""
    case = _case_fixture()
    # Craft an option with a non-approve decision_type but action_code AI.
    case["decision_options"].append({
        "action_code": "AI",
        "decision_type": "alternative_plan",
        "action_label": "Ship AI but relabelled as alternative",
    })
    sup = {
        "supervisor_decision_type": "OVERRIDE",
        "_override_target_label": "Ship AI but relabelled as alternative",
    }
    with pytest.raises(ActionCodeMappingError):
        map_supervisor_to_action_code(sup, case)


def test_override_unknown_label_raises():
    case = _case_fixture()
    sup = {
        "supervisor_decision_type": "OVERRIDE",
        "_override_target_label": "This label does not exist in the case",
    }
    with pytest.raises(ActionCodeMappingError, match="not found"):
        map_supervisor_to_action_code(sup, case)


def test_override_on_case_missing_alternative_plan_with_verify_label_succeeds():
    """If a case has no alternative_plan, OVERRIDE with an exact verify_pause
    action_label is still a valid non-approve target and must succeed."""
    case = _case_fixture()
    case["decision_options"] = [
        o for o in case["decision_options"]
        if o["decision_type"] != "alternative_plan"
    ]
    sup = {
        "supervisor_decision_type": "OVERRIDE",
        "_override_target_label": "Pause to review latest inbound/outbound scans",
    }
    assert map_supervisor_to_action_code(sup, case) == "ALT1"


def test_override_on_case_missing_alternative_plan_without_label_raises():
    case = _case_fixture()
    case["decision_options"] = [
        o for o in case["decision_options"]
        if o["decision_type"] != "alternative_plan"
    ]
    with pytest.raises(ActionCodeMappingError):
        map_supervisor_to_action_code(
            {"supervisor_decision_type": "OVERRIDE"}, case)


# -------------------------------------------------------------------------
# Misc
# -------------------------------------------------------------------------

def test_unknown_mode_raises():
    with pytest.raises(ActionCodeMappingError):
        map_supervisor_to_action_code(
            {"supervisor_decision_type": "SOMETHING_ELSE"}, _case_fixture())


def test_missing_decision_options_raises():
    case = {"agent_recommendation_action_code": "AI", "decision_options": []}
    with pytest.raises(ActionCodeMappingError):
        map_supervisor_to_action_code(
            {"supervisor_decision_type": "APPROVE"}, case)


def test_mapper_never_emits_operational_identifier():
    case = _case_fixture()
    # APPROVE and VERIFY
    for mode in ("APPROVE", "VERIFY"):
        code = map_supervisor_to_action_code(
            {"supervisor_decision_type": mode}, case)
        assert code in {"AI", "ALT1", "ALT2"}
    # OVERRIDE with explicit label
    code = map_supervisor_to_action_code(
        {"supervisor_decision_type": "OVERRIDE",
         "_override_target_label": "Pick from reserve location instead"},
        case,
    )
    assert code in {"AI", "ALT1", "ALT2"}


def test_real_case_m01_mappings():
    case_path = Path(__file__).parent.parent / "data" / "cases" / "M01.json"
    case = json.loads(case_path.read_text())
    assert map_supervisor_to_action_code(
        {"supervisor_decision_type": "APPROVE"}, case) == "AI"
    assert map_supervisor_to_action_code(
        {"supervisor_decision_type": "VERIFY"}, case) == "ALT1"
    # OVERRIDE now requires the exact label from the case.
    alt_label = next(
        o["action_label"] for o in case["decision_options"]
        if o["decision_type"] == "alternative_plan"
    )
    assert map_supervisor_to_action_code(
        {"supervisor_decision_type": "OVERRIDE",
         "_override_target_label": alt_label},
        case,
    ) == "ALT2"


# -------------------------------------------------------------------------
# find_override_target_label helper
# -------------------------------------------------------------------------

def test_find_override_target_label_present():
    case = _case_fixture()
    assert find_override_target_label(case) == "Pick from reserve location instead"


def test_find_override_target_label_absent():
    case = _case_fixture()
    case["decision_options"] = [
        o for o in case["decision_options"]
        if o["decision_type"] != "alternative_plan"
    ]
    assert find_override_target_label(case) is None
