"""Source profiling, catalog history and sample redaction."""

import json

import pytest
from source_fixtures import AS_OF, MAPPING, csv_source

from forecast_anything.contracts import DomainError, SourceSpec
from forecast_anything.sources.catalog import SourceCatalog
from forecast_anything.sources.profiling import ingest_source, inspect_source


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
@pytest.mark.parametrize("credential_row", [0, 100])
def test_sensitive_column_credentials_cannot_reenter_through_mapping_constants(
    tmp_path, monkeypatch, kind, artifact, credential_row
):
    from forecast_anything.connectors import http_json

    credential = "opaque-private-value"
    mapping = {**MAPPING, "series_id": {"constant": credential}}
    if kind == "csv":
        source = csv_source(
            tmp_path,
            "date,published,edition,amount,api_key\n"
            + "2026-10-23,2026-10-23,a,1,\n" * credential_row
            + "2026-10-23,2026-10-23,a,1,opaque-private-value\n",
            mapping,
        )
    else:

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, *args):
                row = {
                    "date": "2026-10-23",
                    "published": "2026-10-23",
                    "edition": "a",
                    "amount": 1,
                    "api_key": "",
                }
                return json.dumps(
                    [row] * credential_row + [{**row, "api_key": credential}]
                ).encode()

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

    if artifact == "profile" and credential_row == 100:
        safe_source = source.model_copy(update={"mapping": MAPPING})
        profile = inspect_source(safe_source)
        assert len(profile.sample_rows) == 100
        assert credential not in profile.model_dump_json()
