# Optional Timestral provider

The library adapter is implemented and **real CPU fp32 parity passed** against the pinned official implementation. The project owner authorized one local personal evaluation of the weights for this open-source project; that authorization applies to this evaluation only and does not resolve the license for other users or deployments. The stock CLI uses the seasonal-naive provider; Timestral remains opt-in.

## Install the optional dependency

From the repository root:

```sh
uv sync --locked --extra timestral --extra dev
```

This installs the pinned Timestral source package and its Python dependencies, including PyTorch. It does **not** download model weights. Weights are not included in this repository. With `FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED=1`, an explicitly invoked forecast can download the pinned weights to the Hugging Face cache on its first model load. Importing the provider or reading its capabilities does not load Timestral or PyTorch; the core remains usable without this extra.

## Pins and licenses

The provenance and resolved dependencies are recorded in [the model lock](../../integrations/models.lock.json):

| Artifact | Repository | Revision | License |
| --- | --- | --- | --- |
| Source code | [mistralai/timestral](https://github.com/mistralai/timestral) | `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff` | Apache-2.0 |
| Model weights | [mistralai/Timestral-28M](https://huggingface.co/mistralai/Timestral-28M) | `49b26409ac87b5935539a5d8ffe7f397b720db47` | Modified MIT |

The code and weights have separate licenses. The [pinned weights license](https://huggingface.co/mistralai/Timestral-28M/blob/49b26409ac87b5935539a5d8ffe7f397b720db47/LICENSE) requires a separate license for global consolidated monthly revenue **above USD 20 million**. The owner authorized local personal evaluation; each downstream user or deployment must assess its own use under the weights license. Installing the optional dependency alone does not authorize weight execution.

The adapter checks the installed source commit before model loading and retains checkpoint, weights revision, and code revision in its results. It exposes point forecasts and marginal quantiles; it does not supply joint paths.

The optional deployment requires `FORECAST_ANYTHING_TIMESTRAL_ENABLED=1`, `FORECAST_ANYTHING_TIMESTRAL_CHECKPOINT`, `FORECAST_ANYTHING_TIMESTRAL_REVISION` and `FORECAST_ANYTHING_TIMESTRAL_CODE_REVISION`. Registration reads capabilities but does not import PyTorch or download weights. The `compose.timestral.yaml` overlay uses pinned values from `integrations/models.lock.json` and installs the optional library code; the first run whose graph explicitly selects Timestral attempts the weight download.

## Real parity and benchmark evidence

[The real parity test](../../tests/model/test_timestral_parity.py) is guarded by `FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED`. Without approval, the following command reports a skipped test, **not a passed acceptance gate**:

```sh
uv run --locked --extra timestral --extra dev pytest tests/model/test_timestral_parity.py -q -rs
```

The owner-approved local run passed against the pinned official API on macOS arm64, Python 3.14, CPU fp32. It verified source and model revisions before weight download, compared medians and every marginal quantile at absolute and relative tolerances of `1e-5`, and recorded cold/warm latency and peak process memory. The measured cross-domain benchmark is archived in [`timestral-benchmark.json`](../research/timestral-benchmark.json): Timestral relative MAE was 0.896 on activity, 0.793 on energy, and 1.043 on retail, over the same 130, 230, and 37 final origins respectively. Values below 1 favor Timestral; these results describe this pinned evaluation and do not establish general superiority.
