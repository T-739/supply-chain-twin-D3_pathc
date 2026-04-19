"""
operations_agent.py — Deterministic Operations Agent for the supply chain twin.

Consumes twin_state context and scenario_context to produce ranked operational
action candidates from the bounded MVP action family:
  EXPEDITE, TRANSFER, COMPENSATE, NO_ACTION

This agent operates at the OPERATIONAL layer only.  It does NOT:
  - Emit AI / ALT1 / ALT2 supervision decision codes
  - Emit approve / verify_pause / alternative_plan decision types
  - Consume oracle labels or evaluation truth
  - Define or overwrite cost/evaluation truth

AI/ALT1/ALT2 are supervision-layer codes resolved by the Supervisor node.
The Operations Agent produces operational candidates that inform — but do not
replace — the supervision decision.

The output contract (OperationsOutput) is stable and JSON-serializable.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# B4 Slice 2B — single-point prompt seam for agent-visible memory.
#
# See docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §12 D1/D2/D3/D4/D5.
# The operations agent is the single experiment target (D1). The
# seam lives in ``_build_ops_llm_user_prompt`` only. The rules-mode
# path (``run_operations_agent``) never reaches the seam, so its
# byte output is unchanged under any B4 flag combination.
#
# This module consumes an already-built ``AgentMemoryContext`` from
# the caller. It does NOT call ``build_agent_memory_context(...)``
# itself (S7): when the runtime orchestrator wiring lands in a
# later slice, the caller will own the builder call. As of Slice
# 2B no caller inside this repo invokes this seam with a non-None
# context — the seam is exercised only by ``tests/test_operations
# _agent_agent_memory_seam.py``.
# ---------------------------------------------------------------------------

from agent_memory.agent_memory_config import AgentMemoryExperimentConfig
from agent_memory.agent_memory_renderer import render_agent_memory_context
from agent_memory.agent_memory_schema import AgentMemoryContext

#: Fixed section delimiters around the renderer output. Values
#: are stable under all flag combinations; renderer output itself
#: is byte-deterministic (see agent_memory_renderer tests). The
#: OFF path never emits either delimiter.
_B4_SECTION_HEADER: str = "HISTORICAL_STRUCTURED_MEMORY_CONTEXT"
_B4_SECTION_FOOTER: str = "END_HISTORICAL_STRUCTURED_MEMORY_CONTEXT"


def _b4_should_inject(
    agent_memory_context: Optional[AgentMemoryContext],
    agent_memory_config: Optional[AgentMemoryExperimentConfig],
) -> bool:
    """Return True iff the five S3 conditions hold.

    Any one of them missing → OFF path. Ordering is exhaustive
    AND; short-circuiting on ``None`` keeps the check cheap in
    the default-off case.
    """
    if agent_memory_context is None:
        return False
    if agent_memory_config is None:
        return False
    if not agent_memory_config.enable_agent_visible_memory:
        return False
    if agent_memory_config.target_agent != "operations":
        return False
    return True

# ---------------------------------------------------------------------------
# Phase 4 — Operations Agent dual-mode (rules / llm)
# ---------------------------------------------------------------------------
#
# Mode dispatch, LLM language enrichment, and forbidden-token guards live at
# the bottom of this file. The existing run_operations_agent() entry point is
# byte-identical to its pre-Phase-4 behavior; the LLM path sits beside it.

_OPS_MODE_ENV = "SUPPLY_CHAIN_TWIN_OPERATIONS_MODE"
_VALID_OPS_MODES = frozenset({"rules", "llm"})

# Tokens that MUST NEVER leak into operations candidate free-text fields.
# These are supervision / evaluation identifiers — they belong to other layers.
# AI is included as a standalone uppercase token; "AI" as a phrase in natural
# language (e.g. "AI recommends") would match \bAI\b too, so the guard is
# deliberately conservative on the operations side where there is no benign
# reason to emit any of these.
_OPS_FORBIDDEN_TOKENS_RE = None  # lazy-compiled


def _ops_forbidden_pattern():
    import re
    global _OPS_FORBIDDEN_TOKENS_RE
    if _OPS_FORBIDDEN_TOKENS_RE is None:
        _OPS_FORBIDDEN_TOKENS_RE = re.compile(
            r"\b(AI|ALT1|ALT2|APPROVE|VERIFY|OVERRIDE)\b"
        )
    return _OPS_FORBIDDEN_TOKENS_RE


def _ops_contains_forbidden_token(text: str) -> bool:
    return bool(_ops_forbidden_pattern().search(text or ""))


def _resolve_ops_mode(mode: str | None) -> str:
    """Resolve operations mode. Unknown values degrade to 'rules'."""
    import os
    cand = (mode or os.environ.get(_OPS_MODE_ENV) or "rules")
    cand = str(cand).strip().lower()
    if cand not in _VALID_OPS_MODES:
        return "rules"
    return cand


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The bounded MVP operational action family (from TwinState ActionType).
# VERIFY is intentionally excluded — it is a supervision step, not an
# operational action.
VALID_CANDIDATE_TYPES: frozenset[str] = frozenset({
    "EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION",
})

# Supervision codes that must NEVER appear as candidate_type.
_FORBIDDEN_SUPERVISION_CODES: frozenset[str] = frozenset({
    "AI", "ALT1", "ALT2",
})

# Decision types that must NEVER appear as candidate_type.
_FORBIDDEN_DECISION_TYPES: frozenset[str] = frozenset({
    "approve", "verify_pause", "alternative_plan",
})


# ---------------------------------------------------------------------------
# Output sub-schemas
# ---------------------------------------------------------------------------


class EvidenceRef(BaseModel):
    """A reference to a retrieved knowledge chunk used in reasoning."""

    chunk_id: str
    source_doc: str
    section: str
    retrieval_score: float
    excerpt: str            # first N chars of chunk text for traceability


class RankedCandidate(BaseModel):
    """A single ranked operational action candidate.

    candidate_type must be one of: EXPEDITE, TRANSFER, COMPENSATE, NO_ACTION.
    It must never be a supervision code (AI/ALT1/ALT2) or a decision type
    (approve/verify_pause/alternative_plan).
    """

    candidate_id: str               # unique id, e.g. "EXPEDITE_CR_2"
    candidate_type: str             # from VALID_CANDIDATE_TYPES
    description: str                # human-readable summary
    feasibility_score: float        # bounded [0.0, 1.0]; higher = more feasible
    feasible: bool                  # hard pass/fail from constraint checks
    feasibility_reason: str | None  # short explanation; None when feasible
    rationale: str                  # grounded explanation
    evidence_refs: list[EvidenceRef]
    target_entities: dict[str, str] # e.g. {"carrier_id": "CR_2"}

    @field_validator("feasibility_score")
    @classmethod
    def check_score_bounds(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"feasibility_score must be in [0.0, 1.0], got {v}")
        return round(v, 4)

    @field_validator("candidate_type")
    @classmethod
    def check_candidate_type(cls, v: str) -> str:
        if v in _FORBIDDEN_SUPERVISION_CODES:
            raise ValueError(
                f"candidate_type must not be a supervision code, got '{v}'. "
                f"AI/ALT1/ALT2 belong to the Supervisor layer."
            )
        if v in _FORBIDDEN_DECISION_TYPES:
            raise ValueError(
                f"candidate_type must not be a decision type, got '{v}'."
            )
        if v not in VALID_CANDIDATE_TYPES:
            raise ValueError(
                f"candidate_type must be one of {sorted(VALID_CANDIDATE_TYPES)}, got '{v}'."
            )
        return v


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------


class OperationsOutput(BaseModel):
    """Structured output contract for the Operations Agent.

    ranked_candidates are ordered by feasibility_score descending (best first).
    Only feasible candidates (feasible=True) are ranked; infeasible ones are
    listed at the end for traceability.
    """

    ranked_candidates: list[RankedCandidate]
    retrieval_query: str
    scenario_summary: str
    evidence_chunks_used: int

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Operational candidate bridge
# ---------------------------------------------------------------------------


def _resolve_order_units(twin_state: dict[str, Any], order_units: int | None) -> int:
    """Resolve effective order_units from explicit parameter or twin_state.

    Lookup order: explicit parameter > active_order.order_units > baseline default (10).
    The baseline default matches data/configs/baseline_network.json.
    """
    if order_units is not None and order_units > 0:
        return order_units
    ao = twin_state.get("active_order", {})
    if isinstance(ao, dict) and ao.get("order_units", 0) > 0:
        return int(ao["order_units"])
    return _BASELINE_ORDER_UNITS


# Baseline default matching data/configs/baseline_network.json active_order.
_BASELINE_ORDER_UNITS: int = 10


def build_operational_candidates(
    twin_state: dict[str, Any],
    order_units: int | None = None,
) -> list[dict[str, Any]]:
    """Generate bounded operational candidates from twin_state entities.

    Feasibility filtering is aligned with TwinState.apply_action() constraints:
      - EXPEDITE: carrier available AND capacity_limit >= order_units
      - TRANSFER: src inventory >= order_units AND dst headroom >= order_units
                  AND src != dst
      - COMPENSATE: always feasible
      - NO_ACTION: always feasible

    Parameters
    ----------
    twin_state:
        Serialized twin state (initial_state_snapshot or equivalent).
    order_units:
        Explicit order size. If None, resolved from twin_state.active_order
        or baseline default (10).

    Returns a list of candidate dicts, each with:
      candidate_id, candidate_type, description, feasible, feasibility_reason,
      target_entities.

    This function does NOT read oracle truth or case decision_options.
    """
    units = _resolve_order_units(twin_state, order_units)
    candidates: list[dict[str, Any]] = []

    carriers = twin_state.get("carriers", [])
    warehouses = twin_state.get("warehouses", [])
    customer_zones = twin_state.get("customer_zones", [])

    # --- EXPEDITE candidates: one per carrier ---
    for carrier in carriers:
        if not isinstance(carrier, dict):
            continue
        cid = carrier.get("id", "?")
        available = carrier.get("available", False)
        capacity = carrier.get("capacity_limit", 0)

        # Aligned with TwinState.apply_action() EXPEDITE checks:
        #   carrier must be available AND capacity_limit >= order_units
        feasible = True
        reason = None
        if not available:
            feasible = False
            reason = f"Carrier {cid} is unavailable."
        elif capacity < units:
            feasible = False
            reason = (
                f"Carrier {cid} capacity ({capacity}) "
                f"< order_units ({units})."
            )

        candidates.append({
            "candidate_id": f"EXPEDITE_{cid}",
            "candidate_type": "EXPEDITE",
            "description": (
                f"Expedite shipment via {carrier.get('name', cid)} "
                f"(transit {carrier.get('transit_time_hours', '?')}h, "
                f"${carrier.get('cost_per_unit', '?')}/unit)"
            ),
            "feasible": feasible,
            "feasibility_reason": reason,
            "target_entities": {"carrier_id": cid},
        })

    # --- TRANSFER candidates: one per warehouse pair (src→dst) ---
    for src_wh in warehouses:
        if not isinstance(src_wh, dict):
            continue
        src_id = src_wh.get("id", "?")
        src_inv = src_wh.get("current_inventory", 0)

        for dst_wh in warehouses:
            if not isinstance(dst_wh, dict):
                continue
            dst_id = dst_wh.get("id", "?")
            if src_id == dst_id:
                continue

            dst_cap = dst_wh.get("max_capacity", 0)
            dst_inv = dst_wh.get("current_inventory", 0)
            headroom = dst_cap - dst_inv

            # Aligned with TwinState.apply_action() TRANSFER checks:
            #   src.current_inventory >= order_units
            #   dst.current_inventory + order_units <= dst.max_capacity
            feasible = True
            reason = None
            if src_inv < units:
                feasible = False
                reason = (
                    f"Source {src_id} inventory ({src_inv}) "
                    f"< order_units ({units})."
                )
            elif headroom < units:
                feasible = False
                reason = (
                    f"Destination {dst_id} headroom ({headroom}) "
                    f"< order_units ({units})."
                )

            candidates.append({
                "candidate_id": f"TRANSFER_{src_id}_to_{dst_id}",
                "candidate_type": "TRANSFER",
                "description": (
                    f"Transfer inventory from {src_wh.get('name', src_id)} "
                    f"to {dst_wh.get('name', dst_id)} "
                    f"(src inv={src_inv}, dst headroom={headroom})"
                ),
                "feasible": feasible,
                "feasibility_reason": reason,
                "target_entities": {
                    "from_warehouse_id": src_id,
                    "to_warehouse_id": dst_id,
                },
            })

    # --- COMPENSATE candidate: always one ---
    zone_desc = ""
    if customer_zones:
        z = customer_zones[0] if isinstance(customer_zones, list) else None
        if z and isinstance(z, dict):
            zone_desc = (
                f" for {z.get('name', 'customer zone')} "
                f"(SLA {z.get('sla_deadline_hours', '?')}h)"
            )
    candidates.append({
        "candidate_id": "COMPENSATE",
        "candidate_type": "COMPENSATE",
        "description": f"Proactive customer compensation{zone_desc}.",
        "feasible": True,
        "feasibility_reason": None,
        "target_entities": {},
    })

    # --- NO_ACTION candidate: always one ---
    candidates.append({
        "candidate_id": "NO_ACTION",
        "candidate_type": "NO_ACTION",
        "description": "Take no operational action; monitor situation.",
        "feasible": True,
        "feasibility_reason": None,
        "target_entities": {},
    })

    return candidates


# ---------------------------------------------------------------------------
# Retrieval query builder
# ---------------------------------------------------------------------------


def _build_retrieval_query(scenario_context: dict[str, Any]) -> str:
    """Build a retrieval query string from scenario context fields."""
    parts: list[str] = []

    scenario_type = scenario_context.get("scenario_type", "")
    if scenario_type:
        parts.append(scenario_type)

    risk_level = scenario_context.get("risk_level", "")
    if risk_level:
        parts.append(f"{risk_level} risk")

    exception_desc = scenario_context.get("exception_description", "")
    if exception_desc:
        parts.append(exception_desc[:120])

    if not parts:
        return "fulfillment exception handling operational action"

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Feasibility scoring heuristics
# ---------------------------------------------------------------------------

# Signal keywords that boost or penalize specific candidate types.

_EXPEDITE_BOOST_SIGNALS: list[str] = [
    "delay", "late", "sla pressure", "breach", "transit",
    "carrier disruption", "urgent", "express",
]

_EXPEDITE_PENALTY_SIGNALS: list[str] = [
    "compliance", "documentation", "inventory discrepancy",
    "blocked", "warehouse capacity",
]

_TRANSFER_BOOST_SIGNALS: list[str] = [
    "shortage", "inventory", "stock", "discrepancy", "warehouse",
    "reallocation", "capacity", "alternative location",
]

_TRANSFER_PENALTY_SIGNALS: list[str] = [
    "carrier", "transit", "compliance", "documentation",
]

_COMPENSATE_BOOST_SIGNALS: list[str] = [
    "service failure", "customer", "compensation", "recovery",
    "confirmed breach", "high risk", "penalty",
]

_NO_ACTION_BOOST_SIGNALS: list[str] = [
    "low risk", "stable", "no abnormal", "routine", "on track",
    "no disruption", "fresh", "within sla",
]


def _count_signal_matches(text: str, signals: list[str]) -> int:
    """Count how many signal phrases appear in the text (case-insensitive)."""
    text_lower = text.lower()
    return sum(1 for s in signals if s in text_lower)


def _score_candidate(
    candidate: dict[str, Any],
    context_text: str,
    evidence_text: str,
) -> float:
    """Compute a deterministic feasibility score for an operational candidate.

    Scoring logic:
      - Infeasible candidates get 0.0
      - Base score of 0.5 for feasible candidates
      - Adjust based on signal keyword matches in context + evidence
      - Bounded to [0.0, 1.0]

    The score reflects operational fit given the scenario signals,
    not oracle truth or cost optimality.
    """
    if not candidate.get("feasible", False):
        return 0.0

    combined = context_text + " " + evidence_text
    ctype = candidate.get("candidate_type", "")
    base = 0.5

    if ctype == "EXPEDITE":
        boost = _count_signal_matches(combined, _EXPEDITE_BOOST_SIGNALS) * 0.06
        penalty = _count_signal_matches(combined, _EXPEDITE_PENALTY_SIGNALS) * 0.05
        score = base + boost - penalty

    elif ctype == "TRANSFER":
        boost = _count_signal_matches(combined, _TRANSFER_BOOST_SIGNALS) * 0.05
        penalty = _count_signal_matches(combined, _TRANSFER_PENALTY_SIGNALS) * 0.04
        score = base + boost - penalty

    elif ctype == "COMPENSATE":
        boost = _count_signal_matches(combined, _COMPENSATE_BOOST_SIGNALS) * 0.06
        penalty = 0.05  # slight base penalty — compensate is a secondary instrument
        score = base + boost - penalty

    elif ctype == "NO_ACTION":
        boost = _count_signal_matches(combined, _NO_ACTION_BOOST_SIGNALS) * 0.07
        penalty = _count_signal_matches(combined, _EXPEDITE_BOOST_SIGNALS) * 0.04
        score = base + boost - penalty

    else:
        score = base

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Rationale builder
# ---------------------------------------------------------------------------


def _build_rationale(
    candidate: dict[str, Any],
    scenario_context: dict[str, Any],
    evidence_chunks: list[dict[str, Any]],
    feasibility_score: float,
) -> str:
    """Build a grounded rationale string for a ranked candidate."""
    parts: list[str] = []

    ctype = candidate["candidate_type"]
    desc = candidate["description"]
    scenario_type = scenario_context.get("scenario_type", "unknown scenario")
    risk_level = scenario_context.get("risk_level", "unknown")

    if not candidate.get("feasible", False):
        reason = candidate.get("feasibility_reason", "Unknown constraint violation.")
        parts.append(f"{ctype} candidate '{desc}' is infeasible: {reason}")
        return " ".join(parts)

    parts.append(
        f"{ctype} candidate evaluated against "
        f"scenario '{scenario_type}' at {risk_level} risk level."
    )

    parts.append(f"Feasibility score: {feasibility_score:.2f}/1.00.")

    # Cite top evidence sources
    if evidence_chunks:
        top_sources = [
            f"{c['source_doc']}:{c['chunk_id']}" for c in evidence_chunks[:2]
        ]
        parts.append(f"Key evidence from: {', '.join(top_sources)}.")

    if ctype == "EXPEDITE":
        parts.append(
            "Expediting is indicated when delay risk is material "
            "and a feasible faster carrier option exists."
        )
    elif ctype == "TRANSFER":
        parts.append(
            "Transfer is indicated when the current source cannot fulfill "
            "reliably and another location can support fulfillment."
        )
    elif ctype == "COMPENSATE":
        parts.append(
            "Compensation is a recovery option when service failure is "
            "likely or confirmed and no operational fix fully restores the promise."
        )
    elif ctype == "NO_ACTION":
        parts.append(
            "No action is indicated when service risk is low, the current "
            "path is stable, and intervention would add unnecessary cost."
        )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _build_context_text(
    twin_state: dict[str, Any],
    scenario_context: dict[str, Any],
) -> str:
    """Flatten twin_state and scenario_context into a searchable text block."""
    parts: list[str] = []

    for key in ("scenario_type", "risk_level", "exception_description"):
        val = scenario_context.get(key, "")
        if val:
            parts.append(str(val))

    disruptions = twin_state.get("current_disruptions", [])
    for d in disruptions:
        desc = d.get("description", "")
        if desc:
            parts.append(desc)

    for carrier in twin_state.get("carriers", []):
        if isinstance(carrier, dict) and not carrier.get("available", True):
            parts.append(f"carrier {carrier.get('id', '?')} unavailable")

    return " ".join(parts) if parts else "general fulfillment exception"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


_LAST_RETRIEVAL_TRACE_SUMMARY: dict[str, Any] | None = None


def _get_last_retrieval_trace_summary() -> dict[str, Any] | None:
    """Internal accessor used by run_operations_agent_with_meta() to expose
    the retrieval trace summary without changing the frozen OperationsOutput
    schema."""
    return _LAST_RETRIEVAL_TRACE_SUMMARY


def run_operations_agent(
    twin_state: dict[str, Any],
    scenario_context: dict[str, Any],
    order_units: int | None = None,
    *,
    retrieval_mode: str | None = None,
    retrieval_k: int = 4,
) -> OperationsOutput:
    """Run the Operations Agent and produce ranked operational candidates.

    Parameters
    ----------
    twin_state:
        Serialized twin state context (initial_state_snapshot from case JSON).
    scenario_context:
        Dict with scenario_type, risk_level, exception_description.
    order_units:
        Explicit order size for feasibility checks.  If None, resolved from
        twin_state.active_order or baseline default (10).
    retrieval_mode:
        Optional. One of "tfidf_legacy" (default when None), "dense", "hybrid",
        "hybrid_rerank". Unknown values degrade to "tfidf_legacy". When the
        mode is "tfidf_legacy" (or None) the retrieval path is byte-identical
        to the pre-Phase-6 behavior.
    retrieval_k:
        Number of evidence chunks to retrieve (default 4). Ignored for the
        legacy path (which keeps k=4 for byte-identity with prior releases).

    Returns
    -------
    OperationsOutput
        Ranked operational candidates with evidence grounding.
    """
    global _LAST_RETRIEVAL_TRACE_SUMMARY
    _LAST_RETRIEVAL_TRACE_SUMMARY = None

    # --- Step 1: Build operational candidates from twin_state ---
    raw_candidates = build_operational_candidates(twin_state, order_units=order_units)

    # --- Step 2: Retrieve evidence ---
    query = _build_retrieval_query(scenario_context)

    # Default path is byte-identical to the pre-Phase-6 behavior.
    if retrieval_mode is None or str(retrieval_mode).strip().lower() == "tfidf_legacy":
        from rag_setup import build_vector_store, retrieve
        build_vector_store()  # idempotent
        evidence_chunks = retrieve(query, k=4)
        _LAST_RETRIEVAL_TRACE_SUMMARY = {
            "agent_mode": "tfidf_legacy",
            "engine_mode": "tfidf_legacy",
            "query_hash": None,
            "k": 4,
            "candidate_count": len(evidence_chunks),
            "contextualized": False,
            "reranker_used": False,
            "fallback_used": False,
            "embedder_name": None,
            "reranker_name": None,
            "error": None,
            "top_chunk_ids": [c.get("chunk_id") for c in evidence_chunks],
        }
    else:
        from retrieval import retrieve_for_agent, summarize_trace
        from rag_setup import build_vector_store
        build_vector_store()  # idempotent — needed for advanced + fallback
        evidence_chunks, trace = retrieve_for_agent(
            query, mode=retrieval_mode, k=int(retrieval_k),
        )
        _LAST_RETRIEVAL_TRACE_SUMMARY = summarize_trace(trace, str(retrieval_mode))

    # --- Step 3: Build context text for scoring ---
    context_text = _build_context_text(twin_state, scenario_context)
    evidence_text = " ".join(c["text"] for c in evidence_chunks)

    # --- Step 4: Build evidence refs ---
    evidence_refs = [
        EvidenceRef(
            chunk_id=c["chunk_id"],
            source_doc=c["source_doc"],
            section=c.get("section", ""),
            retrieval_score=c["retrieval_score"],
            excerpt=c["text"][:150],
        )
        for c in evidence_chunks
    ]

    # --- Step 5: Score and rank candidates ---
    ranked: list[RankedCandidate] = []
    for cand in raw_candidates:
        score = _score_candidate(cand, context_text, evidence_text)
        rationale = _build_rationale(
            cand, scenario_context, evidence_chunks, score,
        )
        ranked.append(
            RankedCandidate(
                candidate_id=cand["candidate_id"],
                candidate_type=cand["candidate_type"],
                description=cand["description"],
                feasibility_score=score,
                feasible=cand["feasible"],
                feasibility_reason=cand.get("feasibility_reason"),
                rationale=rationale,
                evidence_refs=evidence_refs,
                target_entities=cand.get("target_entities", {}),
            )
        )

    # Sort: feasible first (desc by score), then infeasible
    ranked.sort(key=lambda r: (-int(r.feasible), -r.feasibility_score))

    return OperationsOutput(
        ranked_candidates=ranked,
        retrieval_query=query,
        scenario_summary=(
            f"{scenario_context.get('scenario_type', 'Unknown')} | "
            f"Risk: {scenario_context.get('risk_level', 'Unknown')}"
        ),
        evidence_chunks_used=len(evidence_chunks),
    )


# ---------------------------------------------------------------------------
# Phase 4 — LLM language enrichment for the Operations Agent
# ---------------------------------------------------------------------------
#
# Policy:
#   * Candidate generation, IDs, types, feasible, feasibility_score, and
#     ranking are ALWAYS deterministic. The LLM cannot change them.
#   * Only the free-text fields `rationale` and (for infeasible candidates)
#     `feasibility_reason` may be replaced by LLM-produced text.
#   * Any provider failure / malformed JSON / validation failure / forbidden-
#     token leak → the deterministic baseline is returned unchanged.
#   * On length / id mismatch we keep baseline text per-candidate (no silent
#     reorder, no partial drift of unrelated candidates).


class _LLMCandidateEntry(BaseModel):
    candidate_id: str
    rationale: str | None = None
    feasibility_reason: str | None = None


class _LLMOpsPayload(BaseModel):
    """Validator for the LLM-produced operations enrichment payload."""

    candidates: list[_LLMCandidateEntry] = []


def _build_ops_llm_system_prompt() -> str:
    return (
        "You are the Operations Agent of a human-supervised supply chain twin. "
        "You refine natural-language fields ONLY (rationale, feasibility_reason). "
        "You must not change candidate_id, candidate_type, feasible, "
        "feasibility_score, or ordering. "
        "You must not emit the tokens AI, ALT1, ALT2, APPROVE, VERIFY, or OVERRIDE — "
        "those belong to other layers. "
        "Respond with a single JSON object; no code fences; no commentary."
    )


def _build_ops_llm_user_prompt(
    baseline: OperationsOutput,
    scenario_context: dict[str, Any],
    *,
    agent_memory_context: Optional[AgentMemoryContext] = None,
    agent_memory_config: Optional[AgentMemoryExperimentConfig] = None,
) -> str:
    import json as _json
    facts = {
        "scenario_type": scenario_context.get("scenario_type", ""),
        "risk_level": scenario_context.get("risk_level", ""),
        "exception_description": scenario_context.get("exception_description", ""),
        "candidates": [
            {
                "candidate_id": c.candidate_id,
                "candidate_type": c.candidate_type,
                "description": c.description,
                "feasible": c.feasible,
                "feasibility_score": c.feasibility_score,
                "baseline_rationale": c.rationale,
                "baseline_feasibility_reason": c.feasibility_reason,
            }
            for c in baseline.ranked_candidates
        ],
    }
    prompt = (
        "Refine the rationale (and feasibility_reason for infeasible "
        "candidates) of each operational candidate listed below. Preserve "
        "every candidate_id verbatim. Return a JSON object of this shape:\n"
        "{\n"
        '  "candidates": [\n'
        '    {"candidate_id": "<id>", "rationale": "<text>", '
        '"feasibility_reason": "<text or null>"}\n'
        "  ]\n"
        "}\n"
        "Do not introduce, remove, or reorder candidates. Do not change any "
        "numeric value or candidate_type.\n\n"
        f"Facts:\n{_json.dumps(facts, indent=2, default=str)}\n"
    )

    # B4 Slice 2B single-point injection (S3 / S4 / S5). OFF path
    # returns ``prompt`` unchanged — the whole block below is a
    # no-op unless all five S3 conditions hold.
    if _b4_should_inject(agent_memory_context, agent_memory_config):
        rendered = render_agent_memory_context(
            agent_memory_context, agent_memory_config
        )
        prompt = (
            prompt
            + "\n"
            + _B4_SECTION_HEADER
            + "\n"
            + rendered
            + "\n"
            + _B4_SECTION_FOOTER
            + "\n"
        )
    return prompt


def _deterministic_ops_fallback(baseline: OperationsOutput):
    """Return a callable fallback that reproduces baseline text, matching the
    Phase 2 gateway fallback signature (prompt, schema) -> dict."""
    payload = {
        "candidates": [
            {
                "candidate_id": c.candidate_id,
                "rationale": c.rationale,
                "feasibility_reason": c.feasibility_reason,
            }
            for c in baseline.ranked_candidates
        ],
    }

    def _fb(prompt, schema):
        return payload

    return _fb


def _enrich_ops_with_llm(
    baseline: OperationsOutput,
    scenario_context: dict[str, Any],
    *,
    gateway_config: Any = None,
    agent_memory_context: Optional[AgentMemoryContext] = None,
    agent_memory_config: Optional[AgentMemoryExperimentConfig] = None,
) -> tuple[OperationsOutput, dict[str, Any]]:
    """Run the Phase 2 gateway and return (possibly-enriched OperationsOutput,
    meta_dict). On any enrichment failure returns the baseline unchanged.

    ``agent_memory_context`` / ``agent_memory_config`` are the B4
    Slice 2B prompt-seam inputs. Both default to ``None`` and are
    a byte no-op on the enrichment meta / output shape — they only
    influence the LLM user prompt bytes when the five S3 conditions
    hold.
    """
    llm_meta: dict[str, Any] = {"enriched_fields": [], "trace": None}

    try:
        from llm_backend import generate_structured
    except Exception as exc:  # pragma: no cover
        llm_meta["trace"] = {"error": f"llm_backend import failed: {exc}"}
        return baseline, llm_meta

    system = _build_ops_llm_system_prompt()
    prompt = _build_ops_llm_user_prompt(
        baseline,
        scenario_context,
        agent_memory_context=agent_memory_context,
        agent_memory_config=agent_memory_config,
    )

    result = generate_structured(
        prompt,
        _LLMOpsPayload,
        gateway_config=gateway_config,
        deterministic_fallback=_deterministic_ops_fallback(baseline),
        system=system,
    )
    llm_meta["trace"] = (
        result.to_trace_dict() if hasattr(result, "to_trace_dict") else None
    )

    payload = result.value if result is not None else None
    if not isinstance(payload, dict):
        return baseline, llm_meta

    entries_raw = payload.get("candidates") or []
    if not isinstance(entries_raw, list):
        return baseline, llm_meta

    # Build id → entry map. Reject duplicate ids or unknown ids.
    baseline_ids = [c.candidate_id for c in baseline.ranked_candidates]
    baseline_id_set = set(baseline_ids)
    by_id: dict[str, dict] = {}
    for entry in entries_raw:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("candidate_id")
        if not isinstance(cid, str) or cid not in baseline_id_set:
            # Unknown id → reject entire payload (defence against silent drift).
            return baseline, llm_meta
        if cid in by_id:
            # Duplicate id → reject entire payload.
            return baseline, llm_meta
        by_id[cid] = entry

    # Forbidden-token guard over all enriched free text.
    enriched_text_blob_parts: list[str] = []
    for entry in by_id.values():
        for k in ("rationale", "feasibility_reason"):
            v = entry.get(k)
            if isinstance(v, str):
                enriched_text_blob_parts.append(v)
    text_blob = " ".join(enriched_text_blob_parts)
    if _ops_contains_forbidden_token(text_blob):
        llm_meta["trace"] = {
            **(llm_meta.get("trace") or {}),
            "rejected_reason": "forbidden_token_in_enriched_fields",
        }
        return baseline, llm_meta

    # Rebuild ranked_candidates — ORDER from baseline, language fields
    # optionally replaced. All deterministic fields copied verbatim.
    new_ranked: list[RankedCandidate] = []
    enriched_count = 0
    for c in baseline.ranked_candidates:
        entry = by_id.get(c.candidate_id)
        new_rationale = c.rationale
        new_reason = c.feasibility_reason

        if entry is not None:
            r = entry.get("rationale")
            if isinstance(r, str) and r.strip():
                new_rationale = r.strip()
                enriched_count += 1
            # feasibility_reason: only honor for infeasible candidates.
            # For feasible candidates the baseline reason is None and must
            # stay None (semantic contract: reason is only present on
            # constraint violation).
            if not c.feasible:
                fr = entry.get("feasibility_reason")
                if isinstance(fr, str) and fr.strip():
                    new_reason = fr.strip()

        new_ranked.append(RankedCandidate(
            candidate_id=c.candidate_id,
            candidate_type=c.candidate_type,
            description=c.description,
            feasibility_score=c.feasibility_score,
            feasible=c.feasible,
            feasibility_reason=new_reason,
            rationale=new_rationale,
            evidence_refs=list(c.evidence_refs),
            target_entities=dict(c.target_entities),
        ))

    enriched = OperationsOutput(
        ranked_candidates=new_ranked,
        retrieval_query=baseline.retrieval_query,
        scenario_summary=baseline.scenario_summary,
        evidence_chunks_used=baseline.evidence_chunks_used,
    )

    enriched_fields: list[str] = []
    if enriched_count > 0:
        enriched_fields.append("ranked_candidates.rationale")
    enriched_fields.append("ranked_candidates.feasibility_reason")
    llm_meta["enriched_fields"] = enriched_fields
    return enriched, llm_meta


def run_operations_agent_llm(
    twin_state: dict[str, Any],
    scenario_context: dict[str, Any],
    order_units: int | None = None,
    *,
    gateway_config: Any = None,
    retrieval_mode: str | None = None,
    retrieval_k: int = 4,
    agent_memory_context: Optional[AgentMemoryContext] = None,
    agent_memory_config: Optional[AgentMemoryExperimentConfig] = None,
) -> OperationsOutput:
    """Deterministic candidate generation + LLM language enrichment.

    On any enrichment failure returns the deterministic baseline unchanged.

    ``agent_memory_context`` / ``agent_memory_config`` are the B4
    Slice 2B optional prompt-seam inputs; both default to ``None``
    and preserve pre-B4 byte identity on the OFF path.
    """
    baseline = run_operations_agent(
        twin_state, scenario_context, order_units,
        retrieval_mode=retrieval_mode, retrieval_k=retrieval_k,
    )
    enriched, _ = _enrich_ops_with_llm(
        baseline, scenario_context,
        gateway_config=gateway_config,
        agent_memory_context=agent_memory_context,
        agent_memory_config=agent_memory_config,
    )
    return enriched


def run_operations_agent_modeful(
    mode: str,
    twin_state: dict[str, Any],
    scenario_context: dict[str, Any],
    order_units: int | None = None,
    *,
    gateway_config: Any = None,
    retrieval_mode: str | None = None,
    retrieval_k: int = 4,
    agent_memory_context: Optional[AgentMemoryContext] = None,
    agent_memory_config: Optional[AgentMemoryExperimentConfig] = None,
) -> OperationsOutput:
    """Entry point that dispatches by operations mode.

    Both modes return a schema-valid OperationsOutput. Unknown modes degrade
    to 'rules'.

    The ``agent_memory_*`` kwargs are the B4 Slice 2B optional
    prompt-seam inputs. They reach the prompt builder only on the
    ``llm`` branch; the ``rules`` branch ignores them entirely,
    preserving rules-mode byte identity under any B4 flag
    combination.
    """
    resolved = _resolve_ops_mode(mode)
    if resolved == "llm":
        return run_operations_agent_llm(
            twin_state, scenario_context, order_units,
            gateway_config=gateway_config,
            retrieval_mode=retrieval_mode, retrieval_k=retrieval_k,
            agent_memory_context=agent_memory_context,
            agent_memory_config=agent_memory_config,
        )
    return run_operations_agent(
        twin_state, scenario_context, order_units,
        retrieval_mode=retrieval_mode, retrieval_k=retrieval_k,
    )


def run_operations_agent_with_meta(
    twin_state: dict[str, Any],
    scenario_context: dict[str, Any],
    order_units: int | None = None,
    *,
    mode: str | None = None,
    gateway_config: Any = None,
    retrieval_mode: str | None = None,
    retrieval_k: int = 4,
    agent_memory_context: Optional[AgentMemoryContext] = None,
    agent_memory_config: Optional[AgentMemoryExperimentConfig] = None,
) -> tuple[OperationsOutput, dict[str, Any]]:
    """Run the Operations Agent and return (output, meta) for graph plumbing.

    The meta dict carries Phase 4 identity metadata outside the frozen
    OperationsOutput schema:
      - mode: "rules" | "llm"
      - llm_enriched_fields: list of enriched field paths (empty in rules mode)
      - llm_trace: LLMResult.to_trace_dict() (None in rules mode)
    """
    resolved = _resolve_ops_mode(mode)

    if resolved == "llm":
        baseline = run_operations_agent(
            twin_state, scenario_context, order_units,
            retrieval_mode=retrieval_mode, retrieval_k=retrieval_k,
        )
        retrieval_summary = _get_last_retrieval_trace_summary()
        enriched, llm_meta = _enrich_ops_with_llm(
            baseline, scenario_context,
            gateway_config=gateway_config,
            agent_memory_context=agent_memory_context,
            agent_memory_config=agent_memory_config,
        )
        meta = {
            "mode": "llm",
            "llm_enriched_fields": llm_meta.get("enriched_fields", []),
            "llm_trace": llm_meta.get("trace"),
            "retrieval": retrieval_summary,
        }
        return enriched, meta

    out = run_operations_agent(
        twin_state, scenario_context, order_units,
        retrieval_mode=retrieval_mode, retrieval_k=retrieval_k,
    )
    retrieval_summary = _get_last_retrieval_trace_summary()
    meta = {
        "mode": "rules",
        "llm_enriched_fields": [],
        "llm_trace": None,
        "retrieval": retrieval_summary,
    }
    return out, meta
