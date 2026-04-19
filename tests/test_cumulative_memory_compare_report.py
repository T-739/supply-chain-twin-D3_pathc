"""B3 Slice 2C: cumulative_memory_summary sibling block on the
compare report.

Pins that:

  - when no compared artifact carries cross-session memory rows,
    ``build_compare_report`` does NOT emit a
    ``cumulative_memory_summary`` key and the rendered markdown
    contains no cumulative section;
  - when at least one artifact does, an additive
    ``cumulative_memory_summary`` block appears with
    deterministic structural content (per-session provenance,
    overall prior-session row counts, prior-session ref union);
  - existing compare blocks (``kpi_matrix``, ``deltas``,
    ``diverged_events``, ``thesis_claim_support``,
    ``replan_trace_summary``, ``correlation_summary``) keep
    their shape and values regardless of cumulative-memory
    presence;
  - the rendered markdown is a pure function of the compare
    report (same input → same bytes);
  - the summary is derived only from
    ``memory_snapshot["records"]`` + each row's ``session_id`` —
    not KPIs, not governance NL fields, not agent outputs;
  - rows whose ``session_id == artifact.session_id`` are counted
    as self-session rows, not cumulative rows;
  - mixed compared artifacts (some with cumulative, some
    without) behave cleanly.
"""

from __future__ import annotations

import ast
import inspect
import os
import sys
from typing import Any, Optional

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from session import session_compare as _sc
from session.session_compare import (
    COMPARE_REPORT_SCHEMA_VERSION,
    build_compare_report,
    render_thesis_markdown,
)
from session.session_schema import (
    EffectiveDecisionRef,
    GovernanceTruthRef,
    SessionArtifact,
    SessionConfig,
    SessionEventRecord,
    SessionKPIs,
)


def _ser(
    *,
    event_id: str,
    mode: str = "BASELINE_STATIC",
    route: str = "AUTO_EXECUTE",
    action: Optional[str] = "EXPEDITE",
    status: str = "executed",
) -> SessionEventRecord:
    return SessionEventRecord(
        baseline_event_result={
            "event_id": event_id,
            "execution_outcome": {
                "action_taken": action,
                "cost_incurred": 100.0,
                "sla_impact": {"preserved": True},
            },
            "policy_decision": {"route": route},
            "execution_status": status,
        },
        session_id=f"SID-{mode}",
        mode=mode,
        policy_route_source="baseline_static",
        governance_truth=GovernanceTruthRef(
            risk_level="LOW", recommended_candidate_type="EXPEDITE",
        ),
        effective_decision=EffectiveDecisionRef(
            effective_risk="LOW",
            final_route=route,
            action_taken=action,
            execution_status=status,
        ),
    )


def _mem_row(
    *,
    sid: str,
    ts: str,
    eid: str,
) -> dict[str, Any]:
    """Build one serialized MemoryRecord-shaped dict suitable for a
    ``SessionArtifact.memory_snapshot['records']`` entry."""
    return {
        "event_id": eid,
        "event_type": "CARRIER_DELAY_ESCALATION",
        "event_timestamp": ts,
        "action_taken": "EXPEDITE",
        "execution_status": "executed",
        "final_route": "AUTO_EXECUTE",
        "cost_incurred": 100.0,
        "sla_preserved": True,
        "risk_level": "LOW",
        "session_id": sid,
        "schema_version": "1.0",
    }


def _artifact(
    *,
    mode_name: str,
    mode_value: str,
    records: list[SessionEventRecord],
    memory_rows: list[dict[str, Any]] | None = None,
) -> SessionArtifact:
    snap = {
        "records": list(memory_rows) if memory_rows else [],
        "schema_version": "1.0",
    }
    return SessionArtifact(
        session_id=f"SID-{mode_name}",
        config=SessionConfig(
            seed=42, mode=mode_value, events_source="demo_stream",
        ),
        event_records=records,
        memory_snapshot=snap,
        kpis=SessionKPIs(events_observed=len(records)),
        schema_versions={},
        notes="",
    )


# ---------------------------------------------------------------------------
# Shape invariance: no cumulative data → no block, no section
# ---------------------------------------------------------------------------


