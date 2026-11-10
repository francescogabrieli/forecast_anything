"""Private configuration for a local workspace and its MCP client."""

import json
import os
import secrets
import sqlite3
from http.client import HTTPConnection, HTTPException
from pathlib import Path

from .contracts import DomainError
from .providers.configuration import (
    DEFAULT_TIMESTRAL_MODEL,
    TIMESTRAL_MODEL_ENV,
    TIMESTRAL_MODELS,
)
from .sources.catalog import SourceCatalog


def create_workspace(
    directory: Path,
    csv_root: Path,
    port: int,
    *,
    timestral_model: str | None = None,
) -> Path:
    root = csv_root.resolve(strict=True)
    if not root.is_dir() or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid workspace configuration")
    if timestral_model is not None and timestral_model not in TIMESTRAL_MODELS:
        raise ValueError("invalid Timestral model")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = directory.resolve(strict=True)
    path = directory / "config.json"
    config = {
        "version": 1,
        "db": str(directory / "state.db"),
        "port": port,
        "token": secrets.token_urlsafe(32),
        "csv_roots": [str(root)],
        "source_ids": [],
    }
    if timestral_model is not None:
        config["timestral_model"] = timestral_model
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)
        file.write("\n")
    return path


def load_workspace(path: Path) -> dict:
    try:
        if path.stat().st_size > 65536:
            raise ValueError
        config = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or set(config) - {"timestral_model"} != {
            "version",
            "db",
            "port",
            "token",
            "csv_roots",
            "source_ids",
        }:
            raise ValueError
        if (
            config.get("timestral_model", DEFAULT_TIMESTRAL_MODEL)
            not in TIMESTRAL_MODELS
        ):
            raise ValueError
        if type(config["version"]) is not int or config["version"] != 1:
            raise ValueError
        if type(config["port"]) is not int or not 1 <= config["port"] <= 65535:
            raise ValueError
        if not isinstance(config["db"], str) or not Path(config["db"]).is_absolute():
            raise ValueError
        token = config["token"]
        if (
            not isinstance(token, str)
            or not token
            or any(not 33 <= ord(c) <= 126 for c in token)
        ):
            raise ValueError
        roots, ids = config["csv_roots"], config["source_ids"]
        if not isinstance(roots, list) or any(
            not isinstance(root, str)
            or not Path(root).is_absolute()
            or not Path(root).is_dir()
            for root in roots
        ):
            raise ValueError
        if not isinstance(ids, list) or any(
            not isinstance(item, str) or not item.strip() for item in ids
        ):
            raise ValueError
        return config
    except (ValueError, TypeError, OSError, UnicodeError):
        raise ValueError("invalid workspace configuration") from None


def apply_workspace(config: dict) -> None:
    os.environ.update(
        {
            TIMESTRAL_MODEL_ENV: config.get("timestral_model", DEFAULT_TIMESTRAL_MODEL),
            "FORECAST_ANYTHING_WORKSPACE_TOKEN": config["token"],
            "FORECAST_ANYTHING_MCP_API_URL": f"http://127.0.0.1:{config['port']}",
            "FORECAST_ANYTHING_MCP_CSV_ROOTS": json.dumps(config["csv_roots"]),
            "FORECAST_ANYTHING_MCP_SOURCE_IDS": json.dumps(config["source_ids"]),
        }
    )


def manage_source_permissions(
    path: Path, action: str, source_id: str | None = None
) -> dict:
    """List or change MCP source grants in a private workspace config."""
    config = load_workspace(path)
    allowed = set(config["source_ids"])
    if action == "list":
        if source_id is not None:
            raise ValueError("source_id is only valid with grant or revoke")
        return {"source_ids": sorted(allowed), "restart_required": False}
    if action not in {"grant", "revoke"}:
        raise ValueError("unknown permission action")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id is required")
    source_id = source_id.strip()

    if action == "grant":
        database = Path(config["db"])
        if not database.is_file():
            raise ValueError("source_not_registered")
        try:
            SourceCatalog(database).get(source_id)
        except DomainError as error:
            if error.code == "source_not_found":
                raise ValueError("source_not_registered") from None
            raise ValueError("workspace database unavailable") from None
        except (OSError, sqlite3.Error, ValueError):
            raise ValueError("workspace database unavailable") from None

    previous = source_id in allowed
    if action == "grant":
        allowed.add(source_id)
    else:
        allowed.discard(source_id)

    changed = allowed != set(config["source_ids"])
    if changed:
        config["source_ids"] = sorted(allowed)
        _write_workspace(path, config)
    result = {"action": action, "source_id": source_id}
    if action == "grant":
        result["state"] = "granted" if changed else "already_granted"
    else:
        result["state"] = "revoked" if previous else "not_granted"
    result["restart_required"] = changed
    return result


def _write_workspace(path: Path, config: dict) -> None:
    """Atomically replace the private config without printing its contents."""
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(config, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def check_api(config: dict) -> dict:
    """Check authenticated API access and its shared-database worker heartbeat."""
    connection = HTTPConnection("127.0.0.1", config["port"], timeout=2)
    try:
        connection.request(
            "GET", "/v1/sources", headers={"Authorization": "Bearer " + config["token"]}
        )
        response = connection.getresponse()
        state = "available" if response.status == 200 else "authentication_or_api_error"
    except (OSError, HTTPException):
        state = "unreachable"
    finally:
        connection.close()

    worker = "unknown"
    if state == "available":
        health = HTTPConnection("127.0.0.1", config["port"], timeout=2)
        try:
            health.request("GET", "/health")
            response = health.getresponse()
            body = response.read(4097)
            if response.status == 200 and len(body) <= 4096:
                payload = json.loads(body)
                if isinstance(payload, dict) and payload.get("worker") in {
                    "running",
                    "stale",
                    "not_running",
                }:
                    worker = payload["worker"]
        except (OSError, HTTPException, ValueError, UnicodeError):
            pass
        finally:
            health.close()
    return {"api": state, "worker": worker}
