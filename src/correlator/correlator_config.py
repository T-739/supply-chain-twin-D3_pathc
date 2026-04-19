"""correlator/correlator_config.py — Path C B2 Slice 2A configuration.

Configuration dataclass and module-level constants. No matching
logic, no orchestration, no I/O. Acceptable consumers in future
slices will read these values; Slice 2A only freezes the shape.

Owner-fixed decisions (see docs/B2_CORRELATOR_BOUNDARY.md §12):
  D1 : ``correlation_context`` sideband only — enforced by the
       absence of any EventType extension here.
  D2 : Additive optional field on ``SessionEventRecord``.
  D3 : Observability-only in Slice 2A — this config does NOT expose
       any "feed-into-policy" or "feed-into-replan" toggle.
  D4 : ``window_size: int`` is a stream-ordinal window. No
       wall-clock-driven window. Hard upper bound is
       ``MAX_CORRELATOR_WINDOW``.
  D5 : Closed pattern catalog — ``enabled_patterns`` must be a
       subset of ``KNOWN_CORRELATOR_PATTERN_IDS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from correlator.correlator_schema import CORRELATOR_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Module-level constants (closed)
# ---------------------------------------------------------------------------

#: Hard upper bound on ``CorrelatorConfig.window_size``. Chosen to
#: match the demo event-stream length (6 events) so a full session
#: can be inspected if the owner opts in. Raising this is a
#: documented MINOR bump.
MAX_CORRELATOR_WINDOW: Final[int] = 6


#: The closed, canonical set of pattern ids. Must stay in sync with
#: the ``CORRELATOR_PATTERN_ID`` Literal in ``correlator_schema.py``
#: and with ``PATTERN_DECLARATIONS`` in ``correlator_patterns.py``.
#: The frozen-schema test asserts all three stay consistent.
KNOWN_CORRELATOR_PATTERN_IDS: frozenset[str] = frozenset({
    "ETA_PATH_COMPOUND",
    "CARRIER_DOUBLE_HIT",
})


# ---------------------------------------------------------------------------
# Configuration dataclass (frozen)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrelatorConfig:
    """Event-correlator configuration, consumed by future B2 runtime.

    Fields
    ------
    enable_correlator
        Master gate. Slice 2A ships with ``False`` and no runtime
        path reads this; Slice 2B+ wires it into ``event_loop_c``.
    window_size
        Maximum number of most-recent finalized ``SessionEventRecord``
        entries available to the match function (including the
        current one). Must satisfy
        ``1 <= window_size <= MAX_CORRELATOR_WINDOW``. No wall-clock
        window, no dynamic resizing.
    enabled_patterns
        Subset of ``KNOWN_CORRELATOR_PATTERN_IDS``. Empty means no
        pattern will ever fire (valid, useful for ablations). Any
        member not in the known set is rejected.
    schema_version
        Version pin for the config record. Stays at
        ``CORRELATOR_SCHEMA_VERSION`` (1.0) until a MAJOR bump is
        required.
    """

    enable_correlator: bool = False
    window_size: int = 3
    enabled_patterns: frozenset[str] = field(
        default_factory=lambda: frozenset(KNOWN_CORRELATOR_PATTERN_IDS)
    )
    schema_version: str = CORRELATOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.enable_correlator, bool):
            raise TypeError(
                "enable_correlator must be bool, got "
                f"{type(self.enable_correlator).__name__}"
            )
        if not isinstance(self.window_size, int) or isinstance(
            self.window_size, bool
        ):
            raise TypeError(
                "window_size must be int, got "
                f"{type(self.window_size).__name__}"
            )
        if self.window_size < 1:
            raise ValueError(
                f"window_size must be >= 1, got {self.window_size}"
            )
        if self.window_size > MAX_CORRELATOR_WINDOW:
            raise ValueError(
                f"window_size={self.window_size} exceeds hard cap "
                f"MAX_CORRELATOR_WINDOW={MAX_CORRELATOR_WINDOW}"
            )

        if not isinstance(self.enabled_patterns, frozenset):
            # Normalize via a new frozenset if the caller passed a
            # set/list/tuple. Uses object.__setattr__ to respect the
            # frozen dataclass contract.
            try:
                normalized = frozenset(self.enabled_patterns)
            except TypeError as exc:
                raise TypeError(
                    "enabled_patterns must be a frozenset (or an "
                    "iterable of strings)"
                ) from exc
            object.__setattr__(self, "enabled_patterns", normalized)

        unknown = set(self.enabled_patterns) - set(
            KNOWN_CORRELATOR_PATTERN_IDS
        )
        if unknown:
            raise ValueError(
                f"enabled_patterns contains unknown ids: {sorted(unknown)!r}. "
                f"Known: {sorted(KNOWN_CORRELATOR_PATTERN_IDS)!r}"
            )

        if self.schema_version != CORRELATOR_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {CORRELATOR_SCHEMA_VERSION!r}, "
                f"got {self.schema_version!r}"
            )