def test_no_cumulative_anywhere_omits_block():
    records = [_ser(event_id=f"E{i}") for i in range(3)]
    a = _artifact(
        mode_name="baseline_static",
        mode_value="BASELINE_STATIC",
        records=records,
    )
    b = _artifact(
        mode_name="path_c_cold",
        mode_value="PATH_C_COLD",
        records=records,
    )
    report = build_compare_report(
        {"baseline_static": a, "path_c_cold": b},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    assert "cumulative_memory_summary" not in report
    md = render_thesis_markdown(report)
    assert "Cumulative memory provenance" not in md
    assert "## Cumulative memory provenance (B3)" not in md


def test_only_self_session_rows_omits_block():
    # Memory snapshot contains rows whose session_id equals the
    # artifact's OWN session_id. These are self-session rows only —
    # no cumulative memory is present.
    records = [_ser(event_id=f"E{i}") for i in range(2)]
    memory_rows = [
        _mem_row(sid="SID-baseline_static", ts="2026-01-01T10:00:00+00:00", eid="E0"),
        _mem_row(sid="SID-baseline_static", ts="2026-01-01T11:00:00+00:00", eid="E1"),
    ]
    a = _artifact(
        mode_name="baseline_static",
        mode_value="BASELINE_STATIC",
        records=records,
        memory_rows=memory_rows,
    )
    report = build_compare_report(
        {"baseline_static": a},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    assert "cumulative_memory_summary" not in report


def test_no_cumulative_keeps_existing_top_level_keys_stable():
    records = [_ser(event_id=f"E{i}") for i in range(3)]
    a = _artifact(
        mode_name="baseline_static",
        mode_value="BASELINE_STATIC",
        records=records,
    )
    report = build_compare_report(
        {"baseline_static": a},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    expected_top_keys = {
        "schema_version",
        "sessions_compared",
        "baseline_mode",
        "min_records_for_shift",
        "per_session_kpi_report",
        "kpi_matrix",
        "deltas",
        "diverged_events",
        "thesis_claim_support",
    }
    assert set(report.keys()) == expected_top_keys


# ---------------------------------------------------------------------------
# Additive block appears when cumulative data is present
# ---------------------------------------------------------------------------


def test_cumulative_summary_appears_when_data_present():
    # Baseline: only self-session memory. Path C cold: has 2
    # cumulative rows from PRIOR_SESSION_1 and 1 from
    # PRIOR_SESSION_2 plus 1 self-session row.
    base_records = [_ser(event_id="E0")]
    base_mem = [_mem_row(sid="SID-baseline_static", ts="2026-01-01T10:00:00+00:00", eid="E0")]

    cold_records = [_ser(event_id="E0", mode="PATH_C_COLD")]
    cold_mem = [
        _mem_row(sid="PRIOR_SESSION_1", ts="2026-02-01T10:00:00+00:00", eid="P1"),
        _mem_row(sid="PRIOR_SESSION_1", ts="2026-02-02T10:00:00+00:00", eid="P2"),
        _mem_row(sid="PRIOR_SESSION_2", ts="2026-02-03T10:00:00+00:00", eid="P3"),
        _mem_row(sid="SID-path_c_cold", ts="2026-04-01T10:00:00+00:00", eid="E0"),
    ]

    base = _artifact(
        mode_name="baseline_static",
        mode_value="BASELINE_STATIC",
        records=base_records,
        memory_rows=base_mem,
    )
    cold = _artifact(
        mode_name="path_c_cold",
        mode_value="PATH_C_COLD",
        records=cold_records,
        memory_rows=cold_mem,
    )

    report = build_compare_report(
        {"baseline_static": base, "path_c_cold": cold},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )

    assert "cumulative_memory_summary" in report
    cms = report["cumulative_memory_summary"]

    # Only the mode with cumulative rows is listed.
    assert cms["sessions_with_cumulative_memory"] == ["path_c_cold"]

    # Per-session block structure.
    psc = cms["per_session"]["path_c_cold"]
    assert psc["current_session_id"] == "SID-path_c_cold"
    assert psc["has_cumulative_memory"] is True
    assert psc["cumulative_row_count"] == 3
    assert psc["self_session_row_count"] == 1
    assert psc["prior_session_refs"] == ["PRIOR_SESSION_1", "PRIOR_SESSION_2"]
    assert psc["rows_by_prior_session"] == {
        "PRIOR_SESSION_1": 2,
        "PRIOR_SESSION_2": 1,
    }

    # Overall + union fields.
    assert cms["all_prior_session_refs"] == [
        "PRIOR_SESSION_1", "PRIOR_SESSION_2",
    ]
    assert cms["overall_rows_by_prior_session"] == {
        "PRIOR_SESSION_1": 2,
        "PRIOR_SESSION_2": 1,
    }


def test_self_session_rows_counted_separately_from_cumulative():
    # All rows are self-session + one cumulative from PRIOR_X.
    records = [_ser(event_id="E0", mode="PATH_C_WARM")]
    mem = [
        _mem_row(sid="SID-path_c_warm", ts="2026-04-01T10:00:00+00:00", eid="E0"),
        _mem_row(sid="SID-path_c_warm", ts="2026-04-01T11:00:00+00:00", eid="E1"),
        _mem_row(sid="SID-path_c_warm", ts="2026-04-01T12:00:00+00:00", eid="E2"),
        _mem_row(sid="PRIOR_X", ts="2026-02-01T10:00:00+00:00", eid="P0"),
    ]
    art = _artifact(
        mode_name="path_c_warm",
        mode_value="PATH_C_WARM",
        records=records,
        memory_rows=mem,
    )
    report = build_compare_report(
        {"path_c_warm": art},
        baseline_mode="path_c_warm",
        min_records_for_shift=3,
    )
    psc = report["cumulative_memory_summary"]["per_session"]["path_c_warm"]
    assert psc["cumulative_row_count"] == 1
    assert psc["self_session_row_count"] == 3
    assert psc["prior_session_refs"] == ["PRIOR_X"]
    assert psc["rows_by_prior_session"] == {"PRIOR_X": 1}


def test_per_session_sorted_by_mode_name():
    cold_records = [_ser(event_id="E0", mode="PATH_C_COLD")]
    warm_records = [_ser(event_id="E0", mode="PATH_C_WARM")]
    cold_mem = [_mem_row(sid="PRIOR_COLD", ts="2026-02-01T10:00:00+00:00", eid="P0")]
    warm_mem = [_mem_row(sid="PRIOR_WARM", ts="2026-02-01T10:00:00+00:00", eid="P0")]
    cold = _artifact(
        mode_name="path_c_cold",
        mode_value="PATH_C_COLD",
        records=cold_records,
        memory_rows=cold_mem,
    )
    warm = _artifact(
        mode_name="path_c_warm",
        mode_value="PATH_C_WARM",
        records=warm_records,
        memory_rows=warm_mem,
    )
    # Intentionally insert in reverse order; build_compare_report
    # sorts sessions_compared, so sessions_with_cumulative_memory
    # must also come out sorted.
    report = build_compare_report(
        {"path_c_warm": warm, "path_c_cold": cold},
        baseline_mode="path_c_cold",
        min_records_for_shift=3,
    )
    cms = report["cumulative_memory_summary"]
    assert cms["sessions_with_cumulative_memory"] == [
        "path_c_cold", "path_c_warm",
    ]
    assert list(cms["per_session"].keys()) == [
        "path_c_cold", "path_c_warm",
    ]
    assert cms["all_prior_session_refs"] == ["PRIOR_COLD", "PRIOR_WARM"]
    assert cms["overall_rows_by_prior_session"] == {
        "PRIOR_COLD": 1,
        "PRIOR_WARM": 1,
    }


def test_mixed_compared_artifacts_behave_cleanly():
    # One artifact has cumulative memory, one does not. The block
    # must appear and list only the mode with cumulative rows.
    base_records = [_ser(event_id="E0")]
    warm_records = [_ser(event_id="E0", mode="PATH_C_WARM")]
    warm_mem = [_mem_row(sid="PRIOR_X", ts="2026-02-01T10:00:00+00:00", eid="P0")]

    base = _artifact(
        mode_name="baseline_static",
        mode_value="BASELINE_STATIC",
        records=base_records,
        # No memory_snapshot rows at all.
    )
    warm = _artifact(
        mode_name="path_c_warm",
        mode_value="PATH_C_WARM",
        records=warm_records,
        memory_rows=warm_mem,
    )
    report = build_compare_report(
        {"baseline_static": base, "path_c_warm": warm},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    cms = report["cumulative_memory_summary"]
    assert cms["sessions_with_cumulative_memory"] == ["path_c_warm"]
    assert "baseline_static" not in cms["per_session"]


# ---------------------------------------------------------------------------
# Existing-field stability when cumulative block is present
# ---------------------------------------------------------------------------


def test_existing_blocks_untouched_when_cumulative_present():
    records_no_mem = [_ser(event_id=f"E{i}") for i in range(3)]
    records_for_artifact_with_mem = [_ser(event_id=f"E{i}") for i in range(3)]
    mem = [_mem_row(sid="PRIOR_X", ts="2026-02-01T10:00:00+00:00", eid="P0")]

    a_plain = _artifact(
        mode_name="baseline_static",
        mode_value="BASELINE_STATIC",
        records=records_no_mem,
    )
    a_with_mem = _artifact(
        mode_name="baseline_static",
        mode_value="BASELINE_STATIC",
        records=records_for_artifact_with_mem,
        memory_rows=mem,
    )

    report_plain = build_compare_report(
        {"baseline_static": a_plain},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    report_with_cum = build_compare_report(
        {"baseline_static": a_with_mem},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )

    for key in (
        "sessions_compared", "kpi_matrix", "deltas",
        "diverged_events", "thesis_claim_support",
        "per_session_kpi_report",
    ):
        assert report_plain[key] == report_with_cum[key], (
            f"existing compare block {key!r} drifted when cumulative "
            f"memory was added"
        )
    assert "cumulative_memory_summary" not in report_plain
    assert "cumulative_memory_summary" in report_with_cum


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def test_markdown_renders_cumulative_section_when_block_present():
    records = [_ser(event_id="E0", mode="PATH_C_WARM")]
    mem = [
        _mem_row(sid="PRIOR_A", ts="2026-02-01T10:00:00+00:00", eid="P0"),
        _mem_row(sid="PRIOR_A", ts="2026-02-02T10:00:00+00:00", eid="P1"),
        _mem_row(sid="PRIOR_B", ts="2026-02-03T10:00:00+00:00", eid="P2"),
        _mem_row(sid="SID-path_c_warm", ts="2026-04-01T10:00:00+00:00", eid="E0"),
    ]
    warm = _artifact(
        mode_name="path_c_warm",
        mode_value="PATH_C_WARM",
        records=records,
        memory_rows=mem,
    )
    report = build_compare_report(
        {"path_c_warm": warm},
        baseline_mode="path_c_warm",
        min_records_for_shift=3,
    )
    md = render_thesis_markdown(report)
    assert "## Cumulative memory provenance (B3)" in md
    assert "PRIOR_A" in md and "PRIOR_B" in md
    # Existing thesis block still present.
    assert "## Relation to calibrated supervision thesis" in md


def test_markdown_has_no_cumulative_section_when_block_absent():
    records = [_ser(event_id=f"E{i}") for i in range(2)]
    art = _artifact(
        mode_name="baseline_static",
        mode_value="BASELINE_STATIC",
        records=records,
    )
    report = build_compare_report(
        {"baseline_static": art},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    md = render_thesis_markdown(report)
    assert "Cumulative memory provenance" not in md


def test_markdown_is_pure_function_with_cumulative_block():
    records = [_ser(event_id="E0", mode="PATH_C_WARM")]
    mem = [_mem_row(sid="PRIOR_A", ts="2026-02-01T10:00:00+00:00", eid="P0")]
    warm = _artifact(
        mode_name="path_c_warm",
        mode_value="PATH_C_WARM",
        records=records,
        memory_rows=mem,
    )
    report = build_compare_report(
        {"path_c_warm": warm},
        baseline_mode="path_c_warm",
        min_records_for_shift=3,
    )
    md_a = render_thesis_markdown(report)
    md_b = render_thesis_markdown(report)
    assert md_a == md_b


# ---------------------------------------------------------------------------
# Determinism of the summary itself
# ---------------------------------------------------------------------------


def test_build_compare_report_with_cumulative_is_deterministic():
    records = [_ser(event_id="E0", mode="PATH_C_WARM")]
    mem = [
        _mem_row(sid="PRIOR_A", ts="2026-02-01T10:00:00+00:00", eid="P0"),
        _mem_row(sid="PRIOR_B", ts="2026-02-02T10:00:00+00:00", eid="P1"),
    ]
    art = _artifact(
        mode_name="path_c_warm",
        mode_value="PATH_C_WARM",
        records=records,
        memory_rows=mem,
    )
    r1 = build_compare_report(
        {"path_c_warm": art},
        baseline_mode="path_c_warm",
        min_records_for_shift=3,
    )
    r2 = build_compare_report(
        {"path_c_warm": art},
        baseline_mode="path_c_warm",
        min_records_for_shift=3,
    )
    assert r1 == r2


# ---------------------------------------------------------------------------
# Forbidden-source guard: the cumulative-summary builders must not
# touch KPI / governance / agent / correlator / replan fields. The
# block is derived only from memory_snapshot + session_id.
# ---------------------------------------------------------------------------


_FORBIDDEN_SOURCE_STRINGS = {
    # Governance NL fields.
    "cost_summary",
    "confidence_note",
    "rationale_trace",
    "situational_explanation",
    "alternative_actions",
    # KPI attribute names.
    "sla_preservation_rate",
    "avg_cost_per_event",
    "calibrated_autonomy_score",
    "human_escalation_rate",
    "auto_execute_rate",
    # Agent-/decision-side attribute names.
    "governance_output",
    "_governance_meta",
    "cost_output",
    # B1/B2 sibling-block internals.
    "replan_trace",
    "replan_triggers",
    "correlation_context",
    "correlation_signal",
}


def _scan_names_and_strings(source: str) -> set[str]:
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found


@pytest.mark.parametrize(
    "fn",
    [
        _sc._build_cumulative_memory_summary,
        _sc._build_per_session_cumulative_block,
        _sc._any_cumulative_memory_in_artifacts,
        _sc._iter_memory_snapshot_records,
    ],
)
def test_cumulative_summary_builders_avoid_forbidden_names(fn):
    source = inspect.getsource(fn)
    seen = _scan_names_and_strings(source)
    hit = _FORBIDDEN_SOURCE_STRINGS & seen
    assert not hit, (
        f"{fn.__name__} references forbidden names/strings: "
        f"{sorted(hit)!r}. cumulative_memory_summary must derive "
        f"only from memory_snapshot + session_id."
    )


# ---------------------------------------------------------------------------
# Schema-version stability (B3 does NOT bump the compare version)
# ---------------------------------------------------------------------------


def test_compare_schema_version_unchanged_when_cumulative_absent():
    records = [_ser(event_id=f"E{i}") for i in range(2)]
    a = _artifact(
        mode_name="baseline_static",
        mode_value="BASELINE_STATIC",
        records=records,
    )
    report = build_compare_report(
        {"baseline_static": a},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    assert report["schema_version"] == COMPARE_REPORT_SCHEMA_VERSION
    assert COMPARE_REPORT_SCHEMA_VERSION == "1.1"


def test_compare_schema_version_unchanged_when_cumulative_present():
    records = [_ser(event_id="E0", mode="PATH_C_WARM")]
    mem = [_mem_row(sid="PRIOR_X", ts="2026-02-01T10:00:00+00:00", eid="P0")]
    art = _artifact(
        mode_name="path_c_warm",
        mode_value="PATH_C_WARM",
        records=records,
        memory_rows=mem,
    )
    report = build_compare_report(
        {"path_c_warm": art},
        baseline_mode="path_c_warm",
        min_records_for_shift=3,
    )
    assert report["schema_version"] == "1.1"
    assert "cumulative_memory_summary" in report
