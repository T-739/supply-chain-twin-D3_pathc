"""
batch_eval_runner.py — Phase 1 minimal batch runner.

Runs every case in data/cases/*.json through the compiled graph under a
fixed supervisor mode (default: approve) and exports evaluation metrics
to a CSV. Deliberately small: one mode per run, deterministic output.

Usage:
    python scripts/batch_eval_runner.py
    python scripts/batch_eval_runner.py --mode verify
    python scripts/batch_eval_runner.py --mode override --out data/eval_override.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

from action_code_mapper import find_override_target_label  # noqa: E402
from graph import compile_graph  # noqa: E402


_FIELDS = [
    "case_id",
    "supervisor_mode",
    "supervisor_decision_type",
    "human_action_code",
    "agent_action_code",
    "oracle_action_code",
    "chosen_cost",
    "oracle_cost",
    "regret",
    "is_override",
    "is_unnecessary_override",
    "override_effectiveness",
    "override_target_label",
    "status",
    "skip_reason",
]


def _base_instruction(mode: str) -> dict:
    if mode == "approve":
        return {"mode": "approve"}
    if mode == "verify":
        return {"mode": "verify", "review_focus": "Batch replay verify."}
    if mode == "override":
        # Per-case target label is injected in build_rows(); this base stays empty
        # so a missing label is a hard, visible failure (not a silent collapse).
        return {"mode": "override"}
    raise SystemExit(f"Unknown mode: {mode}")


def _load_case(case_id: str) -> dict | None:
    path = _PROJECT_DIR / "data" / "cases" / f"{case_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _empty_row(case_id: str, mode: str) -> dict:
    return {k: None for k in _FIELDS} | {
        "case_id": case_id,
        "supervisor_mode": mode,
    }


def build_rows(mode: str, case_ids: list[str], graph=None) -> list[dict]:
    """Run the graph for each case and produce a list of CSV rows.

    For override mode, the per-case `alternative_plan` action_label is read
    from the case JSON and injected as target_action_label. Cases without an
    alternative_plan option are recorded as skipped — no silent mapping.
    """
    graph = graph or compile_graph()
    base = _base_instruction(mode)
    rows: list[dict] = []

    for case_id in case_ids:
        case = _load_case(case_id)
        if case is None:
            row = _empty_row(case_id, mode)
            row["status"] = "skipped"
            row["skip_reason"] = "case file not found"
            rows.append(row)
            continue

        instruction = dict(base)
        override_target = None
        if mode == "override":
            override_target = find_override_target_label(case)
            if not override_target:
                row = _empty_row(case_id, mode)
                row["status"] = "skipped"
                row["skip_reason"] = "no alternative_plan option in decision_options"
                rows.append(row)
                continue
            instruction["target_action_label"] = override_target

        try:
            result = graph.invoke({
                "case_id": case_id,
                "supervisor_instruction": instruction,
            })
            ev = result.get("evaluation_result", {}) or {}
            rows.append({
                "case_id": case_id,
                "supervisor_mode": mode,
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
                "override_target_label": override_target,
                "status": ev.get("status", "unknown"),
                "skip_reason": ev.get("reason") if ev.get("status") != "ok" else None,
            })
        except Exception as exc:  # pragma: no cover — batch resiliency only
            row = _empty_row(case_id, mode)
            row["status"] = "error"
            row["skip_reason"] = f"{type(exc).__name__}: {exc}"
            row["override_target_label"] = override_target
            rows.append(row)

    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="approve",
                    choices=["approve", "verify", "override"])
    ap.add_argument("--out", default=None,
                    help="Output CSV path (default: data/eval_<mode>.csv)")
    args = ap.parse_args()

    out_path = Path(args.out) if args.out else (
        _PROJECT_DIR / "data" / f"eval_{args.mode}.csv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cases_dir = _PROJECT_DIR / "data" / "cases"
    case_files = sorted(glob.glob(str(cases_dir / "*.json")))
    if not case_files:
        print(f"No cases found in {cases_dir}", file=sys.stderr)
        return 1
    case_ids = [Path(p).stem for p in case_files]

    rows = build_rows(args.mode, case_ids)

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in _FIELDS})

    n_ok = sum(1 for r in rows if r.get("status") == "ok")
    n_skip = sum(1 for r in rows if r.get("status") == "skipped")
    n_err = sum(1 for r in rows if r.get("status") == "error")
    print(f"Wrote {len(rows)} rows → {out_path}  "
          f"(ok={n_ok}, skipped={n_skip}, error={n_err})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
