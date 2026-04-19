"""B1 closeout: CLI exposure of ``--enable-replan``.

Covers the two script surfaces that already existed before B1:

  - ``scripts/run_session.py``
  - ``scripts/session_eval_harness.py``

Only behavior worth pinning here is:

  - Default CLI invocation (no ``--enable-replan``) uses the default
    ``ReplanConfig()`` via the normal ``run_session`` signature —
    i.e. behavior is identical to pre-B1 for the scripts.
  - ``--enable-replan`` flips ``ReplanConfig.enable_replan=True`` and
    the flag is threaded through ``run_session``.
  - The harness's ``run_eval_harness(enable_replan=True)`` path
    actually materializes a ``replan_trace_summary`` block in the
    compare_report (smoke check — full compare / report semantics
    are covered in Slice 4 tests).

No new runtime behavior is introduced by this patch; these tests
just guard that the plumbing is wired.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
_SCRIPTS_DIR = os.path.join(_PROJECT_DIR, "scripts")
for _p in (_SRC_DIR, _PROJECT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# run_session.py / session_eval_harness.py are under scripts/. They
# don't expose an importable package, so we run them via subprocess
# only when we need end-to-end coverage. For the plumbing-wiring
# tests we import their `main` callables via importlib.
import importlib.util  # noqa: E402


def _load_script(path: str, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


# ---------------------------------------------------------------------------
# scripts/run_session.py plumbing
# ---------------------------------------------------------------------------


def test_run_session_default_passes_replan_disabled(tmp_path, monkeypatch):
    """Default CLI (no --enable-replan) passes a ReplanConfig with
    enable_replan=False into run_session."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b1_closeout_run_session",
    )

    captured: dict = {}

    def _fake_run_session(**kwargs):
        captured.update(kwargs)
        # Return a minimal, well-formed artifact.
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    rc = mod.main([
        "--seed", "42", "--mode", "BASELINE_STATIC",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    replan_config = captured["replan_config"]
    assert replan_config.enable_replan is False


def test_run_session_flag_enables_replan(tmp_path, monkeypatch):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b1_closeout_run_session_flag",
    )

    captured: dict = {}

    def _fake_run_session(**kwargs):
        captured.update(kwargs)
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    rc = mod.main([
        "--seed", "42", "--mode", "PATH_C_COLD",
        "--enable-replan",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    assert captured["replan_config"].enable_replan is True


# ---------------------------------------------------------------------------
# scripts/session_eval_harness.py plumbing
# ---------------------------------------------------------------------------


def test_harness_default_is_replan_disabled(tmp_path, monkeypatch):
    """Default harness invocation threads ReplanConfig(enable_replan=False)
    through every run_session call."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b1_closeout_harness_default",
    )

    calls: list[dict] = []

    def _fake_run_session(**kwargs):
        calls.append(kwargs)
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    # n_synthetic_records=0 keeps the warm-memory seed small/empty;
    # the harness still runs all three modes.
    mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
        min_records_for_shift=3,
        warm_memory="empty",
    )
    assert len(calls) == 3  # BASELINE_STATIC, PATH_C_COLD, PATH_C_WARM
    for call in calls:
        assert call["replan_config"].enable_replan is False

    # compare_report must not carry replan_trace_summary by default.
    with open(tmp_path / "compare_report.json") as f:
        compare = json.load(f)
    assert "replan_trace_summary" not in compare


def test_harness_enable_replan_adds_replan_trace_summary(tmp_path, monkeypatch):
    """--enable-replan through run_eval_harness threads
    ReplanConfig(enable_replan=True) AND the compare_report gains
    the replan_trace_summary block when any trace materializes."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b1_closeout_harness_enabled",
    )

    # Force the trigger to fire on every attempt-0 so every PATH_C_*
    # event materializes a trace; BASELINE_STATIC is unaffected.
    from replan.replan_schema import ReplanTriggerRecord

    def _force(*, expected_outcome, execution_status, execution_outcome,
               attempt_index, config):
        if attempt_index == 0:
            return ReplanTriggerRecord(
                trigger_rule_id="cost_deviation_v1",
                trigger_type="COST_DEVIATION",
                attempt_index=0,
                deviation_measurement={
                    "realized_cost": 500.0,
                    "absolute_delta": 400.0,
                    "relative_delta": 3.0,
                },
                expected_outcome_ref=expected_outcome,
            )
        return ReplanTriggerRecord(
            trigger_rule_id="no_trigger_v1",
            trigger_type="NO_TRIGGER",
            attempt_index=attempt_index,
            deviation_measurement={},
            expected_outcome_ref=expected_outcome,
        )

    monkeypatch.setattr(
        "replan.replan_orchestrator.decide_replan_trigger", _force,
    )

    calls: list[dict] = []

    def _fake_run_session(**kwargs):
        calls.append(kwargs)
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
        min_records_for_shift=3,
        warm_memory="empty",
        enable_replan=True,
    )
    assert len(calls) == 3
    for call in calls:
        assert call["replan_config"].enable_replan is True

    with open(tmp_path / "compare_report.json") as f:
        compare = json.load(f)
    assert "replan_trace_summary" in compare
    # Thesis markdown should now carry the bounded-replan section.
    with open(tmp_path / "thesis_report.md") as f:
        md = f.read()
    assert "Bounded-replan behavior (B1)" in md


# ---------------------------------------------------------------------------
# Version constants landed per closeout patch
# ---------------------------------------------------------------------------


def test_kpi_and_compare_report_versions_are_bumped():
    from session.kpi_calculator import KPI_REPORT_SCHEMA_VERSION
    from session.session_compare import COMPARE_REPORT_SCHEMA_VERSION

    assert KPI_REPORT_SCHEMA_VERSION == "1.1"
    assert COMPARE_REPORT_SCHEMA_VERSION == "1.1"


def test_schema_versions_registers_replan_components():
    from event_loop_c import _SCHEMA_VERSIONS

    for key in (
        "expected_outcome_ref",
        "replan_trigger_record",
        "replan_attempt_record",
        "replan_config",
    ):
        assert key in _SCHEMA_VERSIONS, (
            f"_SCHEMA_VERSIONS missing replan component key {key!r}"
        )
    # Existing keys remain present — no regression on the pre-B1 set.
    for key in (
        "session_artifact", "session_config",
        "session_event_record", "session_kpis",
    ):
        assert key in _SCHEMA_VERSIONS
