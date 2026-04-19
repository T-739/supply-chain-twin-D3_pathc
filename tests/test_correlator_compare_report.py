"""B2 Slice 2C: correlation_summary sibling block on the compare report.

Pins that:

  - when no compared artifact carries a ``correlation_context``,
    ``build_compare_report`` does NOT emit a ``correlation_summary``
    key and the rendered markdown contains no correlation section;
  - when at least one artifact does, an additive
    ``correlation_summary`` block appears with deterministic
    structural content (pattern counts, event ids, per-session
    summaries);
  - existing compare blocks (``kpi_matrix``, ``deltas``,
    ``diverged_events``, ``thesis_claim_support``,
    ``replan_trace_summary``) keep their shape and values regardless
    of correlator presence;
  - the rendered markdown is a pure function of the compare report
    (same input → same bytes);
  - the summary is derived only from ``correlation_context`` and
    existing metadata — no KPI, no agent output, no governance NL
    field.
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

from correlator.correlator_schema import (
    CorrelationContext,
    CorrelationSignal,
)
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


def _rec(
    *,
    event_id: str,
    correlation_context: Optional[CorrelationContext] = None,
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
        correlation_context=correlation_context,
    )


def _artifact(
    mode_name: str, mode_value: str, records: list[SessionEventRecord],
) -> SessionArtifact:
    return SessionArtifact(
        session_id=f"SID-{mode_name}",
        config=SessionConfig(
            seed=42, mode=mode_value, events_source="demo_stream",
        ),
        event_records=records,
        memory_snapshot={"records": [], "schema_version": "1.0"},
        kpis=SessionKPIs(events_observed=len(records)),
        schema_versions={},
        notes="",
    )


def _p1_signal(
    *, triggering: str, participants: list[str],
    window_size: int = 3, start: int = 0, end: int = 1,
) -> CorrelationSignal:
    return CorrelationSignal(
        pattern_id="ETA_PATH_COMPOUND",
        triggering_event_id=triggering,
        participant_event_ids=participants,
        shared_entities=[],
        window_start_ordinal=start,
        window_end_ordinal=end,
        window_size=window_size,
        matched_conditions=["SHARED_ETA_PATH", "STREAM_ADJACENT"],
    )


def _p3_signal(
    *, triggering: str, participants: list[str],
    window_size: int = 3, start: int = 0, end: int = 1,
) -> CorrelationSignal:
    # Carrier-focused signal. Use AffectedEntityRef shape without
    # importing it directly — CorrelationSignal accepts the dict form
    # via pydantic validation.
    from event_schema import AffectedEntityRef  # local import to avoid top-level noise

    return CorrelationSignal(
        pattern_id="CARRIER_DOUBLE_HIT",
        triggering_event_id=triggering,
        participant_event_ids=participants,
        shared_entities=[
            AffectedEntityRef(entity_type="carrier", entity_id="CR_1"),
        ],
        window_start_ordinal=start,
        window_end_ordinal=end,
        window_size=window_size,
        matched_conditions=["SAME_ENTITY_ID", "STREAM_ADJACENT"],
    )


def _ctx(signals: list[CorrelationSignal]) -> CorrelationContext:
    return CorrelationContext(
        signals=signals,
        window_size=3,
        window_events_considered=max(
            2, len(signals) + 1,
        ) if signals else 1,
    )


# ---------------------------------------------------------------------------
# Shape invariance: no correlation data → no block, no section
# ---------------------------------------------------------------------------


def test_no_correlation_anywhere_omits_block():
    records = [_rec(event_id=f"E{i}") for i in range(4)]
    a = _artifact("baseline_static", "BASELINE_STATIC", records)
    b = _artifact("path_c_cold", "PATH_C_COLD", records)
    report = build_compare_report(
        {"baseline_static": a, "path_c_cold": b},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    assert "correlation_summary" not in report
    md = render_thesis_markdown(report)
    assert "Correlation observations" not in md
    assert "ETA_PATH_COMPOUND" not in md
    assert "CARRIER_DOUBLE_HIT" not in md


def test_no_correlation_keeps_existing_top_level_keys_stable():
    records = [_rec(event_id=f"E{i}") for i in range(4)]
    a = _artifact("baseline_static", "BASELINE_STATIC", records)
    report = build_compare_report(
        {"baseline_static": a},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    expected_top_keys = {
        "schema_version", "sessions_compared", "baseline_mode",
        "min_records_for_shift", "per_session_kpi_report",
        "kpi_matrix", "deltas", "diverged_events",
        "thesis_claim_support",
    }
    assert set(report.keys()) == expected_top_keys


# ---------------------------------------------------------------------------
# Additive block appears when correlation data is present
# ---------------------------------------------------------------------------


def test_correlation_summary_appears_when_data_present():
    # Baseline: no correlator data. Path C cold: E1 has one P1
    # signal, E2 has one P3 signal.
    base_records = [_rec(event_id=f"E{i}") for i in range(3)]
    cold_records = [
        _rec(event_id="E0", mode="PATH_C_COLD"),
        _rec(
            event_id="E1",
            mode="PATH_C_COLD",
            correlation_context=_ctx(
                [_p1_signal(triggering="E1", participants=["E0", "E1"])]
            ),
        ),
        _rec(
            event_id="E2",
            mode="PATH_C_COLD",
            correlation_context=_ctx(
                [_p3_signal(triggering="E2", participants=["E0", "E2"], start=0, end=2)]
            ),
        ),
    ]
    base = _artifact("baseline_static", "BASELINE_STATIC", base_records)
    cold = _artifact("path_c_cold", "PATH_C_COLD", cold_records)

    report = build_compare_report(
        {"baseline_static": base, "path_c_cold": cold},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )

    assert "correlation_summary" in report
    cs = report["correlation_summary"]

    # Only the mode with correlation data is listed.
    assert cs["sessions_with_correlation_data"] == ["path_c_cold"]

    # Per-session block structure.
    psc = cs["per_session"]["path_c_cold"]
    assert psc["events_with_context"] == 2  # E1, E2 have contexts
    assert psc["events_with_signals"] == 2
    assert psc["total_signals"] == 2
    assert psc["pattern_counts"] == {
        "CARRIER_DOUBLE_HIT": 1,
        "ETA_PATH_COMPOUND": 1,
    }
    assert psc["correlated_event_ids"] == ["E1", "E2"]
    # signals_by_event carries full structural signal dumps.
    assert [e["event_id"] for e in psc["signals_by_event"]] == ["E1", "E2"]
    assert [e["event_index"] for e in psc["signals_by_event"]] == [1, 2]

    # Overall and union fields.
    assert cs["overall_pattern_counts"] == {
        "CARRIER_DOUBLE_HIT": 1,
        "ETA_PATH_COMPOUND": 1,
    }
    assert cs["all_correlated_event_ids"] == ["E1", "E2"]


def test_empty_signals_context_counts_only_events_with_context():
    # Simulate correlator enabled but no pattern fired — context
    # present but with empty signals list on every record.
    records = [
        _rec(
            event_id=f"E{i}",
            mode="PATH_C_COLD",
            correlation_context=CorrelationContext(
                signals=[],
                window_size=3,
                window_events_considered=min(i + 1, 3),
            ),
        )
        for i in range(3)
    ]
    art = _artifact("path_c_cold", "PATH_C_COLD", records)
    report = build_compare_report(
        {"path_c_cold": art},
        baseline_mode="path_c_cold",
        min_records_for_shift=3,
    )
    assert "correlation_summary" in report
    psc = report["correlation_summary"]["per_session"]["path_c_cold"]
    assert psc["events_with_context"] == 3
    assert psc["events_with_signals"] == 0
    assert psc["total_signals"] == 0
    assert psc["pattern_counts"] == {}
    assert psc["correlated_event_ids"] == []
    assert psc["signals_by_event"] == []
    assert report["correlation_summary"]["overall_pattern_counts"] == {}
    assert report["correlation_summary"]["all_correlated_event_ids"] == []


def test_per_session_sorted_by_mode_name():
    cold_records = [
        _rec(
            event_id="E0",
            mode="PATH_C_COLD",
            correlation_context=_ctx(
                [_p1_signal(triggering="E0", participants=["E0", "E1"])]
            ),
        ),
    ]
    warm_records = [
        _rec(
            event_id="E0",
            mode="PATH_C_WARM",
            correlation_context=_ctx(
                [_p1_signal(triggering="E0", participants=["E0", "E1"])]
            ),
        ),
    ]
    cold = _artifact("path_c_cold", "PATH_C_COLD", cold_records)
    warm = _artifact("path_c_warm", "PATH_C_WARM", warm_records)

    report = build_compare_report(
        {"path_c_warm": warm, "path_c_cold": cold},
        baseline_mode="path_c_cold",
        min_records_for_shift=3,
    )
    cs = report["correlation_summary"]
    # sessions_compared is alphabetical; sessions_with_correlation_data
    # follows the same sort order.
    assert cs["sessions_with_correlation_data"] == ["path_c_cold", "path_c_warm"]
    assert list(cs["per_session"].keys()) == ["path_c_cold", "path_c_warm"]
    assert cs["overall_pattern_counts"] == {"ETA_PATH_COMPOUND": 2}


# ---------------------------------------------------------------------------
# Existing-field stability when correlation is present
# ---------------------------------------------------------------------------


def test_existing_blocks_untouched_when_correlation_present():
    records_no_ctx = [_rec(event_id=f"E{i}") for i in range(3)]
    records_with_ctx = [
        _rec(
            event_id=f"E{i}",
            correlation_context=_ctx(
                [_p1_signal(triggering=f"E{i}", participants=[f"E{i-1 if i else 0}", f"E{i}"])]
            ),
        )
        if i > 0 else _rec(event_id=f"E{i}")
        for i in range(3)
    ]
    a = _artifact("baseline_static", "BASELINE_STATIC", records_no_ctx)
    # Same records semantically, just with correlation contexts added.
    a_with = _artifact(
        "baseline_static", "BASELINE_STATIC", records_with_ctx,
    )

    report_plain = build_compare_report(
        {"baseline_static": a},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    report_with_corr = build_compare_report(
        {"baseline_static": a_with},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )

    # Existing blocks must be byte-identical between the two reports,
    # since correlator output does not feed any other compare block.
    for key in (
        "sessions_compared", "kpi_matrix", "deltas",
        "diverged_events", "thesis_claim_support",
        "per_session_kpi_report",
    ):
        assert report_plain[key] == report_with_corr[key], (
            f"existing compare block {key!r} drifted when correlation was added"
        )
    # Correlation summary appears only on the second report.
    assert "correlation_summary" not in report_plain
    assert "correlation_summary" in report_with_corr


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def test_markdown_renders_correlation_section_when_block_present():
    records = [
        _rec(
            event_id="E0",
            mode="PATH_C_COLD",
            correlation_context=_ctx(
                [_p1_signal(triggering="E0", participants=["E0", "E1"])]
            ),
        ),
        _rec(
            event_id="E1",
            mode="PATH_C_COLD",
            correlation_context=_ctx(
                [_p3_signal(triggering="E1", participants=["E0", "E1"])]
            ),
        ),
    ]
    cold = _artifact("path_c_cold", "PATH_C_COLD", records)
    report = build_compare_report(
        {"path_c_cold": cold},
        baseline_mode="path_c_cold",
        min_records_for_shift=3,
    )
    md = render_thesis_markdown(report)
    assert "## Correlation observations (B2)" in md
    assert "ETA_PATH_COMPOUND" in md
    assert "CARRIER_DOUBLE_HIT" in md
    # Event ids appear in the correlated-events sentence.
    assert "`E0`" in md and "`E1`" in md
    # Existing thesis block still present.
    assert "## Relation to calibrated supervision thesis" in md


def test_markdown_has_no_correlation_section_when_block_absent():
    records = [_rec(event_id=f"E{i}") for i in range(3)]
    a = _artifact("baseline_static", "BASELINE_STATIC", records)
    b = _artifact("path_c_cold", "PATH_C_COLD", records)
    report = build_compare_report(
        {"baseline_static": a, "path_c_cold": b},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    md = render_thesis_markdown(report)
    assert "Correlation observations" not in md


def test_markdown_is_pure_function_with_correlation_block():
    records = [
        _rec(
            event_id=f"E{i}",
            mode="PATH_C_COLD",
            correlation_context=_ctx(
                [_p1_signal(triggering=f"E{i}", participants=[f"E{max(i-1,0)}", f"E{i}"])]
            ),
        )
        for i in range(3)
    ]
    cold = _artifact("path_c_cold", "PATH_C_COLD", records)
    report = build_compare_report(
        {"path_c_cold": cold},
        baseline_mode="path_c_cold",
        min_records_for_shift=3,
    )
    md1 = render_thesis_markdown(report)
    md2 = render_thesis_markdown(report)
    assert md1 == md2


# ---------------------------------------------------------------------------
# Determinism of the summary itself
# ---------------------------------------------------------------------------


def test_build_compare_report_with_correlation_is_deterministic():
    records = [
        _rec(
            event_id=f"E{i}",
            mode="PATH_C_COLD",
            correlation_context=_ctx(
                [_p1_signal(triggering=f"E{i}", participants=[f"E{max(i-1,0)}", f"E{i}"])]
            ),
        )
        for i in range(3)
    ]
    cold = _artifact("path_c_cold", "PATH_C_COLD", records)
    report_1 = build_compare_report(
        {"path_c_cold": cold},
        baseline_mode="path_c_cold",
        min_records_for_shift=3,
    )
    report_2 = build_compare_report(
        {"path_c_cold": cold},
        baseline_mode="path_c_cold",
        min_records_for_shift=3,
    )
    assert report_1 == report_2


# ---------------------------------------------------------------------------
# Forbidden-source guard: the correlation-summary builder must not
# touch KPI fields, agent outputs, or governance NL fields.
# ---------------------------------------------------------------------------


_FORBIDDEN_SOURCE_STRINGS = {
    # Governance NL fields (never authoritative for correlator).
    "cost_summary",
    "confidence_note",
    "rationale_trace",
    "situational_explanation",
    "alternative_actions",
    # KPI-internal attribute names. The summary must not read KPI
    # values; every piece of data comes from correlation_context.
    "sla_preservation_rate",
    "avg_cost_per_event",
    "calibrated_autonomy_score",
    "human_escalation_rate",
    "auto_execute_rate",
    # Agent-output-specific attributes.
    "governance_output",
    "_governance_meta",
    "cost_output",
}


def _scan_names_and_strings(source: str) -> set[str]:
    """Return the set of identifier names and string-literal values
    referenced in ``source``. Used to assert that the Slice 2C
    correlation-summary builders do not touch forbidden names."""
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
        _sc._build_correlation_summary,
        _sc._build_per_session_correlation_block,
        _sc._any_correlation_context_in_artifacts,
        _sc._event_id_for_record,
    ],
)
def test_correlation_summary_builders_avoid_forbidden_names(fn):
    source = inspect.getsource(fn)
    seen = _scan_names_and_strings(source)
    hit = _FORBIDDEN_SOURCE_STRINGS & seen
    assert not hit, (
        f"{fn.__name__} references forbidden names/strings: {sorted(hit)!r}. "
        f"correlation_summary must be derived from correlation_context only."
    )


# ---------------------------------------------------------------------------
# Schema version stability — the additive sibling block does NOT
# bump the top-level version (pre-B2 compares stay byte-identical
# at the version-string level; readers key off sibling presence).
# ---------------------------------------------------------------------------


def test_compare_schema_version_unchanged_when_correlation_absent():
    assert COMPARE_REPORT_SCHEMA_VERSION == "1.1"
    records = [_rec(event_id=f"E{i}") for i in range(2)]
    a = _artifact("baseline_static", "BASELINE_STATIC", records)
    report = build_compare_report(
        {"baseline_static": a},
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    assert report["schema_version"] == "1.1"


def test_compare_schema_version_unchanged_when_correlation_present():
    records = [
        _rec(
            event_id="E0",
            mode="PATH_C_COLD",
            correlation_context=_ctx(
                [_p1_signal(triggering="E0", participants=["E0", "E1"])]
            ),
        ),
    ]
    art = _artifact("path_c_cold", "PATH_C_COLD", records)
    report = build_compare_report(
        {"path_c_cold": art},
        baseline_mode="path_c_cold",
        min_records_for_shift=3,
    )
    assert report["schema_version"] == "1.1"
    assert "correlation_summary" in report
