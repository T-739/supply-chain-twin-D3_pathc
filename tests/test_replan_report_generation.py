"""B1 Slice 4: thesis markdown rendering — replan section conditional.

Tests the light additive replan section in
``session.session_compare.render_thesis_markdown``:

  - When the compare report has no ``replan_trace_summary``, the
    rendered markdown omits the "Bounded-replan behavior" header
    entirely — the prior report surface is preserved.
  - When the compare report has a ``replan_trace_summary`` block,
    the renderer adds a section with the per-mode replan KPIs and
    trigger-type counts.
  - Rendering is deterministic: same compare report in → same
    markdown out, byte-for-byte.
"""

from __future__ import annotations

import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


def _compare_report_no_replan() -> dict:
    """Minimal valid compare report with no replan data."""
    return {
        "schema_version": "1.0",
        "sessions_compared": ["baseline_static", "path_c_warm"],
        "baseline_mode": "baseline_static",
        "min_records_for_shift": 3,
        "per_session_kpi_report": {
            "baseline_static": {
                "schema_version": "1.0",
                "session_id": "S-B",
                "mode": "BASELINE_STATIC",
                "min_records_for_shift": 3,
                "cold_phase": _empty_phase(),
                "warm_phase": _empty_phase(),
                "overall": _empty_phase(),
            },
            "path_c_warm": {
                "schema_version": "1.0",
                "session_id": "S-W",
                "mode": "PATH_C_WARM",
                "min_records_for_shift": 3,
                "cold_phase": _empty_phase(),
                "warm_phase": _empty_phase(),
                "overall": _empty_phase(),
            },
        },
        "kpi_matrix": _empty_matrix(),
        "deltas": {"path_c_warm_minus_baseline_static": _empty_delta()},
        "diverged_events": [],
        "thesis_claim_support": {
            "claim": "Path C is great.",
            "warm_calibrated_autonomy_delta": None,
            "warm_sla_preservation_delta": None,
            "warm_cost_delta": None,
            "supports_claim": None,
            "notes": "",
        },
    }


def _empty_phase() -> dict:
    return {
        "events_observed": 0,
        "events_with_outcome": 0,
        "events_skipped": 0,
        "events_failed": 0,
        "events_processed": 0,
        "sla_preservation_rate": None,
        "avg_cost_per_event": None,
        "calibrated_autonomy_score": None,
        "human_escalation_rate": None,
        "auto_execute_rate": None,
        "known_outcome_coverage": None,
    }


def _empty_delta() -> dict:
    return {
        "sla_preservation_rate": None,
        "avg_cost_per_event": None,
        "calibrated_autonomy_score": None,
        "human_escalation_rate": None,
        "auto_execute_rate": None,
        "known_outcome_coverage": None,
    }


def _empty_matrix() -> dict:
    kpi_keys = [
        "events_observed", "events_with_outcome", "events_skipped",
        "events_failed", "events_processed", "sla_preservation_rate",
        "avg_cost_per_event", "calibrated_autonomy_score",
        "human_escalation_rate", "auto_execute_rate",
        "known_outcome_coverage",
    ]
    modes = ["baseline_static", "path_c_warm"]
    return {
        seg: {k: {m: 0 for m in modes} for k in kpi_keys}
        for seg in ("cold_phase", "warm_phase", "overall")
    }


def _with_replan_block(report: dict) -> dict:
    out = dict(report)
    out["replan_trace_summary"] = {
        "sessions_with_replan": ["path_c_warm"],
        "total_replan_events": 3,
        "trigger_type_counts": {
            "path_c_warm": {
                "NO_TRIGGER": 0,
                "COST_DEVIATION": 2,
                "SLA_DEVIATION": 1,
                "EXECUTION_FAILED": 0,
                "PREFLIGHT_FAILED": 0,
            },
        },
        "recovered_events_count": {"path_c_warm": 2},
        "by_mode": {
            "path_c_warm": {
                "replan_kpis_overall": {
                    "replan_events_observed": 3,
                    "replan_fire_count": 3,
                    "replan_trigger_rate": 0.3,
                    "replan_success_count": 2,
                    "replan_recovery_rate": 0.6667,
                },
                "events_with_trace": 3,
                "recovered_events": 2,
            },
        },
    }
    return out


# ---------------------------------------------------------------------------
# (1) No replan_trace_summary → markdown has no Replan header
# ---------------------------------------------------------------------------


def test_no_replan_section_when_no_summary_block():
    from session.session_compare import render_thesis_markdown

    md = render_thesis_markdown(_compare_report_no_replan())
    assert "Bounded-replan behavior" not in md


# ---------------------------------------------------------------------------
# (2) replan_trace_summary present → markdown includes the section
# ---------------------------------------------------------------------------


def test_replan_section_appears_with_summary():
    from session.session_compare import render_thesis_markdown

    md = render_thesis_markdown(_with_replan_block(_compare_report_no_replan()))
    assert "## Bounded-replan behavior (B1)" in md
    # Per-mode row shows counts/rates.
    assert "path_c_warm" in md
    # Trigger-type counts header carries the five canonical types.
    for ttype in (
        "NO_TRIGGER", "COST_DEVIATION", "SLA_DEVIATION",
        "EXECUTION_FAILED", "PREFLIGHT_FAILED",
    ):
        assert ttype in md


# ---------------------------------------------------------------------------
# (3) Rendering is deterministic
# ---------------------------------------------------------------------------


def test_rendering_is_deterministic_with_replan():
    from session.session_compare import render_thesis_markdown

    report = _with_replan_block(_compare_report_no_replan())
    md_a = render_thesis_markdown(report)
    md_b = render_thesis_markdown(report)
    assert md_a == md_b


def test_rendering_is_deterministic_without_replan():
    from session.session_compare import render_thesis_markdown

    report = _compare_report_no_replan()
    md_a = render_thesis_markdown(report)
    md_b = render_thesis_markdown(report)
    assert md_a == md_b


# ---------------------------------------------------------------------------
# (4) Presence toggles the section — nothing else changes in structure
# ---------------------------------------------------------------------------


def test_pre_b1_surface_preserved_minus_replan_section():
    """All non-replan headers must appear in both the no-replan and
    replan-present markdowns; only the replan section should be the
    difference."""
    from session.session_compare import render_thesis_markdown

    md_base = render_thesis_markdown(_compare_report_no_replan())
    md_with = render_thesis_markdown(
        _with_replan_block(_compare_report_no_replan()),
    )
    for required_header in (
        "# Path C Phase 3 — Thesis-Aligned Session Compare Report",
        "## Overall KPIs",
        "## Cold-phase KPIs",
        "## Warm-phase KPIs",
        "## Deltas vs baseline (overall)",
        "## Diverged events",
        "## Relation to calibrated supervision thesis",
    ):
        assert required_header in md_base
        assert required_header in md_with
    # Only the presence of the replan section distinguishes the two.
    assert "Bounded-replan behavior" not in md_base
    assert "Bounded-replan behavior" in md_with
