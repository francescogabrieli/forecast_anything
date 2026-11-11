# Assistant interface and local runtime

## Context

People should be able to ask a forecasting question in an assistant they already use and find the same question and evidence after reconnecting. Forecasting and recurring source checks need access to the configured workspace even when the assistant is closed.

## Decision

Use MCP as the primary assistant interface. The local API, worker and ledger own forecasting, scheduling and durable results. The site introduces the product and guides setup. Contextual views and the optional console let users inspect a stored result.

## Consequences

The worker can complete accepted jobs while the assistant is disconnected, provided the local service and machine are running. MCP clients can recover stored records and replay supported requests with the same idempotency key. Embedded views depend on host support. Text and browser links provide access to results across hosts. See the [discovery runtime decision](agent-runtime.md) for the boundary with external integrations.

See the [MCP guide](../implementation/mcp.md) and [capability matrix](../capabilities.md).
