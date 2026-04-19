"""correlator/correlator_patterns.py — Path C B2 Slice 2A pattern
declarations.

Declarations and constants ONLY. No matching function. A future
slice (2B) will add ``correlator_engine.py`` that imports
``PATTERN_DECLARATIONS`` here and emits ``CorrelationSignal`` values.

Owner-fixed decisions (see docs/B2_CORRELATOR_BOUNDARY.md §12 and
docs/B2_CORRELATOR_CONTRACT_DRAFT.md §5, §6, §7):

  D5 : Closed pattern catalog. Slice 2A lands P1 and P3 only.

Deferred from Slice 2A:

  * P2 SUPPLY_DEMAND_MISMATCH — the design draft required a static
    zone ↔ warehouse topology table to relate a ``DEMAND_SPIKE`` on
    a customer zone to an ``INVENTORY_DISCREPANCY`` on its serving
    warehouse. That table is a fragile source of truth that would
    couple the correlator to the specific 2x2x2x2 baseline network.
    The owner constraint for Slice 2A is to avoid introducing
    fragile static truth tables; P2 therefore stays out of the
    landed default catalog. Adding P2 later is a MINOR bump on
    ``CORRELATOR_PATTERN_ID`` and on ``KNOWN_CORRELATOR_PATTERN_IDS``.

  * P4 CANCELLATION_AFTER_SPIKE — deferred (low signal-to-noise
    under the current demo stream); tracked as O2 in the contract
    draft.

Structural severity threshold:

  * ``SEVERITY_HIGH_CONCURRENCE`` — a pattern may list this
    matched-condition iff ALL participating events have
    severity in ``SEVERITY_HIGH_CONCURRENCE_SET``. The threshold
    is a module constant (not a free parameter) — changing it is
    a MINOR bump.

This module does NOT:
  - import evaluation.py or action_code_mapper.py
  - read or write data/cases/*.json
  - call datetime.now / utcnow / time.time / uuid.uuid4
  - import from ``adaptive``, ``replan``, ``learning``, or
    ``session``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from event_schema import EventSeverity, EventType

from correlator.correlator_schema import (
    CORRELATOR_MATCHED_CONDITION,
    CORRELATOR_PATTERN_ID,
)


# ---------------------------------------------------------------------------
# Severity threshold (structural; not a free parameter)
# ---------------------------------------------------------------------------

#: Participating events must ALL have a severity in this set for a
#: pattern to legitimately emit ``SEVERITY_HIGH_CONCURRENCE``.
SEVERITY_HIGH_CONCURRENCE_SET: Final[frozenset[EventSeverity]] = frozenset({
    EventSeverity.MEDIUM,
    EventSeverity.HIGH,
})


# ---------------------------------------------------------------------------
# Pattern declaration record (declaration only; no behavior)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatternDeclaration:
    """Immutable description of a correlation pattern.

    A ``PatternDeclaration`` tells a future match function WHAT to
    look for. It does not implement the match.

    Fields
    ------
    pattern_id
        Member of ``CORRELATOR_PATTERN_ID``.
    description
        Short human-readable intent. NOT used as authoritative truth;
        emitted only to boundary docs and to the registry.
    required_event_types
        The multiset of ``EventType`` values that must all be present
        inside the window for this pattern to fire. Represented as a
        tuple for deterministic iteration. Duplicates are significant
        (e.g. two carrier-delays would be ``(CARRIER_DELAY_ESCALATION,
        CARRIER_DELAY_ESCALATION)``) — Slice 2A ships only
        ``len==2`` patterns but the structure admits future growth.
    default_matched_conditions
        The closed subset of ``CORRELATOR_MATCHED_CONDITION`` values
        that this pattern is ALLOWED to emit. The match function in
        Slice 2B MUST NOT emit any condition outside this set.
    allow_empty_shared_entities
        True iff the pattern is inherently entity-free (its evidence
        lives on a shared latent, not on an ``AffectedEntityRef``
        that both participants carry). Only P1 has this property in
        Slice 2A.
    """

    pattern_id: CORRELATOR_PATTERN_ID
    description: str
    required_event_types: tuple[EventType, ...]
    default_matched_conditions: tuple[CORRELATOR_MATCHED_CONDITION, ...]
    allow_empty_shared_entities: bool


# ---------------------------------------------------------------------------
# Pattern catalog (Slice 2A)
# ---------------------------------------------------------------------------

#: P1 — ``ETA_PATH_COMPOUND``. Carrier delay + weather worsening
#: stacking pressure on planned ETA. Entity-free (the shared latent
#: is the twin's planned_eta).
P1_ETA_PATH_COMPOUND: Final[PatternDeclaration] = PatternDeclaration(
    pattern_id="ETA_PATH_COMPOUND",
    description=(
        "Carrier delay escalation and weather worsening observed "
        "inside the same window, both pressuring planned ETA."
    ),
    required_event_types=(
        EventType.CARRIER_DELAY_ESCALATION,
        EventType.WEATHER_WORSENING,
    ),
    default_matched_conditions=(
        "SHARED_ETA_PATH",
        "STREAM_ADJACENT",
        "SEVERITY_HIGH_CONCURRENCE",
    ),
    allow_empty_shared_entities=True,
)


#: P3 — ``CARRIER_DOUBLE_HIT``. Two qualitatively different shocks
#: on the same carrier entity (delay + compliance hold).
P3_CARRIER_DOUBLE_HIT: Final[PatternDeclaration] = PatternDeclaration(
    pattern_id="CARRIER_DOUBLE_HIT",
    description=(
        "Carrier delay escalation and compliance hold observed on "
        "the same carrier entity inside the same window."
    ),
    required_event_types=(
        EventType.CARRIER_DELAY_ESCALATION,
        EventType.COMPLIANCE_HOLD,
    ),
    default_matched_conditions=(
        "SAME_ENTITY_ID",
        "STREAM_ADJACENT",
        "SEVERITY_HIGH_CONCURRENCE",
    ),
    allow_empty_shared_entities=False,
)


#: Canonical, declaration-ordered catalog. The match function in
#: Slice 2B MUST iterate this tuple in order so that signal
#: emission is deterministic.
PATTERN_DECLARATIONS: Final[tuple[PatternDeclaration, ...]] = (
    P1_ETA_PATH_COMPOUND,
    P3_CARRIER_DOUBLE_HIT,
)


#: Convenience re-export: the pattern ids in declaration order.
#: ``KNOWN_CORRELATOR_PATTERN_IDS`` in ``correlator_config`` must
#: equal ``frozenset(PATTERN_IDS)``; the frozen-schema test asserts
#: this.
PATTERN_IDS: Final[tuple[str, ...]] = tuple(
    d.pattern_id for d in PATTERN_DECLARATIONS
)
