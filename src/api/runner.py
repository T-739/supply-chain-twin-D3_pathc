"""Graph invocation helper for the Phase 7 API.

This module is a thin adapter. It reuses the compiled LangGraph from
``src/graph.py`` and enforces no business logic of its own. Its only job
is to:

  - translate API request fields into a GraphState dict
  - hand it to the compiled graph
  - return the engine's outputs verbatim (dicts from existing .to_dict())

Frozen schemas and evaluation truth remain authoritative upstream.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
_CASES_DIR = _PROJECT_DIR / "data" / "cases"


class RunnerError(Exception):
    """Non-HTTP runner error; routes translate these into HTTP responses."""

    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@lru_cache(maxsize=1)
def _get_graph():
    # Defer imports so that importing this module does not force the graph
    # module to load unless a run is actually performed.
    import sys

    sys.path.insert(0, str(_PROJECT_DIR / "src"))
    from graph import compile_graph

    return compile_graph()


def list_case_ids() -> list[str]:
    if not _CASES_DIR.is_dir():
        return []
    return sorted(p.stem for p in _CASES_DIR.glob("*.json"))


def load_case(case_id: str) -> dict[str, Any] | None:
    p = _CASES_DIR / f"{case_id}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as exc:
        raise RunnerError(
            "case_unreadable",
            f"case file unreadable: {case_id} ({exc})",
            http_status=500,
        )


def build_graph_input(
    *,
    case_id: str,
    supervisor_instruction: dict[str, Any] | None,
    retrieval_mode: str | None,
    retrieval_k: int | None,
    operations_mode: str | None,
    governance_mode: str | None,
) -> dict[str, Any]:
    """Translate an API-layer request into a GraphState-compatible dict."""
    gi: dict[str, Any] = {"case_id": case_id}
    if supervisor_instruction is not None:
        # Drop None values so the engine's defaults kick in naturally.
        cleaned = {k: v for k, v in supervisor_instruction.items() if v is not None}
        gi["supervisor_instruction"] = cleaned
    if retrieval_mode is not None:
        gi["retrieval_mode"] = retrieval_mode
    if retrieval_k is not None:
        gi["retrieval_k"] = int(retrieval_k)
    if operations_mode is not None:
        gi["operations_mode"] = operations_mode
    if governance_mode is not None:
        gi["governance_mode"] = governance_mode
    return gi


def validate_supervisor_instruction(
    instruction: dict[str, Any], case_id: str,
) -> None:
    mode = (instruction or {}).get("mode")
    if mode not in ("approve", "verify", "override"):
        raise RunnerError(
            "invalid_supervisor_mode",
            f"supervisor_instruction.mode must be one of "
            f"approve|verify|override, got {mode!r}",
            http_status=400,
        )
    if mode == "override":
        label = (instruction or {}).get("target_action_label")
        if not label:
            # Not strictly required here — the engine/mapper will raise its
            # own explicit error if no alternative is available. We don't
            # fabricate a target silently.
            raise RunnerError(
                "missing_override_target",
                "override decisions require `target_action_label` "
                "(matching an alternative_plan option from the case).",
                http_status=400,
            )


def run_case(
    *,
    case_id: str,
    supervisor_instruction: dict[str, Any] | None = None,
    retrieval_mode: str | None = None,
    retrieval_k: int | None = None,
    operations_mode: str | None = None,
    governance_mode: str | None = None,
) -> dict[str, Any]:
    """Run a single case through the compiled graph and return its state."""
    if not isinstance(case_id, str) or not case_id.strip():
        raise RunnerError(
            "missing_case_id", "case_id must be a non-empty string", 400,
        )
    if load_case(case_id) is None:
        raise RunnerError(
            "case_not_found", f"case {case_id!r} not found under data/cases/",
            http_status=404,
        )

    instruction = supervisor_instruction or {"mode": "approve"}
    validate_supervisor_instruction(instruction, case_id)

    graph = _get_graph()
    graph_input = build_graph_input(
        case_id=case_id,
        supervisor_instruction=instruction,
        retrieval_mode=retrieval_mode,
        retrieval_k=retrieval_k,
        operations_mode=operations_mode,
        governance_mode=governance_mode,
    )
    result = graph.invoke(graph_input)
    return result


def extract_retrieval_summary(result: dict[str, Any]) -> dict[str, Any] | None:
    ops_meta = result.get("_operations_meta") or {}
    return ops_meta.get("retrieval")
