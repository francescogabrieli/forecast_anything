"""Create a private, local-only environment file for a demo workspace."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path


def bootstrap_demo(workspace: Path) -> Path:
    """Create and return the workspace environment file without overwriting it."""
    workspace = Path(workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    config = workspace / "demo.env"
    content = (
        f"FORECAST_ANYTHING_WORKSPACE={workspace}\n"
        f"FORECAST_ANYTHING_DATA_DIR={workspace}\n"
        f"FORECAST_ANYTHING_DATABASE={workspace / 'state.db'}\n"
        f"FORECAST_ANYTHING_WORKSPACE_TOKEN={secrets.token_urlsafe(32)}\n"
        "FORECAST_ANYTHING_CONSOLE_ORIGINS=http://127.0.0.1:5173,http://localhost:5173\n"
    )
    try:
        descriptor = os.open(config, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return config
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path, help="directory for the private demo state")
    args = parser.parse_args()
    print(bootstrap_demo(args.workspace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
