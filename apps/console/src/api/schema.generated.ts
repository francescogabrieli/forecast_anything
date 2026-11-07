// Generated from src/api/schemas.json. Run npm run generate:types.

export namespace ForecastSelectionGenerated {
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;

  export interface ForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
}
export type ForecastSelection = ForecastSelectionGenerated.ForecastSelection;

export namespace BacktestSettingsGenerated {
  export type MaxOriginsPerPartition = number;
  export type OriginOffsetSeconds = number;

  export interface BacktestSettings {
    max_origins_per_partition?: MaxOriginsPerPartition;
    origin_offset_seconds?: OriginOffsetSeconds;
  }
}
export type BacktestSettings = BacktestSettingsGenerated.BacktestSettings;

export namespace BacktestReportGenerated {
  export type ActualsSnapshotId = string;
  export type ArchiveId = string;
  export type Assumptions = string[];
  export type BacktestId = string;
  export type CapturedAt = string;
  export type Frequency = string;
  export type BaselineMae = number | null;
  export type Evaluated = number;
  export type Excluded = number;
  export type Failed = number;
  export type Insufficient = number;
  export type MatchedCount = number;
  export type ModelMae = number | null;
  export type Partition = "exploration" | "selection" | "final";
  export type Planned = number;
  export type RelativeMae = number | null;
  export type RelativeMaeReason = ("no_matched_cells" | "zero_baseline_mae" | "ratio_unrepresentable") | null;
  export type Partitions = PartitionScore[];
  export type PlanId = string;
  export type ProtocolVersion = "backtest-v1";
  export type ProviderId = string;
  export type ProviderRevision = string;
  export type Representations = ("point" | "marginal_quantiles" | "joint_paths")[];
  export type SupportsKnownFuture = boolean;
  export type ReportId = string;
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  export type MaxOriginsPerPartition = number;
  export type OriginOffsetSeconds = number;
  export type SourceId = string;
  export type SourceRevision = string;
  export type Status = "completed" | "insufficient_evidence";

  export interface BacktestReport {
    actuals_snapshot_id: ActualsSnapshotId;
    archive_id: ArchiveId;
    assumptions?: Assumptions;
    backtest_id: BacktestId;
    captured_at: CapturedAt;
    frequency: Frequency;
    partitions: Partitions;
    plan_id: PlanId;
    protocol_version?: ProtocolVersion;
    provider_contracts: ProviderContracts;
    report_id?: ReportId;
    selection: ForecastSelection;
    settings: BacktestSettings;
    source_id: SourceId;
    source_revision: SourceRevision;
    status: Status;
  }
  export interface PartitionScore {
    baseline_mae?: BaselineMae;
    evaluated?: Evaluated;
    excluded?: Excluded;
    failed?: Failed;
    insufficient?: Insufficient;
    matched_count?: MatchedCount;
    model_mae?: ModelMae;
    partition: Partition;
    planned: Planned;
    relative_mae?: RelativeMae;
    relative_mae_reason?: RelativeMaeReason;
  }
  export interface ProviderContracts {
    [k: string]: Capabilities;
  }
  export interface Capabilities {
    provider_id: ProviderId;
    provider_revision: ProviderRevision;
    representations: Representations;
    supports_known_future: SupportsKnownFuture;
  }
  export interface ForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
  export interface BacktestSettings {
    max_origins_per_partition?: MaxOriginsPerPartition;
    origin_offset_seconds?: OriginOffsetSeconds;
  }
}
export type BacktestReport = BacktestReportGenerated.BacktestReport;

export namespace OriginOutcomeGenerated {
  export type BacktestId = string;
  export type BaselineMae = number | null;
  export type EvaluationId = string | null;
  export type IssuanceTime = string;
  export type MatchedCount = number;
  export type ModelMae = number | null;
  export type NominalOrigin = string;
  export type Ordinal = number;
  export type Partition = "exploration" | "selection" | "final";
  export type PlanId = string;
  export type ReasonCode = string | null;
  export type RunId = string | null;
  export type Status = "evaluated" | "excluded" | "failed" | "insufficient_evidence";
  export type TargetEnd = string;
  export type TargetStart = string;

  export interface OriginOutcome {
    backtest_id: BacktestId;
    baseline_mae?: BaselineMae;
    evaluation_id?: EvaluationId;
    issuance_time: IssuanceTime;
    matched_count?: MatchedCount;
    model_mae?: ModelMae;
    nominal_origin: NominalOrigin;
    ordinal: Ordinal;
    partition: Partition;
    plan_id: PlanId;
    reason_code?: ReasonCode;
    run_id?: RunId;
    status: Status;
    target_end: TargetEnd;
    target_start: TargetStart;
  }
}
export type OriginOutcome = OriginOutcomeGenerated.OriginOutcome;

export namespace OriginPageGenerated {
  export type BacktestId = string;
  export type Limit = number;
  export type NextOffset = number | null;
  export type Offset = number;
  export type BacktestId1 = string;
  export type BaselineMae = number | null;
  export type EvaluationId = string | null;
  export type IssuanceTime = string;
  export type MatchedCount = number;
  export type ModelMae = number | null;
  export type NominalOrigin = string;
  export type Ordinal = number;
  export type Partition = "exploration" | "selection" | "final";
  export type PlanId = string;
  export type ReasonCode = string | null;
  export type RunId = string | null;
  export type Status = "evaluated" | "excluded" | "failed" | "insufficient_evidence";
  export type TargetEnd = string;
  export type TargetStart = string;
  /**
   * @maxItems 50
   */
  export type Origins = OriginOutcome[];

  export interface OriginPage {
    backtest_id: BacktestId;
    limit: Limit;
    next_offset?: NextOffset;
    offset: Offset;
    origins: Origins;
  }
  export interface OriginOutcome {
    backtest_id: BacktestId1;
    baseline_mae?: BaselineMae;
    evaluation_id?: EvaluationId;
    issuance_time: IssuanceTime;
    matched_count?: MatchedCount;
    model_mae?: ModelMae;
    nominal_origin: NominalOrigin;
    ordinal: Ordinal;
    partition: Partition;
    plan_id: PlanId;
    reason_code?: ReasonCode;
    run_id?: RunId;
    status: Status;
    target_end: TargetEnd;
    target_start: TargetStart;
  }
}
export type OriginPage = OriginPageGenerated.OriginPage;

export namespace PartitionScoreGenerated {
  export type BaselineMae = number | null;
  export type Evaluated = number;
  export type Excluded = number;
  export type Failed = number;
  export type Insufficient = number;
  export type MatchedCount = number;
  export type ModelMae = number | null;
  export type Partition = "exploration" | "selection" | "final";
  export type Planned = number;
  export type RelativeMae = number | null;
  export type RelativeMaeReason = ("no_matched_cells" | "zero_baseline_mae" | "ratio_unrepresentable") | null;

  export interface PartitionScore {
    baseline_mae?: BaselineMae;
    evaluated?: Evaluated;
    excluded?: Excluded;
    failed?: Failed;
    insufficient?: Insufficient;
    matched_count?: MatchedCount;
    model_mae?: ModelMae;
    partition: Partition;
    planned: Planned;
    relative_mae?: RelativeMae;
    relative_mae_reason?: RelativeMaeReason;
  }
}
export type PartitionScore = PartitionScoreGenerated.PartitionScore;

export namespace SourceFieldGenerated {
  export type DataType = "string" | "integer" | "number" | "boolean" | "datetime" | "null" | "mixed";
  export type Nullable = boolean;

  export interface SourceField {
    data_type: DataType;
    nullable: Nullable;
  }
}
export type SourceField = SourceFieldGenerated.SourceField;

export namespace SourceProfileGenerated {
  export type Assumptions = string[];
  export type DataType = "string" | "integer" | "number" | "boolean" | "datetime" | "null" | "mixed";
  export type Nullable = boolean;
  export type JsonValue = unknown;
  /**
   * @maxItems 100
   */
  export type SampleRows = {
    [k: string]: string | boolean | number | null;
  }[];
  export type SourceId = string;
  export type SourceRevision = string | null;
  export type Unresolved = string[];

  /**
   * Sanitized agent-facing view, bounded independently of source size.
   */
  export interface SourceProfile {
    assumptions: Assumptions;
    fields: Fields;
    proposed_mapping: ProposedMapping;
    sample_rows?: SampleRows;
    source_id: SourceId;
    source_revision?: SourceRevision;
    unresolved: Unresolved;
  }
  export interface Fields {
    [k: string]: SourceField;
  }
  export interface SourceField {
    data_type: DataType;
    nullable: Nullable;
  }
  export interface ProposedMapping {
    [k: string]: JsonValue;
  }
}
export type SourceProfile = SourceProfileGenerated.SourceProfile;

