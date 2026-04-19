# B3_CUMULATIVE_MEMORY_BOUNDARY.md

Status: **B3 Slice 1 draft (boundary only). No runtime logic, no
schema files, no test additions yet.**
Authority: `Path_C_Roadmap_v2_1.docx`, `PATH_C_BOUNDARY.md`,
`PATH_C_SCHEMA_REGISTRY.md`, `B1-B5_Implementation_Roadmap_Report.docx`,
`docs/B1_REPLAN_BOUNDARY.md` (additive-subpackage precedent),
`docs/B2_CORRELATOR_BOUNDARY.md` (additive-sibling precedent).

This document is the contract that governs any future B3 (Cross-
session cumulative memory) implementation PR. It does not itself
introduce runtime behavior, and it does not supersede
`PATH_C_BOUNDARY.md`; it narrows scope further for B3 and locks the
D1–Dn decisions in §12 below.

---

## 1. Purpose

Define the boundary within which the B3 *Cross-session cumulative
memory* branch may later be implemented, so that:

- Path C-min (Phases 0–3), B1 (Replan), and B2 (Event correlator)
  remain fully intact and regression-clean.
- B3 code is strictly additive over the existing three-layer
  separation (Path B raw → Path C session overlay → Path C session
  artifact), matching the additive pattern used by
  `src/replan/` and `src/correlator/`.
- B3 never becomes a vehicle for exposing memory to agent prompts,
  rewriting Path C-min, relaxing the append-only `EpisodicMemory`
  rule, or widening the adaptive-gate consumer surface.
- A future reviewer can answer "is this PR inside B3 Slice N
  scope?" from this file alone, not from conversation history.

## 2. Why B3 is the next branch now

- Path C-min closes the single-session decision loop. B1 closes
  bounded temporal replanning within a single event. B2 closes
  same-session compound-pattern observability. B3 is the smallest
  useful extension that exercises the *cross-session* dimension:
  legitimately carry memory forward from earlier sessions into a
  later session, so a `PATH_C_WARM` run sees a larger, more
  realistic record history than synthetic seed data.
- The runtime seam already exists: `run_session(initial_memory=...)`
  accepts an `EpisodicMemory` whose records the orchestrator seeds
  into the session's memory via `_seed_memory`. `MemoryRecord`
  already carries `session_id`, so cross-session provenance is
  preserved row-by-row without any schema change. The harness
  already demonstrates mode-gated warm-memory attachment via
  `_build_synthetic_warm_memory` for `PATH_C_WARM` only.
- What is **missing** is a canonical loader and a locked set of
  merge / dedupe / bounded-growth semantics. B3 Slice 1 answers
  those; later slices land the loader and later still, optional
  compare-report visibility and CLI/harness flags.
- B4 (agent-visible memory) and B5 (frontend) are larger-footprint
  or contract-sensitive branches. B3 deliberately stops *before*
  anything that would let a `MemoryRecord` reach an agent prompt.

## 3. In-scope (for the future B3 implementation PR; NOT this turn)

B3 implementation (across slices) will be allowed to:

1. Add a new Path C module (preferred path:
   `src/learning/cumulative_memory.py`) that is included in the
   Path-C AST-scan roots via the existing
   `tests/test_path_c_import_topology.py` surface.
2. Introduce a new frozen dataclass (preferred name:
   `CumulativeMemoryConfig`) carrying the caller's ordered list of
   prior-session references and the locked dedupe policy literal.
   No new `MemoryRecord` / `MemoryQuery` / `MemorySummary` shape —
   `MemoryRecord.session_id` already carries per-row provenance.
3. Introduce a pure loader function (preferred name:
   `load_cumulative_memory(...)`) that reads `memory.jsonl` files
   from the locked canonical source and returns a fresh
   `EpisodicMemory` whose rows satisfy the dedupe invariant.
4. Use the **existing** `run_session(initial_memory=...)` seam
   as the primary runtime integration — the loader's output is
   what the caller passes as `initial_memory`. Adding a new
   top-level `cumulative_memory_config` kwarg to `run_session`
   is a possible *later* refinement, not the Slice 2A/2B default
   path (see §12 D8).
