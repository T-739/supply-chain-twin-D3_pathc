"""replan/replan_schema.py — Path C B1 Slice 1 schema skeletons.

Classes and constants only. No runtime behavior — no estimator, no
trigger function, no orchestrator. Matching entries live in
``PATH_C_SCHEMA_REGISTRY.md`` under the B1 Slice 1 section.

Owner-fixed decisions (see docs/B1_REPLAN_CONTRACT_DRAFT.md §7):

  D1 : expected-cost range is a cost_output-derived overlay. The
       provenance literal ``"cost_output_derived_overlay"`` is the
       only accepted value of ``ExpectedOutcomeRef.range_source`` in
       Slice 1. Natural-language governance fields
       (``cost_summary``, ``confidence_note``, ``rationale_trace``,
       ``situational_explanation``, ``alternative_actions``) are
       forbidden as numeric trigger truth — enforced structurally
       here by the closed Literal type, and by the source-scan test
       ``tests/test_replan_contract_no_nl_truth.py``.

  D3 : both absolute and relative cost-deviation are carried as
       structured fields. The *decision* logic is not implemented
       in Slice 1.

  D5 : B1's eventual second cycle is a full reasoning cycle
       (operations → cost → governance → adaptive policy gate →
       preflight → execute_action). The per-attempt record here
       carries the *effective per-attempt operational outcome*, not
       intermediate agent outputs. No mid-event memory append/read
       is designed in.

This module does NOT:
  - import evaluation.py or action_code_mapper.py
  - read or write data/cases/*.json
  - call datetime.now / utcnow / time.time / uuid.uuid4
  - mutate governance_output, _governance_meta, baseline_event_result,
    or any Path B contract
  - import session.session_schema (avoids circular import; ReplanAttemptRecord
    carries per-attempt operational fields inline rather than reusing
    EffectiveDecisionRef as a nested model)
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from adaptive.adaptive_schema import AdaptivePolicyAdjustment


REPLAN_SCHEMA_VERSION: str = "1.0"


# ---------------------------------------------------------------------------
# Provenance literal for the expected-cost-range overlay (D1)
# ---------------------------------------------------------------------------

# Closed set. Slice 1 admits exactly one source. Any future source MUST
# arrive as an owner-approved MINOR bump on this Literal and a matching
# registry update.
EXPECTED_COST_RANGE_SOURCE_LITERAL = Literal["cost_output_derived_overlay"]


# ---------------------------------------------------------------------------
# Trigger taxonomy (D3 + structural explainability)
# ---------------------------------------------------------------------------

ReplanTriggerType = Literal[
    "NO_TRIGGER",          # rule evaluated; no replan warranted
    "COST_DEVIATION",      # realized cost outside expected range
    "SLA_DEVIATION",       # expected SLA preserved; realized SLA missed
    "EXECUTION_FAILED",    # execute_action raised during first attempt
    "PREFLIGHT_FAILED",    # preflight rejected the first attempt
]

# Per-attempt operational-outcome fields mirror the closed Literals in
# session_schema.py to keep dual-track consistent. Redefined here
# (not imported) to break the circular import with session_schema.
_REPLAN_FINAL_ROUTE = Literal["AUTO_EXECUTE", "HUMAN_REQUIRED"]
_REPLAN_ACTION_TAKEN = Literal["EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"]
_REPLAN_EXECUTION_STATUS = Literal[
    "executed",
    "executed_via_demo_override",
    "awaiting_human_review",
    "execution_failed",
    "unknown_route",
    "preflight_failed",
]


# ---------------------------------------------------------------------------
# ExpectedOutcomeRef
# ---------------------------------------------------------------------------


class ExpectedOutcomeRef(BaseModel):
    """Structured expected-outcome reference for a single execution attempt.

    Produced by a future deterministic projector over the Cost Agent's
    structured output (``CostOutput.cost_estimates``), keyed by the
    governance identity (``recommended_candidate_type`` /
    ``recommended_candidate_id``). Slice 1 freezes the shape; Slice 2
    (estimator) fills the values.

    Invariants (structural):
      - ``expected_cost_min`` >= 0
      - ``expected_cost_max`` >= ``expected_cost_min``
      - ``range_source`` is a closed Literal — the only admitted value
        is ``"cost_output_derived_overlay"``. Natural-language sources
        are not representable.
    """

    model_config = ConfigDict(extra="forbid")

    expected_cost_min: float
    expected_cost_max: float
    expected_sla_preserved: bool
    range_source: EXPECTED_COST_RANGE_SOURCE_LITERAL = (
        "cost_output_derived_overlay"
    )
    estimator_id: str
    estimator_signature: str = ""
    schema_version: str = Field(default=REPLAN_SCHEMA_VERSION)

    @field_validator("expected_cost_min")
    @classmethod
    def _cost_min_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"expected_cost_min must be >= 0, got {v}")
        return float(v)

    @field_validator("expected_cost_max")
    @classmethod
    def _cost_max_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"expected_cost_max must be >= 0, got {v}")
        return float(v)

    @field_validator("estimator_id")
    @classmethod
    def _estimator_id_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("estimator_id must be a non-empty string")
        return v


# ---------------------------------------------------------------------------
# ReplanTriggerRecord
# ---------------------------------------------------------------------------


class ReplanTriggerRecord(BaseModel):
    """Structured, auditable record of one replan-trigger decision.

    Parallel in spirit to ``AdaptivePolicyAdjustment`` but orthogonal
    in role: the trigger decides whether a second reasoning cycle is
    warranted after an execution attempt. Slice 1 freezes the shape;
    Slice 2 (trigger function) emits values into this record.

    ``deviation_measurement`` carries numeric facts only (floats,
    ints, bools). It never carries natural-language strings.
    """

    model_config = ConfigDict(extra="forbid")

    trigger_rule_id: str
    trigger_type: ReplanTriggerType
    attempt_index: int
    deviation_measurement: dict[str, float | int | bool] = Field(
        default_factory=dict
    )
    expected_outcome_ref: Optional[ExpectedOutcomeRef] = None
    realized_cost: Optional[float] = None
    realized_sla_preserved: Optional[bool] = None
    notes: str = ""
    schema_version: str = Field(default=REPLAN_SCHEMA_VERSION)

    @field_validator("trigger_rule_id")
    @classmethod
    def _rule_id_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("trigger_rule_id must be a non-empty string")
        return v

    @field_validator("attempt_index")
    @classmethod
    def _attempt_index_bounded(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise ValueError(f"attempt_index must be a non-negative int, got {v!r}")
        return int(v)


# ---------------------------------------------------------------------------
# ReplanAttemptRecord
# ---------------------------------------------------------------------------


class ReplanAttemptRecord(BaseModel):
    """One attempt in a bounded replan cycle.

    Slice 1 freezes the shape only. Slice 2+ populates instances.

    Per-attempt operational outcome is carried inline rather than by
    nesting ``EffectiveDecisionRef`` — this avoids a circular import
    between ``replan_schema`` and ``session.session_schema`` while
    preserving the exact Literal domains for route / action /
    execution_status.

    The authoritative, session-observable ``EffectiveDecisionRef``
    on ``SessionEventRecord`` still reflects the *final* attempt;
    per-attempt intermediate outcomes live here only for audit.
    """

    model_config = ConfigDict(extra="forbid")

    attempt_index: int
    attempt_final_route: _REPLAN_FINAL_ROUTE
    attempt_action_taken: Optional[_REPLAN_ACTION_TAKEN] = None
    attempt_execution_status: _REPLAN_EXECUTION_STATUS
    execution_outcome: Optional[dict[str, Any]] = None
    adaptive_adjustment: Optional[AdaptivePolicyAdjustment] = None
    expected_outcome: Optional[ExpectedOutcomeRef] = None
    trigger: ReplanTriggerRecord
    notes: str = ""
    schema_version: str = Field(default=REPLAN_SCHEMA_VERSION)

    @field_validator("attempt_index")
    @classmethod
    def _attempt_index_non_negative(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise ValueError(
                f"attempt_index must be a non-negative int, got {v!r}"
            )
        return int(v)
