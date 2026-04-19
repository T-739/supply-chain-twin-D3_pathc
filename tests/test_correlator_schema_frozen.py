"""B2 Slice 2A: correlator schema + config contract freeze.

Focused invariants for the B2 subpackage. The broader field-set /
version / roundtrip checks live in
``tests/test_path_c_schema_frozen.py``; this file exercises the
closed-set and validator behaviors that only matter for the B2
contracts and that we want to fail loudly on future drift:

  - ``CORRELATOR_PATTERN_ID`` is a closed set matching the catalog
    declared in ``correlator_patterns.py``.
  - ``CORRELATOR_MATCHED_CONDITION`` is a closed set.
  - ``KNOWN_CORRELATOR_PATTERN_IDS`` equals ``frozenset(PATTERN_IDS)``.
  - ``MAX_CORRELATOR_WINDOW`` is a positive int.
  - ``CorrelatorConfig`` defaults are runtime-no-op safe
    (``enable_correlator=False``) and validator rejects bad values.
  - ``CorrelationSignal`` enforces:
      * ``len(participant_event_ids) >= 2``
      * ``triggering_event_id in participant_event_ids``
      * ``window_end_ordinal >= window_start_ordinal``
      * span <= ``window_size``
      * ``matched_conditions`` non-empty
      * no unknown ``pattern_id``, no unknown ``matched_conditions``
      * ``extra='forbid'``
  - ``CorrelationContext`` allows empty ``signals`` (ran-but-found-
    nothing), rejects ``window_events_considered > window_size``.
  - Schema-version pins equal ``CORRELATOR_SCHEMA_VERSION``.

No runtime behavior is exercised; the point is to freeze the shape.
"""

from __future__ import annotations

import os
import sys
import typing

import pytest
from pydantic import ValidationError


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from correlator import (  # noqa: E402
    CORRELATOR_MATCHED_CONDITION,
    CORRELATOR_PATTERN_ID,
    CORRELATOR_SCHEMA_VERSION,
    KNOWN_CORRELATOR_PATTERN_IDS,
    MAX_CORRELATOR_WINDOW,
    PATTERN_DECLARATIONS,
    PATTERN_IDS,
    CorrelationContext,
    CorrelationSignal,
    CorrelatorConfig,
)


# ---------------------------------------------------------------------------
# Closed-set literals
# ---------------------------------------------------------------------------


def test_pattern_id_literal_is_closed_and_matches_catalog():
    args = set(typing.get_args(CORRELATOR_PATTERN_ID))
    assert args == {"ETA_PATH_COMPOUND", "CARRIER_DOUBLE_HIT"}, (
        f"CORRELATOR_PATTERN_ID drifted, got {args!r}"
    )
    # The pattern catalog, the Literal, and the known-ids frozenset
    # must all agree exactly.
    assert set(PATTERN_IDS) == args
    assert KNOWN_CORRELATOR_PATTERN_IDS == frozenset(PATTERN_IDS)


def test_matched_condition_literal_closed_set():
    args = set(typing.get_args(CORRELATOR_MATCHED_CONDITION))
    assert args == {
        "SHARED_ETA_PATH",
        "SAME_ENTITY_ID",
        "STREAM_ADJACENT",
        "SEVERITY_HIGH_CONCURRENCE",
    }


def test_pattern_declarations_default_conditions_are_in_literal():
    allowed = set(typing.get_args(CORRELATOR_MATCHED_CONDITION))
    for decl in PATTERN_DECLARATIONS:
        for cond in decl.default_matched_conditions:
            assert cond in allowed, (
                f"{decl.pattern_id} lists unknown matched-condition {cond!r}"
            )


# ---------------------------------------------------------------------------
# Config invariants
# ---------------------------------------------------------------------------


def test_max_correlator_window_is_positive_int():
    assert isinstance(MAX_CORRELATOR_WINDOW, int)
    assert MAX_CORRELATOR_WINDOW >= 1


def test_correlator_config_defaults_are_runtime_no_op():
    cfg = CorrelatorConfig()
    assert cfg.enable_correlator is False
    assert cfg.window_size == 3
    assert cfg.enabled_patterns == KNOWN_CORRELATOR_PATTERN_IDS
    assert cfg.schema_version == CORRELATOR_SCHEMA_VERSION


@pytest.mark.parametrize(
    "kwargs,exc",
    [
        ({"enable_correlator": "no"}, TypeError),
        ({"window_size": 0}, ValueError),
        ({"window_size": -1}, ValueError),
        ({"window_size": MAX_CORRELATOR_WINDOW + 1}, ValueError),
        ({"window_size": "3"}, TypeError),
        ({"enabled_patterns": frozenset({"NOT_A_PATTERN"})}, ValueError),
        ({"schema_version": "9.9"}, ValueError),
    ],
)
def test_correlator_config_validator_rejects_bad_values(kwargs, exc):
    with pytest.raises(exc):
        CorrelatorConfig(**kwargs)