export namespace SourceSpecGenerated {
  export type Kind = "csv" | "http_json";
  export type Location = string;
  export type JsonValue = unknown;
  export type RefreshSeconds = number;
  export type SecretRef = string | null;
  export type SourceId = string;

  /**
   * Registered source configuration. Mapping is explicit; see profiling module.
   *
   * secret_ref names a source-scoped injected credential, never a literal token.
   * Locations and secret references must not be passed to agents or logs.
   */
  export interface SourceSpec {
    kind: Kind;
    location: Location;
    mapping?: Mapping;
    refresh_seconds: RefreshSeconds;
    secret_ref?: SecretRef;
    source_id: SourceId;
  }
  export interface Mapping {
    [k: string]: JsonValue;
  }
}
export type SourceSpec = SourceSpecGenerated.SourceSpec;

export namespace SourceViewGenerated {
  export type Kind = "csv" | "http_json";
  export type RefreshSeconds = number;
  export type Revision = string;
  export type SourceId = string;

  export interface SourceView {
    kind: Kind;
    refresh_seconds: RefreshSeconds;
    revision: Revision;
    source_id: SourceId;
  }
}
export type SourceView = SourceViewGenerated.SourceView;

export namespace SourceRegistrationGenerated {
  export type EpochId = string;
  export type JobId = string;
  export type Kind = "csv" | "http_json";
  export type Assumptions = string[];
  export type DataType = "string" | "integer" | "number" | "boolean" | "datetime" | "null" | "mixed";
  export type Nullable = boolean;
  export type JsonValue = unknown;
  /**
   * @maxItems 100
   */
  export type SampleRows = {
    [k: string]: string | boolean | number | null;
  }[];
  export type SourceId = string;
  export type SourceRevision = string | null;
  export type Unresolved = string[];
  export type RefreshSeconds = number;
  export type Revision = string;
  export type SourceId1 = string;

  export interface SourceRegistration {
    epoch_id: EpochId;
    job_id: JobId;
    kind: Kind;
    profile: SourceProfile;
    refresh_seconds: RefreshSeconds;
    revision: Revision;
    source_id: SourceId1;
  }
  /**
   * Sanitized agent-facing view, bounded independently of source size.
   */
  export interface SourceProfile {
    assumptions: Assumptions;
    fields: Fields;
    proposed_mapping: ProposedMapping;
    sample_rows?: SampleRows;
    source_id: SourceId;
    source_revision?: SourceRevision;
    unresolved: Unresolved;
  }
  export interface Fields {
    [k: string]: SourceField;
  }
  export interface SourceField {
    data_type: DataType;
    nullable: Nullable;
  }
  export interface ProposedMapping {
    [k: string]: JsonValue;
  }
}
export type SourceRegistration = SourceRegistrationGenerated.SourceRegistration;

export namespace ForecastResultGenerated {
  export type Assumptions = string[];
  export type Paths = number[][][] | null;
  export type Point = number[][] | null;
  export type ProviderId = string;
  export type ProviderRevision = string;
  export type Quantiles = {
    [k: string]: number[][];
  } | null;
  export type SampleGroupId = string | null;
  export type SeriesIds = string[];
  export type Timestamps = string[];
  export type Units = string[];

  export interface ForecastResult {
    assumptions: Assumptions;
    paths: Paths;
    point: Point;
    provider_id: ProviderId;
    provider_revision: ProviderRevision;
    quantiles: Quantiles;
    sample_group_id: SampleGroupId;
    series_ids: SeriesIds;
    timestamps: Timestamps;
    units: Units;
  }
}
export type ForecastResult = ForecastResultGenerated.ForecastResult;

export namespace RunRecordGenerated {
  export type AsOf = string;
  export type EvidenceIds = string[];
  export type GraphId = string;
  export type GraphVersion = number;
  export type ParentRunId = string | null;
  export type PrimaryNodeId = string | null;
  export type Assumptions = string[];
  export type Paths = number[][][] | null;
  export type Point = number[][] | null;
  export type ProviderId = string;
  export type ProviderRevision = string;
  export type Quantiles = {
    [k: string]: number[][];
  } | null;
  export type SampleGroupId = string | null;
  export type SeriesIds = string[];
  export type Timestamps = string[];
  export type Units = string[];
  export type RunId = string;
  export type ScenarioId = string | null;
  export type SnapshotIds = string[];
  export type State = string;

  export interface RunRecord {
    actual_provider: ActualProvider;
    as_of: AsOf;
    evidence_ids: EvidenceIds;
    graph_id: GraphId;
    graph_version: GraphVersion;
    parent_run_id: ParentRunId;
    primary_node_id?: PrimaryNodeId;
    requested_provider: RequestedProvider;
    results: Results;
    run_id: RunId;
    scenario_id: ScenarioId;
    snapshot_ids: SnapshotIds;
    state: State;
  }
  export interface ActualProvider {
    [k: string]: string;
  }
  export interface RequestedProvider {
    [k: string]: string;
  }
  export interface Results {
    [k: string]: ForecastResult;
  }
  export interface ForecastResult {
    assumptions: Assumptions;
    paths: Paths;
    point: Point;
    provider_id: ProviderId;
    provider_revision: ProviderRevision;
    quantiles: Quantiles;
    sample_group_id: SampleGroupId;
    series_ids: SeriesIds;
    timestamps: Timestamps;
    units: Units;
  }
}
export type RunRecord = RunRecordGenerated.RunRecord;

export namespace CandidateGenerated {
  export type CandidateId = string;
  export type EpochId = string;
  export type Basis = string;
  export type Status = "known" | "unavailable";
  export type Unit = "provider_calls_per_run";
  export type Value = number | null;
  export type Executable = boolean;
  export type GraphId = string;
  export type Inputs = string[];
  export type Kind = "source" | "forecast" | "transform" | "event";
  export type NodeId = string;
  export type Nodes = Node[];
  export type Version = number;
  export type Criterion = "mae" | "brier";
  export type ReferenceNodeId = string;
  export type SelectionMethod = "prespecified_holdout" | "exploratory" | "corrected";
  export type TargetNodeId = string;
  export type ProtocolId = string;
  export type Reason = string;
  export type SourceIds = string[];
  export type Assumptions = string[];
  export type DataType = "string" | "integer" | "number" | "boolean" | "datetime" | "null" | "mixed";
  export type Nullable = boolean;
  export type JsonValue = unknown;
  /**
   * @maxItems 100
   */
  export type SampleRows = {
    [k: string]: string | boolean | number | null;
  }[];
  export type SourceId = string;
  export type SourceRevision = string | null;
  export type Unresolved = string[];
  export type SourceProfiles = SourceProfile[];
  export type TemplateId = string;
  export type Unresolved1 = string[];

  export interface Candidate {
    candidate_id: CandidateId;
    epoch_id: EpochId;
    estimated_cost?: CandidateCostEstimate;
    executable?: Executable;
    graph: GraphSpec;
    protocol?: VerificationProtocol;
    protocol_id: ProtocolId;
    reason: Reason;
    source_ids: SourceIds;
    source_profiles?: SourceProfiles;
    template_id: TemplateId;
    unresolved?: Unresolved1;
  }
  /**
   * Static execution work, not a latency or monetary quote.
   *
   * Unknown/unsupported execution has no numeric value; zero is never a stand-in
   * for an unavailable estimate. The compiler owns the estimate and its basis.
   */
  export interface CandidateCostEstimate {
    basis?: Basis;
    status?: Status;
    unit?: Unit;
    value?: Value;
  }
  export interface GraphSpec {
    graph_id: GraphId;
    nodes: Nodes;
    version: Version;
  }
  export interface Node {
    config: Config;
    inputs: Inputs;
    kind: Kind;
    node_id: NodeId;
  }
  export interface Config {
    [k: string]: unknown;
  }
  /**
   * Frozen before final evaluation; no post-selection correction is assumed.
   */
  export interface VerificationProtocol {
    criterion?: Criterion;
    reference_node_id?: ReferenceNodeId;
    selection_method?: SelectionMethod;
    target_node_id?: TargetNodeId;
  }
  /**
   * Sanitized agent-facing view, bounded independently of source size.
   */
  export interface SourceProfile {
    assumptions: Assumptions;
    fields: Fields;
    proposed_mapping: ProposedMapping;
    sample_rows?: SampleRows;
    source_id: SourceId;
    source_revision?: SourceRevision;
    unresolved: Unresolved;
  }
  export interface Fields {
    [k: string]: SourceField;
  }
  export interface SourceField {
    data_type: DataType;
    nullable: Nullable;
  }
  export interface ProposedMapping {
    [k: string]: JsonValue;
  }
}
export type Candidate = CandidateGenerated.Candidate;

