# B3_CUMULATIVE_MEMORY_FILE_MAP.md

Status: **B3 Slice 1 draft.** Decisions D1–D9 (see
`docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12`) are proposed. The
file map below partitions the repo for the planned Slice 2A PR
(contracts + frozen tests, no runtime wiring yet) and for the
Slice 2B / 2B.5 / 2C / 2D follow-ons.
Authority: `docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md`,
`docs/B3_CUMULATIVE_MEMORY_CONTRACT_DRAFT.md`,
`PATH_C_BOUNDARY.md`.

This document maps B3 (Cross-session cumulative memory) against
the current repo layout so the Slice 2A implementation PR can
proceed without surprises. Every entry is grounded in the state
of the repo at the time of writing.

Slice 2A delta (not yet on `main`):
- Create `src/learning/cumulative_memory.py` with
  `CumulativeMemoryConfig` (frozen dataclass), closed dedupe-
  policy Literal, `MAX_CUMULATIVE_MEMORY_RECORDS` module
  constant, and a loader-function signature (no runtime fs read
  yet — schemas and invariants only).
- No changes to `src/learning/memory_schema.py`,
  `src/learning/episodic_memory.py`, `src/event_loop_c.py`,
  `src/session/*`, `src/adaptive/*`, `src/replan/*`,
  `src/correlator/*`, `src/agents/*`.
- `PATH_C_SCHEMA_REGISTRY.md` — register
  `CumulativeMemoryConfig` at 1.0.
- `PATH_C_BOUNDARY.md` — append a B3 cross-reference alongside
  the B1 / B2 references.
- `tests/test_path_c_import_topology.py` — add the new module to
  the scan roots.
- `tests/test_cumulative_memory_schema_frozen.py`,
  `tests/test_cumulative_memory_no_agent_coupling.py` — added.

---

## 1. Files expected to stay untouched (frozen under B3)

These files MUST NOT be modified by any PR labelled B3 Slice
2A/2B.

### Path B runtime core (frozen Tier 1)

- `src/event_schema.py` — `EventPayload`, `EventType`,
  `EventSeverity`, `AffectedEntityRef`.
- `src/outcome_schema.py` — `ExecutionOutcome`.
- `src/policy_gate.py` — `PolicyDecision`, `decide_policy`.
- `src/agents/governance_agent.py` — `GovernanceOutput`.
- `src/agents/cost_agent.py`, `src/agents/operations_agent.py`.
- `src/execution_adapters.py`.
- `src/twin_state.py`.
- `src/event_loop.py`.
- `src/graph.py`.
- `src/outcome_store.py`.

### Research Core (frozen)

- `src/evaluation.py`
- `src/action_code_mapper.py`
- `data/cases/*.json`

### Path C-min adaptive / preflight

- `src/adaptive/adaptive_policy_gate.py`.
- `src/adaptive/adaptive_policy_config.py`.
- `src/adaptive/adaptive_schema.py`.
- `src/adaptive/cold_start.py`.
- `src/adaptive/preflight.py`.

### Learning (memory core)

- `src/learning/memory_schema.py` — `MemoryRecord`,
  `MemoryQuery`, `MemorySummary` stay at 1.0. **No new field.**
- `src/learning/memory_summarizer.py` — unchanged.
- `src/learning/episodic_memory.py` — append-only + canonical
  order stay exactly as today. The B3 loader does NOT edit
  this file; it consumes it by constructing
  `EpisodicMemory(records=...)` through the existing public
  constructor.

### B1 replan layer

- `src/replan/*` — every file, unchanged. Replan does not
  couple to cumulative memory.

### B2 correlator layer

- `src/correlator/*` — every file, unchanged. The correlator
  does not couple to cumulative memory in B3.

### Path C-min session core

- `src/session/session_schema.py` — no new field on
  `SessionEventRecord`, `SessionArtifact`, or `SessionConfig`.
- `src/session/digests.py` — `digest_memory_records`,
  `compute_session_id`, `memory_record_id` formulas stay
  untouched.
