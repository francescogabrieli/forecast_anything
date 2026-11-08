BEGIN IMMEDIATE;

-- Durable inbox events linked to questions and runs
CREATE TABLE IF NOT EXISTS inbox_events (
    event_id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(question_id),
    revision INTEGER NOT NULL,
    event_kind TEXT NOT NULL,
    transition_id TEXT NOT NULL,
    run_id TEXT REFERENCES runs(run_id),
    decision_id TEXT,
    watch_id TEXT REFERENCES watches(watch_id),
    occurred_at TEXT NOT NULL,
    muted INTEGER NOT NULL CHECK (muted IN (0, 1)),
    summary TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (question_id, revision)
        REFERENCES question_revisions(question_id, revision)
);

CREATE INDEX IF NOT EXISTS inbox_events_question_page
    ON inbox_events(question_id, occurred_at DESC, event_id);

-- Opt-in webhook subscriptions
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    subscription_id TEXT PRIMARY KEY,
    target_url TEXT NOT NULL,
    secret TEXT,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL
);

-- Durable outbox queue for webhook deliveries
CREATE TABLE IF NOT EXISTS webhook_outbox (
    delivery_id TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL REFERENCES webhook_subscriptions(subscription_id),
    event_id TEXT NOT NULL REFERENCES inbox_events(event_id),
    state TEXT NOT NULL CHECK (state IN ('pending', 'delivering', 'delivered', 'delivery_failed', 'delivery_suppressed_muted')),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_attempt_at TEXT NOT NULL,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS webhook_outbox_queue
    ON webhook_outbox(state, next_attempt_at);

-- Background source polling subscriptions
CREATE TABLE IF NOT EXISTS source_subscriptions (
    source_id TEXT PRIMARY KEY,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Automatic requalification is budgeted per question over a rolling 24 hours.
CREATE TABLE IF NOT EXISTS requalification_budgets (
    question_id TEXT NOT NULL REFERENCES questions(question_id),
    watch_id TEXT NOT NULL REFERENCES watches(watch_id),
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    scheduled_at REAL NOT NULL,
    PRIMARY KEY (question_id, job_id)
);

CREATE INDEX IF NOT EXISTS requalification_budgets_window
    ON requalification_budgets(question_id, scheduled_at);

-- Extend questions with muted and priority controls
ALTER TABLE questions ADD COLUMN muted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE questions ADD COLUMN priority INTEGER NOT NULL DEFAULT 3;

-- Extend jobs with priority ordering
ALTER TABLE jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 3;

PRAGMA user_version = 13;
COMMIT;
