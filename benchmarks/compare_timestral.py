"""Paired local checkpoint evaluation on a fixed univariate GIFT-Eval sample.

Requires PyArrow in the benchmark environment and explicitly prepared weights.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

from forecast_anything.providers.configuration import (
    TIMESTRAL_MODELS,
    pinned_timestral_provider,
)

DATASET_REVISION = "30841734ac5cfddbd0c3bad6d09d2b6b32becbb0"
# Split by original dataset. Values are path, seasonal period, horizon.
GROUPS = {
    "development": {
        "hospital": ("hospital", 12, 12),
        "car_parts_with_missing": ("car_parts_with_missing", 12, 12),
        "m4_hourly": ("m4_hourly", 24, 24),
    },
    "holdout": {
        "jena_weather": ("jena_weather", 144, 144),
        "saugeenday": ("saugeenday/D", 7, 7),
        "us_births": ("us_births/D", 7, 7),
        "solar": ("solar/H", 24, 24),
    },
}
INPUT_SHA256 = {
    "car_parts_with_missing": "78ea2e9ed786061c2c2c723f265bd61dcba8b316a0a6b9d39366ccf1ca26245a",
    "hospital": "761494d348761856659fc901d9c509b6564af87fc9e1b165c703cec6086e332e",
    "jena_weather": "b2cc351f93268eea352a08cdd76d836711535c6cb157a7f3cf338d9b4db9c700",
    "m4_hourly": "44f0f708d4ab5f8008fb7d656c02b6990752cf8009ea2655f97cb01fadde5bb2",
    "saugeenday": "94d1adf6571e606c8d22784253335b38cb23854983b9c374d04285a233f8d0e7",
    "solar": "16d10540595200124ac0d8d3f46e6d27951ce53ca3d0782cb2453e1afbba86f8",
    "us_births": "c72c9ec4a8840eb79d876aaec0dd4ca0ea57fd53d264039bd9cd4b0e5c667b13",
}
CONTEXT = 512
SERIES_PER_DATASET = 12
ORIGINS_PER_SERIES = 4
THREADS = 4


def read_series(path):
    import pyarrow as pa

    with pa.memory_map(str(path)) as source:
        table = pa.ipc.open_stream(source).read_all()
        for row in table.select(["item_id", "target"]).to_pylist():
            values = np.asarray(row["target"], dtype=np.float32)
            for index, series in enumerate(np.atleast_2d(values)):
                yield f"{row['item_id']}:{index}", series


def cases(path, period, horizon):
    series = sorted(
        read_series(path), key=lambda pair: hashlib.sha256(pair[0].encode()).digest()
    )
    for key, values in series[:SERIES_PER_DATASET]:
        for offset in range(ORIGINS_PER_SERIES, 0, -1):
            start = len(values) - offset * horizon
            if start < period * 2:
                continue
            history = values[max(0, start - CONTEXT) : start]
            actual = values[start : start + horizon]
            seasonal = np.resize(history[-period:], horizon)
            mask = np.isfinite(actual) & np.isfinite(seasonal)
            difference = np.abs(history[period:] - history[:-period])
            valid_difference = difference[np.isfinite(difference)]
            if not mask.any() or not valid_difference.size:
                continue
            scale = float(valid_difference.mean())
            if scale == 0:
                continue
            yield key, start, history, actual, seasonal, mask, scale


def _point_forecast(forecaster, context, horizon):
    result = forecaster.forecast(
        context,
        prediction_length=horizon,
        observation_mask=np.isfinite(context),
    )
    return result.median.detach().cpu().numpy().reshape(-1)


def compare(data, model, recent_context=None):
    import torch

    for dataset, expected in INPUT_SHA256.items():
        with (data / f"{dataset}.arrow").open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != expected:
            raise ValueError(f"Input SHA-256 mismatch for {dataset}")
    torch.set_num_threads(THREADS)
    provider = pinned_timestral_provider(model)
    start = perf_counter()
    forecaster = provider._load()
    load_seconds = perf_counter() - start
    datasets = {}
    for split, group in GROUPS.items():
        for dataset, (_, period, horizon) in group.items():
            observations = []
            for key, index, history, actual, seasonal, mask, scale in cases(
                data / f"{dataset}.arrow", period, horizon
            ):
                context = history.reshape(1, 1, -1)
                start = perf_counter()
                prediction = _point_forecast(forecaster, context, horizon)
                if recent_context is not None and history.size > recent_context:
                    recent = _point_forecast(
                        forecaster, context[..., -recent_context:], horizon
                    )
                    prediction = (prediction + recent) / 2
                seconds = perf_counter() - start
                if not np.isfinite(prediction).all():
                    raise ValueError(f"Nonfinite forecast: {dataset} {key} {index}")
                observations.append(
                    {
                        "series": key,
                        "origin_index": index,
                        "cells": int(mask.sum()),
                        "mase": float(
                            np.abs(prediction[mask] - actual[mask]).mean() / scale
                        ),
                        "baseline_mase": float(
                            np.abs(seasonal[mask] - actual[mask]).mean() / scale
                        ),
                        "seconds": seconds,
                    }
                )
            if not observations:
                raise ValueError(f"No matched evaluation cases for {dataset}")
            datasets[dataset] = {
                "split": split,
                "horizon": horizon,
                "period": period,
                "cases": observations,
                "mase": float(np.mean([r["mase"] for r in observations])),
                "baseline_mase": float(
                    np.mean([r["baseline_mase"] for r in observations])
                ),
            }
            print(f"{model} {dataset}: {len(observations)} windows", file=sys.stderr)
    return {
        "dataset_revision": DATASET_REVISION,
        "input_sha256": INPUT_SHA256,
        "provider_revision": provider.capabilities().provider_revision,
        "load_seconds": load_seconds,
        "threads": THREADS,
        "context": CONTEXT,
        "recent_context": recent_context,
        "datasets": datasets,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--model", choices=TIMESTRAL_MODELS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--recent-context", type=int, choices=range(1, CONTEXT), metavar="STEPS"
    )
    args = parser.parse_args()
    report = compare(args.data, args.model, args.recent_context)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
