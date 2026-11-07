"""Product-only forecasting requirements; the generic library remains injectable."""

from .contracts import DomainError, GraphSpec


def validate_primary_provider(
    graph: GraphSpec, required_provider: str | None, primary_node_id: str | None = None
) -> str | None:
    if required_provider is None:
        return primary_node_id
    nodes = {node.node_id: node for node in graph.nodes}
    consumed = {name for node in graph.nodes for name in node.inputs}
    terminals = set(nodes) - consumed
    if primary_node_id is None:
        if "question" in terminals:
            primary_node_id = "question"
        else:
            conventional = terminals.intersection({"model", "forecast"})
            if len(conventional) == 1:
                primary_node_id = conventional.pop()
            elif not conventional and len(terminals) == 1:
                primary_node_id = next(iter(terminals))
            else:
                raise DomainError("ambiguous_primary_output", {})
    if primary_node_id not in terminals:
        raise DomainError("invalid_primary_output", {"node_id": primary_node_id})
    seen, pending = set(), [primary_node_id]
    found_required = False
    while pending:
        name = pending.pop()
        if name in seen or name not in nodes:
            continue
        seen.add(name)
        node = nodes[name]
        if node.kind == "forecast":
            if node.config.get("provider") != required_provider:
                raise DomainError(
                    "required_forecast_provider", {"provider": required_provider}
                )
            found_required = True
        pending.extend(node.inputs)
    if found_required:
        return primary_node_id
    raise DomainError("required_forecast_provider", {"provider": required_provider})


def ensure_required_model(runtime) -> None:
    required = runtime.required_provider
    if required is None:
        return
    provider = runtime.providers.get(required)
    if provider is None:
        raise DomainError("required_model_unavailable", {"provider": required})
    checker = getattr(provider, "check_model", None)
    if checker is not None:
        status = checker()
        if not status.get("cached") and not status.get("ready"):
            raise DomainError(
                "model_not_prepared",
                {"provider": required, "status": status.get("status")},
            )


def validate_selection(runtime, selection) -> None:
    if (
        runtime.required_provider is not None
        and selection.provider != runtime.required_provider
    ):
        raise DomainError(
            "required_forecast_provider", {"provider": runtime.required_provider}
        )
    ensure_required_model(runtime)


def model_readiness(runtime) -> dict:
    required = runtime.required_provider
    if required is None:
        return {"status": "not_required", "ready": False, "cached": False}
    provider = runtime.providers.get(required)
    if provider is None:
        return {"status": "unavailable", "ready": False, "cached": False}
    checker = getattr(provider, "check_model", None)
    if checker is None:
        return {"status": "unverified", "ready": False, "cached": False}
    return checker()


def provider_epoch_context(runtime) -> dict:
    if runtime.required_provider is None:
        return {}
    provider = runtime.providers.get(runtime.required_provider)
    return {
        "required_provider": runtime.required_provider,
        "provider_revision": provider.capabilities().provider_revision
        if provider
        else None,
    }