5. Add a workflow / orchestration rule, documented here and
   enforced at the caller surface (CLI / harness in a later
   slice), that cumulative memory is attached only for
   `PATH_C_WARM` runs. `BASELINE_STATIC` and `PATH_C_COLD` keep
   the current no-initial-memory expectation for thesis
   comparability; this is a workflow property, not a change to
   the `run_session` API surface.
6. Extend digest inputs **additively and conditionally**. The
   content fingerprint of cumulative memory is already captured
   by the existing `initial_memory_digest` contribution to
   `session_id`. Any additional source-intent fingerprint (e.g.
   ordered prior `session_id`s or ordered per-file digests) is
   added only as a conditional `config_for_digest` fragment that
   appears when cumulative memory is actually used (mirroring the
   B1/B2 conditional fragments).
7. Add new tests under `tests/test_cumulative_memory_*` covering
   loader purity, dedupe determinism, bounded-growth invariants,
   and replay byte identity when cumulative memory is enabled.
8. Optionally extend `src/session/session_compare.py` additively
   (later slice) with a conditional `cumulative_memory_summary`
   sibling block. This is reserved for a future slice and
   explicitly NOT in Slice 2A/2B scope.
9. Optionally add `--prior-session-dir` (repeatable) +
   `--cumulative-dedupe-policy` flags on
   `scripts/run_session.py` and `scripts/session_eval_harness.py`
   in a later slice. Default off; pre-B3 byte identity preserved.

## 4. Explicit out-of-scope

B3 MUST NOT, in its first implementation PR or any follow-up
labelled B3 Slice 1/2A/2B/2B.5:

1. Expose any `MemoryRecord` field, any memory summary, or any
   loader output to an agent prompt. Memory stays behind the
   adaptive policy gate — that's B4's territory, and a B3 PR
   that touches `src/agents/*` is out-of-scope.
2. Relax the `EpisodicMemory` append-only contract. No delete,
   no update, no replace, no mid-session re-seed. The loader
   returns a **fresh** `EpisodicMemory`; it never mutates an
   existing one.
3. Change the `MemoryRecord` schema, the `MemoryQuery` schema,
   or the `MemorySummary` schema. They stay at 1.0.
4. Change `AdaptivePolicyGateConfig` / `decide_policy_adaptive`
   consumption semantics. In particular, B3 does NOT introduce a
   same-session filter, a cross-session filter, or any
   session-id-aware branching inside the adaptive gate.
5. Change the `session_id` digest formula. The formula stays
   `sha256(f"{seed}|{config_digest}|{event_stream_digest}|{initial_memory_digest}")`;
   only the inputs `config_for_digest` consumes may expand
   additively, and only conditionally.
6. Propose raw filesystem paths (`prior_session_dirs`,
   `/tmp/run_42/memory.jsonl`, etc.) as a canonical `session_id`
   digest input. Filesystem paths are not portable, not stable,
   and not content-addressed — they are a CLI/caller convenience,
   not a digest ingredient. The locked digest ingredients are
   either (a) ordered prior `session_id` strings, or (b) ordered
   per-file content digests of the source `memory.jsonl` blobs,
   or (c) nothing beyond the already-existing
   `initial_memory_digest`. See §12 D5.
7. Change the core `run_session(..., initial_memory=...)` API
   semantics. "`PATH_C_WARM`-only consumption" is a workflow /
   orchestration rule enforced at the caller boundary (loader,
   CLI, harness), not a gate that `run_session` grows in Slice
   2A/2B. A future slice may harden this with an optional reject
   guard, but that is not the default first move.
8. Collapse `GovernanceTruthRef` and `EffectiveDecisionRef`,
   mutate `SessionEventRecord.baseline_event_result`, or add any
   new field to `SessionEventRecord`. Cross-session provenance
   lives on `MemoryRecord.session_id`, not on per-event overlay
   fields.
9. Introduce unbounded prior-memory loading. The loader enforces
   a hard cap (module constant, suggested `MAX_CUMULATIVE_MEMORY_RECORDS`)
   and raises above the cap. Exceeding the cap is an error, not
   a soft truncate.
10. Cross into B2 correlator territory. B3 does not read or write
    `correlation_context`; the correlator does not depend on
    cumulative memory.
