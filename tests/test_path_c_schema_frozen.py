"""Phase 0 + B1 Slice 1: Path C schema shape freeze.

Checks, for each Path C schema:
  - expected field set exactly matches
  - schema_version default equals EXPECTED_SCHEMA_VERSION[name]
  - JSON roundtrip via the stored sample is lossless

Most schemas pin "1.0". SessionEventRecord is additively bumped to
"1.1" in B1 Slice 1 to carry two optional replan overlay fields
(`replan_trace`, `replan_triggers`) with `None` defaults. All other
schemas remain at 1.0; the registry is authoritative.
"""

import json
import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from adaptive.adaptive_schema import (
    AdaptivePolicyAdjustment,
    AdjustmentRuleSpec,
)
from agent_memory.agent_memory_schema import (
    AgentMemoryContext,
    AgentMemoryExampleRef,
)
from correlator.correlator_schema import (
    CorrelationContext,
    CorrelationSignal,
)
from learning.memory_schema import MemoryQuery, MemoryRecord, MemorySummary
from replan.replan_schema import (
    ExpectedOutcomeRef,
    ReplanAttemptRecord,
    ReplanTriggerRecord,
)
from session.session_schema import (
    EffectiveDecisionRef,
    GovernanceTruthRef,
    SessionArtifact,
    SessionConfig,
    SessionEventRecord,
    SessionKPIs,
)


_SAMPLES_PATH = os.path.join(
    _PROJECT_DIR, "tests", "fixtures", "path_c_schema_samples_1_0.json"
)


EXPECTED_FIELDS = {
    "MemoryRecord": {
        "event_id", "event_type", "event_timestamp", "action_taken",
        "execution_status", "final_route", "cost_incurred", "sla_preserved",
        "risk_level", "session_id", "schema_version",
    },
    "MemoryQuery": {
        "event_type", "action_type", "final_route", "recent_n",
        "schema_version",
    },
    "MemorySummary": {
        "matched_records", "cold_start", "auto_execute_success_rate",
        "sla_preservation_rate", "action_type_distribution", "avg_cost",
        "query_signature", "schema_version",
    },
    "AdaptivePolicyAdjustment": {
        "rule_id", "adjustment_type", "pre_adjustment_risk",
        "post_adjustment_risk", "query_signature", "memory_evidence",
        "notes", "schema_version",
    },
    "AdjustmentRuleSpec": {
        "rule_id", "description", "applies_to_event_types", "schema_version",
    },
    "GovernanceTruthRef": {
        "risk_level", "recommended_candidate_type", "schema_version",
    },
    "EffectiveDecisionRef": {
        "effective_risk", "final_route", "action_taken", "execution_status",
        "schema_version",
    },
    "SessionEventRecord": {
        "baseline_event_result", "session_id", "mode", "policy_route_source",
        "adaptive_adjustment", "governance_truth", "effective_decision",
        "memory_record_id", "replan_trace", "replan_triggers",
        "correlation_context",
        "notes", "schema_version",
    },
    "CorrelationSignal": {
        "pattern_id", "triggering_event_id", "participant_event_ids",
        "shared_entities", "window_start_ordinal", "window_end_ordinal",
        "window_size", "matched_conditions", "schema_version",
    },
    "CorrelationContext": {
        "signals", "window_size", "window_events_considered",
        "schema_version",
    },
    "AgentMemoryExampleRef": {
        "event_id", "event_type", "source_session_id",
        "action_taken", "final_route", "execution_status",
        "cost_incurred", "sla_preserved", "schema_version",
    },
    "AgentMemoryContext": {
        "matched_records", "cold_start", "query_signature",
        "auto_execute_success_rate", "sla_preservation_rate",
        "avg_cost", "action_type_distribution", "recent_examples",
        "schema_version",
    },
    "ExpectedOutcomeRef": {
        "expected_cost_min", "expected_cost_max", "expected_sla_preserved",
        "range_source", "estimator_id", "estimator_signature",
        "schema_version",
    },
    "ReplanTriggerRecord": {
        "trigger_rule_id", "trigger_type", "attempt_index",
        "deviation_measurement", "expected_outcome_ref", "realized_cost",
        "realized_sla_preserved", "notes", "schema_version",
    },
    "ReplanAttemptRecord": {
        "attempt_index", "attempt_final_route", "attempt_action_taken",
        "attempt_execution_status", "execution_outcome",
        "adaptive_adjustment", "expected_outcome", "trigger",
        "notes", "schema_version",
    },
    "SessionConfig": {
        "seed", "mode", "events_source", "initial_memory_digest",
        "schema_version",
    },
    "SessionKPIs": {
        "events_observed", "events_with_outcome", "events_skipped",
        "events_failed", "events_processed", "auto_execute_success_rate",
        "sla_preservation_rate", "total_cost", "avg_cost",
        "known_outcome_coverage",
        # B1 Slice 4 additive:
        "replan_events_observed", "replan_fire_count",
        "replan_trigger_rate", "replan_success_count",
        "replan_recovery_rate",
        "schema_version",
    },
    "SessionArtifact": {
        "session_id", "config", "event_records", "memory_snapshot",
        "kpis", "schema_versions", "notes", "schema_version",
    },
}

