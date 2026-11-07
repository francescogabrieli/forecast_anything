"""Setup boundaries use model doubles; these are not numerical acceptance."""

import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace

import pytest

from forecast_anything.cli import configured_providers, main
from forecast_anything.contracts import DomainError

CHECKPOINT = "mistralai/Timestral-28M"
REVISION = "49b26409ac87b5935539a5d8ffe7f397b720db47"
CODE = "a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff"


@pytest.fixture(autouse=True)
def clean_configuration(monkeypatch):
    for suffix in ("ENABLED", "CHECKPOINT", "REVISION", "CODE_REVISION"):
        monkeypatch.delenv(f"FORECAST_ANYTHING_TIMESTRAL_{suffix}", raising=False)


def test_default_registration_keeps_timestral_primary_and_baseline_comparator():
    providers = configured_providers()
    assert set(providers) == {"timestral", "seasonal_naive"}
    assert providers["timestral"].capabilities().provider_revision == (
        f"{CHECKPOINT}@{REVISION};code={CODE}"
    )


@pytest.mark.parametrize(
    "suffix,value",
    [
        ("ENABLED", "0"),
        ("ENABLED", "no"),
        ("CHECKPOINT", "other/model"),
        ("REVISION", "main"),
        ("CODE_REVISION", "main"),
        ("REVISION", ""),
    ],
)
def test_product_configuration_cannot_disable_or_relabel_pins(
    monkeypatch, suffix, value
):
    monkeypatch.setenv(f"FORECAST_ANYTHING_TIMESTRAL_{suffix}", value)
    with pytest.raises(DomainError, match="invalid_provider_configuration"):
        configured_providers()


def test_compatible_explicit_pins_still_work(monkeypatch):
    for suffix, value in (
        ("ENABLED", "1"),
        ("CHECKPOINT", CHECKPOINT),
        ("REVISION", REVISION),
        ("CODE_REVISION", CODE),
    ):
        monkeypatch.setenv(f"FORECAST_ANYTHING_TIMESTRAL_{suffix}", value)
    assert configured_providers()["timestral"].revision == REVISION


@pytest.fixture
def installed_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    path = tmp_path / "models--mistralai--Timestral-28M" / "snapshots" / REVISION
    path.mkdir(parents=True)
    (path / "config.json").write_text("{}")
    (path / "model.safetensors").write_bytes(b"fixture weights")
    monkeypatch.setattr(
        "forecast_anything.providers.timestral.distribution",
        lambda name: SimpleNamespace(
            read_text=lambda file: json.dumps({"vcs_info": {"commit_id": CODE}})
        ),
    )
    return path


def test_check_distinguishes_cached_artifacts_from_loaded_model(installed_cache):
    provider = configured_providers()["timestral"]
    status = provider.check_model()
    assert status["status"] == "cached"
    assert status["cached"] is True and status["ready"] is False
    assert status["revision"] == REVISION
    (installed_cache / "model.safetensors").unlink()
    status = provider.check_model()
    assert status["status"] == "weights_missing"
    assert status["cached"] is False and status["ready"] is False
    assert status["prepare_command"] == "forecast-anything model prepare"


def test_check_missing_dependency_and_wrong_revision_are_actionable(
    installed_cache, monkeypatch
):
    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr("forecast_anything.providers.timestral.distribution", missing)
    status = configured_providers()["timestral"].check_model()
    assert status["status"] == "missing_dependency" and status["ready"] is False
    monkeypatch.setattr(
        "forecast_anything.providers.timestral.distribution",
        lambda name: SimpleNamespace(
            read_text=lambda file: '{"vcs_info":{"commit_id":"wrong"}}'
        ),
    )
    assert (
        configured_providers()["timestral"].check_model()["status"]
        == "code_revision_mismatch"
    )


