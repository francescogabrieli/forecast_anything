BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS worker_runtime (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    worker_id TEXT NOT NULL,
    model_status TEXT NOT NULL
);
PRAGMA user_version = 10;
COMMIT;
