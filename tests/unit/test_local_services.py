import subprocess

from forecast_anything.local_services import run_services


class Process:
    def __init__(self, result=None):
        self.result = result
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.result

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return self.result

    def kill(self):
        self.killed = True


def test_child_failure_stops_other_service(monkeypatch, tmp_path):
    api, worker = Process(3), Process()
    calls = []

    def start(command, **kwargs):
        calls.append(command)
        return (api, worker)[len(calls) - 1]

    monkeypatch.setattr(subprocess, "Popen", start)
    assert run_services(tmp_path / "state.db", "127.0.0.1", 0) == 1
    assert worker.terminated
    assert calls[0][-2] == "--socket-fd"
    assert calls[1][-2:] == ["--db", str(tmp_path / "state.db")]


def test_worker_timeout_restarts_worker_without_stopping_api(monkeypatch, tmp_path):
    import signal

    api, timed_out, replacement = Process(), Process(124), Process()
    calls = []
    api_stopped_on_restart = []
    handlers = {}

    def capture_signal(signum, handler):
        if callable(handler):
            handlers[signum] = handler
        return None

    def start(command, **kwargs):
        calls.append(command)
        if len(calls) == 3:
            api_stopped_on_restart.append(api.terminated)
            handlers[signal.SIGTERM](signal.SIGTERM, None)
        return (api, timed_out, replacement)[len(calls) - 1]

    monkeypatch.setattr(subprocess, "Popen", start)
    monkeypatch.setattr(
        "forecast_anything.local_services.signal.signal", capture_signal
    )
    monkeypatch.setattr("forecast_anything.local_services.time.sleep", lambda _: None)

    assert run_services(tmp_path / "state.db", "127.0.0.1", 0) == 0

    assert len(calls) == 3
    assert calls[1] == calls[2]
    assert api_stopped_on_restart == [False]
    assert replacement.terminated


def test_start_failure_cleans_up_started_child(monkeypatch, tmp_path):
    api = Process()
    calls = 0

    def start(command, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("cannot start worker")
        return api

    monkeypatch.setattr(subprocess, "Popen", start)
    assert run_services(tmp_path / "state.db", "127.0.0.1", 0) == 1
    assert api.terminated


def test_interrupt_during_spawn_tracks_api_and_never_starts_worker(
    monkeypatch, tmp_path
):
    import os
    import signal

    api = Process()
    calls = []

    def start(command, **kwargs):
        calls.append(command)
        os.kill(os.getpid(), signal.SIGTERM)
        return api

    monkeypatch.setattr(subprocess, "Popen", start)
    assert run_services(tmp_path / "state.db", "127.0.0.1", 0) == 0
    assert len(calls) == 1
    assert api.terminated