def test_correlator_config_accepts_non_frozenset_iterable_for_patterns():
    cfg = CorrelatorConfig(enabled_patterns={"ETA_PATH_COMPOUND"})
    assert isinstance(cfg.enabled_patterns, frozenset)
    assert cfg.enabled_patterns == frozenset({"ETA_PATH_COMPOUND"})


def test_correlator_config_empty_enabled_patterns_is_valid():
    # Useful for ablations — valid, but no pattern will ever fire.
    cfg = CorrelatorConfig(enabled_patterns=frozenset())
    assert cfg.enabled_patterns == frozenset()


# ---------------------------------------------------------------------------
# CorrelationSignal invariants
# ---------------------------------------------------------------------------


def _valid_signal_kwargs(**overrides):
    kwargs = dict(
        pattern_id="ETA_PATH_COMPOUND",
        triggering_event_id="EVT-D02",
        participant_event_ids=["EVT-D01", "EVT-D02"],
        shared_entities=[],
        window_start_ordinal=0,
        window_end_ordinal=1,
        window_size=3,
        matched_conditions=["SHARED_ETA_PATH"],
    )
    kwargs.update(overrides)
    return kwargs


def test_correlation_signal_valid_construction():
    sig = CorrelationSignal(**_valid_signal_kwargs())
    assert sig.pattern_id == "ETA_PATH_COMPOUND"
    assert sig.schema_version == CORRELATOR_SCHEMA_VERSION


def test_correlation_signal_requires_two_participants():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(
                participant_event_ids=["EVT-D02"],
                triggering_event_id="EVT-D02",
            )
        )


def test_correlation_signal_requires_triggering_in_participants():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(
                triggering_event_id="EVT-XXX",
            )
        )


def test_correlation_signal_rejects_end_before_start():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(
                window_start_ordinal=3,
                window_end_ordinal=1,
            )
        )


def test_correlation_signal_rejects_span_over_window():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(
                window_start_ordinal=0,
                window_end_ordinal=5,
                window_size=3,
            )
        )


def test_correlation_signal_requires_non_empty_matched_conditions():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(matched_conditions=[])
        )


def test_correlation_signal_rejects_unknown_pattern_id():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(pattern_id="NOT_A_PATTERN")
        )


def test_correlation_signal_rejects_unknown_matched_condition():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(
                matched_conditions=["SHARED_ETA_PATH", "MYSTERY_CONDITION"],
            )
        )


def test_correlation_signal_rejects_empty_triggering_event_id():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(
                triggering_event_id="   ",
                participant_event_ids=["   ", "EVT-D01"],
            )
        )


def test_correlation_signal_rejects_empty_participant_id():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(
                participant_event_ids=["EVT-D01", ""],
            )
        )


def test_correlation_signal_forbids_extra_fields():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(),
            confidence=0.9,  # extra field, no such attribute allowed
        )


def test_correlation_signal_rejects_zero_window_size():
    with pytest.raises(ValidationError):
        CorrelationSignal(
            **_valid_signal_kwargs(window_size=0)
        )


# ---------------------------------------------------------------------------
# CorrelationContext invariants
# ---------------------------------------------------------------------------


def test_correlation_context_ran_but_empty_is_valid():
    ctx = CorrelationContext(
        signals=[],
        window_size=3,
        window_events_considered=0,
    )
    assert ctx.signals == []
    assert ctx.schema_version == CORRELATOR_SCHEMA_VERSION


def test_correlation_context_with_one_signal():
    sig = CorrelationSignal(**_valid_signal_kwargs())
    ctx = CorrelationContext(
        signals=[sig],
        window_size=3,
        window_events_considered=2,
    )
    assert len(ctx.signals) == 1


def test_correlation_context_rejects_considered_over_window():
    with pytest.raises(ValidationError):
        CorrelationContext(
            signals=[],
            window_size=3,
            window_events_considered=4,
        )


def test_correlation_context_forbids_extra_fields():
    with pytest.raises(ValidationError):
        CorrelationContext(
            signals=[],
            window_size=3,
            window_events_considered=0,
            mystery_field=1,
        )


# ---------------------------------------------------------------------------
# Version pin
# ---------------------------------------------------------------------------


def test_correlator_schema_version_pin():
    assert CORRELATOR_SCHEMA_VERSION == "1.0"
    assert CorrelationSignal.model_fields["schema_version"].default == "1.0"
    assert CorrelationContext.model_fields["schema_version"].default == "1.0"
    assert CorrelatorConfig().schema_version == "1.0"
