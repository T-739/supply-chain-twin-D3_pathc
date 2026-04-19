"""session/kpi_calculator.py — Path C Phase 3 deterministic KPI calculator.

KPI definitions and source-of-truth table are taken verbatim from Roadmap
v2.1 §3.D (owner point v2.1-C). Every field used has exactly one
canonical source path in a ``SessionEventRecord``:

  execution_status  -> SessionEventRecord.effective_decision.execution_status
  final_route       -> SessionEventRecord.effective_decision.final_route
  action_taken      -> SessionEventRecord.effective_decision.action_taken
  cost_incurred     -> baseline_event_result["execution_outcome"]["cost_incurred"]
  sla_preserved     -> baseline_event_result["execution_outcome"]["sla_impact"]["preserved"]
  mode / policy_route_source / adaptive_adjustment -> SessionEventRecord overlay

No field is ever read from a non-canonical path. Overlay is canonical
for anything the adaptive layer might touch (``execution_status``,
``final_route``, ``action_taken``). Baseline fields are referenced only
for the two numeric outcome fields (``cost_incurred``,
``sla_impact.preserved``) that are definitionally Path B's ownership.

Zero-denominator policy: a KPI with a zero denominator returns ``None``.
Count-over-observed rates (``auto_execute_rate``,
``human_escalation_rate``) have ``events_observed`` as denominator and
are ``None`` only when the session is empty. ``known_outcome_coverage``
follows the same rule.

Rounding policy: arithmetic is in full Python float precision. The
top-level ``serialize_kpi_report`` / ``round_kpi_report`` helper rounds
to 4 decimals only when preparing for serialization.

No wall-clock, no uuid4, no data/cases access, no decision logic here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from session.session_schema import SessionArtifact, SessionEventRecord


# KPI report schema version.
#   1.0 — Phase 3 initial (cold_phase / warm_phase / overall).
#   1.1 — B1 Slice 4 closeout: ``compute_session_kpi_report`` now
#         conditionally emits a sibling ``replan`` block keyed by the
#         same cold/warm/overall segments when the artifact contains
#         at least one event with ``replan_trace is not None``. The
#         bump is strictly additive — pre-B1 / replan-disabled reports
#         still serialize with the same keys they did at 1.0.
KPI_REPORT_SCHEMA_VERSION: str = "1.1"


# Ordered Phase 3 KPI field names, used everywhere for deterministic output.
PHASE_KPI_KEYS: tuple[str, ...] = (
    "events_observed",
    "events_with_outcome",
    "events_skipped",
    "events_failed",
    "events_processed",
    "sla_preservation_rate",
    "avg_cost_per_event",
    "calibrated_autonomy_score",
    "human_escalation_rate",
    "auto_execute_rate",
    "known_outcome_coverage",
)


# B1 Slice 4: ordered replan-aware KPI field names. These live on a
# SEPARATE block from PHASE_KPI_KEYS so that the pre-B1 kpi_matrix
# surface in session_compare is unaffected when no replan traces
# exist. Populated only from structured ``SessionEventRecord.replan_trace``
# / ``SessionEventRecord.replan_triggers`` / final
# ``EffectiveDecisionRef`` — never from free-text notes.
REPLAN_KPI_KEYS: tuple[str, ...] = (
    "replan_events_observed",
    "replan_fire_count",
    "replan_trigger_rate",
    "replan_success_count",
    "replan_recovery_rate",
)


_EXEC_STATUS_WITH_OUTCOME: frozenset[str] = frozenset({
    "executed", "executed_via_demo_override",
})
_EXEC_STATUS_SKIPPED: frozenset[str] = frozenset({"awaiting_human_review"})
_EXEC_STATUS_FAILED: frozenset[str] = frozenset({
    "execution_failed", "preflight_failed", "unknown_route",
})


# ---------------------------------------------------------------------------
# Canonical field readers — never ``.get("...")``-guess on non-canonical paths
# ---------------------------------------------------------------------------


def _effective_execution_status(ser: SessionEventRecord) -> str:
    return ser.effective_decision.execution_status


def _effective_final_route(ser: SessionEventRecord) -> str:
    return ser.effective_decision.final_route


def _effective_action_taken(ser: SessionEventRecord) -> Optional[str]:
    return ser.effective_decision.action_taken


def _baseline_cost_incurred(ser: SessionEventRecord) -> Optional[float]:
    outcome = (ser.baseline_event_result or {}).get("execution_outcome")
    if not isinstance(outcome, dict):
        return None
    v = outcome.get("cost_incurred")
    return float(v) if v is not None else None


def _baseline_sla_preserved(ser: SessionEventRecord) -> Optional[bool]:
    outcome = (ser.baseline_event_result or {}).get("execution_outcome")
    if not isinstance(outcome, dict):
        return None
    sla = outcome.get("sla_impact")
    if not isinstance(sla, dict):
        return None
    p = sla.get("preserved")
    return p if isinstance(p, bool) else None


# ---------------------------------------------------------------------------
# Count helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Counts:
    events_observed: int
    events_with_outcome: int
    events_skipped: int
    events_failed: int
    events_processed: int


def _compute_counts(records: list[SessionEventRecord]) -> _Counts:
    obs = len(records)
    with_outcome = 0
    skipped = 0
    failed = 0
    for ser in records:
        status = _effective_execution_status(ser)
        action = _effective_action_taken(ser)
        if status in _EXEC_STATUS_WITH_OUTCOME and action is not None:
            with_outcome += 1
        elif status in _EXEC_STATUS_SKIPPED:
            skipped += 1
        elif status in _EXEC_STATUS_FAILED:
            failed += 1
        else:
            # Path B contract guarantees only the 6 known values. If an
            # unknown status appears, count as failed so KPIs degrade safely.
            failed += 1
    processed = obs - failed
    return _Counts(
        events_observed=obs,
        events_with_outcome=with_outcome,
        events_skipped=skipped,
        events_failed=failed,
        events_processed=processed,
    )


# ---------------------------------------------------------------------------
# Phase KPI computation
# ---------------------------------------------------------------------------


def compute_phase_kpis(records: list[SessionEventRecord]) -> dict[str, Any]:
    """Compute Phase-3 KPI block over a single segment of session records.

    Returns a dict keyed by ``PHASE_KPI_KEYS``. Numeric rates are in full
    precision — the caller must round at serialization if desired.
    """
    counts = _compute_counts(records)

    # Precompute canonical-source-reads once.
    statuses: list[str] = [_effective_execution_status(r) for r in records]
    routes: list[str] = [_effective_final_route(r) for r in records]
    actions: list[Optional[str]] = [_effective_action_taken(r) for r in records]

    # Mask of "events_with_outcome" — canonical definition.
    ewo_mask: list[bool] = [
        s in _EXEC_STATUS_WITH_OUTCOME and a is not None
        for s, a in zip(statuses, actions)
    ]

    # sla_preservation_rate
    sla_num = 0
    sla_den = 0
    for i, is_with_outcome in enumerate(ewo_mask):
        if not is_with_outcome:
            continue
        sla_den += 1
        preserved = _baseline_sla_preserved(records[i])
        if preserved is True:
            sla_num += 1
    sla_preservation_rate: Optional[float] = (sla_num / sla_den) if sla_den > 0 else None

    # avg_cost_per_event
    cost_sum = 0.0
    cost_den = 0
    for i, is_with_outcome in enumerate(ewo_mask):
        if not is_with_outcome:
            continue
        c = _baseline_cost_incurred(records[i])
        if c is None:
            continue
        cost_sum += c
        cost_den += 1
    avg_cost_per_event: Optional[float] = (
        (cost_sum / cost_den) if cost_den > 0 else None
    )

    # calibrated_autonomy_score:
    # numerator  = AUTO_EXECUTE AND with_outcome AND sla_preserved==True
    # denominator = AUTO_EXECUTE AND with_outcome
    cas_num = 0
    cas_den = 0
    for i, is_with_outcome in enumerate(ewo_mask):
        if not is_with_outcome:
            continue
        if routes[i] != "AUTO_EXECUTE":
            continue
        cas_den += 1
        if _baseline_sla_preserved(records[i]) is True:
            cas_num += 1
    calibrated_autonomy_score: Optional[float] = (
        (cas_num / cas_den) if cas_den > 0 else None
    )

    # human_escalation_rate and auto_execute_rate have events_observed
    # as denominator; None only when the segment is empty.
    if counts.events_observed > 0:
        hr_num = sum(1 for r in routes if r == "HUMAN_REQUIRED")
        ar_num = sum(1 for r in routes if r == "AUTO_EXECUTE")
        human_escalation_rate: Optional[float] = hr_num / counts.events_observed
        auto_execute_rate: Optional[float] = ar_num / counts.events_observed
        known_outcome_coverage: Optional[float] = (
            counts.events_with_outcome / counts.events_observed
        )
    else:
        human_escalation_rate = None
        auto_execute_rate = None
        known_outcome_coverage = None

    return {
        "events_observed": counts.events_observed,
        "events_with_outcome": counts.events_with_outcome,
        "events_skipped": counts.events_skipped,
        "events_failed": counts.events_failed,
        "events_processed": counts.events_processed,
        "sla_preservation_rate": sla_preservation_rate,
        "avg_cost_per_event": avg_cost_per_event,
        "calibrated_autonomy_score": calibrated_autonomy_score,
        "human_escalation_rate": human_escalation_rate,
        "auto_execute_rate": auto_execute_rate,
        "known_outcome_coverage": known_outcome_coverage,
    }


# ---------------------------------------------------------------------------
# B1 Slice 4 — replan-aware KPIs
# ---------------------------------------------------------------------------


_EXECUTED_STATUSES: frozenset[str] = frozenset(
    {"executed", "executed_via_demo_override"}
)
_TERMINAL_FAIL_STATUSES: frozenset[str] = frozenset(
    {"execution_failed", "preflight_failed", "unknown_route"}
)


def _attempt_sla_preserved(attempt) -> Optional[bool]:
    """Read ``sla_impact.preserved`` off an attempt's structured outcome.

    Returns ``None`` when the attempt has no executed outcome, so the
    caller can distinguish "unknown" from False.
    """
    outcome = getattr(attempt, "execution_outcome", None)
    if not isinstance(outcome, dict):
        return None
    sla = outcome.get("sla_impact")
    if not isinstance(sla, dict):
        return None
    v = sla.get("preserved")
    return v if isinstance(v, bool) else None


def is_replan_success(ser: SessionEventRecord) -> bool:
    """B1 replan-success rule — narrow, auditable, conservative.

    A replanned event counts as a success iff the final attempt is
    strictly better than attempt 0 on AT LEAST ONE of the following
    explicit dimensions (any-of):

      R1. Status recovery — attempt 0 was a terminal failure
          (``execution_failed`` / ``preflight_failed`` /
          ``unknown_route``) AND the final attempt is executed
          (``executed`` / ``executed_via_demo_override``).
      R2. SLA recovery — attempt 0's ``sla_impact.preserved`` was
          False AND the final attempt's ``sla_impact.preserved`` is
          True.
      R3. Cost recovery — attempt 0's trigger was ``COST_DEVIATION``
          AND the final attempt's trigger is ``NO_TRIGGER`` AND the
          final attempt is executed. (Attempt 1's trigger evaluates
          realized cost against a fresh expected range, so
          ``NO_TRIGGER`` here means the cost landed back inside the
          attempt-1 expected range.)

    Events with no replan_trace (``None`` or length < 2) return
    ``False``. This function reads only structured fields — never
    free-text notes — matching the locked analytics rule.
    """
    trace = ser.replan_trace
    if trace is None or len(trace) < 2:
        return False
    a0 = trace[0]
    a_final = trace[-1]

    # R1: failed → executed
    if (
        a0.attempt_execution_status in _TERMINAL_FAIL_STATUSES
        and a_final.attempt_execution_status in _EXECUTED_STATUSES
    ):
        return True

    # R2: SLA missed → preserved
    a0_sla = _attempt_sla_preserved(a0)
    a_final_sla = _attempt_sla_preserved(a_final)
    if a0_sla is False and a_final_sla is True:
        return True

    # R3: COST_DEVIATION → NO_TRIGGER and final executed
    a0_trig = a0.trigger.trigger_type if a0.trigger is not None else None
    a_final_trig = (
        a_final.trigger.trigger_type if a_final.trigger is not None else None
    )
    if (
        a0_trig == "COST_DEVIATION"
        and a_final_trig == "NO_TRIGGER"
        and a_final.attempt_execution_status in _EXECUTED_STATUSES
    ):
        return True

    return False


def compute_replan_kpis(records: list[SessionEventRecord]) -> dict[str, Any]:
    """Compute the B1 replan-aware KPI block over one segment.

    All five keys in ``REPLAN_KPI_KEYS`` are always present in the
    returned dict; zero-denominator rates are ``None``. Canonical
    sources: ``SessionEventRecord.replan_trace`` and
    ``SessionEventRecord.replan_triggers``. Free-text notes are not
    consulted.

      - ``replan_events_observed`` = count of records where
        ``replan_trace is not None``.
      - ``replan_fire_count`` = count of records whose first trigger
        has ``trigger_type != "NO_TRIGGER"``; by the orchestrator
        contract this equals ``replan_events_observed`` (trace is
        only materialized when attempt 0 fires a trigger), but the
        count is derived independently here for auditable
        consistency.
      - ``replan_trigger_rate`` = ``replan_fire_count /
        events_observed``; ``None`` when the segment is empty.
      - ``replan_success_count`` = count of replanned records for
        which :func:`is_replan_success` returns True.
      - ``replan_recovery_rate`` = ``replan_success_count /
        replan_fire_count``; ``None`` when ``replan_fire_count == 0``.
    """
    events_observed = len(records)

    replan_events_observed = 0
    replan_fire_count = 0
    replan_success_count = 0

    for ser in records:
        if ser.replan_trace is None:
            continue
        replan_events_observed += 1
        triggers = ser.replan_triggers or []
        # By the orchestrator contract, triggers[0] is the attempt-0
        # decision. A replan is only materialized when attempt 0
        # fires a non-NO_TRIGGER — but we derive the count here from
        # the structured triggers list rather than trust the shape.
        if triggers and triggers[0].trigger_type != "NO_TRIGGER":
            replan_fire_count += 1
        if is_replan_success(ser):
            replan_success_count += 1

    replan_trigger_rate: Optional[float] = (
        replan_fire_count / events_observed if events_observed > 0 else None
    )
    replan_recovery_rate: Optional[float] = (
        replan_success_count / replan_fire_count
        if replan_fire_count > 0
        else None
    )
    return {
        "replan_events_observed": replan_events_observed,
        "replan_fire_count": replan_fire_count,
        "replan_trigger_rate": replan_trigger_rate,
        "replan_success_count": replan_success_count,
        "replan_recovery_rate": replan_recovery_rate,
    }


def _any_replan_trace(records: Iterable[SessionEventRecord]) -> bool:
    return any(r.replan_trace is not None for r in records)


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------


def segment_records(
    records: list[SessionEventRecord],
    *,
    min_records_for_shift: int,
) -> tuple[list[SessionEventRecord], list[SessionEventRecord]]:
    """Split records into (cold_phase, warm_phase).

    cold_phase = events 1..min_records_for_shift        (i.e., first N by index)
    warm_phase = events min_records_for_shift+1..end    (i.e., remainder)

    Both lists are in event order. Accepts N larger than len(records)
    (warm phase may be empty).
    """
    n = int(min_records_for_shift)
    if n < 0:
        raise ValueError(f"min_records_for_shift must be >= 0, got {n}")
    cold = list(records[:n])
    warm = list(records[n:])
    return cold, warm


# ---------------------------------------------------------------------------
# Session-level KPI report
# ---------------------------------------------------------------------------


def compute_session_kpi_report(
    artifact: SessionArtifact,
    *,
    min_records_for_shift: int,
) -> dict[str, Any]:
    """Compute the full cold/warm/overall KPI report for one SessionArtifact.

    Returns a plain dict suitable for embedding into a SessionCompareReport
    and for canonical-JSON serialization.

    B1 Slice 4 additive behavior: when the artifact has at least one
    event with ``replan_trace is not None``, a sibling ``replan``
    block is attached carrying per-segment replan KPIs
    (``cold_phase``, ``warm_phase``, ``overall``). When no event has
    a replan trace, the ``replan`` key is OMITTED — pre-B1 / replan-
    disabled artifacts serialize byte-identically to their pre-B1
    output.
    """
    records = list(artifact.event_records)
    cold, warm = segment_records(
        records, min_records_for_shift=min_records_for_shift,
    )
    report: dict[str, Any] = {
        "schema_version": KPI_REPORT_SCHEMA_VERSION,
        "session_id": artifact.session_id,
        "mode": artifact.config.mode,
        "min_records_for_shift": int(min_records_for_shift),
        "cold_phase": compute_phase_kpis(cold),
        "warm_phase": compute_phase_kpis(warm),
        "overall": compute_phase_kpis(records),
    }
    if _any_replan_trace(records):
        report["replan"] = {
            "cold_phase": compute_replan_kpis(cold),
            "warm_phase": compute_replan_kpis(warm),
            "overall": compute_replan_kpis(records),
        }
    return report


# ---------------------------------------------------------------------------
# Rounding helpers (serialization boundary only)
# ---------------------------------------------------------------------------


_ROUNDABLE_KEYS: frozenset[str] = frozenset({
    "sla_preservation_rate",
    "avg_cost_per_event",
    "calibrated_autonomy_score",
    "human_escalation_rate",
    "auto_execute_rate",
    "known_outcome_coverage",
})


_REPLAN_ROUNDABLE_KEYS: frozenset[str] = frozenset({
    "replan_trigger_rate",
    "replan_recovery_rate",
})


def _round_phase_kpis(block: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in PHASE_KPI_KEYS:
        v = block[k]
        if k in _ROUNDABLE_KEYS and isinstance(v, float):
            out[k] = round(v, 4)
        else:
            out[k] = v
    return out


def _round_replan_kpis(block: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in REPLAN_KPI_KEYS:
        v = block[k]
        if k in _REPLAN_ROUNDABLE_KEYS and isinstance(v, float):
            out[k] = round(v, 4)
        else:
            out[k] = v
    return out


def round_kpi_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a new KPI report with numeric rates rounded to 4 decimals.

    Use this only at the serialization boundary (writing a compare
    report or thesis markdown). Intermediate computation never rounds.
    """
    rounded = dict(report)
    for seg in ("cold_phase", "warm_phase", "overall"):
        rounded[seg] = _round_phase_kpis(report[seg])
    if "replan" in report:
        rounded["replan"] = {
            seg: _round_replan_kpis(report["replan"][seg])
            for seg in ("cold_phase", "warm_phase", "overall")
        }
    return rounded
