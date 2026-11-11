"""Command and argument definitions for the local CLI."""

import argparse
from collections.abc import Collection
from pathlib import Path


def build_parser(timestral_models: Collection[str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forecast-anything")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Freeze CSV observations and emit a forecast")
    run.add_argument("graph", type=Path)
    run.add_argument("--data", type=Path, required=True)
    run.add_argument("--as-of", required=True, help="ISO 8601 origin with timezone")
    run.add_argument("--db", type=Path, required=True)
    run.add_argument(
        "--primary-node-id", help="Primary terminal output for a raw graph"
    )
    model = commands.add_parser(
        "model", help="Check or explicitly prepare pinned local Timestral"
    )
    model_actions = model.add_subparsers(dest="model_action", required=True)
    model_status = model_actions.add_parser(
        "status", help="Inspect dependency provenance and local cache without loading"
    )
    model_prepare = model_actions.add_parser(
        "prepare",
        help="Install pinned model code and download weights if needed; review the Modified MIT weights license",
    )
    for action in (model_status, model_prepare):
        target_model = action.add_mutually_exclusive_group()
        target_model.add_argument("--config", type=Path)
        target_model.add_argument("--timestral-model", choices=timestral_models)
    show = commands.add_parser("show", help="Read a stored immutable emission")
    show.add_argument("run_id")
    show.add_argument("--db", type=Path, required=True)
    serve = commands.add_parser("serve", help="Serve the authenticated local API")
    serve.add_argument("--db", type=Path, required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--socket-fd", type=int, help=argparse.SUPPRESS)
    worker = commands.add_parser("worker", help="Process the shared durable queue")
    worker.add_argument("--db", type=Path, required=True)
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--verify-model", action="store_true")
    worker.add_argument("--limit", type=int, default=10)
    worker.add_argument("--poll-seconds", type=float, default=1)
    worker.add_argument("--lease-seconds", type=int, default=60)
    init = commands.add_parser("init", help="Create a private local workspace")
    init.add_argument("--workspace", type=Path, required=True)
    init.add_argument("--csv-root", type=Path, required=True)
    init.add_argument("--port", type=int, default=8000)
    init.add_argument("--timestral-model", choices=timestral_models)
    up = commands.add_parser("up", help="Run the local API and worker together")
    target = up.add_mutually_exclusive_group(required=True)
    target.add_argument("--db", type=Path)
    target.add_argument("--config", type=Path)
    up.add_argument("--port", type=int)
    up.add_argument(
        "--verify-model",
        action="store_true",
        help="Load prepared Timestral weights in the worker at startup",
    )
    setup = commands.add_parser(
        "setup",
        help="Set up a macOS login service and register its MCP server with Codex",
    )
    setup.add_argument(
        "--workspace",
        type=Path,
        default=Path.home() / "Library/Application Support/Forecast Anything",
    )
    setup.add_argument("--csv-root", type=Path)
    setup.add_argument("--port", type=int)
    setup.add_argument("--codex-bin", default="codex")
    setup.add_argument("--codex-name")
    setup.add_argument("--timestral-model", choices=timestral_models)
    setup.add_argument(
        "--prepare-model",
        action="store_true",
        help="Explicitly allow downloading pinned Timestral weights after reviewing the model license",
    )
    service = commands.add_parser("service", help="Manage the macOS user LaunchAgent")
    service.add_argument(
        "action", choices=("install", "start", "status", "stop", "restart", "remove")
    )
    service.add_argument("--config", type=Path, required=True)
    doctor = commands.add_parser(
        "doctor", help="Diagnose the local workspace and suggest recovery"
    )
    doctor.add_argument("--config", type=Path, required=True)
    status = commands.add_parser(
        "status", help="Check the configured local API and worker"
    )
    status.add_argument("--config", type=Path, required=True)
    mcp = commands.add_parser("mcp", help="Serve optional MCP tools over stdio")
    mcp.add_argument("--config", type=Path)
    permissions = commands.add_parser(
        "permissions", help="Manage persistent MCP source permissions"
    )
    permission_actions = permissions.add_subparsers(
        dest="permission_action", required=True
    )
    permission_list = permission_actions.add_parser("list", help="List source grants")
    permission_list.add_argument("--config", type=Path, required=True)
    permission_grant = permission_actions.add_parser("grant", help="Grant a source ID")
    permission_grant.add_argument("source_id")
    permission_grant.add_argument("--config", type=Path, required=True)
    permission_revoke = permission_actions.add_parser(
        "revoke", help="Revoke a source ID"
    )
    permission_revoke.add_argument("source_id")
    permission_revoke.add_argument("--config", type=Path, required=True)
    return parser
