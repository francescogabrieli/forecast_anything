"""Tool discovery order and dispatch registration."""

from __future__ import annotations

from . import (
    context_views,
    forecast_tools,
    operation_tools,
    question_tools,
    source_tools,
    watch_tools,
    workspace_tools,
)

_GROUPS = (
    context_views,
    workspace_tools,
    operation_tools,
    question_tools,
    source_tools,
    watch_tools,
    forecast_tools,
)
_DEFINITIONS = {tool.name: tool for group in _GROUPS for tool in group.TOOLS}
DELEGATES = {tool.name: group.delegate for group in _GROUPS for tool in group.TOOLS}

# Discovery preserves the server's existing presentation order.
TOOLS = tuple(
    _DEFINITIONS[name]
    for name in (
        "open_context_view",
        "get_browser_link",
        "get_diagnostics",
        "get_capabilities",
        "create_operation",
        "update_operation",
        "list_operations",
        "get_operation",
        "submit_operation",
        "resume_operation",
        "create_question",
        "list_questions",
        "list_inbox_events",
        "list_source_subscriptions",
        "set_source_subscription",
        "create_webhook_subscription",
        "list_webhook_subscriptions",
        "update_webhook_subscription",
        "list_webhook_deliveries",
        "get_question",
        "update_question",
        "revise_question",
        "list_question_revisions",
        "get_question_revision",
        "link_question_reference",
        "list_question_references",
        "list_sources",
        "create_watch",
        "list_watches",
        "get_watch",
        "update_watch",
        "get_watch_history",
        "summarize_watch_change",
        "preview_csv_source",
        "confirm_csv_source",
        "register_csv_source",
        "get_source_profile",
        "refresh_source",
        "get_job",
        "get_candidate",
        "submit_forecast",
        "submit_configured_forecast",
        "submit_backtest",
        "get_backtest",
        "get_backtest_presentation",
        "summarize_backtest",
        "list_backtest_origins",
        "get_run",
        "get_forecast_presentation",
        "get_question_presentation",
        "get_graph",
        "get_snapshot",
        "summarize_snapshot",
        "list_snapshot_series",
        "list_run_evaluations",
        "get_evaluation",
        "submit_evaluation",
        "get_events",
    )
)
CATALOG = {tool.name: tool for tool in TOOLS}
