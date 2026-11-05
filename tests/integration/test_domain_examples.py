"""Provider doubles check example wiring; genuine model evidence is separate."""

from pathlib import Path
from runpy import run_path

from forecast_anything.providers.baseline import SeasonalNaiveProvider


def test_public_example_uses_model_and_retains_separate_baseline(tmp_path):
    class Model(SeasonalNaiveProvider):
        def capabilities(self):
            return (
                super()
                .capabilities()
                .model_copy(
                    update={
                        "provider_id": "timestral",
                        "provider_revision": "model-double",
                    }
                )
            )

        def forecast(self, request):
            return (
                super()
                .forecast(request)
                .model_copy(
                    update={
                        "provider_id": "timestral",
                        "provider_revision": "model-double",
                    }
                )
            )

        def check_model(self):
            return {"cached": True, "ready": True}

    runner = run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/run_example.py")
    )["run_example"]
    runner.__globals__["configured_providers"] = lambda: {
        "timestral": Model(1),
        "seasonal_naive": SeasonalNaiveProvider(1),
    }
    run = runner("retail", tmp_path / "example.db")
    assert run.actual_provider["forecast"] == "timestral"
    assert run.results["reference"].provider_id == "seasonal_naive"
    assert run.results["reference"].point == ((12, 18, 15),)
    assert run.graph_id.endswith("_timestral")
