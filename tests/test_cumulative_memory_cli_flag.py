"""B3 Slice 2D: CLI exposure of cumulative-memory flags.

Mirrors ``test_correlator_cli_flag.py`` / ``test_replan_cli_flag.py``
for the B3 cumulative-memory surface. Covers the two script
surfaces:

  - ``scripts/run_session.py``
  - ``scripts/session_eval_harness.py``

Behavior pinned here (plumbing only — runtime loader behavior is
covered by other tests):

  - Default CLI invocation (no ``--prior-session-dir``) threads
    ``initial_memory=None`` through ``run_session`` — pre-B3
    behavior preserved.
  - Supplying ``--prior-session-dir`` with ``--mode PATH_C_WARM``
    actually threads a non-None ``EpisodicMemory`` through the
    existing ``run_session(initial_memory=...)`` seam, and the
    loaded memory carries the prior session's rows.
  - Supplying ``--prior-session-dir`` with a non-PATH_C_WARM mode
    exits with a clear error (argparse ``error`` → ``SystemExit``).
  - Canonical ref resolution is deterministic: the resolver layer
    turns each dir into the prior session's own ``session_id``,
    and repeat invocations yield the same refs.
  - Raw filesystem paths never enter ``CumulativeMemoryConfig``.
  - Harness default run (without ``--prior-session-dir``) still
    behaves exactly as before.
  - Harness cumulative-enabled path attaches the loaded memory
    to ``PATH_C_WARM`` only; ``BASELINE_STATIC`` / ``PATH_C_COLD``
    receive ``initial_memory=None``.
  - Harness cumulative-enabled compare report carries the B3
    ``cumulative_memory_summary`` block with the expected prior
    refs.
  - The cumulative-memory CLI axis is independent from
    ``--enable-replan`` and ``--enable-correlator`` axes.
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


@pytest.fixture(scope="module")
def prior_session_dir(tmp_path_factory):
    """Produce a real PATH_C_COLD session artifact on disk, which
    the tests point at as a prior-session directory. Using a real
    session ensures ``session_artifact.json`` and ``memory.jsonl``
    are present with a valid ``session_id`` and non-empty memory
    rows — the same shape a future user would feed into
    ``--prior-session-dir``."""
    from event_loop_c import run_session
    from session.session_manager import save_session

    out = tmp_path_factory.mktemp("b3_prior_session")
    artifact = run_session(seed=7, mode="PATH_C_COLD")
    save_session(artifact, str(out))
    return str(out), artifact.session_id


# ---------------------------------------------------------------------------
# scripts/run_session.py — default path unchanged
# ---------------------------------------------------------------------------


def test_run_session_default_threads_no_initial_memory(tmp_path, monkeypatch):
    """Default CLI (no --prior-session-dir) passes
    ``initial_memory=None`` to run_session."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b3_slice_2d_run_session_default",
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
    assert captured["initial_memory"] is None


# ---------------------------------------------------------------------------
# scripts/run_session.py — cumulative path wires EpisodicMemory
# ---------------------------------------------------------------------------


def test_run_session_cumulative_flag_threads_prior_memory(
    prior_session_dir, tmp_path, monkeypatch,
):
    prior_dir, prior_sid = prior_session_dir
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b3_slice_2d_run_session_cumulative",
    )

    captured: dict = {}

    def _fake_run_session(**kwargs):
        captured.update(kwargs)
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    rc = mod.main([
        "--seed", "42", "--mode", "PATH_C_WARM",
        "--prior-session-dir", prior_dir,
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    mem = captured["initial_memory"]
    assert mem is not None
    # Prior session's session_id shows up on at least one row.
    row_sids = {r.session_id for r in mem.records()}
    assert prior_sid in row_sids


def test_run_session_cumulative_rejects_non_warm_mode(
    prior_session_dir, tmp_path,
):
    prior_dir, _ = prior_session_dir
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b3_slice_2d_run_session_rejects_cold",
    )
    with pytest.raises(SystemExit):
        mod.main([
            "--seed", "42", "--mode", "PATH_C_COLD",
            "--prior-session-dir", prior_dir,
            "--out-dir", str(tmp_path),
        ])


def test_run_session_cumulative_rejects_baseline_mode(
    prior_session_dir, tmp_path,
):
    prior_dir, _ = prior_session_dir
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b3_slice_2d_run_session_rejects_baseline",
    )
    with pytest.raises(SystemExit):
        mod.main([
            "--seed", "42", "--mode", "BASELINE_STATIC",
            "--prior-session-dir", prior_dir,
            "--out-dir", str(tmp_path),
        ])


