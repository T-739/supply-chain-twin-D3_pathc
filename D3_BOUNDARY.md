# D3-Demo Boundary Document

Phase 0 deliverable — frozen scope, contracts, and engineering constraints.

---

## 1. Current System Identity

**D3-Demo** is an event-driven semi-autonomous exception loop demonstrator for supply chain fulfillment disruption response.

- **Primary identity**: Event-driven semi-autonomous exception loop demonstrator (Path B target).
- **Secondary identity**: Preserved Research Core for benchmark evaluation and thesis alignment (sidecar).
- **Engineering foundation**: Built on a mature V2 codebase with deterministic backbone, structured agent outputs, strict truth boundary, and comprehensive tests.

V2 is **not** the current main-line identity. It serves three roles:
1. Reusable engineering asset source
2. Baseline for comparison
3. Research Core / evaluation sidecar source

---

## 2. In-Scope for Path B

Path B (~50h) delivers the event-driven closed loop:

- **Phase 0**: Freeze scope + design contracts (this document + schema files)
- **Phase 1**: Policy Gate + sequential event processing (Path A fallback)
- **Phase 2**: Event Engine + TwinState hot-patch (true event-driven behavior)
- **Phase 3**: Execution adapters + outcome feedback (closed loop)
- **Phase 4**: Event-centric UI in Streamlit

Each phase produces a demoable state and can serve as fallback.

---

## 3. Explicit Out-of-Scope Items

The following are **not** part of the current deliverable:

- **Path C** in its entirety: learning module, adaptive policy gate, replan trigger, event correlator, React dashboard, session management
- Production ERP/WMS/TMS integration
- Multi-user or multi-tenant support
- Stochastic outcome generation (all outcomes are deterministic)
- ML model training of any kind
- LLM-determined numbers, costs, labels, or evaluation metrics
- New LLM providers or LLM backend changes

---

## 4. Frozen Reuse Modules

These files must **never** be modified. They are reused as-is.

| File | Role |
|------|------|
| `src/evaluation.py` | Research Core — oracle truth evaluation |
| `src/action_code_mapper.py` | Three-layer identifier bridge contract |
| `data/cases/*.json` (all 20 cases) | Oracle truth — frozen case data |
| `src/agents/operations_agent.py` | Candidate generation + feasibility gating |
| `src/agents/cost_agent.py` | Deterministic cost estimation backbone |
| `src/agents/governance_agent.py` | 8-field structured recommendation schema |
| `src/agents/__init__.py` | Agent package init |
| `src/supervisor.py` | Supervision decision logic |
| `src/rag_setup.py` | Domain grounding layer |
| `src/retrieval.py` | Retrieval stack |
| `src/llm_backend.py` | LLM gateway with fallback chain |
| `src/llm_providers/*.py` | Provider implementations |
| `src/case_translation.py` | Case translation utilities |
| `src/api/*.py` | FastAPI assets (frozen until needed) |
| `SPEC.md` | V2 specification |
| `SPEC_BRIDGE.md` | V2 bridge specification |
| `data/scenarios/*.json` | Scenario definitions |
| `data/configs/*.json` | Configuration files |
| `scripts/*.py` | Batch evaluation and utility scripts |

---

## 5. Additive-Only Modules

These files may be modified in future phases, but **only additively** — existing methods, signatures, and behavior must not change.

| File | Allowed Change | Phase |
|------|---------------|-------|
| `src/twin_state.py` | Add `apply_event_patch()` method | Phase 2 |
| `src/twin_state.py` | Add `apply_action_outcome()` method | Phase 3 |
| `src/graph.py` | Add `policy_gate_node` after governance, before supervisor | Phase 1 |
| `src/graph.py` | Add conditional edge for auto-execute path | Phase 1 |
| `app.py` | Add event sequence UI elements | Phase 1+ |
| `app.py` | Add event timeline, decision panel, outcome log | Phase 4 |

All existing nodes, edges, methods, and tests must remain unchanged.

---

## 6. Forbidden Modifications

The following rules are **inviolable**:

- **No runtime module may import** `src/evaluation.py` or `src/action_code_mapper.py`
- **No runtime module may use oracle truth** (`oracle`, `cost_ground_truth`, evaluation-layer labels) from `data/cases/*.json` as execution decision inputs. Phase 1 fallback (sequential case replay via the existing graph path) may read legacy case snapshots and scenario context through the V2 `load_case_or_scenario` node, but this is a transitional path — the primary event-driven runtime (Phase 2+) ingests events from the Event Engine, not case JSONs
- **No modification** to any existing test file in `tests/`
- **No deletion** of any existing file
- **No modification** to `data/cases/*.json` — oracle truth is immutable
- **GovernanceOutput 8-field schema** must not be extended — outcome injection goes through input context (scenario_context sideband), never into the output schema
- **No LLM call** may determine numeric values, cost calculations, evaluation labels, or routing decisions

