# Forecast Anything roadmap

Forecast Anything helps people forecast a time series from their assistant, save the question, and compare the forecast with later observations. The primary interface is MCP. The optional console provides detailed views of forecasts, inputs and evidence.

## Product priorities

1. **Make the operational CSV workflow easy to complete.** Start with a regularly sampled metric such as daily orders. Help users check the source mapping, issue a short-horizon forecast, compare it with a seasonal baseline and return to the saved question.
2. **Make results easy to verify.** Show when each observation became available, the data used for each run and what happened after new observations arrived. Keep historical backtests and evaluation of issued forecasts easy to distinguish.
3. **Validate the workflow with new users.** Observe installation, the first forecast, reconnection and follow-up. Use those results to prioritize improvements to setup, error messages and documentation.
4. **Improve distribution for supported environments.** Test installation from clean artifacts, make compatibility limits explicit and keep model weights separate from the code distribution.

The optional console and scenarios are maintained while the primary workflow is being validated. Autonomous discovery is deferred. New model or source support should come with documented input requirements and comparable evaluation evidence.

## Documentation

- [Quickstart](quickstart.md) and [local installation](installation.md)
- [MCP tools and workflows](implementation/mcp.md)
- [Capabilities and tested environments](capabilities.md)
- [Quality roadmap](quality-roadmap.md)
- [Assistant interface decision](decisions/assistant-interface.md) and [discovery runtime decision](decisions/agent-runtime.md)

- [Phase 0 measurement benchmark](../benchmarks/README.md)
