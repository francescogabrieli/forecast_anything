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

    def start(command):
        calls.append(command)
        return (api, worker)[len(calls) - 1]

    monkeypatch.setattr(subprocess, "Popen", start)
    assert run_services(tmp_path / "state.db", "127.0.0.1", 8000) == 1
    assert worker.terminated
    assert calls[0][-4:] == ["--host", "127.0.0.1", "--port", "8000"]
    assert calls[1][-2:] == ["--db", str(tmp_path / "state.db")]


def test_start_failure_cleans_up_started_child(monkeypatch, tmp_path):
    api = Process()
    calls = 0

    def start(command):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("cannot start worker")
        return api

    monkeypatch.setattr(subprocess, "Popen", start)
    assert run_services(tmp_path / "state.db", "127.0.0.1", 8000) == 1
    assert api.terminated
