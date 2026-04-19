"""B4 Slice 2D3-A / 2D3-B: exercised-path truth-stability test.

Goal — under controlled, *actually-activated* B4 conditions:

  - SUPPLY_CHAIN_TWIN_OPERATIONS_MODE=llm   (so the W4 gate in
    ``event_loop_c._maybe_build_agent_memory_context`` fires and
    builds an ``AgentMemoryContext``, AND — after the Slice
    2D3-B internal-sideband repair — the operations agent
    dispatch in ``graph.operations_agent_node`` observes the
    same mode reality and actually takes the LLM path);
  - operations LLM gateway monkeypatched to a deterministic
    spy that captures every prompt and returns the baseline
    rationale verbatim (no real provider call, no flakiness);
  - PATH_C_WARM with a fixed warm-seed memory so the agent_memory
    builder produces a non-cold-start AgentMemoryContext;
  - one ``run_session`` call with B4 OFF and one with B4 ON,
    holding every other input fixed,

assert that:

  - the B4 ON run actually produced at least one operations LLM
    prompt that contained the fixed
    ``HISTORICAL_STRUCTURED_MEMORY_CONTEXT`` section header (i.e.
    we are NOT trivially passing on a rules-only path);
  - the B4 OFF run produced operations LLM prompts but NONE of
    them carried the B4 section header;
  - per-event ``GovernanceTruthRef`` bytes match between OFF / ON;
  - per-event ``EffectiveDecisionRef`` bytes match between OFF / ON;
  - per-event ``baseline_event_result`` bytes match between OFF /
    ON.

This is a structural assertion: even with B4 actually injecting
content into the operations LLM user prompt, the dual-track truth
references and the Path B raw shadow bytes are byte-stable. It
does NOT prove anything about non-deterministic LLM behavior —
that is out of scope for 2D3-A and properly belongs to whatever
future slice runs the experiment under a real provider.
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
    """Mirrors the fixture in tests/test_replay_byte_identical.py —
    PATH_C_* runs use the operations agent's retrieval, which
    needs the vector store built once per process."""
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


def _build_warm_seed_memory():
    """Two CARRIER_DELAY_ESCALATION rows so the W6 query (event-type
    only) returns matched rows for the demo stream's first event."""
    from learning.episodic_memory import EpisodicMemory
    from learning.memory_schema import MemoryRecord

    mem = EpisodicMemory()
    for i in range(2):
        mem.append(MemoryRecord(
            event_id=f"WARM-SEED-{i:02d}",
            event_type="CARRIER_DELAY_ESCALATION",
            event_timestamp=f"2026-01-{i + 1:02d}T08:00:00+00:00",
            action_taken="EXPEDITE",
            execution_status="executed",
            final_route="AUTO_EXECUTE",
            cost_incurred=200.0,
            sla_preserved=True,
            risk_level="LOW",
            session_id="PRIOR-SESSION-FOR-WARM-SEED",
        ))
    return mem


def _install_deterministic_ops_llm_spy(monkeypatch, captured_prompts):
    """Monkeypatch ``llm_backend.generate_structured`` so the
    operations-agent LLM path is exercised but the returned payload
    is the deterministic baseline (the same payload
    ``_deterministic_ops_fallback`` would have produced).

    Captures every prompt the operations agent sends so the test
    can verify whether B4's fixed section header appeared.

    The operations agent's ``_enrich_ops_with_llm`` does
    ``from llm_backend import generate_structured`` lazily INSIDE
    the function, so re-binding ``llm_backend.generate_structured``
    here is sufficient — every call into the gateway picks up the
    monkeypatched function.

    We deliberately do NOT monkeypatch governance here: governance
    defaults to ``rules`` (env-only via
    ``SUPPLY_CHAIN_TWIN_GOVERNANCE_MODE``), so the governance LLM
    path is not reached and the dual-track truth bytes are
    determined entirely by the rules-mode governance + the
    deterministic operations baseline."""
    import llm_backend as _llm_backend

    def _spy(prompt, schema, *, gateway_config=None,
             deterministic_fallback=None, system=None):
        captured_prompts.append(prompt)
        if deterministic_fallback is not None:
            value = deterministic_fallback(prompt, schema)
        else:
            value = None
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


