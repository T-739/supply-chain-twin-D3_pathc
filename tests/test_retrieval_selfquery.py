"""Self-query / metadata-aware retrieval branch — offline tests.

Covers:
- default retrieval behavior unchanged
- deterministic metadata derivation is stable
- deterministic self-query parser is stable
- metadata filters are applied correctly
- self-query modes work offline
- empty-filter fallback to unfiltered hybrid
- parser failure falls back safely
- trace metadata is populated
- benchmark harness supports self-query modes
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


CARRIER_QUERY = "Which carrier expediting rule applies when CR_1 is unavailable?"
ESCALATION_QUERY = "When should the supervisor escalate to override review?"
INVENTORY_QUERY = "Inventory reallocation between warehouses under shortage."
AMBIGUOUS_QUERY = "general guidance"


# ---------------------------------------------------------------------------
# Metadata schema
# ---------------------------------------------------------------------------

def test_derive_chunk_metadata_stable_for_known_docs():
    chunk = {
        "chunk_id": "CSR-02",
        "source_doc": "carrier_selection_rules.md",
        "section": "Rules / Decision Logic",
        "text": "Do not recommend a carrier that is unavailable.",
    }
    meta = retrieval.derive_chunk_metadata(chunk)
    assert meta["doc_type"] == "carrier"
    assert meta["policy_family"] == "carrier_selection"
    assert meta["scenario_family"] == "carrier"
    assert meta["rule_scope"] == "hard_gate"
    # Deterministic.
    assert meta == retrieval.derive_chunk_metadata(chunk)


def test_derive_chunk_metadata_escalation_governance():
    chunk = {
        "chunk_id": "EP-03",
        "source_doc": "escalation_protocol.md",
        "section": "Rules / Decision Logic",
        "text": "VERIFY is appropriate when key facts are missing. Override review ...",
    }
    meta = retrieval.derive_chunk_metadata(chunk)
    assert meta["doc_type"] == "escalation"
    assert meta["policy_family"] == "escalation"
    assert meta["scenario_family"] == "escalation"
    assert meta["agent_relevance"] == "governance"


def test_store_chunks_have_metadata_after_build():
    rag_setup.build_vector_store()
    retrieval.build_advanced_store()
    assert retrieval._store.is_built
    assert retrieval._store.chunks
    for c in retrieval._store.chunks:
        m = c.get("metadata")
        assert m is not None
        for f in ("doc_type", "policy_family", "scenario_family",
                  "agent_relevance", "rule_scope", "source_doc", "section"):
            assert f in m


# ---------------------------------------------------------------------------
# Self-query parser
# ---------------------------------------------------------------------------

def test_default_parser_is_deterministic():
    a = retrieval.default_self_query_parser(CARRIER_QUERY)
    b = retrieval.default_self_query_parser(CARRIER_QUERY)
    assert a == b
    assert a["parser_name"] == "default_self_query_parser"


def test_parser_emits_carrier_policy_filter():
    p = retrieval.default_self_query_parser(CARRIER_QUERY)
    assert p["filters"].get("policy_family") == "carrier_selection"


def test_parser_emits_escalation_when_governance_language():
    p = retrieval.default_self_query_parser(ESCALATION_QUERY)
    assert p["filters"].get("policy_family") == "escalation"
    assert p["filters"].get("agent_relevance") == "governance"


def test_parser_skips_filter_on_ambiguous_query():
    p = retrieval.default_self_query_parser(AMBIGUOUS_QUERY)
    assert p["filters"] == {}


def test_parser_empty_on_empty_string():
    p = retrieval.default_self_query_parser("")
    assert p["filters"] == {}
    assert p["refined_query"] == ""


# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------

def test_self_query_filters_restrict_corpus():
    chunks, trace = retrieval.retrieve_self_query(
        CARRIER_QUERY, base_mode="hybrid", k=4,
    )
    assert trace.self_query is not None
    sq = trace.self_query
    assert sq["filters"].get("policy_family") == "carrier_selection"
    assert sq["filtered_corpus_size"] < sq["full_corpus_size"]
    assert sq["filtered_corpus_size"] > 0
    # Every returned chunk must match the filter.
    for c in chunks:
        assert c["metadata"]["policy_family"] == "carrier_selection"


def test_self_query_no_filter_uses_full_corpus():
    chunks, trace = retrieval.retrieve_self_query(
        AMBIGUOUS_QUERY, base_mode="hybrid", k=3,
    )
    sq = trace.self_query
    assert sq["filters"] == {}
    assert sq["filtered_corpus_size"] == sq["full_corpus_size"]
    assert chunks


def test_filters_override_wins_over_parser():
    # Parser would emit carrier; override forces inventory_transfer.
    chunks, trace = retrieval.retrieve_self_query(
        CARRIER_QUERY, base_mode="hybrid", k=3,
        filters_override={"policy_family": "inventory_transfer"},
    )
    for c in chunks:
        assert c["metadata"]["policy_family"] == "inventory_transfer"
    assert trace.self_query["filters"] == {"policy_family": "inventory_transfer"}


# ---------------------------------------------------------------------------
# retrieve_for_agent dispatch
# ---------------------------------------------------------------------------

def test_retrieve_for_agent_self_hybrid_runs():
    chunks, trace = retrieval.retrieve_for_agent(
        CARRIER_QUERY, mode="self_hybrid", k=3,
    )
    assert chunks
    assert trace.mode == "self_hybrid"
    assert trace.self_query is not None
    assert trace.reranker_name is None


def test_retrieve_for_agent_self_hybrid_rerank_runs():
    chunks, trace = retrieval.retrieve_for_agent(
        CARRIER_QUERY, mode="self_hybrid_rerank", k=3,
    )
    assert chunks
    assert trace.mode == "self_hybrid_rerank"
    assert trace.self_query is not None
    assert trace.reranker_name is not None


def test_summarize_trace_surfaces_self_query_block():
    _, trace = retrieval.retrieve_for_agent(
        ESCALATION_QUERY, mode="self_hybrid_rerank", k=3,
    )
    s = retrieval.summarize_trace(trace, "self_hybrid_rerank")
    assert "self_query" in s
    sq = s["self_query"]
    assert sq["parser_name"] == "default_self_query_parser"
    assert sq["filters"].get("policy_family") == "escalation"


# ---------------------------------------------------------------------------
# Fallback behavior
# ---------------------------------------------------------------------------

def test_empty_filter_match_falls_back_to_unfiltered():
    # Use an override that cannot possibly match any indexed chunk.
    chunks, trace = retrieval.retrieve_self_query(
        CARRIER_QUERY, base_mode="hybrid", k=3,
        filters_override={"policy_family": "no_such_family"},
    )
    assert chunks, "fallback should still return candidates"
    assert trace.fallback_used is True
    assert trace.self_query["filter_empty"] is True
    assert trace.self_query["filtered_corpus_size"] == 0
    assert "filter_empty_fallback" in (trace.error or "")


def test_parser_exception_is_caught_and_treated_as_no_filter():
    def boom(q):
        raise RuntimeError("parser boom")

    chunks, trace = retrieval.retrieve_self_query(
        CARRIER_QUERY, base_mode="hybrid", k=3, parser=boom,
    )
    assert chunks
    # Parser exploded → treated as empty filters, still runs unfiltered.
    assert trace.self_query["filters"] == {}
    assert trace.self_query["filter_empty"] is False
    assert "self_query_parser_failed" in (trace.error or "")


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

def test_existing_agent_modes_have_no_self_query_block():
    for mode in ("tfidf_legacy", "dense", "hybrid", "hybrid_rerank",
                 "multi_hybrid", "multi_hybrid_rerank"):
        _, trace = retrieval.retrieve_for_agent(
            CARRIER_QUERY, mode=mode, k=3,
        )
        assert trace.self_query is None
        s = retrieval.summarize_trace(trace, mode)
        assert "self_query" not in s


def test_unknown_mode_still_degrades_to_legacy():
    _, trace = retrieval.retrieve_for_agent(
        CARRIER_QUERY, mode="self_nonsense", k=3,
    )
    assert trace.mode == "tfidf_legacy"
    assert trace.self_query is None


# ---------------------------------------------------------------------------
# Agent contract compatibility
# ---------------------------------------------------------------------------

def test_self_query_chunks_carry_legacy_shape_fields():
    chunks, _ = retrieval.retrieve_for_agent(
        CARRIER_QUERY, mode="self_hybrid_rerank", k=3,
    )
    for c in chunks:
        for f in ("chunk_id", "source_doc", "section", "text",
                  "retrieval_score", "final_rank"):
            assert f in c
        # Self-query adds metadata but does not remove or rename fields.
        assert "metadata" in c


# ---------------------------------------------------------------------------
# Benchmark integration
# ---------------------------------------------------------------------------

def test_benchmark_harness_supports_self_query_modes():
    sys.path.insert(0, str(_PROJECT_DIR / "scripts"))
    try:
        bench = importlib.import_module("retrieval_benchmark")
        importlib.reload(bench)
    finally:
        sys.path.pop(0)

    assert "self_hybrid" in bench.MODES
    assert "self_hybrid_rerank" in bench.MODES

    report = bench.run_benchmark(queries=bench.QUERY_SET[:2], k=3)
    for qr in report["queries"]:
        for mode in ("hybrid", "hybrid_rerank",
                     "self_hybrid", "self_hybrid_rerank"):
            assert mode in qr["modes"]
            r = qr["modes"][mode]
            assert "top_chunk_ids" in r
            assert "latency_ms" in r

    # Self-query rows carry filter fields.
    for qr in report["queries"]:
        for mode in ("self_hybrid", "self_hybrid_rerank"):
            r = qr["modes"][mode]
            assert "self_query_filters" in r
            assert "self_query_filtered_corpus_size" in r

    md = bench.render_markdown(report)
    assert "self_hybrid" in md
    assert "self_hybrid_rerank" in md