11. Cross into B4 / B5. No agent-visible memory. No frontend
    visualization. A B3 PR that incidentally touches those
    surfaces is out-of-scope.
12. Introduce wall-clock, `uuid4`, or `data/cases` access
    anywhere under `src/learning/cumulative_memory.py`.

## 5. Preserved invariants (non-negotiable)

All invariants from `PATH_C_BOUNDARY.md` §1,
`docs/B1_REPLAN_BOUNDARY.md` §5, and
`docs/B2_CORRELATOR_BOUNDARY.md` §5 stand unchanged under B3. B3
additionally preserves:

- **EpisodicMemory append-only rule.** The loader produces a new
  `EpisodicMemory` by construction; no existing memory is
  mutated; no delete/update primitive is introduced.
- **Canonical observable order** `(event_timestamp, event_id)`
  stays intact. Cross-session rows interleave with self-session
  rows under this order — the adaptive gate already reads rows
  by structural query, not insertion order, so interleaving is
  semantically neutral.
- **Policy-only learning injection.** The adaptive policy gate
  is the only consumer of `MemoryRecord`. B3 does not add a
  second consumer surface. Loader output feeds the adaptive gate
  through the existing `initial_memory → _seed_memory → memory →
  decide_policy_adaptive` path and nowhere else.
- **Row-level provenance.** `MemoryRecord.session_id` is the
  canonical cross-session provenance field. No new provenance
  overlay on `SessionEventRecord`, no new per-record flag like
  `is_cross_session: bool`.
- **Deterministic-first.** The loader is a pure function of its
  inputs (ordered prior-session references + locked dedupe
  policy). It does not call `datetime.now()`, `time.time()`,
  `uuid4()`, and does not read `data/cases/*.json`.
- **Dual-track rule.** `GovernanceTruthRef` /
  `EffectiveDecisionRef` unchanged.
- **Bounded action set.** Cross-session memory does not expand
  `adjustment_type`; the adaptive gate still emits only
  `UPGRADE_ONE_LEVEL / NO_ADJUSTMENT / COLD_START_FALLBACK`.
- **Structural explainability.** Every MemoryRecord retains its
  existing structured fields. No free-text-as-truth leak through
  the loader.

## 6. Allowed files to touch later (B3 PR allowlist)

The future B3 PR may *create* files under:

- `src/learning/cumulative_memory.py` (new module; expected
  members in `docs/B3_CUMULATIVE_MEMORY_FILE_MAP.md`). Placing
  the loader inside `src/learning/` matches the additive-
  subpackage convention — it sits next to `episodic_memory.py`
  as a loader layer, not a new consumer layer.
- `tests/test_cumulative_memory_*.py`
- `tests/fixtures/cumulative_memory_*` (if fixture-based
  snapshots are needed)

The future B3 PR may *additively* modify, but must not rewrite
or repurpose:

- `PATH_C_SCHEMA_REGISTRY.md` — register `CumulativeMemoryConfig`
  at 1.0.
- `PATH_C_BOUNDARY.md` — append a B3 cross-reference line
  alongside the B1 / B2 references. Existing §1–§8 unchanged.
- `tests/test_path_c_import_topology.py` — add the new module's
  path to the scan roots.

Later-slice additive surfaces (explicitly NOT in Slice 1/2A/2B):

- `scripts/run_session.py` — add `--prior-session-dir`
  (repeatable) + `--cumulative-dedupe-policy` flags. Default
  off.
- `scripts/session_eval_harness.py` — mirror those flags. Thread
  the resulting `CumulativeMemoryConfig` → loader →
  `EpisodicMemory` through the **existing**
  `run_session(initial_memory=...)` seam for `PATH_C_WARM` only.
- `src/session/session_compare.py` — optional conditional
  sibling block `cumulative_memory_summary`. No bump of
  `COMPARE_REPORT_SCHEMA_VERSION`.
- `docs/path_c_thesis_alignment.md` — optional B3 addendum.

The future B3 PR may *not* additively modify:

