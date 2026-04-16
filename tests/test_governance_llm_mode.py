"""Phase 3 tests — Governance Agent dual-mode (rules vs llm).

No live API. LLM behavior is injected via llm_backend.register_provider().
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

import llm_backend
from agents.governance_agent import (
    GovernanceOutput,
    run_governance_agent,
    run_governance_agent_llm,
    run_governance_agent_modeful,
    run_governance_agent_with_meta,
)
from llm_backend import GatewayConfig, ProviderConfig, register_provider
from llm_providers import ProviderCallError


# -------------------------------------------------------------------------
# Minimal synthetic ops + cost inputs — avoids RAG/case dependencies
# -------------------------------------------------------------------------

def _ops() -> dict:
    return {
        "ranked_candidates": [
            {
                "candidate_id": "C1",
                "candidate_type": "EXPEDITE",
                "description": "Expedite via CR_2",
                "feasibility_score": 0.85,
                "feasible": True,
                "rationale": "Capacity available and SLA tight",
                "evidence_refs": [
                    {"source_doc": "policy.md", "chunk_id": "p1",
                     "section": "Expedite", "excerpt": "Expedite allowed under SLA risk."}
                ],
            },
            {
                "candidate_id": "C2",
                "candidate_type": "TRANSFER",
                "description": "Transfer from WH_2",
                "feasibility_score": 0.55,
                "feasible": True,
                "rationale": "Reserve stock available",
                "evidence_refs": [],
            },
            {
                "candidate_id": "C3",
                "candidate_type": "NO_ACTION",
                "description": "Hold and monitor",
                "feasibility_score": 0.30,
                "feasible": False,
                "feasibility_reason": "Below SLA threshold",
                "rationale": "Not viable",
                "evidence_refs": [],
            },
        ],
    }


def _cost() -> dict:
    return {
        "cost_estimates": [
            {"candidate_id": "C1", "candidate_type": "EXPEDITE",
             "is_feasible": True,
             "direct_cost_estimate": 150.0, "recovery_cost_estimate": 30.0,
             "total_cost_estimate": 180.0,
             "cost_breakdown_explanation": "Express carrier premium"},
            {"candidate_id": "C2", "candidate_type": "TRANSFER",
             "is_feasible": True,
             "direct_cost_estimate": 90.0, "recovery_cost_estimate": 60.0,
             "total_cost_estimate": 150.0,
             "cost_breakdown_explanation": "Reserve WH operating cost"},
            {"candidate_id": "C3", "candidate_type": "NO_ACTION",
             "is_feasible": False,
             "direct_cost_estimate": None, "recovery_cost_estimate": None,
             "total_cost_estimate": None,
             "cost_breakdown_explanation": ""},
        ],
    }


def _scenario() -> dict:
    return {
        "scenario_type": "Carrier Capacity Shortage",
        "risk_level": "MEDIUM",
        "exception_description": "Carrier CR_1 unavailable for the next window.",
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


# -------------------------------------------------------------------------
# Rules-mode unchanged
# -------------------------------------------------------------------------

def test_rules_mode_unchanged_vs_direct_call():
    """run_governance_agent_with_meta(mode='rules') must produce the same
    GovernanceOutput as the legacy direct run_governance_agent()."""
    direct = run_governance_agent(_scenario(), _ops(), _cost())
    modeful, meta = run_governance_agent_with_meta(
        _scenario(), _ops(), _cost(), mode="rules",
    )
    assert direct.to_dict() == modeful.to_dict()
    assert meta["mode"] == "rules"
    assert meta["llm_enriched_fields"] == []
    assert meta["llm_trace"] is None


def test_default_mode_is_rules():
    _direct = run_governance_agent(_scenario(), _ops(), _cost())
    default, meta = run_governance_agent_with_meta(_scenario(), _ops(), _cost())
    assert default.to_dict() == _direct.to_dict()
    assert meta["mode"] == "rules"


# -------------------------------------------------------------------------
# LLM mode — schema valid, recommended_action preserved
# -------------------------------------------------------------------------

def test_llm_mode_returns_schema_valid_governance_output():
    calls: list = []
    good_payload = (
        '{"situational_explanation": "Refined scenario narrative.",'
        ' "confidence_note": "Calibrated confidence note.",'
        ' "rationale_trace": "Refined rationale trace.",'
        ' "cost_summary": "Refined cost summary.",'
        ' "alternative_descriptions": ["alt-a", "alt-b"]}'
    )
    register_provider("primary", _fake([good_payload], calls))

    enriched = run_governance_agent_llm(
        _scenario(), _ops(), _cost(),
        gateway_config=_auto_gateway(),
    )
    # Still a valid GovernanceOutput against the frozen schema.
    assert isinstance(enriched, GovernanceOutput)
    # Language fields replaced.
    assert enriched.situational_explanation == "Refined scenario narrative."
    assert enriched.confidence_note == "Calibrated confidence note."
    assert enriched.rationale_trace == "Refined rationale trace."
    assert enriched.cost_summary == "Refined cost summary."


def test_llm_mode_does_not_change_recommended_action_or_risk():
    """Deterministic inputs → recommended_action and risk_level identical
    between rules and llm modes."""
    calls: list = []
    good_payload = (
        '{"situational_explanation": "x",'
        ' "confidence_note": "y",'
        ' "rationale_trace": "z",'
        ' "cost_summary": "w",'
        ' "alternative_descriptions": ["a", "b"]}'
    )
    register_provider("primary", _fake([good_payload], calls))

    rules_out, _ = run_governance_agent_with_meta(
        _scenario(), _ops(), _cost(), mode="rules",
    )
    llm_out, meta = run_governance_agent_with_meta(
        _scenario(), _ops(), _cost(),
        mode="llm", gateway_config=_auto_gateway(),
    )
    assert llm_out.recommended_action == rules_out.recommended_action
    assert llm_out.risk_level == rules_out.risk_level
    # Evidence sources are deterministic — compare by dict.
    assert [e.model_dump() for e in llm_out.evidence_sources] == \
           [e.model_dump() for e in rules_out.evidence_sources]
    # Alternative action_labels and estimated_risk must match rules mode.
    assert [a.action_label for a in llm_out.alternative_actions] == \
           [a.action_label for a in rules_out.alternative_actions]
    assert [a.estimated_risk for a in llm_out.alternative_actions] == \
           [a.estimated_risk for a in rules_out.alternative_actions]
    # Meta trace available for graph logging.
    assert meta["mode"] == "llm"
    assert "situational_explanation" in meta["llm_enriched_fields"]
    assert meta["llm_trace"] is not None


def test_llm_mode_preserves_alternative_descriptions_when_length_mismatch():
    """If LLM returns a mismatched alternative_descriptions length, baseline
    descriptions must be preserved (no silent reorder)."""
    calls: list = []
    rules_out, _ = run_governance_agent_with_meta(
        _scenario(), _ops(), _cost(), mode="rules",
    )
    # Only 1 description returned, but baseline has >=2 alternatives.
    mismatched = (
        '{"situational_explanation": "x",'
        ' "confidence_note": "y",'
        ' "rationale_trace": "z",'
        ' "cost_summary": "w",'
        ' "alternative_descriptions": ["only one"]}'
    )
    register_provider("primary", _fake([mismatched], calls))
    enriched = run_governance_agent_llm(
        _scenario(), _ops(), _cost(),
        gateway_config=_auto_gateway(),
    )
    # Baseline alt descriptions unchanged.
    assert [a.description for a in enriched.alternative_actions] == \
           [a.description for a in rules_out.alternative_actions]


# -------------------------------------------------------------------------
# Forbidden-token guard
# -------------------------------------------------------------------------

def test_forbidden_tokens_cause_fallback_to_rules():
    calls: list = []
    # Contains 'ALT2' as a standalone token — must be rejected.
    bad_payload = (
        '{"situational_explanation": "This explanation mentions ALT2 directly.",'
        ' "confidence_note": "c",'
        ' "rationale_trace": "r",'
        ' "cost_summary": "s",'
        ' "alternative_descriptions": ["a", "b"]}'
    )
    register_provider("primary", _fake([bad_payload], calls))

    rules_out = run_governance_agent(_scenario(), _ops(), _cost())
    enriched = run_governance_agent_llm(
        _scenario(), _ops(), _cost(),
        gateway_config=_auto_gateway(),
    )
    # Must fall back to the deterministic text.
    assert enriched.to_dict() == rules_out.to_dict()


def test_ai_token_in_free_text_is_allowed():
    """'AI' as a word in natural language is not a layer-identifier leak."""
    calls: list = []
    ok_payload = (
        '{"situational_explanation": "AI recommends expediting the shipment.",'
        ' "confidence_note": "c",'
        ' "rationale_trace": "r",'
        ' "cost_summary": "s",'
        ' "alternative_descriptions": ["a", "b"]}'
    )
    register_provider("primary", _fake([ok_payload], calls))
    enriched = run_governance_agent_llm(
        _scenario(), _ops(), _cost(),
        gateway_config=_auto_gateway(),
    )
    assert "AI recommends" in enriched.situational_explanation


# -------------------------------------------------------------------------
# Failure fallback
# -------------------------------------------------------------------------

def test_provider_failure_falls_back_to_rules_mode():
    calls: list = []
    register_provider("primary", _fake(
        [ProviderCallError("boom"), ProviderCallError("boom2")], calls,
    ))
    rules_out = run_governance_agent(_scenario(), _ops(), _cost())
    enriched = run_governance_agent_llm(
        _scenario(), _ops(), _cost(),
        gateway_config=_auto_gateway(retries=2),
    )
    assert enriched.to_dict() == rules_out.to_dict()


def test_malformed_json_falls_back_without_crash():
    calls: list = []
    register_provider("primary", _fake(
        ["<<< not json >>>", "still not json"], calls,
    ))
    rules_out = run_governance_agent(_scenario(), _ops(), _cost())
    enriched = run_governance_agent_llm(
        _scenario(), _ops(), _cost(),
        gateway_config=_auto_gateway(retries=2),
    )
    # Fallback to the deterministic baseline — no crash.
    assert enriched.to_dict() == rules_out.to_dict()


def test_global_off_mode_skips_provider_calls():
    """When SUPPLY_CHAIN_TWIN_LLM_MODE is unset, gateway still works via
    its own fallback path (deterministic language = baseline)."""
    calls: list = []
    register_provider("primary", _fake(
        ['{"situational_explanation":"unused","confidence_note":"u",'
         '"rationale_trace":"u","cost_summary":"u",'
         '"alternative_descriptions":["u","u"]}'], calls,
    ))
    # No force_mode → will use env, which defaults to "off".
    gw = GatewayConfig(
        providers=(ProviderConfig(name="primary", model="m"),),
        max_retries_per_provider=1,
        force_mode="off",
    )
    rules_out = run_governance_agent(_scenario(), _ops(), _cost())
    enriched = run_governance_agent_llm(
        _scenario(), _ops(), _cost(), gateway_config=gw,
    )
    assert enriched.to_dict() == rules_out.to_dict()
    assert calls == []


# -------------------------------------------------------------------------
# Layer separation
# -------------------------------------------------------------------------

def test_recommended_action_never_contains_supervision_codes():
    calls: list = []
    good_payload = (
        '{"situational_explanation":"AI recommends X.",'
        ' "confidence_note":"c","rationale_trace":"r",'
        ' "cost_summary":"s","alternative_descriptions":["a","b"]}'
    )
    register_provider("primary", _fake([good_payload], calls))
    enriched = run_governance_agent_llm(
        _scenario(), _ops(), _cost(),
        gateway_config=_auto_gateway(),
    )
    for forbidden in ("ALT1", "ALT2"):
        assert forbidden not in enriched.recommended_action


def test_modeful_dispatch_unknown_mode_degrades_to_rules():
    rules_out = run_governance_agent(_scenario(), _ops(), _cost())
    out = run_governance_agent_modeful(
        "nonsense", _scenario(), _ops(), _cost(),
    )
    assert out.to_dict() == rules_out.to_dict()


# -------------------------------------------------------------------------
# Graph plumbing
# -------------------------------------------------------------------------

def test_graph_default_is_rules_mode_and_unchanged():
    """Running the compiled graph without governance_mode should be identical
    to the Phase 1/2 behavior (trace includes governance_mode=rules)."""
    from graph import compile_graph
    graph = compile_graph()
    result = graph.invoke({
        "case_id": "M01",
        "supervisor_instruction": {"mode": "approve"},
    })
    # Trace entry carries mode metadata.
    gov_entries = [
        e for e in result.get("trace_log", [])
        if e.get("node") == "governance_agent"
    ]
    assert gov_entries and gov_entries[0].get("governance_mode") == "rules"


def test_graph_llm_mode_with_fake_provider_updates_language_only():
    from graph import compile_graph
    calls: list = []
    good_payload = (
        '{"situational_explanation":"LLM explanation for M01.",'
        ' "confidence_note":"LLM confidence.",'
        ' "rationale_trace":"LLM rationale.",'
        ' "cost_summary":"LLM cost summary.",'
        ' "alternative_descriptions":[]}'
    )
    register_provider("primary", _fake([good_payload], calls))
    graph = compile_graph()

    # Get the rules-mode recommended_action first, then compare llm-mode.
    rules_result = graph.invoke({
        "case_id": "M01",
        "supervisor_instruction": {"mode": "approve"},
    })
    llm_result = graph.invoke({
        "case_id": "M01",
        "supervisor_instruction": {"mode": "approve"},
        "governance_mode": "llm",
        "governance_gateway_config": _auto_gateway(),
    })

    rules_gov = rules_result["governance_output"]
    llm_gov = llm_result["governance_output"]

    # Language fields updated
    assert llm_gov["situational_explanation"] == "LLM explanation for M01."
    assert llm_gov["confidence_note"] == "LLM confidence."
    # Deterministic fields untouched
    assert llm_gov["recommended_action"] == rules_gov["recommended_action"]
    assert llm_gov["risk_level"] == rules_gov["risk_level"]
    assert llm_gov["evidence_sources"] == rules_gov["evidence_sources"]
    # Meta sidecar records mode
    assert llm_result["_governance_meta"]["mode"] == "llm"
    # Trace records mode
    gov_entries = [
        e for e in llm_result.get("trace_log", [])
        if e.get("node") == "governance_agent"
    ]
    assert gov_entries and gov_entries[0].get("governance_mode") == "llm"


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
        "governance_mode": "llm",
        "governance_gateway_config": _auto_gateway(retries=2),
    })
    # Fallback → governance output equals rules mode.
    assert llm_result["governance_output"] == rules_result["governance_output"]
    # But the meta still records mode=llm (the attempt was made).
    assert llm_result["_governance_meta"]["mode"] == "llm"
