"""B2 Slice 2A: no-natural-language-as-correlation-truth guard.

Owner-fixed decision D1+D5 (see
``docs/B2_CORRELATOR_BOUNDARY.md §12`` and
``docs/B2_CORRELATOR_CONTRACT_DRAFT.md §7``): correlation evidence
must be structural. It MUST NOT be read out of governance natural-
language fields, and the correlator MUST NOT import from the
governance agent module.

This test is a source-level AST scan over every file under
``src/correlator/``. It fails if any of the following appear:

  * a string literal equal to a forbidden governance NL field name
    (evidence of a field-name lookup — e.g. ``obj.get("cost_summary")``,
    ``obj["rationale_trace"]``);
  * an attribute access like ``.cost_summary`` / ``.rationale_trace``
    on any receiver (evidence of pydantic model access);
  * an import of ``agents.governance_agent`` or a from-import of its
    ``GovernanceOutput`` symbol;
  * any import from ``adaptive``, ``replan``, ``learning``, or
    ``session`` — correlator is a standalone overlay and must not
    couple to the policy, replan, memory, or session-artifact layers.
    It is allowed to import from ``event_schema`` (for
    ``AffectedEntityRef`` / ``EventType`` / ``EventSeverity``, which
    are Path B frozen contracts).
"""

from __future__ import annotations

import ast
import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


# Forbidden governance NL field names (same set enforced for replan).
_FORBIDDEN_GOVERNANCE_NL_FIELDS = frozenset({
    "cost_summary",
    "confidence_note",
    "rationale_trace",
    "situational_explanation",
    "alternative_actions",
})

# Forbidden import-origin modules. Correlator must remain a
# standalone overlay in Slice 2A.
_FORBIDDEN_IMPORT_ROOTS = frozenset({
    "adaptive",
    "replan",
    "learning",
    "session",
    "agents",
})

_CORRELATOR_ROOT = os.path.join(_PROJECT_DIR, "src", "correlator")


def _iter_correlator_files() -> list[str]:
    out: list[str] = []
    if not os.path.isdir(_CORRELATOR_ROOT):
        return out
    for dirpath, _dirs, files in os.walk(_CORRELATOR_ROOT):
        for name in files:
            if name.endswith(".py"):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def _top_root(modname: str | None) -> str:
    if not modname:
        return ""
    return modname.split(".")[0]


def _scan_file_for_nl_truth(tree: ast.AST) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        # String-literal lookups
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in _FORBIDDEN_GOVERNANCE_NL_FIELDS:
                findings.append(
                    f"forbidden NL field name as string literal: {node.value!r}"
                )
        # Attribute access
        if isinstance(node, ast.Attribute):
            if node.attr in _FORBIDDEN_GOVERNANCE_NL_FIELDS:
                findings.append(
                    f"forbidden NL field access: .{node.attr}"
                )
        # Forbidden governance imports
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("governance_agent") or mod.endswith(
                "agents.governance_agent"
            ):
                findings.append(
                    f"forbidden import: from {mod} import ..."
                )
            for alias in node.names:
                if alias.name == "GovernanceOutput":
                    findings.append(
                        f"forbidden import: GovernanceOutput from {mod}"
                    )
            if _top_root(mod) in _FORBIDDEN_IMPORT_ROOTS:
                findings.append(
                    f"forbidden subpackage import: from {mod} import ..."
                )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("governance_agent"):
                    findings.append(
                        f"forbidden import: import {alias.name}"
                    )
                if _top_root(alias.name) in _FORBIDDEN_IMPORT_ROOTS:
                    findings.append(
                        f"forbidden subpackage import: import {alias.name}"
                    )
    return findings


@pytest.mark.parametrize("path", _iter_correlator_files())
def test_correlator_source_has_no_nl_truth_or_forbidden_imports(path):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    findings = _scan_file_for_nl_truth(tree)
    assert not findings, f"{path} :: {findings}"


# ---------------------------------------------------------------------------
# Self-test: make sure the guard actually flags a bad sample.
# ---------------------------------------------------------------------------


_BAD_SAMPLES = {
    "string-literal-lookup": 'x = obj.get("cost_summary")',
    "attr-access": 'x = output.rationale_trace',
    "from-import-governance": 'from agents.governance_agent import GovernanceOutput',
    "import-governance": 'import agents.governance_agent',
    "from-import-adaptive": 'from adaptive.adaptive_schema import X',
    "from-import-replan": 'from replan import X',
    "from-import-learning": 'from learning.memory_schema import X',
    "from-import-session": 'from session.session_schema import X',
    "import-learning": 'import learning.episodic_memory',
}


@pytest.mark.parametrize("name,src", list(_BAD_SAMPLES.items()))
def test_guard_flags_bad_sample(name, src):
    findings = _scan_file_for_nl_truth(ast.parse(src))
    assert findings, f"guard failed to flag {name}: {src!r}"


_GOOD_SAMPLES = [
    "from event_schema import AffectedEntityRef, EventType",
    "from correlator.correlator_schema import CorrelationSignal",
    'x = {"signals": []}',
    'from pydantic import BaseModel',
]


@pytest.mark.parametrize("src", _GOOD_SAMPLES)
def test_guard_clean_on_good_sample(src):
    assert _scan_file_for_nl_truth(ast.parse(src)) == []
