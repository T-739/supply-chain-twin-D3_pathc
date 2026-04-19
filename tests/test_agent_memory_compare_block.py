"""B4 Slice 2D3-A: ``session_compare`` ``agent_memory_experiment_summary``
conditional sibling block.

Pins:

- Default 3-mode compare (no new kwarg) does NOT emit the block —
  pre-2D3 byte identity preserved.
- ``COMPARE_REPORT_SCHEMA_VERSION`` stays ``"1.1"`` (no bump).
- When ``agent_memory_variant_tags`` is supplied AND every tag is
  present in ``artifacts``, the block appears with a stable shape.
- When the supplied tags are not all present in ``artifacts``, the
  block is omitted (defensive).
- The block carries only structural information — no KPI math, no
  natural-language paraphrase, no agent-output read.
- Diverged-event extraction is restricted to the
  ``path_c_warm_policy_only`` vs
  ``path_c_warm_agent_visible_memory`` pair.
- Markdown renderer emits a short B4 section iff the block is
  present.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from session.session_compare import (  # noqa: E402
    COMPARE_REPORT_SCHEMA_VERSION,
    build_compare_report,
    render_thesis_markdown,
)
from session.session_schema import (  # noqa: E402
    EffectiveDecisionRef,
    GovernanceTruthRef,
    SessionArtifact,
    SessionConfig,
    SessionEventRecord,
    SessionKPIs,
)


_B4_TRIPLET: tuple[str, ...] = (
    "baseline_static",
    "path_c_warm_policy_only",
    "path_c_warm_agent_visible_memory",
)


# ---------------------------------------------------------------------------
# Minimal fixtures (mirrors test_session_compare patterns)
# ---------------------------------------------------------------------------


def _ser(
    *,
    event_id: str,
    route: str = "AUTO_EXECUTE",
    action: Optional[str] = "EXPEDITE",
    status: str = "executed",
    cost: Optional[float] = 100.0,
    preserved: Optional[bool] = True,
    mode: str = "BASELINE_STATIC",
) -> SessionEventRecord:
    if cost is None and preserved is None:
        outcome: Optional[dict[str, Any]] = None
    else:
        outcome = {
            "action_taken": action,
            "cost_incurred": cost,
            "sla_impact": {"preserved": preserved},
        }
    return SessionEventRecord(
        baseline_event_result={
            "event_id": event_id,
            "execution_outcome": outcome,
            "policy_decision": {"route": route},
            "execution_status": status,
        },
        session_id=f"SID-{mode}",
        mode=mode,
        policy_route_source="baseline_static",
        adaptive_adjustment=None,
        governance_truth=GovernanceTruthRef(
            risk_level="LOW", recommended_candidate_type="EXPEDITE",
        ),
        effective_decision=EffectiveDecisionRef(
            effective_risk="LOW",
            final_route=route,
            action_taken=action if action in (
                "EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION",
            ) else None,
            execution_status=status,
        ),
    )


def _artifact(tag: str, mode_value: str, records: list[SessionEventRecord]) -> SessionArtifact:
    return SessionArtifact(
        session_id=f"SID-{tag}",
        config=SessionConfig(
            seed=42, mode=mode_value, events_source="demo_stream",
        ),
        event_records=records,
        memory_snapshot={"records": [], "schema_version": "1.0"},
        kpis=SessionKPIs(events_observed=len(records)),
        schema_versions={},
        notes="",
    )


def _three_mode_default_set() -> dict[str, SessionArtifact]:
    """Pre-2D3 default 3-mode set: baseline / cold / warm."""
    base_records = [_ser(event_id=f"E{i}") for i in range(4)]
    cold_records = [_ser(event_id=f"E{i}", mode="PATH_C_COLD") for i in range(4)]
    warm_records = [_ser(event_id=f"E{i}", mode="PATH_C_WARM") for i in range(4)]
    return {
        "baseline_static": _artifact("baseline_static", "BASELINE_STATIC", base_records),
        "path_c_cold": _artifact("path_c_cold", "PATH_C_COLD", cold_records),
        "path_c_warm": _artifact("path_c_warm", "PATH_C_WARM", warm_records),
    }


def _b4_triplet_artifacts(*, divergent_event_ids: tuple[str, ...] = ()) -> dict[str, SessionArtifact]:
    """B4 Slice 2D2 locked triplet of artifacts.

    Optional ``divergent_event_ids`` lets us inject divergence between
    the policy-only and agent-visible warm variants on specific event
    ids — used to pin the
    ``agent_visible_vs_policy_only_diverged_event_ids`` extraction.
    """
    base_records = [_ser(event_id=f"E{i}") for i in range(4)]
    policy_records = [_ser(event_id=f"E{i}", mode="PATH_C_WARM") for i in range(4)]
    agent_records = []
    for i in range(4):
        eid = f"E{i}"
        if eid in divergent_event_ids:
            # Diverge on (route, action) so _find_diverged_events fires
            # on this event index across the three artifacts.
            agent_records.append(_ser(
                event_id=eid, mode="PATH_C_WARM",
                route="HUMAN_REQUIRED",
                action=None,
                status="awaiting_human_review",
                cost=None,
                preserved=None,
            ))
        else:
            agent_records.append(_ser(event_id=eid, mode="PATH_C_WARM"))
    return {
        "baseline_static": _artifact(
            "baseline_static", "BASELINE_STATIC", base_records,
        ),
        "path_c_warm_policy_only": _artifact(
            "path_c_warm_policy_only", "PATH_C_WARM", policy_records,
        ),
        "path_c_warm_agent_visible_memory": _artifact(
            "path_c_warm_agent_visible_memory", "PATH_C_WARM", agent_records,
        ),
    }


# ---------------------------------------------------------------------------
# 1. Default 3-mode compare — no block, no version bump
# ---------------------------------------------------------------------------


def test_default_3_mode_compare_omits_b4_block():
    """The pre-2D3 default 3-mode compare must NOT emit
    ``agent_memory_experiment_summary``."""
    artifacts = _three_mode_default_set()
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    assert "agent_memory_experiment_summary" not in report


def test_compare_report_schema_version_unchanged_at_1_1():
    """No bump in 2D3-A — the new sibling block is strictly
    additive (B1 / B2 / B3 precedent)."""
    assert COMPARE_REPORT_SCHEMA_VERSION == "1.1"
    artifacts = _three_mode_default_set()
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    assert report["schema_version"] == "1.1"


def test_default_compare_byte_identical_with_or_without_kwarg_when_none():
    """Calling ``build_compare_report`` without ``agent_memory_variant_tags``
    and calling it with ``agent_memory_variant_tags=None`` must produce
    byte-identical output."""
    artifacts = _three_mode_default_set()
    a = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    b = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
        agent_memory_variant_tags=None,
    )
    assert a == b
    assert "agent_memory_experiment_summary" not in b


# ---------------------------------------------------------------------------
# 2. Block appears when triplet is supplied AND complete
# ---------------------------------------------------------------------------


def test_b4_block_present_when_full_triplet_supplied():
    artifacts = _b4_triplet_artifacts()
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
        agent_memory_variant_tags=_B4_TRIPLET,
    )
    assert "agent_memory_experiment_summary" in report
    block = report["agent_memory_experiment_summary"]
    # Stable, structural shape — no KPI math, no NL paraphrase.
    assert set(block.keys()) == {
        "schema_version",
        "variant_tags",
        "session_ids_by_variant",
        "agent_visible_vs_policy_only_diverged_event_ids",
        "notes",
    }
    assert block["schema_version"] == "1.0"
    assert block["variant_tags"] == list(_B4_TRIPLET)
    assert block["session_ids_by_variant"] == {
        "baseline_static": "SID-baseline_static",
        "path_c_warm_policy_only": "SID-path_c_warm_policy_only",
        "path_c_warm_agent_visible_memory":
            "SID-path_c_warm_agent_visible_memory",
    }
    assert isinstance(block["notes"], str) and block["notes"]


def test_b4_block_absent_when_partial_triplet_in_artifacts():
    """If the caller asks for the block but only a subset of the
    triplet exists in ``artifacts``, the block is silently omitted
    (defensive — never raise on a partially-completed triplet)."""
    artifacts = _b4_triplet_artifacts()
    # Drop one variant.
    del artifacts["path_c_warm_agent_visible_memory"]
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
        agent_memory_variant_tags=_B4_TRIPLET,
    )
    assert "agent_memory_experiment_summary" not in report


def test_b4_block_absent_when_empty_tag_list_supplied():
    """An empty tag list is treated as ``no opt-in`` — block omitted."""
    artifacts = _b4_triplet_artifacts()
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
        agent_memory_variant_tags=(),
    )
    assert "agent_memory_experiment_summary" not in report


# ---------------------------------------------------------------------------
# 3. Diverged-event extraction restricted to the WARM pair
# ---------------------------------------------------------------------------


def test_b4_block_diverged_event_ids_only_from_warm_pair():
    """``agent_visible_vs_policy_only_diverged_event_ids`` must
    reflect ONLY divergence between the two PATH_C_WARM variants —
    baseline-vs-warm divergence does not contribute to this list."""
    # Inject divergence between policy-only and agent-visible warm
    # variants on E1 only.
    artifacts = _b4_triplet_artifacts(divergent_event_ids=("E1",))
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
        agent_memory_variant_tags=_B4_TRIPLET,
    )
    block = report["agent_memory_experiment_summary"]
    assert block["agent_visible_vs_policy_only_diverged_event_ids"] == ["E1"]


def test_b4_block_diverged_event_ids_empty_when_pair_matches():
    artifacts = _b4_triplet_artifacts()
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
        agent_memory_variant_tags=_B4_TRIPLET,
    )
    block = report["agent_memory_experiment_summary"]
    assert block["agent_visible_vs_policy_only_diverged_event_ids"] == []


# ---------------------------------------------------------------------------
# 4. No KPI math / no agent output / no NL paraphrase in the block
# ---------------------------------------------------------------------------


def test_b4_block_carries_no_kpi_or_agent_output_keys():
    """The block must not leak KPI keys, governance fields, or NL
    governance text into the structural summary."""
    artifacts = _b4_triplet_artifacts()
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
        agent_memory_variant_tags=_B4_TRIPLET,
    )
    block = report["agent_memory_experiment_summary"]
    forbidden = {
        "sla_preservation_rate", "avg_cost_per_event",
        "calibrated_autonomy_score", "human_escalation_rate",
        "auto_execute_rate", "known_outcome_coverage",
        "cost_summary", "confidence_note", "rationale_trace",
        "situational_explanation", "alternative_actions",
        "governance_truth", "effective_decision",
        "kpi_matrix", "deltas",
    }
    leaks = set(block.keys()) & forbidden
    assert not leaks, f"B4 block leaked forbidden keys: {sorted(leaks)!r}"


# ---------------------------------------------------------------------------
# 5. Markdown renderer emits the short B4 section iff block is present
# ---------------------------------------------------------------------------


def test_thesis_markdown_omits_b4_section_when_block_absent():
    artifacts = _three_mode_default_set()
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    md = render_thesis_markdown(report)
    assert "Agent-visible memory experiment" not in md
    assert "agent_memory_experiment_summary" not in md


def test_thesis_markdown_emits_b4_section_when_block_present():
    artifacts = _b4_triplet_artifacts(divergent_event_ids=("E2",))
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
        agent_memory_variant_tags=_B4_TRIPLET,
    )
    md = render_thesis_markdown(report)
    # Section heading + canonical variant tags appear.
    assert "Agent-visible memory experiment" in md
    for tag in _B4_TRIPLET:
        assert tag in md
    # Diverged event id appears.
    assert "E2" in md


def test_thesis_markdown_is_pure_function_of_compare_report():
    """Same compare report → byte-identical markdown."""
    artifacts = _b4_triplet_artifacts()
    report = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
        agent_memory_variant_tags=_B4_TRIPLET,
    )
    a = render_thesis_markdown(report)
    b = render_thesis_markdown(report)
    assert a == b


# ---------------------------------------------------------------------------
# 6. Default-set with the kwarg supplied is a no-op (caller error
#    safety: passing tags that aren't in artifacts is silently OFF).
# ---------------------------------------------------------------------------


def test_default_3_mode_with_b4_tags_supplied_is_noop():
    """Caller passes B4 triplet tags but artifacts dict is the
    default 3-mode set (no triplet variants present): block is
    omitted, behavior matches not-supplying the kwarg."""
    artifacts = _three_mode_default_set()
    a = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
    )
    b = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=3,
        agent_memory_variant_tags=_B4_TRIPLET,
    )
    assert a == b
    assert "agent_memory_experiment_summary" not in b
