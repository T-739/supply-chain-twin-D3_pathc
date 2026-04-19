import type {
  BundleDetailResponse,
  BundleIndexResponse,
  CompareReportRaw,
  SessionArtifactResponse,
  SessionEventRecordRaw,
} from '@/lib/types';

export const defaultBundleDetail: BundleDetailResponse = {
  metadata: {
    bundle_schema_version: '1.0',
    bundle_id: 'fixture_default_3mode_v1',
    variant_set: 'default_3_mode',
    variant_tags: ['baseline_static', 'path_c_cold', 'path_c_warm'],
    session_ids: {
      baseline_static: 'FIXTURE-DEFAULT-BASELINE_STATIC',
      path_c_cold: 'FIXTURE-DEFAULT-PATH_C_COLD',
      path_c_warm: 'FIXTURE-DEFAULT-PATH_C_WARM',
    },
    has_compare_report: true,
    has_thesis_report: true,
    source: {
      kind: 'fixture_builder',
      origin: 'build_default_3mode_fixture',
      notes: 'Deterministic synthetic fixture covering the default trio.',
    },
    produced_by: '0.1.0',
    warnings: [],
  },
  sessions: [
    {
      variant_tag: 'baseline_static',
      session_id: 'FIXTURE-DEFAULT-BASELINE_STATIC',
      mode: 'BASELINE_STATIC',
      events_observed: 2,
      events_with_outcome: 2,
      total_cost: 201.0,
      avg_cost: 100.5,
      sla_preservation_rate: 1.0,
      auto_execute_success_rate: 1.0,
      memory_jsonl_present: true,
      session_artifact_loadable: true,
      warnings: [],
    },
    {
      variant_tag: 'path_c_cold',
      session_id: 'FIXTURE-DEFAULT-PATH_C_COLD',
      mode: 'PATH_C_COLD',
      events_observed: 2,
      events_with_outcome: 2,
      total_cost: 201.0,
      avg_cost: 100.5,
      sla_preservation_rate: 1.0,
      auto_execute_success_rate: 1.0,
      memory_jsonl_present: true,
      session_artifact_loadable: true,
      warnings: [],
    },
    {
      variant_tag: 'path_c_warm',
      session_id: 'FIXTURE-DEFAULT-PATH_C_WARM',
      mode: 'PATH_C_WARM',
      events_observed: 2,
      events_with_outcome: 2,
      total_cost: 201.0,
      avg_cost: 100.5,
      sla_preservation_rate: 1.0,
      auto_execute_success_rate: 1.0,
      memory_jsonl_present: true,
      session_artifact_loadable: true,
      warnings: [],
    },
  ],
  compare_report_raw: { schema_version: '1.1' },
  thesis_report_raw_markdown: '# Fixture thesis report\n',
  load_warnings: [],
};

