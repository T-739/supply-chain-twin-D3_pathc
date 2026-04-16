"""
retrieval.py — Phase 5 Contextual Hybrid Retrieval Stack.

Layered, deterministic, and testable without live APIs:

  (A) Contextual indexing
        For each chunk: contextualized_text = "[{source_doc} | {section}] " + text
        Deterministic by default; a pluggable Contextualizer callable allows
        an LLM-produced contextual prefix to be injected later. Raw text is
        preserved.

  (B) Hybrid first-stage retrieval
        Modes: "tfidf_legacy", "bm25", "dense", "hybrid"
        Hybrid fuses dense + lexical (BM25) with Reciprocal Rank Fusion.

  (C) Reranker
        A pluggable callable scores (query, chunk) over the fused candidate
        set. Default deterministic reranker = Jaccard + normalized fused
        score + positional prior. Never introduces a chunk outside the
        fused candidate set.

  (D) Trace
        Every call returns a RetrievalTrace carrying mode, query_hash,
        per-candidate dense_score / lexical_score / fused_score /
        reranker_score / final_rank, fallback_used, contextualized flag,
        and component names.

Truth boundary
--------------
Retrieval here improves grounding only. It never redefines oracle truth,
evaluation authority, or numeric truth. Agent outputs and evaluation
semantics stay unchanged.

Backward compatibility
----------------------
This module is additive. The existing `rag_setup.retrieve()` entry point is
untouched and remains the legacy path. Advanced retrieval is exposed via
`retrieve_advanced()`. Any failure inside the advanced path falls back to
legacy TF-IDF retrieval with `fallback_used=True`.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

import rag_setup


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


# ---------------------------------------------------------------------------
# Contextualizer
# ---------------------------------------------------------------------------

Contextualizer = Callable[[dict[str, Any]], str]
"""Takes a chunk dict and returns a short contextual prefix (may be empty)."""


def default_contextualizer(chunk: dict[str, Any]) -> str:
    """Deterministic contextual prefix: [source_doc | section]."""
    src = str(chunk.get("source_doc", "")).strip()
    sec = str(chunk.get("section", "")).strip()
    parts = [p for p in (src, sec) if p]
    return f"[{' | '.join(parts)}] " if parts else ""


def build_contextualized_chunks(
    chunks: list[dict[str, Any]],
    contextualizer: Contextualizer | None = None,
) -> list[dict[str, Any]]:
    """Return chunks with `contextual_prefix` and `contextualized_text` fields.

    The raw `text` field is preserved verbatim. Contextualization is optional:
    passing None for `contextualizer` yields `contextual_prefix == ""` and
    `contextualized_text == text` (i.e. no contextualization).
    """
    out: list[dict[str, Any]] = []
    ctx_fn = contextualizer  # may be None
    for c in chunks:
        prefix = ctx_fn(c) if ctx_fn is not None else ""
        prefix = str(prefix or "")
        new_c = dict(c)
        new_c["contextual_prefix"] = prefix
        new_c["contextualized_text"] = (prefix + c.get("text", "")).strip()
        out.append(new_c)
    return out


# ---------------------------------------------------------------------------
# Embedder (dense) interface — pluggable
# ---------------------------------------------------------------------------

Embedder = Callable[[list[str]], np.ndarray]
"""Takes a list of strings, returns a (N, D) L2-normalized float array."""


class _TfidfDenseEmbedder:
    """Default deterministic dense embedder.

    Fits a TfidfVectorizer on the corpus and returns L2-normalized rows
    that behave like dense vectors under cosine similarity. This is a
    stand-in for a real embedding model: the Embedder interface is
    pluggable so that sentence-transformers or an API client can be
    swapped in without changing the retrieval API.
    """

    name = "tfidf_dense_stub"

    def __init__(self, max_features: int = 4096) -> None:
        self._vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=max_features,
            sublinear_tf=True,
        )
        self._fitted = False

    def fit(self, corpus: list[str]) -> None:
        self._vectorizer.fit(corpus)
        self._fitted = True

    def __call__(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("dense embedder not fitted")
        mat = self._vectorizer.transform(texts).toarray().astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms


# ---------------------------------------------------------------------------
# BM25 index (pure Python Okapi BM25)
# ---------------------------------------------------------------------------


@dataclass
class BM25Index:
    k1: float = 1.5
    b: float = 0.75

    def __post_init__(self) -> None:
        self._docs: list[list[str]] = []
        self._df: dict[str, int] = {}
        self._idf: dict[str, float] = {}
        self._doc_lens: list[int] = []
        self._avg_len: float = 0.0
        self._built: bool = False

    def build(self, texts: Iterable[str]) -> None:
        self._docs = [_tokenize(t) for t in texts]
        self._doc_lens = [len(d) for d in self._docs]
        self._avg_len = (sum(self._doc_lens) / len(self._doc_lens)) if self._doc_lens else 0.0

        df: dict[str, int] = {}
        for tokens in self._docs:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        self._df = df

        # Okapi BM25 idf with +1 smoothing (always >= 0).
        n = len(self._docs)
        self._idf = {
            term: math.log(1.0 + (n - d + 0.5) / (d + 0.5))
            for term, d in df.items()
        }
        self._built = True

    def score(self, query: str) -> np.ndarray:
        if not self._built:
            raise RuntimeError("BM25Index not built")
        q_terms = _tokenize(query)
        scores = np.zeros(len(self._docs), dtype=np.float64)
        if not q_terms or self._avg_len == 0:
            return scores
        for i, doc in enumerate(self._docs):
            if not doc:
                continue
            tf: dict[str, int] = {}
            for t in doc:
                tf[t] = tf.get(t, 0) + 1
            dl = self._doc_lens[i]
            s = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                idf = self._idf.get(term, 0.0)
                f = tf[term]
                denom = f + self.k1 * (
                    1 - self.b + self.b * (dl / self._avg_len)
                )
                s += idf * (f * (self.k1 + 1.0)) / denom
            scores[i] = s
        return scores


# ---------------------------------------------------------------------------
# Dense index
# ---------------------------------------------------------------------------


class DenseIndex:
    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder
        self._own_embedder = False
        self._matrix: np.ndarray | None = None
        self._built = False

    def build(self, texts: list[str]) -> None:
        if self._embedder is None:
            emb = _TfidfDenseEmbedder()
            emb.fit(texts)
            self._embedder = emb
            self._own_embedder = True
        self._matrix = self._embedder(texts)
        self._built = True

    @property
    def embedder_name(self) -> str:
        emb = self._embedder
        return getattr(emb, "name", emb.__class__.__name__ if emb else "none")

    def score(self, query: str) -> np.ndarray:
        if not self._built or self._matrix is None or self._embedder is None:
            raise RuntimeError("DenseIndex not built")
        q = self._embedder([query])
        # cosine similarity — rows are pre-normalized
        q_norm = np.linalg.norm(q, axis=1, keepdims=True)
        q_norm[q_norm == 0] = 1.0
        qn = q / q_norm
        return (self._matrix @ qn[0]).astype(np.float64)


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------


def _ranks_from_scores(scores: np.ndarray) -> np.ndarray:
    """Higher score → smaller rank. Rank is 1-based. Ties broken by index."""
    order = np.argsort(-scores, kind="stable")
    ranks = np.zeros_like(scores, dtype=np.int64)
    for r, idx in enumerate(order, start=1):
        ranks[idx] = r
    return ranks


def reciprocal_rank_fusion(
    score_tables: list[np.ndarray],
    k_rrf: int = 60,
) -> np.ndarray:
    """Compute RRF fused score per document index.

    RRF formula: score(d) = Σ 1 / (k_rrf + rank_i(d)).
    """
    if not score_tables:
        raise ValueError("score_tables must be non-empty")
    n = len(score_tables[0])
    fused = np.zeros(n, dtype=np.float64)
    for s in score_tables:
        if len(s) != n:
            raise ValueError("score tables must have identical length")
        ranks = _ranks_from_scores(s)
        fused += 1.0 / (k_rrf + ranks.astype(np.float64))
    return fused


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------

Reranker = Callable[[str, list[dict[str, Any]]], list[float]]
"""Takes (query, list_of_candidate_chunks) and returns per-candidate scores."""


def default_reranker(query: str, candidates: list[dict[str, Any]]) -> list[float]:
    """Deterministic reranker fallback.

    Score = 0.5 * Jaccard(query_tokens, chunk_tokens)
          + 0.4 * normalized fused_score (if present)
          + 0.1 * 1/(1+original_position_index).
    """
    q_tokens = set(_tokenize(query))
    fused = [float(c.get("fused_score", 0.0)) for c in candidates]
    f_max = max(fused) if fused else 0.0
    f_min = min(fused) if fused else 0.0
    span = (f_max - f_min) or 1.0

    scores: list[float] = []
    for idx, c in enumerate(candidates):
        ct = set(_tokenize(c.get("contextualized_text") or c.get("text", "")))
        if q_tokens and ct:
            jacc = len(q_tokens & ct) / len(q_tokens | ct)
        else:
            jacc = 0.0
        f_norm = (float(c.get("fused_score", 0.0)) - f_min) / span
        pos = 1.0 / (1.0 + idx)
        scores.append(0.5 * jacc + 0.4 * f_norm + 0.1 * pos)
    return scores


# ---------------------------------------------------------------------------
# Trace dataclass
# ---------------------------------------------------------------------------


@dataclass
class RetrievalTrace:
    mode: str
    query: str
    query_hash: str
    k: int
    contextualized: bool
    fallback_used: bool
    embedder_name: str | None
    reranker_name: str | None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    # Multi-query branch (optional): populated only when a multi-query
    # retrieval path was taken. Shape:
    #   {
    #     "sub_queries": [str, ...],
    #     "sub_query_count": int,
    #     "per_subquery_candidate_counts": [int, ...],
    #     "merged_count": int,          # total chunks before dedup
    #     "deduped_count": int,         # unique chunks after dedup
    #     "sub_query_hashes": [str, ...],
    #     "generator_name": str,
    #   }
    multi_query: dict[str, Any] | None = None
    # Self-query branch (optional): populated only when a self-query
    # retrieval path was taken. Shape:
    #   {
    #     "original_query": str,
    #     "refined_query": str,
    #     "filters": {field: value, ...},
    #     "parser_name": str,
    #     "full_corpus_size": int,
    #     "filtered_corpus_size": int,
    #     "filter_empty": bool,     # True if filter matched 0 chunks → fallback
    #   }
    self_query: dict[str, Any] | None = None
    # Compression branch (optional): populated only when a compressor ran.
    # Shape:
    #   {
    #     "compressor_name": str,
    #     "raw_chunk_count": int,
    #     "compressed_chunk_count": int,
    #     "raw_total_chars": int,
    #     "compressed_total_chars": int,
    #     "compression_ratio": float,   # compressed / raw  (1.0 if no op)
    #     "fallback_used": bool,        # True if compressor raised
    #     "per_chunk": [ {chunk_id, raw_length, compressed_length, ratio}, ... ]
    #   }
    compression: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Advanced retrieval store
# ---------------------------------------------------------------------------


_VALID_MODES = frozenset({"tfidf_legacy", "bm25", "dense", "hybrid"})

# Agent-facing modes (Phase 6 + multi-query + self-query + compression).
AGENT_RETRIEVAL_MODES: frozenset[str] = frozenset({
    "tfidf_legacy", "dense", "hybrid", "hybrid_rerank",
    "multi_hybrid", "multi_hybrid_rerank",
    "self_hybrid", "self_hybrid_rerank",
    "hybrid_rerank_compress",
    "multi_hybrid_rerank_compress",
    "self_hybrid_rerank_compress",
})

# Suffix that signals compression should be applied after the base retrieval.
_COMPRESS_SUFFIX = "_compress"


# ---------------------------------------------------------------------------
# Self-query branch — deterministic metadata schema
# ---------------------------------------------------------------------------

# Map source_doc filename → (doc_type, policy_family).
_DOC_TYPE_MAP: dict[str, tuple[str, str]] = {
    "exception_handling_sop.md": ("sop", "exception_handling"),
    "sla_terms.md": ("sla", "sla"),
    "carrier_selection_rules.md": ("carrier", "carrier_selection"),
    "escalation_protocol.md": ("escalation", "escalation"),
    "inventory_transfer_policy.md": ("inventory", "inventory_transfer"),
}

# Map chunk_id prefix → scenario_family.
_CHUNK_PREFIX_FAMILY: dict[str, str] = {
    "EH": "exception",
    "CSR": "carrier",
    "EP": "escalation",
    "ITP": "inventory",
    "SLA": "sla",
}

# Agent-relevance keyword tables (lowercased).
_GOVERNANCE_TOKENS = (
    "approve", "verify", "override", "supervisor", "escalat", "governance",
    "reviewability", "supervision",
)
_OPERATIONS_TOKENS = (
    "carrier", "expedite", "reallocat", "transfer", "warehouse", "inventory",
    "compensat", "fulfillment", "sla", "lane",
)

# Rule-scope keyword tables.
_HARD_GATE_TOKENS = (
    "do not", "must not", "shall not", "hard gate", "hard rule", "prohibited",
)
_SOFT_TOKENS = ("prefer", "favor", "avoid unnecessary", "selectiv")
_PROCEDURE_TOKENS = ("procedure", "step", "when ", "if ")


def _prefix_of(chunk_id: str) -> str:
    cid = str(chunk_id or "")
    if "-" in cid:
        return cid.split("-", 1)[0].upper()
    return cid.upper()


def derive_chunk_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    """Deterministic, offline metadata derivation for a single chunk.

    Returns a dict with a small, explainable set of fields used by the
    self-query retrieval path. Keys are stable across runs. No network
    or LLM call is required.
    """
    src = str(chunk.get("source_doc", ""))
    doc_type, policy_family = _DOC_TYPE_MAP.get(src, ("other", "other"))

    prefix = _prefix_of(chunk.get("chunk_id", ""))
    scenario_family = _CHUNK_PREFIX_FAMILY.get(prefix, "other")

    text_l = (chunk.get("text") or "").lower()

    gov_hits = sum(1 for t in _GOVERNANCE_TOKENS if t in text_l)
    ops_hits = sum(1 for t in _OPERATIONS_TOKENS if t in text_l)
    if gov_hits > ops_hits and gov_hits > 0:
        agent_relevance = "governance"
    elif ops_hits > gov_hits and ops_hits > 0:
        agent_relevance = "operations"
    else:
        agent_relevance = "shared"

    if any(t in text_l for t in _HARD_GATE_TOKENS):
        rule_scope = "hard_gate"
    elif any(t in text_l for t in _SOFT_TOKENS):
        rule_scope = "soft_preference"
    elif any(t in text_l for t in _PROCEDURE_TOKENS):
        rule_scope = "procedure"
    else:
        rule_scope = "definition"

    return {
        "source_doc": src,
        "section": str(chunk.get("section", "")),
        "doc_type": doc_type,
        "policy_family": policy_family,
        "scenario_family": scenario_family,
        "agent_relevance": agent_relevance,
        "rule_scope": rule_scope,
    }


# Fields the self-query parser is allowed to emit filters over.
_FILTER_FIELDS = frozenset({
    "doc_type", "policy_family", "scenario_family",
    "agent_relevance", "rule_scope", "source_doc",
})


class AdvancedRetrievalStore:
    """Owns contextualized chunks and the derived indexes.

    This store is deliberately kept separate from the legacy
    rag_setup._store so legacy behavior remains byte-identical.
    """

    def __init__(self) -> None:
        self.chunks: list[dict[str, Any]] = []
        self._bm25: BM25Index | None = None
        self._dense: DenseIndex | None = None
        self._contextualized: bool = False
        self._built: bool = False

    @property
    def is_built(self) -> bool:
        return self._built

    @property
    def embedder_name(self) -> str | None:
        return self._dense.embedder_name if self._dense is not None else None

    def build(
        self,
        chunks: list[dict[str, Any]],
        *,
        contextualizer: Contextualizer | None = default_contextualizer,
        embedder: Embedder | None = None,
    ) -> None:
        contextualized = contextualizer is not None
        self.chunks = build_contextualized_chunks(chunks, contextualizer)
        # Self-query branch: attach deterministic metadata to each chunk.
        # Purely additive; none of the existing retrieval paths read it.
        for c in self.chunks:
            c["metadata"] = derive_chunk_metadata(c)
        texts = [c["contextualized_text"] for c in self.chunks]

        self._bm25 = BM25Index()
        self._bm25.build(texts)

        self._dense = DenseIndex(embedder=embedder)
        self._dense.build(texts)

        self._contextualized = contextualized
        self._built = True

    def score_bm25(self, query: str) -> np.ndarray:
        assert self._bm25 is not None
        return self._bm25.score(query)

    def score_dense(self, query: str) -> np.ndarray:
        assert self._dense is not None
        return self._dense.score(query)


_store = AdvancedRetrievalStore()


def reset_advanced_store() -> None:
    global _store
    _store = AdvancedRetrievalStore()


def build_advanced_store(
    *,
    contextualizer: Contextualizer | None = default_contextualizer,
    embedder: Embedder | None = None,
    force_rebuild: bool = False,
) -> int:
    """Build the advanced retrieval indexes over the legacy-parsed chunks.

    Requires `rag_setup.build_vector_store()` to have been called first
    (the legacy store is the source of truth for chunk parsing).
    Returns the number of indexed chunks.
    """
    global _store
    if _store.is_built and not force_rebuild:
        return len(_store.chunks)

    if not rag_setup.is_store_built():
        rag_setup.build_vector_store()

    base_chunks = rag_setup.get_indexed_chunks()
    if not base_chunks:
        raise RuntimeError("No chunks available from rag_setup for advanced store.")

    _store = AdvancedRetrievalStore()
    _store.build(base_chunks, contextualizer=contextualizer, embedder=embedder)
    return len(_store.chunks)


# ---------------------------------------------------------------------------
# Public advanced retrieval API
# ---------------------------------------------------------------------------


def _hash_query(q: str) -> str:
    return hashlib.sha1(q.encode("utf-8")).hexdigest()[:12]


def _legacy_fallback(query: str, k: int, trace: RetrievalTrace) -> list[dict[str, Any]]:
    """Run the legacy TF-IDF path and populate the trace accordingly."""
    if not rag_setup.is_store_built():
        rag_setup.build_vector_store()
    results = rag_setup.legacy_tfidf_query(query, k)
    trace.candidates = [
        {
            "chunk_id": r["chunk_id"],
            "source_doc": r["source_doc"],
            "section": r.get("section", ""),
            "dense_score": None,
            "lexical_score": None,
            "fused_score": None,
            "reranker_score": None,
            "final_rank": i + 1,
            "legacy_tfidf_score": float(r.get("retrieval_score", 0.0)),
        }
        for i, r in enumerate(results)
    ]
    return results


def retrieve_advanced(
    query: str,
    *,
    mode: str = "hybrid",
    k: int = 4,
    first_stage_n: int | None = None,
    contextualizer: Contextualizer | None = default_contextualizer,
    embedder: Embedder | None = None,
    reranker: Reranker | None = default_reranker,
    rerank: bool = True,
) -> tuple[list[dict[str, Any]], RetrievalTrace]:
    """Advanced retrieval entry point.

    Parameters
    ----------
    query : non-empty query string
    mode  : "tfidf_legacy" | "bm25" | "dense" | "hybrid"
    k     : final top-K returned
    first_stage_n : how many candidates to consider before reranking
                    (default = max(k*3, 8))
    contextualizer : chunk-contextualization function (None to disable)
    embedder       : dense embedder; None → default _TfidfDenseEmbedder
    reranker       : callable(query, candidates) -> list[float]; None → off
    rerank         : if False, skip the reranker stage entirely

    Returns
    -------
    (chunks, trace) : chunks are dicts with text/source_doc/chunk_id/section/
                      retrieval_score plus enriched scores; trace is a
                      RetrievalTrace.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(k, int) or k < 1:
        raise ValueError(f"k must be an integer >= 1, got {k!r}")
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}, got {mode!r}")

    q = query.strip()
    first_n = first_stage_n or max(k * 3, 8)

    trace = RetrievalTrace(
        mode=mode,
        query=q,
        query_hash=_hash_query(q),
        k=k,
        contextualized=(contextualizer is not None) and mode != "tfidf_legacy",
        fallback_used=False,
        embedder_name=None,
        reranker_name=None,
    )

    # Legacy mode — bypass all advanced machinery.
    if mode == "tfidf_legacy":
        try:
            results = _legacy_fallback(q, k, trace)
            return results, trace
        except Exception as exc:  # pragma: no cover
            trace.error = f"legacy_tfidf_failed: {exc}"
            trace.fallback_used = True
            return [], trace

    # Advanced modes — wrap in a safety net that falls back to legacy.
    try:
        if not _store.is_built:
            build_advanced_store(contextualizer=contextualizer, embedder=embedder)

        trace.embedder_name = _store.embedder_name

        dense_scores: np.ndarray | None = None
        lexical_scores: np.ndarray | None = None

        if mode in ("dense", "hybrid"):
            dense_scores = _store.score_dense(q)
        if mode in ("bm25", "hybrid"):
            lexical_scores = _store.score_bm25(q)

        if mode == "dense":
            assert dense_scores is not None
            fused = dense_scores.copy()
        elif mode == "bm25":
            assert lexical_scores is not None
            fused = lexical_scores.copy()
        else:  # hybrid
            assert dense_scores is not None and lexical_scores is not None
            fused = reciprocal_rank_fusion([dense_scores, lexical_scores])

        n = len(_store.chunks)
        first_n_capped = min(first_n, n)
        top_first = np.argsort(-fused, kind="stable")[:first_n_capped]

        candidates: list[dict[str, Any]] = []
        for idx in top_first:
            c = dict(_store.chunks[int(idx)])
            c["dense_score"] = float(dense_scores[idx]) if dense_scores is not None else None
            c["lexical_score"] = float(lexical_scores[idx]) if lexical_scores is not None else None
            c["fused_score"] = float(fused[idx])
            candidates.append(c)

        # Rerank stage — reorders within the fused candidate set only.
        if rerank and reranker is not None and candidates:
            try:
                rr_scores = reranker(q, candidates)
                if len(rr_scores) != len(candidates):
                    raise ValueError("reranker returned wrong length")
                for c, s in zip(candidates, rr_scores):
                    c["reranker_score"] = float(s)
                # Stable reorder by reranker score desc.
                candidates.sort(
                    key=lambda c: c.get("reranker_score", 0.0), reverse=True,
                )
                trace.reranker_name = getattr(
                    reranker, "__name__", reranker.__class__.__name__,
                )
            except Exception as exc:
                # Reranker failure → keep fused order, mark fallback.
                for c in candidates:
                    c.setdefault("reranker_score", None)
                trace.error = f"reranker_failed: {exc}"
        else:
            for c in candidates:
                c["reranker_score"] = None

        # Trim to k.
        final = candidates[:k]

        # Build trace candidate entries.
        trace.candidates = [
            {
                "chunk_id": c["chunk_id"],
                "source_doc": c["source_doc"],
                "section": c.get("section", ""),
                "dense_score": c.get("dense_score"),
                "lexical_score": c.get("lexical_score"),
                "fused_score": c.get("fused_score"),
                "reranker_score": c.get("reranker_score"),
                "final_rank": i + 1,
            }
            for i, c in enumerate(final)
        ]

        # Build public chunk dicts matching the legacy retrieve() shape,
        # plus advanced score fields for provenance.
        out: list[dict[str, Any]] = []
        for i, c in enumerate(final):
            primary_score = (
                c.get("reranker_score")
                if c.get("reranker_score") is not None
                else c.get("fused_score", 0.0)
            )
            out.append({
                "chunk_id": c["chunk_id"],
                "source_doc": c["source_doc"],
                "section": c.get("section", ""),
                "text": c["text"],                     # raw chunk text
                "contextualized_text": c.get("contextualized_text", c["text"]),
                "contextual_prefix": c.get("contextual_prefix", ""),
                "retrieval_score": float(primary_score),
                "dense_score": c.get("dense_score"),
                "lexical_score": c.get("lexical_score"),
                "fused_score": c.get("fused_score"),
                "reranker_score": c.get("reranker_score"),
                "final_rank": i + 1,
            })
        return out, trace

    except Exception as exc:
        trace.error = f"advanced_retrieval_failed: {exc}"
        trace.fallback_used = True
        try:
            results = _legacy_fallback(q, k, trace)
            return results, trace
        except Exception as exc2:  # pragma: no cover
            trace.error = f"{trace.error}; legacy_also_failed: {exc2}"
            return [], trace


