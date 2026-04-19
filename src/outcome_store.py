"""
outcome_store.py — D3-Demo Phase 3: Append-only runtime outcome store.

Stores ExecutionOutcome records for runtime audit and cross-event summary
injection. Completely separate from oracle case JSONs.

In-memory only (no persistence, no delete, no update).

This module does NOT:
  - Read or write data/cases/*.json
  - Import evaluation.py or action_code_mapper.py
  - Implement adaptive thresholds, learning, replan, correlation (Path C)
  - Depend on evaluation semantics in any form
"""

from __future__ import annotations

from typing import Any

from outcome_schema import ExecutionOutcome


_RECENT_DEFAULT = 5


class OutcomeStore:
    """Append-only, in-memory store of ExecutionOutcome records.

    Tracks two things:
      - outcomes: every ExecutionOutcome appended
      - routing counts: every policy route seen (including routes that did
        not produce an outcome, e.g. HUMAN_REQUIRED events skipped in the
        default Phase 3 policy)
    """

    def __init__(self) -> None:
        self._outcomes: list[ExecutionOutcome] = []
        self._route_counts: dict[str, int] = {
            "AUTO_EXECUTE": 0,
            "HUMAN_REQUIRED": 0,
        }

    # ------------------------------------------------------------------
    # Append API (append-only)
    # ------------------------------------------------------------------

    def append(self, outcome: ExecutionOutcome) -> None:
        """Append an ExecutionOutcome. Raises TypeError on bad input.

        Append-only: there is no delete/update/replace. Each call appends
        one record in arrival order.
        """
        if not isinstance(outcome, ExecutionOutcome):
            raise TypeError(
                f"outcome must be ExecutionOutcome, got {type(outcome).__name__}"
            )
        self._outcomes.append(outcome)

    def record_routing(self, route: str) -> None:
        """Record a policy routing decision (regardless of execution).

        Used by the event loop to count escalations vs. auto-executions,
        even when HUMAN_REQUIRED events are skipped (no outcome appended).
        Unknown route strings are counted under their exact string value.
        """
        if not isinstance(route, str) or not route:
            return
        self._route_counts[route] = self._route_counts.get(route, 0) + 1

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def all(self) -> list[ExecutionOutcome]:
        """Return a shallow copy of all outcomes in arrival order."""
        return list(self._outcomes)

    def count(self) -> int:
        """Number of outcomes stored."""
        return len(self._outcomes)

    def latest(self) -> ExecutionOutcome | None:
        """The most recently appended outcome, or None if empty."""
        return self._outcomes[-1] if self._outcomes else None

    # ------------------------------------------------------------------
    # Summary — deterministic aggregates
    # ------------------------------------------------------------------

    def summary(self, *, recent_n: int = _RECENT_DEFAULT) -> dict[str, Any]:
        """Deterministic aggregate statistics over stored outcomes.

        Returns a flat dict safe to inject into scenario_context. Empty
        store returns an empty-but-valid summary.

        Fields:
          - outcomes_count
          - total_cost, avg_cost
          - action_counts (per operational action type)
          - status_counts (EXECUTED/SKIPPED/REJECTED)
          - sla_preserved_count, sla_missed_count
          - auto_executed_count, human_required_count (from record_routing)
          - recent_actions (at most recent_n entries; compact summary)
          - recent_resolution_patterns (action_type:status histogram)
        """
        n = len(self._outcomes)

        action_counts: dict[str, int] = {
            "EXPEDITE": 0, "TRANSFER": 0, "COMPENSATE": 0, "NO_ACTION": 0,
        }
        status_counts: dict[str, int] = {
            "EXECUTED": 0, "SKIPPED": 0, "REJECTED": 0,
        }
        sla_preserved = 0
        sla_missed = 0
        total_cost = 0.0

        for o in self._outcomes:
            action_counts[o.action_taken] = action_counts.get(o.action_taken, 0) + 1
            status_counts[o.status] = status_counts.get(o.status, 0) + 1
            total_cost += float(o.cost_incurred)
            sla = o.sla_impact if isinstance(o.sla_impact, dict) else {}
            preserved = sla.get("preserved")
            if preserved is True:
                sla_preserved += 1
            elif preserved is False:
                sla_missed += 1

        avg_cost = (total_cost / n) if n > 0 else 0.0

        recent: list[dict[str, Any]] = []
        for o in self._outcomes[-recent_n:]:
            sla = o.sla_impact if isinstance(o.sla_impact, dict) else {}
            recent.append({
                "event_id": o.event_id,
                "action_taken": o.action_taken,
                "cost_incurred": float(o.cost_incurred),
                "status": o.status,
                "sla_preserved": sla.get("preserved"),
            })

        resolution_patterns: dict[str, int] = {}
        for o in self._outcomes:
            key = f"{o.action_taken}:{o.status}"
            resolution_patterns[key] = resolution_patterns.get(key, 0) + 1

        return {
            "schema_version": "1.0",
            "outcomes_count": n,
            "total_cost": round(total_cost, 4),
            "avg_cost": round(avg_cost, 4),
            "action_counts": action_counts,
            "status_counts": status_counts,
            "sla_preserved_count": sla_preserved,
            "sla_missed_count": sla_missed,
            "auto_executed_count": self._route_counts.get("AUTO_EXECUTE", 0),
            "human_required_count": self._route_counts.get("HUMAN_REQUIRED", 0),
            "recent_actions": recent,
            "recent_resolution_patterns": resolution_patterns,
        }
