"""Source boundaries: explicit semantics, bounded samples and safe credentials."""

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from forecast_anything.contracts import DomainError, SourceSpec
from forecast_anything.sources.catalog import SourceCatalog
from forecast_anything.sources.profiling import ingest_source, inspect_source

AS_OF = datetime(2026, 10, 24, tzinfo=timezone.utc)
MAPPING = {
    "series_id": {"constant": "sales"},
    "event_time": "date",
    "available_at": "published",
    "revision": "edition",
    "value": "amount",
    "unit": {"constant": "count"},
    "frequency": {"constant": "D"},
    "timezone": {"constant": "UTC"},
    "calendar": {"constant": "gregorian"},
    "missing_values": {"constant": [""]},
}


def csv_source(tmp_path, text="date,amount\n2026-10-24,1\n", mapping=None):
    path = tmp_path / "source.csv"
    path.write_text(text)
    return SourceSpec(
        source_id="s",
        kind="csv",
        location=str(path),
        secret_ref=None,
        mapping=mapping or {},
        refresh_seconds=60,
    )


def test_profile_does_not_invent_units(tmp_path):
    source = csv_source(tmp_path, "date,value\n2026-10-24,1\n")
    profile = inspect_source(source)
    assert "unit" in profile.unresolved
    assert "frequency" in profile.unresolved
    assert "timezone" in profile.unresolved
    assert profile.proposed_mapping["event_time"] == "date"
    assert "unit" not in profile.proposed_mapping


def test_ambiguous_timestamp_requires_resolution(tmp_path):
    profile = inspect_source(
        csv_source(tmp_path, "date,timestamp,value\n2026-10-24,2026-10-23,1\n")
    )
    assert "event_time" in profile.unresolved
    assert "event_time" not in profile.proposed_mapping


def test_unknown_unit_blocks_composition(tmp_path):
    mapping = {key: value for key, value in MAPPING.items() if key != "unit"}
    source = csv_source(
        tmp_path, "date,published,edition,amount\n2026-10-23,2026-10-23,a,1\n", mapping
    )
    with pytest.raises(DomainError) as error:
        ingest_source(source, AS_OF)
    assert error.value.code == "unresolved_source_mapping"
    assert "unit" in error.value.details["unresolved"]


def test_explicit_mapping_freezes_point_in_time(tmp_path):
    source = csv_source(
        tmp_path,
        "date,published,edition,amount\n2026-10-23,2026-10-23,a,1\n2026-10-23,2026-10-25,b,2\n",
        MAPPING,
    )
    assert inspect_source(source).unresolved == ()
    snapshot = ingest_source(source, AS_OF)
    assert len(snapshot.observations) == 1
    assert snapshot.observations[0].value == 1
    assert snapshot.observations[0].unit == "count"
    assert snapshot.observations[0].event_time.tzinfo is not None
    assert "source_revision=" in " ".join(snapshot.assumptions)


def test_duplicate_fetch_is_stable(tmp_path):
    source = csv_source(
        tmp_path, "date,published,edition,amount\n2026-10-23,2026-10-23,a,1\n", MAPPING
    )
    first = ingest_source(source, AS_OF)
    assert first.snapshot_id == ingest_source(source, AS_OF).snapshot_id
    changed = source.model_copy(
        update={"mapping": {**MAPPING, "unit": {"constant": "USD"}}}
    )
    assert first.snapshot_id != ingest_source(changed, AS_OF).snapshot_id


def test_samples_are_typed_and_bounded(tmp_path):
    source = csv_source(tmp_path, "date,value\n" + "2026-10-24,1\n" * 120)
    profile = inspect_source(source)
    assert len(profile.sample_rows) == 100
    assert profile.fields["value"].data_type == "integer"
    assert profile.fields["date"].data_type == "datetime"
    assert profile.sample_rows[0]["value"] == 1


def test_credentials_never_enter_profile(tmp_path):
    source = csv_source(
        tmp_path,
        'date,value,api_key,notes\n2026-10-24,1,private-token,"Authorization: Bearer hidden"\n',
    )
    profile = inspect_source(source)
    serialized = profile.model_dump_json()
    assert "private-token" not in serialized
    assert "hidden" not in serialized
    assert "api_key" not in profile.fields
    assert profile.sample_rows[0]["notes"] == "[redacted]"


