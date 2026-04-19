"""B2 Slice 2B: reverse-import allowlist for ``src/correlator/``.

Slice 2B is still observability-only, but the Path C orchestrator
``src/event_loop_c.py`` now owns the narrow attach point for
``correlation_context``. This test allowlists exactly two
consumers:

  1. ``src/session/session_schema.py`` — additive optional field
     (``SessionEventRecord.correlation_context``), landed in
     Slice 2A.
  2. ``src/event_loop_c.py``            — post-finalization
     attach pass (pure ``model_copy(update=...)``), landed in
     Slice 2B.

Every other Path C layer and every Path B file below MUST NOT
import from ``src/correlator/``. This is a source-level AST scan
across the canonical source roots:

  * ``src/adaptive/``  — policy gate, preflight, cold-start
  * ``src/replan/``    — bounded replan
  * ``src/learning/``  — episodic memory, summarizer
  * ``src/agents/``    — governance / cost / operations
  * top-level Path B files that could plausibly host a mis-wiring:
      ``event_loop.py``, ``execution_adapters.py``,
      ``policy_gate.py``, ``outcome_store.py``

Adding a third consumer (for example feeding correlator output
into the adaptive policy gate, which is explicitly OUT of scope
in Slice 2B) REQUIRES widening this allowlist in the same PR.
Until then, any import of ``correlator`` from the surfaces below
is a hard failure.

Positive / negative self-tests are included so the guard's own
coverage is itself verified on every CI run.
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
    os.path.join(_SRC_DIR, "learning"),
    os.path.join(_SRC_DIR, "agents"),
]
_CONSUMER_FILES = [
    os.path.join(_SRC_DIR, "event_loop.py"),
    os.path.join(_SRC_DIR, "execution_adapters.py"),
    os.path.join(_SRC_DIR, "policy_gate.py"),
    os.path.join(_SRC_DIR, "outcome_store.py"),
]

# session/ is scanned separately — session_schema.py IS allowed to
# import `CorrelationContext` from correlator (additive optional
# field on SessionEventRecord), but the rest of the session/
# subpackage (kpi_calculator, session_compare, session_manager,
# digests) must NOT import correlator in Slice 2A.
_SESSION_FORBIDDEN_FILES = [
    os.path.join(_SRC_DIR, "session", "kpi_calculator.py"),
    os.path.join(_SRC_DIR, "session", "session_compare.py"),
    os.path.join(_SRC_DIR, "session", "session_manager.py"),
    os.path.join(_SRC_DIR, "session", "digests.py"),
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
    for path in _SESSION_FORBIDDEN_FILES:
        if os.path.isfile(path):
            yield path


def _imports_correlator(tree: ast.AST) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "correlator" or alias.name.startswith(
                    "correlator."
                ):
                    findings.append(f"import {alias.name}")
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            top = mod.split(".")[0]
            if top == "correlator":
                findings.append(f"from {mod} import ...")
    return findings


@pytest.mark.parametrize("path", list(_iter_files()))
def test_no_reverse_correlator_import(path):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    findings = _imports_correlator(tree)
    assert not findings, (
        f"{path} must not import from correlator in Slice 2A. "
        f"findings={findings!r}"
    )


# ---------------------------------------------------------------------------
# Allowed consumers (positive pins): if a future refactor drops these
# imports without replacing them, these tests fail and surface the
# regression loudly.
# ---------------------------------------------------------------------------


def _file_imports_correlator_name(path: str, name: str) -> bool:
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("correlator"):
                names = {a.name for a in node.names}
                if name in names:
                    return True
    return False


def test_session_schema_imports_correlation_context():
    """Slice 2A allowlist: session_schema.py pulls CorrelationContext
    in as an optional-field type."""
    path = os.path.join(_SRC_DIR, "session", "session_schema.py")
    assert _file_imports_correlator_name(path, "CorrelationContext"), (
        "session_schema.py must import CorrelationContext from "
        "correlator.correlator_schema — allowlisted Slice 2A consumer."
    )


def test_event_loop_c_imports_engine_and_config():
    """Slice 2B allowlist: event_loop_c.py pulls
    ``compute_correlation_context`` and ``CorrelatorConfig`` in as
    the narrow post-finalization attach consumer."""
    path = os.path.join(_SRC_DIR, "event_loop_c.py")
    assert _file_imports_correlator_name(
        path, "compute_correlation_context"
    ), (
        "event_loop_c.py must import compute_correlation_context from "
        "correlator.correlator_engine — allowlisted Slice 2B consumer."
    )
    assert _file_imports_correlator_name(path, "CorrelatorConfig"), (
        "event_loop_c.py must import CorrelatorConfig from "
        "correlator.correlator_config — allowlisted Slice 2B consumer."
    )


# ---------------------------------------------------------------------------
# Self-tests
# ---------------------------------------------------------------------------


_BAD_SAMPLES = {
    "import-pkg": "import correlator",
    "import-submodule": "import correlator.correlator_schema",
    "from-import": "from correlator import CorrelationContext",
    "from-submodule": "from correlator.correlator_schema import CorrelationSignal",
}


@pytest.mark.parametrize("name,src", list(_BAD_SAMPLES.items()))
def test_guard_flags_bad_sample(name, src):
    findings = _imports_correlator(ast.parse(src))
    assert findings, f"guard failed to flag {name}: {src!r}"


_GOOD_SAMPLES = [
    "from session.session_schema import SessionEventRecord",
    "import json",
    "from replan.replan_schema import ReplanAttemptRecord",
    "from adaptive.adaptive_schema import AdaptivePolicyAdjustment",
]


@pytest.mark.parametrize("src", _GOOD_SAMPLES)
def test_guard_clean_on_good_sample(src):
    assert _imports_correlator(ast.parse(src)) == []
