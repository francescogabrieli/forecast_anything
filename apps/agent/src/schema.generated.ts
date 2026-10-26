// Generated from contracts/v1/schemas.json and openapi.json. Run npm run contracts:generate.

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

