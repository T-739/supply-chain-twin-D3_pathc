"""Phase 7 API integration tests — fully offline.

Uses fastapi's TestClient against a freshly built FastAPI app. All engine
work is done through the existing compiled graph; no live API calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

_PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

from api import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Discovery endpoints
# ---------------------------------------------------------------------------

def test_health(client: TestClient):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "supply-chain-twin-api"


def test_modes_lists_retrieval_and_supervisor_modes(client: TestClient):
    r = client.get("/api/v1/modes")
    assert r.status_code == 200
    body = r.json()
    for m in ("tfidf_legacy", "hybrid", "hybrid_rerank",
              "multi_hybrid", "self_hybrid", "hybrid_rerank_compress"):
        assert m in body["retrieval_modes"]
    assert set(body["supervisor_modes"]) == {"approve", "verify", "override"}
    assert set(body["operations_modes"]) == {"rules", "llm"}
    assert set(body["governance_modes"]) == {"rules", "llm"}


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

def test_list_cases_returns_expected_shape(client: TestClient):
    r = client.get("/api/v1/cases")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert body["count"] == len(body["cases"])
    assert any(c["case_id"] == "M01" for c in body["cases"])
    for c in body["cases"][:3]:
        assert "scenario_type" in c
        assert "risk_level" in c


def test_get_case_returns_raw_json(client: TestClient):
    r = client.get("/api/v1/cases/M01")
    assert r.status_code == 200
    body = r.json()
    # Authoritative case JSON fields are present; API does not invent them.
    assert body.get("case_id") == "M01"
    assert "oracle" in body
    assert "decision_options" in body


def test_get_case_not_found_returns_404(client: TestClient):
    r = client.get("/api/v1/cases/DOES_NOT_EXIST")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "case_not_found"


# ---------------------------------------------------------------------------
# Run endpoint — default + mode plumbing
# ---------------------------------------------------------------------------

def test_run_default_mode_succeeds_and_matches_engine_shape(client: TestClient):
    r = client.post("/api/v1/runs", json={"case_id": "M01"})
    assert r.status_code == 200
    body = r.json()

    assert body["case_id"] == "M01"
    # Structured domain outputs are passed through verbatim.
    assert body["operations_output"]["ranked_candidates"]
    assert body["supervisor_output"]["supervisor_decision_type"] == "APPROVE"
    ev = body["evaluation_result"]
    assert ev["status"] == "ok"
    # Evaluation truth still comes from the frozen bridge — never fabricated.
    assert ev["oracle_action_code"] in ("AI", "ALT1", "ALT2")
    # Default retrieval is deterministic tfidf_legacy.
    assert body["retrieval_summary"]["agent_mode"] == "tfidf_legacy"


def test_run_retrieval_mode_is_surfaced(client: TestClient):
    r = client.post("/api/v1/runs", json={
        "case_id": "M01",
        "retrieval_mode": "hybrid_rerank",
        "retrieval_k": 3,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["retrieval_summary"]["agent_mode"] == "hybrid_rerank"
    assert body["retrieval_summary"]["reranker_used"] is True
    assert body["resolved_modes"]["retrieval_mode"] == "hybrid_rerank"


def test_run_unknown_retrieval_mode_degrades_to_legacy(client: TestClient):
    r = client.post("/api/v1/runs", json={
        "case_id": "M01",
        "retrieval_mode": "nonsense_mode",
    })
    assert r.status_code == 200
    body = r.json()
    # Engine-side _normalize_agent_mode coerces unknown → tfidf_legacy.
    assert body["retrieval_summary"]["engine_mode"] == "tfidf_legacy"


def test_run_unknown_case_returns_404(client: TestClient):
    r = client.post("/api/v1/runs", json={"case_id": "NOPE_99"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "case_not_found"


def test_run_unknown_supervisor_mode_returns_422(client: TestClient):
    r = client.post("/api/v1/runs", json={
        "case_id": "M01",
        "supervisor_instruction": {"mode": "reject"},
    })
    # FastAPI's Literal validation → 422.
    assert r.status_code == 422


def test_run_override_without_target_label_returns_400(client: TestClient):
    r = client.post("/api/v1/runs", json={
        "case_id": "M01",
        "supervisor_instruction": {"mode": "override"},
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "missing_override_target"


def test_run_verify_mode_produces_verify_decision(client: TestClient):
    r = client.post("/api/v1/runs", json={
        "case_id": "M01",
        "supervisor_instruction": {
            "mode": "verify",
            "review_focus": "check assumptions",
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert body["supervisor_output"]["supervisor_decision_type"] == "VERIFY"


# ---------------------------------------------------------------------------
# Trace / observability
# ---------------------------------------------------------------------------

def test_run_trace_log_contains_expected_nodes(client: TestClient):
    r = client.post("/api/v1/runs", json={"case_id": "M01"})
    body = r.json()
    nodes = {e.get("node") for e in body["trace_log"]}
    for n in ("load_case_or_scenario", "operations_agent", "cost_agent",
              "governance_agent", "supervisor", "evaluation"):
        assert n in nodes


def test_run_retrieval_summary_has_top_chunk_ids(client: TestClient):
    r = client.post("/api/v1/runs", json={
        "case_id": "M01",
        "retrieval_mode": "hybrid_rerank",
    })
    body = r.json()
    rs = body["retrieval_summary"]
    assert rs is not None
    assert rs["candidate_count"] >= 1
    assert rs["top_chunk_ids"]


# ---------------------------------------------------------------------------
# Supervisor-action convenience endpoint
# ---------------------------------------------------------------------------

def test_supervisor_action_approve_endpoint(client: TestClient):
    r = client.post("/api/v1/runs/supervisor-action", json={
        "case_id": "M01",
        "decision": "approve",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["supervisor_output"]["supervisor_decision_type"] == "APPROVE"


def test_supervisor_action_override_requires_target(client: TestClient):
    r = client.post("/api/v1/runs/supervisor-action", json={
        "case_id": "M01",
        "decision": "override",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "missing_override_target"


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def test_batch_runs_small_matrix_and_returns_rows(client: TestClient):
    r = client.post("/api/v1/batch", json={
        "case_ids": ["M01"],
        "supervisor_modes": ["approve", "verify"],
        "retrieval_modes": ["tfidf_legacy", "hybrid"],
        "retrieval_k": 3,
    })
    assert r.status_code == 200
    body = r.json()
    # 1 case × 2 supervisors × 2 retrievals = 4 rows.
    assert body["row_count"] == 4
    assert len(body["rows"]) == 4
    agg = body["aggregations"]
    assert "overall" in agg
    assert "by_supervisor_mode" in agg
    assert "by_retrieval_mode" in agg
    assert body["persisted_paths"] is None


def test_batch_persist_writes_artifacts(client: TestClient, tmp_path, monkeypatch):
    # Redirect _PROJECT_DIR for phase6 batch writer — we only check that
    # the API reports persisted_paths; actual file I/O goes to the real
    # data/phase6_eval/ directory. Delete after.
    r = client.post("/api/v1/batch", json={
        "case_ids": ["M01"],
        "supervisor_modes": ["approve"],
        "retrieval_modes": ["tfidf_legacy"],
        "persist": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["persisted_paths"] is not None
    for key in ("rows_csv", "summary_json", "report_md"):
        assert Path(body["persisted_paths"][key]).exists()


def test_batch_latest_endpoint_returns_summary_after_persist(client: TestClient):
    # Persist something first to guarantee latest exists.
    client.post("/api/v1/batch", json={
        "case_ids": ["M01"],
        "supervisor_modes": ["approve"],
        "retrieval_modes": ["tfidf_legacy"],
        "persist": True,
    })
    r = client.get("/api/v1/batch/latest")
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body and "aggregations" in body


# ---------------------------------------------------------------------------
# No duplication of business logic
# ---------------------------------------------------------------------------

def test_api_does_not_redefine_evaluation_truth(client: TestClient):
    """API responses must reflect case JSON + evaluation.py truth exactly."""
    case_path = _PROJECT_DIR / "data" / "cases" / "M01.json"
    case = json.loads(case_path.read_text())
    oracle_code = str(case["oracle"]["action_code"])

    r = client.post("/api/v1/runs", json={"case_id": "M01"})
    ev = r.json()["evaluation_result"]
    assert ev["oracle_action_code"] == oracle_code
    assert ev["oracle_cost"] == float(case["oracle"]["cost_total"])