export const b4BundleDetail: BundleDetailResponse = {
  metadata: {
    bundle_schema_version: '1.0',
    bundle_id: 'fixture_b4_triplet_v1',
    variant_set: 'b4_experiment_triplet',
    variant_tags: [
      'baseline_static',
      'path_c_warm_policy_only',
      'path_c_warm_agent_visible_memory',
    ],
    session_ids: {
      baseline_static: 'FIXTURE-B4-BASELINE_STATIC',
      path_c_warm_policy_only: 'FIXTURE-B4-PATH_C_WARM_POLICY_ONLY',
      path_c_warm_agent_visible_memory:
        'FIXTURE-B4-PATH_C_WARM_AGENT_VISIBLE_MEMORY',
    },
    has_compare_report: true,
    has_thesis_report: false,
    source: {
      kind: 'fixture_builder',
      origin: 'build_b4_triplet_fixture',
      notes: 'Deterministic synthetic B4 triplet fixture (no path_c_cold).',
    },
    produced_by: '0.1.0',
    warnings: [
      'path_c_cold variant intentionally absent (B4 experiment triplet).',
      'thesis_report.md intentionally omitted.',
    ],
  },
  sessions: [
    {
      variant_tag: 'baseline_static',
      session_id: 'FIXTURE-B4-BASELINE_STATIC',
      mode: 'BASELINE_STATIC',
      events_observed: 3,
      events_with_outcome: 3,
      total_cost: 303.0,
      avg_cost: 101.0,
      sla_preservation_rate: 1.0,
      auto_execute_success_rate: 1.0,
      memory_jsonl_present: true,
      session_artifact_loadable: true,
      warnings: [],
    },
    {
      variant_tag: 'path_c_warm_policy_only',
      session_id: 'FIXTURE-B4-PATH_C_WARM_POLICY_ONLY',
      mode: 'PATH_C_WARM',
      events_observed: 3,
      events_with_outcome: 3,
      total_cost: 303.0,
      avg_cost: 101.0,
      sla_preservation_rate: 1.0,
      auto_execute_success_rate: 1.0,
      memory_jsonl_present: false,
      session_artifact_loadable: true,
      warnings: [],
    },
    {
      variant_tag: 'path_c_warm_agent_visible_memory',
      session_id: 'FIXTURE-B4-PATH_C_WARM_AGENT_VISIBLE_MEMORY',
      mode: 'PATH_C_WARM',
      events_observed: 3,
      events_with_outcome: 3,
      total_cost: 303.0,
      avg_cost: 101.0,
      sla_preservation_rate: 1.0,
      auto_execute_success_rate: 1.0,
      memory_jsonl_present: false,
      session_artifact_loadable: true,
      warnings: [],
    },
  ],
  compare_report_raw: { schema_version: '1.1' },
  thesis_report_raw_markdown: null,
  load_warnings: [],
};

export const fullIndex: BundleIndexResponse = {
  bundle_schema_version: '1.0',
  bundles: [
    {
      bundle_id: 'fixture_b4_triplet_v1',
      variant_set: 'b4_experiment_triplet',
      variant_tags: [
        'baseline_static',
        'path_c_warm_policy_only',
        'path_c_warm_agent_visible_memory',
      ],
      has_compare_report: true,
      has_thesis_report: false,
      warning_count: 2,
      bundle_schema_version: '1.0',
    },
    {
      bundle_id: 'fixture_default_3mode_v1',
      variant_set: 'default_3_mode',
      variant_tags: ['baseline_static', 'path_c_cold', 'path_c_warm'],
      has_compare_report: true,
      has_thesis_report: true,
      warning_count: 0,
      bundle_schema_version: '1.0',
    },
  ],
};

export const emptyIndex: BundleIndexResponse = {
  bundle_schema_version: '1.0',
  bundles: [],
};

// --------------------------- Session Runtime -----------------

function makeEvent(
  index: number,
  overrides: Partial<SessionEventRecordRaw> = {},
): SessionEventRecordRaw {
  return {
    baseline_event_result: {
      event_id: `EV-${index.toString().padStart(3, '0')}`,
      event_type: 'CARRIER_DELAY_ESCALATION',
      severity: 'MEDIUM',
      scenario_context: {},
      execution_status: 'executed',
      execution_outcome: {
        cost_incurred: 100.0 + index,
        sla_impact: { preserved: true },
      },
      trace_log: [],
    },
    session_id: 'FIXTURE-SESSION',
    mode: 'PATH_C_WARM',
    policy_route_source: 'adaptive_adjusted',
    adaptive_adjustment: null,
    governance_truth: {
      risk_level: 'MEDIUM',
      recommended_candidate_type: 'EXPEDITE',
      schema_version: '1.0',
    },
    effective_decision: {
      effective_risk: 'MEDIUM',
      final_route: 'AUTO_EXECUTE',
      action_taken: 'EXPEDITE',
      execution_status: 'executed',
      schema_version: '1.0',
    },
    memory_record_id: null,
    replan_trace: null,
    replan_triggers: null,
    correlation_context: null,
    notes: '',
    schema_version: '1.2',
    ...overrides,
  };
}

