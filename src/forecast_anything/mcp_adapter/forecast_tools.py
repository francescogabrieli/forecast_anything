"""Forecast jobs, stored snapshots, and historical evidence."""

from __future__ import annotations

from ..backtesting.contracts import BacktestReport, OriginPage
from ..contracts import (
    BacktestJobRequest,
    Candidate,
    ConfiguredRunJobRequest,
    Contract,
    EvaluationJobRequest,
    EvaluationRecord,
    GraphSpec,
    JobView,
    RunJobRequest,
    RunRecord,
    Snapshot,
    SnapshotSeriesPage,
    SnapshotSummary,
)
from ..graph import SourceConfig, parse_node_config
from ..presentations import BacktestPresentation, ForecastPresentation
from .arguments import (
    BacktestArguments,
    BacktestOriginsArguments,
    BacktestPresentationArguments,
    BacktestReadArguments,
    BacktestSummaryArguments,
    CandidateArguments,
    ConfiguredForecastArguments,
    EvaluationArguments,
    ForecastArguments,
    GraphArguments,
    JobArguments,
    RunArguments,
    SnapshotArguments,
    SnapshotSeriesArguments,
    SubmitEvaluationArguments,
)
from .client import CoreRequestError, encode_identifier
from .config import McpConfigError
from .dispatch import ToolContext
from .protocol import Tool
from .summaries import BacktestSummary

_READS = {
    "get_job": ("jobs", "job_id"),
    "get_candidate": ("candidates", "candidate_id"),
    "get_run": ("runs", "run_id"),
    "get_graph": ("graphs", "graph_id"),
    "get_snapshot": ("snapshots", "snapshot_id"),
    "get_evaluation": ("evaluations", "evaluation_id"),
    "get_backtest": ("backtests", "backtest_id"),
    "list_backtest_origins": ("backtests", "backtest_id"),
    "list_run_evaluations": ("runs", "run_id"),
}


TOOLS = (
    Tool(
        "get_job",
        JobArguments,
        JobView,
        "Poll an accepted job for its durable state, result IDs or error. Pending or running work requires an active worker. Use the result IDs to read completed records.",
    ),
    Tool(
        "get_candidate",
        CandidateArguments,
        Candidate,
        "Read a candidate's exact graph, executable status and unresolved support conditions.",
    ),
    Tool(
        "submit_forecast",
        ForecastArguments,
        JobView,
        "Queue an executable candidate unchanged. Supply a stored snapshot ID for each declared source, a timezone-aware cutoff and a replay key. Poll get_job, then read get_forecast_presentation with the run ID.",
        True,
    ),
    Tool(
        "submit_configured_forecast",
        ConfiguredForecastArguments,
        JobView,
        "Queue a forecast against a stored snapshot. Timestral is the default. Supply selection_report_id and optionally challenger_report_id to choose from compatible backtests. Poll get_job and read model_selection on the run. No source read; providers may use configured external resources.",
        mutating=True,
        open_world=True,
    ),
    Tool(
        "submit_backtest",
        BacktestArguments,
        JobView,
        "Submit a bounded historical comparison for an operator-allowed registered CSV source with a replay key. Without watch_id the report is generic and cannot qualify a watch. With watch_id the core requires an exact match to that watch's frozen candidate and at least 30 origins per partition, then applies the eligibility policy to previously unused final windows. Poll get_job, then call summarize_backtest with its backtest_id and watch_id; ordinary source reads may occur.",
        mutating=True,
        open_world=True,
    ),
    Tool(
        "get_backtest",
        BacktestReadArguments,
        BacktestReport,
        "Read the full completed immutable backtest report. For interpretation and final-origin chart points, use summarize_backtest. Missing/pending reports return not_found; poll get_job. No raw archive is exposed.",
    ),
    Tool(
        "get_backtest_presentation",
        BacktestPresentationArguments,
        BacktestPresentation,
        "Read a bounded, chart-ready presentation of a completed backtest by backtest_id. Use get_backtest for the full immutable report or summarize_backtest for a textual comparison and optional watch linkage.",
    ),
    Tool(
        "summarize_backtest",
        BacktestSummaryArguments,
        BacktestSummary,
        "Explain a stored backtest report with partition counts, model-versus-baseline MAE, final-origin chart points, assumptions, and optional current watch linkage. This is read-only: no source reads, provider calls, qualification, or accuracy claim.",
    ),
    Tool(
        "list_backtest_origins",
        BacktestOriginsArguments,
        OriginPage,
        "Read a bounded page of recorded origin outcomes for a completed backtest. No side effects; missing/pending reports return not_found. Failures and exclusions remain explicit.",
    ),
    Tool(
        "get_run",
        RunArguments,
        RunRecord,
        "Read immutable issued forecast values, provider and evidence identities. An issued forecast is not an accuracy score; use list_run_evaluations for recorded validation.",
    ),
    Tool(
        "get_forecast_presentation",
        RunArguments,
        ForecastPresentation,
        "Read a bounded chart and summary for a recorded forecast run by run_id. Includes primary provider, baseline when available and model-selection evidence when recorded. Use get_run when the exact stored output is needed.",
    ),
    Tool("get_graph", GraphArguments, GraphSpec, "Read an exact stored graph version."),
    Tool(
        "get_snapshot",
        SnapshotArguments,
        Snapshot,
        "Read an immutable snapshot; oversized output is refused.",
    ),
    Tool(
        "summarize_snapshot",
        SnapshotArguments,
        SnapshotSummary,
        "Read counts, event and availability coverage, assumptions, and missingness without returning raw observations.",
    ),
    Tool(
        "list_snapshot_series",
        SnapshotSeriesArguments,
        SnapshotSeriesPage,
        "Read a bounded page of per-series coverage, unit samples and revision counts without observation values.",
    ),
    Tool(
        "list_run_evaluations",
        RunArguments,
        list[EvaluationRecord],
        "Read recorded evaluations; an empty list means unevaluated, never qualified.",
    ),
    Tool(
        "get_evaluation",
        EvaluationArguments,
        EvaluationRecord,
        "Read persisted evaluation metrics and assumptions.",
    ),
    Tool(
        "submit_evaluation",
        SubmitEvaluationArguments,
        JobView,
        "Queue scoring of one issued run against a later actuals snapshot from the same source. Supply a replay key and poll get_job for the evaluation ID. Read get_evaluation for the recorded metrics. Single-run scoring does not qualify a watch.",
        True,
    ),
)