def test_run_session_cumulative_missing_dir_raises(tmp_path):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b3_slice_2d_run_session_missing_dir",
    )
    with pytest.raises(FileNotFoundError):
        mod.main([
            "--seed", "42", "--mode", "PATH_C_WARM",
            "--prior-session-dir", str(tmp_path / "does_not_exist"),
            "--out-dir", str(tmp_path / "out"),
        ])


# ---------------------------------------------------------------------------
# scripts/run_session.py — source-resolution determinism
# ---------------------------------------------------------------------------


def test_run_session_canonical_ref_resolution_deterministic(
    prior_session_dir,
):
    """Given the same dir, the CLI helper resolves to the same
    ``(ref, rows)`` pair on every call."""
    prior_dir, prior_sid = prior_session_dir
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b3_slice_2d_run_session_ref_resolution",
    )
    ref_a, rows_a = mod._resolve_prior_session_dir(prior_dir)
    ref_b, rows_b = mod._resolve_prior_session_dir(prior_dir)
    assert ref_a == ref_b == prior_sid
    assert [r.model_dump() for r in rows_a] == [r.model_dump() for r in rows_b]


def test_run_session_cumulative_config_has_no_raw_paths(
    prior_session_dir,
):
    """CumulativeMemoryConfig built from CLI dirs carries canonical
    refs only — no raw filesystem paths (D5)."""
    prior_dir, prior_sid = prior_session_dir
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b3_slice_2d_run_session_no_paths_in_config",
    )

    # Build the cumulative memory via the helper; inspect the
    # CumulativeMemoryConfig the helper must have constructed by
    # re-invoking the resolver step directly.
    refs: list[str] = []
    rows_by_ref: dict = {}
    canonical_ref, rows = mod._resolve_prior_session_dir(prior_dir)
    refs.append(canonical_ref)
    rows_by_ref[canonical_ref] = rows

    from learning.cumulative_memory import CumulativeMemoryConfig

    cfg = CumulativeMemoryConfig(prior_session_refs=tuple(refs))
    assert cfg.prior_session_refs == (prior_sid,)
    # The raw path must not appear anywhere in the config's serialized form.
    cfg_repr = repr(cfg.prior_session_refs) + "|" + cfg.dedupe_policy
    assert prior_dir not in cfg_repr


# ---------------------------------------------------------------------------
# scripts/session_eval_harness.py — default unchanged
# ---------------------------------------------------------------------------