export const defaultSessionArtifact: SessionArtifactResponse = {
  bundle_id: 'fixture_default_3mode_v1',
  variant_tag: 'path_c_warm',
  session_artifact_loadable: true,
  memory_jsonl_present: true,
  session_artifact_raw: {
    session_id: 'FIXTURE-DEFAULT-PATH_C_WARM',
    config: {
      mode: 'PATH_C_WARM',
      seed: 42,
      events_source: 'fixture_stream',
    },
    event_records: [makeEvent(0), makeEvent(1)],
    memory_snapshot: { records: [] },
    kpis: { events_observed: 2, events_with_outcome: 2 },
    schema_version: '1.0',
    schema_versions: {
      session_artifact: '1.0',
      session_event_record: '1.2',
      session_kpis: '1.1',
    },
  },
  load_warnings: [],
};

export const defaultBaselineArtifact: SessionArtifactResponse = {
  bundle_id: 'fixture_default_3mode_v1',
  variant_tag: 'baseline_static',
  session_artifact_loadable: true,
  memory_jsonl_present: true,
  session_artifact_raw: {
    session_id: 'FIXTURE-DEFAULT-BASELINE_STATIC',
    config: { mode: 'BASELINE_STATIC', seed: 42, events_source: 'fixture_stream' },
    event_records: [
      makeEvent(0, { mode: 'BASELINE_STATIC' }),
      makeEvent(1, { mode: 'BASELINE_STATIC' }),
    ],
    memory_snapshot: { records: [] },
    kpis: {},
    schema_version: '1.0',
  },
  load_warnings: [],
};

export const b4AgentVisibleArtifact: SessionArtifactResponse = {
  bundle_id: 'fixture_b4_triplet_v1',
  variant_tag: 'path_c_warm_agent_visible_memory',
  session_artifact_loadable: true,
  memory_jsonl_present: false,
  session_artifact_raw: {
    session_id: 'FIXTURE-B4-PATH_C_WARM_AGENT_VISIBLE_MEMORY',
    config: {
      mode: 'PATH_C_WARM',
      seed: 42,
      events_source: 'fixture_stream',
    },
    event_records: [
      makeEvent(0),
      makeEvent(1, {
        replan_trace: [{ attempt_index: 0, trigger: { trigger_type: 'NO_TRIGGER' } }],
        replan_triggers: [{ trigger_type: 'NO_TRIGGER', attempt_index: 0 }],
        correlation_context: { signals: [], window_size: 3, window_events_considered: 0 },
      }),
      makeEvent(2),
    ],
    memory_snapshot: { records: [] },
    kpis: {},
    schema_version: '1.0',
  },
  load_warnings: [],
};

export const zeroEventArtifact: SessionArtifactResponse = {
  bundle_id: 'fixture_default_3mode_v1',
  variant_tag: 'path_c_warm',
  session_artifact_loadable: true,
  memory_jsonl_present: false,
  session_artifact_raw: {
    session_id: 'FIXTURE-EMPTY',
    config: { mode: 'PATH_C_WARM', seed: 0, events_source: 'none' },
    event_records: [],
    memory_snapshot: {},
    kpis: {},
    schema_version: '1.0',
  },
  load_warnings: [],
};

/**
 * Artifact variant that exercises the dual-track divergence
 * highlight: governance_truth.risk_level = "MEDIUM" but the
 * adaptive gate downgrades to effective_risk = "LOW" via an
 * UPGRADE_ONE_LEVEL adjustment (structurally represented; the
 * front end does not evaluate the adjustment semantics, only
 * renders them). Used by the dual-track visibility test.
 */
