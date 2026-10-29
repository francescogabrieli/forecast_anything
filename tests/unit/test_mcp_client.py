"""Operator and HTTP boundaries for the optional local MCP adapter."""

import asyncio
import importlib
import json

import httpx
import pytest

from forecast_anything.contracts import SourceSpec


def config_module():
    return importlib.import_module("forecast_anything.mcp_adapter.config")


@pytest.fixture(autouse=True)
def operator_env(monkeypatch):
    for name in (
        "FORECAST_ANYTHING_MCP_API_URL",
        "FORECAST_ANYTHING_MCP_CSV_ROOTS",
        "FORECAST_ANYTHING_MCP_SOURCE_IDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FORECAST_ANYTHING_WORKSPACE_TOKEN", "operator-secret")


def test_config_defaults_are_local_and_deny_source_access():
    config = config_module().McpConfig.from_env()
    assert config.api_url == "http://127.0.0.1:8000"
    assert config.workspace_token == "operator-secret"
    assert config.csv_roots == ()
    assert config.source_ids == frozenset()
    assert "operator-secret" not in repr(config)


@pytest.mark.parametrize("token", [None, "", " ", "secret\nheader", "private secret"])
def test_missing_or_unsafe_token_is_a_safe_configuration_error(monkeypatch, token):
    module = config_module()
    if token is None:
        monkeypatch.delenv("FORECAST_ANYTHING_WORKSPACE_TOKEN")
    else:
        monkeypatch.setenv("FORECAST_ANYTHING_WORKSPACE_TOKEN", token)
    with pytest.raises(module.McpConfigError) as error:
        module.McpConfig.from_env()
    assert error.value.code == "configuration_error"
    assert str(error.value) == "configuration_error"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://example.com",
        "http://127.1:8000",
        "http://127.0.0.2:8000",
        "http://2130706433:8000",
        "http://[::ffff:127.0.0.1]:8000",
        "http://private:secret@127.0.0.1:8000",
        "http://127.0.0.1:8000?private=secret",
        "http://127.0.0.1:8000#private",
        "http://127.0.0.1:8000/v1",
        "http://127.0.0.1:8000?",
        "http://127.0.0.1:8000#",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "file:///private/data",
        "http://127.0.0.1:8000\\@example.com",
    ],
)
def test_configuration_rejects_origins_that_escape_explicit_loopback(monkeypatch, url):
    module = config_module()
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_API_URL", url)
    with pytest.raises(module.McpConfigError) as error:
        module.McpConfig.from_env()
    assert str(error.value) == "configuration_error"
    assert url not in repr(error.value)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000", "http://[::1]:8000"])
def test_explicit_loopback_origins_are_supported(monkeypatch, url):
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_API_URL", url)
    assert config_module().McpConfig.from_env().api_url == url


@pytest.mark.parametrize(
    "roots", ["not-json", "{}", '"/private"', "[1]", "[null]", '["relative"]']
)
def test_malformed_roots_do_not_expose_configuration(monkeypatch, roots):
    module = config_module()
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_CSV_ROOTS", roots)
    with pytest.raises(module.McpConfigError) as error:
        module.McpConfig.from_env()
    assert str(error.value) == "configuration_error"


def test_roots_must_be_existing_directories(monkeypatch, tmp_path):
    module = config_module()
    file = tmp_path / "private-file.csv"
    file.write_text("value\n1\n")
    for root in (file, tmp_path / "private-missing"):
        monkeypatch.setenv("FORECAST_ANYTHING_MCP_CSV_ROOTS", json.dumps([str(root)]))
        with pytest.raises(module.McpConfigError) as error:
            module.McpConfig.from_env()
        assert str(error.value) == "configuration_error"
        assert str(root) not in repr(error.value)


@pytest.mark.parametrize(
    "source_ids", ["not-json", "{}", '"source"', "[1]", "[null]", '[""]', '[" "]']
)
def test_source_allowlist_requires_json_nonempty_strings(monkeypatch, source_ids):
    module = config_module()
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_SOURCE_IDS", source_ids)
    with pytest.raises(module.McpConfigError) as error:
        module.McpConfig.from_env()
    assert str(error.value) == "configuration_error"


