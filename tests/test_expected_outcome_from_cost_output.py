"""B1 Slice 2: estimator pure-function tests.

Covers ``src/replan/expected_outcome.py::estimate_expected_outcome``.
The estimator is pure and deterministic: these tests exercise:

  - the structural matching rule (recommended_candidate_id in
    governance_meta vs candidate_id in cost_output.cost_estimates);
  - fail-closed behavior on each of: missing id, zero matches,
    multiple matches, infeasible candidate, missing
    total_cost_estimate, missing recovery_cost_estimate;
  - the closed-range projection formula driven by ReplanConfig;
  - the SLA-preserved proxy rule (recovery_cost == 0.0);
  - deterministic ``estimator_signature`` across repeated calls;
  - no input mutation.
"""

from __future__ import annotations

import copy
import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from replan import (  # noqa: E402
    ESTIMATOR_ID,
    ExpectedOutcomeRef,
    ReplanConfig,
    estimate_expected_outcome,
)


# ---------------------------------------------------------------------------
# Fixture builders — CostOutput-shaped dicts matching CostOutput.to_dict()
# ---------------------------------------------------------------------------


def _cost_estimate(
    candidate_id: str,
    candidate_type: str,
    *,
    is_feasible: bool = True,
    direct: float | None = 100.0,
    recovery: float | None = 0.0,
    total: float | None = 100.0,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "is_feasible": is_feasible,
        "direct_cost_estimate": direct,
        "recovery_cost_estimate": recovery,
        "total_cost_estimate": total,
        "cost_breakdown_explanation": "",
        "estimation_notes": "",
    }


def _cost_output(estimates: list[dict]) -> dict:
    return {
        "cost_estimates": estimates,
        "order_units_used": 10,
        "planned_eta_used": 36.0,
        "cost_policy_used": {},
    }


def _gov_meta(cand_id: str | None, cand_type: str = "EXPEDITE") -> dict:
    return {
        "recommended_candidate_id": cand_id,
        "recommended_candidate_type": cand_type,
        "alternatives": [],
        "mode": "rules",
        "llm_enriched_fields": [],
        "llm_trace": None,
    }


# ---------------------------------------------------------------------------
# Happy-path: deterministic extraction for the recommended candidate
# ---------------------------------------------------------------------------


def test_happy_path_projects_closed_range_from_point_estimate():
    co = _cost_output([
        _cost_estimate("C1", "EXPEDITE", total=200.0, recovery=0.0),
        _cost_estimate("C2", "TRANSFER", total=160.0, recovery=12.0),
    ])
    gm = _gov_meta("C1", "EXPEDITE")
    cfg = ReplanConfig(
        expected_cost_band_abs=25.0,
        expected_cost_band_rel=0.1,
    )

    ref = estimate_expected_outcome(
        cost_output=co, governance_meta=gm, config=cfg,
    )

    assert isinstance(ref, ExpectedOutcomeRef)
    # band = max(25.0, 200*0.1) = max(25, 20) = 25.0
    assert ref.expected_cost_min == pytest.approx(175.0)
    assert ref.expected_cost_max == pytest.approx(225.0)
    assert ref.expected_sla_preserved is True
    assert ref.range_source == "cost_output_derived_overlay"
    assert ref.estimator_id == ESTIMATOR_ID
    assert isinstance(ref.estimator_signature, str) and len(ref.estimator_signature) == 64


def test_relative_band_dominates_when_large_point():
    co = _cost_output([_cost_estimate("C1", "EXPEDITE", total=1000.0, recovery=0.0)])
    gm = _gov_meta("C1")
    cfg = ReplanConfig(expected_cost_band_abs=25.0, expected_cost_band_rel=0.1)
    ref = estimate_expected_outcome(cost_output=co, governance_meta=gm, config=cfg)
    # band = max(25, 1000*0.1) = 100
    assert ref.expected_cost_min == pytest.approx(900.0)
    assert ref.expected_cost_max == pytest.approx(1100.0)


def test_range_min_is_clamped_to_zero():
    co = _cost_output([_cost_estimate("C1", "EXPEDITE", total=10.0, recovery=0.0)])
    gm = _gov_meta("C1")
    cfg = ReplanConfig(expected_cost_band_abs=25.0, expected_cost_band_rel=0.1)
    ref = estimate_expected_outcome(cost_output=co, governance_meta=gm, config=cfg)
    # band = max(25, 10*0.1) = 25; min = max(0, 10-25) = 0
    assert ref.expected_cost_min == 0.0
    assert ref.expected_cost_max == pytest.approx(35.0)


def test_sla_expected_false_when_recovery_positive():
    co = _cost_output([_cost_estimate("C1", "EXPEDITE", total=200.0, recovery=15.0)])
    gm = _gov_meta("C1")
    ref = estimate_expected_outcome(
        cost_output=co, governance_meta=gm, config=ReplanConfig(),
    )
    assert ref.expected_sla_preserved is False


def test_sla_expected_true_when_recovery_zero():
    co = _cost_output([_cost_estimate("C1", "EXPEDITE", total=200.0, recovery=0.0)])
    gm = _gov_meta("C1")
    ref = estimate_expected_outcome(
        cost_output=co, governance_meta=gm, config=ReplanConfig(),
    )
    assert ref.expected_sla_preserved is True


