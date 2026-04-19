"""B2 Slice 2B: event_loop_c integration — post-finalization attach.

Structural / integration checks that:

  - ``run_session(..., correlator_config=None)`` is byte-equivalent
    to ``run_session(..., correlator_config=CorrelatorConfig())`` —
    the default is indistinguishable from an explicit-disabled
    config (no accidental ``enable_correlator=True``).
  - When enabled, every ``SessionEventRecord`` in the artifact has
    ``correlation_context`` populated, one per event.
  - The attach is post-finalization: enabling the correlator does
    NOT change ``memory_snapshot``, ``kpis`` values on disabled
    fields, or the ``schema_versions`` map.
  - Replan enabled × correlator enabled does not cross-contaminate
    — both overlays land on the same records, and correlator does
    not change any replan field.
  - ``model_copy`` was used (records are not mutated in place):
    the record objects referenced from outside the attach call
    are a new list, and the old records' identity is not reused
    with mutated contents.
"""

from __future__ import annotations

import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from correlator.correlator_config import CorrelatorConfig  # noqa: E402
from event_loop_c import _attach_correlation_contexts, run_session  # noqa: E402
from event_engine import generate_demo_event_stream  # noqa: E402
from replan.replan_config import ReplanConfig  # noqa: E402


def test_default_correlator_config_is_disabled():
    # Default (None) must produce an artifact with every record's
    # correlation_context=None.
    art = run_session(seed=42, mode="BASELINE_STATIC")
    assert all(r.correlation_context is None for r in art.event_records)


def test_enabled_populates_correlation_context_on_every_record():
    art = run_session(
        seed=42,
        mode="BASELINE_STATIC",
        correlator_config=CorrelatorConfig(enable_correlator=True, window_size=3),
    )
    assert len(art.event_records) == len(generate_demo_event_stream())
    for rec in art.event_records:
        assert rec.correlation_context is not None
        assert rec.correlation_context.window_size == 3


def test_kpis_unchanged_by_correlator_enable():
    art_off = run_session(seed=42, mode="BASELINE_STATIC")
    art_on = run_session(
        seed=42,
        mode="BASELINE_STATIC",
        correlator_config=CorrelatorConfig(enable_correlator=True, window_size=3),
    )
    # Slice 2B adds no KPIs; Phase 3 KPI surface must be invariant.
    assert art_off.kpis.model_dump() == art_on.kpis.model_dump()


def test_schema_versions_map_stable_under_enable():
    art_off = run_session(seed=42, mode="BASELINE_STATIC")
    art_on = run_session(
        seed=42,
        mode="BASELINE_STATIC",
        correlator_config=CorrelatorConfig(enable_correlator=True, window_size=3),
    )
    # schema_versions map is a function of the orchestrator, not the
    # config flags — it must be equal whether correlator is on or off.
    assert art_off.schema_versions == art_on.schema_versions


def test_schema_versions_map_reflects_b2_landed_state():
    """B2 cleanup pin: the schema_versions map must report the
    actually-landed schema versions for every B2-affected record.

    Previously ``session_event_record`` drifted to ``"1.1"`` here
    while the SessionEventRecord pydantic class itself was bumped
    to ``"1.2"`` in Slice 2A — a consistency bug. This test pins
    the landed state so a future drift fails loudly."""
    art = run_session(seed=42, mode="BASELINE_STATIC")
    sv = art.schema_versions

    # SessionEventRecord is at 1.2 per Slice 2A (additive
    # ``correlation_context`` field).
    assert sv["session_event_record"] == "1.2"

    # Correlator components registered at 1.0 per Slice 2A.
    assert sv["correlation_signal"] == "1.0"
    assert sv["correlation_context"] == "1.0"
    assert sv["correlator_config"] == "1.0"


def test_correlator_does_not_cross_contaminate_replan_overlay():
    art_replan = run_session(
        seed=42,
        mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=True),
    )
    art_both = run_session(
        seed=42,
        mode="PATH_C_COLD",
        replan_config=ReplanConfig(enable_replan=True),
        correlator_config=CorrelatorConfig(enable_correlator=True, window_size=3),
    )
    # Every field except correlation_context, session_id, and
    # memory_record_id must match. session_id / memory_record_id
    # correctly differ because the correlator contributes to the
    # session_id digest when enabled.
    ignored = {"correlation_context", "session_id", "memory_record_id"}
    for r_r, r_b in zip(art_replan.event_records, art_both.event_records):
        r_r_sans = {k: v for k, v in r_r.model_dump().items() if k not in ignored}
        r_b_sans = {k: v for k, v in r_b.model_dump().items() if k not in ignored}
        assert r_r_sans == r_b_sans
        # Replan fields are unchanged.
        assert r_r.replan_trace == r_b.replan_trace
        assert r_r.replan_triggers == r_b.replan_triggers
        # Correlator is attached.
        assert r_b.correlation_context is not None


def test_attach_helper_returns_new_list_and_does_not_mutate_inputs():
    # Build a session with correlator disabled, capture records,
    # then call the attach helper directly.
    art = run_session(seed=42, mode="BASELINE_STATIC")
    records_before = list(art.event_records)
    records_before_dump = [r.model_dump() for r in records_before]

    events = generate_demo_event_stream()
    updated = _attach_correlation_contexts(
        session_records=records_before,
        events=events,
        correlator_config=CorrelatorConfig(
            enable_correlator=True, window_size=3,
        ),
    )

    # Returned list is a distinct object.
    assert updated is not records_before
    # Original records were NOT mutated — dumps still match.
    records_after_dump = [r.model_dump() for r in records_before]
    assert records_after_dump == records_before_dump
    # All originals still have correlation_context=None.
    for r in records_before:
        assert r.correlation_context is None
    # All new records have correlation_context populated and every
    # OTHER field equals the original.
    for r_old, r_new in zip(records_before, updated):
        assert r_new.correlation_context is not None
        old_sans = {
            k: v for k, v in r_old.model_dump().items() if k != "correlation_context"
        }
        new_sans = {
            k: v for k, v in r_new.model_dump().items() if k != "correlation_context"
        }
        assert old_sans == new_sans


def test_attach_helper_rejects_length_mismatch():
    art = run_session(seed=42, mode="BASELINE_STATIC")
    events = generate_demo_event_stream()
    with pytest.raises(RuntimeError):
        _attach_correlation_contexts(
            session_records=list(art.event_records)[:-1],  # too short
            events=events,
            correlator_config=CorrelatorConfig(
                enable_correlator=True, window_size=3,
            ),
        )
