"""
governance_agent.py — Governance Agent: frozen output schema + deterministic synthesis.

Schema (frozen in Package 1):
  GovernanceOutput with 8 required fields — risk_level, situational_explanation,
  recommended_action, evidence_sources, cost_summary, confidence_note,
  rationale_trace, alternative_actions.

Synthesis (added in Package 2D):
  run_governance_agent() joins Operations output (ranked candidates + evidence)
  with Cost output (deterministic estimates) and scenario context to produce
  a GovernanceOutput.

The governance output is advisory.  It does NOT overwrite evaluation truth
(which comes from case JSON / CSV oracle via src/evaluation.py).
The recommended_action refers to an operational candidate (EXPEDITE, TRANSFER,
COMPENSATE, NO_ACTION), never to AI/ALT1/ALT2 supervision decision codes.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------


class EvidenceSource(BaseModel):
    """A single piece of evidence backing the governance recommendation."""

    source_type: str          # e.g. "twin_state", "scenario", "case_data"
    field_or_key: str         # e.g. "CR_1.transit_time_hours"
    value: Any                # observed value
    relevance: str            # why this matters


class AlternativeAction(BaseModel):
    """A single alternative the governance agent considered."""

    action_label: str         # human-readable label
    description: str          # brief rationale
    estimated_risk: str       # qualitative risk note


# ---------------------------------------------------------------------------
# Frozen output contract
# ---------------------------------------------------------------------------


class GovernanceOutput(BaseModel):
    """Exact structured output contract for the Governance Agent.

    All 8 fields are required. The schema is frozen for Week 2.
    """

    risk_level: RiskLevel
    situational_explanation: str
    recommended_action: str
    evidence_sources: list[EvidenceSource]
    cost_summary: str
    confidence_note: str
    rationale_trace: str
    alternative_actions: list[AlternativeAction]

    @field_validator("risk_level", mode="before")
    @classmethod
    def normalize_risk_level(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator("evidence_sources")
    @classmethod
    def at_least_one_evidence(cls, v: list[EvidenceSource]) -> list[EvidenceSource]:
        if len(v) == 0:
            raise ValueError("evidence_sources must contain at least one entry")
        return v

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        """Serialize to a JSON string for trace logging."""
        return self.model_dump_json(indent=2)

    def to_dict(self) -> dict:
        """Serialize to a plain dict (JSON-safe via Pydantic)."""
        return self.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Factory helper for placeholder / testing
# ---------------------------------------------------------------------------


def make_placeholder_governance_output() -> GovernanceOutput:
    """Return a minimal valid GovernanceOutput for testing and stub nodes."""
    return GovernanceOutput(
        risk_level=RiskLevel.MEDIUM,
        situational_explanation="Placeholder — governance agent not yet executed.",
        recommended_action="No recommendation available.",
        evidence_sources=[
            EvidenceSource(
                source_type="placeholder",
                field_or_key="N/A",
                value=None,
                relevance="Stub data for graph skeleton testing.",
            )
        ],
        cost_summary="No cost analysis performed.",
        confidence_note="Low confidence — stub output.",
        rationale_trace="Governance agent stub; no analysis was run.",
        alternative_actions=[],
    )


# ---------------------------------------------------------------------------
# Forbidden fields — governance must never contain these
# ---------------------------------------------------------------------------

_FORBIDDEN_SUPERVISION_TOKENS: frozenset[str] = frozenset({
    "AI", "ALT1", "ALT2",
})


# ---------------------------------------------------------------------------
# Synthesis helpers
# ---------------------------------------------------------------------------


def _join_candidates_with_costs(
    ops_output: dict[str, Any],
    cost_output: dict[str, Any],
) -> list[dict[str, Any]]:
    """Join ranked candidates with cost estimates by candidate_id.

    Returns a list of merged dicts (candidate fields + cost fields).
    """
    cost_map: dict[str, dict[str, Any]] = {}
    for ce in cost_output.get("cost_estimates", []):
        cost_map[ce["candidate_id"]] = ce

    joined: list[dict[str, Any]] = []
    for rc in ops_output.get("ranked_candidates", []):
        merged = dict(rc)
        ce = cost_map.get(rc["candidate_id"], {})
        merged["direct_cost_estimate"] = ce.get("direct_cost_estimate")
        merged["recovery_cost_estimate"] = ce.get("recovery_cost_estimate")
        merged["total_cost_estimate"] = ce.get("total_cost_estimate")
        merged["cost_breakdown_explanation"] = ce.get("cost_breakdown_explanation", "")
        joined.append(merged)
    return joined


def _select_recommended(
    joined: list[dict[str, Any]],
    scenario_context: dict[str, Any],
) -> dict[str, Any]:
    """Select the recommended operational candidate.

    Selection rule (deterministic, transparent):
      1. Filter to feasible candidates only
      2. Among feasible, sort by:
         a. feasibility_score descending (operational fit first)
         b. total_cost_estimate ascending (cost as tiebreak support)
      3. Pick the top candidate

    This is NOT "pick cheapest".  Feasibility score (which encodes scenario-
    signal alignment) is the primary key; cost is secondary support.

    Falls back to the first candidate if none are feasible.
    """
    feasible = [c for c in joined if c.get("feasible", c.get("is_feasible", False))]

    if not feasible:
        # All infeasible — return first candidate with a note
        return joined[0] if joined else {}

    # Sort: primary = feasibility_score DESC, secondary = total_cost ASC
    def sort_key(c: dict) -> tuple:
        fs = c.get("feasibility_score", 0.0)
        tc = c.get("total_cost_estimate")
        # None costs sort last (infinity)
        return (-fs, tc if tc is not None else float("inf"))

    feasible.sort(key=sort_key)
    return feasible[0]


def _determine_risk_level(
    scenario_context: dict[str, Any],
    recommended: dict[str, Any],
    joined: list[dict[str, Any]],
) -> RiskLevel:
    """Determine risk_level from scenario context and candidate feasibility.

    Rules:
      - Case risk_level from scenario_context is the primary signal
      - Escalate if many candidates are infeasible
      - Do not escalate beyond scenario signal without cause
    """
    case_risk = scenario_context.get("risk_level", "").upper()

    if case_risk == "HIGH":
        return RiskLevel.HIGH
    if case_risk == "LOW":
        # Escalate to MEDIUM if recommended candidate is barely feasible
        # or if most candidates are infeasible
        feasible_count = sum(
            1 for c in joined if c.get("feasible", c.get("is_feasible", False))
        )
        if feasible_count <= 1:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    # Default / MEDIUM
    feasible_count = sum(
        1 for c in joined if c.get("feasible", c.get("is_feasible", False))
    )
    if feasible_count <= 1:
        return RiskLevel.HIGH
    return RiskLevel.MEDIUM


def _build_evidence_sources(
    recommended: dict[str, Any],
    cost_output: dict[str, Any],
) -> list[EvidenceSource]:
    """Build structured evidence_sources from operations evidence_refs and cost facts."""
    sources: list[EvidenceSource] = []

    # Evidence from RAG retrieval (via operations agent)
    for ref in recommended.get("evidence_refs", [])[:3]:
        sources.append(EvidenceSource(
            source_type="knowledge_base",
            field_or_key=f"{ref.get('source_doc', '?')}:{ref.get('chunk_id', '?')}",
            value=ref.get("section", ""),
            relevance=ref.get("excerpt", "")[:120],
        ))

    # Cost estimate as evidence
    tc = recommended.get("total_cost_estimate")
    if tc is not None:
        sources.append(EvidenceSource(
            source_type="cost_estimate",
            field_or_key=f"{recommended.get('candidate_id', '?')}.total_cost_estimate",
            value=tc,
            relevance=(
                "Runtime decision-support cost estimate. "
                "Not authoritative evaluation truth."
            ),
        ))

    # Feasibility as evidence
    sources.append(EvidenceSource(
        source_type="feasibility_check",
        field_or_key=f"{recommended.get('candidate_id', '?')}.feasible",
        value=recommended.get("feasible", recommended.get("is_feasible", False)),
        relevance="Operational feasibility gate aligned with TwinState constraints.",
    ))

    return sources


def _build_cost_summary(
    recommended: dict[str, Any],
    joined: list[dict[str, Any]],
) -> str:
    """Build a cost_summary string using estimate-oriented language only."""
    parts: list[str] = []

    rec_id = recommended.get("candidate_id", "?")
    rec_total = recommended.get("total_cost_estimate")
    rec_direct = recommended.get("direct_cost_estimate")
    rec_recovery = recommended.get("recovery_cost_estimate")

    if rec_total is not None:
        parts.append(
            f"Recommended candidate {rec_id}: estimated total cost "
            f"${rec_total:.2f} (direct estimate ${rec_direct:.2f} + "
            f"recovery estimate ${rec_recovery:.2f})."
        )
    else:
        parts.append(
            f"Recommended candidate {rec_id}: cost estimate unavailable "
            f"(candidate may be infeasible)."
        )

    # Brief comparison with alternatives
    feasible_costs = [
        (c["candidate_id"], c["total_cost_estimate"])
        for c in joined
        if c.get("total_cost_estimate") is not None
        and c["candidate_id"] != rec_id
        and c.get("feasible", c.get("is_feasible", False))
    ]
    if feasible_costs:
        cheapest = min(feasible_costs, key=lambda x: x[1])
        costliest = max(feasible_costs, key=lambda x: x[1])
        parts.append(
            f"Alternative estimates range from ${cheapest[1]:.2f} "
            f"({cheapest[0]}) to ${costliest[1]:.2f} ({costliest[0]})."
        )

    parts.append(
        "All figures are runtime decision-support estimates, "
        "not authoritative evaluation truth."
    )

    return " ".join(parts)


def _build_rationale_trace(
    recommended: dict[str, Any],
    scenario_context: dict[str, Any],
    risk_level: RiskLevel,
    joined: list[dict[str, Any]],
) -> str:
    """Build rationale_trace covering feasibility, evidence, and cost tradeoff."""
    parts: list[str] = []

    rec_id = recommended.get("candidate_id", "?")
    rec_type = recommended.get("candidate_type", "?")
    scenario_type = scenario_context.get("scenario_type", "unknown")

    # 1. Candidate feasibility
    is_feasible = recommended.get("feasible", recommended.get("is_feasible", False))
    fs = recommended.get("feasibility_score", 0)
    parts.append(
        f"Selected {rec_type} candidate ({rec_id}) with "
        f"feasibility score {fs:.2f}/1.00 "
        f"({'feasible' if is_feasible else 'INFEASIBLE'})."
    )

    feasible_count = sum(
        1 for c in joined if c.get("feasible", c.get("is_feasible", False))
    )
    parts.append(
        f"{feasible_count} of {len(joined)} candidates passed feasibility checks."
    )

    # 2. Retrieved policy/evidence support
    evidence_refs = recommended.get("evidence_refs", [])
    if evidence_refs:
        top_docs = list({ref.get("source_doc", "?") for ref in evidence_refs[:3]})
        parts.append(
            f"Policy evidence retrieved from: {', '.join(top_docs)}."
        )

    # 3. Estimated cost tradeoff
    rec_total = recommended.get("total_cost_estimate")
    if rec_total is not None:
        # Find the cheapest feasible alternative
        alt_costs = [
            c["total_cost_estimate"]
            for c in joined
            if c["candidate_id"] != rec_id
            and c.get("total_cost_estimate") is not None
            and c.get("feasible", c.get("is_feasible", False))
        ]
        if alt_costs:
            min_alt = min(alt_costs)
            if rec_total <= min_alt:
                parts.append(
                    f"Estimated cost (${rec_total:.2f}) is the lowest "
                    f"among feasible alternatives."
                )
            else:
                parts.append(
                    f"Estimated cost (${rec_total:.2f}) is not the lowest "
                    f"(cheapest feasible alternative: ${min_alt:.2f}), "
                    f"but operational fit score ({fs:.2f}) supports this choice."
                )
        else:
            parts.append(f"Estimated cost: ${rec_total:.2f}.")

    parts.append(
        f"Scenario: {scenario_type}, assessed risk: {risk_level.value}."
    )

    return " ".join(parts)


def _build_confidence_note(
    recommended: dict[str, Any],
    scenario_context: dict[str, Any],
    risk_level: RiskLevel,
    joined: list[dict[str, Any]],
) -> str:
    """Build confidence_note expressing assumptions and uncertainty."""
    notes: list[str] = []

    is_feasible = recommended.get("feasible", recommended.get("is_feasible", False))
    if not is_feasible:
        notes.append(
            "Low confidence: recommended candidate did not pass feasibility checks."
        )

    feasible_count = sum(
        1 for c in joined if c.get("feasible", c.get("is_feasible", False))
    )
    if feasible_count <= 2:
        notes.append(
            f"Limited options: only {feasible_count} of {len(joined)} "
            f"candidates are feasible."
        )

    if risk_level == RiskLevel.HIGH:
        notes.append("High-risk scenario warrants careful human review.")

    # Standard MVP caveats
    notes.append(
        "Cost figures are runtime estimates using baseline policy defaults; "
        "actual costs may differ."
    )

    exception_desc = scenario_context.get("exception_description", "")
    if any(kw in exception_desc.lower() for kw in
           ("uncertain", "unverified", "discrepancy", "may not match")):
        notes.append(
            "Scenario description contains uncertainty signals; "
            "verification may be warranted."
        )

    return " ".join(notes)


def _build_alternative_actions(
    recommended: dict[str, Any],
    joined: list[dict[str, Any]],
) -> list[AlternativeAction]:
    """Build alternative_actions from remaining feasible candidates."""
    alts: list[AlternativeAction] = []
    rec_id = recommended.get("candidate_id", "?")

    for c in joined:
        if c["candidate_id"] == rec_id:
            continue
        is_feasible = c.get("feasible", c.get("is_feasible", False))
        if not is_feasible:
            continue

        tc = c.get("total_cost_estimate")
        cost_note = f"estimated cost ${tc:.2f}" if tc is not None else "cost unavailable"

        risk_note = "Lower" if c.get("feasibility_score", 0) > 0.6 else "Moderate"
        if c.get("feasibility_score", 0) < 0.4:
            risk_note = "Higher"

        alts.append(AlternativeAction(
            action_label=f"{c['candidate_type']}: {c.get('description', c['candidate_id'])}",
            description=f"{cost_note}, feasibility {c.get('feasibility_score', 0):.2f}",
            estimated_risk=f"{risk_note} operational risk",
        ))

    return alts[:4]  # cap at 4 alternatives for readability


# ---------------------------------------------------------------------------
# Main synthesis entry point
# ---------------------------------------------------------------------------


def run_governance_agent(
    scenario_context: dict[str, Any],
    operations_output: dict[str, Any],
    cost_output: dict[str, Any],
) -> GovernanceOutput:
    """Synthesize a GovernanceOutput from operations + cost + scenario context.

    This is a deterministic synthesis layer.  It does NOT:
      - Invoke an LLM
      - Read oracle/evaluation truth
      - Emit AI/ALT1/ALT2 as recommended_action
      - Claim cost estimates are authoritative evaluation truth

    Parameters
    ----------
    scenario_context:
        Dict with scenario_type, risk_level, exception_description.
    operations_output:
        Serialized OperationsOutput dict (ranked_candidates + evidence).
    cost_output:
        Serialized CostOutput dict (cost_estimates).

    Returns
    -------
    GovernanceOutput
        Frozen 8-field governance output.
    """
    # Step 1: Join candidates with cost estimates
    joined = _join_candidates_with_costs(operations_output, cost_output)

    if not joined:
        return make_placeholder_governance_output()

    # Step 2: Select recommended candidate
    recommended = _select_recommended(joined, scenario_context)

    # Step 3: Determine risk level
    risk_level = _determine_risk_level(scenario_context, recommended, joined)

    # Step 4: Build situational explanation
    scenario_type = scenario_context.get("scenario_type", "Unknown")
    exception_desc = scenario_context.get("exception_description", "")
    rec_id = recommended.get("candidate_id", "?")
    rec_type = recommended.get("candidate_type", "?")

    situational_explanation = (
        f"Scenario '{scenario_type}' assessed at {risk_level.value} risk. "
        f"{exception_desc[:150]} "
        f"Governance recommends {rec_type} ({rec_id}) based on "
        f"feasibility analysis, policy evidence, and estimated cost tradeoffs."
    )

    # Step 5: Build recommended_action (operational candidate, never supervision code)
    recommended_action = (
        f"{rec_type}: {recommended.get('description', rec_id)}"
    )

    # Step 6: Build evidence_sources
    evidence_sources = _build_evidence_sources(recommended, cost_output)

    # Step 7: Build cost_summary
    cost_summary = _build_cost_summary(recommended, joined)

    # Step 8: Build rationale_trace
    rationale_trace = _build_rationale_trace(
        recommended, scenario_context, risk_level, joined,
    )

    # Step 9: Build confidence_note
    confidence_note = _build_confidence_note(
        recommended, scenario_context, risk_level, joined,
    )

    # Step 10: Build alternative_actions
    alternative_actions = _build_alternative_actions(recommended, joined)

    return GovernanceOutput(
        risk_level=risk_level,
        situational_explanation=situational_explanation,
        recommended_action=recommended_action,
        evidence_sources=evidence_sources,
        cost_summary=cost_summary,
        confidence_note=confidence_note,
        rationale_trace=rationale_trace,
        alternative_actions=alternative_actions,
    )


def run_governance_agent_with_meta(
    scenario_context: dict[str, Any],
    operations_output: dict[str, Any],
    cost_output: dict[str, Any],
    *,
    mode: str = "rules",
    gateway_config: Any = None,
) -> tuple[GovernanceOutput, dict[str, Any]]:
    """Run governance synthesis and also return supervisor identity metadata.

    Returns (GovernanceOutput, governance_meta_dict).
    The meta dict is for graph state; it is NOT part of the frozen 8-field schema.

    Parameters
    ----------
    mode:
        "rules" (default) → deterministic synthesis only.
        "llm"   → deterministic synthesis, then language-field enrichment via
                  src/llm_backend.py. On any LLM failure the rules-mode
                  output is returned unchanged.
    gateway_config:
        Optional Phase 2 GatewayConfig. Ignored in rules mode.
    """
    from supervisor import build_governance_meta

    joined = _join_candidates_with_costs(operations_output, cost_output)

    if not joined:
        return make_placeholder_governance_output(), {
            "recommended_candidate_id": None,
            "recommended_candidate_type": None,
            "alternatives": [],
            "mode": "rules",
            "llm_enriched_fields": [],
            "llm_trace": None,
        }

    recommended = _select_recommended(joined, scenario_context)
    meta = build_governance_meta(recommended, joined)

    resolved_mode = _resolve_mode(mode)
    if resolved_mode == "llm":
        baseline = run_governance_agent(scenario_context, operations_output, cost_output)
        gov_output, llm_meta = _enrich_with_llm(
            baseline, scenario_context, joined, recommended,
            gateway_config=gateway_config,
        )
        meta["mode"] = "llm"
        meta["llm_enriched_fields"] = llm_meta.get("enriched_fields", [])
        meta["llm_trace"] = llm_meta.get("trace")
    else:
        gov_output = run_governance_agent(scenario_context, operations_output, cost_output)
        meta["mode"] = "rules"
        meta["llm_enriched_fields"] = []
        meta["llm_trace"] = None

    return gov_output, meta


# ---------------------------------------------------------------------------
# Phase 3: mode dispatch + LLM language enrichment
# ---------------------------------------------------------------------------


_VALID_GOVERNANCE_MODES = frozenset({"rules", "llm"})
_GOVERNANCE_MODE_ENV = "SUPPLY_CHAIN_TWIN_GOVERNANCE_MODE"

# Enriched-only fields. recommended_action, risk_level, evidence_sources, and
# alternative action_label/estimated_risk remain deterministic.
_LLM_ENRICHED_FIELDS: tuple[str, ...] = (
    "situational_explanation",
    "confidence_note",
    "rationale_trace",
    "cost_summary",
    "alternative_descriptions",
)

# Forbidden standalone tokens in LLM-enriched free text. "AI" appears in
# natural language (e.g. "AI recommends") so only ALT1/ALT2 are guarded here.
_FORBIDDEN_LLM_TOKENS_RE = None  # lazy init


def _forbidden_token_pattern():
    import re
    global _FORBIDDEN_LLM_TOKENS_RE
    if _FORBIDDEN_LLM_TOKENS_RE is None:
        _FORBIDDEN_LLM_TOKENS_RE = re.compile(r"\b(ALT1|ALT2)\b")
    return _FORBIDDEN_LLM_TOKENS_RE


def _resolve_mode(mode: str | None) -> str:
    """Resolve governance mode from arg, falling back to env, falling back to
    'rules'. Unknown values degrade to 'rules' (safe default)."""
    import os
    candidate = (mode or os.environ.get(_GOVERNANCE_MODE_ENV) or "rules")
    candidate = str(candidate).strip().lower()
    if candidate not in _VALID_GOVERNANCE_MODES:
        return "rules"
    return candidate


def run_governance_agent_modeful(
    mode: str,
    scenario_context: dict[str, Any],
    operations_output: dict[str, Any],
    cost_output: dict[str, Any],
    *,
    gateway_config: Any = None,
) -> GovernanceOutput:
    """Entry point that dispatches by governance mode.

    Both modes return a schema-valid GovernanceOutput. In llm mode, on any
    LLM failure (unavailable / malformed / validation / forbidden tokens)
    the deterministic rules-mode output is returned unchanged.
    """
    resolved = _resolve_mode(mode)
    if resolved == "llm":
        return run_governance_agent_llm(
            scenario_context, operations_output, cost_output,
            gateway_config=gateway_config,
        )
    return run_governance_agent(scenario_context, operations_output, cost_output)


def run_governance_agent_llm(
    scenario_context: dict[str, Any],
    operations_output: dict[str, Any],
    cost_output: dict[str, Any],
    *,
    gateway_config: Any = None,
) -> GovernanceOutput:
    """Deterministic synthesis + LLM language enrichment.

    On any enrichment failure returns the deterministic baseline unchanged.
    """
    baseline = run_governance_agent(scenario_context, operations_output, cost_output)
    joined = _join_candidates_with_costs(operations_output, cost_output)
    if not joined:
        return baseline
    recommended = _select_recommended(joined, scenario_context)
    enriched, _ = _enrich_with_llm(
        baseline, scenario_context, joined, recommended,
        gateway_config=gateway_config,
    )
    return enriched


# ---------------------------------------------------------------------------
# LLM enrichment internals
# ---------------------------------------------------------------------------


class _LLMLanguagePayload(BaseModel):
    """Validator for the LLM-produced language enrichment payload."""

    situational_explanation: str
    confidence_note: str
    rationale_trace: str
    cost_summary: str
    alternative_descriptions: list[str] = []

    @field_validator(
        "situational_explanation", "confidence_note",
        "rationale_trace", "cost_summary",
    )
    @classmethod
    def _strip_nonempty(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("field must be non-empty")
        return v


def _build_llm_system_prompt() -> str:
    return (
        "You are the Governance Agent of a human-supervised supply chain twin. "
        "You rewrite and refine natural-language fields ONLY. "
        "You must not change numeric values, operational identifiers, recommended actions, "
        "risk levels, or evidence. "
        "You must not emit the tokens ALT1 or ALT2 in your output. "
        "Respond with a single JSON object; no code fences; no commentary."
    )


def _build_llm_user_prompt(
    baseline: GovernanceOutput,
    scenario_context: dict[str, Any],
    joined: list[dict[str, Any]],
    recommended: dict[str, Any],
) -> str:
    import json as _json
    facts = {
        "scenario_type": scenario_context.get("scenario_type", ""),
        "risk_level": baseline.risk_level.value,
        "recommended_action": baseline.recommended_action,
        "recommended_candidate_id": recommended.get("candidate_id"),
        "recommended_candidate_type": recommended.get("candidate_type"),
        "recommended_total_cost_estimate": recommended.get("total_cost_estimate"),
        "recommended_feasibility_score": recommended.get("feasibility_score"),
        "feasible_count": sum(
            1 for c in joined
            if c.get("feasible", c.get("is_feasible", False))
        ),
        "total_candidates": len(joined),
        "exception_description": scenario_context.get("exception_description", ""),
        "baseline": {
            "situational_explanation": baseline.situational_explanation,
            "confidence_note": baseline.confidence_note,
            "rationale_trace": baseline.rationale_trace,
            "cost_summary": baseline.cost_summary,
            "alternative_action_labels": [
                a.action_label for a in baseline.alternative_actions
            ],
            "alternative_descriptions": [
                a.description for a in baseline.alternative_actions
            ],
        },
    }
    return (
        "Refine the following governance language fields. Preserve every "
        "numeric value, operational identifier, and risk level exactly as "
        "shown in the baseline. Produce only this JSON shape:\n"
        "{\n"
        '  "situational_explanation": "...",\n'
        '  "confidence_note": "...",\n'
        '  "rationale_trace": "...",\n'
        '  "cost_summary": "...",\n'
        '  "alternative_descriptions": ["...", "..."]\n'
        "}\n"
        "The alternative_descriptions list must have the same length and "
        "order as baseline.alternative_descriptions. Do not add, remove, or "
        "reorder alternatives.\n\n"
        f"Facts:\n{_json.dumps(facts, indent=2, default=str)}\n"
    )


def _deterministic_language_fallback(baseline: GovernanceOutput):
    """Return the baseline's language fields as a callable fallback for the
    LLM gateway. Accepts (prompt, schema) per the Phase 2 gateway contract."""

    payload = {
        "situational_explanation": baseline.situational_explanation,
        "confidence_note": baseline.confidence_note,
        "rationale_trace": baseline.rationale_trace,
        "cost_summary": baseline.cost_summary,
        "alternative_descriptions": [
            a.description for a in baseline.alternative_actions
        ],
    }

    def _fb(prompt, schema):
        return payload

    return _fb


def _contains_forbidden_token(text: str) -> bool:
    return bool(_forbidden_token_pattern().search(text or ""))


def _enrich_with_llm(
    baseline: GovernanceOutput,
    scenario_context: dict[str, Any],
    joined: list[dict[str, Any]],
    recommended: dict[str, Any],
    *,
    gateway_config: Any = None,
) -> tuple[GovernanceOutput, dict[str, Any]]:
    """Run the Phase 2 gateway to enrich language fields. Returns
    (new_governance_output_or_baseline, llm_meta)."""
    llm_meta: dict[str, Any] = {"enriched_fields": [], "trace": None}

    try:
        from llm_backend import generate_structured
    except Exception as exc:  # pragma: no cover — llm_backend must exist
        llm_meta["trace"] = {"error": f"llm_backend import failed: {exc}"}
        return baseline, llm_meta

    system = _build_llm_system_prompt()
    prompt = _build_llm_user_prompt(baseline, scenario_context, joined, recommended)

    result = generate_structured(
        prompt,
        _LLMLanguagePayload,
        gateway_config=gateway_config,
        deterministic_fallback=_deterministic_language_fallback(baseline),
        system=system,
    )
    llm_meta["trace"] = result.to_trace_dict() if hasattr(result, "to_trace_dict") else None

    payload = result.value if result is not None else None
    if payload is None:
        return baseline, llm_meta

    # Forbidden-token guard over the language fields (not over raw evidence).
    text_blob = " ".join([
        str(payload.get("situational_explanation", "")),
        str(payload.get("confidence_note", "")),
        str(payload.get("rationale_trace", "")),
        str(payload.get("cost_summary", "")),
        *[str(d) for d in payload.get("alternative_descriptions", []) or []],
    ])
    if _contains_forbidden_token(text_blob):
        llm_meta["trace"] = {
            **(llm_meta.get("trace") or {}),
            "rejected_reason": "forbidden_token_in_enriched_fields",
        }
        return baseline, llm_meta

    # Alternative descriptions are deterministic cost/feasibility strings.
    # Only allow LLM to replace them when the LLM list is non-trivial
    # (>=2 entries), exactly matches the baseline length, and every entry
    # is a non-empty string. Otherwise keep the baseline descriptions —
    # this avoids silent reorders or one-off rewrites of structured text.
    baseline_alts = baseline.alternative_actions
    alt_descs_raw = payload.get("alternative_descriptions") or []
    use_alt_descs = (
        isinstance(alt_descs_raw, list)
        and len(alt_descs_raw) >= 2
        and len(alt_descs_raw) == len(baseline_alts)
        and all(isinstance(d, str) and d.strip() for d in alt_descs_raw)
    )

    # Build new alternative_actions preserving deterministic action_label and
    # estimated_risk; only description is swapped when safe.
    new_alts = []
    enriched_alt_count = 0
    for i, alt in enumerate(baseline_alts):
        if use_alt_descs:
            new_desc = alt_descs_raw[i].strip()
            new_alts.append(AlternativeAction(
                action_label=alt.action_label,
                description=new_desc,
                estimated_risk=alt.estimated_risk,
            ))
            enriched_alt_count += 1
        else:
            new_alts.append(alt)

    # Build new GovernanceOutput — frozen schema preserved, deterministic
    # fields copied verbatim.
    enriched = GovernanceOutput(
        risk_level=baseline.risk_level,
        situational_explanation=str(payload["situational_explanation"]).strip(),
        recommended_action=baseline.recommended_action,  # deterministic
        evidence_sources=list(baseline.evidence_sources),  # deterministic
        cost_summary=str(payload["cost_summary"]).strip(),
        confidence_note=str(payload["confidence_note"]).strip(),
        rationale_trace=str(payload["rationale_trace"]).strip(),
        alternative_actions=new_alts,
    )

    enriched_fields = [
        "situational_explanation", "confidence_note",
        "rationale_trace", "cost_summary",
    ]
    if enriched_alt_count > 0:
        enriched_fields.append("alternative_actions.description")
    llm_meta["enriched_fields"] = enriched_fields

    return enriched, llm_meta
