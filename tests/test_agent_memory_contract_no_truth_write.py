"""B4 Slice 1: agent-visible memory contract must NOT be a truth
write surface.

Owner-fixed decision D2 (see docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md
§12): ``AgentMemoryContext`` is the single B4 agent-visible surface.
It must never grow into a truth source and must never be
structurally coupled to B2's correlator sideband, B1's replan
overlay, or the Path B raw shadow.

This test family encodes that rule at three levels:

1. **Structural (schema-level):** the frozen B4 schemas do NOT
   carry any of the forbidden governance NL field names
   (``cost_summary``, ``confidence_note``, ``rationale_trace``,
   ``situational_explanation``, ``alternative_actions``), any
   governance-truth field names (``risk_level``,
   ``recommended_action``, ``recommended_candidate_type``,
   ``governance_truth``, ``effective_decision``), the B2 sideband
   name (``correlation_context``), or the Path B raw shadow name
   (``baseline_event_result``).

2. **Source-scan (AST-level):** every ``.py`` file under
   ``src/agent_memory/`` is scanned for:
     - string-literal lookups of any forbidden name (evidence of
       runtime ``.get("risk_level")`` / ``obj["cost_summary"]`` style);
     - attribute access ``.risk_level`` / ``.rationale_trace`` / …
       (evidence of pydantic model access);
     - imports of the four Path C frozen consumer surfaces B4
       must not structurally couple to —
       ``src.agents.*`` (agent-output schemas),
       ``src.session.session_schema`` (truth refs),
       ``src.correlator.*`` (B2 sideband),
       ``src.replan.*`` (B1 overlay),
       ``src.learning.cumulative_memory`` (B3 loader internals).
   Mirrors ``tests/test_replan_contract_no_nl_truth.py`` and
   ``tests/test_correlator_no_nl_truth.py``.

3. **Behavioral (via pydantic ``extra='forbid'``):** attempting to
   validate an ``AgentMemoryContext`` or ``AgentMemoryExampleRef``
   payload that carries any of those field names fails
   construction. This guards against a runtime caller smuggling
   truth back in through a permissive `.model_validate(extra)`
   call.

This test does NOT exercise any runtime behavior — B4 Slice 1
does not ship any.
"""

from __future__ import annotations

import ast
import os
import sys

import pytest
from pydantic import ValidationError


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


_AGENT_MEMORY_ROOT = os.path.join(_PROJECT_DIR, "src", "agent_memory")


# Five forbidden governance NL field names — same list as B1 /
# B2's no-NL-truth scans.
_FORBIDDEN_GOVERNANCE_NL_FIELDS = frozenset({
    "cost_summary",
    "confidence_note",
    "rationale_trace",
    "situational_explanation",
    "alternative_actions",
})

# Truth-surface field names B4 must not expose.
_FORBIDDEN_TRUTH_FIELDS = frozenset({
    "risk_level",
    "recommended_action",
    "recommended_candidate_type",
    "governance_truth",
    "effective_decision",
})

# B2 / Path B shadow fields B4 must not structurally couple to.
_FORBIDDEN_OVERLAY_FIELDS = frozenset({
    "correlation_context",
    "baseline_event_result",
    "replan_trace",
    "replan_triggers",
})


_ALL_FORBIDDEN_FIELD_NAMES = (
    _FORBIDDEN_GOVERNANCE_NL_FIELDS
    | _FORBIDDEN_TRUTH_FIELDS
    | _FORBIDDEN_OVERLAY_FIELDS
)


# Import-path prefixes B4 must not reach into. Each entry is a
# tuple of module-path components we match from the left, so
# "src.session.session_schema" catches both `import ...` and
# `from ... import ...` regardless of how the session subpackage
# is reached.
_FORBIDDEN_IMPORT_PREFIXES = [
    ("agents",),                            # every agent module
    ("session", "session_schema"),          # truth-ref surface
    ("correlator",),                        # B2 sideband
    ("replan",),                            # B1 overlay
    ("learning", "cumulative_memory"),      # B3 loader internals
    ("adaptive",),                          # G8: no adaptive coupling
]


# ---------------------------------------------------------------------------
# Structural (schema-level) checks
# ---------------------------------------------------------------------------


def _agent_memory_schema_field_names():
    from agent_memory.agent_memory_schema import (
        AgentMemoryContext,
        AgentMemoryExampleRef,
    )
    names = set()
    names.update(AgentMemoryContext.model_fields.keys())
    names.update(AgentMemoryExampleRef.model_fields.keys())
    return names


def test_agent_memory_schemas_do_not_expose_forbidden_field_names():
    exposed = _agent_memory_schema_field_names()
    leaks = exposed & _ALL_FORBIDDEN_FIELD_NAMES
    assert not leaks, (
        "B4 contract surface leaks forbidden field names: "
        f"{sorted(leaks)!r}"
    )


def test_agent_memory_config_dataclass_does_not_expose_forbidden_fields():
    from dataclasses import fields as dc_fields

    from agent_memory.agent_memory_config import AgentMemoryExperimentConfig

    config_field_names = {f.name for f in dc_fields(AgentMemoryExperimentConfig)}
    leaks = config_field_names & _ALL_FORBIDDEN_FIELD_NAMES
    assert not leaks, (
        "B4 config dataclass leaks forbidden field names: "
        f"{sorted(leaks)!r}"
    )


# ---------------------------------------------------------------------------
# Source-scan (AST-level) checks
# ---------------------------------------------------------------------------


