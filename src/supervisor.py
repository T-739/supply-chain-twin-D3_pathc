"""
supervisor.py — Minimal Supervisor for approve / verify / override decisions.

The Supervisor consumes governance output (plus supporting metadata) and
records a structured supervision decision.  It operates in the SUPERVISION
layer (APPROVE / VERIFY / OVERRIDE), NOT the operational layer
(EXPEDITE / TRANSFER / COMPENSATE / NO_ACTION).

It does NOT:
  - Emit AI / ALT1 / ALT2 as operational candidate identities
  - Modify oracle truth, cost_ground_truth, or evaluation semantics
  - Invoke an LLM or UI
  - Collapse supervision decisions into operational action types

Decision paths (all deterministic for MVP):
  APPROVE  — accept governance recommendation as-is
  VERIFY   — flag for additional review; keep recommendation but mark review_requested
  OVERRIDE — select one named alternative from governance alternatives
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Supervision decision type (mirrors twin_state.SupervisorDecisionType)
# ---------------------------------------------------------------------------


class SupervisorDecisionType(str, Enum):
    """Supervision-layer decision type.  NOT an operational action type."""

    APPROVE = "APPROVE"
    VERIFY = "VERIFY"
    OVERRIDE = "OVERRIDE"


# ---------------------------------------------------------------------------
# Forbidden tokens — supervisor must never emit these as candidate identities
# ---------------------------------------------------------------------------

_FORBIDDEN_CANDIDATE_TOKENS: frozenset[str] = frozenset({
    "AI", "ALT1", "ALT2",
})


# ---------------------------------------------------------------------------
# Input: instruction injected into graph state by caller / test harness
# ---------------------------------------------------------------------------


class SupervisorInstruction(BaseModel):
    """Minimal instruction telling the supervisor what decision to make.

    For MVP there is no UI; the caller injects this into graph state.
    """

    mode: str  # "approve" | "verify" | "override"
    review_focus: str = ""  # used when mode == "verify"
    target_action_label: str = ""  # used when mode == "override"

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"approve", "verify", "override"}
        v_lower = v.strip().lower()
        if v_lower not in allowed:
            raise ValueError(
                f"mode must be one of {allowed}, got '{v}'"
            )
        return v_lower


# ---------------------------------------------------------------------------
# Output: structured supervisor decision
# ---------------------------------------------------------------------------


class SupervisorDecision(BaseModel):
    """Structured output contract for the Supervisor node.

    supervisor_decision_type:  APPROVE / VERIFY / OVERRIDE
    selected_candidate_id:     stable candidate ID (or None for VERIFY)
    selected_candidate_type:   operational type of selected candidate (or None)
    decision_rationale:        brief explanation
    review_requested:          True when VERIFY, False otherwise
    review_focus:              short focus area (empty when not VERIFY)
    override_from_recommendation:  True when OVERRIDE, False otherwise
    """

    supervisor_decision_type: SupervisorDecisionType
    selected_candidate_id: str | None
    selected_candidate_type: str | None
    decision_rationale: str
    review_requested: bool
    review_focus: str
    override_from_recommendation: bool

    @field_validator("selected_candidate_id")
    @classmethod
    def reject_forbidden_ids(cls, v: str | None) -> str | None:
        if v is not None and v.strip().upper() in _FORBIDDEN_CANDIDATE_TOKENS:
            raise ValueError(
                f"selected_candidate_id must not be a supervision code, got '{v}'"
            )
        return v

    @field_validator("selected_candidate_type")
    @classmethod
    def reject_forbidden_types(cls, v: str | None) -> str | None:
        if v is not None and v.strip().upper() in _FORBIDDEN_CANDIDATE_TOKENS:
            raise ValueError(
                f"selected_candidate_type must not be a supervision code, got '{v}'"
            )
        return v

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Governance metadata — identity mapping outside frozen GovernanceOutput
# ---------------------------------------------------------------------------


def build_governance_meta(
    recommended: dict[str, Any],
    joined: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build identity metadata for the supervisor.

    This lives in graph state as _governance_meta, NOT inside the frozen
    8-field GovernanceOutput schema.

    Returns dict with:
      recommended_candidate_id
      recommended_candidate_type
      alternatives: list of {action_label, candidate_id, candidate_type}
    """
    rec_id = recommended.get("candidate_id", "?")
    rec_type = recommended.get("candidate_type", "?")

    alts: list[dict[str, str]] = []
    for c in joined:
        if c["candidate_id"] == rec_id:
            continue
        is_feasible = c.get("feasible", c.get("is_feasible", False))
        if not is_feasible:
            continue
        # action_label matches the format used by _build_alternative_actions
        label = f"{c['candidate_type']}: {c.get('description', c['candidate_id'])}"
        alts.append({
            "action_label": label,
            "candidate_id": c["candidate_id"],
            "candidate_type": c["candidate_type"],
        })

    return {
        "recommended_candidate_id": rec_id,
        "recommended_candidate_type": rec_type,
        "alternatives": alts[:4],  # matches governance cap
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_supervisor(
    governance_output: dict[str, Any],
    governance_meta: dict[str, Any],
    instruction: dict[str, Any] | None = None,
) -> SupervisorDecision:
    """Run the Supervisor and produce a structured decision.

    Parameters
    ----------
    governance_output:
        Serialized GovernanceOutput dict (8 fields).
    governance_meta:
        Identity metadata from build_governance_meta().
    instruction:
        Optional SupervisorInstruction-compatible dict.
        Defaults to {"mode": "approve"} if not provided.

    Returns
    -------
    SupervisorDecision
    """
    # Parse instruction
    if instruction is None:
        instruction = {"mode": "approve"}
    inst = SupervisorInstruction(**instruction)

    rec_id = governance_meta.get("recommended_candidate_id")
    rec_type = governance_meta.get("recommended_candidate_type")
    alternatives = governance_meta.get("alternatives", [])
    risk_level = governance_output.get("risk_level", "MEDIUM")

    if inst.mode == "approve":
        return _do_approve(rec_id, rec_type, risk_level, governance_output)

    if inst.mode == "verify":
        return _do_verify(
            rec_id, rec_type, risk_level, governance_output, inst.review_focus,
        )

    if inst.mode == "override":
        return _do_override(
            rec_id, rec_type, alternatives, governance_output,
            inst.target_action_label,
        )

    # Should never reach here due to validator, but be safe
    raise ValueError(f"Unknown supervisor mode: {inst.mode}")


# ---------------------------------------------------------------------------
# Decision path implementations
# ---------------------------------------------------------------------------


def _do_approve(
    rec_id: str | None,
    rec_type: str | None,
    risk_level: str,
    governance_output: dict[str, Any],
) -> SupervisorDecision:
    """APPROVE: accept governance recommendation as-is."""
    return SupervisorDecision(
        supervisor_decision_type=SupervisorDecisionType.APPROVE,
        selected_candidate_id=rec_id,
        selected_candidate_type=rec_type,
        decision_rationale=(
            f"Supervisor approves governance recommendation "
            f"({rec_type}: {rec_id}) at {risk_level} risk."
        ),
        review_requested=False,
        review_focus="",
        override_from_recommendation=False,
    )


def _do_verify(
    rec_id: str | None,
    rec_type: str | None,
    risk_level: str,
    governance_output: dict[str, Any],
    review_focus: str,
) -> SupervisorDecision:
    """VERIFY: flag for review, keep current recommendation provisionally."""
    if not review_focus:
        # Auto-generate a focus from confidence_note
        confidence = governance_output.get("confidence_note", "")
        if "high-risk" in confidence.lower():
            review_focus = "High-risk scenario requires human verification."
        elif "limited options" in confidence.lower():
            review_focus = "Limited feasible options; review operational constraints."
        else:
            review_focus = "General review requested before finalizing decision."

    return SupervisorDecision(
        supervisor_decision_type=SupervisorDecisionType.VERIFY,
        selected_candidate_id=rec_id,
        selected_candidate_type=rec_type,
        decision_rationale=(
            f"Supervisor requests verification before finalizing "
            f"({rec_type}: {rec_id}). Review focus: {review_focus}"
        ),
        review_requested=True,
        review_focus=review_focus,
        override_from_recommendation=False,
    )


def _do_override(
    rec_id: str | None,
    rec_type: str | None,
    alternatives: list[dict[str, str]],
    governance_output: dict[str, Any],
    target_action_label: str,
) -> SupervisorDecision:
    """OVERRIDE: select a named alternative instead of the recommendation.

    If target_action_label matches an alternative, use it.
    If no match and alternatives exist, pick the first alternative.
    If no alternatives, fall back to approving the recommendation with a note.
    """
    # Try exact match first
    selected = None
    for alt in alternatives:
        if alt["action_label"] == target_action_label:
            selected = alt
            break

    # Try prefix match (candidate_type or candidate_id in the label)
    if selected is None and target_action_label:
        target_upper = target_action_label.strip().upper()
        for alt in alternatives:
            if (target_upper in alt["action_label"].upper()
                    or target_upper == alt["candidate_id"].upper()
                    or target_upper == alt["candidate_type"].upper()):
                selected = alt
                break

    # Fall back to first alternative if no target specified or no match
    if selected is None and alternatives:
        selected = alternatives[0]

    if selected is None:
        # No alternatives available — cannot override, fall back to approve
        return SupervisorDecision(
            supervisor_decision_type=SupervisorDecisionType.APPROVE,
            selected_candidate_id=rec_id,
            selected_candidate_type=rec_type,
            decision_rationale=(
                "Override requested but no feasible alternatives available. "
                "Falling back to governance recommendation."
            ),
            review_requested=False,
            review_focus="",
            override_from_recommendation=False,
        )

    return SupervisorDecision(
        supervisor_decision_type=SupervisorDecisionType.OVERRIDE,
        selected_candidate_id=selected["candidate_id"],
        selected_candidate_type=selected["candidate_type"],
        decision_rationale=(
            f"Supervisor overrides recommendation ({rec_type}: {rec_id}) "
            f"in favor of alternative ({selected['candidate_type']}: "
            f"{selected['candidate_id']})."
        ),
        review_requested=False,
        review_focus="",
        override_from_recommendation=True,
    )
