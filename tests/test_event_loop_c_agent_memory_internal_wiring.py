"""B4 Slice 2C: event_loop_c internal caller-wiring tests.

Pins the W1–W8 locks landed in Slice 2C, kept in sync with the
Slice 2D1 / 2D1.x evolution of the ``run_session`` public
surface. At the time Slice 2C landed the invariants below were
all true; Slice 2D1 / 2D1.x deliberately relaxed two of them
(and that relaxation is pinned by
``tests/test_run_session_agent_memory_public_kwarg.py``):

- W1/W2/W4 — the B4 context is built only inside the Path C
  internal caller layer, gated by the five W4 conditions.
  *Still true.*
- W3 — ``run_session``'s public signature was unchanged at the
  time Slice 2C landed. **Superseded by D8 / P1 in Slice 2D1**:
  ``run_session`` now exposes exactly one additive optional
  kwarg ``agent_memory_config``. The updated §5 tests below pin
  the post-2D1 shape.
- W5 — the context sees pre-current-event memory only
  (no self-reference). *Still true.*
- W6 — the MemoryQuery is event-type-only. *Still true.*
- W7 — the builder is a pure function; flag gating lives at the
  caller. *Still true.*
- W8 — no ``SessionEventRecord`` overlay / compare block / KPI
  is added. *Still true.* **Digest fragment carve-out as of
  Slice 2D1.x (F1 / F2):** an ``agent_memory`` fragment IS
  contributed to ``config_for_digest`` when the public config's
  ``enable_agent_visible_memory`` is True. That fragment is
  pinned by the Slice 2D1.x test file, not here.

All tests in this file remain structural / signature-level /
behavioral on the internal helpers. End-to-end public-API B4
behavior (activation, digest, artifact-level pins) lives in
``tests/test_run_session_agent_memory_public_kwarg.py``.
"""

from __future__ import annotations

import inspect
import os
import sys
from typing import Any

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from agent_memory import (  # noqa: E402
    AgentMemoryContext,
    AgentMemoryExperimentConfig,
)
from event_engine import generate_demo_event_stream  # noqa: E402
from event_loop_c import (  # noqa: E402
    _build_agent_memory_query_for_event,
    _build_path_c_main_records,
    _maybe_build_agent_memory_context,
    _resolve_operations_mode_from_env,
    run_session,
)
from event_schema import EventType  # noqa: E402
from learning.episodic_memory import EpisodicMemory  # noqa: E402
from learning.memory_schema import MemoryRecord  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mk_memory_record(
    *,
    event_id: str,
    event_type: str = "CARRIER_DELAY",
    ts: str = "2026-01-01T00:00:00Z",
    session_id: str = "S-PRIOR",
    action_taken: str | None = "EXPEDITE",
    final_route: str = "AUTO_EXECUTE",
    execution_status: str = "executed",
    cost: float | None = 100.0,
    sla: bool | None = True,
) -> MemoryRecord:
    return MemoryRecord(
        event_id=event_id,
        event_type=event_type,
        event_timestamp=ts,
        action_taken=action_taken,
        execution_status=execution_status,
        final_route=final_route,
        cost_incurred=cost,
        sla_preserved=sla,
        risk_level="LOW",
        session_id=session_id,
    )


def _cfg_on_warm() -> AgentMemoryExperimentConfig:
    return AgentMemoryExperimentConfig(enable_agent_visible_memory=True)


def _cfg_off() -> AgentMemoryExperimentConfig:
    return AgentMemoryExperimentConfig(enable_agent_visible_memory=False)


# ---------------------------------------------------------------------------
# 1. Query builder contract (W6)
# ---------------------------------------------------------------------------


def test_query_builder_event_type_only():
    events = generate_demo_event_stream()
    q = _build_agent_memory_query_for_event(events[0])
    assert q.event_type == events[0].event_type.value
    assert q.action_type is None
    assert q.final_route is None
    assert q.recent_n is None


def test_query_builder_uses_current_event_type_string_literally():
    events = generate_demo_event_stream()
    for ev in events:
        q = _build_agent_memory_query_for_event(ev)
        assert q.event_type == ev.event_type.value


def test_query_builder_is_pure():
    events = generate_demo_event_stream()
    q1 = _build_agent_memory_query_for_event(events[0])
    q2 = _build_agent_memory_query_for_event(events[0])
    assert q1.model_dump() == q2.model_dump()


