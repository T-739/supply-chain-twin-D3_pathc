# escalation_protocol.md

<!-- CHUNK: EP-01 -->
## Purpose
Define when the system should recommend approve, verify, override review, or explicit human escalation in the MVP.
This document is designed to support calibrated supervision, uncertainty expression, and traceability-oriented governance.

## Scope
Applies to supervisor-facing review logic for fulfillment exception handling.
This document governs reviewability and intervention logic, not numeric evaluation truth.

<!-- CHUNK: EP-02 -->
## Rules / Decision Logic
1. Default to calibrated supervision, not flat control.
   - Human review should be selective and risk-sensitive.
   - The goal is not to maximize overrides; the goal is to intervene when intervention is justified.
   - Override frequency alone is not a quality metric.

2. APPROVE is appropriate when:
   - the recommended action is within the bounded action set
   - no hard constraint is violated
   - the evidence basis is clear enough for review
   - the remaining uncertainty is limited and openly stated
   - the case is not materially compliance-sensitive or irreversible

<!-- CHUNK: EP-03 -->
## Rules / Decision Logic
3. VERIFY is appropriate when:
   - key facts are missing, conflicting, or weakly supported
   - the recommendation depends on an assumption that could change the action choice
   - ETA, inventory, carrier status, or documentation status is not reliable enough
   - the case has medium-to-high service risk but the evidence is incomplete
   - additional retrieval, clarification, or cost detail is needed before decision

4. OVERRIDE review is appropriate when:
   - the proposed recommendation appears to violate a hard rule
   - stronger counter-evidence exists in the case context
   - the recommendation ignores a material compliance, feasibility, or service-risk factor
   - the human can state a reviewable reason tied to evidence, not intuition alone

<!-- CHUNK: EP-04 -->
## Rules / Decision Logic
5. Mandatory human escalation is appropriate when:
   - the case involves compliance or potential legal/regulatory violation
   - shipment release may be irreversible
   - inventory or fulfillment data appears materially inconsistent
   - a customer commitment may be broken with significant downstream consequences
   - no feasible bounded action is clearly available
   - compound disruptions make the dominant driver unclear

6. Every non-trivial review decision must remain auditable.
   - Record the trigger for review.
   - Record the evidence used.
   - Record the recommendation accepted, questioned, or rejected.
   - Record major assumptions or uncertainty notes.
   - Record the final human decision and brief rationale.

<!-- CHUNK: EP-05 -->
## Rules / Decision Logic
7. Confidence should be expressed, not hidden.
   - A recommendation can be operationally useful while still carrying a confidence caveat.
   - Lack of confidence should increase reviewability, not force automatic rejection.

8. Governance outputs should map directly to review needs.
   - risk_level should reflect case risk, not generic model self-confidence.
   - situational_explanation should explain why the case is low, medium, or high risk.
   - evidence_sources and rationale_trace should identify the main rule basis and tradeoffs.
   - confidence_note should surface unresolved assumptions and evidence limitations.

<!-- CHUNK: EP-06 -->
## Escalation or Review Trigger
Immediate escalation or structured review is required when:
- compliance, customs, or documentation risk is present
- the case combines multiple exception types
- the rationale trace is incomplete
- the risk level cannot be justified
- the case is likely HIGH risk
- the proposed action changes shipment release, customer promise, or inventory allocation materially
- the recommendation relies on weak or conflicting evidence

<!-- CHUNK: EP-07 -->
## Evidence Notes
- This protocol supports evidence-based reviewability.
- It is designed to reduce unnecessary override without suppressing necessary intervention.
- Override quality matters more than override frequency.
- Verify is a supervision step for clarification, not a new operational action type.

## Known Assumptions / MVP Simplifications
- MVP policy assumption: no separate legal or finance agent exists.
- MVP policy assumption: verify means request additional clarification or evidence, not a new operational action.
- Practice-oriented rule: high-risk or irreversible cases should be more reviewable than routine cases.
- Risk classification remains qualitative unless the case explicitly provides stronger structured evidence.
- This document does not redefine AI / ALT1 / ALT2 evaluation codes.

<!-- CHUNK: EP-08 -->
## Source grounding note
Mainly grounded in the revised thesis proposal, project proposal Governance Agent design, Week 1 frozen supervision contract, and safe implementation-facing reviewability rules consistent with the supervisor and governance workflow.
