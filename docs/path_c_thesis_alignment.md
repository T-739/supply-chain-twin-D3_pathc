# Path C — Thesis Alignment (Phase 3)

This document describes, at a Path-C-min level, how the Phase 3 eval
harness relates to the calibrated-supervision thesis the project
investigates. It is a reading aid for reviewers; the canonical
artifact is the structured `compare_report.json` produced by
`scripts/session_eval_harness.py`, and the human-readable rollup is
`thesis_report.md` rendered deterministically by
`session.session_compare.render_thesis_markdown`.

## Thesis claim

> **Path C extends calibrated supervision into a temporally adaptive
> semi-autonomy loop.**

Operationally this means: given a stream of events processed through
Path B's reasoning stack, adding an episodic-memory-driven adaptive
policy gate can *selectively* escalate to human review when past
memory indicates a pattern of poor-SLA auto-execution outcomes —
without changing any agent prompt, any `GovernanceOutput` schema, or
any Research Core surface.

## How Phase 3 tests the claim

Three sessions are run with matched inputs (same seed, same event
source, same `min_records_for_shift`):

- `baseline_static` — Path B unchanged, no adaptive layer, no memory.
- `path_c_cold` — Path C main path with empty seed memory. First
  `min_records_for_shift` events are cold-start fallbacks
  (decision-byte-identical to baseline). Warm-phase events may diverge
  if accumulated memory triggers rules.
- `path_c_warm` — Path C main path with a deterministic synthetic
  seed memory (10 poor-SLA CARRIER_DELAY records by default).
  Warm-phase adaptive behavior is exercisable from event 1 (subject
  to cold-start threshold on any specific rule's memory slice).

The compare report computes Phase-3 KPIs at three segments (cold /
warm / overall) and derives the `thesis_claim_support` block from
the overall warm-vs-baseline deltas.

## KPI source-of-truth (Roadmap §3.D)

| Field | Canonical source |
|---|---|
| `execution_status` | `SessionEventRecord.effective_decision.execution_status` |
| `final_route` | `SessionEventRecord.effective_decision.final_route` |
| `action_taken` | `SessionEventRecord.effective_decision.action_taken` |
| `cost_incurred` | `baseline_event_result["execution_outcome"]["cost_incurred"]` |
| `sla_impact.preserved` | `baseline_event_result["execution_outcome"]["sla_impact"]["preserved"]` |
| `mode`, `policy_route_source`, `adaptive_adjustment` | `SessionEventRecord` overlay |

No KPI is ever read from a non-canonical path. Overlay is canonical
for anything the adaptive layer might touch; baseline is canonical for
the two numeric outcome fields that are definitionally Path B's.

## Honesty rule

If `path_c_warm` fails to improve calibrated autonomy over
`baseline_static`, the compare report records
`supports_claim = False` with explanatory notes. Phase 3 code contains
no switch to re-tune rules, thresholds, or baselines in order to force
`supports_claim = True`. This is an explicit Roadmap §3.F rollback
clause: "thesis honesty requires reporting real outcomes, not
re-engineering rules to force an improvement."

## Out-of-Path-C-min

The following belong to post-Phase-3 backlog (Roadmap §3.G):
React/UI, replan, correlator, agent-visible memory, cross-session
cumulative memory. None of them is implemented or imported by
Phase 3 code.
