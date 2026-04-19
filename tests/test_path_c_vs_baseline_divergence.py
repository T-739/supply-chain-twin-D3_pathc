"""Phase 2: R1 validation — Path C warm session diverges from baseline.

Seeds memory with 10 poor-performing CARRIER_DELAY_ESCALATION
auto-execute records, runs the demo stream under BASELINE_STATIC and
PATH_C_WARM, and asserts at least one event diverges at the effective
decision level with a non-None adaptive_adjustment on every divergent
event.
"""

from __future__ import annotations

import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from event_engine import generate_demo_event_stream
from event_loop_c import run_session
from learning.episodic_memory import EpisodicMemory
from learning.memory_schema import MemoryRecord


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


def _seed_memory_poor_carrier_delays(n: int = 10) -> EpisodicMemory:
    mem = EpisodicMemory()
    for i in range(n):
        mem.append(MemoryRecord(
            event_id=f"SEED-{i:03d}",
            event_type="CARRIER_DELAY_ESCALATION",
            event_timestamp=f"2026-02-{(i % 28) + 1:02d}T10:00:00+00:00",
            action_taken="EXPEDITE",
            execution_status="executed",
            final_route="AUTO_EXECUTE",
            cost_incurred=250.0,
            sla_preserved=False,
            risk_level="LOW",
            session_id="SEED-SESSION",
        ))
    return mem


def test_warm_seeded_memory_produces_divergence():
    seed_memory = _seed_memory_poor_carrier_delays(10)

    baseline = run_session(seed=42, mode="BASELINE_STATIC")
    warm = run_session(
        seed=42, mode="PATH_C_WARM",
        initial_memory=seed_memory,
    )

    assert len(baseline.event_records) == len(warm.event_records)

    divergent_indices = []
    for i, (b, w) in enumerate(zip(baseline.event_records, warm.event_records)):
        b_route = b.effective_decision.final_route
        w_route = w.effective_decision.final_route
        if b_route != w_route or b.effective_decision.effective_risk != w.effective_decision.effective_risk:
            divergent_indices.append(i)
            # Every divergence must be explained by an adaptive_adjustment.
            assert w.adaptive_adjustment is not None, (
                f"event {i} diverges but has no adaptive_adjustment"
            )
            assert w.adaptive_adjustment.adjustment_type == "UPGRADE_ONE_LEVEL"
            assert w.policy_route_source == "adaptive_adjusted"

    assert divergent_indices, (
        "PATH_C_WARM with seeded poor-SLA memory must diverge from "
        "BASELINE_STATIC on at least one event"
    )


def test_baseline_event_result_still_byte_equal_in_warm_mode():
    """baseline_event_result is the Path B shadow — independent of mode."""
    seed_memory = _seed_memory_poor_carrier_delays(10)
    warm = run_session(
        seed=42, mode="PATH_C_WARM",
        initial_memory=seed_memory,
    )

    from event_loop import run_event_loop
    direct = run_event_loop(generate_demo_event_stream())

    for ser, er in zip(warm.event_records, direct["event_results"]):
        assert ser.baseline_event_result == er


def test_divergent_events_do_not_modify_baseline_event_result():
    """preflight_failed / adaptive divergence never leaks into baseline_event_result."""
    seed_memory = _seed_memory_poor_carrier_delays(10)
    warm = run_session(
        seed=42, mode="PATH_C_WARM",
        initial_memory=seed_memory,
    )
    for ser in warm.event_records:
        assert "preflight_failed" not in str(ser.baseline_event_result)
