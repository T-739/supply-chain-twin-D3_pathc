"""Phase 2: decide_policy_adaptive contract tests."""

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
from adaptive.cold_start import COLD_START_RULE_ID
from learning.episodic_memory import EpisodicMemory
from learning.memory_schema import MemoryRecord
from policy_gate import PolicyDecision, PolicyRoute, RiskLevel


_EVENT_TYPE = "CARRIER_DELAY_ESCALATION"


def _poor_sla_record(i: int) -> MemoryRecord:
    return MemoryRecord(
        event_id=f"SEED-{i:03d}",
        event_type=_EVENT_TYPE,
        event_timestamp=f"2026-03-0{(i % 9) + 1}T10:00:00+00:00",
        action_taken="EXPEDITE",
        execution_status="executed",
        final_route="AUTO_EXECUTE",
        cost_incurred=200.0,
        sla_preserved=False,
        risk_level="LOW",
        session_id="SEED-SESSION",
    )


def _good_sla_record(i: int) -> MemoryRecord:
    r = _poor_sla_record(i)
    return MemoryRecord(
        **{**r.model_dump(), "sla_preserved": True, "event_id": f"GOOD-{i:03d}"}
    )


def _event_ctx(risk: str = "LOW") -> EventContext:
    return EventContext(
        event_id="EVT-LIVE",
        event_type=_EVENT_TYPE,
        severity="LOW",
        risk_level=risk,
    )


def _gov(risk: str = "LOW") -> dict:
    return {"risk_level": risk, "recommended_action": "EXPEDITE: x"}


class TestShapeAndNoMutation:
    def test_returns_policy_decision_and_optional_adjustment(self):
        mem = EpisodicMemory()
        cfg = AdaptivePolicyGateConfig()
        decision, adj = decide_policy_adaptive(_gov("LOW"), _event_ctx(), mem, cfg)
        assert isinstance(decision, PolicyDecision)
        assert adj is None or adj.rule_id

    def test_policy_decision_shape_unchanged(self):
        mem = EpisodicMemory()
        cfg = AdaptivePolicyGateConfig()
        decision, _ = decide_policy_adaptive(_gov("LOW"), _event_ctx(), mem, cfg)
        assert set(decision.model_fields.keys()) == {
            "route", "risk_level", "requires_human_review",
            "reason", "policy_config_version",
        }

    def test_governance_output_is_not_mutated(self):
        mem = EpisodicMemory([_poor_sla_record(i) for i in range(10)])
        cfg = AdaptivePolicyGateConfig()
        gov = _gov("LOW")
        snapshot = dict(gov)
        decide_policy_adaptive(gov, _event_ctx("LOW"), mem, cfg)
        assert gov == snapshot


class TestColdStartReturnsFallback:
    def test_cold_start_returns_baseline_and_fallback_adjustment(self):
        mem = EpisodicMemory()
        cfg = AdaptivePolicyGateConfig(min_records_for_shift=3)
        decision, adj = decide_policy_adaptive(_gov("LOW"), _event_ctx(), mem, cfg)
        assert adj is not None
        assert adj.adjustment_type == "COLD_START_FALLBACK"
        assert adj.rule_id == COLD_START_RULE_ID
        assert adj.pre_adjustment_risk == adj.post_adjustment_risk
        assert decision.route == PolicyRoute.AUTO_EXECUTE  # LOW -> AUTO_EXECUTE, unshifted


class TestUpgradeOnFire:
    def test_warm_poor_sla_memory_upgrades_low_to_medium(self):
        mem = EpisodicMemory([_poor_sla_record(i) for i in range(10)])
        cfg = AdaptivePolicyGateConfig(min_records_for_shift=3)
        decision, adj = decide_policy_adaptive(_gov("LOW"), _event_ctx("LOW"), mem, cfg)
        assert adj is not None
        assert adj.adjustment_type == "UPGRADE_ONE_LEVEL"
        assert adj.pre_adjustment_risk == "LOW"
        assert adj.post_adjustment_risk == "MEDIUM"
        assert decision.risk_level == RiskLevel.MEDIUM
        assert decision.route == PolicyRoute.HUMAN_REQUIRED

    def test_never_jumps_two_levels(self):
        mem = EpisodicMemory([_poor_sla_record(i) for i in range(10)])
        cfg = AdaptivePolicyGateConfig(min_records_for_shift=3)
        decision, adj = decide_policy_adaptive(_gov("LOW"), _event_ctx("LOW"), mem, cfg)
        assert adj.post_adjustment_risk != "HIGH"

    def test_good_memory_does_not_fire(self):
        mem = EpisodicMemory([_good_sla_record(i) for i in range(10)])
        cfg = AdaptivePolicyGateConfig(min_records_for_shift=3)
        decision, adj = decide_policy_adaptive(_gov("LOW"), _event_ctx("LOW"), mem, cfg)
        assert adj is None
        assert decision.route == PolicyRoute.AUTO_EXECUTE


class TestDifferentEventTypeIsolation:
    def test_weather_event_does_not_see_carrier_records(self):
        mem = EpisodicMemory([_poor_sla_record(i) for i in range(10)])
        cfg = AdaptivePolicyGateConfig(min_records_for_shift=3)
        ctx = EventContext(
            event_id="EVT-W", event_type="WEATHER_WORSENING",
            severity="MEDIUM", risk_level="MEDIUM",
        )
        _, adj = decide_policy_adaptive(_gov("MEDIUM"), ctx, mem, cfg)
        # WEATHER_WORSENING records: 0 in memory → cold start.
        assert adj is not None
        assert adj.adjustment_type == "COLD_START_FALLBACK"
