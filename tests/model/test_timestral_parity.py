"""Real CPU parity gate. A skipped run never satisfies provider acceptance.

Only set FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED=1 after the pending
Modified MIT license applicability question has been resolved by the user.
"""

import json
import os
import platform
import resource
import time
from datetime import datetime, timedelta, timezone
from importlib.metadata import distribution
from pathlib import Path

import numpy as np
import pytest

from forecast_anything.contracts import ForecastRequest, Observation, Snapshot
from forecast_anything.providers.timestral import TimestralProvider

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    os.environ.get("FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED") != "1",
    reason="Unresolved Modified MIT weights license applicability; real parity not executed",
)
def test_real_timestral_cpu_fp32_parity(tmp_path):
    # Resolve/verify provenance before from_pretrained can download any weights.
    lock = json.loads((ROOT / "integrations/models.lock.json").read_text())["timestral"]
    checkpoint = lock["weights"]["repo"]
    revision = lock["weights"]["revision"]
    code_revision = lock["code"]["revision"]
    direct = json.loads(distribution("timestral").read_text("direct_url.json"))
    assert direct["vcs_info"]["commit_id"] == code_revision
    from huggingface_hub import HfApi

    assert HfApi().model_info(checkpoint, revision=revision).sha == revision
    import torch
    from timestral import TimestralForecaster

    torch.set_num_threads(1)
    origin = datetime(2026, 10, 24, tzinfo=timezone.utc)
    context = np.array(
        [[[1, 2, np.nan, 4, 3, 6, 5, 8], [9, 8, 7, 6, 5, 4, 3, 2]]], dtype=np.float32
    )
    known = np.array([[[np.nan] * 8 + [1, 0, 1]]], dtype=np.float32)
    observations = tuple(
        Observation(
            series_id=s,
            event_time=origin - timedelta(hours=7 - i),
            available_at=origin,
            revision="1",
            value=None if np.isnan(v) else float(v),
            unit="count",
        )
        for s, row in zip(("a", "b"), context[0])
        for i, v in enumerate(row)
    )
    covariates = tuple(
        Observation(
            series_id="calendar",
            event_time=origin + timedelta(hours=i + 1),
            available_at=origin,
            revision="1",
            value=float(v),
            unit="flag",
        )
        for i, v in enumerate((1, 0, 1))
    )
    request = ForecastRequest(
        snapshot=Snapshot(
            snapshot_id="parity",
            as_of=origin,
            observations=observations,
            assumptions=(),
        ),
        horizon=3,
        frequency="1h",
        known_future=Snapshot(
            snapshot_id="parity-cov",
            as_of=origin,
            observations=covariates,
            assumptions=(),
        ),
    )
    start = time.perf_counter()
    official = TimestralForecaster.from_pretrained(
        checkpoint, revision=revision, device="cpu"
    )
    assert all(
        p.device.type == "cpu" and p.dtype == torch.float32
        for p in official.model.parameters()
    )
    expected = official.forecast(
        context,
        prediction_length=3,
        observation_mask=np.isfinite(context),
        known_covariates=known,
    )
    cold = time.perf_counter() - start
    provider = TimestralProvider(checkpoint, revision, code_revision)
    start = time.perf_counter()
    actual = provider.forecast(request)
    adapter_cold = time.perf_counter() - start
    start = time.perf_counter()
    warm = provider.forecast(request)
    warm_seconds = time.perf_counter() - start
    np.testing.assert_allclose(
        actual.point, expected.median.detach().cpu().numpy()[0], atol=1e-5, rtol=1e-5
    )
    for i, level in enumerate(expected.quantile_levels):
        np.testing.assert_allclose(
            actual.quantiles[str(float(level))],
            expected.quantiles.detach().cpu().numpy()[0, :, :, i],
            atol=1e-5,
            rtol=1e-5,
        )
    assert warm == actual
    record = {
        "machine": platform.platform(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "checkpoint": checkpoint,
        "weights_revision": revision,
        "code_revision": code_revision,
        "device": "cpu",
        "dtype": "float32",
        "atol": 1e-5,
        "rtol": 1e-5,
        "official_cold_load_and_forecast_seconds": cold,
        "adapter_cold_seconds": adapter_cold,
        "adapter_warm_seconds": warm_seconds,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if platform.system() == "Darwin" else 1024),
        "status": "passed",
    }
    path = Path(
        os.environ.get(
            "FORECAST_ANYTHING_TIMESTRAL_EVIDENCE",
            str(tmp_path / "timestral-parity.json"),
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")
    print(f"Timestral parity evidence: {path}")
