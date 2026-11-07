BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS worker_liveness (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    worker_id TEXT NOT NULL,
    heartbeat_at REAL NOT NULL
);
PRAGMA user_version = 9;
COMMIT;
