"""Phase 0+1: import-topology / determinism guard for Path C code.

Scans every Path C source file for forbidden imports and
nondeterministic API uses. As of Phase 1 this is:

  - ``src/learning/``           (Phase 0 subpackage; B3 Slice 2A
                                 adds ``cumulative_memory.py``
                                 under this same root)
  - ``src/adaptive/``           (Phase 0 subpackage)
  - ``src/session/``            (Phase 0 subpackage)
  - ``src/outcome_persistence/`` (Phase 1 subpackage)
  - ``src/replan/``             (B1 Slice 1 subpackage)
  - ``src/correlator/``         (B2 Slice 2A subpackage)
  - ``src/agent_memory/``       (B4 Slice 1 subpackage — contracts only)
  - ``src/event_loop_c.py``     (Phase 1 outer orchestrator)

Every finding is a hard failure — determinism and Research Core
isolation are non-negotiable per PATH_C_BOUNDARY.md §1 and §6.

Coverage of this guard (kept in sync with PATH_C_BOUNDARY.md §6):

  (a) ``import evaluation`` / ``import action_code_mapper``
      and ``from evaluation import ...`` / ``from action_code_mapper
      import ...`` (including dotted suffixes).

  (b) Nondeterministic call sites:
        ``uuid.uuid4(...)``, ``uuid4(...)``        (via any binding form)
        ``time.time(...)``                         (clock)
        ``datetime.now(...)`` / ``datetime.utcnow(...)``
        ``datetime(...)`` construction without a ``tzinfo=`` keyword.

  (c) Research Core case-path access, whatever syntactic form:
        - any string literal ``"data/cases/..."`` appearing as a Call
          argument (so ``open("data/cases/...")``, ``Path("data/cases
          /...")``, ``json.loads(open("data/cases/...").read())``, …
          all trigger).
        - a segment-wise ``os.path.join(..., "cases", ...)`` or
          ``os.path.join(..., "data", "cases", ...)``.
        - a ``Path(...) / "data" / "cases"`` chain or any ``Path(...)
          / "cases"`` under a parent segment equal to ``"data"``.
        - attribute calls on a Path-like object whose method name is one
          of ``open``, ``read_text``, ``read_bytes`` and whose receiver
          AST contains a ``"data/cases"`` literal or a
          ``"cases"`` segment combined with a sibling ``"data"``.

This is not a static proof. It is a deliberately conservative syntactic
guard — fewer false positives than a string search, stronger than the
Phase 0 v1 literal-only scan. Any Phase 1+ consumer that wants Research
Core data must route through an approved boundary layer, not Path C
overlay code.
"""

from __future__ import annotations

import ast
import os

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH_C_ROOTS = [
    os.path.join(_PROJECT_DIR, "src", "learning"),
    os.path.join(_PROJECT_DIR, "src", "adaptive"),
    os.path.join(_PROJECT_DIR, "src", "session"),
    os.path.join(_PROJECT_DIR, "src", "outcome_persistence"),
    os.path.join(_PROJECT_DIR, "src", "replan"),
    os.path.join(_PROJECT_DIR, "src", "correlator"),
    os.path.join(_PROJECT_DIR, "src", "agent_memory"),
]
_PATH_C_FILES = [
    os.path.join(_PROJECT_DIR, "src", "event_loop_c.py"),
]

FORBIDDEN_IMPORT_NAMES = {"evaluation", "action_code_mapper"}

FORBIDDEN_CALL_ATTRS = {
    ("uuid", "uuid4"),
    ("time", "time"),
    ("datetime", "now"),
    ("datetime", "utcnow"),
}

PATH_IO_METHOD_NAMES = {"open", "read_text", "read_bytes", "write_text", "write_bytes"}


def _iter_py_files():
    for root in _PATH_C_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)
    for path in _PATH_C_FILES:
        if os.path.isfile(path):
            yield path


def _string_constants_in(node: ast.AST) -> list[str]:
    """All string-constant *values* reachable under ``node`` (recursive)."""
    out: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.append(child.value)
    return out


def _call_string_args(call: ast.Call) -> list[str]:
    out: list[str] = []
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.append(arg.value)
    return out


def _references_data_cases(text: str) -> bool:
    normalized = text.replace("\\", "/")
    return "data/cases" in normalized


def _joinpath_segments(call: ast.Call) -> list[str]:
    """Flatten a possibly-nested os.path.join chain into string segments."""
    segs: list[str] = []
    for a in call.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            # split on / so "data/cases" also splits correctly
            segs.extend(s for s in a.value.replace("\\", "/").split("/") if s)
        elif isinstance(a, ast.Call) and _is_os_path_join(a):
            segs.extend(_joinpath_segments(a))
    return segs


def _is_os_path_join(call: ast.Call) -> bool:
    fn = call.func
    if isinstance(fn, ast.Attribute) and fn.attr == "join":
        v = fn.value
        if isinstance(v, ast.Attribute) and v.attr == "path":
            if isinstance(v.value, ast.Name) and v.value.id == "os":
                return True
    return False


