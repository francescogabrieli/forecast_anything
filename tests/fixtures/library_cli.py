"""Test-only CLI harness for generic ledger/queue behavior, without model weights.

Production entrypoints always enforce Timestral. This explicit library fixture
uses the injectable Runtime policy to test process recovery and failed emissions;
it is not product forecasting or model acceptance.
"""

from forecast_anything import cli
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime


def library_runtime(*args, **kwargs):
    kwargs.pop("required_provider", None)
    return Runtime(*args, **kwargs)


cli.Runtime = library_runtime
cli.configured_providers = lambda: {"seasonal_naive": SeasonalNaiveProvider(1)}
raise SystemExit(cli.main())
