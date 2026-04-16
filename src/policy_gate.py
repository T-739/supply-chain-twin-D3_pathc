"""
policy_gate.py — D3-Demo: Policy gate contract and deterministic routing.

Defines the policy gate routing contract: given a governance output and a
policy configuration, produce a deterministic routing decision (auto-execute
vs. human-required).

Phase 0: contracts and signatures.
Phase 1: deterministic routing logic in decide_policy().

Hard constraints:
  - No imports from evaluation.py, action_code_mapper.py, graph.py,
    supervisor.py, or agents/*.
  - RiskLevel is defined locally (not imported from governance_agent)
    to avoid coupling the policy gate contract to agent internals.
  - The decide function reads ONLY risk_level from governance_output.
    No LLM-derived fields participate in routing decisions.
  - Unknown or missing risk_level → fail closed → HUMAN_REQUIRED.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PolicyRoute(str, Enum):
    """Routing decision from the policy gate."""

    AUTO_EXECUTE = "AUTO_EXECUTE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class RiskLevel(str, Enum):
    """Risk levels for policy gate routing.

    Locally defined to avoid coupling to governance_agent internals.
    Values must stay in sync with governance_agent.RiskLevel by convention.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


_ALL_RISK_LEVELS = frozenset({RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH})


# ---------------------------------------------------------------------------
# PolicyGateConfig
# ---------------------------------------------------------------------------


class PolicyGateConfig(BaseModel):
    """Configuration for the policy gate routing rules.

    Default: LOW → auto-execute, MEDIUM/HIGH → human required.
    Must satisfy:
      - auto_execute_levels ∩ human_required_levels == ∅
      - auto_execute_levels ∪ human_required_levels == {LOW, MEDIUM, HIGH}
    """

    model_config = ConfigDict(frozen=True)

    auto_execute_levels: frozenset[RiskLevel] = frozenset({RiskLevel.LOW})
    human_required_levels: frozenset[RiskLevel] = frozenset(
        {RiskLevel.MEDIUM, RiskLevel.HIGH}
    )
    version: str = "v0"

    @model_validator(mode="after")
    def check_level_coverage(self) -> PolicyGateConfig:
        overlap = self.auto_execute_levels & self.human_required_levels
        if overlap:
            raise ValueError(
                f"auto_execute_levels and human_required_levels must be disjoint, "
                f"but overlap on: {sorted(r.value for r in overlap)}"
            )
        union = self.auto_execute_levels | self.human_required_levels
        if union != _ALL_RISK_LEVELS:
            missing = _ALL_RISK_LEVELS - union
            raise ValueError(
                f"auto_execute_levels ∪ human_required_levels must cover all risk "
                f"levels, but missing: {sorted(r.value for r in missing)}"
            )
        return self


# ---------------------------------------------------------------------------
# PolicyDecision — output of the policy gate
# ---------------------------------------------------------------------------


class PolicyDecision(BaseModel):
    """Structured routing decision from the policy gate."""

    model_config = ConfigDict(frozen=True)

    route: PolicyRoute
    risk_level: RiskLevel
    requires_human_review: bool
    reason: str
    policy_config_version: str


# ---------------------------------------------------------------------------
# decide_policy — deterministic routing (Phase 1)
# ---------------------------------------------------------------------------


def decide_policy(
    governance_output: dict[str, Any],
    config: PolicyGateConfig | None = None,
) -> PolicyDecision:
    """Route a governance recommendation through the policy gate.

    Reads ONLY ``governance_output["risk_level"]`` for routing.
    All other fields (confidence_note, rationale_trace, cost magnitudes,
    LLM text) are explicitly ignored — deterministic-first.

    Fail-closed: unknown or missing risk_level → HUMAN_REQUIRED.

    Parameters
    ----------
    governance_output : dict
        The governance agent's 8-field structured output (as dict).
        Only the ``risk_level`` field is read for routing.
    config : PolicyGateConfig or None
        Policy gate configuration. Defaults to PolicyGateConfig() if None.

    Returns
    -------
    PolicyDecision
        Deterministic routing decision.
    """
    if config is None:
        config = PolicyGateConfig()

    raw_risk = governance_output.get("risk_level")

    # --- Resolve risk level (fail-closed on unknown/missing) ---
    resolved_level: RiskLevel | None = None
    if raw_risk is not None:
        raw_upper = str(raw_risk).strip().upper()
        try:
            resolved_level = RiskLevel(raw_upper)
        except ValueError:
            resolved_level = None

    # --- Fail-closed: missing or unrecognized risk_level ---
    if resolved_level is None:
        return PolicyDecision(
            route=PolicyRoute.HUMAN_REQUIRED,
            risk_level=RiskLevel.HIGH,  # conservative fallback
            requires_human_review=True,
            reason=f"risk_level missing or unrecognized (raw={raw_risk!r}); fail-closed to HUMAN_REQUIRED",
            policy_config_version=config.version,
        )

    # --- Deterministic routing based on config ---
    if resolved_level in config.auto_execute_levels:
        return PolicyDecision(
            route=PolicyRoute.AUTO_EXECUTE,
            risk_level=resolved_level,
            requires_human_review=False,
            reason=f"{resolved_level.value}→AUTO_EXECUTE per policy {config.version}",
            policy_config_version=config.version,
        )

    # HUMAN_REQUIRED (covers MEDIUM, HIGH, or any custom config)
    return PolicyDecision(
        route=PolicyRoute.HUMAN_REQUIRED,
        risk_level=resolved_level,
        requires_human_review=True,
        reason=f"{resolved_level.value}→HUMAN_REQUIRED per policy {config.version}",
        policy_config_version=config.version,
    )
