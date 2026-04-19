"""B1 Slice 1: no-natural-language-as-numeric-truth guard.

Owner-fixed decision D1 (see docs/B1_REPLAN_CONTRACT_DRAFT.md §7):
expected-cost ranges and SLA deviation MUST be derived from the
structured ``CostOutput.cost_estimates`` overlay. They MUST NOT be
read out of governance natural-language fields.

This test is a source-level AST scan over every file under
``src/replan/``. It fails if any of the following appear:

  * a string literal equal to a forbidden governance NL field name
    (treated as evidence of a field-name lookup in runtime code —
    e.g. ``obj.get("cost_summary")``, ``obj["rationale_trace"]``);
  * an attribute access like ``.cost_summary`` / ``.rationale_trace``
    on any receiver (evidence of pydantic model access);
  * an import of ``agents.governance_agent`` or a from-import of its
    ``GovernanceOutput`` symbol (B1 must not reach into governance's
    NL surface — the cost overlay is the only admitted source).

The guard also checks that the schema for ``ReplanTriggerRecord``'s
``deviation_measurement`` field remains a numeric-only mapping
(``dict[str, float | int | bool]``). If someone later widens it to
``dict[str, Any]`` or adds ``str`` to the value union, this test
fails, forcing a design conversation before NL can leak into
numeric truth.

Allowed exceptions:
  * References to these field names inside docstrings / comments are
    permitted (we don't scan comments). We scan string-constant
    values and attribute-access names in the AST, which is where
    runtime lookups would live.
  * The docstring-style string `__doc__` is never matched because
    forbidden names are whole-string matches; we compare via equality
    to avoid false positives on longer natural-language prose that
    merely mentions the field name.
"""

from __future__ import annotations

import ast
import os
import sys
import typing

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


# Forbidden governance NL field names. Source: Cost Agent +
# Governance Agent structured-output schemas carry these as
# explanation fields (not numeric facts).
_FORBIDDEN_GOVERNANCE_NL_FIELDS = frozenset({
    "cost_summary",
    "confidence_note",
    "rationale_trace",
    "situational_explanation",
    "alternative_actions",
})

_REPLAN_ROOT = os.path.join(_PROJECT_DIR, "src", "replan")


def _iter_replan_files() -> list[str]:
    out: list[str] = []
    if not os.path.isdir(_REPLAN_ROOT):
        return out
    for dirpath, _dirs, files in os.walk(_REPLAN_ROOT):
        for name in files:
            if name.endswith(".py"):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def _scan_file_for_nl_truth(tree: ast.AST) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        # String-literal lookups: obj.get("cost_summary"), obj["rationale_trace"]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in _FORBIDDEN_GOVERNANCE_NL_FIELDS:
                findings.append(
                    f"forbidden NL field name as string literal: {node.value!r}"
                )
        # Attribute access: .cost_summary / .rationale_trace / ...
        if isinstance(node, ast.Attribute):
            if node.attr in _FORBIDDEN_GOVERNANCE_NL_FIELDS:
                findings.append(
                    f"forbidden NL field access: .{node.attr}"
                )
        # Forbidden governance imports
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("governance_agent") or mod.endswith("agents.governance_agent"):
                findings.append(
                    f"forbidden import: from {mod} import ..."
                )
            for alias in node.names:
                if alias.name == "GovernanceOutput":
                    findings.append(
                        f"forbidden import: GovernanceOutput from {mod}"
                    )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("governance_agent"):
                    findings.append(
                        f"forbidden import: import {alias.name}"
                    )
    return findings


@pytest.mark.parametrize("path", _iter_replan_files())
def test_replan_source_has_no_nl_truth_refs(path):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    findings = _scan_file_for_nl_truth(tree)
    assert not findings, f"{path} :: {findings}"


# ---------------------------------------------------------------------------
# Schema-level guard: deviation_measurement stays numeric-only.
# ---------------------------------------------------------------------------


def test_deviation_measurement_value_type_is_numeric_only():
    """ReplanTriggerRecord.deviation_measurement MUST remain
    ``dict[str, float | int | bool]`` — no ``str`` or ``Any``.
    """
    from replan.replan_schema import ReplanTriggerRecord

    field = ReplanTriggerRecord.model_fields["deviation_measurement"]
    annotation = field.annotation
    # annotation is dict[str, float | int | bool]
    origin = typing.get_origin(annotation)
    assert origin is dict, (
        f"deviation_measurement outer type must be dict, got {origin!r}"
    )
    key_t, value_t = typing.get_args(annotation)
    assert key_t is str
    # value_t is a Union / types.UnionType of {float, int, bool}
    value_members = set(typing.get_args(value_t))
    # bool is a subclass of int, but typing preserves the literal members
    assert value_members <= {float, int, bool}, (
        f"deviation_measurement value type leaked: {value_members!r}"
    )
    assert str not in value_members, (
        "deviation_measurement must not admit str — NL values are forbidden"
    )
    assert typing.Any not in value_members, (
        "deviation_measurement must not admit Any — opens NL back door"
    )


# ---------------------------------------------------------------------------
# Self-test: make sure the guard actually flags a bad sample.
# ---------------------------------------------------------------------------


_BAD_SAMPLES = {
    "string-literal-lookup": 'x = obj.get("cost_summary")',
    "attr-access": 'x = output.rationale_trace',
    "from-import-governance": 'from agents.governance_agent import GovernanceOutput',
    "import-governance": 'import agents.governance_agent',
}


@pytest.mark.parametrize("name,src", list(_BAD_SAMPLES.items()))
def test_guard_flags_bad_sample(name, src):
    findings = _scan_file_for_nl_truth(ast.parse(src))
    assert findings, f"guard failed to flag {name}: {src!r}"


_GOOD_SAMPLES = [
    'from replan.replan_schema import ReplanTriggerRecord',
    'x = {"cost_min": 10.0, "cost_max": 50.0}',
    'cost = cost_output.cost_estimates[0].total_cost_estimate',
]


@pytest.mark.parametrize("src", _GOOD_SAMPLES)
def test_guard_clean_on_good_sample(src):
    assert _scan_file_for_nl_truth(ast.parse(src)) == []
