"""B2 Slice 2D: CLI exposure of correlator flags.

Mirrors ``test_replan_cli_flag.py`` for the correlator surface.
Covers the two script surfaces:

  - ``scripts/run_session.py``
  - ``scripts/session_eval_harness.py``

Behavior pinned here (plumbing only — runtime correlator behavior
is covered by other tests):

  - Default CLI invocation (no ``--enable-correlator``) threads a
    ``CorrelatorConfig(enable_correlator=False)`` through
    ``run_session``.
  - ``--enable-correlator`` flips ``enable_correlator=True``.
  - ``--correlator-window-size N`` is threaded through.
  - ``--correlator-pattern`` (repeatable) narrows
    ``enabled_patterns`` to the provided subset; absent flag keeps
    the default ``KNOWN_CORRELATOR_PATTERN_IDS``.
  - Unknown pattern ids are rejected by argparse ``choices=``.
  - Harness default run produces a compare_report WITHOUT a
    ``correlation_summary`` block.
  - Harness ``enable_correlator=True`` produces a compare_report
    WITH a ``correlation_summary`` block (the default demo stream
    fires P1 at event index 1, so correlation data is guaranteed
    to be present).
  - Unrelated replan / adaptive plumbing is unaffected.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
_SCRIPTS_DIR = os.path.join(_PROJECT_DIR, "scripts")
for _p in (_SRC_DIR, _PROJECT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


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
# scripts/run_session.py — correlator plumbing
# ---------------------------------------------------------------------------


def test_run_session_default_passes_correlator_disabled(tmp_path, monkeypatch):
    """Default CLI (no --enable-correlator) passes a CorrelatorConfig
    with enable_correlator=False into run_session."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b2_slice_2d_run_session_default",
    )

    captured: dict = {}

    def _fake_run_session(**kwargs):
        captured.update(kwargs)
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    rc = mod.main([
        "--seed", "42", "--mode", "BASELINE_STATIC",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    corr = captured["correlator_config"]
    assert corr.enable_correlator is False
    # And the unrelated replan surface still defaults to disabled.
    assert captured["replan_config"].enable_replan is False


def test_run_session_flag_enables_correlator(tmp_path, monkeypatch):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b2_slice_2d_run_session_on",
    )

    captured: dict = {}

    def _fake_run_session(**kwargs):
        captured.update(kwargs)
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    rc = mod.main([
        "--seed", "42", "--mode", "PATH_C_COLD",
        "--enable-correlator",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    corr = captured["correlator_config"]
    assert corr.enable_correlator is True
    # Window-size default matches the CorrelatorConfig default.
    from correlator.correlator_config import CorrelatorConfig
    assert corr.window_size == CorrelatorConfig().window_size
    # Patterns default to the full known set when no --correlator-pattern is given.
    from correlator.correlator_config import KNOWN_CORRELATOR_PATTERN_IDS
    assert corr.enabled_patterns == KNOWN_CORRELATOR_PATTERN_IDS


def test_run_session_correlator_window_size_flag_threaded(tmp_path, monkeypatch):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b2_slice_2d_run_session_window_size",
    )

    captured: dict = {}

    def _fake_run_session(**kwargs):
        captured.update(kwargs)
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    rc = mod.main([
        "--seed", "42", "--mode", "BASELINE_STATIC",
        "--enable-correlator",
        "--correlator-window-size", "5",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    assert captured["correlator_config"].window_size == 5


def test_run_session_correlator_pattern_flag_narrows_subset(
    tmp_path, monkeypatch,
):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b2_slice_2d_run_session_pattern_subset",
    )

    captured: dict = {}

    def _fake_run_session(**kwargs):
        captured.update(kwargs)
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    rc = mod.main([
        "--seed", "42", "--mode", "BASELINE_STATIC",
        "--enable-correlator",
        "--correlator-pattern", "ETA_PATH_COMPOUND",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    assert captured["correlator_config"].enabled_patterns == frozenset(
        {"ETA_PATH_COMPOUND"}
    )


def test_run_session_rejects_unknown_pattern_id(tmp_path):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b2_slice_2d_run_session_bad_pattern",
    )
    with pytest.raises(SystemExit):
        mod.main([
            "--seed", "42", "--mode", "BASELINE_STATIC",
            "--enable-correlator",
            "--correlator-pattern", "NOT_A_PATTERN",
            "--out-dir", str(tmp_path),
        ])


def test_run_session_disabled_plumbing_ignores_window_and_pattern_flags(
    tmp_path, monkeypatch,
):
    """When --enable-correlator is NOT set, window-size and pattern
    flags on the CLI must NOT flip the correlator on. The resulting
    CorrelatorConfig is the plain default — byte-identity with
    pre-B2 runs is preserved."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b2_slice_2d_run_session_disabled_ignores_flags",
    )

    captured: dict = {}

    def _fake_run_session(**kwargs):
        captured.update(kwargs)
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    rc = mod.main([
        "--seed", "42", "--mode", "BASELINE_STATIC",
        "--correlator-window-size", "5",
        "--correlator-pattern", "ETA_PATH_COMPOUND",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    from correlator.correlator_config import CorrelatorConfig
    assert captured["correlator_config"] == CorrelatorConfig()


# ---------------------------------------------------------------------------
# scripts/session_eval_harness.py — correlator plumbing
# ---------------------------------------------------------------------------


def test_harness_default_is_correlator_disabled(tmp_path, monkeypatch):
    """Default harness invocation threads
    CorrelatorConfig(enable_correlator=False) through every
    run_session call and the compare_report omits
    ``correlation_summary``."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b2_slice_2d_harness_default",
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
    )
    assert len(calls) == 3
    for call in calls:
        assert call["correlator_config"].enable_correlator is False

    # compare_report must not carry correlation_summary by default.
    with open(tmp_path / "compare_report.json") as f:
        compare = json.load(f)
    assert "correlation_summary" not in compare


def test_harness_enable_correlator_adds_correlation_summary(
    tmp_path, monkeypatch,
):
    """``enable_correlator=True`` through run_eval_harness threads
    CorrelatorConfig(enable_correlator=True) AND the compare_report
    gains the correlation_summary block. The default demo event
    stream includes a CARRIER_DELAY_ESCALATION + WEATHER_WORSENING
    adjacency at ordinals 0, 1 so P1 is guaranteed to fire."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b2_slice_2d_harness_enabled",
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
        enable_correlator=True,
        correlator_window_size=3,
    )
    assert len(calls) == 3
    for call in calls:
        assert call["correlator_config"].enable_correlator is True
        assert call["correlator_config"].window_size == 3

    with open(tmp_path / "compare_report.json") as f:
        compare = json.load(f)
    assert "correlation_summary" in compare
    cs = compare["correlation_summary"]
    # All three modes run with correlator_config — all three should
    # have correlation data (even if only "ran-but-empty" context).
    assert set(cs["sessions_with_correlation_data"]) == {
        "baseline_static", "path_c_cold", "path_c_warm",
    }
    # P1 ETA_PATH_COMPOUND fires on the default demo stream.
    assert cs["overall_pattern_counts"].get("ETA_PATH_COMPOUND", 0) > 0

    # Thesis markdown should now carry the correlation section.
    with open(tmp_path / "thesis_report.md") as f:
        md = f.read()
    assert "## Correlation observations (B2)" in md


def test_harness_cli_main_threads_correlator_flags(tmp_path, monkeypatch):
    """Invoke the harness through its argparse ``main(argv)`` entry
    point to exercise the full CLI surface (not just the Python
    kwargs), and confirm the flags reach CorrelatorConfig."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b2_slice_2d_harness_main_cli",
    )

    calls: list[dict] = []

    def _fake_run_session(**kwargs):
        calls.append(kwargs)
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    rc = mod.main([
        "--seed", "42",
        "--events-source", "demo_stream",
        "--out-dir", str(tmp_path),
        "--min-records-for-shift", "3",
        "--warm-memory", "empty",
        "--enable-correlator",
        "--correlator-window-size", "4",
        "--correlator-pattern", "ETA_PATH_COMPOUND",
    ])
    assert rc == 0
    assert len(calls) == 3
    for call in calls:
        corr = call["correlator_config"]
        assert corr.enable_correlator is True
        assert corr.window_size == 4
        assert corr.enabled_patterns == frozenset({"ETA_PATH_COMPOUND"})


def test_harness_default_still_omits_correlation_summary_with_replan_enabled(
    tmp_path, monkeypatch,
):
    """Regression pin: enabling the replan flag alone must NOT
    accidentally turn on the correlator. This pins the independence
    of the two additive CLI axes."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b2_slice_2d_harness_replan_only",
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
        assert call["correlator_config"].enable_correlator is False

    with open(tmp_path / "compare_report.json") as f:
        compare = json.load(f)
    assert "correlation_summary" not in compare
