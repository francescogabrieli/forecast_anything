"""Freeze calendars, compare approved providers, and export scored evidence.

Timestral inference is opt-in and requires explicit local weights approval.
Preparation and baseline inference never load or download model weights.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from forecast_anything.connectors.csv import load_csv
from forecast_anything.contracts import DomainError, GraphSpec, Node
from forecast_anything.evaluation.metrics import relative_mae
from forecast_anything.evaluation.records import evaluate_run
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.providers.classical import (
    AutoARIMAProvider,
    ETSProvider,
    ThetaProvider,
)
from forecast_anything.providers.timestral import TimestralProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze

from .frozen_splits import (
    PARTITIONS,
    dataset_origins,
    dataset_split,
    freeze_calendar,
    validate_frozen_calendar,
)
from .prepare import digest, load_manifest, prepare_suite, write_json
from .scoring import bootstrap_skill_interval, diebold_mariano, score_origin

SCORABLE_PARTITIONS = ("exploration", "selection")
TIMESTRAL_APPROVAL_ENV = "FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED"
TIMESTRAL_123M_APPROVAL_ENV = "FORECAST_ANYTHING_TIMESTRAL_123M_WEIGHTS_APPROVED"
TIMESTRAL_PROVIDERS = ("timestral", "timestral_123m")
HOLDOUT_REASON = "holdout_reserved_for_final_evaluation"


def _graph(name, config, provider="baseline"):
    return GraphSpec(
        graph_id=(
            f"benchmark:{name}"
            if provider == "baseline"
            else f"benchmark:{name}:{provider}"
        ),
        version=1,
        nodes=(
            Node(
                node_id="history",
                kind="source",
                inputs=(),
                config={
                    "source_id": "history",
                    "series_ids": [config["series_id"]],
                    "units": [config["unit"]],
                    "frequency": config["frequency"],
                },
            ),
            Node(
                node_id="baseline",
                kind="forecast",
                inputs=("history",),
                config={
                    "provider": "seasonal_naive"
                    if provider == "baseline"
                    else provider,
                    "history": "history",
                    "horizon": config["horizon"],
                    "frequency": config["frequency"],
                    "options": {"period": config["period"]}
                    if provider == "baseline"
                    else {},
                    "relation_type": {"history": "statistical"},
                },
            ),
        ),
    )


def _environment(timestral_statuses=None, requested_providers=()):
    timestral_statuses = timestral_statuses or {}
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": revision,
        "harness_sha256": {
            name: digest(Path(__file__).with_name(name))
            for name in (
                "prepare.py",
                "run.py",
                "frozen_splits.py",
                "scoring.py",
            )
        },
        "classical_provider_sha256": digest(
            Path(__file__).resolve().parents[1]
            / "src/forecast_anything/providers/classical.py"
        ),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("forecast-anything", "numpy", "pydantic")
        },
        "providers": {
            "baseline": "seasonal_naive@1",
            "timestral": timestral_statuses.get("timestral", "not_requested"),
            "timestral_123m": timestral_statuses.get("timestral_123m", "not_requested"),
            "ets": "ets-a-n-n-ses-grid-v1"
            if "ets" in requested_providers
            else "not_requested",
            "theta": "theta-nonseasonal-ses-drift-v1"
            if "theta" in requested_providers
            else "not_requested",
            "autoarima": "autoarima-css-aic-p0-3-d0-1-q0-v1"
            if "autoarima" in requested_providers
            else "not_requested",
        },
    }


def _prepared(manifest, output, specification):
    directory = output / "data"
    if not (directory / "preparation.json").exists():
        candidate = Path(specification.get("prepared_directory", ".local/data"))
        if (candidate / "preparation.json").exists() and json.loads(
            (candidate / "preparation.json").read_text()
        )["manifest_sha256"] == digest(manifest):
            directory = candidate
        else:
            prepare_suite(manifest, directory)
    metadata = json.loads((directory / "preparation.json").read_text())
    if metadata["manifest_sha256"] != digest(manifest):
        raise ValueError("prepared manifest mismatch; prepare again")
    for name, entry in metadata["datasets"].items():
        if digest(directory / f"{name}.csv") != entry["prepared_sha256"]:
            raise ValueError(f"prepared checksum mismatch: {name}")
    return directory, metadata


def _write_origins(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "dataset",
                "provider",
                "split",
                "origin",
                "target_start",
                "target_end",
                "input_key",
                "status",
                "reason",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)


def _empty_split(partition):
    reserved = partition == "final"
    return {
        "status": "reserved" if reserved else "insufficient_evidence",
        "origin_count": 0,
        "count": 0,
        "mae": None,
        "mase": None,
        "smape": None,
        "wql": None,
        "pinball": {},
        "intervals": {},
        "relative_mae": None,
        "relative_mae_reason": "holdout_reserved" if reserved else None,
        "_absolute_error_sum": 0.0,
        "_scale_sum": {name: 0.0 for name in ("mase", "smape", "wql")},
        "_scale_count": {name: 0 for name in ("mase", "smape", "wql")},
        "_pinball_sum": {},
        "_interval_coverage_sum": {},
        "_interval_width_sum": {},
        "_interval_level": {},
    }


def _data_class(source_kind):
    if source_kind == "real_observations":
        return "historical"
    if "synthetic" in source_kind:
        return "synthetic"
    return "unclassified"


def _peak_rss_bytes():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def _percentile(values, probability):
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _write_origin_scores(path, rows):
    fields = (
        "dataset",
        "data_class",
        "provider",
        "split",
        "origin",
        "mae",
        "mase",
        "mase_reason",
        "smape",
        "smape_reason",
        "wql",
        "wql_reason",
        "pinball",
        "intervals",
        "latency_ms",
    )
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "pinball": json.dumps(row["pinball"], sort_keys=True),
                    "intervals": json.dumps(row["intervals"], sort_keys=True),
                }
            )


def _add_to_split(aggregate, core, benchmark):
    count = core["count"]
    aggregate["origin_count"] += 1
    aggregate["count"] += count
    aggregate["_absolute_error_sum"] += core["mae"] * count
    for name in ("mase", "smape", "wql"):
        value = benchmark[name]
        if value is not None:
            aggregate["_scale_sum"][name] += value * count
            aggregate["_scale_count"][name] += count
    for name, value in core.get("pinball", {}).items():
        aggregate["_pinball_sum"][name] = (
            aggregate["_pinball_sum"].get(name, 0.0) + value * count
        )
    for name, values in core.get("intervals", {}).items():
        aggregate["_interval_coverage_sum"][name] = (
            aggregate["_interval_coverage_sum"].get(name, 0.0)
            + values["coverage"] * count
        )
        aggregate["_interval_width_sum"][name] = (
            aggregate["_interval_width_sum"].get(name, 0.0) + values["width"] * count
        )
        aggregate["_interval_level"][name] = values["level"]


def _finish_split(aggregate):
    count = aggregate["count"]
    if not count:
        for key in tuple(aggregate):
            if key.startswith("_"):
                aggregate.pop(key)
        return
    aggregate["status"] = "evaluated"
    aggregate["mae"] = aggregate.pop("_absolute_error_sum") / count
    scale_sum = aggregate.pop("_scale_sum")
    scale_count = aggregate.pop("_scale_count")
    for name in ("mase", "smape", "wql"):
        score_count = scale_count[name]
        total = scale_sum[name]
        aggregate[name] = total / score_count if score_count else None
    aggregate["pinball"] = {
        name: value / count
        for name, value in sorted(aggregate.pop("_pinball_sum").items())
    }
    coverage = aggregate.pop("_interval_coverage_sum")
    width = aggregate.pop("_interval_width_sum")
    levels = aggregate.pop("_interval_level")
    aggregate["intervals"] = {
        name: {
            "coverage": value / count,
            "width": width[name] / count,
            "level": levels[name],
        }
        for name, value in sorted(coverage.items())
    }


def _latency_summary(values):
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values),
        "median_ms": statistics.median(values),
        "p95_ms": _percentile(values, 0.95),
        "max_ms": max(values),
    }


def run_suite(
    manifest: Path,
    output: Path,
    providers: tuple[str, ...],
    *,
    split_file: Path | None = None,
    score_splits: tuple[str, ...] = SCORABLE_PARTITIONS,
    allow_synthetic_final_for_legacy_experiment: bool = False,
) -> Path:
    """Run the benchmark, keeping real holdouts reserved.

    ``allow_synthetic_final_for_legacy_experiment`` exists only to recreate
    historical synthetic fixtures consumed by the joint-paths experiment.
    It cannot enable final scoring for a manifest containing real observations.
    """
    manifest, output = Path(manifest), Path(output)
    if "baseline" not in providers:
        raise DomainError("baseline_required", {"providers": list(providers)})
    score_splits = tuple(score_splits)
    if len(set(score_splits)) != len(score_splits) or set(score_splits) - set(
        (*SCORABLE_PARTITIONS, "final")
    ):
        raise ValueError(
            "the final holdout is reserved and cannot be scored by this runner"
        )
    specification = load_manifest(manifest)
    synthetic_legacy_final = (
        "final" in score_splits and allow_synthetic_final_for_legacy_experiment
    )
    if "final" in score_splits and not synthetic_legacy_final:
        raise ValueError(
            "the final holdout is reserved and cannot be scored by this runner"
        )
    if synthetic_legacy_final and any(
        "synthetic" not in config["source"]["kind"]
        for config in specification["datasets"].values()
    ):
        raise ValueError("legacy final scoring is restricted to synthetic fixtures")
    if len(set(providers)) != len(providers):
        raise ValueError("providers must be unique")
    supported_providers = {
        "baseline",
        "ets",
        "theta",
        "autoarima",
        *TIMESTRAL_PROVIDERS,
    }
    if set(providers) - supported_providers:
        raise ValueError("unsupported benchmark provider")
    output.mkdir(parents=True, exist_ok=True)
    directory, preparation = _prepared(manifest, output, specification)
    frozen = (
        validate_frozen_calendar(split_file, manifest, directory)
        if split_file
        else freeze_calendar(manifest, directory)
    )
    assumptions = {
        "datasets": {
            name: {
                "assumed_available_at": config["assumed_available_at"],
                "vintage_status": "assumed_not_observed",
                "timezone_assumption": config["timezone_assumption"],
                "bucket_labels": "right endpoint; bucket complete at event_time",
                "no_real_publication_time_certification": True,
            }
            for name, config in specification["datasets"].items()
        },
        "scenarios": specification.get("scenarios", []),
    }
    write_json(output / "assumptions.json", assumptions)
    pins = json.loads(
        (
            Path(__file__).resolve().parent.parent / "integrations/models.lock.json"
        ).read_text()
    )
    approval_envs = {
        "timestral": TIMESTRAL_APPROVAL_ENV,
        "timestral_123m": TIMESTRAL_123M_APPROVAL_ENV,
    }
    approved_timestral = {
        provider: provider in providers
        and os.environ.get(approval_envs[provider]) == "1"
        for provider in TIMESTRAL_PROVIDERS
    }
    timestral_statuses = {}
    for provider in TIMESTRAL_PROVIDERS:
        model_pins = pins[provider]
        revision = (
            f"{model_pins['weights']['repo']}@{model_pins['weights']['revision']};"
            f"code={model_pins['code']['revision']}"
        )
        timestral_statuses[provider] = (
            revision
            if approved_timestral[provider]
            else "pending_license; no weights loaded"
            if provider in providers
            else "not_requested"
        )
    write_json(output / "environment.json", _environment(timestral_statuses, providers))
    pending_models = {
        provider
        for provider in TIMESTRAL_PROVIDERS
        if provider in providers and not approved_timestral[provider]
    }
    pending = bool(pending_models)
    report = {
        "schema_version": 2,
        "status": "pending_model_comparison"
        if pending and not set(providers) - {"baseline", *TIMESTRAL_PROVIDERS}
        else "partial_comparison"
        if pending
        else "comparison_pending"
        if set(providers) - {"baseline"}
        else "baseline_only",
        "evaluation_mode": "rolling_origin_replay",
        "partition_names": {
            "exploration": "development",
            "selection": "validation",
            "final": "holdout",
        },
        "score_splits": list(score_splits),
        "manifest_sha256": digest(manifest),
        "frozen_splits": {
            "split_sha256": frozen["split_sha256"],
            "repository_file_sha256": digest(split_file) if split_file else None,
            "repository_file": str(split_file) if split_file else None,
            "calendar_artifact": "frozen_calendar.json",
        },
        "model_comparison": {
            "status": "pending_license"
            if pending
            else "not_requested"
            if set(providers) == {"baseline"}
            else "comparison_pending"
            if set(providers) - {"baseline"}
            else "not_requested",
            "reason": "Timestral checkpoints remain gated; no weights were loaded"
            if pending
            else "final holdout remains reserved for one future evaluation"
            if any(approved_timestral.values())
            else None,
        },
        "datasets": {},
        "scenarios": [
            dict(s, included_in_scores=False)
            for s in specification.get("scenarios", [])
        ],
    }
    # Freeze every dataset calendar and split before the first provider invocation.
    origins, jobs = [], []
    observations_by_dataset = {}
    snapshot_ids = {}
    frozen_calendar_output = {}
    classical_providers = {
        "ets": ETSProvider(),
        "theta": ThetaProvider(),
        "autoarima": AutoARIMAProvider(),
    }
    timestral_providers = {
        provider: TimestralProvider(
            pins[provider]["weights"]["repo"],
            pins[provider]["weights"]["revision"],
            pins[provider]["code"]["revision"],
            provider_id=provider,
        )
        for provider in TIMESTRAL_PROVIDERS
        if approved_timestral[provider]
    }
    for name, config in specification["datasets"].items():
        observations = load_csv(directory / f"{name}.csv")
        observations_by_dataset[name] = observations
        calendar = tuple(sorted({o.event_time for o in observations}))
        if len(calendar) != len(observations):
            raise ValueError("benchmark v1 requires one preselected series")
        split = dataset_split(calendar, config)
        partition_origins = dataset_origins(split, calendar, config)
        index_by_time = {value: index for index, value in enumerate(calendar)}
        frozen_dataset = frozen["datasets"][name]
        frozen_calendar_output[name] = {
            "timestamps": [value.isoformat() for value in calendar],
            "exploration_end": split.exploration_end.isoformat(),
            "selection_end": split.selection_end.isoformat(),
            "final_start": split.final_start.isoformat(),
            "final_end": split.final_end.isoformat() if split.final_end else None,
            "horizon": split.horizon,
            "stride": split.stride,
            "status": split.status,
            "origins": {
                partition: [
                    origin.isoformat() for origin in partition_origins[partition]
                ]
                for partition in PARTITIONS
            },
        }
        report["datasets"][name] = {
            "source": preparation["datasets"][name],
            "domain": config.get("domain", name),
            "data_class": _data_class(config["source"]["kind"]),
            "evaluation_mode": "rolling_origin_replay",
            "split_status": "historical_final_origins_excluded"
            if config.get("final_origin_policy") == "previously_evaluated"
            else split.status,
            "split_sha256": {
                "calendar": frozen_dataset["calendar_sha256"],
                "origins": frozen_dataset["origin_sha256"],
            },
            "providers": {},
        }
        for provider in providers:
            provider_report = {
                "status": "insufficient_evidence",
                "splits": {part: _empty_split(part) for part in PARTITIONS},
                "excluded": [],
            }
            if provider in TIMESTRAL_PROVIDERS and not approved_timestral[provider]:
                provider_report.update(
                    status="pending_license",
                    reason=(
                        f"{provider} weights are not approved for local evaluation; "
                        "no inference or weight download was attempted"
                    ),
                    relative_mae=None,
                    relative_mae_reason="unmatched_baseline",
                )
                report["datasets"][name]["providers"][provider] = provider_report
                continue
            report["datasets"][name]["providers"][provider] = provider_report
            for partition in PARTITIONS:
                for origin in partition_origins[partition]:
                    index = index_by_time[origin]
                    target_times = calendar[index + 1 : index + 1 + config["horizon"]]
                    row = {
                        "dataset": name,
                        "provider": provider,
                        "split": partition,
                        "origin": origin.isoformat(),
                        "target_start": target_times[0].isoformat(),
                        "target_end": target_times[-1].isoformat(),
                        "input_key": "",
                    }
                    if partition == "final" and not synthetic_legacy_final:
                        row.update(status="reserved", reason=HOLDOUT_REASON)
                        origins.append(row)
                        continue
                    if partition not in score_splits:
                        row.update(status="not_scored", reason="split_not_selected")
                        origins.append(row)
                        continue

                    targets = observations[index + 1 : index + 1 + config["horizon"]]
                    history = observations[
                        max(0, index + 1 - config["context"]) : index + 1
                    ]
                    snapshot_key = (name, origin)
                    if snapshot_key not in snapshot_ids:
                        snapshot_ids[snapshot_key] = freeze(
                            history,
                            origin,
                            (
                                "assumed_available_at=period_end_UTC; no historical publication-time certification",
                            ),
                        ).snapshot_id
                    row["input_key"] = snapshot_ids[snapshot_key]
                    reason = (
                        "incomplete_targets"
                        if any(o.value is None for o in targets)
                        else "insufficient_history"
                        if len(history) < config["context"]
                        else "missing_history"
                        if any(o.value is None for o in history)
                        else ""
                    )
                    row.update(
                        status="excluded" if reason else "eligible", reason=reason
                    )
                    origins.append(row)
                    if reason:
                        provider_report["excluded"].append(dict(row))
                    else:
                        jobs.append(
                            (
                                provider,
                                name,
                                config,
                                partition,
                                origin,
                                index,
                                row,
                            )
                        )
    write_json(output / "frozen_calendar.json", frozen_calendar_output)
    panels = []
    origin_scores = []
    timings = defaultdict(list)
    ledger = Ledger(output / "ledger.sqlite")
    graphs = {}
    exported_graphs = set()
    for (
        provider,
        name,
        config,
        partition,
        origin,
        index,
        row,
    ) in jobs:
        observations = observations_by_dataset[name]
        targets = observations[index + 1 : index + 1 + config["horizon"]]
        history = observations[max(0, index + 1 - config["context"]) : index + 1]
        snapshot = freeze(
            history,
            origin,
            (
                "assumed_available_at=period_end_UTC; no historical publication-time certification",
            ),
        )
        dataset = report["datasets"][name]
        provider_report = dataset["providers"][provider]
        graph_key = (name, provider)
        if graph_key not in graphs:
            graphs[graph_key] = _graph(name, config, provider)
        graph = graphs[graph_key]
        provider_instance = (
            SeasonalNaiveProvider(config["period"])
            if provider == "baseline"
            else timestral_providers[provider]
            if provider in TIMESTRAL_PROVIDERS
            else classical_providers[provider]
        )
        runtime_providers = {"seasonal_naive": SeasonalNaiveProvider(config["period"])}
        if provider != "baseline":
            runtime_providers[provider] = provider_instance
        runtime = Runtime(
            ledger,
            runtime_providers,
            {},
            lambda origin=origin: origin,
        )
        started = time.perf_counter()
        run = runtime.run(
            graph,
            {"history": snapshot},
            origin,
            f"benchmark:{digest(manifest)}:{name}:{origin.isoformat()}:{provider}",
        )
        latency_ms = (time.perf_counter() - started) * 1_000
        actuals = freeze(
            tuple(targets),
            max(o.available_at for o in targets),
            ("assumed_available_at=period_end_UTC",),
        )
        evaluation = evaluate_run(run, actuals, graph)
        ledger.put_snapshot(actuals)
        ledger.append_evaluation(evaluation)
        if provider == "baseline" and name not in exported_graphs:
            write_json(output / f"graph.{name}.json", graph.model_dump(mode="json"))
            exported_graphs.add(name)
        core = evaluation.metrics.get("baseline", {})
        if run.state != "completed" or core.get("status") != "evaluated":
            row.update(
                status="excluded", reason="provider_failed_or_insufficient_evidence"
            )
            provider_report["excluded"].append(dict(row))
            continue
        row.update(status="evaluated", reason="")
        forecast = run.results["baseline"]
        benchmark = score_origin(
            forecast,
            actual=(tuple(o.value for o in targets),),
            history=(tuple(o.value for o in history),),
            period=config["period"],
            core_metrics=core,
        )
        aggregate = provider_report["splits"][partition]
        _add_to_split(aggregate, core, benchmark)
        provider_report["status"] = "evaluated"
        provider_report.setdefault("provider_revision", forecast.provider_revision)
        if provider in TIMESTRAL_PROVIDERS:
            provider_report["authorization"] = "explicit_local_user_opt_in"
        origin_scores.append(
            {
                "dataset": name,
                "data_class": dataset["data_class"],
                "provider": provider,
                "split": partition,
                "origin": origin.isoformat(),
                "mae": core["mae"],
                **benchmark,
                "pinball": core.get("pinball", {}),
                "intervals": core.get("intervals", {}),
                "latency_ms": latency_ms,
            }
        )
        timings[(name, provider, partition)].append(latency_ms)
        if partition in SCORABLE_PARTITIONS:
            panels.append(
                {
                    "origin": origin.isoformat(),
                    "horizon": config["horizon"],
                    "series_ids": list(forecast.series_ids),
                    "errors": [
                        [
                            o.value - p
                            for o, p in zip(targets, forecast.point[0], strict=True)
                        ]
                    ],
                    "available_at": max(o.available_at for o in targets).isoformat(),
                    "target_timestamps": [o.event_time.isoformat() for o in targets],
                    "dataset": name,
                    "provider": provider,
                    "provider_id": forecast.provider_id,
                    "provider_revision": forecast.provider_revision,
                    "snapshot_id": snapshot.snapshot_id,
                    "actuals_snapshot_id": actuals.snapshot_id,
                    "run_id": run.run_id,
                    "evaluation_id": evaluation.evaluation_id,
                    "split": partition,
                    "manifest_sha256": digest(manifest),
                    "download_sha256": preparation["datasets"][name]["download_sha256"],
                    "availability_basis": "assumed_not_observed",
                    "assumed_available_at": config["assumed_available_at"],
                    "source_kind": config["source"]["kind"],
                }
            )
    for dataset in report["datasets"].values():
        for provider_report in dataset["providers"].values():
            for aggregate in provider_report["splits"].values():
                _finish_split(aggregate)
    by_origin = {
        (row["dataset"], row["provider"], row["split"], row["origin"]): row
        for row in origin_scores
    }
    comparison_providers = tuple(
        provider
        for provider in providers
        if provider != "baseline"
        and (provider not in TIMESTRAL_PROVIDERS or approved_timestral[provider])
    )
    any_comparison = False
    evaluated_comparisons = set()
    for provider_name in comparison_providers:
        for name, dataset in report["datasets"].items():
            model_report = dataset["providers"][provider_name]
            for partition in SCORABLE_PARTITIONS:
                model_rows = {
                    origin: row
                    for (
                        dataset_name,
                        provider,
                        split_name,
                        origin,
                    ), row in by_origin.items()
                    if dataset_name == name
                    and provider == provider_name
                    and split_name == partition
                }
                baseline_rows = {
                    origin: row
                    for (
                        dataset_name,
                        provider,
                        split_name,
                        origin,
                    ), row in by_origin.items()
                    if dataset_name == name
                    and provider == "baseline"
                    and split_name == partition
                }
                matched = sorted(set(model_rows) & set(baseline_rows))
                split_result = model_report["splits"][partition]
                split_result["matched_origin_count"] = len(matched)
                model_losses = [model_rows[origin]["mae"] for origin in matched]
                baseline_losses = [baseline_rows[origin]["mae"] for origin in matched]
                value, reason = relative_mae(
                    statistics.fmean(model_losses) if model_losses else None,
                    statistics.fmean(baseline_losses) if baseline_losses else None,
                )
                split_result["relative_mae"] = value
                split_result["relative_mae_reason"] = reason
                if matched:
                    any_comparison = True
                    evaluated_comparisons.add(provider_name)
                seed_material = (
                    f"{frozen['split_sha256']}:{name}:{provider_name}:"
                    f"{partition}:bootstrap"
                )
                seed = int(hashlib.sha256(seed_material.encode()).hexdigest()[:16], 16)
                split_result["bootstrap_skill"] = bootstrap_skill_interval(
                    model_losses,
                    baseline_losses,
                    horizon=specification["datasets"][name]["horizon"],
                    stride=frozen_calendar_output[name]["stride"],
                    seed=seed,
                )
                split_result["diebold_mariano"] = diebold_mariano(
                    model_losses,
                    baseline_losses,
                    horizon=specification["datasets"][name]["horizon"],
                    stride=frozen_calendar_output[name]["stride"],
                )

    if any_comparison:
        report["status"] = (
            "partial_comparison" if pending else "development_validation_evaluated"
        )
        report["model_comparison"].update(
            status="development_validation_evaluated",
            evaluated_providers=sorted(evaluated_comparisons),
            reason="final holdout remains reserved for one future evaluation",
        )
    elif pending:
        report["status"] = "pending_model_comparison"
        report["model_comparison"]["status"] = "pending_license"
    elif comparison_providers:
        report["status"] = "insufficient_evidence"
        report["model_comparison"]["status"] = "insufficient_evidence"
    else:
        report["status"] = "baseline_only"
        report["model_comparison"]["status"] = "not_requested"

    for provider in providers:
        with (output / f"residuals.{provider}.jsonl").open("w") as stream:
            for panel in panels:
                if panel["provider"] == provider:
                    stream.write(
                        json.dumps(panel, sort_keys=True, allow_nan=False) + "\n"
                    )
    _write_origins(output / "origins.csv", origins)
    _write_origin_scores(output / "origin_scores.csv", origin_scores)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    performance = {
        "execution_device": "cpu",
        "latency_scope": "Runtime.run forecast issuance; excludes evaluation and data preparation",
        "memory_scope": "process peak RSS; includes preparation, inference, evaluation, and output",
        "process_peak_rss_bytes": _peak_rss_bytes(),
        "process_cpu_seconds": {
            "user": usage.ru_utime,
            "system": usage.ru_stime,
        },
        "origins": [
            {
                "dataset": name,
                "provider": provider,
                "split": partition,
                **_latency_summary(values),
                "process_peak_rss_bytes": _peak_rss_bytes(),
            }
            for (name, provider, partition), values in sorted(timings.items())
        ],
    }
    write_json(output / "performance.json", performance)
    report["performance"] = performance
    write_json(output / "report.json", report)
    return output / "report.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split-file", type=Path)
    parser.add_argument(
        "--providers",
        nargs="+",
        default=[
            "baseline",
            "ets",
            "theta",
            "autoarima",
            "timestral",
            "timestral_123m",
        ],
    )
    args = parser.parse_args()
    try:
        print(
            run_suite(
                args.manifest,
                args.output,
                tuple(args.providers),
                split_file=args.split_file,
            )
        )
    except DomainError as error:
        print(error.model_dump_json(), file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