export namespace WatchGenerated {
  export type CandidateId = string;
  export type EpochId = string;
  export type Basis = string;
  export type Status = "known" | "unavailable";
  export type Unit = "provider_calls_per_run";
  export type Value = number | null;
  export type Executable = boolean;
  export type GraphId = string;
  export type Inputs = string[];
  export type Kind = "source" | "forecast" | "transform" | "event";
  export type NodeId = string;
  export type Nodes = Node[];
  export type Version = number;
  export type Criterion = "mae" | "brier";
  export type ReferenceNodeId = string;
  export type SelectionMethod = "prespecified_holdout" | "exploratory" | "corrected";
  export type TargetNodeId = string;
  export type ProtocolId = string;
  export type Reason = string;
  export type SourceIds = string[];
  export type Assumptions = string[];
  export type DataType = "string" | "integer" | "number" | "boolean" | "datetime" | "null" | "mixed";
  export type Nullable = boolean;
  export type JsonValue = unknown;
  /**
   * @maxItems 100
   */
  export type SampleRows = {
    [k: string]: string | boolean | number | null;
  }[];
  export type SourceId = string;
  export type SourceRevision = string | null;
  export type Unresolved = string[];
  export type SourceProfiles = SourceProfile[];
  export type TemplateId = string;
  export type Unresolved1 = string[];
  export type CandidateId1 = string;
  export type CandidateInvalidated = boolean;
  export type Action = "activate" | "provisional" | "reject";
  export type BacktestId = string | null;
  export type CandidateId2 = string | null;
  export type EpochId1 = string | null;
  export type EvaluationIds = string[];
  export type PolicyVersion = string;
  export type ProtocolId1 = string | null;
  export type ReasonCodes = string[];
  export type EvidenceApplicable = boolean;
  export type GraphId1 = string;
  export type GraphVersion = number;
  export type InvalidatedEvaluationIds = string[];
  export type Lifecycle = "candidate" | "evaluating" | "active" | "paused" | "unsupported";
  export type MigrationReason = string | null;
  export type Muted = boolean;
  export type NextDueAt = string;
  export type PolicyVersion1 = string;
  export type Priority = number;
  export type Quality = "provisional" | "usable" | "stale" | "degraded";
  export type ReevaluationRequired = boolean;
  export type SourceSnapshotIds = string[];
  export type SupersedesWatchId = string | null;
  export type WatchId = string;

  /**
   * Current relevance state; Candidate and decision retain their issued lineage.
   *
   * Evidence applicability is current metadata, independent of immutable scores.
   * A minimal watch can be displayed without lineage, but cannot be qualified.
   */
  export interface Watch {
    candidate?: Candidate | null;
    candidate_id: CandidateId1;
    candidate_invalidated?: CandidateInvalidated;
    eligibility_decision?: EligibilityDecision | null;
    evidence_applicable?: EvidenceApplicable;
    graph_id: GraphId1;
    graph_version: GraphVersion;
    invalidated_evaluation_ids?: InvalidatedEvaluationIds;
    lifecycle: Lifecycle;
    migration_reason?: MigrationReason;
    muted: Muted;
    next_due_at: NextDueAt;
    policy_version: PolicyVersion1;
    priority?: Priority;
    quality: Quality;
    reevaluation_required?: ReevaluationRequired;
    source_snapshot_ids?: SourceSnapshotIds;
    supersedes_watch_id?: SupersedesWatchId;
    watch_id: WatchId;
  }
  export interface Candidate {
    candidate_id: CandidateId;
    epoch_id: EpochId;
    estimated_cost?: CandidateCostEstimate;
    executable?: Executable;
    graph: GraphSpec;
    protocol?: VerificationProtocol;
    protocol_id: ProtocolId;
    reason: Reason;
    source_ids: SourceIds;
    source_profiles?: SourceProfiles;
    template_id: TemplateId;
    unresolved?: Unresolved1;
  }
  /**
   * Static execution work, not a latency or monetary quote.
   *
   * Unknown/unsupported execution has no numeric value; zero is never a stand-in
   * for an unavailable estimate. The compiler owns the estimate and its basis.
   */
  export interface CandidateCostEstimate {
    basis?: Basis;
    status?: Status;
    unit?: Unit;
    value?: Value;
  }
  export interface GraphSpec {
    graph_id: GraphId;
    nodes: Nodes;
    version: Version;
  }
  export interface Node {
    config: Config;
    inputs: Inputs;
    kind: Kind;
    node_id: NodeId;
  }
  export interface Config {
    [k: string]: unknown;
  }
  /**
   * Frozen before final evaluation; no post-selection correction is assumed.
   */
  export interface VerificationProtocol {
    criterion?: Criterion;
    reference_node_id?: ReferenceNodeId;
    selection_method?: SelectionMethod;
    target_node_id?: TargetNodeId;
  }
  /**
   * Sanitized agent-facing view, bounded independently of source size.
   */
  export interface SourceProfile {
    assumptions: Assumptions;
    fields: Fields;
    proposed_mapping: ProposedMapping;
    sample_rows?: SampleRows;
    source_id: SourceId;
    source_revision?: SourceRevision;
    unresolved: Unresolved;
  }
  export interface Fields {
    [k: string]: SourceField;
  }
  export interface SourceField {
    data_type: DataType;
    nullable: Nullable;
  }
  export interface ProposedMapping {
    [k: string]: JsonValue;
  }
  export interface EligibilityDecision {
    action: Action;
    backtest_id?: BacktestId;
    candidate_id?: CandidateId2;
    epoch_id?: EpochId1;
    evaluation_ids?: EvaluationIds;
    policy_version?: PolicyVersion;
    protocol_id?: ProtocolId1;
    reason_codes: ReasonCodes;
  }
}
export type Watch = WatchGenerated.Watch;

export namespace WatchViewGenerated {
  export type CandidateId = string;
  export type EpochId = string;
  export type Basis = string;
  export type Status = "known" | "unavailable";
  export type Unit = "provider_calls_per_run";
  export type Value = number | null;
  export type Executable = boolean;
  export type GraphId = string;
  export type Inputs = string[];
  export type Kind = "source" | "forecast" | "transform" | "event";
  export type NodeId = string;
  export type Nodes = Node[];
  export type Version = number;
  export type Criterion = "mae" | "brier";
  export type ReferenceNodeId = string;
  export type SelectionMethod = "prespecified_holdout" | "exploratory" | "corrected";
  export type TargetNodeId = string;
  export type ProtocolId = string;
  export type Reason = string;
  export type SourceIds = string[];
  export type Assumptions = string[];
  export type DataType = "string" | "integer" | "number" | "boolean" | "datetime" | "null" | "mixed";
  export type Nullable = boolean;
  export type JsonValue = unknown;
  /**
   * @maxItems 100
   */
  export type SampleRows = {
    [k: string]: string | boolean | number | null;
  }[];
  export type SourceId = string;
  export type SourceRevision = string | null;
  export type Unresolved = string[];
  export type SourceProfiles = SourceProfile[];
  export type TemplateId = string;
  export type Unresolved1 = string[];
  export type CandidateId1 = string;
  export type CandidateInvalidated = boolean;
  export type Action = "activate" | "provisional" | "reject";
  export type BacktestId = string | null;
  export type CandidateId2 = string | null;
  export type EpochId1 = string | null;
  export type EvaluationIds = string[];
  export type PolicyVersion = string;
  export type ProtocolId1 = string | null;
  export type ReasonCodes = string[];
  export type EvidenceApplicable = boolean;
  export type GraphId1 = string;
  export type GraphVersion = number;
  export type InvalidatedEvaluationIds = string[];
  export type Lifecycle = "candidate" | "evaluating" | "active" | "paused" | "unsupported";
  export type MigrationReason = string | null;
  export type Muted = boolean;
  export type NextDueAt = string;
  export type Operational = boolean;
  export type PolicyVersion1 = string;
  export type Priority = number;
  export type Quality = "provisional" | "usable" | "stale" | "degraded";
  export type ReevaluationRequired = boolean;
  export type SourceSnapshotIds = string[];
  export type SupersedesWatchId = string | null;
  export type WatchId = string;

