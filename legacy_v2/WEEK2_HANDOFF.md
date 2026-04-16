# Week 3 Handoff Package — Supply Chain Twin MVP

## 1. Executive Summary

### What this project is

A thesis-aligned LangGraph-based human-supervised supply chain twin for disruption simulation and fulfillment exception handling. The theoretical core centers on **calibrated supervision**, **uncertainty expression**, and **traceability-oriented governance**.

The MVP uses a deterministic 2x2x2x2 entity network (2 suppliers, 2 warehouses, 2 carriers, 2 customer zones) with 20 synthetic cases containing pre-computed oracle ground truth. There are no LLM calls, no external APIs, and no stochastic simulation — all computation is deterministic.

### What Week 2 completed

The entire backend pipeline is implemented and passing:

- **Graph backbone**: 7-node LangGraph sequential pipeline
- **RAG foundation**: TF-IDF retrieval over 5 business-rule markdown docs (37 chunks)
- **Operations Agent**: generates bounded operational candidates (EXPEDITE/TRANSFER/COMPENSATE/NO_ACTION) from twin state entities
- **Cost Agent**: deterministic runtime cost estimates aligned with TwinState formulas
- **Governance Agent**: synthesizes frozen 8-field GovernanceOutput from ops + cost + scenario
- **Supervisor node**: structured APPROVE/VERIFY/OVERRIDE decisions with identity resolution
- **Case-driven end-to-end flow**: all 20 cases run through the full pipeline

### Why the backend is ready for Week 3 UI

- **699 tests pass**, zero failures
- All agent outputs are JSON-serializable Pydantic models with `.to_dict()` / `.to_json()`
- The graph accepts `case_id` + optional `supervisor_instruction` and returns a fully populated state dict
- Every piece of content a Streamlit UI needs is already available in the graph state
- No backend changes are needed to build the UI

---

## 2. Current Backend Status

### Test status

```
699 passed in ~2 seconds
11 test files, 4,303 lines of test code
```

### Module inventory

| Module | Lines | Status |
|--------|-------|--------|
| `src/graph.py` | 297 | Complete — 7-node graph, GraphState with 16 fields |
| `src/agents/operations_agent.py` | 604 | Complete — candidate generation + scoring |
| `src/agents/cost_agent.py` | 476 | Complete — deterministic cost estimation |
| `src/agents/governance_agent.py` | 596 | Complete — 8-field synthesis + meta for supervisor |
| `src/supervisor.py` | 345 | Complete — APPROVE/VERIFY/OVERRIDE paths |
| `src/rag_setup.py` | 270 | Complete — TF-IDF vector store + retrieval |
| `src/twin_state.py` | 624 | FROZEN Week 1 — entity models + mutations |
| `src/evaluation.py` | 328 | FROZEN Week 1 — oracle truth from case JSON |
| `src/case_translation.py` | 161 | Week 1 — case JSON to runtime translation |

### Data inventory

- `data/cases/` — 20 JSON case files (M01–M14, P01–P06) with oracle ground truth
- `data/knowledge/` — 5 core markdown docs + 1 meta-doc (excluded from retrieval)
- `data/configs/baseline_network.json` — canonical MVP entity configuration
- `data/scenarios/` — 7 scenario template files
- `data/mappings/case_to_scenario_map.json`

---

## 3. Frozen Contracts — Must Not Be Changed

### Truth boundary

- **Evaluation truth** comes ONLY from `case["cost_ground_truth"][action_code]["c_total"]` resolved by `src/evaluation.py`
- `evaluation.py` defines `ActionCode = Literal["AI", "ALT1", "ALT2"]` — these are evaluation-layer codes
- No agent or supervisor file imports `evaluation.py`
- The cost agent produces `_estimate`-suffixed fields that explicitly disclaim being evaluation truth

### Layer separation

Three distinct layers exist and must remain separate:

| Layer | Codes | Module(s) |
|-------|-------|-----------|
| **Operational** | EXPEDITE, TRANSFER, COMPENSATE, NO_ACTION | operations_agent.py, cost_agent.py |
| **Supervision** | APPROVE, VERIFY, OVERRIDE | supervisor.py |
| **Evaluation** | AI, ALT1, ALT2 | evaluation.py |