export const divergedArtifact: SessionArtifactResponse = {
  bundle_id: 'fixture_default_3mode_v1',
  variant_tag: 'path_c_warm',
  session_artifact_loadable: true,
  memory_jsonl_present: true,
  session_artifact_raw: {
    session_id: 'FIXTURE-DEFAULT-PATH_C_WARM',
    config: {
      mode: 'PATH_C_WARM',
      seed: 42,
      events_source: 'fixture_stream',
    },
    event_records: [
      makeEvent(0, {
        governance_truth: {
          risk_level: 'MEDIUM',
          recommended_candidate_type: 'EXPEDITE',
          schema_version: '1.0',
        },
        effective_decision: {
          effective_risk: 'LOW',
          final_route: 'AUTO_EXECUTE',
          action_taken: 'EXPEDITE',
          execution_status: 'executed',
          schema_version: '1.0',
        },
        adaptive_adjustment: {
          rule_id: 'R-AUTOEXPEDITE-LOW',
          adjustment_type: 'UPGRADE_ONE_LEVEL',
          pre_adjustment_risk: 'MEDIUM',
          post_adjustment_risk: 'LOW',
          query_signature: 'sig:CARRIER_DELAY_ESCALATION|...|v1',
          memory_evidence: { matched_records: 8 },
          notes: '',
          schema_version: '1.0',
        },
      }),
    ],
    memory_snapshot: { records: [] },
    kpis: {},
    schema_version: '1.0',
  },
  load_warnings: [],
};

/**
 * Session artifact with a non-empty memory_snapshot.records
 * list, so the 3B summary strip can show memory row count.
 */
export const withMemorySnapshotArtifact: SessionArtifactResponse = {
  bundle_id: 'fixture_default_3mode_v1',
  variant_tag: 'path_c_warm',
  session_artifact_loadable: true,
  memory_jsonl_present: true,
  session_artifact_raw: {
    session_id: 'FIXTURE-WITH-MEMORY',
    config: { mode: 'PATH_C_WARM', seed: 1, events_source: 'mem' },
    event_records: [makeEvent(0), makeEvent(1)],
    memory_snapshot: {
      records: [
        { session_id: 'FIXTURE-WITH-MEMORY', event_id: 'EV-000' },
        { session_id: 'FIXTURE-WITH-MEMORY', event_id: 'EV-001' },
        { session_id: 'PRIOR-SESSION', event_id: 'EV-PRIOR' },
      ],
    },
    kpis: {},
    schema_version: '1.0',
  },
  load_warnings: [],
};

export const unloadableArtifact: SessionArtifactResponse = {
  bundle_id: 'fixture_default_3mode_v1',
  variant_tag: 'path_c_warm',
  session_artifact_loadable: false,
  memory_jsonl_present: false,
  session_artifact_raw: null,
  load_warnings: [
    'session_artifact.json is unreadable or not canonical JSON for variant path_c_warm',
  ],
};

// =============================================================
// Compare / thesis fixtures (Phase 4A)
// =============================================================

/**
 * Canonical compare-report fixture modelling a default-trio
 * run. Shape mirrors what `src/session/session_compare.py`
 * would emit for a 3-mode compare (sessions_compared sorted,
 * numeric cells, honest nulls in the deltas where a mode has
 * no outcome-derived KPI).
 */
