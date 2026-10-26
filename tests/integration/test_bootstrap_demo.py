from pathlib import Path
from runpy import run_path

bootstrap_demo = run_path("scripts/bootstrap_demo.py")["bootstrap_demo"]


def test_bootstrap_never_overwrites_existing_workspace(tmp_path: Path):
    config = bootstrap_demo(tmp_path / "workspace")
    before = config.read_bytes()

    assert bootstrap_demo(tmp_path / "workspace") == config
    assert config.read_bytes() == before


def test_demo_bootstrap_has_local_credentials_and_no_external_keys(tmp_path: Path):
    config = bootstrap_demo(tmp_path / "workspace")
    content = config.read_text(encoding="utf-8")

    assert "FORECAST_ANYTHING_WORKSPACE_TOKEN=" in content
    assert (
        f"FORECAST_ANYTHING_DATABASE={tmp_path / 'workspace' / 'state.db'}" in content
    )
    assert "FORECAST_ANYTHING_CONSOLE_ORIGINS=" in content
    assert "OPENAI_API_KEY" not in content
    assert "MISTRAL_API_KEY" not in content
    assert config.stat().st_mode & 0o777 == 0o600