# ---------------------------------------------------------------------------
# Multi-query branch — deterministic expansion + merged hybrid retrieval
# ---------------------------------------------------------------------------

QueryGenerator = Callable[[str], list[str]]
"""Takes the original query and returns a list of sub-queries (includes orig)."""


def default_query_generator(query: str) -> list[str]:
    """Deterministic, offline-safe multi-query expansion.

    Produces a small, bounded, explainable set of reformulations framed
    around supply-chain exception handling. The original query is always
    included as the first entry. Duplicates (after whitespace-normalization)
    are removed while preserving order.

    This is intentionally minimal. Pluggable generators (e.g. an LLM-backed
    one using the Phase 2 gateway) can be supplied through
    ``retrieve_multi(query_generator=...)``.
    """
    if not isinstance(query, str) or not query.strip():
        return []
    q = query.strip()
    frames = [
        q,
        f"supply chain policy and rules guidance for: {q}",
        f"exception handling procedure for: {q}",
        f"fulfillment operations decision context for: {q}",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for f in frames:
        key = " ".join(f.lower().split())
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


default_query_generator.name = "default_query_generator"  # type: ignore[attr-defined]


# Multi-query first-stage modes (delegated to retrieve_advanced sub-calls).
_MULTI_BASE_MODES = frozenset({"hybrid", "dense", "bm25"})


def retrieve_multi(
    query: str,
    *,
    base_mode: str = "hybrid",
    k: int = 4,
    per_subquery_n: int | None = None,
    contextualizer: Contextualizer | None = default_contextualizer,
    embedder: Embedder | None = None,
    reranker: Reranker | None = default_reranker,
    rerank: bool = True,
    query_generator: QueryGenerator | None = None,
    max_sub_queries: int = 4,
    k_rrf: int = 60,
) -> tuple[list[dict[str, Any]], RetrievalTrace]:
    """Multi-query retrieval wrapper around `retrieve_advanced`.

    Flow:
      1. Expand `query` into sub-queries via `query_generator` (default:
         `default_query_generator`). Capped to `max_sub_queries`.
      2. For each sub-query, call `retrieve_advanced(..., rerank=False)`
         with mode=`base_mode` to obtain a per-sub-query candidate list
         (only the fused first stage is used).
      3. Merge candidates by `chunk_id`, dedup, and aggregate a
         multi-query fused score = Σ 1 / (k_rrf + rank_in_sub_query).
      4. If `rerank`, run the existing `reranker` over the merged pool
         (never introducing chunks outside it).
      5. Trim to top-k and return (chunks, trace). Trace carries a
         `multi_query` dict with sub-queries and counts.

    Fallback: any exception falls back to the legacy TF-IDF single-query
    path and sets `trace.fallback_used = True`.

    Backward compatibility: purely additive; does not touch the existing
    single-query entry points.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(k, int) or k < 1:
        raise ValueError(f"k must be an integer >= 1, got {k!r}")
    if base_mode not in _MULTI_BASE_MODES:
        raise ValueError(
            f"base_mode must be one of {sorted(_MULTI_BASE_MODES)}, got {base_mode!r}"
        )

    q = query.strip()
    gen = query_generator or default_query_generator
    generator_name = getattr(gen, "name", getattr(gen, "__name__", "query_generator"))

    trace = RetrievalTrace(
        mode=f"multi_{base_mode}" + ("_rerank" if rerank else ""),
        query=q,
        query_hash=_hash_query(q),
        k=k,
        contextualized=(contextualizer is not None),
        fallback_used=False,
        embedder_name=None,
        reranker_name=None,
    )

    try:
        sub_queries_raw = gen(q) or []
        # Always include original as a safety net.
        if not sub_queries_raw:
            sub_queries_raw = [q]
        elif sub_queries_raw[0].strip() != q:
            sub_queries_raw = [q] + list(sub_queries_raw)
        # Dedup (normalized) + cap.
        seen: set[str] = set()
        sub_queries: list[str] = []
        for s in sub_queries_raw:
            if not isinstance(s, str) or not s.strip():
                continue
            key = " ".join(s.lower().split())
            if key in seen:
                continue
            seen.add(key)
            sub_queries.append(s.strip())
            if len(sub_queries) >= max_sub_queries:
                break

        if not sub_queries:
            raise RuntimeError("query_generator produced no usable sub-queries")

        # First-stage size per sub-query — wider than final k so merging helps.
        per_n = per_subquery_n or max(k * 3, 8)

        # Run each sub-query through the existing advanced stack with
        # reranker disabled — we rerank once over the merged pool.
        merged: dict[str, dict[str, Any]] = {}
        per_sub_counts: list[int] = []
        sub_hashes: list[str] = []

        for sub_q in sub_queries:
            sub_chunks, sub_trace = retrieve_advanced(
                sub_q,
                mode=base_mode,
                k=per_n,
                first_stage_n=per_n,
                contextualizer=contextualizer,
                embedder=embedder,
                reranker=None,
                rerank=False,
            )
            sub_hashes.append(sub_trace.query_hash)
            per_sub_counts.append(len(sub_chunks))
            if sub_trace.fallback_used:
                # A sub-query fell back to legacy TF-IDF — still usable, but
                # multi_query semantics are weakened. We surface it via trace.
                trace.error = (
                    (trace.error + "; " if trace.error else "")
                    + f"subquery_fallback({sub_trace.query_hash})"
                )

            # Merge with RRF-over-sub-queries.
            for rank, c in enumerate(sub_chunks, start=1):
                cid = c.get("chunk_id")
                if cid is None:
                    continue
                rr_contrib = 1.0 / (k_rrf + rank)
                if cid in merged:
                    merged[cid]["multi_query_rrf_score"] += rr_contrib
                    merged[cid]["sub_query_hits"] += 1
                    # Accumulate max fused_score for reranker compatibility.
                    if c.get("fused_score") is not None:
                        prev = merged[cid].get("fused_score") or 0.0
                        merged[cid]["fused_score"] = max(
                            prev, float(c["fused_score"])
                        )
                else:
                    m = dict(c)
                    m["multi_query_rrf_score"] = rr_contrib
                    m["sub_query_hits"] = 1
                    merged[cid] = m

        merged_total = sum(per_sub_counts)
        deduped_count = len(merged)

        # Sort merged pool by multi-query RRF score, tie-break by sub_query_hits.
        pool = list(merged.values())
        pool.sort(
            key=lambda c: (
                c.get("multi_query_rrf_score", 0.0),
                c.get("sub_query_hits", 0),
            ),
            reverse=True,
        )

        # Optional reranker stage — reorders within the merged pool only.
        if rerank and reranker is not None and pool:
            try:
                rr_scores = reranker(q, pool)
                if len(rr_scores) != len(pool):
                    raise ValueError("reranker returned wrong length")
                for c, s in zip(pool, rr_scores):
                    c["reranker_score"] = float(s)
                pool.sort(
                    key=lambda c: c.get("reranker_score", 0.0), reverse=True,
                )
                trace.reranker_name = getattr(
                    reranker, "__name__", reranker.__class__.__name__,
                )
            except Exception as exc:
                for c in pool:
                    c.setdefault("reranker_score", None)
                trace.error = (
                    (trace.error + "; " if trace.error else "")
                    + f"reranker_failed: {exc}"
                )
        else:
            for c in pool:
                c.setdefault("reranker_score", None)

        final = pool[:k]
        trace.embedder_name = _store.embedder_name if _store.is_built else None

        # Build trace.candidates matching existing shape.
        trace.candidates = [
            {
                "chunk_id": c["chunk_id"],
                "source_doc": c["source_doc"],
                "section": c.get("section", ""),
                "dense_score": c.get("dense_score"),
                "lexical_score": c.get("lexical_score"),
                "fused_score": c.get("fused_score"),
                "reranker_score": c.get("reranker_score"),
                "multi_query_rrf_score": c.get("multi_query_rrf_score"),
                "sub_query_hits": c.get("sub_query_hits"),
                "final_rank": i + 1,
            }
            for i, c in enumerate(final)
        ]
        trace.multi_query = {
            "sub_queries": sub_queries,
            "sub_query_count": len(sub_queries),
            "per_subquery_candidate_counts": per_sub_counts,
            "merged_count": merged_total,
            "deduped_count": deduped_count,
            "sub_query_hashes": sub_hashes,
            "generator_name": generator_name,
            "base_mode": base_mode,
            "rerank": bool(rerank and reranker is not None),
        }

        # Public chunk dicts (legacy-compatible shape + multi-query extras).
        out: list[dict[str, Any]] = []
        for i, c in enumerate(final):
            primary_score = (
                c.get("reranker_score")
                if c.get("reranker_score") is not None
                else c.get("multi_query_rrf_score", 0.0)
            )
            out.append({
                "chunk_id": c["chunk_id"],
                "source_doc": c["source_doc"],
                "section": c.get("section", ""),
                "text": c.get("text", ""),
                "contextualized_text": c.get("contextualized_text", c.get("text", "")),
                "contextual_prefix": c.get("contextual_prefix", ""),
                "retrieval_score": float(primary_score),
                "dense_score": c.get("dense_score"),
                "lexical_score": c.get("lexical_score"),
                "fused_score": c.get("fused_score"),
                "reranker_score": c.get("reranker_score"),
                "multi_query_rrf_score": c.get("multi_query_rrf_score"),
                "sub_query_hits": c.get("sub_query_hits"),
                "final_rank": i + 1,
            })
        return out, trace

    except Exception as exc:
        trace.error = (
            (trace.error + "; " if trace.error else "")
            + f"multi_query_failed: {exc}"
        )
        trace.fallback_used = True
        try:
            results = _legacy_fallback(q, k, trace)
            return results, trace
        except Exception as exc2:  # pragma: no cover
            trace.error = f"{trace.error}; legacy_also_failed: {exc2}"
            return [], trace


# ---------------------------------------------------------------------------
# Self-query branch — parser + metadata-aware retrieval
# ---------------------------------------------------------------------------

SelfQueryParser = Callable[[str], dict[str, Any]]
"""Takes a natural-language query and returns:
    {"refined_query": str, "filters": {field: value, ...}, "parser_name": str}
"""


# Parser keyword tables. Each table maps a filter-field candidate to a set
# of trigger tokens that must appear (case-insensitive, substring match)
# in the query. To keep the parser safe, a filter is emitted only if exactly
# one candidate in a table is triggered (unambiguous match).

_POLICY_FAMILY_TRIGGERS: dict[str, tuple[str, ...]] = {
    "carrier_selection": ("carrier", "expedit", "lane"),
    "sla": ("sla", "deadline", "promise"),
    "escalation": ("escalat", "approve", "verify", "override", "supervisor"),
    "inventory_transfer": ("inventory", "reallocat", "transfer", "warehouse"),
    "exception_handling": ("exception", "disruption", "incident"),
}

_SCENARIO_FAMILY_TRIGGERS: dict[str, tuple[str, ...]] = {
    "carrier": ("carrier",),
    "sla": ("sla", "deadline"),
    "inventory": ("inventory", "warehouse", "stock"),
    "escalation": ("escalat", "approval", "verify"),
    "exception": ("exception", "disruption"),
}

_AGENT_RELEVANCE_TRIGGERS: dict[str, tuple[str, ...]] = {
    "governance": ("governance", "approve", "verify", "override", "supervisor"),
    "operations": ("operations", "recommend", "reroute", "expedit", "transfer"),
}

_RULE_SCOPE_TRIGGERS: dict[str, tuple[str, ...]] = {
    "hard_gate": ("hard rule", "hard gate", "must not", "do not"),
    "soft_preference": ("prefer", "favor", "preference"),
    "procedure": ("procedure", "step", "workflow"),
}


def _resolve_unambiguous(
    q_lower: str, table: dict[str, tuple[str, ...]],
) -> str | None:
    hits = [
        key for key, toks in table.items()
        if any(t in q_lower for t in toks)
    ]
    # Emit only when exactly one candidate matches — avoid over-constraining.
    return hits[0] if len(hits) == 1 else None


# Filler tokens stripped from the refined query.
_REFINED_DROP = (
    "policy", "rule", "according to", "per the", "in the docs",
    "please", "kindly",
)


def _refine_query(q: str) -> str:
    out = q
    for tok in _REFINED_DROP:
        out = re.sub(r"\b" + re.escape(tok) + r"\b", "", out, flags=re.IGNORECASE)
    return " ".join(out.split()).strip() or q


def default_self_query_parser(query: str) -> dict[str, Any]:
    """Deterministic, offline self-query parser.

    Uses bounded keyword heuristics to produce:
      - a refined retrieval query (same query minus a few filler tokens)
      - a small filters dict keyed by metadata fields

    A filter is emitted only if its trigger table yields exactly one
    unambiguous candidate for the given query. This keeps the parser
    safe: ambiguous queries receive no filter (→ unfiltered retrieval).
    """
    if not isinstance(query, str) or not query.strip():
        return {
            "refined_query": "",
            "filters": {},
            "parser_name": "default_self_query_parser",
        }
    q = query.strip()
    q_l = q.lower()

    filters: dict[str, Any] = {}
    for field, table in (
        ("policy_family", _POLICY_FAMILY_TRIGGERS),
        ("scenario_family", _SCENARIO_FAMILY_TRIGGERS),
        ("agent_relevance", _AGENT_RELEVANCE_TRIGGERS),
        ("rule_scope", _RULE_SCOPE_TRIGGERS),
    ):
        v = _resolve_unambiguous(q_l, table)
        if v is not None:
            filters[field] = v

    return {
        "refined_query": _refine_query(q),
        "filters": filters,
        "parser_name": "default_self_query_parser",
    }


default_self_query_parser.name = "default_self_query_parser"  # type: ignore[attr-defined]


def _matches_filters(meta: dict[str, Any], filters: dict[str, Any]) -> bool:
    for k, v in filters.items():
        if k not in _FILTER_FIELDS:
            continue
        if meta.get(k) != v:
            return False
    return True


def retrieve_self_query(
    query: str,
    *,
    base_mode: str = "hybrid",
    k: int = 4,
    first_stage_n: int | None = None,
    contextualizer: Contextualizer | None = default_contextualizer,
    embedder: Embedder | None = None,
    reranker: Reranker | None = default_reranker,
    rerank: bool = True,
    parser: SelfQueryParser | None = None,
    filters_override: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], RetrievalTrace]:
    """Metadata-aware retrieval.

    Pipeline:
      1. `parser(query)` → {refined_query, filters, parser_name}. If
         `filters_override` is supplied, it replaces parser filters.
      2. Ensure advanced store is built.
      3. Compute dense + BM25 scores over the full corpus.
      4. Mask candidates whose `metadata` matches the filters. If the
         mask is empty, fall back to unfiltered hybrid retrieval and
         mark `fallback_used=True`.
      5. Rerank (optional) within the filtered top-N pool.
      6. Return top-k with the same shape used by the rest of the stack
         plus a populated `trace.self_query` block.

    Fallback: any exception during self-query retrieval falls back to the
    legacy TF-IDF path and sets `fallback_used=True`.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(k, int) or k < 1:
        raise ValueError(f"k must be an integer >= 1, got {k!r}")
    if base_mode not in _MULTI_BASE_MODES:
        raise ValueError(
            f"base_mode must be one of {sorted(_MULTI_BASE_MODES)}, got {base_mode!r}"
        )

    q = query.strip()
    parser_fn = parser or default_self_query_parser

    trace = RetrievalTrace(
        mode=f"self_{base_mode}" + ("_rerank" if rerank else ""),
        query=q,
        query_hash=_hash_query(q),
        k=k,
        contextualized=(contextualizer is not None),
        fallback_used=False,
        embedder_name=None,
        reranker_name=None,
    )

    try:
        # 1) Parse (with exception safety).
        try:
            parsed = parser_fn(q) or {}
        except Exception as exc:
            trace.error = f"self_query_parser_failed: {exc}"
            parsed = {
                "refined_query": q,
                "filters": {},
                "parser_name": getattr(parser_fn, "name",
                                       getattr(parser_fn, "__name__", "parser")),
            }

        refined = str(parsed.get("refined_query") or q)
        filters = dict(parsed.get("filters") or {})
        if filters_override is not None:
            filters = dict(filters_override)
        # Keep only recognized filter fields.
        filters = {k2: v for k2, v in filters.items() if k2 in _FILTER_FIELDS}
        parser_name = str(parsed.get(
            "parser_name",
            getattr(parser_fn, "name",
                    getattr(parser_fn, "__name__", "parser")),
        ))

        # 2) Build store.
        if not _store.is_built:
            build_advanced_store(contextualizer=contextualizer, embedder=embedder)
        full_corpus_size = len(_store.chunks)
        trace.embedder_name = _store.embedder_name

        # 3) Build filter mask.
        if filters:
            mask = np.array(
                [_matches_filters(c.get("metadata") or {}, filters)
                 for c in _store.chunks],
                dtype=bool,
            )
        else:
            mask = np.ones(full_corpus_size, dtype=bool)
        filtered_corpus_size = int(mask.sum())

        # Populate self_query trace upfront.
        trace.self_query = {
            "original_query": q,
            "refined_query": refined,
            "filters": filters,
            "parser_name": parser_name,
            "full_corpus_size": full_corpus_size,
            "filtered_corpus_size": filtered_corpus_size,
            "filter_empty": bool(filtered_corpus_size == 0),
        }

        if filtered_corpus_size == 0:
            # Filter excluded every chunk — fall back to unfiltered hybrid
            # but preserve the self_query trace block so it is auditable.
            trace.fallback_used = True
            trace.error = (
                (trace.error + "; " if trace.error else "")
                + "self_query_filter_empty_fallback_to_unfiltered"
            )
            fb_chunks, fb_trace = retrieve_advanced(
                refined if refined else q,
                mode=base_mode, k=k,
                first_stage_n=first_stage_n,
                contextualizer=contextualizer, embedder=embedder,
                reranker=reranker, rerank=rerank,
            )
            # Copy the fallback trace's first-stage candidates but keep the
            # outer self_query block intact.
            trace.candidates = fb_trace.candidates
            trace.reranker_name = fb_trace.reranker_name
            return fb_chunks, trace

        # 4) Compute scores.
        dense_scores = _store.score_dense(refined)
        lexical_scores = _store.score_bm25(refined)
        if base_mode == "dense":
            fused = dense_scores.copy()
        elif base_mode == "bm25":
            fused = lexical_scores.copy()
        else:  # hybrid
            fused = reciprocal_rank_fusion([dense_scores, lexical_scores])

        # Mask out non-matching indices by pushing them below any plausible
        # score. We still only consider matching indices when slicing.
        first_n = first_stage_n or max(k * 3, 8)
        matching_indices = np.where(mask)[0]
        # Sort matching indices by fused score desc.
        order = matching_indices[np.argsort(-fused[matching_indices], kind="stable")]
        first_n_capped = min(first_n, len(order))
        top_first = order[:first_n_capped]

        candidates: list[dict[str, Any]] = []
        for idx in top_first:
            c = dict(_store.chunks[int(idx)])
            c["dense_score"] = float(dense_scores[idx])
            c["lexical_score"] = float(lexical_scores[idx])
            c["fused_score"] = float(fused[idx])
            candidates.append(c)

        # 5) Rerank.
        if rerank and reranker is not None and candidates:
            try:
                rr = reranker(refined, candidates)
                if len(rr) != len(candidates):
                    raise ValueError("reranker returned wrong length")
                for c, s in zip(candidates, rr):
                    c["reranker_score"] = float(s)
                candidates.sort(
                    key=lambda c: c.get("reranker_score", 0.0), reverse=True,
                )
                trace.reranker_name = getattr(
                    reranker, "__name__", reranker.__class__.__name__,
                )
            except Exception as exc:
                for c in candidates:
                    c.setdefault("reranker_score", None)
                trace.error = (
                    (trace.error + "; " if trace.error else "")
                    + f"reranker_failed: {exc}"
                )
        else:
            for c in candidates:
                c["reranker_score"] = None

        final = candidates[:k]

        trace.candidates = [
            {
                "chunk_id": c["chunk_id"],
                "source_doc": c["source_doc"],
                "section": c.get("section", ""),
                "dense_score": c.get("dense_score"),
                "lexical_score": c.get("lexical_score"),
                "fused_score": c.get("fused_score"),
                "reranker_score": c.get("reranker_score"),
                "final_rank": i + 1,
                "metadata": c.get("metadata"),
            }
            for i, c in enumerate(final)
        ]

        out: list[dict[str, Any]] = []
        for i, c in enumerate(final):
            primary = (
                c.get("reranker_score")
                if c.get("reranker_score") is not None
                else c.get("fused_score", 0.0)
            )
            out.append({
                "chunk_id": c["chunk_id"],
                "source_doc": c["source_doc"],
                "section": c.get("section", ""),
                "text": c.get("text", ""),
                "contextualized_text": c.get("contextualized_text", c.get("text", "")),
                "contextual_prefix": c.get("contextual_prefix", ""),
                "retrieval_score": float(primary),
                "dense_score": c.get("dense_score"),
                "lexical_score": c.get("lexical_score"),
                "fused_score": c.get("fused_score"),
                "reranker_score": c.get("reranker_score"),
                "final_rank": i + 1,
                "metadata": c.get("metadata"),
            })
        return out, trace

    except Exception as exc:
        trace.error = (
            (trace.error + "; " if trace.error else "")
            + f"self_query_failed: {exc}"
        )
        trace.fallback_used = True
        try:
            results = _legacy_fallback(q, k, trace)
            return results, trace
        except Exception as exc2:  # pragma: no cover
            trace.error = f"{trace.error}; legacy_also_failed: {exc2}"
            return [], trace


# ---------------------------------------------------------------------------
# Compression branch — post-retrieval, per-chunk sentence selection
# ---------------------------------------------------------------------------

Compressor = Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]]
"""Takes (query, retrieved_chunks) and returns chunks with a populated
`compressed_text` field. Must not add, remove, or reorder chunks.
"""

