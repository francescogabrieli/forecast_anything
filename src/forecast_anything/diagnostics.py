"""Small read-only loopback diagnostics shared by CLI and the MCP adapter."""

import contextlib
import hmac
import json
import os
import re
import secrets
import socket
from functools import cache
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from importlib.metadata import PackageNotFoundError, version
from threading import Timer
from urllib.parse import urlsplit

_PROBE_TIMEOUT_SECONDS = 2
_NONCE_HEADER = "X-Forecast-Diagnostics-Nonce"
_PROBE_HEADER = "X-Forecast-Diagnostics-Probe"


@cache
def runtime_version() -> str:
    try:
        return version("forecast-anything")
    except PackageNotFoundError:
        return "source"


def _proof(token: str, nonce: str, payload: dict | None = None) -> str:
    message = "diagnostics/request/" + nonce
    if payload is not None:
        message = (
            "diagnostics/response/"
            + nonce
            + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        )
    return hmac.digest(token.encode(), message.encode(), "sha256").hex()


def validated_nonce(headers, token: str) -> str | None:
    nonce = headers.get(_NONCE_HEADER, "")
    probe = headers.get(_PROBE_HEADER, "")
    if (
        re.fullmatch(r"[0-9a-f]{32}", nonce)
        and re.fullmatch(r"[0-9a-f]{64}", probe)
        and hmac.compare_digest(probe, _proof(token, nonce))
    ):
        return nonce
    return None


def sign_diagnostics(payload: dict, nonce: str, token: str) -> dict:
    return {**payload, "diagnostic_proof": _proof(token, nonce, payload)}


def _get(url, path, headers):
    origin = urlsplit(url)
    connection_type = HTTPSConnection if origin.scheme == "https" else HTTPConnection
    connection = connection_type(
        origin.hostname, origin.port, timeout=_PROBE_TIMEOUT_SECONDS
    )
    timer = None
    try:
        connection.connect()
        connected_socket = connection.sock

        def expire():
            with contextlib.suppress(OSError):
                connected_socket.shutdown(socket.SHUT_RDWR)

        # The socket timeout alone resets when a peer drips headers or a body.
        timer = Timer(_PROBE_TIMEOUT_SECONDS, expire)
        timer.daemon = True
        timer.start()
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            return response.status, None
        data = response.read(65537)
        if len(data) <= 65536:
            payload = json.loads(data)
            if isinstance(payload, dict):
                return 200, payload
        return 200, None
    except (OSError, HTTPException):
        return None, None
    except (ValueError, UnicodeError, RecursionError):
        return 200, None
    finally:
        if timer is not None:
            timer.cancel()
        connection.close()


_MODEL_STATES = {
    "loaded",
    "cached",
    "weights_missing",
    "missing_dependency",
    "code_revision_mismatch",
    "model_not_prepared",
    "missing_model_dependency",
    "model_code_revision_mismatch",
    "model_load_failed",
    "unverified",
    "unavailable",
    "not_required",
}


def diagnose(
    url, token, csv_roots, source_ids, *, expected_supervisor_pid=None
) -> dict:
    """Authenticate a bounded health response without sending the workspace token."""
    local_version = runtime_version()
    nonce = secrets.token_hex(16)
    status, health = _get(
        url, "/health", {_NONCE_HEADER: nonce, _PROBE_HEADER: _proof(token, nonce)}
    )
    api = "unreachable" if status is None else "unexpected_response"
    authentication = worker = model = "unknown"
    remote_version = None
    recovery = []
    required_model = False
    readable = sum(
        os.path.isdir(root) and os.access(root, os.R_OK | os.X_OK) for root in csv_roots
    )
    if (
        health
        and health.get("status") == "ok"
        and health.get("worker") in ("running", "not_running", "stale")
        and (
            expected_supervisor_pid is None
            or health.get("supervisor_pid") == expected_supervisor_pid
        )
    ):
        api = "reachable"
        proof = health.pop("diagnostic_proof", None)
        if health.get("diagnostics_version") != 1:
            recovery.append(
                "Use the same installed Forecast Anything artifact for the service and client."
            )
        elif not (
            isinstance(proof, str)
            and re.fullmatch(r"[0-9a-f]{64}", proof)
            and hmac.compare_digest(proof, _proof(token, nonce, health))
        ):
            authentication = "rejected"
            recovery.append(
                "Use the same private workspace config for the service and MCP; restart the adapter after changes."
            )
        else:
            authentication = "accepted"
            worker = health["worker"]
            required_model = health.get("required_provider") == "timestral"
            candidate_version = health.get("runtime_version")
            if isinstance(candidate_version, str) and re.fullmatch(
                r"[0-9][A-Za-z0-9.+!-]{0,47}", candidate_version
            ):
                remote_version = candidate_version
            if remote_version != local_version:
                recovery.append(
                    "Use the same installed Forecast Anything artifact for the service and client."
                )
            state = health.get("worker_model") if worker == "running" else None
            if not isinstance(state, str) or state not in _MODEL_STATES:
                state = health.get("model_cache")
                if state == "loaded":
                    state = "unverified"
            if isinstance(state, str) and state in _MODEL_STATES:
                model = state
            if worker != "running":
                recovery.append(
                    "Start the workspace worker with service start or up; check its logs if the heartbeat is stale."
                )
            if model in {"weights_missing", "model_not_prepared", "model_load_failed"}:
                recovery.append(
                    "Run forecast-anything model prepare --config /absolute/path/to/config.json for the workspace, then restart the service."
                )
            elif model in {
                "missing_dependency",
                "missing_model_dependency",
                "code_revision_mismatch",
                "model_code_revision_mismatch",
            }:
                recovery.append(
                    "Reinstall the pinned artifact dependencies, prepare Timestral and restart the service."
                )
            elif model != "loaded" or not required_model:
                recovery.append(
                    "Use the managed service or up --verify-model to confirm the worker can load Timestral."
                )
    elif api == "unreachable":
        recovery.append(
            "Start the workspace service with service start or up; verify its loopback port."
        )
    else:
        recovery.append(
            "Verify that the managed workspace owns this port. Stop any competing supervisor or select a free port for a new workspace."
        )
    if not csv_roots or readable != len(csv_roots):
        recovery.append(
            "Configure readable CSV roots to register local sources; grant existing source IDs with permissions grant."
        )
    return {
        "api": api,
        "authentication": authentication,
        "worker": worker,
        "model": model,
        "runtime_version": remote_version,
        "client_version": local_version,
        "permissions": {
            "csv_roots": len(csv_roots),
            "readable_csv_roots": readable,
            "source_grants": len(source_ids),
        },
        "ready": (
            api == "reachable"
            and authentication == "accepted"
            and worker == "running"
            and model == "loaded"
            and required_model
            and remote_version == local_version
        ),
        "recovery": recovery,
    }


def diagnose_workspace(config: dict, *, expected_supervisor_pid=None) -> dict:
    return diagnose(
        f"http://127.0.0.1:{config['port']}",
        config["token"],
        config["csv_roots"],
        config["source_ids"],
        expected_supervisor_pid=expected_supervisor_pid,
    )
