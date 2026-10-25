"""Whole-origin sampling, leakage guards, and honest research scoring."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from forecast_anything.contracts import DomainError, ForecastResult
from forecast_anything.operators import register_builtin_operators
from forecast_anything.uncertainty.residual_panels import (
    ResidualPanel,
    ResidualPanelSampler,
)

T = datetime(2026, 10, 24, tzinfo=timezone.utc)


def base(series=("a", "b"), horizon=2):
    return ForecastResult(
        provider_id="fixture",
        provider_revision="1",
        series_ids=series,
        timestamps=tuple(T + timedelta(days=i + 1) for i in range(horizon)),
        units=("count",) * len(series),
        point=((0,) * horizon,) * len(series),
        quantiles=None,
        paths=None,
        sample_group_id=None,
        assumptions=("source",),
    )


def panel(initial_errors, days=4, **changes):
    values = dict(
        origin=T - timedelta(days=days),
        horizon=2,
        series_ids=("a", "b"),
        errors=initial_errors,
        available_at=T - timedelta(days=days - 2),
    )
    return ResidualPanel(**(values | changes))


def sample(panels, **changes):
    options = dict(base=base(), panels=panels, as_of=T, draws=1000, seed=0)
    return ResidualPanelSampler().sample(**(options | changes))


def test_excludes_unmatured_panels():
    result = sample((panel([[1, 2], [3, 4]]), panel([[99, 99], [99, 99]], days=1)))
    assert set(result.paths) == {((1.0, 2.0), (3.0, 4.0))}
    with pytest.raises(DomainError) as error:
        sample((panel([[99, 99], [99, 99]], days=1),))
    assert error.value.code == "insufficient_joint_support"


def test_shared_origin_preserves_cross_series_dependence():
    result = sample((panel([[1, 2], [-1, -2]], days=5), panel([[-3, -4], [3, 4]])))
    assert set(result.paths) == {((1.0, 2.0), (-1.0, -2.0)), ((-3.0, -4.0), (3.0, 4.0))}
    assert all(path[0][0] == -path[1][0] for path in result.paths)


def test_seed_and_draw_identity():
    panels = (panel([[1, 2], [3, 4]], days=5), panel([[5, 6], [7, 8]]))
    first = sample(panels)
    assert sample(panels) == first
    assert sample(tuple(reversed(panels))) == first
    assert sample(panels, draws=30).paths == first.paths[:30]
    assert sample(panels, seed=1).paths != first.paths
    assert sample(panels, seed=1).sample_group_id != first.sample_group_id
    assert sample(panels, draws=30).sample_group_id != first.sample_group_id
    moved = base().model_copy(update={"point": ((10.0, 10.0), (10.0, 10.0))})
    assert sample(panels, base=moved).sample_group_id != first.sample_group_id
    assert first.provider_id == "residual_panel_sampler"
    assert "base_provider=fixture@1" in first.assumptions
    assert "status=experimental; evidence=provisional" in first.assumptions


@pytest.mark.parametrize(
    "changes",
    [
        {"horizon": 1},
        {"series_ids": ("b", "a")},
        {"errors": [[1, 2]]},
        {"errors": [[1], [2]]},
        {"errors": [[float("nan"), 0], [0, 0]]},
        {"available_at": T - timedelta(days=3)},
        {"origin": (T - timedelta(days=4)).replace(tzinfo=None)},
        {"provider_id": "other", "provider_revision": "1"},
        {"target_timestamps": (T - timedelta(days=2), T - timedelta(days=1))},
    ],
)
def test_missing_joint_support(changes):
    with pytest.raises(DomainError) as error:
        sample((panel([[1, 2], [3, 4]], **changes),))
    assert error.value.code == "invalid_residual_panel"


def test_duplicate_origins_rejected_instead_of_weighting_support_twice():
    value = panel([[1, 2], [3, 4]])
    with pytest.raises(DomainError) as error:
        sample((value, value))
    assert error.value.code == "invalid_residual_panel"


def test_no_panels_cannot_create_joint_information():
    with pytest.raises(DomainError) as error:
        sample((), base=base(("s",), 1))
    assert error.value.code == "insufficient_joint_support"


@pytest.mark.parametrize(
    "changes",
    [
        {"draws": 0},
        {"draws": True},
        {"seed": True},
        {"as_of": T.replace(tzinfo=None)},
        {"base": base().model_copy(update={"point": None})},
        {"base": base().model_copy(update={"timestamps": (T, T + timedelta(days=1))})},
    ],
)
def test_invalid_sampling_requests(changes):
    with pytest.raises(DomainError):
        sample((panel([[1, 2], [3, 4]]),), **changes)


def probability(value):
    event = register_builtin_operators()["any_exceed"].apply(
        {"value": value}, {"threshold": 0, "comparator": "gt"}
    )
    return event.point[0][0]


@pytest.mark.parametrize(
    "series,horizon,positive,negative",
    [
        (("a", "b"), 1, [[[1], [1]], [[-1], [-1]]], [[[1], [-1]], [[-1], [1]]]),
        (("a",), 2, [[[1, 1]], [[-1, -1]]], [[[1, -1]], [[-1, 1]]]),
    ],
)
def test_dependence_changes_window_event_ordering(series, horizon, positive, negative):
    def draw(errors):
        return sample(
            tuple(
                panel(e, days=5 + i, series_ids=series, horizon=horizon)
                for i, e in enumerate(errors)
            ),
            base=base(series, horizon),
        )

    assert 0.45 < probability(draw(positive)) < 0.55
    assert probability(draw(negative)) == 1.0
    support = tuple(
        panel(e, days=5 + i, series_ids=series, horizon=horizon)
        for i, e in enumerate(positive)
    )
    independent = independent_sample(base(series, horizon), support, T, 1000, 0)
    assert (
        probability(draw(positive))
        < probability(independent)
        < probability(draw(negative))
    )


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.joint_paths import (  # noqa: E402
    freeze_event,
    frozen_split,
    independent_sample,
    load_panels,
    run_experiment,
    score_probabilities,
)


def test_independent_control_breaks_dependence_but_preserves_marginals():
    panels = (panel([[1, 1], [1, 1]], days=5), panel([[-1, -1], [-1, -1]]))
    joint = sample(panels, draws=10000)
    independent = independent_sample(base(), panels, T, 10000, 0)
    assert 0.45 < probability(joint) < 0.55
    assert 0.92 < probability(independent) < 0.96  # 1 - (1/2)^4
    assert independent.provider_id == "independent_residual_control"
    assert independent_sample(base(), panels, T, 10, 0).paths == independent.paths[:10]


def test_scores_pair_origin_bootstrap_and_fail_closed_without_events():
    result = score_probabilities([0.0, 1.0] * 20, [0.0, 1.0] * 20, 0.5, seed=0)
    assert result["brier"] == 0.0
    assert result["brier_skill"] == 1.0
    assert result["brier_skill_ci95"] == [1.0, 1.0]
    assert result["status"] == "evaluated_support"
    assert result["calibration"][0]["observed_frequency"] == 0.0
    assert result["calibration"][-1]["observed_frequency"] == 1.0
    failed = score_probabilities([1.0] * 40, [1.0] * 40, 1.0, seed=0)
    assert failed["brier_skill"] is None
    assert failed["status"] == "provisional"
    assert "fewer_than_10_non_events" in failed["unmet_thresholds"]
    empty = score_probabilities([], [], 0.5, seed=0)
    assert empty["brier"] is None
    assert empty["status"] == "provisional"


def test_event_definition_uses_only_supplied_historical_windows():
    definition = freeze_event(
        [((1.0, 2.0),), ((3.0, 4.0),), ((5.0, 6.0),), ((7.0, 8.0),)]
    )
    assert definition["threshold"] == 6.5
    assert definition["operator"] == "any_exceed"
    assert definition["comparator"] == "gt"


def test_fixture_experiment_uses_frozen_final_origins_and_preserves_inputs(tmp_path):
    import hashlib
    import json

    from benchmarks.run import run_suite

    manifest = Path("tests/fixtures/benchmarks/manifest.yaml")
    source = tmp_path / "m4"
    run_suite(manifest, source, ("baseline",))
    fingerprints = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source.iterdir()
        if p.is_file()
    }
    output = run_experiment(source, tmp_path / "m5", seed=0, draws=100)
    report = json.loads(output.read_text())
    assert report["status"] == "experimental/provisional"
    for name, dataset in report["benchmark"].items():
        assert dataset["final_origin_count"] == 4
        assert dataset["event"]["defined_on"] == "exploration"
        assert dataset["panel_counts"]["final"] == 0
        assert dataset["methods"]["residual_panel_sampler@1"]["status"] == "provisional"
        frozen = json.loads((source / "frozen_calendar.json").read_text())[name]
        split, calendar = frozen_split(frozen)
        assert [p["origin"] for p in dataset["predictions"]] == [
            t.isoformat() for t in split.origins_for("final", calendar)
        ]
    assert fingerprints == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source.iterdir()
        if p.is_file()
    }


def test_final_panel_and_provider_contamination_rejected(tmp_path):
    import json

    from benchmarks.run import run_suite

    source = tmp_path / "m4"
    run_suite(Path("tests/fixtures/benchmarks/manifest.yaml"), source, ("baseline",))
    path = source / "residuals.baseline.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    frozen = json.loads((source / "frozen_calendar.json").read_text())["activity"]
    split, calendar = frozen_split(frozen)
    chosen = [r for r in rows if r["dataset"] == "activity"]
    for field, value in (
        ("split", "final"),
        ("provider_id", "timestral"),
        ("target_timestamps", ["2099-01-01T00:00:00+00:00"]),
        ("manifest_sha256", "changed"),
    ):
        altered = [dict(r) for r in chosen]
        altered[0][field] = value
        path.write_text("\n".join(json.dumps(r) for r in altered) + "\n")
        with pytest.raises(DomainError):
            load_panels(
                path,
                "activity",
                "seasonal_naive",
                "1",
                split,
                calendar,
                chosen[0]["manifest_sha256"],
            )


def test_empty_support_uses_required_domain_error_even_for_same_time_base():
    value = ForecastResult(
        provider_id="fixture",
        provider_revision="1",
        series_ids=("s",),
        timestamps=(T,),
        units=("count",),
        point=((1.0,),),
        quantiles=None,
        paths=None,
        sample_group_id=None,
        assumptions=(),
    )
    with pytest.raises(DomainError) as error:
        ResidualPanelSampler().sample(
            base=value, panels=(), as_of=T, draws=1000, seed=0
        )
    assert error.value.code == "insufficient_joint_support"


def test_final_actual_perturbation_cannot_change_event_or_sample_probabilities(
    tmp_path,
):
    import json
    import sqlite3

    from benchmarks.run import run_suite

    source = tmp_path / "m4"
    run_suite(Path("tests/fixtures/benchmarks/manifest.yaml"), source, ("baseline",))
    before = json.loads(run_experiment(source, tmp_path / "before", 0, 100).read_text())
    frozen = json.loads((source / "frozen_calendar.json").read_text())
    finals = {
        name: set(frozen_split(f)[0].origins_for("final", frozen_split(f)[1]))
        for name, f in frozen.items()
    }
    with sqlite3.connect(source / "ledger.sqlite") as connection:
        final_runs = {
            r["run_id"]
            for (content,) in connection.execute("SELECT content FROM runs")
            if (r := json.loads(content))["graph_id"].removeprefix("benchmark:")
            in finals
            and datetime.fromisoformat(r["as_of"])
            in finals[r["graph_id"].removeprefix("benchmark:")]
        }
        for (content,) in connection.execute(
            "SELECT content FROM evaluations"
        ).fetchall():
            evaluation = json.loads(content)
            if evaluation["run_id"] not in final_runs:
                continue
            identity = evaluation["actuals_snapshot_id"]
            snapshot = json.loads(
                connection.execute(
                    "SELECT content FROM snapshots WHERE snapshot_id = ?", (identity,)
                ).fetchone()[0]
            )
            for observation in snapshot["observations"]:
                observation["value"] = -1000000
            connection.execute(
                "UPDATE snapshots SET content = ? WHERE snapshot_id = ?",
                (json.dumps(snapshot), identity),
            )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    after = json.loads(run_experiment(source, tmp_path / "after", 0, 100).read_text())
    changed = False
    for name in before["benchmark"]:
        left, right = before["benchmark"][name], after["benchmark"][name]
        assert left["event"] == right["event"]
        for first, second in zip(
            left["predictions"], right["predictions"], strict=True
        ):
            assert first["probabilities"] == second["probabilities"]
            assert first["sample_group_ids"] == second["sample_group_ids"]
            changed |= first["outcome"] != second["outcome"]
    assert changed


def test_independent_control_reports_its_own_draw_count():
    value = independent_sample(base(), (panel([[1, 2], [3, 4]]),), T, 7, 0)
    assert any("seed=0; draws=7;" in a for a in value.assumptions)
    assert not any("seed=0; draws=1;" in a for a in value.assumptions)
    with pytest.raises(DomainError):
        independent_sample(base(), (panel([[1, 2], [3, 4]]),), T, 0, 0)


def test_shifted_historical_grid_is_not_aligned_support():
    shifted = panel(
        [[1, 2], [3, 4]],
        origin=T - timedelta(days=4) + timedelta(hours=1),
        available_at=T - timedelta(days=2) + timedelta(hours=1),
    )
    with pytest.raises(DomainError) as error:
        sample((shifted,))
    assert error.value.code == "invalid_residual_panel"
