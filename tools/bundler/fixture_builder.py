"""Synthesize fixture bundles without invoking the runtime.

Fixture bundles are deterministic, minimal, and satisfy the
B5 bundle contract (``docs/B5_BUNDLE_CONTRACT.md``). They exist
so backend contract tests and future frontend smoke tests can
load representative bundles without running the eval harness.

The session_artifact.json shapes emitted here are *structurally*
aligned with ``src/session/session_schema.py`` 1.x, but this
module does NOT import that module — the fixtures are pure JSON
literals and stay stable even if the runtime schema bumps a MINOR
version. Backend tests validate that the read-only repository
tolerates the range of actual bundle shapes it will see.
"""

from __future__ import annotations

import json
import os
from typing import Any

from tools.bundler.bundler import build_metadata
from tools.bundler.bundle_schema import (
    B4_TRIPLET_TAGS,
    DEFAULT_3_MODE_TAGS,
)


_FIXTURE_SCHEMA_VERSION_STAMP: dict[str, str] = {
    "session_artifact": "1.0",
    "session_event_record": "1.2",
    "session_kpis": "1.1",
}


def _minimal_session_artifact(
    *,
    session_id: str,
    mode: str,
    events: int = 2,
    seed: int = 42,
) -> dict[str, Any]:
    """Return a minimal but schema-shaped session artifact dict.

    Uses only the fields the B5 backend repository will read. All
    numeric values are deterministic; no wall-clock, no uuid4.
    """
    event_records: list[dict[str, Any]] = []
    for i in range(events):
        event_records.append({
            "baseline_event_result": {
                "schema_version": "1.0",
                "event_id": f"{session_id}-EV-{i:03d}",
                "event_type": "CARRIER_DELAY_ESCALATION",
                "severity": "MEDIUM",
                "scenario_context": {},
                "governance_output": {
                    "risk_level": "MEDIUM",
                    "recommended_action": "EXPEDITE",
                },
                "policy_decision": {},
                "execution_status": "executed",
                "execution_outcome": {
                    "cost_incurred": 100.0 + i,
                    "sla_impact": {"preserved": True},
                },
                "trace_log": [],
            },
            "session_id": session_id,
            "mode": mode,
            "policy_route_source": "baseline_static",
            "adaptive_adjustment": None,
            "governance_truth": {
                "risk_level": "MEDIUM",
                "recommended_candidate_type": "EXPEDITE",
                "schema_version": "1.0",
            },
            "effective_decision": {
                "effective_risk": "MEDIUM",
                "final_route": "AUTO_EXECUTE",
                "action_taken": "EXPEDITE",
                "execution_status": "executed",
                "schema_version": "1.0",
            },
            "memory_record_id": None,
            "replan_trace": None,
            "replan_triggers": None,
            "correlation_context": None,
            "notes": "",
            "schema_version": "1.2",
        })

    return {
        "session_id": session_id,
        "config": {
            "seed": seed,
            "mode": mode,
            "events_source": "fixture_stream",
            "initial_memory_digest": "",
            "schema_version": "1.0",
        },
        "event_records": event_records,
        "memory_snapshot": {"records": []},
        "kpis": {
            "events_observed": events,
            "events_with_outcome": events,
            "events_skipped": 0,
            "events_failed": 0,
            "events_processed": events,
            "auto_execute_success_rate": 1.0,
            "sla_preservation_rate": 1.0,
            "total_cost": round(sum(100.0 + i for i in range(events)), 4),
            "avg_cost": 100.0 + (events - 1) / 2.0,
            "known_outcome_coverage": 1.0,
            "replan_events_observed": 0,
            "replan_fire_count": 0,
            "replan_trigger_rate": None,
            "replan_success_count": 0,
            "replan_recovery_rate": None,
            "schema_version": "1.1",
        },
        "schema_versions": dict(_FIXTURE_SCHEMA_VERSION_STAMP),
        "notes": "B5 fixture synthesized via tools/bundler/fixture_builder.py",
        "schema_version": "1.0",
    }


def _minimal_compare_report(variant_tags: list[str]) -> dict[str, Any]:
    """Return a small but shape-valid compare report.

    Mirrors the non-conditional fields ``session_compare``
    produces. Conditional sibling blocks (replan / correlation /
    cumulative / agent_memory_experiment_summary) are
    deliberately omitted so backend models MUST NOT assume they
    are always present.
    """
    return {
        "schema_version": "1.1",
        "sessions_compared": sorted(variant_tags),
        "baseline_mode": "baseline_static",
        "min_records_for_shift": 3,
        "per_session_kpi_report": {},
        "kpi_matrix": {"cold_phase": {}, "warm_phase": {}, "overall": {}},
        "deltas": {},
        "diverged_events": [],
        "thesis_claim_support": {
            "claim": (
                "Path C extends calibrated supervision into a "
                "temporally adaptive semi-autonomy loop."
            ),
            "warm_calibrated_autonomy_delta": None,
            "warm_sla_preservation_delta": None,
            "warm_cost_delta": None,
            "supports_claim": None,
            "notes": "Fixture compare report; no runtime computation.",
        },
    }


