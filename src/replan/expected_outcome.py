"""replan/expected_outcome.py — B1 Slice 2 pure estimator.

Derives an ``ExpectedOutcomeRef`` from a structured ``CostOutput`` and
the structured governance identity dict (``_governance_meta``). Pure
and deterministic: no I/O, no wall-clock, no randomness, no mutation
of its inputs.

Owner-fixed D1 (see ``docs/B1_REPLAN_CONTRACT_DRAFT.md §7``):
the expected-cost range is a ``cost_output_derived_overlay``.
Inputs are the Cost Agent's structured output and the governance
operational identity only. Natural-language governance fields
(``cost_summary``, ``confidence_note``, ``rationale_trace``,
``situational_explanation``, ``alternative_actions``) are never
read or parsed. The AST scan in
``tests/test_replan_contract_no_nl_truth.py`` enforces this at the
source level.

Structural matching rule (the D1-grounded rule used here):

    1. Read ``governance_meta["recommended_candidate_id"]``. If
       missing/empty, FAIL CLOSED.
    2. Walk ``cost_output["cost_estimates"]`` looking for a single
       entry whose ``candidate_id`` equals the recommended id.
       If zero matches or >1 matches, FAIL CLOSED.
    3. Require the matched entry to satisfy ``is_feasible == True``
       AND ``total_cost_estimate is not None`` (a feasible
       structured numeric estimate). Otherwise FAIL CLOSED.
    4. Project the point estimate into a closed range using the
       config-provided band:

           band = max(config.expected_cost_band_abs,
                      point_estimate * config.expected_cost_band_rel)
           expected_cost_min = max(0.0, point_estimate - band)
           expected_cost_max = point_estimate + band

    5. Derive the SLA expectation as a cost-output-derived proxy:

           expected_sla_preserved = (recovery_cost_estimate == 0.0)

       Rationale: the Cost Agent's ``recovery_cost_estimate`` is
       positive iff ``late_hours > 0`` AND ``sla_penalty > 0`` under
       the twin-state formulas. A zero recovery cost therefore means
       the cost model predicts no SLA recovery burden. This is a
       structural proxy, not an authoritative SLA verdict; it is
       deliberately conservative in the edge case where SLA penalty
       is zero (which would read as "preserved" but is also not a
       meaningful breach for the replan trigger).

All failure modes raise :class:`ValueError` with a message that
includes the rule name, to support targeted ``pytest.raises(...,
match=...)`` assertions.
"""

from __future__ import annotations

from typing import Any

from replan.replan_config import ReplanConfig
from replan.replan_schema import ExpectedOutcomeRef
from session.digests import canonical_json, sha256_hex


ESTIMATOR_ID: str = "replan_cost_overlay_v1"


def _select_recommended_estimate(
    cost_estimates: list[Any],
    recommended_id: str,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for entry in cost_estimates:
        if isinstance(entry, dict):
            cand_id = entry.get("candidate_id")
            if cand_id == recommended_id:
                matches.append(entry)
    if len(matches) == 0:
        raise ValueError(
            f"expected_outcome: no cost_estimate found for "
            f"recommended_candidate_id={recommended_id!r}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"expected_outcome: multiple cost_estimates matched "
            f"recommended_candidate_id={recommended_id!r}; "
            f"expected exactly one"
        )
    return matches[0]


def estimate_expected_outcome(
    *,
    cost_output: dict[str, Any],
    governance_meta: dict[str, Any],
    config: ReplanConfig,
) -> ExpectedOutcomeRef:
    """Derive an ``ExpectedOutcomeRef`` from structured inputs only.

    Pure: no I/O, no clock, no randomness, no input mutation.

    Parameters
    ----------
    cost_output
        A ``CostOutput``-shaped dict (as produced by
        ``CostOutput.to_dict()`` or ``model_dump``). Must carry a
        ``cost_estimates`` list.
    governance_meta
        The ``_governance_meta`` dict from the event_loop reasoning
        result. Must carry ``recommended_candidate_id``. Natural-
        language fields (if any accidentally present) are not read.
    config
        The replan configuration carrying the band parameters.

    Returns
    -------
    ExpectedOutcomeRef
        Structured expected-outcome with ``range_source ==
        "cost_output_derived_overlay"`` and a deterministic
        ``estimator_signature``.

    Raises
    ------
    ValueError
        If any of the structural-match invariants fail (missing id,
        zero/multiple matches, infeasible candidate, missing numeric
        estimate, missing recovery estimate).
    """
    if not isinstance(cost_output, dict):
        raise ValueError(
            "expected_outcome: cost_output must be a dict (got "
            f"{type(cost_output).__name__})"
        )
    if not isinstance(governance_meta, dict):
        raise ValueError(
            "expected_outcome: governance_meta must be a dict (got "
            f"{type(governance_meta).__name__})"
        )

    recommended_id = governance_meta.get("recommended_candidate_id")
    if not isinstance(recommended_id, str) or not recommended_id.strip():
        raise ValueError(
            "expected_outcome: governance_meta.recommended_candidate_id "
            "must be a non-empty string"
        )

    cost_estimates = cost_output.get("cost_estimates")
    if not isinstance(cost_estimates, list) or len(cost_estimates) == 0:
        raise ValueError(
            "expected_outcome: cost_output.cost_estimates must be a "
            "non-empty list"
        )

    estimate = _select_recommended_estimate(cost_estimates, recommended_id)

    is_feasible = estimate.get("is_feasible")
    if not isinstance(is_feasible, bool) or not is_feasible:
        raise ValueError(
            "expected_outcome: recommended candidate "
            f"{recommended_id!r} is not feasible "
            "(is_feasible must be True)"
        )

    point = estimate.get("total_cost_estimate")
    if point is None or not isinstance(point, (int, float)):
        raise ValueError(
            "expected_outcome: recommended candidate "
            f"{recommended_id!r} has no numeric total_cost_estimate"
        )
    point_f = float(point)
    if point_f < 0:
        raise ValueError(
            "expected_outcome: total_cost_estimate must be >= 0 for "
            f"candidate {recommended_id!r}, got {point_f}"
        )

    recovery = estimate.get("recovery_cost_estimate")
    if recovery is None or not isinstance(recovery, (int, float)):
        raise ValueError(
            "expected_outcome: recommended candidate "
            f"{recommended_id!r} has no numeric recovery_cost_estimate"
        )
    expected_sla_preserved = float(recovery) == 0.0

    band = max(
        float(config.expected_cost_band_abs),
        point_f * float(config.expected_cost_band_rel),
    )
    expected_cost_min = max(0.0, point_f - band)
    expected_cost_max = point_f + band

    candidate_type = estimate.get("candidate_type") or governance_meta.get(
        "recommended_candidate_type"
    ) or ""

    # Deterministic provenance digest over the exact inputs used.
    signature_payload = {
        "estimator_id": ESTIMATOR_ID,
        "recommended_candidate_id": recommended_id,
        "candidate_type": candidate_type,
        "point_estimate": point_f,
        "recovery_cost_estimate": float(recovery),
        "band_abs": float(config.expected_cost_band_abs),
        "band_rel": float(config.expected_cost_band_rel),
        "range_source": "cost_output_derived_overlay",
    }
    estimator_signature = sha256_hex(canonical_json(signature_payload))

    return ExpectedOutcomeRef(
        expected_cost_min=expected_cost_min,
        expected_cost_max=expected_cost_max,
        expected_sla_preserved=expected_sla_preserved,
        range_source="cost_output_derived_overlay",
        estimator_id=ESTIMATOR_ID,
        estimator_signature=estimator_signature,
    )
