"""Optional agent sessions in discovery and after database restart."""

from datetime import timedelta
from hashlib import sha256

from agent_gateway_fixtures import NOW, _setup

from forecast_anything.jobs import JobQueue
from forecast_anything.runtime import Runtime
from forecast_anything.sources.catalog import SourceCatalog
from forecast_anything.sources.profiling import ingest_source
from forecast_anything.watches import create_watch
from forecast_anything.worker import Worker


def test_template_discovery_schedules_optional_agent_session(tmp_path):
    _, ledger, existing, candidate, _ = _setup(tmp_path)
    queue = JobQueue(ledger)
    claimed = queue.claim("setup", NOW, 60)
    assert claimed.job_id == existing.job_id
    queue.complete(claimed, NOW, {})
    profile = candidate.source_profiles[0]
    registered = SourceCatalog(ledger.path).get("sales")
    template_job = queue.enqueue(
        "templates/new",
        {
            "kind": "discovery_templates",
            "source_id": "sales",
            "revision": registered.revision,
            "epoch_id": "new-epoch",
            "profile": profile.model_dump(mode="json"),
        },
    )
    runtime = Runtime(ledger, {}, {}, lambda: NOW)
    Worker(runtime, queue, discovery_gateway=object()).run_due(NOW, limit=1)
    assert queue.get(template_job.job_id).state == "completed", queue.history(
        template_job.job_id
    )
    agent_job = queue.claim("assert", NOW, 60)
    assert agent_job is not None
    assert agent_job.payload == {
        "kind": "discovery",
        "epoch_id": "new-epoch",
        "source_ids": ["sales"],
    }


def test_refreshed_epoch_schedules_optional_agent_session(tmp_path):
    _, ledger, _existing, candidate, _ = _setup(tmp_path)
    queue = JobQueue(ledger)
    queue.complete(queue.claim("setup", NOW, 60), NOW, {})
    watch = create_watch(
        candidate, watch_id="watch", next_due_at=NOW + timedelta(days=1)
    )
    ledger.put_watch(watch, now=NOW)
    spec = SourceCatalog(ledger.path).get("sales").spec
    snapshot = ingest_source(spec, NOW)
    ledger.put_snapshot(snapshot)
    refresh = queue.enqueue(
        "rediscover/test",
        {
            "kind": "discover_refresh",
            "watch_id": "watch",
            "snapshot_id": snapshot.snapshot_id,
            "profile": candidate.source_profiles[0].model_dump(mode="json"),
        },
    )
    Worker(
        Runtime(ledger, {}, {}, lambda: NOW), queue, discovery_gateway=object()
    ).run_due(NOW, limit=1)
    refreshed = queue.get(refresh.job_id)
    assert refreshed.state == "completed", queue.history(refresh.job_id)
    epoch_id = queue.history(refresh.job_id)[0]["result"]["epoch_id"]
    agent_job_id = sha256(f"discovery/agent/{epoch_id}".encode()).hexdigest()
    agent_job = queue.get(agent_job_id)
    assert agent_job.payload == {
        "kind": "discovery",
        "epoch_id": epoch_id,
        "source_ids": ["sales"],
    }
