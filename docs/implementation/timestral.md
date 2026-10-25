# Optional Timestral provider

The library adapter is implemented, but provider acceptance remains pending: **real CPU fp32 parity has not run**. The user's clarification about applicability of the weights license is still required before downloading, loading, or executing weights. Unit tests and a skipped parity test do not satisfy this acceptance gate. The initial CLI continues to use the seasonal-naive provider.

## Install the optional dependency

From the repository root:

```sh
uv sync --locked --extra timestral --extra dev
```

This installs the pinned Timestral source package and its Python dependencies, including PyTorch. It does **not** download model weights. Weights are not included in this repository. After license applicability is resolved, an explicitly invoked forecast can download the pinned weights to the Hugging Face cache on its first model load. Importing the provider or reading its capabilities does not load Timestral or PyTorch; the core remains usable without this extra.

## Pins and licenses

The provenance and resolved dependencies are recorded in [the model lock](../../integrations/models.lock.json):

| Artifact | Repository | Revision | License |
| --- | --- | --- | --- |
| Source code | [mistralai/timestral](https://github.com/mistralai/timestral) | `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff` | Apache-2.0 |
| Model weights | [mistralai/Timestral-28M](https://huggingface.co/mistralai/Timestral-28M) | `49b26409ac87b5935539a5d8ffe7f397b720db47` | Modified MIT |

The code and weights have separate licenses. The [pinned weights license](https://huggingface.co/mistralai/Timestral-28M/blob/49b26409ac87b5935539a5d8ffe7f397b720db47/LICENSE) requires a separate license for global consolidated monthly revenue **above USD 20 million**. Applicability to the user's intended use remains unresolved; installing the optional dependency does not resolve that question or authorize weight execution.

The adapter checks the installed source commit before model loading and retains checkpoint, weights revision, and code revision in its results. It exposes point forecasts and marginal quantiles; it does not supply joint paths.

## Pending real parity gate

[The real parity test](../../tests/model/test_timestral_parity.py) remains guarded by `FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED`. Leave this approval unset until the user resolves the license question. Without approval, the following command reports a skipped test, **not a passed acceptance gate**:

```sh
uv run --locked --extra timestral --extra dev pytest tests/model/test_timestral_parity.py -q -rs
```

After explicit approval, the existing guarded test must actually run against the pinned official API. It verifies source and model revisions before weight download, compares CPU fp32 medians and every marginal quantile with absolute and relative tolerances of `1e-5`, and records machine, cold/warm latency, and peak process memory. Until that execution succeeds, real parity and provider acceptance remain open.