def test_metadata_status_never_imports_model_or_downloads(tmp_path):
    script = f"""
import os, sys
os.environ["HF_HUB_CACHE"] = {str(tmp_path)!r}
class NoModel:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'torch', 'timestral', 'huggingface_hub'}}:
            raise AssertionError('heavy or network import: ' + fullname)
sys.meta_path.insert(0, NoModel())
from forecast_anything.cli import configured_providers
provider = configured_providers()["timestral"]
provider.capabilities()
provider.check_model()
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_unprepared_model_loading_refuses_implicit_download(installed_cache):
    (installed_cache / "model.safetensors").unlink()
    with pytest.raises(DomainError, match="model_not_prepared"):
        configured_providers()["timestral"]._load()


def test_prepare_explicitly_downloads_pins_and_loads_local_only(
    installed_cache, monkeypatch
):
    calls = []
    (installed_cache / "model.safetensors").unlink()

    def download(repo_id, *, revision, allow_patterns):
        assert repo_id == CHECKPOINT and revision == REVISION
        assert set(allow_patterns) == {"config.json", "model.safetensors"}
        (installed_cache / "model.safetensors").write_bytes(b"fixture weights")
        return str(installed_cache)

    def load(checkpoint, *, revision, device, local_files_only):
        calls.append((checkpoint, revision, device, local_files_only))
        return object()

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download)
    )
    monkeypatch.setitem(
        sys.modules,
        "timestral",
        SimpleNamespace(TimestralForecaster=SimpleNamespace(from_pretrained=load)),
    )
    status = configured_providers()["timestral"].prepare_model()
    assert status["status"] == "loaded" and status["ready"] is True
    assert calls == [(CHECKPOINT, REVISION, "cpu", True)]


def test_load_failure_has_structured_error_and_no_baseline_fallback(
    installed_cache, monkeypatch
):
    def load(*args, **kwargs):
        raise RuntimeError("fixture failure")

    monkeypatch.setitem(
        sys.modules,
        "timestral",
        SimpleNamespace(TimestralForecaster=SimpleNamespace(from_pretrained=load)),
    )
    with pytest.raises(DomainError, match="model_load_failed"):
        configured_providers()["timestral"]._load()


def test_model_status_cli_reports_unprepared_with_nonzero_exit(
    installed_cache, monkeypatch, capsys
):
    (installed_cache / "model.safetensors").unlink()
    monkeypatch.setattr(sys, "argv", ["forecast-anything", "model", "status"])
    assert main() == 1
    assert json.loads(capsys.readouterr().out)["status"] == "weights_missing"


def test_model_prepare_cli_returns_loaded_status(installed_cache, monkeypatch, capsys):
    monkeypatch.setitem(
        sys.modules,
        "timestral",
        SimpleNamespace(
            TimestralForecaster=SimpleNamespace(
                from_pretrained=lambda *args, **kwargs: object()
            )
        ),
    )
    monkeypatch.setattr(sys, "argv", ["forecast-anything", "model", "prepare"])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "loaded"


@pytest.mark.parametrize("provenance", ["[]", '{"vcs_info":null}', '{"vcs_info":[]}'])
def test_invalid_installed_provenance_remains_diagnosable(
    installed_cache, monkeypatch, provenance
):
    monkeypatch.setattr(
        "forecast_anything.providers.timestral.distribution",
        lambda name: SimpleNamespace(read_text=lambda file: provenance),
    )
    status = configured_providers()["timestral"].check_model()
    assert status["status"] == "code_revision_mismatch"
    assert status["ready"] is False


def test_preparation_download_failure_is_structured(installed_cache, monkeypatch):
    (installed_cache / "model.safetensors").unlink()

    def fail(*args, **kwargs):
        raise OSError("fixture connection failed")

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=fail)
    )
    with pytest.raises(DomainError, match="model_preparation_failed"):
        configured_providers()["timestral"].prepare_model()


@pytest.mark.parametrize(
    "variable", ["HF_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"]
)
def test_cache_paths_with_user_home_match_huggingface(variable, monkeypatch):
    from pathlib import Path

    for name in ("HF_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(variable, "~/.timestral-cache-fixture")
    path = configured_providers()["timestral"]._snapshot_path()
    assert path.is_absolute()
    assert path.is_relative_to(Path.home())