async def delegate(context: ToolContext, name: str, arguments: Contract):
    client, allowed = context.client, context.allowed
    if name in _READS:
        resource, identifier = _READS[name]
        path = f"/v1/{resource}"
        if identifier:
            path += "/" + encode_identifier(getattr(arguments, identifier))
        if name == "list_run_evaluations":
            path += "/evaluations"
        params = {"version": arguments.version} if name == "get_graph" else None
        if name == "list_backtest_origins":
            path += "/origins"
            params = {"offset": arguments.offset, "limit": arguments.limit}
        return await client.request("GET", path, params=params)
    if name == "summarize_snapshot":
        return await client.request(
            "GET",
            "/v1/snapshots/" + encode_identifier(arguments.snapshot_id) + "/summary",
        )
    if name == "list_snapshot_series":
        return await client.request(
            "GET",
            "/v1/snapshots/" + encode_identifier(arguments.snapshot_id) + "/series",
            params={"offset": arguments.offset, "limit": arguments.limit},
        )
    if name == "get_forecast_presentation":
        return await client.request(
            "GET",
            "/v1/runs/" + encode_identifier(arguments.run_id) + "/presentation",
        )
    if name in {"summarize_backtest", "get_backtest_presentation"}:
        backtest_id = encode_identifier(arguments.backtest_id)
        params = {}
        if arguments.watch_id is not None:
            params["watch_id"] = arguments.watch_id
        presentation = BacktestPresentation.model_validate(
            await client.request(
                "GET",
                f"/v1/backtests/{backtest_id}/presentation",
                params=params,
            )
        )
        if presentation.summary.backtest_id != arguments.backtest_id:
            raise CoreRequestError("invalid_response")
        return presentation.summary if name == "summarize_backtest" else presentation
    if name == "submit_forecast":
        candidate = Candidate.model_validate(
            await client.request(
                "GET", "/v1/candidates/" + encode_identifier(arguments.candidate_id)
            )
        )
        if not candidate.executable or candidate.unresolved:
            raise CoreRequestError("candidate_not_executable")
        declared = {
            parse_node_config(node).source_id
            for node in candidate.graph.nodes
            if node.kind == "source"
            and isinstance(parse_node_config(node), SourceConfig)
        }
        if set(arguments.snapshot_ids) != declared:
            raise CoreRequestError("invalid_snapshot_bindings")
        request = RunJobRequest(
            kind="run",
            key=arguments.key,
            graph=candidate.graph,
            snapshot_ids=arguments.snapshot_ids,
            as_of=arguments.as_of,
            primary_node_id=arguments.primary_node_id,
        )
        return await client.request(
            "POST", "/v1/jobs", body=request.model_dump(mode="json")
        )
    if name in {"submit_configured_forecast", "submit_backtest"}:
        if name == "submit_backtest":
            if arguments.source_id not in allowed:
                raise McpConfigError("source_forbidden")
            request = BacktestJobRequest(kind="backtest", **arguments.model_dump())
        else:
            request = ConfiguredRunJobRequest(
                kind="configured_run", **arguments.model_dump()
            )
        return await client.request(
            "POST", "/v1/jobs", body=request.model_dump(mode="json")
        )
    if name == "submit_evaluation":
        request = EvaluationJobRequest(kind="evaluation", **arguments.model_dump())
        return await client.request(
            "POST", "/v1/jobs", body=request.model_dump(mode="json")
        )
    raise CoreRequestError("unknown_tool")