# Sentence splitter: end-punctuation or newline boundary. Bounded + offline.
_SENT_SPLIT_RE = re.compile(r"(?<=[\.!\?])\s+|\n+")


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = _SENT_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p and p.strip()]


def default_compressor(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    max_sentences: int = 3,
    max_chars: int = 400,
) -> list[dict[str, Any]]:
    """Deterministic, offline, provenance-preserving compressor.

    For each chunk:
      1. Split the raw text into sentences.
      2. Score each sentence by (query_token_overlap, Jaccard, original_order).
      3. Pick the top `max_sentences`, restore original order, truncate to
         `max_chars`.
      4. If the selection is empty or contains no query token at all,
         fall back to the first sentence of the chunk.
      5. Attach `raw_text` (original) and `compressed_text`; set `text` to
         the compressed version so existing agent code continues to work.
      6. Chunk identity (chunk_id, source_doc, section) and provenance
         fields (retrieval_score, fused_score, reranker_score, metadata,
         final_rank) are preserved verbatim.

    This function never adds, removes, or reorders chunks.
    """
    if not isinstance(query, str):
        query = ""
    q_tokens = set(_tokenize(query))

    out: list[dict[str, Any]] = []
    for c in chunks:
        new_c = dict(c)
        raw = str(c.get("text", ""))
        sents = _split_sentences(raw)

        if not sents:
            compressed = raw
        else:
            scored: list[tuple[int, float, int, int, str]] = []
            for i, s in enumerate(sents):
                st = set(_tokenize(s))
                overlap = len(q_tokens & st)
                jacc = (len(q_tokens & st) / len(q_tokens | st)) if (q_tokens | st) else 0.0
                # Sort key: overlap desc, jaccard desc, position asc.
                scored.append((overlap, jacc, -i, i, s))
            scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
            picked_idx = sorted({t[3] for t in scored[:max_sentences]})
            picked = [sents[i] for i in picked_idx]
            compressed = " ".join(picked).strip()[:max_chars]

            # Fallback if compression stripped every query-relevant token
            # (or returned empty) — use the first sentence of the chunk.
            if not compressed or (q_tokens and not (q_tokens & set(_tokenize(compressed)))):
                compressed = sents[0][:max_chars]

        new_c["raw_text"] = raw
        new_c["compressed_text"] = compressed
        new_c["text"] = compressed
        new_c["compression_applied"] = True
        new_c["raw_length"] = len(raw)
        new_c["compressed_length"] = len(compressed)
        out.append(new_c)
    return out


