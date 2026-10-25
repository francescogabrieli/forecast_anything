BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS watches (
    watch_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES discovery_candidates(candidate_id),
    supersedes_watch_id TEXT REFERENCES watches(watch_id),
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watch_history (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id TEXT NOT NULL REFERENCES watches(watch_id),
    event_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    event_content TEXT NOT NULL,
    content TEXT NOT NULL,
    UNIQUE(watch_id, event_id)
);
CREATE TRIGGER IF NOT EXISTS watches_no_delete BEFORE DELETE ON watches
BEGIN SELECT RAISE(ABORT, 'watch identities are retained'); END;
CREATE TRIGGER IF NOT EXISTS watch_identity_no_update BEFORE UPDATE OF watch_id, candidate_id, supersedes_watch_id ON watches
BEGIN SELECT RAISE(ABORT, 'watch lineage is immutable'); END;
CREATE TRIGGER IF NOT EXISTS watch_history_no_update BEFORE UPDATE ON watch_history
BEGIN SELECT RAISE(ABORT, 'watch history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS watch_history_no_delete BEFORE DELETE ON watch_history
BEGIN SELECT RAISE(ABORT, 'watch history is immutable'); END;
PRAGMA user_version = 4;
COMMIT;
