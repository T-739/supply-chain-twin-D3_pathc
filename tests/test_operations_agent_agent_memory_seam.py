"""B4 Slice 2B: operations-agent prompt seam tests.

Covers the S1–S7 locks landed in
``src/agents/operations_agent.py``:

- S1/S2 — only ``operations_agent.py`` is modified, and the seam
  lives in a single prompt helper (``_build_ops_llm_user_prompt``)
  that is reachable only on the LLM path;
- S3 — five-condition injection predicate;
- S4 — injection content is verbatim renderer output (no
  free-form recap);
- S5 — fixed section header/footer delimiters, single insertion
  point;
- S6 — public entry points gained two optional kwargs with safe
  ``None`` defaults;
- S7 — the agent module does NOT import the builder.

Tests avoid calling the actual LLM gateway; they exercise the
prompt-builder helper directly and, where needed, drive the full
``_enrich_ops_with_llm`` pipeline with a null gateway_config so the
import try/except path fabricates a baseline-equivalent output
without mutating shape.
"""

from __future__ import annotations

import ast
import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from agent_memory import (  # noqa: E402
    AgentMemoryContext,
    AgentMemoryExampleRef,
    AgentMemoryExperimentConfig,
    render_agent_memory_context,
)
from agents.operations_agent import (  # noqa: E402
    _B4_SECTION_FOOTER,
    _B4_SECTION_HEADER,
    _build_ops_llm_user_prompt,
    run_operations_agent,
    run_operations_agent_modeful,
    run_operations_agent_with_meta,
)


# ---------------------------------------------------------------------------
# Minimal fixtures
# ---------------------------------------------------------------------------


def _baseline_with_no_candidates():
    """A stand-in OperationsOutput-shaped object with no
    ranked_candidates. The prompt builder only reads
    ``baseline.ranked_candidates`` so a duck-typed object is
    enough for this helper-level test."""

    class _Baseline:
        ranked_candidates: list = []

    return _Baseline()


def _scenario_context() -> dict:
    return {
        "scenario_type": "CARRIER_DELAY",
        "risk_level": "LOW",
        "exception_description": "demo",
    }


def _context_empty() -> AgentMemoryContext:
    return AgentMemoryContext(
        matched_records=0, cold_start=True, query_signature="sig-empty",
    )


def _context_full() -> AgentMemoryContext:
    return AgentMemoryContext(
        matched_records=2,
        cold_start=False,
        query_signature="sig-demo",
        auto_execute_success_rate=0.5,
        sla_preservation_rate=0.5,
        avg_cost=42.5,
        action_type_distribution={"EXPEDITE": 1, "TRANSFER": 1},
        recent_examples=[
            AgentMemoryExampleRef(
                event_id="E1", event_type="CARRIER_DELAY",
                source_session_id="S-PRIOR",
                action_taken="EXPEDITE", final_route="AUTO_EXECUTE",
                execution_status="executed",
                cost_incurred=100.0, sla_preserved=True,
            ),
            AgentMemoryExampleRef(
                event_id="E2", event_type="CARRIER_DELAY",
                source_session_id="S-PRIOR",
                action_taken="TRANSFER", final_route="AUTO_EXECUTE",
                execution_status="executed",
                cost_incurred=50.0, sla_preserved=False,
            ),
        ],
    )


def _cfg_on() -> AgentMemoryExperimentConfig:
    return AgentMemoryExperimentConfig(enable_agent_visible_memory=True)


def _cfg_off() -> AgentMemoryExperimentConfig:
    return AgentMemoryExperimentConfig(enable_agent_visible_memory=False)


# ---------------------------------------------------------------------------
# 1. flag OFF invariance
# ---------------------------------------------------------------------------


def test_prompt_bytes_default_args_match_pre_b4_path():
    """Calling the helper with no B4 kwargs at all produces the
    pre-B4 prompt bytes by construction. This test pins that
    identity."""
    pre = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context()
    )
    post = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=None, agent_memory_config=None,
    )
    assert pre == post
    assert _B4_SECTION_HEADER not in pre
    assert _B4_SECTION_FOOTER not in pre


def test_prompt_bytes_context_only_is_off_path():
    """Context supplied but config=None → OFF (short-circuit on
    missing config)."""
    pre = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context()
    )
    p = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=_context_full(),
        agent_memory_config=None,
    )
    assert p == pre
    assert _B4_SECTION_HEADER not in p


