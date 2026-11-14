# Required local Timestral provider

The library adapter is implemented and **real CPU fp32 parity passed** against the pinned official implementation. Model weight terms apply to each deployment. The product CLI, API and worker use pinned Timestral by default. Configured forecasts can [choose a provider using backtest evidence](mcp.md#choose-a-provider-using-backtest-evidence). No remote inference API key is required.

## Install and prepare the model

From the repository root:

```sh
uv sync --locked --extra dev --extra mcp
uv run --locked --extra mcp forecast-anything model status
uv run --locked --extra mcp forecast-anything model prepare
```

The base package provides the forecasting runtime and seasonal baseline. Run `forecast-anything model prepare` in the installed CLI environment to install the pinned Timestral inference package and its dependencies, fetch missing weights into the Hugging Face cache, and verify CPU loading. The command uses uv when available and the same interpreter's pip otherwise. The optional `timestral` extra installs numerical dependencies from the package index. Source checkouts and the container build use the Git pin from the locked development dependency group.

Inference reads the prepared model with `local_files_only=True`. `model status` reports installed provenance and cache state without importing Torch or installing anything. The wheel and source distribution keep the pinned code and weights external.

## Pins and licenses

The provenance and resolved dependencies are recorded in [the model lock](../../integrations/models.lock.json):

| Artifact | Repository | Revision | License |
| --- | --- | --- | --- |
| Source code | [mistralai/timestral](https://github.com/mistralai/timestral) | `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff` | Apache-2.0 |
| Model weights | [mistralai/Timestral-28M](https://huggingface.co/mistralai/Timestral-28M) | `49b26409ac87b5935539a5d8ffe7f397b720db47` | Modified MIT |

The code and weights have separate licenses. The [pinned weights license](https://huggingface.co/mistralai/Timestral-28M/blob/49b26409ac87b5935539a5d8ffe7f397b720db47/LICENSE) requires a separate license for global consolidated monthly revenue **above USD 20 million**. Each user or deployment must assess its use under the weights license. Installing the optional dependency alone does not authorize weight execution.

The adapter checks the installed source commit before model loading and retains checkpoint, weights revision, and code revision in its results. It exposes point forecasts and marginal quantiles; it does not supply joint paths.

Pinned configuration is packaged with the code. Workspaces can select 28M or 123M at creation. See [checkpoint setup](../installation.md#choose-a-timestral-checkpoint). For CLI processes without a workspace configuration, `FORECAST_ANYTHING_TIMESTRAL_MODEL=123m` selects the packaged 123M pin. Legacy environment aliases must match the selected packaged pins. Compose core and worker share the same model cache. Before starting the forecasting workflow, run `docker compose ... run --rm core model prepare` after building the images. The old Timestral overlay is a compatible alias; the default product images already include the model dependency.

`model status` reports `cached` separately from `loaded`: cache presence alone does not prove inference succeeds. The public health/worker heartbeat reports process liveness; authenticated capabilities include model status inspected in the API process. A worker's loaded instance is distinct from the API's metadata-only instance.

## Real parity and benchmark evidence

[The real parity test](../../tests/model/test_timestral_parity.py) is guarded by `FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED`. Without approval, the following command reports a skipped test, **not a passed acceptance gate**:

```sh
uv run --locked --extra timestral --extra dev pytest tests/model/test_timestral_parity.py -q -rs
```

The local parity check passed against the pinned official API on macOS arm64, Python 3.14, CPU fp32. It verified source and model revisions before weight download, compared medians and every marginal quantile at absolute and relative tolerances of `1e-5`, and recorded cold/warm latency and peak process memory. The measured cross-domain benchmark is archived in [`timestral-benchmark/report.json`](../research/timestral-benchmark/report.json), with its [environment](../research/timestral-benchmark/environment.json) and [assumptions](../research/timestral-benchmark/assumptions.json): Timestral relative MAE was 0.896 on activity, 0.793 on energy, and 1.043 on retail, over the same 130, 230, and 37 final origins respectively. Values below 1 favor Timestral; these results describe this pinned evaluation and do not establish general superiority.

## Required-product acceptance

See the [capability matrix](../capabilities.md) for verified Timestral workflows and their limits. An insufficient/losing backtest remains provisional/rejected even though Timestral is required; model selection never certifies forecast quality. Legacy `timestral_acceptance_pending` logic applies to the old evaluation-attestation path; the supported candidate-bound backtest uses its own preserved final-evidence safeguards.

## Phase 0 benchmark

The [Phase 0 runner](../../benchmarks/README.md) compares the pinned 28M and 123M checkpoints on development and validation with separate local approval gates. The final holdout remains reserved.
