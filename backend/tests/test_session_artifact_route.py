"""Phase 3A Session Runtime additive route contract tests."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.repository import BundleNotFoundError, BundleRepository


def test_load_session_artifact_default_bundle(bundles_root_with_default):
    repo = BundleRepository(bundles_root_with_default)
    art = repo.load_session_artifact(
        "fixture_default_3mode_v1", "path_c_warm",
    )
    assert art.session_artifact_loadable is True
    assert art.session_artifact_raw is not None
    assert art.variant_tag == "path_c_warm"
    # The raw artifact carries event_records structurally; we do
    # not reinterpret them here, just check they are present.
    assert isinstance(art.session_artifact_raw.get("event_records"), list)


def test_load_session_artifact_b4_triplet(bundles_root_with_b4):
    repo = BundleRepository(bundles_root_with_b4)
    # B4 triplet has no path_c_cold — asking for it must 404.
    import pytest
    with pytest.raises(BundleNotFoundError):
        repo.load_session_artifact(
            "fixture_b4_triplet_v1", "path_c_cold",
        )
    # The three real tags load cleanly.
    for tag in (
        "baseline_static",
        "path_c_warm_policy_only",
        "path_c_warm_agent_visible_memory",
    ):
        art = repo.load_session_artifact("fixture_b4_triplet_v1", tag)
        assert art.session_artifact_loadable is True
        assert art.variant_tag == tag


def test_http_session_artifact_route(bundles_root_with_default):
    app = create_app(bundles_root=bundles_root_with_default)
    client = TestClient(app)
    resp = client.get(
        "/bundles/fixture_default_3mode_v1/sessions/path_c_warm"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["bundle_id"] == "fixture_default_3mode_v1"
    assert body["variant_tag"] == "path_c_warm"
    assert body["session_artifact_loadable"] is True
    assert isinstance(body["session_artifact_raw"], dict)


def test_http_session_artifact_unknown_tag_404(bundles_root_with_default):
    app = create_app(bundles_root=bundles_root_with_default)
    client = TestClient(app)
    resp = client.get(
        "/bundles/fixture_default_3mode_v1/sessions/path_c_cold_typo"
    )
    assert resp.status_code == 404


def test_http_session_artifact_unreadable(
    bundles_root_with_default, tmp_path,
):
    # Corrupt one session_artifact.json: the repository must
    # still respond 200 with session_artifact_loadable=False and
    # a non-empty load_warnings list.
    target = os.path.join(
        bundles_root_with_default,
        "fixture_default_3mode_v1",
        "sessions",
        "path_c_warm",
        "session_artifact.json",
    )
    with open(target, "w") as f:
        f.write("{not json")
    app = create_app(bundles_root=bundles_root_with_default)
    client = TestClient(app)
    resp = client.get(
        "/bundles/fixture_default_3mode_v1/sessions/path_c_warm"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_artifact_loadable"] is False
    assert body["session_artifact_raw"] is None
    assert body["load_warnings"]


def test_http_session_artifact_missing_file(
    bundles_root_with_default,
):
    # Remove the session_artifact.json entirely.
    target = os.path.join(
        bundles_root_with_default,
        "fixture_default_3mode_v1",
        "sessions",
        "path_c_warm",
        "session_artifact.json",
    )
    os.remove(target)
    app = create_app(bundles_root=bundles_root_with_default)
    client = TestClient(app)
    resp = client.get(
        "/bundles/fixture_default_3mode_v1/sessions/path_c_warm"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_artifact_loadable"] is False
    assert body["session_artifact_raw"] is None


def test_session_artifact_route_method_guard(bundles_root_with_default):
    """POST to the new route must be rejected."""
    app = create_app(bundles_root=bundles_root_with_default)
    client = TestClient(app)
    resp = client.post(
        "/bundles/fixture_default_3mode_v1/sessions/path_c_warm",
        json={"x": 1},
    )
    assert resp.status_code in (404, 405)
