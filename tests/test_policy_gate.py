"""
tests/test_policy_gate.py — D3-Demo Phase 1 policy gate tests.

Covers:
  - Deterministic routing: LOW → AUTO, MEDIUM → HUMAN, HIGH → HUMAN
  - Fail-closed: missing/unknown risk_level → HUMAN_REQUIRED
  - Config validation: overlap rejected, incomplete coverage rejected
  - Graph integration smoke: auto path bypasses supervisor, evaluation runs
"""

import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Path setup — same pattern as existing tests
# ---------------------------------------------------------------------------
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from pydantic import ValidationError

from policy_gate import (
    PolicyDecision,
    PolicyGateConfig,
    PolicyRoute,
    RiskLevel,
    decide_policy,
)


# ===========================================================================
# Unit tests: decide_policy routing
# ===========================================================================


class TestDecidePolicyRouting:
    """Core routing logic — deterministic, based on risk_level only."""

    def test_low_auto_execute(self):
        result = decide_policy({"risk_level": "LOW"})
        assert result.route == PolicyRoute.AUTO_EXECUTE
        assert result.risk_level == RiskLevel.LOW
        assert result.requires_human_review is False

    def test_medium_human_required(self):
        result = decide_policy({"risk_level": "MEDIUM"})
        assert result.route == PolicyRoute.HUMAN_REQUIRED
        assert result.risk_level == RiskLevel.MEDIUM
        assert result.requires_human_review is True

    def test_high_human_required(self):
        result = decide_policy({"risk_level": "HIGH"})
        assert result.route == PolicyRoute.HUMAN_REQUIRED
        assert result.risk_level == RiskLevel.HIGH
        assert result.requires_human_review is True

    def test_missing_risk_level_fail_closed(self):
        """Missing risk_level → fail-closed → HUMAN_REQUIRED."""
        result = decide_policy({})
        assert result.route == PolicyRoute.HUMAN_REQUIRED
        assert result.requires_human_review is True
        assert "missing" in result.reason.lower() or "unrecognized" in result.reason.lower()

    def test_unknown_risk_level_fail_closed(self):
        """Unknown value → fail-closed → HUMAN_REQUIRED."""
        result = decide_policy({"risk_level": "EXTREME"})
        assert result.route == PolicyRoute.HUMAN_REQUIRED
        assert result.requires_human_review is True

    def test_none_risk_level_fail_closed(self):
        """Explicit None → fail-closed → HUMAN_REQUIRED."""
        result = decide_policy({"risk_level": None})
        assert result.route == PolicyRoute.HUMAN_REQUIRED
        assert result.requires_human_review is True

    def test_empty_string_risk_level_fail_closed(self):
        """Empty string → fail-closed → HUMAN_REQUIRED."""
        result = decide_policy({"risk_level": ""})
        assert result.route == PolicyRoute.HUMAN_REQUIRED
        assert result.requires_human_review is True

    def test_case_insensitive(self):
        """risk_level should be case-insensitive."""
        result = decide_policy({"risk_level": "low"})
        assert result.route == PolicyRoute.AUTO_EXECUTE

    def test_whitespace_trimmed(self):
        result = decide_policy({"risk_level": "  LOW  "})
        assert result.route == PolicyRoute.AUTO_EXECUTE


class TestDecidePolicyOutput:
    """Verify output contract completeness."""

    def test_output_has_all_fields(self):
        result = decide_policy({"risk_level": "HIGH"})
        assert isinstance(result, PolicyDecision)
        assert result.route is not None
        assert result.risk_level is not None
        assert isinstance(result.requires_human_review, bool)
        assert result.reason  # non-empty
        assert result.policy_config_version  # non-empty

    def test_config_version_propagated(self):
        cfg = PolicyGateConfig(version="test-v1")
        result = decide_policy({"risk_level": "LOW"}, cfg)
        assert result.policy_config_version == "test-v1"


