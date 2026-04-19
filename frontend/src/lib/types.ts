/**
 * Hand-maintained mirror of the B5 backend response shapes.
 *
 * These types describe what the frontend *expects* from the
 * backend — they are NOT a runtime validator. TypeScript erases
 * at compile time and does not verify that the bytes returned
 * by the BFF actually match these shapes. The authoritative
 * runtime validators live on the backend (`backend/models/
 * bundle_models.py` — Pydantic with `extra="forbid"`), where
 * every response is validated before it leaves the process.
 *
 * A backend response that passes Pydantic is trusted at the
 * edge here; consumer components still defend against missing
 * / malformed nested fields (Optional, isArray / isObject
 * checks) because an HTTP surface can always surprise its
 * caller. If a backend response shape drifts from this file,
 * the drift will only be noticed when a TypeScript consumer
 * touches the affected field — keep this mirror in lockstep
 * with the Pydantic models on every backend contract change.
 */

export type VariantSet =
  | 'default_3_mode'
  | 'b4_experiment_triplet'
  | 'custom';

export interface BundleSourceRef {
  kind: string;
  origin: string;
  notes: string;
}

export interface BundleMetadata {
  bundle_schema_version: string;
  bundle_id: string;
  variant_set: VariantSet;
  variant_tags: string[];
  session_ids: Record<string, string>;
  has_compare_report: boolean;
  has_thesis_report: boolean;
  source: BundleSourceRef;
  produced_by: string;
  warnings: string[];
}

export interface SessionSummary {
  variant_tag: string;
  session_id: string | null;
  mode: string | null;
  events_observed: number | null;
  events_with_outcome: number | null;
  total_cost: number | null;
  avg_cost: number | null;
  sla_preservation_rate: number | null;
  auto_execute_success_rate: number | null;
  memory_jsonl_present: boolean;
  session_artifact_loadable: boolean;
  warnings: string[];
}

export interface BundleIndexEntry {
  bundle_id: string;
  variant_set: VariantSet;
  variant_tags: string[];
  has_compare_report: boolean;
  has_thesis_report: boolean;
  warning_count: number;
  bundle_schema_version: string;
}

export interface BundleIndexResponse {
  bundle_schema_version: string;
  bundles: BundleIndexEntry[];
}

export interface BundleDetailResponse {
  metadata: BundleMetadata;
  sessions: SessionSummary[];
  compare_report_raw: CompareReportRaw | null;
  thesis_report_raw_markdown: string | null;
  load_warnings: string[];
}

/**
 * Phase 3A Session Runtime — raw session artifact envelope.
 *
 * `session_artifact_raw` is the verbatim dict parsed from
 * `session_artifact.json`. We do NOT enumerate every runtime
 * session-schema field here; the Runtime page reads structural
 * fields (`event_records`, `baseline_event_result`, overlay
 * fields) off the opaque record and defends against missing /
 * malformed shapes per-event. `SessionArtifactRaw` and
 * `SessionEventRecordRaw` below document the minimum structure
 * the runtime UI relies on — they are deliberately narrow so
 * the page never pretends to validate the full Path C schema.
 */
export interface SessionArtifactResponse {
  bundle_id: string;
  variant_tag: string;
  session_artifact_loadable: boolean;
  memory_jsonl_present: boolean;
  session_artifact_raw: SessionArtifactRaw | null;
  load_warnings: string[];
}

/**
 * Minimum structural contract the Runtime page relies on. Every
 * field is optional because a sparse / malformed artifact must
 * still render a non-crashing view.
 */
export interface SessionArtifactRaw {
  session_id?: string;
  config?: {
    mode?: string;
    seed?: number;
    events_source?: string;
    initial_memory_digest?: string;
  };
  event_records?: SessionEventRecordRaw[];
  memory_snapshot?: Record<string, unknown>;
  kpis?: Record<string, unknown>;
  schema_version?: string;
  // Aggregate of tier-wise schema versions emitted by
  // SessionArtifact (e.g. {"session_artifact": "1.0",
  // "session_event_record": "1.2", "session_kpis": "1.1"}).
  // Purely informational — the runtime page surfaces it as a
  // version stamp, it is NEVER used for schema validation.
  schema_versions?: Record<string, string>;
  notes?: string;
  // Any other fields ride along opaquely.
  [key: string]: unknown;
}

/**
 * Narrow structural mirror of the canonical compare-report
 * shape produced by `src/session/session_compare.py`. Every
 * field is optional because Compare Lab is a read-only
 * canonical viewer — it MUST render sparse / older / opt-in
 * shapes without crashing, and it MUST NOT coerce defaults
 * into semantics the artifact did not commit to.
 *
 * This mirror is deliberately shallow: cells that session_
 * compare emits as arbitrary per-mode dicts ride along opaquely
 * as `Record<string, unknown>`, so future non-breaking shape
 * evolutions do not force a lockstep type edit.
 */