# ---------------------------------------------------------------------------
# 2. Caller gating: OFF paths (W4)
# ---------------------------------------------------------------------------


def _mem_with_one_matching_row(event) -> EpisodicMemory:
    mem = EpisodicMemory()
    mem.append(_mk_memory_record(
        event_id="E-PRIOR",
        event_type=event.event_type.value,
    ))
    return mem


def test_gate_off_when_config_is_none():
    events = generate_demo_event_stream()
    mem = _mem_with_one_matching_row(events[0])
    ctx = _maybe_build_agent_memory_context(
        mem, events[0],
        mode="PATH_C_WARM", operations_mode="llm",
        agent_memory_config=None,
    )
    assert ctx is None


def test_gate_off_when_flag_disabled():
    events = generate_demo_event_stream()
    mem = _mem_with_one_matching_row(events[0])
    ctx = _maybe_build_agent_memory_context(
        mem, events[0],
        mode="PATH_C_WARM", operations_mode="llm",
        agent_memory_config=_cfg_off(),
    )
    assert ctx is None


def test_gate_off_when_mode_not_path_c_warm():
    events = generate_demo_event_stream()
    mem = _mem_with_one_matching_row(events[0])
    for mode in ("BASELINE_STATIC", "PATH_C_COLD"):
        ctx = _maybe_build_agent_memory_context(
            mem, events[0],
            mode=mode, operations_mode="llm",
            agent_memory_config=_cfg_on_warm(),
        )
        assert ctx is None, mode


def test_gate_off_when_operations_mode_is_rules():
    events = generate_demo_event_stream()
    mem = _mem_with_one_matching_row(events[0])
    ctx = _maybe_build_agent_memory_context(
        mem, events[0],
        mode="PATH_C_WARM", operations_mode="rules",
        agent_memory_config=_cfg_on_warm(),
    )
    assert ctx is None


def test_allowed_modes_is_contract_closed_to_path_c_warm():
    """Condition 5 (``PATH_C_WARM in allowed_modes``) is
    trivially satisfied under Slice 1's closed contract
    (``allowed_modes = frozenset({"PATH_C_WARM"})``). Pin the
    contract so a future widening trips this test and forces
    review of the caller gate."""
    cfg = AgentMemoryExperimentConfig(enable_agent_visible_memory=True)
    assert cfg.allowed_modes == frozenset({"PATH_C_WARM"})


# ---------------------------------------------------------------------------
# 3. Caller gating: ON path (W4)
# ---------------------------------------------------------------------------


def test_gate_on_yields_non_empty_context_when_memory_has_matches():
    events = generate_demo_event_stream()
    mem = _mem_with_one_matching_row(events[0])
    ctx = _maybe_build_agent_memory_context(
        mem, events[0],
        mode="PATH_C_WARM", operations_mode="llm",
        agent_memory_config=_cfg_on_warm(),
    )
    assert isinstance(ctx, AgentMemoryContext)
    assert ctx.matched_records == 1
    assert ctx.cold_start is False
    assert len(ctx.recent_examples) == 1
    assert ctx.recent_examples[0].event_id == "E-PRIOR"


def test_gate_on_yields_cold_start_context_when_memory_empty():
    """ON path with no matching rows still produces a context —
    the B4 ``cold_start`` semantic (R3) is ``matched_records ==
    0``."""
    events = generate_demo_event_stream()
    mem = EpisodicMemory()
    ctx = _maybe_build_agent_memory_context(
        mem, events[0],
        mode="PATH_C_WARM", operations_mode="llm",
        agent_memory_config=_cfg_on_warm(),
    )
    assert isinstance(ctx, AgentMemoryContext)
    assert ctx.matched_records == 0
    assert ctx.cold_start is True
    assert ctx.recent_examples == []


# ---------------------------------------------------------------------------
# 4. Pre-current-event memory only (W5)
# ---------------------------------------------------------------------------