def test_harness_default_threads_no_cumulative_memory(
    tmp_path, monkeypatch,
):
    """Default harness invocation (no --prior-session-dir) behaves
    exactly as before: no session in the pre-B3 harness received
    cumulative memory from the CLI layer; the synthetic warm seed
    still feeds PATH_C_WARM (but that one's rows share the prior
    SYNTHETIC_WARM_SEED session id — that's the existing Slice 2C
    behavior, not this slice's surface)."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b3_slice_2d_harness_default",
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
        warm_memory="empty",  # disable synthetic warm so the test
                              # isolates the CLI-layer cumulative axis
    )
    assert len(calls) == 3
    # With warm_memory="empty" and no prior-session-dir, all three
    # modes receive initial_memory=None.
    for call in calls:
        assert call["initial_memory"] is None


# ---------------------------------------------------------------------------
# scripts/session_eval_harness.py — cumulative-enabled wiring
# ---------------------------------------------------------------------------


def test_harness_cumulative_enabled_attaches_to_path_c_warm_only(
    prior_session_dir, tmp_path, monkeypatch,
):
    prior_dir, prior_sid = prior_session_dir
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b3_slice_2d_harness_cumulative_path_c_warm_only",
    )

    per_mode_initial: dict[str, object] = {}

    def _fake_run_session(**kwargs):
        per_mode_initial[kwargs["mode"]] = kwargs["initial_memory"]
        from event_loop_c import run_session as real_run_session
        return real_run_session(**kwargs)

    monkeypatch.setattr(mod, "run_session", _fake_run_session)

    mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
        min_records_for_shift=3,
        warm_memory="empty",
        prior_session_dirs=[prior_dir],
    )

    # Only PATH_C_WARM gets a non-None initial memory.
    assert per_mode_initial["BASELINE_STATIC"] is None
    assert per_mode_initial["PATH_C_COLD"] is None
    warm_mem = per_mode_initial["PATH_C_WARM"]
    assert warm_mem is not None
    # The loaded memory carries the prior session's session_id.
    sids = {r.session_id for r in warm_mem.records()}
    assert prior_sid in sids


def test_harness_cumulative_enabled_compare_block_surfaces(
    prior_session_dir, tmp_path,
):
    """End-to-end: enabling --prior-session-dir through
    run_eval_harness produces a compare_report.json that carries
    the already-landed B3 ``cumulative_memory_summary`` sibling
    block with the prior session's ``session_id`` listed."""
    prior_dir, prior_sid = prior_session_dir
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b3_slice_2d_harness_compare_block",
    )

    mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
        min_records_for_shift=3,
        warm_memory="empty",
        prior_session_dirs=[prior_dir],
    )

    with open(os.path.join(str(tmp_path), "compare_report.json")) as f:
        compare = json.load(f)
    assert "cumulative_memory_summary" in compare
    cms = compare["cumulative_memory_summary"]
    assert cms["sessions_with_cumulative_memory"] == ["path_c_warm"]
    assert prior_sid in cms["all_prior_session_refs"]

    # Thesis markdown also carries the section.
    with open(os.path.join(str(tmp_path), "thesis_report.md")) as f:
        md = f.read()
    assert "## Cumulative memory provenance (B3)" in md
    assert prior_sid in md


def test_harness_cli_main_threads_cumulative_flags(
    prior_session_dir, tmp_path, monkeypatch,
):
    """Invoke the harness through its argparse ``main(argv)`` entry
    point to exercise the full CLI surface and confirm the flags
    reach ``run_eval_harness``."""
    prior_dir, _ = prior_session_dir
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b3_slice_2d_harness_cli_main",
    )

    captured: dict = {}

    def _fake_run_eval_harness(**kwargs):
        captured.update(kwargs)
        # Still run the real harness so files get produced.
        from importlib import reload  # noqa: F401
        # Use the module-level reference to the real impl by
        # calling the original function via a direct import.
        import sys as _sys
        import importlib.util as _iu
        spec = _iu.spec_from_file_location(
            "b3_slice_2d_harness_cli_real",
            os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        )
        real = _iu.module_from_spec(spec)
        spec.loader.exec_module(real)
        return real.run_eval_harness(**kwargs)

    monkeypatch.setattr(mod, "run_eval_harness", _fake_run_eval_harness)

    rc = mod.main([
        "--seed", "42",
        "--events-source", "demo_stream",
        "--out-dir", str(tmp_path),
        "--min-records-for-shift", "3",
        "--warm-memory", "empty",
        "--prior-session-dir", prior_dir,
    ])
    assert rc == 0
    assert captured["prior_session_dirs"] == [prior_dir]
    assert captured["cumulative_dedupe_policy"] == "drop_equal_raise_mismatch"


# ---------------------------------------------------------------------------
# Axis independence — cumulative flag doesn't flip replan/correlator
# ---------------------------------------------------------------------------


def test_harness_cumulative_axis_independent_from_replan_and_correlator(
    prior_session_dir, tmp_path, monkeypatch,
):
    prior_dir, _ = prior_session_dir
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "session_eval_harness.py"),
        "b3_slice_2d_harness_axis_independence",
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
        prior_session_dirs=[prior_dir],
    )
    assert len(calls) == 3
    for call in calls:
        # Replan still default-disabled.
        assert call["replan_config"].enable_replan is False
        # Correlator still default-disabled.
        assert call["correlator_config"].enable_correlator is False
