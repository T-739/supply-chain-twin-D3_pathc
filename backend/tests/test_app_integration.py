"""End-to-end HTTP smoke over the GET-only backend app.

Uses fastapi/starlette's TestClient, which does not require any
running server. These tests exercise the app factory + repository
wiring on both fixture variants.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import create_app


def test_healthz(bundles_root_with_default):
    app = create_app(bundles_root=bundles_root_with_default)
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["bundles_root"] == bundles_root_with_default


def test_bundles_index(bundles_root_with_both):
    app = create_app(bundles_root=bundles_root_with_both)
    client = TestClient(app)
    resp = client.get("/bundles")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bundle_schema_version"] == "1.0"
    ids = sorted(b["bundle_id"] for b in body["bundles"])
    assert ids == ["fixture_b4_triplet_v1", "fixture_default_3mode_v1"]


def test_bundle_detail_default(bundles_root_with_default):
    app = create_app(bundles_root=bundles_root_with_default)
    client = TestClient(app)
    resp = client.get("/bundles/fixture_default_3mode_v1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metadata"]["variant_set"] == "default_3_mode"
    tags = [s["variant_tag"] for s in body["sessions"]]
    assert tags == ["baseline_static", "path_c_cold", "path_c_warm"]


def test_bundle_detail_b4(bundles_root_with_b4):
    app = create_app(bundles_root=bundles_root_with_b4)
    client = TestClient(app)
    resp = client.get("/bundles/fixture_b4_triplet_v1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metadata"]["variant_set"] == "b4_experiment_triplet"
    assert body["thesis_report_raw_markdown"] is None
    tags = [s["variant_tag"] for s in body["sessions"]]
    assert "path_c_cold" not in tags


def test_bundle_detail_404(bundles_root_with_default):
    app = create_app(bundles_root=bundles_root_with_default)
    client = TestClient(app)
    resp = client.get("/bundles/does_not_exist")
    assert resp.status_code == 404


def test_bundle_post_not_allowed(bundles_root_with_default):
    """Even if a caller TRIES a POST, the router must refuse it."""
    app = create_app(bundles_root=bundles_root_with_default)
    client = TestClient(app)
    resp = client.post("/bundles/fixture_default_3mode_v1", json={"x": 1})
    # 405 Method Not Allowed on an existing GET-only path is the
    # correct FastAPI behavior; 404 is also acceptable if no route
    # matches. Either way, the server MUST NOT accept the write.
    assert resp.status_code in (404, 405)
