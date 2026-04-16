"""Phase 6 tests — batch evaluation + observability runner.

All offline. Uses the compiled graph with the default "rules" modes so no
live API is required. Exercises a small subset of cases to keep runtime low.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

_PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))
sys.path.insert(0, str(_PROJECT_DIR / "scripts"))

phase6 = importlib.import_module("phase6_batch_eval")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SUBSET_CASES = ["M01", "M02"]


@pytest.fixture(scope="module")
def small_rows():
    return phase6.build_observability_rows(
        supervisor_modes=("approve", "verify", "override"),
        retrieval_modes=("tfidf_legacy", "hybrid"),
        case_ids=SUBSET_CASES,
        retrieval_k=3,
    )


# ---------------------------------------------------------------------------
# Core: runner executes offline
# ---------------------------------------------------------------------------

def test_runner_executes_offline_and_returns_rows(small_rows):
    # 2 cases × 3 supervisors × 2 retrievals = 12 rows
    assert len(small_rows) == 12
    for row in small_rows:
        # Every row must carry identity.
        assert row["case_id"] in SUBSET_CASES
        assert row["supervisor_mode"] in ("approve", "verify", "override")
        assert row["retrieval_mode"] in ("tfidf_legacy", "hybrid")
        assert row["operations_mode"] == "rules"
        assert row["governance_mode"] == "rules"
        assert row["status"] in ("ok", "skipped", "error")


# ---------------------------------------------------------------------------
# replay_id deterministic + stable
# ---------------------------------------------------------------------------

def test_replay_id_format_and_determinism():
    a = phase6._replay_id("M01", "approve", "hybrid", "rules", "rules")
    b = phase6._replay_id("M01", "approve", "hybrid", "rules", "rules")
    assert a == b
    assert re.fullmatch(r"rp_[0-9a-f]{12}", a)

    c = phase6._replay_id("M01", "verify", "hybrid", "rules", "rules")
    assert c != a


def test_replay_id_unique_per_row(small_rows):
    ids = [r["replay_id"] for r in small_rows]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Override rows use explicit target labels (Phase 1 discipline)
# ---------------------------------------------------------------------------

def test_override_rows_use_explicit_target_label(small_rows):
    override_rows = [r for r in small_rows if r["supervisor_mode"] == "override"]
    assert override_rows
    for r in override_rows:
        if r["status"] == "ok":
            assert r["override_target_label"], (
                "ok override row must carry a concrete target_action_label"
            )
        else:
            # Skipped override must have an explicit skip_reason.
            assert r["status"] == "skipped"
            assert r["skip_reason"]


# ---------------------------------------------------------------------------
# Retrieval observability fields populated when available
# ---------------------------------------------------------------------------

def test_retrieval_fields_present_for_ok_rows(small_rows):
    ok_rows = [r for r in small_rows if r["status"] == "ok"]
    assert ok_rows
    for r in ok_rows:
        # engine_mode should reflect the requested retrieval_mode family
        # (could be normalized — just assert presence).
        assert r["retrieval_engine_mode"] is not None
        assert r["retrieval_candidate_count"] is not None
        # These are tri-state booleans — must be one of {True, False}.
        assert r["retrieval_contextualized"] in (True, False)
        assert r["retrieval_reranker_used"] in (True, False)
        assert r["retrieval_fallback_used"] in (True, False)


def test_llm_trace_fields_are_none_in_rules_mode(small_rows):
    # rules mode ⇒ no LLM invoked, so llm_trace fields degrade to None.
    for r in small_rows:
        if r["status"] != "ok":
            continue
        assert r["ops_llm_fallback_used"] in (None, False)
        assert r["gov_llm_fallback_used"] in (None, False)


# ---------------------------------------------------------------------------
# Missing metadata degrades safely
# ---------------------------------------------------------------------------

def test_extract_helpers_handle_missing_meta():
    # Entirely absent meta.
    r = phase6._extract_retrieval_fields(None)
    assert all(v is None for v in r.values())

    l = phase6._extract_llm_trace(None, prefix="ops")
    assert set(l.keys()) == {
        "ops_llm_provider", "ops_llm_model",
        "ops_llm_attempts", "ops_llm_fallback_used",
    }
    assert all(v is None for v in l.values())

    # Meta present but with unrelated keys.
    r2 = phase6._extract_retrieval_fields({"foo": "bar"})
    assert all(v is None for v in r2.values())


def test_missing_case_becomes_skipped_row():
    rows = phase6.build_observability_rows(
        supervisor_modes=("approve",),
        retrieval_modes=("tfidf_legacy",),
        case_ids=["DOES_NOT_EXIST"],
        case_loader=lambda cid: None,
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "skipped"
    assert rows[0]["skip_reason"] == "case file not found"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def test_aggregate_report_shape(small_rows):
    agg = phase6.aggregate_report(small_rows)
    assert set(agg.keys()) == {
        "overall", "by_supervisor_mode", "by_retrieval_mode",
        "by_risk_level", "by_scenario_family",
    }
    for sup in ("approve", "verify", "override"):
        assert sup in agg["by_supervisor_mode"]
    for ret in ("tfidf_legacy", "hybrid"):
        assert ret in agg["by_retrieval_mode"]

    overall = agg["overall"]
    assert overall["n_total"] == len(small_rows)
    assert overall["n_ok"] + overall["n_skipped"] + overall["n_error"] <= overall["n_total"]


def test_aggregate_slice_metrics_keys(small_rows):
    agg = phase6.aggregate_report(small_rows)
    expected_keys = {
        "n_total", "n_ok", "n_skipped", "n_error",
        "mean_regret", "unnecessary_override_rate",
        "override_effectiveness_mean",
        "retrieval_fallback_count",
        "ops_llm_fallback_count", "gov_llm_fallback_count",
        "mean_latency_ms",
    }
    assert set(agg["overall"].keys()) == expected_keys
    for s in agg["by_supervisor_mode"].values():
        assert set(s.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Artifact emission
# ---------------------------------------------------------------------------

def test_write_rows_csv_and_summary_and_markdown(tmp_path, small_rows):
    agg = phase6.aggregate_report(small_rows)

    csv_path = tmp_path / "rows.csv"
    json_path = tmp_path / "summary.json"
    md_path = tmp_path / "report.md"

    phase6.write_rows_csv(small_rows, csv_path)
    phase6.write_summary_json(small_rows, agg, json_path)
    md = phase6.render_markdown(small_rows, agg)
    md_path.write_text(md)

    # CSV has header + one line per row.
    lines = csv_path.read_text().splitlines()
    assert lines[0].split(",")[0] == "replay_id"
    assert len(lines) == len(small_rows) + 1

    # JSON round-trips.
    data = json.loads(json_path.read_text())
    assert "rows" in data and "aggregations" in data
    assert len(data["rows"]) == len(small_rows)

    # Markdown has headings.
    assert "Phase 6 Batch Evaluation Report" in md
    assert "By supervisor mode" in md
    assert "By retrieval mode" in md


# ---------------------------------------------------------------------------
# Full matrix on 1 case — sanity
# ---------------------------------------------------------------------------

def test_full_matrix_on_single_case_runs():
    rows = phase6.build_observability_rows(case_ids=["M01"], retrieval_k=3)
    # 1 case × 3 supervisors × 3 retrievals = 9
    assert len(rows) == 9
    # All replay_ids unique.
    assert len({r["replay_id"] for r in rows}) == 9


# ---------------------------------------------------------------------------
# Regression — existing flows untouched
# ---------------------------------------------------------------------------

def test_scenario_family_normalization():
    assert phase6._scenario_family("Carrier Capacity Shortage") == "carrier"
    assert phase6._scenario_family("") == "unknown"
    assert phase6._scenario_family(None) == "unknown"
