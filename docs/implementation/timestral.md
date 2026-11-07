# Required local Timestral provider

The library adapter is implemented and **real CPU fp32 parity passed** against the pinned official implementation. The project owner authorized one local personal evaluation of the weights for this open-source project; that authorization applies to this evaluation only and does not resolve the license for other users or deployments. The product CLI/API/worker now require pinned Timestral for primary forecasts. Seasonal-naive remains the independent reference. No remote inference API key is required.

## Install and prepare the model

From the repository root:

```sh
uv sync --locked --extra dev --extra mcp
uv run --locked --extra mcp forecast-anything model status
uv run --locked --extra mcp forecast-anything model prepare
```

The normal package includes the pinned model code and PyTorch dependencies. Weights remain separate and are never bundled in the wheel. `model prepare` explicitly fetches missing pinned artifacts into the Hugging Face cache and verifies CPU loading. Inference requires that prepared local cache and uses `local_files_only=True`; it never silently downloads weights or falls back to the seasonal reference. Metadata/cache checks do not import Torch or model code. The legacy `timestral` installation extra remains a compatibility alias, not an opt-in product mode.

## Pins and licenses

The provenance and resolved dependencies are recorded in [the model lock](../../integrations/models.lock.json):

| Artifact | Repository | Revision | License |
| --- | --- | --- | --- |
| Source code | [mistralai/timestral](https://github.com/mistralai/timestral) | `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff` | Apache-2.0 |
| Model weights | [mistralai/Timestral-28M](https://huggingface.co/mistralai/Timestral-28M) | `49b26409ac87b5935539a5d8ffe7f397b720db47` | Modified MIT |

The code and weights have separate licenses. The [pinned weights license](https://huggingface.co/mistralai/Timestral-28M/blob/49b26409ac87b5935539a5d8ffe7f397b720db47/LICENSE) requires a separate license for global consolidated monthly revenue **above USD 20 million**. The owner authorized local personal evaluation; each downstream user or deployment must assess its own use under the weights license. Installing the optional dependency alone does not authorize weight execution.

The adapter checks the installed source commit before model loading and retains checkpoint, weights revision, and code revision in its results. It exposes point forecasts and marginal quantiles; it does not supply joint paths.

Pinned configuration is packaged with the code. Legacy environment aliases are accepted only when equal to the exact packaged pins; disabling Timestral or pointing at another revision is rejected. Compose core and worker share the same model cache. Before starting the forecasting workflow, run `docker compose ... run --rm core model prepare` after building the images. The old Timestral overlay is a compatible alias; the default product images already include the model dependency.

`model status` reports `cached` separately from `loaded`: cache presence alone does not prove inference succeeds. The public health/worker heartbeat reports process liveness; authenticated capabilities include model status inspected in the API process. A worker's loaded instance is distinct from the API's metadata-only instance.

## Real parity and benchmark evidence

[The real parity test](../../tests/model/test_timestral_parity.py) is guarded by `FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED`. Without approval, the following command reports a skipped test, **not a passed acceptance gate**:

```sh
uv run --locked --extra timestral --extra dev pytest tests/model/test_timestral_parity.py -q -rs
```

The owner-approved local run passed against the pinned official API on macOS arm64, Python 3.14, CPU fp32. It verified source and model revisions before weight download, compared medians and every marginal quantile at absolute and relative tolerances of `1e-5`, and recorded cold/warm latency and peak process memory. The measured cross-domain benchmark is archived in [`timestral-benchmark/report.json`](../research/timestral-benchmark/report.json), with its [environment](../research/timestral-benchmark/environment.json) and [assumptions](../research/timestral-benchmark/assumptions.json): Timestral relative MAE was 0.896 on activity, 0.793 on energy, and 1.043 on retail, over the same 130, 230, and 37 final origins respectively. Values below 1 favor Timestral; these results describe this pinned evaluation and do not establish general superiority.

## Required-product acceptance

[Current acceptance](../research/required-timestral-acceptance.md) records a genuine candidate-bound model backtest, foreground product services, real MCP reconnect, automatic source refresh and stored change explanation. An insufficient/losing backtest remains provisional/rejected even though Timestral is required; model selection never certifies forecast quality. Legacy `timestral_acceptance_pending` logic applies to the old evaluation-attestation path; the supported candidate-bound backtest uses its own preserved final-evidence safeguards.
