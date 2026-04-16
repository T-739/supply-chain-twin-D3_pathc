"""
test_rag_setup.py — Minimal tests for the local RAG retrieval layer (Package 2A).

Verifies:
  1. Knowledge docs listing works
  2. Excluded meta doc is not indexed
  3. build_vector_store runs and returns chunk count
  4. retrieve() returns results for obvious queries
  5. Returned metadata includes source_doc, text, chunk_id, section, retrieval_score
  6. Invalid query raises ValueError
  7. Invalid k raises ValueError
  8. Results are JSON-serializable
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rag_setup import (
    CORE_DOCS,
    build_vector_store,
    list_knowledge_docs,
    reset_store,
    retrieve,
)


@pytest.fixture(autouse=True)
def _fresh_store():
    """Reset the vector store before each test."""
    reset_store()
    yield
    reset_store()


# ---------------------------------------------------------------------------
# Document listing
# ---------------------------------------------------------------------------


class TestListKnowledgeDocs:
    def test_lists_five_core_docs(self):
        docs = list_knowledge_docs()
        assert len(docs) == 5
        filenames = {d["filename"] for d in docs}
        assert filenames == set(CORE_DOCS)

    def test_all_core_docs_present(self):
        docs = list_knowledge_docs()
        for d in docs:
            assert d["status"] == "present", f"{d['filename']} is {d['status']}"

    def test_excluded_meta_doc_not_listed(self):
        docs = list_knowledge_docs()
        filenames = {d["filename"] for d in docs}
        assert "rag_knowledge_usage_notes.md" not in filenames

    def test_missing_directory_raises(self):
        with pytest.raises(FileNotFoundError):
            list_knowledge_docs(knowledge_dir="/nonexistent/path")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


class TestBuildVectorStore:
    def test_build_returns_positive_chunk_count(self):
        n = build_vector_store(force_rebuild=True)
        assert n > 0

    def test_build_idempotent_without_force(self):
        n1 = build_vector_store()
        n2 = build_vector_store()  # should return cached count
        assert n1 == n2

    def test_rebuild_with_force(self):
        n1 = build_vector_store()
        n2 = build_vector_store(force_rebuild=True)
        assert n1 == n2  # same docs, same count

    def test_excluded_doc_not_indexed(self):
        build_vector_store(force_rebuild=True)
        results = retrieve("knowledge usage notes meta document", k=20)
        source_docs = {r["source_doc"] for r in results}
        assert "rag_knowledge_usage_notes.md" not in source_docs


# ---------------------------------------------------------------------------
# Retrieve
# ---------------------------------------------------------------------------


class TestRetrieve:
    @pytest.fixture(autouse=True)
    def _build(self):
        build_vector_store(force_rebuild=True)

    def test_returns_results_for_carrier_query(self):
        results = retrieve("carrier disruption reassignment", k=3)
        assert len(results) == 3
        # At least one result should come from carrier_selection_rules.md
        sources = {r["source_doc"] for r in results}
        assert "carrier_selection_rules.md" in sources

    def test_returns_results_for_sla_query(self):
        results = retrieve("SLA deadline penalty breach", k=3)
        assert len(results) >= 1
        sources = {r["source_doc"] for r in results}
        assert "sla_terms.md" in sources

    def test_returns_results_for_inventory_query(self):
        results = retrieve("inventory transfer warehouse capacity", k=3)
        assert len(results) >= 1
        sources = {r["source_doc"] for r in results}
        assert "inventory_transfer_policy.md" in sources

    def test_returns_results_for_escalation_query(self):
        results = retrieve("escalation override approve verify", k=3)
        assert len(results) >= 1
        sources = {r["source_doc"] for r in results}
        assert "escalation_protocol.md" in sources

    def test_result_metadata_fields(self):
        results = retrieve("exception handling", k=1)
        assert len(results) == 1
        r = results[0]
        assert "text" in r
        assert "source_doc" in r
        assert "chunk_id" in r
        assert "section" in r
        assert "retrieval_score" in r
        assert isinstance(r["text"], str)
        assert len(r["text"]) > 0
        assert isinstance(r["retrieval_score"], float)

    def test_results_ordered_by_score(self):
        results = retrieve("carrier expediting feasibility", k=5)
        scores = [r["retrieval_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_results_json_serializable(self):
        results = retrieve("compliance documentation", k=3)
        serialized = json.dumps(results)
        roundtrip = json.loads(serialized)
        assert len(roundtrip) == len(results)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.fixture(autouse=True)
    def _build(self):
        build_vector_store(force_rebuild=True)

    def test_empty_query_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            retrieve("", k=3)

    def test_whitespace_query_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            retrieve("   ", k=3)

    def test_invalid_k_zero_raises(self):
        with pytest.raises(ValueError):
            retrieve("test query", k=0)

    def test_invalid_k_negative_raises(self):
        with pytest.raises(ValueError):
            retrieve("test query", k=-1)

    def test_retrieve_before_build_raises(self):
        reset_store()
        with pytest.raises(RuntimeError, match="not built"):
            retrieve("test query", k=3)
