"""Local CSV-to-ledger CLI; stdout is a RunRecord, stderr structured errors."""

import argparse
import json
import os
import signal
import socket
import sqlite3
import sys
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from .connectors.csv import load_csv
from .contracts import DomainError, GraphSpec
from .graph import SourceConfig, parse_node_config
from .providers.configuration import configured_providers
from .runtime import Runtime
from .store import Ledger
from .temporal import freeze


def _stop_continuous_worker(signum, frame):
    raise KeyboardInterrupt


def _run(args):
    origin = datetime.fromisoformat(args.as_of)
    if origin.tzinfo is None or origin.utcoffset() is None:
        raise DomainError("naive_timestamp", {"field": "as_of"})
    origin = origin.astimezone(timezone.utc)
    spec = GraphSpec.model_validate_json(args.graph.read_text(encoding="utf-8"))
    sources = [parse_node_config(node) for node in spec.nodes if node.kind == "source"]
    # A single --data file has no source discriminator. Require one unambiguous
    # declared binding rather than silently assigning a file to several sources.
    if len(sources) != 1 or not isinstance(sources[0], SourceConfig):
        raise DomainError(
            "ambiguous_csv_binding",
            {"reason": "--data requires exactly one source node"},
        )
    snapshot = freeze(load_csv(args.data), origin)
    snapshots = {sources[0].source_id: snapshot}
    content = {
        "graph": spec.model_dump(mode="json"),
        "as_of": origin.isoformat(),
        "snapshots": {
            name: value.model_dump(mode="json") for name, value in snapshots.items()
        },
    }
    if args.primary_node_id is not None:
        content["primary_node_id"] = args.primary_node_id
    key = sha256(
        json.dumps(
            content, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    return Runtime(
        Ledger(args.db),
        configured_providers(),
        {},
        lambda: datetime.now(timezone.utc),
        required_provider="timestral",
    ).run(spec, snapshots, origin, key, primary_node_id=args.primary_node_id)


def main() -> int:
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
    model_actions.add_parser(
        "status", help="Inspect dependency provenance and local cache without loading"
    )
    model_actions.add_parser(
        "prepare",
        help="Download pinned weights if needed and load on CPU; review the Modified MIT weights license",
    )
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
    args = parser.parse_args()
    if args.command in {"setup", "service", "doctor"}:
        from .diagnostics import diagnose_workspace
        from .setup_local import LaunchAgent, setup
        from .workspace_config import load_workspace

        try:
            executable = Path(sys.argv[0]).resolve()
            if args.command in {"setup", "service"} and (
                executable.name != "forecast-anything"
                or not os.access(executable, os.X_OK)
            ):
                raise DomainError(
                    "installed_entrypoint_required",
                    {
                        "recovery": "Run the installed forecast-anything executable from its environment bin directory."
                    },
                )
            if args.command == "setup":
                result = setup(
                    args.workspace,
                    args.csv_root,
                    args.port,
                    args.codex_bin,
                    args.codex_name,
                    args.prepare_model,
                    executable,
                )
            elif args.command == "service":
                result = LaunchAgent(args.config, executable).run(args.action)
            else:
                result = diagnose_workspace(load_workspace(args.config))
        except DomainError as error:
            print(error.model_dump_json(), file=sys.stderr)
            return 2
        except (OSError, ValueError):
            print(
                json.dumps(
                    {
                        "code": "local_configuration_error",
                        "details": {
                            "recovery": "Check that the workspace config is valid and the workspace and service directories are accessible."
                        },
                    }
                ),
                file=sys.stderr,
            )
            return 2
        print(json.dumps(result))
        if args.command == "setup":
            registered = result["codex"]["registration"] in {"added", "existing"}
            return 0 if result["ready"] and registered else 1
        if args.command == "doctor" or args.action == "status":
            return 0 if result["ready"] else 1
        return 0
    if args.command == "permissions":
        from .workspace_config import manage_source_permissions

        try:
            result = manage_source_permissions(
                args.config, args.permission_action, getattr(args, "source_id", None)
            )
        except (OSError, ValueError) as error:
            print(
                json.dumps(
                    {"code": "permission_error", "details": {"message": str(error)}}
                ),
                file=sys.stderr,
            )
            return 2
        print(json.dumps(result))
        return 0
    if args.command in {"init", "status", "up", "mcp"}:
        from .workspace_config import apply_workspace, create_workspace, load_workspace

        try:
            if args.command == "init":
                path = create_workspace(args.workspace, args.csv_root, args.port)
                print(json.dumps({"config": str(path)}))
                return 0
            if getattr(args, "config", None):
                config = load_workspace(args.config)
                apply_workspace(config)
            if args.command == "status":
                from .workspace_config import check_api

                result = check_api(config)
                print(json.dumps(result))
                return (
                    0
                    if result["api"] == "available" and result["worker"] == "running"
                    else 1
                )
            if args.command == "up" and args.config:
                if args.port is not None:
                    raise ValueError("--port cannot be used with --config")
                args.db, args.port = Path(config["db"]), config["port"]
        except FileExistsError:
            print(
                "Workspace config already exists; it was not changed.", file=sys.stderr
            )
            return 2
        except (OSError, ValueError) as error:
            print(f"Workspace configuration error: {error}", file=sys.stderr)
            return 2
    if args.command == "up":
        from .local_services import run_services

        try:
            return run_services(
                args.db,
                "127.0.0.1",
                args.port if args.port is not None else 8000,
                verify_model=args.verify_model,
            )
        except DomainError as error:
            print(error.model_dump_json(), file=sys.stderr)
            return 2
        except (OSError, sqlite3.Error) as error:
            print(
                json.dumps({"code": "input_error", "details": {"message": str(error)}}),
                file=sys.stderr,
            )
            return 2
    if args.command == "mcp":
        try:
            from .mcp_adapter.server import run_stdio
        except ImportError:
            print(
                "Install forecast-anything[mcp] to use the MCP stdio server.",
                file=sys.stderr,
            )
            return 2
        return run_stdio()
    try:
        if args.command == "model":
            provider = configured_providers()["timestral"]
            result = (
                provider.prepare_model()
                if args.model_action == "prepare"
                else provider.check_model()
            )
            print(json.dumps(result))
            return 0 if result["status"] in {"cached", "loaded"} else 1
        if args.command in {"serve", "worker"}:
            from .local_services import worker_lock
            from .operators import register_builtin_operators

            ownership = (
                worker_lock(args.db) if args.command == "worker" else nullcontext()
            )
            with ownership:
                ledger = Ledger(args.db)
                runtime = Runtime(
                    ledger,
                    configured_providers(),
                    register_builtin_operators(),
                    lambda: datetime.now(timezone.utc),
                    required_provider="timestral",
                )
                if args.command == "serve":
                    import uvicorn

                    from .api.app import create_app

                    app = create_app(
                        ledger,
                        runtime,
                        os.environ.get("FORECAST_ANYTHING_WORKSPACE_TOKEN", ""),
                        agent_token=os.environ.get(
                            "FORECAST_ANYTHING_AGENT_CORE_TOKEN"
                        ),
                        expected_worker_id=os.environ.get(
                            "FORECAST_ANYTHING_SUPERVISOR_ID"
                        ),
                        supervisor_pid=int(
                            os.environ["FORECAST_ANYTHING_SUPERVISOR_PID"]
                        )
                        if "FORECAST_ANYTHING_SUPERVISOR_PID" in os.environ
                        else None,
                        console_origins=tuple(
                            origin.strip()
                            for origin in os.environ.get(
                                "FORECAST_ANYTHING_CONSOLE_ORIGINS", ""
                            ).split(",")
                            if origin.strip()
                        ),
                    )
                    if args.socket_fd is None:
                        uvicorn.run(
                            app, host=args.host, port=args.port, access_log=False
                        )
                    else:
                        with socket.socket(fileno=args.socket_fd) as listener:
                            uvicorn.Server(uvicorn.Config(app, access_log=False)).run(
                                sockets=[listener]
                            )
                    return 0
                from .discovery.agent_gateway import AgentGateway
                from .jobs import JobQueue
                from .worker import Worker

                if args.poll_seconds <= 0:
                    raise DomainError("invalid_poll_interval", {})
                agent_url = os.environ.get("FORECAST_ANYTHING_AGENT_URL")
                bridge_token = os.environ.get("FORECAST_ANYTHING_AGENT_BRIDGE_TOKEN")
                if bool(agent_url) != bool(bridge_token):
                    raise DomainError("agent_gateway_config_incomplete", {})
                gateway = (
                    AgentGateway(agent_url, token=bridge_token)
                    if agent_url and bridge_token
                    else None
                )
                worker = Worker(
                    runtime,
                    JobQueue(ledger),
                    discovery_gateway=gateway,
                    lease_seconds=args.lease_seconds,
                )
                if owner := os.environ.get("FORECAST_ANYTHING_SUPERVISOR_ID"):
                    worker.owner = owner
                if args.once:
                    if args.verify_model:
                        runtime.providers["timestral"].verify_cached_model()
                    completed = worker.run_due(runtime.clock(), limit=args.limit)
                    print(json.dumps({"job_ids": completed}))
                    return 0
                from .forecast_policy import model_readiness

                previous_sigterm = signal.signal(
                    signal.SIGTERM, _stop_continuous_worker
                )
                try:
                    model_error = None
                    if args.verify_model:
                        try:
                            runtime.providers["timestral"].verify_cached_model()
                        except DomainError as error:
                            model_error = error.code
                    with worker.liveness(
                        model_status=lambda: (
                            model_error or model_readiness(runtime)["status"]
                        )
                    ):
                        while True:
                            worker.run_due(runtime.clock(), limit=args.limit)
                            time.sleep(args.poll_seconds)
                finally:
                    signal.signal(signal.SIGTERM, previous_sigterm)
        record = (
            _run(args)
            if args.command == "run"
            else Ledger(args.db).get_run(args.run_id)
        )
        print(record.model_dump_json())
        return 0 if record.state == "completed" else 1
    except KeyboardInterrupt:
        return 0
    except DomainError as error:
        print(error.model_dump_json(), file=sys.stderr)
    except ValidationError as error:
        print(
            json.dumps(
                {
                    "code": "validation_error",
                    "details": {
                        "errors": error.errors(include_context=False, include_url=False)
                    },
                }
            ),
            file=sys.stderr,
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        print(
            json.dumps({"code": "input_error", "details": {"message": str(error)}}),
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