def test_catalog_preserves_immutable_spec_and_assumption_revisions(tmp_path):
    source = csv_source(tmp_path)
    catalog_path = tmp_path / "catalog.db"
    catalog = SourceCatalog(catalog_path)
    first = catalog.append(source, assumptions=("reviewed",))
    source.mapping["unit"] = {"constant": "count"}
    second = catalog.append(source, assumptions=("reviewed",))
    third = catalog.append(source, assumptions=("reviewed again",))
    assert first.revision != second.revision != third.revision
    assert first.spec.mapping == {}
    assert (
        catalog.append(source, assumptions=("reviewed again",)).revision
        == third.revision
    )
    reopened = SourceCatalog(catalog_path)
    assert len(reopened.history("s")) == 3
    assert reopened.get("s", first.revision).spec.mapping == {}
    assert reopened.get("s").assumptions == ("reviewed again",)


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


def test_invalid_row_errors_do_not_echo_source_content(tmp_path):
    source = csv_source(
        tmp_path,
        "date,published,edition,amount\n2026-10-23,2026-10-23,a,Authorization: Bearer private-token\n",
        MAPPING,
    )
    with pytest.raises(DomainError) as error:
        ingest_source(source, AS_OF)
    assert "private-token" not in error.value.model_dump_json()
    assert error.value.code == "invalid_source_row"


def test_sensitive_field_values_are_redacted_in_other_sample_columns(tmp_path):
    source = csv_source(
        tmp_path,
        "date,value,api_key,description\n2026-10-24,1,opaque-private-value,opaque-private-value\n",
    )
    assert "opaque-private-value" not in inspect_source(source).model_dump_json()


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


def test_sample_redaction_cannot_silently_change_observation_identity(tmp_path):
    mapping = {**MAPPING, "series_id": "entity"}
    source = csv_source(
        tmp_path,
        'date,published,edition,amount,entity\n2026-10-23,2026-10-23,a,1,"Authorization: Bearer private-value"\n',
        mapping,
    )
    with pytest.raises(DomainError) as error:
        ingest_source(source, AS_OF)
    assert error.value.code == "invalid_source_row"
    assert "private-value" not in error.value.model_dump_json()


def test_dst_ambiguity_is_not_silently_assigned_a_fold(tmp_path):
    mapping = {**MAPPING, "timezone": {"constant": "Europe/Rome"}}
    source = csv_source(
        tmp_path,
        "date,published,edition,amount\n2026-10-25T02:30:00,2026-10-24,a,1\n",
        mapping,
    )
    with pytest.raises(DomainError) as error:
        ingest_source(source, AS_OF)
    assert error.value.code == "invalid_source_row"


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


def test_catalog_database_rejects_history_rewrite(tmp_path):
    import sqlite3

    path = tmp_path / "catalog.db"
    catalog = SourceCatalog(path)
    catalog.append(csv_source(tmp_path))
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM source_revisions")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE source_revisions SET assumptions_json = '[]'")
    assert len(catalog.history("s")) == 1


@pytest.mark.parametrize("kind", ["csv", "http_json"])
@pytest.mark.parametrize("artifact", ["profile", "snapshot"])
def test_sensitive_column_credentials_cannot_reenter_through_mapping_constants(
    tmp_path, monkeypatch, kind, artifact
):
    from forecast_anything.connectors import http_json

    credential = "opaque-private-value"
    mapping = {**MAPPING, "series_id": {"constant": credential}}
    if kind == "csv":
        source = csv_source(
            tmp_path,
            "date,published,edition,amount,api_key\n"
            "2026-10-23,2026-10-23,a,1,opaque-private-value\n",
            mapping,
        )
    else:

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, *args):
                return b'[{"date":"2026-10-23","published":"2026-10-23","edition":"a","amount":1,"api_key":"opaque-private-value"}]'

        class Opener:
            def open(self, *args, **kwargs):
                return Response()

        monkeypatch.setattr(http_json, "build_opener", lambda *args: Opener())
        source = SourceSpec(
            source_id="remote",
            kind="http_json",
            location="https://example.test/data",
            secret_ref=None,
            mapping=mapping,
            refresh_seconds=60,
        )

    # Both entry points must reject before they can return a credential-bearing
    # artifact; their error payloads must also keep the credential private.
    with pytest.raises(DomainError) as error:
        if artifact == "profile":
            inspect_source(source)
        else:
            ingest_source(source, AS_OF)
    assert error.value.code == "invalid_source_mapping"
    assert credential not in error.value.model_dump_json()
