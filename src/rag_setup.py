"""
rag_setup.py — Lightweight local RAG retrieval for business-rule knowledge docs.

Uses TF-IDF + cosine similarity over markdown chunks from data/knowledge/.
No external API or embedding service required.

Only the five core business-rule documents are indexed by default:
  - exception_handling_sop.md
  - sla_terms.md
  - carrier_selection_rules.md
  - escalation_protocol.md
  - inventory_transfer_policy.md

The meta-document rag_knowledge_usage_notes.md is excluded from retrieval.

Chunk boundaries are detected from <!-- CHUNK: XX-NN --> markers embedded
in the markdown files. Section headings (## lines) are captured as metadata.

This module does NOT define oracle truth, cost truth, or evaluation logic.
"""

from __future__ import annotations

import os
import re
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_KNOWLEDGE_DIR = os.path.join(os.path.dirname(_BASE_DIR), "data", "knowledge")

CORE_DOCS: list[str] = [
    "exception_handling_sop.md",
    "sla_terms.md",
    "carrier_selection_rules.md",
    "escalation_protocol.md",
    "inventory_transfer_policy.md",
]

_EXCLUDED_DOCS: set[str] = {"rag_knowledge_usage_notes.md"}

_CHUNK_RE = re.compile(r"<!--\s*CHUNK:\s*([\w-]+)\s*-->")
_SECTION_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Chunk parsing
# ---------------------------------------------------------------------------


