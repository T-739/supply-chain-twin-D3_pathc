"""Tests for the Phase 1 evaluation_node wiring in src/graph.py (hardened)."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

from graph import compile_graph


_CASES_DIR = _PROJECT_DIR / "data" / "cases"


@pytest.fixture(scope="module")
def graph_runner():
    return compile_graph()


@pytest.fixture(scope="module")
def m01_case():
    return json.loads((_CASES_DIR / "M01.json").read_text())


def _invoke(graph_runner, case_id: str, mode: str, **extra):
    instruction = {"mode": mode, **extra}
    return graph_runner.invoke({
        "case_id": case_id,
        "supervisor_instruction": instruction,
    })


def _find_non_ai_correct_case_id() -> str | None:
    """Return a case_id whose agent recommendation != oracle.action_code."""
    for p in sorted(_CASES_DIR.glob("*.json")):
        c = json.loads(p.read_text())
        if c.get("agent_recommendation_action_code") != c["oracle"]["action_code"]:
            return p.stem
    return None


# -------------------------------------------------------------------------
# Approve / Verify — AI-correct case
# -------------------------------------------------------------------------

def test_approve_produces_zero_regret_on_ai_correct_case(graph_runner, m01_case):
    result = _invoke(graph_runner, "M01", "approve")
    ev = result["evaluation_result"]
    assert ev["status"] == "ok"
    assert ev["human_action_code"] == "AI"
    assert ev["regret"] == 0.0
    assert ev["is_override"] is False
    assert ev["is_unnecessary_override"] is False
    assert ev["override_effectiveness"] == "no_override"
    assert ev["chosen_cost"] == float(m01_case["cost_ground_truth"]["AI"]["c_total"])


def test_verify_on_ai_correct_case_is_unnecessary_override(graph_runner, m01_case):
    result = _invoke(graph_runner, "M01", "verify", review_focus="Sanity check.")
    ev = result["evaluation_result"]
    assert ev["status"] == "ok"
    assert ev["human_action_code"] == "ALT1"
    assert ev["is_override"] is True
    assert ev["is_unnecessary_override"] is True
    expected_regret = (
        float(m01_case["cost_ground_truth"]["ALT1"]["c_total"])
        - float(m01_case["oracle"]["cost_total"])
    )
    assert ev["regret"] == expected_regret
    assert ev["override_effectiveness"] == "cost_increasing"


# -------------------------------------------------------------------------
# OVERRIDE — hardened contract
# -------------------------------------------------------------------------

def test_override_with_exact_label_uses_alternative_plan(graph_runner, m01_case):
    alt_label = next(
        o["action_label"] for o in m01_case["decision_options"]
        if o["decision_type"] == "alternative_plan"
    )
    result = _invoke(graph_runner, "M01", "override",
                     target_action_label=alt_label)
    ev = result["evaluation_result"]
    assert ev["status"] == "ok"
    assert ev["human_action_code"] == "ALT2"
    assert ev["is_override"] is True
    expected_regret = (
        float(m01_case["cost_ground_truth"]["ALT2"]["c_total"])
        - float(m01_case["oracle"]["cost_total"])
    )
    assert ev["regret"] == expected_regret


def test_override_without_target_label_degrades_to_error(graph_runner):
    """A real override without a target must NOT silently collapse to ALT2."""
    result = _invoke(graph_runner, "M01", "override")
    ev = result["evaluation_result"]
    assert ev["status"] == "error"
    assert "OVERRIDE" in (ev.get("reason") or "") or "target" in (ev.get("reason") or "")


def test_override_with_substring_label_degrades_to_error(graph_runner):
    """Substring matching is disabled; evaluation must surface the mis-label."""
    result = _invoke(graph_runner, "M01", "override",
                     target_action_label="reserve location")
    ev = result["evaluation_result"]
    assert ev["status"] == "error"


def test_override_targeting_approve_label_degrades_to_error(graph_runner, m01_case):
    approve_label = next(
        o["action_label"] for o in m01_case["decision_options"]
        if o["decision_type"] == "approve"
    )
    result = _invoke(graph_runner, "M01", "override",
                     target_action_label=approve_label)
    ev = result["evaluation_result"]
    assert ev["status"] == "error"


# -------------------------------------------------------------------------
# Non-AI-correct case — metrics must remain correct
# -------------------------------------------------------------------------

def test_non_ai_correct_case_approve_has_positive_regret(graph_runner):
    case_id = _find_non_ai_correct_case_id()
    if case_id is None:
        pytest.skip("No non-AI-correct case available in data/cases/")

    case = json.loads((_CASES_DIR / f"{case_id}.json").read_text())
    result = _invoke(graph_runner, case_id, "approve")
    ev = result["evaluation_result"]
    assert ev["status"] == "ok"
    # Human=AI (approve), agent=AI, so is_override is False (human matches agent).
    assert ev["is_override"] is False
    assert ev["is_unnecessary_override"] is False
    # But AI is NOT oracle; regret must be strictly positive.
    assert ev["agent_action_code"] != ev["oracle_action_code"]
    assert ev["regret"] > 0.0
    # Chosen cost equals cost_ground_truth[AI], not runtime cost.
    assert ev["chosen_cost"] == float(case["cost_ground_truth"]["AI"]["c_total"])


def test_non_ai_correct_case_override_to_oracle_has_zero_regret(graph_runner):
    """If the case's alternative_plan happens to be the oracle action, then
    an explicit OVERRIDE to that label must produce regret == 0 and a
    non-unnecessary, cost-reducing override."""
    case_id = _find_non_ai_correct_case_id()
    if case_id is None:
        pytest.skip("No non-AI-correct case available in data/cases/")
    case = json.loads((_CASES_DIR / f"{case_id}.json").read_text())
    oracle_code = case["oracle"]["action_code"]

    target_opt = next(
        (o for o in case["decision_options"]
         if o["action_code"] == oracle_code
         and o["decision_type"] not in ("approve",)),
        None,
    )
    if target_opt is None:
        pytest.skip(
            f"Case {case_id}: oracle action_code {oracle_code} is not a "
            "non-approve decision_option; cannot test override-to-oracle."
        )

    result = _invoke(graph_runner, case_id, "override",
                     target_action_label=target_opt["action_label"])
    ev = result["evaluation_result"]
    assert ev["status"] == "ok"
    assert ev["human_action_code"] == oracle_code
    assert ev["regret"] == 0.0
    assert ev["is_override"] is True
    assert ev["is_unnecessary_override"] is False
    assert ev["override_effectiveness"] == "cost_reducing"


# -------------------------------------------------------------------------
# GraphState / truth-boundary invariants
# -------------------------------------------------------------------------

def test_evaluation_never_uses_runtime_cost(graph_runner, m01_case):
    result = _invoke(graph_runner, "M01", "approve")
    ev = result["evaluation_result"]
    gt = float(m01_case["cost_ground_truth"][ev["human_action_code"]]["c_total"])
    assert ev["chosen_cost"] == gt


def test_graph_state_keys_unchanged(graph_runner):
    result = _invoke(graph_runner, "M01", "approve")
    for key in (
        "scenario_context", "twin_state", "operations_output", "cost_output",
        "governance_output", "supervisor_output", "trace_log", "evaluation_result",
    ):
        assert key in result, f"missing GraphState key: {key}"


# -------------------------------------------------------------------------
# Batch runner — explicit per-case override targets
# -------------------------------------------------------------------------

def test_batch_override_uses_explicit_per_case_targets(graph_runner):
    """The override batch must inject each case's own alternative_plan label
    and must NOT collapse every case to a generic ALT2-by-default."""
    from scripts_shim import batch_override_rows  # noqa: F401 (see below)

    rows = batch_override_rows(["M01", "M02", "M03"])
    assert len(rows) == 3
    for r in rows:
        if r["status"] != "ok":
            continue
        case = json.loads((_CASES_DIR / f"{r['case_id']}.json").read_text())
        alt_opt = next(
            (o for o in case["decision_options"]
             if o["decision_type"] == "alternative_plan"),
            None,
        )
        assert alt_opt is not None
        # The target label recorded in the CSV row must match the case's own
        # alternative_plan label exactly — not a placeholder.
        assert r["override_target_label"] == alt_opt["action_label"]
        # And the mapped action code must be that option's action_code.
        assert r["human_action_code"] == alt_opt["action_code"]


def test_batch_override_skips_cases_without_alternative_plan(graph_runner, tmp_path):
    """If a case has no alternative_plan option, batch must record a skip
    with a reason — never fabricate an ALT2 row."""
    from scripts_shim import batch_rows_with_fixture_cases

    # Synthetic case: only approve + verify_pause, no alternative_plan.
    fixture = {
        "case_id": "SYN1",
        "agent_recommendation_action_code": "AI",
        "oracle": {"action_code": "AI", "cost_total": 100},
        "cost_ground_truth": {
            "AI": {"c_direct": 60, "c_outcome": 40, "c_total": 100},
            "ALT1": {"c_direct": 140, "c_outcome": 80, "c_total": 220},
            "ALT2": {"c_direct": 120, "c_outcome": 120, "c_total": 240},
        },
        "decision_options": [
            {"action_code": "AI", "decision_type": "approve",
             "action_label": "Approve"},
            {"action_code": "ALT1", "decision_type": "verify_pause",
             "action_label": "Pause"},
        ],
    }
    rows = batch_rows_with_fixture_cases("override", {"SYN1": fixture}, tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == "skipped"
    assert "alternative_plan" in (r["skip_reason"] or "")
    assert r["human_action_code"] is None
