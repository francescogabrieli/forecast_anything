"""Job submissions, run and backtest results, and their input records."""

from typing import Annotated

from fastapi import Query

from ..backtesting.contracts import BacktestReport, OriginPage
from ..contracts import (
    EvaluationRecord,
    GraphSpec,
    JobRequest,
    JobView,
    RunRecord,
    Snapshot,
    SnapshotSeriesPage,
    SnapshotSummary,
)
from ..discovery.agent_gateway import AgentOperationRequest, AgentOperationResponse
from ..presentations import (
    BacktestPresentation,
    ForecastPresentation,
)


def register_jobs(api, service):
    @api.post("/jobs", response_model=JobView, status_code=202)
    def submit(request: JobRequest):
        return service.submit(request)

    @api.post("/agent/operations", response_model=AgentOperationResponse)
    def agent_operation(request: AgentOperationRequest):
        return service.agent_operation(request)

    @api.get("/jobs/{job_id}", response_model=JobView)
    def job(job_id: str):
        return service.job(job_id)

    @api.get("/runs/{run_id}", response_model=RunRecord)
    def run(run_id: str):
        return service.ledger.get_run(run_id)

    @api.get("/runs/{run_id}/presentation", response_model=ForecastPresentation)
    def forecast_presentation(run_id: str):
        return service.forecast_presentation(run_id)

    @api.get("/runs/{run_id}/evaluations", response_model=list[EvaluationRecord])
    def run_evaluations(run_id: str):
        return service.ledger.evaluations_for_run(run_id)

    @api.get("/evaluations/{evaluation_id}", response_model=EvaluationRecord)
    def evaluation(evaluation_id: str):
        return service.ledger.get_evaluation(evaluation_id)

    @api.get("/reports/{report_id}/presentation", response_model=BacktestPresentation)
    def report_presentation(report_id: str):
        report = service.report_by_id(report_id)
        return service.backtest_presentation(report.backtest_id, watch_id=None)

    @api.get("/reports/{report_id}/origins", response_model=OriginPage)
    def report_origins(
        report_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=50)] = 25,
    ):
        report = service.report_by_id(report_id)
        return service.backtest_origins(report.backtest_id, offset=offset, limit=limit)

    @api.get("/backtests/{backtest_id}", response_model=BacktestReport)
    def backtest(backtest_id: str):
        return service.backtest(backtest_id)

    @api.get(
        "/backtests/{backtest_id}/presentation",
        response_model=BacktestPresentation,
    )
    def backtest_presentation(
        backtest_id: str,
        watch_id: Annotated[str | None, Query(min_length=1)] = None,
    ):
        return service.backtest_presentation(backtest_id, watch_id=watch_id)

    @api.get("/backtests/{backtest_id}/origins", response_model=OriginPage)
    def backtest_origins(
        backtest_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=50)] = 25,
    ):
        return service.backtest_origins(backtest_id, offset=offset, limit=limit)

    @api.get("/snapshots/{snapshot_id}", response_model=Snapshot)
    def snapshot(snapshot_id: str):
        return service.ledger.get_snapshot(snapshot_id)

    @api.get("/snapshots/{snapshot_id}/summary", response_model=SnapshotSummary)
    def snapshot_summary(snapshot_id: str):
        return service.snapshot_summary(snapshot_id)

    @api.get("/snapshots/{snapshot_id}/series", response_model=SnapshotSeriesPage)
    def snapshot_series(
        snapshot_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.snapshot_series(snapshot_id, offset=offset, limit=limit)

    @api.get("/graphs/{graph_id}", response_model=GraphSpec)
    def graph(graph_id: str, version: Annotated[int, Query(gt=0)] = 1):
        return service.ledger.get_graph(graph_id, version)
