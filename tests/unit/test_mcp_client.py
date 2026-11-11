"""MCP HTTP authentication, transport errors and payload bounds."""

import asyncio
import json

import httpx
import pytest
from mcp_client_fixtures import client_module, config_module, request
from mcp_client_fixtures import operator_env as operator_env


def test_authorization_and_timeout_come_from_operator_configuration():
    seen = []

    def respond(req):
        seen.append(req)
        return httpx.Response(200, json={"providers": {}})

    result = request(httpx.MockTransport(respond))
    assert result == {"providers": {}}
    assert len(seen) == 1
    assert seen[0].headers["Authorization"] == "Bearer operator-secret"
    assert seen[0].headers["Accept-Encoding"] == "identity"
    assert seen[0].extensions["timeout"] == {
        "connect": 15.0,
        "read": 15.0,
        "write": 15.0,
        "pool": 15.0,
    }


def test_environment_proxy_and_redirect_configuration_are_disabled(monkeypatch):
    original = httpx.AsyncClient
    options = []

    def configured_client(**kwargs):
        options.append(kwargs)
        return original(**kwargs)

    monkeypatch.setenv("HTTP_PROXY", "http://private:password@proxy.example")
    monkeypatch.setenv("HTTPS_PROXY", "http://private:password@proxy.example")
    monkeypatch.setenv("ALL_PROXY", "http://private:password@proxy.example")
    monkeypatch.setattr(httpx, "AsyncClient", configured_client)
    assert request(httpx.MockTransport(lambda req: httpx.Response(200, json=[]))) == []
    assert options[0]["trust_env"] is False
    assert options[0]["follow_redirects"] is False


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "not_found"),
        (409, "conflict"),
        (422, "validation_error"),
        (500, "upstream_error"),
        (302, "upstream_error"),
    ],
)
def test_upstream_errors_are_safe_codes_without_raw_bodies(status, code, capsys):
    module = client_module()
    calls = []

    def respond(req):
        calls.append(req)
        return httpx.Response(
            status,
            content=b"<html>/private/data operator-secret source instruction</html>",
            headers={"Location": "http://private:password@example.com/private"},
        )

    with pytest.raises(module.CoreRequestError) as error:
        request(
            httpx.MockTransport(respond), "POST", "/v1/jobs", body={"key": "original"}
        )
    assert error.value.code == code
    assert str(error.value) == code
    assert error.value.args == (code,)
    assert len(calls) == 1
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    "error_type",
    [httpx.ConnectError, httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError],
)
def test_network_errors_do_not_retry_or_echo_exceptions(error_type):
    module = client_module()
    calls = []

    def fail(req):
        calls.append(req)
        raise error_type(
            "operator-secret /private/file http://private.example", request=req
        )

    with pytest.raises(module.CoreRequestError) as error:
        request(httpx.MockTransport(fail), "POST", "/v1/jobs", body={"key": "original"})
    assert error.value.code == "network_error"
    assert str(error.value) == "network_error"
    assert error.value.args == ("network_error",)
    assert len(calls) == 1


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.read_count = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.read_count += 1
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    async def aclose(self):
        self.closed = True


def test_lost_submission_response_preserves_key_for_explicit_replay():
    module = client_module()
    accepted = []
    stream = Chunks([b'{"job_id":', httpx.ReadError("private lost response")])

    def respond(req):
        payload = json.loads(req.content)
        accepted.append(payload)
        if len(accepted) == 1:
            return httpx.Response(202, stream=stream)
        return httpx.Response(202, json={"job_id": "accepted-job"})

    async def run():
        async with module.CoreClient(
            config_module().McpConfig.from_env(), transport=httpx.MockTransport(respond)
        ) as client:
            body = {"key": "stable-key", "candidate_id": "candidate"}
            with pytest.raises(module.CoreRequestError, match=r"^network_error$"):
                await client.request("POST", "/v1/jobs", body=body)
            assert len(accepted) == 1
            replay = await client.request("POST", "/v1/jobs", body=body)
            assert replay == {"job_id": "accepted-job"}

    asyncio.run(run())
    assert accepted == [
        {"key": "stable-key", "candidate_id": "candidate"},
        {"key": "stable-key", "candidate_id": "candidate"},
    ]
    assert stream.closed


