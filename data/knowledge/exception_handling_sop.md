# exception_handling_sop.md

<!-- CHUNK: EH-01 -->
## Purpose
Provide a compact operating SOP for fulfillment exception handling in the MVP.
This document helps agents classify exceptions, filter infeasible actions, and produce reviewable recommendations within a bounded action set.

## Scope
Applies to bounded fulfillment exception handling only:
- shipment delay
- carrier disruption
- inventory discrepancy or shortage
- warehouse capacity or execution issue
- SLA pressure
- split vs hold decision
- compliance-related fulfillment block
- customer service recovery after a confirmed service failure

This document does not define oracle truth, numeric evaluation truth, or optimization logic.

<!-- CHUNK: EH-02 -->
## Rules / Decision Logic
1. Detect and classify the exception before proposing action.
   - Identify the primary exception type.
   - Identify whether the issue is operational, service-related, or compliance-related.
   - Record the most relevant affected entity or entities.

2. Verify the minimum facts first.
   - Confirm inventory status if stock or allocation is involved.
   - Confirm carrier availability and capacity if transport action is involved.
   - Confirm ETA or delay exposure if SLA risk is involved.
   - Confirm documentation or release status if compliance risk is involved.

3. Use a bounded action set only.
   - Allowed action families in this MVP are:
     - carrier reassignment / expediting
     - cross-warehouse transfer / inventory reallocation
     - proactive customer communication
     - proactive compensation
     - no action / monitor
   - Do not invent new strategic or optimization actions.
   - Do not recommend actions outside the predefined operational scope.

<!-- CHUNK: EH-03 -->
## Rules / Decision Logic
4. Remove infeasible actions before ranking.
   - Exclude any action that violates a hard operational constraint.
   - Exclude any action that depends on missing mandatory information.
   - Exclude any action that bypasses a compliance block.
   - Before recommending EXPEDITE, verify the target carrier is available and has enough capacity.
   - Before recommending TRANSFER, verify source inventory, destination capacity, and that source and destination are different warehouses.

5. Rank actions by risk-aware operational fit, not generic aggressiveness.
   - Prefer the least disruptive feasible action when service risk is low.
   - Prefer faster recovery actions when SLA or customer-impact risk is high.
   - Treat compliance risk and irreversible service failure as higher priority than convenience.

6. Use proactive communication when service impact is likely.
   - If delay, split shipment, or partial fulfillment is likely to affect the customer experience, include communication as a supporting recovery step.
   - Communication should clarify status, next step, and uncertainty where relevant.

<!-- CHUNK: EH-04 -->
## Rules / Decision Logic
7. Use compensation selectively.
   - Compensation is a recovery option after a likely or confirmed service failure.
   - Compensation should not substitute for resolving a preventable operational root cause.
   - Compensation should not be used to bypass compliance requirements.
   - Compensation is more appropriate when no feasible operational action can restore the service promise.

8. Prefer reviewable recommendations.
   - Every recommendation should cite the exception type, the main operational constraint, and the main service-risk logic.
   - If critical facts are uncertain, prefer a verify-oriented recommendation over forced confidence.
   - Do not present speculative assumptions as confirmed operational facts.

<!-- CHUNK: EH-05 -->
## Escalation or Review Trigger
Escalate or trigger review when:
- more than one exception type is active and the dominant driver is unclear
- inventory data appears inconsistent or unverified
- the proposed action depends on a blocked or unavailable carrier
- the issue may breach a committed SLA
- the case includes compliance or documentation uncertainty
- the recommendation relies on a major assumption rather than verified facts
- no feasible bounded action is clearly available
- the action would materially affect customer promise or irreversible shipment release

<!-- CHUNK: EH-06 -->
## Evidence Notes
- This SOP supports risk discrimination rather than generic automation.
- The recommendation should remain reviewable through explicit evidence references, rationale trace, and confidence notes.
- When uncertainty remains unresolved, the system should express that uncertainty instead of masking it.
- Safe feasibility gates from the runtime action model may be cited here, but this document is not the authority for evaluation truth.

## Known Assumptions / MVP Simplifications
- MVP policy assumption: no enterprise-wide priority score or customer-tier engine is available unless explicitly provided by the case.
- MVP policy assumption: no dynamic optimization engine is used.
- Practice-oriented rule: communication and compensation may accompany an operational action, but they do not replace feasibility checks.
- Feasibility checks are treated as pass/fail in the MVP knowledge layer.
- This document does not set numeric cost thresholds, SLA fines, or response-time guarantees.

<!-- CHUNK: EH-07 -->
## Source grounding note
Mainly grounded in the project proposal, revised thesis framing on calibrated supervision, Week 1 freeze constraints, and safe implementation-facing feasibility wording consistent with the bounded action set and TwinState action gates.