export const defaultTrioCompareRaw: CompareReportRaw = {
  schema_version: '1.1',
  sessions_compared: ['baseline_static', 'path_c_cold', 'path_c_warm'],
  baseline_mode: 'baseline_static',
  min_records_for_shift: 3,
  per_session_kpi_report: {
    baseline_static: { cold_phase: {}, warm_phase: {}, overall: {} },
    path_c_cold: { cold_phase: {}, warm_phase: {}, overall: {} },
    path_c_warm: { cold_phase: {}, warm_phase: {}, overall: {} },
  },
  kpi_matrix: {
    overall: {
      sla_preservation_rate: {
        baseline_static: 0.82,
        path_c_cold: 0.84,
        path_c_warm: 0.91,
      },
      avg_cost_per_event: {
        baseline_static: 250.0,
        path_c_cold: 248.5,
        path_c_warm: 239.0,
      },
      calibrated_autonomy_score: {
        baseline_static: 0.5,
        path_c_cold: 0.55,
        path_c_warm: 0.62,
      },
    },
    cold_phase: {
      sla_preservation_rate: {
        baseline_static: 0.8,
        path_c_cold: 0.8,
        path_c_warm: 0.8,
      },
    },
    warm_phase: {
      sla_preservation_rate: {
        baseline_static: 0.85,
        path_c_cold: 0.88,
        path_c_warm: 0.95,
      },
    },
  },
  deltas: {
    path_c_cold_minus_baseline_static: {
      sla_preservation_rate: 0.02,
      avg_cost_per_event: -1.5,
      calibrated_autonomy_score: 0.05,
    },
    path_c_warm_minus_baseline_static: {
      sla_preservation_rate: 0.09,
      avg_cost_per_event: -11.0,
      calibrated_autonomy_score: 0.12,
      known_outcome_coverage: null,
    },
  },
  diverged_events: [
    {
      event_index: 3,
      event_id: 'EV-003',
      modes: ['baseline_static', 'path_c_cold', 'path_c_warm'],
      routes: {
        baseline_static: 'HUMAN_REQUIRED',
        path_c_cold: 'HUMAN_REQUIRED',
        path_c_warm: 'AUTO_EXECUTE',
      },
      actions: {
        baseline_static: null,
        path_c_cold: null,
        path_c_warm: 'EXPEDITE',
      },
      statuses: {
        baseline_static: 'awaiting_human_review',
        path_c_cold: 'awaiting_human_review',
        path_c_warm: 'executed',
      },
      adjustment_ref: {
        rule_id: 'R-AUTOEXPEDITE-LOW',
        adjustment_type: 'UPGRADE_ONE_LEVEL',
        pre_adjustment_risk: 'MEDIUM',
        post_adjustment_risk: 'LOW',
        query_signature: 'sig:…',
        memory_evidence: { matched_records: 8 },
        notes: '',
        schema_version: '1.0',
      },
    },
  ],
  thesis_claim_support: {
    claim:
      'Path C extends calibrated supervision into a temporally adaptive semi-autonomy loop.',
    warm_calibrated_autonomy_delta: 0.12,
    warm_sla_preservation_delta: 0.09,
    warm_cost_delta: -11.0,
    supports_claim: true,
    notes:
      'Warm session matches or exceeds baseline on SLA and calibrated autonomy with non-increasing cost.',
  },
};

export const defaultTrioThesisMd =
  '# Path C Phase 3 — Thesis-Aligned Session Compare Report\n' +
  '\n' +
  'Schema: `SessionCompareReport v1.1`. Baseline mode: `baseline_static`. min_records_for_shift = `3`.\n' +
  '\n' +
  '## Overall KPIs\n' +
  '\n' +
  '| KPI | baseline_static | path_c_cold | path_c_warm |\n' +
  '|---|---|---|---|\n' +
  '| sla_preservation_rate | 0.8200 | 0.8400 | 0.9100 |\n';

/**
 * BundleDetailResponse for the default trio carrying a real
 * canonical compare + thesis. Use this when a Compare Lab test
 * needs substantive compare content.
 */
export const defaultBundleDetailWithCompare: BundleDetailResponse = {
  ...defaultBundleDetail,
  compare_report_raw: defaultTrioCompareRaw,
  thesis_report_raw_markdown: defaultTrioThesisMd,
};

/**
 * Canonical compare-report fixture modelling the B4 experiment
 * triplet. Includes the opt-in
 * `agent_memory_experiment_summary` sibling block — this is
 * the block Compare Lab must surface inside its isolated
 * experiment panel and MUST NOT merge into KPI / thesis views.
 */
