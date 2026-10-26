"""Freeze calendars, issue core runtime forecasts and export scored evidence.

The real Timestral gate is intentionally pending until license authorization.
Preparation and baseline inference never import or download model weights.
"""

import argparse
import csv
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

from forecast_anything.connectors.csv import load_csv
from forecast_anything.contracts import DomainError, GraphSpec, Node
from forecast_anything.evaluation.records import evaluate_run
from forecast_anything.evaluation.splits import build_splits
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze

from .prepare import digest, load_manifest, prepare_suite, write_json

PARTITIONS = ("exploration", "selection", "final")


def _graph(name, config):
    return GraphSpec(
        graph_id=f"benchmark:{name}",
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
                    "provider": "seasonal_naive",
                    "history": "history",
                    "horizon": config["horizon"],
                    "frequency": config["frequency"],
                    "options": {"period": config["period"]},
                    "relation_type": {"history": "statistical"},
                },
            ),
        ),
    )


def _environment():
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
            for name in ("prepare.py", "run.py")
        },
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("forecast-anything", "numpy", "pydantic")
        },
        "providers": {
            "baseline": "seasonal_naive@1",
            "timestral": "pending_license; no weights loaded",
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


def run_suite(manifest: Path, output: Path, providers: tuple[str, ...]) -> Path:
    manifest, output = Path(manifest), Path(output)
    if "baseline" not in providers:
        raise DomainError("baseline_required", {"providers": list(providers)})
    specification = load_manifest(manifest)
    if len(set(providers)) != len(providers):
        raise ValueError("providers must be unique")
    if set(providers) - {"baseline", "timestral"}:
        raise ValueError("unsupported benchmark provider")
    output.mkdir(parents=True, exist_ok=True)
    directory, preparation = _prepared(manifest, output, specification)
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
    write_json(output / "environment.json", _environment())
    report = {
        "schema_version": 1,
        "status": "pending_model_comparison",
        "manifest_sha256": digest(manifest),
        "model_comparison": {
            "status": "pending_license",
            "reason": "Timestral weights are not authorized; baseline-only evidence does not complete M4",
        },
        "datasets": {},
        "scenarios": [
            dict(s, included_in_scores=False)
            for s in specification.get("scenarios", [])
        ],
    }
    # Freeze every dataset calendar and split before the first provider invocation.
    frozen, origins, jobs = {}, [], []
    for name, config in specification["datasets"].items():
        observations = load_csv(directory / f"{name}.csv")
        calendar = tuple(sorted({o.event_time for o in observations}))
        if len(calendar) != len(observations):
            raise ValueError("benchmark v1 requires one preselected series")
        split = build_splits(calendar, config["horizon"])
        frozen[name] = {
            "timestamps": [t.isoformat() for t in calendar],
            "exploration_end": split.exploration_end.isoformat(),
            "selection_end": split.selection_end.isoformat(),
            "final_start": split.final_start.isoformat(),
            "horizon": split.horizon,
            "stride": split.stride,
            "status": split.status,
            "origins": {
                part: [t.isoformat() for t in split.origins_for(part, calendar)]
                for part in PARTITIONS
            },
        }
        report["datasets"][name] = {
            "source": preparation["datasets"][name],
            "split_status": split.status,
            "providers": {},
        }
        for provider in providers:
            if provider == "timestral":
                report["datasets"][name]["providers"][provider] = {
                    "status": "pending_license",
                    "reason": "No Timestral inference or weight download authorized",
                    "relative_mae": None,
                    "relative_mae_reason": "unmatched_baseline",
                }
                continue
            report["datasets"][name]["providers"][provider] = {
                "status": "insufficient_evidence",
                "splits": {
                    part: {"origin_count": 0, "count": 0, "mae": None}
                    for part in PARTITIONS
                },
                "excluded": [],
            }
            for partition in PARTITIONS:
                for origin in split.origins_for(partition, calendar):
                    index = calendar.index(origin)
                    targets = observations[index + 1 : index + 1 + config["horizon"]]
                    history = observations[
                        max(0, index + 1 - config["context"]) : index + 1
                    ]
                    snapshot = freeze(
                        history,
                        origin,
                        (
                            "assumed_available_at=period_end_UTC; no historical publication-time certification",
                        ),
                    )
                    reason = (
                        "incomplete_targets"
                        if any(o.value is None for o in targets)
                        else "insufficient_history"
                        if len(history) < config["context"]
                        else "missing_history"
                        if any(o.value is None for o in history)
                        else ""
                    )
                    row = {
                        "dataset": name,
                        "provider": provider,
                        "split": partition,
                        "origin": origin.isoformat(),
                        "target_start": targets[0].event_time.isoformat(),
                        "target_end": targets[-1].event_time.isoformat(),
                        "input_key": snapshot.snapshot_id,
                        "status": "excluded" if reason else "eligible",
                        "reason": reason,
                    }
                    origins.append(row)
                    if reason:
                        report["datasets"][name]["providers"][provider][
                            "excluded"
                        ].append(dict(row))
                    else:
                        jobs.append(
                            (name, config, partition, origin, snapshot, targets, row)
                        )
    write_json(output / "frozen_calendar.json", frozen)
    _write_origins(output / "origins.csv", origins)
    panels = []
    ledger = Ledger(output / "ledger.sqlite")
    for name, config, partition, origin, snapshot, targets, row in jobs:
        result = report["datasets"][name]["providers"]["baseline"]
        graph = _graph(name, config)
        runtime = Runtime(
            ledger,
            {"seasonal_naive": SeasonalNaiveProvider(config["period"])},
            {},
            lambda: origin,
        )
        run = runtime.run(
            graph,
            {"history": snapshot},
            origin,
            f"benchmark:{digest(manifest)}:{name}:{origin.isoformat()}:baseline",
        )
        actuals = freeze(
            tuple(targets),
            max(o.available_at for o in targets),
            ("assumed_available_at=period_end_UTC",),
        )
        evaluation = evaluate_run(run, actuals, graph)
        ledger.put_snapshot(actuals)
        ledger.append_evaluation(evaluation)
        write_json(output / f"graph.{name}.json", graph.model_dump(mode="json"))
        score = evaluation.metrics.get("baseline", {})
        if run.state != "completed" or score.get("status") != "evaluated":
            row.update(
                status="excluded", reason="provider_failed_or_insufficient_evidence"
            )
            result["excluded"].append(dict(row))
            continue
        row["status"] = "evaluated"
        aggregate = result["splits"][partition]
        aggregate["origin_count"] += 1
        aggregate["count"] += score["count"]
        aggregate["absolute_error_sum"] = (
            aggregate.get("absolute_error_sum", 0) + score["mae"] * score["count"]
        )
        aggregate["mae"] = aggregate["absolute_error_sum"] / aggregate["count"]
        result["status"] = "evaluated"
        if partition != "final":
            forecast = run.results["baseline"]
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
                    "provider": "baseline",
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
    for provider in providers:
        with (output / f"residuals.{provider}.jsonl").open("w") as stream:
            for panel in panels:
                if panel["provider"] == provider:
                    stream.write(
                        json.dumps(panel, sort_keys=True, allow_nan=False) + "\n"
                    )
    _write_origins(output / "origins.csv", origins)
    write_json(output / "report.json", report)
    return output / "report.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--providers", nargs="+", default=["baseline", "timestral"])
    args = parser.parse_args()
    try:
        print(run_suite(args.manifest, args.output, tuple(args.providers)))
    except DomainError as error:
        print(error.model_dump_json(), file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
