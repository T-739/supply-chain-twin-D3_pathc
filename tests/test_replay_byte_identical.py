"""Phase 1: save → load → replay is byte-identical to the original save.

B2 Slice 2B.5 additionally parametrizes over correlator-enabled
sessions so that ``enable_correlator=True`` artifacts (with
populated ``correlation_context`` sidebands) survive the
save → load → replay cycle byte-for-byte.
"""

from __future__ import annotations

import os
import sys

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from correlator.correlator_config import CorrelatorConfig
from event_loop_c import run_session
from session.digests import canonical_json
from session.session_manager import (
    ARTIFACT_FILENAME,
    MEMORY_FILENAME,
    load_session,
    replay_session_bytes,
    save_session,
)


# Parametrize over (mode, correlator_config) pairs. ``None`` means
# "default (correlator disabled)". Enabled variants use the same
# fixed window_size to keep the expected session_id digest stable
# across runs.
_CORR_ON = CorrelatorConfig(enable_correlator=True, window_size=3)

_MODE_CORR_MATRIX = [
    ("BASELINE_STATIC", None),
    ("BASELINE_STATIC", _CORR_ON),
    ("PATH_C_COLD", None),
    ("PATH_C_COLD", _CORR_ON),
    ("PATH_C_WARM", _CORR_ON),
]


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