export const b4TripletCompareRaw: CompareReportRaw = {
  schema_version: '1.1',
  sessions_compared: [
    'baseline_static',
    'path_c_warm_agent_visible_memory',
    'path_c_warm_policy_only',
  ],
  baseline_mode: 'baseline_static',
  min_records_for_shift: 3,
  per_session_kpi_report: {},
  kpi_matrix: {
    overall: {
      sla_preservation_rate: {
        baseline_static: 0.82,
        path_c_warm_policy_only: 0.9,
        path_c_warm_agent_visible_memory: 0.92,
      },
    },
    cold_phase: {},
    warm_phase: {},
  },
  deltas: {
    path_c_warm_policy_only_minus_baseline_static: {
      sla_preservation_rate: 0.08,
    },
    path_c_warm_agent_visible_memory_minus_baseline_static: {
      sla_preservation_rate: 0.1,
    },
  },
  diverged_events: [],
  thesis_claim_support: {
    claim:
      'Path C extends calibrated supervision into a temporally adaptive semi-autonomy loop.',
    warm_calibrated_autonomy_delta: null,
    warm_sla_preservation_delta: null,
    warm_cost_delta: null,
    supports_claim: null,
    notes:
      'thesis_claim_support requires a path_c_warm session in the compare; none was provided. No claim determination.',
  },
  agent_memory_experiment_summary: {
    schema_version: '1.0',
    variant_tags: [
      'baseline_static',
      'path_c_warm_policy_only',
      'path_c_warm_agent_visible_memory',
    ],
    session_ids_by_variant: {
      baseline_static: 'FIXTURE-B4-BASELINE_STATIC',
      path_c_warm_policy_only: 'FIXTURE-B4-PATH_C_WARM_POLICY_ONLY',
      path_c_warm_agent_visible_memory:
        'FIXTURE-B4-PATH_C_WARM_AGENT_VISIBLE_MEMORY',
    },
    agent_visible_vs_policy_only_diverged_event_ids: ['EV-007'],
    notes:
      'B4 agent-visible memory experiment compare-only summary. Structural-only: variant tags + session_ids + diverged event ids between the policy-only and agent-visible PATH_C_WARM variants. No KPI deltas, no agent-output paraphrase.',
  },
};

export const b4BundleDetailWithCompare: BundleDetailResponse = {
  ...b4BundleDetail,
  compare_report_raw: b4TripletCompareRaw,
  // B4 triplet fixture intentionally omits thesis_report.md.
  thesis_report_raw_markdown: null,
};

/**
 * Bundle that claims a compare_report but the backend could
 * not load it. Exercises the "compare raw unreadable" state.
 */
export const bundleDetailCompareUnreadable: BundleDetailResponse = {
  ...defaultBundleDetail,
  metadata: {
    ...defaultBundleDetail.metadata,
    has_compare_report: true,
    has_thesis_report: true,
  },
  compare_report_raw: null,
  thesis_report_raw_markdown: null,
  load_warnings: [
    'metadata.has_compare_report=True but compare_report.json is missing or unreadable at load time',
    'metadata.has_thesis_report=True but thesis_report.md is missing or unreadable at load time',
  ],
};

/**
 * Bundle with no compare report at all (metadata-honest).
 */
export const bundleDetailNoCompare: BundleDetailResponse = {
  ...defaultBundleDetail,
  metadata: {
    ...defaultBundleDetail.metadata,
    has_compare_report: false,
    has_thesis_report: false,
  },
  compare_report_raw: null,
  thesis_report_raw_markdown: null,
  load_warnings: [],
};

/**
 * Default-trio compare report *with* every Phase 5A sibling
 * block present: `replan_trace_summary`, `correlation_summary`,
 * `cumulative_memory_summary`. Shapes mirror what
 * `session_compare.build_compare_report` would emit under the
 * relevant enable-flags.
 */
