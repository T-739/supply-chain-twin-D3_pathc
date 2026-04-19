"""correlator/correlator_engine.py — Path C B2 Slice 2B pure matcher.

A single pure function, ``compute_correlation_context``, that takes
a finalized event stream and a current-index cursor and returns a
``CorrelationContext`` (or ``None`` if the correlator is disabled).

Determinism (roadmap §1.D + §2.D):
  - no wall-clock input, no uuid4, no datetime.now / time.time
  - iteration order is pattern-catalog declaration order, then
    ``window_start_ordinal`` ascending; ties broken by participant-
    id lexicographic order
  - the matcher is a pure function of (events, current_index, config)

Truth boundary:
  - the matcher reads only structural EventPayload fields:
    ``event_id``, ``event_type``, ``severity``, ``affected_entities``.
  - no governance natural-language fields are touched
  - no import from ``adaptive``, ``replan``, ``learning``, or
    ``session`` (enforced by the reverse-import scan and the
    no-NL-truth scan)

Pattern matching (Slice 2B):

  P1 ``ETA_PATH_COMPOUND``
    Fires at a current-index ``i`` iff:
      (a) ``events[i].event_type`` is in
          {CARRIER_DELAY_ESCALATION, WEATHER_WORSENING} AND
      (b) some earlier event in the window has the OTHER required
          type.
    Anchoring at the current index guarantees each compound is
    emitted exactly once across sliding windows — at the moment
    the second required participant arrives.

  P3 ``CARRIER_DOUBLE_HIT``
    Fires at a current-index ``i`` iff:
      (a) ``events[i].event_type`` is in
          {CARRIER_DELAY_ESCALATION, COMPLIANCE_HOLD} AND
      (b) the current event's ``affected_entities`` includes a
          carrier (``entity_type == "carrier"``) whose
          ``entity_id`` also appears, under the OTHER required
          type, somewhere earlier in the window.
    Multiple qualifying carriers (different ``entity_id``s) each
    produce their own signal. Ordering is ``entity_id``
    lexicographic ascending.

Slice 2B ships exactly P1 + P3. P2 ``SUPPLY_DEMAND_MISMATCH`` is
deferred (see ``correlator_patterns.py``). Adding a pattern is a
MINOR bump on ``CORRELATOR_PATTERN_ID`` + a same-PR registry
update.
"""

from __future__ import annotations

from typing import Optional

from event_schema import AffectedEntityRef, EventPayload, EventType

