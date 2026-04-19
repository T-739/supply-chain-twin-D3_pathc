"""replan/replan_config.py — Path C B1 Slice 1 configuration contract.

Configuration dataclass and module-level constants. No trigger logic,
no orchestration, no I/O. Acceptable consumers in future slices will
read these values; Slice 1 only freezes the shape.

Owner-fixed decisions:
  D1 : expected cost range comes from a cost_output-derived overlay
       (``ExpectedCostRangeSource = "cost_output_derived_overlay"``).
       Natural-language governance fields are not admissible.
  D3 : both absolute and relative cost-deviation thresholds are
       carried here. The trigger logic is NOT implemented in Slice 1.
  D4 : ``MAX_REPLAN_ATTEMPTS = 1``. Hard cap.
  D5 : B1's eventual second cycle is a full reasoning cycle
       (operations → cost → governance → adaptive gate → preflight
       → execute_action). This config lives at the orchestration
       entry; individual inner-layer configs are already owned by
       their respective subpackages.

Memory rule (carried from Path C-min): memory remains final-attempt
only. No per-attempt ``MemoryRecord``. This config intentionally
exposes no memory-read/write toggle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from replan.replan_schema import EXPECTED_COST_RANGE_SOURCE_LITERAL


# ---------------------------------------------------------------------------
# Module-level constants (closed)
# ---------------------------------------------------------------------------

#: Maximum number of replan attempts per event. Roadmap wording:
#: "one bounded re-reasoning cycle". Hard cap — exceeding this is an
#: error at the orchestration layer, not a soft degrade.
MAX_REPLAN_ATTEMPTS: Final[int] = 1


#: Re-exported for callers that import from this module.
ExpectedCostRangeSource = EXPECTED_COST_RANGE_SOURCE_LITERAL


#: Registry of every ``trigger_rule_id`` that may appear on a fired
#: ``ReplanTriggerRecord`` in future slices. Slice 1 only seeds the
#: registry; no rule implementations exist yet. The audit-trail test
#: (added in Slice 2) asserts fired ``trigger_rule_id`` ∈ this set.
KNOWN_TRIGGER_RULE_IDS: frozenset[str] = frozenset({
    "no_trigger_v1",
    "cost_deviation_v1",
    "sla_deviation_v1",
    "execution_failed_v1",
    "preflight_failed_v1",
})


# ---------------------------------------------------------------------------
# Configuration dataclass (frozen)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplanConfig:
    """Bounded-replan configuration, consumed by future B1 runtime.

    Fields
    ------
    enable_replan
        Master gate. Slice 1 ships with ``False`` and no runtime path
        reads this; Slice 2+ wires it into ``event_loop_c``.
    max_replan_attempts
        Hard cap, defaults to ``MAX_REPLAN_ATTEMPTS``. Exposed as a
        config field so tests can set it explicitly, but the class
        refuses values outside ``[0, MAX_REPLAN_ATTEMPTS]`` to prevent
        accidental unbounded retry.
    cost_deviation_abs_threshold
        Absolute cost deviation carried for audit. Slice 2's trigger
        rule is range-based (realized outside [min, max]); this
        threshold is recorded in the trigger record's
        ``deviation_measurement`` and is reserved for a future
        secondary-gate refinement. Units match
        ``ExecutionOutcome.cost_incurred`` (float).
    cost_deviation_rel_threshold
        Relative cost deviation carried for audit. Closed interval
        ``[0.0, 1.0]`` — higher values are rejected to prevent
        meaningless "deviation > 200%" rules. Not consulted by the
        Slice 2 trigger rule; reserved for future refinement.
    expected_cost_band_abs
        Absolute floor on the half-width of the expected-cost band
        produced by ``estimate_expected_outcome``. Units match
        ``ExecutionOutcome.cost_incurred`` (float). >= 0.
    expected_cost_band_rel
        Relative component of the expected-cost band, applied as a
        fraction of the Cost Agent's point estimate for the
        recommended candidate. Closed interval ``[0.0, 1.0]``. The
        effective band half-width is
        ``max(expected_cost_band_abs,
             point_estimate * expected_cost_band_rel)``.
    sla_deviation_enabled
        Master gate for ``SLA_DEVIATION`` trigger rule. Defaults
        ``True`` — the dimension stays usable by default when the
        master ``enable_replan`` flag is flipped.
    expected_cost_range_source
        Provenance literal for the expected-cost overlay. Slice 1
        admits exactly one value (``"cost_output_derived_overlay"``)
        — closed set ensures no natural-language source can be
        plumbed in by configuration.
    """

    enable_replan: bool = False
    max_replan_attempts: int = MAX_REPLAN_ATTEMPTS
    cost_deviation_abs_threshold: float = 50.0
    cost_deviation_rel_threshold: float = 0.2
    expected_cost_band_abs: float = 25.0
    expected_cost_band_rel: float = 0.1
    sla_deviation_enabled: bool = True
    expected_cost_range_source: ExpectedCostRangeSource = (
        "cost_output_derived_overlay"
    )

    def __post_init__(self) -> None:
        # Bounded retry — hard cap invariant, even against a caller
        # that constructs ReplanConfig directly.
        if not isinstance(self.max_replan_attempts, int):
            raise TypeError(
                f"max_replan_attempts must be int, got "
                f"{type(self.max_replan_attempts).__name__}"
            )
        if self.max_replan_attempts < 0:
            raise ValueError(
                f"max_replan_attempts must be >= 0, got {self.max_replan_attempts}"
            )
        if self.max_replan_attempts > MAX_REPLAN_ATTEMPTS:
            raise ValueError(
                f"max_replan_attempts={self.max_replan_attempts} exceeds hard "
                f"cap MAX_REPLAN_ATTEMPTS={MAX_REPLAN_ATTEMPTS}"
            )

        if not isinstance(self.cost_deviation_abs_threshold, (int, float)):
            raise TypeError(
                "cost_deviation_abs_threshold must be numeric"
            )
        if float(self.cost_deviation_abs_threshold) < 0:
            raise ValueError(
                "cost_deviation_abs_threshold must be >= 0, got "
                f"{self.cost_deviation_abs_threshold}"
            )

        if not isinstance(self.cost_deviation_rel_threshold, (int, float)):
            raise TypeError(
                "cost_deviation_rel_threshold must be numeric"
            )
        rel = float(self.cost_deviation_rel_threshold)
        if rel < 0.0 or rel > 1.0:
            raise ValueError(
                "cost_deviation_rel_threshold must be in [0.0, 1.0], got "
                f"{self.cost_deviation_rel_threshold}"
            )

        if not isinstance(self.expected_cost_band_abs, (int, float)):
            raise TypeError("expected_cost_band_abs must be numeric")
        if float(self.expected_cost_band_abs) < 0:
            raise ValueError(
                "expected_cost_band_abs must be >= 0, got "
                f"{self.expected_cost_band_abs}"
            )

        if not isinstance(self.expected_cost_band_rel, (int, float)):
            raise TypeError("expected_cost_band_rel must be numeric")
        band_rel = float(self.expected_cost_band_rel)
        if band_rel < 0.0 or band_rel > 1.0:
            raise ValueError(
                "expected_cost_band_rel must be in [0.0, 1.0], got "
                f"{self.expected_cost_band_rel}"
            )

        if not isinstance(self.sla_deviation_enabled, bool):
            raise TypeError(
                "sla_deviation_enabled must be bool"
            )

        if self.expected_cost_range_source != "cost_output_derived_overlay":
            # Belt-and-braces: the Literal type already enforces this
            # at static-type-check time, but a runtime assertion keeps
            # dynamic callers honest.
            raise ValueError(
                "expected_cost_range_source must be "
                "'cost_output_derived_overlay' (closed set in Slice 1), "
                f"got {self.expected_cost_range_source!r}"
            )
