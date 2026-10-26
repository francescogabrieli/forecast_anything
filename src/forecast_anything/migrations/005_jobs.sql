BEGIN IMMEDIATE;
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    logical_key TEXT NOT NULL UNIQUE,
    original_payload TEXT NOT NULL,
    payload TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK(attempt > 0),
    state TEXT NOT NULL CHECK(state IN ('pending', 'running', 'completed', 'failed')),
    lease_token TEXT,
    lease_until REAL,
    owner TEXT,
    next_due_at REAL NOT NULL,
    result TEXT
);
CREATE INDEX jobs_due ON jobs(state, next_due_at, lease_until);
CREATE TABLE job_attempts (
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    attempt INTEGER NOT NULL,
    state TEXT NOT NULL,
    result TEXT,
    error TEXT,
    PRIMARY KEY(job_id, attempt)
);
CREATE TABLE source_polling (
    source_id TEXT PRIMARY KEY,
    revision TEXT NOT NULL,
    snapshot_id TEXT REFERENCES snapshots(snapshot_id),
    next_due_at REAL NOT NULL,
    available INTEGER NOT NULL
);
PRAGMA user_version = 5;
COMMIT;
