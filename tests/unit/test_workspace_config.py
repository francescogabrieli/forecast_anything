import json
import os

import pytest

from forecast_anything.workspace_config import (
    apply_workspace,
    create_workspace,
    load_workspace,
)


def test_workspace_is_private_and_never_overwrites(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    path = create_workspace(tmp_path / "workspace", root, 8123)
    assert os.stat(path).st_mode & 0o777 == 0o600
    config = load_workspace(path)
    assert config["port"] == 8123
    assert config["csv_roots"] == [str(root.resolve())]
    assert len(config["token"]) >= 32
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        create_workspace(path.parent, root, 8123)
    assert path.read_bytes() == original


def test_invalid_config_is_rejected_without_exposing_token(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"token": "secret", "port": 99999}))
    with pytest.raises(ValueError, match="invalid workspace configuration") as error:
        load_workspace(path)
    assert "secret" not in str(error.value)


def test_workspace_sets_same_mcp_and_api_configuration(tmp_path, monkeypatch):
    root = tmp_path / "sources"
    root.mkdir()
    config = load_workspace(create_workspace(tmp_path / "workspace", root, 8123))
    for name in (
        "FORECAST_ANYTHING_WORKSPACE_TOKEN",
        "FORECAST_ANYTHING_MCP_API_URL",
        "FORECAST_ANYTHING_MCP_CSV_ROOTS",
        "FORECAST_ANYTHING_MCP_SOURCE_IDS",
    ):
        monkeypatch.delenv(name, raising=False)
    apply_workspace(config)
    from forecast_anything.mcp_adapter.config import McpConfig

    mcp = McpConfig.from_env()
    assert mcp.workspace_token == config["token"]
    assert mcp.api_url == "http://127.0.0.1:8123"
    assert mcp.csv_roots == (root.resolve(),)


def test_workspace_pins_selected_timestral_model(tmp_path, monkeypatch):
    from forecast_anything.providers.configuration import configured_providers

    path = create_workspace(
        tmp_path / "workspace", tmp_path, 8123, timestral_model="123m"
    )
    config = load_workspace(path)
    assert config["timestral_model"] == "123m"
    monkeypatch.setenv("FORECAST_ANYTHING_TIMESTRAL_MODEL", "28m")
    apply_workspace(config)
    provider = configured_providers()["timestral"]
    assert provider.checkpoint == "mistralai/Timestral-123M"
    assert provider.revision == "5a147287addda85f6acd8da3fb8858fe9af7e8f7"


def test_legacy_workspace_keeps_the_default_model(tmp_path, monkeypatch):
    from forecast_anything.providers.configuration import configured_providers

    path = create_workspace(tmp_path / "workspace", tmp_path, 8123)
    monkeypatch.setenv("FORECAST_ANYTHING_TIMESTRAL_MODEL", "123m")
    apply_workspace(load_workspace(path))
    assert configured_providers()["timestral"].checkpoint == "mistralai/Timestral-28M"


def test_model_status_reads_selected_workspace(tmp_path, monkeypatch, capsys):
    import json
    import sys

    from forecast_anything.cli import main

    path = create_workspace(
        tmp_path / "workspace", tmp_path, 8123, timestral_model="123m"
    )
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty-cache"))
    monkeypatch.setattr(
        sys, "argv", ["forecast-anything", "model", "status", "--config", str(path)]
    )
    assert main() == 1
    status = json.loads(capsys.readouterr().out)
    assert status["checkpoint"] == "mistralai/Timestral-123M"
    assert (
        status["prepare_command"]
        == "forecast-anything model prepare --timestral-model 123m"
    )
