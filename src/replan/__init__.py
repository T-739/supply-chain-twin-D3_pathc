"""replan/ — Path C B1 bounded-replan subpackage (Slice 1: contracts only).

Slice 1 scope is intentionally *contracts only*. This subpackage
exposes pydantic schemas and configuration constants used by future
B1 slices (expected-outcome estimator, trigger function, bounded
orchestration wrapper). It contains no runtime trigger logic, no
orchestration, and no I/O.

Design anchors (see docs/B1_REPLAN_BOUNDARY.md,
docs/B1_REPLAN_CONTRACT_DRAFT.md, docs/B1_REPLAN_FILE_MAP.md):

  - ``expected_cost_range`` is a cost_output-derived overlay — never
    parsed from natural-language governance fields, never an extension
    of ``GovernanceOutput`` or ``_governance_meta``.
  - ``MAX_REPLAN_ATTEMPTS = 1``. Bounded second reasoning cycle only.
  - Memory remains final-attempt-only. No per-attempt ``MemoryRecord``.
  - The Path B raw shadow (``SessionEventRecord.baseline_event_result``)
    is never mutated.
  - The dual-track rule stands: ``GovernanceTruthRef`` reflects the
    pre-replan governance identity; ``EffectiveDecisionRef`` on the
    primary ``SessionEventRecord`` reflects the final attempt.
  - Replan is disabled by default (``ReplanConfig.enable_replan=False``);
    this slice does not wire replan into any runtime path.

This module does NOT:
  - import ``evaluation`` or ``action_code_mapper``
  - read ``data/cases/*.json``
  - call ``datetime.now`` / ``utcnow`` / ``time.time`` / ``uuid.uuid4``
"""

from replan.expected_outcome import ESTIMATOR_ID, estimate_expected_outcome
from replan.replan_config import (
    MAX_REPLAN_ATTEMPTS,
    KNOWN_TRIGGER_RULE_IDS,
    ExpectedCostRangeSource,
    ReplanConfig,
)
from replan.replan_orchestrator import ReplanCycleResult, run_replan_cycle
from replan.replan_schema import (
    EXPECTED_COST_RANGE_SOURCE_LITERAL,
    REPLAN_SCHEMA_VERSION,
    ExpectedOutcomeRef,
    ReplanAttemptRecord,
    ReplanTriggerRecord,
    ReplanTriggerType,
)
from replan.replan_trigger import decide_replan_trigger

__all__ = [
    "ESTIMATOR_ID",
    "EXPECTED_COST_RANGE_SOURCE_LITERAL",
    "ExpectedCostRangeSource",
    "ExpectedOutcomeRef",
    "KNOWN_TRIGGER_RULE_IDS",
    "MAX_REPLAN_ATTEMPTS",
    "REPLAN_SCHEMA_VERSION",
    "ReplanAttemptRecord",
    "ReplanConfig",
    "ReplanCycleResult",
    "ReplanTriggerRecord",
    "ReplanTriggerType",
    "decide_replan_trigger",
    "estimate_expected_outcome",
    "run_replan_cycle",
]
