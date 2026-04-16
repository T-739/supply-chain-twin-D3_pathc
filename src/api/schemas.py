"""Phase 7 API schemas — thin pydantic wrappers around existing domain outputs.

These models do not redefine any domain meaning. Structured engine outputs
(operations_output, governance_output, supervisor_output, evaluation_result)
are passed through verbatim as ``dict[str, Any]`` so the frozen schemas
defined elsewhere remain authoritative.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "supply-chain-twin-api"
    version: str = "0.1.0"


class ModesResponse(BaseModel):
    retrieval_modes: list[str]
    supervisor_modes: list[str]
    operations_modes: list[str]
    governance_modes: list[str]


class CaseSummary(BaseModel):
    case_id: str
    scenario_id: str | None = None
    scenario_type: str | None = None
    risk_level: str | None = None


class CaseListResponse(BaseModel):
    count: int
    cases: list[CaseSummary]


# ---------------------------------------------------------------------------
# Run request / response
# ---------------------------------------------------------------------------


SupervisorMode = Literal["approve", "verify", "override"]


class SupervisorInstruction(BaseModel):
    """Mirror of the engine's supervisor_instruction dict.

    The engine accepts a plain dict; this schema gives it a stable public
    contract. `target_action_label` is required when mode == "override".
    """

    mode: SupervisorMode
    target_action_label: str | None = None
    review_focus: str | None = None
    notes: str | None = None


class RunRequest(BaseModel):
    """Request body for `POST /api/v1/runs`.

    All mode fields are optional. Omitted values fall through to the engine
    defaults (which are the safe / deterministic modes).
    """

    case_id: str = Field(..., description="Case identifier, e.g. 'M01'")
    supervisor_instruction: SupervisorInstruction = Field(
        default_factory=lambda: SupervisorInstruction(mode="approve"),
    )
    retrieval_mode: str | None = None
    retrieval_k: int | None = Field(default=None, ge=1, le=64)
    operations_mode: Literal["rules", "llm"] | None = None
    governance_mode: Literal["rules", "llm"] | None = None


class SupervisorActionRequest(BaseModel):
    """Request body for `POST /api/v1/runs/supervisor-action` — convenience
    endpoint that builds a SupervisorInstruction from a flat payload.
    """

    case_id: str
    decision: SupervisorMode
    target_action_label: str | None = None
    review_focus: str | None = None
    retrieval_mode: str | None = None
    retrieval_k: int | None = Field(default=None, ge=1, le=64)
    operations_mode: Literal["rules", "llm"] | None = None
    governance_mode: Literal["rules", "llm"] | None = None


class RetrievalSummary(BaseModel):
    agent_mode: str | None = None
    engine_mode: str | None = None
    query_hash: str | None = None
    k: int | None = None
    candidate_count: int | None = None
    contextualized: bool | None = None
    reranker_used: bool | None = None
    fallback_used: bool | None = None
    embedder_name: str | None = None
    reranker_name: str | None = None
    error: str | None = None
    top_chunk_ids: list[str | None] | None = None
    multi_query: dict[str, Any] | None = None
    self_query: dict[str, Any] | None = None
    compression: dict[str, Any] | None = None


class RunResponse(BaseModel):
    case_id: str
    scenario_id: str | None = None
    scenario_context: dict[str, Any] | None = None

    operations_output: dict[str, Any] | None = None
    cost_output: dict[str, Any] | None = None
    governance_output: dict[str, Any] | None = None
    supervisor_output: dict[str, Any] | None = None
    evaluation_result: dict[str, Any] | None = None

    retrieval_summary: RetrievalSummary | None = None
    trace_log: list[dict[str, Any]] = Field(default_factory=list)

    # Pass-through mode info for client reflection.
    resolved_modes: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Batch (Phase 6 bridge)
# ---------------------------------------------------------------------------


class BatchRequest(BaseModel):
    case_ids: list[str] | None = None
    supervisor_modes: list[SupervisorMode] | None = None
    retrieval_modes: list[str] | None = None
    operations_mode: Literal["rules", "llm"] = "rules"
    governance_mode: Literal["rules", "llm"] = "rules"
    retrieval_k: int = Field(default=4, ge=1, le=64)
    persist: bool = Field(
        default=False,
        description="If True, write rows.csv / summary.json / report.md "
                    "under data/phase6_eval/.",
    )


class BatchResponse(BaseModel):
    row_count: int
    rows: list[dict[str, Any]]
    aggregations: dict[str, Any]
    persisted_paths: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