@pytest.mark.parametrize(
    "payload",
    [
        b"<html>private</html>",
        b"null",
        b"true",
        b"1",
        b'"private"',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b"\xff",
        b"{" + b'"nested":[' * 1200 + b"]" * 1200 + b"}",
    ],
)
def test_invalid_json_or_noncontainer_responses_are_sanitized(payload):
    module = client_module()
    with pytest.raises(module.CoreRequestError, match=r"^invalid_response$"):
        request(httpx.MockTransport(lambda req: httpx.Response(200, content=payload)))


def test_json_number_overflow_is_not_returned_as_an_infinite_forecast():
    module = client_module()
    with pytest.raises(module.CoreRequestError, match=r"^invalid_response$"):
        request(
            httpx.MockTransport(
                lambda req: httpx.Response(200, content=b'{"forecast":1e999}')
            )
        )


def test_response_body_is_bounded_and_stream_closed_without_reading_the_rest():
    module = client_module()
    stream = Chunks([b" " * (64 * 1024)] * 17 + [b"private data never read"])
    with pytest.raises(module.CoreRequestError, match=r"^response_too_large$"):
        request(httpx.MockTransport(lambda req: httpx.Response(200, stream=stream)))
    assert stream.read_count == 17
    assert stream.closed


def test_exact_response_limit_accepts_json():
    payload = b'{"value":"' + b"a" * (1024 * 1024 - 12) + b'"}'
    assert len(payload) == 1024 * 1024
    result = request(
        httpx.MockTransport(lambda req: httpx.Response(200, content=payload))
    )
    assert len(result["value"]) == 1024 * 1024 - 12


def test_declared_oversized_response_is_rejected_without_consuming_stream():
    module = client_module()
    stream = Chunks([b"private"])
    with pytest.raises(module.CoreRequestError, match=r"^response_too_large$"):
        request(
            httpx.MockTransport(
                lambda req: httpx.Response(
                    200, stream=stream, headers={"Content-Length": str(1024 * 1024 + 1)}
                )
            )
        )
    assert stream.read_count == 0
    assert stream.closed


def test_compressed_response_is_refused_before_decompression():
    module = client_module()
    stream = Chunks([b"compressed-untrusted-bytes"])
    with pytest.raises(module.CoreRequestError, match=r"^invalid_response$"):
        request(
            httpx.MockTransport(
                lambda req: httpx.Response(
                    200, stream=stream, headers={"Content-Encoding": "gzip"}
                )
            )
        )
    assert stream.read_count == 0
    assert stream.closed


def test_oversized_request_never_reaches_transport():
    module = client_module()
    calls = []

    def respond(req):
        calls.append(req)
        return httpx.Response(202, json={})

    with pytest.raises(module.CoreRequestError, match=r"^request_too_large$"):
        request(
            httpx.MockTransport(respond),
            "POST",
            "/v1/jobs",
            body={"value": "é" * (1024 * 1024)},
        )
    assert calls == []


def test_exact_serialized_request_limit_is_accepted_unchanged():
    received = []
    body = {"value": "a" * (1024 * 1024 - 12)}

    def respond(req):
        received.append(req.content)
        return httpx.Response(202, json={"job_id": "accepted"})

    assert request(httpx.MockTransport(respond), "POST", "/v1/jobs", body=body) == {
        "job_id": "accepted"
    }
    assert len(received[0]) == 1024 * 1024
    assert json.loads(received[0]) == body


@pytest.mark.parametrize("body", [{"value": float("nan")}, {"value": object()}])
def test_non_json_request_body_is_a_safe_error(body):
    module = client_module()
    with pytest.raises(module.CoreRequestError, match=r"^invalid_request$"):
        request(
            httpx.MockTransport(lambda req: pytest.fail("must not send")),
            "POST",
            "/v1/jobs",
            body=body,
        )