export interface CompareReportRaw {
  schema_version?: string;
  sessions_compared?: string[];
  baseline_mode?: string;
  min_records_for_shift?: number;
  per_session_kpi_report?: Record<string, Record<string, unknown>>;
  kpi_matrix?: {
    cold_phase?: Record<string, Record<string, unknown>>;
    warm_phase?: Record<string, Record<string, unknown>>;
    overall?: Record<string, Record<string, unknown>>;
  };
  deltas?: Record<string, Record<string, number | null>>;
  diverged_events?: DivergedEventEntry[];
  thesis_claim_support?: ThesisClaimSupportBlock;
  // Conditional sibling blocks (additive, opt-in — may be absent).
  replan_trace_summary?: ReplanTraceSummary;
  correlation_summary?: CorrelationSummary;
  cumulative_memory_summary?: CumulativeMemorySummary;
  agent_memory_experiment_summary?: AgentMemoryExperimentSummary;
  [key: string]: unknown;
}

/**
 * B1 replan_trace_summary — Phase 5A Advanced Lenses consumer.
 * Emitted by `session_compare._build_replan_trace_summary` only
 * when at least one compared artifact has a non-None replan
 * trace. Absence therefore is itself information ("no replan
 * data on this compare"), and B5 surfaces absence as a neutral
 * state rather than fabricating zeros.
 */
export interface ReplanTraceSummary {
  sessions_with_replan?: string[];
  total_replan_events?: number;
  trigger_type_counts?: Record<string, Record<string, number>>;
  recovered_events_count?: Record<string, number>;
  by_mode?: Record<
    string,
    {
      replan_kpis_overall?: Record<string, unknown>;
      events_with_trace?: number;
      recovered_events?: number;
      [key: string]: unknown;
    }
  >;
  [key: string]: unknown;
}

/**
 * B2 correlation_summary — conditional sibling emitted by
 * `session_compare._build_correlation_summary`. Observability
 * only; no policy / compare math involved.
 */
export interface CorrelationSummary {
  sessions_with_correlation_data?: string[];
  per_session?: Record<
    string,
    {
      events_with_context?: number;
      events_with_signals?: number;
      total_signals?: number;
      pattern_counts?: Record<string, number>;
      correlated_event_ids?: string[];
      signals_by_event?: Array<Record<string, unknown>>;
      [key: string]: unknown;
    }
  >;
  overall_pattern_counts?: Record<string, number>;
  all_correlated_event_ids?: string[];
  [key: string]: unknown;
}

/**
 * B3 cumulative_memory_summary — conditional sibling emitted
 * by `session_compare._build_cumulative_memory_summary`. Always
 * session / compare-level provenance; there is no per-event
 * B3 overlay (see `docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md`).
 */
export interface CumulativeMemorySummary {
  sessions_with_cumulative_memory?: string[];
  per_session?: Record<
    string,
    {
      current_session_id?: string;
      has_cumulative_memory?: boolean;
      cumulative_row_count?: number;
      self_session_row_count?: number;
      prior_session_refs?: string[];
      rows_by_prior_session?: Record<string, number>;
      [key: string]: unknown;
    }
  >;
  all_prior_session_refs?: string[];
  overall_rows_by_prior_session?: Record<string, number>;
  [key: string]: unknown;
}

export interface DivergedEventEntry {
  event_index?: number;
  event_id?: string | null;
  modes?: string[];
  routes?: Record<string, string | null>;
  actions?: Record<string, string | null>;
  statuses?: Record<string, string | null>;
  adjustment_ref?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface ThesisClaimSupportBlock {
  claim?: string;
  warm_calibrated_autonomy_delta?: number | null;
  warm_sla_preservation_delta?: number | null;
  warm_cost_delta?: number | null;
  supports_claim?: boolean | null;
  notes?: string;
  [key: string]: unknown;
}

/**
 * B4 `agent_memory_experiment_summary` sibling block shape
 * (see `session_compare._build_agent_memory_experiment_summary`).
 * The block is compare-only, opt-in via the harness's
 * `agent_memory_variant_tags` kwarg, and never changes the
 * top-level compare schema version. Surfaced here as its own
 * type so the Compare Lab can render it inside a visually
 * distinct experiment panel rather than folding it into the
 * mainline compare surface.
 */
export interface AgentMemoryExperimentSummary {
  schema_version?: string;
  variant_tags?: string[];
  session_ids_by_variant?: Record<string, string>;
  agent_visible_vs_policy_only_diverged_event_ids?: string[];
  notes?: string;
  [key: string]: unknown;
}

export interface SessionEventRecordRaw {
  baseline_event_result?: {
    event_id?: string;
    event_type?: string;
    execution_status?: string;
    [key: string]: unknown;
  };
  session_id?: string;
  mode?: string;
  policy_route_source?: string;
  adaptive_adjustment?: Record<string, unknown> | null;
  governance_truth?: Record<string, unknown>;
  effective_decision?: {
    final_route?: string;
    action_taken?: string | null;
    execution_status?: string;
    effective_risk?: string;
    [key: string]: unknown;
  };
  memory_record_id?: string | null;
  replan_trace?: unknown[] | null;
  replan_triggers?: unknown[] | null;
  correlation_context?: Record<string, unknown> | null;
  notes?: string;
  schema_version?: string;
  [key: string]: unknown;
}
