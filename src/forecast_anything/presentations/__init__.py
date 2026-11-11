"""Bounded core projections shared by HTTP and MCP read surfaces."""

from .backtest import (
    BacktestPresentation,
    BacktestSummary,
    FinalOriginPoint,
    WatchBacktestSummary,
    present_backtest,
    summarize_backtest_records,
)
from .forecast import (
    ForecastPresentation,
    ForecastPresentationPoint,
    ForecastProviderUse,
    present_run,
)
from .question import (
    QuestionPresentation,
    QuestionPresentationReference,
    present_question,
)
from .snapshot import snapshot_series_page, summarize_snapshot

__all__ = [
    "BacktestPresentation",
    "BacktestSummary",
    "FinalOriginPoint",
    "ForecastPresentation",
    "ForecastPresentationPoint",
    "ForecastProviderUse",
    "QuestionPresentation",
    "QuestionPresentationReference",
    "WatchBacktestSummary",
    "present_backtest",
    "present_question",
    "present_run",
    "snapshot_series_page",
    "summarize_backtest_records",
    "summarize_snapshot",
]
