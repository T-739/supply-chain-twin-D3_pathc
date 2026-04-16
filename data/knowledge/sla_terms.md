# sla_terms.md

<!-- CHUNK: SLA-01 -->
## Purpose
Provide a compact service-risk interpretation guide for SLA-sensitive fulfillment exceptions.
This document helps agents frame delay risk, service exposure, and recovery urgency without creating authoritative penalty truth.

## Scope
Applies to:
- late-delivery risk
- committed-date risk
- OTIF-sensitive fulfillment
- customer-facing recovery decisions after likely service failure

Does not define contractual fine truth, invoice-level penalty truth, or legal liability.

<!-- CHUNK: SLA-02 -->
## Rules / Decision Logic
1. Treat SLA as a service commitment, not only a timing variable.
   - A case may be SLA-sensitive even before a formal breach occurs.
   - Rising delay probability should be treated as rising service risk.

2. Distinguish likely breach from confirmed breach.
   - Likely breach: current signals indicate the order may miss the expected service commitment.
   - Confirmed breach: the commitment is already missed or failure is operationally unavoidable.

3. Use risk framing, not false precision.
   - LOW: no clear signal of breach and recovery path remains stable.
   - MEDIUM: some signal of delay or service degradation exists, but recovery remains feasible.
   - HIGH: breach is likely, committed service is unstable, or customer impact is immediate.

<!-- CHUNK: SLA-03 -->
## Rules / Decision Logic
4. Penalty logic may inform reasoning, but not truth.
   - The MVP uses a lateness-sensitive penalty structure in the runtime and evaluation design.
   - Agents may reason that longer lateness and larger order impact generally worsen service exposure.
   - Do not treat knowledge-base wording as the authoritative cost formula for evaluation.

5. Communication should start before the customer is surprised.
   - If service degradation is likely, proactive notice is preferred over silent waiting.
   - The notice should state what changed, what is being done, and what remains uncertain.

6. Compensation is a secondary recovery instrument.
   - Consider compensation when service failure is likely or confirmed.
   - Do not use compensation as a substitute for operational correction when a feasible correction still exists.
   - Do not use compensation to justify violating compliance or safety rules.

<!-- CHUNK: SLA-04 -->
## Rules / Decision Logic
7. Customer priority may be inferred cautiously.
   - Higher service sensitivity may justify more careful review and stronger mitigation.
   - If the case provides explicit priority, contract, or key-account context, use it.
   - If the case does not provide such context, avoid inventing customer-tier rules.

8. Split shipments increase service complexity.
   - Treat split shipment as a service-risk decision, not only a logistics decision.
   - Use split shipment more cautiously when the customer requires complete-order coordination.

9. High service-risk cases require stronger reviewability.
   - Higher SLA risk should lead to more explicit rationale, evidence, and confidence notes.
   - Avoid generic claims such as "minor delay" when the service impact is not yet verified.

<!-- CHUNK: SLA-05 -->
## Escalation or Review Trigger
Escalate or trigger review when:
- delay risk is rising but ETA confidence is weak
- more than one service commitment may be affected
- the case likely requires proactive compensation
- the shipment may be partially fulfilled or split
- the recommendation changes the customer promise materially
- the system cannot explain why the case is LOW, MEDIUM, or HIGH risk
- compensation appears to be the only feasible response to a material service failure

<!-- CHUNK: SLA-06 -->
## Evidence Notes
- OTIF and deadline pressure can materially change operational consequences.
- Customers often judge the handling of an exception, not only the exception itself.
- Service-risk framing should support calibrated intervention, not blanket escalation.
- Runtime formulas and case-level lookup truth remain outside this document's authority.

## Known Assumptions / MVP Simplifications
- MVP policy assumption: no project-specific SLA fine schedule is embedded in the knowledge base.
- MVP policy assumption: no customer-tier-specific service matrix is available unless the case explicitly provides it.
- Practice-oriented rule: proactive customer communication is generally preferred once likely service failure becomes visible.
- This document supports qualitative risk framing only.
- Any mention of lateness or penalty logic here is explanatory, not authoritative evaluation truth.

<!-- CHUNK: SLA-07 -->
## Source grounding note
Mainly grounded in the project proposal, revised thesis framing on uncertainty expression and calibrated supervision, Week 1 truth-layer separation, and safe implementation-facing SLA reasoning cues consistent with the MVP service model.