def _iter_agent_memory_files() -> list[str]:
    out: list[str] = []
    if not os.path.isdir(_AGENT_MEMORY_ROOT):
        return out
    for dirpath, _dirs, files in os.walk(_AGENT_MEMORY_ROOT):
        for name in files:
            if name.endswith(".py"):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def _module_matches_prefix(module: str, prefix: tuple[str, ...]) -> bool:
    parts = [p for p in module.split(".") if p]
    # Allow an optional leading "src." shim so both
    # `from src.correlator.foo import ...` and
    # `from correlator.foo import ...` are caught.
    if parts[:1] == ["src"]:
        parts = parts[1:]
    return tuple(parts[: len(prefix)]) == prefix


def _scan_file_for_truth_leaks(tree: ast.AST) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        # String-literal lookups: obj.get("risk_level"), obj["cost_summary"]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in _ALL_FORBIDDEN_FIELD_NAMES:
                findings.append(
                    f"forbidden field name as string literal: "
                    f"{node.value!r}"
                )
        # Attribute access: .risk_level / .rationale_trace / ...
        if isinstance(node, ast.Attribute):
            if node.attr in _ALL_FORBIDDEN_FIELD_NAMES:
                findings.append(
                    f"forbidden field access: .{node.attr}"
                )
        # Forbidden imports
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                if _module_matches_prefix(mod, prefix):
                    findings.append(
                        f"forbidden import: from {mod} import ..."
                    )
                    break
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                    if _module_matches_prefix(alias.name, prefix):
                        findings.append(
                            f"forbidden import: import {alias.name}"
                        )
                        break
    return findings


@pytest.mark.parametrize("path", _iter_agent_memory_files())
def test_agent_memory_source_has_no_truth_leak(path):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    findings = _scan_file_for_truth_leaks(tree)
    assert not findings, f"{path} :: {findings}"


# ---------------------------------------------------------------------------
# Behavioral — pydantic extra='forbid' rejects smuggled truth
# ---------------------------------------------------------------------------


def _valid_context_dict():
    return {
        "matched_records": 0,
        "cold_start": True,
        "query_signature": "sig",
        "auto_execute_success_rate": None,
        "sla_preservation_rate": None,
        "avg_cost": None,
        "action_type_distribution": {},
        "recent_examples": [],
        "schema_version": "1.0",
    }


def _valid_example_ref_dict():
    return {
        "event_id": "EVT-1",
        "event_type": "CARRIER_DELAY",
        "source_session_id": "S-PRIOR",
        "action_taken": "EXPEDITE",
        "final_route": "AUTO_EXECUTE",
        "execution_status": "executed",
        "cost_incurred": 10.0,
        "sla_preserved": True,
        "schema_version": "1.0",
    }


@pytest.mark.parametrize("forbidden", sorted(_ALL_FORBIDDEN_FIELD_NAMES))
def test_context_rejects_smuggled_forbidden_key(forbidden):
    from agent_memory.agent_memory_schema import AgentMemoryContext

    payload = _valid_context_dict()
    payload[forbidden] = "x"
    with pytest.raises(ValidationError):
        AgentMemoryContext.model_validate(payload)


@pytest.mark.parametrize("forbidden", sorted(_ALL_FORBIDDEN_FIELD_NAMES))
def test_example_ref_rejects_smuggled_forbidden_key(forbidden):
    from agent_memory.agent_memory_schema import AgentMemoryExampleRef

    payload = _valid_example_ref_dict()
    payload[forbidden] = "x"
    with pytest.raises(ValidationError):
        AgentMemoryExampleRef.model_validate(payload)


# ---------------------------------------------------------------------------
# Guard self-tests: make sure the AST scan catches what it claims.
# ---------------------------------------------------------------------------


_BAD_SAMPLES = {
    "nl-literal-cost-summary": 'x = payload.get("cost_summary")',
    "nl-literal-confidence-note": 'x = payload["confidence_note"]',
    "truth-attr-risk-level": 'risk = output.risk_level',
    "truth-attr-recommended-action": 'a = gov.recommended_action',
    "overlay-attr-correlation-context": 'ctx = record.correlation_context',
    "overlay-literal-baseline-event-result": 'x = payload.get("baseline_event_result")',
    "import-agents": 'from agents.operations_agent import run_operations_agent',
    "import-session-schema": 'from session.session_schema import SessionEventRecord',
    "import-correlator": 'from correlator.correlator_schema import CorrelationContext',
    "import-replan": 'from replan.replan_schema import ReplanAttemptRecord',
    "import-cumulative-memory": 'from learning.cumulative_memory import load_cumulative_memory',
    "import-src-prefixed-agents": 'import src.agents.governance_agent',
    "import-adaptive-module": 'import adaptive.adaptive_policy_gate',
    "from-import-adaptive": 'from adaptive.adaptive_policy_gate import decide_policy_adaptive',
    "import-src-prefixed-adaptive": 'import src.adaptive.adaptive_schema',
    "from-import-src-prefixed-adaptive": 'from src.adaptive.adaptive_schema import AdaptivePolicyAdjustment',
}


@pytest.mark.parametrize("name,src", list(_BAD_SAMPLES.items()))
def test_guard_flags_bad_sample(name, src):
    findings = _scan_file_for_truth_leaks(ast.parse(src))
    assert findings, f"guard failed to flag {name}: {src!r}"


_GOOD_SAMPLES = [
    'from agent_memory.agent_memory_schema import AgentMemoryContext',
    'from pydantic import BaseModel',
    'x = {"matched_records": 0, "cold_start": True}',
    'from typing import Literal',
]


@pytest.mark.parametrize("src", _GOOD_SAMPLES)
def test_guard_clean_on_good_sample(src):
    assert _scan_file_for_truth_leaks(ast.parse(src)) == []