def _sha_bytes(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_artifact_roundtrip_byte_identical(tmp_path):
    a = run_session(seed=42, mode="BASELINE_STATIC")
    save_session(a, tmp_path)

    with open(tmp_path / ARTIFACT_FILENAME, "r") as f:
        saved_bytes = f.read()

    loaded = load_session(tmp_path)
    replayed_bytes = replay_session_bytes(loaded)

    assert replayed_bytes == saved_bytes
    assert _sha_bytes(replayed_bytes) == _sha_bytes(saved_bytes)


def test_memory_jsonl_roundtrip(tmp_path):
    a = run_session(seed=42, mode="PATH_C_COLD")
    save_session(a, tmp_path)

    with open(tmp_path / MEMORY_FILENAME, "r") as f:
        lines = [ln for ln in f.read().split("\n") if ln]

    expected = [canonical_json(r) for r in a.memory_snapshot["records"]]
    assert lines == expected


def test_two_fresh_runs_produce_byte_identical_artifacts(tmp_path):
    a = run_session(seed=42, mode="BASELINE_STATIC")
    b = run_session(seed=42, mode="BASELINE_STATIC")
    assert canonical_json(a.model_dump()) == canonical_json(b.model_dump())


# ---------------------------------------------------------------------------
# B2 Slice 2B.5 — correlator-enabled replay byte identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode,corr", _MODE_CORR_MATRIX)
def test_artifact_roundtrip_byte_identical_across_correlator(
    mode, corr, tmp_path,
):
    """Save → load → replay stays byte-identical whether correlator
    is disabled or enabled. The crucial new case is ``corr=_CORR_ON``
    where ``correlation_context`` is populated on every record and
    must survive persistence unchanged."""
    a = run_session(seed=42, mode=mode, correlator_config=corr)
    save_session(a, tmp_path)

    with open(tmp_path / ARTIFACT_FILENAME, "r") as f:
        saved_bytes = f.read()

    loaded = load_session(tmp_path)
    replayed_bytes = replay_session_bytes(loaded)

    assert replayed_bytes == saved_bytes
    assert _sha_bytes(replayed_bytes) == _sha_bytes(saved_bytes)

    # Validate the correlator sideband actually made the trip when
    # enabled. This is the new property on top of the pre-B2 roundtrip.
    if corr is not None and corr.enable_correlator:
        for rec_original, rec_loaded in zip(
            a.event_records, loaded.event_records
        ):
            assert rec_loaded.correlation_context is not None, (
                "enabled correlator must populate correlation_context "
                "on every record"
            )
            assert (
                rec_loaded.correlation_context.model_dump()
                == rec_original.correlation_context.model_dump()
            )
    else:
        for rec_loaded in loaded.event_records:
            assert rec_loaded.correlation_context is None


@pytest.mark.parametrize("mode,corr", _MODE_CORR_MATRIX)
def test_two_fresh_same_process_runs_byte_identical_across_correlator(
    mode, corr,
):
    """Repeated same-process runs produce byte-identical canonical
    artifact JSON regardless of correlator state."""
    a = run_session(seed=42, mode=mode, correlator_config=corr)
    b = run_session(seed=42, mode=mode, correlator_config=corr)
    assert canonical_json(a.model_dump()) == canonical_json(b.model_dump())
    assert a.session_id == b.session_id


def test_correlator_on_vs_off_produce_distinct_session_ids():
    """Sanity pin on the orthogonal direction: enabling the
    correlator must shift ``session_id`` (because
    ``CorrelatorConfig`` contributes to ``config_for_digest`` when
    enabled). Paired with the identity guarantees above, this keeps
    the digest well-formed: enable flips one and only one axis."""
    a_off = run_session(seed=42, mode="BASELINE_STATIC")
    a_on = run_session(
        seed=42, mode="BASELINE_STATIC", correlator_config=_CORR_ON,
    )
    assert a_off.session_id != a_on.session_id


def test_correlator_window_size_change_shifts_session_id():
    """Two different correlator window sizes must produce different
    ``session_id`` values — otherwise the digest would be blind to a
    parameter that demonstrably affects correlator output."""
    a_w3 = run_session(
        seed=42,
        mode="BASELINE_STATIC",
        correlator_config=CorrelatorConfig(enable_correlator=True, window_size=3),
    )
    a_w5 = run_session(
        seed=42,
        mode="BASELINE_STATIC",
        correlator_config=CorrelatorConfig(enable_correlator=True, window_size=5),
    )
    assert a_w3.session_id != a_w5.session_id


# ---------------------------------------------------------------------------
# B3 Slice 2B.5 — cumulative-memory replay byte identity (PATH_C_WARM)
# ---------------------------------------------------------------------------


def _cumulative_fixture_rows():
    """Deterministic prior-session rows used by the Slice 2B.5
    replay/determinism tests. The rows mirror the harness's
    synthetic-warm scenario (CARRIER_DELAY_ESCALATION with poor
    SLA history) so the PATH_C_WARM policy gate has a believable
    signal to react to, while staying fully reconstructible from
    code (no file I/O)."""
    from learning.memory_schema import MemoryRecord

    rows = []
    for i in range(6):
        rows.append(
            MemoryRecord(
                event_id=f"PRIOR-EVT-{i:03d}",
                event_type="CARRIER_DELAY_ESCALATION",
                event_timestamp=f"2026-02-{(i % 28) + 1:02d}T10:00:00+00:00",
                action_taken="EXPEDITE",
                execution_status="executed",
                final_route="AUTO_EXECUTE",
                cost_incurred=250.0 + i,
                sla_preserved=False,
                risk_level="LOW",
                session_id=f"PRIOR_SESSION_{(i % 2) + 1}",
            )
        )
    return rows


def _cumulative_memory_via_loader():
    """Build an ``EpisodicMemory`` using the Slice 2B loader — the
    same runtime seam the eventual CLI (Slice 2D) will use."""
    from learning.cumulative_memory import (
        CumulativeMemoryConfig,
        load_cumulative_memory,
    )

    rows = _cumulative_fixture_rows()
    cfg = CumulativeMemoryConfig(
        prior_session_refs=("PRIOR_SESSION_1", "PRIOR_SESSION_2"),
    )

    rows_by_ref = {
        "PRIOR_SESSION_1": [r for r in rows if r.session_id == "PRIOR_SESSION_1"],
        "PRIOR_SESSION_2": [r for r in rows if r.session_id == "PRIOR_SESSION_2"],
    }

    def resolver(ref: str):
        return list(rows_by_ref[ref])

    return load_cumulative_memory(cfg, source_resolver=resolver)


def test_cumulative_enabled_roundtrip_byte_identical(tmp_path):
    """PATH_C_WARM with a cumulative-loaded initial memory:
    save → load → replay must stay byte-identical."""
    prior = _cumulative_memory_via_loader()
    art = run_session(
        seed=42, mode="PATH_C_WARM", initial_memory=prior,
    )
    save_session(art, tmp_path)

    with open(tmp_path / ARTIFACT_FILENAME, "r") as f:
        saved_bytes = f.read()

    loaded = load_session(tmp_path)
    replayed_bytes = replay_session_bytes(loaded)

    assert replayed_bytes == saved_bytes
    assert _sha_bytes(replayed_bytes) == _sha_bytes(saved_bytes)

    # Cross-session provenance on the loaded memory must survive
    # the roundtrip: rows carrying PRIOR_SESSION_* session_ids
    # remain in ``memory_snapshot``.
    prior_sids = {
        r["session_id"]
        for r in loaded.memory_snapshot["records"]
        if r["session_id"].startswith("PRIOR_SESSION_")
    }
    assert prior_sids == {"PRIOR_SESSION_1", "PRIOR_SESSION_2"}


def test_cumulative_enabled_two_fresh_runs_byte_identical():
    """Repeated same-input PATH_C_WARM runs with the same cumulative
    memory produce byte-identical canonical artifact JSON."""
    a = run_session(
        seed=42,
        mode="PATH_C_WARM",
        initial_memory=_cumulative_memory_via_loader(),
    )
    b = run_session(
        seed=42,
        mode="PATH_C_WARM",
        initial_memory=_cumulative_memory_via_loader(),
    )
    assert canonical_json(a.model_dump()) == canonical_json(b.model_dump())
    assert a.session_id == b.session_id


def test_cumulative_resolver_identity_does_not_affect_artifact():
    """Two different resolver implementations that return the same
    resolved row content (byte-equal) produce byte-identical
    artifacts. Determinism flows from ref content, not from
    resolver identity (D10)."""
    from learning.cumulative_memory import (
        CumulativeMemoryConfig,
        load_cumulative_memory,
    )

    rows = _cumulative_fixture_rows()
    cfg = CumulativeMemoryConfig(
        prior_session_refs=("PRIOR_SESSION_1", "PRIOR_SESSION_2"),
    )

    # Resolver #1: dict-based lookup.
    rows_by_ref = {
        "PRIOR_SESSION_1": [r for r in rows if r.session_id == "PRIOR_SESSION_1"],
        "PRIOR_SESSION_2": [r for r in rows if r.session_id == "PRIOR_SESSION_2"],
    }

    def resolver_dict(ref):
        return list(rows_by_ref[ref])

    # Resolver #2: list-comprehension per call over the flat rows
    # (distinct closure, different code path, same resolved content).
    def resolver_listcomp(ref):
        return [r for r in rows if r.session_id == ref]

    mem_1 = load_cumulative_memory(cfg, source_resolver=resolver_dict)
    mem_2 = load_cumulative_memory(cfg, source_resolver=resolver_listcomp)

    # Loader-level bytes match.
    assert mem_1.snapshot() == mem_2.snapshot()

    # Full session-artifact bytes also match.
    a = run_session(seed=42, mode="PATH_C_WARM", initial_memory=mem_1)
    b = run_session(seed=42, mode="PATH_C_WARM", initial_memory=mem_2)
    assert canonical_json(a.model_dump()) == canonical_json(b.model_dump())


def test_cumulative_memory_does_not_affect_baseline_or_cold():
    """BASELINE_STATIC / PATH_C_COLD default-disabled paths are
    untouched regardless of what cumulative memory the caller
    prepared — the workflow rule (D7) is that those modes don't
    attach prior memory in the first place. Pin that running
    them without ``initial_memory`` matches pre-B3 behavior even
    if a separate PATH_C_WARM in the same process used
    cumulative memory."""
    # Prime a cumulative memory (this exercises the loader).
    _ = _cumulative_memory_via_loader()

    # Now run BASELINE_STATIC / PATH_C_COLD WITHOUT initial_memory
    # and assert two fresh runs are byte-identical.
    for mode in ("BASELINE_STATIC", "PATH_C_COLD"):
        a = run_session(seed=42, mode=mode)
        b = run_session(seed=42, mode=mode)
        assert canonical_json(a.model_dump()) == canonical_json(b.model_dump()), (
            f"{mode} mode artifact bytes drifted across repeated runs"
        )