def test_caller_sees_only_pre_current_event_memory_across_events(monkeypatch):
    """Spy on ``run_operations_agent_with_meta`` via
    ``graph.operations_agent_node`` so we can observe exactly
    what ``AgentMemoryContext`` the operations agent is handed
    for each event. Run two events through the Path C main path
    and assert:

      - event #1: the context reflects memory as seen BEFORE
        the event's own ``mem_record`` is appended;
      - event #2: the context reflects memory plus event #1's
        row (but NOT event #2's).
    """
    # Force the operations agent path through llm so the W4
    # condition ``operations_mode == "llm"`` is satisfied at the
    # gate (which reads env). We still spy the agent itself to
    # avoid calling any real LLM gateway.
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")

    # Use only the first two events to keep the assertion set
    # tight and the live TwinState behavior bounded.
    events = generate_demo_event_stream()[:2]

    from adaptive.adaptive_policy_config import AdaptivePolicyGateConfig
    from event_loop import run_event_loop
    from replan.replan_config import ReplanConfig

    # Path B shadow runs the operations agent too (once per event).
    # Compute it FIRST so those calls don't trip the Path C spy.
    baseline_shadow = run_event_loop(events)
    baseline_event_results = baseline_shadow["event_results"]

    observed: list[AgentMemoryContext | None] = []

    import agents.operations_agent as _ops_mod

    real_run = _ops_mod.run_operations_agent_with_meta

    def _spy(*args, **kwargs):
        observed.append(kwargs.get("agent_memory_context"))
        # Delegate to the real rules-mode path by clearing the
        # llm hint and dropping B4 kwargs so the spy stays safe
        # (no LLM gateway call), matching what operations_mode
        # resolution would do in a dry-run environment without a
        # gateway.
        safe_kwargs = dict(kwargs)
        safe_kwargs["mode"] = "rules"
        safe_kwargs.pop("agent_memory_context", None)
        safe_kwargs.pop("agent_memory_config", None)
        return real_run(*args, **safe_kwargs)

    monkeypatch.setattr(_ops_mod, "run_operations_agent_with_meta", _spy)
    # graph.py imports the symbol lazily inside the node
    # function; patch the agent module itself (above) to cover
    # that call path.

    # Seed memory with one historical row that matches event #1's
    # event_type, so the first context must see exactly 1 match
    # rather than 0.
    seed_memory = EpisodicMemory()
    seed_memory.append(_mk_memory_record(
        event_id="E-HISTORIC",
        event_type=events[0].event_type.value,
    ))

    _build_path_c_main_records(
        events=events,
        baseline_event_results=baseline_event_results,
        memory=seed_memory,
        session_id="S-TEST",
        mode="PATH_C_WARM",
        adaptive_config=AdaptivePolicyGateConfig(),
        initial_twin_state=None,
        replan_config=ReplanConfig(),
        agent_memory_config=_cfg_on_warm(),
    )

    assert len(observed) == len(events)

    # Event #1 context must reflect the pre-seeded row only —
    # event #1's own mem_record has not been appended yet at the
    # moment the context is built.
    ctx_1 = observed[0]
    assert isinstance(ctx_1, AgentMemoryContext)
    assert ctx_1.matched_records == 1
    ids_1 = {ex.event_id for ex in ctx_1.recent_examples}
    assert ids_1 == {"E-HISTORIC"}
    # Self-reference sanity: the live event's own id must NOT
    # appear in the context the agent receives for that event.
    assert events[0].event_id not in ids_1

    # Event #2 context: whatever matched event #2's event_type,
    # excluding event #2's own id.
    ctx_2 = observed[1]
    assert isinstance(ctx_2, AgentMemoryContext)
    ids_2 = {ex.event_id for ex in ctx_2.recent_examples}
    assert events[1].event_id not in ids_2


# ---------------------------------------------------------------------------
# 5. Public run_session API surface (W3 → superseded by D8 / P1 in Slice 2D1)
#
# Slice 2C's invariant was "run_session has NO B4 kwargs at all".
# Slice 2D1 legitimately flips that invariant by adding exactly one
# optional B4 kwarg (``agent_memory_config``). The two tests below
# pin the post-2D1 reality: the *single* B4 kwarg landed, and no
# other B4-related kwarg (``agent_memory_context`` or
# ``operations_mode``) leaked in alongside it. The deeper Slice
# 2D1 public-kwarg tests live in
# ``tests/test_run_session_agent_memory_public_kwarg.py``.
# ---------------------------------------------------------------------------