- `src/event_loop_c.py` core API. `run_session(initial_memory=...)`
  stays as-is in Slice 2A/2B. (A possible future slice may add an
  optional reject-guard for non-PATH_C_WARM — see §12 D8 — but
  that is NOT the first-cut integration path and is not in this
  slice's allowlist.)
- `src/learning/episodic_memory.py` — append-only + canonical
  order stay exactly as today.
- `src/learning/memory_schema.py` — `MemoryRecord`,
  `MemoryQuery`, `MemorySummary` stay at 1.0.
- `src/adaptive/*` — no consumer change.
- `src/replan/*` — no coupling in B3.
- `src/correlator/*` — no coupling in B3.

## 7. Forbidden files / forbidden modifications

B3 MUST NOT touch, in any PR:

- `src/agents/**` — any agent, any agent output schema.
- `src/policy_gate.py` — `PolicyDecision`, `decide_policy` stay
  frozen.
- `src/outcome_schema.py` — `ExecutionOutcome` stays frozen.
- `src/event_schema.py` — `EventPayload`, `EventType` stay
  frozen.
- `src/evaluation.py`, `src/action_code_mapper.py` — Research
  Core.
- `data/cases/*.json` — Research Core data.
- `src/graph.py` node wiring.
- `src/execution_adapters.py`.
- `src/event_loop.py` (Path B core).
- `src/session/session_schema.py` — no new field on
  `SessionEventRecord`, `SessionArtifact`, or
  `SessionConfig` in Slice 2A/2B.
- `src/session/kpi_calculator.py` — no KPI change in any B3
  slice.
- `src/session/digests.py` — `digest_memory_records`,
  `compute_session_id`, `memory_record_id` formulas stay
  untouched; the digest formula is not extended. (Source-intent
  fragments, if any, live inside `config_for_digest` payloads
  that already flow through `digest_config_dict` — no new API
  needed.)

Forbidden modification classes:

- Any change that would cause `BASELINE_STATIC` mode to produce a
  byte non-equal `SessionArtifact` for a given seed/event stream
  when no cumulative memory is attached.
- Any change that would cause `PATH_C_COLD` / `PATH_C_WARM` with
  the default loader (cumulative disabled / empty
  `CumulativeMemoryConfig`) to diverge from current behavior
  byte-for-byte.
- Any change to the canonical JSON byte layout of Phase-3
  compare reports under default harness flags.
- Any change that introduces a second memory consumer outside
  the adaptive gate.
- Any change to `MemoryRecord`'s observable field set or order.

## 8. B3-specific risks (and their mitigations)

| # | Risk | Mitigation (mandatory for B3 implementation PR) |
|---|---|---|
| R1 | Silent dedupe drift — two callers feeding the same prior session produce different loader output | Dedupe by the `(session_id, event_timestamp, event_id)` triple. Same triple + equal row content → silently drop. Same triple + non-equal content → hard error at loader boundary. Tested with constructed collision fixtures. |
| R2 | Contamination of BASELINE_STATIC / PATH_C_COLD comparability | `PATH_C_WARM`-only attachment is a workflow / orchestration rule enforced at the caller boundary (loader entry, CLI, harness). The `run_session` core API does NOT silently reject or ignore; callers don't attach in the first place. Pinned via harness integration tests. |
| R3 | Ambiguous session_id contribution | `initial_memory_digest` already sees the resulting memory bytes. Source-intent fragments, if any, use ordered prior `session_id` strings (preferred) or ordered per-file content digests. **Raw filesystem paths are explicitly forbidden as digest input** — they are non-portable and not content-addressed. |
| R4 | Adaptive gate accidentally growing a session-id-aware filter | `src/adaptive/*` is on the forbidden-modification list for B3. A source scan asserts no B3 PR touches it. |
| R5 | Agent-prompt contamination (B4 leak) | `src/agents/*` is forbidden. AST / import-topology scan asserts `src/learning/cumulative_memory.py` does not import `src/agents/*`. |
| R6 | Wall-clock leakage via file timestamps | The loader reads only `memory.jsonl` content, never `os.stat` metadata, `ctime`, `mtime`, or `time.time()`. The Path-C AST scan already enforces this for `src/learning/`. |
| R7 | Unbounded memory growth | `MAX_CUMULATIVE_MEMORY_RECORDS` module constant; loader raises above the cap. No soft truncate — callers that hit the cap must choose a smaller prior-session set explicitly. |
| R8 | Replay byte drift | Loader output is a pure function of `CumulativeMemoryConfig`. When cumulative is disabled / empty, no bytes change. Replay byte identity preserved for pre-B3 inputs. Parametrized save/load/replay tests added in Slice 2B.5. |
| R9 | EpisodicMemory append-only silently relaxed | The loader returns a fresh `EpisodicMemory`. An invariant test asserts `load_cumulative_memory(...)` does not mutate the fs-source state or any pre-existing `EpisodicMemory` object. |
| R10 | B3 drifts into B4 | Forbidden modification of `src/agents/*` + AST check that `src/learning/cumulative_memory.py` does not import any agent module. A second integration test asserts agent prompt inputs are byte-identical whether cumulative memory is empty or populated (same test shape as B2 G5). |

## 9. How B3 stays separate from B4

B3 = what the *adaptive policy gate* sees as its historical row
set can legitimately come from prior sessions.
B4 = what an *agent prompt* sees can include memory-derived
content.

Structural separators:

- B3 touches `src/learning/` only. It does not create, edit, or
  import from `src/agents/`.
- B3 produces an `EpisodicMemory` object. It does not produce a
  prompt string, a summary paragraph, or any natural-language
  artifact.
- B3's loader output is consumed by `run_session` through the
  existing `initial_memory` seam. It is NOT consumed by any
  prompt-building layer.
- An AST scan on `src/learning/cumulative_memory.py` will assert
  no import from `src/agents/`, no reference to agent output
  field names, and no construction of prompt-like strings.
- The thesis report's eventual `cumulative_memory_summary`
  block, if landed in a later B3 slice, is structural (source
  session ids + row counts), never a natural-language
  recapitulation.

A B3 PR that enables any of the above (prompt injection, agent-
visible summary, free-text explanation of prior sessions) is out-
of-scope regardless of label. That work belongs to B4 under its
own boundary doc.

## 10. Rollback rules

If the first B3 implementation PR, or any follow-up, causes any
of the following, it MUST be reverted (not patched forward):

- A Path C-min / B1 / B2 test regresses: any test currently
  passing on `main` in the files listed under
  `docs/B2_CORRELATOR_BOUNDARY.md §9` plus every
  `test_correlator_*.py` test.
- `BASELINE_STATIC` session artifact bytes change for any seed
  that passed before and no cumulative memory is attached.
- `PATH_C_COLD` / `PATH_C_WARM` session artifact bytes change
  for any seed that passed before when `CumulativeMemoryConfig`
  is empty / disabled.
- Canonical JSON of the existing Phase-3 compare report changes
  under default harness flags.
- The AST import-topology scan grows a new allowed import or a
  new exception.
- Agent prompt inputs change in any byte-observable way.

Partial B3 landings must be rolled back as a whole — no half-
implemented loader, no "docs landed but schema not".

## 11. Acceptance gates for future implementation

The B3 implementation PR (across 2A / 2B / 2B.5) will be
considered acceptable only if ALL of the following hold
simultaneously:

- **G1 Contracts first.** `CumulativeMemoryConfig` lands as a
  frozen schema with frozen tests, before any runtime logic.
  Registered in `PATH_C_SCHEMA_REGISTRY.md`.
- **G2 Loader purity.** `load_cumulative_memory(...)` is a pure
  function: no `datetime.now()`, no `uuid4()`, no
  `data/cases/*` access, no file-timestamp use, no global
  mutable state read. Tested.
- **G3 Dedupe determinism.** A fixed ordered list of prior-
  session sources produces a byte-identical `EpisodicMemory`
  snapshot across two fresh subprocesses (varied
  `PYTHONHASHSEED`).
- **G4 Collision handling.** Duplicate-but-equal rows silently
  drop; duplicate-but-different rows raise. Tested with
  constructed fixtures.
- **G5 EpisodicMemory append-only preserved.** No mutation of
  any pre-existing `EpisodicMemory`; the loader constructs a
  fresh one.
- **G6 `BASELINE_STATIC` / `PATH_C_COLD` byte identity.** When
  cumulative is disabled/empty, artifact bytes match pre-B3 for
  all seeds tested.
- **G7 `PATH_C_WARM` replay byte identity.** When cumulative is
  enabled with a fixed `CumulativeMemoryConfig`, repeated runs
  produce byte-identical artifacts.
- **G8 Mode-gating workflow.** The caller surface (CLI /
  harness) attaches cumulative memory only to `PATH_C_WARM`;
  tested by inspecting harness `run_session` kwargs. (Core
  `run_session` semantics unchanged in this slice.)
- **G9 No reverse adaptive coupling.** AST scan asserts
  `src/adaptive/*` does not import `src/learning/cumulative_memory.py`.
- **G10 No agent coupling.** AST scan asserts
  `src/learning/cumulative_memory.py` does not import
  `src/agents/*`, does not reference the five forbidden
  natural-language governance field names, and does not
  construct prompt-like strings.
- **G11 Bounded-growth.** Loader raises above
  `MAX_CUMULATIVE_MEMORY_RECORDS`.
- **G12 Honesty rule.** If enabling cumulative memory under
  `PATH_C_WARM` degrades the thesis claim, the report reports
  it honestly. No code branch suppresses a negative finding.

No gate may be waived. A single failing gate blocks the B3 PR.

---

## 12. Owner-fixed decisions for B3 Slice 1 (locked for this
turn)

