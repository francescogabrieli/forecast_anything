"""Run the phase-zero benchmark twice and publish a stable leaderboard."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .prepare import write_json

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SPLIT_LABELS = {
    "exploration": "development",
    "selection": "validation",
    "final": "holdout",
}
ORIGIN_FIELDS = (
    "dataset",
    "provider",
    "split",
    "origin",
    "target_start",
    "target_end",
    "status",
    "reason",
)
SCORE_FIELDS = (
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
)
LEADERBOARD_FIELDS = (
    "dataset",
    "domain",
    "data_class",
    "evaluation_mode",
    "provider",
    "provider_status",
    "split",
    "split_label",
    "status",
    "origin_count",
    "count",
    "mae",
    "mase",
    "smape",
    "wql",
    "pinball",
    "intervals",
    "relative_mae",
    "bootstrap_skill",
    "diebold_mariano",
)


def _canonical_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read_projection(path: Path, fields: tuple[str, ...]) -> list[dict]:
    with path.open(newline="") as stream:
        rows = csv.DictReader(stream)
        return [
            {field: row[field] for field in fields}
            for row in sorted(
                rows,
                key=lambda item: (
                    item["dataset"],
                    item["provider"],
                    item["split"],
                    item.get("origin", ""),
                ),
            )
        ]


def _stability_projection(run_directory: Path) -> dict:
    report = json.loads((run_directory / "report.json").read_text())
    return {
        "manifest_sha256": report["manifest_sha256"],
        "split_sha256": report["frozen_splits"]["split_sha256"],
        "score_splits": report["score_splits"],
        "datasets": {
            dataset_name: {
                "data_class": dataset["data_class"],
                "split_sha256": dataset["split_sha256"],
                "providers": {
                    provider_name: {
                        "status": provider["status"],
                        "splits": {
                            split_name: {
                                key: split.get(key)
                                for key in (
                                    "status",
                                    "origin_count",
                                    "count",
                                    "mae",
                                    "mase",
                                    "smape",
                                    "wql",
                                    "pinball",
                                    "intervals",
                                    "relative_mae",
                                    "relative_mae_reason",
                                    "matched_origin_count",
                                    "bootstrap_skill",
                                    "diebold_mariano",
                                )
                            }
                            for split_name, split in provider["splits"].items()
                        },
                    }
                    for provider_name, provider in dataset["providers"].items()
                },
            }
            for dataset_name, dataset in report["datasets"].items()
        },
        "origins": _read_projection(run_directory / "origins.csv", ORIGIN_FIELDS),
        "scores": _read_projection(run_directory / "origin_scores.csv", SCORE_FIELDS),
    }


def _assert_holdout_reserved(run_directory: Path) -> int:
    """Reject run artifacts that score or materialize final holdout origins."""
    report = json.loads((run_directory / "report.json").read_text())
    if "final" in report.get("score_splits", []):
        raise RuntimeError("final holdout must not appear in score_splits")

    final_summaries = []
    for dataset in report.get("datasets", {}).values():
        for provider in dataset.get("providers", {}).values():
            final = provider.get("splits", {}).get("final")
            if final is None:
                raise RuntimeError("run report is missing a reserved final split")
            final_summaries.append(final)

    if not final_summaries:
        raise RuntimeError("run report has no final split summaries")
    metric_fields = (
        "mae",
        "mase",
        "smape",
        "wql",
        "pinball",
        "intervals",
        "relative_mae",
        "bootstrap_skill",
        "diebold_mariano",
    )
    for final in final_summaries:
        if (
            final.get("status") != "reserved"
            or final.get("origin_count") != 0
            or final.get("count") != 0
            or any(final.get(key) not in (None, "", {}) for key in metric_fields)
        ):
            raise RuntimeError("final holdout report contains scored values")

    with (run_directory / "origins.csv").open(newline="") as stream:
        final_origins = [
            row for row in csv.DictReader(stream) if row["split"] == "final"
        ]
    if not final_origins:
        raise RuntimeError("run artifacts are missing reserved final origins")
    if any(
        row.get("status") != "reserved" or row.get("input_key") for row in final_origins
    ):
        raise RuntimeError("final holdout origins are not reserved without inputs")

    with (run_directory / "origin_scores.csv").open(newline="") as stream:
        final_scores = [
            row for row in csv.DictReader(stream) if row["split"] == "final"
        ]
    if final_scores:
        raise RuntimeError(f"final holdout score rows detected: {len(final_scores)}")

    residual_files = tuple(run_directory.glob("residuals.*.jsonl"))
    for residual_file in residual_files:
        with residual_file.open() as stream:
            for line in stream:
                if line.strip() and json.loads(line).get("split") == "final":
                    raise RuntimeError(
                        f"final holdout residual rows detected in {residual_file.name}"
                    )
    return len(final_scores)


def _leaderboard_rows(report: dict) -> list[dict]:
    rows = []
    for dataset_name, dataset in report["datasets"].items():
        for provider_name, provider in dataset["providers"].items():
            for split_name, score in provider["splits"].items():
                rows.append(
                    {
                        "dataset": dataset_name,
                        "domain": dataset.get("domain", dataset_name),
                        "data_class": dataset["data_class"],
                        "evaluation_mode": dataset["evaluation_mode"],
                        "provider": provider_name,
                        "provider_status": provider["status"],
                        "split": split_name,
                        "split_label": SPLIT_LABELS[split_name],
                        **{
                            key: score.get(key)
                            for key in (
                                "status",
                                "origin_count",
                                "count",
                                "mae",
                                "mase",
                                "smape",
                                "wql",
                                "pinball",
                                "intervals",
                                "relative_mae",
                                "bootstrap_skill",
                                "diebold_mariano",
                            )
                        },
                    }
                )
    return rows


def _reference_model_rows(report: dict, providers: tuple[str, ...]) -> list[dict]:
    datasets = ";".join(sorted(report["datasets"]))
    pins = json.loads((REPOSITORY_ROOT / "integrations/models.lock.json").read_text())

    def provider_model(model, family, provider, revision, reason):
        if provider not in providers:
            status = (
                "not_requested"
                if provider in {"timestral", "timestral_123m"}
                else "available"
            )
            status_reason = "Implemented; not requested in this run"
        else:
            provider_reports = [
                dataset["providers"].get(provider, {})
                for dataset in report["datasets"].values()
            ]
            evaluated = next(
                (
                    item
                    for item in provider_reports
                    if item.get("status") == "evaluated"
                ),
                None,
            )
            if evaluated:
                status = "evaluated"
                revision = evaluated.get("provider_revision", revision)
                status_reason = "Development/validation only; holdout reserved"
            elif any(
                item.get("status") == "pending_license" for item in provider_reports
            ):
                status = "pending_license"
                status_reason = "Weights remain behind the explicit local approval gate"
            else:
                status = "insufficient_evidence"
                status_reason = "No complete matched development/validation origins"
        return {
            "model": model,
            "family": family,
            "provider": provider,
            "status": status,
            "revision": revision,
            "reason": reason if status == "available" else status_reason,
            "datasets": datasets if status in {"available", "evaluated"} else "",
        }

    rows = [
        provider_model(
            "seasonal_naive",
            "statistical_baseline",
            "baseline",
            "seasonal_naive@1",
            "Existing core provider",
        ),
        provider_model(
            "timestral_28m",
            "foundation_model",
            "timestral",
            f"{pins['timestral']['weights']['repo']}@{pins['timestral']['weights']['revision']}",
            "Existing gated Timestral 28M adapter",
        ),
        provider_model(
            "ets",
            "statistical",
            "ets",
            "ets-a-n-n-ses-grid-v1",
            "ETS(A,N,N), alpha selected on a fixed one-step SSE grid",
        ),
        provider_model(
            "theta",
            "statistical",
            "theta",
            "theta-nonseasonal-ses-drift-v1",
            "Nonseasonal Theta with optimized SES and fitted linear trend",
        ),
        provider_model(
            "autoarima",
            "statistical",
            "autoarima",
            "autoarima-css-aic-p0-3-d0-1-q0-v1",
            "AIC search over ARIMA(p,d,0), p=0..3 and d=0..1",
        ),
    ]
    rows.append(
        provider_model(
            "timestral_123m",
            "foundation_model",
            "timestral_123m",
            f"{pins['timestral_123m']['weights']['repo']}@"
            f"{pins['timestral_123m']['weights']['revision']};"
            f"code={pins['timestral_123m']['code']['revision']}",
            "Pinned Timestral 123M adapter behind the separate local approval gate",
        )
    )
    return rows


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True, allow_nan=False)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def _compress_intermediate_ledger(run_directory: Path) -> None:
    """Keep audit data for prior repetitions without duplicating raw DB size."""
    ledger = run_directory / "ledger.sqlite"
    if not ledger.exists():
        return
    archive = run_directory / "ledger.sqlite.gz"
    with (
        ledger.open("rb") as source,
        gzip.open(archive, "wb", compresslevel=1) as target,
    ):
        shutil.copyfileobj(source, target)
    ledger.unlink()


def run_repeated_leaderboard(
    manifest: Path,
    output: Path,
    providers: tuple[str, ...],
    *,
    split_file: Path | None = None,
    repetitions: int = 2,
) -> dict:
    """Run isolated benchmark processes and compare scores, not noisy timings."""
    if type(repetitions) is not int or repetitions < 2:
        raise ValueError("stability verification requires at least two repetitions")
    if "baseline" not in providers:
        raise ValueError("baseline is required for the reference leaderboard")
    if len(set(providers)) != len(providers):
        raise ValueError("providers must be unique")

    manifest = Path(manifest).resolve()
    output = Path(output).resolve()
    split_file = Path(split_file).resolve() if split_file else None
    output.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_id += f"-{uuid.uuid4().hex[:8]}"
    batch = output / "runs" / run_id
    batch.mkdir(parents=True)
    report_paths = []
    for index in range(repetitions):
        run_directory = batch / f"run-{index + 1:02d}"
        command = [
            sys.executable,
            "-m",
            "benchmarks.run",
            "--manifest",
            str(manifest),
            "--output",
            str(run_directory),
            "--providers",
            *providers,
        ]
        if split_file:
            command.extend(("--split-file", str(split_file)))
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=14_400,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(
                "benchmark repetition failed "
                f"({index + 1}/{repetitions}, exit={completed.returncode}): "
                f"{completed.stderr.strip()}"
            )
        report_paths.append(run_directory / "report.json")
        if index + 1 < repetitions:
            _compress_intermediate_ledger(run_directory)

    holdout_score_rows = sum(
        _assert_holdout_reserved(path.parent) for path in report_paths
    )
    projections = [_stability_projection(path.parent) for path in report_paths]
    projection_hashes = [_canonical_hash(projection) for projection in projections]
    stable = all(value == projection_hashes[0] for value in projection_hashes[1:])
    first_report = json.loads(report_paths[0].read_text())
    leaderboard_path = output / "leaderboard.csv"
    reference_path = output / "reference_models.csv"
    stability_path = output / "stability.json"
    _write_csv(leaderboard_path, LEADERBOARD_FIELDS, _leaderboard_rows(first_report))
    _write_csv(
        reference_path,
        ("model", "family", "provider", "status", "revision", "reason", "datasets"),
        _reference_model_rows(first_report, providers),
    )
    stability = {
        "schema_version": 1,
        "status": "stable" if stable else "unstable",
        "repetitions": repetitions,
        "compared_splits": [
            SPLIT_LABELS[name] for name in first_report["score_splits"]
        ],
        "holdout": {
            "status": "reserved_unscored",
            "score_rows": holdout_score_rows,
        },
        "ignored_measurements": [
            "latency_ms",
            "performance.process_peak_rss_bytes",
            "performance.process_cpu_seconds",
        ],
        "score_projection_sha256": projection_hashes[0],
        "runs": [
            {
                "report": str(path),
                "projection_sha256": projection_hash,
            }
            for path, projection_hash in zip(
                report_paths, projection_hashes, strict=True
            )
        ],
    }
    write_json(stability_path, stability)
    return {
        "leaderboard": leaderboard_path,
        "reference_models": reference_path,
        "stability_file": stability_path,
        "stability": stability,
        "run_directory": batch,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--split-file", type=Path, default=Path("benchmarks/splits/phase0.json")
    )
    parser.add_argument("--output", type=Path, required=True)
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
    parser.add_argument("--repetitions", type=int, default=2)
    args = parser.parse_args()
    try:
        result = run_repeated_leaderboard(
            args.manifest,
            args.output,
            tuple(args.providers),
            split_file=args.split_file,
            repetitions=args.repetitions,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
    print(
        json.dumps(
            {
                "status": result["stability"]["status"],
                "leaderboard": str(result["leaderboard"]),
                "reference_models": str(result["reference_models"]),
                "stability": str(result["stability_file"]),
                "runs": str(result["run_directory"]),
            }
        )
    )
    if result["stability"]["status"] != "stable":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
