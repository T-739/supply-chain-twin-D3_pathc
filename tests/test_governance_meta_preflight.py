"""Phase 2: governance-metadata preflight tests."""

from __future__ import annotations

import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from adaptive.preflight import (
    GovernanceMetaPreflightError,
    OPERATIONAL_LITERALS,
    validate_governance_meta,
)


def _valid_meta(**over):
    base = {
        "recommended_candidate_type": "EXPEDITE",
        "recommended_candidate_id": "EXPEDITE_CR_2",
        "alternatives": [],
    }
    base.update(over)
    return base


def test_valid_meta_passes():
    validate_governance_meta(_valid_meta())


@pytest.mark.parametrize("t", list(OPERATIONAL_LITERALS))
def test_every_operational_literal_passes(t):
    validate_governance_meta(_valid_meta(recommended_candidate_type=t))


def test_lowercase_operational_literal_passes():
    validate_governance_meta(_valid_meta(recommended_candidate_type="expedite"))


def test_missing_recommended_candidate_type_fails():
    with pytest.raises(GovernanceMetaPreflightError):
        validate_governance_meta({"recommended_candidate_id": "X"})


def test_empty_recommended_candidate_type_fails():
    with pytest.raises(GovernanceMetaPreflightError):
        validate_governance_meta(_valid_meta(recommended_candidate_type=""))


def test_non_string_recommended_candidate_type_fails():
    with pytest.raises(GovernanceMetaPreflightError):
        validate_governance_meta(_valid_meta(recommended_candidate_type=123))


@pytest.mark.parametrize("token", ["APPROVE", "VERIFY", "OVERRIDE"])
def test_supervision_layer_token_fails(token):
    with pytest.raises(GovernanceMetaPreflightError):
        validate_governance_meta(_valid_meta(recommended_candidate_type=token))


@pytest.mark.parametrize("token", ["AI", "ALT1", "ALT2"])
def test_evaluation_layer_token_fails(token):
    with pytest.raises(GovernanceMetaPreflightError):
        validate_governance_meta(_valid_meta(recommended_candidate_type=token))


def test_unknown_operational_token_fails():
    with pytest.raises(GovernanceMetaPreflightError):
        validate_governance_meta(_valid_meta(recommended_candidate_type="PIVOT"))


def test_missing_recommended_candidate_id_fails():
    with pytest.raises(GovernanceMetaPreflightError):
        validate_governance_meta({"recommended_candidate_type": "EXPEDITE"})


def test_empty_recommended_candidate_id_fails():
    with pytest.raises(GovernanceMetaPreflightError):
        validate_governance_meta(_valid_meta(recommended_candidate_id=""))


def test_non_dict_fails():
    with pytest.raises(GovernanceMetaPreflightError):
        validate_governance_meta("EXPEDITE:CR_2")