Parallel to `docs/B1_REPLAN_BOUNDARY.md §12` and
`docs/B2_CORRELATOR_BOUNDARY.md §12`. Structural consequences are
enforced by tests and the schema registry once the implementation
PR lands.

- **D1 — Dedupe policy: dedupe-union, keyed by
  `(session_id, event_timestamp, event_id)`.**
  Duplicate-but-equal rows silently drop. Duplicate-but-
  different rows raise `CumulativeMemoryCollisionError` (or
  equivalent) at loader boundary — never silently overwrite.
  Rationale: prevents the adaptive gate from seeing two
  contradictory rows for the same triple without a human
  noticing.

- **D2 — Canonical prior-memory source: `memory.jsonl` files
  from a caller-supplied ordered list of prior-session
  references.** The reference is per-session, not per-file-
  path for digest purposes — the canonical source-intent
  identifier is the prior session's `session_id` (or, if
  unavailable from the loaded content, the content digest of
  the source file). **Raw filesystem paths are a caller
  convenience, not a digest ingredient.** Loading via
  `session_manager.load_session(...)` is an acceptable
  implementation; loading via direct `memory.jsonl` read is
  also acceptable. Either way, the parsed result must be a
  list of `MemoryRecord` instances, validated.

- **D3 — Raw `MemoryRecord` union is sufficient; no new overlay
  schema.** `MemoryRecord.session_id` already serves as
  per-row provenance. No `CumulativeMemoryRecord`,
  `CrossSessionMemoryRecord`, or wrapper class. The loader
  returns `EpisodicMemory` as the universal type.

