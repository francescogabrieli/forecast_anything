"""Local CSV-to-ledger CLI; stdout is a RunRecord, stderr structured errors."""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from .connectors.csv import load_csv
from .contracts import DomainError, GraphSpec
from .graph import SourceConfig, parse_node_config
from .providers.baseline import SeasonalNaiveProvider
from .runtime import Runtime
from .store import Ledger
from .temporal import freeze


def configured_providers():
    """Register the baseline and only opt-in, pinned providers from the environment."""
    providers = {"seasonal_naive": SeasonalNaiveProvider(1)}
    enabled = os.environ.get("FORECAST_ANYTHING_TIMESTRAL_ENABLED", "").strip()
    if enabled not in {"", "0", "1"}:
        raise DomainError("invalid_provider_configuration", {})
    if enabled == "1":
        values = {
            "checkpoint": os.environ.get("FORECAST_ANYTHING_TIMESTRAL_CHECKPOINT"),
            "revision": os.environ.get("FORECAST_ANYTHING_TIMESTRAL_REVISION"),
            "code_revision": os.environ.get(
                "FORECAST_ANYTHING_TIMESTRAL_CODE_REVISION"
            ),
        }
        if not all(
            isinstance(value, str) and value.strip() for value in values.values()
        ):
            raise DomainError("incomplete_timestral_configuration", {})
        from .providers.timestral import TimestralProvider

        providers["timestral"] = TimestralProvider(**values)
    return providers


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
    ).run(spec, snapshots, origin, key)


def main() -> int:
    parser = argparse.ArgumentParser(prog="forecast-anything")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Freeze CSV observations and emit a forecast")
    run.add_argument("graph", type=Path)
    run.add_argument("--data", type=Path, required=True)
    run.add_argument("--as-of", required=True, help="ISO 8601 origin with timezone")
    run.add_argument("--db", type=Path, required=True)
    show = commands.add_parser("show", help="Read a stored immutable emission")
    show.add_argument("run_id")
    show.add_argument("--db", type=Path, required=True)
    serve = commands.add_parser("serve", help="Serve the authenticated local API")
    serve.add_argument("--db", type=Path, required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    worker = commands.add_parser("worker", help="Process the shared durable queue")
    worker.add_argument("--db", type=Path, required=True)
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--limit", type=int, default=10)
    worker.add_argument("--poll-seconds", type=float, default=1)
    worker.add_argument("--lease-seconds", type=int, default=60)
    commands.add_parser("mcp", help="Serve optional MCP tools over stdio")
    args = parser.parse_args()
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
        if args.command in {"serve", "worker"}:
            from .operators import register_builtin_operators

            ledger = Ledger(args.db)
            runtime = Runtime(
                ledger,
                configured_providers(),
                register_builtin_operators(),
                lambda: datetime.now(timezone.utc),
            )
            if args.command == "serve":
                import uvicorn

                from .api.app import create_app

                app = create_app(
                    ledger,
                    runtime,
                    os.environ.get("FORECAST_ANYTHING_WORKSPACE_TOKEN", ""),
                    agent_token=os.environ.get("FORECAST_ANYTHING_AGENT_CORE_TOKEN"),
                    console_origins=tuple(
                        origin.strip()
                        for origin in os.environ.get(
                            "FORECAST_ANYTHING_CONSOLE_ORIGINS", ""
                        ).split(",")
                        if origin.strip()
                    ),
                )
                uvicorn.run(app, host=args.host, port=args.port, access_log=False)
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
            while True:
                completed = worker.run_due(runtime.clock(), limit=args.limit)
                if args.once:
                    print(json.dumps({"job_ids": completed}))
                    return 0
                time.sleep(args.poll_seconds)
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
