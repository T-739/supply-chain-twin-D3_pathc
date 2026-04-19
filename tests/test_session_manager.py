"""Phase 1: session_manager + session_id determinism tests.

B2 Slice 2B.5 adds ``TestCorrelatorSaveLoadReplay`` — a save / load /
replay roundtrip class for correlator-enabled sessions. It pins:

  - the on-disk artifact bytes match ``canonical_json`` of the
    in-memory artifact when ``correlation_context`` is populated;
  - the reloaded artifact equals the original artifact (full
    ``model_dump`` equality, including every ``correlation_context``
    and every ``CorrelationSignal`` therein);
  - ``session_id`` is preserved across load.
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


_CORR_ON = CorrelatorConfig(enable_correlator=True, window_size=3)


@pytest.fixture(autouse=True, scope="module")
def _ensure_rag():
    from rag_setup import build_vector_store, is_store_built
    if not is_store_built():
        build_vector_store()


class TestSessionIdDeterminism:
    def test_same_inputs_same_id(self):
        a = run_session(seed=42, mode="BASELINE_STATIC")
        b = run_session(seed=42, mode="BASELINE_STATIC")
        assert a.session_id == b.session_id
        assert len(a.session_id) == 64  # full SHA-256 hex

    def test_different_seed_changes_id(self):
        a = run_session(seed=42, mode="BASELINE_STATIC")
        b = run_session(seed=43, mode="BASELINE_STATIC")
        assert a.session_id != b.session_id

    def test_different_mode_changes_id(self):
        a = run_session(seed=42, mode="BASELINE_STATIC")
        b = run_session(seed=42, mode="PATH_C_COLD")
        assert a.session_id != b.session_id


class TestSaveLoadReplay:
    def test_save_then_load_preserves_bytes(self, tmp_path):
        original = run_session(seed=42, mode="BASELINE_STATIC")
        paths = save_session(original, tmp_path)

        assert os.path.basename(paths["artifact_path"]) == ARTIFACT_FILENAME
        assert os.path.basename(paths["memory_path"]) == MEMORY_FILENAME

        with open(paths["artifact_path"], "r") as f:
            on_disk = f.read()

        assert on_disk == canonical_json(original.model_dump())

        reloaded = load_session(tmp_path)
        assert replay_session_bytes(reloaded) == on_disk

    def test_load_returns_equivalent_artifact(self, tmp_path):
        original = run_session(seed=42, mode="PATH_C_COLD")
        save_session(original, tmp_path)
        reloaded = load_session(tmp_path)
        assert reloaded.session_id == original.session_id
        assert reloaded.model_dump() == original.model_dump()


class TestCorrelatorSessionIdDeterminism:
    """B2 Slice 2B.5 — session_id determinism for correlator runs."""

    def test_same_inputs_same_id_enabled(self):
        a = run_session(
            seed=42, mode="BASELINE_STATIC", correlator_config=_CORR_ON,
        )
        b = run_session(
            seed=42, mode="BASELINE_STATIC", correlator_config=_CORR_ON,
        )
        assert a.session_id == b.session_id
        assert len(a.session_id) == 64

    def test_enable_flag_shifts_session_id(self):
        a = run_session(seed=42, mode="BASELINE_STATIC")
        b = run_session(
            seed=42, mode="BASELINE_STATIC", correlator_config=_CORR_ON,
        )
        assert a.session_id != b.session_id

    def test_window_size_shifts_session_id_when_enabled(self):
        a = run_session(
            seed=42,
            mode="BASELINE_STATIC",
            correlator_config=CorrelatorConfig(
                enable_correlator=True, window_size=3,
            ),
        )
        b = run_session(
            seed=42,
            mode="BASELINE_STATIC",
            correlator_config=CorrelatorConfig(
                enable_correlator=True, window_size=5,
            ),
        )
        assert a.session_id != b.session_id

    def test_enabled_pattern_subset_shifts_session_id(self):
        a = run_session(
            seed=42,
            mode="BASELINE_STATIC",
            correlator_config=CorrelatorConfig(
                enable_correlator=True,
                window_size=3,
                enabled_patterns=frozenset({"ETA_PATH_COMPOUND"}),
            ),
        )
        b = run_session(
            seed=42,
            mode="BASELINE_STATIC",
            correlator_config=CorrelatorConfig(
                enable_correlator=True,
                window_size=3,
                enabled_patterns=frozenset({"CARRIER_DOUBLE_HIT"}),
            ),
        )
        assert a.session_id != b.session_id


class TestCorrelatorSaveLoadReplay:
    """B2 Slice 2B.5 — save / load / replay for correlator-enabled
    sessions. Exercises the persistence path end-to-end under
    ``enable_correlator=True`` so ``correlation_context`` and every
    nested ``CorrelationSignal`` survive the cycle unchanged."""

    @pytest.mark.parametrize(
        "mode", ["BASELINE_STATIC", "PATH_C_COLD", "PATH_C_WARM"],
    )
    def test_save_then_load_preserves_bytes_enabled(self, mode, tmp_path):
        original = run_session(
            seed=42, mode=mode, correlator_config=_CORR_ON,
        )
        # Sanity: correlator is populated on every record — otherwise
        # this test is not actually exercising the correlator path.
        assert all(
            r.correlation_context is not None for r in original.event_records
        )

        paths = save_session(original, tmp_path)
        assert os.path.basename(paths["artifact_path"]) == ARTIFACT_FILENAME
        assert os.path.basename(paths["memory_path"]) == MEMORY_FILENAME

        with open(paths["artifact_path"], "r") as f:
            on_disk = f.read()
        assert on_disk == canonical_json(original.model_dump())

        reloaded = load_session(tmp_path)
        assert replay_session_bytes(reloaded) == on_disk

    @pytest.mark.parametrize(
        "mode", ["BASELINE_STATIC", "PATH_C_COLD", "PATH_C_WARM"],
    )
    def test_load_returns_equivalent_artifact_enabled(self, mode, tmp_path):
        original = run_session(
            seed=42, mode=mode, correlator_config=_CORR_ON,
        )
        save_session(original, tmp_path)
        reloaded = load_session(tmp_path)
        assert reloaded.session_id == original.session_id
        assert reloaded.model_dump() == original.model_dump()

        # Explicit correlator-sideband fidelity — pin every signal's
        # full dump so drift shows up as a direct assertion failure
        # rather than buried inside a large dict diff.
        for r_orig, r_loaded in zip(
            original.event_records, reloaded.event_records,
        ):
            orig_ctx = r_orig.correlation_context
            loaded_ctx = r_loaded.correlation_context
            assert orig_ctx is not None and loaded_ctx is not None
            assert loaded_ctx.model_dump() == orig_ctx.model_dump()
            # Nested signal list matches element-by-element.
            assert len(loaded_ctx.signals) == len(orig_ctx.signals)
            for s_orig, s_loaded in zip(orig_ctx.signals, loaded_ctx.signals):
                assert s_loaded.model_dump() == s_orig.model_dump()

    def test_disabled_roundtrip_still_has_none_correlation_context(
        self, tmp_path,
    ):
        """Regression guard: disabled-path persistence must keep
        ``correlation_context=None`` on every record after a
        save/load roundtrip — a subtle way the pydantic default
        could drift would be hard to notice without this pin."""
        original = run_session(seed=42, mode="PATH_C_COLD")
        save_session(original, tmp_path)
        reloaded = load_session(tmp_path)
        assert all(
            r.correlation_context is None for r in reloaded.event_records
        )


# ---------------------------------------------------------------------------
# B3 Slice 2B.5 — cumulative-memory save/load/replay
# ---------------------------------------------------------------------------


def _build_cumulative_memory_for_session_tests():
    """Deterministic prior-memory fixture used by the Slice 2B.5
    session-manager tests. Goes through the Slice 2B loader —
    same runtime seam the eventual CLI (Slice 2D) will use."""
    from learning.cumulative_memory import (
        CumulativeMemoryConfig,
        load_cumulative_memory,
    )
    from learning.memory_schema import MemoryRecord

    rows = []
    for i in range(4):
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

    rows_by_ref = {
        "PRIOR_SESSION_1": [r for r in rows if r.session_id == "PRIOR_SESSION_1"],
        "PRIOR_SESSION_2": [r for r in rows if r.session_id == "PRIOR_SESSION_2"],
    }

    def resolver(ref):
        return list(rows_by_ref[ref])

    cfg = CumulativeMemoryConfig(
        prior_session_refs=("PRIOR_SESSION_1", "PRIOR_SESSION_2"),
    )
    return load_cumulative_memory(cfg, source_resolver=resolver)


class TestCumulativeMemorySaveLoadReplay:
    """B3 Slice 2B.5 — save / load / replay for PATH_C_WARM runs
    that use cumulative prior memory via the loader +
    existing ``run_session(initial_memory=...)`` seam."""

    def test_save_then_load_preserves_bytes_with_cumulative(self, tmp_path):
        prior = _build_cumulative_memory_for_session_tests()
        original = run_session(
            seed=42, mode="PATH_C_WARM", initial_memory=prior,
        )
        paths = save_session(original, tmp_path)

        assert os.path.basename(paths["artifact_path"]) == ARTIFACT_FILENAME
        assert os.path.basename(paths["memory_path"]) == MEMORY_FILENAME

        with open(paths["artifact_path"], "r") as f:
            on_disk = f.read()
        assert on_disk == canonical_json(original.model_dump())

        reloaded = load_session(tmp_path)
        assert replay_session_bytes(reloaded) == on_disk

    def test_load_returns_equivalent_artifact_with_cumulative(self, tmp_path):
        prior = _build_cumulative_memory_for_session_tests()
        original = run_session(
            seed=42, mode="PATH_C_WARM", initial_memory=prior,
        )
        save_session(original, tmp_path)
        reloaded = load_session(tmp_path)

        assert reloaded.session_id == original.session_id
        assert reloaded.model_dump() == original.model_dump()

    def test_prior_session_provenance_survives_roundtrip(self, tmp_path):
        """Cross-session ``session_id`` markers on the loaded
        memory rows must be preserved byte-for-byte through
        save/load/replay."""
        prior = _build_cumulative_memory_for_session_tests()
        prior_sids_before = sorted(
            {r.session_id for r in prior.records()}
        )
        assert prior_sids_before == ["PRIOR_SESSION_1", "PRIOR_SESSION_2"]

        original = run_session(
            seed=42, mode="PATH_C_WARM", initial_memory=prior,
        )
        save_session(original, tmp_path)
        reloaded = load_session(tmp_path)

        reloaded_sids = {
            r["session_id"]
            for r in reloaded.memory_snapshot["records"]
        }
        # Both prior-session markers must still be present on
        # some rows; additional sids from the current session are
        # fine.
        assert "PRIOR_SESSION_1" in reloaded_sids
        assert "PRIOR_SESSION_2" in reloaded_sids

        # memory.jsonl on disk must carry those rows too, one
        # per line.
        with open(os.path.join(str(tmp_path), MEMORY_FILENAME), "r") as f:
            jsonl = f.read()
        assert "PRIOR_SESSION_1" in jsonl
        assert "PRIOR_SESSION_2" in jsonl

    def test_repeated_cumulative_warm_runs_byte_identical(self, tmp_path):
        """Two same-input PATH_C_WARM runs with identical
        cumulative memory produce byte-identical canonical JSON
        and share a session_id."""
        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"
        dir_a.mkdir()
        dir_b.mkdir()

        prior_a = _build_cumulative_memory_for_session_tests()
        prior_b = _build_cumulative_memory_for_session_tests()

        art_a = run_session(
            seed=42, mode="PATH_C_WARM", initial_memory=prior_a,
        )
        art_b = run_session(
            seed=42, mode="PATH_C_WARM", initial_memory=prior_b,
        )
        save_session(art_a, dir_a)
        save_session(art_b, dir_b)

        with open(dir_a / ARTIFACT_FILENAME) as f_a, \
             open(dir_b / ARTIFACT_FILENAME) as f_b:
            assert f_a.read() == f_b.read()
        assert art_a.session_id == art_b.session_id

    def test_cumulative_warm_session_id_differs_from_non_cumulative(
        self, tmp_path,
    ):
        """Enabling cumulative prior memory for PATH_C_WARM
        changes the ``initial_memory_digest`` input to
        ``compute_session_id``; session_id therefore shifts
        deterministically vs a PATH_C_WARM run without prior
        memory. Pinned so a future silent equivalence would be
        caught."""
        prior = _build_cumulative_memory_for_session_tests()
        with_prior = run_session(
            seed=42, mode="PATH_C_WARM", initial_memory=prior,
        )
        without_prior = run_session(seed=42, mode="PATH_C_WARM")
        assert with_prior.session_id != without_prior.session_id
