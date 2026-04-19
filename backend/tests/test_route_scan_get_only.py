"""Guard: the backend MUST expose only GET routes.

This test is the one hard boundary the B5 Phase-1 foundation
promises to enforce. If a future PR accidentally adds a POST /
PUT / PATCH / DELETE route, this test fails, and the PR is
out-of-scope for B5 Phase-1.
"""

from __future__ import annotations

from starlette.routing import Route

from backend.app import create_app


_FORBIDDEN_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def test_no_write_methods_registered(tmp_path):
    # Use a clean (empty) bundles root — route registration does
    # not depend on any bundle being present.
    app = create_app(bundles_root=str(tmp_path))
    observed: list[tuple[str, str]] = []
    for route in app.routes:
        # Starlette synthesizes HEAD for every GET and injects
        # framework utility routes (OpenAPI, docs, redoc) — those
        # are GET-only by design, but we still scan them.
        if isinstance(route, Route):
            methods = set(route.methods or set())
            for m in methods:
                if m in _FORBIDDEN_METHODS:
                    observed.append((route.path, m))

    assert not observed, (
        f"Forbidden write-path routes registered on the B5 backend: "
        f"{observed}. The Phase-1 foundation is GET-only."
    )


def test_expected_get_routes_present(tmp_path):
    app = create_app(bundles_root=str(tmp_path))
    seen_paths: set[str] = set()
    for route in app.routes:
        if isinstance(route, Route):
            seen_paths.add(route.path)
    for expected in (
        "/healthz",
        "/bundles",
        "/bundles/{bundle_id}",
        "/bundles/{bundle_id}/sessions/{variant_tag}",
    ):
        assert expected in seen_paths, (
            f"expected GET route {expected!r} missing from backend app"
        )
