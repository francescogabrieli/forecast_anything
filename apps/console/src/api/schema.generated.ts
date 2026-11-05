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
  export type ScenarioId = string;
  export type Version = number;

  export interface ScenarioView {
    graph_id: GraphId;
    job_id: JobId;
    label: Label;
    parent_run_id: ParentRunId;
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
