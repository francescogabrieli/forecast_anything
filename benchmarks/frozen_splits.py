"""Create and verify repository-pinned split hashes without reading values."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

from forecast_anything.evaluation.splits import build_splits

from .prepare import digest, load_manifest, prepare_suite, timestamp, write_json

PARTITIONS = ("exploration", "selection", "final")
FINAL_ORIGIN_POLICIES = {
    "rolling_tail",
    "previously_evaluated",
    "fresh_window",
}


def _hash_json(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _timestamp_calendar(path: Path) -> tuple[datetime, ...]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "event_time" not in reader.fieldnames:
            raise ValueError(f"prepared calendar has no event_time column: {path.name}")
        calendar = tuple(sorted(timestamp(row["event_time"]) for row in reader))
    if not calendar or len(calendar) != len(set(calendar)):
        raise ValueError(
            f"prepared calendar must have unique event_time values: {path.name}"
        )
    return calendar


def _target_timestamps(calendar, origins, horizon):
    index_by_origin = {origin: index for index, origin in enumerate(calendar)}
    return tuple(
        calendar[target_index]
        for origin in origins
        for target_index in range(
            index_by_origin[origin] + 1,
            index_by_origin[origin] + horizon + 1,
        )
    )


def dataset_origins(
    split,
    calendar,
    config,
    *,
    historical_target_timestamps=(),
) -> dict[str, tuple[datetime, ...]]:
    """Apply the declared holdout policy to the complete rolling-origin calendar."""
    policy = config.get("final_origin_policy", "rolling_tail")
    if policy not in FINAL_ORIGIN_POLICIES:
        raise ValueError(f"unsupported final origin policy: {policy}")
    origins = {
        partition: split.origins_for(partition, calendar) for partition in PARTITIONS
    }
    if policy == "previously_evaluated":
        origins["final"] = ()
    elif policy == "fresh_window" and split.final_end is None:
        raise ValueError("fresh final windows require an explicit final_end")
    if policy == "fresh_window" and not origins["final"]:
        raise ValueError("fresh final window does not contain complete origins")
    previous_targets = {
        value.astimezone(calendar[0].tzinfo)
        if isinstance(value, datetime)
        else timestamp(value)
        for value in historical_target_timestamps
    }
    if origins["final"] and previous_targets:
        final_targets = set(
            _target_timestamps(calendar, origins["final"], split.horizon)
        )
        reused = final_targets.intersection(previous_targets)
        if reused:
            series_id = config.get("series_id", "unknown")
            first = min(reused).isoformat()
            raise ValueError(
                f"final holdout for {series_id} reuses historically scored target "
                f"timestamp {first} ({len(reused)} reused labels)"
            )
    return origins


def dataset_split(calendar, config):
    bounds = config.get("split_bounds")
    if bounds is None:
        return build_splits(
            calendar,
            config["horizon"],
            stride=config.get("origin_stride"),
        )
    return build_splits(
        calendar,
        config["horizon"],
        stride=config.get("origin_stride"),
        exploration_end=timestamp(bounds["exploration_end"]),
        selection_end=timestamp(bounds["selection_end"]),
        final_start=timestamp(bounds["final_start"]),
        final_end=timestamp(bounds["final_end"]),
    )


def freeze_calendar(manifest: Path, prepared_directory: Path) -> dict:
    """Build split metadata from timestamps alone; no observation value is read."""
    manifest, prepared_directory = Path(manifest), Path(prepared_directory)
    specification = load_manifest(manifest)
    history_file_value = specification.get("historical_targets_file")
    history_path = manifest.parent / history_file_value if history_file_value else None
    if history_path is not None:
        if not history_path.is_file():
            raise ValueError(f"historical target archive is missing: {history_path}")
        history_archive = json.loads(history_path.read_text())
        if history_archive.get("schema_version") != 1:
            raise ValueError("unsupported historical target archive schema")
        history_by_series = history_archive.get("series", {})
    else:
        history_archive = {"series": {}}
        history_by_series = {}
    datasets = {}
    for name, config in specification["datasets"].items():
        calendar = _timestamp_calendar(prepared_directory / f"{name}.csv")
        split = dataset_split(calendar, config)
        series_id = config.get("series_id", name)
        series_history = history_by_series.get(series_id, {})
        historical_targets = tuple(
            timestamp(value) for value in series_history.get("target_timestamps", ())
        )
        partition_origins = dataset_origins(
            split,
            calendar,
            config,
            historical_target_timestamps=historical_targets,
        )
        origins = {
            partition: [origin.isoformat() for origin in partition_origins[partition]]
            for partition in PARTITIONS
        }
        final_targets = sorted(
            {
                target.isoformat()
                for target in _target_timestamps(
                    calendar, partition_origins["final"], split.horizon
                )
            }
        )
        timestamps = [value.isoformat() for value in calendar]
        datasets[name] = {
            "series_id": series_id,
            "calendar_count": len(timestamps),
            "calendar_sha256": _hash_json(timestamps),
            "exploration_end": split.exploration_end.isoformat(),
            "selection_end": split.selection_end.isoformat(),
            "final_start": split.final_start.isoformat(),
            "final_end": split.final_end.isoformat() if split.final_end else None,
            "horizon": split.horizon,
            "stride": split.stride,
            "origin_count": {part: len(rows) for part, rows in origins.items()},
            "origin_sha256": {part: _hash_json(rows) for part, rows in origins.items()},
            "historical_target_count": len(historical_targets),
            "historical_target_sha256": _hash_json(
                [value.isoformat() for value in historical_targets]
            ),
            "final_target_count": len(final_targets),
            "final_target_sha256": _hash_json(final_targets),
        }
    frozen = {
        "schema_version": 1,
        "manifest_sha256": digest(manifest),
        "historical_targets_file": history_file_value,
        "historical_targets_sha256": digest(history_path) if history_path else None,
        "datasets": datasets,
    }
    frozen["split_sha256"] = _hash_json(frozen)
    return frozen


def write_frozen_calendar(path: Path, frozen_calendar: dict) -> None:
    write_json(path, frozen_calendar)


def validate_frozen_calendar(
    path: Path, manifest: Path, prepared_directory: Path
) -> dict:
    """Reject changed manifests, calendars, boundaries, or origin assignments."""
    path = Path(path)
    recorded = json.loads(path.read_text())
    current = freeze_calendar(manifest, prepared_directory)
    if recorded != current:
        raise ValueError(
            "frozen split mismatch; regenerate the split file before evaluation"
        )
    return recorded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, default=Path(".local/data"))
    parser.add_argument(
        "--output", type=Path, default=Path("benchmarks/splits/phase0.json")
    )
    args = parser.parse_args()
    prepare_suite(args.manifest, args.prepared)
    frozen = freeze_calendar(args.manifest, args.prepared)
    write_frozen_calendar(args.output, frozen)
    print(
        json.dumps(
            {
                "split_sha256": frozen["split_sha256"],
                "output": str(args.output),
                "datasets": {
                    name: dataset["origin_count"]
                    for name, dataset in frozen["datasets"].items()
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
