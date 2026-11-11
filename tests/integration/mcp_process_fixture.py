"""Run the production HTTP API or worker in an isolated test process."""

import os
import sys
import time
from datetime import datetime
from pathlib import Path


def fixture_main():
    import uvicorn

    from forecast_anything.api.app import create_app
    from forecast_anything.jobs import JobQueue
    from forecast_anything.operators import register_builtin_operators
    from forecast_anything.providers.baseline import SeasonalNaiveProvider
    from forecast_anything.runtime import Runtime
    from forecast_anything.store import Ledger
    from forecast_anything.worker import Worker

    mode, directory, port = sys.argv[1:]
    root = Path(directory)
    source_root = os.environ.get("FORECAST_ANYTHING_TEST_SOURCE_ROOT")
    if source_root is not None:
        sys.path.insert(0, str(Path(source_root) / "src"))

    def clock():
        return datetime.fromisoformat((root / "clock.txt").read_text())

    ledger = Ledger(root / "state.db", clock=clock)
    runtime = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        register_builtin_operators(),
        clock,
    )
    if mode == "api":
        uvicorn.run(
            create_app(ledger, runtime, "private-synthetic-workspace-token"),
            host="127.0.0.1",
            port=int(port),
            log_level="error",
            access_log=False,
        )
    else:
        # Deterministic crash boundary only: all production writes/inference run.
        # The parent kills this OS process after observing persisted origin 1.
        from forecast_anything.backtesting.store import BacktestStore

        original_put = BacktestStore.put_origin

        def put_and_pause(self, outcome, **kwargs):
            result = original_put(self, outcome, **kwargs)
            if outcome.ordinal == 1 and (root / "pause-after-origin").exists():
                (root / "origin-persisted").touch()
                while (root / "pause-after-origin").exists():
                    time.sleep(0.02)
            return result

        BacktestStore.put_origin = put_and_pause
        worker = Worker(runtime, JobQueue(ledger))
        with worker.liveness():
            while True:
                worker.run_due(clock())
                time.sleep(0.02)


if __name__ == "__main__":
    fixture_main()
