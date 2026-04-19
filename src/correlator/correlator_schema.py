"""correlator/correlator_schema.py — Path C B2 Slice 2A schema skeletons.

Classes + closed Literals only. No matching logic, no runtime hook.
Matching entries live in ``PATH_C_SCHEMA_REGISTRY.md`` under the
B2 Slice 2A section.

Owner-fixed decisions (see docs/B2_CORRELATOR_BOUNDARY.md §12 and
docs/B2_CORRELATOR_CONTRACT_DRAFT.md §7):

  D1 : First cut is a ``correlation_context`` sideband. No
       ``EventType`` extension, no synthetic compound event.

  D2 : Placement A — ``SessionEventRecord`` gains one optional
       ``correlation_context`` field (MINOR bump 1.1 → 1.2). No
       sibling artifact.

  D3 : Slice 1/2A is observability-only; ``SessionKPIs`` is NOT
       bumped. No KPI fields added here.

  D4 : Window is an event-stream ordinal window, not a wall-clock
       window. ``window_size`` is an integer config carried on
       every emitted signal for audit.

  D5 : Closed pattern catalog — Slice 2A lands P1 and P3 only
       (see ``correlator_patterns.py``). P2 SUPPLY_DEMAND_MISMATCH
       is deferred until a non-fragile topology source is agreed
       (it would currently require a static truth table — see the
       deferral notice in ``correlator_patterns.py``).

Structural explainability (enforced here):
  - every ``CorrelationSignal`` carries a ``triggering_event_id``
    — the event whose arrival in the stream caused the signal to
    be emitted. It MUST appear in ``participant_event_ids``;
  - ``participant_event_ids`` has length >= 2;
  - ``matched_conditions`` is non-empty;
  - no free-text explanation field, no confidence/probability,
    no cost/SLA outcome field.

This module does NOT:
  - import evaluation.py or action_code_mapper.py
  - read or write data/cases/*.json
  - call datetime.now / utcnow / time.time / uuid.uuid4
  - mutate governance_output, _governance_meta, or any Path B
    contract
  - import from ``adaptive``, ``replan``, ``learning``, or
    ``session`` — correlator is a standalone overlay.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from event_schema import AffectedEntityRef


CORRELATOR_SCHEMA_VERSION: str = "1.0"


# ---------------------------------------------------------------------------
# Closed Literals (D5, structural explainability)
# ---------------------------------------------------------------------------

#: Closed pattern-id set. Slice 2A ships exactly two patterns
#: (``ETA_PATH_COMPOUND`` and ``CARRIER_DOUBLE_HIT``).
#: Adding a pattern is a MINOR bump on this Literal and a same-PR
#: registry update.
CORRELATOR_PATTERN_ID = Literal[
    "ETA_PATH_COMPOUND",
    "CARRIER_DOUBLE_HIT",
]

#: Closed matched-condition vocabulary. Each ``CorrelationSignal``
#: carries a non-empty subset of these values to structurally
#: explain why the pattern fired. Opening this set is a MINOR bump.
CORRELATOR_MATCHED_CONDITION = Literal[
    "SHARED_ETA_PATH",
    "SAME_ENTITY_ID",
    "STREAM_ADJACENT",
    "SEVERITY_HIGH_CONCURRENCE",
]


# ---------------------------------------------------------------------------
# CorrelationSignal
# ---------------------------------------------------------------------------


class CorrelationSignal(BaseModel):
    """Structured evidence for a single matched compound pattern.

    A single correlation match produces exactly one
    ``CorrelationSignal``. If two distinct patterns match on the same
    event, two distinct signals are emitted. There is no "compound
    signal" that merges multiple patterns.

    Invariants (structural):
      - ``len(participant_event_ids) >= 2``
      - ``triggering_event_id in participant_event_ids``
      - ``window_end_ordinal >= window_start_ordinal``
      - ``window_end_ordinal - window_start_ordinal + 1 <= window_size``
      - ``matched_conditions`` is non-empty
      - every ``matched_conditions`` entry is a member of
        ``CORRELATOR_MATCHED_CONDITION``
    """

    model_config = ConfigDict(extra="forbid")

    pattern_id: CORRELATOR_PATTERN_ID
    triggering_event_id: str
    participant_event_ids: list[str]
    shared_entities: list[AffectedEntityRef] = Field(default_factory=list)
    window_start_ordinal: int
    window_end_ordinal: int
    window_size: int
    matched_conditions: list[CORRELATOR_MATCHED_CONDITION]
    schema_version: str = Field(default=CORRELATOR_SCHEMA_VERSION)

    @field_validator("triggering_event_id")
    @classmethod
    def _triggering_event_id_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("triggering_event_id must be a non-empty string")
        return v

    @field_validator("participant_event_ids")
    @classmethod
    def _participants_min_two_non_empty(cls, v: list[str]) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("participant_event_ids must be a list")
        if len(v) < 2:
            raise ValueError(
                "participant_event_ids must contain at least 2 event ids"
            )
        for eid in v:
            if not isinstance(eid, str) or not eid.strip():
                raise ValueError(
                    "every participant_event_ids entry must be a "
                    "non-empty string"
                )
        return v

    @field_validator("window_start_ordinal")
    @classmethod
    def _start_non_negative(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("window_start_ordinal must be an int")
        if v < 0:
            raise ValueError(
                f"window_start_ordinal must be >= 0, got {v}"
            )
        return v

    @field_validator("window_end_ordinal")
    @classmethod
    def _end_non_negative(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("window_end_ordinal must be an int")
        if v < 0:
            raise ValueError(
                f"window_end_ordinal must be >= 0, got {v}"
            )
        return v

    @field_validator("window_size")
    @classmethod
    def _window_size_positive(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("window_size must be an int")
        if v < 1:
            raise ValueError(f"window_size must be >= 1, got {v}")
        return v

    @field_validator("matched_conditions")
    @classmethod
    def _conditions_non_empty(
        cls, v: list[str]
    ) -> list[str]:
        if not isinstance(v, list) or len(v) == 0:
            raise ValueError("matched_conditions must be non-empty")
        return v

    def model_post_init(self, __context) -> None:
        # Cross-field invariants that can only run after all fields
        # are bound. Raised as ValueError to surface via
        # ValidationError at construction time.
        if self.window_end_ordinal < self.window_start_ordinal:
            raise ValueError(
                f"window_end_ordinal ({self.window_end_ordinal}) must be "
                f">= window_start_ordinal ({self.window_start_ordinal})"
            )
        span = self.window_end_ordinal - self.window_start_ordinal + 1
        if span > self.window_size:
            raise ValueError(
                f"window span ({span}) exceeds window_size "
                f"({self.window_size})"
            )
        if self.triggering_event_id not in self.participant_event_ids:
            raise ValueError(
                f"triggering_event_id {self.triggering_event_id!r} must "
                f"appear in participant_event_ids"
            )


# ---------------------------------------------------------------------------
# CorrelationContext
# ---------------------------------------------------------------------------


class CorrelationContext(BaseModel):
    """Per-event sideband carrying the correlator's findings for one
    stream position.

    The distinction between ``correlation_context = None`` on
    ``SessionEventRecord`` and a ``CorrelationContext`` with
    ``signals == []`` is semantic:

      - ``correlation_context = None`` — correlator did not run
        (``enable_correlator=False`` or slice has not wired the hook).
      - ``CorrelationContext(signals=[], ...)`` — correlator ran and
        found no matches inside the window at this stream position.

    ``window_events_considered`` is the count of finalized session
    records actually inspected (<= ``window_size``). It is recorded
    for audit so a reader can tell "no matches" apart from "no
    window data yet".

    Ordering of ``signals`` is deterministic: pattern-catalog
    declaration order first, then ``window_start_ordinal`` ascending.
    """

    model_config = ConfigDict(extra="forbid")

    signals: list[CorrelationSignal] = Field(default_factory=list)
    window_size: int
    window_events_considered: int
    schema_version: str = Field(default=CORRELATOR_SCHEMA_VERSION)

    @field_validator("window_size")
    @classmethod
    def _window_size_positive(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("window_size must be an int")
        if v < 1:
            raise ValueError(f"window_size must be >= 1, got {v}")
        return v

    @field_validator("window_events_considered")
    @classmethod
    def _considered_non_negative(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("window_events_considered must be an int")
        if v < 0:
            raise ValueError(
                f"window_events_considered must be >= 0, got {v}"
            )
        return v

    def model_post_init(self, __context) -> None:
        if self.window_events_considered > self.window_size:
            raise ValueError(
                f"window_events_considered ({self.window_events_considered}) "
                f"cannot exceed window_size ({self.window_size})"
            )
