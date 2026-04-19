"""B4 Slice 2A: pure builder tests.

Covers R1 (signature), R3 (B4-local ``cold_start`` semantics),
R4 (``recent_examples`` selection + ordering), plus purity and
forbidden-import guards. No runtime wiring is exercised — the
builder is reachable from tests but not from any agent /
event_loop_c / harness path.
"""

from __future__ import annotations

import ast
import copy
import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from agent_memory.agent_memory_builder import build_agent_memory_context
from agent_memory.agent_memory_config import (
    MAX_AGENT_MEMORY_EXAMPLES,
    AgentMemoryExperimentConfig,
)
from agent_memory.agent_memory_schema import AgentMemoryContext
from learning.episodic_memory import EpisodicMemory
from learning.memory_schema import MemoryQuery, MemoryRecord


def _rec(
    *,
    event_id: str,
    ts: str,
    event_type: str = "CARRIER_DELAY",
    action_taken: str | None = "EXPEDITE",
    execution_status: str = "executed",
    final_route: str = "AUTO_EXECUTE",
    cost: float | None = 100.0,
    sla: bool | None = True,
    session_id: str = "S1",
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


def _default_config() -> AgentMemoryExperimentConfig:
    return AgentMemoryExperimentConfig(enable_agent_visible_memory=True)


# ---------------------------------------------------------------------------
# R1 / return shape
# ---------------------------------------------------------------------------


def test_builder_returns_agent_memory_context_instance():
    mem = EpisodicMemory()
    ctx = build_agent_memory_context(mem, MemoryQuery(), _default_config())
    assert isinstance(ctx, AgentMemoryContext)


# ---------------------------------------------------------------------------
# R3 cold_start semantics — matched_records == 0
# ---------------------------------------------------------------------------


def test_builder_empty_memory_yields_cold_start_and_empty_examples():
    mem = EpisodicMemory()
    ctx = build_agent_memory_context(
        mem, MemoryQuery(event_type="CARRIER_DELAY"), _default_config()
    )
    assert ctx.matched_records == 0
    assert ctx.cold_start is True
    assert ctx.recent_examples == []
    assert ctx.action_type_distribution == {}
    # Rate / avg fields are None when there are no rows to compute on.
    assert ctx.auto_execute_success_rate is None
    assert ctx.sla_preservation_rate is None
    assert ctx.avg_cost is None


def test_builder_single_match_is_not_cold_start_even_at_low_threshold():
    """R3 decouples B4's cold_start from the adaptive gate's
    threshold. One matched row ⇒ cold_start is False, regardless
    of whatever policy-path threshold might be in use."""
    mem = EpisodicMemory()
    mem.append(_rec(event_id="E1", ts="2026-01-01T00:00:00Z"))
    ctx = build_agent_memory_context(
        mem, MemoryQuery(event_type="CARRIER_DELAY"), _default_config()
    )
    assert ctx.matched_records == 1
    assert ctx.cold_start is False


def test_builder_non_matching_query_gives_cold_start_even_if_memory_nonempty():
    mem = EpisodicMemory()
    mem.append(_rec(event_id="E1", ts="2026-01-01T00:00:00Z"))
    ctx = build_agent_memory_context(
        mem, MemoryQuery(event_type="NONEXISTENT_TYPE"), _default_config()
    )
    assert ctx.matched_records == 0
    assert ctx.cold_start is True


# ---------------------------------------------------------------------------
# Aggregate fields — delegated to summarize_records
# ---------------------------------------------------------------------------


def test_builder_aggregates_match_summarizer_contract():
    mem = EpisodicMemory()
    mem.append(_rec(
        event_id="E1", ts="2026-01-01T00:00:00Z",
        action_taken="EXPEDITE", final_route="AUTO_EXECUTE",
        execution_status="executed", cost=100.0, sla=True,
    ))
    mem.append(_rec(
        event_id="E2", ts="2026-01-01T00:01:00Z",
        action_taken="TRANSFER", final_route="AUTO_EXECUTE",
        execution_status="execution_failed", cost=50.0, sla=False,
    ))
    mem.append(_rec(
        event_id="E3", ts="2026-01-01T00:02:00Z",
        action_taken="COMPENSATE", final_route="HUMAN_REQUIRED",
        execution_status="awaiting_human_review", cost=None, sla=None,
    ))

    ctx = build_agent_memory_context(
        mem, MemoryQuery(event_type="CARRIER_DELAY"), _default_config()
    )

    assert ctx.matched_records == 3
    # 2 AUTO_EXECUTE rows, 1 successful → 0.5
    assert ctx.auto_execute_success_rate == pytest.approx(0.5)
    # 2 rows with sla_preserved not None; 1 True → 0.5
    assert ctx.sla_preservation_rate == pytest.approx(0.5)
    # avg cost over rows with non-None cost_incurred = (100 + 50)/2
    assert ctx.avg_cost == pytest.approx(75.0)
    # Distribution is sorted lexicographically at the summarizer.
    assert ctx.action_type_distribution == {
        "COMPENSATE": 1,
        "EXPEDITE": 1,
        "TRANSFER": 1,
    }
    # Signature embeds the logical query, not schema_version.
    assert "event_type='CARRIER_DELAY'" in ctx.query_signature


# ---------------------------------------------------------------------------
# R4 recent_examples — cap + ordering
# ---------------------------------------------------------------------------


def test_builder_recent_examples_cap_defaults_to_three():
    """With the Slice 1 default config (max_recent_examples=3)
    the builder selects at most 3 rows even when 5 match."""
    mem = EpisodicMemory()
    for i in range(5):
        mem.append(_rec(
            event_id=f"E{i}", ts=f"2026-01-01T00:0{i}:00Z"
        ))
    ctx = build_agent_memory_context(
        mem, MemoryQuery(event_type="CARRIER_DELAY"),
        _default_config(),
    )
    assert ctx.matched_records == 5
    assert len(ctx.recent_examples) == MAX_AGENT_MEMORY_EXAMPLES == 3


def test_builder_recent_examples_are_selected_tail_oldest_to_newest():
    """R4 — selected tail is the most-recent N matches, and the
    ordering *within* the tail preserves canonical order
    (oldest-to-newest inside the tail)."""
    mem = EpisodicMemory()
    # Insert in canonical order E0 → E4; tail of 3 is E2,E3,E4.
    for i in range(5):
        mem.append(_rec(
            event_id=f"E{i}", ts=f"2026-01-01T00:0{i}:00Z"
        ))
    ctx = build_agent_memory_context(
        mem, MemoryQuery(event_type="CARRIER_DELAY"),
        _default_config(),
    )
    event_ids = [ex.event_id for ex in ctx.recent_examples]
    assert event_ids == ["E2", "E3", "E4"]


def test_builder_recent_examples_respect_max_recent_examples_below_cap():
    mem = EpisodicMemory()
    for i in range(5):
        mem.append(_rec(
            event_id=f"E{i}", ts=f"2026-01-01T00:0{i}:00Z"
        ))
    cfg = AgentMemoryExperimentConfig(
        enable_agent_visible_memory=True, max_recent_examples=2
    )
    ctx = build_agent_memory_context(
        mem, MemoryQuery(event_type="CARRIER_DELAY"), cfg
    )
    event_ids = [ex.event_id for ex in ctx.recent_examples]
    assert event_ids == ["E3", "E4"]


def test_builder_insertion_order_does_not_affect_recent_examples():
    """Memory is canonical-sorted by (event_timestamp, event_id);
    the builder must not leak insertion order."""
    mem_a = EpisodicMemory()
    mem_b = EpisodicMemory()
    ids_tss = [("E0", "2026-01-01T00:00:00Z"),
               ("E1", "2026-01-01T00:01:00Z"),
               ("E2", "2026-01-01T00:02:00Z"),
               ("E3", "2026-01-01T00:03:00Z")]
    for eid, ts in ids_tss:
        mem_a.append(_rec(event_id=eid, ts=ts))
    for eid, ts in reversed(ids_tss):
        mem_b.append(_rec(event_id=eid, ts=ts))

    cfg = _default_config()
    q = MemoryQuery(event_type="CARRIER_DELAY")
    ctx_a = build_agent_memory_context(mem_a, q, cfg)
    ctx_b = build_agent_memory_context(mem_b, q, cfg)
    assert ctx_a.model_dump() == ctx_b.model_dump()


# ---------------------------------------------------------------------------
# Example-ref projection — source_session_id
# ---------------------------------------------------------------------------


def test_builder_preserves_source_session_id_per_row():
    mem = EpisodicMemory()
    mem.append(_rec(event_id="E1", ts="2026-01-01T00:00:00Z", session_id="S-PRIOR"))
    mem.append(_rec(event_id="E2", ts="2026-01-01T00:01:00Z", session_id="S-CURRENT"))
    ctx = build_agent_memory_context(
        mem, MemoryQuery(event_type="CARRIER_DELAY"), _default_config()
    )
    sids = [ex.source_session_id for ex in ctx.recent_examples]
    assert sids == ["S-PRIOR", "S-CURRENT"]


def test_builder_projects_all_example_ref_fields_verbatim():
    mem = EpisodicMemory()
    mem.append(_rec(
        event_id="E1", ts="2026-01-01T00:00:00Z",
        event_type="CARRIER_DELAY",
        action_taken="COMPENSATE", execution_status="executed_via_demo_override",
        final_route="HUMAN_REQUIRED", cost=7.5, sla=None, session_id="S-PRIOR",
    ))
    ctx = build_agent_memory_context(
        mem, MemoryQuery(), _default_config()
    )
    assert len(ctx.recent_examples) == 1
    ex = ctx.recent_examples[0]
    assert ex.event_id == "E1"
    assert ex.event_type == "CARRIER_DELAY"
    assert ex.source_session_id == "S-PRIOR"
    assert ex.action_taken == "COMPENSATE"
    assert ex.final_route == "HUMAN_REQUIRED"
    assert ex.execution_status == "executed_via_demo_override"
    assert ex.cost_incurred == 7.5
    assert ex.sla_preserved is None


def test_builder_handles_action_taken_none():
    mem = EpisodicMemory()
    mem.append(_rec(
        event_id="E1", ts="2026-01-01T00:00:00Z",
        action_taken=None, execution_status="awaiting_human_review",
        final_route="HUMAN_REQUIRED", cost=None, sla=None,
    ))
    ctx = build_agent_memory_context(mem, MemoryQuery(), _default_config())
    assert ctx.recent_examples[0].action_taken is None


# ---------------------------------------------------------------------------
# Purity + no mutation
# ---------------------------------------------------------------------------


def test_builder_is_pure_repeat_call_same_inputs_same_output():
    mem = EpisodicMemory()
    for i in range(4):
        mem.append(_rec(event_id=f"E{i}", ts=f"2026-01-01T00:0{i}:00Z"))
    cfg = _default_config()
    q = MemoryQuery(event_type="CARRIER_DELAY")
    ctx_1 = build_agent_memory_context(mem, q, cfg)
    ctx_2 = build_agent_memory_context(mem, q, cfg)
    assert ctx_1.model_dump() == ctx_2.model_dump()


def test_builder_does_not_mutate_memory_snapshot():
    mem = EpisodicMemory()
    for i in range(3):
        mem.append(_rec(event_id=f"E{i}", ts=f"2026-01-01T00:0{i}:00Z"))
    before_snapshot = copy.deepcopy(mem.snapshot())
    _ = build_agent_memory_context(
        mem, MemoryQuery(event_type="CARRIER_DELAY"), _default_config()
    )
    assert mem.snapshot() == before_snapshot


def test_builder_does_not_mutate_query_or_config():
    mem = EpisodicMemory()
    mem.append(_rec(event_id="E1", ts="2026-01-01T00:00:00Z"))
    q = MemoryQuery(event_type="CARRIER_DELAY")
    q_before = q.model_dump()
    cfg = _default_config()
    cfg_before = (
        cfg.enable_agent_visible_memory,
        cfg.target_agent,
        cfg.context_source,
        cfg.max_recent_examples,
        frozenset(cfg.allowed_modes),
        cfg.schema_version,
    )
    _ = build_agent_memory_context(mem, q, cfg)
    assert q.model_dump() == q_before
    assert (
        cfg.enable_agent_visible_memory,
        cfg.target_agent,
        cfg.context_source,
        cfg.max_recent_examples,
        frozenset(cfg.allowed_modes),
        cfg.schema_version,
    ) == cfg_before


# ---------------------------------------------------------------------------
# Forbidden-import source scan — light AST guard
# ---------------------------------------------------------------------------


_BUILDER_PATH = os.path.join(
    _PROJECT_DIR, "src", "agent_memory", "agent_memory_builder.py"
)

_FORBIDDEN_IMPORT_PREFIXES = [
    ("agents",),
    ("adaptive",),
    ("replan",),
    ("correlator",),
    ("learning", "cumulative_memory"),
    ("session",),
    ("evaluation",),
    ("action_code_mapper",),
]


def _module_matches_prefix(module: str, prefix: tuple[str, ...]) -> bool:
    parts = [p for p in module.split(".") if p]
    if parts[:1] == ["src"]:
        parts = parts[1:]
    return tuple(parts[: len(prefix)]) == prefix


def test_builder_source_has_no_forbidden_imports():
    with open(_BUILDER_PATH, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                if _module_matches_prefix(mod, prefix):
                    findings.append(f"from {mod} import ...")
                    break
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                    if _module_matches_prefix(alias.name, prefix):
                        findings.append(f"import {alias.name}")
                        break
    assert not findings, f"builder leaks forbidden imports: {findings!r}"
