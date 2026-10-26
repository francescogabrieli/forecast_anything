BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id TEXT PRIMARY KEY,
    content TEXT NOT NULL
);
PRAGMA user_version = 6;
COMMIT;
