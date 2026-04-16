"""
tests/test_evaluation.py
=========================
Tests for src/evaluation.py.

All numeric truth is sourced from case JSON cost_ground_truth.
TwinState simulation is not invoked here.

Coverage:
- normalize_action_code
- get_agent_action_code
- get_total_cost / compute_total_cost
- is_override
- is_unnecessary_override
- compute_override_effectiveness
- compute_regret
- validate_split_cost
- validate_oracle_consistency
- Integration checks against real generated case files
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Allow imports from src/ without an installed package (matches repo convention)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from evaluation import (
    ActionCode,
    compute_override_effectiveness,
    compute_regret,
    compute_total_cost,
    get_agent_action_code,
    get_total_cost,
    is_override,
    is_unnecessary_override,
    normalize_action_code,
    validate_oracle_consistency,
    validate_split_cost,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = REPO_ROOT / "data" / "cases"


def _make_case(
    oracle_code: str = "AI",
    oracle_cost: int = 80,
    ai_correct: bool = True,
    agent_rec: str = "AI",
    c_dir_ai: int = 40,
    c_out_ai: int = 40,
    c_total_ai: int = 80,
    c_dir_alt1: int = 140,
    c_out_alt1: int = 60,
    c_total_alt1: int = 200,
    c_dir_alt2: int = 100,
    c_out_alt2: int = 120,
    c_total_alt2: int = 220,
) -> dict:
    """Build a minimal synthetic case dict for unit tests."""
    return {
        "case_id": "TEST",
        "ai_correct": ai_correct,
        "oracle": {"action_code": oracle_code, "cost_total": oracle_cost},
        "agent_recommendation_action_code": agent_rec,
        "cost_ground_truth": {
            "AI":   {"c_direct": c_dir_ai,   "c_outcome": c_out_ai,   "c_total": c_total_ai},
            "ALT1": {"c_direct": c_dir_alt1, "c_outcome": c_out_alt1, "c_total": c_total_alt1},
            "ALT2": {"c_direct": c_dir_alt2, "c_outcome": c_out_alt2, "c_total": c_total_alt2},
        },
    }


def _load_case(case_id: str) -> dict:
    path = CASES_DIR / f"{case_id}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# normalize_action_code
# ---------------------------------------------------------------------------

class TestNormalizeActionCode:
    @pytest.mark.parametrize("code", ["AI", "ALT1", "ALT2"])
    def test_valid_codes_pass_through(self, code):
        assert normalize_action_code(code) == code

    @pytest.mark.parametrize("code", ["ai", "alt1", "alt2", "Alt1"])
    def test_case_insensitive(self, code):
        result = normalize_action_code(code)
        assert result in {"AI", "ALT1", "ALT2"}

    @pytest.mark.parametrize("bad", ["VERIFY", "APPROVE", "OVERRIDE", "X", "", "ALT3"])
    def test_invalid_code_raises(self, bad):
        with pytest.raises(ValueError, match="Unknown action code"):
            normalize_action_code(bad)


# ---------------------------------------------------------------------------
# get_agent_action_code
# ---------------------------------------------------------------------------

class TestGetAgentActionCode:
    def test_defaults_to_ai(self):
        case = _make_case()
        del case["agent_recommendation_action_code"]
        assert get_agent_action_code(case) == "AI"

    def test_reads_explicit_override(self):
        case = _make_case(agent_rec="ALT1")
        assert get_agent_action_code(case) == "ALT1"

    def test_explicit_ai(self):
        case = _make_case(agent_rec="AI")
        assert get_agent_action_code(case) == "AI"


# ---------------------------------------------------------------------------
# get_total_cost / compute_total_cost
# ---------------------------------------------------------------------------

class TestGetTotalCost:
    def test_ai_cost(self):
        case = _make_case(c_total_ai=80)
        assert get_total_cost(case, "AI") == 80.0

    def test_alt1_cost(self):
        case = _make_case(c_total_alt1=200)
        assert get_total_cost(case, "ALT1") == 200.0

    def test_alt2_cost(self):
        case = _make_case(c_total_alt2=220)
        assert get_total_cost(case, "ALT2") == 220.0

    def test_compute_total_cost_is_alias(self):
        case = _make_case(c_total_ai=80)
        assert compute_total_cost(case, "AI") == get_total_cost(case, "AI")

    def test_returns_float(self):
        case = _make_case(c_total_ai=80)
        result = get_total_cost(case, "AI")
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# is_override
# ---------------------------------------------------------------------------

class TestIsOverride:
    def test_same_action_not_override(self):
        case = _make_case(agent_rec="AI")
        assert is_override(case, "AI") is False

    def test_different_action_is_override(self):
        case = _make_case(agent_rec="AI")
        assert is_override(case, "ALT1") is True

    def test_alt2_is_override(self):
        case = _make_case(agent_rec="AI")
        assert is_override(case, "ALT2") is True

    def test_alt1_agent_approve_same(self):
        case = _make_case(agent_rec="ALT1")
        assert is_override(case, "ALT1") is False


# ---------------------------------------------------------------------------
# is_unnecessary_override
# ---------------------------------------------------------------------------

class TestIsUnnecessaryOverride:
    # SPEC_BRIDGE.md §Tests — Case 1
    def test_unnecessary_override_when_agent_and_oracle_both_ai(self):
        """
        agent=AI, oracle=AI, human=ALT1 → unnecessary override.
        """
        case = _make_case(oracle_code="AI", agent_rec="AI")
        assert is_unnecessary_override(case, "ALT1") is True

    def test_unnecessary_override_human_alt2(self):
        case = _make_case(oracle_code="AI", agent_rec="AI")
        assert is_unnecessary_override(case, "ALT2") is True

    def test_not_unnecessary_when_human_follows_agent(self):
        case = _make_case(oracle_code="AI", agent_rec="AI")
        assert is_unnecessary_override(case, "AI") is False

    def test_not_unnecessary_when_agent_is_wrong(self):
        """
        If agent=AI but oracle=ALT2, human choosing ALT2 is a correct override
        (not unnecessary).
        """
        case = _make_case(oracle_code="ALT2", oracle_cost=220, agent_rec="AI", ai_correct=False)
        assert is_unnecessary_override(case, "ALT2") is False

    def test_not_unnecessary_when_agent_was_already_wrong_and_human_different(self):
        """
        agent=AI, oracle=ALT1, human=ALT2.
        Human != agent, but agent != oracle → not unnecessary (agent was wrong).
        """
        case = _make_case(oracle_code="ALT1", oracle_cost=200, agent_rec="AI", ai_correct=False)
        assert is_unnecessary_override(case, "ALT2") is False

    def test_p01_ai_correct_human_alt1_is_unnecessary(self):
        case = _load_case("P01")
        assert is_unnecessary_override(case, "ALT1") is True

    def test_p01_human_ai_is_not_unnecessary(self):
        case = _load_case("P01")
        assert is_unnecessary_override(case, "AI") is False


# ---------------------------------------------------------------------------
# compute_regret
# ---------------------------------------------------------------------------

class TestComputeRegret:
    # SPEC_BRIDGE.md §Tests — Case 2: regret positive
    def test_regret_positive_when_human_chooses_worse_than_oracle(self):
        """oracle=AI(80), human=ALT2(220) → regret = 220-80 = 140 > 0."""
        case = _make_case(oracle_code="AI", oracle_cost=80, c_total_alt2=220)
        regret = compute_regret(case, "ALT2")
        assert regret > 0
        assert regret == pytest.approx(140.0)

    # SPEC_BRIDGE.md §Tests — Case 3: regret zero
    def test_regret_zero_when_human_chooses_oracle(self):
        """oracle=AI(80), human=AI → regret = 0."""
        case = _make_case(oracle_code="AI", oracle_cost=80, c_total_ai=80)
        assert compute_regret(case, "AI") == pytest.approx(0.0)

    def test_regret_zero_when_human_chooses_alt1_and_oracle_is_alt1(self):
        case = _make_case(
            oracle_code="ALT1", oracle_cost=200,
            c_total_alt1=200, agent_rec="AI", ai_correct=False
        )
        assert compute_regret(case, "ALT1") == pytest.approx(0.0)

    def test_regret_alt1_above_ai_oracle(self):
        case = _make_case(oracle_code="AI", oracle_cost=80, c_total_alt1=200)
        assert compute_regret(case, "ALT1") == pytest.approx(120.0)

    def test_p01_regret_zero_for_oracle(self):
        case = _load_case("P01")
        oracle_code = case["oracle"]["action_code"]
        assert compute_regret(case, oracle_code) == pytest.approx(0.0)

    def test_p01_regret_alt1(self):
        """P01: oracle=AI(80), ALT1 cost=200 → regret=120."""
        case = _load_case("P01")
        assert compute_regret(case, "ALT1") == pytest.approx(120.0)

    def test_p01_regret_alt2(self):
        """P01: oracle=AI(80), ALT2 cost=220 → regret=140."""
        case = _load_case("P01")
        assert compute_regret(case, "ALT2") == pytest.approx(140.0)


# ---------------------------------------------------------------------------
# compute_override_effectiveness
# ---------------------------------------------------------------------------

class TestComputeOverrideEffectiveness:
    # SPEC_BRIDGE.md §Tests — Case 4: cost_reducing
    def test_cost_reducing_when_human_override_cheaper(self):
        """
        agent=ALT1(200), human=AI(80) → cost_reducing.
        """
        case = _make_case(agent_rec="ALT1", c_total_ai=80, c_total_alt1=200)
        result = compute_override_effectiveness(case, "AI")
        assert result == "cost_reducing"

    def test_no_override_when_same_action(self):
        case = _make_case(agent_rec="AI")
        assert compute_override_effectiveness(case, "AI") == "no_override"

    def test_cost_increasing_when_override_more_expensive(self):
        """agent=AI(80), human=ALT1(200) → cost_increasing."""
        case = _make_case(agent_rec="AI", c_total_ai=80, c_total_alt1=200)
        assert compute_override_effectiveness(case, "ALT1") == "cost_increasing"

    def test_neutral_when_override_same_cost(self):
        """agent=AI(100), human=ALT1(100) → neutral."""
        case = _make_case(
            agent_rec="AI",
            c_total_ai=80, c_dir_ai=40, c_out_ai=40,
            c_total_alt1=80, c_dir_alt1=20, c_out_alt1=60,
        )
        assert compute_override_effectiveness(case, "ALT1") == "neutral"

    def test_p01_human_ai_no_override(self):
        case = _load_case("P01")
        assert compute_override_effectiveness(case, "AI") == "no_override"

    def test_p01_human_alt1_cost_increasing(self):
        """P01: agent=AI(80), human=ALT1(200) → cost_increasing."""
        case = _load_case("P01")
        assert compute_override_effectiveness(case, "ALT1") == "cost_increasing"


# ---------------------------------------------------------------------------
# validate_split_cost
# ---------------------------------------------------------------------------

class TestValidateSplitCost:
    def test_valid_case_passes(self):
        case = _make_case()  # c_direct+c_outcome == c_total by construction
        validate_split_cost(case)  # should not raise

    def test_broken_total_raises(self):
        case = _make_case(c_total_ai=999)  # 40+40=80 != 999
        with pytest.raises(AssertionError, match="c_direct"):
            validate_split_cost(case)

    def test_all_real_cases_pass(self):
        for case_id in ["P01", "P02", "P03", "M01", "M13"]:
            case = _load_case(case_id)
            validate_split_cost(case)  # must not raise


# ---------------------------------------------------------------------------
# validate_oracle_consistency
# ---------------------------------------------------------------------------

class TestValidateOracleConsistency:
    def test_valid_case_passes(self):
        case = _make_case()
        validate_oracle_consistency(case)  # should not raise

    def test_mismatched_oracle_cost_raises(self):
        case = _make_case(oracle_code="AI", oracle_cost=999, c_total_ai=80)
        with pytest.raises(AssertionError, match="oracle cost_total"):
            validate_oracle_consistency(case)

    def test_ai_correct_but_oracle_not_ai_raises(self):
        case = _make_case(oracle_code="ALT1", oracle_cost=200, ai_correct=True, c_total_alt1=200)
        with pytest.raises(AssertionError, match="ai_correct"):
            validate_oracle_consistency(case)

    def test_all_real_cases_pass(self):
        for case_id in ["P01", "P02", "P03", "P04", "M13"]:
            case = _load_case(case_id)
            validate_oracle_consistency(case)  # must not raise


# ---------------------------------------------------------------------------
# Integration — ai-error cases
# ---------------------------------------------------------------------------

class TestAIErrorCases:
    """
    Cases where oracle != AI (P03, P04, M02, M03, M08, M13).
    Verify that unnecessary_override logic is correct for these cases.
    """

    @pytest.mark.parametrize("case_id", ["P03", "P04", "M02", "M03", "M08", "M13"])
    def test_ai_error_case_ai_correct_is_false(self, case_id):
        case = _load_case(case_id)
        assert case["ai_correct"] is False, f"{case_id}: expected ai_correct=False"

    @pytest.mark.parametrize("case_id", ["P03", "P04", "M02", "M03", "M08", "M13"])
    def test_ai_error_case_oracle_not_ai(self, case_id):
        case = _load_case(case_id)
        assert case["oracle"]["action_code"] != "AI", (
            f"{case_id}: expected oracle != 'AI'"
        )

    @pytest.mark.parametrize("case_id", ["P03", "P04", "M02", "M03", "M08", "M13"])
    def test_human_choosing_oracle_in_ai_error_case_is_not_unnecessary_override(self, case_id):
        """
        In AI-error cases, choosing the oracle action is NOT an unnecessary override
        (the agent was wrong, so correcting it is appropriate).
        """
        case = _load_case(case_id)
        oracle_code = case["oracle"]["action_code"]
        assert is_unnecessary_override(case, oracle_code) is False

    @pytest.mark.parametrize("case_id", ["P03", "P04", "M02", "M03", "M08", "M13"])
    def test_human_choosing_oracle_in_ai_error_case_has_zero_regret(self, case_id):
        case = _load_case(case_id)
        oracle_code = case["oracle"]["action_code"]
        assert compute_regret(case, oracle_code) == pytest.approx(0.0)