  export interface WatchView {
    candidate?: Candidate | null;
    candidate_id: CandidateId1;
    candidate_invalidated?: CandidateInvalidated;
    eligibility_decision?: EligibilityDecision | null;
    evidence_applicable?: EvidenceApplicable;
    graph_id: GraphId1;
    graph_version: GraphVersion;
    invalidated_evaluation_ids?: InvalidatedEvaluationIds;
    lifecycle: Lifecycle;
    migration_reason?: MigrationReason;
    muted: Muted;
    next_due_at: NextDueAt;
    operational: Operational;
    policy_version: PolicyVersion1;
    priority?: Priority;
    quality: Quality;
    reevaluation_required?: ReevaluationRequired;
    source_snapshot_ids?: SourceSnapshotIds;
    supersedes_watch_id?: SupersedesWatchId;
    watch_id: WatchId;
  }
  export interface Candidate {
    candidate_id: CandidateId;
    epoch_id: EpochId;
    estimated_cost?: CandidateCostEstimate;
    executable?: Executable;
    graph: GraphSpec;
    protocol?: VerificationProtocol;
    protocol_id: ProtocolId;
    reason: Reason;
    source_ids: SourceIds;
    source_profiles?: SourceProfiles;
    template_id: TemplateId;
    unresolved?: Unresolved1;
  }
  /**
   * Static execution work, not a latency or monetary quote.
   *
   * Unknown/unsupported execution has no numeric value; zero is never a stand-in
   * for an unavailable estimate. The compiler owns the estimate and its basis.
   */
  export interface CandidateCostEstimate {
    basis?: Basis;
    status?: Status;
    unit?: Unit;
    value?: Value;
  }
  export interface GraphSpec {
    graph_id: GraphId;
    nodes: Nodes;
    version: Version;
  }
  export interface Node {
    config: Config;
    inputs: Inputs;
    kind: Kind;
    node_id: NodeId;
  }
  export interface Config {
    [k: string]: unknown;
  }
  /**
   * Frozen before final evaluation; no post-selection correction is assumed.
   */
  export interface VerificationProtocol {
    criterion?: Criterion;
    reference_node_id?: ReferenceNodeId;
    selection_method?: SelectionMethod;
    target_node_id?: TargetNodeId;
  }
  /**
   * Sanitized agent-facing view, bounded independently of source size.
   */
  export interface SourceProfile {
    assumptions: Assumptions;
    fields: Fields;
    proposed_mapping: ProposedMapping;
    sample_rows?: SampleRows;
    source_id: SourceId;
    source_revision?: SourceRevision;
    unresolved: Unresolved;
  }
  export interface Fields {
    [k: string]: SourceField;
  }
  export interface SourceField {
    data_type: DataType;
    nullable: Nullable;
  }
  export interface ProposedMapping {
    [k: string]: JsonValue;
  }
  export interface EligibilityDecision {
    action: Action;
    backtest_id?: BacktestId;
    candidate_id?: CandidateId2;
    epoch_id?: EpochId1;
    evaluation_ids?: EvaluationIds;
    policy_version?: PolicyVersion;
    protocol_id?: ProtocolId1;
    reason_codes: ReasonCodes;
  }
}
export type WatchView = WatchViewGenerated.WatchView;

export namespace EventRecordGenerated {
  export type Cursor = number;
  export type EventId = string;
  export type Kind = string;
  export type RunId = string;

  export interface EventRecord {
    cursor: Cursor;
    event_id: EventId;
    kind: Kind;
    payload: Payload;
    run_id: RunId;
  }
  export interface Payload {
    [k: string]: unknown;
  }
}
export type EventRecord = EventRecordGenerated.EventRecord;

export namespace EvaluationRecordGenerated {
  export type ActualsSnapshotId = string;
  export type Assumptions = string[];
  export type CandidateId = string;
  export type EpochId = string;
  export type OriginId = string;
  export type Partition = "exploration" | "selection" | "final";
  export type ProtocolId = string;
  export type SemanticValid = boolean;
  export type SourceSnapshotIds = string[];
  export type TargetEnd = string;
  export type TargetStart = string;
  export type TemporalValid = boolean;
  export type EvaluationId = string;
  export type OriginCount = number;
  export type RunId = string;
  export type Status = "pending" | "evaluated" | "insufficient_evidence";

  export interface EvaluationRecord {
    actuals_snapshot_id: ActualsSnapshotId;
    assumptions: Assumptions;
    discovery?: EvaluationContext | null;
    evaluation_id: EvaluationId;
    metrics: Metrics;
    origin_count: OriginCount;
    run_id: RunId;
    status: Status;
  }
  /**
   * Trusted evaluator attestation, never accepted as an agent proposal.
   *
   * Origin IDs identify the frozen target window, independently of model/config.
   * The caller establishes temporal/semantic validity using Plan 02 evaluation.
   * Defaults fail closed when that verification has not been performed.
   */
  export interface EvaluationContext {
    candidate_id: CandidateId;
    epoch_id: EpochId;
    origin_id: OriginId;
    partition: Partition;
    protocol_id: ProtocolId;
    semantic_valid?: SemanticValid;
    source_snapshot_ids: SourceSnapshotIds;
    target_end: TargetEnd;
    target_start: TargetStart;
    temporal_valid?: TemporalValid;
  }
  export interface Metrics {
    [k: string]: unknown;
  }
}
export type EvaluationRecord = EvaluationRecordGenerated.EvaluationRecord;

export namespace NodeGenerated {
  export type Inputs = string[];
  export type Kind = "source" | "forecast" | "transform" | "event";
  export type NodeId = string;

  export interface Node {
    config: Config;
    inputs: Inputs;
    kind: Kind;
    node_id: NodeId;
  }
  export interface Config {
    [k: string]: unknown;
  }
}
export type Node = NodeGenerated.Node;

export namespace GraphSpecGenerated {
  export type GraphId = string;
  export type Inputs = string[];
  export type Kind = "source" | "forecast" | "transform" | "event";
  export type NodeId = string;
  export type Nodes = Node[];
  export type Version = number;

  export interface GraphSpec {
    graph_id: GraphId;
    nodes: Nodes;
    version: Version;
  }
  export interface Node {
    config: Config;
    inputs: Inputs;
    kind: Kind;
    node_id: NodeId;
  }
  export interface Config {
    [k: string]: unknown;
  }
}
export type GraphSpec = GraphSpecGenerated.GraphSpec;

export namespace SnapshotGenerated {
  export type AsOf = string;
  export type Assumptions = string[];
  export type AvailableAt = string;
  export type EventTime = string;
  export type Revision = string;
  export type SeriesId = string;
  export type Unit = string;
  export type Value = number | null;
  export type Observations = Observation[];
  export type SnapshotId = string;

  export interface Snapshot {
    as_of: AsOf;
    assumptions: Assumptions;
    observations: Observations;
    snapshot_id: SnapshotId;
  }
  export interface Observation {
    available_at: AvailableAt;
    event_time: EventTime;
    revision: Revision;
    series_id: SeriesId;
    unit: Unit;
    value: Value;
  }
}
export type Snapshot = SnapshotGenerated.Snapshot;

export namespace ScenarioRequestGenerated {
  export type BaseGraphId = string;
  export type BaseVersion = number;
  export type Label = string;
  export type AsOf = string;
  export type Assumptions = string[];
  export type AvailableAt = string;
  export type EventTime = string;
  export type Revision = string;
  export type SeriesId = string;
  export type Unit = string;
  export type Value = number | null;
  export type Observations = Observation[];
  export type SnapshotId = string;

  export interface ScenarioRequest {
    base_graph_id: BaseGraphId;
    base_version: BaseVersion;
    label: Label;
    source_overrides: SourceOverrides;
  }
  export interface SourceOverrides {
    [k: string]: Snapshot;
  }
  export interface Snapshot {
    as_of: AsOf;
    assumptions: Assumptions;
    observations: Observations;
    snapshot_id: SnapshotId;
  }
  export interface Observation {
    available_at: AvailableAt;
    event_time: EventTime;
    revision: Revision;
    series_id: SeriesId;
    unit: Unit;
    value: Value;
  }
}
export type ScenarioRequest = ScenarioRequestGenerated.ScenarioRequest;

export namespace ScenarioViewGenerated {
  export type GraphId = string;
  export type JobId = string;
  export type Label = string;
  export type ParentRunId = string;
  export type PrimaryNodeId = string | null;
  export type ScenarioId = string;
  export type Version = number;

  export interface ScenarioView {
    graph_id: GraphId;
    job_id: JobId;
    label: Label;
    parent_run_id: ParentRunId;
    primary_node_id?: PrimaryNodeId;
    scenario_id: ScenarioId;
    snapshot_ids: SnapshotIds;
    version: Version;
  }
  export interface SnapshotIds {
    [k: string]: string;
  }
}
export type ScenarioView = ScenarioViewGenerated.ScenarioView;

export namespace JobViewGenerated {
  export type Attempt = number;
  export type Error = {
    [k: string]: unknown;
  } | null;
  export type JobId = string;
  export type Result = {
    [k: string]: unknown;
  } | null;
  export type State = string;

