"""Phase 1: fresh-process determinism stress for run_session.

Spawns independent Python subprocesses with unset ``PYTHONHASHSEED``.
Each subprocess builds the RAG store (if not already built), runs
``run_session(seed=42, mode=...)``, and prints a sha-256 hash of the
canonical artifact bytes. All hashes must match for ``seed=42``, and
different seeds must produce different session_ids.

B2 Slice 2B.5 extends coverage to correlator-enabled sessions
(``_run_corr``) and additionally varies ``PYTHONHASHSEED`` across
the three cross-process runs to catch any accidental reliance on
hash-randomized dict/set iteration order in the correlator engine
or the attach pass.
"""

from __future__ import annotations

import os
import subprocess
import sys

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")


_SUBPROCESS = r"""
import sys, json, hashlib
sys.path.insert(0, {src!r})
from rag_setup import build_vector_store, is_store_built
if not is_store_built():
    build_vector_store()
from event_loop_c import run_session
from session.digests import canonical_json
a = run_session(seed={seed}, mode={mode!r})
h = hashlib.sha256(canonical_json(a.model_dump()).encode()).hexdigest()
sys.stdout.write(a.session_id + "|" + h)
"""


_SUBPROCESS_CORR = r"""
import sys, json, hashlib
sys.path.insert(0, {src!r})
from rag_setup import build_vector_store, is_store_built
if not is_store_built():
    build_vector_store()
from event_loop_c import run_session
from correlator.correlator_config import CorrelatorConfig
from session.digests import canonical_json
cfg = CorrelatorConfig(enable_correlator=True, window_size={window_size})
a = run_session(seed={seed}, mode={mode!r}, correlator_config=cfg)
h = hashlib.sha256(canonical_json(a.model_dump()).encode()).hexdigest()
# Independent hash of just the correlator sideband so a
# sideband-only drift surfaces on its own, separate from any
# incidental drift in the rest of the artifact.
corr_dump = [
    (r.correlation_context.model_dump()
     if r.correlation_context is not None else None)
    for r in a.event_records
]
corr_h = hashlib.sha256(
    canonical_json(corr_dump).encode()
).hexdigest()
sys.stdout.write(a.session_id + "|" + h + "|" + corr_h)
"""


def _run(seed: int, mode: str, *, hashseed: str | None = None) -> tuple[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
    if hashseed is not None:
        env["PYTHONHASHSEED"] = hashseed
    out = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS.format(src=_SRC_DIR, seed=seed, mode=mode)],
        capture_output=True,
        text=True,
        env=env,
        cwd=_PROJECT_DIR,
    )
    assert out.returncode == 0, out.stderr
    sid, h = out.stdout.strip().split("|")
    return sid, h


def _run_corr(
    seed: int, mode: str, *, window_size: int = 3,
    hashseed: str | None = None,
) -> tuple[str, str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
    if hashseed is not None:
        env["PYTHONHASHSEED"] = hashseed
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            _SUBPROCESS_CORR.format(
                src=_SRC_DIR, seed=seed, mode=mode, window_size=window_size,
            ),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=_PROJECT_DIR,
    )
    assert out.returncode == 0, out.stderr
    sid, h, corr_h = out.stdout.strip().split("|")
    return sid, h, corr_h


def test_same_seed_same_artifact_across_fresh_processes():
    results = [_run(42, "BASELINE_STATIC") for _ in range(3)]
    sids = {r[0] for r in results}
    hashes = {r[1] for r in results}
    assert len(sids) == 1, f"session_ids diverged: {sids}"
    assert len(hashes) == 1, f"artifact hashes diverged: {hashes}"


def test_different_seed_different_session_id_across_fresh_processes():
    sid_42, _ = _run(42, "BASELINE_STATIC")
    sid_99, _ = _run(99, "BASELINE_STATIC")
    assert sid_42 != sid_99


def test_different_mode_different_session_id_across_fresh_processes():
    sid_static, _ = _run(42, "BASELINE_STATIC")
    sid_cold, _ = _run(42, "PATH_C_COLD")
    assert sid_static != sid_cold


# ---------------------------------------------------------------------------
# B2 Slice 2B.5 — correlator-enabled cross-process determinism
# ---------------------------------------------------------------------------


def test_corr_on_same_seed_same_artifact_across_fresh_processes():
    """Correlator-enabled runs, same inputs, three fresh processes
    under three different ``PYTHONHASHSEED`` values. All three must
    agree on session_id, full-artifact sha, and correlator-sideband
    sha — otherwise hash-randomized iteration is leaking in."""
    results = [
        _run_corr(42, "BASELINE_STATIC", hashseed=hs)
        for hs in ("0", "1", "random")
    ]
    sids = {r[0] for r in results}
    hashes = {r[1] for r in results}
    corr_hashes = {r[2] for r in results}
    assert len(sids) == 1, f"session_ids diverged: {sids}"
    assert len(hashes) == 1, f"artifact hashes diverged: {hashes}"
    assert len(corr_hashes) == 1, (
        f"correlator sideband hashes diverged across PYTHONHASHSEED: "
        f"{corr_hashes}"
    )


def test_corr_on_different_seed_different_session_id_across_fresh_processes():
    sid_42, _, _ = _run_corr(42, "BASELINE_STATIC")
    sid_99, _, _ = _run_corr(99, "BASELINE_STATIC")
    assert sid_42 != sid_99


