"""Phase 0: byte-exact baseline snapshot of run_event_loop(demo_stream).

The demo event stream is deterministic by construction (fixed t0 and
interval_minutes, no wall-clock input, no uuid). With LLM mode "off"
(the default) every agent call falls through to deterministic fallback
logic. Therefore the full run_event_loop output can be compared byte-
for-byte against a stored fixture without any normalization.
"""

import json
import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

_FIXTURE = os.path.join(
    _PROJECT_DIR, "tests", "fixtures", "d3_baseline_v1_demo_stream.json"
)


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def test_demo_stream_output_exact():
    """Canonical serialization must be byte-identical to the fixture."""
    from event_engine import generate_demo_event_stream
    from event_loop import run_event_loop

    result = run_event_loop(generate_demo_event_stream())
    produced = _canonical(result)

    with open(_FIXTURE, "rb") as f:
        expected = f.read().decode("utf-8")

    assert produced == expected, (
        "Baseline demo stream output diverged from Phase 0 snapshot. "
        "If this is an intentional contract change, update the fixture "
        "AND bump the relevant schema version in PATH_C_SCHEMA_REGISTRY.md."
    )


def test_demo_stream_output_deterministic_within_process():
    """Two back-to-back runs in the same process produce identical output."""
    from event_engine import generate_demo_event_stream
    from event_loop import run_event_loop

    a = _canonical(run_event_loop(generate_demo_event_stream()))
    b = _canonical(run_event_loop(generate_demo_event_stream()))
    assert a == b


_FRESH_PROCESS_SCRIPT = r"""
import sys, json, hashlib
sys.path.insert(0, {src!r})
from rag_setup import build_vector_store, is_store_built
if not is_store_built():
    build_vector_store()
from event_engine import generate_demo_event_stream
from event_loop import run_event_loop
r = run_event_loop(generate_demo_event_stream())
s = json.dumps(r, sort_keys=True, separators=(',',':'), default=str)
sys.stdout.write(hashlib.sha256(s.encode()).hexdigest())
"""


def test_demo_stream_output_deterministic_across_fresh_processes():
    """Spawn three fresh Python processes; all three must hash-match.

    Each subprocess has an independent Python hash-randomization seed
    (PYTHONHASHSEED is unset / random in each). Byte-identical output
    across fresh processes is the Roadmap v2.1 §0.E acceptance criterion
    for deterministic-by-construction.
    """
    import subprocess

    script = _FRESH_PROCESS_SCRIPT.format(src=_SRC_DIR)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}

    hashes = []
    for _ in range(3):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=env,
            cwd=_PROJECT_DIR,
        )
        assert proc.returncode == 0, proc.stderr
        hashes.append(proc.stdout.strip())

    assert len(set(hashes)) == 1, (
        f"Fresh-process outputs diverged: {hashes}"
    )
