BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS workspace_identity (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    workspace_id TEXT NOT NULL UNIQUE
);
INSERT OR IGNORE INTO workspace_identity VALUES (1, lower(hex(randomblob(16))));
PRAGMA user_version = 12;
COMMIT;
