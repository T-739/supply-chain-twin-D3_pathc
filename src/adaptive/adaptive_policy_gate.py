"""adaptive/adaptive_policy_gate.py — Path C Phase 2 adaptive policy gate.

The dual-track rule (Roadmap §0.3, owner point 8):
  ``decide_policy_adaptive`` NEVER writes into ``governance_output``.
  It reads ``governance_output`` read-only, and returns

      (PolicyDecision, AdaptivePolicyAdjustment | None)

  The caller (``event_loop_c``) places the adjustment into
  ``SessionEventRecord.adaptive_adjustment`` ALONGSIDE — never instead
  of — the governance truth reference.

Bounded action set (Phase 2):
  - ``UPGRADE_ONE_LEVEL``   (LOW→MEDIUM, MEDIUM→HIGH; never LOW→HIGH)
  - ``NO_ADJUSTMENT``       (rule evaluated, explicit pass)
  - ``COLD_START_FALLBACK`` (memory too sparse)

No ``DOWNGRADE_*``. No schema change to ``PolicyDecision``.

This module is pure: no I/O, no wall-clock, no uuid4, no
``data/cases`` access.
"""

from __future__ import annotations

from typing import Any, Optional

from policy_gate import PolicyDecision, decide_policy

from adaptive.adaptive_policy_config import (
    AdaptivePolicyGateConfig,
    EventContext,
)
from adaptive.adaptive_schema import AdaptivePolicyAdjustment
from adaptive.cold_start import build_cold_start_adjustment, is_cold_start
from learning.episodic_memory import EpisodicMemory
from learning.memory_schema import MemoryQuery


def _build_query_for_event(event_context: EventContext) -> MemoryQuery:
    """Default adaptive query: filter memory by current event_type."""
    return MemoryQuery(event_type=str(event_context.event_type))


def decide_policy_adaptive(
    governance_output: dict[str, Any],
    event_context: EventContext,
    memory: EpisodicMemory,
    config: AdaptivePolicyGateConfig,
) -> tuple[PolicyDecision, Optional[AdaptivePolicyAdjustment]]:
    """Produce (PolicyDecision, AdaptivePolicyAdjustment | None).

    Algorithm:

      1. Build a ``MemoryQuery`` for this event type, summarize memory.
      2. If memory is cold-start (matched < threshold), return the
         *baseline* policy plus a ``COLD_START_FALLBACK`` adjustment.
      3. Otherwise, invoke each rule in config order. First rule that
         returns a non-None adjustment wins.
         - ``UPGRADE_ONE_LEVEL``: compute decision with the
           post-adjustment risk level and return it + adjustment.
         - anything else: return the baseline decision + adjustment.
      4. No rule fired → return the baseline decision and ``None``.

    The input ``governance_output`` is NEVER mutated.
    """
    query = _build_query_for_event(event_context)
    summary = memory.summarize(query, threshold=config.min_records_for_shift)

    # --- Baseline reference decision (static policy, unmodified input) ---
    baseline_decision = decide_policy(governance_output, config.base_policy_config)

    # --- Cold start ---
    if is_cold_start(summary.matched_records, config.min_records_for_shift):
        adj = build_cold_start_adjustment(
            risk_level=str(event_context.risk_level).strip().upper(),
            summary=summary,
            min_records_for_shift=config.min_records_for_shift,
        )
        return baseline_decision, adj

    # --- Rule evaluation ---
    for rule in config.rules:
        adjustment = rule(summary, event_context)
        if adjustment is None:
            continue

        if adjustment.adjustment_type == "UPGRADE_ONE_LEVEL":
            # Bounded action set invariant: exactly one-level shift.
            if adjustment.pre_adjustment_risk == adjustment.post_adjustment_risk:
                raise ValueError(
                    f"UPGRADE_ONE_LEVEL adjustment must have pre != post; "
                    f"rule_id={adjustment.rule_id}"
                )
            # Local copy; NEVER mutate governance_output.
            shadow = dict(governance_output)
            shadow["risk_level"] = adjustment.post_adjustment_risk
            adjusted_decision = decide_policy(shadow, config.base_policy_config)
            return adjusted_decision, adjustment

        # NO_ADJUSTMENT / COLD_START_FALLBACK reported by a rule: record
        # but do NOT change route. (COLD_START_FALLBACK normally comes
        # from the cold-start branch above, not from a rule.)
        return baseline_decision, adjustment

    # --- No rule fired ---
    return baseline_decision, None
