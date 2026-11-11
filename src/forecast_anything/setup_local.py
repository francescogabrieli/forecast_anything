"""Install and operate a macOS user LaunchAgent and a Codex stdio entry."""

import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path

from .contracts import DomainError
from .diagnostics import diagnose_workspace
from .local_services import local_lock, reserve_port, worker_lock
from .providers.configuration import DEFAULT_TIMESTRAL_MODEL, configured_providers
from .workspace_config import create_workspace, load_workspace


def _identity(config_path: Path) -> str:
    return sha256(os.fsencode(config_path.resolve())).hexdigest()[:16]


def _run(command):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        raise DomainError("local_command_failed", {"operation": command[1]}) from None


def _codex_entry(codex: str, name: str, executable: Path, config_path: Path) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise DomainError("invalid_codex_name", {})
    command = [codex, "mcp"]
    result = _run([*command, "list", "--json"])
    try:
        entries = json.loads(result.stdout) if not result.returncode else None
        if not isinstance(entries, list) or not all(
            isinstance(e, dict) for e in entries
        ):
            raise ValueError
    except (ValueError, RecursionError):
        raise DomainError("codex_mcp_list_failed", {}) from None
    args = ["mcp", "--config", str(config_path)]
    for entry in entries:
        if entry.get("name") != name:
            continue
        transport = entry.get("transport")
        if (
            entry.get("enabled") is True
            and isinstance(transport, dict)
            and transport.get("type") == "stdio"
            and transport.get("command") == str(executable)
            and transport.get("args") == args
            and not transport.get("env")
            and not transport.get("env_vars")
            and not transport.get("cwd")
        ):
            return "existing"
        raise DomainError(
            "codex_entry_conflict",
            {
                "name": name,
                "recovery": "Choose a different --codex-name or review the existing entry in Codex.",
            },
        )
    return "pending"


def register_codex(codex: str, name: str, executable: Path, config_path: Path) -> str:
    if _codex_entry(codex, name, executable, config_path) == "existing":
        return "existing"
    result = _run(
        [
            codex,
            "mcp",
            "add",
            name,
            "--",
            str(executable),
            "mcp",
            "--config",
            str(config_path),
        ]
    )
    if result.returncode:
        raise DomainError("codex_mcp_add_failed", {"name": name})
    return "added"


