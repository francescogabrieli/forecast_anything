"""Persistent question identity and revision API behavior."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from forecast_anything.api.app import create_app
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger


def _client(path):
    ledger = Ledger(path, clock=lambda: datetime(2026, 11, 7, tzinfo=timezone.utc))
    runtime = Runtime(
        ledger, {"seasonal_naive": SeasonalNaiveProvider(1)}, {}, lambda: ledger.clock()
    )
    return ledger, TestClient(
        create_app(ledger, runtime, "test-token"),
        headers={"Authorization": "Bearer test-token"},
    )


def _question(
    key="question-create", title="Revenue outlook", meaning="Forecast monthly revenue"
):
    return {
        "key": key,
        "title": title,
        "meaning": meaning,
        "source_ids": ["sales"],
        "selection": {"provider": "seasonal_naive", "horizon": 3},
    }


def test_same_key_concurrent_question_create_is_idempotent(tmp_path):
    ledger, client = _client(tmp_path / "questions.db")
    payload = _question()

    def create(_):
        response = TestClient(
            client.app, headers={"Authorization": "Bearer test-token"}
        ).post("/v1/questions", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    with ThreadPoolExecutor(max_workers=8) as pool:
        created = list(pool.map(create, range(16)))

    assert len({item["question_id"] for item in created}) == 1
    assert all(item == created[0] for item in created)
    assert ledger.get_question(created[0]["question_id"]).revision_count == 1


def test_question_create_key_conflicts_on_changed_content(tmp_path):
    _, client = _client(tmp_path / "questions.db")
    assert client.post("/v1/questions", json=_question()).status_code == 201
    conflict = client.post("/v1/questions", json=_question(meaning="Different intent"))
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"


def test_title_edit_does_not_change_semantic_revision_and_revisions_are_cas(tmp_path):
    _, client = _client(tmp_path / "questions.db")
    created = client.post("/v1/questions", json=_question()).json()
    question_id = created["question_id"]

    renamed = client.patch(
        f"/v1/questions/{question_id}", json={"title": "Board outlook"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["current_revision"] == 1

    request = {
        "key": "revise-1",
        "expected_revision": 1,
        "meaning": "Forecast quarterly net revenue",
        "source_ids": ["sales", "costs"],
        "selection": {"provider": "seasonal_naive", "horizon": 4},
    }
    first = client.post(f"/v1/questions/{question_id}/revisions", json=request)
    retry = client.post(f"/v1/questions/{question_id}/revisions", json=request)
    assert first.status_code == 200, first.text
    assert retry.status_code == 200, retry.text
    assert first.json() == retry.json()
    assert first.json()["current_revision"] == 2

    stale = client.post(
        f"/v1/questions/{question_id}/revisions",
        json={
            **request,
            "key": "stale",
            "expected_revision": 1,
            "meaning": "A third intent",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_question_revision"

    history = client.get(
        f"/v1/questions/{question_id}/revisions", params={"offset": 0, "limit": 1}
    )
    assert history.status_code == 200
    assert history.json()["revisions"][0]["revision"] == 1
    assert history.json()["next_offset"] == 1


def test_question_survives_api_restart_and_pages_are_stable(tmp_path):
    path = tmp_path / "questions.db"
    _, client = _client(path)
    first = client.post("/v1/questions", json=_question("z-question")).json()
    second = client.post("/v1/questions", json=_question("a-question", "Costs")).json()

    restarted_ledger, restarted = _client(path)
    assert restarted.get(f"/v1/questions/{first['question_id']}").json() == first
    page1 = restarted.get("/v1/questions", params={"offset": 0, "limit": 1}).json()
    page2 = restarted.get("/v1/questions", params={"offset": 1, "limit": 1}).json()
    ids = [page1["questions"][0]["question_id"], page2["questions"][0]["question_id"]]
    assert ids == sorted([first["question_id"], second["question_id"]])
    assert restarted_ledger.list_questions(offset=0, limit=2).next_offset is None
