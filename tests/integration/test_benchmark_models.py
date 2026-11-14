"""Cross-domain recipes and frozen, complete-window benchmark evidence."""

import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.run import run_suite

MANIFEST = Path("tests/fixtures/benchmarks/manifest.yaml")


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def test_classical_reference_models_are_scored_and_compared(tmp_path):
    specification = json.loads(MANIFEST.read_text())
    for config in specification["datasets"].values():
        config["source"]["path"] = str(
            MANIFEST.parent.resolve() / config["source"]["path"]
        )
        config["context"] = 10
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(json.dumps(specification))

    report = json.loads(
        run_suite(
            manifest,
            tmp_path / "run",
            ("baseline", "ets", "theta", "autoarima"),
        ).read_text()
    )

    assert report["model_comparison"]["status"] == "development_validation_evaluated"
    for dataset in report["datasets"].values():
        baseline = dataset["providers"]["baseline"]
        for provider_name in ("ets", "theta", "autoarima"):
            provider = dataset["providers"][provider_name]
            assert provider["status"] == "evaluated"
            assert provider["provider_revision"]
            for split in ("exploration", "selection"):
                result = provider["splits"][split]
                assert (
                    result["matched_origin_count"]
                    == baseline["splits"][split]["origin_count"]
                )
                if result["matched_origin_count"]:
                    assert (
                        result["relative_mae"] is not None
                        or result["relative_mae_reason"] == "zero_baseline_mae"
                    )
                else:
                    assert result["relative_mae_reason"] == "point_unavailable"
                assert (
                    result["bootstrap_skill"]["count"] == result["matched_origin_count"]
                )
                assert (
                    result["diebold_mariano"]["count"] == result["matched_origin_count"]
                )
                if result["matched_origin_count"]:
                    # With no explicit stride, the frozen calendar uses the
                    # horizon as its stride. No origins overlap for horizon 2.
                    assert result["bootstrap_skill"]["block_size"] == 1
                    assert result["diebold_mariano"]["lag"] == 0
            assert provider["splits"]["final"]["status"] == "reserved"


def test_relative_mae_uses_only_origins_matched_with_baseline(tmp_path, monkeypatch):

    from forecast_anything.contracts import Capabilities
    from forecast_anything.providers.baseline import SeasonalNaiveProvider

    skipped_origin = datetime(2020, 1, 6, tzinfo=UTC)

    class MissingOriginProvider:
        def __init__(self):
            self.delegate = SeasonalNaiveProvider(period=2)

        def capabilities(self):
            return Capabilities(
                provider_id="ets",
                provider_revision="fixture-skip-one-origin-v1",
                representations=("point",),
                supports_known_future=True,
            )

        def forecast(self, request):
            if request.snapshot.as_of == skipped_origin:
                raise RuntimeError("fixture skips one origin")
            result = self.delegate.forecast(request)
            return result.model_copy(
                update={
                    "provider_id": "ets",
                    "provider_revision": "fixture-skip-one-origin-v1",
                }
            )

    monkeypatch.setattr(
        "benchmarks.run.ETSProvider", MissingOriginProvider, raising=False
    )
    report = json.loads(run_suite(MANIFEST, tmp_path, ("baseline", "ets")).read_text())
    result = report["datasets"]["activity"]["providers"]["ets"]["splits"]["exploration"]
    baseline = report["datasets"]["activity"]["providers"]["baseline"]["splits"][
        "exploration"
    ]
    assert result["matched_origin_count"] == baseline["origin_count"] - 1
    assert result["relative_mae"] == pytest.approx(1.0)


def test_approved_timestral_comparison_uses_same_development_and_validation_origins(
    tmp_path, monkeypatch
):
    from forecast_anything.contracts import Capabilities
    from forecast_anything.providers.baseline import SeasonalNaiveProvider

    class FixtureTimestralProvider:
        def __init__(
            self, checkpoint, revision, code_revision, *, provider_id="timestral"
        ):
            self.delegate = SeasonalNaiveProvider(period=1)
            self.revision = f"{checkpoint}@{revision};code={code_revision}"
            self.provider_id = provider_id

        def capabilities(self):
            return Capabilities(
                provider_id=self.provider_id,
                provider_revision=self.revision,
                representations=("point",),
                supports_known_future=True,
            )

        def forecast(self, request):
            result = self.delegate.forecast(request)
            return result.model_copy(
                update={
                    "provider_id": self.provider_id,
                    "provider_revision": self.revision,
                }
            )

    monkeypatch.setenv("FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED", "1")
    monkeypatch.setattr(
        "benchmarks.run.TimestralProvider", FixtureTimestralProvider, raising=False
    )
    report = json.loads(
        run_suite(MANIFEST, tmp_path, ("baseline", "timestral")).read_text()
    )

    assert report["status"] == "development_validation_evaluated"
    assert report["model_comparison"]["status"] == "development_validation_evaluated"
    for dataset in report["datasets"].values():
        baseline = dataset["providers"]["baseline"]
        timestral = dataset["providers"]["timestral"]
        assert timestral["status"] == "evaluated"
        for split in ("exploration", "selection"):
            baseline_split = baseline["splits"][split]
            timestral_split = timestral["splits"][split]
            assert timestral_split["origin_count"] == baseline_split["origin_count"] > 0
            assert (
                timestral_split["matched_origin_count"]
                == baseline_split["origin_count"]
            )
            assert timestral_split["relative_mae"] is not None
            assert timestral_split["bootstrap_skill"]["estimate"] is not None
            dm = timestral_split["diebold_mariano"]
            assert dm["reason"] in {None, "zero_loss_difference_variance"}
            assert (dm["p_value"] is not None) == (dm["reason"] is None)
        assert timestral["splits"]["final"]["status"] == "reserved"
        assert timestral["provider_revision"].startswith("mistralai/Timestral-28M@")


def test_approved_timestral_123m_uses_its_pinned_executable_route(
    tmp_path, monkeypatch
):
    from forecast_anything.contracts import Capabilities
    from forecast_anything.providers.baseline import SeasonalNaiveProvider

    class FixtureTimestralProvider:
        def __init__(self, checkpoint, revision, code_revision, *, provider_id):
            self.delegate = SeasonalNaiveProvider(period=1)
            self.revision = f"{checkpoint}@{revision};code={code_revision}"
            self.provider_id = provider_id

        def capabilities(self):
            return Capabilities(
                provider_id=self.provider_id,
                provider_revision=self.revision,
                representations=("point",),
                supports_known_future=True,
            )

        def forecast(self, request):
            result = self.delegate.forecast(request)
            return result.model_copy(
                update={
                    "provider_id": self.provider_id,
                    "provider_revision": self.revision,
                }
            )

    monkeypatch.setenv("FORECAST_ANYTHING_TIMESTRAL_123M_WEIGHTS_APPROVED", "1")
    monkeypatch.setattr(
        "benchmarks.run.TimestralProvider", FixtureTimestralProvider, raising=False
    )
    report = json.loads(
        run_suite(MANIFEST, tmp_path, ("baseline", "timestral_123m")).read_text()
    )

    for dataset in report["datasets"].values():
        model = dataset["providers"]["timestral_123m"]
        assert model["status"] == "evaluated"
        assert model["provider_revision"].startswith("mistralai/Timestral-123M@")
        assert model["splits"]["final"]["status"] == "reserved"