---

## 7. Truth Boundary

> Evaluation truth comes **exclusively** from pre-computed oracle case JSONs (`data/cases/*.json`).
> Runtime outcomes, agent outputs, and LLM-generated content **never** substitute for oracle truth.

Specifically:
- `cost_ground_truth` in case JSON is the **only** authoritative cost source for evaluation
- `oracle.action_code` and `oracle.cost_total` are the **only** authoritative oracle references
- `ExecutionOutcome.cost_incurred` is a **runtime** field — it reflects simulated execution cost, not evaluation truth
- The outcome store (Phase 3) is a **completely separate** data structure from oracle case JSONs
- Research Core evaluation metrics (regret, unnecessary override, override effectiveness) are computed **only** against frozen oracle truth

---

## 8. Layer Separation

Three identifier layers exist and must **never** be mixed:

| Layer | Identifiers | Used By |
|-------|------------|---------|
| **Operational** | `EXPEDITE`, `TRANSFER`, `COMPENSATE`, `NO_ACTION` | Operations Agent, Cost Agent, Execution Adapters, `ExecutionOutcome.action_taken` |
| **Supervision** | `APPROVE`, `VERIFY`, `OVERRIDE` | Supervisor, Policy Gate routing context |
| **Evaluation** | `AI`, `ALT1`, `ALT2` | Evaluation module, action code mapper, oracle case JSONs |

- `src/action_code_mapper.py` is the **only** sanctioned bridge between layers
- `ExecutionOutcome.action_taken` accepts **only** operational-layer identifiers
- Policy Gate reads `risk_level` (a governance output field), **not** evaluation codes
- Runtime modules must not reference evaluation-layer identifiers

---

## 9. Runtime vs Research Core Separation

| Aspect | Runtime Path (D3 loop) | Research Core (sidecar) |
|--------|----------------------|------------------------|
| Data source | Synthetic events from Event Engine | Frozen oracle case JSONs |
| State | TwinState with hot-patching | Static `initial_state_snapshot` from case JSON |
| Outcome | `ExecutionOutcome` in outcome store | `cost_ground_truth` in case JSON |
| Metrics | Event resolution rate, SLA rescue rate, cost-to-recover | Regret, unnecessary override, override effectiveness |
| Contamination rule | **Must not read** oracle cases for decisions | **Must not read** runtime outcomes as truth |

The two paths share the reasoning sub-graph (Operations → Cost → Governance) but diverge at:
- **Runtime**: Policy Gate → Execution Adapter → Outcome Store
- **Research Core**: Supervisor → Evaluation Node (reads oracle truth)

---

## 10. Phase Progression and Scope-Cut Ladder

### Phase progression

| Phase | Deliverable | Demoable State |
|-------|------------|----------------|
| 0 | Contracts + boundary doc | No runtime change |
| 1 | Policy Gate + sequential events | Path A: cases with semi-autonomy |
| 2 | Event Engine + TwinState hot-patch | True event-driven behavior |
| 3 | Execution adapters + outcome feedback | Path B: complete closed loop |
| 4 | Event-centric UI | Full visual demo |

### Scope-cut ladder (cut in this order if time runs out)

1. Drop outcome summary injection (Phase 3 partial) — loop still works, no cross-event augmentation
2. Drop event-centric UI (Phase 4) — use Streamlit with event sequence runner
3. Drop execution adapters + outcome feedback (Phase 3) — retreat to Phase 1 end state
4. Drop Event Engine (Phase 2) — retreat to Path A: V2 + Policy Gate
5. Drop Policy Gate (Phase 1) — retreat to V2 as-is (still a complete, tested system)

### TwinState mutation entry points (declared, not yet implemented)

- `apply_event_patch(event: EventPayload) -> None` — Phase 2
- `apply_action_outcome(outcome: ExecutionOutcome) -> None` — Phase 3

These are the **only** sanctioned mutation entry points for D3 event-driven state updates. All other TwinState access during the event loop is read-only.

---

*Phase 0 deliverable. This document is the authority for what may and may not change during D3-Demo implementation.*
