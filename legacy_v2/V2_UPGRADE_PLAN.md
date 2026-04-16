# V2 Upgrade Plan — Frozen Boundaries and Migration Rules

**Status:** Phase 0 artifact. Authoritative until a phase explicitly amends it.
**Companion docs:** `Supply Chain Twin V1 Report.pdf`, `Supply_Chain_Twin_V2_Upgrade_Roadmap.pdf`, `SPEC_BRIDGE.md`.

## 0. Upgrade principle

LLMs upgrade reasoning, synthesis, and explanation. LLMs **do not** redefine numeric truth, oracle labels, or evaluation authority. Deterministic V1 logic remains the mandatory fallback.

## 1. Non-negotiable rules

1. Operational / supervision / evaluation layers stay strictly separate.
2. `cost_ground_truth` and `src/evaluation.py` remain the only authoritative evaluation source.
3. GovernanceOutput (8 fields) and SupervisorDecision schemas stay frozen unless formally migrated.
4. Every phase has an explicit rollback point.
5. Streamlit remains the fallback UI until the new frontend is stable.

## 2. Frozen contracts (do NOT modify outside a formal migration phase)

| Contract | File | Why frozen |
|---|---|---|
| GraphState shared keys | `src/graph.py` | Contract for all nodes; widening only via additive keys. |
| TwinState / runtime cost | `src/twin_state.py` | Runtime simulation; never substituted for evaluation truth. |
| Evaluation semantics | `src/evaluation.py` | Ground-truth reader for regret / override metrics. |
| GovernanceOutput (8 fields) | `src/agents/governance_agent.py` | Thesis-core synthesis contract. |
| SupervisorDecision schema | `src/supervisor.py` | Supervision-layer output. |
| Case JSON truth structure | `data/cases/*.json` | `cost_ground_truth`, `oracle`, `agent_recommendation_action_code`, `decision_options` are oracle truth. |
| V1 fallback behavior | rules-mode path | Must remain runnable when LLMs disabled. |

## 3. Identifier domains (never mixed)

| Layer | Identifiers | Where used |
|---|---|---|
| Operational | `EXPEDITE`, `TRANSFER`, `COMPENSATE`, `NO_ACTION` | Operations candidates, cost estimates. |
| Supervision | `APPROVE`, `VERIFY`, `OVERRIDE` | SupervisorDecision. |
| Evaluation | `AI`, `ALT1`, `ALT2` | `cost_ground_truth`, oracle, case `decision_options`, `evaluation.py`. |

A mapper module is the **only** sanctioned adapter between supervision and evaluation domains. Operational identifiers never appear in evaluation payloads; evaluation identifiers never appear in supervisor fields.

## 4. Truth boundary

- Evaluation truth is read from case JSON: `cost_ground_truth[code].c_total`, `oracle.action_code`, `oracle.cost_total`.
- Runtime `cost_output` / `TwinState.compute_total_cost()` are **decision support**, not evaluation truth.
- LLM text (situational_explanation, rationale_trace, confidence_note) never overrides numeric fields.

## 5. Provider strategy

- **Primary provider:** OpenAI (structured-output engine, Phase 2+).
- **Secondary provider:** Anthropic (comparison path).
- **Mandatory fallback:** deterministic V1 rules path.
- Global feature flag switches to deterministic-only mode.

## 6. What may change vs. what may not

| May change per phase | Must not change without formal migration |
|---|---|
| Node internals (prompts, rationale generation) | Node names, GraphState key names, edge topology |
| LLM-generated text fields in GovernanceOutput | 8-field schema, field types |
| UI rendering, new panels | Case JSON truth structure |
| Additive GraphState keys (e.g. `evaluation_result`) | Existing key semantics |
| Batch runner, API layer (later phases) | `evaluation.py` function signatures and semantics |

## 7. Per-phase rollback points

| Phase | Rollback |
|---|---|
| 0 | No production code touched; V1 intact. |
| 1 | Disable evaluation panel; V1 single-case workflow still runs without eval fields. |
| 2 | Global feature flag → deterministic-only. |
| 3 | `governance_mode` flag → rules. |
| 4 | Operations deterministic mode, governance LLM can remain on. |
| 5 | TF-IDF retrieval fallback retained. |
| 6 | Single-case demo still works without batch. |
| 7 | Streamlit is the fallback API client. |
| 8 | Streamlit UI retained. |
| 9 | Prior phase output still demoable. |

## 8. Per-phase success gates

- **Phase 0:** This file exists; collaborator can revert to V1 in one sentence. (Revert = delete new files added in Phases 1+; no existing V1 files modified destructively.)
- **Phase 1:** One case run produces `evaluation_result` with `regret`, `is_override`, `is_unnecessary_override`, `override_effectiveness`; 20-case batch exports a CSV with those columns; no V1 test regresses.
- **Phase 2:** Dummy schema round-trips on both providers; malformed JSON degrades to deterministic path; trace records provider + latency.
- **Phase 3:** Dual-mode governance valid against 8-field schema; flag flips cleanly.
- **Phase 4:** Operations never emits forbidden action types or evaluation identifiers.
- **Phase 5+:** Deferred — see roadmap PDF §§ Phase 5–9.

## 9. Phase 1 touched-module inventory

**Added:**
- `src/action_code_mapper.py` — isolated adapter (supervisor mode + case JSON → AI/ALT1/ALT2).
- `tests/test_action_code_mapper.py`
- `tests/test_evaluation_node.py`
- `scripts/batch_eval_runner.py`
- Streamlit "Evaluation Results" panel (in `app.py`).

**Edited:**
- `src/graph.py` — `evaluation_node` body replaced (stub → real call). Graph topology, node names, and GraphState keys unchanged.
- `app.py` — additive panel only.

**Explicitly NOT edited in Phase 1:**
- `src/evaluation.py` (semantics frozen).
- `src/supervisor.py`, `src/twin_state.py`, any agent, any case JSON.

## 10. Rollback procedure for Phase 1

1. In `src/graph.py`, restore the stub body of `evaluation_node`:
   ```python
   state["evaluation_result"] = {"status": "stub", "regret": None}
   ```
2. Remove the Evaluation Results panel block from `app.py`.
3. Delete `src/action_code_mapper.py`, `tests/test_action_code_mapper.py`, `tests/test_evaluation_node.py`, `scripts/batch_eval_runner.py`.
4. V1 behavior is exactly restored; no case JSON or evaluation semantics touched.