Rules:
- AI/ALT1/ALT2 must NEVER appear as `candidate_type`, `recommended_action`, or `selected_candidate_id`
- APPROVE/VERIFY/OVERRIDE must NEVER be treated as operational action types
- EXPEDITE/TRANSFER/COMPENSATE/NO_ACTION must NEVER be treated as supervision decisions

### Schemas that must not be redesigned

- **GovernanceOutput**: exactly 8 fields — `risk_level`, `situational_explanation`, `recommended_action`, `evidence_sources`, `cost_summary`, `confidence_note`, `rationale_trace`, `alternative_actions`
- **TwinState**: entity models, `apply_action()`, `compute_total_cost()` — all frozen
- **Case JSON structure**: `cost_ground_truth`, `oracle`, `decision_options` — all frozen
- **SupervisorDecision**: 7 fields as defined in `supervisor.py`

### Scenario delta authority

- `inject_scenario` is currently a stub (pass-through)
- When implemented, scenario `entity_patches` are the authority for state mutations
- Do not silently replace this with hardcoded state overrides

### Runtime IDs

- Entity IDs use the `_1` / `_2` system: `CR_1`, `CR_2`, `WH_1`, `WH_2`, `SUP_1`, `SUP_2`, `CZ_1`, `CZ_2`
- Candidate IDs follow patterns: `EXPEDITE_CR_1`, `TRANSFER_WH_1_to_WH_2`, `COMPENSATE`, `NO_ACTION`
- Do not introduce new ID schemes

---

## 4. Current Architecture and Flow

### Graph node sequence

```
load_case_or_scenario
    |
inject_scenario          (stub — pass-through)
    |
operations_agent_node    reads: twin_state, scenario_context
    |                    writes: operations_output
cost_agent_node          reads: twin_state, operations_output.ranked_candidates
    |                    writes: cost_output
governance_agent_node    reads: scenario_context, operations_output, cost_output
    |                    writes: governance_output, _governance_meta
supervisor_node          reads: governance_output, _governance_meta, supervisor_instruction
    |                    writes: supervisor_output, supervisor_decision, final_decision_code
evaluation_node          (stub — returns {"status": "stub", "regret": None})
    |
END
```

### GraphState fields (16 total)

```python
class GraphState(TypedDict, total=False):
    # Identity
    case_id: str
    scenario_id: str
    scenario_context: dict[str, Any]      # {scenario_type, risk_level, exception_description}

    # Twin state
    twin_state: dict[str, Any]

    # From case JSON (currently unused by pipeline)
    allowed_operational_actions: list[dict[str, Any]]

    # Agent outputs
    operations_output: dict[str, Any]     # OperationsOutput.to_dict()
    cost_output: dict[str, Any]           # CostOutput.to_dict()
    governance_output: dict[str, Any]     # GovernanceOutput.to_dict()

    # Governance identity metadata (outside frozen schema)
    _governance_meta: dict[str, Any]

    # Supervisor
    supervisor_instruction: dict[str, Any]  # injected by caller: {mode, review_focus?, target_action_label?}
    supervisor_output: dict[str, Any]       # SupervisorDecision.to_dict()

    # Legacy (backward compat — values are now APPROVE/VERIFY/OVERRIDE, not AI/ALT1/ALT2)
    supervisor_decision: str
    final_decision_code: str

    # Evaluation (stub)
    evaluation_result: dict[str, Any]

    # Audit trail
    trace_log: list[dict[str, Any]]
```

### What each agent consumes and produces

**Operations Agent** (`run_operations_agent(twin_state, scenario_context, order_units=None) -> OperationsOutput`):
- Reads: `twin_state.carriers`, `twin_state.warehouses`, `twin_state.customer_zones`
- Retrieves: 4 RAG chunks based on scenario query
- Produces: `OperationsOutput` with `ranked_candidates: list[RankedCandidate]`, each having `candidate_id`, `candidate_type`, `feasibility_score`, `feasible`, `evidence_refs`, `target_entities`

**Cost Agent** (`run_cost_agent(twin_state, candidates) -> CostOutput`):
- Reads: `twin_state` entity data + candidate list from operations
- Produces: `CostOutput` with `cost_estimates: list[CandidateCostEstimate]`, each having `direct_cost_estimate`, `recovery_cost_estimate`, `total_cost_estimate` (all `_estimate` suffix)

