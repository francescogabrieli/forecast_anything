"""Comparable forecast changes and watch question semantics."""

from datetime import timedelta

import pytest
from watch_fixtures import NOW, run, watch

from forecast_anything.contracts import (
    DomainError,
)
from forecast_anything.watches import (
    summarize_change,
    summarize_watch_change,
)


def test_change_summary_separates_window_advance_from_common_target_changes():
    previous = run("old", (1, 2), ((10, 20),))
    current = run("new", (2, 3), ((23, 30),))
    summary = summarize_change(previous, current)
    assert summary["changes"] == [
        {
            "node_id": "question",
            "series_id": "sales",
            "timestamp": (NOW + timedelta(days=2)).isoformat(),
            "representation": "point",
            "previous": 20.0,
            "current": 23.0,
            "delta": 3.0,
            "unit": "count",
        }
    ]
    assert summary["added_targets"] == [
        {
            "node_id": "question",
            "series_id": "sales",
            "timestamp": (NOW + timedelta(days=3)).isoformat(),
        }
    ]
    assert summary["removed_targets"] == [
        {
            "node_id": "question",
            "series_id": "sales",
            "timestamp": (NOW + timedelta(days=1)).isoformat(),
        }
    ]
    assert summary["new_snapshot_ids"] == ["snapshot-new"]


def test_window_advance_alone_is_not_forecast_change():
    summary = summarize_change(
        run("a", (1, 2), ((10, 20),)), run("b", (2, 3), ((20, 30),))
    )
    assert summary["changes"] == []
    assert summary["added_targets"]


def test_change_summary_matches_series_identity_instead_of_row_position():
    a = run("a", (1,), ((10,), (50,)), series=("sales", "cost"), units=("count", "EUR"))
    b = run("b", (1,), ((55,), (10,)), series=("cost", "sales"), units=("EUR", "count"))
    summary = summarize_change(a, b)
    assert len(summary["changes"]) == 1
    assert summary["changes"][0]["series_id"] == "cost"
    assert summary["changes"][0]["delta"] == 5


def test_change_summary_compares_common_quantiles_without_pairing_joint_samples():
    before = run("a", (1,), ((10,),))
    after = run("b", (1,), ((10,),))
    before.results["question"] = before.results["question"].model_copy(
        update={
            "quantiles": {"0.5": ((10,),), "0.9": ((20,),)},
            "paths": (((1,),),),
            "sample_group_id": "old-samples",
        }
    )
    after.results["question"] = after.results["question"].model_copy(
        update={
            "quantiles": {"0.5": ((12,),), "0.95": ((30,),)},
            "paths": (((100,),),),
            "sample_group_id": "new-samples",
        }
    )
    summary = summarize_change(before, after)
    assert len(summary["changes"]) == 1
    assert summary["changes"][0]["representation"] == "quantile:0.5"
    assert summary["changes"][0]["delta"] == 2


def test_ambiguous_target_identity_is_rejected():
    with pytest.raises(DomainError, match="ambiguous_forecast_identity"):
        summarize_change(run("a", (1, 1), ((10, 10),)), run("b", (1,), ((11,),)))


@pytest.mark.parametrize(
    "changes",
    [
        {"graph_id": "other"},
        {"graph_version": 2},
        {"scenario_id": "scenario"},
        {"state": "failed"},
    ],
)
def test_incomparable_runs_are_rejected(changes):
    with pytest.raises(DomainError, match="incomparable_runs"):
        summarize_change(run("a", (1,), ((10,),)), run("b", (1,), ((11,),), **changes))


def test_incompatible_units_and_unshared_series_are_not_subtracted():
    summary = summarize_change(
        run("a", (1,), ((10,),)), run("b", (1,), ((11,),), units=("EUR",))
    )
    assert summary["changes"] == []
    assert summary["incomparable"]
    summary = summarize_change(
        run("a", (1,), ((10,),)), run("b", (1,), ((11,),), series=("other",))
    )
    assert summary["changes"] == []
    assert summary["added_targets"] == []


@pytest.mark.parametrize("template", ["forecast_change", "expected_deviation"])
def test_watch_change_summary_retains_question_semantics(template):
    w = watch(template)
    summary = summarize_watch_change(
        w, run("a", (1,), ((10,),)), run("b", (1,), ((11,),))
    )
    assert summary["template_id"] == template
    assert summary["question"] == "Review sales"
    assert summary["candidate_id"] == w.candidate_id
    assert "causal" in summary["explanation"]
