"""Bundler tests: missing files, B4 without path_c_cold, malformed
metadata, null-safe normalization.

These tests live under ``backend/tests/`` because they verify the
bundler <-> backend boundary — the bundler's output must be
loadable by the backend repository.
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

from backend.repository import (
    BundleRepository,
    MalformedBundleError,
)
from tools.bundler import (
    B4_TRIPLET_TAGS,
    DEFAULT_3_MODE_TAGS,
    BundlerError,
    build_bundle_from_harness_dir,
    classify_variant_set,
)
from tools.bundler.fixture_builder import (
    build_b4_triplet_fixture,
    build_default_3mode_fixture,
)


# ---------------------------------------------------------------------------
# classify_variant_set
# ---------------------------------------------------------------------------


def test_classify_default_3_mode():
    assert classify_variant_set(DEFAULT_3_MODE_TAGS) == "default_3_mode"


def test_classify_b4_triplet():
    assert classify_variant_set(B4_TRIPLET_TAGS) == "b4_experiment_triplet"


def test_classify_custom_subset():
    # Only baseline_static + warm — neither the default trio nor
    # the B4 triplet. MUST classify as custom, not crash.
    assert classify_variant_set(["baseline_static", "path_c_warm"]) == "custom"


def test_classify_empty_is_custom():
    assert classify_variant_set([]) == "custom"


# ---------------------------------------------------------------------------
# build_bundle_from_harness_dir — happy path & null-safety
# ---------------------------------------------------------------------------


def _make_minimal_harness_dir(
    root: str,
    *,
    tags: list[str],
    include_memory: set[str] | None = None,
    include_compare: bool = True,
    include_thesis: bool = True,
) -> None:
    """Build a fake harness output directory on disk."""
    os.makedirs(root, exist_ok=True)
    include_memory = include_memory if include_memory is not None else set(tags)
    for tag in tags:
        sub = os.path.join(root, tag)
        os.makedirs(sub, exist_ok=True)
        artifact = {
            "session_id": f"TEST-{tag.upper()}",
            "config": {
                "seed": 1,
                "mode": "BASELINE_STATIC",
                "events_source": "demo",
                "initial_memory_digest": "",
                "schema_version": "1.0",
            },
            "event_records": [],
            "memory_snapshot": {"records": []},
            "kpis": {
                "events_observed": 0,
                "events_with_outcome": 0,
                "events_skipped": 0,
                "events_failed": 0,
                "events_processed": 0,
                "auto_execute_success_rate": None,
                "sla_preservation_rate": None,
                "total_cost": 0.0,
                "avg_cost": None,
                "known_outcome_coverage": None,
                "replan_events_observed": 0,
                "replan_fire_count": 0,
                "replan_trigger_rate": None,
                "replan_success_count": 0,
                "replan_recovery_rate": None,
                "schema_version": "1.1",
            },
            "schema_versions": {},
            "notes": "",
            "schema_version": "1.0",
        }
        with open(os.path.join(sub, "session_artifact.json"), "w") as f:
            json.dump(artifact, f, sort_keys=True)
        if tag in include_memory:
            with open(os.path.join(sub, "memory.jsonl"), "w") as f:
                f.write("")
    if include_compare:
        with open(os.path.join(root, "compare_report.json"), "w") as f:
            json.dump({"schema_version": "1.1"}, f)
    if include_thesis:
        with open(os.path.join(root, "thesis_report.md"), "w") as f:
            f.write("# fake thesis\n")


def test_repackage_default_3_mode_happy_path(tmp_path):
    harness = tmp_path / "harness_default"
    bundles_root = tmp_path / "bundles"
    _make_minimal_harness_dir(
        str(harness), tags=list(DEFAULT_3_MODE_TAGS),
    )
    meta = build_bundle_from_harness_dir(
        harness_dir=str(harness),
        bundles_root=str(bundles_root),
        bundle_id="test_default_happy",
    )
    assert meta["variant_set"] == "default_3_mode"
    assert meta["has_compare_report"] is True
    assert meta["has_thesis_report"] is True
    # Round-trip via repository.
    repo = BundleRepository(str(bundles_root))
    detail = repo.load_detail("test_default_happy")
    assert [s.variant_tag for s in detail.sessions] == list(DEFAULT_3_MODE_TAGS)


def test_repackage_b4_triplet_without_path_c_cold(tmp_path):
    harness = tmp_path / "harness_b4"
    bundles_root = tmp_path / "bundles"
    _make_minimal_harness_dir(str(harness), tags=list(B4_TRIPLET_TAGS))
    meta = build_bundle_from_harness_dir(
        harness_dir=str(harness),
        bundles_root=str(bundles_root),
        bundle_id="test_b4",
    )
    assert meta["variant_set"] == "b4_experiment_triplet"
    assert "path_c_cold" not in meta["variant_tags"]
    # Repository loads cleanly without assuming path_c_cold exists.
    repo = BundleRepository(str(bundles_root))
    detail = repo.load_detail("test_b4")
    tags = {s.variant_tag for s in detail.sessions}
    assert "path_c_cold" not in tags


def test_missing_compare_and_thesis_are_tolerated(tmp_path):
    harness = tmp_path / "harness_no_compare"
    bundles_root = tmp_path / "bundles"
    _make_minimal_harness_dir(
        str(harness),
        tags=list(DEFAULT_3_MODE_TAGS),
        include_compare=False,
        include_thesis=False,
    )
    meta = build_bundle_from_harness_dir(
        harness_dir=str(harness),
        bundles_root=str(bundles_root),
        bundle_id="test_no_reports",
    )
    assert meta["has_compare_report"] is False
    assert meta["has_thesis_report"] is False
    assert any("compare_report.json absent" in w for w in meta["warnings"])
    assert any("thesis_report.md absent" in w for w in meta["warnings"])

    repo = BundleRepository(str(bundles_root))
    detail = repo.load_detail("test_no_reports")
    assert detail.compare_report_raw is None
    assert detail.thesis_report_raw_markdown is None


def test_partial_memory_jsonl_is_tolerated(tmp_path):
    harness = tmp_path / "harness_partial_memory"
    bundles_root = tmp_path / "bundles"
    _make_minimal_harness_dir(
        str(harness),
        tags=list(DEFAULT_3_MODE_TAGS),
        include_memory={"baseline_static"},
    )
    meta = build_bundle_from_harness_dir(
        harness_dir=str(harness),
        bundles_root=str(bundles_root),
        bundle_id="test_partial_memory",
    )
    # Warnings name the tags whose memory file was missing.
    absent_tags_in_warnings = [
        w for w in meta["warnings"]
        if "memory.jsonl absent" in w
    ]
    assert len(absent_tags_in_warnings) == 2

    repo = BundleRepository(str(bundles_root))
    detail = repo.load_detail("test_partial_memory")
    per_tag = {s.variant_tag: s for s in detail.sessions}
    assert per_tag["baseline_static"].memory_jsonl_present is True
    assert per_tag["path_c_cold"].memory_jsonl_present is False
    assert per_tag["path_c_warm"].memory_jsonl_present is False


def test_malformed_session_artifact_is_skipped_not_crashed(tmp_path):
    harness = tmp_path / "harness_malformed_session"
    bundles_root = tmp_path / "bundles"
    _make_minimal_harness_dir(str(harness), tags=list(DEFAULT_3_MODE_TAGS))
    # Corrupt ONE of the three session_artifact.json files.
    bad_path = os.path.join(
        str(harness), "path_c_cold", "session_artifact.json",
    )
    with open(bad_path, "w") as f:
        f.write("{not valid json")

    meta = build_bundle_from_harness_dir(
        harness_dir=str(harness),
        bundles_root=str(bundles_root),
        bundle_id="test_malformed_session",
    )
    # path_c_cold is omitted from session_ids but still tracked in
    # variant_tags (the file exists, it was copied, but the id
    # couldn't be read back).
    assert "path_c_cold" in meta["variant_tags"]
    assert "path_c_cold" not in meta["session_ids"]
    assert any("not readable" in w for w in meta["warnings"])

    repo = BundleRepository(str(bundles_root))
    detail = repo.load_detail("test_malformed_session")
    per_tag = {s.variant_tag: s for s in detail.sessions}
    assert per_tag["path_c_cold"].session_artifact_loadable is False
    # The other two are still loadable.
    assert per_tag["baseline_static"].session_artifact_loadable is True
    assert per_tag["path_c_warm"].session_artifact_loadable is True


def test_malformed_metadata_raises_on_repository_load(tmp_path):
    bundles_root = tmp_path / "bundles"
    build_default_3mode_fixture(str(bundles_root))
    # Corrupt the metadata.json of the committed-shape fixture.
    meta_path = os.path.join(
        str(bundles_root), "fixture_default_3mode_v1", "metadata.json",
    )
    with open(meta_path, "w") as f:
        f.write("{not valid json at all")
    repo = BundleRepository(str(bundles_root))
    # Index tolerates the broken bundle silently.
    idx = repo.build_index()
    assert idx.bundles == []
    # Direct load surfaces the error explicitly.
    with pytest.raises(MalformedBundleError):
        repo.load_detail("fixture_default_3mode_v1")


def test_harness_dir_does_not_exist_raises(tmp_path):
    with pytest.raises(BundlerError):
        build_bundle_from_harness_dir(
            harness_dir=str(tmp_path / "nope"),
            bundles_root=str(tmp_path / "bundles"),
            bundle_id="x",
        )


def test_empty_harness_dir_raises(tmp_path):
    os.makedirs(tmp_path / "empty_harness", exist_ok=True)
    with pytest.raises(BundlerError):
        build_bundle_from_harness_dir(
            harness_dir=str(tmp_path / "empty_harness"),
            bundles_root=str(tmp_path / "bundles"),
            bundle_id="x",
        )


def test_missing_bundle_id_raises(tmp_path):
    os.makedirs(tmp_path / "harness", exist_ok=True)
    with pytest.raises(BundlerError):
        build_bundle_from_harness_dir(
            harness_dir=str(tmp_path / "harness"),
            bundles_root=str(tmp_path / "bundles"),
            bundle_id="",
        )


def test_rebundle_drops_stale_compare_and_thesis(tmp_path):
    """Re-bundling the same bundle_id must erase stale top-level
    artifacts that the new run no longer produces."""
    bundles_root = tmp_path / "bundles"

    # First run: compare + thesis present.
    harness_full = tmp_path / "harness_full"
    _make_minimal_harness_dir(
        str(harness_full),
        tags=list(DEFAULT_3_MODE_TAGS),
        include_compare=True,
        include_thesis=True,
    )
    build_bundle_from_harness_dir(
        harness_dir=str(harness_full),
        bundles_root=str(bundles_root),
        bundle_id="rebundle_reports",
    )
    first_dir = os.path.join(str(bundles_root), "rebundle_reports")
    assert os.path.isfile(os.path.join(first_dir, "compare_report.json"))
    assert os.path.isfile(os.path.join(first_dir, "thesis_report.md"))

    # Second run: same bundle_id, source has neither compare nor
    # thesis. The stale files from the first run must be gone.
    harness_bare = tmp_path / "harness_bare"
    _make_minimal_harness_dir(
        str(harness_bare),
        tags=list(DEFAULT_3_MODE_TAGS),
        include_compare=False,
        include_thesis=False,
    )
    meta = build_bundle_from_harness_dir(
        harness_dir=str(harness_bare),
        bundles_root=str(bundles_root),
        bundle_id="rebundle_reports",
    )
    assert meta["has_compare_report"] is False
    assert meta["has_thesis_report"] is False
    assert not os.path.isfile(os.path.join(first_dir, "compare_report.json"))
    assert not os.path.isfile(os.path.join(first_dir, "thesis_report.md"))

    # Repository agrees.
    repo = BundleRepository(str(bundles_root))
    detail = repo.load_detail("rebundle_reports")
    assert detail.metadata.has_compare_report is False
    assert detail.metadata.has_thesis_report is False
    assert detail.compare_report_raw is None
    assert detail.thesis_report_raw_markdown is None


def test_rebundle_drops_stale_session_subdir(tmp_path):
    """Re-bundling the same bundle_id with fewer variant tags must
    remove the previously-present session subdirectories that are
    no longer part of this run."""
    bundles_root = tmp_path / "bundles"

    # First run: full default 3-mode trio.
    harness_full = tmp_path / "harness_full"
    _make_minimal_harness_dir(str(harness_full), tags=list(DEFAULT_3_MODE_TAGS))
    build_bundle_from_harness_dir(
        harness_dir=str(harness_full),
        bundles_root=str(bundles_root),
        bundle_id="rebundle_shrink",
    )
    first_dir = os.path.join(str(bundles_root), "rebundle_shrink")
    assert os.path.isdir(os.path.join(first_dir, "sessions", "path_c_cold"))

    # Second run: B4 triplet — no ``path_c_cold``.
    harness_b4 = tmp_path / "harness_b4"
    _make_minimal_harness_dir(str(harness_b4), tags=list(B4_TRIPLET_TAGS))
    meta = build_bundle_from_harness_dir(
        harness_dir=str(harness_b4),
        bundles_root=str(bundles_root),
        bundle_id="rebundle_shrink",
    )
    assert meta["variant_set"] == "b4_experiment_triplet"
    # Stale path_c_cold session directory is gone.
    assert not os.path.exists(
        os.path.join(first_dir, "sessions", "path_c_cold")
    )
    # And no .staging.* sibling has been left behind.
    leftover = [
        name for name in os.listdir(str(bundles_root))
        if name.startswith(".rebundle_shrink.staging.")
    ]
    assert leftover == []

    # Repository reflects the new, tighter shape.
    repo = BundleRepository(str(bundles_root))
    detail = repo.load_detail("rebundle_shrink")
    tags = {s.variant_tag for s in detail.sessions}
    assert tags == set(B4_TRIPLET_TAGS)
    assert "path_c_cold" not in tags


def test_detail_surfaces_load_warning_when_compare_file_disappears(tmp_path):
    """If metadata claims compare_report=True but the file has been
    removed out-of-band, the detail response flags it in
    ``load_warnings`` rather than silently returning None."""
    bundles_root = tmp_path / "bundles"
    build_default_3mode_fixture(str(bundles_root))
    compare_path = os.path.join(
        str(bundles_root),
        "fixture_default_3mode_v1",
        "compare_report.json",
    )
    assert os.path.isfile(compare_path)
    os.remove(compare_path)

    repo = BundleRepository(str(bundles_root))
    detail = repo.load_detail("fixture_default_3mode_v1")
    assert detail.metadata.has_compare_report is True
    assert detail.compare_report_raw is None
    assert any(
        "compare_report.json is missing or unreadable" in w
        for w in detail.load_warnings
    ), detail.load_warnings


def test_repackage_then_reload_is_consistent(tmp_path):
    """Round-trip: fixture bundle -> repackage via bundler -> reload."""
    src_root = tmp_path / "src_bundles"
    build_b4_triplet_fixture(str(src_root))
    # Treat the fixture bundle as a "harness dir" — its
    # sessions/{tag}/ subdirectories look like harness
    # subdirectories because of how the fixture was laid out.
    harness_like = tmp_path / "harness_like"
    shutil.copytree(
        os.path.join(str(src_root), "fixture_b4_triplet_v1", "sessions"),
        str(harness_like),
    )
    # Copy compare_report up to match harness shape.
    shutil.copyfile(
        os.path.join(
            str(src_root), "fixture_b4_triplet_v1", "compare_report.json",
        ),
        os.path.join(str(harness_like), "compare_report.json"),
    )
    bundles_out = tmp_path / "bundles_out"
    meta = build_bundle_from_harness_dir(
        harness_dir=str(harness_like),
        bundles_root=str(bundles_out),
        bundle_id="roundtrip_b4",
    )
    assert meta["variant_set"] == "b4_experiment_triplet"
    repo = BundleRepository(str(bundles_out))
    detail = repo.load_detail("roundtrip_b4")
    assert {s.variant_tag for s in detail.sessions} == set(B4_TRIPLET_TAGS)
