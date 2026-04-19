"""B5 backend FastAPI scaffold — GET-only.

This app exposes a read-only view over the B5 bundle layout
(see ``docs/B5_BUNDLE_CONTRACT.md``). It MUST NOT grow any
write-path routes in this slice; the route-scan test in
``backend/tests/test_route_scan_get_only.py`` enforces that.

Run locally (optional, for manual smoke):

    BUNDLES_ROOT=$PWD/bundles \\
    uvicorn backend.app:app --port 8001

The production-shape concerns (auth, rate-limiting, CORS) are
deliberately deferred — this is the Phase-1 foundation, not a
deployable service.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException

from backend.models.bundle_models import (
    BundleDetailResponse,
    BundleIndexResponse,
    SessionArtifactResponse,
)
from backend.repository import (
    BundleNotFoundError,
    BundleRepository,
    MalformedBundleError,
)


_DEFAULT_BUNDLES_ROOT_ENV = "B5_BUNDLES_ROOT"


def _resolve_bundles_root() -> str:
    env = os.environ.get(_DEFAULT_BUNDLES_ROOT_ENV)
    if env:
        return env
    # Fallback: repo-root/bundles — matches the on-disk layout the
    # bundler and fixture_builder both write into.
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    return os.path.join(repo_root, "bundles")


def create_app(*, bundles_root: Optional[str] = None) -> FastAPI:
    """Factory so tests can inject a different ``bundles_root``.

    The module-level ``app`` uses the env/default resolver so a
    ``uvicorn backend.app:app`` style run still works.
    """
    repo = BundleRepository(bundles_root or _resolve_bundles_root())
    fastapi_app = FastAPI(
        title="B5 Bundle BFF (read-only foundation)",
        version="0.1.0",
        description=(
            "Phase-1 read-only surface over the B5 bundle contract. "
            "No write-path routes; no runtime decision logic."
        ),
    )

    @fastapi_app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "bundles_root": repo.root}

    @fastapi_app.get("/bundles", response_model=BundleIndexResponse)
    def list_bundles() -> BundleIndexResponse:
        return repo.build_index()

    @fastapi_app.get(
        "/bundles/{bundle_id}",
        response_model=BundleDetailResponse,
    )
    def get_bundle(bundle_id: str) -> BundleDetailResponse:
        try:
            return repo.load_detail(bundle_id)
        except BundleNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MalformedBundleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @fastapi_app.get(
        "/bundles/{bundle_id}/sessions/{variant_tag}",
        response_model=SessionArtifactResponse,
    )
    def get_session_artifact(
        bundle_id: str, variant_tag: str,
    ) -> SessionArtifactResponse:
        """Serve one session's ``session_artifact.json`` verbatim.

        Added for Phase 3A Session Runtime — the shallow
        per-bundle detail does not carry per-event payloads.
        Read-only, no reinterpretation of event records, no
        compare/thesis math.
        """
        try:
            return repo.load_session_artifact(bundle_id, variant_tag)
        except BundleNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MalformedBundleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return fastapi_app


app = create_app()
