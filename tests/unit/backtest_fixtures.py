"""Controlled numerical fixtures shared by focused backtest tests."""

from datetime import UTC, datetime, timedelta

from forecast_anything.contracts import (
    BacktestSettings,
    ForecastSelection,
    Observation,
    SourceSpec,
)
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.sources.catalog import SourceRevision
from forecast_anything.store import Ledger

START = datetime(2026, 1, 1, tzinfo=UTC)


def rows(count=16):
    return tuple(
        Observation(
            series_id="sales",
            event_time=START + timedelta(days=i),
            available_at=START + timedelta(days=i),
            revision="a",
            value=i + 1,
            unit="count",
        )
        for i in range(count)
    )


def revision(frequency="D", assumptions=()):
    return SourceRevision(
        revision="revision-1",
        assumptions=assumptions,
        spec=SourceSpec(
            source_id="sales",
            kind="csv",
            location="/not/read.csv",
            refresh_seconds=60,
            mapping={
                "frequency": {"constant": frequency},
                "timezone": {"constant": "UTC"},
                "calendar": {"constant": "gregorian"},
            },
        ),
    )


def prepare(
    observations=None,
    *,
    selection=None,
    settings=None,
    source=None,
    captured_at=None,
    contracts=None,
    origin_target_after=None,
):
    from forecast_anything.backtesting.planning import prepare_backtest

    return prepare_backtest(
        "backtest",
        source or revision(),
        rows() if observations is None else observations,
        selection
        or ForecastSelection(
            provider="seasonal_naive", horizon=2, options={"period": 2}
        ),
        settings or BacktestSettings(),
        captured_at or START + timedelta(days=15),
        provider_contracts=contracts
        or {"seasonal_naive": SeasonalNaiveProvider(9).capabilities()},
        origin_target_after=origin_target_after,
    )


def setup(tmp_path, plan=None, provider=None):
    from forecast_anything.backtesting.store import BacktestStore

    ledger = Ledger(tmp_path / "ledger.db")
    runtime = Runtime(
        ledger,
        {"seasonal_naive": provider or SeasonalNaiveProvider(99)},
        {},
        lambda: START + timedelta(days=20),
    )
    return runtime, BacktestStore(ledger), plan or prepare()


def execute(runtime, store, plan, **kwargs):
    from forecast_anything.backtesting.runner import execute_backtest

    return execute_backtest(runtime, store, plan, lease_guard=kwargs.get("lease_guard"))


def outcomes(store, plan):
    return store.list_origins(plan.backtest_id, limit=50).origins


class ControlledProvider:
    def __init__(
        self, *, fail_at=None, drift_at=None, wrong_result=False, before_call=None
    ):
        self.calls = 0
        self.revision = "1"
        self.fail_at, self.drift_at = fail_at, drift_at
        self.wrong_result, self.before_call = wrong_result, before_call

    def capabilities(self):
        return (
            SeasonalNaiveProvider(1)
            .capabilities()
            .model_copy(
                update={"provider_id": "controlled", "provider_revision": self.revision}
            )
        )

    def forecast(self, request):
        self.calls += 1
        if self.before_call:
            self.before_call(request)
        if self.calls == self.fail_at:
            raise RuntimeError("controlled failure")
        if self.calls == self.drift_at:
            self.revision = "2"
        return (
            SeasonalNaiveProvider(1)
            .forecast(request)
            .model_copy(
                update={
                    "provider_id": "controlled",
                    "provider_revision": "wrong"
                    if self.wrong_result
                    else self.revision,
                }
            )
        )


def controlled(tmp_path, provider, *, data=None):
    from forecast_anything.backtesting.store import BacktestStore

    plan = prepare(
        data,
        selection=ForecastSelection(provider="controlled", horizon=2),
        contracts={
            "controlled": provider.capabilities(),
            "seasonal_naive": SeasonalNaiveProvider(1).capabilities(),
        },
    )
    ledger = Ledger(tmp_path / "controlled.db")
    return (
        Runtime(
            ledger,
            {"controlled": provider, "seasonal_naive": SeasonalNaiveProvider(1)},
            {},
            lambda: START,
        ),
        BacktestStore(ledger),
        plan,
    )
