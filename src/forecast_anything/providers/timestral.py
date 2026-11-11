"""Pinned local CPU Timestral adapter; importing this module never imports Torch.

Weights have a Modified MIT license with a restriction above USD 20 million
in global consolidated monthly revenue. Review applicability before loading.
"""

import itertools
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from threading import Lock

import numpy as np

from ..contracts import Capabilities, DomainError, ForecastRequest, ForecastResult
from .base import frequency_step, observation_grid


class TimestralProvider:
    """One lazily loaded checkpoint per provider/worker, with immutable provenance."""

    def __init__(
        self,
        checkpoint: str,
        revision: str,
        code_revision: str,
        *,
        prepare_command: str = "forecast-anything model prepare",
    ):
        if not all(
            isinstance(v, str) and v.strip()
            for v in (checkpoint, revision, code_revision)
        ):
            raise DomainError("invalid_model_provenance", {})
        self._checkpoint = checkpoint
        self._revision = revision
        self._code_revision = code_revision
        self._prepare_command = prepare_command
        self._forecaster = None
        self._load_lock = Lock()

    @property
    def checkpoint(self) -> str:
        return self._checkpoint

    @property
    def revision(self) -> str:
        return self._revision

    @property
    def code_revision(self) -> str:
        return self._code_revision

    def capabilities(self) -> Capabilities:
        return Capabilities(
            provider_id="timestral",
            provider_revision=f"{self.checkpoint}@{self.revision};code={self.code_revision}",
            representations=("point", "marginal_quantiles"),
            supports_known_future=True,
        )

    def _dependency_status(self) -> str | None:
        try:
            package = distribution("timestral")
            distribution("torch")
            provenance = json.loads(package.read_text("direct_url.json") or "{}")
        except PackageNotFoundError:
            return "missing_dependency"
        except (OSError, ValueError, TypeError):
            return "code_revision_mismatch"
        if not isinstance(provenance, dict):
            return "code_revision_mismatch"
        vcs = provenance.get("vcs_info")
        if not isinstance(vcs, dict) or vcs.get("commit_id") != self.code_revision:
            return "code_revision_mismatch"
        return None

    def _snapshot_path(self) -> Path:
        # Mirror the Hub's cache environment without importing its networking client.
        home = Path(
            os.environ.get(
                "HF_HOME",
                str(
                    Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
                    / "huggingface"
                ),
            )
        )
        cache = Path(
            os.environ.get(
                "HF_HUB_CACHE",
                os.environ.get("HUGGINGFACE_HUB_CACHE", str(home / "hub")),
            )
        ).expanduser()
        return (
            cache
            / ("models--" + self.checkpoint.replace("/", "--"))
            / "snapshots"
            / self.revision
        )

    def check_model(self) -> dict:
        """Inspect installed provenance and exact cache revision, without imports/I/O to network.

        ``cached`` is artifact availability, not a successful in-process model load.
        Only explicit preparation or actual inference can establish ``ready``.
        """
        dependency_error = self._dependency_status()
        path = self._snapshot_path()
        try:
            cached = all(
                (path / name).is_file() and (path / name).stat().st_size > 0
                for name in ("config.json", "model.safetensors")
            )
        except OSError:
            cached = False
        status = dependency_error or (
            "loaded"
            if self._forecaster is not None
            else "cached"
            if cached
            else "weights_missing"
        )
        return {
            "provider_id": "timestral",
            "checkpoint": self.checkpoint,
            "revision": self.revision,
            "code_revision": self.code_revision,
            "device": "cpu",
            "dtype": "float32",
            "status": status,
            "cached": cached if dependency_error is None else False,
            "ready": self._forecaster is not None and dependency_error is None,
            "prepare_command": self._prepare_command,
            "install_command": self._prepare_command,
            "weights_license": "Modified MIT; global consolidated monthly revenue above USD 20 million requires a separate license",
            "weights_license_url": f"https://huggingface.co/{self.checkpoint}/blob/{self.revision}/LICENSE",
        }

    def _require_dependency(self):
        status = self._dependency_status()
        if status:
            raise DomainError(
                "missing_model_dependency"
                if status == "missing_dependency"
                else "model_code_revision_mismatch",
                {
                    "expected": self.code_revision,
                    "setup": f"Run {self._prepare_command} to install the pinned model code and weights.",
                },
            )

    def _install_model_dependency(self) -> None:
        requirement = f"timestral @ git+https://github.com/mistralai/timestral.git@{self.code_revision}"
        uv = shutil.which("uv")
        command = (
            [uv, "pip", "install", "--python", sys.executable, requirement]
            if uv
            else [sys.executable, "-m", "pip", "install", requirement]
        )
        try:
            subprocess.run(command, check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise DomainError(
                "model_dependency_install_failed",
                {
                    "prepare_command": self._prepare_command,
                    "error_type": type(error).__name__,
                },
            ) from error

    def prepare_dependencies(self) -> None:
        """Install the pinned inference package explicitly, without downloading weights."""
        if self._dependency_status() is not None:
            self._install_model_dependency()
        self._require_dependency()

    def prepare_model(self) -> dict:
        """Prepare pinned inference code and weights, then verify CPU loading."""
        self.prepare_dependencies()
        if not self.check_model()["cached"]:
            try:
                from huggingface_hub import snapshot_download

                snapshot_download(
                    self.checkpoint,
                    revision=self.revision,
                    allow_patterns=["config.json", "model.safetensors"],
                )
            except Exception as error:
                raise DomainError(
                    "model_preparation_failed",
                    {
                        "prepare_command": self._prepare_command,
                        "error_type": type(error).__name__,
                    },
                ) from error
        self._load()
        return self.check_model()

    def verify_cached_model(self) -> None:
        """Load the pinned local model without fetching missing artifacts."""
        self._load()

    def _load(self):
        with self._load_lock:
            if self._forecaster is None:
                self._require_dependency()
                if not self.check_model()["cached"]:
                    raise DomainError(
                        "model_not_prepared",
                        {
                            "prepare_command": self._prepare_command,
                            "checkpoint": self.checkpoint,
                            "revision": self.revision,
                        },
                    )
                try:
                    from timestral import TimestralForecaster

                    self._forecaster = TimestralForecaster.from_pretrained(
                        self.checkpoint,
                        revision=self.revision,
                        device="cpu",
                        local_files_only=True,
                    )
                except Exception as error:
                    raise DomainError(
                        "model_load_failed",
                        {
                            "prepare_command": self._prepare_command,
                            "error_type": type(error).__name__,
                        },
                    ) from error
        return self._forecaster

    def forecast(self, request: ForecastRequest) -> ForecastResult:
        request = ForecastRequest.model_validate(request.model_dump())
        if request.options:
            raise DomainError(
                "unsupported_options", {"options": sorted(request.options)}
            )
        origin = request.snapshot.as_of.astimezone(UTC)
        # Check before grid validation or any optional import/download.
        if any(
            o.event_time.astimezone(UTC) > origin for o in request.snapshot.observations
        ):
            raise DomainError("future_history", {})
        groups, calendar = observation_grid(request.snapshot, request.frequency)
        series_ids = tuple(sorted(groups))
        context = np.array(
            [
                [
                    [o.value if o.value is not None else np.nan for o in groups[s]]
                    for s in series_ids
                ]
            ],
            dtype=np.float32,
        )
        if not np.isfinite(context).any(axis=-1).all():
            raise DomainError("missing_observation", {})
        step = frequency_step(request.frequency)
        future = tuple(calendar[-1] + step * (i + 1) for i in range(request.horizon))
        known = None
        assumptions = request.snapshot.assumptions
        if request.known_future is not None:
            snapshot = request.known_future
            if any(
                o.available_at.astimezone(UTC) > origin for o in snapshot.observations
            ):
                raise DomainError("unavailable_observation", {})
            cov_groups, cov_calendar = observation_grid(snapshot, request.frequency)
            full_calendar = (*calendar, *future)
            if cov_calendar not in (future, full_calendar):
                raise DomainError("incompatible_calendar", {"input": "known_future"})
            known = np.full(
                (1, len(cov_groups), len(full_calendar)), np.nan, dtype=np.float32
            )
            offset = len(calendar) if cov_calendar == future else 0
            for i, s in enumerate(sorted(cov_groups)):
                known[0, i, offset:] = [
                    o.value if o.value is not None else np.nan for o in cov_groups[s]
                ]
            assumptions = (*assumptions, *snapshot.assumptions)
        forecaster = self._load()
        try:
            output = forecaster.forecast(
                context,
                prediction_length=request.horizon,
                observation_mask=np.isfinite(context),
                known_covariates=known,
            )
        except Exception as error:
            raise DomainError(
                "model_inference_failed",
                {"provider_id": "timestral", "error_type": type(error).__name__},
            ) from error
        # Official outputs are CPU tensors; fixtures may supply NumPy arrays.
        values = output.quantiles
        if hasattr(values, "detach"):
            values = values.detach().cpu().numpy()
        values = np.asarray(values)
        levels = tuple(float(v) for v in output.quantile_levels)
        if (
            values.shape != (1, len(series_ids), request.horizon, len(levels))
            or not np.isfinite(values).all()
            or 0.5 not in levels
            or len(set(levels)) != len(levels)
            or any(not 0 < q < 1 for q in levels)
            or any(b <= a for a, b in itertools.pairwise(levels))
            or (np.diff(values, axis=-1) < 0).any()
        ):
            raise DomainError("invalid_model_output", {})
        quantiles = {
            str(q): tuple(tuple(float(v) for v in row) for row in values[0, :, :, i])
            for i, q in enumerate(levels)
        }
        caps = self.capabilities()
        return ForecastResult(
            provider_id=caps.provider_id,
            provider_revision=caps.provider_revision,
            series_ids=series_ids,
            timestamps=future,
            units=tuple(groups[s][0].unit for s in series_ids),
            point=quantiles["0.5"],
            quantiles=quantiles,
            paths=None,
            sample_group_id=None,
            assumptions=(
                *assumptions,
                f"Timestral checkpoint={self.checkpoint}@{self.revision}; code={self.code_revision}; CPU fp32; official defaults; missing values remain NaN; marginal quantiles only",
            ),
        )
