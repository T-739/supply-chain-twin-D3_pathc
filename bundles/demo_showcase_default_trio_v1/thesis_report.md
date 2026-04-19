# Path C Phase 3 — Thesis-Aligned Session Compare Report

Schema: `SessionCompareReport v1.1`. Baseline mode: `baseline_static`. min_records_for_shift = `3`.

## Overall KPIs

| KPI | baseline_static | path_c_cold | path_c_warm |
|---|---|---|---|
| events_observed | 7 | 7 | 7 |
| events_with_outcome | 6 | 6 | 7 |
| events_skipped | 0 | 0 | 0 |
| events_failed | 0 | 0 | 0 |
| events_processed | 7 | 7 | 7 |
| sla_preservation_rate | 0.8571 | 0.8571 | 1.0000 |
| avg_cost_per_event | 195.7100 | 195.7100 | 195.7100 |
| calibrated_autonomy_score | 0.7143 | 0.7143 | 0.8571 |
| human_escalation_rate | 0.2857 | 0.2857 | 0.1429 |
| auto_execute_rate | 0.7143 | 0.7143 | 0.8571 |
| known_outcome_coverage | 0.8571 | 0.8571 | 1.0000 |

## Cold-phase KPIs

| KPI | baseline_static | path_c_cold | path_c_warm |
|---|---|---|---|
| events_observed | 3 | 3 | 3 |
| events_with_outcome | 2 | 2 | 2 |
| events_skipped | 0 | 0 | 0 |
| events_failed | 0 | 0 | 0 |
| events_processed | 3 | 3 | 3 |
| sla_preservation_rate | 0.6667 | 0.6667 | 0.6667 |
| avg_cost_per_event | 256.6700 | 256.6700 | 256.6700 |
| calibrated_autonomy_score | 0.6667 | 0.6667 | 0.6667 |
| human_escalation_rate | 0.3333 | 0.3333 | 0.3333 |
| auto_execute_rate | 0.6667 | 0.6667 | 0.6667 |
| known_outcome_coverage | 0.6667 | 0.6667 | 0.6667 |

## Warm-phase KPIs

| KPI | baseline_static | path_c_cold | path_c_warm |
|---|---|---|---|
| events_observed | 4 | 4 | 4 |
| events_with_outcome | 4 | 4 | 4 |
| events_skipped | 0 | 0 | 0 |
| events_failed | 0 | 0 | 0 |
| events_processed | 4 | 4 | 4 |
| sla_preservation_rate | 1.0000 | 1.0000 | 1.0000 |
| avg_cost_per_event | 150.0000 | 150.0000 | 150.0000 |
| calibrated_autonomy_score | 0.7500 | 0.7500 | 1.0000 |
| human_escalation_rate | 0.2500 | 0.2500 | 0.0000 |
| auto_execute_rate | 0.7500 | 0.7500 | 1.0000 |
| known_outcome_coverage | 1.0000 | 1.0000 | 1.0000 |

## Deltas vs baseline (overall)

### path_c_cold_minus_baseline_static

| KPI | delta |
|---|---|
| sla_preservation_rate | 0.0000 |
| avg_cost_per_event | 0.0000 |
| calibrated_autonomy_score | 0.0000 |
| human_escalation_rate | 0.0000 |
| auto_execute_rate | 0.0000 |
| known_outcome_coverage | 0.0000 |

### path_c_warm_minus_baseline_static

| KPI | delta |
|---|---|
| sla_preservation_rate | 0.1429 |
| avg_cost_per_event | 0.0000 |
| calibrated_autonomy_score | 0.1428 |
| human_escalation_rate | -0.1428 |
| auto_execute_rate | 0.1428 |
| known_outcome_coverage | 0.1429 |

## Diverged events

1 event(s) diverged.

## Relation to calibrated supervision thesis

**Claim:** Path C extends calibrated supervision into a temporally adaptive semi-autonomy loop.

- warm_calibrated_autonomy_delta: `0.1428`
- warm_sla_preservation_delta: `0.1429`
- warm_cost_delta: `0.0000`
- supports_claim: **true**

Notes: Warm session matches or exceeds baseline on SLA and calibrated autonomy with non-increasing cost.

This paragraph is generated deterministically from the structured compare report. The verdict reflects the observed deltas and is not post-tuned to match the claim.
