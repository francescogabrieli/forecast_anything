"""MCP operator configuration and CSV path access."""

import json

import pytest
from mcp_client_fixtures import config_module
from mcp_client_fixtures import operator_env as operator_env

from forecast_anything.contracts import SourceSpec


def test_config_defaults_are_local_and_deny_source_access():
    config = config_module().McpConfig.from_env()
    assert config.api_url == "http://127.0.0.1:8000"
    assert config.workspace_token == "operator-secret"
    assert config.csv_roots == ()
    assert config.source_ids == frozenset()
    assert "operator-secret" not in repr(config)


@pytest.mark.parametrize("token", [None, "", " ", "secret\nheader", "private secret"])
def test_missing_or_unsafe_token_is_a_safe_configuration_error(monkeypatch, token):
    module = config_module()
    if token is None:
        monkeypatch.delenv("FORECAST_ANYTHING_WORKSPACE_TOKEN")
    else:
        monkeypatch.setenv("FORECAST_ANYTHING_WORKSPACE_TOKEN", token)
    with pytest.raises(module.McpConfigError) as error:
        module.McpConfig.from_env()
    assert error.value.code == "configuration_error"
    assert str(error.value) == "configuration_error"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://example.com",
        "http://127.1:8000",
        "http://127.0.0.2:8000",
        "http://2130706433:8000",
        "http://[::ffff:127.0.0.1]:8000",
        "http://private:secret@127.0.0.1:8000",
        "http://127.0.0.1:8000?private=secret",
        "http://127.0.0.1:8000#private",
        "http://127.0.0.1:8000/v1",
        "http://127.0.0.1:8000?",
        "http://127.0.0.1:8000#",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "file:///private/data",
        "http://127.0.0.1:8000\\@example.com",
    ],
)
def test_configuration_rejects_origins_that_escape_explicit_loopback(monkeypatch, url):
    module = config_module()
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_API_URL", url)
    with pytest.raises(module.McpConfigError) as error:
        module.McpConfig.from_env()
    assert str(error.value) == "configuration_error"
    assert url not in repr(error.value)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000", "http://[::1]:8000"])
def test_explicit_loopback_origins_are_supported(monkeypatch, url):
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_API_URL", url)
    assert config_module().McpConfig.from_env().api_url == url


@pytest.mark.parametrize(
    "roots", ["not-json", "{}", '"/private"', "[1]", "[null]", '["relative"]']
)
def test_malformed_roots_do_not_expose_configuration(monkeypatch, roots):
    module = config_module()
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_CSV_ROOTS", roots)
    with pytest.raises(module.McpConfigError) as error:
        module.McpConfig.from_env()
    assert str(error.value) == "configuration_error"


def test_roots_must_be_existing_directories(monkeypatch, tmp_path):
    module = config_module()
    file = tmp_path / "private-file.csv"
    file.write_text("value\n1\n")
    for root in (file, tmp_path / "private-missing"):
        monkeypatch.setenv("FORECAST_ANYTHING_MCP_CSV_ROOTS", json.dumps([str(root)]))
        with pytest.raises(module.McpConfigError) as error:
            module.McpConfig.from_env()
        assert str(error.value) == "configuration_error"
        assert str(root) not in repr(error.value)


@pytest.mark.parametrize(
    "source_ids", ["not-json", "{}", '"source"', "[1]", "[null]", '[""]', '[" "]']
)
def test_source_allowlist_requires_json_nonempty_strings(monkeypatch, source_ids):
    module = config_module()
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_SOURCE_IDS", source_ids)
    with pytest.raises(module.McpConfigError) as error:
        module.McpConfig.from_env()
    assert str(error.value) == "configuration_error"


def test_source_allowlist_is_operator_configuration(monkeypatch):
    monkeypatch.setenv(
        "FORECAST_ANYTHING_MCP_SOURCE_IDS", '["sales", "history", "sales"]'
    )
    assert config_module().McpConfig.from_env().source_ids == {"sales", "history"}


@pytest.mark.parametrize(
    "name", ["FORECAST_ANYTHING_MCP_CSV_ROOTS", "FORECAST_ANYTHING_MCP_SOURCE_IDS"]
)
def test_excessively_nested_configuration_is_a_safe_error(monkeypatch, name):
    module = config_module()
    monkeypatch.setenv(name, "[" * 2000 + "]" * 2000)
    with pytest.raises(module.McpConfigError, match=r"^configuration_error$"):
        module.McpConfig.from_env()


def source(path, **updates):
    return SourceSpec(
        source_id="history",
        kind=updates.get("kind", "csv"),
        location=str(path),
        secret_ref=updates.get("secret_ref"),
        refresh_seconds=60,
        mapping={"value": "sales"},
    )


def test_csv_guard_returns_resolved_spec_preserving_semantics(monkeypatch, tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    path = root / "data.csv"
    path.write_text("sales\n1\n")
    link = root / "link.csv"
    link.symlink_to(path)
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_CSV_ROOTS", json.dumps([str(root)]))
    config = config_module().McpConfig.from_env()
    original = source(link)
    validated = config.validate_csv(original)
    assert validated.location == str(path.resolve())
    assert validated.mapping == {"value": "sales"}
    assert validated.source_id == "history"
    assert original.location == str(link)
    assert str(root) not in repr(config)


@pytest.mark.parametrize(
    "case",
    [
        "outside",
        "traversal",
        "symlink",
        "directory",
        "missing",
        "relative",
        "kind",
        "secret",
    ],
)
def test_csv_guard_rejects_unapproved_files_and_capabilities(
    monkeypatch, tmp_path, case
):
    module = config_module()
    root = tmp_path / "allowed"
    root.mkdir()
    inside = root / "data.csv"
    inside.write_text("sales\n1\n")
    outside = tmp_path / "private.csv"
    outside.write_text("sales\n9\n")
    link = root / "link.csv"
    link.symlink_to(outside)
    paths = {
        "outside": outside,
        "traversal": root / ".." / "private.csv",
        "symlink": link,
        "directory": root,
        "missing": root / "missing.csv",
        "relative": "data.csv",
        "kind": inside,
        "secret": inside,
    }
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_CSV_ROOTS", json.dumps([str(root)]))
    spec = source(
        paths[case],
        kind="http_json" if case == "kind" else "csv",
        secret_ref="private-credential" if case == "secret" else None,
    )
    with pytest.raises(module.McpConfigError) as error:
        module.McpConfig.from_env().validate_csv(spec)
    assert error.value.code == "source_forbidden"
    assert str(error.value) == "source_forbidden"
    assert str(tmp_path) not in repr(error.value)


def test_unconfigured_roots_deny_even_existing_csv(tmp_path):
    module = config_module()
    path = tmp_path / "data.csv"
    path.write_text("sales\n1\n")
    with pytest.raises(module.McpConfigError, match=r"^source_forbidden$"):
        module.McpConfig.from_env().validate_csv(source(path))
