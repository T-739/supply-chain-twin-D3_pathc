"""Phase 2: execute_action require_metadata=True contract tests.

  - require_metadata=True + metadata absent          -> GovernanceActionParseError
  - require_metadata=True + valid metadata           -> success
  - require_metadata=False + metadata absent +
    valid text prefix                                -> Path B text fallback still works
    (Path B backward-compat regression)
"""

from __future__ import annotations

import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from event_loop import load_baseline_twin_state
from execution_adapters import (
    GovernanceActionParseError,
    _parse_operational_type,
    execute_action,
)


_GOV_OUTPUT_WITH_TEXT_PREFIX = {
    "risk_level": "LOW",
    "recommended_action": "NO_ACTION: accept current penalty",
}

_META_VALID = {
    "recommended_candidate_type": "NO_ACTION",
    "recommended_candidate_id": "NO_ACTION",
}


class TestParser:
    def test_require_metadata_true_missing_meta_raises(self):
        with pytest.raises(GovernanceActionParseError):
            _parse_operational_type(
                _GOV_OUTPUT_WITH_TEXT_PREFIX,
                governance_meta=None,
                require_metadata=True,
            )

    def test_require_metadata_true_empty_meta_raises(self):
        with pytest.raises(GovernanceActionParseError):
            _parse_operational_type(
                _GOV_OUTPUT_WITH_TEXT_PREFIX,
                governance_meta={"recommended_candidate_type": ""},
                require_metadata=True,
            )

    def test_require_metadata_true_valid_meta_returns_metadata(self):
        t, src = _parse_operational_type(
            _GOV_OUTPUT_WITH_TEXT_PREFIX,
            governance_meta=_META_VALID,
            require_metadata=True,
        )
        assert t == "NO_ACTION"
        assert src == "metadata"

    def test_require_metadata_false_text_fallback_still_works(self):
        """Path B backward-compat regression."""
        t, src = _parse_operational_type(
            _GOV_OUTPUT_WITH_TEXT_PREFIX,
            governance_meta=None,
            require_metadata=False,
        )
        assert t == "NO_ACTION"
        assert src == "text_fallback"


class TestExecuteAction:
    def test_require_metadata_true_success(self):
        state = load_baseline_twin_state()
        new_state, outcome = execute_action(
            _GOV_OUTPUT_WITH_TEXT_PREFIX,
            state,
            event_id="EVT-TEST-1",
            governance_meta=_META_VALID,
            require_metadata=True,
        )
        assert outcome.action_taken == "NO_ACTION"

    def test_require_metadata_true_without_meta_fails(self):
        state = load_baseline_twin_state()
        with pytest.raises(GovernanceActionParseError):
            execute_action(
                _GOV_OUTPUT_WITH_TEXT_PREFIX,
                state,
                event_id="EVT-TEST-2",
                governance_meta=None,
                require_metadata=True,
            )

    def test_require_metadata_false_text_fallback_executes(self):
        state = load_baseline_twin_state()
        new_state, outcome = execute_action(
            _GOV_OUTPUT_WITH_TEXT_PREFIX,
            state,
            event_id="EVT-TEST-3",
            governance_meta=None,
            require_metadata=False,
        )
        assert outcome.action_taken == "NO_ACTION"
        assert "parse=text_fallback" in outcome.notes
