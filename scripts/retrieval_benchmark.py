"""
retrieval_benchmark.py — Offline retrieval-mode comparison harness.

Runs a fixed set of representative supply-chain queries across:
    - tfidf_legacy
    - hybrid
    - hybrid_rerank

For each (mode, query) pair captures:
    - top-k chunk provenance (chunk_id, source_doc)
    - mean retrieval latency (ms)
    - fallback occurrence
    - pairwise top-k overlap vs tfidf_legacy baseline
    - rank-biased overlap and a simple "coverage" relevance proxy based on
      expected source documents per query

Outputs:
    - a markdown summary report (stdout or --out-md)
    - a JSON dump of the raw per-query results (--out-json)
    - optional CSV per-mode summary (--out-csv)

No live API. Uses only local vector stores + pluggable deterministic
dense embedder from src/retrieval.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from typing import Any

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, os.path.join(_PROJECT_DIR, "src"))

import rag_setup  # noqa: E402
from retrieval import (  # noqa: E402
    reset_advanced_store,
    retrieve_for_agent,
    summarize_trace,
)


# ---------------------------------------------------------------------------
# Representative query set
# ---------------------------------------------------------------------------
# Each query carries an 'expected_docs' set — source docs we consider
# relevant for the scenario. This is a simple grounding-quality proxy; it
# is not an oracle truth label, and it is not used in evaluation.py.
QUERY_SET: list[dict[str, Any]] = [
    {
        "name": "carrier_capacity_shortage",
        "query": "Carrier Capacity Shortage MEDIUM risk Carrier CR_1 unavailable for the next window.",
        "expected_docs": {"carrier_selection_rules.md", "exception_handling_sop.md"},
    },
    {
        "name": "sla_breach_risk",
        "query": "SLA breach risk shipment delayed beyond promise deadline",
        "expected_docs": {"sla_terms.md", "escalation_protocol.md"},
    },
    {
        "name": "inventory_discrepancy_transfer",
        "query": "Inventory discrepancy warehouse shortage consider reallocation transfer",
        "expected_docs": {"inventory_transfer_policy.md", "exception_handling_sop.md"},
    },
    {
        "name": "compliance_block",
        "query": "Compliance documentation block on shipment confirm escalation protocol",
        "expected_docs": {"escalation_protocol.md", "exception_handling_sop.md"},
    },
    {
        "name": "stable_routine",
        "query": "No abnormal signal stable route within SLA routine fulfillment",
        "expected_docs": {"sla_terms.md", "exception_handling_sop.md"},
    },
]

MODES = (
    "tfidf_legacy",
    "hybrid",
    "hybrid_rerank",
    "multi_hybrid",
    "multi_hybrid_rerank",
    "self_hybrid",
    "self_hybrid_rerank",
    "hybrid_rerank_compress",
    "multi_hybrid_rerank_compress",
    "self_hybrid_rerank_compress",
)


# ---------------------------------------------------------------------------
# Run + summarize
# ---------------------------------------------------------------------------


def _run_single(query: str, mode: str, k: int) -> dict[str, Any]:
    t0 = time.perf_counter()
    chunks, trace = retrieve_for_agent(query, mode=mode, k=k)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    summary = summarize_trace(trace, mode)
    mq = summary.get("multi_query") or {}
    sq = summary.get("self_query") or {}
    return {
        "mode": mode,
        "latency_ms": dt_ms,
        "top_chunk_ids": [c.get("chunk_id") for c in chunks],
        "top_source_docs": [c.get("source_doc") for c in chunks],
        "fallback_used": summary.get("fallback_used", False),
        "reranker_used": summary.get("reranker_used", False),
        "contextualized": summary.get("contextualized", False),
        "candidate_count": summary.get("candidate_count", len(chunks)),
        "error": summary.get("error"),
        "sub_query_count": mq.get("sub_query_count"),
        "merged_count": mq.get("merged_count"),
        "deduped_count": mq.get("deduped_count"),
        "self_query_filters": sq.get("filters"),
        "self_query_filtered_corpus_size": sq.get("filtered_corpus_size"),
        "self_query_filter_empty": sq.get("filter_empty"),
        "compression_ratio": (summary.get("compression") or {}).get("compression_ratio"),
        "compression_compressor_name": (summary.get("compression") or {}).get("compressor_name"),
        "compression_fallback_used": (summary.get("compression") or {}).get("fallback_used"),
    }


def _overlap(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def _coverage(top_docs: list[str], expected: set[str]) -> float:
    if not expected:
        return 0.0
    seen = {d for d in top_docs if d in expected}
    return len(seen) / len(expected)


def run_benchmark(
    queries: list[dict[str, Any]] = None,
    modes: tuple[str, ...] = MODES,
    k: int = 4,
) -> dict[str, Any]:
    queries = queries or QUERY_SET

    # Warm both stores (idempotent).
    rag_setup.reset_store()
    reset_advanced_store()
    rag_setup.build_vector_store()

    per_query: list[dict[str, Any]] = []
    for q in queries:
        q_results: dict[str, Any] = {
            "name": q["name"],
            "query": q["query"],
            "expected_docs": sorted(q.get("expected_docs") or []),
            "modes": {},
        }
        for m in modes:
            r = _run_single(q["query"], m, k)
            r["coverage_vs_expected"] = _coverage(
                r["top_source_docs"], set(q.get("expected_docs") or []),
            )
            q_results["modes"][m] = r

        # Pairwise overlap vs tfidf_legacy baseline.
        base_ids = q_results["modes"].get("tfidf_legacy", {}).get("top_chunk_ids", [])
        for m in modes:
            ids = q_results["modes"][m]["top_chunk_ids"]
            q_results["modes"][m]["jaccard_vs_legacy"] = _overlap(ids, base_ids)
        per_query.append(q_results)

    # Aggregate per-mode.
    agg: dict[str, Any] = {}
    for m in modes:
        latencies = [qr["modes"][m]["latency_ms"] for qr in per_query]
        coverages = [qr["modes"][m]["coverage_vs_expected"] for qr in per_query]
        overlaps = [qr["modes"][m]["jaccard_vs_legacy"] for qr in per_query]
        fallbacks = sum(1 for qr in per_query if qr["modes"][m]["fallback_used"])
        agg[m] = {
            "mean_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
            "p95_latency_ms": (
                sorted(latencies)[int(0.95 * (len(latencies) - 1))]
                if latencies else 0.0
            ),
            "mean_coverage_vs_expected": (
                statistics.fmean(coverages) if coverages else 0.0
            ),
            "mean_jaccard_vs_legacy": (
                statistics.fmean(overlaps) if overlaps else 0.0
            ),
            "fallback_count": fallbacks,
            "query_count": len(per_query),
        }

    return {"queries": per_query, "modes": list(modes), "k": k, "summary": agg}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Retrieval Benchmark Report\n")
    lines.append(f"- k = {report['k']}")
    lines.append(f"- modes: {', '.join(report['modes'])}")
    lines.append(f"- queries: {len(report['queries'])}\n")

    lines.append("## Mode summary\n")
    lines.append("| mode | mean_latency_ms | p95_latency_ms | "
                 "mean_coverage_vs_expected | mean_jaccard_vs_legacy | "
                 "fallback_count |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for m, s in report["summary"].items():
        lines.append(
            f"| {m} | {s['mean_latency_ms']:.2f} | {s['p95_latency_ms']:.2f} "
            f"| {s['mean_coverage_vs_expected']:.2f} "
            f"| {s['mean_jaccard_vs_legacy']:.2f} | {s['fallback_count']} |"
        )
    lines.append("")

    lines.append("## Per-query detail\n")
    for qr in report["queries"]:
        lines.append(f"### {qr['name']}")
        lines.append(f"> {qr['query']}")
        lines.append(f"- expected_docs: `{qr['expected_docs']}`\n")
        lines.append("| mode | top_chunk_ids | top_source_docs | "
                     "latency_ms | coverage | jaccard_vs_legacy | fallback |")
        lines.append("|---|---|---|---:|---:|---:|---:|")
        for m, r in qr["modes"].items():
            lines.append(
                f"| {m} | `{r['top_chunk_ids']}` | `{r['top_source_docs']}` "
                f"| {r['latency_ms']:.2f} "
                f"| {r['coverage_vs_expected']:.2f} "
                f"| {r['jaccard_vs_legacy']:.2f} "
                f"| {'yes' if r['fallback_used'] else 'no'} |"
            )
        lines.append("")
    return "\n".join(lines)


def write_csv_summary(report: dict[str, Any], path: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["mode", "mean_latency_ms", "p95_latency_ms",
                    "mean_coverage_vs_expected", "mean_jaccard_vs_legacy",
                    "fallback_count", "query_count"])
        for m, s in report["summary"].items():
            w.writerow([
                m, f"{s['mean_latency_ms']:.4f}", f"{s['p95_latency_ms']:.4f}",
                f"{s['mean_coverage_vs_expected']:.4f}",
                f"{s['mean_jaccard_vs_legacy']:.4f}",
                s["fallback_count"], s["query_count"],
            ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Retrieval-mode benchmark harness")
    p.add_argument("--k", type=int, default=4, help="top-k (default 4)")
    p.add_argument("--out-md", type=str, default=None,
                   help="write markdown report to this path")
    p.add_argument("--out-json", type=str, default=None,
                   help="write raw report JSON to this path")
    p.add_argument("--out-csv", type=str, default=None,
                   help="write per-mode CSV summary to this path")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = run_benchmark(k=args.k)
    md = render_markdown(report)

    if args.out_md:
        with open(args.out_md, "w") as f:
            f.write(md)
    else:
        print(md)

    if args.out_json:
        with open(args.out_json, "w") as f:
            json.dump(report, f, indent=2, default=str)

    if args.out_csv:
        write_csv_summary(report, args.out_csv)

    return 0


if __name__ == "__main__":
    sys.exit(main())
