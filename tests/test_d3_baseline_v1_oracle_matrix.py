"""Phase 0: byte-exact oracle matrix snapshot over compile_graph().

Matrix definition (rationale — see §3 of the Phase 0 correction review
package):

  cases : the canonical 20 research-core cases shipped in data/cases/
          (sorted lexicographically, no subset).
  modes : ``supervisor_mode ∈ {approve, verify, override}``

This is the only "3 modes" axis already present in the repo, already
named in the compile_graph() state contract
(``state["supervisor_instruction"]["mode"]``), already tested by
``scripts/phase6_batch_eval.py``, and already documented in the Phase 6
runner docstring as the canonical supervisor-mode triple. Choosing it
here introduces zero new interpretation space.

Fixed axes held constant to keep the snapshot deterministic and small:
  retrieval_mode = "tfidf_legacy"   (deterministic baseline)
  operations_mode, governance_mode = default ("rules")

For each (case_id, mode) we record a stable, time-independent subset of
the graph output — specifically the ``evaluation_result`` fields (which
are derived deterministically from case JSON + evaluation.py), plus the
governance risk level, policy route, and override target label. We do
NOT record latency_ms, trace_log, or any object id / timestamp.

Byte-exact compare, no normalization. Path C must not contaminate the
Research Core, so this test is strictly a *read-only* snapshot of Path B
behavior.
"""

import glob
import json
import os
import sys
from pathlib import Path

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

_FIXTURE = os.path.join(
    _PROJECT_DIR, "tests", "fixtures", "d3_baseline_v1_oracle_matrix.json"
)


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


_RECORDED_FIELDS = (
    "status",
    "supervisor_decision_type",
    "human_action_code",
    "agent_action_code",
    "oracle_action_code",
    "chosen_cost",
    "oracle_cost",
    "regret",
    "is_override",
    "is_unnecessary_override",
    "override_effectiveness",
)


def _load_case(cid: str) -> dict:
    with open(os.path.join(_PROJECT_DIR, "data", "cases", f"{cid}.json")) as f:
        return json.load(f)


def _run_matrix() -> dict:
    from action_code_mapper import find_override_target_label
    from graph import compile_graph

    app = compile_graph()
    case_ids = sorted(
        Path(p).stem
        for p in glob.glob(os.path.join(_PROJECT_DIR, "data", "cases", "*.json"))
    )
    assert len(case_ids) == 20, f"expected 20 cases, got {len(case_ids)}"

    matrix: dict = {}
    for cid in case_ids:
        case = _load_case(cid)
        matrix[cid] = {}
        for mode in ("approve", "verify", "override"):
            instruction: dict = {"mode": mode}
            override_target = None
            if mode == "override":
                override_target = find_override_target_label(case)
                if not override_target:
                    matrix[cid][mode] = {"status": "skipped_no_override_target"}
                    continue
                instruction["target_action_label"] = override_target

            result = app.invoke({
                "case_id": cid,
                "supervisor_instruction": instruction,
                "retrieval_mode": "tfidf_legacy",
            })

            ev = result.get("evaluation_result", {}) or {}
            gov = result.get("governance_output", {}) or {}
            pd = result.get("policy_decision", {}) or {}

            row = {k: ev.get(k) for k in _RECORDED_FIELDS}
            row["override_target_label"] = override_target
            row["governance_risk_level"] = gov.get("risk_level")
            row["policy_route"] = pd.get("route")
            matrix[cid][mode] = row
    return matrix


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def test_oracle_matrix_exact():
    produced = _canonical(_run_matrix())

    with open(_FIXTURE, "rb") as f:
        expected = f.read().decode("utf-8")

    assert produced == expected, (
        "Oracle matrix snapshot diverged. If this is an intentional Research "
        "Core change, update the fixture and bump any affected schema_version "
        "in PATH_C_SCHEMA_REGISTRY.md."
    )