CLASS_MAP = {
    "MemoryRecord": MemoryRecord,
    "MemoryQuery": MemoryQuery,
    "MemorySummary": MemorySummary,
    "AdaptivePolicyAdjustment": AdaptivePolicyAdjustment,
    "AdjustmentRuleSpec": AdjustmentRuleSpec,
    "GovernanceTruthRef": GovernanceTruthRef,
    "EffectiveDecisionRef": EffectiveDecisionRef,
    "SessionEventRecord": SessionEventRecord,
    "SessionConfig": SessionConfig,
    "SessionKPIs": SessionKPIs,
    "SessionArtifact": SessionArtifact,
    "ExpectedOutcomeRef": ExpectedOutcomeRef,
    "ReplanTriggerRecord": ReplanTriggerRecord,
    "ReplanAttemptRecord": ReplanAttemptRecord,
    "CorrelationSignal": CorrelationSignal,
    "CorrelationContext": CorrelationContext,
    "AgentMemoryExampleRef": AgentMemoryExampleRef,
    "AgentMemoryContext": AgentMemoryContext,
}


# Per-class expected schema_version default. Keep this in sync with
# PATH_C_SCHEMA_REGISTRY.md — any drift is either a stale registry
# entry or a stale default.
EXPECTED_SCHEMA_VERSION = {name: "1.0" for name in CLASS_MAP}
EXPECTED_SCHEMA_VERSION["SessionEventRecord"] = "1.2"  # B2 Slice 2A additive bump
EXPECTED_SCHEMA_VERSION["SessionKPIs"] = "1.1"          # B1 Slice 4 additive bump


@pytest.mark.parametrize("name,cls", list(CLASS_MAP.items()))
def test_field_set_matches_expected(name, cls):
    actual = set(cls.model_fields.keys())
    expected = EXPECTED_FIELDS[name]
    assert actual == expected, (
        f"{name} field set drift. "
        f"missing={expected - actual}, unexpected={actual - expected}"
    )


@pytest.mark.parametrize("name,cls", list(CLASS_MAP.items()))
def test_schema_version_default_matches_registry(name, cls):
    field = cls.model_fields["schema_version"]
    default = field.default
    expected = EXPECTED_SCHEMA_VERSION[name]
    assert default == expected, (
        f"{name}.schema_version default = {default!r}, expected {expected!r}"
    )


def test_sample_roundtrip_lossless():
    with open(_SAMPLES_PATH) as f:
        samples = json.load(f)
    for name, cls in CLASS_MAP.items():
        data = samples[name]
        obj = cls.model_validate(data)
        reserialized = obj.model_dump()
        assert reserialized == data, f"{name} roundtrip diverged"
