"""Phase 7 API layer — thin FastAPI wrapper around the LangGraph engine.

This package exposes a minimal, stable HTTP contract over the existing
compiled graph in ``src/graph.py``. It does not duplicate business logic,
does not redefine evaluation truth, and does not alter frozen schemas.

Entry points:
    src.api.app   — FastAPI application factory
    src.api.schemas — request / response pydantic models
    src.api.runner  — graph-invocation helper used by the routes
"""

from .app import create_app

__all__ = ["create_app"]
