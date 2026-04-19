"""Phase 2: AdjustmentRule purity + contract tests.

Rules are pure functions: ``(MemorySummary, event_context) ->
AdaptivePolicyAdjustment | None``. No I/O, no memory access, no
nondeterminism.
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
    DEFAULT_RULES,
    EventContext,
    KNOWN_RULE_IDS,
    POOR_SLA_UPGRADE_RULE_ID,
    POOR_SLA_UPGRADE_THRESHOLD,
    _poor_sla_upgrade_rule,
)
from learning.memory_schema import MemorySummary


def _summary(
    *,
    matched=10,
    sla_rate=0.1,
    auto_rate=0.5,
    avg_cost=100.0,
    distribution=None,
    sig="MemoryQuery(event_type='CARRIER_DELAY_ESCALATION')",
) -> MemorySummary:
    return MemorySummary(
        matched_records=matched,
        cold_start=False,
        auto_execute_success_rate=auto_rate,
        sla_preservation_rate=sla_rate,
        action_type_distribution=distribution or {"EXPEDITE": matched},
        avg_cost=avg_cost,
        query_signature=sig,
    )


def _ctx(risk="LOW", event_type="CARRIER_DELAY_ESCALATION") -> EventContext:
    return EventContext(
        event_id="EVT-1",
        event_type=event_type,
        severity="LOW",
        risk_level=risk,
    )


class TestPurityAndDeterminism:
    def test_same_input_same_output(self):
        s = _summary()
        c = _ctx()
        a = _poor_sla_upgrade_rule(s, c)
        b = _poor_sla_upgrade_rule(s, c)
        assert a is not None
        assert a.model_dump() == b.model_dump()

    def test_no_side_effects_on_inputs(self):
        s = _summary()
        c = _ctx()
        s_before = s.model_dump()
        _poor_sla_upgrade_rule(s, c)
        assert s.model_dump() == s_before


class TestFireConditions:
    def test_fires_when_sla_rate_below_threshold(self):
        adj = _poor_sla_upgrade_rule(_summary(sla_rate=0.0), _ctx("LOW"))
        assert adj is not None
        assert adj.adjustment_type == "UPGRADE_ONE_LEVEL"
        assert adj.pre_adjustment_risk == "LOW"
        assert adj.post_adjustment_risk == "MEDIUM"

    def test_fires_medium_to_high(self):
        adj = _poor_sla_upgrade_rule(_summary(sla_rate=0.1), _ctx("MEDIUM"))
        assert adj is not None
        assert adj.pre_adjustment_risk == "MEDIUM"
        assert adj.post_adjustment_risk == "HIGH"

    def test_never_jumps_two_levels(self):
        """LOW should only go to MEDIUM, never to HIGH."""
        adj = _poor_sla_upgrade_rule(_summary(sla_rate=0.0), _ctx("LOW"))
        assert adj is not None
        assert adj.post_adjustment_risk != "HIGH"

    def test_high_does_not_upgrade(self):
        """HIGH has no upgrade target — rule returns None."""
        adj = _poor_sla_upgrade_rule(_summary(sla_rate=0.0), _ctx("HIGH"))
        assert adj is None

    def test_does_not_fire_when_rate_at_threshold(self):
        adj = _poor_sla_upgrade_rule(
            _summary(sla_rate=POOR_SLA_UPGRADE_THRESHOLD), _ctx("LOW"),
        )
        assert adj is None

    def test_does_not_fire_when_rate_above_threshold(self):
        adj = _poor_sla_upgrade_rule(_summary(sla_rate=0.9), _ctx("LOW"))
        assert adj is None

    def test_does_not_fire_when_rate_is_none(self):
        adj = _poor_sla_upgrade_rule(_summary(sla_rate=None), _ctx("LOW"))
        assert adj is None

    def test_does_not_fire_when_matched_zero(self):
        adj = _poor_sla_upgrade_rule(_summary(matched=0, sla_rate=0.0), _ctx("LOW"))
        assert adj is None


class TestEvidenceAndRegistry:
    def test_memory_evidence_numerically_correct(self):
        s = _summary(matched=10, sla_rate=0.1)
        adj = _poor_sla_upgrade_rule(s, _ctx("LOW"))
        assert adj is not None
        assert adj.memory_evidence["matched_records"] == 10
        assert adj.memory_evidence["sla_preservation_rate"] == 0.1
        assert adj.memory_evidence["threshold_rate"] == POOR_SLA_UPGRADE_THRESHOLD

    def test_rule_id_in_known_registry(self):
        adj = _poor_sla_upgrade_rule(_summary(sla_rate=0.1), _ctx("LOW"))
        assert adj is not None
        assert adj.rule_id == POOR_SLA_UPGRADE_RULE_ID
        assert adj.rule_id in KNOWN_RULE_IDS

    def test_query_signature_non_empty(self):
        adj = _poor_sla_upgrade_rule(_summary(sla_rate=0.1), _ctx("LOW"))
        assert adj is not None
        assert adj.query_signature
        assert adj.query_signature == _summary(sla_rate=0.1).query_signature


class TestNoDowngrade:
    def test_default_rules_never_produce_downgrade_type(self):
        """Bounded action set: no DOWNGRADE_* allowed."""
        for rule in DEFAULT_RULES:
            # Exercise across LOW/MEDIUM/HIGH and range of sla rates
            for risk in ("LOW", "MEDIUM", "HIGH"):
                for sla in (0.0, 0.25, 0.5, 0.75, 1.0, None):
                    adj = rule(_summary(sla_rate=sla), _ctx(risk))
                    if adj is None:
                        continue
                    assert not adj.adjustment_type.startswith("DOWNGRADE")
                    assert adj.adjustment_type in {
                        "UPGRADE_ONE_LEVEL",
                        "NO_ADJUSTMENT",
                        "COLD_START_FALLBACK",
                    }
