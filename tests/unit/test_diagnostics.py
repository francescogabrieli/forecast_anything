from forecast_anything import diagnostics


def test_offline_diagnostics_keep_local_permissions_and_recovery(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics, "_get", lambda *args: (None, None))
    result = diagnostics.diagnose(
        "http://127.0.0.1:1234", "private", [tmp_path], {"one"}
    )
    assert result["api"] == "unreachable"
    assert result["authentication"] == result["worker"] == "unknown"
    assert result["permissions"]["source_grants"] == 1
    assert result["permissions"]["readable_csv_roots"] == 1
    assert not result["ready"] and result["recovery"]
    assert "private" not in str(result) and str(tmp_path) not in str(result)


def test_diagnostics_require_loaded_worker_model(monkeypatch, tmp_path):
    payload = {
        "status": "ok",
        "worker": "running",
        "worker_model": "cached",
        "runtime_version": diagnostics.runtime_version(),
        "diagnostics_version": 1,
        "required_provider": "timestral",
        "model_cache": "cached",
    }

    def get(url, path, headers):
        assert path == "/health" and "Authorization" not in headers
        nonce = diagnostics.validated_nonce(headers, "private")
        assert nonce is not None
        return 200, diagnostics.sign_diagnostics(payload, nonce, "private")

    monkeypatch.setattr(diagnostics, "_get", get)
    result = diagnostics.diagnose("http://127.0.0.1:1234", "private", [tmp_path], ())
    assert result["authentication"] == "accepted"
    assert result["model"] == "cached" and not result["ready"]
    payload["worker_model"] = "loaded"
    assert diagnostics.diagnose("http://127.0.0.1:1234", "private", [tmp_path], ())[
        "ready"
    ]


def test_heartbeat_from_previous_supervisor_cannot_report_loaded(tmp_path):
    from forecast_anything.store import Ledger

    ledger = Ledger(tmp_path / "state.db")
    now = ledger.clock()
    ledger.update_worker_heartbeat("old", now, model_status="loaded")
    assert ledger.worker_diagnostics(now, expected_worker_id="new") == (
        "not_running",
        None,
    )
    assert ledger.worker_diagnostics(now, expected_worker_id="old") == (
        "running",
        "loaded",
    )


def test_foreign_supervisor_never_gets_workspace_credentials(monkeypatch, tmp_path):
    requests = []

    def get(url, path, headers):
        requests.append((path, headers))
        return 200, {"status": "ok", "worker": "running", "supervisor_pid": 12}

    monkeypatch.setattr(diagnostics, "_get", get)
    result = diagnostics.diagnose(
        "http://127.0.0.1:1234", "private", [tmp_path], (), expected_supervisor_pid=13
    )
    assert result["api"] == "unexpected_response" and not result["ready"]
    assert len(requests) == 1
    path, headers = requests[0]
    assert path == "/health" and "Authorization" not in headers
    assert "private" not in str(headers)


def test_slow_headers_cannot_extend_diagnostic_deadline(monkeypatch):
    import socket
    import threading
    import time

    monkeypatch.setattr(diagnostics, "_PROBE_TIMEOUT_SECONDS", 0.3)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        def send():
            with listener.accept()[0] as peer:
                peer.recv(4096)
                try:
                    for byte in b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}":
                        peer.sendall(bytes([byte]))
                        time.sleep(0.05)
                except OSError:
                    pass

        server = threading.Thread(target=send, daemon=True)
        server.start()
        start = time.monotonic()
        result = diagnostics.diagnose(f"http://127.0.0.1:{port}", "private", [], ())
        elapsed = time.monotonic() - start
        server.join(timeout=1)
        assert elapsed < 1
        assert not result["ready"]
