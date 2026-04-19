"""adaptive/adaptive_policy_config.py — Path C Phase 2 adaptive config.

Contains:
  - ``AdaptivePolicyGateConfig``: canonical owner of
    ``min_records_for_shift`` (Roadmap owner-point v2.1-D).
  - Default adjustment-rule set.
  - ``KNOWN_RULE_IDS`` registry used by the audit-trail test to check
    that every fired adjustment carries an acknowledged ``rule_id``.

A rule is a *pure callable* with signature::

    (summary: MemorySummary, event_context: EventContext)
        -> AdaptivePolicyAdjustment | None

The caller (``decide_policy_adaptive``) is responsible for building the
``MemoryQuery`` and computing the ``MemorySummary``; rules never perform
their own memory I/O. Rules return ``None`` to pass, or a fully-populated
``AdaptivePolicyAdjustment``. Only ``UPGRADE_ONE_LEVEL``,
``NO_ADJUSTMENT`` and ``COLD_START_FALLBACK`` are permitted
``adjustment_type`` values (Phase 2 bounded action set).

Deterministic, no wall-clock, no uuid4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from policy_gate import PolicyGateConfig

from adaptive.adaptive_schema import AdaptivePolicyAdjustment
from adaptive.cold_start import COLD_START_RULE_ID
from learning.memory_schema import MemorySummary


_RISK_UPGRADE: dict[str, str] = {"LOW": "MEDIUM", "MEDIUM": "HIGH"}


@dataclass(frozen=True)
class EventContext:
    """Minimal event context surface for adjustment rules."""
    event_id: str
    event_type: str
    severity: str
    risk_level: str  # governance_output.risk_level, uppercased


# ---------------------------------------------------------------------------
# Default rule: poor-SLA upgrade
# ---------------------------------------------------------------------------


POOR_SLA_UPGRADE_RULE_ID: str = "poor_sla_upgrade_v1"
POOR_SLA_UPGRADE_THRESHOLD: float = 0.5


def _poor_sla_upgrade_rule(
    summary: MemorySummary,
    event_context: EventContext,
) -> Optional[AdaptivePolicyAdjustment]:
    """Upgrade risk one level if recent memory shows poor SLA preservation.

    Pure: same (summary, event_context) → same output.
    Fires iff:
      - summary.matched_records > 0
      - summary.sla_preservation_rate is not None
      - summary.sla_preservation_rate < POOR_SLA_UPGRADE_THRESHOLD
      - event_context.risk_level is LOW or MEDIUM (upgrade possible)
    """
    if summary.matched_records <= 0:
        return None
    if summary.sla_preservation_rate is None:
        return None
    if summary.sla_preservation_rate >= POOR_SLA_UPGRADE_THRESHOLD:
        return None

    pre = str(event_context.risk_level).strip().upper()
    post = _RISK_UPGRADE.get(pre)
    if post is None:
        # HIGH has no upgrade target — bounded action set (no DOWNGRADE, no
        # two-level jumps). Rule passes.
        return None

    return AdaptivePolicyAdjustment(
        rule_id=POOR_SLA_UPGRADE_RULE_ID,
        adjustment_type="UPGRADE_ONE_LEVEL",
        pre_adjustment_risk=pre,
        post_adjustment_risk=post,
        query_signature=summary.query_signature,
        memory_evidence={
            "matched_records": summary.matched_records,
            "sla_preservation_rate": summary.sla_preservation_rate,
            "threshold_rate": POOR_SLA_UPGRADE_THRESHOLD,
        },
        notes=(
            f"Upgrade {pre}->{post}: sla_preservation_rate="
            f"{summary.sla_preservation_rate} "
            f"< threshold={POOR_SLA_UPGRADE_THRESHOLD} over "
            f"{summary.matched_records} matched records."
        ),
    )


AdjustmentRule = Callable[
    [MemorySummary, EventContext],
    Optional[AdaptivePolicyAdjustment],
]


DEFAULT_RULES: tuple[AdjustmentRule, ...] = (
    _poor_sla_upgrade_rule,
)


# Every rule_id that may appear in a fired AdaptivePolicyAdjustment.
# test_adaptive_audit_trail verifies fired rule_ids belong to this set.
KNOWN_RULE_IDS: frozenset[str] = frozenset({
    COLD_START_RULE_ID,
    POOR_SLA_UPGRADE_RULE_ID,
})


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdaptivePolicyGateConfig:
    """Adaptive policy gate configuration.

    - ``min_records_for_shift`` is the canonical cold-start threshold.
      Default 3 per Roadmap §1.D; tests parameterize it over multiple
      values to verify there is no ``first 3 events`` assumption baked
      into downstream code.
    - ``rules`` is the ordered list of adjustment rules. First rule to
      fire wins.
    - ``base_policy_config`` is the *same* ``PolicyGateConfig`` that
      Path B's ``policy_gate.decide_policy`` uses; the adaptive layer
      never modifies or replaces it, only consults ``decide_policy``
      with an adjusted ``risk_level`` when a rule fires.
    """

    min_records_for_shift: int = 3
    rules: tuple[AdjustmentRule, ...] = field(default_factory=lambda: DEFAULT_RULES)
    base_policy_config: PolicyGateConfig = field(default_factory=PolicyGateConfig)