def test_run_session_public_signature_exposes_only_agent_memory_config():
    sig = inspect.signature(run_session)
    param_names = set(sig.parameters.keys())
    # Still forbidden under D9 / P2:
    forbidden = {"agent_memory_context", "operations_mode"}
    leaks = param_names & forbidden
    assert not leaks, (
        "run_session public signature must not expose "
        f"{sorted(forbidden)!r} (D9 / P2). Leaked: {sorted(leaks)!r}"
    )
    # Locked by D8 / P1:
    assert "agent_memory_config" in param_names


def test_run_session_public_signature_matches_expected():
    sig = inspect.signature(run_session)
    assert set(sig.parameters.keys()) == {
        "seed", "mode", "events", "events_source",
        "initial_twin_state", "initial_memory",
        "adaptive_config", "replan_config", "correlator_config",
        # B4 Slice 2D1 additive optional kwarg (D8 / P1):
        "agent_memory_config",
    }


def test_build_path_c_main_records_gained_optional_b4_param():
    sig = inspect.signature(_build_path_c_main_records)
    assert "agent_memory_config" in sig.parameters
    p = sig.parameters["agent_memory_config"]
    assert p.default is None


# ---------------------------------------------------------------------------
# 6. Operations caller actually receives the context
# ---------------------------------------------------------------------------


def test_on_path_spy_observes_context_in_ops_kwargs(monkeypatch):
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")
    events = generate_demo_event_stream()[:1]

    from adaptive.adaptive_policy_config import AdaptivePolicyGateConfig
    from event_loop import run_event_loop
    from replan.replan_config import ReplanConfig

    mem = _mem_with_one_matching_row(events[0])
    baseline_shadow = run_event_loop(events)

    observed: dict[str, Any] = {}

    import agents.operations_agent as _ops_mod
    real_run = _ops_mod.run_operations_agent_with_meta

    def _spy(*args, **kwargs):
        observed["ctx"] = kwargs.get("agent_memory_context")
        observed["cfg"] = kwargs.get("agent_memory_config")
        safe = dict(kwargs)
        safe["mode"] = "rules"
        safe.pop("agent_memory_context", None)
        safe.pop("agent_memory_config", None)
        return real_run(*args, **safe)

    monkeypatch.setattr(_ops_mod, "run_operations_agent_with_meta", _spy)

    _build_path_c_main_records(
        events=events,
        baseline_event_results=baseline_shadow["event_results"],
        memory=mem,
        session_id="S",
        mode="PATH_C_WARM",
        adaptive_config=AdaptivePolicyGateConfig(),
        initial_twin_state=None,
        replan_config=ReplanConfig(),
        agent_memory_config=_cfg_on_warm(),
    )

    assert isinstance(observed.get("ctx"), AgentMemoryContext)
    assert isinstance(observed.get("cfg"), AgentMemoryExperimentConfig)


def test_off_path_spy_observes_none_ops_kwargs(monkeypatch):
    """When ``agent_memory_config`` is not supplied, the operations
    agent must receive ``agent_memory_context=None`` (Slice 2B's
    S3 predicate then short-circuits)."""
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")
    events = generate_demo_event_stream()[:1]

    from adaptive.adaptive_policy_config import AdaptivePolicyGateConfig
    from event_loop import run_event_loop
    from replan.replan_config import ReplanConfig

    baseline_shadow = run_event_loop(events)

    observed: dict[str, Any] = {}

    import agents.operations_agent as _ops_mod
    real_run = _ops_mod.run_operations_agent_with_meta

    def _spy(*args, **kwargs):
        observed["ctx"] = kwargs.get("agent_memory_context")
        observed["cfg"] = kwargs.get("agent_memory_config")
        safe = dict(kwargs)
        safe["mode"] = "rules"
        safe.pop("agent_memory_context", None)
        safe.pop("agent_memory_config", None)
        return real_run(*args, **safe)

    monkeypatch.setattr(_ops_mod, "run_operations_agent_with_meta", _spy)

    _build_path_c_main_records(
        events=events,
        baseline_event_results=baseline_shadow["event_results"],
        memory=EpisodicMemory(),
        session_id="S",
        mode="PATH_C_WARM",
        adaptive_config=AdaptivePolicyGateConfig(),
        initial_twin_state=None,
        replan_config=ReplanConfig(),
        # agent_memory_config intentionally omitted → default None
    )

    assert observed.get("ctx") is None
    assert observed.get("cfg") is None