def test_corr_on_path_c_cold_deterministic_across_fresh_processes():
    """Same guarantee under ``PATH_C_COLD`` — exercises the adaptive
    path alongside the correlator attach."""
    results = [
        _run_corr(42, "PATH_C_COLD", hashseed=hs)
        for hs in ("0", "random")
    ]
    sids = {r[0] for r in results}
    hashes = {r[1] for r in results}
    corr_hashes = {r[2] for r in results}
    assert len(sids) == 1
    assert len(hashes) == 1
    assert len(corr_hashes) == 1


def test_corr_on_vs_off_session_id_differs_across_fresh_processes():
    sid_off, _ = _run(42, "BASELINE_STATIC")
    sid_on, _, _ = _run_corr(42, "BASELINE_STATIC")
    assert sid_off != sid_on


def test_corr_window_size_contributes_to_digest_across_fresh_processes():
    sid_w3, _, _ = _run_corr(42, "BASELINE_STATIC", window_size=3)
    sid_w5, _, _ = _run_corr(42, "BASELINE_STATIC", window_size=5)
    assert sid_w3 != sid_w5


# ---------------------------------------------------------------------------
# B3 Slice 2B.5 — cumulative-memory fresh-process determinism
# ---------------------------------------------------------------------------
#
# The subprocess reconstructs the prior rows inline (same rows as
# the replay test's ``_cumulative_fixture_rows``) so every fresh
# subprocess starts from identical inputs. Under varied
# ``PYTHONHASHSEED``, session_id + artifact-sha + a
# memory-snapshot-sha must all agree.


_SUBPROCESS_CUMULATIVE = r"""
import sys, hashlib, json
sys.path.insert(0, {src!r})
from rag_setup import build_vector_store, is_store_built
if not is_store_built():
    build_vector_store()
from event_loop_c import run_session
from session.digests import canonical_json
from learning.memory_schema import MemoryRecord
from learning.cumulative_memory import (
    CumulativeMemoryConfig, load_cumulative_memory,
)

rows = []
for i in range(6):
    rows.append(MemoryRecord(
        event_id=f"PRIOR-EVT-{{i:03d}}",
        event_type="CARRIER_DELAY_ESCALATION",
        event_timestamp=f"2026-02-{{(i % 28) + 1:02d}}T10:00:00+00:00",
        action_taken="EXPEDITE",
        execution_status="executed",
        final_route="AUTO_EXECUTE",
        cost_incurred=250.0 + i,
        sla_preserved=False,
        risk_level="LOW",
        session_id=f"PRIOR_SESSION_{{(i % 2) + 1}}",
    ))

cfg = CumulativeMemoryConfig(
    prior_session_refs=("PRIOR_SESSION_1", "PRIOR_SESSION_2"),
)
rows_by_ref = {{
    "PRIOR_SESSION_1": [r for r in rows if r.session_id == "PRIOR_SESSION_1"],
    "PRIOR_SESSION_2": [r for r in rows if r.session_id == "PRIOR_SESSION_2"],
}}

def resolver(ref):
    return list(rows_by_ref[ref])

prior = load_cumulative_memory(cfg, source_resolver=resolver)

a = run_session(seed={seed}, mode={mode!r}, initial_memory=prior)
h = hashlib.sha256(canonical_json(a.model_dump()).encode()).hexdigest()
mem_h = hashlib.sha256(
    canonical_json(a.memory_snapshot).encode()
).hexdigest()
sys.stdout.write(a.session_id + "|" + h + "|" + mem_h)
"""


def _run_cumulative(
    seed: int, mode: str, *, hashseed: str | None = None,
) -> tuple[str, str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
    if hashseed is not None:
        env["PYTHONHASHSEED"] = hashseed
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            _SUBPROCESS_CUMULATIVE.format(
                src=_SRC_DIR, seed=seed, mode=mode,
            ),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=_PROJECT_DIR,
    )
    assert out.returncode == 0, out.stderr
    sid, h, mem_h = out.stdout.strip().split("|")
    return sid, h, mem_h


def test_cumulative_warm_same_inputs_identical_across_fresh_processes():
    """PATH_C_WARM with a deterministic cumulative prior memory,
    three fresh subprocesses under three different
    ``PYTHONHASHSEED`` values. session_id, full-artifact sha, and
    memory-snapshot sha must all agree — any drift means hash-
    randomization is leaking into the cumulative path."""
    results = [
        _run_cumulative(42, "PATH_C_WARM", hashseed=hs)
        for hs in ("0", "1", "random")
    ]
    sids = {r[0] for r in results}
    hashes = {r[1] for r in results}
    mem_hashes = {r[2] for r in results}
    assert len(sids) == 1, f"session_ids diverged: {sids}"
    assert len(hashes) == 1, f"artifact hashes diverged: {hashes}"
    assert len(mem_hashes) == 1, (
        f"memory_snapshot hashes diverged across PYTHONHASHSEED: "
        f"{mem_hashes}"
    )


def test_cumulative_warm_different_seed_different_session_id():
    sid_42, _, _ = _run_cumulative(42, "PATH_C_WARM")
    sid_99, _, _ = _run_cumulative(99, "PATH_C_WARM")
    assert sid_42 != sid_99
