"""
phase6_batch_eval.py — Official Phase 6 batch evaluation + observability runner.

Scope
-----
Replays the full case set through the compiled LangGraph across a matrix of:
    supervisor_mode  ∈ {approve, verify, override}
    retrieval_mode   ∈ {tfidf_legacy, hybrid, hybrid_rerank}
and, defaulting to "rules", also records:
    operations_mode  ∈ {rules, llm}
    governance_mode  ∈ {rules, llm}

For each (case × supervisor × retrieval) triple it captures:

  - replay_id (deterministic short hash over (case,supervisor,retrieval,ops,gov))
  - timestamp_utc
  - scenario_id / scenario_type / risk_level
  - all Phase 1 evaluation metrics from case JSON + evaluation.py
  - retrieval trace summary from _operations_meta.retrieval
  - LLM trace summary from _operations_meta.llm_trace and _governance_meta.llm_trace
  - latency_ms
  - status / skip_reason / error

It then produces aggregate comparison artifacts (CSV + JSON + markdown) sliced
by supervisor_mode, retrieval_mode, risk_level, and scenario_family.

Boundaries
----------
* runtime estimates are not oracle truth
* evaluation truth still comes only from case JSON + evaluation.py
* operational / supervision / evaluation identifiers never mixed
* frozen schemas untouched
* override uses Phase 1 explicit per-case target label — no silent collapse

Offline-compatible; no live API required.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import glob
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Iterable

_PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

from action_code_mapper import find_override_target_label  # noqa: E402
from graph import compile_graph  # noqa: E402


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SUPERVISOR_MODES: tuple[str, ...] = ("approve", "verify", "override")
DEFAULT_RETRIEVAL_MODES: tuple[str, ...] = (
    "tfidf_legacy", "hybrid", "hybrid_rerank",
)

_ROW_FIELDS: list[str] = [
    # Identity
    "replay_id", "timestamp_utc",
    "case_id", "scenario_id", "scenario_type", "scenario_family", "risk_level",
    # Mode matrix
    "supervisor_mode", "retrieval_mode",
    "operations_mode", "governance_mode",
    # Supervisor / evaluation outcomes
    "supervisor_decision_type",
    "human_action_code", "agent_action_code", "oracle_action_code",
    "chosen_cost", "oracle_cost",
    "regret", "is_override", "is_unnecessary_override",
    "override_effectiveness", "override_target_label",
    # Retrieval observability
    "retrieval_engine_mode", "retrieval_candidate_count",
    "retrieval_query_hash", "retrieval_contextualized",
    "retrieval_reranker_used", "retrieval_fallback_used",
    "retrieval_embedder_name", "retrieval_reranker_name",
    # LLM observability (operations + governance)
    "ops_llm_provider", "ops_llm_model", "ops_llm_attempts", "ops_llm_fallback_used",
    "gov_llm_provider", "gov_llm_model", "gov_llm_attempts", "gov_llm_fallback_used",
    # Run-time
    "latency_ms",
    # Status
    "status", "skip_reason", "error",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_instruction(mode: str) -> dict:
    if mode == "approve":
        return {"mode": "approve"}
    if mode == "verify":
        return {"mode": "verify", "review_focus": "Phase 6 batch replay verify."}
    if mode == "override":
        return {"mode": "override"}
    raise ValueError(f"Unknown supervisor mode: {mode}")


def _load_case(case_id: str) -> dict | None:
    path = _PROJECT_DIR / "data" / "cases" / f"{case_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _replay_id(case_id: str, supervisor: str, retrieval: str,
               ops_mode: str, gov_mode: str) -> str:
    raw = f"{case_id}|{supervisor}|{retrieval}|{ops_mode}|{gov_mode}"
    return "rp_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _now_utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scenario_family(scenario_type: str | None) -> str:
    if not scenario_type:
        return "unknown"
    # Normalize: first significant token, lowercased.
    return str(scenario_type).strip().split()[0].lower() if scenario_type.strip() else "unknown"


def _empty_row(case_id: str, supervisor_mode: str, retrieval_mode: str,
               operations_mode: str, governance_mode: str) -> dict:
    row = {k: None for k in _ROW_FIELDS}
    row.update({
        "replay_id": _replay_id(case_id, supervisor_mode, retrieval_mode,
                                operations_mode, governance_mode),
        "timestamp_utc": _now_utc_iso(),
        "case_id": case_id,
        "supervisor_mode": supervisor_mode,
        "retrieval_mode": retrieval_mode,
        "operations_mode": operations_mode,
        "governance_mode": governance_mode,
    })
    return row


def _extract_retrieval_fields(ops_meta: dict | None) -> dict:
    r = (ops_meta or {}).get("retrieval") or {}
    return {
        "retrieval_engine_mode": r.get("engine_mode"),
        "retrieval_candidate_count": r.get("candidate_count"),
        "retrieval_query_hash": r.get("query_hash"),
        "retrieval_contextualized": r.get("contextualized"),
        "retrieval_reranker_used": r.get("reranker_used"),
        "retrieval_fallback_used": r.get("fallback_used"),
        "retrieval_embedder_name": r.get("embedder_name"),
        "retrieval_reranker_name": r.get("reranker_name"),
    }


def _extract_llm_trace(meta: dict | None, prefix: str) -> dict:
    t = (meta or {}).get("llm_trace") or {}
    return {
        f"{prefix}_llm_provider": t.get("provider"),
        f"{prefix}_llm_model": t.get("model"),
        f"{prefix}_llm_attempts": t.get("attempts"),
        f"{prefix}_llm_fallback_used": t.get("fallback_used"),
    }


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------


def build_observability_rows(
    supervisor_modes: Iterable[str] = DEFAULT_SUPERVISOR_MODES,
    retrieval_modes: Iterable[str] = DEFAULT_RETRIEVAL_MODES,
    case_ids: Iterable[str] | None = None,
    *,
    operations_mode: str = "rules",
    governance_mode: str = "rules",
    graph: Any = None,
    retrieval_k: int = 4,
    case_loader=None,
) -> list[dict]:
    """Run the graph over the matrix and return a list of row dicts.

    Parameters
    ----------
    supervisor_modes, retrieval_modes, case_ids:
        The matrix axes. If `case_ids` is None, loads every *.json under
        data/cases/.
    operations_mode, governance_mode:
        Phase 4 / Phase 3 modes. Default "rules" keeps runs deterministic.
    graph:
        Optional precompiled graph (reused across rows).
    retrieval_k:
        Passed through to the operations agent retrieval call.
    case_loader:
        Optional callable(case_id) -> dict | None. Defaults to reading the
        case JSON from disk. Tests inject a fixture loader here.
    """
    graph = graph or compile_graph()
    loader = case_loader or _load_case

    if case_ids is None:
        case_files = sorted(
            glob.glob(str(_PROJECT_DIR / "data" / "cases" / "*.json"))
        )
        case_ids = [Path(p).stem for p in case_files]

    rows: list[dict] = []

    for case_id in case_ids:
        case = loader(case_id)
        for supervisor in supervisor_modes:
            base = _base_instruction(supervisor)
            for retrieval in retrieval_modes:
                row = _empty_row(case_id, supervisor, retrieval,
                                 operations_mode, governance_mode)

                if case is None:
                    row["status"] = "skipped"
                    row["skip_reason"] = "case file not found"
                    rows.append(row)
                    continue

                row["scenario_id"] = case.get("scenario_id")
                row["scenario_type"] = case.get("scenario_type")
                row["scenario_family"] = _scenario_family(case.get("scenario_type"))
                row["risk_level"] = case.get("risk_level")

                instruction = dict(base)
                override_target = None
                if supervisor == "override":
                    override_target = find_override_target_label(case)
                    if not override_target:
                        row["status"] = "skipped"
                        row["skip_reason"] = (
                            "no alternative_plan option in decision_options"
                        )
                        row["override_target_label"] = None
                        rows.append(row)
                        continue
                    instruction["target_action_label"] = override_target
                row["override_target_label"] = override_target

                graph_input = {
                    "case_id": case_id,
                    "supervisor_instruction": instruction,
                    "retrieval_mode": retrieval,
                    "retrieval_k": int(retrieval_k),
                    "operations_mode": operations_mode,
                    "governance_mode": governance_mode,
                }

                t0 = time.perf_counter()
                try:
                    result = graph.invoke(graph_input)
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                except Exception as exc:  # pragma: no cover
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    row["status"] = "error"
                    row["error"] = f"{type(exc).__name__}: {exc}"
                    row["latency_ms"] = latency_ms
                    rows.append(row)
                    continue

                row["latency_ms"] = latency_ms

                ev = result.get("evaluation_result", {}) or {}
                row.update({
                    "supervisor_decision_type": ev.get("supervisor_decision_type"),
                    "human_action_code": ev.get("human_action_code"),
                    "agent_action_code": ev.get("agent_action_code"),
                    "oracle_action_code": ev.get("oracle_action_code"),
                    "chosen_cost": ev.get("chosen_cost"),
                    "oracle_cost": ev.get("oracle_cost"),
                    "regret": ev.get("regret"),
                    "is_override": ev.get("is_override"),
                    "is_unnecessary_override": ev.get("is_unnecessary_override"),
                    "override_effectiveness": ev.get("override_effectiveness"),
                    "status": ev.get("status", "unknown"),
                    "skip_reason": (ev.get("reason")
                                    if ev.get("status") not in ("ok", None)
                                    else None),
                })

                ops_meta = result.get("_operations_meta") or {}
                gov_meta = result.get("_governance_meta") or {}
                row.update(_extract_retrieval_fields(ops_meta))
                row.update(_extract_llm_trace(ops_meta, prefix="ops"))
                row.update(_extract_llm_trace(gov_meta, prefix="gov"))

                rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


def _mean_safe(xs: list[Any]) -> float | None:
    nums = [float(x) for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return statistics.fmean(nums) if nums else None


def _rate_safe(flags: list[Any]) -> float | None:
    flags = [bool(x) for x in flags if x is not None]
    return (sum(flags) / len(flags)) if flags else None


def _slice_metrics(rows: list[dict]) -> dict:
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    return {
        "n_total": len(rows),
        "n_ok": len(ok_rows),
        "n_skipped": sum(1 for r in rows if r.get("status") == "skipped"),
        "n_error": sum(1 for r in rows if r.get("status") == "error"),
        "mean_regret": _mean_safe([r.get("regret") for r in ok_rows]),
        "unnecessary_override_rate": _rate_safe(
            [r.get("is_unnecessary_override") for r in ok_rows]
        ),
        "override_effectiveness_mean": _mean_safe(
            [r.get("override_effectiveness") for r in ok_rows]
        ),
        "retrieval_fallback_count": sum(
            1 for r in rows if r.get("retrieval_fallback_used") is True
        ),
        "ops_llm_fallback_count": sum(
            1 for r in rows if r.get("ops_llm_fallback_used") is True
        ),
        "gov_llm_fallback_count": sum(
            1 for r in rows if r.get("gov_llm_fallback_used") is True
        ),
        "mean_latency_ms": _mean_safe([r.get("latency_ms") for r in rows]),
    }


def _group_by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        k = r.get(key) or "unknown"
        buckets.setdefault(str(k), []).append(r)
    return buckets


def aggregate_report(rows: list[dict]) -> dict:
    """Produce overall + sliced aggregations."""
    return {
        "overall": _slice_metrics(rows),
        "by_supervisor_mode": {
            k: _slice_metrics(v)
            for k, v in _group_by(rows, "supervisor_mode").items()
        },
        "by_retrieval_mode": {
            k: _slice_metrics(v)
            for k, v in _group_by(rows, "retrieval_mode").items()
        },
        "by_risk_level": {
            k: _slice_metrics(v)
            for k, v in _group_by(rows, "risk_level").items()
        },
        "by_scenario_family": {
            k: _slice_metrics(v)
            for k, v in _group_by(rows, "scenario_family").items()
        },
    }


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------


def write_rows_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_ROW_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in _ROW_FIELDS})


def write_summary_json(rows: list[dict], agg: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"rows": rows, "aggregations": agg}, f,
                  indent=2, default=str)


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _slice_table(title: str, slices: dict[str, dict]) -> list[str]:
    lines = [f"### {title}\n"]
    lines.append(
        "| key | n_total | n_ok | n_skipped | n_error | mean_regret | "
        "unnecessary_override_rate | override_effectiveness_mean | "
        "retrieval_fallback_count | ops_llm_fallback_count | "
        "gov_llm_fallback_count | mean_latency_ms |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for k in sorted(slices.keys()):
        s = slices[k]
        lines.append(
            f"| {k} | {_fmt(s['n_total'])} | {_fmt(s['n_ok'])} | "
            f"{_fmt(s['n_skipped'])} | {_fmt(s['n_error'])} | "
            f"{_fmt(s['mean_regret'])} | "
            f"{_fmt(s['unnecessary_override_rate'])} | "
            f"{_fmt(s['override_effectiveness_mean'])} | "
            f"{_fmt(s['retrieval_fallback_count'])} | "
            f"{_fmt(s['ops_llm_fallback_count'])} | "
            f"{_fmt(s['gov_llm_fallback_count'])} | "
            f"{_fmt(s['mean_latency_ms'])} |"
        )
    lines.append("")
    return lines


def render_markdown(rows: list[dict], agg: dict) -> str:
    lines: list[str] = []
    lines.append("# Phase 6 Batch Evaluation Report\n")
    lines.append(f"- rows: {len(rows)}")
    lines.append(f"- generated_at: {_now_utc_iso()}\n")

    overall = agg["overall"]
    lines.append("## Overall\n")
    lines.append(
        "| n_total | n_ok | n_skipped | n_error | mean_regret | "
        "unnecessary_override_rate | override_effectiveness_mean | "
        "retrieval_fallback_count | ops_llm_fallback_count | "
        "gov_llm_fallback_count | mean_latency_ms |"
    )
    lines.append(
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    lines.append(
        f"| {_fmt(overall['n_total'])} | {_fmt(overall['n_ok'])} | "
        f"{_fmt(overall['n_skipped'])} | {_fmt(overall['n_error'])} | "
        f"{_fmt(overall['mean_regret'])} | "
        f"{_fmt(overall['unnecessary_override_rate'])} | "
        f"{_fmt(overall['override_effectiveness_mean'])} | "
        f"{_fmt(overall['retrieval_fallback_count'])} | "
        f"{_fmt(overall['ops_llm_fallback_count'])} | "
        f"{_fmt(overall['gov_llm_fallback_count'])} | "
        f"{_fmt(overall['mean_latency_ms'])} |\n"
    )

    lines += _slice_table("By supervisor mode", agg["by_supervisor_mode"])
    lines += _slice_table("By retrieval mode", agg["by_retrieval_mode"])
    lines += _slice_table("By risk level", agg["by_risk_level"])
    lines += _slice_table("By scenario family", agg["by_scenario_family"])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 6 batch evaluation + observability runner"
    )
    p.add_argument("--supervisor-modes", nargs="+",
                   default=list(DEFAULT_SUPERVISOR_MODES))
    p.add_argument("--retrieval-modes", nargs="+",
                   default=list(DEFAULT_RETRIEVAL_MODES))
    p.add_argument("--operations-mode", default="rules",
                   choices=["rules", "llm"])
    p.add_argument("--governance-mode", default="rules",
                   choices=["rules", "llm"])
    p.add_argument("--cases", nargs="*", default=None,
                   help="case_ids to run (default: all under data/cases)")
    p.add_argument("--retrieval-k", type=int, default=4)
    p.add_argument("--out-dir", default=str(_PROJECT_DIR / "data" / "phase6_eval"))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = build_observability_rows(
        supervisor_modes=tuple(args.supervisor_modes),
        retrieval_modes=tuple(args.retrieval_modes),
        case_ids=args.cases,
        operations_mode=args.operations_mode,
        governance_mode=args.governance_mode,
        retrieval_k=args.retrieval_k,
    )
    agg = aggregate_report(rows)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_rows_csv(rows, out_dir / "rows.csv")
    write_summary_json(rows, agg, out_dir / "summary.json")
    md = render_markdown(rows, agg)
    (out_dir / "report.md").write_text(md)

    n_ok = sum(1 for r in rows if r.get("status") == "ok")
    n_skip = sum(1 for r in rows if r.get("status") == "skipped")
    n_err = sum(1 for r in rows if r.get("status") == "error")
    print(f"Wrote {len(rows)} rows → {out_dir}  "
          f"(ok={n_ok}, skipped={n_skip}, error={n_err})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
