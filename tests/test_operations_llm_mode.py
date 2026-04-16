"""Phase 4 tests — Operations Agent dual-mode (rules vs llm).

No live API. LLM behavior is injected via llm_backend.register_provider().
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

import llm_backend  # noqa: F401
from agents.operations_agent import (
    OperationsOutput,
    RankedCandidate,
    run_operations_agent,
    run_operations_agent_llm,
    run_operations_agent_modeful,
    run_operations_agent_with_meta,
)
from llm_backend import GatewayConfig, ProviderConfig, register_provider
from llm_providers import ProviderCallError


# ---------------------------------------------------------------------------
# Shared fixtures — minimal twin_state + scenario so RAG still works
# ---------------------------------------------------------------------------

def _twin_state() -> dict:
    return {
        "active_order": {"order_units": 10},
        "carriers": [
            {"id": "CR_1", "name": "CR_1", "available": True,
             "capacity_limit": 50, "transit_time_hours": 24,
             "cost_per_unit": 10},
            {"id": "CR_2", "name": "CR_2", "available": True,
             "capacity_limit": 30, "transit_time_hours": 12,
             "cost_per_unit": 15},
        ],
        "warehouses": [
            {"id": "WH_1", "name": "WH_1",
             "current_inventory": 40, "max_capacity": 100},
            {"id": "WH_2", "name": "WH_2",
             "current_inventory": 20, "max_capacity": 80},
        ],
        "customer_zones": [
            {"id": "Z_1", "name": "Z_1", "sla_deadline_hours": 48},
        ],
        "current_disruptions": [
            {"description": "Carrier CR_1 delayed on regional route"}
        ],
    }


def _scenario() -> dict:
    return {
        "scenario_type": "Carrier Capacity Shortage",
        "risk_level": "MEDIUM",
        "exception_description": "Carrier capacity constraints force a retiming decision.",
    }


def _auto_gateway(providers=("primary",), retries=1):
    return GatewayConfig(
        providers=tuple(
            ProviderConfig(name=p, model=f"{p}-model") for p in providers
        ),
        max_retries_per_provider=retries,
        force_mode="auto",
    )


def _fake(responses, log):
    it = iter(responses)

    def _adapter(prompt, model, temperature, max_tokens, timeout_s,
                 system=None, api_key_env=None):
        log.append({"prompt": prompt, "system": system})
        nxt = next(it)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt, {"provider": "fake", "model": model, "latency_ms": 1}

    return _adapter


def _payload_from_baseline(baseline: OperationsOutput,
                           rationale_override: str = "LLM rationale",
                           reason_override: str = "LLM reason",
                           only_ids=None) -> str:
    """Build a JSON payload enriching every baseline candidate (or only those
    in `only_ids`) with predictable text."""
    entries = []
    for c in baseline.ranked_candidates:
        if only_ids is not None and c.candidate_id not in only_ids:
            continue
        entry = {
            "candidate_id": c.candidate_id,
            "rationale": rationale_override,
            "feasibility_reason": reason_override,
        }
        entries.append(entry)
    return json.dumps({"candidates": entries})


# ---------------------------------------------------------------------------
# Rules mode unchanged
# ---------------------------------------------------------------------------

def test_rules_mode_byte_identical_to_direct_call():
    direct = run_operations_agent(_twin_state(), _scenario())
    modeful, meta = run_operations_agent_with_meta(
        _twin_state(), _scenario(), mode="rules",
    )
    assert direct.to_dict() == modeful.to_dict()
    assert meta["mode"] == "rules"
    assert meta["llm_enriched_fields"] == []
    assert meta["llm_trace"] is None


def test_default_mode_is_rules():
    direct = run_operations_agent(_twin_state(), _scenario())
    default, meta = run_operations_agent_with_meta(_twin_state(), _scenario())
    assert default.to_dict() == direct.to_dict()
    assert meta["mode"] == "rules"


def test_modeful_dispatch_unknown_mode_degrades_to_rules():
    direct = run_operations_agent(_twin_state(), _scenario())
    out = run_operations_agent_modeful("nonsense", _twin_state(), _scenario())
    assert out.to_dict() == direct.to_dict()


# ---------------------------------------------------------------------------
# LLM mode — deterministic fields preserved
# ---------------------------------------------------------------------------

def _compare_deterministic_fields(rules: OperationsOutput,
                                  llm: OperationsOutput):
    """Helper: assert that every deterministic field is identical
    (candidate_id/type/feasible/score/description/ordering/evidence/targets)."""
    assert len(rules.ranked_candidates) == len(llm.ranked_candidates)
    for r, l in zip(rules.ranked_candidates, llm.ranked_candidates):
        assert r.candidate_id == l.candidate_id
        assert r.candidate_type == l.candidate_type
        assert r.feasible == l.feasible
        assert r.feasibility_score == l.feasibility_score
        assert r.description == l.description
        assert r.target_entities == l.target_entities
        assert [e.model_dump() for e in r.evidence_refs] == \
               [e.model_dump() for e in l.evidence_refs]
    assert rules.retrieval_query == llm.retrieval_query
    assert rules.scenario_summary == llm.scenario_summary
    assert rules.evidence_chunks_used == llm.evidence_chunks_used


def test_llm_mode_preserves_ids_types_feasibility_scores_and_order():
    rules_out = run_operations_agent(_twin_state(), _scenario())
    payload = _payload_from_baseline(rules_out)

    calls: list = []
    register_provider("primary", _fake([payload], calls))

    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(),
    )
    _compare_deterministic_fields(rules_out, llm_out)


def test_llm_mode_replaces_rationale_text_only():
    rules_out = run_operations_agent(_twin_state(), _scenario())
    payload = _payload_from_baseline(
        rules_out, rationale_override="Refined rationale.",
    )
    calls: list = []
    register_provider("primary", _fake([payload], calls))

    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(),
    )
    # Every feasible candidate: rationale replaced.
    for c in llm_out.ranked_candidates:
        assert c.rationale == "Refined rationale."


def test_llm_mode_feasibility_reason_stays_none_for_feasible_candidates():
    """LLM must not inject a feasibility_reason string on a feasible candidate —
    the semantic contract is: reason is only present on constraint violation."""
    rules_out = run_operations_agent(_twin_state(), _scenario())
    payload = _payload_from_baseline(
        rules_out, reason_override="LLM invented reason",
    )
    calls: list = []
    register_provider("primary", _fake([payload], calls))

    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(),
    )
    for r_c, l_c in zip(rules_out.ranked_candidates, llm_out.ranked_candidates):
        if r_c.feasible:
            # Baseline None → must stay None.
            assert l_c.feasibility_reason is None
        else:
            # Infeasible candidates CAN carry LLM reason text.
            assert l_c.feasibility_reason == "LLM invented reason"


def test_llm_mode_partial_coverage_keeps_baseline_for_missing_ids():
    rules_out = run_operations_agent(_twin_state(), _scenario())
    first_id = rules_out.ranked_candidates[0].candidate_id
    payload = _payload_from_baseline(
        rules_out, rationale_override="Only first is enriched",
        only_ids={first_id},
    )
    calls: list = []
    register_provider("primary", _fake([payload], calls))

    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(),
    )
    for r_c, l_c in zip(rules_out.ranked_candidates, llm_out.ranked_candidates):
        if l_c.candidate_id == first_id:
            assert l_c.rationale == "Only first is enriched"
        else:
            # All other candidates keep their deterministic rationale.
            assert l_c.rationale == r_c.rationale


# ---------------------------------------------------------------------------
# Candidate-set invariants
# ---------------------------------------------------------------------------

def test_llm_mode_rejects_unknown_candidate_id_and_falls_back():
    rules_out = run_operations_agent(_twin_state(), _scenario())
    # Append a fake extra candidate — must trigger whole-payload rejection.
    entries = [
        {"candidate_id": c.candidate_id, "rationale": "llm",
         "feasibility_reason": "llm"}
        for c in rules_out.ranked_candidates
    ]
    entries.append({"candidate_id": "GHOST_CANDIDATE",
                    "rationale": "I do not exist", "feasibility_reason": None})
    payload = json.dumps({"candidates": entries})

    calls: list = []
    register_provider("primary", _fake([payload], calls))

    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(),
    )
    assert llm_out.to_dict() == rules_out.to_dict()


def test_llm_mode_rejects_duplicate_candidate_id_and_falls_back():
    rules_out = run_operations_agent(_twin_state(), _scenario())
    first_id = rules_out.ranked_candidates[0].candidate_id
    payload = json.dumps({
        "candidates": [
            {"candidate_id": first_id, "rationale": "a",
             "feasibility_reason": None},
            {"candidate_id": first_id, "rationale": "b",
             "feasibility_reason": None},
        ],
    })
    calls: list = []
    register_provider("primary", _fake([payload], calls))

    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(),
    )
    assert llm_out.to_dict() == rules_out.to_dict()


def test_llm_mode_does_not_change_candidate_count_or_order():
    rules_out = run_operations_agent(_twin_state(), _scenario())
    # Payload with entries in reverse order — must not rearrange output.
    entries = [
        {"candidate_id": c.candidate_id, "rationale": f"r-{c.candidate_id}",
         "feasibility_reason": None}
        for c in reversed(rules_out.ranked_candidates)
    ]
    payload = json.dumps({"candidates": entries})
    calls: list = []
    register_provider("primary", _fake([payload], calls))

    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(),
    )
    # Same length, same id order.
    assert [c.candidate_id for c in llm_out.ranked_candidates] == \
           [c.candidate_id for c in rules_out.ranked_candidates]
    # And rationale was still applied — but by id, not by position.
    for c in llm_out.ranked_candidates:
        assert c.rationale == f"r-{c.candidate_id}"


# ---------------------------------------------------------------------------
# Forbidden-token guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", ["AI", "ALT1", "ALT2", "APPROVE",
                                   "VERIFY", "OVERRIDE"])
def test_forbidden_token_in_rationale_falls_back_to_rules(token):
    rules_out = run_operations_agent(_twin_state(), _scenario())
    first_id = rules_out.ranked_candidates[0].candidate_id
    entries = [
        {"candidate_id": c.candidate_id,
         "rationale": (f"Recommended decision is {token}."
                       if c.candidate_id == first_id
                       else "ok"),
         "feasibility_reason": None}
        for c in rules_out.ranked_candidates
    ]
    payload = json.dumps({"candidates": entries})
    calls: list = []
    register_provider("primary", _fake([payload], calls))

    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(),
    )
    assert llm_out.to_dict() == rules_out.to_dict()


# ---------------------------------------------------------------------------
# Failure fallback
# ---------------------------------------------------------------------------

def test_provider_failure_falls_back_to_rules_mode():
    rules_out = run_operations_agent(_twin_state(), _scenario())
    calls: list = []
    register_provider("primary", _fake(
        [ProviderCallError("boom"), ProviderCallError("boom2")], calls,
    ))
    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(retries=2),
    )
    assert llm_out.to_dict() == rules_out.to_dict()


def test_malformed_json_falls_back_without_crash():
    rules_out = run_operations_agent(_twin_state(), _scenario())
    calls: list = []
    register_provider("primary", _fake(
        ["<<< not json >>>", "still not json"], calls,
    ))
    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(retries=2),
    )
    assert llm_out.to_dict() == rules_out.to_dict()


def test_global_off_mode_skips_provider_calls():
    calls: list = []
    register_provider("primary", _fake(
        ['{"candidates":[]}'], calls,
    ))
    gw = GatewayConfig(
        providers=(ProviderConfig(name="primary", model="m"),),
        max_retries_per_provider=1,
        force_mode="off",
    )
    rules_out = run_operations_agent(_twin_state(), _scenario())
    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=gw,
    )
    # off mode skips provider; deterministic fallback returns baseline text.
    assert llm_out.to_dict() == rules_out.to_dict()
    assert calls == []


# ---------------------------------------------------------------------------
# Graph plumbing
# ---------------------------------------------------------------------------

def test_graph_default_is_rules_mode_for_operations():
    from graph import compile_graph
    graph = compile_graph()
    result = graph.invoke({
        "case_id": "M01",
        "supervisor_instruction": {"mode": "approve"},
    })
    ops_entries = [
        e for e in result.get("trace_log", [])
        if e.get("node") == "operations_agent"
    ]
    assert ops_entries and ops_entries[0].get("operations_mode") == "rules"


def test_graph_llm_mode_preserves_candidate_skeleton():
    from graph import compile_graph
    graph = compile_graph()

    # First run rules mode to capture the baseline candidate skeleton.
    rules_result = graph.invoke({
        "case_id": "M01",
        "supervisor_instruction": {"mode": "approve"},
    })
    rules_ops = rules_result["operations_output"]

    # Build an LLM payload that matches the baseline ids from the real case.
    entries = [
        {"candidate_id": c["candidate_id"],
         "rationale": "LLM rationale for M01",
         "feasibility_reason": "LLM reason text"}
        for c in rules_ops["ranked_candidates"]
    ]
    payload = json.dumps({"candidates": entries})
    calls: list = []
    register_provider("primary", _fake([payload], calls))

    llm_result = graph.invoke({
        "case_id": "M01",
        "supervisor_instruction": {"mode": "approve"},
        "operations_mode": "llm",
        "operations_gateway_config": _auto_gateway(),
    })
    llm_ops = llm_result["operations_output"]

    # Deterministic fields equal across modes.
    rules_ids = [c["candidate_id"] for c in rules_ops["ranked_candidates"]]
    llm_ids = [c["candidate_id"] for c in llm_ops["ranked_candidates"]]
    assert rules_ids == llm_ids

    for r_c, l_c in zip(rules_ops["ranked_candidates"],
                        llm_ops["ranked_candidates"]):
        assert r_c["candidate_type"] == l_c["candidate_type"]
        assert r_c["feasible"] == l_c["feasible"]
        assert r_c["feasibility_score"] == l_c["feasibility_score"]
        assert r_c["description"] == l_c["description"]
        assert r_c["target_entities"] == l_c["target_entities"]

    # Meta + trace carry mode=llm.
    assert llm_result["_operations_meta"]["mode"] == "llm"
    ops_entries = [
        e for e in llm_result.get("trace_log", [])
        if e.get("node") == "operations_agent"
    ]
    assert ops_entries and ops_entries[0].get("operations_mode") == "llm"


def test_graph_llm_mode_on_provider_failure_falls_back_cleanly():
    from graph import compile_graph
    calls: list = []
    register_provider("primary", _fake(
        [ProviderCallError("boom"), ProviderCallError("boom2")], calls,
    ))
    graph = compile_graph()

    rules_result = graph.invoke({
        "case_id": "M01",
        "supervisor_instruction": {"mode": "approve"},
    })
    llm_result = graph.invoke({
        "case_id": "M01",
        "supervisor_instruction": {"mode": "approve"},
        "operations_mode": "llm",
        "operations_gateway_config": _auto_gateway(retries=2),
    })
    assert llm_result["operations_output"] == rules_result["operations_output"]
    # Meta still records attempted mode.
    assert llm_result["_operations_meta"]["mode"] == "llm"


# ---------------------------------------------------------------------------
# Layer separation — candidate_type never takes supervision/eval identifiers
# ---------------------------------------------------------------------------

def test_llm_cannot_change_candidate_type_via_payload():
    """Even if the LLM fabricates a different candidate_type in its payload,
    the output schema only accepts candidate_type from baseline (we never
    pipe it into RankedCandidate construction)."""
    rules_out = run_operations_agent(_twin_state(), _scenario())
    # Payload embeds a bogus candidate_type; our enricher ignores it.
    entries = [
        {"candidate_id": c.candidate_id, "rationale": "text",
         "feasibility_reason": None, "candidate_type": "AI"}
        for c in rules_out.ranked_candidates
    ]
    payload = json.dumps({"candidates": entries})
    calls: list = []
    register_provider("primary", _fake([payload], calls))

    llm_out = run_operations_agent_llm(
        _twin_state(), _scenario(), gateway_config=_auto_gateway(),
    )
    for r_c, l_c in zip(rules_out.ranked_candidates, llm_out.ranked_candidates):
        assert l_c.candidate_type == r_c.candidate_type
        # No supervision code leaked.
        assert l_c.candidate_type in {"EXPEDITE", "TRANSFER",
                                      "COMPENSATE", "NO_ACTION"}