def _write_canonical_json(path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False))
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_default_3mode_fixture(bundles_root: str | os.PathLike) -> str:
    """Write the default-trio fixture bundle and return its path."""
    bundle_id = "fixture_default_3mode_v1"
    bundles_root = os.fspath(bundles_root)
    bundle_dir = os.path.join(bundles_root, bundle_id)
    sessions_root = os.path.join(bundle_dir, "sessions")
    os.makedirs(sessions_root, exist_ok=True)

    tag_to_mode = {
        "baseline_static": "BASELINE_STATIC",
        "path_c_cold": "PATH_C_COLD",
        "path_c_warm": "PATH_C_WARM",
    }
    session_ids: dict[str, str] = {}
    for tag in DEFAULT_3_MODE_TAGS:
        sid = f"FIXTURE-DEFAULT-{tag.upper()}"
        artifact = _minimal_session_artifact(
            session_id=sid,
            mode=tag_to_mode[tag],
            events=2,
        )
        _write_canonical_json(
            os.path.join(sessions_root, tag, "session_artifact.json"),
            artifact,
        )
        # Deterministic empty memory file (exercises the
        # "file present but empty" null-safety branch).
        _write_text(
            os.path.join(sessions_root, tag, "memory.jsonl"),
            "",
        )
        session_ids[tag] = sid

    _write_canonical_json(
        os.path.join(bundle_dir, "compare_report.json"),
        _minimal_compare_report(list(DEFAULT_3_MODE_TAGS)),
    )
    _write_text(
        os.path.join(bundle_dir, "thesis_report.md"),
        "# Fixture thesis report (default 3-mode)\n\n"
        "Synthesized for B5 Phase-1 backend contract tests.\n",
    )

    metadata = build_metadata(
        bundle_id=bundle_id,
        variant_tags=list(DEFAULT_3_MODE_TAGS),
        session_ids=session_ids,
        has_compare_report=True,
        has_thesis_report=True,
        source_kind="fixture_builder",
        source_origin="build_default_3mode_fixture",
        source_notes=(
            "Deterministic synthetic fixture covering the default "
            "baseline_static / path_c_cold / path_c_warm trio."
        ),
        warnings=[],
    )
    _write_canonical_json(
        os.path.join(bundle_dir, "metadata.json"),
        metadata,
    )
    return bundle_dir


def build_b4_triplet_fixture(bundles_root: str | os.PathLike) -> str:
    """Write the B4 experiment triplet fixture and return its path.

    Deliberately omits ``path_c_cold`` — this fixture exists to
    force backend tests to exercise the ``no path_c_cold`` branch
    of the contract.
    """
    bundle_id = "fixture_b4_triplet_v1"
    bundles_root = os.fspath(bundles_root)
    bundle_dir = os.path.join(bundles_root, bundle_id)
    sessions_root = os.path.join(bundle_dir, "sessions")
    os.makedirs(sessions_root, exist_ok=True)

    tag_to_mode = {
        "baseline_static": "BASELINE_STATIC",
        "path_c_warm_policy_only": "PATH_C_WARM",
        "path_c_warm_agent_visible_memory": "PATH_C_WARM",
    }
    session_ids: dict[str, str] = {}
    for tag in B4_TRIPLET_TAGS:
        sid = f"FIXTURE-B4-{tag.upper()}"
        artifact = _minimal_session_artifact(
            session_id=sid,
            mode=tag_to_mode[tag],
            events=3,
        )
        _write_canonical_json(
            os.path.join(sessions_root, tag, "session_artifact.json"),
            artifact,
        )
        session_ids[tag] = sid

    # Only the first variant gets a memory.jsonl file, so this
    # fixture also covers the "some-but-not-all memory files"
    # null-safety branch.
    _write_text(
        os.path.join(sessions_root, "baseline_static", "memory.jsonl"),
        "",
    )

    _write_canonical_json(
        os.path.join(bundle_dir, "compare_report.json"),
        _minimal_compare_report(list(B4_TRIPLET_TAGS)),
    )
    # Deliberately no thesis_report.md — exercises the
    # "compare present, thesis absent" branch.

    warnings = [
        "path_c_cold variant intentionally absent (B4 experiment triplet).",
        "memory.jsonl present only for baseline_static "
        "(intentional null-safety coverage).",
        "thesis_report.md intentionally omitted.",
    ]
    metadata = build_metadata(
        bundle_id=bundle_id,
        variant_tags=list(B4_TRIPLET_TAGS),
        session_ids=session_ids,
        has_compare_report=True,
        has_thesis_report=False,
        source_kind="fixture_builder",
        source_origin="build_b4_triplet_fixture",
        source_notes=(
            "Deterministic synthetic fixture covering the B4 "
            "experiment triplet (no path_c_cold)."
        ),
        warnings=warnings,
    )
    _write_canonical_json(
        os.path.join(bundle_dir, "metadata.json"),
        metadata,
    )
    return bundle_dir


def build_all_fixtures(bundles_root: str | os.PathLike) -> list[str]:
    """Convenience: build every fixture bundle. Returns their paths."""
    return [
        build_default_3mode_fixture(bundles_root),
        build_b4_triplet_fixture(bundles_root),
    ]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build B5 fixture bundles.")
    parser.add_argument("--bundles-root", required=True)
    args = parser.parse_args()
    for path in build_all_fixtures(args.bundles_root):
        print(path)
