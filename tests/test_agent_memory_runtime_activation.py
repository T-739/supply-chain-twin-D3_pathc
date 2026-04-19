"""B4 Slice 2D3-B: runtime-activation regression test.

Pins the internal-sideband repair that wires
``event_loop_c``'s env-resolved ``operations_mode`` into
``GraphState["operations_mode"]`` so the operations agent
dispatch observes the same env reality the W4 gate observes.

Without this seam:

  - ``SUPPLY_CHAIN_TWIN_OPERATIONS_MODE=llm`` made the W4 gate in
    ``event_loop_c._maybe_build_agent_memory_context`` build an
    ``AgentMemoryContext``;
  - …but ``graph.operations_agent_node`` falls back to its
    ``state.get("operations_mode") or "rules"`` default and
    ``agents.operations_agent._resolve_ops_mode("rules")``
    short-circuits the env;
  - so the operations agent took the rules path and the
    ``AgentMemoryContext`` reached the seam but was never
    injected into an actual LLM prompt.

These tests assert the gap is closed — and would have caught it
the moment a future refactor reopens it. They do NOT monkeypatch
``_resolve_ops_mode``: any test-side override there would
mask the gap.
"""

from __future__ import annotations

import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


def _install_ops_llm_prompt_spy(monkeypatch, captured_prompts):
    """Capture every operations-LLM prompt and return the
    deterministic baseline payload, mirroring
    ``_deterministic_ops_fallback``. Operates by monkeypatching
    ``llm_backend.generate_structured`` — the operations agent
    re-imports it lazily inside ``_enrich_ops_with_llm`` so the
    rebind is picked up on every call."""
    import llm_backend as _llm_backend

    def _spy(prompt, schema, *, gateway_config=None,
             deterministic_fallback=None, system=None):
        captured_prompts.append(prompt)
        value = (
            deterministic_fallback(prompt, schema)
            if deterministic_fallback is not None else None
        )
        return _llm_backend.LLMResult(
            value=value,
            provider="test-spy",
            model="test-spy",
            latency_ms=0,
            attempts=0,
            validation_ok=value is not None,
            fallback_used=True,
            mode="off",
            error=None,
            provider_trace=[],
        )

    monkeypatch.setattr(_llm_backend, "generate_structured", _spy)


def _b4_section_header() -> str:
    from agents.operations_agent import _B4_SECTION_HEADER
    return _B4_SECTION_HEADER


# ---------------------------------------------------------------------------
# 1. The wiring repair lets B4 reach the operations LLM seam under env=llm
# ---------------------------------------------------------------------------


def test_b4_on_under_env_llm_actually_injects_section_into_ops_llm_prompt(
    monkeypatch,
):
    """End-to-end runtime activation under the public
    ``run_session(...)`` API. No ``_resolve_ops_mode``
    monkeypatch — if the wiring breaks, this test must fail."""
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")

    from agent_memory.agent_memory_config import AgentMemoryExperimentConfig
    from event_loop_c import run_session

    captured: list[str] = []
    _install_ops_llm_prompt_spy(monkeypatch, captured)

    run_session(
        seed=42,
        mode="PATH_C_WARM",
        agent_memory_config=AgentMemoryExperimentConfig(
            enable_agent_visible_memory=True,
        ),
    )

    assert captured, (
        "operations LLM gateway was never invoked under env=llm + "
        "PATH_C_WARM + B4-enabled config — the runtime-activation "
        "repair has regressed; B4 is silently rules-path-only again."
    )

    header = _b4_section_header()
    with_header = [p for p in captured if header in p]
    assert with_header, (
        "B4 ON run produced operations LLM prompts but NONE carried "
        f"the {header!r} section. The W4 gate fired (or the LLM path "
        "fired) but the seam did not actually inject — investigate "
        "the GraphState sideband threading in "
        "event_loop._run_reasoning_slice and the prompt-builder "
        "guard ``_b4_should_inject``."
    )


# ---------------------------------------------------------------------------
# 2. The OFF baseline still reaches the LLM seam, but without the section
# ---------------------------------------------------------------------------


def test_b4_off_under_env_llm_reaches_ops_llm_seam_without_b4_section(
    monkeypatch,
):
    """Mirror image: same env, same mode, but no
    ``agent_memory_config``. The LLM seam must still be exercised
    (so the OFF baseline is comparable to the ON run); the B4
    section header must NOT appear in any captured prompt."""
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")

    from event_loop_c import run_session

    captured: list[str] = []
    _install_ops_llm_prompt_spy(monkeypatch, captured)

    run_session(
        seed=42,
        mode="PATH_C_WARM",
        agent_memory_config=None,
    )

    assert captured, (
        "operations LLM gateway was never invoked under env=llm + "
        "PATH_C_WARM (B4 OFF) — the env→GraphState wiring is broken "
        "for the OFF baseline, which would silently invalidate every "
        "OFF-vs-ON comparison."
    )

    header = _b4_section_header()
    leaks = [p for p in captured if header in p]
    assert not leaks, (
        f"B4 section header leaked into {len(leaks)} operations LLM "
        "prompt(s) on the B4 OFF run — default-off invariance "
        "violated."
    )


# ---------------------------------------------------------------------------
# 3. Path B (env unset) stays on the rules path — no behavior change
# ---------------------------------------------------------------------------


def test_path_c_warm_under_env_unset_does_not_reach_ops_llm_seam(monkeypatch):
    """Default-off byte identity proxy: with the env unset, the
    operations agent stays on the rules path and the LLM gateway
    is never called. Confirms the 2D3-B sideband does not
    accidentally widen the LLM-dispatch surface."""
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)

    from event_loop_c import run_session

    captured: list[str] = []
    _install_ops_llm_prompt_spy(monkeypatch, captured)

    run_session(
        seed=42,
        mode="PATH_C_WARM",
        agent_memory_config=None,
    )

    assert captured == [], (
        "operations LLM gateway was invoked under env-unset PATH_C_"
        "WARM — the 2D3-B internal sideband may have widened "
        "LLM-dispatch reach beyond the env-opt-in surface."
    )