  export interface JobView {
    attempt: Attempt;
    error?: Error;
    job_id: JobId;
    result?: Result;
    state: State;
  }
}
export type JobView = JobViewGenerated.JobView;

export namespace QuestionForecastSelectionGenerated {
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;

  export interface QuestionForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
}
export type QuestionForecastSelection = QuestionForecastSelectionGenerated.QuestionForecastSelection;

export namespace QuestionCreateRequestGenerated {
  export type Key = string;
  export type Meaning = string;
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  /**
   * @maxItems 16
   */
  export type SourceIds =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  export type Title = string;

  export interface QuestionCreateRequest {
    key: Key;
    meaning: Meaning;
    selection: QuestionForecastSelection;
    source_ids?: SourceIds;
    title: Title;
  }
  export interface QuestionForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
}
export type QuestionCreateRequest = QuestionCreateRequestGenerated.QuestionCreateRequest;

export namespace QuestionRevisionRequestGenerated {
  export type ExpectedRevision = number;
  export type Key = string;
  export type Meaning = string;
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  /**
   * @maxItems 16
   */
  export type SourceIds =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];

  export interface QuestionRevisionRequest {
    expected_revision: ExpectedRevision;
    key: Key;
    meaning: Meaning;
    selection: QuestionForecastSelection;
    source_ids?: SourceIds;
  }
  export interface QuestionForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
}
export type QuestionRevisionRequest = QuestionRevisionRequestGenerated.QuestionRevisionRequest;

export namespace QuestionTitlePatchGenerated {
  export type Status = ("open" | "paused" | "resolved") | null;
  export type Title = string | null;

  export interface QuestionTitlePatch {
    status?: Status;
    title?: Title;
  }
}
export type QuestionTitlePatch = QuestionTitlePatchGenerated.QuestionTitlePatch;

export namespace QuestionRevisionGenerated {
  export type CreatedAt = string;
  export type Meaning = string;
  export type QuestionId = string;
  export type Revision = number;
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  /**
   * @maxItems 16
   */
  export type SourceIds =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];

  export interface QuestionRevision {
    created_at: CreatedAt;
    meaning: Meaning;
    question_id: QuestionId;
    revision: Revision;
    selection: QuestionForecastSelection;
    source_ids: SourceIds;
  }
  export interface QuestionForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
}
export type QuestionRevision = QuestionRevisionGenerated.QuestionRevision;

export namespace QuestionViewGenerated {
  export type CreatedAt = string;
  export type CurrentRevision = number;
  export type QuestionId = string;
  export type ReferenceCount = number;
  export type CreatedAt1 = string;
  export type Meaning = string;
  export type QuestionId1 = string;
  export type Revision = number;
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  /**
   * @maxItems 16
   */
  export type SourceIds =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  export type RevisionCount = number;
  export type Status = "open" | "paused" | "resolved";
  export type Title = string;
  export type UpdatedAt = string;

  export interface QuestionView {
    created_at: CreatedAt;
    current_revision: CurrentRevision;
    question_id: QuestionId;
    reference_count: ReferenceCount;
    revision: QuestionRevision;
    revision_count: RevisionCount;
    status: Status;
    title: Title;
    updated_at: UpdatedAt;
  }
  export interface QuestionRevision {
    created_at: CreatedAt1;
    meaning: Meaning;
    question_id: QuestionId1;
    revision: Revision;
    selection: QuestionForecastSelection;
    source_ids: SourceIds;
  }
  export interface QuestionForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
}
export type QuestionView = QuestionViewGenerated.QuestionView;

export namespace QuestionReferenceRequestGenerated {
  export type Key = string;
  export type Note = string;
  export type Revision = number;
  export type TargetId = string;
  export type TargetType = "candidate" | "run" | "backtest" | "watch" | "evaluation" | "operation";

  export interface QuestionReferenceRequest {
    key: Key;
    note?: Note;
    revision: Revision;
    target_id: TargetId;
    target_type: TargetType;
  }
}
export type QuestionReferenceRequest = QuestionReferenceRequestGenerated.QuestionReferenceRequest;

export namespace QuestionReferenceGenerated {
  export type CreatedAt = string;
  export type Note = string;
  export type QuestionId = string;
  export type ReferenceId = string;
  export type Revision = number;
  export type TargetId = string;
  export type TargetType = "candidate" | "run" | "backtest" | "watch" | "evaluation" | "operation";

  export interface QuestionReference {
    created_at: CreatedAt;
    note: Note;
    question_id: QuestionId;
    reference_id: ReferenceId;
    revision: Revision;
    target_id: TargetId;
    target_type: TargetType;
  }
}
export type QuestionReference = QuestionReferenceGenerated.QuestionReference;

export namespace QuestionPageGenerated {
  export type NextOffset = number | null;
  export type CreatedAt = string;
  export type CurrentRevision = number;
  export type QuestionId = string;
  export type ReferenceCount = number;
  export type CreatedAt1 = string;
  export type Meaning = string;
  export type QuestionId1 = string;
  export type Revision = number;
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  /**
   * @maxItems 16
   */
  export type SourceIds =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  export type RevisionCount = number;
  export type Status = "open" | "paused" | "resolved";
  export type Title = string;
  export type UpdatedAt = string;
  export type Questions = QuestionView[];

  export interface QuestionPage {
    next_offset: NextOffset;
    questions: Questions;
  }
  export interface QuestionView {
    created_at: CreatedAt;
    current_revision: CurrentRevision;
    question_id: QuestionId;
    reference_count: ReferenceCount;
    revision: QuestionRevision;
    revision_count: RevisionCount;
    status: Status;
    title: Title;
    updated_at: UpdatedAt;
  }
  export interface QuestionRevision {
    created_at: CreatedAt1;
    meaning: Meaning;
    question_id: QuestionId1;
    revision: Revision;
    selection: QuestionForecastSelection;
    source_ids: SourceIds;
  }
  export interface QuestionForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
}
export type QuestionPage = QuestionPageGenerated.QuestionPage;

export namespace QuestionRevisionPageGenerated {
  export type NextOffset = number | null;
  export type CreatedAt = string;
  export type Meaning = string;
  export type QuestionId = string;
  export type Revision = number;
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  /**
   * @maxItems 16
   */
  export type SourceIds =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  export type Revisions = QuestionRevision[];

  export interface QuestionRevisionPage {
    next_offset: NextOffset;
    revisions: Revisions;
  }
  export interface QuestionRevision {
    created_at: CreatedAt;
    meaning: Meaning;
    question_id: QuestionId;
    revision: Revision;
    selection: QuestionForecastSelection;
    source_ids: SourceIds;
  }
  export interface QuestionForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
}
export type QuestionRevisionPage = QuestionRevisionPageGenerated.QuestionRevisionPage;

export namespace QuestionReferencePageGenerated {
  export type NextOffset = number | null;
  export type CreatedAt = string;
  export type Note = string;
  export type QuestionId = string;
  export type ReferenceId = string;
  export type Revision = number;
  export type TargetId = string;
  export type TargetType = "candidate" | "run" | "backtest" | "watch" | "evaluation" | "operation";
  export type References = QuestionReference[];

  export interface QuestionReferencePage {
    next_offset: NextOffset;
    references: References;
  }
  export interface QuestionReference {
    created_at: CreatedAt;
    note: Note;
    question_id: QuestionId;
    reference_id: ReferenceId;
    revision: Revision;
    target_id: TargetId;
    target_type: TargetType;
  }
}
export type QuestionReferencePage = QuestionReferencePageGenerated.QuestionReferencePage;

export namespace OperationCreateRequestGenerated {
  export type Key = string;
  /**
   * @maxItems 32
   */
  export type MissingData = string[];
  export type Phase = "collecting" | "ready";
  export type QuestionId = string | null;
  export type QuestionRevision = number | null;

  export interface OperationCreateRequest {
    key: Key;
    missing_data?: MissingData;
    phase?: Phase;
    question_id?: QuestionId;
    question_revision?: QuestionRevision;
  }
}
export type OperationCreateRequest = OperationCreateRequestGenerated.OperationCreateRequest;

export namespace OperationUpdateRequestGenerated {
  export type ExpectedVersion = number;
  export type Key = string;
  /**
   * @maxItems 32
   */
  export type MissingData = string[];
  export type Phase = "collecting" | "ready";

  export interface OperationUpdateRequest {
    expected_version: ExpectedVersion;
    key: Key;
    missing_data?: MissingData;
    phase: Phase;
  }
}
export type OperationUpdateRequest = OperationUpdateRequestGenerated.OperationUpdateRequest;

