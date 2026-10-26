"""Adapter boundaries: leakage, array axes, provenance, and optional imports."""

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from forecast_anything.contracts import (
    DomainError,
    ForecastRequest,
    Observation,
    Snapshot,
)
from forecast_anything.providers.timestral import TimestralProvider

T = datetime(2026, 10, 24, tzinfo=timezone.utc)


def request():
    return ForecastRequest(
        snapshot=Snapshot(
            snapshot_id="fixture",
            as_of=T,
            observations=tuple(
                Observation(
                    series_id=s,
                    event_time=T - timedelta(hours=1 - i),
                    available_at=T,
                    revision="r",
                    value=v,
                    unit=u,
                )
                for s, u, vs in (("b", "kWh", (3, 4)), ("a", "count", (1, None)))
                for i, v in enumerate(vs)
            ),
            assumptions=("fixture history",),
        ),
        horizon=2,
        frequency="1h",
        known_future=None,
    )


@pytest.fixture
def fake(monkeypatch):
    class Forecaster:
        loads = []
        calls = []

        @classmethod
        def from_pretrained(cls, checkpoint, *, revision, device):
            cls.loads.append((checkpoint, revision, device))
            return cls()

        def forecast(
            self, context, *, prediction_length, observation_mask, known_covariates
        ):
            self.calls.append((context, observation_mask, known_covariates))
            q = np.array(
                [[[[10, 11, 12], [20, 21, 22]], [[30, 31, 32], [40, 41, 42]]]],
                dtype=np.float32,
            )
            return SimpleNamespace(
                quantiles=q, quantile_levels=(0.1, 0.5, 0.9), median=q[..., 1]
            )

    monkeypatch.setattr(
        "forecast_anything.providers.timestral.distribution",
        lambda name: SimpleNamespace(
            read_text=lambda path: '{"vcs_info":{"commit_id":"fixture"}}'
        ),
    )
    monkeypatch.setitem(
        sys.modules, "timestral", SimpleNamespace(TimestralForecaster=Forecaster)
    )
    return Forecaster


def provider():
    return TimestralProvider("mistralai/Timestral-28M", "fixture", "fixture")


def test_target_after_origin_is_rejected(fake):
    r = request()
    r.snapshot.observations[-1].event_time = T + timedelta(hours=1)
    with pytest.raises(DomainError, match="future_history"):
        provider().forecast(r)
    assert fake.loads == []


def test_late_known_covariate_is_rejected(fake):
    r = request()
    r.known_future = Snapshot(
        snapshot_id="cov",
        as_of=T + timedelta(hours=1),
        observations=(
            Observation(
                series_id="calendar",
                event_time=T + timedelta(hours=1),
                available_at=T + timedelta(seconds=1),
                revision="1",
                value=5,
                unit="flag",
            ),
        ),
        assumptions=(),
    )
    with pytest.raises(DomainError, match="unavailable_observation"):
        provider().forecast(r)
    assert fake.loads == []


def test_preserves_quantiles_and_real_provider(fake):
    p = provider()
    result = p.forecast(request())
    p.forecast(request())
    assert result.series_ids == ("a", "b")
    assert result.units == ("count", "kWh")
    assert result.point == ((11, 21), (31, 41))
    assert result.quantiles == {
        "0.1": ((10, 20), (30, 40)),
        "0.5": ((11, 21), (31, 41)),
        "0.9": ((12, 22), (32, 42)),
    }
    assert result.provider_id == "timestral"
    assert "fixture" in result.provider_revision
    assert any("mistralai/Timestral-28M" in a for a in result.assumptions)
    assert result.paths is None and result.sample_group_id is None
    assert result.timestamps == (T + timedelta(hours=1), T + timedelta(hours=2))
    assert fake.loads == [("mistralai/Timestral-28M", "fixture", "cpu")]
    context, mask, known = fake.calls[0]
    np.testing.assert_equal(context, [[[1, np.nan], [3, 4]]])
    np.testing.assert_equal(mask, [[[True, False], [True, True]]])
    assert known is None


def test_known_future_only_has_nan_history(fake):
    r = request()
    r.known_future = Snapshot(
        snapshot_id="cov",
        as_of=T,
        observations=tuple(
            Observation(
                series_id="calendar",
                event_time=T + timedelta(hours=i),
                available_at=T,
                revision="r",
                value=v,
                unit="flag",
            )
            for i, v in ((1, 5), (2, 6))
        ),
        assumptions=("calendar known",),
    )
    result = provider().forecast(r)
    np.testing.assert_equal(fake.calls[0][2], [[[np.nan, np.nan, 5, 6]]])
    assert "calendar known" in result.assumptions


def test_timestral_declares_marginals_not_paths():
    p = TimestralProvider(
        checkpoint="mistralai/Timestral-28M",
        revision="fixture",
        code_revision="fixture",
    )
    caps = p.capabilities()
    assert "marginal_quantiles" in caps.representations
    assert "joint_paths" not in caps.representations


def test_core_import_without_torch():
    script = """
import sys
class NoTorch:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'timestral'}:
            raise AssertionError('optional model import: ' + fullname)
sys.meta_path.insert(0, NoTorch())
from forecast_anything.providers.timestral import TimestralProvider
from forecast_anything.providers.baseline import SeasonalNaiveProvider
TimestralProvider('checkpoint', 'revision', 'code').capabilities()
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_wrong_code_revision_rejected_before_loading(fake, monkeypatch):
    monkeypatch.setattr(
        "forecast_anything.providers.timestral.distribution",
        lambda name: SimpleNamespace(
            read_text=lambda path: '{"vcs_info":{"commit_id":"other"}}'
        ),
    )
    with pytest.raises(DomainError, match="model_code_revision_mismatch"):
        provider().forecast(request())
    assert fake.loads == []


@pytest.mark.parametrize("change", ["missing", "shifted", "late_target", "options"])
def test_invalid_inputs_never_load_model(fake, change):
    r = request()
    if change == "missing":
        for o in r.snapshot.observations:
            o.value = None
    elif change == "shifted":
        r.snapshot.observations[0].event_time -= timedelta(minutes=1)
    elif change == "late_target":
        r.snapshot.observations[0].available_at += timedelta(seconds=1)
    else:
        r.options = {"unknown": True}
    with pytest.raises(DomainError):
        provider().forecast(r)
    assert fake.loads == []


def test_loaded_provider_provenance_cannot_be_relabelled(fake):
    p = provider()
    p.forecast(request())
    with pytest.raises(AttributeError):
        p.revision = "different-weights"
    with pytest.raises(AttributeError):
        p.code_revision = "different-code"
    with pytest.raises(AttributeError):
        p.checkpoint = "different-checkpoint"
