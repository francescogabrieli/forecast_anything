// Generated from contracts/v1/schemas.json and openapi.json. Run npm run contracts:generate.

export const forecastSelectionSchema = {
  "$defs": {
    "JsonValue": {}
  },
  "additionalProperties": false,
  "properties": {
    "baseline_period": {
      "default": 1,
      "maximum": 10000,
      "minimum": 1,
      "title": "Baseline Period",
      "type": "integer"
    },
    "horizon": {
      "maximum": 366,
      "minimum": 1,
      "title": "Horizon",
      "type": "integer"
    },
    "options": {
      "additionalProperties": {
        "$ref": "#/$defs/JsonValue"
      },
      "title": "Options",
      "type": "object"
    },
    "provider": {
      "minLength": 1,
      "title": "Provider",
      "type": "string"
    }
  },
  "required": [
    "provider",
    "horizon"
  ],
  "title": "ForecastSelection",
  "type": "object"
} as const;

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

export const backtestSettingsSchema = {
  "additionalProperties": false,
  "properties": {
    "max_origins_per_partition": {
      "default": 10,
      "maximum": 50,
      "minimum": 1,
      "title": "Max Origins Per Partition",
      "type": "integer"
    },
    "origin_offset_seconds": {
      "default": 0,
      "minimum": 0,
      "title": "Origin Offset Seconds",
      "type": "integer"
    }
  },
  "title": "BacktestSettings",
  "type": "object"
} as const;

export namespace BacktestSettingsGenerated {
  export type MaxOriginsPerPartition = number;
  export type OriginOffsetSeconds = number;

  export interface BacktestSettings {
    max_origins_per_partition?: MaxOriginsPerPartition;
    origin_offset_seconds?: OriginOffsetSeconds;
  }
}
export type BacktestSettings = BacktestSettingsGenerated.BacktestSettings;

export const backtestReportSchema = {
  "$defs": {
    "BacktestSettings": {
      "additionalProperties": false,
      "properties": {
        "max_origins_per_partition": {
          "default": 10,
          "maximum": 50,
          "minimum": 1,
          "title": "Max Origins Per Partition",
          "type": "integer"
        },
        "origin_offset_seconds": {
          "default": 0,
          "minimum": 0,
          "title": "Origin Offset Seconds",
          "type": "integer"
        }
      },
      "title": "BacktestSettings",
      "type": "object"
    },
    "Capabilities": {
      "additionalProperties": false,
      "properties": {
        "provider_id": {
          "minLength": 1,
          "title": "Provider Id",
          "type": "string"
        },
        "provider_revision": {
          "minLength": 1,
          "title": "Provider Revision",
          "type": "string"
        },
        "representations": {
          "items": {
            "enum": [
              "point",
              "marginal_quantiles",
              "joint_paths"
            ],
            "type": "string"
          },
          "title": "Representations",
          "type": "array"
        },
        "supports_known_future": {
          "title": "Supports Known Future",
          "type": "boolean"
        }
      },
      "required": [
        "provider_id",
        "provider_revision",
        "representations",
        "supports_known_future"
      ],
      "title": "Capabilities",
      "type": "object"
    },
    "ForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "ForecastSelection",
      "type": "object"
    },
    "JsonValue": {},
    "PartitionScore": {
      "additionalProperties": false,
      "properties": {
        "baseline_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Baseline Mae"
        },
        "evaluated": {
          "default": 0,
          "minimum": 0,
          "title": "Evaluated",
          "type": "integer"
        },
        "excluded": {
          "default": 0,
          "minimum": 0,
          "title": "Excluded",
          "type": "integer"
        },
        "failed": {
          "default": 0,
          "minimum": 0,
          "title": "Failed",
          "type": "integer"
        },
        "insufficient": {
          "default": 0,
          "minimum": 0,
          "title": "Insufficient",
          "type": "integer"
        },
        "matched_count": {
          "default": 0,
          "minimum": 0,
          "title": "Matched Count",
          "type": "integer"
        },
        "model_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Model Mae"
        },
        "partition": {
          "enum": [
            "exploration",
            "selection",
            "final"
          ],
          "title": "Partition",
          "type": "string"
        },
        "planned": {
          "minimum": 0,
          "title": "Planned",
          "type": "integer"
        },
        "relative_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Relative Mae"
        },
        "relative_mae_reason": {
          "anyOf": [
            {
              "enum": [
                "no_matched_cells",
                "zero_baseline_mae",
                "ratio_unrepresentable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": "no_matched_cells",
          "title": "Relative Mae Reason"
        }
      },
      "required": [
        "partition",
        "planned"
      ],
      "title": "PartitionScore",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "actuals_snapshot_id": {
      "minLength": 1,
      "title": "Actuals Snapshot Id",
      "type": "string"
    },
    "archive_id": {
      "minLength": 1,
      "title": "Archive Id",
      "type": "string"
    },
    "assumptions": {
      "default": [],
      "items": {
        "type": "string"
      },
      "title": "Assumptions",
      "type": "array"
    },
    "backtest_id": {
      "minLength": 1,
      "title": "Backtest Id",
      "type": "string"
    },
    "captured_at": {
      "format": "date-time",
      "title": "Captured At",
      "type": "string"
    },
    "frequency": {
      "minLength": 1,
      "title": "Frequency",
      "type": "string"
    },
    "partitions": {
      "items": {
        "$ref": "#/$defs/PartitionScore"
      },
      "title": "Partitions",
      "type": "array"
    },
    "plan_id": {
      "minLength": 1,
      "title": "Plan Id",
      "type": "string"
    },
    "protocol_version": {
      "const": "backtest-v1",
      "default": "backtest-v1",
      "title": "Protocol Version",
      "type": "string"
    },
    "provider_contracts": {
      "additionalProperties": {
        "$ref": "#/$defs/Capabilities"
      },
      "propertyNames": {
        "minLength": 1
      },
      "title": "Provider Contracts",
      "type": "object"
    },
    "report_id": {
      "default": "",
      "title": "Report Id",
      "type": "string"
    },
    "selection": {
      "$ref": "#/$defs/ForecastSelection"
    },
    "settings": {
      "$ref": "#/$defs/BacktestSettings"
    },
    "source_id": {
      "minLength": 1,
      "title": "Source Id",
      "type": "string"
    },
    "source_revision": {
      "minLength": 1,
      "title": "Source Revision",
      "type": "string"
    },
    "status": {
      "enum": [
        "completed",
        "insufficient_evidence"
      ],
      "title": "Status",
      "type": "string"
    }
  },
  "required": [
    "backtest_id",
    "plan_id",
    "archive_id",
    "source_id",
    "source_revision",
    "captured_at",
    "actuals_snapshot_id",
    "selection",
    "settings",
    "provider_contracts",
    "frequency",
    "status",
    "partitions"
  ],
  "title": "BacktestReport",
  "type": "object"
} as const;

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

export const originPageSchema = {
  "$defs": {
    "OriginOutcome": {
      "additionalProperties": false,
      "properties": {
        "backtest_id": {
          "minLength": 1,
          "title": "Backtest Id",
          "type": "string"
        },
        "baseline_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Baseline Mae"
        },
        "evaluation_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Evaluation Id"
        },
        "issuance_time": {
          "format": "date-time",
          "title": "Issuance Time",
          "type": "string"
        },
        "matched_count": {
          "default": 0,
          "minimum": 0,
          "title": "Matched Count",
          "type": "integer"
        },
        "model_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Model Mae"
        },
        "nominal_origin": {
          "format": "date-time",
          "title": "Nominal Origin",
          "type": "string"
        },
        "ordinal": {
          "minimum": 0,
          "title": "Ordinal",
          "type": "integer"
        },
        "partition": {
          "enum": [
            "exploration",
            "selection",
            "final"
          ],
          "title": "Partition",
          "type": "string"
        },
        "plan_id": {
          "minLength": 1,
          "title": "Plan Id",
          "type": "string"
        },
        "reason_code": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Reason Code"
        },
        "run_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Run Id"
        },
        "status": {
          "enum": [
            "evaluated",
            "excluded",
            "failed",
            "insufficient_evidence"
          ],
          "title": "Status",
          "type": "string"
        },
        "target_end": {
          "format": "date-time",
          "title": "Target End",
          "type": "string"
        },
        "target_start": {
          "format": "date-time",
          "title": "Target Start",
          "type": "string"
        }
      },
      "required": [
        "ordinal",
        "partition",
        "nominal_origin",
        "issuance_time",
        "target_start",
        "target_end",
        "backtest_id",
        "plan_id",
        "status"
      ],
      "title": "OriginOutcome",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "backtest_id": {
      "minLength": 1,
      "title": "Backtest Id",
      "type": "string"
    },
    "limit": {
      "maximum": 50,
      "minimum": 1,
      "title": "Limit",
      "type": "integer"
    },
    "next_offset": {
      "anyOf": [
        {
          "minimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Next Offset"
    },
    "offset": {
      "minimum": 0,
      "title": "Offset",
      "type": "integer"
    },
    "origins": {
      "items": {
        "$ref": "#/$defs/OriginOutcome"
      },
      "maxItems": 50,
      "title": "Origins",
      "type": "array"
    }
  },
  "required": [
    "backtest_id",
    "origins",
    "offset",
    "limit"
  ],
  "title": "OriginPage",
  "type": "object"
} as const;

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

export const candidateRequestSchema = {
  "additionalProperties": false,
  "properties": {
    "reason": {
      "minLength": 1,
      "title": "Reason",
      "type": "string"
    },
    "selection_method": {
      "default": "prespecified_holdout",
      "enum": [
        "prespecified_holdout",
        "exploratory",
        "corrected"
      ],
      "title": "Selection Method",
      "type": "string"
    },
    "source_ids": {
      "items": {
        "minLength": 1,
        "type": "string"
      },
      "title": "Source Ids",
      "type": "array"
    },
    "template_id": {
      "minLength": 1,
      "title": "Template Id",
      "type": "string"
    }
  },
  "required": [
    "template_id",
    "source_ids",
    "reason"
  ],
  "title": "CandidateRequest",
  "type": "object"
} as const;

export namespace CandidateRequestGenerated {
  export type Reason = string;
  export type SelectionMethod = "prespecified_holdout" | "exploratory" | "corrected";
  export type SourceIds = string[];
  export type TemplateId = string;

