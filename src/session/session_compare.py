"""session/session_compare.py — Path C Phase 3 multi-session compare.

Produces a deterministic ``SessionCompareReport`` v1.0 per Roadmap v2.1
§3.D. Inputs are already-built ``SessionArtifact`` objects and their
KPI reports (from ``session.kpi_calculator``). No runtime re-execution,
no decision logic. Read-only analysis.

Report shape::

    {
      "schema_version": "1.0",
      "sessions_compared": [<mode_name>, ...],
      "kpi_matrix": {
        "cold_phase": { <kpi_name>: {<mode>: value} },
        "warm_phase": { <kpi_name>: {<mode>: value} },
        "overall":    { <kpi_name>: {<mode>: value} }
      },
      "deltas": {
        "path_c_cold_minus_baseline": { <kpi_name>: delta_or_null },
        "path_c_warm_minus_baseline": { <kpi_name>: delta_or_null }
      },
      "diverged_events": [
        { "event_id": ..., "modes": {...}, "routes": {...},
          "actions": {...}, "statuses": {...},
          "adjustment_ref": <AdaptivePolicyAdjustment> | None }
      ],
      "thesis_claim_support": {
        "claim": ..., "warm_calibrated_autonomy_delta": ...,
        "warm_sla_preservation_delta": ..., "warm_cost_delta": ...,
        "supports_claim": ..., "notes": ...
      }
    }

All numeric values are rounded to 4 decimals at the serialization
boundary (via ``kpi_calculator.round_kpi_report`` and the delta
helpers in this module). Intermediate computation keeps full precision.

Zero-denominator rule: a delta where either side is ``None`` is
reported as ``None`` (no silent zero-coercion).

Comparing a session to itself produces:
  - All deltas 0.0 (or None where the base KPI was None).
  - ``diverged_events == []``.
Validated by ``test_session_compare.py``.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from session.kpi_calculator import (
    PHASE_KPI_KEYS,
    REPLAN_KPI_KEYS,
    _round_phase_kpis,
    _round_replan_kpis,
    compute_replan_kpis,
    compute_session_kpi_report,
    is_replan_success,
)
from session.session_schema import SessionArtifact, SessionEventRecord


# Compare report schema version.
#   1.0 — Phase 3 initial compare surface.
#   1.1 — B1 Slice 4 closeout: ``build_compare_report`` now
#         conditionally emits a ``replan_trace_summary`` sibling block
#         when at least one compared artifact has replan traces. The
#         bump is strictly additive — compares where no artifact has
#         replan data still produce the pre-B1 top-level key set.
#
# B2 Slice 2C adds a second conditional sibling block
# (``correlation_summary``) without bumping this version. The
# top-level version string stays at ``"1.1"`` to preserve byte
# identity for correlator-disabled compares; the additive block
# appears only when correlation data is present, and a reader can
# key off its presence directly. This matches the Slice 2C
# "no report-shape noise when correlation is absent" constraint.
#
# B4 Slice 2D3-A adds a third conditional sibling block
# (``agent_memory_experiment_summary``), again without bumping
# this version. The block is opt-in through the
# ``agent_memory_variant_tags`` kwarg on ``build_compare_report``
# — the harness explicitly passes its locked B4 triplet tag list
# when the experiment mode is on. ``session_compare`` itself does
# not introspect artifacts to decide whether B4 was active; that
# would require coupling to mode-name strings or to the
# (artifact-invisible) ``config_for_digest`` ``agent_memory``
# fragment. The opt-in shape keeps every existing call site
# byte-identical and preserves the no-NL-paraphrase /
# no-KPI-leak invariants from B4 boundary §8 R2 / §11 G12.
COMPARE_REPORT_SCHEMA_VERSION: str = "1.1"

_THESIS_CLAIM: str = (
    "Path C extends calibrated supervision into a temporally adaptive "
    "semi-autonomy loop."
)

_NUMERIC_KPI_KEYS: tuple[str, ...] = (
    "sla_preservation_rate",
    "avg_cost_per_event",
    "calibrated_autonomy_score",
    "human_escalation_rate",
    "auto_execute_rate",
    "known_outcome_coverage",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_compare_report(
    artifacts: dict[str, SessionArtifact],
    *,
    baseline_mode: str = "baseline_static",
    min_records_for_shift: int,
    agent_memory_variant_tags: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Build a canonical SessionCompareReport from named session artifacts.

    Parameters
    ----------
    artifacts:
        Mapping from *report mode name* (e.g. ``"baseline_static"``,
        ``"path_c_cold"``, ``"path_c_warm"``) to SessionArtifact. Keys
        are used as-is in the output (``sessions_compared`` is in
        sorted order for determinism).
    baseline_mode:
        The reference mode used to compute deltas. Must be a key in
        ``artifacts``.
    min_records_for_shift:
        Canonical owner is ``AdaptivePolicyGateConfig.min_records_for_shift``.
        Passed through for cold/warm segmentation consistency.
    agent_memory_variant_tags:
        B4 Slice 2D3-A opt-in. When supplied AND every named tag is
        present in ``artifacts``, the report gains an additive
        ``agent_memory_experiment_summary`` sibling block whose
        contents are structural (variant tag list, session_ids,
        diverged-event ids restricted to the
        ``path_c_warm_policy_only`` ↔
        ``path_c_warm_agent_visible_memory`` pair). When ``None``
        (default), or when the tag set is empty, or when at least
        one named tag is missing from ``artifacts``, the block is
        omitted and the rest of the report is byte-identical to
        the pre-2D3 surface. ``COMPARE_REPORT_SCHEMA_VERSION``
        does NOT bump (B1 / B2 / B3 conditional-sibling
        precedent).
    """
    if baseline_mode not in artifacts:
        raise ValueError(
            f"baseline_mode {baseline_mode!r} missing from artifacts keys "
            f"{sorted(artifacts.keys())}"
        )
    if len(artifacts) == 0:
        raise ValueError("artifacts must be non-empty")

    modes_sorted = sorted(artifacts.keys())
    kpi_reports = {
        m: compute_session_kpi_report(
            artifacts[m], min_records_for_shift=min_records_for_shift,
        )
        for m in modes_sorted
    }

    # ---- kpi_matrix ----
    kpi_matrix = _build_kpi_matrix(kpi_reports, modes_sorted)

    # ---- deltas ----
    deltas = _build_deltas(
        kpi_reports, modes_sorted=modes_sorted, baseline_mode=baseline_mode,
    )

    # ---- diverged_events ----
    diverged = _find_diverged_events(artifacts, modes_sorted=modes_sorted)

    # ---- thesis_claim_support ----
    thesis = _build_thesis_claim_support(
        kpi_reports=kpi_reports,
        baseline_mode=baseline_mode,
        warm_mode="path_c_warm" if "path_c_warm" in artifacts else None,
    )

    report = {
        "schema_version": COMPARE_REPORT_SCHEMA_VERSION,
        "sessions_compared": modes_sorted,
        "baseline_mode": baseline_mode,
        "min_records_for_shift": int(min_records_for_shift),
        "per_session_kpi_report": kpi_reports,
        "kpi_matrix": kpi_matrix,
        "deltas": deltas,
        "diverged_events": diverged,
        "thesis_claim_support": thesis,
    }

    # ---- B1 Slice 4: replan_trace_summary (conditional) ----
    # Only emit the sibling block if at least one compared artifact
    # actually has replan traces on at least one event. Sessions run
    # with enable_replan=False therefore produce the pre-B1 compare
    # surface byte-identically.
    replan_summary = _build_replan_trace_summary(artifacts, modes_sorted)
    if replan_summary is not None:
        report["replan_trace_summary"] = replan_summary

    # ---- B2 Slice 2C: correlation_summary (conditional) ----
    # Only emit when at least one compared artifact has a non-None
    # ``correlation_context`` on at least one event. Sessions run
    # with ``enable_correlator=False`` therefore produce no sibling
    # block. Derived purely from
    # ``SessionEventRecord.correlation_context`` — no KPI read, no
    # agent-output read, no natural-language parsing.
    correlation_summary = _build_correlation_summary(artifacts, modes_sorted)
    if correlation_summary is not None:
        report["correlation_summary"] = correlation_summary

    # ---- B3 Slice 2C: cumulative_memory_summary (conditional) ----
    # Only emit when at least one compared artifact carries a
    # memory_snapshot row whose ``session_id`` differs from the
    # artifact's own ``session_id`` — i.e. at least one
    # cross-session prior-memory row is present. Sessions run
    # without cumulative prior memory therefore produce no sibling
    # block and the compare shape stays byte-identical to pre-B3.
    # Derived purely from ``SessionArtifact.memory_snapshot`` and
    # ``SessionArtifact.session_id`` — no KPI read, no agent-output
    # read, no natural-language parsing.
    cumulative_summary = _build_cumulative_memory_summary(
        artifacts, modes_sorted,
    )
    if cumulative_summary is not None:
        report["cumulative_memory_summary"] = cumulative_summary

    # ---- B4 Slice 2D3-A: agent_memory_experiment_summary (conditional) ----
    # Opt-in via ``agent_memory_variant_tags``. The block is emitted
    # only when the caller supplies a non-empty tag list AND every
    # named tag is present in ``artifacts``. ``session_compare`` does
    # NOT introspect artifacts to decide whether B4 was active —
    # that decision lives at the caller (the harness, currently).
    # Structural-only: no KPI math, no NL paraphrase, no agent
    # output read. Diverged-event extraction is restricted to the
    # PATH_C_WARM pair so baseline-vs-warm divergence does not
    # contaminate the experiment delta.
    agent_memory_block = _build_agent_memory_experiment_summary(
        artifacts=artifacts,
        diverged_events=diverged,
        variant_tags=agent_memory_variant_tags,
    )
    if agent_memory_block is not None:
        report["agent_memory_experiment_summary"] = agent_memory_block

    return _round_report(report)


