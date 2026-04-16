"""Phase 6 integration tests — advanced retrieval wired into the Operations
Agent path, graph plumbing, and offline benchmark harness.

No live API. Pure deterministic stubs.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

_PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

import rag_setup
import retrieval
from agents.operations_agent import (
    run_operations_agent,
    run_operations_agent_with_meta,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_stores():
    rag_setup.reset_store()
    retrieval.reset_advanced_store()
    yield
    rag_setup.reset_store()
    retrieval.reset_advanced_store()


def _twin_state() -> dict:
    return {
        "active_order": {"order_units": 10},
        "carriers": [
            {"id": "CR_1", "name": "CR_1", "available": True,
             "capacity_limit": 50, "transit_time_hours": 24,
             "cost_per_unit": 10},
        ],
        "warehouses": [
            {"id": "WH_1", "name": "WH_1",
             "current_inventory": 40, "max_capacity": 100},
            {"id": "WH_2", "name": "WH_2",
             "current_inventory": 20, "max_capacity": 80},
        ],
        "customer_zones": [
            {"id": "Z_1", "name": "Z_1", "sla_deadline_hours": 48},
        ],
        "current_disruptions": [
            {"description": "Carrier CR_1 delayed on regional route"}
        ],
    }


def _scenario() -> dict:
    return {
        "scenario_type": "Carrier Capacity Shortage",
        "risk_level": "MEDIUM",
        "exception_description": "Carrier capacity constraints force a retiming decision.",
    }


# ---------------------------------------------------------------------------
# Default path: byte-identical to pre-Phase-6 behavior
# ---------------------------------------------------------------------------

def test_default_retrieval_mode_is_legacy_and_unchanged():
    out_default = run_operations_agent(_twin_state(), _scenario()).to_dict()
    out_explicit = run_operations_agent(
        _twin_state(), _scenario(), retrieval_mode="tfidf_legacy",
    ).to_dict()
    assert out_default == out_explicit


def test_meta_records_legacy_retrieval_by_default():
    _, meta = run_operations_agent_with_meta(_twin_state(), _scenario())
    assert meta["retrieval"]["agent_mode"] == "tfidf_legacy"
    assert meta["retrieval"]["fallback_used"] is False
    assert meta["retrieval"]["reranker_used"] is False
    assert meta["retrieval"]["contextualized"] is False
    assert meta["retrieval"]["candidate_count"] >= 1


# ---------------------------------------------------------------------------
# Mode switching
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode,expected_reranker,expected_context", [
    ("tfidf_legacy", False, False),
    ("dense", False, True),
    ("hybrid", False, True),
    ("hybrid_rerank", True, True),
])
def test_each_agent_retrieval_mode_runs_and_trace_fields_match(
        mode, expected_reranker, expected_context):
    out, meta = run_operations_agent_with_meta(
        _twin_state(), _scenario(), retrieval_mode=mode,
    )
    # Output schema still valid.
    assert out.ranked_candidates
    for c in out.ranked_candidates:
        # Agent contract untouched — evidence refs still populated.
        assert c.evidence_refs
    r = meta["retrieval"]
    assert r["agent_mode"] == mode
    assert r["reranker_used"] is expected_reranker
    assert r["contextualized"] is expected_context
    assert r["fallback_used"] is False
    # candidate_count reflects k (default 4) where available
    assert r["candidate_count"] >= 1


def test_unknown_mode_degrades_to_legacy():
    _, meta = run_operations_agent_with_meta(
        _twin_state(), _scenario(), retrieval_mode="nonsense",
    )
    assert meta["retrieval"]["agent_mode"] == "nonsense"
    # engine_mode is tfidf_legacy because _normalize_agent_mode coerced it
    assert meta["retrieval"]["engine_mode"] == "tfidf_legacy"


# ---------------------------------------------------------------------------
# Advanced failure falls back safely
# ---------------------------------------------------------------------------

def test_advanced_failure_falls_back_to_legacy_and_agent_succeeds(monkeypatch):
    # Force BM25 scoring to explode inside the advanced path.
    def boom(self, q):
        raise RuntimeError("bm25 boom")

    monkeypatch.setattr(retrieval.BM25Index, "score", boom)
    retrieval.reset_advanced_store()

    out, meta = run_operations_agent_with_meta(
        _twin_state(), _scenario(), retrieval_mode="hybrid",
    )
    assert out.ranked_candidates  # agent still produced an answer
    r = meta["retrieval"]
    assert r["fallback_used"] is True
    assert r["error"] is not None
    # Candidates still returned because legacy fallback ran.
    assert r["candidate_count"] >= 1


# ---------------------------------------------------------------------------
# Agent contract compatibility — evidence_refs still well-formed
# ---------------------------------------------------------------------------

def test_evidence_refs_wellformed_across_modes():
    for mode in ("tfidf_legacy", "dense", "hybrid", "hybrid_rerank"):
        out = run_operations_agent(
            _twin_state(), _scenario(), retrieval_mode=mode,
        )
        assert out.ranked_candidates
        for c in out.ranked_candidates:
            for ref in c.evidence_refs:
                assert ref.chunk_id
                assert ref.source_doc
                assert 0.0 <= ref.retrieval_score or ref.retrieval_score < 1e6
                assert isinstance(ref.excerpt, str)


# ---------------------------------------------------------------------------
# Graph plumbing
# ---------------------------------------------------------------------------

def test_graph_default_trace_shows_legacy_retrieval():
    from graph import compile_graph
    graph = compile_graph()
    result = graph.invoke({
        "case_id": "M01",
        "supervisor_instruction": {"mode": "approve"},
    })
    ops_entry = next(
        e for e in result["trace_log"] if e.get("node") == "operations_agent"
    )
    assert ops_entry["retrieval_mode"] == "tfidf_legacy"
    assert ops_entry["retrieval_fallback_used"] is False
    assert ops_entry["retrieval_reranker_used"] is False


def test_graph_retrieval_mode_hybrid_rerank_is_surfaced():
    from graph import compile_graph
    graph = compile_graph()
    result = graph.invoke({
        "case_id": "M01",
        "supervisor_instruction": {"mode": "approve"},
        "retrieval_mode": "hybrid_rerank",
        "retrieval_k": 4,
    })
    ops_entry = next(
        e for e in result["trace_log"] if e.get("node") == "operations_agent"
    )
    assert ops_entry["retrieval_mode"] == "hybrid_rerank"
    assert ops_entry["retrieval_reranker_used"] is True
    assert ops_entry["retrieval_contextualized"] is True
    # Sidecar meta also carries the retrieval summary.
    ops_meta = result["_operations_meta"]
    assert ops_meta["retrieval"]["agent_mode"] == "hybrid_rerank"


# ---------------------------------------------------------------------------
# Benchmark harness
# ---------------------------------------------------------------------------

def test_benchmark_harness_runs_offline_and_returns_expected_shape(tmp_path):
    sys.path.insert(0, str(_PROJECT_DIR / "scripts"))
    try:
        bench = importlib.import_module("retrieval_benchmark")
    finally:
        sys.path.pop(0)

    # Run on a 2-query subset for speed.
    subset = bench.QUERY_SET[:2]
    report = bench.run_benchmark(queries=subset, k=3)

    assert report["k"] == 3
    assert report["modes"] == list(bench.MODES)
    assert len(report["queries"]) == 2
    for qr in report["queries"]:
        for mode in bench.MODES:
            r = qr["modes"][mode]
            assert "top_chunk_ids" in r
            assert "top_source_docs" in r
            assert "latency_ms" in r
            assert "coverage_vs_expected" in r
            assert "jaccard_vs_legacy" in r
            assert "fallback_used" in r

    # Markdown renders without crashing.
    md = bench.render_markdown(report)
    assert "Retrieval Benchmark Report" in md
    assert "tfidf_legacy" in md
    assert "hybrid_rerank" in md

    # CSV writes.
    csv_path = tmp_path / "summary.csv"
    bench.write_csv_summary(report, str(csv_path))
    assert csv_path.exists()
    content = csv_path.read_text()
    assert "mode" in content.splitlines()[0]


def test_benchmark_self_overlap_is_one_for_legacy():
    sys.path.insert(0, str(_PROJECT_DIR / "scripts"))
    try:
        bench = importlib.import_module("retrieval_benchmark")
    finally:
        sys.path.pop(0)

    report = bench.run_benchmark(queries=bench.QUERY_SET[:2], k=4)
    # jaccard_vs_legacy for tfidf_legacy itself must equal 1.0 exactly.
    for qr in report["queries"]:
        assert qr["modes"]["tfidf_legacy"]["jaccard_vs_legacy"] == 1.0
