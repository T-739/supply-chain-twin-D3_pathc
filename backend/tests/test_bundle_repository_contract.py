"""Backend contract tests driven by the fixture bundles."""

from __future__ import annotations

from backend.repository import (
    BundleNotFoundError,
    BundleRepository,
    MalformedBundleError,
)


def test_index_includes_default_bundle(bundles_root_with_default):
    repo = BundleRepository(bundles_root_with_default)
    idx = repo.build_index()
    assert idx.bundle_schema_version == "1.0"
    assert [b.bundle_id for b in idx.bundles] == ["fixture_default_3mode_v1"]
    entry = idx.bundles[0]
    assert entry.variant_set == "default_3_mode"
    assert entry.variant_tags == [
        "baseline_static", "path_c_cold", "path_c_warm",
    ]
    assert entry.has_compare_report is True
    assert entry.has_thesis_report is True


def test_detail_default_bundle_shape(bundles_root_with_default):
    repo = BundleRepository(bundles_root_with_default)
    detail = repo.load_detail("fixture_default_3mode_v1")
    assert detail.metadata.variant_set == "default_3_mode"
    tags = [s.variant_tag for s in detail.sessions]
    assert tags == ["baseline_static", "path_c_cold", "path_c_warm"]
    # Every session is loadable; every one has an (empty) memory.jsonl.
    for s in detail.sessions:
        assert s.session_artifact_loadable is True
        assert s.memory_jsonl_present is True
        assert s.session_id is not None
        assert s.mode in {"BASELINE_STATIC", "PATH_C_COLD", "PATH_C_WARM"}
    # Compare and thesis are both present.
    assert isinstance(detail.compare_report_raw, dict)
    assert detail.thesis_report_raw_markdown
    assert "fixture thesis report" in detail.thesis_report_raw_markdown.lower()


def test_b4_bundle_has_no_path_c_cold(bundles_root_with_b4):
    repo = BundleRepository(bundles_root_with_b4)
    detail = repo.load_detail("fixture_b4_triplet_v1")
    tags = {s.variant_tag for s in detail.sessions}
    # The critical B4 contract: no path_c_cold.
    assert "path_c_cold" not in tags
    assert tags == {
        "baseline_static",
        "path_c_warm_policy_only",
        "path_c_warm_agent_visible_memory",
    }
    assert detail.metadata.variant_set == "b4_experiment_triplet"


def test_b4_bundle_memory_file_null_safety(bundles_root_with_b4):
    repo = BundleRepository(bundles_root_with_b4)
    detail = repo.load_detail("fixture_b4_triplet_v1")
    per_tag = {s.variant_tag: s for s in detail.sessions}
    # Only baseline_static has a memory.jsonl in this fixture — the
    # B4 fixture is designed to exercise the "some-but-not-all
    # memory files" branch.
    assert per_tag["baseline_static"].memory_jsonl_present is True
    assert per_tag["path_c_warm_policy_only"].memory_jsonl_present is False
    assert (
        per_tag["path_c_warm_agent_visible_memory"].memory_jsonl_present
        is False
    )


def test_b4_bundle_no_thesis_report(bundles_root_with_b4):
    repo = BundleRepository(bundles_root_with_b4)
    detail = repo.load_detail("fixture_b4_triplet_v1")
    assert detail.metadata.has_thesis_report is False
    assert detail.thesis_report_raw_markdown is None
    # But compare report is present, per fixture design.
    assert detail.metadata.has_compare_report is True
    assert isinstance(detail.compare_report_raw, dict)


def test_index_with_both_fixtures(bundles_root_with_both):
    repo = BundleRepository(bundles_root_with_both)
    idx = repo.build_index()
    ids = sorted(b.bundle_id for b in idx.bundles)
    assert ids == ["fixture_b4_triplet_v1", "fixture_default_3mode_v1"]


def test_missing_bundle_raises(bundles_root_with_default):
    repo = BundleRepository(bundles_root_with_default)
    import pytest
    with pytest.raises(BundleNotFoundError):
        repo.load_detail("this_bundle_does_not_exist")


def test_empty_bundles_root(tmp_path):
    repo = BundleRepository(str(tmp_path / "empty_bundles"))
    idx = repo.build_index()
    assert idx.bundles == []
