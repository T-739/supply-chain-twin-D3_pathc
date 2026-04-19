"""B3 Slice 2B: no reverse import of
``src/learning/cumulative_memory`` from adaptive / replan /
correlator / agents / event_loop orchestrator.

B3 is observability/structural — the loader is a *producer* of
``EpisodicMemory`` rows that the existing adaptive gate already
consumes via the session's memory. It MUST NOT be imported by
any of the following in Slice 2B:

  * ``src/adaptive/*``   — adaptive gate reads MemoryRecord rows,
                           it does not care how the loader built
                           them; reverse import would invite a
                           source-aware branch in the gate,
                           which is explicitly forbidden.
  * ``src/replan/*``     — B1 bounded replan is orthogonal.
  * ``src/correlator/*`` — B2 compound-pattern sideband is
                           orthogonal.
  * ``src/agents/*``     — agents must never see memory.
  * ``src/event_loop.py`` — Path B core.
  * ``src/event_loop_c.py`` — B3 Slice 2B keeps the Path C
                           orchestrator unaware of the loader;
                           callers go through existing
                           ``run_session(initial_memory=...)``.
  * ``src/policy_gate.py`` / ``src/execution_adapters.py`` —
                           out of reach by design.

Self-tests ensure the scan detects real bad samples.
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


_CONSUMER_ROOTS = [
    os.path.join(_SRC_DIR, "adaptive"),
    os.path.join(_SRC_DIR, "replan"),
    os.path.join(_SRC_DIR, "correlator"),
    os.path.join(_SRC_DIR, "agents"),
]
_CONSUMER_FILES = [
    os.path.join(_SRC_DIR, "event_loop.py"),
    os.path.join(_SRC_DIR, "event_loop_c.py"),
    os.path.join(_SRC_DIR, "execution_adapters.py"),
    os.path.join(_SRC_DIR, "policy_gate.py"),
    os.path.join(_SRC_DIR, "outcome_store.py"),
]


def _iter_files():
    for root in _CONSUMER_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)
    for path in _CONSUMER_FILES:
        if os.path.isfile(path):
            yield path


def _imports_cumulative_memory(tree: ast.AST) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "learning.cumulative_memory" or (
                    alias.name.startswith("learning.cumulative_memory.")
                ):
                    findings.append(f"import {alias.name}")
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "learning.cumulative_memory" or mod.startswith(
                "learning.cumulative_memory."
            ):
                findings.append(f"from {mod} import ...")
            # Catch the shorter form: ``from learning import cumulative_memory``
            if mod == "learning":
                for alias in node.names:
                    if alias.name == "cumulative_memory":
                        findings.append(
                            "from learning import cumulative_memory"
                        )
    return findings


@pytest.mark.parametrize("path", list(_iter_files()))
def test_no_reverse_cumulative_memory_import(path):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    findings = _imports_cumulative_memory(tree)
    assert not findings, (
        f"{path} must not import from learning.cumulative_memory in "
        f"Slice 2B. findings={findings!r}"
    )


# ---------------------------------------------------------------------------
# Self-tests — ensure the guard actually flags bad samples.
# ---------------------------------------------------------------------------


_BAD_SAMPLES = {
    "import-module": "import learning.cumulative_memory",
    "import-submodule-attr": "import learning.cumulative_memory.foo",
    "from-import": "from learning.cumulative_memory import CumulativeMemoryConfig",
    "from-parent-import": "from learning import cumulative_memory",
}


@pytest.mark.parametrize("name,src", list(_BAD_SAMPLES.items()))
def test_guard_flags_bad_sample(name, src):
    findings = _imports_cumulative_memory(ast.parse(src))
    assert findings, f"guard failed to flag {name}: {src!r}"


_GOOD_SAMPLES = [
    # Allowed: importing from the memory primitive itself (not the
    # cumulative loader).
    "from learning.episodic_memory import EpisodicMemory",
    "from learning.memory_schema import MemoryRecord",
    "from session.session_schema import SessionEventRecord",
    "import json",
]


@pytest.mark.parametrize("src", _GOOD_SAMPLES)
def test_guard_clean_on_good_sample(src):
    assert _imports_cumulative_memory(ast.parse(src)) == []