def _pathlib_chain_has_data_cases(node: ast.AST) -> bool:
    """Detect ``Path(...) / "data" / "cases"`` or ``Path("...")`` literal hit."""
    # 1) Path("data/cases/...") literal
    if isinstance(node, ast.Call):
        fn = node.func
        name = None
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr
        if name == "Path":
            for s in _call_string_args(node):
                if _references_data_cases(s):
                    return True

    # 2) BinOp '/' chain — gather all string segments on either side,
    #    recursing into nested BinOp subexpressions.
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        strings = [
            c.value for c in ast.walk(node)
            if isinstance(c, ast.Constant) and isinstance(c.value, str)
        ]
        has_data = any(s == "data" for s in strings)
        has_cases = any(s == "cases" for s in strings)
        joined = "/".join(strings)
        if _references_data_cases(joined) or (has_data and has_cases):
            return True

    return False


def _scan(tree: ast.AST) -> list[str]:
    findings: list[str] = []

    for node in ast.walk(tree):
        # (a) imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in FORBIDDEN_IMPORT_NAMES:
                    findings.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in FORBIDDEN_IMPORT_NAMES:
                findings.append(f"from {node.module} import ...")

        # (b) forbidden attribute calls and naive datetime construction
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                key = (fn.value.id, fn.attr)
                if key in FORBIDDEN_CALL_ATTRS:
                    findings.append(f"{fn.value.id}.{fn.attr}(...)")
            if isinstance(fn, ast.Name) and fn.id == "uuid4":
                findings.append("uuid4(...)")
            if isinstance(fn, ast.Name) and fn.id == "datetime":
                if not any(k.arg == "tzinfo" for k in node.keywords):
                    findings.append("naive datetime(...) without tzinfo")
            if isinstance(fn, ast.Attribute) and fn.attr == "datetime":
                if not any(k.arg == "tzinfo" for k in node.keywords):
                    findings.append("naive datetime(...) without tzinfo")

        # (c) data/cases path access
        if isinstance(node, ast.Call):
            # c1) any call whose literal string arg embeds "data/cases"
            for s in _call_string_args(node):
                if _references_data_cases(s):
                    findings.append(
                        f"call-arg literal references data/cases: {s!r}"
                    )

            # c2) os.path.join(..., "cases", ...) with sibling "data"
            if _is_os_path_join(node):
                segs = _joinpath_segments(node)
                if "cases" in segs and "data" in segs:
                    findings.append(
                        "os.path.join chain references data/cases segments"
                    )

            # c3) Path-like IO: x.open()/read_text()/... whose subtree touches
            #     a data/cases literal
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr in PATH_IO_METHOD_NAMES:
                for s in _string_constants_in(fn.value):
                    if _references_data_cases(s):
                        findings.append(
                            f"{fn.attr}() on receiver that embeds data/cases"
                        )
                        break

        # c4) Path(...) literal or Path(...) / "data" / "cases" chains
        if _pathlib_chain_has_data_cases(node):
            findings.append("Path-chain references data/cases")

    return findings


@pytest.mark.parametrize("path", list(_iter_py_files()))
def test_file_has_no_forbidden_constructs(path):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    findings = _scan(tree)
    assert not findings, f"{path} :: {findings}"


# ---------------------------------------------------------------------------
# Self-tests: make sure the guard actually flags the patterns it claims to.
# If these tests pass, the guard is real — not a placeholder.
# ---------------------------------------------------------------------------


_BAD_SAMPLES = {
    "open-literal": 'open("data/cases/M01.json")',
    "pathlib-literal": 'from pathlib import Path\nPath("data/cases/M01.json")',
    "pathlib-chain": 'from pathlib import Path\n_p = Path("x") / "data" / "cases" / "M01.json"',
    "ospath-join": 'import os\nos.path.join("root", "data", "cases", "M01.json")',
    "read-text": 'from pathlib import Path\nPath("data/cases/M01.json").read_text()',
    "uuid4": 'import uuid\nuuid.uuid4()',
    "bare-uuid4": 'from uuid import uuid4\nuuid4()',
    "time-time": 'import time\ntime.time()',
    "dt-now": 'from datetime import datetime\ndatetime.now()',
    "dt-utcnow": 'from datetime import datetime\ndatetime.utcnow()',
    "naive-dt": 'from datetime import datetime\ndatetime(2026, 1, 1)',
    "forbidden-import": 'import evaluation',
    "forbidden-fromimport": 'from action_code_mapper import map_supervisor_to_action_code',
}


@pytest.mark.parametrize("name,src", list(_BAD_SAMPLES.items()))
def test_guard_flags_bad_sample(name, src):
    findings = _scan(ast.parse(src))
    assert findings, f"guard failed to flag {name}: {src!r}"


_GOOD_SAMPLES = [
    'x = 1 + 2',
    'from pydantic import BaseModel',
    'import json\njson.dumps({"a": 1})',
    'from datetime import datetime, timezone\ndatetime(2026, 1, 1, tzinfo=timezone.utc)',
]


@pytest.mark.parametrize("src", _GOOD_SAMPLES)
def test_guard_clean_on_good_sample(src):
    assert _scan(ast.parse(src)) == []