def test_rules_path_spy_observes_none_ops_kwargs(monkeypatch):
    """When operations_mode resolves to ``rules``, the caller
    gate refuses to build a context regardless of the B4 config
    state (W4 condition 4)."""
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "rules")
    events = generate_demo_event_stream()[:1]

    from adaptive.adaptive_policy_config import AdaptivePolicyGateConfig
    from event_loop import run_event_loop
    from replan.replan_config import ReplanConfig

    baseline_shadow = run_event_loop(events)

    observed: dict[str, Any] = {}

    import agents.operations_agent as _ops_mod
    real_run = _ops_mod.run_operations_agent_with_meta

    def _spy(*args, **kwargs):
        observed["ctx"] = kwargs.get("agent_memory_context")
        observed["cfg"] = kwargs.get("agent_memory_config")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(_ops_mod, "run_operations_agent_with_meta", _spy)

    _build_path_c_main_records(
        events=events,
        baseline_event_results=baseline_shadow["event_results"],
        memory=_mem_with_one_matching_row(events[0]),
        session_id="S",
        mode="PATH_C_WARM",
        adaptive_config=AdaptivePolicyGateConfig(),
        initial_twin_state=None,
        replan_config=ReplanConfig(),
        agent_memory_config=_cfg_on_warm(),
    )

    assert observed.get("ctx") is None
    assert observed.get("cfg") is None


def test_env_resolver_returns_rules_by_default(monkeypatch):
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    assert _resolve_operations_mode_from_env() == "rules"


def test_env_resolver_returns_llm_when_set(monkeypatch):
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")
    assert _resolve_operations_mode_from_env() == "llm"


def test_env_resolver_returns_rules_on_bogus_value(monkeypatch):
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "WILD")
    assert _resolve_operations_mode_from_env() == "rules"


# ---------------------------------------------------------------------------
# 7. No compare / overlay / digest side effects (W8)
# ---------------------------------------------------------------------------


def test_session_event_record_has_no_agent_memory_field():
    from session.session_schema import SessionEventRecord

    forbidden = {"agent_memory_context", "agent_memory_config"}
    leaks = set(SessionEventRecord.model_fields.keys()) & forbidden
    assert not leaks, (
        "SessionEventRecord must not carry B4 overlay fields in "
        f"Slice 2C. Leaked: {sorted(leaks)!r}"
    )


def test_session_compare_b4_block_is_opt_in_only():
    """Slice 2D3-A flip of the prior Slice 2C "no B4 string in
    session_compare" pin: ``session_compare.py`` now exposes an
    ``agent_memory_variant_tags`` opt-in kwarg + an additive
    ``agent_memory_experiment_summary`` sibling block. The
    structural invariant we still enforce is that the block is
    OPT-IN — the report shape stays byte-identical when the
    kwarg is omitted, and ``COMPARE_REPORT_SCHEMA_VERSION`` does
    NOT bump."""
    from session.session_compare import COMPARE_REPORT_SCHEMA_VERSION

    assert COMPARE_REPORT_SCHEMA_VERSION == "1.1", (
        "Slice 2D3-A must NOT bump COMPARE_REPORT_SCHEMA_VERSION."
    )

    import inspect

    from session import session_compare as _sc

    sig = inspect.signature(_sc.build_compare_report)
    assert "agent_memory_variant_tags" in sig.parameters, (
        "Slice 2D3-A must expose ``agent_memory_variant_tags`` as "
        "the public opt-in kwarg on ``build_compare_report``."
    )
    assert sig.parameters["agent_memory_variant_tags"].default is None, (
        "``agent_memory_variant_tags`` must default to None to "
        "preserve pre-2D3 byte identity."
    )


def test_event_loop_c_does_not_reach_cumulative_memory_loader():
    """Cross-branch hygiene — B4 Slice 2C must not import B3
    loader internals (boundary §4 forbids B4 → B3 coupling)."""
    with open(
        os.path.join(_SRC_DIR, "event_loop_c.py"),
        "r", encoding="utf-8",
    ) as f:
        source = f.read()
    assert "cumulative_memory" not in source


def test_event_loop_c_does_not_import_renderer():
    """Slice 2C constraint: event_loop_c does not call the
    renderer (that's the agent module's job)."""
    with open(
        os.path.join(_SRC_DIR, "event_loop_c.py"),
        "r", encoding="utf-8",
    ) as f:
        source = f.read()
    assert "render_agent_memory_context" not in source
