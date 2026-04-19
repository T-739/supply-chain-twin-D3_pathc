"""B3 Slice 2A: structural coupling guards for
``src/learning/cumulative_memory.py``.

Owner-fixed decisions D3/D7 and boundary §9 require the B3 module
to stay strictly inside the learning layer. In particular:

  - it MUST NOT import ``src/agents/*`` (no prompt-building,
    no governance-output coupling);
  - it MUST NOT import ``src/adaptive/*`` (no policy-gate
    coupling; the adaptive gate is the *consumer* of memory,
    not a dependency of the loader);
  - it MUST NOT import ``src/replan/*`` or ``src/correlator/*``
    (B1/B2 are independent branches; cross-branch coupling in
    B3 would violate the additive-branch discipline);
  - it MUST NOT import ``src/llm_backend`` or
    ``src/llm_providers/*`` (no LLM, no prompt construction at
    the loader layer);
  - it MUST NOT reference any of the five forbidden governance
    natural-language field names (``cost_summary``,
    ``confidence_note``, ``rationale_trace``,
    ``situational_explanation``, ``alternative_actions``) as
    either string literals or attribute names — these are
    structural markers that a loader has drifted into B4
    territory (memory-as-prompt-input);
  - it MUST NOT construct prompt-like strings. This is a
    structural proxy: we fail on any string literal containing
    the second-person "you are" or similar high-signal markers
    that are not legitimately present in a pure data module.

These are source-level AST scans — the guard is conservative and
deliberately simple. Runtime behavior is not exercised (the
Slice 2A loader body is intentionally a ``NotImplementedError``
stub).
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


_TARGET_FILE = os.path.join(
    _SRC_DIR, "learning", "cumulative_memory.py",
)


# Forbidden import-origin top-level roots.
_FORBIDDEN_IMPORT_ROOTS = frozenset({
    "agents",
    "adaptive",
    "replan",
    "correlator",
    "llm_backend",
    "llm_providers",
})


# Forbidden governance natural-language field names. Same set as
# the B1 / B2 guards use.
_FORBIDDEN_GOVERNANCE_NL_FIELDS = frozenset({
    "cost_summary",
    "confidence_note",
    "rationale_trace",
    "situational_explanation",
    "alternative_actions",
})


# Structural proxy for prompt-like string construction. The module
# is a data loader — none of these should appear in legitimate
# source. Matched case-insensitively on string literals only
# (docstrings are string literals too, so the module's docstring
# must not contain them either — which is enforced by choosing
# markers that don't appear in legitimate memory-loader prose).
_PROMPT_LIKE_MARKERS = frozenset({
    "you are",
    "you are a ",
    "system prompt",
    "as an ai ",
    "<|system|>",
})


def _read_source() -> str:
    with open(_TARGET_FILE, "r", encoding="utf-8") as f:
        return f.read()


def _top_root(modname: str | None) -> str:
    if not modname:
        return ""
    return modname.split(".")[0]


def _scan(tree: ast.AST) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        # Forbidden imports (top-level root match).
        if isinstance(node, ast.ImportFrom):
            top = _top_root(node.module)
            if top in _FORBIDDEN_IMPORT_ROOTS:
                findings.append(
                    f"forbidden from-import: from {node.module} import ..."
                )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _top_root(alias.name) in _FORBIDDEN_IMPORT_ROOTS:
                    findings.append(
                        f"forbidden import: import {alias.name}"
                    )

        # Forbidden governance NL field names (string literals OR
        # attribute names).
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in _FORBIDDEN_GOVERNANCE_NL_FIELDS:
                findings.append(
                    f"forbidden NL field name as string literal: "
                    f"{node.value!r}"
                )
        if isinstance(node, ast.Attribute):
            if node.attr in _FORBIDDEN_GOVERNANCE_NL_FIELDS:
                findings.append(
                    f"forbidden NL field access: .{node.attr}"
                )

        # Prompt-like string construction markers.
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            for marker in _PROMPT_LIKE_MARKERS:
                if marker in low:
                    findings.append(
                        f"prompt-like marker {marker!r} in string literal "
                        f"(len={len(node.value)})"
                    )
                    break
    return findings


def test_target_file_exists():
    assert os.path.isfile(_TARGET_FILE), _TARGET_FILE


def test_cumulative_memory_has_no_agent_or_prompt_coupling():
    source = _read_source()
    tree = ast.parse(source, filename=_TARGET_FILE)
    findings = _scan(tree)
    assert not findings, f"{_TARGET_FILE} :: {findings}"


# ---------------------------------------------------------------------------
# Positive pins: the module is allowed to rely on the learning-
# layer append-only primitive. This test ensures we can still
# import the module cleanly.
# ---------------------------------------------------------------------------


def test_cumulative_memory_imports_successfully():
    import importlib

    importlib.invalidate_caches()
    mod = importlib.import_module("learning.cumulative_memory")
    assert hasattr(mod, "CumulativeMemoryConfig")
    assert hasattr(mod, "load_cumulative_memory")
    assert hasattr(mod, "CumulativeMemoryCollisionError")


def test_cumulative_memory_imports_episodic_memory_type_only():
    """The module is allowed to import ``EpisodicMemory`` from
    ``learning.episodic_memory`` for the loader return-type
    annotation. Pin that positive relationship so a future
    refactor that drops it accidentally fails loudly."""
    source = _read_source()
    tree = ast.parse(source, filename=_TARGET_FILE)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "learning.episodic_memory":
                names = {a.name for a in node.names}
                if "EpisodicMemory" in names:
                    found = True
                    break
    assert found, (
        "cumulative_memory.py should import EpisodicMemory from "
        "learning.episodic_memory for the loader return type"
    )


# ---------------------------------------------------------------------------
# Self-tests: ensure the guard actually flags bad samples.
# ---------------------------------------------------------------------------


_BAD_SAMPLES = {
    "import-agents": "import agents.governance_agent",
    "from-import-agents": "from agents.governance_agent import X",
    "from-import-adaptive": "from adaptive.adaptive_policy_gate import X",
    "from-import-replan": "from replan import X",
    "from-import-correlator": "from correlator import X",
    "from-import-llm-backend": "from llm_backend import X",
    "from-import-llm-providers": "from llm_providers.anthropic_provider import X",
    "nl-literal": 'x = obj.get("cost_summary")',
    "nl-attr": 'x = output.rationale_trace',
    "prompt-marker": 'system_prompt = "You are a helpful assistant"',
}


@pytest.mark.parametrize("name,src", list(_BAD_SAMPLES.items()))
def test_guard_flags_bad_sample(name, src):
    findings = _scan(ast.parse(src))
    assert findings, f"guard failed to flag {name}: {src!r}"


_GOOD_SAMPLES = [
    "from learning.episodic_memory import EpisodicMemory",
    "from learning.memory_schema import MemoryRecord",
    "from dataclasses import dataclass, field",
    "x = {'prior_session_refs': ()}",
]


@pytest.mark.parametrize("src", _GOOD_SAMPLES)
def test_guard_clean_on_good_sample(src):
    assert _scan(ast.parse(src)) == []
