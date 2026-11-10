BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS workspace_forecast_checkpoint (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    checkpoint TEXT NOT NULL
);
-- Existing forecasting state predates model selection and used 28M.
INSERT OR IGNORE INTO workspace_forecast_checkpoint
SELECT 1, 'mistralai/Timestral-28M'
WHERE EXISTS (SELECT 1 FROM runs)
   OR EXISTS (SELECT 1 FROM jobs)
   OR EXISTS (SELECT 1 FROM watches);
PRAGMA user_version = 14;
COMMIT;