# ---------------------------------------------------------------------------
# kpi_matrix
# ---------------------------------------------------------------------------


def _build_kpi_matrix(
    kpi_reports: dict[str, dict[str, Any]],
    modes_sorted: list[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {
        "cold_phase": {}, "warm_phase": {}, "overall": {},
    }
    for seg in ("cold_phase", "warm_phase", "overall"):
        for kpi in PHASE_KPI_KEYS:
            out[seg][kpi] = {}
            for m in modes_sorted:
                out[seg][kpi][m] = kpi_reports[m][seg][kpi]
    return out


# ---------------------------------------------------------------------------
# deltas
# ---------------------------------------------------------------------------


def _delta(a: Any, b: Any) -> Optional[float]:
    """Return a - b if both are numeric; ``None`` if either is ``None``."""
    if a is None or b is None:
        return None
    return float(a) - float(b)


def _build_deltas(
    kpi_reports: dict[str, dict[str, Any]],
    *,
    modes_sorted: list[str],
    baseline_mode: str,
) -> dict[str, dict[str, Optional[float]]]:
    deltas: dict[str, dict[str, Optional[float]]] = {}
    for m in modes_sorted:
        if m == baseline_mode:
            continue
        key = f"{m}_minus_{baseline_mode}"
        deltas[key] = {}
        for kpi in _NUMERIC_KPI_KEYS:
            a = kpi_reports[m]["overall"][kpi]
            b = kpi_reports[baseline_mode]["overall"][kpi]
            deltas[key][kpi] = _delta(a, b)
    return deltas


# ---------------------------------------------------------------------------
# diverged_events
# ---------------------------------------------------------------------------


def _find_diverged_events(
    artifacts: dict[str, SessionArtifact],
    *,
    modes_sorted: list[str],
) -> list[dict[str, Any]]:
    """Events where effective decision diverges across sessions.

    Iterates by index (all sessions are run on matched inputs and
    produce the same number of event records per Roadmap contract).
    Divergence fires if ``(final_route, action_taken, execution_status)``
    differs across any two sessions for the same event index.
    """
    if len(modes_sorted) < 2:
        return []

    session_lens = {m: len(artifacts[m].event_records) for m in modes_sorted}
    max_len = max(session_lens.values())
    if len(set(session_lens.values())) > 1:
        # Shouldn't happen for matched inputs; we still emit divergence
        # over the minimum length and note the mismatch.
        max_len = min(session_lens.values())

    diverged: list[dict[str, Any]] = []
    for i in range(max_len):
        per_mode_key: dict[str, tuple[str, Optional[str], str]] = {}
        routes: dict[str, str] = {}
        actions: dict[str, Optional[str]] = {}
        statuses: dict[str, str] = {}
        event_id: Optional[str] = None
        adjustment_ref: Optional[dict[str, Any]] = None

        for m in modes_sorted:
            ser: SessionEventRecord = artifacts[m].event_records[i]
            ed = ser.effective_decision
            per_mode_key[m] = (ed.final_route, ed.action_taken, ed.execution_status)
            routes[m] = ed.final_route
            actions[m] = ed.action_taken
            statuses[m] = ed.execution_status
            if event_id is None:
                event_id = (ser.baseline_event_result or {}).get("event_id")
            if adjustment_ref is None and ser.adaptive_adjustment is not None:
                # Serialize adjustment to a plain canonical-JSON-ready dict.
                adjustment_ref = ser.adaptive_adjustment.model_dump()

        keys = set(per_mode_key.values())
        if len(keys) <= 1:
            continue

        diverged.append({
            "event_index": i,
            "event_id": event_id,
            "modes": modes_sorted,
            "routes": routes,
            "actions": actions,
            "statuses": statuses,
            "adjustment_ref": adjustment_ref,
        })

    return diverged


# ---------------------------------------------------------------------------
# thesis_claim_support
# ---------------------------------------------------------------------------


def _build_thesis_claim_support(
    *,
    kpi_reports: dict[str, dict[str, Any]],
    baseline_mode: str,
    warm_mode: Optional[str],
) -> dict[str, Any]:
    if warm_mode is None or warm_mode == baseline_mode:
        return {
            "claim": _THESIS_CLAIM,
            "warm_calibrated_autonomy_delta": None,
            "warm_sla_preservation_delta": None,
            "warm_cost_delta": None,
            "supports_claim": None,
            "notes": (
                "thesis_claim_support requires a path_c_warm session in the "
                "compare; none was provided. No claim determination."
            ),
        }

    warm_overall = kpi_reports[warm_mode]["overall"]
    base_overall = kpi_reports[baseline_mode]["overall"]

    cas_delta = _delta(
        warm_overall["calibrated_autonomy_score"],
        base_overall["calibrated_autonomy_score"],
    )
    sla_delta = _delta(
        warm_overall["sla_preservation_rate"],
        base_overall["sla_preservation_rate"],
    )
    cost_delta = _delta(
        warm_overall["avg_cost_per_event"],
        base_overall["avg_cost_per_event"],
    )

    # supports_claim rule (deterministic, honest):
    #   True  iff sla_delta is not None and >= 0 AND
    #             cas_delta is not None and >= 0 AND
    #             (cost_delta is None or cost_delta <= 0)
    #   False iff any of the above is a strictly adverse number
    #   None  iff any critical field is None (insufficient data)
    supports: Optional[bool]
    notes_parts: list[str] = []

    if sla_delta is None or cas_delta is None:
        supports = None
        if sla_delta is None:
            notes_parts.append(
                "warm_sla_preservation_delta is None (insufficient with_outcome events)"
            )
        if cas_delta is None:
            notes_parts.append(
                "warm_calibrated_autonomy_delta is None "
                "(insufficient AUTO_EXECUTE with_outcome events)"
            )
    else:
        cost_ok = cost_delta is None or cost_delta <= 0
        supports = bool(sla_delta >= 0 and cas_delta >= 0 and cost_ok)
        if not supports:
            if sla_delta < 0:
                notes_parts.append(
                    f"warm_sla_preservation_delta={sla_delta} < 0 "
                    f"(SLA preservation worsened)"
                )
            if cas_delta < 0:
                notes_parts.append(
                    f"warm_calibrated_autonomy_delta={cas_delta} < 0 "
                    f"(calibrated autonomy worsened)"
                )
            if cost_delta is not None and cost_delta > 0:
                notes_parts.append(
                    f"warm_cost_delta={cost_delta} > 0 (avg cost higher)"
                )
        else:
            notes_parts.append(
                "Warm session matches or exceeds baseline on SLA and "
                "calibrated autonomy with non-increasing cost."
            )

    return {
        "claim": _THESIS_CLAIM,
        "warm_calibrated_autonomy_delta": cas_delta,
        "warm_sla_preservation_delta": sla_delta,
        "warm_cost_delta": cost_delta,
        "supports_claim": supports,
        "notes": "; ".join(notes_parts),
    }


# ---------------------------------------------------------------------------
# B1 Slice 4 — replan_trace_summary (conditional sibling block)
# ---------------------------------------------------------------------------


_TRIGGER_TYPES: tuple[str, ...] = (
    "NO_TRIGGER",
    "COST_DEVIATION",
    "SLA_DEVIATION",
    "EXECUTION_FAILED",
    "PREFLIGHT_FAILED",
)


def _any_replan_trace_in_artifacts(
    artifacts: dict[str, SessionArtifact],
) -> bool:
    for art in artifacts.values():
        for rec in art.event_records:
            if rec.replan_trace is not None:
                return True
    return False


def _build_replan_trace_summary(
    artifacts: dict[str, SessionArtifact],
    modes_sorted: list[str],
) -> Optional[dict[str, Any]]:
    """Summarize replan behavior across compared sessions.

    Returns ``None`` (and the caller omits the block) when no
    compared artifact has any replan trace — so pre-B1 /
    replan-disabled compare reports stay byte-identical.

    When at least one artifact has replan traces, the returned block
    carries deterministic numeric and categorical counts only. Free-
    text notes are never read.
    """
    if not _any_replan_trace_in_artifacts(artifacts):
        return None

    sessions_with_replan: list[str] = []
    total_replan_events = 0
    trigger_type_counts: dict[str, dict[str, int]] = {}
    recovered_events_count: dict[str, int] = {}
    by_mode: dict[str, dict[str, Any]] = {}

    for mode in modes_sorted:
        art = artifacts[mode]
        replanned_records = [
            r for r in art.event_records if r.replan_trace is not None
        ]
        if not replanned_records:
            continue

        sessions_with_replan.append(mode)
        total_replan_events += len(replanned_records)

        # Count attempt-0 trigger types (the "fired" trigger per event).
        per_mode_counts: dict[str, int] = {t: 0 for t in _TRIGGER_TYPES}
        recovered = 0
        for rec in replanned_records:
            trigs = rec.replan_triggers or []
            if trigs:
                t = trigs[0].trigger_type
                if t in per_mode_counts:
                    per_mode_counts[t] += 1
            if is_replan_success(rec):
                recovered += 1

        trigger_type_counts[mode] = per_mode_counts
        recovered_events_count[mode] = recovered
        by_mode[mode] = {
            "replan_kpis_overall": compute_replan_kpis(
                list(art.event_records),
            ),
            "events_with_trace": len(replanned_records),
            "recovered_events": recovered,
        }

    return {
        "sessions_with_replan": sessions_with_replan,
        "total_replan_events": total_replan_events,
        "trigger_type_counts": trigger_type_counts,
        "recovered_events_count": recovered_events_count,
        "by_mode": by_mode,
    }


# ---------------------------------------------------------------------------
# B2 Slice 2C — correlation_summary (conditional sibling block)
# ---------------------------------------------------------------------------


def _any_correlation_context_in_artifacts(
    artifacts: dict[str, SessionArtifact],
) -> bool:
    for art in artifacts.values():
        for rec in art.event_records:
            if rec.correlation_context is not None:
                return True
    return False


def _event_id_for_record(rec: SessionEventRecord) -> str:
    """Prefer ``baseline_event_result.event_id`` (the canonical Path B
    identifier); fall back to the empty string so the block remains
    serializable on malformed inputs."""
    base = rec.baseline_event_result or {}
    eid = base.get("event_id")
    return eid if isinstance(eid, str) else ""


def _build_per_session_correlation_block(
    art: SessionArtifact,
) -> dict[str, Any]:
    """Summarize one session's correlator output.

    Returns a structural, compact block. Derived only from
    ``SessionEventRecord.correlation_context``; no KPI fields, no
    agent outputs, no natural-language parsing.
    """
    events_with_context = 0
    events_with_signals = 0
    total_signals = 0
    pattern_counts: dict[str, int] = {}
    correlated_event_ids: list[str] = []
    signals_by_event: list[dict[str, Any]] = []

    for event_index, rec in enumerate(art.event_records):
        ctx = rec.correlation_context
        if ctx is None:
            continue
        events_with_context += 1
        if not ctx.signals:
            continue
        events_with_signals += 1
        total_signals += len(ctx.signals)
        event_id = _event_id_for_record(rec)
        correlated_event_ids.append(event_id)

        per_event_signals: list[dict[str, Any]] = []
        for sig in ctx.signals:
            pattern_counts[sig.pattern_id] = (
                pattern_counts.get(sig.pattern_id, 0) + 1
            )
            per_event_signals.append(sig.model_dump())
        signals_by_event.append({
            "event_index": event_index,
            "event_id": event_id,
            "signals": per_event_signals,
        })

    return {
        "events_with_context": events_with_context,
        "events_with_signals": events_with_signals,
        "total_signals": total_signals,
        "pattern_counts": dict(sorted(pattern_counts.items())),
        "correlated_event_ids": correlated_event_ids,
        "signals_by_event": signals_by_event,
    }


def _build_correlation_summary(
    artifacts: dict[str, SessionArtifact],
    modes_sorted: list[str],
) -> Optional[dict[str, Any]]:
    """Summarize correlator output across compared sessions.

    Returns ``None`` (and the caller omits the block) when no
    compared artifact has any ``correlation_context`` — so pre-B2 /
    correlator-disabled compare reports stay shape-compatible.

    When at least one artifact has correlation data, the returned
    block carries:

      - ``sessions_with_correlation_data``: modes (sorted) for which
        any event carries a non-None ``correlation_context``.
      - ``per_session``: dict keyed by mode (sorted) → structural
        per-session block (``events_with_context``,
        ``events_with_signals``, ``total_signals``,
        ``pattern_counts``, ``correlated_event_ids``,
        ``signals_by_event``).
      - ``overall_pattern_counts``: dict pattern_id → int, summed
        across included sessions.
      - ``all_correlated_event_ids``: sorted union of event ids that
        had at least one emitted signal anywhere in the compare.
    """
    if not _any_correlation_context_in_artifacts(artifacts):
        return None

    sessions_with_correlation_data: list[str] = []
    per_session: dict[str, dict[str, Any]] = {}
    overall_pattern_counts: dict[str, int] = {}
    all_correlated_event_ids: set[str] = set()

    for mode in modes_sorted:
        art = artifacts[mode]
        has_ctx = any(
            r.correlation_context is not None for r in art.event_records
        )
        if not has_ctx:
            continue
        sessions_with_correlation_data.append(mode)
        block = _build_per_session_correlation_block(art)
        per_session[mode] = block
        for pid, count in block["pattern_counts"].items():
            overall_pattern_counts[pid] = (
                overall_pattern_counts.get(pid, 0) + int(count)
            )
        for eid in block["correlated_event_ids"]:
            if eid:
                all_correlated_event_ids.add(eid)

    return {
        "sessions_with_correlation_data": sessions_with_correlation_data,
        "per_session": per_session,
        "overall_pattern_counts": dict(sorted(overall_pattern_counts.items())),
        "all_correlated_event_ids": sorted(all_correlated_event_ids),
    }


# ---------------------------------------------------------------------------
# B3 Slice 2C — cumulative_memory_summary (conditional sibling block)
# ---------------------------------------------------------------------------


def _iter_memory_snapshot_records(
    art: SessionArtifact,
) -> list[dict[str, Any]]:
    """Return the artifact's memory snapshot row list, defensively.

    ``SessionArtifact.memory_snapshot`` is a ``dict[str, Any]``;
    during test construction it may be an empty dict. This helper
    returns an empty list in that case so the caller can iterate
    unconditionally.
    """
    snap = art.memory_snapshot or {}
    recs = snap.get("records") if isinstance(snap, dict) else None
    return list(recs) if isinstance(recs, list) else []


def _any_cumulative_memory_in_artifacts(
    artifacts: dict[str, SessionArtifact],
) -> bool:
    for art in artifacts.values():
        own_sid = art.session_id
        for rec in _iter_memory_snapshot_records(art):
            sid = rec.get("session_id")
            if isinstance(sid, str) and sid and sid != own_sid:
                return True
    return False


def _build_per_session_cumulative_block(
    art: SessionArtifact,
) -> dict[str, Any]:
    """Summarize one session's cumulative-memory provenance.

    Derived purely from ``memory_snapshot["records"]`` + the
    artifact's own ``session_id``. No KPI read, no agent read, no
    event-record inspection. Rows whose ``session_id`` equals the
    artifact's own session id are counted as self-session rows;
    every other row is a cumulative row.
    """
    own_sid = art.session_id
    rows = _iter_memory_snapshot_records(art)

    cumulative_row_count = 0
    self_session_row_count = 0
    rows_by_prior_session: dict[str, int] = {}

    for rec in rows:
        sid = rec.get("session_id")
        if not isinstance(sid, str) or not sid:
            # Malformed row — skip defensively rather than raising
            # in the read-only compare layer. Runtime loaders will
            # have already raised earlier if a row was invalid.
            continue
        if sid == own_sid:
            self_session_row_count += 1
        else:
            cumulative_row_count += 1
            rows_by_prior_session[sid] = (
                rows_by_prior_session.get(sid, 0) + 1
            )

    prior_session_refs = sorted(rows_by_prior_session.keys())

    return {
        "current_session_id": own_sid,
        "has_cumulative_memory": cumulative_row_count > 0,
        "cumulative_row_count": cumulative_row_count,
        "self_session_row_count": self_session_row_count,
        "prior_session_refs": prior_session_refs,
        "rows_by_prior_session": dict(sorted(rows_by_prior_session.items())),
    }


def _build_cumulative_memory_summary(
    artifacts: dict[str, SessionArtifact],
    modes_sorted: list[str],
) -> Optional[dict[str, Any]]:
    """Summarize cross-session prior-memory provenance across
    compared sessions.

    Returns ``None`` (and the caller omits the block) when no
    compared artifact has any prior-session row — so pre-B3 /
    cumulative-disabled compare reports stay shape-compatible
    byte-identically.

    When at least one artifact has cumulative memory, the returned
    block carries:

      - ``sessions_with_cumulative_memory``: compared sessions
        (in ``modes_sorted`` order) that actually contain prior-
        session rows.
      - ``per_session``: dict keyed by mode (in the same order) →
        structural per-session block.
      - ``all_prior_session_refs``: sorted union of every prior
        ``session_id`` observed anywhere in the compared set.
      - ``overall_rows_by_prior_session``: dict (sorted) of prior
        session id → total row count summed across included modes.
    """
    if not _any_cumulative_memory_in_artifacts(artifacts):
        return None

    sessions_with_cumulative_memory: list[str] = []
    per_session: dict[str, dict[str, Any]] = {}
    overall_rows_by_prior_session: dict[str, int] = {}
    all_prior_session_refs: set[str] = set()

    for mode in modes_sorted:
        art = artifacts[mode]
        block = _build_per_session_cumulative_block(art)
        if not block["has_cumulative_memory"]:
            continue
        sessions_with_cumulative_memory.append(mode)
        per_session[mode] = block
        for prior_sid, count in block["rows_by_prior_session"].items():
            overall_rows_by_prior_session[prior_sid] = (
                overall_rows_by_prior_session.get(prior_sid, 0) + int(count)
            )
        for prior_sid in block["prior_session_refs"]:
            all_prior_session_refs.add(prior_sid)

    return {
        "sessions_with_cumulative_memory": sessions_with_cumulative_memory,
        "per_session": per_session,
        "all_prior_session_refs": sorted(all_prior_session_refs),
        "overall_rows_by_prior_session": dict(
            sorted(overall_rows_by_prior_session.items())
        ),
    }


# ---------------------------------------------------------------------------
# B4 Slice 2D3-A — agent_memory_experiment_summary (conditional sibling)
# ---------------------------------------------------------------------------


#: Locked B4 warm-pair tag names. The harness's
#: ``_B4_EXPERIMENT_VARIANT_TAGS`` triplet uses these two as the second
#: and third entries; this module names them locally rather than
#: importing from the script layer to keep ``session_compare``
#: structurally independent of the harness.
_B4_POLICY_ONLY_TAG: str = "path_c_warm_policy_only"
_B4_AGENT_VISIBLE_TAG: str = "path_c_warm_agent_visible_memory"

_B4_EXPERIMENT_SUMMARY_NOTES: str = (
    "B4 agent-visible memory experiment compare-only summary. "
    "Structural-only: variant tags + session_ids + diverged event ids "
    "between the policy-only and agent-visible PATH_C_WARM variants. "
    "No KPI deltas, no agent-output paraphrase. See "
    "docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §11 G12 / §15 RO1."
)


def _build_agent_memory_experiment_summary(
    *,
    artifacts: dict[str, SessionArtifact],
    diverged_events: list[dict[str, Any]],
    variant_tags: Optional[Sequence[str]],
) -> Optional[dict[str, Any]]:
    """Build the B4 conditional sibling block.

    Returns ``None`` (so the caller omits the block) when:

    - ``variant_tags`` is ``None`` or empty, or
    - any named tag is missing from ``artifacts``.

    When the block is emitted, it carries:

    - ``schema_version`` — locked at ``"1.0"``.
    - ``variant_tags`` — the caller-supplied order, list-ified for
      JSON-stable serialization.
    - ``session_ids_by_variant`` — ``{tag: SessionArtifact.session_id}``
      for each named tag, preserving the caller-supplied order.
    - ``agent_visible_vs_policy_only_diverged_event_ids`` — sorted
      list of event ids from ``diverged_events`` where divergence is
      observed between the policy-only and agent-visible warm
      variants. Baseline-vs-warm divergence does not contribute.
      Restricted to event ids that are present (non-empty strings).
    - ``notes`` — fixed informational string.
    """
    if not variant_tags:
        return None
    tags = list(variant_tags)
    missing = [t for t in tags if t not in artifacts]
    if missing:
        return None

    session_ids_by_variant = {tag: artifacts[tag].session_id for tag in tags}

    # Diverged-event extraction is restricted to the WARM pair. Both
    # tags must be in the supplied ``variant_tags`` AND in
    # ``artifacts`` for the extraction to fire — otherwise the list
    # is empty (still a valid block when only the baseline + one
    # warm variant are supplied).
    diverged_pair_event_ids: list[str] = []
    if (
        _B4_POLICY_ONLY_TAG in tags
        and _B4_AGENT_VISIBLE_TAG in tags
    ):
        for d in diverged_events:
            routes = d.get("routes") or {}
            actions = d.get("actions") or {}
            statuses = d.get("statuses") or {}
            policy_key = (
                routes.get(_B4_POLICY_ONLY_TAG),
                actions.get(_B4_POLICY_ONLY_TAG),
                statuses.get(_B4_POLICY_ONLY_TAG),
            )
            agent_key = (
                routes.get(_B4_AGENT_VISIBLE_TAG),
                actions.get(_B4_AGENT_VISIBLE_TAG),
                statuses.get(_B4_AGENT_VISIBLE_TAG),
            )
            if policy_key == agent_key:
                continue
            eid = d.get("event_id")
            if isinstance(eid, str) and eid:
                diverged_pair_event_ids.append(eid)

    diverged_pair_event_ids = sorted(set(diverged_pair_event_ids))

    return {
        "schema_version": "1.0",
        "variant_tags": tags,
        "session_ids_by_variant": session_ids_by_variant,
        "agent_visible_vs_policy_only_diverged_event_ids": diverged_pair_event_ids,
        "notes": _B4_EXPERIMENT_SUMMARY_NOTES,
    }


# ---------------------------------------------------------------------------
# Serialization rounding
# ---------------------------------------------------------------------------


def _round_delta_block(block: dict[str, Optional[float]]) -> dict[str, Optional[float]]:
    return {
        k: (round(v, 4) if isinstance(v, float) else v)
        for k, v in block.items()
    }


def _round_kpi_matrix_entry(entry: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode_name, val in entry.items():
        out[mode_name] = round(val, 4) if isinstance(val, float) else val
    return out


# ---------------------------------------------------------------------------
# Thesis markdown renderer (pure function over the structured compare report)
# ---------------------------------------------------------------------------


def _fmt(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def render_thesis_markdown(compare_report: dict[str, Any]) -> str:
    """Render a deterministic thesis-aligned markdown from a compare report.

    The output is a pure function of the structured compare report —
    same report in produces the same markdown out, byte-for-byte.
    """
    modes = list(compare_report["sessions_compared"])
    matrix = compare_report["kpi_matrix"]
    deltas = compare_report["deltas"]
    diverged = compare_report["diverged_events"]
    thesis = compare_report["thesis_claim_support"]
    n = int(compare_report["min_records_for_shift"])

    lines: list[str] = []
    lines.append("# Path C Phase 3 — Thesis-Aligned Session Compare Report")
    lines.append("")
    lines.append(
        f"Schema: `SessionCompareReport v{compare_report['schema_version']}`. "
        f"Baseline mode: `{compare_report['baseline_mode']}`. "
        f"min_records_for_shift = `{n}`."
    )
    lines.append("")

    # ---- KPI tables per segment ----
    for segment_title, segment_key in (
        ("Overall KPIs", "overall"),
        ("Cold-phase KPIs (events 1..min_records_for_shift)", "cold_phase"),
        ("Warm-phase KPIs (events min_records_for_shift+1..end)", "warm_phase"),
    ):
        lines.append(f"## {segment_title}")
        lines.append("")
        header = "| KPI | " + " | ".join(modes) + " |"
        sep = "|---|" + "|".join(["---"] * len(modes)) + "|"
        lines.append(header)
        lines.append(sep)
        for kpi in PHASE_KPI_KEYS:
            row_vals = [_fmt(matrix[segment_key][kpi][m]) for m in modes]
            lines.append(f"| {kpi} | " + " | ".join(row_vals) + " |")
        lines.append("")

    # ---- Deltas ----
    lines.append("## Deltas vs baseline (overall)")
    lines.append("")
    if not deltas:
        lines.append("_No non-baseline sessions present in the comparison._")
    else:
        for key, block in deltas.items():
            lines.append(f"### {key}")
            lines.append("")
            lines.append("| KPI | delta |")
            lines.append("|---|---|")
            for kpi in (
                "sla_preservation_rate", "avg_cost_per_event",
                "calibrated_autonomy_score", "human_escalation_rate",
                "auto_execute_rate", "known_outcome_coverage",
            ):
                lines.append(f"| {kpi} | {_fmt(block.get(kpi))} |")
            lines.append("")

    # ---- Diverged events ----
    lines.append("## Diverged events")
    lines.append("")
    if not diverged:
        lines.append("_No events diverged across compared sessions._")
    else:
        lines.append(
            f"{len(diverged)} event(s) diverged. Each row links to the "
            f"adaptive_adjustment record (if any) that explains the "
            f"divergence."
        )
        lines.append("")
        # header
        header = "| idx | event_id | " + " | ".join(
            f"route[{m}]" for m in modes
        ) + " | rule_id | adjustment_type | pre→post |"
        sep = "|---|---|" + "|".join(["---"] * len(modes)) + "|---|---|---|"
        lines.append(header)
        lines.append(sep)
        for d in diverged:
            adj = d.get("adjustment_ref") or {}
            rule_id = adj.get("rule_id", "")
            adj_type = adj.get("adjustment_type", "")
            pre = adj.get("pre_adjustment_risk", "")
            post = adj.get("post_adjustment_risk", "")
            pre_post = f"{pre}→{post}" if (pre or post) else ""
            routes = [str(d["routes"].get(m, "")) for m in modes]
            lines.append(
                f"| {d['event_index']} | {d.get('event_id','') or ''} | "
                + " | ".join(routes)
                + f" | {rule_id} | {adj_type} | {pre_post} |"
            )
        lines.append("")

    # ---- Replan summary (B1 Slice 4, additive; rendered only when
    #      replan_trace_summary is present on the compare report) ----
    if "replan_trace_summary" in compare_report:
        rts = compare_report["replan_trace_summary"]
        lines.append("## Bounded-replan behavior (B1)")
        lines.append("")
        lines.append(
            "Replan trace was observed in "
            f"{len(rts['sessions_with_replan'])} session(s): "
            f"{', '.join(rts['sessions_with_replan'])}. "
            f"Total replanned events: {rts['total_replan_events']}."
        )
        lines.append("")
        lines.append(
            "| mode | events_with_trace | recovered | "
            "replan_trigger_rate | replan_recovery_rate |"
        )
        lines.append("|---|---|---|---|---|")
        for mode in rts["sessions_with_replan"]:
            by = rts["by_mode"][mode]
            rk = by.get("replan_kpis_overall", {})
            lines.append(
                f"| {mode} | {by['events_with_trace']} | "
                f"{by['recovered_events']} | "
                f"{_fmt(rk.get('replan_trigger_rate'))} | "
                f"{_fmt(rk.get('replan_recovery_rate'))} |"
            )
        lines.append("")
        lines.append("### Trigger-type counts (attempt 0 fired trigger)")
        lines.append("")
        header = "| mode | " + " | ".join(_TRIGGER_TYPES) + " |"
        sep = "|---|" + "|".join(["---"] * len(_TRIGGER_TYPES)) + "|"
        lines.append(header)
        lines.append(sep)
        for mode in rts["sessions_with_replan"]:
            counts = rts["trigger_type_counts"].get(mode, {})
            row = [str(counts.get(t, 0)) for t in _TRIGGER_TYPES]
            lines.append(f"| {mode} | " + " | ".join(row) + " |")
        lines.append("")

    # ---- Correlation observations (B2 Slice 2C, additive; rendered
    #      only when correlation_summary is present on the compare
    #      report) ----
    if "correlation_summary" in compare_report:
        cs = compare_report["correlation_summary"]
        lines.append("## Correlation observations (B2)")
        lines.append("")
        sessions = cs["sessions_with_correlation_data"]
        lines.append(
            "Correlation data was observed in "
            f"{len(sessions)} session(s): {', '.join(sessions)}."
        )
        lines.append("")
        lines.append(
            "| mode | events_with_context | events_with_signals | "
            "total_signals |"
        )
        lines.append("|---|---|---|---|")
        for mode in sessions:
            block = cs["per_session"][mode]
            lines.append(
                f"| {mode} | {block['events_with_context']} | "
                f"{block['events_with_signals']} | "
                f"{block['total_signals']} |"
            )
        lines.append("")
        lines.append("### Pattern counts (overall, across compared sessions)")
        lines.append("")
        overall = cs["overall_pattern_counts"]
        if not overall:
            lines.append("_No pattern fired across any compared session._")
        else:
            lines.append("| pattern_id | count |")
            lines.append("|---|---|")
            for pid, count in overall.items():
                lines.append(f"| {pid} | {count} |")
        lines.append("")
        lines.append("### Per-session pattern counts")
        lines.append("")
        # Union of pattern ids in declaration / sorted order across sessions.
        all_pids = sorted({
            pid
            for mode in sessions
            for pid in cs["per_session"][mode]["pattern_counts"].keys()
        })
        if not all_pids:
            lines.append(
                "_No pattern fired in any compared session's correlator "
                "output._"
            )
        else:
            header = "| mode | " + " | ".join(all_pids) + " |"
            sep = "|---|" + "|".join(["---"] * len(all_pids)) + "|"
            lines.append(header)
            lines.append(sep)
            for mode in sessions:
                counts = cs["per_session"][mode]["pattern_counts"]
                row = [str(counts.get(pid, 0)) for pid in all_pids]
                lines.append(f"| {mode} | " + " | ".join(row) + " |")
        lines.append("")
        if cs["all_correlated_event_ids"]:
            lines.append("### Correlated event ids (union across sessions)")
            lines.append("")
            lines.append(
                ", ".join(f"`{eid}`" for eid in cs["all_correlated_event_ids"])
            )
            lines.append("")
        lines.append(
            "_This section is observability-only. The correlator does not "
            "feed policy routing, adaptive adjustments, or replan decisions "
            "in Slice 2C. Counts above are structural — derived from event "
            "types, shared entity ids, and stream ordinals. No natural-"
            "language reasoning is used._"
        )
        lines.append("")

    # ---- Cumulative memory provenance (B3 Slice 2C, additive;
    #      rendered only when cumulative_memory_summary is present
    #      on the compare report) ----
    if "cumulative_memory_summary" in compare_report:
        cms = compare_report["cumulative_memory_summary"]
        lines.append("## Cumulative memory provenance (B3)")
        lines.append("")
        sessions = cms["sessions_with_cumulative_memory"]
        lines.append(
            "Cumulative (cross-session) prior memory was observed in "
            f"{len(sessions)} session(s): {', '.join(sessions)}."
        )
        lines.append("")
        lines.append(
            "| mode | self_rows | cumulative_rows | prior_session_refs |"
        )
        lines.append("|---|---|---|---|")
        for mode in sessions:
            block = cms["per_session"][mode]
            refs = (
                ", ".join(f"`{r}`" for r in block["prior_session_refs"])
                if block["prior_session_refs"]
                else "_none_"
            )
            lines.append(
                f"| {mode} | {block['self_session_row_count']} | "
                f"{block['cumulative_row_count']} | {refs} |"
            )
        lines.append("")
        lines.append("### Rows by prior session (overall)")
        lines.append("")
        overall = cms["overall_rows_by_prior_session"]
        if not overall:
            lines.append("_No prior-session rows were observed._")
        else:
            lines.append("| prior_session_id | row_count |")
            lines.append("|---|---|")
            for prior_sid, count in overall.items():
                lines.append(f"| `{prior_sid}` | {count} |")
        lines.append("")
        lines.append(
            "_This section is observability-only. Cumulative memory "
            "flows into the adaptive policy gate via the existing "
            "memory substrate and influences nothing else. Counts "
            "above are structural — derived from "
            "`memory_snapshot[\"records\"]` + each row's `session_id`."
            " No agent prompt sees cumulative memory (that is B4, "
            "not B3)._"
        )
        lines.append("")

    # ---- Agent-visible memory experiment (B4 Slice 2D3-A, additive;
    #      rendered only when agent_memory_experiment_summary is
    #      present on the compare report) ----
    if "agent_memory_experiment_summary" in compare_report:
        ams = compare_report["agent_memory_experiment_summary"]
        lines.append("## Agent-visible memory experiment (B4)")
        lines.append("")
        lines.append(
            "Variants compared: "
            + ", ".join(f"`{tag}`" for tag in ams["variant_tags"])
            + "."
        )
        lines.append("")
        lines.append("| variant | session_id |")
        lines.append("|---|---|")
        for tag in ams["variant_tags"]:
            sid = ams["session_ids_by_variant"].get(tag, "")
            lines.append(f"| `{tag}` | `{sid}` |")
        lines.append("")
        diverged_ids = ams["agent_visible_vs_policy_only_diverged_event_ids"]
        if diverged_ids:
            lines.append(
                "Event ids where the agent-visible variant diverged from "
                "the policy-only variant: "
                + ", ".join(f"`{eid}`" for eid in diverged_ids)
                + "."
            )
        else:
            lines.append(
                "No event diverged between the policy-only and "
                "agent-visible PATH_C_WARM variants."
            )
        lines.append("")
        lines.append(f"_{ams['notes']}_")
        lines.append("")

    # ---- Thesis paragraph ----
    lines.append("## Relation to calibrated supervision thesis")
    lines.append("")
    lines.append(f"**Claim:** {thesis['claim']}")
    lines.append("")
    lines.append(
        "- warm_calibrated_autonomy_delta: "
        f"`{_fmt(thesis['warm_calibrated_autonomy_delta'])}`"
    )
    lines.append(
        "- warm_sla_preservation_delta: "
        f"`{_fmt(thesis['warm_sla_preservation_delta'])}`"
    )
    lines.append(
        f"- warm_cost_delta: `{_fmt(thesis['warm_cost_delta'])}`"
    )
    lines.append(
        f"- supports_claim: **{_fmt(thesis['supports_claim'])}**"
    )
    if thesis.get("notes"):
        lines.append("")
        lines.append(f"Notes: {thesis['notes']}")
    lines.append("")
    lines.append(
        "This paragraph is generated deterministically from the structured "
        "compare report. Numbers above come from the KPI matrix; the "
        "supports_claim verdict reflects the observed deltas and is not "
        "post-tuned to match the claim."
    )
    lines.append("")
    return "\n".join(lines)


def _round_report(report: dict[str, Any]) -> dict[str, Any]:
    out = dict(report)

    # Per-session reports round at serialization.
    rounded_reports: dict[str, dict[str, Any]] = {}
    for mode, kr in report["per_session_kpi_report"].items():
        rr = dict(kr)
        for seg in ("cold_phase", "warm_phase", "overall"):
            rr[seg] = _round_phase_kpis(kr[seg])
        if "replan" in kr:
            rr["replan"] = {
                seg: _round_replan_kpis(kr["replan"][seg])
                for seg in ("cold_phase", "warm_phase", "overall")
            }
        rounded_reports[mode] = rr
    out["per_session_kpi_report"] = rounded_reports

    # kpi_matrix: round every numeric leaf value.
    rounded_matrix: dict[str, dict[str, dict[str, Any]]] = {}
    for seg, by_kpi in report["kpi_matrix"].items():
        rounded_matrix[seg] = {}
        for kpi, per_mode in by_kpi.items():
            rounded_matrix[seg][kpi] = _round_kpi_matrix_entry(per_mode)
    out["kpi_matrix"] = rounded_matrix

    # deltas
    rounded_deltas = {
        k: _round_delta_block(v) for k, v in report["deltas"].items()
    }
    out["deltas"] = rounded_deltas

    # thesis
    t = dict(report["thesis_claim_support"])
    for k in ("warm_calibrated_autonomy_delta",
              "warm_sla_preservation_delta",
              "warm_cost_delta"):
        v = t.get(k)
        if isinstance(v, float):
            t[k] = round(v, 4)
    out["thesis_claim_support"] = t

    # replan_trace_summary (present only if replan traces exist).
    if "replan_trace_summary" in report:
        rts = dict(report["replan_trace_summary"])
        rounded_by_mode: dict[str, dict[str, Any]] = {}
        for mode, block in rts["by_mode"].items():
            bb = dict(block)
            if "replan_kpis_overall" in bb:
                bb["replan_kpis_overall"] = _round_replan_kpis(
                    bb["replan_kpis_overall"],
                )
            rounded_by_mode[mode] = bb
        rts["by_mode"] = rounded_by_mode
        out["replan_trace_summary"] = rts

    return out
