"""HTTP boundary of the optional Eve discovery gateway."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.error import HTTPError

import pytest

from forecast_anything.contracts import DomainError


def test_agent_gateway_sends_scoped_bearer_and_rejects_untrusted_response(monkeypatch):
    from forecast_anything.discovery import agent_gateway

    requests = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, size):
            return json.dumps(self.payload).encode()

    responses = iter(
        (
            {"sessionId": "session-1"},
            {"state": "pending", "candidates": []},
            {"state": "completed", "candidates": []},
        )
    )

    def open_request(request, timeout):
        requests.append(request)
        assert timeout == 5
        return Response(next(responses))

    monkeypatch.setattr(agent_gateway, "urlopen", open_request)
    gateway = agent_gateway.AgentGateway(
        "http://127.0.0.1:3333", token="agent", timeout_seconds=5
    )
    assert gateway.start("epoch", ("sales",), "job-key") == "session-1"
    assert gateway.poll("session-1") is None
    assert gateway.poll("session-1") == ()
    assert [request.get_header("Authorization") for request in requests] == [
        "Bearer agent"
    ] * 3
    assert json.loads(requests[0].data) == {
        "epochId": "epoch",
        "sourceIds": ["sales"],
        "idempotencyKey": "job-key",
    }
    assert requests[0].full_url.endswith("/forecast/discover")
    assert requests[1].full_url.endswith("/forecast/discover/session-1")

    monkeypatch.setattr(
        agent_gateway,
        "urlopen",
        lambda *_args, **_kwargs: Response(
            {"state": "completed", "candidates": [{"probability": 0.99}]}
        ),
    )
    with pytest.raises(DomainError, match="invalid_agent_response"):
        gateway.poll("session-1")


def test_agent_gateway_never_returns_remote_body_or_credentials(monkeypatch):
    from forecast_anything.discovery import agent_gateway

    def unavailable(*_args, **_kwargs):
        raise HTTPError(
            "http://127.0.0.1:3333/forecast/discover",
            503,
            "private-secret",
            {},
            None,
        )

    monkeypatch.setattr(agent_gateway, "urlopen", unavailable)
    gateway = agent_gateway.AgentGateway(
        "http://127.0.0.1:3333", token="private-secret"
    )
    with pytest.raises(DomainError, match="agent_gateway_unavailable") as error:
        gateway.start("epoch", ("sales",), "job-key")
    assert "private-secret" not in error.value.model_dump_json()


def test_agent_gateway_rejects_redirect_without_sending_bearer_to_target():
    from forecast_anything.discovery.agent_gateway import AgentGateway

    redirected_requests = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self):
            redirected_requests.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"sessionId":"redirected"}')

        def log_message(self, *_args):
            pass

    target = HTTPServer(("127.0.0.1", 0), Target)

    class Redirect(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(302)
            self.send_header(
                "Location", f"http://127.0.0.1:{target.server_port}/capture"
            )
            self.end_headers()

        def log_message(self, *_args):
            pass

    origin = HTTPServer(("127.0.0.1", 0), Redirect)
    threads = [
        Thread(target=server.serve_forever, daemon=True) for server in (target, origin)
    ]
    for thread in threads:
        thread.start()
    try:
        gateway = AgentGateway(
            f"http://127.0.0.1:{origin.server_port}", token="private-agent-token"
        )
        with pytest.raises(DomainError, match="agent_gateway_unavailable"):
            gateway.start("epoch", ("sales",), "job-key")
        assert redirected_requests == []
    finally:
        for server in (origin, target):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()