- `src/session/session_manager.py` — `save_session`,
  `load_session`, `replay_session_bytes` stay untouched. (The
  loader MAY import `load_session` as a helper, per O1.)

### Orchestration

- `src/event_loop_c.py` — **core API unchanged in Slice 2A/2B**.
  No new `cumulative_memory_config` kwarg on `run_session`. The
  loader's output flows through the existing
  `initial_memory=...` kwarg at the caller boundary.
- `src/session/kpi_calculator.py` — **frozen for all B3 slices**.
  No B3 KPI.
- `src/session/session_compare.py` — **frozen for Slice 2A/2B**.
  An optional `cumulative_memory_summary` sibling block is
  reserved for Slice 2C (later).

### Scripts

- `scripts/run_session.py`, `scripts/session_eval_harness.py` —
  **frozen for Slice 2A/2B**. CLI / harness wiring lands in
  Slice 2D (later).

### Tests that must continue to pass byte-for-byte

- `tests/test_phase0_baseline_regression_phase1.py`
- `tests/test_path_c_vs_baseline_divergence.py`
- `tests/test_replay_byte_identical.py` (additive new cases
  allowed in Slice 2B.5)
- `tests/test_determinism_stress.py` (additive new cases
  allowed in Slice 2B.5)
- `tests/test_kpi_calculator.py`
- `tests/test_session_compare.py`
- `tests/test_adaptive_audit_trail.py`
- `tests/test_cold_start_behavior.py`
- `tests/test_adjustment_rules.py`
- `tests/test_adaptive_policy_gate.py`
- `tests/test_governance_meta_preflight.py`
- `tests/test_execution_metadata_mandatory.py`
- `tests/test_event_loop_c_wrapping.py`
- `tests/test_session_manager.py` (additive cumulative-memory
  save/load cases allowed in Slice 2B.5)
- `tests/test_thesis_report_generation.py`
- Every `tests/test_replan_*.py` currently on `main`.
- Every `tests/test_correlator_*.py` currently on `main`.

---

## 2. Files extendable additively under B3

### Slice 2A (contracts + frozen tests)

- `PATH_C_SCHEMA_REGISTRY.md` — register
  `CumulativeMemoryConfig` at 1.0 with a change-history line
  "1.0 — initial (B3 Slice 2A, contract only)".
- `PATH_C_BOUNDARY.md` — append a B3 cross-reference alongside
  the existing B1 / B2 entries in §9. Existing §1–§8 text
  unchanged.
- `tests/test_path_c_import_topology.py` — add
  `src/learning/cumulative_memory.py` (or the new module's
  root) to `_PATH_C_FILES` or `_PATH_C_ROOTS` as appropriate.
  The positive/negative self-tests already exercise the scan.

### Slice 2B (runtime loader + test surface, no new kwarg on
`run_session`)

- `tests/test_cumulative_memory_*` — new dedupe / bounded-
  growth / loader-purity tests. No change to
  `src/event_loop_c.py` or `run_session`.

### Slice 2B.5 (determinism / replay hardening)

- `tests/test_replay_byte_identical.py`,
  `tests/test_determinism_stress.py`,
  `tests/test_session_manager.py` — additive parametrization
  for cumulative-memory-enabled `PATH_C_WARM` runs. Cumulative
  memory is attached via `initial_memory=...` in the test
  helper, not via a new `run_session` kwarg.

### Slice 2C (optional, compare-report visibility)

- `src/session/session_compare.py` — optional conditional
  `cumulative_memory_summary` sibling block and a matching
  markdown section in `render_thesis_markdown`. **No
  `COMPARE_REPORT_SCHEMA_VERSION` bump.** Pre-B3 compares stay
  byte-identical.

### Slice 2D (optional, CLI / harness)

- `scripts/run_session.py` — add `--prior-session-dir`
  (repeatable) and `--cumulative-dedupe-policy` flags. Default
  off. Flags resolve into a `CumulativeMemoryConfig` via a
  caller-level helper; the loader's output is threaded through
  the existing `initial_memory=...` kwarg. `BASELINE_STATIC`
  and non-`PATH_C_WARM` `PATH_C_COLD` modes do NOT attach
  cumulative memory — this is enforced in the script, not in
  `run_session`.
