"""HTTP source ingestion, network boundaries and credential handling."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from source_fixtures import AS_OF, MAPPING

from forecast_anything.contracts import DomainError, SourceSpec
from forecast_anything.sources.profiling import ingest_source, inspect_source


@pytest.fixture
def http_source():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/unauthorized":
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"secret response body")
            elif self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "http://localhost:1/stolen?token=secret")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        [
                            {
                                "date": "2026-10-23",
                                "published": "2026-10-23",
                                "edition": "a",
                                "amount": 3,
                            }
                        ]
                    ).encode()
                )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def source(path="/"):
        return SourceSpec(
            source_id="remote",
            kind="http_json",
            location=f"http://127.0.0.1:{server.server_port}{path}",
            secret_ref=None,
            mapping=MAPPING,
            refresh_seconds=60,
        )

    yield source
    server.shutdown()
    thread.join()
    server.server_close()


def test_http_json_get_ingests_without_model(http_source):
    source = http_source()
    profile = inspect_source(source)
    assert profile.unresolved == ()
    assert ingest_source(source, AS_OF).observations[0].value == 3
    assert (
        ingest_source(source, AS_OF).snapshot_id
        == ingest_source(source, AS_OF).snapshot_id
    )


def test_http_401_is_explicit_source_unavailable(http_source):
    with pytest.raises(DomainError) as error:
        ingest_source(http_source("/unauthorized"), AS_OF)
    assert error.value.code == "source_unavailable"
    assert error.value.details["status"] == 401
    assert "secret response body" not in error.value.model_dump_json()


def test_cross_origin_redirect_is_rejected(http_source):
    with pytest.raises(DomainError) as error:
        inspect_source(http_source("/redirect"))
    assert error.value.code == "source_unavailable"
    assert error.value.details["reason"] == "unsafe_redirect"
    assert "stolen" not in error.value.model_dump_json()


def test_secret_ref_requires_https_before_resolver_is_called(http_source):
    source = http_source().model_copy(update={"secret_ref": "vault/private"})

    def resolver(source_id, secret_ref):
        pytest.fail("resolver must not run on insecure transport")

    with pytest.raises(DomainError) as error:
        inspect_source(source, secret_resolver=resolver)
    assert error.value.details["reason"] == "insecure_credentials"
    assert "vault/private" not in error.value.model_dump_json()


def test_https_secret_is_source_scoped_and_redacted(monkeypatch):
    from forecast_anything.connectors import http_json

    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return b'[{"value": 1, "note": "private-token", "secret": "vault/private"}]'

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://example.test/data"
            assert request.get_header("Authorization") == "Bearer private-token"
            return Response()

    monkeypatch.setattr(http_json, "build_opener", lambda *args: Opener())

    def resolver(source_id, secret_ref):
        seen.append((source_id, secret_ref))
        return "private-token"

    source = SourceSpec(
        source_id="remote",
        kind="http_json",
        location="https://example.test/data",
        secret_ref="vault/private",
        mapping={},
        refresh_seconds=60,
    )
    profile = inspect_source(source, secret_resolver=resolver)
    assert seen == [("remote", "vault/private")]
    assert "private-token" not in profile.model_dump_json()
    assert "vault/private" not in profile.model_dump_json()
    assert "secret" not in profile.fields


def test_null_requires_explicit_missing_value_semantics(http_source, monkeypatch):
    from forecast_anything.connectors import http_json

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return b'[{"date":"2026-10-23","published":"2026-10-23","edition":"a","amount":null}]'

    class Opener:
        def open(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(http_json, "build_opener", lambda *args: Opener())
    source = http_source()
    with pytest.raises(DomainError) as error:
        ingest_source(source, AS_OF)
    assert error.value.code == "invalid_source_row"
    declared = source.model_copy(
        update={"mapping": {**MAPPING, "missing_values": {"constant": [None]}}}
    )
    assert ingest_source(declared, AS_OF).observations[0].value is None


def test_nonfinite_http_cells_fail_without_echoing_content(http_source, monkeypatch):
    from forecast_anything.connectors import http_json

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return b'[{"amount":NaN,"api_key":"private-value"}]'

    class Opener:
        def open(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(http_json, "build_opener", lambda *args: Opener())
    with pytest.raises(DomainError) as error:
        inspect_source(http_source())
    assert error.value.code == "invalid_source_data"
    assert "private-value" not in error.value.model_dump_json()


def test_resolved_credentials_cannot_be_reintroduced_in_query(monkeypatch):
    from forecast_anything.connectors import http_json

    def unexpected_open(*args):
        pytest.fail("credential-bearing URL must not be requested")

    monkeypatch.setattr(http_json, "build_opener", unexpected_open)
    source = SourceSpec(
        source_id="remote",
        kind="http_json",
        location="https://example.test/data?filter=private-token",
        secret_ref="vault/private",
        mapping={},
        refresh_seconds=60,
    )
    with pytest.raises(DomainError) as error:
        inspect_source(
            source, secret_resolver=lambda source_id, secret_ref: "private-token"
        )
    assert error.value.code == "source_unavailable"
    assert error.value.details["reason"] == "credentials_in_url"
    assert "private-token" not in error.value.model_dump_json()


def test_network_failure_is_explicit_and_redacted(monkeypatch):
    from urllib.error import URLError

    from forecast_anything.connectors import http_json

    class Opener:
        def open(self, request, timeout):
            raise URLError("private-token from transport")

    monkeypatch.setattr(http_json, "build_opener", lambda *args: Opener())
    source = SourceSpec(
        source_id="remote",
        kind="http_json",
        location="https://example.test/data",
        secret_ref="vault/private",
        mapping={},
        refresh_seconds=60,
    )
    with pytest.raises(DomainError) as error:
        inspect_source(
            source, secret_resolver=lambda source_id, secret_ref: "private-token"
        )
    assert error.value.code == "source_unavailable"
    assert "private-token" not in error.value.model_dump_json()


def test_json_records_path_is_explicit(monkeypatch):
    from forecast_anything.connectors import http_json

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return b'{"data":{"observations":[{"date":"2026-10-23","published":"2026-10-23","edition":"a","amount":7}]}}'

    class Opener:
        def open(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(http_json, "build_opener", lambda *args: Opener())
    source = SourceSpec(
        source_id="remote",
        kind="http_json",
        location="https://example.test/data",
        secret_ref=None,
        mapping=MAPPING,
        refresh_seconds=60,
    )
    with pytest.raises(DomainError) as error:
        ingest_source(source, AS_OF)
    assert error.value.code == "invalid_source_data"
    selected = source.model_copy(
        update={"mapping": {**MAPPING, "records_path": "data.observations"}}
    )
    assert ingest_source(selected, AS_OF).observations[0].value == 7
