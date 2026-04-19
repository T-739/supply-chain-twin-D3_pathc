"""Phase 2: structural explainability of AdaptivePolicyAdjustment.

Explicit non-goals (per Roadmap §2.E, owner point 7):
  - NO length-based test on any free-text field.
  - NO fuzzy-match on notes / reasons.

Structural asserts only:
  - rule_id non-empty AND present in KNOWN_RULE_IDS.
  - query_signature non-empty.
  - memory_evidence contains at least one of
    {matched_records, auto_execute_success_rate, sla_preservation_rate},
    and at least one value is numerically consistent with the
    referenced memory slice.
  - pre_adjustment_risk != post_adjustment_risk iff
    adjustment_type == "UPGRADE_ONE_LEVEL".
  - Replaying the rule against the same memory slice reproduces the
    same fire/no-fire outcome.
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
    KNOWN_RULE_IDS,
)
from adaptive.adaptive_policy_gate import (
    _build_query_for_event,
    decide_policy_adaptive,
)
from event_engine import generate_demo_event_stream
from event_loop_c import run_session
from learning.episodic_memory import EpisodicMemory
from learning.memory_schema import MemoryRecord


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


_EVIDENCE_KEYS = {"matched_records", "auto_execute_success_rate", "sla_preservation_rate"}


def _seed(n: int = 10) -> EpisodicMemory:
    mem = EpisodicMemory()
    for i in range(n):
        mem.append(MemoryRecord(
            event_id=f"SEED-{i:03d}",
            event_type="CARRIER_DELAY_ESCALATION",
            event_timestamp=f"2026-02-{(i % 28) + 1:02d}T10:00:00+00:00",
            action_taken="EXPEDITE",
            execution_status="executed",
            final_route="AUTO_EXECUTE",
            cost_incurred=150.0,
            sla_preserved=False,
            risk_level="LOW",
            session_id="SEED",
        ))
    return mem


def _collect_adjustments(artifact):
    return [ser.adaptive_adjustment for ser in artifact.event_records if ser.adaptive_adjustment is not None]


class TestStructuralExplainability:
    def test_all_fired_adjustments_have_structural_fields(self):
        warm = run_session(seed=42, mode="PATH_C_WARM", initial_memory=_seed())
        adjustments = _collect_adjustments(warm)
        assert adjustments, "warm run must produce adjustments"

        for adj in adjustments:
            # rule_id
            assert adj.rule_id
            assert adj.rule_id in KNOWN_RULE_IDS

            # query_signature
            assert adj.query_signature

            # memory_evidence present and informative
            ev = adj.memory_evidence
            assert isinstance(ev, dict) and ev, "memory_evidence must be non-empty dict"
            # cold-start uses {matched_records, min_records_for_shift};
            # upgrade uses {matched_records, sla_preservation_rate, threshold_rate}.
            if adj.adjustment_type in ("UPGRADE_ONE_LEVEL", "COLD_START_FALLBACK"):
                assert _EVIDENCE_KEYS & set(ev.keys()), (
                    f"memory_evidence {ev} must include at least one of "
                    f"{_EVIDENCE_KEYS}"
                )

    def test_pre_post_differ_iff_upgrade(self):
        warm = run_session(seed=42, mode="PATH_C_WARM", initial_memory=_seed())
        for adj in _collect_adjustments(warm):
            differ = adj.pre_adjustment_risk != adj.post_adjustment_risk
            assert differ == (adj.adjustment_type == "UPGRADE_ONE_LEVEL"), (
                f"adjustment_type={adj.adjustment_type} pre={adj.pre_adjustment_risk} "
                f"post={adj.post_adjustment_risk} violates pre!=post iff UPGRADE_ONE_LEVEL"
            )


class TestReplayability:
    def test_replay_same_memory_slice_same_fire_outcome(self):
        """Re-run decide_policy_adaptive with the same memory snapshot;
        fire / no-fire must reproduce exactly."""
        seed_mem = _seed()
        cfg = AdaptivePolicyGateConfig(min_records_for_shift=3)

        # First pass
        events = generate_demo_event_stream()
        gov = {"risk_level": "LOW", "recommended_action": "EXPEDITE: x"}
        ctx = EventContext(
            event_id="REPLAY-EVT", event_type="CARRIER_DELAY_ESCALATION",
            severity="LOW", risk_level="LOW",
        )
        d1, a1 = decide_policy_adaptive(gov, ctx, seed_mem, cfg)

        # Replay — identical memory, identical inputs → identical outcome.
        d2, a2 = decide_policy_adaptive(gov, ctx, seed_mem, cfg)

        assert (a1 is None) == (a2 is None)
        if a1 is not None and a2 is not None:
            assert a1.model_dump() == a2.model_dump()
        assert d1.model_dump() == d2.model_dump()

    def test_numerical_evidence_consistent_with_memory_slice(self):
        """sla_preservation_rate in memory_evidence matches what the query
        would see when run against the same memory."""
        from learning.memory_summarizer import summarize_records

        seed_mem = _seed(10)
        cfg = AdaptivePolicyGateConfig(min_records_for_shift=3)
        ctx = EventContext(
            event_id="E", event_type="CARRIER_DELAY_ESCALATION",
            severity="LOW", risk_level="LOW",
        )
        q = _build_query_for_event(ctx)
        summary = summarize_records(
            seed_mem.query(q), q, threshold=cfg.min_records_for_shift,
        )

        _, adj = decide_policy_adaptive({"risk_level": "LOW"}, ctx, seed_mem, cfg)
        assert adj is not None
        assert adj.adjustment_type == "UPGRADE_ONE_LEVEL"
        # memory_evidence must be numerically consistent with the slice.
        assert adj.memory_evidence["matched_records"] == summary.matched_records
        assert adj.memory_evidence["sla_preservation_rate"] == summary.sla_preservation_rate
