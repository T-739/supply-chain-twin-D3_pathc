"""B4 Slice 2B: single-agent injection guard.

Pins the G3 "single-agent injection" invariant from
``docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §11``:

- exactly one agent module under ``src/agents/`` is allowed to
  import from the ``agent_memory`` subpackage, and that module
  is ``operations_agent.py``;
- the other agent modules (``governance_agent.py``,
  ``cost_agent.py``, anything else under ``src/agents/``) must
  stay byte-unchanged at the import surface.

AST-level only. No runtime behavior is exercised.
"""

from __future__ import annotations

import ast
import os

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENTS_ROOT = os.path.join(_PROJECT_DIR, "src", "agents")

#: The single agent module that is allowed — in Slice 2B and
#: until a further boundary amendment — to import from
#: ``src/agent_memory/``. Widening this set is a boundary change
#: that requires its own owner-approved amendment.
_AGENT_MEMORY_ALLOWLIST = frozenset({
    os.path.join(_AGENTS_ROOT, "operations_agent.py"),
})


def _iter_agent_modules() -> list[str]:
    out: list[str] = []
    if not os.path.isdir(_AGENTS_ROOT):
        return out
    for dirpath, _dirs, files in os.walk(_AGENTS_ROOT):
        for name in files:
            if name.endswith(".py") and name != "__init__.py":
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def _module_imports_agent_memory(tree: ast.AST) -> list[str]:
    """Return a list of ``agent_memory``-touching import lines.

    Matches ``import agent_memory``, ``import agent_memory.foo``,
    ``from agent_memory import ...``,
    ``from agent_memory.foo import ...``, and the ``src.``-
    prefixed forms of each.
    """
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            parts = [p for p in mod.split(".") if p]
            if parts[:1] == ["src"]:
                parts = parts[1:]
            if parts[:1] == ["agent_memory"]:
                findings.append(f"from {mod} import ...")
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = [p for p in alias.name.split(".") if p]
                if parts[:1] == ["src"]:
                    parts = parts[1:]
                if parts[:1] == ["agent_memory"]:
                    findings.append(f"import {alias.name}")
    return findings


# ---------------------------------------------------------------------------
# Disallowed agent modules — must NOT import agent_memory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [p for p in _iter_agent_modules() if p not in _AGENT_MEMORY_ALLOWLIST],
)
def test_non_allowlisted_agent_does_not_import_agent_memory(path):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    findings = _module_imports_agent_memory(tree)
    assert not findings, (
        f"{path} imports agent_memory but is not on the Slice 2B "
        f"allowlist: {findings!r}"
    )


# ---------------------------------------------------------------------------
# Explicit high-priority targets from the boundary doc
# ---------------------------------------------------------------------------


def test_governance_agent_does_not_import_agent_memory():
    path = os.path.join(_AGENTS_ROOT, "governance_agent.py")
    assert os.path.isfile(path), (
        "governance_agent.py is expected to exist; boundary doc "
        "asserts it stays unchanged under B4"
    )
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    assert not _module_imports_agent_memory(tree)


def test_cost_agent_does_not_import_agent_memory():
    path = os.path.join(_AGENTS_ROOT, "cost_agent.py")
    assert os.path.isfile(path)
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    assert not _module_imports_agent_memory(tree)


# ---------------------------------------------------------------------------
# Allowlisted agent — operations_agent.py — SHOULD import it
# ---------------------------------------------------------------------------


def test_operations_agent_imports_agent_memory_per_slice_2b():
    """Symmetric to the negative test: the one allowlisted agent
    must actually carry the seam; if Slice 2B were reverted, this
    test would fail loudly rather than silently."""
    path = os.path.join(_AGENTS_ROOT, "operations_agent.py")
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    findings = _module_imports_agent_memory(tree)
    assert findings, (
        "operations_agent.py is expected to import from "
        "agent_memory under Slice 2B (B4 single-agent seam)."
    )


# ---------------------------------------------------------------------------
# Guard self-tests
# ---------------------------------------------------------------------------


_BAD_SAMPLES = {
    "import-agent-memory": "import agent_memory",
    "import-agent-memory-module": "import agent_memory.agent_memory_schema",
    "from-import-agent-memory": "from agent_memory import AgentMemoryContext",
    "from-import-agent-memory-submodule": (
        "from agent_memory.agent_memory_renderer import render_agent_memory_context"
    ),
    "src-prefixed-from-import": (
        "from src.agent_memory.agent_memory_config import AgentMemoryExperimentConfig"
    ),
    "src-prefixed-import": "import src.agent_memory",
}


@pytest.mark.parametrize("name,src", list(_BAD_SAMPLES.items()))
def test_guard_flags_bad_sample(name, src):
    findings = _module_imports_agent_memory(ast.parse(src))
    assert findings, f"guard failed to flag {name}: {src!r}"


_GOOD_SAMPLES = [
    "from pydantic import BaseModel",
    "import json",
    "from learning.memory_schema import MemoryRecord",
    "from adaptive.adaptive_schema import AdaptivePolicyAdjustment",
]


@pytest.mark.parametrize("src", _GOOD_SAMPLES)
def test_guard_clean_on_good_sample(src):
    assert _module_imports_agent_memory(ast.parse(src)) == []
