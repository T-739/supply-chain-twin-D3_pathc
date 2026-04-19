/**
 * Static identity copy for the Overview page.
 *
 * These strings describe what already exists in the repo — they
 * do not invent any new semantics. If the repo lineage or
 * two-path architecture changes, update this file in lockstep
 * with `docs/` and the README.
 */

export const LINEAGE_NODES = [
  {
    id: 'v1',
    title: 'supply-chain-twin',
    subtitle: 'D1 prototype',
    role:
      'Initial scenario bank, twin state, baseline event loop. Sets the research core.',
  },
  {
    id: 'v2',
    title: 'supply-chain-twin-D3',
    subtitle: 'D2 / D3 Path B',
    role:
      'Frozen Path B runtime — governance truth, policy gate, deterministic event loop. Ships as legacy appendix.',
  },
  {
    id: 'pathc',
    title: 'supply-chain-twin-D3_pathc',
    subtitle: 'D3 Path C-min + B1–B4',
    role:
      'Adaptive overlay, session artifacts, bounded replan, correlator, cumulative + agent-visible memory experiments. This repo.',
  },
] as const;

export const TABS = [
  { href: '/overview', label: 'Overview', enabled: true },
  { href: '/session-runtime', label: 'Session Runtime', enabled: true },
  { href: '/compare-lab', label: 'Compare Lab', enabled: true },
  { href: '/advanced-lenses', label: 'Advanced Lenses', enabled: true },
  { href: '/legacy-v2', label: 'Legacy V2', enabled: true },
] as const;

export const TWO_PATH_SUMMARY = {
  pathB: {
    title: 'Path B — Governance truth layer',
    body:
      'Deterministic per-event governance / policy / execution pipeline. Frozen Tier-1 contracts: GovernanceOutput, PolicyDecision, ExecutionOutcome. No wall-clock, no uuid4.',
  },
  pathC: {
    title: 'Path C — Adaptive overlay',
    body:
      'Read-only sibling of Path B. Adds memory-aware adaptive policy gate, session artifacts, optional replan / correlator / cumulative / agent-visible-memory overlays. Never mutates a Path B record.',
  },
  contract: {
    title: 'Dual-track contract',
    body:
      'GovernanceTruthRef and EffectiveDecisionRef are both present on every SessionEventRecord and never collapse into one value. B5 surfaces this boundary; it does not reinterpret it.',
  },
} as const;

/**
 * Legacy V2 appendix copy. Describes the earlier case-centric
 * supervision platform that preceded D3 Path B / Path C. Every
 * string here is grounded only in what the current repo already
 * carries (the V2 系统总览报告, the D3 Path B full report, the
 * PATH_C_BOUNDARY / SCHEMA_REGISTRY docs). No cross-repo reads,
 * no runtime imports.
 */
export const LEGACY_V2_IDENTITY = {
  lede:
    'Legacy V2 (supply-chain-twin-D3 / D3 Path B era) is the earlier case-centric supervision platform that this repo grew out of. B5 does not use it as an active primary surface; it is preserved here as baseline / historical context.',
  whatItWas: [
    'Case-centric scenario bank driven by a hand-authored CSV and deterministic twin state.',
    'Retrieval-augmented evaluation pipeline producing approve / verify / override rows over a curated case set.',
    'Single-threaded governance → policy → execution event loop, with no adaptive overlay and no session artifact.',
    'Operator-facing Gradio-style UI (`app.py`) plus a thin internal API surface (`src/api/*`) used for case-level demonstrations.',
  ],
  role:
    'V2 established the governance truth boundary, the action-code mapper, and the evaluation harness. Those pieces are the frozen Path B / research-core contracts that Path C later overlaid without modifying.',
} as const;

export const LEGACY_V2_WHY_IT_MATTERS = [
  {
    title: 'Baseline reference',
    body:
      'Every Path C comparison is calibrated against the same deterministic Path B baseline V2 introduced. Without that baseline, the warm / cold / adjusted numbers surfaced in Compare Lab would have no reference point.',
  },
  {
    title: 'Truth boundary',
    body:
      'The GovernanceOutput / PolicyDecision / ExecutionOutcome contracts and the "research core" case evaluation API were fixed in V2. Path C treats them as frozen and only extends them through additive overlay fields.',
  },
  {
    title: 'Evaluation discipline',
    body:
      'V2 shipped with the case-level approve / verify / override evaluation tables and the deterministic twin state. Those conventions still define what "correct" looks like for the current research core.',
  },
] as const;

export const LEGACY_V2_CAPABILITY_APPENDIX = [
  {
    id: 'retrieval',
    title: 'Retrieval',
    body:
      'Vector-store-backed retrieval over the canonical scenario bank. Keys the RAG pipeline used by the legacy operator UI for case lookup and evaluation context.',
  },
  {
    id: 'agents',
    title: 'Agents',
    body:
      'Three deterministic agents — operations, cost, governance — each producing a structured output consumed by the policy gate. Governance is the Tier-1 truth source that B5 never overrides.',
  },
  {
    id: 'evaluation',
    title: 'Evaluation',
    body:
      'Case-level evaluation harness (approve / verify / override rows) over `data/cases/*.json`. Research-core API is frozen in V2 and MUST NOT be read by Path C code paths.',
  },
  {
    id: 'api',
    title: 'Internal API (`src/api/*`, `app.py`)',
    body:
      'Legacy HTTP / Gradio surface used for V2 demos. B5 does NOT revive or extend this surface — the B5 BFF is an independent read-only companion that never imports the legacy API modules.',
  },
  {
    id: 'supervision',
    title: 'Supervision platform',
    body:
      'V2 positioned the twin as a human-supervised decision aid. That stance — human in the loop, deterministic truth, evaluation-first — is inherited by Path C and kept intact under the dual-track contract.',
  },
] as const;

export const LEGACY_V2_BOUNDARY_NOTE =
  'This page is explanatory appendix material. It does NOT expose an active legacy runtime, does NOT call into `src/api/*` or `app.py`, and does NOT execute V2 code paths. The legacy system is preserved in the repository for historical and baseline reference only; operational workflows live in Overview, Session Runtime, Compare Lab, and Advanced Lenses.';

export const REPRODUCIBILITY_POINTS = [
  {
    title: 'Deterministic by construction',
    body:
      'No wall-clock, no uuid4, no datetime.now on any Path C code path. Same seed + same events = byte-identical artifacts (enforced by test_path_c_import_topology.py).',
  },
  {
    title: 'Frozen schemas',
    body:
      'Every tier-1 / tier-2 / tier-3 schema is versioned in PATH_C_SCHEMA_REGISTRY.md. B5 bundle contract pins bundle_schema_version = "1.0".',
  },
  {
    title: 'Read-only B5 surface',
    body:
      'The BFF exposes GET routes only. The bundler is a repackager — it never mutates an existing session artifact. This frontend talks to the BFF only and never touches bundle files.',
  },
  {
    title: 'Bundle contract',
    body:
      'Every run is repackaged into bundles/{bundle_id}/ with metadata.json + sessions/{tag}/ + optional compare_report.json / thesis_report.md. See docs/B5_BUNDLE_CONTRACT.md.',
  },
] as const;