export namespace OperationSubmitRequestGenerated {
  export type CandidateId = string | null;
  export type ExpectedVersion = number;
  export type Request =
    RunJobRequest | ConfiguredRunJobRequest | BacktestJobRequest | EvaluationJobRequest | ResumeJobRequest;
  export type AsOf = string;
  export type GraphId = string;
  export type Inputs = string[];
  export type Kind = "source" | "forecast" | "transform" | "event";
  export type NodeId = string;
  export type Nodes = Node[];
  export type Version = number;
  export type Key = string;
  export type Kind1 = "run";
  export type PreviousRunId = string | null;
  export type PrimaryNodeId = string | null;
  export type Key1 = string;
  export type Kind2 = "configured_run";
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  export type SnapshotId = string;
  export type SourceId = string;
  export type Key2 = string;
  export type Kind3 = "backtest";
  export type MaxOriginsPerPartition = number;
  export type OriginOffsetSeconds = number;
  export type SourceId1 = string;
  export type WatchId = string | null;
  export type ActualsSnapshotId = string;
  export type Key3 = string;
  export type Kind4 = "evaluation";
  export type RunId = string;
  export type Key4 = string;
  export type Kind5 = "watch_resume";
  export type WatchId1 = string;

  export interface OperationSubmitRequest {
    candidate_id?: CandidateId;
    expected_version: ExpectedVersion;
    request: Request;
  }
  export interface RunJobRequest {
    as_of: AsOf;
    graph: GraphSpec;
    key: Key;
    kind: Kind1;
    previous_run_id?: PreviousRunId;
    primary_node_id?: PrimaryNodeId;
    snapshot_ids: SnapshotIds;
  }
  export interface GraphSpec {
    graph_id: GraphId;
    nodes: Nodes;
    version: Version;
  }
  export interface Node {
    config: Config;
    inputs: Inputs;
    kind: Kind;
    node_id: NodeId;
  }
  export interface Config {
    [k: string]: unknown;
  }
  export interface SnapshotIds {
    [k: string]: string;
  }
  export interface ConfiguredRunJobRequest {
    key: Key1;
    kind: Kind2;
    selection: ForecastSelection;
    snapshot_id: SnapshotId;
    source_id: SourceId;
  }
  export interface ForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
  export interface BacktestJobRequest {
    key: Key2;
    kind: Kind3;
    selection: ForecastSelection;
    settings?: BacktestSettings;
    source_id: SourceId1;
    watch_id?: WatchId;
  }
  export interface BacktestSettings {
    max_origins_per_partition?: MaxOriginsPerPartition;
    origin_offset_seconds?: OriginOffsetSeconds;
  }
  export interface EvaluationJobRequest {
    actuals_snapshot_id: ActualsSnapshotId;
    key: Key3;
    kind: Kind4;
    run_id: RunId;
  }
  export interface ResumeJobRequest {
    key: Key4;
    kind: Kind5;
    watch_id: WatchId1;
  }
}
export type OperationSubmitRequest = OperationSubmitRequestGenerated.OperationSubmitRequest;

export namespace OperationViewGenerated {
  export type CreatedAt = string;
  export type JobError = {
    [k: string]: unknown;
  } | null;
  export type JobId = string | null;
  export type JobState = string | null;
  export type MissingData = string[];
  export type OperationId = string;
  export type Phase = "collecting" | "ready";
  export type QuestionId = string | null;
  export type QuestionRevision = number | null;
  export type RequestDigest = string | null;
  export type RequestKind = string | null;
  /**
   * @maxItems 16
   */
  export type SourceIds =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  export type State = "open" | "reserved" | "submitted" | "completed" | "failed";
  export type UpdatedAt = string;
  export type Version = number;

  export interface OperationView {
    created_at: CreatedAt;
    job_error: JobError;
    job_id: JobId;
    job_state: JobState;
    missing_data: MissingData;
    operation_id: OperationId;
    phase: Phase;
    question_id: QuestionId;
    question_revision: QuestionRevision;
    request_digest: RequestDigest;
    request_kind: RequestKind;
    source_ids: SourceIds;
    state: State;
    updated_at: UpdatedAt;
    version: Version;
  }
}
export type OperationView = OperationViewGenerated.OperationView;

export namespace OperationPageGenerated {
  export type NextOffset = number | null;
  export type CreatedAt = string;
  export type JobError = {
    [k: string]: unknown;
  } | null;
  export type JobId = string | null;
  export type JobState = string | null;
  export type MissingData = string[];
  export type OperationId = string;
  export type Phase = "collecting" | "ready";
  export type QuestionId = string | null;
  export type QuestionRevision = number | null;
  export type RequestDigest = string | null;
  export type RequestKind = string | null;
  /**
   * @maxItems 16
   */
  export type SourceIds =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  export type State = "open" | "reserved" | "submitted" | "completed" | "failed";
  export type UpdatedAt = string;
  export type Version = number;
  export type Operations = OperationView[];

  export interface OperationPage {
    next_offset: NextOffset;
    operations: Operations;
  }
  export interface OperationView {
    created_at: CreatedAt;
    job_error: JobError;
    job_id: JobId;
    job_state: JobState;
    missing_data: MissingData;
    operation_id: OperationId;
    phase: Phase;
    question_id: QuestionId;
    question_revision: QuestionRevision;
    request_digest: RequestDigest;
    request_kind: RequestKind;
    source_ids: SourceIds;
    state: State;
    updated_at: UpdatedAt;
    version: Version;
  }
}
export type OperationPage = OperationPageGenerated.OperationPage;

export namespace SnapshotSummaryGenerated {
  export type AsOf = string;
  export type AssumptionCount = number;
  /**
   * @maxItems 16
   */
  export type Assumptions =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  export type AssumptionsTruncated = boolean;
  export type AvailableAtEnd = string | null;
  export type AvailableAtStart = string | null;
  export type EventTimeEnd = string | null;
  export type EventTimeStart = string | null;
  export type MissingCount = number;
  export type ObservationCount = number;
  export type RevisionCount = number;
  export type SeriesCount = number;
  export type SnapshotId = string;

  export interface SnapshotSummary {
    as_of: AsOf;
    assumption_count: AssumptionCount;
    assumptions: Assumptions;
    assumptions_truncated: AssumptionsTruncated;
    available_at_end: AvailableAtEnd;
    available_at_start: AvailableAtStart;
    event_time_end: EventTimeEnd;
    event_time_start: EventTimeStart;
    missing_count: MissingCount;
    observation_count: ObservationCount;
    revision_count: RevisionCount;
    series_count: SeriesCount;
    snapshot_id: SnapshotId;
  }
}
export type SnapshotSummary = SnapshotSummaryGenerated.SnapshotSummary;

export namespace SnapshotSeriesSummaryGenerated {
  export type AvailableAtEnd = string | null;
  export type AvailableAtStart = string | null;
  export type EventTimeEnd = string | null;
  export type EventTimeStart = string | null;
  export type MissingCount = number;
  export type ObservationCount = number;
  export type RevisionCount = number;
  export type SeriesId = string;
  export type SnapshotId = string;
  export type UnitCount = number;
  /**
   * @maxItems 8
   */
  export type Units =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string];
  export type UnitsTruncated = boolean;

  export interface SnapshotSeriesSummary {
    available_at_end: AvailableAtEnd;
    available_at_start: AvailableAtStart;
    event_time_end: EventTimeEnd;
    event_time_start: EventTimeStart;
    missing_count: MissingCount;
    observation_count: ObservationCount;
    revision_count: RevisionCount;
    series_id: SeriesId;
    snapshot_id: SnapshotId;
    unit_count: UnitCount;
    units: Units;
    units_truncated: UnitsTruncated;
  }
}
export type SnapshotSeriesSummary = SnapshotSeriesSummaryGenerated.SnapshotSeriesSummary;

export namespace SnapshotSeriesPageGenerated {
  export type NextOffset = number | null;
  export type AvailableAtEnd = string | null;
  export type AvailableAtStart = string | null;
  export type EventTimeEnd = string | null;
  export type EventTimeStart = string | null;
  export type MissingCount = number;
  export type ObservationCount = number;
  export type RevisionCount = number;
  export type SeriesId = string;
  export type SnapshotId = string;
  export type UnitCount = number;
  /**
   * @maxItems 8
   */
  export type Units =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string];
  export type UnitsTruncated = boolean;
  export type Series = SnapshotSeriesSummary[];
  export type SnapshotId1 = string;

  export interface SnapshotSeriesPage {
    next_offset: NextOffset;
    series: Series;
    snapshot_id: SnapshotId1;
  }
  export interface SnapshotSeriesSummary {
    available_at_end: AvailableAtEnd;
    available_at_start: AvailableAtStart;
    event_time_end: EventTimeEnd;
    event_time_start: EventTimeStart;
    missing_count: MissingCount;
    observation_count: ObservationCount;
    revision_count: RevisionCount;
    series_id: SeriesId;
    snapshot_id: SnapshotId;
    unit_count: UnitCount;
    units: Units;
    units_truncated: UnitsTruncated;
  }
}
export type SnapshotSeriesPage = SnapshotSeriesPageGenerated.SnapshotSeriesPage;

