"""Curated deterministic showcase bundles for B5 presentations.

Where ``fixture_builder.py`` emits *structurally minimal* bundles
(good for contract / smoke tests, sparse for demos), this module
emits *presentation-grade* bundles with:

  - a non-trivial event stream (varied event_type / route /
    action values so the Session Runtime route mix, action mix,
    and three-layer event detail all light up);
  - at least one warm-mode event with an adaptive overlay
    (governance vs effective divergence pill + UPGRADE_ONE_LEVEL
    adjustment);
  - a populated compare report with canonical `kpi_matrix`,
    `deltas`, `diverged_events`, and `thesis_claim_support`;
  - populated conditional sibling blocks
    (`replan_trace_summary`, `correlation_summary`,
    `cumulative_memory_summary` for the default trio;
    `agent_memory_experiment_summary` for the B4 triplet);
  - a canonical `thesis_report.md` with the same shape
    `session_compare.render_thesis_markdown` produces.

These are **curated deterministic demo outputs**, not live
harness runs — the bundles carry no dependency on LLM keys,
RAG setup, or `data/cases/*.json`. Every numeric value is
hand-picked to tell a coherent demo story, but the field
shapes match `src/session/session_schema.py` and
`src/session/session_compare.py` exactly so the frontend
renders them as it would render real harness output.

Preserved boundaries:
  - B3 remains session/compare-level only (no per-event B3);
  - B4 remains compare-only experiment (no per-event B4 overlay
    on any event record); only the compare report's
    `agent_memory_experiment_summary` sibling block is
    populated on the B4 showcase;
  - the B4 triplet has no `path_c_cold`.
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


_SCHEMA_VERSIONS_STAMP: dict[str, str] = {
    "session_artifact": "1.0",
    "session_event_record": "1.2",
    "session_kpis": "1.1",
    "compare_report": "1.1",
}


# ---------------------------------------------------------------------------
# Pure JSON writers
# ---------------------------------------------------------------------------


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


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False))
            f.write("\n")
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------------------
# Demo event stream — shared blueprint
# ---------------------------------------------------------------------------

# Each entry is one stream position. Variants derive their
# per-event overlay from a `mode_overrides` dict so the three
# sessions compare naturally against the same baseline event.

_SHOWCASE_EVENTS: list[dict[str, Any]] = [
    {
        "event_id": "EV-000",
        "event_type": "CARRIER_DELAY_ESCALATION",
        "severity": "MEDIUM",
        "governance_risk": "MEDIUM",
        "recommended": "EXPEDITE",
        "cost": 220.0,
        "sla_preserved": True,
        "baseline_route": "AUTO_EXECUTE",
        "baseline_action": "EXPEDITE",
        "baseline_status": "executed",
    },
    {
        "event_id": "EV-001",
        "event_type": "WAREHOUSE_OVERFLOW",
        "severity": "LOW",
        "governance_risk": "LOW",
        "recommended": "TRANSFER",
        "cost": 140.0,
        "sla_preserved": True,
        "baseline_route": "AUTO_EXECUTE",
        "baseline_action": "TRANSFER",
        "baseline_status": "executed",
    },
    {
        "event_id": "EV-002",
        "event_type": "SUPPLIER_DISRUPTION",
        "severity": "HIGH",
        "governance_risk": "HIGH",
        "recommended": "COMPENSATE",
        "cost": 410.0,
        "sla_preserved": False,
        "baseline_route": "HUMAN_REQUIRED",
        "baseline_action": None,
        "baseline_status": "awaiting_human_review",
    },
    {
        "event_id": "EV-003",
        "event_type": "CARRIER_DELAY_ESCALATION",
        "severity": "MEDIUM",
        "governance_risk": "MEDIUM",
        "recommended": "EXPEDITE",
        "cost": 235.0,
        "sla_preserved": True,
        "baseline_route": "HUMAN_REQUIRED",
        "baseline_action": None,
        "baseline_status": "awaiting_human_review",
        # This is the "star" event — warm mode adapts, replan fires,
        # correlator matches.
        "warm_divergent": True,
    },
    {
        "event_id": "EV-004",
        "event_type": "ETA_PATH_REROUTE",
        "severity": "MEDIUM",
        "governance_risk": "MEDIUM",
        "recommended": "TRANSFER",
        "cost": 175.0,
        "sla_preserved": True,
        "baseline_route": "AUTO_EXECUTE",
        "baseline_action": "TRANSFER",
        "baseline_status": "executed",
        "correlation_match": True,
    },
    {
        "event_id": "EV-005",
        "event_type": "CARRIER_DELAY_ESCALATION",
        "severity": "LOW",
        "governance_risk": "LOW",
        "recommended": "NO_ACTION",
        "cost": 0.0,
        "sla_preserved": True,
        "baseline_route": "AUTO_EXECUTE",
        "baseline_action": "NO_ACTION",
        "baseline_status": "executed",
    },
    {
        "event_id": "EV-006",
        "event_type": "WAREHOUSE_OVERFLOW",
        "severity": "MEDIUM",
        "governance_risk": "MEDIUM",
        "recommended": "TRANSFER",
        "cost": 190.0,
        "sla_preserved": True,
        "baseline_route": "AUTO_EXECUTE",
        "baseline_action": "TRANSFER",
        "baseline_status": "executed",
    },
]


# ---------------------------------------------------------------------------
# Session artifact synthesis
# ---------------------------------------------------------------------------


def _build_event_record(
    *,
    stream_event: dict[str, Any],
    session_id: str,
    mode: str,
    apply_adaptive: bool,
    apply_replan: bool,
    apply_correlator: bool,
) -> dict[str, Any]:
    eid = stream_event["event_id"]
    governance_risk = stream_event["governance_risk"]
    recommended = stream_event["recommended"]

    # Baseline truth fields come from the stream event.
    base_route = stream_event["baseline_route"]
    base_action = stream_event["baseline_action"]
    base_status = stream_event["baseline_status"]

    # Path C overlay — starts as a mirror of the baseline.
    effective_route = base_route
    effective_action = base_action
    effective_status = base_status
    effective_risk = governance_risk
    policy_route_source = "baseline_static"
    adaptive_adjustment = None
    replan_trace = None
    replan_triggers = None
    correlation_context = None
    memory_record_id = None

    # Warm-mode adaptive overlay on the "star" event.
    is_warm = mode == "PATH_C_WARM"
    if is_warm and stream_event.get("warm_divergent"):
        policy_route_source = "adaptive_adjusted"
        effective_route = "AUTO_EXECUTE"
        effective_action = "EXPEDITE"
        effective_status = "executed"
        effective_risk = "LOW"
        adaptive_adjustment = {
            "rule_id": "R-AUTOEXPEDITE-LOW",
            "adjustment_type": "UPGRADE_ONE_LEVEL",
            "pre_adjustment_risk": governance_risk,
            "post_adjustment_risk": "LOW",
            "query_signature": (
                f"sig:{stream_event['event_type']}"
                f"|{governance_risk}|v1"
            ),
            "memory_evidence": {
                "matched_records": 8,
                "auto_execute_success_rate": 0.88,
            },
            "notes": "",
            "schema_version": "1.0",
        }
        memory_record_id = f"MEM-{session_id}-{eid}"
        if apply_replan:
            replan_trace = [
                {
                    "attempt_index": 0,
                    "attempt_final_route": "AUTO_EXECUTE",
                    "attempt_action_taken": "EXPEDITE",
                    "attempt_execution_status": "executed",
                    "execution_outcome": {
                        "cost_incurred": 235.0,
                        "sla_impact": {"preserved": True},
                    },
                    "adaptive_adjustment": None,
                    "expected_outcome": None,
                    "trigger": {
                        "trigger_rule_id": "R1_COST_DEVIATION",
                        "trigger_type": "COST_DEVIATION",
                        "attempt_index": 0,
                        "deviation_measurement": {
                            "abs_delta": 22.0,
                            "rel_delta": 0.1,
                        },
                        "expected_outcome_ref": None,
                        "realized_cost": 235.0,
                        "realized_sla_preserved": True,
                        "notes": "",
                        "schema_version": "1.0",
                    },
                    "notes": "",
                    "schema_version": "1.0",
                }
            ]
            replan_triggers = [replan_trace[0]["trigger"]]

    # Path C cold mode: no adaptive overlay fires (cold-start),
    # but policy_route_source is surfaced to distinguish from
    # pure baseline on the summary strip.
    is_cold = mode == "PATH_C_COLD"
    if is_cold:
        policy_route_source = "cold_start_fallback"

    # Correlator fires on EV-004 for warm + cold (observability).
    if (
        apply_correlator
        and stream_event.get("correlation_match")
        and (is_warm or is_cold)
    ):
        correlation_context = {
            "signals": [
                {
                    "pattern_id": "ETA_PATH_COMPOUND",
                    "triggering_event_id": eid,
                    "participant_event_ids": [
                        "EV-003",
                        eid,
                    ],
                    "shared_entities": [],
                    "window_start_ordinal": 3,
                    "window_end_ordinal": 4,
                    "window_size": 3,
                    "matched_conditions": ["SHARED_ETA_PATH"],
                    "schema_version": "1.0",
                }
            ],
            "window_size": 3,
            "window_events_considered": 3,
            "schema_version": "1.0",
        }

    return {
        "baseline_event_result": {
            "schema_version": "1.0",
            "event_id": eid,
            "event_type": stream_event["event_type"],
            "severity": stream_event["severity"],
            "scenario_context": {
                "demo": True,
                "route_hint": base_route,
            },
            "governance_output": {
                "risk_level": governance_risk,
                "recommended_action": recommended,
                "rationale_trace": "",
                "schema_version": "1.0",
            },
            "policy_decision": {
                "final_route": base_route,
                "action_taken": base_action,
                "schema_version": "1.0",
            },
            "execution_status": base_status,
            "execution_outcome": {
                "cost_incurred": stream_event["cost"],
                "sla_impact": {"preserved": stream_event["sla_preserved"]},
            },
            "trace_log": [],
        },
        "session_id": session_id,
        "mode": mode,
        "policy_route_source": policy_route_source,
        "adaptive_adjustment": adaptive_adjustment,
        "governance_truth": {
            "risk_level": governance_risk,
            "recommended_candidate_type": recommended,
            "schema_version": "1.0",
        },
        "effective_decision": {
            "effective_risk": effective_risk,
            "final_route": effective_route,
            "action_taken": effective_action,
            "execution_status": effective_status,
            "schema_version": "1.0",
        },
        "memory_record_id": memory_record_id,
        "replan_trace": replan_trace,
        "replan_triggers": replan_triggers,
        "correlation_context": correlation_context,
        "notes": "",
        "schema_version": "1.2",
    }


def _build_session_artifact(
    *,
    session_id: str,
    mode: str,
    stream: list[dict[str, Any]],
    apply_adaptive: bool,
    apply_replan: bool,
    apply_correlator: bool,
    apply_cumulative_memory: bool,
    seed: int = 42,
) -> dict[str, Any]:
    event_records = [
        _build_event_record(
            stream_event=ev,
            session_id=session_id,
            mode=mode,
            apply_adaptive=apply_adaptive,
            apply_replan=apply_replan,
            apply_correlator=apply_correlator,
        )
        for ev in stream
    ]

    # Derive shallow KPI summary from the effective decision field
    # so the Session Runtime summary strip reflects what the
    # frontend would see on a real run.
    total_events = len(event_records)
    with_outcome = sum(
        1
        for r in event_records
        if r["effective_decision"]["execution_status"] == "executed"
    )
    preserved = sum(
        1
        for r in event_records
        if r["baseline_event_result"]["execution_outcome"]["sla_impact"][
            "preserved"
        ]
    )
    auto_exec = sum(
        1
        for r in event_records
        if r["effective_decision"]["final_route"] == "AUTO_EXECUTE"
    )
    total_cost = sum(
        float(
            r["baseline_event_result"]["execution_outcome"]["cost_incurred"]
        )
        for r in event_records
    )
    avg_cost = total_cost / total_events if total_events else None
    sla_rate = preserved / total_events if total_events else None
    auto_rate = auto_exec / total_events if total_events else None

    replan_fires = sum(
        1 for r in event_records if r.get("replan_trace") is not None
    )

    # Cumulative memory snapshot — only on warm, only when enabled.
    memory_records: list[dict[str, Any]] = []
    if apply_cumulative_memory:
        # Three prior-session rows + two self-session rows.
        memory_records = [
            {
                "event_id": "PRIOR-EV-010",
                "event_type": "CARRIER_DELAY_ESCALATION",
                "event_timestamp": "2026-02-10T10:00:00+00:00",
                "action_taken": "EXPEDITE",
                "execution_status": "executed",
                "final_route": "AUTO_EXECUTE",
                "cost_incurred": 215.0,
                "sla_preserved": True,
                "risk_level": "MEDIUM",
                "session_id": "PRIOR-SESSION-A",
                "schema_version": "1.0",
            },
            {
                "event_id": "PRIOR-EV-011",
                "event_type": "CARRIER_DELAY_ESCALATION",
                "event_timestamp": "2026-02-11T10:00:00+00:00",
                "action_taken": "EXPEDITE",
                "execution_status": "executed",
                "final_route": "AUTO_EXECUTE",
                "cost_incurred": 230.0,
                "sla_preserved": True,
                "risk_level": "MEDIUM",
                "session_id": "PRIOR-SESSION-A",
                "schema_version": "1.0",
            },
            {
                "event_id": "PRIOR-EV-020",
                "event_type": "WAREHOUSE_OVERFLOW",
                "event_timestamp": "2026-02-12T10:00:00+00:00",
                "action_taken": "TRANSFER",
                "execution_status": "executed",
                "final_route": "AUTO_EXECUTE",
                "cost_incurred": 180.0,
                "sla_preserved": True,
                "risk_level": "LOW",
                "session_id": "PRIOR-SESSION-B",
                "schema_version": "1.0",
            },
            {
                "event_id": "EV-000",
                "event_type": "CARRIER_DELAY_ESCALATION",
                "event_timestamp": "2026-03-01T10:00:00+00:00",
                "action_taken": "EXPEDITE",
                "execution_status": "executed",
                "final_route": "AUTO_EXECUTE",
                "cost_incurred": 220.0,
                "sla_preserved": True,
                "risk_level": "MEDIUM",
                "session_id": session_id,
                "schema_version": "1.0",
            },
            {
                "event_id": "EV-003",
                "event_type": "CARRIER_DELAY_ESCALATION",
                "event_timestamp": "2026-03-01T11:00:00+00:00",
                "action_taken": "EXPEDITE",
                "execution_status": "executed",
                "final_route": "AUTO_EXECUTE",
                "cost_incurred": 235.0,
                "sla_preserved": True,
                "risk_level": "MEDIUM",
                "session_id": session_id,
                "schema_version": "1.0",
            },
        ]

    return {
        "session_id": session_id,
        "config": {
            "seed": seed,
            "mode": mode,
            "events_source": "demo_showcase",
            "initial_memory_digest": (
                "demo_showcase_cumulative_v1"
                if apply_cumulative_memory
                else ""
            ),
            "schema_version": "1.0",
        },
        "event_records": event_records,
        "memory_snapshot": {"records": memory_records},
        "kpis": {
            "events_observed": total_events,
            "events_with_outcome": with_outcome,
            "events_skipped": 0,
            "events_failed": 0,
            "events_processed": total_events,
            "auto_execute_success_rate": round(auto_rate, 4)
            if auto_rate is not None
            else None,
            "sla_preservation_rate": round(sla_rate, 4)
            if sla_rate is not None
            else None,
            "total_cost": round(total_cost, 4),
            "avg_cost": round(avg_cost, 4) if avg_cost is not None else None,
            "known_outcome_coverage": round(with_outcome / total_events, 4)
            if total_events
            else None,
            "replan_events_observed": replan_fires,
            "replan_fire_count": replan_fires,
            "replan_trigger_rate": round(replan_fires / total_events, 4)
            if total_events
            else None,
            "replan_success_count": replan_fires,
            "replan_recovery_rate": 1.0 if replan_fires > 0 else None,
            "schema_version": "1.1",
        },
        "schema_versions": dict(_SCHEMA_VERSIONS_STAMP),
        "notes": (
            "Curated deterministic demo_showcase session artifact. "
            "Shapes mirror src/session/session_schema.py; values are "
            "hand-picked to showcase the B5 surface."
        ),
        "schema_version": "1.0",
    }


# ---------------------------------------------------------------------------
# Compare report synthesis — default trio
# ---------------------------------------------------------------------------


_THESIS_CLAIM = (
    "Path C extends calibrated supervision into a temporally adaptive "
    "semi-autonomy loop."
)


def _build_default_trio_compare() -> dict[str, Any]:
    # sessions_compared sorted — matches session_compare's behavior.
    modes_sorted = sorted(DEFAULT_3_MODE_TAGS)
    kpi_matrix = {
        "overall": {
            "events_observed": {m: 7 for m in modes_sorted},
            "events_with_outcome": {
                "baseline_static": 6,
                "path_c_cold": 6,
                "path_c_warm": 7,
            },
            "events_skipped": {m: 0 for m in modes_sorted},
            "events_failed": {m: 0 for m in modes_sorted},
            "events_processed": {m: 7 for m in modes_sorted},
            "sla_preservation_rate": {
                "baseline_static": 0.8571,
                "path_c_cold": 0.8571,
                "path_c_warm": 1.0,
            },
            "avg_cost_per_event": {
                "baseline_static": 195.71,
                "path_c_cold": 195.71,
                "path_c_warm": 195.71,
            },
            "calibrated_autonomy_score": {
                "baseline_static": 0.7143,
                "path_c_cold": 0.7143,
                "path_c_warm": 0.8571,
            },
            "human_escalation_rate": {
                "baseline_static": 0.2857,
                "path_c_cold": 0.2857,
                "path_c_warm": 0.1429,
            },
            "auto_execute_rate": {
                "baseline_static": 0.7143,
                "path_c_cold": 0.7143,
                "path_c_warm": 0.8571,
            },
            "known_outcome_coverage": {
                "baseline_static": 0.8571,
                "path_c_cold": 0.8571,
                "path_c_warm": 1.0,
            },
        },
        "cold_phase": {
            "events_observed": {m: 3 for m in modes_sorted},
            "events_with_outcome": {m: 2 for m in modes_sorted},
            "events_skipped": {m: 0 for m in modes_sorted},
            "events_failed": {m: 0 for m in modes_sorted},
            "events_processed": {m: 3 for m in modes_sorted},
            "sla_preservation_rate": {m: 0.6667 for m in modes_sorted},
            "avg_cost_per_event": {m: 256.67 for m in modes_sorted},
            "calibrated_autonomy_score": {m: 0.6667 for m in modes_sorted},
            "human_escalation_rate": {m: 0.3333 for m in modes_sorted},
            "auto_execute_rate": {m: 0.6667 for m in modes_sorted},
            "known_outcome_coverage": {m: 0.6667 for m in modes_sorted},
        },
        "warm_phase": {
            "events_observed": {m: 4 for m in modes_sorted},
            "events_with_outcome": {
                "baseline_static": 4,
                "path_c_cold": 4,
                "path_c_warm": 4,
            },
            "events_skipped": {m: 0 for m in modes_sorted},
            "events_failed": {m: 0 for m in modes_sorted},
            "events_processed": {m: 4 for m in modes_sorted},
            "sla_preservation_rate": {
                "baseline_static": 1.0,
                "path_c_cold": 1.0,
                "path_c_warm": 1.0,
            },
            "avg_cost_per_event": {
                "baseline_static": 150.0,
                "path_c_cold": 150.0,
                "path_c_warm": 150.0,
            },
            "calibrated_autonomy_score": {
                "baseline_static": 0.75,
                "path_c_cold": 0.75,
                "path_c_warm": 1.0,
            },
            "human_escalation_rate": {
                "baseline_static": 0.25,
                "path_c_cold": 0.25,
                "path_c_warm": 0.0,
            },
            "auto_execute_rate": {
                "baseline_static": 0.75,
                "path_c_cold": 0.75,
                "path_c_warm": 1.0,
            },
            "known_outcome_coverage": {
                "baseline_static": 1.0,
                "path_c_cold": 1.0,
                "path_c_warm": 1.0,
            },
        },
    }

    deltas = {
        "path_c_cold_minus_baseline_static": {
            "sla_preservation_rate": 0.0,
            "avg_cost_per_event": 0.0,
            "calibrated_autonomy_score": 0.0,
            "human_escalation_rate": 0.0,
            "auto_execute_rate": 0.0,
            "known_outcome_coverage": 0.0,
        },
        "path_c_warm_minus_baseline_static": {
            "sla_preservation_rate": 0.1429,
            "avg_cost_per_event": 0.0,
            "calibrated_autonomy_score": 0.1428,
            "human_escalation_rate": -0.1428,
            "auto_execute_rate": 0.1428,
            "known_outcome_coverage": 0.1429,
        },
    }

    diverged_events = [
        {
            "event_index": 3,
            "event_id": "EV-003",
            "modes": modes_sorted,
            "routes": {
                "baseline_static": "HUMAN_REQUIRED",
                "path_c_cold": "HUMAN_REQUIRED",
                "path_c_warm": "AUTO_EXECUTE",
            },
            "actions": {
                "baseline_static": None,
                "path_c_cold": None,
                "path_c_warm": "EXPEDITE",
            },
            "statuses": {
                "baseline_static": "awaiting_human_review",
                "path_c_cold": "awaiting_human_review",
                "path_c_warm": "executed",
            },
            "adjustment_ref": {
                "rule_id": "R-AUTOEXPEDITE-LOW",
                "adjustment_type": "UPGRADE_ONE_LEVEL",
                "pre_adjustment_risk": "MEDIUM",
                "post_adjustment_risk": "LOW",
                "query_signature": (
                    "sig:CARRIER_DELAY_ESCALATION|MEDIUM|v1"
                ),
                "memory_evidence": {
                    "matched_records": 8,
                    "auto_execute_success_rate": 0.88,
                },
                "notes": "",
                "schema_version": "1.0",
            },
        },
    ]

    thesis_claim_support = {
        "claim": _THESIS_CLAIM,
        "warm_calibrated_autonomy_delta": 0.1428,
        "warm_sla_preservation_delta": 0.1429,
        "warm_cost_delta": 0.0,
        "supports_claim": True,
        "notes": (
            "Warm session matches or exceeds baseline on SLA and "
            "calibrated autonomy with non-increasing cost."
        ),
    }

    replan_trace_summary = {
        "sessions_with_replan": ["path_c_warm"],
        "total_replan_events": 1,
        "trigger_type_counts": {
            "path_c_warm": {
                "NO_TRIGGER": 0,
                "COST_DEVIATION": 1,
                "SLA_DEVIATION": 0,
                "EXECUTION_FAILED": 0,
                "PREFLIGHT_FAILED": 0,
            }
        },
        "recovered_events_count": {"path_c_warm": 1},
        "by_mode": {
            "path_c_warm": {
                "replan_kpis_overall": {
                    "replan_events_observed": 1,
                    "replan_fire_count": 1,
                    "replan_trigger_rate": 0.1429,
                    "replan_success_count": 1,
                    "replan_recovery_rate": 1.0,
                },
                "events_with_trace": 1,
                "recovered_events": 1,
            }
        },
    }

    correlation_summary = {
        "sessions_with_correlation_data": ["path_c_cold", "path_c_warm"],
        "per_session": {
            "path_c_cold": {
                "events_with_context": 1,
                "events_with_signals": 1,
                "total_signals": 1,
                "pattern_counts": {"ETA_PATH_COMPOUND": 1},
                "correlated_event_ids": ["EV-004"],
                "signals_by_event": [],
            },
            "path_c_warm": {
                "events_with_context": 1,
                "events_with_signals": 1,
                "total_signals": 1,
                "pattern_counts": {"ETA_PATH_COMPOUND": 1},
                "correlated_event_ids": ["EV-004"],
                "signals_by_event": [],
            },
        },
        "overall_pattern_counts": {"ETA_PATH_COMPOUND": 2},
        "all_correlated_event_ids": ["EV-004"],
    }

    cumulative_memory_summary = {
        "sessions_with_cumulative_memory": ["path_c_warm"],
        "per_session": {
            "path_c_warm": {
                "current_session_id": "DEMO-SHOWCASE-PATH_C_WARM",
                "has_cumulative_memory": True,
                "cumulative_row_count": 3,
                "self_session_row_count": 2,
                "prior_session_refs": [
                    "PRIOR-SESSION-A",
                    "PRIOR-SESSION-B",
                ],
                "rows_by_prior_session": {
                    "PRIOR-SESSION-A": 2,
                    "PRIOR-SESSION-B": 1,
                },
            }
        },
        "all_prior_session_refs": ["PRIOR-SESSION-A", "PRIOR-SESSION-B"],
        "overall_rows_by_prior_session": {
            "PRIOR-SESSION-A": 2,
            "PRIOR-SESSION-B": 1,
        },
    }

    return {
        "schema_version": "1.1",
        "sessions_compared": modes_sorted,
        "baseline_mode": "baseline_static",
        "min_records_for_shift": 3,
        "per_session_kpi_report": {m: kpi_matrix for m in modes_sorted},
        "kpi_matrix": kpi_matrix,
        "deltas": deltas,
        "diverged_events": diverged_events,
        "thesis_claim_support": thesis_claim_support,
        "replan_trace_summary": replan_trace_summary,
        "correlation_summary": correlation_summary,
        "cumulative_memory_summary": cumulative_memory_summary,
    }


def _build_default_trio_thesis_md(compare: dict[str, Any]) -> str:
    """Render a canonical-shape thesis markdown from the compare dict.

    Mirrors the structure of
    ``src/session/session_compare.render_thesis_markdown`` so the
    Compare Lab page displays a realistic markdown block.
    """
    modes = list(compare["sessions_compared"])
    matrix = compare["kpi_matrix"]
    deltas = compare["deltas"]
    diverged = compare["diverged_events"]
    thesis = compare["thesis_claim_support"]
    n = int(compare["min_records_for_shift"])

    def fmt(v: Any) -> str:
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, float):
            return f"{v:.4f}"
        return str(v)

    lines: list[str] = []
    lines.append(
        "# Path C Phase 3 — Thesis-Aligned Session Compare Report"
    )
    lines.append("")
    lines.append(
        f"Schema: `SessionCompareReport v{compare['schema_version']}`. "
        f"Baseline mode: `{compare['baseline_mode']}`. "
        f"min_records_for_shift = `{n}`."
    )
    lines.append("")
    for segment_title, seg in (
        ("Overall KPIs", "overall"),
        ("Cold-phase KPIs", "cold_phase"),
        ("Warm-phase KPIs", "warm_phase"),
    ):
        lines.append(f"## {segment_title}")
        lines.append("")
        header = "| KPI | " + " | ".join(modes) + " |"
        sep = "|---|" + "|".join(["---"] * len(modes)) + "|"
        lines.append(header)
        lines.append(sep)
        for kpi in matrix[seg].keys():
            row = [fmt(matrix[seg][kpi].get(m)) for m in modes]
            lines.append(f"| {kpi} | " + " | ".join(row) + " |")
        lines.append("")

    lines.append("## Deltas vs baseline (overall)")
    lines.append("")
    for key, block in deltas.items():
        lines.append(f"### {key}")
        lines.append("")
        lines.append("| KPI | delta |")
        lines.append("|---|---|")
        for kpi, val in block.items():
            lines.append(f"| {kpi} | {fmt(val)} |")
        lines.append("")

    lines.append("## Diverged events")
    lines.append("")
    lines.append(f"{len(diverged)} event(s) diverged.")
    lines.append("")

    lines.append("## Relation to calibrated supervision thesis")
    lines.append("")
    lines.append(f"**Claim:** {thesis['claim']}")
    lines.append("")
    lines.append(
        "- warm_calibrated_autonomy_delta: "
        f"`{fmt(thesis['warm_calibrated_autonomy_delta'])}`"
    )
    lines.append(
        "- warm_sla_preservation_delta: "
        f"`{fmt(thesis['warm_sla_preservation_delta'])}`"
    )
    lines.append(f"- warm_cost_delta: `{fmt(thesis['warm_cost_delta'])}`")
    lines.append(f"- supports_claim: **{fmt(thesis['supports_claim'])}**")
    if thesis.get("notes"):
        lines.append("")
        lines.append(f"Notes: {thesis['notes']}")
    lines.append("")
    lines.append(
        "This paragraph is generated deterministically from the "
        "structured compare report. The verdict reflects the observed "
        "deltas and is not post-tuned to match the claim."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Compare report synthesis — B4 triplet
# ---------------------------------------------------------------------------


def _build_b4_triplet_compare() -> dict[str, Any]:
    modes_sorted = sorted(B4_TRIPLET_TAGS)
    kpi_matrix = {
        "overall": {
            "sla_preservation_rate": {
                "baseline_static": 0.8571,
                "path_c_warm_policy_only": 0.8571,
                "path_c_warm_agent_visible_memory": 1.0,
            },
            "avg_cost_per_event": {
                "baseline_static": 195.71,
                "path_c_warm_policy_only": 195.71,
                "path_c_warm_agent_visible_memory": 195.71,
            },
            "calibrated_autonomy_score": {
                "baseline_static": 0.7143,
                "path_c_warm_policy_only": 0.8571,
                "path_c_warm_agent_visible_memory": 0.8571,
            },
            "auto_execute_rate": {
                "baseline_static": 0.7143,
                "path_c_warm_policy_only": 0.8571,
                "path_c_warm_agent_visible_memory": 0.8571,
            },
            "human_escalation_rate": {
                "baseline_static": 0.2857,
                "path_c_warm_policy_only": 0.1429,
                "path_c_warm_agent_visible_memory": 0.1429,
            },
            "known_outcome_coverage": {
                "baseline_static": 0.8571,
                "path_c_warm_policy_only": 0.8571,
                "path_c_warm_agent_visible_memory": 1.0,
            },
        },
        "cold_phase": {},
        "warm_phase": {},
    }
    deltas = {
        "path_c_warm_policy_only_minus_baseline_static": {
            "sla_preservation_rate": 0.0,
            "calibrated_autonomy_score": 0.1428,
            "auto_execute_rate": 0.1428,
            "human_escalation_rate": -0.1428,
        },
        "path_c_warm_agent_visible_memory_minus_baseline_static": {
            "sla_preservation_rate": 0.1429,
            "calibrated_autonomy_score": 0.1428,
            "auto_execute_rate": 0.1428,
            "human_escalation_rate": -0.1428,
        },
    }
    diverged_events = [
        {
            "event_index": 3,
            "event_id": "EV-003",
            "modes": modes_sorted,
            "routes": {
                "baseline_static": "HUMAN_REQUIRED",
                "path_c_warm_policy_only": "AUTO_EXECUTE",
                "path_c_warm_agent_visible_memory": "AUTO_EXECUTE",
            },
            "actions": {
                "baseline_static": None,
                "path_c_warm_policy_only": "EXPEDITE",
                "path_c_warm_agent_visible_memory": "EXPEDITE",
            },
            "statuses": {
                "baseline_static": "awaiting_human_review",
                "path_c_warm_policy_only": "executed",
                "path_c_warm_agent_visible_memory": "executed",
            },
            "adjustment_ref": None,
        },
        {
            "event_index": 6,
            "event_id": "EV-006",
            "modes": modes_sorted,
            "routes": {
                "baseline_static": "AUTO_EXECUTE",
                "path_c_warm_policy_only": "AUTO_EXECUTE",
                "path_c_warm_agent_visible_memory": "AUTO_EXECUTE",
            },
            "actions": {
                "baseline_static": "TRANSFER",
                "path_c_warm_policy_only": "TRANSFER",
                "path_c_warm_agent_visible_memory": "COMPENSATE",
            },
            "statuses": {
                "baseline_static": "executed",
                "path_c_warm_policy_only": "executed",
                "path_c_warm_agent_visible_memory": "executed",
            },
            "adjustment_ref": None,
        },
    ]

    # B4 compare fixtures typically include no path_c_warm
    # canonical mode, so thesis_claim_support is honestly null —
    # the frontend already handles this path (null supports_claim
    # + explanatory notes).
    thesis_claim_support = {
        "claim": _THESIS_CLAIM,
        "warm_calibrated_autonomy_delta": None,
        "warm_sla_preservation_delta": None,
        "warm_cost_delta": None,
        "supports_claim": None,
        "notes": (
            "thesis_claim_support requires a path_c_warm session in the "
            "compare; this B4 triplet substitutes it with two PATH_C_WARM "
            "variants (policy-only vs agent-visible). No claim "
            "determination."
        ),
    }

    agent_memory_experiment_summary = {
        "schema_version": "1.0",
        "variant_tags": list(B4_TRIPLET_TAGS),
        "session_ids_by_variant": {
            "baseline_static": "DEMO-SHOWCASE-B4-BASELINE_STATIC",
            "path_c_warm_policy_only": "DEMO-SHOWCASE-B4-PATH_C_WARM_POLICY_ONLY",
            "path_c_warm_agent_visible_memory": (
                "DEMO-SHOWCASE-B4-PATH_C_WARM_AGENT_VISIBLE_MEMORY"
            ),
        },
        "agent_visible_vs_policy_only_diverged_event_ids": ["EV-006"],
        "notes": (
            "B4 agent-visible memory experiment compare-only summary. "
            "Structural-only: variant tags + session_ids + diverged "
            "event ids between the policy-only and agent-visible "
            "PATH_C_WARM variants. No KPI deltas, no agent-output "
            "paraphrase."
        ),
    }

    return {
        "schema_version": "1.1",
        "sessions_compared": modes_sorted,
        "baseline_mode": "baseline_static",
        "min_records_for_shift": 3,
        "per_session_kpi_report": {},
        "kpi_matrix": kpi_matrix,
        "deltas": deltas,
        "diverged_events": diverged_events,
        "thesis_claim_support": thesis_claim_support,
        "agent_memory_experiment_summary": agent_memory_experiment_summary,
    }


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


_DEMO_SHOWCASE_NOTES = (
    "Curated deterministic demo_showcase bundle. Shapes mirror the "
    "canonical session / compare contracts; values are hand-picked "
    "to showcase the B5 surface end-to-end."
)


def build_default_trio_showcase(bundles_root: str | os.PathLike) -> str:
    """Write the default-trio showcase bundle. Returns bundle_dir path."""
    bundle_id = "demo_showcase_default_trio_v1"
    bundles_root = os.fspath(bundles_root)
    bundle_dir = os.path.join(bundles_root, bundle_id)
    sessions_root = os.path.join(bundle_dir, "sessions")
    os.makedirs(sessions_root, exist_ok=True)

    # Per-variant session config:
    tag_to_mode = {
        "baseline_static": ("BASELINE_STATIC", False, False, False, False),
        "path_c_cold": ("PATH_C_COLD", False, False, True, False),
        "path_c_warm": ("PATH_C_WARM", True, True, True, True),
    }

    session_ids: dict[str, str] = {}
    for tag in DEFAULT_3_MODE_TAGS:
        mode, apply_adap, apply_rep, apply_corr, apply_cum = tag_to_mode[tag]
        sid = f"DEMO-SHOWCASE-{tag.upper()}"
        artifact = _build_session_artifact(
            session_id=sid,
            mode=mode,
            stream=_SHOWCASE_EVENTS,
            apply_adaptive=apply_adap,
            apply_replan=apply_rep,
            apply_correlator=apply_corr,
            apply_cumulative_memory=apply_cum,
        )
        _write_canonical_json(
            os.path.join(sessions_root, tag, "session_artifact.json"),
            artifact,
        )
        # memory.jsonl — mirror of memory_snapshot.records.
        rows = artifact["memory_snapshot"].get("records") or []
        _write_jsonl(
            os.path.join(sessions_root, tag, "memory.jsonl"),
            list(rows),
        )
        session_ids[tag] = sid

    compare = _build_default_trio_compare()
    _write_canonical_json(
        os.path.join(bundle_dir, "compare_report.json"),
        compare,
    )
    _write_text(
        os.path.join(bundle_dir, "thesis_report.md"),
        _build_default_trio_thesis_md(compare),
    )

    metadata = build_metadata(
        bundle_id=bundle_id,
        variant_tags=list(DEFAULT_3_MODE_TAGS),
        session_ids=session_ids,
        has_compare_report=True,
        has_thesis_report=True,
        source_kind="showcase_builder",
        source_origin="build_default_trio_showcase",
        source_notes=_DEMO_SHOWCASE_NOTES,
        warnings=[],
    )
    _write_canonical_json(
        os.path.join(bundle_dir, "metadata.json"),
        metadata,
    )
    return bundle_dir


def build_b4_triplet_showcase(bundles_root: str | os.PathLike) -> str:
    """Write the B4 triplet showcase bundle. Returns bundle_dir path."""
    bundle_id = "demo_showcase_b4_triplet_v1"
    bundles_root = os.fspath(bundles_root)
    bundle_dir = os.path.join(bundles_root, bundle_id)
    sessions_root = os.path.join(bundle_dir, "sessions")
    os.makedirs(sessions_root, exist_ok=True)

    # For the B4 triplet:
    # - baseline_static mirrors the default-trio baseline;
    # - path_c_warm_policy_only runs WARM without B4 memory;
    # - path_c_warm_agent_visible_memory runs WARM and diverges
    #   from policy-only on EV-006 (action EXPEDITE -> COMPENSATE).
    # All three share the same per-event stream. B4 deliberately
    # DOES NOT surface at event level — the divergence is only
    # visible through the compare report's
    # `agent_memory_experiment_summary` sibling block and the
    # per-session effective_decision.action_taken field.

    # Build a variant of EV-006 for the agent-visible variant so the
    # effective_decision actually diverges in that session.
    b4_stream_agent_visible = []
    for ev in _SHOWCASE_EVENTS:
        if ev["event_id"] == "EV-006":
            ev_copy = dict(ev)
            ev_copy["baseline_action"] = "COMPENSATE"
            b4_stream_agent_visible.append(ev_copy)
        else:
            b4_stream_agent_visible.append(dict(ev))

    tag_to_spec: dict[str, tuple[str, bool, bool, bool, bool, list[dict[str, Any]]]] = {
        "baseline_static": (
            "BASELINE_STATIC",
            False,
            False,
            False,
            False,
            _SHOWCASE_EVENTS,
        ),
        "path_c_warm_policy_only": (
            "PATH_C_WARM",
            True,
            True,
            True,
            False,
            _SHOWCASE_EVENTS,
        ),
        "path_c_warm_agent_visible_memory": (
            "PATH_C_WARM",
            True,
            True,
            True,
            False,
            b4_stream_agent_visible,
        ),
    }

    session_ids: dict[str, str] = {}
    for tag in B4_TRIPLET_TAGS:
        mode, apply_adap, apply_rep, apply_corr, apply_cum, stream = (
            tag_to_spec[tag]
        )
        sid = f"DEMO-SHOWCASE-B4-{tag.upper()}"
        artifact = _build_session_artifact(
            session_id=sid,
            mode=mode,
            stream=stream,
            apply_adaptive=apply_adap,
            apply_replan=apply_rep,
            apply_correlator=apply_corr,
            apply_cumulative_memory=apply_cum,
        )
        _write_canonical_json(
            os.path.join(sessions_root, tag, "session_artifact.json"),
            artifact,
        )
        rows = artifact["memory_snapshot"].get("records") or []
        _write_jsonl(
            os.path.join(sessions_root, tag, "memory.jsonl"),
            list(rows),
        )
        session_ids[tag] = sid

    compare = _build_b4_triplet_compare()
    _write_canonical_json(
        os.path.join(bundle_dir, "compare_report.json"),
        compare,
    )
    # B4 triplet intentionally omits thesis_report.md.

    warnings = [
        "path_c_cold variant intentionally absent (B4 experiment triplet).",
        "thesis_report.md intentionally omitted.",
        (
            "B4 agent-visible memory overlay is rendered via the "
            "compare report's agent_memory_experiment_summary sibling "
            "block only — NOT as a per-event SessionEventRecord overlay."
        ),
    ]
    metadata = build_metadata(
        bundle_id=bundle_id,
        variant_tags=list(B4_TRIPLET_TAGS),
        session_ids=session_ids,
        has_compare_report=True,
        has_thesis_report=False,
        source_kind="showcase_builder",
        source_origin="build_b4_triplet_showcase",
        source_notes=_DEMO_SHOWCASE_NOTES,
        warnings=warnings,
    )
    _write_canonical_json(
        os.path.join(bundle_dir, "metadata.json"),
        metadata,
    )
    return bundle_dir


def build_all_showcases(bundles_root: str | os.PathLike) -> list[str]:
    return [
        build_default_trio_showcase(bundles_root),
        build_b4_triplet_showcase(bundles_root),
    ]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build the B5 demo_showcase bundles.",
    )
    parser.add_argument("--bundles-root", required=True)
    args = parser.parse_args()
    for path in build_all_showcases(args.bundles_root):
        print(path)