- `scripts/session_eval_harness.py` — mirror the same flags;
  thread the config through `run_eval_harness(...)` and attach
  to the `PATH_C_WARM` `run_session(...)` call only.

### Explicitly NOT modified in Slice 2A/2B/2B.5

- `src/event_loop_c.py` — no new kwarg, no new helper pass
  around memory. **`run_session(initial_memory=...)` is the
  integration point and stays as-is.**
- `src/session/session_schema.py` — no new field on
  `SessionEventRecord`, `SessionConfig`, or any other schema.
- `src/adaptive/*` — no change.
- `src/agents/*` — no change. Ever, for B3.

This mirrors the B1/B2 discipline: contracts + frozen tests
first; runtime + wiring in Slice 2B; determinism hardening in
Slice 2B.5; optional compare/report in Slice 2C; optional CLI
in Slice 2D.

---

## 3. Likely new files for B3 Slice 2A

### 3.1 New module: `src/learning/cumulative_memory.py`

Recommended minimum set of public names (schema + constants
only — no runtime fs read, no event_loop coupling):

- `CumulativeMemoryConfig` (frozen dataclass) — fields per
  `docs/B3_CUMULATIVE_MEMORY_CONTRACT_DRAFT.md §1.2`; validated
  in `__post_init__`.
- `CUMULATIVE_MEMORY_DEDUPE_POLICY` — closed Literal,
  single value `"drop_equal_raise_mismatch"` in Slice 2A.
- `MAX_CUMULATIVE_MEMORY_RECORDS: Final[int]` — suggested value
  `1000`; hard cap.
- `CumulativeMemoryCollisionError` — exception type raised when
  the dedupe rule detects a same-triple non-equal collision.
- `load_cumulative_memory(...)` — **signature only in Slice 2A;
  body may raise `NotImplementedError` or be empty**. The
  runtime body lands in Slice 2B.
- `CUMULATIVE_MEMORY_SCHEMA_VERSION: str = "1.0"`.