  export interface CandidateRequest {
    reason: Reason;
    selection_method?: SelectionMethod;
    source_ids: SourceIds;
    template_id: TemplateId;
  }
}
export type CandidateRequest = CandidateRequestGenerated.CandidateRequest;

export const candidateSchema = {
  "$defs": {
    "CandidateCostEstimate": {
      "additionalProperties": false,
      "description": "Static execution work, not a latency or monetary quote.\n\nUnknown/unsupported execution has no numeric value; zero is never a stand-in\nfor an unavailable estimate. The compiler owns the estimate and its basis.",
      "properties": {
        "basis": {
          "default": "not_estimated",
          "minLength": 1,
          "title": "Basis",
          "type": "string"
        },
        "status": {
          "default": "unavailable",
          "enum": [
            "known",
            "unavailable"
          ],
          "title": "Status",
          "type": "string"
        },
        "unit": {
          "const": "provider_calls_per_run",
          "default": "provider_calls_per_run",
          "title": "Unit",
          "type": "string"
        },
        "value": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Value"
        }
      },
      "title": "CandidateCostEstimate",
      "type": "object"
    },
    "GraphSpec": {
      "additionalProperties": false,
      "properties": {
        "graph_id": {
          "minLength": 1,
          "title": "Graph Id",
          "type": "string"
        },
        "nodes": {
          "items": {
            "$ref": "#/$defs/Node"
          },
          "title": "Nodes",
          "type": "array"
        },
        "version": {
          "title": "Version",
          "type": "integer"
        }
      },
      "required": [
        "graph_id",
        "version",
        "nodes"
      ],
      "title": "GraphSpec",
      "type": "object"
    },
    "JsonValue": {},
    "Node": {
      "additionalProperties": false,
      "properties": {
        "config": {
          "additionalProperties": true,
          "title": "Config",
          "type": "object"
        },
        "inputs": {
          "items": {
            "minLength": 1,
            "type": "string"
          },
          "title": "Inputs",
          "type": "array"
        },
        "kind": {
          "enum": [
            "source",
            "forecast",
            "transform",
            "event"
          ],
          "title": "Kind",
          "type": "string"
        },
        "node_id": {
          "minLength": 1,
          "title": "Node Id",
          "type": "string"
        }
      },
      "required": [
        "node_id",
        "kind",
        "inputs",
        "config"
      ],
      "title": "Node",
      "type": "object"
    },
    "SourceField": {
      "additionalProperties": false,
      "properties": {
        "data_type": {
          "enum": [
            "string",
            "integer",
            "number",
            "boolean",
            "datetime",
            "null",
            "mixed"
          ],
          "title": "Data Type",
          "type": "string"
        },
        "nullable": {
          "title": "Nullable",
          "type": "boolean"
        }
      },
      "required": [
        "data_type",
        "nullable"
      ],
      "title": "SourceField",
      "type": "object"
    },
    "SourceProfile": {
      "additionalProperties": false,
      "description": "Sanitized agent-facing view, bounded independently of source size.",
      "properties": {
        "assumptions": {
          "items": {
            "type": "string"
          },
          "title": "Assumptions",
          "type": "array"
        },
        "fields": {
          "additionalProperties": {
            "$ref": "#/$defs/SourceField"
          },
          "title": "Fields",
          "type": "object"
        },
        "proposed_mapping": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Proposed Mapping",
          "type": "object"
        },
        "sample_rows": {
          "default": [],
          "items": {
            "additionalProperties": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "boolean"
                },
                {
                  "type": "integer"
                },
                {
                  "type": "number"
                },
                {
                  "type": "null"
                }
              ]
            },
            "type": "object"
          },
          "maxItems": 100,
          "title": "Sample Rows",
          "type": "array"
        },
        "source_id": {
          "minLength": 1,
          "title": "Source Id",
          "type": "string"
        },
        "source_revision": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Source Revision"
        },
        "unresolved": {
          "items": {
            "type": "string"
          },
          "title": "Unresolved",
          "type": "array"
        }
      },
      "required": [
        "source_id",
        "fields",
        "proposed_mapping",
        "unresolved",
        "assumptions"
      ],
      "title": "SourceProfile",
      "type": "object"
    },
    "VerificationProtocol": {
      "additionalProperties": false,
      "description": "Frozen before final evaluation; no post-selection correction is assumed.",
      "properties": {
        "criterion": {
          "default": "mae",
          "enum": [
            "mae",
            "brier"
          ],
          "title": "Criterion",
          "type": "string"
        },
        "reference_node_id": {
          "default": "reference",
          "minLength": 1,
          "title": "Reference Node Id",
          "type": "string"
        },
        "selection_method": {
          "default": "prespecified_holdout",
          "enum": [
            "prespecified_holdout",
            "exploratory",
            "corrected"
          ],
          "title": "Selection Method",
          "type": "string"
        },
        "target_node_id": {
          "default": "question",
          "minLength": 1,
          "title": "Target Node Id",
          "type": "string"
        }
      },
      "title": "VerificationProtocol",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "candidate_id": {
      "minLength": 1,
      "title": "Candidate Id",
      "type": "string"
    },
    "epoch_id": {
      "minLength": 1,
      "title": "Epoch Id",
      "type": "string"
    },
    "estimated_cost": {
      "$ref": "#/$defs/CandidateCostEstimate"
    },
    "executable": {
      "default": false,
      "title": "Executable",
      "type": "boolean"
    },
    "graph": {
      "$ref": "#/$defs/GraphSpec"
    },
    "protocol": {
      "$ref": "#/$defs/VerificationProtocol"
    },
    "protocol_id": {
      "minLength": 1,
      "title": "Protocol Id",
      "type": "string"
    },
    "reason": {
      "minLength": 1,
      "title": "Reason",
      "type": "string"
    },
    "source_ids": {
      "items": {
        "minLength": 1,
        "type": "string"
      },
      "title": "Source Ids",
      "type": "array"
    },
    "source_profiles": {
      "default": [],
      "items": {
        "$ref": "#/$defs/SourceProfile"
      },
      "title": "Source Profiles",
      "type": "array"
    },
    "template_id": {
      "minLength": 1,
      "title": "Template Id",
      "type": "string"
    },
    "unresolved": {
      "default": [],
      "items": {
        "type": "string"
      },
      "title": "Unresolved",
      "type": "array"
    }
  },
  "required": [
    "candidate_id",
    "template_id",
    "source_ids",
    "graph",
    "reason",
    "protocol_id",
    "epoch_id"
  ],
  "title": "Candidate",
  "type": "object"
} as const;

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

export const sourceProfileSchema = {
  "$defs": {
    "JsonValue": {},
    "SourceField": {
      "additionalProperties": false,
      "properties": {
        "data_type": {
          "enum": [
            "string",
            "integer",
            "number",
            "boolean",
            "datetime",
            "null",
            "mixed"
          ],
          "title": "Data Type",
          "type": "string"
        },
        "nullable": {
          "title": "Nullable",
          "type": "boolean"
        }
      },
      "required": [
        "data_type",
        "nullable"
      ],
      "title": "SourceField",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "description": "Sanitized agent-facing view, bounded independently of source size.",
  "properties": {
    "assumptions": {
      "items": {
        "type": "string"
      },
      "title": "Assumptions",
      "type": "array"
    },
    "fields": {
      "additionalProperties": {
        "$ref": "#/$defs/SourceField"
      },
      "title": "Fields",
      "type": "object"
    },
    "proposed_mapping": {
      "additionalProperties": {
        "$ref": "#/$defs/JsonValue"
      },
      "title": "Proposed Mapping",
      "type": "object"
    },
    "sample_rows": {
      "default": [],
      "items": {
        "additionalProperties": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "boolean"
            },
            {
              "type": "integer"
            },
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ]
        },
        "type": "object"
      },
      "maxItems": 100,
      "title": "Sample Rows",
      "type": "array"
    },
    "source_id": {
      "minLength": 1,
      "title": "Source Id",
      "type": "string"
    },
    "source_revision": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Source Revision"
    },
    "unresolved": {
      "items": {
        "type": "string"
      },
      "title": "Unresolved",
      "type": "array"
    }
  },
  "required": [
    "source_id",
    "fields",
    "proposed_mapping",
    "unresolved",
    "assumptions"
  ],
  "title": "SourceProfile",
  "type": "object"
} as const;

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

