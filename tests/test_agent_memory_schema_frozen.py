"""B4 Slice 1: agent-visible memory contract freeze.

Pins the shape of ``AgentMemoryExampleRef``, ``AgentMemoryContext``,
and ``AgentMemoryExperimentConfig`` — the three contract surfaces
B4 Slice 1 ships. Mirrors the ``tests/test_correlator_schema_
frozen.py`` precedent for structural freezes and matches the
owner-fixed decisions D1–D6 recorded in
``docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §12``.

The Slice 1 invariants these tests enforce:

- default values match the boundary doc (default-off config, hard
  cap 3, closed Literal set membership);
- JSON roundtrip through pydantic ``model_dump`` is lossless on a
  canonical sample;
- ``recent_examples`` is capped at ``MAX_AGENT_MEMORY_EXAMPLES``
  (Slice 1 value 3) at construction;
- config's closed Literal / closed-set invariants are enforced
  (only ``"operations"`` target, only ``"PATH_C_WARM"`` mode, only
  ``"structured_summary_plus_recent_examples"`` source);
- ``extra='forbid'`` semantics reject cross-layer token names —
  we spot-check the five governance NL fields plus
  ``correlation_context``, ``baseline_event_result``, and
  ``risk_level``.

These tests do NOT exercise any runtime code — the B4 subpackage
contains only schemas and a config dataclass in Slice 1.
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from pydantic import ValidationError

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from agent_memory.agent_memory_config import (
    AgentMemoryExperimentConfig,
    KNOWN_AGENT_MEMORY_CONTEXT_SOURCES,
    KNOWN_AGENT_MEMORY_TARGETS,
    MAX_AGENT_MEMORY_EXAMPLES,
)
from agent_memory.agent_memory_schema import (
    AGENT_MEMORY_SCHEMA_VERSION,
    AgentMemoryContext,
    AgentMemoryExampleRef,
)


# ---------------------------------------------------------------------------
# Module-level constants — pins
# ---------------------------------------------------------------------------


def test_schema_version_pin():
    assert AGENT_MEMORY_SCHEMA_VERSION == "1.0"


def test_max_recent_examples_pin():
    assert MAX_AGENT_MEMORY_EXAMPLES == 3


def test_known_targets_closed_to_operations():
    assert KNOWN_AGENT_MEMORY_TARGETS == frozenset({"operations"})


def test_known_context_sources_closed_to_single_literal():
    assert KNOWN_AGENT_MEMORY_CONTEXT_SOURCES == frozenset(
        {"structured_summary_plus_recent_examples"}
    )


# ---------------------------------------------------------------------------
# AgentMemoryExperimentConfig defaults (D5 — default-off is load-bearing)
# ---------------------------------------------------------------------------


def test_config_defaults_are_slice_1_locked():
    cfg = AgentMemoryExperimentConfig()
    # D5 hard default
    assert cfg.enable_agent_visible_memory is False
    # D1 closed set
    assert cfg.target_agent == "operations"
    # D3 closed set
    assert cfg.context_source == "structured_summary_plus_recent_examples"
    # D3 hard cap
    assert cfg.max_recent_examples == MAX_AGENT_MEMORY_EXAMPLES
    # D5 closed-mode set
    assert cfg.allowed_modes == frozenset({"PATH_C_WARM"})
    assert cfg.schema_version == "1.0"


def test_config_rejects_enable_non_bool():
    with pytest.raises(TypeError):
        AgentMemoryExperimentConfig(enable_agent_visible_memory=1)  # type: ignore[arg-type]


def test_config_rejects_target_agent_outside_closed_set():
    with pytest.raises(ValueError):
        AgentMemoryExperimentConfig(target_agent="governance")  # type: ignore[arg-type]


def test_config_rejects_context_source_outside_closed_set():
    with pytest.raises(ValueError):
        AgentMemoryExperimentConfig(context_source="free_text_summary")  # type: ignore[arg-type]


def test_config_rejects_max_recent_examples_above_cap():
    with pytest.raises(ValueError):
        AgentMemoryExperimentConfig(max_recent_examples=MAX_AGENT_MEMORY_EXAMPLES + 1)


def test_config_rejects_max_recent_examples_below_one():
    with pytest.raises(ValueError):
        AgentMemoryExperimentConfig(max_recent_examples=0)


def test_config_rejects_max_recent_examples_non_int():
    with pytest.raises(TypeError):
        AgentMemoryExperimentConfig(max_recent_examples=True)  # type: ignore[arg-type]


def test_config_allowed_modes_is_slice_1_locked_to_path_c_warm():
    # Explicit PATH_C_WARM-only construction must succeed.
    cfg = AgentMemoryExperimentConfig(
        allowed_modes=frozenset({"PATH_C_WARM"})
    )
    assert cfg.allowed_modes == frozenset({"PATH_C_WARM"})


def test_config_rejects_allowed_modes_with_unknown_member():
    with pytest.raises(ValueError):
        AgentMemoryExperimentConfig(
            allowed_modes=frozenset({"PATH_C_WARM", "BASELINE_STATIC"})
        )


def test_config_rejects_allowed_modes_empty():
    with pytest.raises(ValueError):
        AgentMemoryExperimentConfig(allowed_modes=frozenset())


def test_config_rejects_allowed_modes_path_c_cold_only():
    with pytest.raises(ValueError):
        AgentMemoryExperimentConfig(allowed_modes=frozenset({"PATH_C_COLD"}))


def test_config_normalizes_iterable_allowed_modes_into_frozenset():
    cfg = AgentMemoryExperimentConfig(allowed_modes=["PATH_C_WARM"])  # type: ignore[arg-type]
    assert cfg.allowed_modes == frozenset({"PATH_C_WARM"})


def test_config_rejects_schema_version_drift():
    with pytest.raises(ValueError):
        AgentMemoryExperimentConfig(schema_version="2.0")


# ---------------------------------------------------------------------------
# AgentMemoryExampleRef shape
# ---------------------------------------------------------------------------


def _minimal_example_ref_dict():
    return {
        "event_id": "EVT-1",
        "event_type": "CARRIER_DELAY",
        "source_session_id": "S-PRIOR",
        "action_taken": "EXPEDITE",
        "final_route": "AUTO_EXECUTE",
        "execution_status": "executed",
        "cost_incurred": 100.0,
        "sla_preserved": True,
        "schema_version": "1.0",
    }


def test_example_ref_roundtrip_lossless():
    d = _minimal_example_ref_dict()
    obj = AgentMemoryExampleRef.model_validate(d)
    assert obj.model_dump() == d


def test_example_ref_rejects_empty_event_id():
    d = _minimal_example_ref_dict()
    d["event_id"] = "   "
    with pytest.raises(ValidationError):
        AgentMemoryExampleRef.model_validate(d)


def test_example_ref_rejects_empty_source_session_id():
    d = _minimal_example_ref_dict()
    d["source_session_id"] = ""
    with pytest.raises(ValidationError):
        AgentMemoryExampleRef.model_validate(d)


def test_example_ref_rejects_action_outside_literal_domain():
    d = _minimal_example_ref_dict()
    d["action_taken"] = "DOWNGRADE"
    with pytest.raises(ValidationError):
        AgentMemoryExampleRef.model_validate(d)


def test_example_ref_rejects_route_outside_literal_domain():
    d = _minimal_example_ref_dict()
    d["final_route"] = "ESCALATE"
    with pytest.raises(ValidationError):
        AgentMemoryExampleRef.model_validate(d)


def test_example_ref_rejects_status_outside_literal_domain():
    d = _minimal_example_ref_dict()
    d["execution_status"] = "mystery_state"
    with pytest.raises(ValidationError):
        AgentMemoryExampleRef.model_validate(d)


def test_example_ref_action_taken_allows_none():
    d = _minimal_example_ref_dict()
    d["action_taken"] = None
    obj = AgentMemoryExampleRef.model_validate(d)
    assert obj.action_taken is None


def test_example_ref_forbids_extra_field():
    d = _minimal_example_ref_dict()
    d["confidence"] = 0.5
    with pytest.raises(ValidationError):
        AgentMemoryExampleRef.model_validate(d)


# ---------------------------------------------------------------------------
# AgentMemoryContext shape
# ---------------------------------------------------------------------------


def _minimal_context_dict():
    return {
        "matched_records": 0,
        "cold_start": True,
        "query_signature": "sig-demo",
        "auto_execute_success_rate": None,
        "sla_preservation_rate": None,
        "avg_cost": None,
        "action_type_distribution": {},
        "recent_examples": [],
        "schema_version": "1.0",
    }


def test_context_roundtrip_lossless_empty():
    d = _minimal_context_dict()
    obj = AgentMemoryContext.model_validate(d)
    assert obj.model_dump() == d


def test_context_rejects_negative_matched_records():
    d = _minimal_context_dict()
    d["matched_records"] = -1
    with pytest.raises(ValidationError):
        AgentMemoryContext.model_validate(d)


def test_context_rejects_empty_query_signature():
    d = _minimal_context_dict()
    d["query_signature"] = ""
    with pytest.raises(ValidationError):
        AgentMemoryContext.model_validate(d)


def test_context_rejects_auto_rate_out_of_bounds():
    d = _minimal_context_dict()
    d["auto_execute_success_rate"] = 1.5
    with pytest.raises(ValidationError):
        AgentMemoryContext.model_validate(d)


def test_context_rejects_sla_rate_out_of_bounds():
    d = _minimal_context_dict()
    d["sla_preservation_rate"] = -0.1
    with pytest.raises(ValidationError):
        AgentMemoryContext.model_validate(d)


def test_context_rejects_non_int_distribution_value():
    d = _minimal_context_dict()
    d["action_type_distribution"] = {"EXPEDITE": "many"}
    with pytest.raises(ValidationError):
        AgentMemoryContext.model_validate(d)


def test_context_rejects_empty_distribution_key():
    d = _minimal_context_dict()
    d["action_type_distribution"] = {"": 1}
    with pytest.raises(ValidationError):
        AgentMemoryContext.model_validate(d)


def test_context_allows_recent_examples_at_cap():
    example = AgentMemoryExampleRef.model_validate(_minimal_example_ref_dict())
    d = _minimal_context_dict()
    d["recent_examples"] = [example.model_dump() for _ in range(MAX_AGENT_MEMORY_EXAMPLES)]
    obj = AgentMemoryContext.model_validate(d)
    assert len(obj.recent_examples) == MAX_AGENT_MEMORY_EXAMPLES


def test_context_rejects_recent_examples_above_cap():
    example = AgentMemoryExampleRef.model_validate(_minimal_example_ref_dict())
    d = _minimal_context_dict()
    d["recent_examples"] = [
        example.model_dump() for _ in range(MAX_AGENT_MEMORY_EXAMPLES + 1)
    ]
    with pytest.raises(ValidationError):
        AgentMemoryContext.model_validate(d)


def test_context_empty_recent_examples_is_valid_under_cold_start():
    # D3 explicitly allows empty recent_examples — needed to
    # represent cold-start / no-match sessions structurally.
    d = _minimal_context_dict()
    d["recent_examples"] = []
    d["cold_start"] = True
    obj = AgentMemoryContext.model_validate(d)
    assert obj.recent_examples == []
    assert obj.cold_start is True


def test_context_forbids_free_text_fields():
    """D3 forbids free-text explanation / rationale / confidence
    as B4-visible fields. ``extra='forbid'`` must reject every
    one of them."""
    forbidden_free_text_fields = [
        "rationale",
        "rationale_trace",
        "explanation",
        "situational_explanation",
        "confidence",
        "confidence_note",
        "cost_summary",
        "alternative_actions",
        "summary_paragraph",
    ]
    for bad_field in forbidden_free_text_fields:
        d = _minimal_context_dict()
        d[bad_field] = "some value"
        with pytest.raises(ValidationError):
            AgentMemoryContext.model_validate(d)


def test_context_forbids_cross_layer_overlay_tokens():
    """Correlator and session-overlay tokens must not appear on
    the B4 contract surface (cross-branch coupling guard)."""
    forbidden_cross_layer_fields = [
        "correlation_context",
        "baseline_event_result",
        "risk_level",
        "recommended_action",
        "governance_truth",
        "effective_decision",
    ]
    for bad_field in forbidden_cross_layer_fields:
        d = _minimal_context_dict()
        d[bad_field] = {}
        with pytest.raises(ValidationError):
            AgentMemoryContext.model_validate(d)


# ---------------------------------------------------------------------------
# Shared fixture roundtrip (parity with test_path_c_schema_frozen.py)
# ---------------------------------------------------------------------------


_SAMPLES_PATH = os.path.join(
    _PROJECT_DIR, "tests", "fixtures", "path_c_schema_samples_1_0.json"
)


def test_fixture_sample_roundtrip_lossless():
    with open(_SAMPLES_PATH) as f:
        samples = json.load(f)
    for name, cls in (
        ("AgentMemoryExampleRef", AgentMemoryExampleRef),
        ("AgentMemoryContext", AgentMemoryContext),
    ):
        data = samples[name]
        obj = cls.model_validate(data)
        assert obj.model_dump() == data, f"{name} roundtrip diverged"
