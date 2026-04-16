# carrier_selection_rules.md

<!-- CHUNK: CSR-01 -->
## Purpose
Provide compact carrier-selection and expediting rules for fulfillment exceptions in the MVP.
This document helps the agent reason about carrier reassignment, expediting, and no-switch decisions under disruption.

## Scope
Applies to:
- carrier delay
- carrier unavailability
- reassignment to backup carrier
- expediting under SLA pressure
- shipment release decisions affected by documentation or compliance status

Does not define lane-specific price truth, contractual carrier scorecards, or optimization logic.

<!-- CHUNK: CSR-02 -->
## Rules / Decision Logic
1. Availability is a hard gate.
   - Do not recommend a carrier that is unavailable, blocked, or operationally unusable.

2. Capacity is also a hard feasibility gate.
   - Do not recommend a carrier whose available capacity cannot cover the current order.
   - Do not assume negotiable or future capacity unless the case explicitly provides it.

3. Compliance comes before speed.
   - If shipment documentation or regulatory readiness is uncertain, do not treat a faster carrier as automatically better.
   - Do not release a shipment through an option that creates or hides a compliance problem.

<!-- CHUNK: CSR-03 -->
## Rules / Decision Logic
4. Prefer the feasible carrier that best matches service need with the lowest added disruption.
   - When service risk is modest, avoid unnecessary switching.
   - When service risk is high, consider reassignment or expediting if feasibility is verified.
   - Among feasible options, favor the one that best supports service recovery without inventing unstated assumptions.

5. Use expediting selectively.
   - Expediting is appropriate when delay risk is material and a feasible faster option exists.
   - Expediting is not preferred when the underlying issue is documentation, inventory inaccuracy, or warehouse execution failure.
   - Expediting should be described as a bounded response option, not as a default best practice.

6. Reassignment requires explicit verification.
   - Confirm the alternative carrier can actually take the shipment.
   - Confirm the switch does not create a new hidden bottleneck.
   - Confirm the action fits the current shipment status and timing.

<!-- CHUNK: CSR-04 -->
## Rules / Decision Logic
7. Waiting is acceptable only when the waiting logic is explainable.
   - Do not recommend "wait" by default.
   - Waiting should be linked to a concrete reason such as low service risk, no feasible alternative, or unresolved but material uncertainty.

8. Regulated or cross-border shipments require stricter review.
   - Carrier choice should remain secondary to documentation and release-readiness.
   - Use stronger evidence notes when the shipment may face customs or trade-compliance friction.

9. No speculative carrier assumptions.
   - Do not predict future carrier availability changes.
   - Do not assume hidden backup capacity, hidden service upgrades, or unstated contractual priority.

<!-- CHUNK: CSR-05 -->
## Escalation or Review Trigger
Escalate or trigger review when:
- the primary carrier is unavailable or severely delayed
- the alternative carrier is faster but unverified
- the case is cross-border or compliance-sensitive
- the recommendation depends on a mode switch or exceptional expedite logic
- the service promise is at risk but no clearly feasible carrier option exists
- multiple carrier-related facts conflict
- no compliant carrier is clearly available

<!-- CHUNK: CSR-06 -->
## Evidence Notes
- Carrier disruption is a common and operationally meaningful exception class.
- Reassignment and expediting should be treated as bounded response options, not automatic best practices.
- Recommendations should state the main carrier constraint, the main service-risk logic, and any unresolved assumption.
- Feasibility gates here are safe to align with runtime action validation, but price and evaluation truth remain external to this document.

## Known Assumptions / MVP Simplifications
- MVP policy assumption: no lane-level carrier scorecard is available.
- MVP policy assumption: carrier comparison is qualitative unless explicit state data is provided.
- Practice-oriented rule: backup carrier use is reasonable when primary capacity or reliability fails, but must still pass feasibility checks.
- No multi-carrier or multi-leg routing is modeled in the MVP knowledge layer.
- This document does not create a numeric carrier ranking model.

<!-- CHUNK: CSR-07 -->
## Source grounding note
Mainly grounded in the project proposal bounded action set, Week 1 twin-state carrier attributes, carrier disruption scenario logic, and safe implementation-facing feasibility wording consistent with current state/action contracts.