export const runRecordSchema = {
  "$defs": {
    "ForecastResult": {
      "additionalProperties": false,
      "properties": {
        "assumptions": {
          "items": {
            "type": "string"
          },
          "title": "Assumptions",
          "type": "array"
        },
        "paths": {
          "anyOf": [
            {
              "items": {
                "items": {
                  "items": {
                    "type": "number"
                  },
                  "type": "array"
                },
                "type": "array"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "title": "Paths"
        },
        "point": {
          "anyOf": [
            {
              "items": {
                "items": {
                  "type": "number"
                },
                "type": "array"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "title": "Point"
        },
        "provider_id": {
          "minLength": 1,
          "title": "Provider Id",
          "type": "string"
        },
        "provider_revision": {
          "minLength": 1,
          "title": "Provider Revision",
          "type": "string"
        },
        "quantiles": {
          "anyOf": [
            {
              "additionalProperties": {
                "items": {
                  "items": {
                    "type": "number"
                  },
                  "type": "array"
                },
                "type": "array"
              },
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "title": "Quantiles"
        },
        "sample_group_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Sample Group Id"
        },
        "series_ids": {
          "items": {
            "minLength": 1,
            "type": "string"
          },
          "title": "Series Ids",
          "type": "array"
        },
        "timestamps": {
          "items": {
            "format": "date-time",
            "type": "string"
          },
          "title": "Timestamps",
          "type": "array"
        },
        "units": {
          "items": {
            "minLength": 1,
            "type": "string"
          },
          "title": "Units",
          "type": "array"
        }
      },
      "required": [
        "provider_id",
        "provider_revision",
        "series_ids",
        "timestamps",
        "units",
        "point",
        "quantiles",
        "paths",
        "sample_group_id",
        "assumptions"
      ],
      "title": "ForecastResult",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "actual_provider": {
      "additionalProperties": {
        "minLength": 1,
        "type": "string"
      },
      "propertyNames": {
        "minLength": 1
      },
      "title": "Actual Provider",
      "type": "object"
    },
    "as_of": {
      "format": "date-time",
      "title": "As Of",
      "type": "string"
    },
    "evidence_ids": {
      "items": {
        "minLength": 1,
        "type": "string"
      },
      "title": "Evidence Ids",
      "type": "array"
    },
    "graph_id": {
      "minLength": 1,
      "title": "Graph Id",
      "type": "string"
    },
    "graph_version": {
      "title": "Graph Version",
      "type": "integer"
    },
    "parent_run_id": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Parent Run Id"
    },
    "primary_node_id": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Primary Node Id"
    },
    "requested_provider": {
      "additionalProperties": {
        "minLength": 1,
        "type": "string"
      },
      "propertyNames": {
        "minLength": 1
      },
      "title": "Requested Provider",
      "type": "object"
    },
    "results": {
      "additionalProperties": {
        "$ref": "#/$defs/ForecastResult"
      },
      "propertyNames": {
        "minLength": 1
      },
      "title": "Results",
      "type": "object"
    },
    "run_id": {
      "minLength": 1,
      "title": "Run Id",
      "type": "string"
    },
    "scenario_id": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Scenario Id"
    },
    "snapshot_ids": {
      "items": {
        "minLength": 1,
        "type": "string"
      },
      "title": "Snapshot Ids",
      "type": "array"
    },
    "state": {
      "minLength": 1,
      "title": "State",
      "type": "string"
    }
  },
  "required": [
    "run_id",
    "graph_id",
    "graph_version",
    "as_of",
    "snapshot_ids",
    "requested_provider",
    "actual_provider",
    "state",
    "results",
    "evidence_ids",
    "scenario_id",
    "parent_run_id"
  ],
  "title": "RunRecord",
  "type": "object"
} as const;

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

export const agentOperationRequestSchema = {
  "additionalProperties": false,
  "properties": {
    "call_key": {
      "minLength": 1,
      "title": "Call Key",
      "type": "string"
    },
    "epoch_id": {
      "minLength": 1,
      "title": "Epoch Id",
      "type": "string"
    },
    "input": {
      "additionalProperties": {
        "$ref": "#/$defs/JsonValue"
      },
      "title": "Input",
      "type": "object"
    },
    "job_id": {
      "minLength": 1,
      "title": "Job Id",
      "type": "string"
    },
    "session_id": {
      "minLength": 1,
      "title": "Session Id",
      "type": "string"
    },
    "tool": {
      "enum": [
        "inspectSource",
        "proposeCandidates",
        "explainRun"
      ],
      "title": "Tool",
      "type": "string"
    }
  },
  "required": [
    "job_id",
    "epoch_id",
    "session_id",
    "call_key",
    "tool"
  ],
  "title": "AgentOperationRequest",
  "type": "object",
  "$defs": {
    "JsonValue": {}
  }
} as const;

export namespace AgentOperationRequestGenerated {
  export type CallKey = string;
  export type EpochId = string;
  export type JsonValue = unknown;
  export type JobId = string;
  export type SessionId = string;
  export type Tool = "inspectSource" | "proposeCandidates" | "explainRun";

  export interface AgentOperationRequest {
    call_key: CallKey;
    epoch_id: EpochId;
    input?: Input;
    job_id: JobId;
    session_id: SessionId;
    tool: Tool;
  }
  export interface Input {
    [k: string]: JsonValue;
  }
}
export type AgentOperationRequest = AgentOperationRequestGenerated.AgentOperationRequest;

export const agentOperationResponseSchema = {
  "additionalProperties": false,
  "properties": {
    "operation_id": {
      "minLength": 1,
      "title": "Operation Id",
      "type": "string"
    },
    "result": {
      "additionalProperties": {
        "$ref": "#/$defs/JsonValue"
      },
      "title": "Result",
      "type": "object"
    }
  },
  "required": [
    "operation_id",
    "result"
  ],
  "title": "AgentOperationResponse",
  "type": "object",
  "$defs": {
    "JsonValue": {}
  }
} as const;

export namespace AgentOperationResponseGenerated {
  export type OperationId = string;
  export type JsonValue = unknown;

  export interface AgentOperationResponse {
    operation_id: OperationId;
    result: Result;
  }
  export interface Result {
    [k: string]: JsonValue;
  }
}
export type AgentOperationResponse = AgentOperationResponseGenerated.AgentOperationResponse;

export const questionCreateRequestSchema = {
  "$defs": {
    "JsonValue": {},
    "QuestionForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "QuestionForecastSelection",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "key": {
      "minLength": 1,
      "title": "Key",
      "type": "string"
    },
    "meaning": {
      "maxLength": 1000,
      "minLength": 1,
      "title": "Meaning",
      "type": "string"
    },
    "selection": {
      "$ref": "#/$defs/QuestionForecastSelection"
    },
    "source_ids": {
      "default": [],
      "items": {
        "maxLength": 128,
        "minLength": 1,
        "type": "string"
      },
      "maxItems": 16,
      "title": "Source Ids",
      "type": "array"
    },
    "title": {
      "maxLength": 128,
      "minLength": 1,
      "title": "Title",
      "type": "string"
    }
  },
  "required": [
    "key",
    "title",
    "meaning",
    "selection"
  ],
  "title": "QuestionCreateRequest",
  "type": "object"
} as const;

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

export const questionRevisionRequestSchema = {
  "$defs": {
    "JsonValue": {},
    "QuestionForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "QuestionForecastSelection",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "expected_revision": {
      "minimum": 1,
      "title": "Expected Revision",
      "type": "integer"
    },
    "key": {
      "minLength": 1,
      "title": "Key",
      "type": "string"
    },
    "meaning": {
      "maxLength": 1000,
      "minLength": 1,
      "title": "Meaning",
      "type": "string"
    },
    "selection": {
      "$ref": "#/$defs/QuestionForecastSelection"
    },
    "source_ids": {
      "default": [],
      "items": {
        "maxLength": 128,
        "minLength": 1,
        "type": "string"
      },
      "maxItems": 16,
      "title": "Source Ids",
      "type": "array"
    }
  },
  "required": [
    "key",
    "expected_revision",
    "meaning",
    "selection"
  ],
  "title": "QuestionRevisionRequest",
  "type": "object"
} as const;

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

export const questionTitlePatchSchema = {
  "additionalProperties": false,
  "properties": {
    "status": {
      "anyOf": [
        {
          "enum": [
            "open",
            "paused",
            "resolved"
          ],
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Status"
    },
    "title": {
      "anyOf": [
        {
          "maxLength": 128,
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Title"
    }
  },
  "title": "QuestionTitlePatch",
  "type": "object"
} as const;

export namespace QuestionTitlePatchGenerated {
  export type Status = ("open" | "paused" | "resolved") | null;
  export type Title = string | null;

  export interface QuestionTitlePatch {
    status?: Status;
    title?: Title;
  }
}
export type QuestionTitlePatch = QuestionTitlePatchGenerated.QuestionTitlePatch;

export const questionRevisionSchema = {
  "$defs": {
    "JsonValue": {},
    "QuestionForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "QuestionForecastSelection",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "created_at": {
      "format": "date-time",
      "title": "Created At",
      "type": "string"
    },
    "meaning": {
      "maxLength": 1000,
      "minLength": 1,
      "title": "Meaning",
      "type": "string"
    },
    "question_id": {
      "minLength": 1,
      "title": "Question Id",
      "type": "string"
    },
    "revision": {
      "minimum": 1,
      "title": "Revision",
      "type": "integer"
    },
    "selection": {
      "$ref": "#/$defs/QuestionForecastSelection"
    },
    "source_ids": {
      "items": {
        "maxLength": 128,
        "minLength": 1,
        "type": "string"
      },
      "maxItems": 16,
      "title": "Source Ids",
      "type": "array"
    }
  },
  "required": [
    "question_id",
    "revision",
    "meaning",
    "source_ids",
    "selection",
    "created_at"
  ],
  "title": "QuestionRevision",
  "type": "object"
} as const;

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

export const questionViewSchema = {
  "$defs": {
    "JsonValue": {},
    "QuestionForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "QuestionForecastSelection",
      "type": "object"
    },
    "QuestionRevision": {
      "additionalProperties": false,
      "properties": {
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "meaning": {
          "maxLength": 1000,
          "minLength": 1,
          "title": "Meaning",
          "type": "string"
        },
        "question_id": {
          "minLength": 1,
          "title": "Question Id",
          "type": "string"
        },
        "revision": {
          "minimum": 1,
          "title": "Revision",
          "type": "integer"
        },
        "selection": {
          "$ref": "#/$defs/QuestionForecastSelection"
        },
        "source_ids": {
          "items": {
            "maxLength": 128,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 16,
          "title": "Source Ids",
          "type": "array"
        }
      },
      "required": [
        "question_id",
        "revision",
        "meaning",
        "source_ids",
        "selection",
        "created_at"
      ],
      "title": "QuestionRevision",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "created_at": {
      "format": "date-time",
      "title": "Created At",
      "type": "string"
    },
    "current_revision": {
      "minimum": 1,
      "title": "Current Revision",
      "type": "integer"
    },
    "question_id": {
      "minLength": 1,
      "title": "Question Id",
      "type": "string"
    },
    "reference_count": {
      "minimum": 0,
      "title": "Reference Count",
      "type": "integer"
    },
    "revision": {
      "$ref": "#/$defs/QuestionRevision"
    },
    "revision_count": {
      "minimum": 1,
      "title": "Revision Count",
      "type": "integer"
    },
    "status": {
      "enum": [
        "open",
        "paused",
        "resolved"
      ],
      "title": "Status",
      "type": "string"
    },
    "title": {
      "minLength": 1,
      "title": "Title",
      "type": "string"
    },
    "updated_at": {
      "format": "date-time",
      "title": "Updated At",
      "type": "string"
    }
  },
  "required": [
    "question_id",
    "title",
    "status",
    "current_revision",
    "revision",
    "revision_count",
    "reference_count",
    "created_at",
    "updated_at"
  ],
  "title": "QuestionView",
  "type": "object"
} as const;

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

export const questionReferenceRequestSchema = {
  "additionalProperties": false,
  "properties": {
    "key": {
      "minLength": 1,
      "title": "Key",
      "type": "string"
    },
    "note": {
      "default": "",
      "maxLength": 800,
      "title": "Note",
      "type": "string"
    },
    "revision": {
      "minimum": 1,
      "title": "Revision",
      "type": "integer"
    },
    "target_id": {
      "maxLength": 128,
      "minLength": 1,
      "title": "Target Id",
      "type": "string"
    },
    "target_type": {
      "enum": [
        "candidate",
        "run",
        "backtest",
        "watch",
        "evaluation",
        "operation"
      ],
      "title": "Target Type",
      "type": "string"
    }
  },
  "required": [
    "key",
    "revision",
    "target_type",
    "target_id"
  ],
  "title": "QuestionReferenceRequest",
  "type": "object"
} as const;

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

export const questionReferenceSchema = {
  "additionalProperties": false,
  "properties": {
    "created_at": {
      "format": "date-time",
      "title": "Created At",
      "type": "string"
    },
    "note": {
      "maxLength": 800,
      "title": "Note",
      "type": "string"
    },
    "question_id": {
      "minLength": 1,
      "title": "Question Id",
      "type": "string"
    },
    "reference_id": {
      "minLength": 1,
      "title": "Reference Id",
      "type": "string"
    },
    "revision": {
      "minimum": 1,
      "title": "Revision",
      "type": "integer"
    },
    "target_id": {
      "maxLength": 128,
      "minLength": 1,
      "title": "Target Id",
      "type": "string"
    },
    "target_type": {
      "enum": [
        "candidate",
        "run",
        "backtest",
        "watch",
        "evaluation",
        "operation"
      ],
      "title": "Target Type",
      "type": "string"
    }
  },
  "required": [
    "reference_id",
    "question_id",
    "revision",
    "target_type",
    "target_id",
    "note",
    "created_at"
  ],
  "title": "QuestionReference",
  "type": "object"
} as const;

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

export const questionPageSchema = {
  "$defs": {
    "JsonValue": {},
    "QuestionForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "QuestionForecastSelection",
      "type": "object"
    },
    "QuestionRevision": {
      "additionalProperties": false,
      "properties": {
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "meaning": {
          "maxLength": 1000,
          "minLength": 1,
          "title": "Meaning",
          "type": "string"
        },
        "question_id": {
          "minLength": 1,
          "title": "Question Id",
          "type": "string"
        },
        "revision": {
          "minimum": 1,
          "title": "Revision",
          "type": "integer"
        },
        "selection": {
          "$ref": "#/$defs/QuestionForecastSelection"
        },
        "source_ids": {
          "items": {
            "maxLength": 128,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 16,
          "title": "Source Ids",
          "type": "array"
        }
      },
      "required": [
        "question_id",
        "revision",
        "meaning",
        "source_ids",
        "selection",
        "created_at"
      ],
      "title": "QuestionRevision",
      "type": "object"
    },
    "QuestionView": {
      "additionalProperties": false,
      "properties": {
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "current_revision": {
          "minimum": 1,
          "title": "Current Revision",
          "type": "integer"
        },
        "question_id": {
          "minLength": 1,
          "title": "Question Id",
          "type": "string"
        },
        "reference_count": {
          "minimum": 0,
          "title": "Reference Count",
          "type": "integer"
        },
        "revision": {
          "$ref": "#/$defs/QuestionRevision"
        },
        "revision_count": {
          "minimum": 1,
          "title": "Revision Count",
          "type": "integer"
        },
        "status": {
          "enum": [
            "open",
            "paused",
            "resolved"
          ],
          "title": "Status",
          "type": "string"
        },
        "title": {
          "minLength": 1,
          "title": "Title",
          "type": "string"
        },
        "updated_at": {
          "format": "date-time",
          "title": "Updated At",
          "type": "string"
        }
      },
      "required": [
        "question_id",
        "title",
        "status",
        "current_revision",
        "revision",
        "revision_count",
        "reference_count",
        "created_at",
        "updated_at"
      ],
      "title": "QuestionView",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "next_offset": {
      "anyOf": [
        {
          "minimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Next Offset"
    },
    "questions": {
      "items": {
        "$ref": "#/$defs/QuestionView"
      },
      "title": "Questions",
      "type": "array"
    }
  },
  "required": [
    "questions",
    "next_offset"
  ],
  "title": "QuestionPage",
  "type": "object"
} as const;

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

export const questionRevisionPageSchema = {
  "$defs": {
    "JsonValue": {},
    "QuestionForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "QuestionForecastSelection",
      "type": "object"
    },
    "QuestionRevision": {
      "additionalProperties": false,
      "properties": {
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "meaning": {
          "maxLength": 1000,
          "minLength": 1,
          "title": "Meaning",
          "type": "string"
        },
        "question_id": {
          "minLength": 1,
          "title": "Question Id",
          "type": "string"
        },
        "revision": {
          "minimum": 1,
          "title": "Revision",
          "type": "integer"
        },
        "selection": {
          "$ref": "#/$defs/QuestionForecastSelection"
        },
        "source_ids": {
          "items": {
            "maxLength": 128,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 16,
          "title": "Source Ids",
          "type": "array"
        }
      },
      "required": [
        "question_id",
        "revision",
        "meaning",
        "source_ids",
        "selection",
        "created_at"
      ],
      "title": "QuestionRevision",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "next_offset": {
      "anyOf": [
        {
          "minimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Next Offset"
    },
    "revisions": {
      "items": {
        "$ref": "#/$defs/QuestionRevision"
      },
      "title": "Revisions",
      "type": "array"
    }
  },
  "required": [
    "revisions",
    "next_offset"
  ],
  "title": "QuestionRevisionPage",
  "type": "object"
} as const;

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

export const questionReferencePageSchema = {
  "$defs": {
    "QuestionReference": {
      "additionalProperties": false,
      "properties": {
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "note": {
          "maxLength": 800,
          "title": "Note",
          "type": "string"
        },
        "question_id": {
          "minLength": 1,
          "title": "Question Id",
          "type": "string"
        },
        "reference_id": {
          "minLength": 1,
          "title": "Reference Id",
          "type": "string"
        },
        "revision": {
          "minimum": 1,
          "title": "Revision",
          "type": "integer"
        },
        "target_id": {
          "maxLength": 128,
          "minLength": 1,
          "title": "Target Id",
          "type": "string"
        },
        "target_type": {
          "enum": [
            "candidate",
            "run",
            "backtest",
            "watch",
            "evaluation",
            "operation"
          ],
          "title": "Target Type",
          "type": "string"
        }
      },
      "required": [
        "reference_id",
        "question_id",
        "revision",
        "target_type",
        "target_id",
        "note",
        "created_at"
      ],
      "title": "QuestionReference",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "next_offset": {
      "anyOf": [
        {
          "minimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Next Offset"
    },
    "references": {
      "items": {
        "$ref": "#/$defs/QuestionReference"
      },
      "title": "References",
      "type": "array"
    }
  },
  "required": [
    "references",
    "next_offset"
  ],
  "title": "QuestionReferencePage",
  "type": "object"
} as const;

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

export const operationCreateRequestSchema = {
  "additionalProperties": false,
  "properties": {
    "key": {
      "minLength": 1,
      "title": "Key",
      "type": "string"
    },
    "missing_data": {
      "default": [],
      "items": {
        "maxLength": 128,
        "minLength": 1,
        "type": "string"
      },
      "maxItems": 32,
      "title": "Missing Data",
      "type": "array"
    },
    "phase": {
      "default": "collecting",
      "enum": [
        "collecting",
        "ready"
      ],
      "title": "Phase",
      "type": "string"
    },
    "question_id": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Question Id"
    },
    "question_revision": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Question Revision"
    }
  },
  "required": [
    "key"
  ],
  "title": "OperationCreateRequest",
  "type": "object"
} as const;

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

export const operationUpdateRequestSchema = {
  "additionalProperties": false,
  "properties": {
    "expected_version": {
      "minimum": 1,
      "title": "Expected Version",
      "type": "integer"
    },
    "key": {
      "minLength": 1,
      "title": "Key",
      "type": "string"
    },
    "missing_data": {
      "default": [],
      "items": {
        "maxLength": 128,
        "minLength": 1,
        "type": "string"
      },
      "maxItems": 32,
      "title": "Missing Data",
      "type": "array"
    },
    "phase": {
      "enum": [
        "collecting",
        "ready"
      ],
      "title": "Phase",
      "type": "string"
    }
  },
  "required": [
    "key",
    "expected_version",
    "phase"
  ],
  "title": "OperationUpdateRequest",
  "type": "object"
} as const;

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

export const operationSubmitRequestSchema = {
  "$defs": {
    "BacktestJobRequest": {
      "additionalProperties": false,
      "properties": {
        "key": {
          "minLength": 1,
          "title": "Key",
          "type": "string"
        },
        "kind": {
          "const": "backtest",
          "title": "Kind",
          "type": "string"
        },
        "selection": {
          "$ref": "#/$defs/ForecastSelection"
        },
        "settings": {
          "$ref": "#/$defs/BacktestSettings"
        },
        "source_id": {
          "minLength": 1,
          "title": "Source Id",
          "type": "string"
        },
        "watch_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Watch Id"
        }
      },
      "required": [
        "kind",
        "key",
        "source_id",
        "selection"
      ],
      "title": "BacktestJobRequest",
      "type": "object"
    },
    "BacktestSettings": {
      "additionalProperties": false,
      "properties": {
        "max_origins_per_partition": {
          "default": 10,
          "maximum": 50,
          "minimum": 1,
          "title": "Max Origins Per Partition",
          "type": "integer"
        },
        "origin_offset_seconds": {
          "default": 0,
          "minimum": 0,
          "title": "Origin Offset Seconds",
          "type": "integer"
        }
      },
      "title": "BacktestSettings",
      "type": "object"
    },
    "ConfiguredRunJobRequest": {
      "additionalProperties": false,
      "properties": {
        "key": {
          "minLength": 1,
          "title": "Key",
          "type": "string"
        },
        "kind": {
          "const": "configured_run",
          "title": "Kind",
          "type": "string"
        },
        "selection": {
          "$ref": "#/$defs/ForecastSelection"
        },
        "snapshot_id": {
          "minLength": 1,
          "title": "Snapshot Id",
          "type": "string"
        },
        "source_id": {
          "minLength": 1,
          "title": "Source Id",
          "type": "string"
        }
      },
      "required": [
        "kind",
        "key",
        "source_id",
        "snapshot_id",
        "selection"
      ],
      "title": "ConfiguredRunJobRequest",
      "type": "object"
    },
    "EvaluationJobRequest": {
      "additionalProperties": false,
      "properties": {
        "actuals_snapshot_id": {
          "minLength": 1,
          "title": "Actuals Snapshot Id",
          "type": "string"
        },
        "key": {
          "minLength": 1,
          "title": "Key",
          "type": "string"
        },
        "kind": {
          "const": "evaluation",
          "title": "Kind",
          "type": "string"
        },
        "run_id": {
          "minLength": 1,
          "title": "Run Id",
          "type": "string"
        }
      },
      "required": [
        "kind",
        "key",
        "run_id",
        "actuals_snapshot_id"
      ],
      "title": "EvaluationJobRequest",
      "type": "object"
    },
    "ForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "ForecastSelection",
      "type": "object"
    },
    "GraphSpec": {
      "additionalProperties": false,
      "properties": {
        "graph_id": {
          "minLength": 1,
          "title": "Graph Id",
          "type": "string"
        },
        "nodes": {
          "items": {
            "$ref": "#/$defs/Node"
          },
          "title": "Nodes",
          "type": "array"
        },
        "version": {
          "title": "Version",
          "type": "integer"
        }
      },
      "required": [
        "graph_id",
        "version",
        "nodes"
      ],
      "title": "GraphSpec",
      "type": "object"
    },
    "JsonValue": {},
    "Node": {
      "additionalProperties": false,
      "properties": {
        "config": {
          "additionalProperties": true,
          "title": "Config",
          "type": "object"
        },
        "inputs": {
          "items": {
            "minLength": 1,
            "type": "string"
          },
          "title": "Inputs",
          "type": "array"
        },
        "kind": {
          "enum": [
            "source",
            "forecast",
            "transform",
            "event"
          ],
          "title": "Kind",
          "type": "string"
        },
        "node_id": {
          "minLength": 1,
          "title": "Node Id",
          "type": "string"
        }
      },
      "required": [
        "node_id",
        "kind",
        "inputs",
        "config"
      ],
      "title": "Node",
      "type": "object"
    },
    "ResumeJobRequest": {
      "additionalProperties": false,
      "properties": {
        "key": {
          "minLength": 1,
          "title": "Key",
          "type": "string"
        },
        "kind": {
          "const": "watch_resume",
          "title": "Kind",
          "type": "string"
        },
        "watch_id": {
          "minLength": 1,
          "title": "Watch Id",
          "type": "string"
        }
      },
      "required": [
        "kind",
        "key",
        "watch_id"
      ],
      "title": "ResumeJobRequest",
      "type": "object"
    },
    "RunJobRequest": {
      "additionalProperties": false,
      "properties": {
        "as_of": {
          "format": "date-time",
          "title": "As Of",
          "type": "string"
        },
        "graph": {
          "$ref": "#/$defs/GraphSpec"
        },
        "key": {
          "minLength": 1,
          "title": "Key",
          "type": "string"
        },
        "kind": {
          "const": "run",
          "title": "Kind",
          "type": "string"
        },
        "previous_run_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Previous Run Id"
        },
        "primary_node_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Primary Node Id"
        },
        "snapshot_ids": {
          "additionalProperties": {
            "minLength": 1,
            "type": "string"
          },
          "propertyNames": {
            "minLength": 1
          },
          "title": "Snapshot Ids",
          "type": "object"
        }
      },
      "required": [
        "kind",
        "key",
        "graph",
        "snapshot_ids",
        "as_of"
      ],
      "title": "RunJobRequest",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "candidate_id": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Candidate Id"
    },
    "expected_version": {
      "minimum": 1,
      "title": "Expected Version",
      "type": "integer"
    },
    "request": {
      "discriminator": {
        "mapping": {
          "backtest": "#/$defs/BacktestJobRequest",
          "configured_run": "#/$defs/ConfiguredRunJobRequest",
          "evaluation": "#/$defs/EvaluationJobRequest",
          "run": "#/$defs/RunJobRequest",
          "watch_resume": "#/$defs/ResumeJobRequest"
        },
        "propertyName": "kind"
      },
      "oneOf": [
        {
          "$ref": "#/$defs/RunJobRequest"
        },
        {
          "$ref": "#/$defs/ConfiguredRunJobRequest"
        },
        {
          "$ref": "#/$defs/BacktestJobRequest"
        },
        {
          "$ref": "#/$defs/EvaluationJobRequest"
        },
        {
          "$ref": "#/$defs/ResumeJobRequest"
        }
      ],
      "title": "Request"
    }
  },
  "required": [
    "expected_version",
    "request"
  ],
  "title": "OperationSubmitRequest",
  "type": "object"
} as const;

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

export const operationViewSchema = {
  "additionalProperties": false,
  "properties": {
    "created_at": {
      "format": "date-time",
      "title": "Created At",
      "type": "string"
    },
    "job_error": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Job Error"
    },
    "job_id": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Job Id"
    },
    "job_state": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Job State"
    },
    "missing_data": {
      "items": {
        "minLength": 1,
        "type": "string"
      },
      "title": "Missing Data",
      "type": "array"
    },
    "operation_id": {
      "minLength": 1,
      "title": "Operation Id",
      "type": "string"
    },
    "phase": {
      "enum": [
        "collecting",
        "ready"
      ],
      "title": "Phase",
      "type": "string"
    },
    "question_id": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Question Id"
    },
    "question_revision": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Question Revision"
    },
    "request_digest": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Request Digest"
    },
    "request_kind": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Request Kind"
    },
    "source_ids": {
      "items": {
        "maxLength": 128,
        "minLength": 1,
        "type": "string"
      },
      "maxItems": 16,
      "title": "Source Ids",
      "type": "array"
    },
    "state": {
      "enum": [
        "open",
        "reserved",
        "submitted",
        "completed",
        "failed"
      ],
      "title": "State",
      "type": "string"
    },
    "updated_at": {
      "format": "date-time",
      "title": "Updated At",
      "type": "string"
    },
    "version": {
      "minimum": 1,
      "title": "Version",
      "type": "integer"
    }
  },
  "required": [
    "operation_id",
    "question_id",
    "question_revision",
    "version",
    "phase",
    "state",
    "missing_data",
    "request_kind",
    "request_digest",
    "source_ids",
    "job_id",
    "job_state",
    "job_error",
    "created_at",
    "updated_at"
  ],
  "title": "OperationView",
  "type": "object"
} as const;

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

export const operationPageSchema = {
  "$defs": {
    "OperationView": {
      "additionalProperties": false,
      "properties": {
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "job_error": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "title": "Job Error"
        },
        "job_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Job Id"
        },
        "job_state": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Job State"
        },
        "missing_data": {
          "items": {
            "minLength": 1,
            "type": "string"
          },
          "title": "Missing Data",
          "type": "array"
        },
        "operation_id": {
          "minLength": 1,
          "title": "Operation Id",
          "type": "string"
        },
        "phase": {
          "enum": [
            "collecting",
            "ready"
          ],
          "title": "Phase",
          "type": "string"
        },
        "question_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Question Id"
        },
        "question_revision": {
          "anyOf": [
            {
              "minimum": 1,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Question Revision"
        },
        "request_digest": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Request Digest"
        },
        "request_kind": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Request Kind"
        },
        "source_ids": {
          "items": {
            "maxLength": 128,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 16,
          "title": "Source Ids",
          "type": "array"
        },
        "state": {
          "enum": [
            "open",
            "reserved",
            "submitted",
            "completed",
            "failed"
          ],
          "title": "State",
          "type": "string"
        },
        "updated_at": {
          "format": "date-time",
          "title": "Updated At",
          "type": "string"
        },
        "version": {
          "minimum": 1,
          "title": "Version",
          "type": "integer"
        }
      },
      "required": [
        "operation_id",
        "question_id",
        "question_revision",
        "version",
        "phase",
        "state",
        "missing_data",
        "request_kind",
        "request_digest",
        "source_ids",
        "job_id",
        "job_state",
        "job_error",
        "created_at",
        "updated_at"
      ],
      "title": "OperationView",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "next_offset": {
      "anyOf": [
        {
          "minimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Next Offset"
    },
    "operations": {
      "items": {
        "$ref": "#/$defs/OperationView"
      },
      "title": "Operations",
      "type": "array"
    }
  },
  "required": [
    "operations",
    "next_offset"
  ],
  "title": "OperationPage",
  "type": "object"
} as const;

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

export const snapshotSummarySchema = {
  "additionalProperties": false,
  "properties": {
    "as_of": {
      "format": "date-time",
      "title": "As Of",
      "type": "string"
    },
    "assumption_count": {
      "minimum": 0,
      "title": "Assumption Count",
      "type": "integer"
    },
    "assumptions": {
      "items": {
        "type": "string"
      },
      "maxItems": 16,
      "title": "Assumptions",
      "type": "array"
    },
    "assumptions_truncated": {
      "title": "Assumptions Truncated",
      "type": "boolean"
    },
    "available_at_end": {
      "anyOf": [
        {
          "format": "date-time",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Available At End"
    },
    "available_at_start": {
      "anyOf": [
        {
          "format": "date-time",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Available At Start"
    },
    "event_time_end": {
      "anyOf": [
        {
          "format": "date-time",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Event Time End"
    },
    "event_time_start": {
      "anyOf": [
        {
          "format": "date-time",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Event Time Start"
    },
    "missing_count": {
      "minimum": 0,
      "title": "Missing Count",
      "type": "integer"
    },
    "observation_count": {
      "minimum": 0,
      "title": "Observation Count",
      "type": "integer"
    },
    "revision_count": {
      "minimum": 0,
      "title": "Revision Count",
      "type": "integer"
    },
    "series_count": {
      "minimum": 0,
      "title": "Series Count",
      "type": "integer"
    },
    "snapshot_id": {
      "minLength": 1,
      "title": "Snapshot Id",
      "type": "string"
    }
  },
  "required": [
    "snapshot_id",
    "as_of",
    "observation_count",
    "series_count",
    "missing_count",
    "revision_count",
    "event_time_start",
    "event_time_end",
    "available_at_start",
    "available_at_end",
    "assumption_count",
    "assumptions",
    "assumptions_truncated"
  ],
  "title": "SnapshotSummary",
  "type": "object"
} as const;

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

export const snapshotSeriesSummarySchema = {
  "additionalProperties": false,
  "properties": {
    "available_at_end": {
      "anyOf": [
        {
          "format": "date-time",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Available At End"
    },
    "available_at_start": {
      "anyOf": [
        {
          "format": "date-time",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Available At Start"
    },
    "event_time_end": {
      "anyOf": [
        {
          "format": "date-time",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Event Time End"
    },
    "event_time_start": {
      "anyOf": [
        {
          "format": "date-time",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Event Time Start"
    },
    "missing_count": {
      "minimum": 0,
      "title": "Missing Count",
      "type": "integer"
    },
    "observation_count": {
      "minimum": 0,
      "title": "Observation Count",
      "type": "integer"
    },
    "revision_count": {
      "minimum": 0,
      "title": "Revision Count",
      "type": "integer"
    },
    "series_id": {
      "minLength": 1,
      "title": "Series Id",
      "type": "string"
    },
    "snapshot_id": {
      "minLength": 1,
      "title": "Snapshot Id",
      "type": "string"
    },
    "unit_count": {
      "minimum": 0,
      "title": "Unit Count",
      "type": "integer"
    },
    "units": {
      "items": {
        "type": "string"
      },
      "maxItems": 8,
      "title": "Units",
      "type": "array"
    },
    "units_truncated": {
      "title": "Units Truncated",
      "type": "boolean"
    }
  },
  "required": [
    "snapshot_id",
    "series_id",
    "observation_count",
    "missing_count",
    "revision_count",
    "unit_count",
    "units",
    "units_truncated",
    "event_time_start",
    "event_time_end",
    "available_at_start",
    "available_at_end"
  ],
  "title": "SnapshotSeriesSummary",
  "type": "object"
} as const;

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

export const snapshotSeriesPageSchema = {
  "$defs": {
    "SnapshotSeriesSummary": {
      "additionalProperties": false,
      "properties": {
        "available_at_end": {
          "anyOf": [
            {
              "format": "date-time",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Available At End"
        },
        "available_at_start": {
          "anyOf": [
            {
              "format": "date-time",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Available At Start"
        },
        "event_time_end": {
          "anyOf": [
            {
              "format": "date-time",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Event Time End"
        },
        "event_time_start": {
          "anyOf": [
            {
              "format": "date-time",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Event Time Start"
        },
        "missing_count": {
          "minimum": 0,
          "title": "Missing Count",
          "type": "integer"
        },
        "observation_count": {
          "minimum": 0,
          "title": "Observation Count",
          "type": "integer"
        },
        "revision_count": {
          "minimum": 0,
          "title": "Revision Count",
          "type": "integer"
        },
        "series_id": {
          "minLength": 1,
          "title": "Series Id",
          "type": "string"
        },
        "snapshot_id": {
          "minLength": 1,
          "title": "Snapshot Id",
          "type": "string"
        },
        "unit_count": {
          "minimum": 0,
          "title": "Unit Count",
          "type": "integer"
        },
        "units": {
          "items": {
            "type": "string"
          },
          "maxItems": 8,
          "title": "Units",
          "type": "array"
        },
        "units_truncated": {
          "title": "Units Truncated",
          "type": "boolean"
        }
      },
      "required": [
        "snapshot_id",
        "series_id",
        "observation_count",
        "missing_count",
        "revision_count",
        "unit_count",
        "units",
        "units_truncated",
        "event_time_start",
        "event_time_end",
        "available_at_start",
        "available_at_end"
      ],
      "title": "SnapshotSeriesSummary",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "next_offset": {
      "anyOf": [
        {
          "minimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Next Offset"
    },
    "series": {
      "items": {
        "$ref": "#/$defs/SnapshotSeriesSummary"
      },
      "title": "Series",
      "type": "array"
    },
    "snapshot_id": {
      "minLength": 1,
      "title": "Snapshot Id",
      "type": "string"
    }
  },
  "required": [
    "snapshot_id",
    "series",
    "next_offset"
  ],
  "title": "SnapshotSeriesPage",
  "type": "object"
} as const;

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

export const forecastPresentationSchema = {
  "$defs": {
    "ForecastPresentationPoint": {
      "additionalProperties": false,
      "properties": {
        "node_id": {
          "minLength": 1,
          "title": "Node Id",
          "type": "string"
        },
        "point": {
          "anyOf": [
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "title": "Point"
        },
        "quantiles": {
          "additionalProperties": {
            "type": "number"
          },
          "maxProperties": 3,
          "title": "Quantiles",
          "type": "object"
        },
        "quantiles_truncated": {
          "title": "Quantiles Truncated",
          "type": "boolean"
        },
        "representation": {
          "enum": [
            "point",
            "marginal_quantiles",
            "joint_paths"
          ],
          "title": "Representation",
          "type": "string"
        },
        "sample_count": {
          "minimum": 0,
          "title": "Sample Count",
          "type": "integer"
        },
        "series_id": {
          "minLength": 1,
          "title": "Series Id",
          "type": "string"
        },
        "timestamp": {
          "format": "date-time",
          "title": "Timestamp",
          "type": "string"
        },
        "unit": {
          "minLength": 1,
          "title": "Unit",
          "type": "string"
        }
      },
      "required": [
        "node_id",
        "series_id",
        "timestamp",
        "unit",
        "representation",
        "point",
        "quantiles",
        "quantiles_truncated",
        "sample_count"
      ],
      "title": "ForecastPresentationPoint",
      "type": "object"
    },
    "ForecastProviderUse": {
      "additionalProperties": false,
      "properties": {
        "actual_provider": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Actual Provider"
        },
        "node_id": {
          "minLength": 1,
          "title": "Node Id",
          "type": "string"
        },
        "requested_provider": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Requested Provider"
        }
      },
      "required": [
        "node_id",
        "requested_provider",
        "actual_provider"
      ],
      "title": "ForecastProviderUse",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "as_of": {
      "format": "date-time",
      "title": "As Of",
      "type": "string"
    },
    "graph_id": {
      "minLength": 1,
      "title": "Graph Id",
      "type": "string"
    },
    "graph_version": {
      "minimum": 1,
      "title": "Graph Version",
      "type": "integer"
    },
    "points": {
      "items": {
        "$ref": "#/$defs/ForecastPresentationPoint"
      },
      "maxItems": 64,
      "title": "Points",
      "type": "array"
    },
    "primary_node_id": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Primary Node Id"
    },
    "providers": {
      "items": {
        "$ref": "#/$defs/ForecastProviderUse"
      },
      "maxItems": 16,
      "title": "Providers",
      "type": "array"
    },
    "providers_truncated": {
      "title": "Providers Truncated",
      "type": "boolean"
    },
    "run_id": {
      "minLength": 1,
      "title": "Run Id",
      "type": "string"
    },
    "schema_version": {
      "const": "forecast-presentation-v1",
      "default": "forecast-presentation-v1",
      "title": "Schema Version",
      "type": "string"
    },
    "snapshot_ids": {
      "items": {
        "minLength": 1,
        "type": "string"
      },
      "maxItems": 16,
      "title": "Snapshot Ids",
      "type": "array"
    },
    "snapshot_ids_truncated": {
      "title": "Snapshot Ids Truncated",
      "type": "boolean"
    },
    "state": {
      "minLength": 1,
      "title": "State",
      "type": "string"
    },
    "total_point_count": {
      "minimum": 0,
      "title": "Total Point Count",
      "type": "integer"
    },
    "truncated": {
      "title": "Truncated",
      "type": "boolean"
    },
    "visual_destination": {
      "const": "time_series",
      "default": "time_series",
      "title": "Visual Destination",
      "type": "string"
    }
  },
  "required": [
    "run_id",
    "graph_id",
    "graph_version",
    "as_of",
    "state",
    "snapshot_ids",
    "snapshot_ids_truncated",
    "providers",
    "providers_truncated",
    "points",
    "total_point_count",
    "truncated"
  ],
  "title": "ForecastPresentation",
  "type": "object"
} as const;

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

export const forecastPresentationPointSchema = {
  "additionalProperties": false,
  "properties": {
    "node_id": {
      "minLength": 1,
      "title": "Node Id",
      "type": "string"
    },
    "point": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "title": "Point"
    },
    "quantiles": {
      "additionalProperties": {
        "type": "number"
      },
      "maxProperties": 3,
      "title": "Quantiles",
      "type": "object"
    },
    "quantiles_truncated": {
      "title": "Quantiles Truncated",
      "type": "boolean"
    },
    "representation": {
      "enum": [
        "point",
        "marginal_quantiles",
        "joint_paths"
      ],
      "title": "Representation",
      "type": "string"
    },
    "sample_count": {
      "minimum": 0,
      "title": "Sample Count",
      "type": "integer"
    },
    "series_id": {
      "minLength": 1,
      "title": "Series Id",
      "type": "string"
    },
    "timestamp": {
      "format": "date-time",
      "title": "Timestamp",
      "type": "string"
    },
    "unit": {
      "minLength": 1,
      "title": "Unit",
      "type": "string"
    }
  },
  "required": [
    "node_id",
    "series_id",
    "timestamp",
    "unit",
    "representation",
    "point",
    "quantiles",
    "quantiles_truncated",
    "sample_count"
  ],
  "title": "ForecastPresentationPoint",
  "type": "object"
} as const;

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

export const forecastProviderUseSchema = {
  "additionalProperties": false,
  "properties": {
    "actual_provider": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Actual Provider"
    },
    "node_id": {
      "minLength": 1,
      "title": "Node Id",
      "type": "string"
    },
    "requested_provider": {
      "anyOf": [
        {
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Requested Provider"
    }
  },
  "required": [
    "node_id",
    "requested_provider",
    "actual_provider"
  ],
  "title": "ForecastProviderUse",
  "type": "object"
} as const;

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

export const backtestPresentationSchema = {
  "$defs": {
    "BacktestSummary": {
      "additionalProperties": false,
      "properties": {
        "assumptions": {
          "items": {
            "type": "string"
          },
          "title": "Assumptions",
          "type": "array"
        },
        "backtest_id": {
          "minLength": 1,
          "title": "Backtest Id",
          "type": "string"
        },
        "captured_at": {
          "format": "date-time",
          "title": "Captured At",
          "type": "string"
        },
        "final_comparison": {
          "enum": [
            "model_lower_mae",
            "model_higher_mae",
            "equal_mae",
            "unavailable"
          ],
          "title": "Final Comparison",
          "type": "string"
        },
        "final_origin_points": {
          "items": {
            "$ref": "#/$defs/FinalOriginPoint"
          },
          "maxItems": 50,
          "title": "Final Origin Points",
          "type": "array"
        },
        "frequency": {
          "minLength": 1,
          "title": "Frequency",
          "type": "string"
        },
        "interpretation_limit": {
          "title": "Interpretation Limit",
          "type": "string"
        },
        "metric_definition": {
          "title": "Metric Definition",
          "type": "string"
        },
        "partitions": {
          "items": {
            "$ref": "#/$defs/PartitionScore"
          },
          "title": "Partitions",
          "type": "array"
        },
        "relative_mae": {
          "anyOf": [
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "title": "Relative Mae"
        },
        "relative_mae_reason": {
          "anyOf": [
            {
              "enum": [
                "no_matched_cells",
                "zero_baseline_mae",
                "ratio_unrepresentable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Relative Mae Reason"
        },
        "report_id": {
          "minLength": 1,
          "title": "Report Id",
          "type": "string"
        },
        "selection": {
          "$ref": "#/$defs/ForecastSelection"
        },
        "source_id": {
          "minLength": 1,
          "title": "Source Id",
          "type": "string"
        },
        "source_revision": {
          "minLength": 1,
          "title": "Source Revision",
          "type": "string"
        },
        "status": {
          "enum": [
            "completed",
            "insufficient_evidence"
          ],
          "title": "Status",
          "type": "string"
        },
        "watch": {
          "anyOf": [
            {
              "$ref": "#/$defs/WatchBacktestSummary"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        }
      },
      "required": [
        "backtest_id",
        "report_id",
        "source_id",
        "source_revision",
        "captured_at",
        "status",
        "selection",
        "frequency",
        "partitions",
        "final_comparison",
        "relative_mae",
        "relative_mae_reason",
        "metric_definition",
        "interpretation_limit",
        "final_origin_points",
        "assumptions"
      ],
      "title": "BacktestSummary",
      "type": "object"
    },
    "FinalOriginPoint": {
      "additionalProperties": false,
      "description": "Chart-ready per-origin scores, never forecast or source values.",
      "properties": {
        "baseline_mae": {
          "anyOf": [
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Baseline Mae"
        },
        "evaluation_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Evaluation Id"
        },
        "model_mae": {
          "anyOf": [
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Model Mae"
        },
        "ordinal": {
          "title": "Ordinal",
          "type": "integer"
        },
        "reason_code": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Reason Code"
        },
        "status": {
          "enum": [
            "evaluated",
            "excluded",
            "failed",
            "insufficient_evidence"
          ],
          "title": "Status",
          "type": "string"
        },
        "target_end": {
          "format": "date-time",
          "title": "Target End",
          "type": "string"
        },
        "target_start": {
          "format": "date-time",
          "title": "Target Start",
          "type": "string"
        }
      },
      "required": [
        "ordinal",
        "target_start",
        "target_end",
        "status"
      ],
      "title": "FinalOriginPoint",
      "type": "object"
    },
    "ForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "ForecastSelection",
      "type": "object"
    },
    "JsonValue": {},
    "PartitionScore": {
      "additionalProperties": false,
      "properties": {
        "baseline_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Baseline Mae"
        },
        "evaluated": {
          "default": 0,
          "minimum": 0,
          "title": "Evaluated",
          "type": "integer"
        },
        "excluded": {
          "default": 0,
          "minimum": 0,
          "title": "Excluded",
          "type": "integer"
        },
        "failed": {
          "default": 0,
          "minimum": 0,
          "title": "Failed",
          "type": "integer"
        },
        "insufficient": {
          "default": 0,
          "minimum": 0,
          "title": "Insufficient",
          "type": "integer"
        },
        "matched_count": {
          "default": 0,
          "minimum": 0,
          "title": "Matched Count",
          "type": "integer"
        },
        "model_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Model Mae"
        },
        "partition": {
          "enum": [
            "exploration",
            "selection",
            "final"
          ],
          "title": "Partition",
          "type": "string"
        },
        "planned": {
          "minimum": 0,
          "title": "Planned",
          "type": "integer"
        },
        "relative_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Relative Mae"
        },
        "relative_mae_reason": {
          "anyOf": [
            {
              "enum": [
                "no_matched_cells",
                "zero_baseline_mae",
                "ratio_unrepresentable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": "no_matched_cells",
          "title": "Relative Mae Reason"
        }
      },
      "required": [
        "partition",
        "planned"
      ],
      "title": "PartitionScore",
      "type": "object"
    },
    "WatchBacktestSummary": {
      "additionalProperties": false,
      "properties": {
        "candidate_invalidated": {
          "title": "Candidate Invalidated",
          "type": "boolean"
        },
        "decision_action": {
          "anyOf": [
            {
              "enum": [
                "activate",
                "provisional",
                "reject"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Decision Action"
        },
        "decision_backtest_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Decision Backtest Id"
        },
        "evidence_applicable": {
          "title": "Evidence Applicable",
          "type": "boolean"
        },
        "final_evaluation_count": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Final Evaluation Count"
        },
        "lifecycle": {
          "enum": [
            "candidate",
            "evaluating",
            "active",
            "paused",
            "unsupported"
          ],
          "title": "Lifecycle",
          "type": "string"
        },
        "linked_to_backtest": {
          "title": "Linked To Backtest",
          "type": "boolean"
        },
        "migration_reason": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Migration Reason"
        },
        "operational": {
          "title": "Operational",
          "type": "boolean"
        },
        "quality": {
          "enum": [
            "provisional",
            "usable",
            "stale",
            "degraded"
          ],
          "title": "Quality",
          "type": "string"
        },
        "reason_codes": {
          "default": [],
          "items": {
            "minLength": 1,
            "type": "string"
          },
          "title": "Reason Codes",
          "type": "array"
        },
        "reevaluation_required": {
          "title": "Reevaluation Required",
          "type": "boolean"
        },
        "watch_id": {
          "minLength": 1,
          "title": "Watch Id",
          "type": "string"
        }
      },
      "required": [
        "watch_id",
        "lifecycle",
        "quality",
        "evidence_applicable",
        "reevaluation_required",
        "candidate_invalidated",
        "operational",
        "linked_to_backtest"
      ],
      "title": "WatchBacktestSummary",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "schema_version": {
      "const": "backtest-presentation-v1",
      "default": "backtest-presentation-v1",
      "title": "Schema Version",
      "type": "string"
    },
    "summary": {
      "$ref": "#/$defs/BacktestSummary"
    },
    "visual_destination": {
      "const": "comparison",
      "default": "comparison",
      "title": "Visual Destination",
      "type": "string"
    }
  },
  "required": [
    "summary"
  ],
  "title": "BacktestPresentation",
  "type": "object"
} as const;

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

export const backtestSummarySchema = {
  "$defs": {
    "FinalOriginPoint": {
      "additionalProperties": false,
      "description": "Chart-ready per-origin scores, never forecast or source values.",
      "properties": {
        "baseline_mae": {
          "anyOf": [
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Baseline Mae"
        },
        "evaluation_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Evaluation Id"
        },
        "model_mae": {
          "anyOf": [
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Model Mae"
        },
        "ordinal": {
          "title": "Ordinal",
          "type": "integer"
        },
        "reason_code": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Reason Code"
        },
        "status": {
          "enum": [
            "evaluated",
            "excluded",
            "failed",
            "insufficient_evidence"
          ],
          "title": "Status",
          "type": "string"
        },
        "target_end": {
          "format": "date-time",
          "title": "Target End",
          "type": "string"
        },
        "target_start": {
          "format": "date-time",
          "title": "Target Start",
          "type": "string"
        }
      },
      "required": [
        "ordinal",
        "target_start",
        "target_end",
        "status"
      ],
      "title": "FinalOriginPoint",
      "type": "object"
    },
    "ForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "ForecastSelection",
      "type": "object"
    },
    "JsonValue": {},
    "PartitionScore": {
      "additionalProperties": false,
      "properties": {
        "baseline_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Baseline Mae"
        },
        "evaluated": {
          "default": 0,
          "minimum": 0,
          "title": "Evaluated",
          "type": "integer"
        },
        "excluded": {
          "default": 0,
          "minimum": 0,
          "title": "Excluded",
          "type": "integer"
        },
        "failed": {
          "default": 0,
          "minimum": 0,
          "title": "Failed",
          "type": "integer"
        },
        "insufficient": {
          "default": 0,
          "minimum": 0,
          "title": "Insufficient",
          "type": "integer"
        },
        "matched_count": {
          "default": 0,
          "minimum": 0,
          "title": "Matched Count",
          "type": "integer"
        },
        "model_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Model Mae"
        },
        "partition": {
          "enum": [
            "exploration",
            "selection",
            "final"
          ],
          "title": "Partition",
          "type": "string"
        },
        "planned": {
          "minimum": 0,
          "title": "Planned",
          "type": "integer"
        },
        "relative_mae": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Relative Mae"
        },
        "relative_mae_reason": {
          "anyOf": [
            {
              "enum": [
                "no_matched_cells",
                "zero_baseline_mae",
                "ratio_unrepresentable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": "no_matched_cells",
          "title": "Relative Mae Reason"
        }
      },
      "required": [
        "partition",
        "planned"
      ],
      "title": "PartitionScore",
      "type": "object"
    },
    "WatchBacktestSummary": {
      "additionalProperties": false,
      "properties": {
        "candidate_invalidated": {
          "title": "Candidate Invalidated",
          "type": "boolean"
        },
        "decision_action": {
          "anyOf": [
            {
              "enum": [
                "activate",
                "provisional",
                "reject"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Decision Action"
        },
        "decision_backtest_id": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Decision Backtest Id"
        },
        "evidence_applicable": {
          "title": "Evidence Applicable",
          "type": "boolean"
        },
        "final_evaluation_count": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Final Evaluation Count"
        },
        "lifecycle": {
          "enum": [
            "candidate",
            "evaluating",
            "active",
            "paused",
            "unsupported"
          ],
          "title": "Lifecycle",
          "type": "string"
        },
        "linked_to_backtest": {
          "title": "Linked To Backtest",
          "type": "boolean"
        },
        "migration_reason": {
          "anyOf": [
            {
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Migration Reason"
        },
        "operational": {
          "title": "Operational",
          "type": "boolean"
        },
        "quality": {
          "enum": [
            "provisional",
            "usable",
            "stale",
            "degraded"
          ],
          "title": "Quality",
          "type": "string"
        },
        "reason_codes": {
          "default": [],
          "items": {
            "minLength": 1,
            "type": "string"
          },
          "title": "Reason Codes",
          "type": "array"
        },
        "reevaluation_required": {
          "title": "Reevaluation Required",
          "type": "boolean"
        },
        "watch_id": {
          "minLength": 1,
          "title": "Watch Id",
          "type": "string"
        }
      },
      "required": [
        "watch_id",
        "lifecycle",
        "quality",
        "evidence_applicable",
        "reevaluation_required",
        "candidate_invalidated",
        "operational",
        "linked_to_backtest"
      ],
      "title": "WatchBacktestSummary",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "assumptions": {
      "items": {
        "type": "string"
      },
      "title": "Assumptions",
      "type": "array"
    },
    "backtest_id": {
      "minLength": 1,
      "title": "Backtest Id",
      "type": "string"
    },
    "captured_at": {
      "format": "date-time",
      "title": "Captured At",
      "type": "string"
    },
    "final_comparison": {
      "enum": [
        "model_lower_mae",
        "model_higher_mae",
        "equal_mae",
        "unavailable"
      ],
      "title": "Final Comparison",
      "type": "string"
    },
    "final_origin_points": {
      "items": {
        "$ref": "#/$defs/FinalOriginPoint"
      },
      "maxItems": 50,
      "title": "Final Origin Points",
      "type": "array"
    },
    "frequency": {
      "minLength": 1,
      "title": "Frequency",
      "type": "string"
    },
    "interpretation_limit": {
      "title": "Interpretation Limit",
      "type": "string"
    },
    "metric_definition": {
      "title": "Metric Definition",
      "type": "string"
    },
    "partitions": {
      "items": {
        "$ref": "#/$defs/PartitionScore"
      },
      "title": "Partitions",
      "type": "array"
    },
    "relative_mae": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "title": "Relative Mae"
    },
    "relative_mae_reason": {
      "anyOf": [
        {
          "enum": [
            "no_matched_cells",
            "zero_baseline_mae",
            "ratio_unrepresentable"
          ],
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Relative Mae Reason"
    },
    "report_id": {
      "minLength": 1,
      "title": "Report Id",
      "type": "string"
    },
    "selection": {
      "$ref": "#/$defs/ForecastSelection"
    },
    "source_id": {
      "minLength": 1,
      "title": "Source Id",
      "type": "string"
    },
    "source_revision": {
      "minLength": 1,
      "title": "Source Revision",
      "type": "string"
    },
    "status": {
      "enum": [
        "completed",
        "insufficient_evidence"
      ],
      "title": "Status",
      "type": "string"
    },
    "watch": {
      "anyOf": [
        {
          "$ref": "#/$defs/WatchBacktestSummary"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    }
  },
  "required": [
    "backtest_id",
    "report_id",
    "source_id",
    "source_revision",
    "captured_at",
    "status",
    "selection",
    "frequency",
    "partitions",
    "final_comparison",
    "relative_mae",
    "relative_mae_reason",
    "metric_definition",
    "interpretation_limit",
    "final_origin_points",
    "assumptions"
  ],
  "title": "BacktestSummary",
  "type": "object"
} as const;

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

export const questionPresentationSchema = {
  "$defs": {
    "JsonValue": {},
    "QuestionForecastSelection": {
      "additionalProperties": false,
      "properties": {
        "baseline_period": {
          "default": 1,
          "maximum": 10000,
          "minimum": 1,
          "title": "Baseline Period",
          "type": "integer"
        },
        "horizon": {
          "maximum": 366,
          "minimum": 1,
          "title": "Horizon",
          "type": "integer"
        },
        "options": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Options",
          "type": "object"
        },
        "provider": {
          "minLength": 1,
          "title": "Provider",
          "type": "string"
        }
      },
      "required": [
        "provider",
        "horizon"
      ],
      "title": "QuestionForecastSelection",
      "type": "object"
    },
    "QuestionPresentationReference": {
      "additionalProperties": false,
      "properties": {
        "applies_to_current_revision": {
          "title": "Applies To Current Revision",
          "type": "boolean"
        },
        "reference": {
          "$ref": "#/$defs/QuestionReference"
        }
      },
      "required": [
        "reference",
        "applies_to_current_revision"
      ],
      "title": "QuestionPresentationReference",
      "type": "object"
    },
    "QuestionReference": {
      "additionalProperties": false,
      "properties": {
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "note": {
          "maxLength": 800,
          "title": "Note",
          "type": "string"
        },
        "question_id": {
          "minLength": 1,
          "title": "Question Id",
          "type": "string"
        },
        "reference_id": {
          "minLength": 1,
          "title": "Reference Id",
          "type": "string"
        },
        "revision": {
          "minimum": 1,
          "title": "Revision",
          "type": "integer"
        },
        "target_id": {
          "maxLength": 128,
          "minLength": 1,
          "title": "Target Id",
          "type": "string"
        },
        "target_type": {
          "enum": [
            "candidate",
            "run",
            "backtest",
            "watch",
            "evaluation",
            "operation"
          ],
          "title": "Target Type",
          "type": "string"
        }
      },
      "required": [
        "reference_id",
        "question_id",
        "revision",
        "target_type",
        "target_id",
        "note",
        "created_at"
      ],
      "title": "QuestionReference",
      "type": "object"
    },
    "QuestionRevision": {
      "additionalProperties": false,
      "properties": {
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "meaning": {
          "maxLength": 1000,
          "minLength": 1,
          "title": "Meaning",
          "type": "string"
        },
        "question_id": {
          "minLength": 1,
          "title": "Question Id",
          "type": "string"
        },
        "revision": {
          "minimum": 1,
          "title": "Revision",
          "type": "integer"
        },
        "selection": {
          "$ref": "#/$defs/QuestionForecastSelection"
        },
        "source_ids": {
          "items": {
            "maxLength": 128,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 16,
          "title": "Source Ids",
          "type": "array"
        }
      },
      "required": [
        "question_id",
        "revision",
        "meaning",
        "source_ids",
        "selection",
        "created_at"
      ],
      "title": "QuestionRevision",
      "type": "object"
    },
    "QuestionView": {
      "additionalProperties": false,
      "properties": {
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "current_revision": {
          "minimum": 1,
          "title": "Current Revision",
          "type": "integer"
        },
        "question_id": {
          "minLength": 1,
          "title": "Question Id",
          "type": "string"
        },
        "reference_count": {
          "minimum": 0,
          "title": "Reference Count",
          "type": "integer"
        },
        "revision": {
          "$ref": "#/$defs/QuestionRevision"
        },
        "revision_count": {
          "minimum": 1,
          "title": "Revision Count",
          "type": "integer"
        },
        "status": {
          "enum": [
            "open",
            "paused",
            "resolved"
          ],
          "title": "Status",
          "type": "string"
        },
        "title": {
          "minLength": 1,
          "title": "Title",
          "type": "string"
        },
        "updated_at": {
          "format": "date-time",
          "title": "Updated At",
          "type": "string"
        }
      },
      "required": [
        "question_id",
        "title",
        "status",
        "current_revision",
        "revision",
        "revision_count",
        "reference_count",
        "created_at",
        "updated_at"
      ],
      "title": "QuestionView",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "next_offset": {
      "anyOf": [
        {
          "minimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Next Offset"
    },
    "question": {
      "$ref": "#/$defs/QuestionView"
    },
    "references": {
      "items": {
        "$ref": "#/$defs/QuestionPresentationReference"
      },
      "maxItems": 3,
      "title": "References",
      "type": "array"
    },
    "schema_version": {
      "const": "question-presentation-v1",
      "default": "question-presentation-v1",
      "title": "Schema Version",
      "type": "string"
    },
    "visual_destination": {
      "const": "question_timeline",
      "default": "question_timeline",
      "title": "Visual Destination",
      "type": "string"
    }
  },
  "required": [
    "question",
    "references",
    "next_offset"
  ],
  "title": "QuestionPresentation",
  "type": "object"
} as const;

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

export const questionPresentationReferenceSchema = {
  "$defs": {
    "QuestionReference": {
      "additionalProperties": false,
      "properties": {
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "note": {
          "maxLength": 800,
          "title": "Note",
          "type": "string"
        },
        "question_id": {
          "minLength": 1,
          "title": "Question Id",
          "type": "string"
        },
        "reference_id": {
          "minLength": 1,
          "title": "Reference Id",
          "type": "string"
        },
        "revision": {
          "minimum": 1,
          "title": "Revision",
          "type": "integer"
        },
        "target_id": {
          "maxLength": 128,
          "minLength": 1,
          "title": "Target Id",
          "type": "string"
        },
        "target_type": {
          "enum": [
            "candidate",
            "run",
            "backtest",
            "watch",
            "evaluation",
            "operation"
          ],
          "title": "Target Type",
          "type": "string"
        }
      },
      "required": [
        "reference_id",
        "question_id",
        "revision",
        "target_type",
        "target_id",
        "note",
        "created_at"
      ],
      "title": "QuestionReference",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "applies_to_current_revision": {
      "title": "Applies To Current Revision",
      "type": "boolean"
    },
    "reference": {
      "$ref": "#/$defs/QuestionReference"
    }
  },
  "required": [
    "reference",
    "applies_to_current_revision"
  ],
  "title": "QuestionPresentationReference",
  "type": "object"
} as const;

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

