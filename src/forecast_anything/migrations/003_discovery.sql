BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS discovery_epochs (
    epoch_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    budget TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_origins (
    origin_id TEXT NOT NULL,
    epoch_id TEXT NOT NULL REFERENCES discovery_epochs(epoch_id),
    role TEXT NOT NULL CHECK(role IN ('final', 'tuning')),
    PRIMARY KEY (origin_id, epoch_id)
);
CREATE TABLE IF NOT EXISTS discovery_candidates (
    candidate_id TEXT PRIMARY KEY,
    epoch_id TEXT NOT NULL REFERENCES discovery_epochs(epoch_id),
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_tool_calls (
    epoch_id TEXT NOT NULL REFERENCES discovery_epochs(epoch_id),
    call_id TEXT NOT NULL,
    PRIMARY KEY (epoch_id, call_id)
);
CREATE TABLE IF NOT EXISTS eligibility_decisions (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL REFERENCES discovery_candidates(candidate_id),
    content TEXT NOT NULL,
    UNIQUE(candidate_id, content)
);
CREATE TRIGGER IF NOT EXISTS discovery_epochs_no_update BEFORE UPDATE ON discovery_epochs
BEGIN SELECT RAISE(ABORT, 'discovery epochs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS discovery_epochs_no_delete BEFORE DELETE ON discovery_epochs
BEGIN SELECT RAISE(ABORT, 'discovery epochs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS discovery_candidates_no_update BEFORE UPDATE ON discovery_candidates
BEGIN SELECT RAISE(ABORT, 'discovery candidates are immutable'); END;
CREATE TRIGGER IF NOT EXISTS discovery_candidates_no_delete BEFORE DELETE ON discovery_candidates
BEGIN SELECT RAISE(ABORT, 'discovery candidates are immutable'); END;
CREATE TRIGGER IF NOT EXISTS discovery_origins_no_update BEFORE UPDATE ON discovery_origins
BEGIN SELECT RAISE(ABORT, 'discovery origin reservations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS discovery_origins_no_delete BEFORE DELETE ON discovery_origins
BEGIN SELECT RAISE(ABORT, 'discovery origin reservations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS discovery_calls_no_update BEFORE UPDATE ON discovery_tool_calls
BEGIN SELECT RAISE(ABORT, 'discovery tool calls are immutable'); END;
CREATE TRIGGER IF NOT EXISTS discovery_calls_no_delete BEFORE DELETE ON discovery_tool_calls
BEGIN SELECT RAISE(ABORT, 'discovery tool calls are immutable'); END;
CREATE TRIGGER IF NOT EXISTS eligibility_decisions_no_update BEFORE UPDATE ON eligibility_decisions
BEGIN SELECT RAISE(ABORT, 'eligibility decisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS eligibility_decisions_no_delete BEFORE DELETE ON eligibility_decisions
BEGIN SELECT RAISE(ABORT, 'eligibility decisions are immutable'); END;
PRAGMA user_version = 3;
COMMIT;
