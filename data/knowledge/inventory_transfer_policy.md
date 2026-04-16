# inventory_transfer_policy.md

<!-- CHUNK: ITP-01 -->
## Purpose
Provide compact rules for cross-warehouse transfer and inventory reallocation in fulfillment exceptions.
This document helps the agent decide when transfer is feasible, when it is risky, and when review is needed.

## Scope
Applies to:
- cross-warehouse transfer
- local stock shortfall with alternative stock location
- split vs hold decisions involving inventory imbalance
- warehouse-capacity-sensitive reallocation

Does not define a network-wide inventory optimization model.

<!-- CHUNK: ITP-02 -->
## Rules / Decision Logic
1. Transfer is allowed only when it is operationally feasible.
   - The source location must have transferable inventory.
   - The destination or receiving location must be able to absorb the transfer operationally.
   - The transfer should not create a new critical shortage at the source.
   - In the MVP, source and destination must be different warehouses.

2. Use transfer when it materially improves fulfillment viability.
   - Consider transfer when the current source cannot fulfill the order reliably.
   - Consider transfer when another location can support faster or more complete fulfillment.
   - Consider transfer when it restores feasibility more cleanly than compensation-only handling.

<!-- CHUNK: ITP-03 -->
## Rules / Decision Logic
3. Transfer feasibility should be checked before ranking.
   - Confirm the source has enough inventory for the order.
   - Confirm the receiving warehouse will not exceed capacity.
   - Confirm the transfer does not depend on inventory that is known to be uncertain.
   - Do not recommend partial transfer logic unless the case explicitly supports it.

4. Do not treat transfer as free or neutral.
   - Transfer adds handling complexity and operational burden.
   - Transfer should be justified by service recovery or fulfillment continuity, not by habit.
   - Transfer is a bounded operational response, not a substitute for broader network optimization.

<!-- CHUNK: ITP-04 -->
## Rules / Decision Logic
5. Transfer and split are different decisions.
   - Transfer aims to restore feasible fulfillment using internal inventory.
   - Split shipment accepts partial fulfillment and additional coordination complexity.
   - When customer need favors complete-order delivery, transfer may be preferable to split if feasible.

6. Hold is acceptable when transfer would create larger operational risk.
   - Do not force transfer when stock accuracy is uncertain.
   - Do not force transfer when receiving capacity or warehouse execution is unstable.
   - Do not force transfer when delay reduction is unclear but source depletion risk is real.

<!-- CHUNK: ITP-05 -->
## Rules / Decision Logic
7. Inventory discrepancy requires verification before aggressive reallocation.
   - If recorded stock and trusted stock may differ, verify before committing a transfer-based recommendation.
   - Inventory uncertainty should raise confidence caution.
   - If the discrepancy leaves neither warehouse clearly feasible, escalate for review.

8. Compliance and transfer logic must remain consistent.
   - Do not use transfer to bypass a compliance restriction.
   - If transfer changes documentation or release requirements, escalate for review.

<!-- CHUNK: ITP-06 -->
## Escalation or Review Trigger
Escalate or trigger review when:
- inventory records appear inconsistent
- the source may fall below a risky operating level after transfer
- the receiving location is near operational constraint
- transfer may still fail to protect the SLA
- the decision is actually transfer vs split vs hold and the tradeoff is ambiguous
- the case combines inventory shortage with compliance or carrier disruption
- neither warehouse is clearly able to support fulfillment

<!-- CHUNK: ITP-07 -->
## Evidence Notes
- Inventory imbalance and stock discrepancy are common operational exception drivers.
- Transfer can be valuable, but only when it improves fulfillment without creating a larger downstream problem.
- Ambiguous inventory quality should reduce confidence and increase reviewability.
- Safe transfer gates can align with current runtime validation, but this document does not define authoritative transfer economics.

## Known Assumptions / MVP Simplifications
- MVP policy assumption: no formal safety-stock engine is available.
- MVP policy assumption: no network optimization model is used.
- Practice-oriented rule: avoid draining one node to solve another unless the operational logic is explicit.
- The MVP generally treats the order as a whole-unit transfer decision unless the case explicitly supports otherwise.
- This document does not define numeric transfer thresholds or lead-time truth.

<!-- CHUNK: ITP-08 -->
## Source grounding note
Mainly grounded in the project proposal bounded action set, Week 1 twin-state feasibility constraints, split-vs-hold scenario rationale, and safe implementation-facing transfer wording consistent with current warehouse/action contracts.
