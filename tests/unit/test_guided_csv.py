"""Guided previews enforce bounded, no-symlink CSV reads."""

from datetime import datetime, timezone

import pytest

from forecast_anything.contracts import DomainError, SourceSpec
from forecast_anything.sources import profiling


def spec(path):
    return SourceSpec(
        source_id="sales", kind="csv", location=str(path), refresh_seconds=60
    )


def test_guided_preview_rejects_oversized_content(tmp_path, monkeypatch):
    path = tmp_path / "source.csv"
    path.write_text("date,value\n2026-01-01,1\n")
    monkeypatch.setattr(profiling, "_MAX_GUIDED_CSV_BYTES", 8, raising=False)
    with pytest.raises(DomainError, match="source_too_large"):
        profiling.preview_csv(spec(path), datetime.now(timezone.utc))


def test_guided_preview_refuses_symlink_replacement(tmp_path):
    target = tmp_path / "target.csv"
    target.write_text("date,value\n2026-01-01,1\n")
    link = tmp_path / "source.csv"
    link.symlink_to(target)
    with pytest.raises(DomainError, match="source_unavailable"):
        profiling.preview_csv(spec(link), datetime.now(timezone.utc))


def test_guided_capture_rejects_excess_rows_before_materializing_all(
    tmp_path, monkeypatch
):
    path = tmp_path / "source.csv"
    path.write_text("date,value\n2026-01-01,1\n2026-01-02,2\n2026-01-03,3\n")
    source = spec(path)
    cutoff = datetime.now(timezone.utc)
    preview = profiling.preview_csv(source, cutoff)
    monkeypatch.setattr(profiling, "_MAX_GUIDED_CSV_ROWS", 2, raising=False)
    with pytest.raises(DomainError, match="source_row_limit"):
        profiling.capture_confirmed_csv(source, preview.proposal_version, cutoff)


def test_guided_adapter_refuses_symlink_paths_to_keep_replay_identity(tmp_path):
    from forecast_anything.mcp_adapter.config import McpConfig, McpConfigError

    target = tmp_path / "target.csv"
    target.write_text("date,value\n2026-01-01,1\n")
    link = tmp_path / "source.csv"
    link.symlink_to(target)
    config = McpConfig(workspace_token="token", csv_roots=(tmp_path,))
    with pytest.raises(McpConfigError, match="source_forbidden"):
        config.validate_guided_csv(spec(link))


def test_guided_preview_refuses_symlink_parent_replacement(tmp_path):
    target = tmp_path / "outside"
    target.mkdir()
    (target / "source.csv").write_text("date,value\n2026-01-01,1\n")
    link = tmp_path / "replaced-directory"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(DomainError, match="source_unavailable"):
        profiling.preview_csv(spec(link / "source.csv"), datetime.now(timezone.utc))
