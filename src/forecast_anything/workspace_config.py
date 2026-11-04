"""Private configuration for a local workspace and its MCP client."""

import json
import os
import secrets
from http.client import HTTPConnection, HTTPException
from pathlib import Path


def create_workspace(directory: Path, csv_root: Path, port: int) -> Path:
    root = csv_root.resolve(strict=True)
    if not root.is_dir() or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid workspace configuration")
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
        if not isinstance(config, dict) or set(config) != {
            "version",
            "db",
            "port",
            "token",
            "csv_roots",
            "source_ids",
        }:
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
            "FORECAST_ANYTHING_WORKSPACE_TOKEN": config["token"],
            "FORECAST_ANYTHING_MCP_API_URL": f"http://127.0.0.1:{config['port']}",
            "FORECAST_ANYTHING_MCP_CSV_ROOTS": json.dumps(config["csv_roots"]),
            "FORECAST_ANYTHING_MCP_SOURCE_IDS": json.dumps(config["source_ids"]),
        }
    )


def check_api(config: dict) -> dict:
    """Check authenticated API access; this does not establish worker health."""
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
    return {"api": state, "worker": "unknown"}
