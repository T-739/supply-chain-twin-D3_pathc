"""agent_memory/agent_memory_config.py — Path C B4 Slice 1 configuration.

Configuration dataclass and module-level constants. No builder,
no renderer, no orchestration, no I/O. Slice 1 freezes the shape;
future slices read these values.

Owner-fixed decisions (see docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §12):

  D1 : ``target_agent`` admits only ``"operations"``.
  D3 : ``max_recent_examples`` is capped by
       ``MAX_AGENT_MEMORY_EXAMPLES`` (= 3).
  D5 : ``enable_agent_visible_memory=False`` is the hard default
       at every surface; ``allowed_modes`` admits only
       ``"PATH_C_WARM"`` in Slice 1; ``context_source`` admits
       only ``"structured_summary_plus_recent_examples"``.

This module does NOT:

- import ``evaluation`` or ``action_code_mapper``;
- read ``data/cases/*.json``;
- call ``datetime.now`` / ``utcnow`` / ``time.time`` /
  ``uuid.uuid4``;
- import from ``src/agents/*``, ``src/adaptive/*``,
  ``src/replan/*``, ``src/correlator/*``,
  ``src/learning/cumulative_memory.py``, or
  ``src/session/*``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal


# ---------------------------------------------------------------------------
# Module-level constants (closed)
# ---------------------------------------------------------------------------

#: Hard cap on the number of ``recent_examples`` admissible on an
#: ``AgentMemoryContext``. Slice 1 ships value 3 per D3. Raising
#: this is a documented MINOR bump plus a same-PR registry update.
MAX_AGENT_MEMORY_EXAMPLES: Final[int] = 3


#: Closed set of admissible experiment targets (D1). Slice 1 ships
#: ``{"operations"}``. Opening this set requires an owner-approved
#: boundary amendment and a MINOR bump.
KNOWN_AGENT_MEMORY_TARGETS: frozenset[str] = frozenset({"operations"})


#: Closed set of admissible context sources (D3 / D5). Slice 1
#: ships ``{"structured_summary_plus_recent_examples"}``. Opening
#: this set requires an owner-approved boundary amendment.
KNOWN_AGENT_MEMORY_CONTEXT_SOURCES: frozenset[str] = frozenset({
    "structured_summary_plus_recent_examples",
})


#: Closed set of session modes under which B4 may be attached
#: (D5). Slice 1 ships ``{"PATH_C_WARM"}``. Broadening this set is
#: an experiment-design change that must pass through the boundary
#: doc before the code.
_KNOWN_AGENT_MEMORY_ALLOWED_MODES: frozenset[str] = frozenset({"PATH_C_WARM"})


_AGENT_MEMORY_CONFIG_SCHEMA_VERSION: str = "1.0"


# ---------------------------------------------------------------------------
# Configuration dataclass (frozen)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentMemoryExperimentConfig:
    """Agent-visible memory experiment configuration (B4 Slice 1).

    Parallel in spirit to ``ReplanConfig`` / ``CorrelatorConfig`` /
    ``CumulativeMemoryConfig``: a frozen dataclass whose
    ``__post_init__`` enforces every invariant. Slice 1 ships with
    ``enable_agent_visible_memory=False`` and no runtime reads this
    value; later slices will wire it into the single operations-
    agent prompt-builder seam via a narrow additive hunk.

    Fields
    ------
    enable_agent_visible_memory
        Master gate. Slice 1 default is ``False``. This default is
        **load-bearing**: the entire B4 boundary document's default-
        off byte-identity invariant rests on it.
    target_agent
        Closed Literal admitting only ``"operations"`` in Slice 1.
        The governance agent is not a Slice 1 target (D1).
    context_source
        Closed Literal admitting only
        ``"structured_summary_plus_recent_examples"`` in Slice 1
        (D3). Alternative surfaces are out-of-scope until a later
        boundary amendment widens the set.
    max_recent_examples
        Per-config hard cap on ``AgentMemoryContext.recent_examples``
        length. Must satisfy
        ``1 <= max_recent_examples <= MAX_AGENT_MEMORY_EXAMPLES``.
    allowed_modes
        Closed subset of session modes under which the config may
        be attached by a caller. Slice 1 admits only
        ``frozenset({"PATH_C_WARM"})``. Any other member is rejected
        at construction time. Mode-gating itself is enforced by the
        future caller / script layer; this field freezes the
        allowed values.
    schema_version
        Version pin for the config record. Stays at ``"1.0"`` until
        a MAJOR bump is required.
    """

    enable_agent_visible_memory: bool = False
    target_agent: Literal["operations"] = "operations"
    context_source: Literal[
        "structured_summary_plus_recent_examples"
    ] = "structured_summary_plus_recent_examples"
    max_recent_examples: int = MAX_AGENT_MEMORY_EXAMPLES
    allowed_modes: frozenset[str] = field(
        default_factory=lambda: frozenset(_KNOWN_AGENT_MEMORY_ALLOWED_MODES)
    )
    schema_version: str = _AGENT_MEMORY_CONFIG_SCHEMA_VERSION

    def __post_init__(self) -> None:
        # enable_agent_visible_memory — strict bool
        if not isinstance(self.enable_agent_visible_memory, bool):
            raise TypeError(
                "enable_agent_visible_memory must be bool, got "
                f"{type(self.enable_agent_visible_memory).__name__}"
            )

        # target_agent — closed set (D1)
        if self.target_agent not in KNOWN_AGENT_MEMORY_TARGETS:
            raise ValueError(
                f"target_agent={self.target_agent!r} is not in the "
                f"known set {sorted(KNOWN_AGENT_MEMORY_TARGETS)!r}"
            )

        # context_source — closed set (D3 / D5)
        if self.context_source not in KNOWN_AGENT_MEMORY_CONTEXT_SOURCES:
            raise ValueError(
                f"context_source={self.context_source!r} is not in the "
                f"known set {sorted(KNOWN_AGENT_MEMORY_CONTEXT_SOURCES)!r}"
            )

        # max_recent_examples — range
        if (
            not isinstance(self.max_recent_examples, int)
            or isinstance(self.max_recent_examples, bool)
        ):
            raise TypeError(
                "max_recent_examples must be int, got "
                f"{type(self.max_recent_examples).__name__}"
            )
        if self.max_recent_examples < 1:
            raise ValueError(
                f"max_recent_examples must be >= 1, got "
                f"{self.max_recent_examples}"
            )
        if self.max_recent_examples > MAX_AGENT_MEMORY_EXAMPLES:
            raise ValueError(
                f"max_recent_examples={self.max_recent_examples} exceeds "
                f"hard cap MAX_AGENT_MEMORY_EXAMPLES="
                f"{MAX_AGENT_MEMORY_EXAMPLES}"
            )

        # allowed_modes — normalize + closed-set membership (D5)
        if not isinstance(self.allowed_modes, frozenset):
            try:
                normalized = frozenset(self.allowed_modes)
            except TypeError as exc:
                raise TypeError(
                    "allowed_modes must be a frozenset (or an iterable "
                    "of strings)"
                ) from exc
            object.__setattr__(self, "allowed_modes", normalized)

        if not self.allowed_modes:
            raise ValueError(
                "allowed_modes must be non-empty; Slice 1 requires "
                f"{sorted(_KNOWN_AGENT_MEMORY_ALLOWED_MODES)!r}"
            )

        unknown = set(self.allowed_modes) - set(
            _KNOWN_AGENT_MEMORY_ALLOWED_MODES
        )
        if unknown:
            raise ValueError(
                f"allowed_modes contains members not admitted by Slice 1: "
                f"{sorted(unknown)!r}. "
                f"Known (Slice 1): "
                f"{sorted(_KNOWN_AGENT_MEMORY_ALLOWED_MODES)!r}"
            )

        # schema_version pin
        if self.schema_version != _AGENT_MEMORY_CONFIG_SCHEMA_VERSION:
            raise ValueError(
                "schema_version must be "
                f"{_AGENT_MEMORY_CONFIG_SCHEMA_VERSION!r}, "
                f"got {self.schema_version!r}"
            )