**Governance Agent** (`run_governance_agent_with_meta(scenario_context, ops_output, cost_output) -> tuple[GovernanceOutput, dict]`):
- Joins candidates with cost estimates
- Selects recommendation (primary: feasibility_score DESC, secondary: total_cost ASC)
- Produces: frozen 8-field `GovernanceOutput` + identity metadata dict

**Supervisor** (`run_supervisor(governance_output, governance_meta, instruction) -> SupervisorDecision`):
- Reads: governance output + meta + instruction
- Produces: `SupervisorDecision` with `supervisor_decision_type`, `selected_candidate_id`, `selected_candidate_type`, `decision_rationale`, `review_requested`, `review_focus`, `override_from_recommendation`

### Where governance meta lives

`_governance_meta` is a separate GraphState key — NOT inside the frozen 8-field GovernanceOutput. It carries:
```python
{
    "recommended_candidate_id": str,
    "recommended_candidate_type": str,
    "alternatives": [
        {"action_label": str, "candidate_id": str, "candidate_type": str},
        ...  # max 4
    ]
}
```

### What remains stubbed

- `inject_scenario` — pass-through, no entity_patches applied
- `evaluation_node` — returns `{"status": "stub", "regret": None}`

---

## 5. Deferred / TODO Items

### Deferred by design (not Week 3 scope)

| Item | Status | Notes |
|------|--------|-------|
| `inject_scenario` | Stub | Scenario entity_patches not applied; future simulation feature |
| `evaluation_node` | Stub | Regret computation, action code mapping deferred |
| Supervisor-to-evaluation bridge | Not built | Mapping APPROVE/OVERRIDE → AI/ALT1/ALT2 belongs in evaluation package |
| `allowed_operational_actions` | Loaded but unused | Operations agent generates from entities, not from case decision_options |

### Known non-blocking risks

1. **Stale GraphState comments** — lines 70–71 in `graph.py` describe `supervisor_decision` as "AI / ALT1 / ALT2" but actual values are now APPROVE/VERIFY/OVERRIDE. Documentation-only; does not affect behavior.

2. **`action_label` format coupling** — `_governance_meta.alternatives[].action_label` must match `GovernanceOutput.alternative_actions[].action_label` format. Both use `f"{candidate_type}: {description}"`. A format change in one without the other would break override target matching.

3. **Duplicate `SupervisorDecisionType` enum** — defined independently in `twin_state.py:157` and `supervisor.py:34`. Intentional isolation but creates a maintenance surface.

4. **`np.argsort` tie stability** — TF-IDF ties may resolve differently across platforms. No failure observed.

---

## 6. Week 3 Objective

### What Week 3 should do

Build a **Streamlit UI** that wraps the existing backend pipeline, enabling:

1. **Case selection and loading** — pick a case, see scenario context
2. **Governance display** — show the AI recommendation, evidence, cost summary, confidence note, alternatives
3. **Supervisor interaction** — let the human approve, request verification, or override with an alternative
4. **Decision recording** — capture the supervisor decision and display the result
5. **Trace/audit display** — show the pipeline trace log for transparency

### What should NOT be changed in Week 3

- Do not modify `twin_state.py` or `evaluation.py`
- Do not redesign the GovernanceOutput 8-field schema
- Do not change the SupervisorDecision schema
- Do not change operational candidate generation logic
- Do not change cost estimation formulas
- Do not add LLM calls to agents
- Do not change case JSON structure or oracle truth
- Do not implement the evaluation bridge (that is a separate package)
- Do not build scenario injection logic

### Minimal backend interaction pattern for UI

```python
from graph import compile_graph

graph = compile_graph()

# Run with a case and supervisor instruction
result = graph.invoke({
    "case_id": "M01",
    "supervisor_instruction": {"mode": "approve"},
    # or: {"mode": "verify", "review_focus": "Check carrier capacity."}
    # or: {"mode": "override", "target_action_label": "TRANSFER: ..."}
})

# All UI content is in the result dict:
governance = result["governance_output"]       # 8-field dict
supervisor = result["supervisor_output"]       # 7-field dict
operations = result["operations_output"]       # ranked candidates
cost = result["cost_output"]                   # cost estimates
meta = result["_governance_meta"]              # candidate identity mapping
trace = result["trace_log"]                    # audit trail
scenario = result["scenario_context"]          # scenario metadata
```