def _drop_volatile_meta_keys(d: dict) -> dict:
    """``llm_meta.trace`` carries spy-side identifiers (provider,
    model, latency) — those vary across B4 OFF/ON only because we
    rebuilt the spy. We compare the underlying truth references
    instead, never the meta dict."""
    return d


def _b4_section_header() -> str:
    """Re-import the locked section header from the operations
    agent module so the assertion below is grounded in the same
    constant the seam uses, not a re-spelled string."""
    from agents.operations_agent import _B4_SECTION_HEADER
    return _B4_SECTION_HEADER


def test_truth_bytes_stable_across_b4_off_vs_on_under_llm_ops(monkeypatch):
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")
    # Leave SUPPLY_CHAIN_TWIN_GOVERNANCE_MODE unset → governance
    # stays in rules mode (deterministic). Leave
    # SUPPLY_CHAIN_TWIN_LLM_MODE unset → the spy short-circuits the
    # provider trip; no real network call is made even in CI.
    #
    # No ``_resolve_ops_mode`` monkeypatch — Slice 2D3-B's
    # internal-sideband repair (event_loop_c → _run_reasoning_slice
    # → GraphState["operations_mode"]) makes the env reach the
    # operations agent dispatch on its own.

    from agent_memory.agent_memory_config import AgentMemoryExperimentConfig
    from event_loop_c import run_session

    captured_off: list[str] = []
    captured_on: list[str] = []

    # --- B4 OFF run ---
    _install_deterministic_ops_llm_spy(monkeypatch, captured_off)
    artifact_off = run_session(
        seed=42,
        mode="PATH_C_WARM",
        initial_memory=_build_warm_seed_memory(),
        agent_memory_config=None,
    )

    # --- B4 ON run ---
    _install_deterministic_ops_llm_spy(monkeypatch, captured_on)
    artifact_on = run_session(
        seed=42,
        mode="PATH_C_WARM",
        initial_memory=_build_warm_seed_memory(),
        agent_memory_config=AgentMemoryExperimentConfig(
            enable_agent_visible_memory=True,
        ),
    )

    # ------------------------------------------------------------------
    # 1. Sanity: both runs ACTUALLY exercised the operations LLM seam.
    # ------------------------------------------------------------------
    assert captured_off, (
        "operations LLM gateway was never called on the B4 OFF run "
        "— the test is not exercising the seam"
    )
    assert captured_on, (
        "operations LLM gateway was never called on the B4 ON run "
        "— the test is not exercising the seam"
    )

    # ------------------------------------------------------------------
    # 2. Discriminative power: B4 ON contains the locked section
    #    header in at least one prompt; B4 OFF contains it in none.
    # ------------------------------------------------------------------
    header = _b4_section_header()
    on_with_header = [p for p in captured_on if header in p]
    off_with_header = [p for p in captured_off if header in p]
    assert on_with_header, (
        "B4 ON run produced no operations LLM prompt carrying "
        f"the {header!r} section — the W4 gate did not fire and "
        "the test would trivially pass. Verify "
        "SUPPLY_CHAIN_TWIN_OPERATIONS_MODE=llm and that the "
        "warm-seed initial memory matches the demo event stream's "
        "first event_type."
    )
    assert not off_with_header, (
        "B4 OFF run leaked the B4 section header into an operations "
        f"LLM prompt: {len(off_with_header)} prompt(s) carried it. "
        "Default-off invariance violated."
    )

    # ------------------------------------------------------------------
    # 3. Per-event truth-byte stability.
    # ------------------------------------------------------------------
    assert len(artifact_off.event_records) == len(artifact_on.event_records), (
        "session length differs across B4 OFF/ON — the experiment "
        "comparison is not well-formed"
    )

    for idx, (rec_off, rec_on) in enumerate(zip(
        artifact_off.event_records, artifact_on.event_records,
    )):
        assert rec_off.governance_truth.model_dump() == rec_on.governance_truth.model_dump(), (
            f"governance_truth bytes diverged on event index {idx} — "
            "B4 truth-leakage candidate"
        )
        assert rec_off.effective_decision.model_dump() == rec_on.effective_decision.model_dump(), (
            f"effective_decision bytes diverged on event index {idx} "
            "— B4 effective-decision drift candidate"
        )
        assert rec_off.baseline_event_result == rec_on.baseline_event_result, (
            f"baseline_event_result bytes diverged on event index "
            f"{idx} — Path B raw shadow integrity violated by B4"
        )
