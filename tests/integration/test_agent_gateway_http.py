"""HTTP boundary of the optional Eve discovery gateway."""

import json
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
