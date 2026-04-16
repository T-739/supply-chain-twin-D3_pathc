"""Multi-query retrieval branch — offline tests.

Covers:
- default behavior still unchanged
- deterministic query generator is stable
- multi-query mode works offline
- merged candidate set is deduplicated and top-k respected
- reranker only reorders within the merged pool
- multi-query trace metadata is populated
- benchmark harness supports multi-query modes
- fallback to legacy tfidf works on failure
- no live API calls
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

import rag_setup
import retrieval


@pytest.fixture(autouse=True)
def _reset_stores():
    rag_setup.reset_store()
    retrieval.reset_advanced_store()
    yield
    rag_setup.reset_store()
    retrieval.reset_advanced_store()


QUERY = "Carrier CR_1 unavailable — evaluate reallocation under SLA pressure"


# ---------------------------------------------------------------------------
# Default query generator
# ---------------------------------------------------------------------------

def test_default_query_generator_is_deterministic_and_includes_original():
    g1 = retrieval.default_query_generator(QUERY)
    g2 = retrieval.default_query_generator(QUERY)
    assert g1 == g2
    assert g1[0] == QUERY
    assert len(g1) >= 2
    # All entries unique (normalized).
    norm = [" ".join(s.lower().split()) for s in g1]
    assert len(set(norm)) == len(norm)


def test_default_query_generator_empty_returns_empty():
    assert retrieval.default_query_generator("") == []
    assert retrieval.default_query_generator("   ") == []


# ---------------------------------------------------------------------------
# AGENT_RETRIEVAL_MODES additive
# ---------------------------------------------------------------------------

def test_agent_modes_include_multi_query_modes():
    assert "multi_hybrid" in retrieval.AGENT_RETRIEVAL_MODES
    assert "multi_hybrid_rerank" in retrieval.AGENT_RETRIEVAL_MODES
    # Original modes still present.
    for m in ("tfidf_legacy", "dense", "hybrid", "hybrid_rerank"):
        assert m in retrieval.AGENT_RETRIEVAL_MODES


# ---------------------------------------------------------------------------
# retrieve_multi basic flow
# ---------------------------------------------------------------------------

def test_retrieve_multi_returns_k_results_with_trace():
    chunks, trace = retrieval.retrieve_multi(QUERY, base_mode="hybrid", k=4)
    assert len(chunks) <= 4
    assert len(chunks) >= 1
    assert trace.multi_query is not None
    mq = trace.multi_query
    assert mq["sub_query_count"] >= 2
    assert len(mq["sub_queries"]) == mq["sub_query_count"]
    assert mq["merged_count"] >= mq["deduped_count"]
    assert len(mq["per_subquery_candidate_counts"]) == mq["sub_query_count"]
    assert mq["generator_name"] == "default_query_generator"
    assert trace.fallback_used is False


def test_retrieve_multi_candidates_are_unique_by_chunk_id():
    chunks, trace = retrieval.retrieve_multi(QUERY, base_mode="hybrid", k=6)
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))
    # And trace candidates must also be unique.
    t_ids = [c["chunk_id"] for c in trace.candidates]
    assert len(t_ids) == len(set(t_ids))


def test_retrieve_multi_rerank_only_reorders_within_merged_pool():
    # Ask for a very large k so both calls return the full merged pool.
    chunks_no_rr, trace_no_rr = retrieval.retrieve_multi(
        QUERY, base_mode="hybrid", k=1000, rerank=False,
    )
    chunks_rr, trace_rr = retrieval.retrieve_multi(
        QUERY, base_mode="hybrid", k=1000, rerank=True,
    )
    # Reranker must not introduce chunks outside the merged pool.
    pool_ids = {c["chunk_id"] for c in chunks_no_rr}
    rr_ids = {c["chunk_id"] for c in chunks_rr}
    assert rr_ids == pool_ids
    # Reranker name recorded only when rerank=True.
    assert trace_no_rr.reranker_name is None
    assert trace_rr.reranker_name is not None


# ---------------------------------------------------------------------------
# retrieve_for_agent dispatch
# ---------------------------------------------------------------------------

def test_retrieve_for_agent_multi_hybrid_runs_multi():
    chunks, trace = retrieval.retrieve_for_agent(
        QUERY, mode="multi_hybrid", k=4,
    )
    assert chunks
    assert trace.multi_query is not None
    assert trace.mode == "multi_hybrid"
    assert trace.reranker_name is None


def test_retrieve_for_agent_multi_hybrid_rerank_runs_multi_with_reranker():
    chunks, trace = retrieval.retrieve_for_agent(
        QUERY, mode="multi_hybrid_rerank", k=4,
    )
    assert chunks
    assert trace.multi_query is not None
    assert trace.mode == "multi_hybrid_rerank"
    assert trace.reranker_name is not None


def test_summarize_trace_surfaces_multi_query_block():
    _, trace = retrieval.retrieve_for_agent(
        QUERY, mode="multi_hybrid_rerank", k=3,
    )
    s = retrieval.summarize_trace(trace, "multi_hybrid_rerank")
    assert s["agent_mode"] == "multi_hybrid_rerank"
    assert "multi_query" in s
    mq = s["multi_query"]
    assert mq["sub_query_count"] >= 2
    assert mq["deduped_count"] >= 1
    assert mq["generator_name"] == "default_query_generator"


# ---------------------------------------------------------------------------
# Backward compatibility — single-query modes unchanged
# ---------------------------------------------------------------------------

def test_single_query_modes_trace_has_no_multi_query_field_set():
    for mode in ("tfidf_legacy", "dense", "hybrid", "hybrid_rerank"):
        _, trace = retrieval.retrieve_for_agent(QUERY, mode=mode, k=3)
        assert trace.multi_query is None
        s = retrieval.summarize_trace(trace, mode)
        assert "multi_query" not in s


def test_unknown_mode_still_degrades_to_legacy_not_multi():
    _, trace = retrieval.retrieve_for_agent(QUERY, mode="multi_nonsense", k=3)
    assert trace.mode == "tfidf_legacy"
    assert trace.multi_query is None


# ---------------------------------------------------------------------------
# Pluggable generator
# ---------------------------------------------------------------------------

def test_custom_query_generator_is_honored():
    custom = lambda q: [q, f"policy: {q}", f"ops: {q}"]
    custom.name = "custom_gen"  # type: ignore[attr-defined]

    _, trace = retrieval.retrieve_multi(
        QUERY, base_mode="hybrid", k=4, query_generator=custom,
    )
    assert trace.multi_query["generator_name"] == "custom_gen"
    assert trace.multi_query["sub_query_count"] == 3


def test_generator_returning_only_original_still_works():
    gen = lambda q: [q]
    chunks, trace = retrieval.retrieve_multi(
        QUERY, base_mode="hybrid", k=3, query_generator=gen,
    )
    assert chunks
    assert trace.multi_query["sub_query_count"] == 1


# ---------------------------------------------------------------------------
# Fallback to single-query on failure
# ---------------------------------------------------------------------------

def test_multi_query_falls_back_when_generator_raises():
    def boom(q):
        raise RuntimeError("gen boom")

    chunks, trace = retrieval.retrieve_multi(
        QUERY, base_mode="hybrid", k=3, query_generator=boom,
    )
    assert trace.fallback_used is True
    assert "multi_query_failed" in (trace.error or "")
    # Legacy fallback still produces candidates.
    assert chunks


def test_multi_query_falls_back_when_advanced_store_explodes(monkeypatch):
    # Force BM25 scoring to explode inside every sub-query.
    def boom(self, q):
        raise RuntimeError("bm25 boom")

    monkeypatch.setattr(retrieval.BM25Index, "score", boom)
    retrieval.reset_advanced_store()

    _, trace = retrieval.retrieve_for_agent(
        QUERY, mode="multi_hybrid", k=3,
    )
    # Sub-calls will themselves fall back to legacy via retrieve_advanced,
    # so the merged multi-query pool is still built — fallback is "soft".
    # Trace.error should reflect a subquery fallback notification.
    assert trace.error is not None


# ---------------------------------------------------------------------------
# Benchmark harness integration
# ---------------------------------------------------------------------------

def test_benchmark_harness_supports_multi_query_modes(tmp_path):
    sys.path.insert(0, str(_PROJECT_DIR / "scripts"))
    try:
        bench = importlib.import_module("retrieval_benchmark")
        importlib.reload(bench)
    finally:
        sys.path.pop(0)

    # Sanity: multi modes are registered.
    assert "multi_hybrid" in bench.MODES
    assert "multi_hybrid_rerank" in bench.MODES

    subset = bench.QUERY_SET[:2]
    report = bench.run_benchmark(queries=subset, k=3)

    # Every mode entry appears, including multi.
    for qr in report["queries"]:
        for mode in ("tfidf_legacy", "hybrid", "hybrid_rerank",
                     "multi_hybrid", "multi_hybrid_rerank"):
            assert mode in qr["modes"]
            r = qr["modes"][mode]
            assert "top_chunk_ids" in r
            assert "latency_ms" in r

    # Multi-query rows carry sub_query_count in the benchmark row.
    for qr in report["queries"]:
        for mode in ("multi_hybrid", "multi_hybrid_rerank"):
            r = qr["modes"][mode]
            assert r["sub_query_count"] is not None
            assert r["sub_query_count"] >= 2

    # Markdown renders.
    md = bench.render_markdown(report)
    assert "multi_hybrid" in md
    assert "multi_hybrid_rerank" in md


# ---------------------------------------------------------------------------
# Evidence shape unchanged (agent contract)
# ---------------------------------------------------------------------------

def test_multi_query_chunks_carry_legacy_shape_fields():
    chunks, _ = retrieval.retrieve_for_agent(
        QUERY, mode="multi_hybrid_rerank", k=3,
    )
    for c in chunks:
        for field in ("chunk_id", "source_doc", "section", "text",
                      "retrieval_score", "final_rank"):
            assert field in c
        # Multi-query extras are additive, not required by agent.
        assert "multi_query_rrf_score" in c
        assert "sub_query_hits" in c
