"""correlator/ — Path C B2 event-correlator subpackage (Slice 2A: contracts only).

Slice 2A scope is intentionally *contracts only*. This subpackage
exposes pydantic schemas, a configuration dataclass, and a closed
pattern-declaration catalog used by future B2 slices (match engine,
event_loop_c integration, compare-report integration). It contains
NO matching logic, NO orchestration, and NO I/O.

Design anchors (see docs/B2_CORRELATOR_BOUNDARY.md,
docs/B2_CORRELATOR_CONTRACT_DRAFT.md, docs/B2_CORRELATOR_FILE_MAP.md):

  - First cut uses a ``correlation_context`` sideband — never an
    ``EventType`` extension.
  - Observability-only in Slice 2A: correlator output does not feed
    the policy gate, the replan layer, or any agent prompt.
  - Window semantics are event-stream ordinal, never wall-clock.
  - Every emitted ``CorrelationSignal`` carries a structured
    evidence chain: ``triggering_event_id``,
    ``participant_event_ids``, ``shared_entities``,
    ``window_*`` ordinals, and a closed-set ``matched_conditions``
    list. No free-text, no confidence field.
  - The closed pattern catalog ships exactly P1
    (``ETA_PATH_COMPOUND``) and P3 (``CARRIER_DOUBLE_HIT``). P2
    ``SUPPLY_DEMAND_MISMATCH`` is deferred (it would require a
    fragile static zone↔warehouse topology table); see
    ``correlator_patterns.py`` for the deferral notice.
  - Correlator is disabled by default
    (``CorrelatorConfig.enable_correlator=False``); Slice 2A does
    NOT wire the correlator into any runtime path.

This module does NOT:
  - import ``evaluation`` or ``action_code_mapper``
  - read ``data/cases/*.json``
  - call ``datetime.now`` / ``utcnow`` / ``time.time`` / ``uuid.uuid4``
  - import from ``adaptive``, ``replan``, ``learning``, or
    ``session``.
"""

from correlator.correlator_config import (
    KNOWN_CORRELATOR_PATTERN_IDS,
    MAX_CORRELATOR_WINDOW,
    CorrelatorConfig,
)
from correlator.correlator_engine import compute_correlation_context
from correlator.correlator_patterns import (
    P1_ETA_PATH_COMPOUND,
    P3_CARRIER_DOUBLE_HIT,
    PATTERN_DECLARATIONS,
    PATTERN_IDS,
    SEVERITY_HIGH_CONCURRENCE_SET,
    PatternDeclaration,
)
from correlator.correlator_schema import (
    CORRELATOR_MATCHED_CONDITION,
    CORRELATOR_PATTERN_ID,
    CORRELATOR_SCHEMA_VERSION,
    CorrelationContext,
    CorrelationSignal,
)

__all__ = [
    "CORRELATOR_MATCHED_CONDITION",
    "CORRELATOR_PATTERN_ID",
    "CORRELATOR_SCHEMA_VERSION",
    "CorrelationContext",
    "CorrelationSignal",
    "CorrelatorConfig",
    "KNOWN_CORRELATOR_PATTERN_IDS",
    "MAX_CORRELATOR_WINDOW",
    "P1_ETA_PATH_COMPOUND",
    "P3_CARRIER_DOUBLE_HIT",
    "PATTERN_DECLARATIONS",
    "PATTERN_IDS",
    "PatternDeclaration",
    "SEVERITY_HIGH_CONCURRENCE_SET",
    "compute_correlation_context",
]