def _parse_chunks(text: str, source_doc: str) -> list[dict[str, Any]]:
    """Split markdown text on <!-- CHUNK: XX-NN --> markers.

    Returns a list of dicts with keys: chunk_id, source_doc, section, text.
    If no CHUNK markers are found, the entire document is one chunk.
    """
    markers = list(_CHUNK_RE.finditer(text))

    if not markers:
        # Whole document as a single chunk
        section = ""
        m = _SECTION_RE.search(text)
        if m:
            section = m.group(2).strip()
        return [
            {
                "chunk_id": f"{source_doc}::0",
                "source_doc": source_doc,
                "section": section,
                "text": text.strip(),
            }
        ]

    chunks: list[dict[str, Any]] = []
    for i, marker in enumerate(markers):
        chunk_id = marker.group(1)  # e.g. "EH-01"
        start = marker.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        chunk_text = text[start:end].strip()

        # Find the first ## heading in this chunk
        section = ""
        sec_match = _SECTION_RE.search(chunk_text)
        if sec_match:
            section = sec_match.group(2).strip()

        chunks.append(
            {
                "chunk_id": chunk_id,
                "source_doc": source_doc,
                "section": section,
                "text": chunk_text,
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# Document listing
# ---------------------------------------------------------------------------


def list_knowledge_docs(
    knowledge_dir: str | None = None,
) -> list[dict[str, str]]:
    """List all core business-rule docs available for indexing.

    Returns a list of dicts with keys: filename, path, status.
    Excludes meta-documents (e.g. rag_knowledge_usage_notes.md).
    Raises FileNotFoundError if the knowledge directory does not exist.
    """
    kdir = knowledge_dir or _DEFAULT_KNOWLEDGE_DIR
    if not os.path.isdir(kdir):
        raise FileNotFoundError(f"Knowledge directory not found: {kdir}")

    results: list[dict[str, str]] = []
    for doc_name in CORE_DOCS:
        path = os.path.join(kdir, doc_name)
        status = "present" if os.path.isfile(path) else "missing"
        results.append({"filename": doc_name, "path": path, "status": status})
    return results


# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------


class _VectorStore:
    """Lightweight in-memory TF-IDF vector store."""

    def __init__(self) -> None:
        self.chunks: list[dict[str, Any]] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix: Any = None  # sparse CSR matrix
        self._built = False

    @property
    def is_built(self) -> bool:
        return self._built

    def build(self, chunks: list[dict[str, Any]]) -> None:
        texts = [c["text"] for c in chunks]
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=5000,
            sublinear_tf=True,
        )
        self.matrix = self.vectorizer.fit_transform(texts)
        self.chunks = list(chunks)
        self._built = True

    def query(self, query_text: str, k: int) -> list[dict[str, Any]]:
        if not self._built or self.vectorizer is None:
            raise RuntimeError("Vector store not built. Call build_vector_store() first.")
        q_vec = self.vectorizer.transform([query_text])
        scores = cosine_similarity(q_vec, self.matrix).flatten()
        top_k = int(min(k, len(self.chunks)))
        top_indices = np.argsort(scores)[::-1][:top_k]

        results: list[dict[str, Any]] = []
        for idx in top_indices:
            chunk = dict(self.chunks[idx])
            chunk["retrieval_score"] = float(scores[idx])
            results.append(chunk)
        return results


# Module-level singleton
_store = _VectorStore()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_vector_store(
    force_rebuild: bool = False,
    knowledge_dir: str | None = None,
) -> int:
    """Load core docs, parse chunks, and build the TF-IDF vector store.

    Parameters
    ----------
    force_rebuild:
        If True, rebuild even if already built.
    knowledge_dir:
        Override for the knowledge directory path.

    Returns
    -------
    int
        Number of chunks indexed.

    Raises
    ------
    FileNotFoundError
        If the knowledge directory or any core doc is missing.
    """
    global _store

    if _store.is_built and not force_rebuild:
        return len(_store.chunks)

    kdir = knowledge_dir or _DEFAULT_KNOWLEDGE_DIR
    if not os.path.isdir(kdir):
        raise FileNotFoundError(f"Knowledge directory not found: {kdir}")

    all_chunks: list[dict[str, Any]] = []
    for doc_name in CORE_DOCS:
        path = os.path.join(kdir, doc_name)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Core knowledge doc missing: {path}")
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        all_chunks.extend(_parse_chunks(text, source_doc=doc_name))

    if not all_chunks:
        raise ValueError("No chunks were parsed from knowledge documents.")

    _store = _VectorStore()
    _store.build(all_chunks)
    return len(all_chunks)


def retrieve(query: str, k: int = 4) -> list[dict[str, Any]]:
    """Retrieve the top-k most relevant chunks for a query.

    Parameters
    ----------
    query:
        Natural-language query string. Must be non-empty.
    k:
        Number of results to return. Must be >= 1.

    Returns
    -------
    list[dict]
        Each dict contains: text, source_doc, chunk_id, section, retrieval_score.

    Raises
    ------
    ValueError
        If query is empty/whitespace or k < 1.
    RuntimeError
        If the vector store has not been built.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Query must be a non-empty string.")
    if not isinstance(k, int) or k < 1:
        raise ValueError(f"k must be an integer >= 1, got {k!r}")
    if not _store.is_built:
        raise RuntimeError(
            "Vector store not built. Call build_vector_store() first."
        )
    return _store.query(query.strip(), k)


def reset_store() -> None:
    """Reset the module-level vector store (useful for testing)."""
    global _store
    _store = _VectorStore()


def get_indexed_chunks() -> list[dict[str, Any]]:
    """Phase 5 accessor: return a copy of the currently indexed chunks.

    The advanced retrieval stack in src/retrieval.py uses this to build
    secondary indexes (BM25, dense, contextualized) over the same corpus
    without re-parsing the knowledge directory. Returns an empty list if
    the vector store has not been built yet.
    """
    if not _store.is_built:
        return []
    return [dict(c) for c in _store.chunks]


def is_store_built() -> bool:
    """Phase 5 helper: report whether the legacy vector store is ready."""
    return _store.is_built


def legacy_tfidf_query(query: str, k: int) -> list[dict[str, Any]]:
    """Phase 5 helper: legacy TF-IDF retrieval bypassing input validation of
    retrieve() so the advanced stack can use it as a trusted fallback.
    """
    if not _store.is_built:
        raise RuntimeError("Vector store not built.")
    return _store.query(query.strip(), k)