export namespace ForecastPresentationGenerated {
  export type AsOf = string;
  export type GraphId = string;
  export type GraphVersion = number;
  export type NodeId = string;
  export type Point = number | null;
  export type QuantilesTruncated = boolean;
  export type Representation = "point" | "marginal_quantiles" | "joint_paths";
  export type SampleCount = number;
  export type SeriesId = string;
  export type Timestamp = string;
  export type Unit = string;
  /**
   * @maxItems 64
   */
  export type Points = ForecastPresentationPoint[];
  export type PrimaryNodeId = string | null;
  /**
   * @maxItems 16
   */
  export type Providers =
    | []
    | [ForecastProviderUse]
    | [ForecastProviderUse, ForecastProviderUse]
    | [ForecastProviderUse, ForecastProviderUse, ForecastProviderUse]
    | [ForecastProviderUse, ForecastProviderUse, ForecastProviderUse, ForecastProviderUse]
    | [ForecastProviderUse, ForecastProviderUse, ForecastProviderUse, ForecastProviderUse, ForecastProviderUse]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ]
    | [
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse,
        ForecastProviderUse
      ];
  export type ActualProvider = string | null;
  export type NodeId1 = string;
  export type RequestedProvider = string | null;
  export type ProvidersTruncated = boolean;
  export type RunId = string;
  export type SchemaVersion = "forecast-presentation-v1";
  /**
   * @maxItems 16
   */
  export type SnapshotIds =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  export type SnapshotIdsTruncated = boolean;
  export type State = string;
  export type TotalPointCount = number;
  export type Truncated = boolean;
  export type VisualDestination = "time_series";

  export interface ForecastPresentation {
    as_of: AsOf;
    graph_id: GraphId;
    graph_version: GraphVersion;
    points: Points;
    primary_node_id?: PrimaryNodeId;
    providers: Providers;
    providers_truncated: ProvidersTruncated;
    run_id: RunId;
    schema_version?: SchemaVersion;
    snapshot_ids: SnapshotIds;
    snapshot_ids_truncated: SnapshotIdsTruncated;
    state: State;
    total_point_count: TotalPointCount;
    truncated: Truncated;
    visual_destination?: VisualDestination;
  }
  export interface ForecastPresentationPoint {
    node_id: NodeId;
    point: Point;
    quantiles: Quantiles;
    quantiles_truncated: QuantilesTruncated;
    representation: Representation;
    sample_count: SampleCount;
    series_id: SeriesId;
    timestamp: Timestamp;
    unit: Unit;
  }
  export interface Quantiles {
    [k: string]: number;
  }
  export interface ForecastProviderUse {
    actual_provider: ActualProvider;
    node_id: NodeId1;
    requested_provider: RequestedProvider;
  }
}
export type ForecastPresentation = ForecastPresentationGenerated.ForecastPresentation;

export namespace ForecastPresentationPointGenerated {
  export type NodeId = string;
  export type Point = number | null;
  export type QuantilesTruncated = boolean;
  export type Representation = "point" | "marginal_quantiles" | "joint_paths";
  export type SampleCount = number;
  export type SeriesId = string;
  export type Timestamp = string;
  export type Unit = string;

  export interface ForecastPresentationPoint {
    node_id: NodeId;
    point: Point;
    quantiles: Quantiles;
    quantiles_truncated: QuantilesTruncated;
    representation: Representation;
    sample_count: SampleCount;
    series_id: SeriesId;
    timestamp: Timestamp;
    unit: Unit;
  }
  export interface Quantiles {
    [k: string]: number;
  }
}
export type ForecastPresentationPoint = ForecastPresentationPointGenerated.ForecastPresentationPoint;

export namespace ForecastProviderUseGenerated {
  export type ActualProvider = string | null;
  export type NodeId = string;
  export type RequestedProvider = string | null;

  export interface ForecastProviderUse {
    actual_provider: ActualProvider;
    node_id: NodeId;
    requested_provider: RequestedProvider;
  }
}
export type ForecastProviderUse = ForecastProviderUseGenerated.ForecastProviderUse;

export namespace BacktestPresentationGenerated {
  export type SchemaVersion = "backtest-presentation-v1";
  export type Assumptions = string[];
  export type BacktestId = string;
  export type CapturedAt = string;
  export type FinalComparison = "model_lower_mae" | "model_higher_mae" | "equal_mae" | "unavailable";
  export type BaselineMae = number | null;
  export type EvaluationId = string | null;
  export type ModelMae = number | null;
  export type Ordinal = number;
  export type ReasonCode = string | null;
  export type Status = "evaluated" | "excluded" | "failed" | "insufficient_evidence";
  export type TargetEnd = string;
  export type TargetStart = string;
  /**
   * @maxItems 50
   */
  export type FinalOriginPoints = FinalOriginPoint[];
  export type Frequency = string;
  export type InterpretationLimit = string;
  export type MetricDefinition = string;
  export type BaselineMae1 = number | null;
  export type Evaluated = number;
  export type Excluded = number;
  export type Failed = number;
  export type Insufficient = number;
  export type MatchedCount = number;
  export type ModelMae1 = number | null;
  export type Partition = "exploration" | "selection" | "final";
  export type Planned = number;
  export type RelativeMae = number | null;
  export type RelativeMaeReason = ("no_matched_cells" | "zero_baseline_mae" | "ratio_unrepresentable") | null;
  export type Partitions = PartitionScore[];
  export type RelativeMae1 = number | null;
  export type RelativeMaeReason1 = ("no_matched_cells" | "zero_baseline_mae" | "ratio_unrepresentable") | null;
  export type ReportId = string;
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  export type SourceId = string;
  export type SourceRevision = string;
  export type Status1 = "completed" | "insufficient_evidence";
  export type CandidateInvalidated = boolean;
  export type DecisionAction = ("activate" | "provisional" | "reject") | null;
  export type DecisionBacktestId = string | null;
  export type EvidenceApplicable = boolean;
  export type FinalEvaluationCount = number | null;
  export type Lifecycle = "candidate" | "evaluating" | "active" | "paused" | "unsupported";
  export type LinkedToBacktest = boolean;
  export type MigrationReason = string | null;
  export type Operational = boolean;
  export type Quality = "provisional" | "usable" | "stale" | "degraded";
  export type ReasonCodes = string[];
  export type ReevaluationRequired = boolean;
  export type WatchId = string;
  export type VisualDestination = "comparison";

  export interface BacktestPresentation {
    schema_version?: SchemaVersion;
    summary: BacktestSummary;
    visual_destination?: VisualDestination;
  }
  export interface BacktestSummary {
    assumptions: Assumptions;
    backtest_id: BacktestId;
    captured_at: CapturedAt;
    final_comparison: FinalComparison;
    final_origin_points: FinalOriginPoints;
    frequency: Frequency;
    interpretation_limit: InterpretationLimit;
    metric_definition: MetricDefinition;
    partitions: Partitions;
    relative_mae: RelativeMae1;
    relative_mae_reason: RelativeMaeReason1;
    report_id: ReportId;
    selection: ForecastSelection;
    source_id: SourceId;
    source_revision: SourceRevision;
    status: Status1;
    watch?: WatchBacktestSummary | null;
  }
  /**
   * Chart-ready per-origin scores, never forecast or source values.
   */
  export interface FinalOriginPoint {
    baseline_mae?: BaselineMae;
    evaluation_id?: EvaluationId;
    model_mae?: ModelMae;
    ordinal: Ordinal;
    reason_code?: ReasonCode;
    status: Status;
    target_end: TargetEnd;
    target_start: TargetStart;
  }
  export interface PartitionScore {
    baseline_mae?: BaselineMae1;
    evaluated?: Evaluated;
    excluded?: Excluded;
    failed?: Failed;
    insufficient?: Insufficient;
    matched_count?: MatchedCount;
    model_mae?: ModelMae1;
    partition: Partition;
    planned: Planned;
    relative_mae?: RelativeMae;
    relative_mae_reason?: RelativeMaeReason;
  }
  export interface ForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
  export interface WatchBacktestSummary {
    candidate_invalidated: CandidateInvalidated;
    decision_action?: DecisionAction;
    decision_backtest_id?: DecisionBacktestId;
    evidence_applicable: EvidenceApplicable;
    final_evaluation_count?: FinalEvaluationCount;
    lifecycle: Lifecycle;
    linked_to_backtest: LinkedToBacktest;
    migration_reason?: MigrationReason;
    operational: Operational;
    quality: Quality;
    reason_codes?: ReasonCodes;
    reevaluation_required: ReevaluationRequired;
    watch_id: WatchId;
  }
}
export type BacktestPresentation = BacktestPresentationGenerated.BacktestPresentation;

