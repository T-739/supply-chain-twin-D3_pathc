"""B4 Slice 2A: deterministic renderer tests.

Covers R5 (signature + deterministic output), R6 (format
rules), plus a subprocess-level determinism test and a forbidden-
narrative-token guard.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from agent_memory.agent_memory_config import AgentMemoryExperimentConfig
from agent_memory.agent_memory_renderer import render_agent_memory_context
from agent_memory.agent_memory_schema import (
    AgentMemoryContext,
    AgentMemoryExampleRef,
)


def _cfg() -> AgentMemoryExperimentConfig:
    return AgentMemoryExperimentConfig(enable_agent_visible_memory=True)


def _context_empty() -> AgentMemoryContext:
    return AgentMemoryContext(
        matched_records=0,
        cold_start=True,
        query_signature="sig-empty",
    )


def _context_full() -> AgentMemoryContext:
    return AgentMemoryContext(
        matched_records=3,
        cold_start=False,
        query_signature="sig-demo",
        auto_execute_success_rate=2 / 3,
        sla_preservation_rate=1 / 3,
        avg_cost=42.5,
        action_type_distribution={"EXPEDITE": 2, "COMPENSATE": 1},
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
                action_taken=None, final_route="HUMAN_REQUIRED",
                execution_status="awaiting_human_review",
                cost_incurred=None, sla_preserved=None,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# R5 — header, field ordering, deterministic bytes
# ---------------------------------------------------------------------------


def test_renderer_starts_with_fixed_header():
    out = render_agent_memory_context(_context_empty(), _cfg())
    assert out.startswith("AGENT_MEMORY_CONTEXT\n")


def test_renderer_field_order_is_locked():
    out = render_agent_memory_context(_context_full(), _cfg())
    # Split into lines and check the fixed order of the
    # single-value prefix block.
    lines = out.splitlines()
    # Locked prefix order per R6.
    expected_prefix = [
        "AGENT_MEMORY_CONTEXT",
        "matched_records: 3",
        "cold_start: false",
        "query_signature: sig-demo",
    ]
    assert lines[:4] == expected_prefix
    # The next three lines are the rate / cost numeric block, in
    # locked order.
    assert lines[4] == "auto_execute_success_rate: " + str(round(2 / 3, 4))
    assert lines[5] == "sla_preservation_rate: " + str(round(1 / 3, 4))
    assert lines[6] == "avg_cost: 42.5"


def test_renderer_two_calls_produce_identical_bytes():
    ctx = _context_full()
    cfg = _cfg()
    out_a = render_agent_memory_context(ctx, cfg)
    out_b = render_agent_memory_context(ctx, cfg)
    assert out_a == out_b


def test_renderer_ignores_config_values_for_output_bytes():
    """R5 — Slice 2A renderer must not branch on config values.
    Two different configs producing the same context must emit
    identical bytes."""
    ctx = _context_full()
    cfg_a = AgentMemoryExperimentConfig(enable_agent_visible_memory=True)
    cfg_b = AgentMemoryExperimentConfig(
        enable_agent_visible_memory=False, max_recent_examples=1
    )
    assert (
        render_agent_memory_context(ctx, cfg_a)
        == render_agent_memory_context(ctx, cfg_b)
    )


def test_renderer_has_no_trailing_newline():
    out = render_agent_memory_context(_context_full(), _cfg())
    assert not out.endswith("\n")


# ---------------------------------------------------------------------------
# R6 — None → "n/a", rounding, distribution sort, empty examples
# ---------------------------------------------------------------------------


def test_renderer_renders_none_rates_as_na():
    ctx = AgentMemoryContext(
        matched_records=1,
        cold_start=False,
        query_signature="sig",
        auto_execute_success_rate=None,
        sla_preservation_rate=None,
        avg_cost=None,
        action_type_distribution={},
        recent_examples=[],
    )
    out = render_agent_memory_context(ctx, _cfg())
    assert "auto_execute_success_rate: n/a" in out
    assert "sla_preservation_rate: n/a" in out
    assert "avg_cost: n/a" in out


def test_renderer_rounds_rates_to_four_decimals():
    ctx = AgentMemoryContext(
        matched_records=3,
        cold_start=False,
        query_signature="sig",
        auto_execute_success_rate=1 / 3,
        sla_preservation_rate=2 / 3,
        avg_cost=1 / 7,
    )
    out = render_agent_memory_context(ctx, _cfg())
    assert "auto_execute_success_rate: " + str(round(1 / 3, 4)) in out
    assert "sla_preservation_rate: " + str(round(2 / 3, 4)) in out
    assert "avg_cost: " + str(round(1 / 7, 4)) in out


def test_renderer_emits_distribution_keys_in_lexicographic_order():
    ctx = AgentMemoryContext(
        matched_records=4,
        cold_start=False,
        query_signature="sig",
        action_type_distribution={"TRANSFER": 1, "EXPEDITE": 2, "COMPENSATE": 1},
    )
    out = render_agent_memory_context(ctx, _cfg())
    lines = out.splitlines()
    dist_start = lines.index("action_type_distribution:")
    assert lines[dist_start + 1].strip() == "COMPENSATE: 1"
    assert lines[dist_start + 2].strip() == "EXPEDITE: 2"
    assert lines[dist_start + 3].strip() == "TRANSFER: 1"


def test_renderer_emits_empty_distribution_marker():
    out = render_agent_memory_context(_context_empty(), _cfg())
    assert "action_type_distribution: (none)" in out


def test_renderer_emits_empty_examples_marker():
    out = render_agent_memory_context(_context_empty(), _cfg())
    assert "recent_examples: none" in out
    # Empty marker is a single line, not a header with an empty
    # indented block.
    assert "recent_examples:\n" not in out


def test_renderer_numbers_recent_examples_from_one():
    out = render_agent_memory_context(_context_full(), _cfg())
    assert "  1. event_id=E1 " in out
    assert "  2. event_id=E2 " in out


def test_renderer_example_fields_are_in_locked_order():
    out = render_agent_memory_context(_context_full(), _cfg())
    # Single line for the first example; fields are "|"-joined
    # in a fixed order per R6 and the renderer helper.
    example_line = next(
        ln for ln in out.splitlines() if ln.startswith("  1. ")
    )
    idx = lambda tok: example_line.index(tok)
    for a, b in (
        ("event_id=", "event_type="),
        ("event_type=", "source_session_id="),
        ("source_session_id=", "action_taken="),
        ("action_taken=", "final_route="),
        ("final_route=", "execution_status="),
        ("execution_status=", "cost_incurred="),
        ("cost_incurred=", "sla_preserved="),
    ):
        assert idx(a) < idx(b), (
            f"example field order broke at {a} / {b}: {example_line!r}"
        )


def test_renderer_example_renders_none_fields_as_na():
    out = render_agent_memory_context(_context_full(), _cfg())
    # Example 2 has action_taken, cost_incurred, sla_preserved
    # all None — should each render as n/a.
    example_line = next(
        ln for ln in out.splitlines() if ln.startswith("  2. ")
    )
    assert "action_taken=n/a" in example_line
    assert "cost_incurred=n/a" in example_line
    assert "sla_preserved=n/a" in example_line


def test_renderer_example_renders_bool_sla_as_lowercase():
    out = render_agent_memory_context(_context_full(), _cfg())
    example_line = next(
        ln for ln in out.splitlines() if ln.startswith("  1. ")
    )
    assert "sla_preserved=true" in example_line


# ---------------------------------------------------------------------------
# No forbidden narrative tokens
# ---------------------------------------------------------------------------


_FORBIDDEN_NARRATIVE_TOKENS = ["therefore", "recommend", "because", "confidence"]


@pytest.mark.parametrize("token", _FORBIDDEN_NARRATIVE_TOKENS)
def test_renderer_output_has_no_forbidden_narrative_token(token):
    # Exercise both the empty and full contexts to be sure the
    # token does not sneak in via any branch.
    for ctx in (_context_empty(), _context_full()):
        out = render_agent_memory_context(ctx, _cfg())
        assert token not in out.lower(), (
            f"renderer emitted forbidden narrative token {token!r} in "
            f"output: {out!r}"
        )


# ---------------------------------------------------------------------------
# Subprocess-level determinism (fresh PYTHONHASHSEED)
# ---------------------------------------------------------------------------


_SUBPROCESS_DRIVER = textwrap.dedent(
    """
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
    from agent_memory.agent_memory_config import AgentMemoryExperimentConfig
    from agent_memory.agent_memory_renderer import render_agent_memory_context
    from agent_memory.agent_memory_schema import (
        AgentMemoryContext, AgentMemoryExampleRef,
    )
    ctx = AgentMemoryContext(
        matched_records=3, cold_start=False, query_signature="sig-demo",
        auto_execute_success_rate=2/3, sla_preservation_rate=1/3, avg_cost=42.5,
        action_type_distribution={"EXPEDITE": 2, "COMPENSATE": 1, "TRANSFER": 3},
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
                action_taken=None, final_route="HUMAN_REQUIRED",
                execution_status="awaiting_human_review",
                cost_incurred=None, sla_preserved=None,
            ),
        ],
    )
    cfg = AgentMemoryExperimentConfig(enable_agent_visible_memory=True)
    sys.stdout.write(render_agent_memory_context(ctx, cfg))
    sys.stdout.flush()
    """
).strip()


def _run_in_subprocess(hashseed: str) -> str:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = hashseed
    # Use a tmp driver file so __file__ math works inside the
    # subprocess.
    driver = os.path.join(
        _PROJECT_DIR, "tests", "_agent_memory_renderer_subprocess_driver.py"
    )
    try:
        with open(driver, "w", encoding="utf-8") as f:
            f.write(_SUBPROCESS_DRIVER)
        result = subprocess.run(
            [sys.executable, driver],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
    finally:
        if os.path.exists(driver):
            os.remove(driver)
    return result.stdout


def test_renderer_subprocess_determinism_across_hashseeds():
    out_a = _run_in_subprocess("0")
    out_b = _run_in_subprocess("123456789")
    out_c = _run_in_subprocess("random")
    assert out_a == out_b == out_c, (
        f"renderer output drifted across subprocess runs: "
        f"{out_a!r} vs {out_b!r} vs {out_c!r}"
    )


# ---------------------------------------------------------------------------
# Optional: builder → renderer roundtrip surface
# ---------------------------------------------------------------------------


def test_builder_then_renderer_chain_is_deterministic():
    from agent_memory.agent_memory_builder import build_agent_memory_context
    from learning.episodic_memory import EpisodicMemory
    from learning.memory_schema import MemoryQuery, MemoryRecord

    mem = EpisodicMemory()
    for i, action in enumerate(
        ("EXPEDITE", "TRANSFER", "EXPEDITE", "COMPENSATE", "EXPEDITE")
    ):
        mem.append(MemoryRecord(
            event_id=f"E{i}",
            event_type="CARRIER_DELAY",
            event_timestamp=f"2026-01-01T00:0{i}:00Z",
            action_taken=action,
            execution_status="executed",
            final_route="AUTO_EXECUTE",
            cost_incurred=float(10 * (i + 1)),
            sla_preserved=(i % 2 == 0),
            risk_level="LOW",
            session_id="S1",
        ))

    q = MemoryQuery(event_type="CARRIER_DELAY")
    cfg = _cfg()
    ctx = build_agent_memory_context(mem, q, cfg)
    out_1 = render_agent_memory_context(ctx, cfg)
    out_2 = render_agent_memory_context(ctx, cfg)
    out_3 = render_agent_memory_context(
        build_agent_memory_context(mem, q, cfg), cfg
    )
    assert out_1 == out_2 == out_3
