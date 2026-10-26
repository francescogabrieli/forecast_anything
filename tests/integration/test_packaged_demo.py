"""The three offline examples exercise one unchanged, point-only core contract."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from forecast_anything.connectors.csv import load_csv
from forecast_anything.contracts import GraphSpec
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("domain", "expected", "unit", "timestamps"),
    [
        (
            "retail",
            ((12.0, 18.0, 15.0),),
            "items",
            (
                "2026-10-22T00:00:00+00:00",
                "2026-10-23T00:00:00+00:00",
                "2026-10-24T00:00:00+00:00",
            ),
        ),
        (
            "energy",
            ((0.8, 1.2, 1.6),),
            "kW",
            (
                "2026-10-21T07:00:00+00:00",
                "2026-10-21T08:00:00+00:00",
                "2026-10-21T09:00:00+00:00",
            ),
        ),
        (
            "activity",
            ((120.0, 180.0, 150.0),),
            "views",
            (
                "2026-10-22T00:00:00+00:00",
                "2026-10-23T00:00:00+00:00",
                "2026-10-24T00:00:00+00:00",
            ),
        ),
    ],
)
def test_three_examples_use_same_core(tmp_path, domain, expected, unit, timestamps):
    example = ROOT / "examples" / domain
    spec = GraphSpec.model_validate_json((example / "graph.json").read_text())
    metadata = json.loads((example / "assumptions.json").read_text())
    origin = datetime.fromisoformat(metadata["as_of"])
    snapshot = freeze(
        load_csv(example / "observations.csv"),
        origin,
        assumptions=tuple(metadata["assumptions"]),
    )
    source = next(node for node in spec.nodes if node.kind == "source")
    bindings = {source.config["source_id"]: snapshot}
    db = tmp_path / "demo.db"

    def runtime():
        return Runtime(
            Ledger(db), {"seasonal_naive": SeasonalNaiveProvider(1)}, {}, lambda: origin
        )

    emitted = runtime().run(spec, bindings, origin, key=domain)
    assert emitted.state == "completed"
    forecast = emitted.results["forecast"]
    assert forecast.point == expected
    assert tuple(time.isoformat() for time in forecast.timestamps) == timestamps
    assert forecast.units == (unit,)
    assert forecast.provider_id == "seasonal_naive"
    assert forecast.quantiles is None and forecast.paths is None
    assert forecast.sample_group_id is None
    assert all(
        assumption in forecast.assumptions for assumption in metadata["assumptions"]
    )
    assert any("synthetic" in assumption.lower() for assumption in forecast.assumptions)
    assert any("UTC" in assumption for assumption in forecast.assumptions)
    assert any("point" in assumption.lower() for assumption in forecast.assumptions)

    # A fresh runtime and ledger connection must return the original immutable run.
    assert runtime().run(spec, bindings, origin, key=domain) == emitted
    assert Ledger(db).get_run(emitted.run_id) == emitted
