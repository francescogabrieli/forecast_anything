BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS backtest_plans (
    backtest_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL UNIQUE,
    archive_id TEXT NOT NULL,
    actuals_snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    content TEXT NOT NULL,
    UNIQUE(backtest_id, plan_id)
);
CREATE TABLE IF NOT EXISTS backtest_origins (
    backtest_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    plan_id TEXT NOT NULL,
    run_id TEXT REFERENCES runs(run_id),
    evaluation_id TEXT REFERENCES evaluations(evaluation_id),
    content TEXT NOT NULL,
    PRIMARY KEY(backtest_id, ordinal),
    FOREIGN KEY(backtest_id, plan_id) REFERENCES backtest_plans(backtest_id, plan_id)
);
CREATE TABLE IF NOT EXISTS backtest_reports (
    backtest_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL UNIQUE,
    plan_id TEXT NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY(backtest_id, plan_id) REFERENCES backtest_plans(backtest_id, plan_id)
);
CREATE TRIGGER IF NOT EXISTS backtest_plans_no_update BEFORE UPDATE ON backtest_plans
BEGIN SELECT RAISE(ABORT, 'backtest plans are immutable'); END;
CREATE TRIGGER IF NOT EXISTS backtest_plans_no_delete BEFORE DELETE ON backtest_plans
BEGIN SELECT RAISE(ABORT, 'backtest plans are immutable'); END;
CREATE TRIGGER IF NOT EXISTS backtest_origins_no_update BEFORE UPDATE ON backtest_origins
BEGIN SELECT RAISE(ABORT, 'backtest origins are immutable'); END;
CREATE TRIGGER IF NOT EXISTS backtest_origins_no_delete BEFORE DELETE ON backtest_origins
BEGIN SELECT RAISE(ABORT, 'backtest origins are immutable'); END;
CREATE TRIGGER IF NOT EXISTS backtest_reports_no_update BEFORE UPDATE ON backtest_reports
BEGIN SELECT RAISE(ABORT, 'backtest reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS backtest_reports_no_delete BEFORE DELETE ON backtest_reports
BEGIN SELECT RAISE(ABORT, 'backtest reports are immutable'); END;
PRAGMA user_version = 8;
COMMIT;