def test_prompt_bytes_config_only_is_off_path():
    """Config supplied but context=None → OFF (short-circuit on
    missing context)."""
    pre = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context()
    )
    p = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=None,
        agent_memory_config=_cfg_on(),
    )
    assert p == pre
    assert _B4_SECTION_HEADER not in p


def test_prompt_bytes_config_disabled_is_off_path():
    """enable_agent_visible_memory=False → OFF even with a
    non-None context."""
    pre = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context()
    )
    p = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=_context_full(),
        agent_memory_config=_cfg_off(),
    )
    assert p == pre
    assert _B4_SECTION_HEADER not in p


def test_config_target_agent_closed_to_operations():
    """S3 condition 4 is trivially satisfied in Slice 1 because
    ``target_agent`` is a closed Literal. Assert the contract so
    a future amendment that widens the literal trips this pin
    and forces review of the seam."""
    from agent_memory.agent_memory_config import KNOWN_AGENT_MEMORY_TARGETS

    assert KNOWN_AGENT_MEMORY_TARGETS == frozenset({"operations"})


# ---------------------------------------------------------------------------
# 2. enabled injection
# ---------------------------------------------------------------------------


def test_prompt_injects_fixed_section_when_all_conditions_hold():
    ctx = _context_full()
    cfg = _cfg_on()
    p = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=ctx, agent_memory_config=cfg,
    )

    # Exactly one header line and one footer line. Plain
    # substring count would double-count the header because the
    # footer ``END_HISTORICAL_STRUCTURED_MEMORY_CONTEXT`` embeds
    # the header string. We count by full line equality instead.
    lines = p.splitlines()
    assert lines.count(_B4_SECTION_HEADER) == 1
    assert lines.count(_B4_SECTION_FOOTER) == 1

    # Header appears before footer.
    assert lines.index(_B4_SECTION_HEADER) < lines.index(_B4_SECTION_FOOTER)


def test_injected_section_contains_verbatim_renderer_output():
    ctx = _context_full()
    cfg = _cfg_on()
    p = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=ctx, agent_memory_config=cfg,
    )
    rendered = render_agent_memory_context(ctx, cfg)
    # The renderer output must appear byte-for-byte inside the
    # header…footer window.
    start = p.index(_B4_SECTION_HEADER) + len(_B4_SECTION_HEADER) + 1
    end = p.index(_B4_SECTION_FOOTER)
    assert p[start:end].rstrip("\n") == rendered


def test_injection_position_is_stable_at_end_of_prompt():
    """S5 — fixed section is appended after the scenario Facts
    block. Two contexts differing only in content produce prompts
    whose pre-injection prefix is byte-identical."""
    cfg = _cfg_on()
    p_a = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=_context_full(), agent_memory_config=cfg,
    )
    p_b = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=_context_empty(), agent_memory_config=cfg,
    )
    header_idx_a = p_a.index(_B4_SECTION_HEADER)
    header_idx_b = p_b.index(_B4_SECTION_HEADER)
    assert p_a[:header_idx_a] == p_b[:header_idx_b]


def test_on_path_strictly_extends_off_path_prefix():
    off = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context()
    )
    on = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=_context_full(), agent_memory_config=_cfg_on(),
    )
    # The OFF-path prompt is the exact prefix of the ON-path
    # prompt — B4 appends, never rewrites.
    assert on.startswith(off)
    assert len(on) > len(off)


# ---------------------------------------------------------------------------
# 3. rules mode untouched
# ---------------------------------------------------------------------------


def test_rules_mode_entrypoint_signature_unchanged():
    """``run_operations_agent`` is the rules-mode entry. It must
    NOT gain B4 kwargs — B4 lives exclusively on the LLM path."""
    import inspect

    sig = inspect.signature(run_operations_agent)
    params = set(sig.parameters.keys())
    assert "agent_memory_context" not in params
    assert "agent_memory_config" not in params


def test_rules_mode_ignores_b4_kwargs_on_modeful_entry():
    """``run_operations_agent_modeful(mode='rules', ...)`` accepts
    B4 kwargs for API uniformity but is byte-identical to calling
    ``run_operations_agent`` directly.
    """
    twin_state = {"inventory": {}, "orders": [], "cost_table": {}}
    sc = _scenario_context()
    out_rules = run_operations_agent(twin_state, sc)
    out_modeful = run_operations_agent_modeful(
        "rules", twin_state, sc,
        agent_memory_context=_context_full(),
        agent_memory_config=_cfg_on(),
    )
    assert out_rules.model_dump() == out_modeful.model_dump()


