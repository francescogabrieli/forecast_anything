import type { RunRecord, SourceProfile, Watch } from "../api/schema.generated";

export function makeProfile(overrides: Partial<SourceProfile> = {}): SourceProfile {
  return {
    source_id: "sales",
    source_revision: "revision-1",
    fields: {
      time: { data_type: "datetime", nullable: false },
      value: { data_type: "number", nullable: false },
    },
    proposed_mapping: {
      event_time: "time",
      value: "value",
      available_at: { constant: "2026-10-23" },
      revision: { constant: "1" },
      series_id: { constant: "sales" },
      unit: { constant: "count" },
      frequency: { constant: "1d" },
      timezone: { constant: "UTC" },
      calendar: { constant: "gregorian" },
      missing_values: { constant: [""] },
    },
    unresolved: [],
    assumptions: ["Field types describe a sample of at most 100 rows."],
    sample_rows: [{ time: "2026-10-23", value: 3 }],
    ...overrides,
  };
}

export function makeRun(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    run_id: "run-1",
    graph_id: "graph-1",
    graph_version: 1,
    as_of: "2026-10-24T00:00:00Z",
    snapshot_ids: ["snapshot-1"],
    requested_provider: { forecast: "seasonal_naive" },
    actual_provider: { forecast: "seasonal_naive" },
    state: "completed",
    results: {
      forecast: {
        provider_id: "seasonal_naive",
        provider_revision: "test-revision",
        series_ids: ["sales"],
        timestamps: ["2026-10-25T00:00:00Z", "2026-10-26T00:00:00Z"],
        units: ["count"],
        point: [[1, 2]],
        quantiles: null,
        paths: null,
        sample_group_id: null,
        assumptions: [],
      },
    },
    evidence_ids: [],
    scenario_id: null,
    parent_run_id: null,
    ...overrides,
  };
}

export function makeWatch(overrides: Partial<Watch> = {}): Watch {
  return {
    watch_id: "watch-1",
    candidate_id: "candidate-1",
    lifecycle: "active",
    quality: "usable",
    graph_id: "graph-1",
    graph_version: 1,
    policy_version: "discovery-v1",
    next_due_at: "2026-10-25T00:00:00Z",
    muted: false,
    priority: 3,
    ...overrides,
  };
}
