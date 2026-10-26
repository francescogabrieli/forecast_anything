BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    actuals_snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS evaluations_run_id ON evaluations(run_id);
PRAGMA user_version = 2;
COMMIT;