class TestDecidePolicyCustomConfig:
    """Custom config — e.g., all auto-execute, or all human-required."""

    def test_all_auto(self):
        cfg = PolicyGateConfig(
            auto_execute_levels=frozenset({RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}),
            human_required_levels=frozenset(),
        )
        assert decide_policy({"risk_level": "HIGH"}, cfg).route == PolicyRoute.AUTO_EXECUTE

    def test_all_human(self):
        cfg = PolicyGateConfig(
            auto_execute_levels=frozenset(),
            human_required_levels=frozenset({RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}),
        )
        assert decide_policy({"risk_level": "LOW"}, cfg).route == PolicyRoute.HUMAN_REQUIRED


# ===========================================================================
# Config validation tests
# ===========================================================================


class TestPolicyGateConfigValidation:
    """Config self-consistency validators."""

    def test_default_config_valid(self):
        cfg = PolicyGateConfig()
        assert RiskLevel.LOW in cfg.auto_execute_levels
        assert RiskLevel.MEDIUM in cfg.human_required_levels
        assert RiskLevel.HIGH in cfg.human_required_levels

    def test_overlap_rejected(self):
        with pytest.raises(ValidationError, match="disjoint"):
            PolicyGateConfig(
                auto_execute_levels=frozenset({RiskLevel.LOW, RiskLevel.MEDIUM}),
                human_required_levels=frozenset({RiskLevel.MEDIUM, RiskLevel.HIGH}),
            )

    def test_incomplete_coverage_rejected(self):
        with pytest.raises(ValidationError, match="missing"):
            PolicyGateConfig(
                auto_execute_levels=frozenset({RiskLevel.LOW}),
                human_required_levels=frozenset({RiskLevel.HIGH}),
            )


# ===========================================================================
# Graph integration smoke test
# ===========================================================================


class TestGraphIntegrationSmoke:
    """Smoke test: policy gate wired into the LangGraph graph."""

    @pytest.fixture(autouse=True)
    def _setup_paths(self):
        """Ensure src is on path and RAG store is built."""
        from rag_setup import build_vector_store, is_store_built
        if not is_store_built():
            build_vector_store()

    def test_low_risk_auto_path(self):
        """LOW risk case → auto path → supervisor bypassed → evaluation runs."""
        from graph import compile_graph

        graph = compile_graph()
        result = graph.invoke({
            "case_id": "M01",  # LOW risk case
            "supervisor_instruction": {"mode": "approve"},
            "policy_gate_enabled": True,
        })

        # Policy gate ran and routed to AUTO_EXECUTE
        pd = result.get("policy_decision", {})
        assert pd.get("route") == "AUTO_EXECUTE", f"Expected AUTO_EXECUTE, got {pd}"

        # Auto-approve shim wrote supervisor_output
        sup = result.get("supervisor_output", {})
        assert sup.get("supervisor_decision_type") == "APPROVE"
        assert "Auto-approved" in sup.get("decision_rationale", "")

        # Evaluation still ran
        ev = result.get("evaluation_result", {})
        assert ev.get("status") == "ok", f"Evaluation status: {ev}"

        # Trace log contains policy_gate and auto_approve_shim (not supervisor)
        trace_nodes = [e.get("node") for e in result.get("trace_log", [])]
        assert "policy_gate" in trace_nodes
        assert "auto_approve_shim" in trace_nodes

    def test_high_risk_human_path(self):
        """HIGH risk case → human path → supervisor invoked → evaluation runs."""
        from graph import compile_graph

        graph = compile_graph()
        result = graph.invoke({
            "case_id": "M05",  # HIGH risk case
            "supervisor_instruction": {"mode": "approve"},
            "policy_gate_enabled": True,
        })

        pd = result.get("policy_decision", {})
        assert pd.get("route") == "HUMAN_REQUIRED", f"Expected HUMAN_REQUIRED, got {pd}"

        # Supervisor was actually invoked
        trace_nodes = [e.get("node") for e in result.get("trace_log", [])]
        assert "supervisor" in trace_nodes
        assert "auto_approve_shim" not in trace_nodes

        # Evaluation still ran
        ev = result.get("evaluation_result", {})
        assert ev.get("status") == "ok", f"Evaluation status: {ev}"
