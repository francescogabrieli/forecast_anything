"""MCP HTTP route allowlists and URL encoding."""

import httpx
import pytest
from mcp_client_fixtures import client_module, request
from mcp_client_fixtures import operator_env as operator_env


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
    with pytest.raises(module.CoreRequestError, match=r"^invalid_request$"):
        request(
            httpx.MockTransport(lambda req: pytest.fail("must not send")), path=path
        )


def test_client_rejects_unexposed_mutation_methods():
    module = client_module()
    with pytest.raises(module.CoreRequestError, match=r"^invalid_request$"):
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
    with pytest.raises(module.CoreRequestError, match=r"^invalid_request$"):
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


@pytest.mark.parametrize(
    "path", ["/v1/backtests/a%2Fb%3Fx%23z%25", "/v1/backtests/b/origins"]
)
def test_backtest_client_permits_only_fixed_public_read_shapes(path):
    def respond(req):
        assert req.method == "GET"
        return httpx.Response(200, json={"backtest_id": "b"})

    assert request(httpx.MockTransport(respond), path=path) == {"backtest_id": "b"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/watches"),
        ("GET", "/v1/watches/w%2F1"),
        ("GET", "/v1/watches/w%2F1/history"),
        ("GET", "/v1/watches/w%2F1/changes"),
        ("POST", "/v1/watches"),
        ("PATCH", "/v1/watches/w%2F1"),
    ],
)
def test_client_permits_only_explicit_watch_routes(method, path):
    seen = []

    def respond(req):
        seen.append(req)
        return httpx.Response(200, json={})

    assert request(httpx.MockTransport(respond), method, path) == {}
    assert seen[0].method == method


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/watches/w/history/private"),
        ("POST", "/v1/watches/w"),
        ("PATCH", "/v1/watches"),
        ("DELETE", "/v1/watches/w"),
    ],
)
def test_client_rejects_unexposed_watch_routes(method, path):
    with pytest.raises(client_module().CoreRequestError, match=r"^invalid_request$"):
        request(
            httpx.MockTransport(
                lambda req: pytest.fail("unexposed watch route reached HTTP")
            ),
            method,
            path,
        )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/backtests"),
        ("GET", "/v1/backtests/b/archive"),
        ("GET", "/v1/backtests/b/plan"),
        ("GET", "/v1/backtests/b/origins/0"),
        ("POST", "/v1/backtests/b"),
        ("DELETE", "/v1/backtests/b"),
    ],
)
def test_backtest_client_rejects_unexposed_private_or_mutating_routes(method, path):
    with pytest.raises(client_module().CoreRequestError, match=r"^invalid_request$"):
        request(
            httpx.MockTransport(
                lambda req: pytest.fail("unexposed route reached HTTP")
            ),
            method=method,
            path=path,
        )