def test_source_allowlist_is_operator_configuration(monkeypatch):
    monkeypatch.setenv(
        "FORECAST_ANYTHING_MCP_SOURCE_IDS", '["sales", "history", "sales"]'
    )
    assert config_module().McpConfig.from_env().source_ids == {"sales", "history"}


@pytest.mark.parametrize(
    "name", ["FORECAST_ANYTHING_MCP_CSV_ROOTS", "FORECAST_ANYTHING_MCP_SOURCE_IDS"]
)
def test_excessively_nested_configuration_is_a_safe_error(monkeypatch, name):
    module = config_module()
    monkeypatch.setenv(name, "[" * 2000 + "]" * 2000)
    with pytest.raises(module.McpConfigError, match="^configuration_error$"):
        module.McpConfig.from_env()


def source(path, **updates):
    return SourceSpec(
        source_id="history",
        kind=updates.get("kind", "csv"),
        location=str(path),
        secret_ref=updates.get("secret_ref"),
        refresh_seconds=60,
        mapping={"value": "sales"},
    )


def test_csv_guard_returns_resolved_spec_preserving_semantics(monkeypatch, tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    path = root / "data.csv"
    path.write_text("sales\n1\n")
    link = root / "link.csv"
    link.symlink_to(path)
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_CSV_ROOTS", json.dumps([str(root)]))
    config = config_module().McpConfig.from_env()
    original = source(link)
    validated = config.validate_csv(original)
    assert validated.location == str(path.resolve())
    assert validated.mapping == {"value": "sales"}
    assert validated.source_id == "history"
    assert original.location == str(link)
    assert str(root) not in repr(config)


@pytest.mark.parametrize(
    "case",
    [
        "outside",
        "traversal",
        "symlink",
        "directory",
        "missing",
        "relative",
        "kind",
        "secret",
    ],
)
def test_csv_guard_rejects_unapproved_files_and_capabilities(
    monkeypatch, tmp_path, case
):
    module = config_module()
    root = tmp_path / "allowed"
    root.mkdir()
    inside = root / "data.csv"
    inside.write_text("sales\n1\n")
    outside = tmp_path / "private.csv"
    outside.write_text("sales\n9\n")
    link = root / "link.csv"
    link.symlink_to(outside)
    paths = {
        "outside": outside,
        "traversal": root / ".." / "private.csv",
        "symlink": link,
        "directory": root,
        "missing": root / "missing.csv",
        "relative": "data.csv",
        "kind": inside,
        "secret": inside,
    }
    monkeypatch.setenv("FORECAST_ANYTHING_MCP_CSV_ROOTS", json.dumps([str(root)]))
    spec = source(
        paths[case],
        kind="http_json" if case == "kind" else "csv",
        secret_ref="private-credential" if case == "secret" else None,
    )
    with pytest.raises(module.McpConfigError) as error:
        module.McpConfig.from_env().validate_csv(spec)
    assert error.value.code == "source_forbidden"
    assert str(error.value) == "source_forbidden"
    assert str(tmp_path) not in repr(error.value)


def test_unconfigured_roots_deny_even_existing_csv(tmp_path):
    module = config_module()
    path = tmp_path / "data.csv"
    path.write_text("sales\n1\n")
    with pytest.raises(module.McpConfigError, match="^source_forbidden$"):
        module.McpConfig.from_env().validate_csv(source(path))


def client_module():
    return importlib.import_module("forecast_anything.mcp_adapter.client")


def request(transport, method="GET", path="/v1/capabilities", **kwargs):
    async def run():
        async with client_module().CoreClient(
            config_module().McpConfig.from_env(), transport=transport
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


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
            with pytest.raises(module.CoreRequestError, match="^network_error$"):
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
    with pytest.raises(module.CoreRequestError, match="^invalid_response$"):
        request(httpx.MockTransport(lambda req: httpx.Response(200, content=payload)))


def test_json_number_overflow_is_not_returned_as_an_infinite_forecast():
    module = client_module()
    with pytest.raises(module.CoreRequestError, match="^invalid_response$"):
        request(
            httpx.MockTransport(
                lambda req: httpx.Response(200, content=b'{"forecast":1e999}')
            )
        )


def test_response_body_is_bounded_and_stream_closed_without_reading_the_rest():
    module = client_module()
    stream = Chunks([b" " * (64 * 1024)] * 17 + [b"private data never read"])
    with pytest.raises(module.CoreRequestError, match="^response_too_large$"):
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
    with pytest.raises(module.CoreRequestError, match="^response_too_large$"):
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
    with pytest.raises(module.CoreRequestError, match="^invalid_response$"):
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

    with pytest.raises(module.CoreRequestError, match="^request_too_large$"):
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
    with pytest.raises(module.CoreRequestError, match="^invalid_request$"):
        request(
            httpx.MockTransport(lambda req: pytest.fail("must not send")),
            "POST",
            "/v1/jobs",
            body=body,
        )


@pytest.mark.parametrize(
    "path",
    [
        "http://example.com/v1/jobs",
        "//example.com/v1/jobs",
        "/v1/jobs/../sources",
        "/v1/jobs/id?token=private",
        "/v1/jobs/id#private",
        "/v1/jobs/id/other",
        "/v1/agent/operations",
        "/v1/sources/preview",
        "/v1/events/stream",
        "/v1/jobs/raw space",
        "/v1/jobs/%ZZ",
        "/v1/jobs/..",
        "/v1/jobs/.",
    ],
)
def test_client_only_sends_fixed_route_shapes(path):
    module = client_module()
    with pytest.raises(module.CoreRequestError, match="^invalid_request$"):
        request(
            httpx.MockTransport(lambda req: pytest.fail("must not send")), path=path
        )


def test_client_rejects_unexposed_mutation_methods():
    module = client_module()
    with pytest.raises(module.CoreRequestError, match="^invalid_request$"):
        request(
            httpx.MockTransport(lambda req: pytest.fail("must not send")),
            "DELETE",
            "/v1/jobs/job",
        )


@pytest.mark.parametrize(
    ("identifier", "encoded"),
    [
        (
            "job/../sources?token=secret#fragment",
            "job%2F..%2Fsources%3Ftoken%3Dsecret%23fragment",
        ),
        ("%2Fprivate", "%252Fprivate"),
        ("é data", "%C3%A9%20data"),
        (".", "%2E"),
        ("..", "%2E%2E"),
    ],
)
def test_identifier_is_one_encoded_segment_without_url_escape(identifier, encoded):
    module = client_module()
    seen = []

    def respond(req):
        seen.append(req.url)
        return httpx.Response(200, json={"job_id": "safe"})

    segment = module.encode_identifier(identifier)
    assert segment == encoded
    assert request(httpx.MockTransport(respond), path=f"/v1/jobs/{segment}") == {
        "job_id": "safe"
    }
    assert seen[0].raw_path == f"/v1/jobs/{encoded}".encode()
    assert seen[0].host == "127.0.0.1"
    assert seen[0].query == b""


@pytest.mark.parametrize("identifier", ["", "\nprivate", "x\x00y", 123, None])
def test_unsafe_identifiers_are_safe_errors(identifier):
    module = client_module()
    with pytest.raises(module.CoreRequestError, match="^invalid_request$"):
        module.encode_identifier(identifier)


def test_query_parameters_are_encoded_without_overriding_origin_or_auth():
    seen = []

    def respond(req):
        seen.append(req)
        return httpx.Response(200, json={})

    assert (
        request(
            httpx.MockTransport(respond), path="/v1/graphs/g", params={"version": 2}
        )
        == {}
    )
    assert str(seen[0].url) == "http://127.0.0.1:8000/v1/graphs/g?version=2"
    assert seen[0].headers["Authorization"] == "Bearer operator-secret"