Module placement rationale (mirrors B1's):

1. `src/learning/` is the natural home — `MemoryRecord` and
   `EpisodicMemory` already live there. Placing the loader
   beside them matches the additive-subpackage pattern.
2. Adds one new file to the existing `src/learning/` Path-C
   scan root, no new root needed. `_PATH_C_ROOTS` already
   includes `src/learning/`.
3. Keeps loader concerns logically separate from
   `episodic_memory.py` (which owns the append-only runtime
   primitive) and from `memory_schema.py` (which owns the frozen
   1.0 record shape).

### 3.2 New tests: `tests/test_cumulative_memory_*.py`

Minimum set, matching the planned acceptance gates
(`docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §11`):

- `tests/test_cumulative_memory_schema_frozen.py` — G1. Asserts
  `CumulativeMemoryConfig` field set, closed-Literal members,
  `__post_init__` validation (bad `max_records`, unknown
  policy), `CUMULATIVE_MEMORY_SCHEMA_VERSION == "1.0"`.
- `tests/test_cumulative_memory_no_agent_coupling.py` — G10.
  Source scan asserts `src/learning/cumulative_memory.py`
  does not import `src/agents/*`, does not reference the five
  forbidden NL governance field names, and does not construct
  prompt-like strings.

Tests deferred to Slice 2B (need the loader body):

- `tests/test_cumulative_memory_loader_purity.py` — G2.
- `tests/test_cumulative_memory_dedupe_determinism.py` — G3.
- `tests/test_cumulative_memory_collision_raises.py` — G4.
- `tests/test_cumulative_memory_append_only_preserved.py` — G5.
- `tests/test_cumulative_memory_bounded_growth.py` — G11.
- `tests/test_cumulative_memory_no_adaptive_reverse_import.py` —
  G9 (`src/adaptive/*` does not import the new module).

Tests deferred to Slice 2B.5:

- Parametrizations of `tests/test_replay_byte_identical.py`,
  `tests/test_determinism_stress.py`,
  `tests/test_session_manager.py` for cumulative-enabled
  `PATH_C_WARM` sessions.

### 3.3 Files not needed in Slice 2A

- No new `src/learning/cumulative_memory_loader.py` — the
  loader lives in `cumulative_memory.py` for Slice 2A; a split
  is premature unless the file grows beyond ~300 lines.
- No runtime wiring in `src/event_loop_c.py`.
- No `CumulativeMemoryConfig` field on `SessionConfig` or any
  other schema.
- No changes to `src/session/*`.
- No CLI or harness changes.

---

## 4. Recommended layering

Clean, non-circular, additive. Mirrors the B2 layering.

```
         ┌─────────────────────────────────────────────┐
         │  Contract layer — Slice 2A                  │
         │  src/learning/cumulative_memory.py          │
         │  (CumulativeMemoryConfig, dedupe Literal,   │
         │   MAX_CUMULATIVE_MEMORY_RECORDS, signature  │
         │   of load_cumulative_memory)                │
         └──────────────────────┬──────────────────────┘
                                │ (Slice 2B adds)
         ┌──────────────────────┴──────────────────────┐
         │  Loader layer (pure) — Slice 2B             │
         │  src/learning/cumulative_memory.py          │
         │  load_cumulative_memory(                    │
         │    config,                                  │
         │    *, source_resolver,                      │
         │  ) → EpisodicMemory (fresh, deduped)        │
         │  (pure function; does NOT read files;       │
         │   calls the caller-supplied resolver once   │
         │   per ref; no wall-clock; no mutation of    │
         │   existing EpisodicMemory instances)        │
         └──────────────────────┬──────────────────────┘
                                │ (caller flow)
         ┌──────────────────────┴──────────────────────┐
         │  Caller / orchestration boundary            │
         │  test / CLI / harness                       │
         │  ─ builds a source_resolver                 │
         │    (reads memory.jsonl for CLI, or returns  │
         │     fixtures for tests)                     │
         │  ─ calls load_cumulative_memory(            │
         │       config, source_resolver=…)            │
         │  ─ run_session(                             │
         │       mode="PATH_C_WARM",                   │
         │       initial_memory=loader_output,         │
         │    )                                        │
         │  (no new run_session kwarg; PATH_C_WARM-    │
         │   only attachment enforced here;            │
         │   filesystem paths never cross into the     │
         │   loader layer above)                       │
         └──────────────────────┬──────────────────────┘
                                │ (Slice 2C adds, optional)
         ┌──────────────────────┴──────────────────────┐
         │  Session-compare visibility — Slice 2C      │
         │  src/session/session_compare.py             │
         │  conditional cumulative_memory_summary      │
         │  (no KPI, no existing-block change, no      │
         │   COMPARE_REPORT_SCHEMA_VERSION bump)       │
         └──────────────────────┬──────────────────────┘
                                │
         ┌──────────────────────┴──────────────────────┐
         │  Tests                                      │
         │  tests/test_cumulative_memory_*.py          │
         └─────────────────────────────────────────────┘
```

Import direction: always top-to-bottom. No upward import, no
cycle. In particular:

- `src/learning/cumulative_memory.py` does NOT import from
  `src/adaptive/`, `src/replan/`, `src/correlator/`,
  `src/session/` (except, optionally, `session.session_manager`
  for `load_session`; see O1).
- `src/adaptive/*`, `src/replan/*`, `src/correlator/*`,
  `src/agents/*` do NOT import from
  `src/learning/cumulative_memory.py`.
- `src/event_loop_c.py` does NOT import from
  `src/learning/cumulative_memory.py` in Slice 2A/2B. The
  module is reached only via the caller (test / CLI / harness).

---

## 5. Where loader logic should live

Locked: **`src/learning/cumulative_memory.py`**.

Alternatives considered and rejected:

- **`src/session/`** — session layer owns overlay / artifact /
  compare / save / load. Memory loading is a learning-layer
  concern, not a session-layer concern; placing the loader
  there would tangle responsibilities.
- **`src/adaptive/`** — adaptive layer owns the policy gate
  (the only memory consumer). Placing the loader there would
  structurally invite the adaptive gate to grow a source-aware
  surface, which is explicitly forbidden.
- **`src/correlator/` / `src/replan/`** — unrelated branch
  directories.
- **A new top-level `src/cumulative/`** — premature; one module
  next to `episodic_memory.py` is sufficient.
- **Helpers inside `scripts/`** — CLI glue is fine as a caller
  layer, but the loader itself must be importable from tests
  without running a script.

---

## 6. Where CLI / harness work would later attach (Slice 2D)

A single change on each script, in a Slice 2D PR:

### `scripts/run_session.py`

- New flags: `--prior-session-dir` (repeatable),
  `--cumulative-dedupe-policy`.
- Default off. When set:
  1. Resolve each directory into a canonical prior-session
     reference (`session_id` from the on-disk artifact, or the
     `memory.jsonl` content digest as fallback).
  2. Build a `CumulativeMemoryConfig` from the resolved refs +
     policy.
  3. Build a concrete `source_resolver` closure (per D10) that
     maps each ref back to the parsed `memory.jsonl` rows for
     the directory that produced it. Path manipulation is
     confined to this closure.
  4. Call
     `load_cumulative_memory(config, source_resolver=resolver)`
     → `EpisodicMemory`.
  5. Pass the result through the existing
     `run_session(initial_memory=...)` kwarg.
  6. Enforce `PATH_C_WARM`-only at this boundary (the script
     raises if `--prior-session-dir` is supplied with a non-
     `PATH_C_WARM` mode).

### `scripts/session_eval_harness.py`

- Mirror the same flags. Add matching kwargs to
  `run_eval_harness(...)`.
- When enabled, build a single `CumulativeMemoryConfig` + a
  single concrete `source_resolver` (same across all three
  modes), call `load_cumulative_memory` once, and attach the
  result to only the `PATH_C_WARM` `run_session(...)` call.
  The other two modes (`BASELINE_STATIC`, `PATH_C_COLD`)
  receive `initial_memory=None` unchanged.
- If the Slice 2C compare block exists by then, it will surface
  automatically because the `PATH_C_WARM` artifact's
  `memory_snapshot` rows carry cross-session `session_id`s.

---

## 7. Interfaces B3 depends on but must not modify

- `EpisodicMemory(records=...)` constructor (`src/learning/
  episodic_memory.py`) — read-only use.
- `EpisodicMemory.snapshot()` — read-only use for digest
  contribution.
- `MemoryRecord` pydantic class (`src/learning/memory_schema.py`) —
  validation only; no schema change.
- `canonical_json(...)` (`src/session/digests.py`) — used by
  caller-level helpers when hashing a per-file content digest.
- `load_session(dir)` (`src/session/session_manager.py`) —
  optional read-only helper for O1 implementations.

## 8. What does *not* need a file change in B3

- `app.py` — no FastAPI surface change.
- `src/api/*` — no route change.
- `src/llm_backend.py`, `src/llm_providers/*` — no new prompt.
- `src/retrieval.py`, `src/rag_setup.py` — cumulative memory
  does not consult RAG.
- `src/supervisor.py` — orthogonal.
- `src/outcome_persistence/*` — persistence semantics unchanged;
  the loader reads `memory.jsonl` but does not write it.

---

## 9. Summary of open decisions that gate the first B3 code PR

Matches `docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12` and
`docs/B3_CUMULATIVE_MEMORY_CONTRACT_DRAFT.md §13`:

- ⟨O1⟩ Loader reads `memory.jsonl` directly vs via
  `session_manager.load_session`.
- ⟨O2⟩ Where prior session `session_id` is sourced from the
  loaded content.
- ⟨O3⟩ `MAX_CUMULATIVE_MEMORY_RECORDS` location.
- ⟨O4⟩ CLI flag names (Slice 2D).
- ⟨O5⟩ Harness integration placement (Slice 2D).
- ⟨O6⟩ `cumulative_memory_summary` block shape (Slice 2C).

None of these decisions is made in this doc. Each resolution is
an input to the subsequent "B3 Slice 2A: contract module +
frozen tests" turn.