- **D4 — First-cut runtime path: the existing
  `run_session(initial_memory=...)` seam.** The loader
  returns an `EpisodicMemory`; the caller (CLI / harness /
  test) passes it through the already-present `initial_memory`
  kwarg. **No new `cumulative_memory_config` kwarg on
  `run_session` in Slice 2A/2B.** A future slice may explore
  a convenience kwarg, but the default first move is to reuse
  the existing seam. This matches §7's rule that the core
  API doesn't grow a B3-specific surface.

- **D5 — `session_id` digest contribution.** The content
  fingerprint is already captured by the pre-existing
  `initial_memory_digest` (computed over the effective
  `EpisodicMemory.snapshot()["records"]`). Any **source-
  intent fragment** added to `config_for_digest` encodes
  *ordered prior `session_id` strings* (preferred) or
  *ordered per-file content digests of the source
  `memory.jsonl` blobs*. **Raw filesystem paths are
  forbidden as digest input** — non-portable, not content-
  addressed, would silently break replay across machines. The
  fragment appears in `config_for_digest` only when the
  loader was actually invoked with a non-empty
  `CumulativeMemoryConfig` (conditional fragment pattern,
  mirroring B1/B2).

- **D6 — Bounded growth: hard cap via
  `MAX_CUMULATIVE_MEMORY_RECORDS` module constant (suggested
  value 1000).** Loader raises above the cap. No soft
  truncate — callers hitting the cap must select a smaller
  prior-session set explicitly.

