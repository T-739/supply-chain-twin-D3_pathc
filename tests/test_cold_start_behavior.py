"""Phase 2: cold-start guard behavior, parameterized on min_records_for_shift.

Explicitly avoids any "first 3 events" hard-coding. Runs the matrix
across at least two ``N`` values per the Roadmap §2.E requirement.
"""

from __future__ import annotations

import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from adaptive.adaptive_policy_config import (
    AdaptivePolicyGateConfig,
    EventContext,
)
from adaptive.adaptive_policy_gate import decide_policy_adaptive
from adaptive.cold_start import is_cold_start
from event_loop_c import run_session
from learning.episodic_memory import EpisodicMemory
from learning.memory_schema import MemoryRecord


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


@pytest.mark.parametrize("n", [1, 3, 5, 10])
def test_is_cold_start_boundary(n):
    assert is_cold_start(n - 1, n) is True
    assert is_cold_start(n, n) is False
    assert is_cold_start(n + 1, n) is False


def _poor_sla_record(i: int) -> MemoryRecord:
    return MemoryRecord(
        event_id=f"SEED-{i:04d}",
        event_type="CARRIER_DELAY_ESCALATION",
        event_timestamp=f"2026-02-0{(i % 9) + 1}T10:00:00+00:00",
        action_taken="EXPEDITE",
        execution_status="executed",
        final_route="AUTO_EXECUTE",
        cost_incurred=200.0,
        sla_preserved=False,
        risk_level="LOW",
        session_id="SEED",
    )


class TestGateColdStartParameterized:
    @pytest.mark.parametrize("n", [3, 5])
    def test_below_threshold_returns_cold_fallback(self, n):
        mem = EpisodicMemory([_poor_sla_record(i) for i in range(n - 1)])
        cfg = AdaptivePolicyGateConfig(min_records_for_shift=n)
        ctx = EventContext(
            event_id="E", event_type="CARRIER_DELAY_ESCALATION",
            severity="LOW", risk_level="LOW",
        )
        _, adj = decide_policy_adaptive({"risk_level": "LOW"}, ctx, mem, cfg)
        assert adj is not None
        assert adj.adjustment_type == "COLD_START_FALLBACK"

    @pytest.mark.parametrize("n", [3, 5])
    def test_at_threshold_is_first_eligible_sample(self, n):
        mem = EpisodicMemory([_poor_sla_record(i) for i in range(n)])
        cfg = AdaptivePolicyGateConfig(min_records_for_shift=n)
        ctx = EventContext(
            event_id="E", event_type="CARRIER_DELAY_ESCALATION",
            severity="LOW", risk_level="LOW",
        )
        _, adj = decide_policy_adaptive({"risk_level": "LOW"}, ctx, mem, cfg)
        # At matched == n, the default poor-SLA rule fires (UPGRADE_ONE_LEVEL).
        assert adj is not None
        assert adj.adjustment_type == "UPGRADE_ONE_LEVEL"


class TestPathCColdSessionParameterized:
    """First ``min_records_for_shift`` events must stay in
    ``{baseline_static, cold_start_fallback}`` under PATH_C_COLD with
    empty seed memory.
    """

    @pytest.mark.parametrize("n", [3, 5])
    def test_cold_phase_policy_route_source(self, n):
        artifact = run_session(
            seed=42,
            mode="PATH_C_COLD",
            adaptive_config=AdaptivePolicyGateConfig(min_records_for_shift=n),
        )
        cold_phase = artifact.event_records[:n]
        for ser in cold_phase:
            assert ser.policy_route_source in (
                "baseline_static", "cold_start_fallback",
            ), (
                f"cold-phase event {ser.baseline_event_result.get('event_id')} "
                f"must not use adaptive_adjusted, got "
                f"{ser.policy_route_source!r}"
            )
