"""Research-only joint residual paths versus an independent-cell control.

Run: uv run python experiments/joint_paths.py --seed 0 --draws 1000
Inputs are existing M4 artifacts, opened read-only. No data preparation, model
weight loading, calendar rebuilding, or holdout-based method selection occurs.
"""

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from random import Random
from time import perf_counter

import numpy as np

# Support both the documented script command and ordinary module imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forecast_anything.contracts import DomainError, ForecastResult, RunRecord, Snapshot  # noqa: E402
from forecast_anything.evaluation.metrics import event_metrics  # noqa: E402
from forecast_anything.evaluation.splits import TemporalSplit  # noqa: E402
from forecast_anything.operators import register_builtin_operators  # noqa: E402
from forecast_anything.uncertainty.residual_panels import (  # noqa: E402
    ResidualPanel,
    ResidualPanelSampler,
)

METHOD = "residual_panel_sampler@1"
CONTROL = "independent_residual_control@1"
OPERATORS = register_builtin_operators()
BOOTSTRAPS = 2000


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def independent_sample(base, panels, as_of, draws, seed):
    """Deliberately destroy dependence, keeping each empirical cell marginal."""
    if type(draws) is not int or draws <= 0:
        raise DomainError(
            "invalid_sampling_request", {"reason": "positive integer draws required"}
        )
    checked = ResidualPanelSampler().sample(base, panels, as_of, 1, seed)
    eligible = sorted(
        (p for p in panels if p.available_at <= as_of), key=lambda p: p.origin
    )
    rng = Random(seed)
    paths = tuple(
        tuple(
            tuple(
                value + eligible[rng.randrange(len(eligible))].errors[s][h]
                for h, value in enumerate(row)
            )
            for s, row in enumerate(base.point)
        )
        for _ in range(draws)
    )
    identity = sha256(
        json.dumps(
            {
                "method": CONTROL,
                "validated_support": checked.sample_group_id,
                "seed": seed,
                "draws": draws,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return ForecastResult(
        provider_id="independent_residual_control",
        provider_revision="1",
        series_ids=base.series_ids,
        timestamps=base.timestamps,
        units=base.units,
        point=base.point,
        quantiles=None,
        paths=paths,
        sample_group_id=identity,
        assumptions=tuple(
            a
            for a in checked.assumptions
            if not a.startswith(("assumption=residual transferability", "seed="))
        )
        + (
            "research control; cells independently resampled; joint dependence deliberately destroyed",
            f"seed={seed}; draws={draws}; order=draw/series/horizon; independent cell origins",
        ),
    )


def event_probability(forecast, definition):
    return (
        OPERATORS[definition["operator"]]
        .apply(
            {"value": forecast},
            {key: definition[key] for key in ("threshold", "comparator")},
        )
        .point[0][0]
    )


def realized_event(base, actual, definition):
    # Registered event implementation scores the single realized world too.
    return event_probability(
        base.model_copy(
            update={
                "point": actual,
                "paths": (actual,),
                "sample_group_id": "realized-world",
            }
        ),
        definition,
    )


def freeze_event(exploration_windows):
    if not exploration_windows:
        raise DomainError("insufficient_historical_events", {})
    return {
        "operator": "any_exceed",
        "comparator": "gt",
        "threshold": float(
            np.quantile(
                [max(x for row in w for x in row) for w in exploration_windows], 0.75
            )
        ),
        "defined_on": "exploration",
        "rule": "75th percentile of complete exploration window maxima; linear quantile",
        "scope": "any selected series at any forecast timestamp",
        "quantile": 0.75,
        "exploration_window_count": len(exploration_windows),
    }


def score_probabilities(probabilities, outcomes, historical_frequency, seed):
    """Paired non-overlapping-origin percentile bootstrap, no holdout refit."""
    if len(probabilities) != len(outcomes) or not 0 <= historical_frequency <= 1:
        raise DomainError("invalid_event_outcome", {})
    errors = np.array(
        [
            event_metrics(p, y)["brier"]
            for p, y in zip(probabilities, outcomes, strict=True)
        ]
    )
    reference = np.array(
        [event_metrics(historical_frequency, y)["brier"] for y in outcomes]
    )
    n, events = len(outcomes), int(sum(outcomes))
    brier = float(errors.mean()) if n else None
    baseline = float(reference.mean()) if n else None
    skill = 1 - brier / baseline if baseline else None
    interval = None
    undefined = 0
    if n and baseline:
        indices = np.random.default_rng(seed).integers(0, n, size=(BOOTSTRAPS, n))
        denominator = reference[indices].mean(axis=1)
        valid = denominator > 0
        undefined = int((~valid).sum())
        # A partially undefined bootstrap does not establish the lower bound.
        if valid.all():
            skills = 1 - errors[indices].mean(axis=1) / denominator
            interval = [float(x) for x in np.quantile(skills, [0.025, 0.975])]
    unmet = []
    if n < 30:
        unmet.append("fewer_than_30_nonoverlapping_final_origins")
    if events < 10:
        unmet.append("fewer_than_10_events")
    if n - events < 10:
        unmet.append("fewer_than_10_non_events")
    if interval is None or interval[0] <= 0:
        unmet.append("brier_skill_bootstrap_lower_bound_not_positive")
    calibration = []
    for i in range(5):
        members = [
            (p, y)
            for p, y in zip(probabilities, outcomes, strict=True)
            if i / 5 <= p and (p < (i + 1) / 5 or i == 4)
        ]
        calibration.append(
            {
                "lower": i / 5,
                "upper": (i + 1) / 5,
                "count": len(members),
                "mean_probability": sum(p for p, _ in members) / len(members)
                if members
                else None,
                "observed_frequency": sum(y for _, y in members) / len(members)
                if members
                else None,
            }
        )
    ece = (
        sum(
            b["count"] * abs(b["mean_probability"] - b["observed_frequency"])
            for b in calibration
            if b["count"]
        )
        / n
        if n
        else None
    )
    return {
        "status": "provisional" if unmet else "evaluated_support",
        "unmet_thresholds": unmet,
        "origin_count": n,
        "events": events,
        "non_events": n - events,
        "brier": brier,
        "historical_frequency": historical_frequency,
        "historical_frequency_brier": baseline,
        "brier_skill": skill,
        "brier_skill_ci95": interval,
        "bootstrap_replicates": BOOTSTRAPS,
        "bootstrap_unit": "paired non-overlapping origin; fixed historical-frequency forecast",
        "bootstrap_undefined_replicates": undefined,
        "brier_skill_undefined_reason": "zero_reference_brier"
        if baseline == 0
        else "no_origins"
        if not n
        else None,
        "calibration": calibration,
        "expected_calibration_error": ece,
    }


def frozen_split(frozen):
    calendar = tuple(datetime.fromisoformat(t) for t in frozen["timestamps"])
    split = TemporalSplit(
        *(
            datetime.fromisoformat(frozen[key])
            for key in ("exploration_end", "selection_end", "final_start")
        ),
        frozen["horizon"],
        frozen["stride"],
        calendar,
    )
    if split.stride < split.horizon:
        raise DomainError("overlapping_final_origins", {})
    for part in ("exploration", "selection", "final"):
        if tuple(
            datetime.fromisoformat(t) for t in frozen["origins"][part]
        ) != split.origins_for(part, calendar):
            raise DomainError("changed_split_calendar", {"partition": part})
    return split, calendar


def load_panels(
    path, dataset, provider_id, provider_revision, split, calendar, manifest_sha256
):
    rows = [
        json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()
    ]
    rows = [row for row in rows if row["dataset"] == dataset]
    origins = {
        part: set(split.origins_for(part, calendar))
        for part in ("exploration", "selection")
    }
    positions = {t: i for i, t in enumerate(calendar)}
    panels, seen = [], set()
    for row in rows:
        origin = datetime.fromisoformat(row["origin"])
        part = row["split"]
        if (
            part not in origins
            or origin not in origins[part]
            or (row["provider_id"], row["provider_revision"])
            != (provider_id, provider_revision)
            or row["manifest_sha256"] != manifest_sha256
            or origin in seen
            or row["horizon"] != split.horizon
        ):
            raise DomainError(
                "invalid_residual_artifact",
                {"dataset": dataset, "origin": row["origin"]},
            )
        targets = tuple(datetime.fromisoformat(t) for t in row["target_timestamps"])
        expected = calendar[
            positions[origin] + 1 : positions[origin] + 1 + split.horizon
        ]
        if (
            targets != expected
            or datetime.fromisoformat(row["available_at"]) < targets[-1]
        ):
            raise DomainError(
                "invalid_residual_artifact",
                {"reason": "unaligned or unmatured panel", "dataset": dataset},
            )
        seen.add(origin)
        panels.append(
            ResidualPanel(
                origin,
                row["horizon"],
                tuple(row["series_ids"]),
                row["errors"],
                datetime.fromisoformat(row["available_at"]),
                provider_id,
                provider_revision,
                targets,
            )
        )
    return tuple(panels), rows


def _actuals(connection, evaluation, base):
    content = connection.execute(
        "SELECT content FROM snapshots WHERE snapshot_id = ?",
        (evaluation["actuals_snapshot_id"],),
    ).fetchone()
    snapshot = Snapshot.model_validate_json(content[0])
    lookup = {(o.series_id, o.event_time): o for o in snapshot.observations}
    actual = tuple(
        tuple(lookup[s, t].value for t in base.timestamps) for s in base.series_ids
    )
    if any(x is None for row in actual for x in row):
        raise DomainError("incomplete_actuals", {})
    return actual, max(
        lookup[s, t].available_at for s in base.series_ids for t in base.timestamps
    )


def synthetic_experiment(seed, draws):
    t = datetime(2026, 10, 24, tzinfo=timezone.utc)
    report = {}
    for label, series, horizon, worlds, truth in (
        (
            "positive_cross_series",
            ("a", "b"),
            1,
            (((1.0,), (1.0,)), ((-1.0,), (-1.0,))),
            0.5,
        ),
        (
            "negative_cross_series",
            ("a", "b"),
            1,
            (((1.0,), (-1.0,)), ((-1.0,), (1.0,))),
            1.0,
        ),
        ("positive_cross_horizon", ("a",), 2, (((1.0, 1.0),), ((-1.0, -1.0),)), 0.5),
        ("negative_cross_horizon", ("a",), 2, (((1.0, -1.0),), ((-1.0, 1.0),)), 1.0),
    ):
        base = ForecastResult(
            provider_id="synthetic_zero",
            provider_revision="1",
            series_ids=series,
            timestamps=tuple(t + timedelta(days=i + 1) for i in range(horizon)),
            units=("count",) * len(series),
            point=((0.0,) * horizon,) * len(series),
            quantiles=None,
            paths=None,
            sample_group_id=None,
            assumptions=("known synthetic process",),
        )
        panels = tuple(
            ResidualPanel(
                t - timedelta(days=i + horizon + 1),
                horizon,
                series,
                [list(row) for row in world],
                t - timedelta(days=i + 1),
            )
            for i, world in enumerate(worlds)
        )
        event = {"operator": "any_exceed", "threshold": 0.0, "comparator": "gt"}
        outcomes = [realized_event(base, worlds[i % 2], event) for i in range(200)]
        methods = {}
        for method, sampler in (
            (METHOD, ResidualPanelSampler().sample),
            (CONTROL, independent_sample),
        ):
            started = perf_counter()
            forecast = sampler(base, panels, t, draws, seed)
            p = event_probability(forecast, event)
            seconds = perf_counter() - started
            methods[method] = {
                **score_probabilities([p] * len(outcomes), outcomes, truth, seed),
                "probability": p,
                "seconds": seconds,
                "draws_per_origin": draws,
                "support_panels": len(panels),
                "forecast_calls": 1,
                "outcome_windows": "200 balanced enumerations of process outcomes; descriptive only",
                "promotion_eligible": False,
            }
        report[label] = {
            "event": event,
            "known_event_probability": truth,
            "known_independent_event_probability": 0.75,
            "source": "synthetic; equal-mass two-world law; no real data",
            "methods": methods,
        }
    return report


def _benchmark_dataset(
    connection,
    name,
    frozen,
    m4,
    panels_path,
    origin_rows,
    runs,
    evaluations,
    seed,
    draws,
):
    split, calendar = frozen_split(frozen)
    positions = {t: i for i, t in enumerate(calendar)}
    manifest_hash = m4["manifest_sha256"]
    panels, panel_rows = load_panels(
        panels_path, name, "seasonal_naive", "1", split, calendar, manifest_hash
    )
    eligible = {
        datetime.fromisoformat(r["origin"]): r
        for r in origin_rows
        if r["dataset"] == name
        and r["provider"] == "baseline"
        and r["status"] == "evaluated"
    }
    final_origins = split.origins_for("final", calendar)
    development = []
    for part in ("exploration", "selection"):
        for origin in split.origins_for(part, calendar):
            if origin not in eligible:
                continue
            run = runs[name, origin]
            base = run.results["baseline"]
            actual, available = _actuals(connection, evaluations[run.run_id], base)
            if final_origins and available <= final_origins[0]:
                development.append((part, base, actual, available))
    # This definition and reference probability are frozen before fetching any final actuals.
    event = freeze_event(
        [actual for part, _, actual, _ in development if part == "exploration"]
    )
    historical = [
        realized_event(base, actual, event) for _, base, actual, _ in development
    ]
    frequency = sum(historical) / len(historical)
    event["historical_frequency"] = frequency
    event["historical_window_count"] = len(historical)
    event["historical_frequency_splits"] = ["exploration", "selection"]
    predictions, excluded = [], []
    cost = {METHOD: 0.0, CONTROL: 0.0}
    for origin in final_origins:
        if origin not in eligible:
            excluded.append(
                {
                    "origin": origin.isoformat(),
                    "reason": "M4 incomplete target/history or insufficient history",
                }
            )
            continue
        run = runs[name, origin]
        base = run.results["baseline"]
        expected = calendar[
            positions[origin] + 1 : positions[origin] + 1 + split.horizon
        ]
        if (base.provider_id, base.provider_revision) != (
            "seasonal_naive",
            "1",
        ) or base.timestamps != expected:
            raise DomainError(
                "invalid_base_forecast", {"dataset": name, "origin": origin.isoformat()}
            )
        row = {
            "origin": origin.isoformat(),
            "run_id": run.run_id,
            "snapshot_ids": run.snapshot_ids,
            "target_start": expected[0].isoformat(),
            "target_end": expected[-1].isoformat(),
            "probabilities": {},
            "sample_group_ids": {},
            "available_panels": sum(p.available_at <= origin for p in panels),
        }
        for method, sampler in (
            (METHOD, ResidualPanelSampler().sample),
            (CONTROL, independent_sample),
        ):
            started = perf_counter()
            forecast = sampler(base, panels, origin, draws, seed)
            row["probabilities"][method] = event_probability(forecast, event)
            row["sample_group_ids"][method] = forecast.sample_group_id
            cost[method] += perf_counter() - started
        actual, _ = _actuals(connection, evaluations[run.run_id], base)
        row["outcome"] = realized_event(base, actual, event)
        row["actuals_snapshot_id"] = evaluations[run.run_id]["actuals_snapshot_id"]
        predictions.append(row)
    methods = {
        method: {
            **score_probabilities(
                [r["probabilities"][method] for r in predictions],
                [r["outcome"] for r in predictions],
                frequency,
                seed,
            ),
            "sampling_and_event_seconds": cost[method],
            "forecast_calls": len(predictions),
            "draws_per_origin": draws,
            "path_cells_per_origin": draws * split.horizon * len(panels[0].series_ids),
            "base_provider": "seasonal_naive@1",
        }
        for method in (METHOD, CONTROL)
    }
    return {
        "status": "experimental/"
        + (
            "evaluated_support"
            if methods[METHOD]["status"] == "evaluated_support"
            else "provisional"
        ),
        "event": event,
        "final_origin_count": len(predictions),
        "frozen_final_candidate_count": len(final_origins),
        "excluded_final_origins": excluded,
        "panel_count": len(panels),
        "panel_counts": dict(Counter(r["split"] for r in panel_rows)) | {"final": 0},
        "panel_provider": "seasonal_naive@1",
        "panel_manifest_sha256": manifest_hash,
        "panel_source_download_sha256": sorted(
            {r["download_sha256"] for r in panel_rows}
        ),
        "availability_basis": sorted({r["availability_basis"] for r in panel_rows}),
        "source": m4["datasets"][name]["source"],
        "nonoverlapping_stride": split.stride,
        "horizon": split.horizon,
        "methods": methods,
        "predictions": predictions,
    }


def run_experiment(source, output, seed=0, draws=1000):
    import csv

    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents:
        raise DomainError("output_overlaps_m4_inputs", {})
    started = perf_counter()
    inputs = {
        name: digest(source / name)
        for name in (
            "frozen_calendar.json",
            "origins.csv",
            "residuals.baseline.jsonl",
            "ledger.sqlite",
            "report.json",
        )
    }
    frozen = json.loads((source / "frozen_calendar.json").read_text())
    m4 = json.loads((source / "report.json").read_text())
    with (source / "origins.csv").open() as stream:
        origin_rows = list(csv.DictReader(stream))
    # Immutable read-only mode also prevents SQLite creating WAL/SHM sidecars.
    # M4 must have finished/checkpointed; ignoring a live WAL would be unsafe.
    wal = source / "ledger.sqlite-wal"
    if wal.exists() and wal.stat().st_size:
        raise DomainError(
            "live_m4_ledger", {"reason": "checkpoint M4 before this experiment"}
        )
    with sqlite3.connect(
        (source / "ledger.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True
    ) as connection:
        runs = {}
        for (content,) in connection.execute("SELECT content FROM runs"):
            run = RunRecord.model_validate_json(content)
            name = run.graph_id.removeprefix("benchmark:")
            if name in frozen:
                key = (name, run.as_of)
                if key in runs:
                    raise DomainError("ambiguous_benchmark_run", {"dataset": name})
                runs[key] = run
        evaluations = {}
        for (content,) in connection.execute("SELECT content FROM evaluations"):
            evaluation = json.loads(content)
            evaluations[evaluation["run_id"]] = evaluation
        # Synthetic evidence cannot promote the empirical method.
        synthetic = synthetic_experiment(seed, draws)
        benchmark = {
            name: _benchmark_dataset(
                connection,
                name,
                f,
                m4,
                source / "residuals.baseline.jsonl",
                origin_rows,
                runs,
                evaluations,
                seed,
                draws,
            )
            for name, f in frozen.items()
        }
    if inputs != {name: digest(source / name) for name in inputs}:
        raise DomainError("changed_m4_inputs", {})
    promoted = all(
        d["methods"][METHOD]["status"] == "evaluated_support"
        for d in benchmark.values()
    )
    report = {
        "schema_version": 1,
        "method": METHOD,
        "base_provider": "seasonal_naive@1",
        "control": CONTROL,
        "status": "experimental/"
        + ("evaluated_support" if promoted else "provisional"),
        "seed": seed,
        "draws": draws,
        "bootstrap_replicates": BOOTSTRAPS,
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "implementation_sha256": {
                "experiment": digest(Path(__file__)),
                "sampler": digest(
                    Path(__file__).resolve().parents[1]
                    / "src/forecast_anything/uncertainty/residual_panels.py"
                ),
            },
        },
        "predeclared_thresholds": {
            "nonoverlapping_final_origins": 30,
            "events": 10,
            "non_events": 10,
            "brier_skill_bootstrap_ci95_lower_strictly_greater_than": 0,
        },
        "inputs": {
            "directory": str(source),
            "sha256": inputs,
            "manifest_sha256": m4["manifest_sha256"],
        },
        "assumptions": [
            "Residual transferability across origins is unverified; complete shared-origin panels only",
            "Uniform empirical panel sampling with replacement; no clipping or gap imputation",
            "One fixed event per dataset; threshold from exploration only; no final-based tuning",
            "Historical frequency from completed exploration/selection windows, fixed before final scoring",
            "Period-end availability assumed, not certified observed historical vintages",
            "Paired-origin IID bootstrap is operational evidence; serial dependence across origins can remain",
            "Single-series benchmark measures temporal dependence; multiseries evidence is synthetic only",
            "Any method change after this test requires a new holdout",
        ],
        "timestral": "separate_m4_evidence; this experiment uses baseline panels only; no Timestral weights loaded",
        "synthetic": synthetic,
        "benchmark": benchmark,
        "total_seconds": perf_counter() - started,
    }
    output.mkdir(parents=True, exist_ok=True)
    path = output / "report.json"
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(".local/benchmark"))
    parser.add_argument("--output", type=Path, default=Path(".local/joint_paths"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--draws", type=int, default=1000)
    args = parser.parse_args()
    try:
        print(run_experiment(args.source, args.output, args.seed, args.draws))
    except DomainError as error:
        print(error.model_dump_json(), file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