default_compressor.name = "default_compressor"  # type: ignore[attr-defined]


def apply_compression(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    compressor: Compressor | None = default_compressor,
    **compressor_kwargs: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply a compressor to already-retrieved chunks.

    Parameters
    ----------
    query : the query used for relevance-aware sentence selection
    chunks : list of retrieved chunk dicts (raw text in `text`)
    compressor : callable(query, chunks, **kwargs) -> compressed chunks
    compressor_kwargs : forwarded to the compressor

    Returns
    -------
    (compressed_chunks, summary)
        `summary` is a dict suitable for populating `RetrievalTrace.compression`.

    Never adds, removes, or reorders chunks. If the compressor raises,
    returns the original chunks unchanged and `fallback_used=True`.
    """
    comp_name = getattr(
        compressor, "name",
        getattr(compressor, "__name__", "compressor")
        if compressor is not None else "none",
    )
    raw_counts = [len(str(c.get("text", ""))) for c in chunks]
    raw_total = sum(raw_counts)
    n = len(chunks)

    if compressor is None or not chunks:
        return chunks, {
            "compressor_name": comp_name,
            "raw_chunk_count": n,
            "compressed_chunk_count": n,
            "raw_total_chars": raw_total,
            "compressed_total_chars": raw_total,
            "compression_ratio": 1.0,
            "fallback_used": False,
            "per_chunk": [
                {
                    "chunk_id": c.get("chunk_id"),
                    "raw_length": len(str(c.get("text", ""))),
                    "compressed_length": len(str(c.get("text", ""))),
                    "ratio": 1.0,
                }
                for c in chunks
            ],
        }

    try:
        out = compressor(query, chunks, **compressor_kwargs)
        if len(out) != n:
            raise RuntimeError(
                f"compressor changed chunk count: {n} → {len(out)}"
            )
        # Verify chunk identity & order preserved.
        for a, b in zip(chunks, out):
            if a.get("chunk_id") != b.get("chunk_id"):
                raise RuntimeError("compressor reordered or swapped chunks")
    except Exception as exc:
        return chunks, {
            "compressor_name": comp_name,
            "raw_chunk_count": n,
            "compressed_chunk_count": n,
            "raw_total_chars": raw_total,
            "compressed_total_chars": raw_total,
            "compression_ratio": 1.0,
            "fallback_used": True,
            "error": f"{type(exc).__name__}: {exc}",
            "per_chunk": [
                {
                    "chunk_id": c.get("chunk_id"),
                    "raw_length": len(str(c.get("text", ""))),
                    "compressed_length": len(str(c.get("text", ""))),
                    "ratio": 1.0,
                }
                for c in chunks
            ],
        }

    per_chunk: list[dict[str, Any]] = []
    compressed_total = 0
    for c in out:
        raw_len = int(c.get("raw_length", len(str(c.get("raw_text", "")))))
        comp_len = int(c.get("compressed_length", len(str(c.get("text", "")))))
        compressed_total += comp_len
        per_chunk.append({
            "chunk_id": c.get("chunk_id"),
            "raw_length": raw_len,
            "compressed_length": comp_len,
            "ratio": (comp_len / raw_len) if raw_len else 1.0,
        })

    return out, {
        "compressor_name": comp_name,
        "raw_chunk_count": n,
        "compressed_chunk_count": len(out),
        "raw_total_chars": raw_total,
        "compressed_total_chars": compressed_total,
        "compression_ratio": (compressed_total / raw_total) if raw_total else 1.0,
        "fallback_used": False,
        "per_chunk": per_chunk,
    }


def _run_with_compression(
    base_mode: str,
    query: str,
    *,
    k: int,
    contextualizer: Contextualizer | None,
    embedder: Embedder | None,
    reranker: Reranker | None,
    compressor: Compressor | None,
    compressor_kwargs: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], RetrievalTrace]:
    """Run a base agent mode, then apply compression and populate trace."""
    # Recurse through the agent dispatcher for the base mode so the
    # compression branch doesn't duplicate base-mode plumbing.
    chunks, trace = retrieve_for_agent(
        query, mode=base_mode, k=k,
        contextualizer=contextualizer, embedder=embedder, reranker=reranker,
    )
    kwargs = compressor_kwargs or {}
    compressed, summary = apply_compression(
        query, chunks, compressor=compressor, **kwargs,
    )
    trace.compression = summary
    trace.mode = f"{trace.mode}_compress" if not trace.mode.endswith("_compress") else trace.mode
    return compressed, trace


# ---------------------------------------------------------------------------
# Agent-facing convenience wrapper (Phase 6 integration)
# ---------------------------------------------------------------------------


def _normalize_agent_mode(mode: str | None) -> str:
    """Normalize and validate agent-facing retrieval mode.

    Unknown or None values degrade to 'tfidf_legacy' (safe default).
    """
    if mode is None:
        return "tfidf_legacy"
    cand = str(mode).strip().lower()
    if cand not in AGENT_RETRIEVAL_MODES:
        return "tfidf_legacy"
    return cand


def retrieve_for_agent(
    query: str,
    *,
    mode: str | None = "tfidf_legacy",
    k: int = 4,
    contextualizer: Contextualizer | None = default_contextualizer,
    embedder: Embedder | None = None,
    reranker: Reranker | None = default_reranker,
) -> tuple[list[dict[str, Any]], RetrievalTrace]:
    """Agent-facing retrieval entry point.

    Accepts the four agent-facing modes:
      - "tfidf_legacy"   : legacy TF-IDF (byte-compatible baseline)
      - "dense"          : dense-only (pluggable embedder)
      - "hybrid"         : dense + BM25 with RRF, NO reranker
      - "hybrid_rerank"  : dense + BM25 with RRF + reranker stage

    Always returns (chunks, trace). On any advanced-path failure the legacy
    TF-IDF path is used and the trace flags `fallback_used=True`.
    """
    resolved = _normalize_agent_mode(mode)

    # Compression modes wrap a base mode and post-process retrieved chunks.
    if resolved.endswith(_COMPRESS_SUFFIX):
        base_mode = resolved[: -len(_COMPRESS_SUFFIX)]
        return _run_with_compression(
            base_mode, query,
            k=k, contextualizer=contextualizer, embedder=embedder,
            reranker=reranker, compressor=default_compressor,
        )

    if resolved == "tfidf_legacy":
        return retrieve_advanced(query, mode="tfidf_legacy", k=k)

    if resolved == "dense":
        return retrieve_advanced(
            query, mode="dense", k=k,
            contextualizer=contextualizer, embedder=embedder,
            reranker=None, rerank=False,
        )

    if resolved == "hybrid":
        return retrieve_advanced(
            query, mode="hybrid", k=k,
            contextualizer=contextualizer, embedder=embedder,
            reranker=None, rerank=False,
        )

    if resolved == "hybrid_rerank":
        return retrieve_advanced(
            query, mode="hybrid", k=k,
            contextualizer=contextualizer, embedder=embedder,
            reranker=reranker, rerank=True,
        )

    # Multi-query branch.
    if resolved == "multi_hybrid":
        return retrieve_multi(
            query, base_mode="hybrid", k=k,
            contextualizer=contextualizer, embedder=embedder,
            reranker=None, rerank=False,
        )

    if resolved == "multi_hybrid_rerank":
        return retrieve_multi(
            query, base_mode="hybrid", k=k,
            contextualizer=contextualizer, embedder=embedder,
            reranker=reranker, rerank=True,
        )

    # Self-query branch.
    if resolved == "self_hybrid":
        return retrieve_self_query(
            query, base_mode="hybrid", k=k,
            contextualizer=contextualizer, embedder=embedder,
            reranker=None, rerank=False,
        )

    # self_hybrid_rerank
    return retrieve_self_query(
        query, base_mode="hybrid", k=k,
        contextualizer=contextualizer, embedder=embedder,
        reranker=reranker, rerank=True,
    )


def summarize_trace(trace: RetrievalTrace, agent_mode: str) -> dict[str, Any]:
    """Build a compact sidecar dict suitable for graph/UI surfacing.

    This is separate from trace.to_dict() so the frozen chunk-level detail
    is not mixed into agent meta. Contains only stable summary fields.
    """
    reranker_used = bool(
        trace.reranker_name and not (trace.error and "reranker_failed" in (trace.error or ""))
    )
    summary = {
        "agent_mode": agent_mode,
        "engine_mode": trace.mode,
        "query_hash": trace.query_hash,
        "k": trace.k,
        "candidate_count": len(trace.candidates),
        "contextualized": trace.contextualized,
        "reranker_used": reranker_used,
        "fallback_used": trace.fallback_used,
        "embedder_name": trace.embedder_name,
        "reranker_name": trace.reranker_name,
        "error": trace.error,
        "top_chunk_ids": [c.get("chunk_id") for c in trace.candidates],
    }
    if trace.compression is not None:
        comp = trace.compression
        summary["compression"] = {
            "compressor_name": comp.get("compressor_name"),
            "raw_chunk_count": comp.get("raw_chunk_count"),
            "compressed_chunk_count": comp.get("compressed_chunk_count"),
            "raw_total_chars": comp.get("raw_total_chars"),
            "compressed_total_chars": comp.get("compressed_total_chars"),
            "compression_ratio": comp.get("compression_ratio"),
            "fallback_used": comp.get("fallback_used"),
        }
    if trace.self_query is not None:
        sq = trace.self_query
        summary["self_query"] = {
            "refined_query": sq.get("refined_query"),
            "filters": sq.get("filters"),
            "parser_name": sq.get("parser_name"),
            "full_corpus_size": sq.get("full_corpus_size"),
            "filtered_corpus_size": sq.get("filtered_corpus_size"),
            "filter_empty": sq.get("filter_empty"),
        }
    if trace.multi_query is not None:
        mq = trace.multi_query
        summary["multi_query"] = {
            "sub_query_count": mq.get("sub_query_count"),
            "per_subquery_candidate_counts": mq.get("per_subquery_candidate_counts"),
            "merged_count": mq.get("merged_count"),
            "deduped_count": mq.get("deduped_count"),
            "generator_name": mq.get("generator_name"),
            "sub_query_hashes": mq.get("sub_query_hashes"),
            "base_mode": mq.get("base_mode"),
            "rerank": mq.get("rerank"),
        }
    return summary
