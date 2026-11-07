import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from forecast_anything.contracts import DomainError
from forecast_anything.setup_local import register_codex
from forecast_anything.workspace_config import create_workspace


def test_registration_preserves_existing_entry(monkeypatch, tmp_path):
    calls = []
    config = create_workspace(tmp_path / "workspace", tmp_path, 8091)
    executable = Path("/runtime/bin/forecast-anything")
    args = ["mcp", "--config", str(config)]
    entries = [
        {"name": "other", "transport": {"type": "stdio", "command": "/other"}},
        {
            "name": "forecast-test",
            "enabled": True,
            "transport": {"type": "stdio", "command": str(executable), "args": args},
        },
    ]

    def run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, json.dumps(entries), "")

    monkeypatch.setattr("forecast_anything.setup_local.subprocess.run", run)
    assert register_codex("/codex", "forecast-test", executable, config) == "existing"
    assert calls == [["/codex", "mcp", "list", "--json"]]
    entries[1]["transport"]["command"] = "/different"
    with pytest.raises(DomainError, match="codex_entry_conflict"):
        register_codex("/codex", "forecast-test", executable, config)
    assert len(calls) == 2


def test_stop_waits_for_asynchronous_bootout(monkeypatch, tmp_path):
    from forecast_anything.setup_local import LaunchAgent

    agent = LaunchAgent.__new__(LaunchAgent)
    agent.target = "gui/501/example"
    agent.config = {"db": str(tmp_path / "state.db"), "port": 8091}
    observations = iter((True, True, False))
    actions = []
    monkeypatch.setattr(agent, "loaded", lambda: next(observations))
    monkeypatch.setattr(
        agent, "_launchctl", lambda action, target: actions.append(action)
    )
    monkeypatch.setattr("forecast_anything.setup_local.time.sleep", lambda delay: None)
    from contextlib import nullcontext

    monkeypatch.setattr(
        "forecast_anything.setup_local.reserve_port", lambda *args: nullcontext()
    )
    agent.stop()
    assert actions == ["disable", "bootout"]
    assert list(observations) == []


@pytest.mark.parametrize("tamper", ["executable", "environment", "arguments"])
def test_conflicting_plist_cannot_be_used(monkeypatch, tmp_path, tamper):
    import plistlib

    from forecast_anything.setup_local import LaunchAgent

    monkeypatch.setattr("forecast_anything.setup_local.sys.platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = create_workspace(tmp_path / "workspace", tmp_path, 8091)
    agent = LaunchAgent(cfg, Path("/runtime/bin/forecast-anything"))
    spec = agent._contents()
    if tamper == "executable":
        spec["ProgramArguments"][0] = "/different"
    elif tamper == "environment":
        spec["EnvironmentVariables"]["DYLD_INSERT_LIBRARIES"] = "/different"
    else:
        spec["ProgramArguments"] = {}
    agent.plist.parent.mkdir(parents=True)
    agent.plist.write_bytes(plistlib.dumps(spec))
    with pytest.raises(DomainError, match="service_definition_conflict"):
        agent._existing()


def test_foreign_loaded_launchagent_is_not_disabled(monkeypatch, tmp_path):
    from forecast_anything.setup_local import LaunchAgent

    monkeypatch.setattr("forecast_anything.setup_local.sys.platform", "darwin")
    cfg = create_workspace(tmp_path / "workspace", tmp_path, 8091)
    agent = LaunchAgent(cfg, Path("/runtime/bin/forecast-anything"))
    operations = []

    def run(command, **kwargs):
        operations.append(command[1])
        return CompletedProcess(command, 0, "\tpath = /some/other.plist\n", "")

    monkeypatch.setattr("forecast_anything.setup_local.subprocess.run", run)
    with pytest.raises(DomainError, match="service_definition_conflict"):
        agent.stop()
    assert operations == ["print"]
