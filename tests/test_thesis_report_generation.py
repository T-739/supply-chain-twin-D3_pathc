"""Phase 3: thesis_report.md structural tests.

Asserts the thesis markdown carries the required structural sections,
uses concrete numeric values drawn from the compare report, and is
deterministically generated from a fixed-seed harness run.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


def _sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@pytest.fixture(scope="module")
def harness_out(tmp_path_factory):
    sys.path.insert(0, _PROJECT_DIR)
    try:
        from scripts.session_eval_harness import run_eval_harness
        out = tmp_path_factory.mktemp("phase3_out")
        run_eval_harness(
            seed=42,
            events_source="demo_stream",
            out_dir=str(out),
            min_records_for_shift=3,
            warm_memory="synthetic",
            n_synthetic_records=10,
        )
        yield out
    finally:
        if _PROJECT_DIR in sys.path:
            sys.path.remove(_PROJECT_DIR)


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestMarkdownSections:
    def test_contains_three_kpi_tables(self, harness_out):
        md = _read(os.path.join(str(harness_out), "thesis_report.md"))
        assert "## Overall KPIs" in md
        assert "## Cold-phase KPIs" in md
        assert "## Warm-phase KPIs" in md
        # Each table has a header row with the three mode column names.
        for mode in ("baseline_static", "path_c_cold", "path_c_warm"):
            assert mode in md, f"mode column {mode!r} missing in thesis report"

    def test_contains_deltas_section(self, harness_out):
        md = _read(os.path.join(str(harness_out), "thesis_report.md"))
        assert "## Deltas vs baseline" in md
        # At least one non-baseline delta block present
        assert "path_c_cold_minus_baseline_static" in md
        assert "path_c_warm_minus_baseline_static" in md

    def test_contains_diverged_events_section(self, harness_out):
        md = _read(os.path.join(str(harness_out), "thesis_report.md"))
        assert "## Diverged events" in md

    def test_contains_thesis_paragraph_with_concrete_numbers(self, harness_out):
        md = _read(os.path.join(str(harness_out), "thesis_report.md"))
        assert "## Relation to calibrated supervision thesis" in md
        assert "warm_calibrated_autonomy_delta" in md
        assert "warm_sla_preservation_delta" in md
        assert "warm_cost_delta" in md
        assert "supports_claim" in md
        # At least one numeric value (digit) appears in the thesis block
        thesis_idx = md.index("## Relation to calibrated supervision thesis")
        block = md[thesis_idx:]
        assert re.search(r"[0-9]", block), (
            "thesis paragraph must contain concrete numeric values"
        )


class TestReportContentMatchesCompareReport:
    def test_thesis_numbers_come_from_compare_report(self, harness_out):
        compare = json.loads(
            _read(os.path.join(str(harness_out), "compare_report.json"))
        )
        md = _read(os.path.join(str(harness_out), "thesis_report.md"))
        thesis = compare["thesis_claim_support"]

        # If warm_calibrated_autonomy_delta is numeric, its formatted form
        # (4-decimal string from _fmt) must appear in the md block.
        cas_delta = thesis["warm_calibrated_autonomy_delta"]
        if isinstance(cas_delta, (int, float)):
            assert f"{float(cas_delta):.4f}" in md

    def test_diverged_event_ids_appear_if_any(self, harness_out):
        compare = json.loads(
            _read(os.path.join(str(harness_out), "compare_report.json"))
        )
        md = _read(os.path.join(str(harness_out), "thesis_report.md"))
        for d in compare["diverged_events"]:
            eid = d.get("event_id")
            if eid:
                assert eid in md, (
                    f"diverged event_id {eid!r} missing from thesis report"
                )


class TestHarnessArtifactSet:
    def test_produces_three_session_artifacts_and_memories(self, harness_out):
        root = str(harness_out)
        for sub in ("baseline_static", "path_c_cold", "path_c_warm"):
            assert os.path.exists(os.path.join(root, sub, "session_artifact.json"))
            assert os.path.exists(os.path.join(root, sub, "memory.jsonl"))
        assert os.path.exists(os.path.join(root, "compare_report.json"))
        assert os.path.exists(os.path.join(root, "thesis_report.md"))


class TestCorrelatorAbsenceRegressionPin:
    """B2 Slice 2C regression pin: the default harness does NOT
    enable the correlator, so the compare report must not carry a
    ``correlation_summary`` block and the thesis markdown must not
    render a correlation section. If this test later fails, the
    harness default changed — check ``scripts/session_eval_harness``
    and the Slice 2C decision that the CLI/harness surface stays
    unchanged."""

    def test_compare_report_has_no_correlation_summary(self, harness_out):
        compare = json.loads(
            _read(os.path.join(str(harness_out), "compare_report.json"))
        )
        assert "correlation_summary" not in compare

    def test_thesis_report_has_no_correlation_section(self, harness_out):
        md = _read(os.path.join(str(harness_out), "thesis_report.md"))
        assert "Correlation observations" not in md
        assert "ETA_PATH_COMPOUND" not in md
        assert "CARRIER_DOUBLE_HIT" not in md


class TestCumulativeMemoryPresenceRegressionPin:
    """B3 Slice 2C regression pin: the default harness attaches
    the synthetic warm-seed memory to the ``PATH_C_WARM`` run
    (``_build_synthetic_warm_memory``), whose rows carry
    ``session_id="SYNTHETIC_WARM_SEED"``. That differs from the
    warm run's own ``session_id``, so by the Slice 2C definition
    the run has cumulative memory. This pin locks that the
    compare report honestly reports:

      - ``cumulative_memory_summary`` is present,
      - only ``path_c_warm`` is listed in
        ``sessions_with_cumulative_memory``,
      - ``SYNTHETIC_WARM_SEED`` is the prior session id.

    Pre-B3 compares (before this slice) did not emit the block;
    the additive visibility is a legitimate behavioral change
    because the data was always there — B3 Slice 2C just
    surfaces it."""

    def test_compare_report_has_cumulative_memory_summary(
        self, harness_out,
    ):
        compare = json.loads(
            _read(os.path.join(str(harness_out), "compare_report.json"))
        )
        assert "cumulative_memory_summary" in compare
        cms = compare["cumulative_memory_summary"]
        # Only PATH_C_WARM received the synthetic warm seed.
        assert cms["sessions_with_cumulative_memory"] == ["path_c_warm"]
        assert "SYNTHETIC_WARM_SEED" in cms["all_prior_session_refs"]
        # Synthetic-warm row count is > 0 (harness default is
        # n_synthetic_records=10).
        assert (
            cms["overall_rows_by_prior_session"].get(
                "SYNTHETIC_WARM_SEED", 0,
            )
            > 0
        )

    def test_thesis_report_has_cumulative_section(self, harness_out):
        md = _read(os.path.join(str(harness_out), "thesis_report.md"))
        assert "## Cumulative memory provenance (B3)" in md
        assert "SYNTHETIC_WARM_SEED" in md

    def test_baseline_and_cold_are_not_listed_as_cumulative(
        self, harness_out,
    ):
        """BASELINE_STATIC and PATH_C_COLD do not receive
        initial_memory — they must NOT appear as sessions with
        cumulative memory in the block."""
        compare = json.loads(
            _read(os.path.join(str(harness_out), "compare_report.json"))
        )
        cms = compare["cumulative_memory_summary"]
        assert "baseline_static" not in cms["per_session"]
        assert "path_c_cold" not in cms["per_session"]


class TestReportReproducibleUnderFixedSeed:
    def test_two_runs_produce_byte_identical_thesis(self, tmp_path):
        sys.path.insert(0, _PROJECT_DIR)
        try:
            from scripts.session_eval_harness import run_eval_harness
            hashes = []
            for i in range(2):
                out = tmp_path / f"run_{i}"
                run_eval_harness(
                    seed=42,
                    events_source="demo_stream",
                    out_dir=str(out),
                    min_records_for_shift=3,
                    warm_memory="synthetic",
                    n_synthetic_records=10,
                )
                hashes.append(
                    _sha(os.path.join(str(out), "thesis_report.md"))
                )
            assert hashes[0] == hashes[1]
        finally:
            if _PROJECT_DIR in sys.path:
                sys.path.remove(_PROJECT_DIR)
