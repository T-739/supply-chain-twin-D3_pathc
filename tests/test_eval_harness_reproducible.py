"""Phase 3: session_eval_harness byte-reproducibility tests.

Same seed, same inputs, fresh runs, independent subprocesses — all
produced artifacts must be byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
_SCRIPTS_DIR = os.path.join(_PROJECT_DIR, "scripts")
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


def _run_harness_in_process(out_dir: str, **kwargs) -> None:
    from scripts.session_eval_harness import run_eval_harness
    run_eval_harness(out_dir=out_dir, **kwargs)


def _all_output_files(out_dir: str) -> list[str]:
    files: list[str] = []
    for dirpath, _dirs, names in os.walk(out_dir):
        for name in sorted(names):
            files.append(os.path.relpath(os.path.join(dirpath, name), out_dir))
    return sorted(files)


def test_harness_in_process_deterministic(tmp_path):
    """Two in-process harness runs with the same inputs → identical file bytes."""
    # Inject scripts dir for the import (so `scripts.session_eval_harness` works)
    sys.path.insert(0, _PROJECT_DIR)
    try:
        a = tmp_path / "run_a"
        b = tmp_path / "run_b"
        for p in (a, b):
            _run_harness_in_process(
                str(p),
                seed=42,
                events_source="demo_stream",
                min_records_for_shift=3,
                warm_memory="synthetic",
                n_synthetic_records=10,
            )

        files_a = _all_output_files(str(a))
        files_b = _all_output_files(str(b))
        assert files_a == files_b

        for rel in files_a:
            ha = _sha(os.path.join(str(a), rel))
            hb = _sha(os.path.join(str(b), rel))
            assert ha == hb, f"{rel} differs: {ha} vs {hb}"
    finally:
        if _PROJECT_DIR in sys.path:
            sys.path.remove(_PROJECT_DIR)


def test_harness_fresh_subprocess_deterministic(tmp_path):
    """Two fresh Python subprocesses with PYTHONHASHSEED stripped →
    identical compare_report.json and thesis_report.md bytes."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}

    sub = r"""
import sys
sys.path.insert(0, {proj!r})
from scripts.session_eval_harness import run_eval_harness
run_eval_harness(
    seed=42,
    events_source='demo_stream',
    out_dir={out!r},
    min_records_for_shift=3,
    warm_memory='synthetic',
    n_synthetic_records=10,
)
"""

    hashes: list[dict[str, str]] = []
    for i in range(2):
        out_dir = tmp_path / f"sub_{i}"
        out_dir.mkdir()
        proc = subprocess.run(
            [sys.executable, "-c", sub.format(proj=_PROJECT_DIR, out=str(out_dir))],
            capture_output=True, text=True, env=env, cwd=_PROJECT_DIR,
        )
        assert proc.returncode == 0, proc.stderr
        compare = os.path.join(str(out_dir), "compare_report.json")
        thesis = os.path.join(str(out_dir), "thesis_report.md")
        hashes.append({
            "compare": _sha(compare),
            "thesis": _sha(thesis),
        })

    assert hashes[0]["compare"] == hashes[1]["compare"], (
        f"compare_report.json hash diverged across fresh processes: {hashes}"
    )
    assert hashes[0]["thesis"] == hashes[1]["thesis"], (
        f"thesis_report.md hash diverged across fresh processes: {hashes}"
    )


def test_harness_cold_run_identity_claim(tmp_path):
    """For sessions at or below the cold-start boundary, baseline_static
    and path_c_cold produce byte-identical baseline_event_result series."""
    sys.path.insert(0, _PROJECT_DIR)
    try:
        out = tmp_path / "identity"
        _run_harness_in_process(
            str(out),
            seed=42,
            events_source="demo_stream",
            min_records_for_shift=100,  # larger than the 6-event demo stream
            warm_memory="empty",
        )

        compare_path = os.path.join(str(out), "compare_report.json")
        with open(compare_path, "r") as f:
            report = json.load(f)

        # Session length (6) < min_records_for_shift (100), so entire
        # session is cold phase. BASELINE_STATIC and PATH_C_COLD must
        # have identical effective_decision values on every event.
        assert report["diverged_events"] == [], (
            "With entire session in cold phase, baseline_static and "
            "path_c_cold must not diverge"
        )

        # And per-KPI, baseline ↔ cold deltas must be 0 or None
        cold_deltas = report["deltas"].get("path_c_cold_minus_baseline_static", {})
        for kpi, delta in cold_deltas.items():
            assert delta == 0 or delta == 0.0 or delta is None, (
                f"cold-only session KPI {kpi} delta baseline vs cold = "
                f"{delta!r}; expected 0 or None"
            )
    finally:
        if _PROJECT_DIR in sys.path:
            sys.path.remove(_PROJECT_DIR)
