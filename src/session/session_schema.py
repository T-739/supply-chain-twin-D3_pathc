"""session_schema.py — Path C Phase 0 schema skeletons.

Classes only. No session_manager, no KPI computation, no session
compare. All runtime logic lands in Phase 1 / Phase 3.

Dual-track contract (roadmap §0.3): GovernanceTruthRef and
EffectiveDecisionRef are *always* both present on a SessionEventRecord
and are never collapsed into one value. Divergence is explained by
``adaptive_adjustment``.

This module does NOT:
  - Import evaluation.py or action_code_mapper.py
  - Read or write data/cases/*.json
  - Call datetime.now / utcnow / time.time / uuid.uuid4
  - Mutate baseline_event_result (it is embedded verbatim)
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from adaptive.adaptive_schema import AdaptivePolicyAdjustment
from correlator.correlator_schema import CorrelationContext
from replan.replan_schema import ReplanAttemptRecord, ReplanTriggerRecord


_SESSION_SCHEMA_VERSION = "1.0"

# SessionEventRecord MINOR bump: 1.1 → 1.2 for B2 Slice 2A (Path C).
# The bump is additive: one new field `correlation_context` is
# optional with a safe `None` default. `None` means the correlator
# did not run; a present `CorrelationContext` with empty `signals`
# means the correlator ran and found nothing. Existing consumers
# that do not read or write this field observe no behavioral
# change; the version string change is visible in serialized
# output so downstream readers can key off it if/when they opt in.
#
# Prior bump (1.0 → 1.1, B1 Slice 1) added optional
# `replan_trace` and `replan_triggers`, also None-defaulted.
_SESSION_EVENT_RECORD_SCHEMA_VERSION = "1.2"

# SessionKPIs MINOR bump: 1.0 → 1.1 for B1 Slice 4 (KPI / compare /
# report integration). Bump is strictly additive — five new
# replan-aware fields with safe defaults (zero-count ints and
# None-rate floats). Pre-B1 artifacts constructed with the defaults
# produce the same analytical numbers they did before the bump.
_SESSION_KPIS_SCHEMA_VERSION = "1.1"


SessionMode = Literal["BASELINE_STATIC", "PATH_C_COLD", "PATH_C_WARM"]

PolicyRouteSource = Literal[
    "baseline_static",
    "adaptive_adjusted",
    "cold_start_fallback",
]

FinalRoute = Literal["AUTO_EXECUTE", "HUMAN_REQUIRED"]

ActionTaken = Literal["EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"]

ExecutionStatus = Literal[
    "executed",
    "executed_via_demo_override",
    "awaiting_human_review",
    "execution_failed",
    "unknown_route",
    "preflight_failed",  # Path-C-only overlay status
]


class GovernanceTruthRef(BaseModel):
    """Frozen snapshot of governance_agent output. Read-only mirror."""

    model_config = ConfigDict(extra="forbid")

    risk_level: str
    recommended_candidate_type: str
    schema_version: str = Field(default=_SESSION_SCHEMA_VERSION)


class EffectiveDecisionRef(BaseModel):
    """What the system actually did after routing and adaptive overlay.

    In BASELINE_STATIC, every field here equals the Path B record by
    construction. In PATH_C_* modes, Path-C-only statuses (notably
    ``preflight_failed``) surface ONLY here, never inside
    baseline_event_result.
    """

    model_config = ConfigDict(extra="forbid")

    effective_risk: str
    final_route: FinalRoute
    action_taken: Optional[ActionTaken] = None
    execution_status: ExecutionStatus
    schema_version: str = Field(default=_SESSION_SCHEMA_VERSION)


class SessionEventRecord(BaseModel):
    """Path C overlay around one Path B event_result.

    ``baseline_event_result`` is the *untouched* Path B dict. No Path C
    code is permitted to mutate it. Consumers that want Path B semantics
    read ``baseline_event_result``; consumers that want Path C overlay
    read the sibling overlay fields.

    B1 overlay (additive, Slice 1 contracts only):
      - ``replan_trace`` carries the per-attempt record of a bounded
        second reasoning cycle, when (and only when) replan is enabled
        AND fires. Default ``None`` means no replan cycle ran — the
        effective decision reflects the first (and only) attempt.
      - ``replan_triggers`` carries the auditable trigger-rule
        decisions evaluated against the first attempt. Default ``None``
        means replan was not enabled or no rule was evaluated.
      - ``effective_decision`` continues to reflect the FINAL attempt,
        so the dual-track contract is preserved unchanged when replan
        fires (GovernanceTruthRef vs EffectiveDecisionRef never
        collapse).

    B2 overlay (additive, Slice 2A contracts only):
      - ``correlation_context`` carries the event-correlator's
        sideband output for this stream position. Default ``None``
        means the correlator did not run (``enable_correlator=False``
        or the hook has not been wired). A present
        ``CorrelationContext`` with empty ``signals`` means the
        correlator ran and found no matches. Correlator output is
        observability-only in Slice 2A: it does NOT alter
        ``effective_decision``, ``adaptive_adjustment``, or any
        replan field.
    """

    model_config = ConfigDict(extra="forbid")

    baseline_event_result: dict[str, Any]
    session_id: str
    mode: SessionMode
    policy_route_source: PolicyRouteSource
    adaptive_adjustment: Optional[AdaptivePolicyAdjustment] = None
    governance_truth: GovernanceTruthRef
    effective_decision: EffectiveDecisionRef
    memory_record_id: Optional[str] = None
    replan_trace: Optional[list[ReplanAttemptRecord]] = None
    replan_triggers: Optional[list[ReplanTriggerRecord]] = None
    correlation_context: Optional[CorrelationContext] = None
    notes: str = ""
    schema_version: str = Field(default=_SESSION_EVENT_RECORD_SCHEMA_VERSION)


class SessionConfig(BaseModel):
    """Configuration inputs to a Path C session run.

    Phase 0 freezes the shape; Phase 1 wires values through
    event_loop_c.run_session.
    """

    model_config = ConfigDict(extra="forbid")

    seed: int
    mode: SessionMode
    events_source: str
    initial_memory_digest: str = ""
    schema_version: str = Field(default=_SESSION_SCHEMA_VERSION)


class SessionKPIs(BaseModel):
    """Deterministic KPI envelope. Phase 3 populates numeric values.

    B1 Slice 4 additive fields (``replan_*``) are all safe-default
    and describe the bounded-replan layer. They appear on every
    artifact (zero/None for non-replan sessions), so pre-B1 KPI
    consumers that don't read them observe no change. Replan-
    disabled sessions have ``replan_fire_count == 0`` and every rate
    ``None`` (zero-denominator rule).
    """

    model_config = ConfigDict(extra="forbid")

    events_observed: int = 0
    events_with_outcome: int = 0
    events_skipped: int = 0
    events_failed: int = 0
    events_processed: int = 0
    auto_execute_success_rate: Optional[float] = None
    sla_preservation_rate: Optional[float] = None
    total_cost: float = 0.0
    avg_cost: Optional[float] = None
    known_outcome_coverage: Optional[float] = None
    # --- B1 Slice 4 additive replan-aware fields ---
    replan_events_observed: int = 0
    replan_fire_count: int = 0
    replan_trigger_rate: Optional[float] = None
    replan_success_count: int = 0
    replan_recovery_rate: Optional[float] = None
    schema_version: str = Field(default=_SESSION_KPIS_SCHEMA_VERSION)


class SessionArtifact(BaseModel):
    """Aggregate session artifact. Phase 1 persists; Phase 3 reports."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    config: SessionConfig
    event_records: list[SessionEventRecord] = Field(default_factory=list)
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)
    kpis: SessionKPIs = Field(default_factory=SessionKPIs)
    schema_versions: dict[str, str] = Field(default_factory=dict)
    notes: str = ""
    schema_version: str = Field(default=_SESSION_SCHEMA_VERSION)