---

## 7. Week 3 Recommended Implementation Order

### Package 3A: UI skeleton + case loading

- Create `app.py` (Streamlit entry point)
- Case selector sidebar (dropdown of 20 cases)
- Load and display scenario context (scenario_type, risk_level, exception_description)
- Display twin state summary (carriers, warehouses, customer zones)
- Run the graph on case selection (initially with default APPROVE)

### Package 3B: Governance display

- Show governance recommendation panel:
  - `risk_level` as a colored badge
  - `recommended_action` as a prominent heading
  - `situational_explanation` as context paragraph
  - `cost_summary` in a cost panel
  - `confidence_note` in a confidence/uncertainty panel
  - `rationale_trace` in an expandable section
  - `evidence_sources` as a structured list
  - `alternative_actions` as a comparison table or cards

### Package 3C: Supervisor interaction wiring

- Three-button supervisor interface: Approve / Verify / Override
- Approve: re-run graph with `{"mode": "approve"}`
- Verify: show a text input for `review_focus`, re-run with `{"mode": "verify", "review_focus": "..."}`
- Override: show alternatives from `governance_output.alternative_actions`, let user pick one, re-run with `{"mode": "override", "target_action_label": "..."}`
- Display supervisor decision result panel

### Package 3D: Cost and evidence detail views

- Cost comparison table across all candidates (from `cost_output.cost_estimates`)
- Evidence detail view (from `governance_output.evidence_sources`)
- Operations candidate ranking table (from `operations_output.ranked_candidates`)

### Package 3E: Trace and audit display

- Pipeline trace log display (from `trace_log`)
- Expandable node-by-node audit trail
- Full JSON state viewer (optional, for debugging)

### Package 3F: Integration testing and polish

- Test all 3 supervisor paths through the UI
- Test with multiple cases across risk levels
- Visual polish, layout refinement
- Error handling for edge cases

---

## 8. Acceptance Criteria for Week 3 Start

### Backend capabilities the UI can rely on

| UI Need | Backend Source | Ready? |
|---------|--------------|--------|
| List of available cases | `data/cases/*.json` (20 files) | Yes |
| Scenario context display | `result["scenario_context"]` | Yes |
| Twin state summary | `result["twin_state"]` | Yes |
| Recommendation heading | `result["governance_output"]["recommended_action"]` | Yes |
| Risk level badge | `result["governance_output"]["risk_level"]` | Yes |
| Situation explanation | `result["governance_output"]["situational_explanation"]` | Yes |
| Cost summary text | `result["governance_output"]["cost_summary"]` | Yes |
| Confidence note | `result["governance_output"]["confidence_note"]` | Yes |
| Rationale trace | `result["governance_output"]["rationale_trace"]` | Yes |
| Evidence sources list | `result["governance_output"]["evidence_sources"]` | Yes |
| Alternative actions | `result["governance_output"]["alternative_actions"]` | Yes |
| Candidate cost estimates | `result["cost_output"]["cost_estimates"]` | Yes |
| Ranked candidates | `result["operations_output"]["ranked_candidates"]` | Yes |
| Supervisor decision | `result["supervisor_output"]` | Yes |
| Candidate identity map | `result["_governance_meta"]` | Yes |
| Pipeline trace | `result["trace_log"]` | Yes |
| Supervisor input | `supervisor_instruction` dict in invoke args | Yes |

### How to invoke the backend from Streamlit

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from rag_setup import build_vector_store
from graph import compile_graph

# Build RAG once at app startup
build_vector_store()

# Compile graph once
graph = compile_graph()