from correlator.correlator_config import CorrelatorConfig
from correlator.correlator_patterns import (
    P1_ETA_PATH_COMPOUND,
    P3_CARRIER_DOUBLE_HIT,
    PATTERN_DECLARATIONS,
    SEVERITY_HIGH_CONCURRENCE_SET,
    PatternDeclaration,
)
from correlator.correlator_schema import (
    CORRELATOR_MATCHED_CONDITION,
    CorrelationContext,
    CorrelationSignal,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_correlation_context(
    *,
    events: list[EventPayload],
    current_index: int,
    config: CorrelatorConfig,
) -> Optional[CorrelationContext]:
    """Compute the correlation sideband for the event at ``current_index``.

    Returns ``None`` when ``config.enable_correlator`` is False — the
    caller must then NOT attach a correlation_context (so the
    orchestrator's downstream consumers see the pre-B2 default of
    ``SessionEventRecord.correlation_context = None``).

    Returns a ``CorrelationContext`` (possibly with empty ``signals``)
    when enabled. An empty context means "ran, found nothing", which
    is semantically distinct from the disabled case.

    Parameters
    ----------
    events
        The full event stream in session order. Must be non-empty.
    current_index
        Index into ``events`` for the event whose sideband we are
        computing. Must satisfy ``0 <= current_index < len(events)``.
    config
        ``CorrelatorConfig`` with ``window_size`` and
        ``enabled_patterns``.
    """
    if not config.enable_correlator:
        return None

    if not isinstance(events, list):
        raise TypeError(
            f"events must be a list, got {type(events).__name__}"
        )
    if not events:
        raise ValueError("events must be non-empty")
    if not (0 <= current_index < len(events)):
        raise ValueError(
            f"current_index={current_index} out of range "
            f"[0, {len(events)})"
        )

    window_size = config.window_size
    window_start = max(0, current_index - window_size + 1)
    window_end = current_index
    window_events = events[window_start : window_end + 1]
    window_ordinals = list(range(window_start, window_end + 1))

    signals: list[CorrelationSignal] = []

    for decl in PATTERN_DECLARATIONS:
        if decl.pattern_id not in config.enabled_patterns:
            continue
        if decl is P1_ETA_PATH_COMPOUND:
            signals.extend(
                _match_eta_path_compound(
                    decl=decl,
                    window_events=window_events,
                    window_ordinals=window_ordinals,
                    current_ordinal=current_index,
                    window_size=window_size,
                )
            )
        elif decl is P3_CARRIER_DOUBLE_HIT:
            signals.extend(
                _match_carrier_double_hit(
                    decl=decl,
                    window_events=window_events,
                    window_ordinals=window_ordinals,
                    current_ordinal=current_index,
                    window_size=window_size,
                )
            )
        # Future patterns appended here in declaration order.

    return CorrelationContext(
        signals=signals,
        window_size=window_size,
        window_events_considered=len(window_events),
    )


# ---------------------------------------------------------------------------
# P1 — ETA_PATH_COMPOUND
# ---------------------------------------------------------------------------


def _match_eta_path_compound(
    *,
    decl: PatternDeclaration,
    window_events: list[EventPayload],
    window_ordinals: list[int],
    current_ordinal: int,
    window_size: int,
) -> list[CorrelationSignal]:
    """Emit at most one P1 signal, anchored at the current event.

    Fires iff the current event is of one of the two required types
    AND the window contains at least one event of the other required
    type.
    """
    current = window_events[-1]
    required = {
        EventType.CARRIER_DELAY_ESCALATION,
        EventType.WEATHER_WORSENING,
    }
    if current.event_type not in required:
        return []

    counterpart_type = (
        EventType.WEATHER_WORSENING
        if current.event_type is EventType.CARRIER_DELAY_ESCALATION
        else EventType.CARRIER_DELAY_ESCALATION
    )

    counterpart_indices: list[int] = []
    for idx_in_window, ev in enumerate(window_events):
        if idx_in_window == len(window_events) - 1:
            continue  # skip current
        if ev.event_type is counterpart_type:
            counterpart_indices.append(idx_in_window)

    if not counterpart_indices:
        return []

    # Participants: every event in the window whose type is one of
    # the two required types. Ordered by stream ordinal ascending.
    participant_pairs: list[tuple[int, EventPayload]] = [
        (window_ordinals[i], ev)
        for i, ev in enumerate(window_events)
        if ev.event_type in required
    ]
    participant_pairs.sort(key=lambda p: p[0])
    participant_event_ids = [ev.event_id for _, ev in participant_pairs]
    participant_ordinals = [o for o, _ in participant_pairs]
    participant_events = [ev for _, ev in participant_pairs]

    window_start_ordinal = participant_ordinals[0]
    window_end_ordinal = participant_ordinals[-1]

    matched_conditions: list[CORRELATOR_MATCHED_CONDITION] = ["SHARED_ETA_PATH"]
    if _is_stream_adjacent(participant_ordinals):
        matched_conditions.append("STREAM_ADJACENT")
    if _all_high_concurrence(participant_events):
        matched_conditions.append("SEVERITY_HIGH_CONCURRENCE")

    # P1 is the only entity-free pattern in Slice 2B: the shared
    # latent is the twin's planned_eta, not an AffectedEntityRef on
    # both sides. The landed contract allows shared_entities=[] only
    # when the pattern's declaration sets
    # allow_empty_shared_entities=True.
    shared_entities: list[AffectedEntityRef] = []

    return [
        CorrelationSignal(
            pattern_id=decl.pattern_id,
            triggering_event_id=current.event_id,
            participant_event_ids=participant_event_ids,
            shared_entities=shared_entities,
            window_start_ordinal=window_start_ordinal,
            window_end_ordinal=window_end_ordinal,
            window_size=window_size,
            matched_conditions=matched_conditions,
        )
    ]


# ---------------------------------------------------------------------------
# P3 — CARRIER_DOUBLE_HIT
# ---------------------------------------------------------------------------


def _match_carrier_double_hit(
    *,
    decl: PatternDeclaration,
    window_events: list[EventPayload],
    window_ordinals: list[int],
    current_ordinal: int,
    window_size: int,
) -> list[CorrelationSignal]:
    """Emit one P3 signal per carrier-id that has both required
    types inside the window, anchored at the current event.

    The current event must be of one of the two required types and
    must target at least one ``carrier`` entity. For each such
    carrier id, an earlier event of the OTHER required type in the
    window must also target the same carrier id. Each qualifying
    carrier-id yields one signal; ordering is ``entity_id``
    lexicographic ascending.
    """
    current = window_events[-1]
    required = {
        EventType.CARRIER_DELAY_ESCALATION,
        EventType.COMPLIANCE_HOLD,
    }
    if current.event_type not in required:
        return []

    counterpart_type = (
        EventType.COMPLIANCE_HOLD
        if current.event_type is EventType.CARRIER_DELAY_ESCALATION
        else EventType.CARRIER_DELAY_ESCALATION
    )

    current_carriers = {
        ref.entity_id
        for ref in current.affected_entities
        if ref.entity_type == "carrier"
    }
    if not current_carriers:
        return []

    # Collect counterpart events (other type) in window, excluding
    # current, keyed by their carrier ids.
    counterpart_events_by_carrier: dict[
        str, list[tuple[int, EventPayload]]
    ] = {}
    for idx_in_window, ev in enumerate(window_events):
        if idx_in_window == len(window_events) - 1:
            continue  # skip current
        if ev.event_type is not counterpart_type:
            continue
        for ref in ev.affected_entities:
            if ref.entity_type != "carrier":
                continue
            if ref.entity_id not in current_carriers:
                continue
            counterpart_events_by_carrier.setdefault(
                ref.entity_id, []
            ).append((window_ordinals[idx_in_window], ev))

    # For each qualifying carrier id, emit one signal. Deterministic
    # emission: ascending entity_id.
    signals: list[CorrelationSignal] = []
    for carrier_id in sorted(counterpart_events_by_carrier.keys()):
        counterparts = counterpart_events_by_carrier[carrier_id]
        # Participant list: the counterpart events that matched
        # this carrier id + the current event.
        pair_items: list[tuple[int, EventPayload]] = list(counterparts)
        pair_items.append((current_ordinal, current))
        pair_items.sort(key=lambda p: p[0])
        participant_event_ids = [ev.event_id for _, ev in pair_items]
        participant_ordinals = [o for o, _ in pair_items]
        participant_events = [ev for _, ev in pair_items]

        window_start_ordinal = participant_ordinals[0]
        window_end_ordinal = participant_ordinals[-1]

        shared_entities: list[AffectedEntityRef] = [
            AffectedEntityRef(
                entity_type="carrier",
                entity_id=carrier_id,
            )
        ]

        matched_conditions: list[CORRELATOR_MATCHED_CONDITION] = ["SAME_ENTITY_ID"]
        if _is_stream_adjacent(participant_ordinals):
            matched_conditions.append("STREAM_ADJACENT")
        if _all_high_concurrence(participant_events):
            matched_conditions.append("SEVERITY_HIGH_CONCURRENCE")

        signals.append(
            CorrelationSignal(
                pattern_id=decl.pattern_id,
                triggering_event_id=current.event_id,
                participant_event_ids=participant_event_ids,
                shared_entities=shared_entities,
                window_start_ordinal=window_start_ordinal,
                window_end_ordinal=window_end_ordinal,
                window_size=window_size,
                matched_conditions=matched_conditions,
            )
        )
    return signals


# ---------------------------------------------------------------------------
# Shared helpers (pure)
# ---------------------------------------------------------------------------


def _is_stream_adjacent(ordinals: list[int]) -> bool:
    """True iff the sorted ordinals form a contiguous run."""
    if len(ordinals) < 2:
        return False
    srt = sorted(ordinals)
    return all(srt[i + 1] - srt[i] == 1 for i in range(len(srt) - 1))


def _all_high_concurrence(participants: list[EventPayload]) -> bool:
    """True iff every participant's severity is in the high-
    concurrence set (MEDIUM or HIGH)."""
    if not participants:
        return False
    return all(p.severity in SEVERITY_HIGH_CONCURRENCE_SET for p in participants)
