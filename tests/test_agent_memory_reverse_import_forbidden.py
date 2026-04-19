"""B4 Slice 1: reverse-import guard — ``src/adaptive/*`` must not
import ``src/agent_memory/*``.

Completes the G8 coverage declared in
``docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §11``: the adaptive
policy gate is Path C-min's policy-side memory consumer, and
B4 introduces a *second, independent* agent-prompt-side
consumer. Those two consumers must remain structurally
separate. The forward direction
(``src/agent_memory/*`` does not import ``src/adaptive/*``) is
covered by ``tests/test_agent_memory_contract_no_truth_write.py``
(``("adaptive",)`` is in its ``_FORBIDDEN_IMPORT_PREFIXES``).
This file covers the **reverse** direction.

AST-level only. No runtime behavior, no schema mutation.
"""

from __future__ import annotations

import ast
import os

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ADAPTIVE_ROOT = os.path.join(_PROJECT_DIR, "src", "adaptive")


# Import-path prefixes that ``src/adaptive/*`` must not reach
# into. Matched from the left, with an optional ``src.`` shim so
# both ``import agent_memory.foo`` and
# ``import src.agent_memory.foo`` are caught.
_FORBIDDEN_IMPORT_PREFIXES = [
    ("agent_memory",),
]


def _iter_adaptive_files() -> list[str]:
    out: list[str] = []
    if not os.path.isdir(_ADAPTIVE_ROOT):
        return out
    for dirpath, _dirs, files in os.walk(_ADAPTIVE_ROOT):
        for name in files:
            if name.endswith(".py"):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def _module_matches_prefix(module: str, prefix: tuple[str, ...]) -> bool:
    parts = [p for p in module.split(".") if p]
    if parts[:1] == ["src"]:
        parts = parts[1:]
    return tuple(parts[: len(prefix)]) == prefix


def _scan_file_for_agent_memory_import(tree: ast.AST) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
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


@pytest.mark.parametrize("path", _iter_adaptive_files())
def test_adaptive_does_not_import_agent_memory(path):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    findings = _scan_file_for_agent_memory_import(tree)
    assert not findings, f"{path} :: {findings}"


# ---------------------------------------------------------------------------
# Guard self-tests: make sure the reverse-import scan actually
# flags what it claims, and does not false-positive on the
# imports adaptive legitimately uses today.
# ---------------------------------------------------------------------------


_BAD_SAMPLES = {
    "adaptive-imports-agent-memory-module": (
        "import agent_memory.agent_memory_schema"
    ),
    "adaptive-from-imports-agent-memory-context": (
        "from agent_memory.agent_memory_schema import AgentMemoryContext"
    ),
    "adaptive-imports-src-prefixed-agent-memory": (
        "import src.agent_memory.agent_memory_config"
    ),
    "adaptive-from-imports-src-prefixed-agent-memory": (
        "from src.agent_memory import AgentMemoryExperimentConfig"
    ),
}


@pytest.mark.parametrize("name,src", list(_BAD_SAMPLES.items()))
def test_reverse_guard_flags_bad_sample(name, src):
    findings = _scan_file_for_agent_memory_import(ast.parse(src))
    assert findings, f"guard failed to flag {name}: {src!r}"


_GOOD_SAMPLES = [
    'from adaptive.adaptive_schema import AdaptivePolicyAdjustment',
    'from learning.memory_schema import MemoryRecord',
    'from typing import Literal',
    'x = {"matched_records": 0}',
]


@pytest.mark.parametrize("src", _GOOD_SAMPLES)
def test_reverse_guard_clean_on_good_sample(src):
    assert _scan_file_for_agent_memory_import(ast.parse(src)) == []
