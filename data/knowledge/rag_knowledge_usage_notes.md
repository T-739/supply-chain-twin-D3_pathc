# rag_knowledge_usage_notes.md

<!-- CHUNK: RKU-01 -->
## Purpose
Explain how the five knowledge-base markdown files should be used in the MVP RAG layer without violating Week 1 frozen contracts.

## Scope
Applies to retrieval setup, chunking, agent consumption paths, governance mapping, and guardrails between the knowledge layer and the truth/evaluation layer.

<!-- CHUNK: RKU-02 -->
## Recommended Integration Logic
1. Put the five markdown files under `data/knowledge/`.
2. Build retrieval from the markdown corpus only; do not merge case JSON, evaluation truth, or scenario delta files into the same knowledge index by default.
3. Use the explicit `CHUNK` markers as first-pass semantic chunk boundaries.
4. If a chunk is still too long for embedding or retrieval quality, split only within that chunk, not across unrelated sections.
5. Preserve source filename and chunk ID in metadata so Governance Agent can cite them in `evidence_sources`.

<!-- CHUNK: RKU-03 -->
## Operations Agent Consumption Path
Use retrieval that starts from the exception type and the bounded action under consideration.

Recommended default retrieval path:
- `exception_handling_sop.md` for general triage and bounded action discipline
- `carrier_selection_rules.md` when EXPEDITE, reassignment, or carrier feasibility is relevant
- `inventory_transfer_policy.md` when TRANSFER, reallocation, or split-vs-hold tradeoffs are relevant
- `sla_terms.md` when urgency or customer-facing service exposure is part of the reasoning

Operations Agent should use these documents to:
- filter infeasible actions
- identify hard constraints
- structure action rationales
- state uncertainty when evidence is incomplete

Operations Agent should not use these documents to:
- generate oracle truth
- redefine numeric evaluation truth
- invent new actions beyond the bounded action set

<!-- CHUNK: RKU-04 -->
## Governance Agent Consumption Path
Governance Agent should retrieve from:
- `escalation_protocol.md` for approve / verify / override review logic
- `sla_terms.md` for service-risk framing
- the action-specific rule document used by Operations Agent for the chosen recommendation

Suggested mapping to Governance output:
- `risk_level` <- escalation and SLA logic
- `situational_explanation` <- case-specific risk explanation using retrieved rules
- `recommended_action` <- action selected after Operations/Cost synthesis
- `evidence_sources` <- filename + chunk IDs + short rule labels
- `confidence_note` <- unresolved assumptions, missing evidence, or fragile feasibility
- `rationale_trace` <- ordered explanation of feasibility, service risk, and tradeoffs
- `alternative_actions` <- other bounded actions considered and why not selected

<!-- CHUNK: RKU-05 -->
## Truth-Layer and Contract Guardrails
The knowledge documents must not:
- override case JSON `cost_ground_truth`
- override case JSON `oracle`
- redefine AI / ALT1 / ALT2 supervision decision codes
- replace scenario JSON `entity_patches` as the delta authority
- act as authoritative cost formulas for evaluation.py

Safe use pattern:
- knowledge docs support recommendation logic, uncertainty expression, and reviewability
- case JSON and evaluation.py remain the only authority for evaluation truth and regret-related metrics

<!-- CHUNK: RKU-06 -->
## Chunking Notes
Recommended practice:
- first split by explicit `CHUNK` markers
- store `doc_name`, `chunk_id`, and section title in metadata
- prefer retrieving 2 to 4 rule chunks instead of one large document excerpt
- keep `Escalation or Review Trigger` chunks independently retrievable for Governance use
- keep `Known Assumptions / MVP Simplifications` retrievable so the agent can surface caveats honestly

Example retrieval intent mapping:
- `carrier unavailable` -> `CSR-02`, `CSR-03`, `EH-05`
- `inventory discrepancy transfer` -> `ITP-02`, `ITP-05`, `EH-03`
- `high SLA risk verify or override` -> `SLA-04`, `EP-03`, `EP-06`
- `compliance block` -> `CSR-02`, `EH-05`, `EP-04`

<!-- CHUNK: RKU-07 -->
## Known Assumptions / MVP Simplifications
- These docs are for a small, bounded corpus and do not assume enterprise taxonomy management.
- Retrieval is expected to support Operations and Governance first; Cost Agent may consume SLA/service logic but should still rely on deterministic cost contracts where available.
- Some implementation-facing wording was absorbed from the alternate draft only where it was consistent with current TwinState or supervisor contracts.
- Unsupported numeric thresholds from the alternate draft were intentionally excluded to avoid false authority.

<!-- CHUNK: RKU-08 -->
## Source grounding note
Grounded in the project proposal's RAG role definition, the revised thesis emphasis on calibrated supervision and traceability-oriented governance, the Week 1 freeze on truth-layer separation, and safe implementation-facing integration logic consistent with current runtime contracts.