# ---------------------------------------------------------------------------
# Fail-closed behavior
# ---------------------------------------------------------------------------


def test_fail_closed_on_missing_recommended_candidate_id():
    co = _cost_output([_cost_estimate("C1", "EXPEDITE")])
    with pytest.raises(ValueError, match="recommended_candidate_id"):
        estimate_expected_outcome(
            cost_output=co, governance_meta=_gov_meta(None), config=ReplanConfig(),
        )


def test_fail_closed_on_empty_recommended_candidate_id():
    co = _cost_output([_cost_estimate("C1", "EXPEDITE")])
    with pytest.raises(ValueError, match="recommended_candidate_id"):
        estimate_expected_outcome(
            cost_output=co, governance_meta=_gov_meta("   "), config=ReplanConfig(),
        )


def test_fail_closed_on_zero_candidate_match():
    co = _cost_output([_cost_estimate("C1", "EXPEDITE")])
    gm = _gov_meta("C_UNKNOWN")
    with pytest.raises(ValueError, match="no cost_estimate found"):
        estimate_expected_outcome(
            cost_output=co, governance_meta=gm, config=ReplanConfig(),
        )


def test_fail_closed_on_multiple_candidate_matches():
    # Degenerate data: two entries sharing the same candidate_id.
    co = _cost_output([
        _cost_estimate("C1", "EXPEDITE"),
        _cost_estimate("C1", "TRANSFER"),
    ])
    with pytest.raises(ValueError, match="multiple cost_estimates"):
        estimate_expected_outcome(
            cost_output=co, governance_meta=_gov_meta("C1"), config=ReplanConfig(),
        )


def test_fail_closed_on_infeasible_recommended():
    co = _cost_output([
        _cost_estimate(
            "C1", "EXPEDITE",
            is_feasible=False, direct=None, recovery=None, total=None,
        ),
    ])
    with pytest.raises(ValueError, match="not feasible"):
        estimate_expected_outcome(
            cost_output=co, governance_meta=_gov_meta("C1"), config=ReplanConfig(),
        )


def test_fail_closed_on_missing_total_cost_estimate():
    co = _cost_output([
        _cost_estimate("C1", "EXPEDITE", total=None, recovery=5.0, direct=50.0),
    ])
    with pytest.raises(ValueError, match="no numeric total_cost_estimate"):
        estimate_expected_outcome(
            cost_output=co, governance_meta=_gov_meta("C1"), config=ReplanConfig(),
        )


def test_fail_closed_on_missing_recovery_cost_estimate():
    co = _cost_output([
        _cost_estimate("C1", "EXPEDITE", total=100.0, recovery=None, direct=100.0),
    ])
    with pytest.raises(ValueError, match="no numeric recovery_cost_estimate"):
        estimate_expected_outcome(
            cost_output=co, governance_meta=_gov_meta("C1"), config=ReplanConfig(),
        )


def test_fail_closed_on_empty_cost_estimates():
    co = _cost_output([])
    with pytest.raises(ValueError, match="cost_estimates"):
        estimate_expected_outcome(
            cost_output=co, governance_meta=_gov_meta("C1"), config=ReplanConfig(),
        )


def test_fail_closed_on_non_dict_cost_output():
    with pytest.raises(ValueError, match="cost_output"):
        estimate_expected_outcome(
            cost_output=[],  # type: ignore[arg-type]
            governance_meta=_gov_meta("C1"),
            config=ReplanConfig(),
        )


# ---------------------------------------------------------------------------
# Provenance stability + input non-mutation
# ---------------------------------------------------------------------------


def test_estimator_signature_is_stable_across_calls():
    co = _cost_output([_cost_estimate("C1", "EXPEDITE", total=200.0, recovery=0.0)])
    gm = _gov_meta("C1")
    cfg = ReplanConfig()
    r1 = estimate_expected_outcome(cost_output=co, governance_meta=gm, config=cfg)
    r2 = estimate_expected_outcome(cost_output=co, governance_meta=gm, config=cfg)
    assert r1.estimator_signature == r2.estimator_signature
    assert r1.model_dump() == r2.model_dump()


def test_estimator_signature_changes_with_band_config():
    co = _cost_output([_cost_estimate("C1", "EXPEDITE", total=200.0, recovery=0.0)])
    gm = _gov_meta("C1")
    cfg_a = ReplanConfig(expected_cost_band_abs=25.0, expected_cost_band_rel=0.1)
    cfg_b = ReplanConfig(expected_cost_band_abs=50.0, expected_cost_band_rel=0.1)
    r_a = estimate_expected_outcome(cost_output=co, governance_meta=gm, config=cfg_a)
    r_b = estimate_expected_outcome(cost_output=co, governance_meta=gm, config=cfg_b)
    assert r_a.estimator_signature != r_b.estimator_signature


def test_estimator_does_not_mutate_inputs():
    co = _cost_output([_cost_estimate("C1", "EXPEDITE", total=200.0, recovery=0.0)])
    gm = _gov_meta("C1")
    co_before = copy.deepcopy(co)
    gm_before = copy.deepcopy(gm)
    estimate_expected_outcome(cost_output=co, governance_meta=gm, config=ReplanConfig())
    assert co == co_before
    assert gm == gm_before