class LaunchAgent:
    def __init__(self, config_path: Path, executable: Path):
        if sys.platform != "darwin":
            raise DomainError(
                "macos_login_service_required",
                {"recovery": "Use forecast-anything up for a foreground workspace."},
            )
        self.config_path = config_path.resolve(strict=True)
        self.config = load_workspace(self.config_path)
        self.executable = executable
        self.label = "com.forecast-anything.workspace." + _identity(self.config_path)
        self.domain = f"gui/{os.getuid()}"
        self.target = f"{self.domain}/{self.label}"
        self.plist = Path.home() / "Library" / "LaunchAgents" / (self.label + ".plist")

    def _launchctl(self, action, *args, required=True):
        result = _run(["/bin/launchctl", action, *map(str, args)])
        if required and result.returncode:
            raise DomainError(
                "launchctl_failed",
                {
                    "operation": action,
                    "recovery": "Run from the logged-in macOS desktop user and inspect the workspace runtime logs.",
                },
            )
        return result.returncode == 0

    def _contents(self):
        root = self.config_path.parent
        environment = {"HF_HUB_OFFLINE": "1", "PYTHONUNBUFFERED": "1"}
        for name in (
            "HF_HOME",
            "HF_HUB_CACHE",
            "HUGGINGFACE_HUB_CACHE",
            "XDG_CACHE_HOME",
        ):
            if value := os.environ.get(name):
                environment[name] = str(Path(value).expanduser().resolve())
        return {
            "Label": self.label,
            "ProgramArguments": [
                str(self.executable),
                "up",
                "--config",
                str(self.config_path),
                "--verify-model",
            ],
            "WorkingDirectory": str(root),
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            "EnvironmentVariables": environment,
            "StandardOutPath": str(root / "runtime.stdout.log"),
            "StandardErrorPath": str(root / "runtime.stderr.log"),
        }

    def _existing(self):
        if not self.plist.exists() and not self.plist.is_symlink():
            return None
        try:
            if self.plist.is_symlink() or self.plist.stat().st_size > 65536:
                raise ValueError
            contents = plistlib.loads(self.plist.read_bytes())
            expected = self._contents()
            expected.pop("EnvironmentVariables")
            if not isinstance(contents, dict):
                raise ValueError
            environment = contents.get("EnvironmentVariables")
            if not isinstance(environment, dict):
                raise ValueError
            cache_names = {
                "HF_HOME",
                "HF_HUB_CACHE",
                "HUGGINGFACE_HUB_CACHE",
                "XDG_CACHE_HOME",
            }
            if (
                {k: v for k, v in contents.items() if k != "EnvironmentVariables"}
                != expected
                or environment.get("HF_HUB_OFFLINE") != "1"
                or environment.get("PYTHONUNBUFFERED") != "1"
                or any(
                    key not in cache_names
                    or not isinstance(value, str)
                    or not Path(value).is_absolute()
                    for key, value in environment.items()
                    if key not in {"HF_HUB_OFFLINE", "PYTHONUNBUFFERED"}
                )
            ):
                raise ValueError
            return contents
        except (OSError, ValueError, TypeError, plistlib.InvalidFileException):
            raise DomainError(
                "service_definition_conflict",
                {"recovery": "Inspect the existing LaunchAgent before making changes."},
            ) from None

    def install(self):
        existing = self._existing()
        contents = self._contents()
        if existing is not None:
            if existing != contents:
                raise DomainError(
                    "service_definition_conflict",
                    {
                        "recovery": "Use the currently installed CLI to remove the service, then rerun setup with the intended artifact and cache settings."
                    },
                )
            return
        if self.loaded():
            raise DomainError(
                "service_definition_conflict",
                {
                    "recovery": "Inspect the loaded job before installing a service definition."
                },
            )
        self.plist.parent.mkdir(parents=True, exist_ok=True)
        # Publish the new definition disabled until start passes preflight.
        self._launchctl("disable", self.target)
        with tempfile.NamedTemporaryFile(dir=self.plist.parent) as temporary:
            plistlib.dump(contents, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
            os.link(temporary.name, self.plist)

    def _job(self):
        result = _run(["/bin/launchctl", "print", self.target])
        if result.returncode:
            return False, None
        fields = dict(
            re.findall(r"^\t(path|program|pid) = (.+)$", result.stdout, re.MULTILINE)
        )
        if fields.get("path") != str(self.plist) or fields.get("program") != str(
            self.executable
        ):
            raise DomainError(
                "service_definition_conflict",
                {"recovery": "Inspect the loaded job before changing this service."},
            )
        pid = fields.get("pid", "")
        return True, int(pid) if pid.isdecimal() else None

    def loaded(self):
        return self._job()[0]

    def start(self):
        if self._existing() is None:
            raise DomainError(
                "service_not_installed",
                {"recovery": "Run service install or setup first."},
            )
        if self.loaded():
            return
        with (
            worker_lock(Path(self.config["db"])),
            reserve_port("127.0.0.1", self.config["port"]),
        ):
            pass
        self._launchctl("enable", self.target)
        try:
            self._launchctl("bootstrap", self.domain, self.plist)
        except DomainError:
            if not self.loaded():
                self._launchctl("disable", self.target, required=False)
            raise

    def stop(self):
        was_loaded = self.loaded()
        self._launchctl("disable", self.target)
        if not was_loaded:
            return
        self._launchctl("bootout", self.target)
        deadline = time.monotonic() + 10
        while True:
            if not self.loaded():
                try:
                    with (
                        worker_lock(Path(self.config["db"])),
                        reserve_port("127.0.0.1", self.config["port"]),
                    ):
                        return
                except DomainError as error:
                    if error.code not in {"worker_already_running", "port_in_use"}:
                        raise
            if time.monotonic() >= deadline:
                raise DomainError(
                    "service_stop_timeout",
                    {
                        "recovery": "Check the service logs and wait for the API and worker to exit before restarting."
                    },
                )
            time.sleep(0.1)

    def inspect(self):
        installed = self._existing() is not None
        loaded, pid = self._job()
        return {
            "service": {"label": self.label, "installed": installed, "loaded": loaded},
            **diagnose_workspace(
                self.config, expected_supervisor_pid=pid if installed and pid else 0
            ),
        }

    def run(self, action):
        if action == "status":
            return self.inspect()
        with local_lock(self.config_path.with_name(".service.lock"), "service_busy"):
            existing = self._existing()
            if action == "install":
                self.install()
            elif action == "start":
                self.start()
            elif action in {"stop", "restart", "remove"} and existing is not None:
                self.stop()
                if action == "restart":
                    self.start()
                elif action == "remove":
                    self.plist.unlink()
            elif action == "restart":
                self.start()
            return self.inspect()


def setup(
    workspace,
    csv_root,
    port,
    codex_bin,
    codex_name,
    prepare_model,
    executable,
    *,
    timestral_model=None,
):
    if sys.platform != "darwin":
        raise DomainError(
            "macos_login_service_required",
            {"recovery": "Use init and up for a foreground workspace."},
        )
    if find_spec("mcp") is None:
        raise DomainError(
            "mcp_dependency_missing",
            {"recovery": "Install the artifact with its locked MCP requirements."},
        )
    codex = shutil.which(codex_bin)
    if codex is None:
        raise DomainError(
            "codex_cli_missing",
            {
                "recovery": "Install the Codex CLI or supply its absolute path with --codex-bin."
            },
        )
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    workspace = workspace.resolve()
    with local_lock(workspace / ".setup.lock", "setup_busy"):
        config_path = (workspace / "config.json").resolve()
        name = codex_name or "forecast-anything-" + _identity(config_path)
        codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        codex_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        codex_lock = codex_home / ".forecast-anything-setup.lock"
        with local_lock(codex_lock, "codex_setup_busy"):
            _codex_entry(codex, name, executable, config_path)
        if config_path.exists():
            config = load_workspace(config_path)
            selected_model = config.get("timestral_model", DEFAULT_TIMESTRAL_MODEL)
            if timestral_model is not None and timestral_model != selected_model:
                raise DomainError(
                    "workspace_model_conflict",
                    {
                        "model": selected_model,
                        "recovery": "Choose a new workspace to use a different checkpoint.",
                    },
                )
            if port is not None and port != config["port"]:
                raise DomainError(
                    "workspace_port_conflict",
                    {"recovery": "Reuse the existing port or choose a new workspace."},
                )
            if (
                csv_root is not None
                and str(csv_root.resolve()) not in config["csv_roots"]
            ):
                raise DomainError(
                    "workspace_csv_root_conflict",
                    {
                        "recovery": "Reuse an existing CSV root or choose a new workspace."
                    },
                )
        else:
            root = csv_root or workspace / "sources"
            if csv_root is None:
                root.mkdir(exist_ok=True, mode=0o700)
            selected_model = timestral_model or DEFAULT_TIMESTRAL_MODEL
            create_workspace(
                workspace,
                root,
                port if port is not None else 8000,
                timestral_model=timestral_model,
            )
        provider = configured_providers(selected_model)["timestral"]
        if prepare_model:
            provider.prepare_model()
        else:
            provider.verify_cached_model()
        agent = LaunchAgent(config_path, executable)
        agent.run("install")
        agent.run("start")
        deadline = time.monotonic() + 35
        while True:
            report = agent.inspect()
            if (
                report["ready"]
                or time.monotonic() >= deadline
                or report["authentication"] == "rejected"
            ):
                break
            time.sleep(0.25)
        report["codex"] = {"name": name, "registration": "pending"}
        if report["ready"]:
            try:
                with local_lock(codex_lock, "codex_setup_busy"):
                    report["codex"]["registration"] = register_codex(
                        codex, name, executable, config_path
                    )
            except DomainError as error:
                # The working service stays available. A retry can finish just the
                # registration, and an existing conflicting entry remains untouched.
                report["codex"].update(registration="failed", code=error.code)
                report["recovery"].append(
                    "The service is running. Check Codex CLI configuration or choose a free --codex-name, then rerun setup."
                )
        return report
