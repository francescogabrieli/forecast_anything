"""Select a model on one partition and confirm it on an independent holdout."""

from ..contracts import (
    Capabilities,
    DomainError,
    ForecastSelection,
    ModelSelectionEvidence,
)
from .contracts import canonical_json
from .planning import _metadata
from .store import BacktestStore

MINIMUM_ORIGINS = 10


def choose_model(runtime, request, snapshot, source_revision, frequency):
    """Resolve one configured forecast using compatible, immutable reports."""
    if request.selection_report_id is None:
        if request.challenger_report_id is not None:
            raise DomainError("model_selection_report_required", {})
        return request.selection, None
    store = BacktestStore(runtime.ledger)
    default = request.selection
    if default.provider == "seasonal_naive":
        raise DomainError("model_selection_requires_comparison", {})
    metadata = _metadata(snapshot.observations)
    series_id, _ = metadata
    current = {(row.series_id, row.event_time): row for row in snapshot.observations}

    def load(report_id):
        report = store.get_report_by_id(report_id)
        if (
            report.source_id != request.source_id
            or report.source_revision != source_revision
            or report.captured_at > snapshot.as_of
            or report.frequency != frequency
            or report.selection.horizon != default.horizon
            or report.selection.baseline_period != default.baseline_period
        ):
            raise DomainError(
                "model_selection_report_mismatch", {"report_id": report_id}
            )
        actuals = runtime.ledger.get_snapshot(report.actuals_snapshot_id)
        if _metadata(actuals.observations) != metadata or any(
            current.get((row.series_id, row.event_time)) != row
            for row in actuals.observations
        ):
            raise DomainError(
                "model_selection_report_mismatch", {"report_id": report_id}
            )
        for name, contract in report.provider_contracts.items():
            provider = runtime.providers.get(name)
            if (
                provider is None
                or Capabilities.model_validate(provider.capabilities().model_dump())
                != contract
            ):
                raise DomainError("provider_contract_changed", {"provider_id": name})
        return report, actuals

    reference, actuals = load(request.selection_report_id)
    if canonical_json(reference.selection.model_dump(mode="json")) != canonical_json(
        default.model_dump(mode="json")
    ):
        raise DomainError(
            "model_selection_report_mismatch", {"report_id": reference.report_id}
        )

    reports = [reference]
    if request.challenger_report_id is not None:
        challenger, challenger_actuals = load(request.challenger_report_id)
        reference_plan = store.get_plan(reference.backtest_id)
        challenger_plan = store.get_plan(challenger.backtest_id)
        if (
            challenger.selection.provider in {default.provider, "seasonal_naive"}
            or challenger_actuals.observations != actuals.observations
            or challenger_plan.origins != reference_plan.origins
            or challenger_plan.archive.observations
            != reference_plan.archive.observations
        ):
            raise DomainError(
                "model_selection_report_mismatch", {"report_id": challenger.report_id}
            )
        reports.append(challenger)

    choices = {report.selection.provider: report.selection for report in reports}
    choices["seasonal_naive"] = ForecastSelection(
        provider="seasonal_naive",
        horizon=default.horizon,
        options={"period": default.baseline_period},
        baseline_period=default.baseline_period,
    )
    winner = default.provider
    reason = "default_retained"
    if all(
        score.evaluated == score.planned and score.evaluated >= MINIMUM_ORIGINS
        for report in reports
        for score in report.partitions[1:]
    ):
        selection_scores, final_scores = (
            {
                **{
                    report.selection.provider: report.partitions[index].model_mae
                    for report in reports
                },
                "seasonal_naive": reference.partitions[index].baseline_mae,
            }
            for index in (1, 2)
        )
        best = min(selection_scores, key=selection_scores.__getitem__)
        if all(
            selection_scores[best] < selection_scores[other]
            and final_scores[best] < final_scores[other]
            for other in choices
            if other != best
        ):
            winner = best
            reason = "confirmed_lower_mae"
    contract = next(
        report.provider_contracts[winner]
        for report in reports
        if winner in report.provider_contracts
    )
    return choices[winner], ModelSelectionEvidence(
        report_ids=tuple(report.report_id for report in reports),
        series_id=series_id,
        provider=winner,
        provider_revision=contract.provider_revision,
        reason=reason,
    )
