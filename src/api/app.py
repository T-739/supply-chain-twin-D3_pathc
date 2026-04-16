"""Phase 7 FastAPI application — thin wrapper over the compiled graph.

This module only exposes HTTP routes. It must never duplicate business
logic, evaluation truth, or agent contracts. All structured domain outputs
are passed through verbatim from the graph result.

Usage:
    uvicorn src.api.app:app --reload
Or programmatically:
    from src.api import create_app
    app = create_app()
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

from retrieval import AGENT_RETRIEVAL_MODES  # noqa: E402

from . import runner  # noqa: E402
from .runner import RunnerError  # noqa: E402
from .schemas import (  # noqa: E402
    BatchRequest,
    BatchResponse,
    CaseListResponse,
    CaseSummary,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    ModesResponse,
    RetrievalSummary,
    RunRequest,
    RunResponse,
    SupervisorActionRequest,
    SupervisorInstruction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error_response(exc: RunnerError) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=exc.code, message=exc.message),
    )
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


def _build_run_response(case_id: str, result: dict[str, Any]) -> RunResponse:
    retrieval_summary_dict = runner.extract_retrieval_summary(result)
    retrieval_summary = (
        RetrievalSummary(**retrieval_summary_dict)
        if retrieval_summary_dict else None
    )
    return RunResponse(
        case_id=case_id,
        scenario_id=result.get("scenario_id"),
        scenario_context=result.get("scenario_context"),
        operations_output=result.get("operations_output"),
        cost_output=result.get("cost_output"),
        governance_output=result.get("governance_output"),
        supervisor_output=result.get("supervisor_output"),
        evaluation_result=result.get("evaluation_result"),
        retrieval_summary=retrieval_summary,
        trace_log=result.get("trace_log", []),
        resolved_modes={
            "operations_mode": (result.get("_operations_meta") or {}).get("mode"),
            "governance_mode": (result.get("_governance_meta") or {}).get("mode"),
            "retrieval_mode": (retrieval_summary_dict or {}).get("agent_mode"),
        },
    )


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="Supply Chain Twin API",
        version="0.1.0",
        description=(
            "Thin HTTP surface over the LangGraph-based supply-chain-twin "
            "engine. Endpoints wrap the existing graph invocation path and "
            "expose structured outputs (operations, cost, governance, "
            "supervisor, evaluation) without redefining domain meaning."
        ),
    )

    # --- Discovery ---

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/api/v1/modes", response_model=ModesResponse)
    def modes() -> ModesResponse:
        return ModesResponse(
            retrieval_modes=sorted(AGENT_RETRIEVAL_MODES),
            supervisor_modes=["approve", "verify", "override"],
            operations_modes=["rules", "llm"],
            governance_modes=["rules", "llm"],
        )

    # --- Cases ---

    @app.get("/api/v1/cases", response_model=CaseListResponse)
    def list_cases() -> CaseListResponse:
        case_ids = runner.list_case_ids()
        summaries: list[CaseSummary] = []
        for cid in case_ids:
            try:
                case = runner.load_case(cid) or {}
            except RunnerError:
                case = {}
            summaries.append(CaseSummary(
                case_id=cid,
                scenario_id=case.get("scenario_id"),
                scenario_type=case.get("scenario_type"),
                risk_level=case.get("risk_level"),
            ))
        return CaseListResponse(count=len(summaries), cases=summaries)

    @app.get("/api/v1/cases/{case_id}")
    def get_case(case_id: str) -> dict[str, Any]:
        try:
            case = runner.load_case(case_id)
        except RunnerError as exc:
            raise HTTPException(
                status_code=exc.http_status,
                detail={"code": exc.code, "message": exc.message},
            )
        if case is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "case_not_found",
                        "message": f"case {case_id!r} not found"},
            )
        return case

    # --- Run ---

    @app.post("/api/v1/runs", response_model=RunResponse)
    def run(req: RunRequest) -> RunResponse:
        try:
            result = runner.run_case(
                case_id=req.case_id,
                supervisor_instruction=req.supervisor_instruction.model_dump(
                    exclude_none=True,
                ),
                retrieval_mode=req.retrieval_mode,
                retrieval_k=req.retrieval_k,
                operations_mode=req.operations_mode,
                governance_mode=req.governance_mode,
            )
        except RunnerError as exc:
            raise HTTPException(
                status_code=exc.http_status,
                detail={"code": exc.code, "message": exc.message},
            )
        return _build_run_response(req.case_id, result)

    @app.post("/api/v1/runs/supervisor-action", response_model=RunResponse)
    def run_supervisor_action(req: SupervisorActionRequest) -> RunResponse:
        instruction = SupervisorInstruction(
            mode=req.decision,
            target_action_label=req.target_action_label,
            review_focus=req.review_focus,
        )
        run_req = RunRequest(
            case_id=req.case_id,
            supervisor_instruction=instruction,
            retrieval_mode=req.retrieval_mode,
            retrieval_k=req.retrieval_k,
            operations_mode=req.operations_mode,
            governance_mode=req.governance_mode,
        )
        return run(run_req)

    # --- Batch ---

    @app.post("/api/v1/batch", response_model=BatchResponse)
    def run_batch(req: BatchRequest) -> BatchResponse:
        # Import lazily to avoid pulling the batch script on non-batch calls.
        sys.path.insert(0, str(_PROJECT_DIR / "scripts"))
        try:
            import phase6_batch_eval as phase6
        finally:
            sys.path.pop(0)

        supervisor_modes = tuple(req.supervisor_modes or phase6.DEFAULT_SUPERVISOR_MODES)
        retrieval_modes = tuple(req.retrieval_modes or phase6.DEFAULT_RETRIEVAL_MODES)

        rows = phase6.build_observability_rows(
            supervisor_modes=supervisor_modes,
            retrieval_modes=retrieval_modes,
            case_ids=req.case_ids,
            operations_mode=req.operations_mode,
            governance_mode=req.governance_mode,
            retrieval_k=req.retrieval_k,
        )
        agg = phase6.aggregate_report(rows)

        persisted: dict[str, str] | None = None
        if req.persist:
            out_dir = _PROJECT_DIR / "data" / "phase6_eval"
            out_dir.mkdir(parents=True, exist_ok=True)
            rows_path = out_dir / "rows.csv"
            json_path = out_dir / "summary.json"
            md_path = out_dir / "report.md"
            phase6.write_rows_csv(rows, rows_path)
            phase6.write_summary_json(rows, agg, json_path)
            md_path.write_text(phase6.render_markdown(rows, agg))
            persisted = {
                "rows_csv": str(rows_path),
                "summary_json": str(json_path),
                "report_md": str(md_path),
            }

        return BatchResponse(
            row_count=len(rows),
            rows=rows,
            aggregations=agg,
            persisted_paths=persisted,
        )

    @app.get("/api/v1/batch/latest")
    def read_latest_batch() -> dict[str, Any]:
        json_path = _PROJECT_DIR / "data" / "phase6_eval" / "summary.json"
        if not json_path.is_file():
            raise HTTPException(
                status_code=404,
                detail={"code": "no_batch_artifacts",
                        "message": "no persisted batch summary found; "
                                   "POST /api/v1/batch with persist=true "
                                   "to create one."},
            )
        try:
            return json.loads(json_path.read_text())
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"code": "batch_unreadable",
                        "message": f"could not parse summary.json: {exc}"},
            )

    return app


# Default app instance for `uvicorn src.api.app:app`.
app = create_app()