export namespace BacktestSummaryGenerated {
  export type Assumptions = string[];
  export type BacktestId = string;
  export type CapturedAt = string;
  export type FinalComparison = "model_lower_mae" | "model_higher_mae" | "equal_mae" | "unavailable";
  export type BaselineMae = number | null;
  export type EvaluationId = string | null;
  export type ModelMae = number | null;
  export type Ordinal = number;
  export type ReasonCode = string | null;
  export type Status = "evaluated" | "excluded" | "failed" | "insufficient_evidence";
  export type TargetEnd = string;
  export type TargetStart = string;
  /**
   * @maxItems 50
   */
  export type FinalOriginPoints = FinalOriginPoint[];
  export type Frequency = string;
  export type InterpretationLimit = string;
  export type MetricDefinition = string;
  export type BaselineMae1 = number | null;
  export type Evaluated = number;
  export type Excluded = number;
  export type Failed = number;
  export type Insufficient = number;
  export type MatchedCount = number;
  export type ModelMae1 = number | null;
  export type Partition = "exploration" | "selection" | "final";
  export type Planned = number;
  export type RelativeMae = number | null;
  export type RelativeMaeReason = ("no_matched_cells" | "zero_baseline_mae" | "ratio_unrepresentable") | null;
  export type Partitions = PartitionScore[];
  export type RelativeMae1 = number | null;
  export type RelativeMaeReason1 = ("no_matched_cells" | "zero_baseline_mae" | "ratio_unrepresentable") | null;
  export type ReportId = string;
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  export type SourceId = string;
  export type SourceRevision = string;
  export type Status1 = "completed" | "insufficient_evidence";
  export type CandidateInvalidated = boolean;
  export type DecisionAction = ("activate" | "provisional" | "reject") | null;
  export type DecisionBacktestId = string | null;
  export type EvidenceApplicable = boolean;
  export type FinalEvaluationCount = number | null;
  export type Lifecycle = "candidate" | "evaluating" | "active" | "paused" | "unsupported";
  export type LinkedToBacktest = boolean;
  export type MigrationReason = string | null;
  export type Operational = boolean;
  export type Quality = "provisional" | "usable" | "stale" | "degraded";
  export type ReasonCodes = string[];
  export type ReevaluationRequired = boolean;
  export type WatchId = string;

  export interface BacktestSummary {
    assumptions: Assumptions;
    backtest_id: BacktestId;
    captured_at: CapturedAt;
    final_comparison: FinalComparison;
    final_origin_points: FinalOriginPoints;
    frequency: Frequency;
    interpretation_limit: InterpretationLimit;
    metric_definition: MetricDefinition;
    partitions: Partitions;
    relative_mae: RelativeMae1;
    relative_mae_reason: RelativeMaeReason1;
    report_id: ReportId;
    selection: ForecastSelection;
    source_id: SourceId;
    source_revision: SourceRevision;
    status: Status1;
    watch?: WatchBacktestSummary | null;
  }
  /**
   * Chart-ready per-origin scores, never forecast or source values.
   */
  export interface FinalOriginPoint {
    baseline_mae?: BaselineMae;
    evaluation_id?: EvaluationId;
    model_mae?: ModelMae;
    ordinal: Ordinal;
    reason_code?: ReasonCode;
    status: Status;
    target_end: TargetEnd;
    target_start: TargetStart;
  }
  export interface PartitionScore {
    baseline_mae?: BaselineMae1;
    evaluated?: Evaluated;
    excluded?: Excluded;
    failed?: Failed;
    insufficient?: Insufficient;
    matched_count?: MatchedCount;
    model_mae?: ModelMae1;
    partition: Partition;
    planned: Planned;
    relative_mae?: RelativeMae;
    relative_mae_reason?: RelativeMaeReason;
  }
  export interface ForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
  export interface WatchBacktestSummary {
    candidate_invalidated: CandidateInvalidated;
    decision_action?: DecisionAction;
    decision_backtest_id?: DecisionBacktestId;
    evidence_applicable: EvidenceApplicable;
    final_evaluation_count?: FinalEvaluationCount;
    lifecycle: Lifecycle;
    linked_to_backtest: LinkedToBacktest;
    migration_reason?: MigrationReason;
    operational: Operational;
    quality: Quality;
    reason_codes?: ReasonCodes;
    reevaluation_required: ReevaluationRequired;
    watch_id: WatchId;
  }
}
export type BacktestSummary = BacktestSummaryGenerated.BacktestSummary;

export namespace QuestionPresentationGenerated {
  export type NextOffset = number | null;
  export type CreatedAt = string;
  export type CurrentRevision = number;
  export type QuestionId = string;
  export type ReferenceCount = number;
  export type CreatedAt1 = string;
  export type Meaning = string;
  export type QuestionId1 = string;
  export type Revision = number;
  export type BaselinePeriod = number;
  export type Horizon = number;
  export type JsonValue = unknown;
  export type Provider = string;
  /**
   * @maxItems 16
   */
  export type SourceIds =
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  export type RevisionCount = number;
  export type Status = "open" | "paused" | "resolved";
  export type Title = string;
  export type UpdatedAt = string;
  /**
   * @maxItems 3
   */
  export type References =
    | []
    | [QuestionPresentationReference]
    | [QuestionPresentationReference, QuestionPresentationReference]
    | [QuestionPresentationReference, QuestionPresentationReference, QuestionPresentationReference];
  export type AppliesToCurrentRevision = boolean;
  export type CreatedAt2 = string;
  export type Note = string;
  export type QuestionId2 = string;
  export type ReferenceId = string;
  export type Revision1 = number;
  export type TargetId = string;
  export type TargetType = "candidate" | "run" | "backtest" | "watch" | "evaluation" | "operation";
  export type SchemaVersion = "question-presentation-v1";
  export type VisualDestination = "question_timeline";

  export interface QuestionPresentation {
    next_offset: NextOffset;
    question: QuestionView;
    references: References;
    schema_version?: SchemaVersion;
    visual_destination?: VisualDestination;
  }
  export interface QuestionView {
    created_at: CreatedAt;
    current_revision: CurrentRevision;
    question_id: QuestionId;
    reference_count: ReferenceCount;
    revision: QuestionRevision;
    revision_count: RevisionCount;
    status: Status;
    title: Title;
    updated_at: UpdatedAt;
  }
  export interface QuestionRevision {
    created_at: CreatedAt1;
    meaning: Meaning;
    question_id: QuestionId1;
    revision: Revision;
    selection: QuestionForecastSelection;
    source_ids: SourceIds;
  }
  export interface QuestionForecastSelection {
    baseline_period?: BaselinePeriod;
    horizon: Horizon;
    options?: Options;
    provider: Provider;
  }
  export interface Options {
    [k: string]: JsonValue;
  }
  export interface QuestionPresentationReference {
    applies_to_current_revision: AppliesToCurrentRevision;
    reference: QuestionReference;
  }
  export interface QuestionReference {
    created_at: CreatedAt2;
    note: Note;
    question_id: QuestionId2;
    reference_id: ReferenceId;
    revision: Revision1;
    target_id: TargetId;
    target_type: TargetType;
  }
}
export type QuestionPresentation = QuestionPresentationGenerated.QuestionPresentation;

export namespace QuestionPresentationReferenceGenerated {
  export type AppliesToCurrentRevision = boolean;
  export type CreatedAt = string;
  export type Note = string;
  export type QuestionId = string;
  export type ReferenceId = string;
  export type Revision = number;
  export type TargetId = string;
  export type TargetType = "candidate" | "run" | "backtest" | "watch" | "evaluation" | "operation";

  export interface QuestionPresentationReference {
    applies_to_current_revision: AppliesToCurrentRevision;
    reference: QuestionReference;
  }
  export interface QuestionReference {
    created_at: CreatedAt;
    note: Note;
    question_id: QuestionId;
    reference_id: ReferenceId;
    revision: Revision;
    target_id: TargetId;
    target_type: TargetType;
  }
}
export type QuestionPresentationReference = QuestionPresentationReferenceGenerated.QuestionPresentationReference;
