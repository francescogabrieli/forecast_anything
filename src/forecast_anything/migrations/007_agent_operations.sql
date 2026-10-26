BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS agent_tool_operations (
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    call_key TEXT NOT NULL,
    epoch_id TEXT NOT NULL REFERENCES discovery_epochs(epoch_id),
    session_id TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    tool TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    result TEXT,
    PRIMARY KEY (job_id, call_key)
);
CREATE TABLE IF NOT EXISTS discovery_explored_appends (
    epoch_id TEXT NOT NULL REFERENCES discovery_epochs(epoch_id),
    candidate_id TEXT NOT NULL REFERENCES discovery_candidates(candidate_id),
    PRIMARY KEY (epoch_id, candidate_id)
);
CREATE TRIGGER IF NOT EXISTS discovery_explored_appends_no_update BEFORE UPDATE ON discovery_explored_appends
BEGIN SELECT RAISE(ABORT, 'explored identities are append-only'); END;
CREATE TRIGGER IF NOT EXISTS discovery_explored_appends_no_delete BEFORE DELETE ON discovery_explored_appends
BEGIN SELECT RAISE(ABORT, 'explored identities are append-only'); END;
CREATE TRIGGER IF NOT EXISTS agent_operations_no_delete BEFORE DELETE ON agent_tool_operations
BEGIN SELECT RAISE(ABORT, 'agent operations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS agent_operations_immutable_binding BEFORE UPDATE ON agent_tool_operations
WHEN NEW.job_id != OLD.job_id OR NEW.call_key != OLD.call_key
    OR NEW.epoch_id != OLD.epoch_id OR NEW.session_id != OLD.session_id
    OR NEW.operation_id != OLD.operation_id OR NEW.tool != OLD.tool
    OR NEW.input_hash != OLD.input_hash OR OLD.result IS NOT NULL OR NEW.result IS NULL
BEGIN SELECT RAISE(ABORT, 'agent operation binding is immutable'); END;
PRAGMA user_version = 7;
COMMIT;