- **D7 — Mode gating: `PATH_C_WARM`-only, enforced at the
  caller surface.** Harness / CLI attach cumulative memory to
  `PATH_C_WARM` runs only; `BASELINE_STATIC` and
  `PATH_C_COLD` receive `initial_memory=None` (today's
  behavior). **This is a workflow / orchestration rule, not a
  change to the `run_session` API.** A future slice may add
  an optional reject-guard on `run_session`, but that is
  explicitly out of scope here and requires its own owner-
  approved boundary update (see D8).

- **D8 — Future `run_session` reject-guard is deferred.**
  If the owner later decides cumulative memory should hard-
  error when attached to `BASELINE_STATIC` or `PATH_C_COLD`,
  that is a separate follow-up slice with its own boundary
  amendment. Slice 2A/2B lands neither the guard nor a
  corresponding API change.

- **D9 — Compare/report visibility is deferred to Slice 2C
  (optional).** No `cumulative_memory_summary` block in
  Slice 2A/2B. `COMPARE_REPORT_SCHEMA_VERSION` will **not**
  be bumped by B3 (mirroring B2's decision to keep it at
  `"1.1"`). When Slice 2C eventually lands, the block is
  conditional — pre-B3 compares stay byte-identical.

- **D10 — Source resolution is a kwarg-only caller-supplied
  callable.** (Locked in Slice 2A.5.) The loader signature is
  `load_cumulative_memory(config, *, source_resolver) -> EpisodicMemory`.
  `source_resolver: Callable[[str], list[MemoryRecord]]` is
  required (no default) and maps each canonical prior-session
  ref from `config.prior_session_refs` to a list of validated
  `MemoryRecord` rows. The loader itself does not touch the
  filesystem — it iterates refs, calls the resolver once per
  ref, and then dedupes/caps/assembles a fresh
  `EpisodicMemory`. Concrete resolvers live outside the module:
  the Slice 2D CLI supplies one that reads `memory.jsonl` from
  disk; Slice 2B / 2B.5 tests supply in-memory fixture
  resolvers. **The resolver is NOT a digest ingredient** — only
  `prior_session_refs` is, and only conditionally via the
  `config_for_digest` fragment. Raw filesystem paths remain
  forbidden at the loader boundary; they may only appear inside
  a concrete resolver's implementation, never in its input.

These decisions are not renegotiable in Slice 2A/2B. A future
design that needs to relax them (for example, a new dedupe
policy literal, or a core `run_session` API change) is a
separate, owner-approved boundary amendment, not a B3 in-scope
change.

---

## 13. Non-goals for B3 (reminder)

- Agent-visible memory (B4, not B3).
- Memory-summary-as-prompt-input (B4).
- Cross-session-aware adaptive-gate filtering.
- Cross-session correlation (not B2, not B3).
- Frontend visualization of memory provenance (B5).
- A new top-level `cumulative_memory_config` kwarg on
  `run_session` in Slice 2A/2B.
- Any change to `run_session(initial_memory=...)` semantics in
  Slice 2A/2B.
- Any `SessionEventRecord` field for cross-session provenance —
  `MemoryRecord.session_id` is the canonical home.
- Any `SessionKPIs` change (no B3 KPI).

## 14. B3 Slice 1 delivery checklist

Slice 1 lands only this docs set. No source, no tests, no
registry updates. The delivery is considered complete when:

- [x] `docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md` exists (this file).
- [x] `docs/B3_CUMULATIVE_MEMORY_CONTRACT_DRAFT.md` exists.
- [x] `docs/B3_CUMULATIVE_MEMORY_FILE_MAP.md` exists.
- [x] The three docs align with `docs/B2_CORRELATOR_BOUNDARY.md`
      precedent and contradict none of `PATH_C_BOUNDARY.md`,
      `PATH_C_SCHEMA_REGISTRY.md`, or the B1/B2 boundary docs.

Slice 2A+ remains future work and must not begin until D1–D10
are reconfirmed.
