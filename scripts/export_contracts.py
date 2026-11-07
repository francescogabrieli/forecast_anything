"""Deterministic schemas derived only from the live FastAPI/Pydantic contracts."""

import argparse
import inspect
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from forecast_anything import contracts
from forecast_anything.api.app import create_app
from forecast_anything.backtesting.contracts import (
    BacktestReport,
    OriginOutcome,
    OriginPage,
    PartitionScore,
)
from forecast_anything.operators import register_builtin_operators
from forecast_anything.presentations import (
    BacktestPresentation,
    BacktestSummary,
    FinalOriginPoint,
    ForecastPresentation,
    ForecastPresentationPoint,
    ForecastProviderUse,
    QuestionPresentation,
    QuestionPresentationReference,
    WatchBacktestSummary,
)
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger


def _normalize_openapi(openapi: dict) -> dict:
    for path in openapi.get("paths", {}).values():
        for operation in path.values():
            response = operation.get("responses", {}).get("422")
            if response is not None:
                response["description"] = "Unprocessable Content"
    return openapi


def export_contracts(output: Path) -> None:
    with TemporaryDirectory() as temporary:
        ledger = Ledger(Path(temporary) / "schema.db")
        runtime = Runtime(
            ledger,
            {"seasonal_naive": SeasonalNaiveProvider(1)},
            register_builtin_operators(),
            ledger.clock,
        )
        app = create_app(ledger, runtime, "schema-export-only")
        schemas = {
            name: model.model_json_schema(mode="serialization")
            for name, model in inspect.getmembers(contracts, inspect.isclass)
            if issubclass(model, contracts.Contract)
            and model.__module__ == contracts.__name__
        }
        schemas.update(
            (model.__name__, model.model_json_schema(mode="serialization"))
            for model in (
                BacktestReport,
                OriginOutcome,
                OriginPage,
                PartitionScore,
                BacktestPresentation,
                BacktestSummary,
                FinalOriginPoint,
                ForecastPresentation,
                ForecastPresentationPoint,
                ForecastProviderUse,
                QuestionPresentation,
                QuestionPresentationReference,
                WatchBacktestSummary,
            )
        )
        output.mkdir(parents=True, exist_ok=True)
        openapi = _normalize_openapi(app.openapi())
        for name, value in (("schemas.json", schemas), ("openapi.json", openapi)):
            (output / name).write_text(
                json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with TemporaryDirectory() as temporary:
            generated = Path(temporary)
            export_contracts(generated)
            if any(
                not (args.output / name).exists()
                or (generated / name).read_bytes() != (args.output / name).read_bytes()
                for name in ("schemas.json", "openapi.json")
            ):
                parser.exit(
                    1,
                    "Contract drift: regenerate schemas with scripts/export_contracts.py\n",
                )
    else:
        export_contracts(args.output)


if __name__ == "__main__":
    main()
