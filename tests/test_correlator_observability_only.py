"""B2 Slice 2B: observability-only invariants (end-to-end).

Runs ``run_session`` twice — once with correlator disabled, once
with correlator enabled — against the same seed / event stream /
initial state. Asserts that enabling the correlator changes ONLY
the ``correlation_context`` field on each
``SessionEventRecord``. Every other field (and every other part
of the ``SessionArtifact``) must be byte-identical.

Covers the Slice 2A boundary-doc invariants G3 / G4 / G5:

  - effective_decision is untouched (final_route, effective_risk,
    action_taken, execution_status);
  - governance_truth is untouched;
  - adaptive_adjustment is untouched;
  - replan overlay fields are untouched (``replan_trace``,
    ``replan_triggers``);
  - ``baseline_event_result`` is byte-identical (Path B shadow);
  - ``memory_snapshot`` is byte-identical (memory write is the
    same before and after);
  - ``session_id`` differs because the correlator contributes to
    the digest when enabled — pinned here so a future accidental
    collapse shows up as a failed assertion.
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
from event_loop_c import run_session  # noqa: E402


_MODES = ["BASELINE_STATIC", "PATH_C_COLD", "PATH_C_WARM"]


def _run(mode: str, correlator: CorrelatorConfig | None):
    return run_session(
        seed=42,
        mode=mode,
        correlator_config=correlator,
    )


@pytest.mark.parametrize("mode", _MODES)
def test_disabled_matches_pre_b2_default(mode):
    # Default (None) and explicit-disabled must produce equal artifacts.
    art_none = _run(mode, None).model_dump(mode="json")
    art_off = _run(mode, CorrelatorConfig()).model_dump(mode="json")
    assert art_none == art_off


@pytest.mark.parametrize("mode", _MODES)
def test_disabled_records_have_correlation_context_none(mode):
    art = _run(mode, None)
    for rec in art.event_records:
        assert rec.correlation_context is None


@pytest.mark.parametrize("mode", _MODES)
def test_enabled_only_adds_correlation_context(mode):
    art_off = _run(mode, CorrelatorConfig()).model_dump(mode="json")
    art_on = _run(
        mode, CorrelatorConfig(enable_correlator=True, window_size=3)
    ).model_dump(mode="json")

    # Compare every per-record field except:
    #   - correlation_context (the new field)
    #   - session_id / memory_record_id (derived from the session_id
    #     digest, which correctly changes when the correlator
    #     contributes to config_for_digest)
    ignored_fields = {"correlation_context", "session_id", "memory_record_id"}
    assert len(art_off["event_records"]) == len(art_on["event_records"])
    for rec_off, rec_on in zip(art_off["event_records"], art_on["event_records"]):
        off_sans = {k: v for k, v in rec_off.items() if k not in ignored_fields}
        on_sans = {k: v for k, v in rec_on.items() if k not in ignored_fields}
        assert off_sans == on_sans, (
            f"enabling correlator changed a non-correlation field in mode={mode}:\n"
            f"off={off_sans}\non={on_sans}"
        )
        # The disabled side holds None; the enabled side holds a
        # CorrelationContext (ran, possibly with empty signals).
        assert rec_off["correlation_context"] is None
        assert rec_on["correlation_context"] is not None

    # memory_snapshot records carry session_id; the correlator
    # changes the session_id, so strict byte equality of the
    # snapshot is not meaningful. Instead assert count+shape
    # stability — correlator does NOT write memory, so the
    # per-record payload (modulo session_id / memory_record_id)
    # must match.
    off_records = art_off["memory_snapshot"]["records"]
    on_records = art_on["memory_snapshot"]["records"]
    assert len(off_records) == len(on_records)
    for mr_off, mr_on in zip(off_records, on_records):
        off_sans_mr = {k: v for k, v in mr_off.items() if k != "session_id"}
        on_sans_mr = {k: v for k, v in mr_on.items() if k != "session_id"}
        assert off_sans_mr == on_sans_mr

    # schema_versions dict and mode must be unchanged.
    assert art_off["schema_versions"] == art_on["schema_versions"]
    assert art_off["config"]["mode"] == art_on["config"]["mode"]


@pytest.mark.parametrize("mode", _MODES)
def test_enabled_changes_session_id(mode):
    art_off = _run(mode, None)
    art_on = _run(
        mode, CorrelatorConfig(enable_correlator=True, window_size=3)
    )
    assert art_off.session_id != art_on.session_id, (
        "enabling correlator must contribute to the session_id digest "
        "(byte-identity for disabled, new digest for enabled)"
    )


@pytest.mark.parametrize("mode", _MODES)
def test_baseline_event_result_untouched(mode):
    art_off = _run(mode, None)
    art_on = _run(
        mode, CorrelatorConfig(enable_correlator=True, window_size=3)
    )
    for rec_off, rec_on in zip(art_off.event_records, art_on.event_records):
        assert rec_on.baseline_event_result == rec_off.baseline_event_result, (
            "correlator attach must not mutate baseline_event_result"
        )


@pytest.mark.parametrize("mode", _MODES)
def test_dual_track_governance_untouched(mode):
    art_off = _run(mode, None)
    art_on = _run(
        mode, CorrelatorConfig(enable_correlator=True, window_size=3)
    )
    for rec_off, rec_on in zip(art_off.event_records, art_on.event_records):
        assert rec_on.governance_truth == rec_off.governance_truth
        assert rec_on.effective_decision == rec_off.effective_decision


@pytest.mark.parametrize("mode", _MODES)
def test_replan_overlay_untouched(mode):
    art_off = _run(mode, None)
    art_on = _run(
        mode, CorrelatorConfig(enable_correlator=True, window_size=3)
    )
    for rec_off, rec_on in zip(art_off.event_records, art_on.event_records):
        assert rec_on.replan_trace == rec_off.replan_trace
        assert rec_on.replan_triggers == rec_off.replan_triggers
