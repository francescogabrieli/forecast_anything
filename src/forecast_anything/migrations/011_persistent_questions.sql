BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS questions (
    question_id TEXT PRIMARY KEY,
    create_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'paused', 'resolved')),
    current_revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS question_revisions (
    question_id TEXT NOT NULL REFERENCES questions(question_id),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (question_id, revision),
    UNIQUE (question_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS question_references (
    reference_id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(question_id),
    revision INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (question_id, revision, idempotency_key),
    FOREIGN KEY (question_id, revision)
        REFERENCES question_revisions(question_id, revision)
);
CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    create_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL,
    question_id TEXT,
    question_revision INTEGER,
    version INTEGER NOT NULL CHECK (version >= 1),
    phase TEXT NOT NULL CHECK (phase IN ('collecting', 'ready')),
    state TEXT NOT NULL CHECK (state IN ('open', 'reserved', 'submitted')),
    missing_data TEXT NOT NULL,
    request_content TEXT,
    request_digest TEXT,
    request_kind TEXT,
    source_ids TEXT NOT NULL,
    expected_job_id TEXT,
    candidate_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (question_id, question_revision)
        REFERENCES question_revisions(question_id, revision)
);
CREATE TABLE IF NOT EXISTS operation_mutations (
    operation_id TEXT NOT NULL REFERENCES operations(operation_id),
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (operation_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS question_revisions_page
    ON question_revisions(question_id, revision);
CREATE INDEX IF NOT EXISTS question_references_page
    ON question_references(question_id, revision, reference_id);
CREATE INDEX IF NOT EXISTS operations_page
    ON operations(question_id, operation_id);
PRAGMA user_version = 11;
COMMIT;