# Per-interaction: invoke with case_id + supervisor instruction
result = graph.invoke({
    "case_id": selected_case_id,
    "supervisor_instruction": instruction_dict,
})
```

---

## 9. Key Schema Reference for UI Development

### GovernanceOutput (8 frozen fields)

```python
{
    "risk_level": "LOW" | "MEDIUM" | "HIGH",
    "situational_explanation": str,
    "recommended_action": str,              # e.g. "COMPENSATE: Proactive customer compensation..."
    "evidence_sources": [
        {
            "source_type": str,             # "knowledge_base" | "cost_estimate" | "feasibility_check"
            "field_or_key": str,            # e.g. "exception_handling_sop.md:EH-01"
            "value": Any,
            "relevance": str
        }
    ],
    "cost_summary": str,
    "confidence_note": str,
    "rationale_trace": str,
    "alternative_actions": [
        {
            "action_label": str,            # e.g. "TRANSFER: Transfer inventory from..."
            "description": str,             # e.g. "estimated cost $60.00, feasibility 0.68"
            "estimated_risk": str           # e.g. "Lower operational risk"
        }
    ]
}
```

### SupervisorDecision (7 fields)

```python
{
    "supervisor_decision_type": "APPROVE" | "VERIFY" | "OVERRIDE",
    "selected_candidate_id": str | None,    # e.g. "COMPENSATE", "EXPEDITE_CR_1"
    "selected_candidate_type": str | None,  # e.g. "COMPENSATE", "EXPEDITE"
    "decision_rationale": str,
    "review_requested": bool,               # True only for VERIFY
    "review_focus": str,                    # non-empty only for VERIFY
    "override_from_recommendation": bool    # True only for OVERRIDE
}
```

### SupervisorInstruction (input)

```python
# APPROVE
{"mode": "approve"}

# VERIFY
{"mode": "verify", "review_focus": "Check carrier capacity constraints."}

# OVERRIDE (target_action_label should match an alternative_actions[].action_label)
{"mode": "override", "target_action_label": "TRANSFER: Transfer inventory from..."}
```

### CandidateCostEstimate (per candidate)

```python
{
    "candidate_id": str,
    "candidate_type": str,
    "is_feasible": bool,
    "direct_cost_estimate": float | None,
    "recovery_cost_estimate": float | None,
    "total_cost_estimate": float | None,
    "cost_breakdown_explanation": str,
    "estimation_notes": str
}
```

### RankedCandidate (per candidate)

```python
{
    "candidate_id": str,
    "candidate_type": str,
    "description": str,
    "feasibility_score": float,
    "feasible": bool,
    "feasibility_reason": str | None,
    "rationale": str,
    "evidence_refs": [...],
    "target_entities": {"carrier_id": str} | {"from_warehouse_id": str, "to_warehouse_id": str} | {}
}
```

---

## 10. New-Conversation Starter Prompt

Copy the block below into a new Claude Code conversation to begin Week 3 UI work:

---

````
I am continuing work on a Supply Chain Twin MVP — a thesis-aligned LangGraph-based
human-supervised supply chain twin for disruption simulation and fulfillment exception handling.

Project location: /Users/tianshi/Desktop/Generative Model Final Project/supply-chain-twin

Week 2 backend is complete and audited (699 tests passing). The full backend pipeline
runs end-to-end: case loading -> operations agent -> cost agent -> governance synthesis -> supervisor.

Read WEEK3_HANDOFF.md at the project root for the complete handoff package. It contains:
- Current backend status and architecture
- Frozen contracts that must not be changed
- All schema definitions (GovernanceOutput, SupervisorDecision, etc.)
- Graph invocation pattern for the UI
- Recommended Week 3 implementation order
- Key constraints

Week 3 objective: Build a Streamlit UI that wraps the existing backend.

Critical constraints:
- Do NOT modify src/twin_state.py, src/evaluation.py, or case JSON truth
- Do NOT redesign the frozen GovernanceOutput 8-field schema
- Do NOT change SupervisorDecision, cost estimation, or candidate generation logic
- Do NOT add LLM calls to any agent
- Do NOT implement the evaluation bridge (deferred)
- AI/ALT1/ALT2 are evaluation codes — never use them as operational action identities
- APPROVE/VERIFY/OVERRIDE are supervision decisions — never treat them as operational actions
- EXPEDITE/TRANSFER/COMPENSATE/NO_ACTION are operational candidates — the only valid candidate types

The UI must support:
1. Case selection (20 cases available)
2. Governance recommendation display (risk level, recommendation, evidence, cost, confidence, alternatives)
3. Supervisor interaction (Approve / Verify / Override buttons)
4. Decision result display
5. Pipeline trace/audit view

Start by reading WEEK3_HANDOFF.md, then inspect the current repo structure.
Then implement Package 3A: UI skeleton with case loading and basic governance display.
````

---

*End of Week 3 Handoff Package*