export const defaultTrioCompareWithLenses: CompareReportRaw = {
  ...defaultTrioCompareRaw,
  replan_trace_summary: {
    sessions_with_replan: ['path_c_warm'],
    total_replan_events: 2,
    trigger_type_counts: {
      path_c_warm: {
        NO_TRIGGER: 0,
        COST_DEVIATION: 1,
        SLA_DEVIATION: 0,
        EXECUTION_FAILED: 1,
        PREFLIGHT_FAILED: 0,
      },
    },
    recovered_events_count: { path_c_warm: 1 },
    by_mode: {
      path_c_warm: {
        replan_kpis_overall: {
          replan_events_observed: 2,
          replan_fire_count: 2,
          replan_trigger_rate: 0.4,
          replan_success_count: 1,
          replan_recovery_rate: 0.5,
        },
        events_with_trace: 2,
        recovered_events: 1,
      },
    },
  },
  correlation_summary: {
    sessions_with_correlation_data: ['path_c_cold', 'path_c_warm'],
    per_session: {
      path_c_cold: {
        events_with_context: 5,
        events_with_signals: 2,
        total_signals: 2,
        pattern_counts: { ETA_PATH_COMPOUND: 2 },
        correlated_event_ids: ['EV-002', 'EV-004'],
        signals_by_event: [],
      },
      path_c_warm: {
        events_with_context: 5,
        events_with_signals: 3,
        total_signals: 4,
        pattern_counts: { ETA_PATH_COMPOUND: 3, CARRIER_DOUBLE_HIT: 1 },
        correlated_event_ids: ['EV-002', 'EV-004', 'EV-006'],
        signals_by_event: [],
      },
    },
    overall_pattern_counts: {
      CARRIER_DOUBLE_HIT: 1,
      ETA_PATH_COMPOUND: 5,
    },
    all_correlated_event_ids: ['EV-002', 'EV-004', 'EV-006'],
  },
  cumulative_memory_summary: {
    sessions_with_cumulative_memory: ['path_c_warm'],
    per_session: {
      path_c_warm: {
        current_session_id: 'FIXTURE-DEFAULT-PATH_C_WARM',
        has_cumulative_memory: true,
        cumulative_row_count: 5,
        self_session_row_count: 12,
        prior_session_refs: ['PRIOR-SESSION-A', 'PRIOR-SESSION-B'],
        rows_by_prior_session: {
          'PRIOR-SESSION-A': 3,
          'PRIOR-SESSION-B': 2,
        },
      },
    },
    all_prior_session_refs: ['PRIOR-SESSION-A', 'PRIOR-SESSION-B'],
    overall_rows_by_prior_session: {
      'PRIOR-SESSION-A': 3,
      'PRIOR-SESSION-B': 2,
    },
  },
};

export const defaultBundleDetailWithLenses: BundleDetailResponse = {
  ...defaultBundleDetailWithCompare,
  compare_report_raw: defaultTrioCompareWithLenses,
};

/**
 * B4 triplet bundle whose compare report carries only the
 * `agent_memory_experiment_summary` sibling block (no B1 / B2 /
 * B3). Used to verify that the B4 lens remains visible and
 * isolated while the other three lenses render their honest
 * absent state.
 */
export const b4OnlyLensesBundleDetail: BundleDetailResponse = {
  ...b4BundleDetailWithCompare,
};

/**
 * Custom / sparse compare shape — missing most optional fields.
 * Ensures the Compare Lab doesn't crash on partial artifacts.
 */
export const sparseCompareBundleDetail: BundleDetailResponse = {
  ...defaultBundleDetail,
  compare_report_raw: {
    schema_version: '0.9',
    // no sessions_compared, kpi_matrix, deltas, diverged_events,
    // thesis_claim_support — simulates a pre-1.0 / broken compare.
  },
  thesis_report_raw_markdown: null,
};
