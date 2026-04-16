"""Context compression branch — offline tests.

Covers:
- default retrieval behavior unchanged
- deterministic compressor is stable
- compression never introduces/removes/reorders chunks
- compression preserves provenance (chunk_id, source_doc, section,
  retrieval_score)
- compressed modes run offline
- compressor failure falls back to uncompressed chunks
- trace metadata populated and surfaced via summarize_trace
- benchmark harness supports compressed modes
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


QUERY = "Carrier CR_1 unavailable — expedite reallocation under SLA pressure"


# ---------------------------------------------------------------------------
# Default compressor unit behavior
# ---------------------------------------------------------------------------

def test_default_compressor_is_deterministic_and_preserves_identity():
    chunks = [
        {
            "chunk_id": "CSR-02",
            "source_doc": "carrier_selection_rules.md",
            "section": "Rules / Decision Logic",
            "text": (
                "Availability is a hard gate. Do not recommend a carrier that is "
                "unavailable. Capacity is also a hard feasibility gate. "
                "Compliance comes before speed."
            ),
            "retrieval_score": 0.7,
        },
        {
            "chunk_id": "SLA-01",
            "source_doc": "sla_terms.md",
            "section": "Purpose",
            "text": "SLA defines delivery promise. Breach means missing the deadline.",
            "retrieval_score": 0.5,
        },
    ]
    out1 = retrieval.default_compressor(QUERY, chunks)
    out2 = retrieval.default_compressor(QUERY, chunks)
    assert out1 == out2
    # Identity preserved.
    assert [c["chunk_id"] for c in out1] == [c["chunk_id"] for c in chunks]
    assert [c["source_doc"] for c in out1] == [c["source_doc"] for c in chunks]
    assert [c["retrieval_score"] for c in out1] == [
        c["retrieval_score"] for c in chunks
    ]
    # Provenance preserved, raw_text attached, compression flag on.
    for a, b in zip(chunks, out1):
        assert b["raw_text"] == a["text"]
        assert b["compressed_text"] == b["text"]
        assert b["compression_applied"] is True
        assert b["compressed_length"] <= b["raw_length"]


def test_default_compressor_empty_chunks_is_noop():
    assert retrieval.default_compressor(QUERY, []) == []


def test_default_compressor_no_query_overlap_falls_back_to_first_sentence():
    chunks = [{
        "chunk_id": "X-1",
        "source_doc": "x.md",
        "section": "",
        "text": "Alpha beta gamma. Delta epsilon zeta. Eta theta iota.",
    }]
    out = retrieval.default_compressor("nothing matches here", chunks)
    # Should not be empty; should start with the first sentence.
    assert out[0]["compressed_text"].startswith("Alpha beta gamma")


# ---------------------------------------------------------------------------
# apply_compression envelope
# ---------------------------------------------------------------------------

def test_apply_compression_returns_summary_with_expected_shape():
    chunks = [
        {"chunk_id": "A", "source_doc": "a.md", "section": "", "text": "Hello world. Test."},
        {"chunk_id": "B", "source_doc": "b.md", "section": "", "text": "Another text here."},
    ]
    out, summary = retrieval.apply_compression(QUERY, chunks)
    assert len(out) == 2
    assert summary["raw_chunk_count"] == 2
    assert summary["compressed_chunk_count"] == 2
    assert summary["compressor_name"] == "default_compressor"
    assert summary["fallback_used"] is False
    assert 0.0 < summary["compression_ratio"] <= 1.0
    assert len(summary["per_chunk"]) == 2
    for p in summary["per_chunk"]:
        assert "chunk_id" in p and "raw_length" in p and "compressed_length" in p


def test_apply_compression_falls_back_on_compressor_exception():
    chunks = [
        {"chunk_id": "A", "source_doc": "a.md", "section": "", "text": "x"},
    ]

    def boom(q, cs, **kw):
        raise RuntimeError("compressor boom")

    out, summary = retrieval.apply_compression(QUERY, chunks, compressor=boom)
    assert out == chunks  # unchanged
    assert summary["fallback_used"] is True
    assert "error" in summary


def test_apply_compression_rejects_compressor_that_reorders_or_drops():
    chunks = [
        {"chunk_id": "A", "source_doc": "a.md", "section": "", "text": "x"},
        {"chunk_id": "B", "source_doc": "b.md", "section": "", "text": "y"},
    ]

    def bad(q, cs, **kw):
        return list(reversed(cs))

    out, summary = retrieval.apply_compression(QUERY, chunks, compressor=bad)
    assert out == chunks  # unchanged
    assert summary["fallback_used"] is True


# ---------------------------------------------------------------------------
# Agent-facing compressed modes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode,base_mode", [
    ("hybrid_rerank_compress", "hybrid_rerank"),
    ("multi_hybrid_rerank_compress", "multi_hybrid_rerank"),
    ("self_hybrid_rerank_compress", "self_hybrid_rerank"),
])
def test_compress_mode_preserves_chunk_identity_vs_base(mode, base_mode):
    base_chunks, base_trace = retrieval.retrieve_for_agent(
        QUERY, mode=base_mode, k=3,
    )
    comp_chunks, comp_trace = retrieval.retrieve_for_agent(
        QUERY, mode=mode, k=3,
    )
    # Same chunk count, same chunk_ids in same order, same source_doc.
    assert len(comp_chunks) == len(base_chunks)
    assert [c["chunk_id"] for c in comp_chunks] == [
        c["chunk_id"] for c in base_chunks
    ]
    assert [c["source_doc"] for c in comp_chunks] == [
        c["source_doc"] for c in base_chunks
    ]
    # retrieval_score preserved.
    assert [c["retrieval_score"] for c in comp_chunks] == [
        c["retrieval_score"] for c in base_chunks
    ]
    # Compression annotations present.
    for c in comp_chunks:
        assert c.get("compression_applied") is True
        assert "raw_text" in c
        assert "compressed_text" in c
        assert c["compressed_length"] <= c["raw_length"]
    assert comp_trace.compression is not None


def test_compress_mode_does_not_increase_total_chars():
    base_chunks, _ = retrieval.retrieve_for_agent(
        QUERY, mode="hybrid_rerank", k=4,
    )
    comp_chunks, comp_trace = retrieval.retrieve_for_agent(
        QUERY, mode="hybrid_rerank_compress", k=4,
    )
    raw_total = sum(len(c["text"]) for c in base_chunks)
    comp_total = sum(len(c["text"]) for c in comp_chunks)
    assert comp_total <= raw_total
    assert comp_trace.compression["compression_ratio"] <= 1.0


def test_compress_mode_summary_surfaces_in_summarize_trace():
    _, trace = retrieval.retrieve_for_agent(
        QUERY, mode="hybrid_rerank_compress", k=3,
    )
    s = retrieval.summarize_trace(trace, "hybrid_rerank_compress")
    assert "compression" in s
    c = s["compression"]
    assert c["compressor_name"] == "default_compressor"
    assert c["compressed_chunk_count"] == c["raw_chunk_count"]
    assert c["fallback_used"] is False


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

def test_existing_modes_have_no_compression_block():
    for mode in ("tfidf_legacy", "dense", "hybrid", "hybrid_rerank",
                 "multi_hybrid", "multi_hybrid_rerank",
                 "self_hybrid", "self_hybrid_rerank"):
        chunks, trace = retrieval.retrieve_for_agent(QUERY, mode=mode, k=3)
        assert trace.compression is None
        s = retrieval.summarize_trace(trace, mode)
        assert "compression" not in s
        # text field unchanged — no compression annotations.
        for c in chunks:
            assert "compression_applied" not in c


def test_unknown_compress_mode_degrades_to_legacy():
    _, trace = retrieval.retrieve_for_agent(
        QUERY, mode="nonsense_compress", k=3,
    )
    # _normalize_agent_mode maps unknown to tfidf_legacy → no compression path.
    assert trace.mode == "tfidf_legacy"
    assert trace.compression is None


# ---------------------------------------------------------------------------
# Agent contract compatibility
# ---------------------------------------------------------------------------

def test_compress_chunks_still_carry_legacy_shape_fields():
    chunks, _ = retrieval.retrieve_for_agent(
        QUERY, mode="hybrid_rerank_compress", k=3,
    )
    for c in chunks:
        for f in ("chunk_id", "source_doc", "section", "text",
                  "retrieval_score", "final_rank"):
            assert f in c


# ---------------------------------------------------------------------------
# Benchmark integration
# ---------------------------------------------------------------------------

def test_benchmark_harness_supports_compress_modes():
    sys.path.insert(0, str(_PROJECT_DIR / "scripts"))
    try:
        bench = importlib.import_module("retrieval_benchmark")
        importlib.reload(bench)
    finally:
        sys.path.pop(0)

    for m in ("hybrid_rerank_compress",
              "multi_hybrid_rerank_compress",
              "self_hybrid_rerank_compress"):
        assert m in bench.MODES

    report = bench.run_benchmark(queries=bench.QUERY_SET[:2], k=3)
    for qr in report["queries"]:
        for mode in ("hybrid_rerank", "hybrid_rerank_compress",
                     "multi_hybrid_rerank", "multi_hybrid_rerank_compress",
                     "self_hybrid_rerank", "self_hybrid_rerank_compress"):
            assert mode in qr["modes"]
            r = qr["modes"][mode]
            assert "top_chunk_ids" in r

    # Compressed rows carry compression_ratio; non-compress rows don't.
    for qr in report["queries"]:
        for mode in ("hybrid_rerank_compress",
                     "multi_hybrid_rerank_compress",
                     "self_hybrid_rerank_compress"):
            r = qr["modes"][mode]
            assert r["compression_ratio"] is not None
            assert 0.0 < r["compression_ratio"] <= 1.0
            assert r["compression_compressor_name"] == "default_compressor"
            assert r["compression_fallback_used"] is False

    md = bench.render_markdown(report)
    assert "hybrid_rerank_compress" in md
