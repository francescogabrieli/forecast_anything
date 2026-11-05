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