def test_rules_mode_meta_shape_unchanged_under_b4_kwargs():
    twin_state = {"inventory": {}, "orders": [], "cost_table": {}}
    sc = _scenario_context()
    _, meta_off = run_operations_agent_with_meta(
        twin_state, sc, mode="rules",
    )
    _, meta_on = run_operations_agent_with_meta(
        twin_state, sc, mode="rules",
        agent_memory_context=_context_full(),
        agent_memory_config=_cfg_on(),
    )
    assert meta_off == meta_on


# ---------------------------------------------------------------------------
# 4. output schema unchanged
# ---------------------------------------------------------------------------


def test_operations_output_schema_unchanged_by_b4_import():
    """OperationsOutput shape has not acquired any B4-specific
    field as a side effect of the import surface."""
    from agents.operations_agent import OperationsOutput

    forbidden = {
        "agent_memory_context", "agent_memory_config",
        "memory_context", "b4_injection",
    }
    leaks = set(OperationsOutput.model_fields.keys()) & forbidden
    assert not leaks, (
        f"OperationsOutput leaked a B4-specific field: {sorted(leaks)!r}"
    )


def test_meta_shape_untouched_under_b4_kwargs_llm_signature():
    """``run_operations_agent_with_meta`` gained two optional
    kwargs; the *returned* meta dict keys stay the rules/llm
    closed set. We validate via the rules branch (no LLM gateway
    required)."""
    twin_state = {"inventory": {}, "orders": [], "cost_table": {}}
    sc = _scenario_context()
    _, meta = run_operations_agent_with_meta(
        twin_state, sc, mode="rules",
        agent_memory_context=_context_full(),
        agent_memory_config=_cfg_on(),
    )
    assert set(meta.keys()) == {
        "mode", "llm_enriched_fields", "llm_trace", "retrieval",
    }


# ---------------------------------------------------------------------------
# 5. no builder call
# ---------------------------------------------------------------------------


_OPS_AGENT_PATH = os.path.join(
    _PROJECT_DIR, "src", "agents", "operations_agent.py"
)


def _scan_ops_agent_for(symbol: str) -> list[str]:
    """Light AST scan for ``from agent_memory.agent_memory_builder``
    imports or name references to ``build_agent_memory_context``."""
    findings: list[str] = []
    with open(_OPS_AGENT_PATH, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=_OPS_AGENT_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "agent_memory.agent_memory_builder" or mod.endswith(
                ".agent_memory_builder"
            ):
                findings.append(f"from {mod} import ...")
            for alias in node.names:
                if alias.name == symbol:
                    findings.append(f"name import: {alias.name}")
        if isinstance(node, ast.Name) and node.id == symbol:
            findings.append(f"name ref: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr == symbol:
            findings.append(f"attr ref: .{node.attr}")
    return findings


def test_operations_agent_does_not_reference_builder_symbol():
    findings = _scan_ops_agent_for("build_agent_memory_context")
    assert not findings, (
        "operations_agent.py must not import or call the B4 "
        f"builder (S7). Findings: {findings!r}"
    )


def test_operations_agent_does_not_import_builder_module():
    """Belt-and-suspenders: even if the module is re-exported from
    ``agent_memory/__init__.py``, we must not reach it via a star
    import either. Scan for any ``agent_memory_builder`` import
    segment."""
    with open(_OPS_AGENT_PATH, "r", encoding="utf-8") as f:
        source = f.read()
    assert "agent_memory_builder" not in source, (
        "operations_agent.py mentions the builder module name — "
        "Slice 2B forbids this (S7)."
    )


# ---------------------------------------------------------------------------
# 6. prompt bytes determinism
# ---------------------------------------------------------------------------


def test_prompt_bytes_are_deterministic_off_path():
    a = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context()
    )
    b = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context()
    )
    assert a == b


def test_prompt_bytes_are_deterministic_on_path():
    cfg = _cfg_on()
    ctx = _context_full()
    a = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=ctx, agent_memory_config=cfg,
    )
    b = _build_ops_llm_user_prompt(
        _baseline_with_no_candidates(), _scenario_context(),
        agent_memory_context=ctx, agent_memory_config=cfg,
    )
    assert a == b
