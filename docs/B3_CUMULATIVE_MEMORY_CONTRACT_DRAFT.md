# B3_CUMULATIVE_MEMORY_CONTRACT_DRAFT.md

Status: **B3 Slice 1 draft.** Decisions D1–D9 in
`docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12` are **proposed** and,
once accepted, will be treated as LOCKED in parallel with the
B1/B2 D1–D5 pattern. Runtime logic (the loader, any digest
fragment addition) is deferred to Slice 2A/2B+.
Authority: `docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md`,
`PATH_C_BOUNDARY.md`, `PATH_C_SCHEMA_REGISTRY.md`.

This document enumerates the minimal schema surface B3 Slice 1
needs. It is the parallel of `docs/B1_REPLAN_CONTRACT_DRAFT.md`
and `docs/B2_CORRELATOR_CONTRACT_DRAFT.md` for the cumulative-
memory branch. It does NOT propose runtime behavior.

---

## 1. `CumulativeMemoryConfig` — candidate contract

The configuration record describing which prior sessions the
loader must consume and how collisions are handled. Parallel in
spirit to `ReplanConfig` / `CorrelatorConfig`: a frozen dataclass
with `__post_init__` validation, no runtime logic.

### 1.1 Why this has to exist as a structured value

The loader's input cannot be a bare list of filesystem paths
because:

- Filesystem paths are not portable (absolute paths break
  across machines; relative paths depend on CWD).
- Filesystem paths are not content-addressed (a path can silently
  swap content beneath the loader between two runs).
- A config object centralizes validation (order, dedupe policy,
  bounded-growth cap) so each caller (test, CLI, harness) gets
  the same guarantees.

Paths remain a **caller-level input to the CLI layer**; they are
resolved into content and/or session-id references before they
reach the loader's digest surface. See §4 and §5.

### 1.2 Proposed fields

Frozen dataclass (not pydantic; matches the `ReplanConfig` /
`CorrelatorConfig` precedent). `__post_init__` enforces every
invariant.

| Field | Type | Notes |
|---|---|---|
| `prior_session_refs` | `tuple[str, ...]` | Ordered list of prior session references. Each entry is a canonical prior-session `session_id` string (preferred) or, equivalently, a reference the loader can resolve to exactly one `memory.jsonl`-equivalent record set. **Not filesystem paths.** The caller CLI/harness is responsible for turning user-supplied dirs into these references. |
| `dedupe_policy` | `Literal["drop_equal_raise_mismatch"]` | Closed single-value Literal in Slice 2A. See §3. |
| `max_records` | `int` | Bounded-growth cap. Defaults to `MAX_CUMULATIVE_MEMORY_RECORDS`. |
| `schema_version` | `str` | `"1.0"`. |

Explicitly NOT on `CumulativeMemoryConfig`:

- `prior_session_dirs: list[str]` — raw filesystem paths. These
  are CLI-layer inputs only (see §5).
- `include_agents: bool` — would widen into B4.
- `summary_template: str` — would widen into B4.
- `session_id_filter: str | None` — would quietly reshape the
  adaptive-gate's query surface; forbidden.

### 1.3 Invariants (tested in Slice 2A)

- `prior_session_refs` is a tuple (frozen); each entry is a non-
  empty string; order is the caller's responsibility.
- `dedupe_policy == "drop_equal_raise_mismatch"` (closed Literal
  in Slice 2A).
- `0 <= max_records <= MAX_CUMULATIVE_MEMORY_RECORDS`.
- `extra='forbid'` equivalent on the dataclass (no silent extra
  fields).

## 2. Closed Literal surfaces

One closed Literal is introduced in Slice 2A.

```
CUMULATIVE_MEMORY_DEDUPE_POLICY = Literal[
    "drop_equal_raise_mismatch",
]
```

Slice 2A admits exactly one policy (see §3). Opening the set is
a MINOR bump on this Literal and a same-PR registry update.

## 3. Dedupe policy

Single admitted policy in Slice 2A: **`drop_equal_raise_mismatch`**.

Semantics:

- **Unique key** for dedupe:
  `(session_id, event_timestamp, event_id)`.
  This matches the triple already used by
  `session.digests.memory_record_id(...)` — the natural
  primary key of a `MemoryRecord`.

- **Same triple, byte-equal rows** (after `model_dump`) →
  silently drop the second occurrence. Rationale: the caller
  may legitimately pass the same prior session twice (e.g., via
  two overlapping warm-memory sets); dropping is safe because
  the row content is identical.

- **Same triple, non-equal rows** → raise a loader-level hard
  error (e.g., `CumulativeMemoryCollisionError`). Rationale: if
  two sources disagree on what happened at the same
  (session_id, event_timestamp, event_id), the adaptive gate
  would see silently contradictory history. This is a source-
  corruption or config-mistake signal, not a runtime condition
  to paper over. Surfacing the error stops the session before
  any adaptive decision is taken on bad inputs.

## 4. Canonical source of prior memory

Locked canonical source: **`memory.jsonl` files** from caller-
supplied prior-session references. Rationale:

- `memory.jsonl` is already the canonical per-session memory
  on-disk form (`session_manager.save_session` writes one
  `MemoryRecord.model_dump()` per line in canonical JSON).
- The loader reads the file as bytes, parses each line, and
  validates each row into a `MemoryRecord`. No partial-row
  recovery, no comment handling — the file format is either
  the canonical one or the loader raises.
- `session_manager.load_session(dir)` is an acceptable richer
  alternative that additionally reconstructs a `SessionArtifact`
  and extracts `artifact.memory_snapshot["records"]`. Slice 2A
  may choose either path; both flow into the same dedupe + cap
  pipeline afterwards.

## 5. Source resolution at the caller boundary

The loader **does not touch the filesystem**. The CLI / harness
layer (future Slice 2D) supplies a kwarg-only callable,
`source_resolver: Callable[[str], list[MemoryRecord]]`, which
the loader invokes once per ref in
`config.prior_session_refs`. This is the source-resolution
contract locked in D10 (Slice 2A.5) — see
`docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12 D10`.

Loader signature (final, Slice 2A):

```
def load_cumulative_memory(
    config: CumulativeMemoryConfig,
    *,
    source_resolver: Callable[[str], list[MemoryRecord]],
) -> EpisodicMemory
```

### 5.1 Two canonical ref encodings

The caller chooses how to encode a ref. Both encodings are
admissible:

- **Per-session ref:** the canonical prior-session ``session_id``
  string. Preferred — content-addressed and portable.
- **Content-digest ref:** a SHA-256 hex string computed over
  the prior ``memory.jsonl`` bytes. Acceptable when a session
  id is not available (e.g., synthetic fixtures).

Whichever encoding the caller uses, the resolver must map it
to `list[MemoryRecord]` the same way for every call — the
resolver is a **pure function** of its input ref.

### 5.2 Concrete resolver implementations

All concrete resolvers live **outside** `src/learning/
cumulative_memory.py`:

- **CLI resolver (Slice 2D):** built inside
  `scripts/run_session.py` / `scripts/session_eval_harness.py`
  from user-supplied `--prior-session-dir` arguments. It reads
  each directory's `memory.jsonl`, parses each line into a
  `MemoryRecord`, and returns the list. Any filesystem-path
  manipulation is confined to this layer.
- **Test resolver (Slice 2B / 2B.5):** an in-memory
  `dict[str, list[MemoryRecord]]` lookup, usually constructed
  from constructed fixtures.
- **Harness resolver (Slice 2D):** a thin wrapper around the
  CLI resolver that's shared across the three compared
  sessions.

### 5.3 Forbidden placements

- **Raw filesystem paths MUST NOT appear inside the loader's
  inputs.** Neither `CumulativeMemoryConfig` field values nor
  any `config_for_digest` fragment carries a path. They may
  appear only inside a concrete resolver's implementation —
  and only as an internal detail of that resolver.
- **The resolver itself is NOT a digest ingredient.** Two
  callers that supply different resolvers which produce the
  same row content for the same ref produce byte-identical
  `EpisodicMemory.snapshot()` output, therefore identical
  `initial_memory_digest`. Determinism flows from ref content,
  not from resolver identity.
- **The loader never accepts `None` for the resolver.** The
  resolver is a required kwarg-only parameter. Empty
  `prior_session_refs` is still legal, but the caller must
  still pass *some* resolver (e.g. `lambda ref: []`) — the
  loader's body will never invoke it in that case but the
  contract stays explicit at the call site.

## 6. Raw `MemoryRecord` union is sufficient

Slice 2A does NOT introduce a new schema type for cross-session
records. Rationale:

- `MemoryRecord.session_id` already carries per-row provenance.
  Readers separating cross-session from self-session rows do so
  by filtering on `session_id`.
- The adaptive gate reads `MemoryRecord` rows by structural
  query (event_type, action_type, final_route). It has no field
  it would need from a "CumulativeMemoryRecord" wrapper.
- Introducing a wrapper type would invite the adaptive gate's
  consumer surface to widen — which is explicitly forbidden
  under the B3 boundary's R4 risk.

The loader therefore returns a plain `EpisodicMemory` whose
records are `MemoryRecord` instances validated from the prior
`memory.jsonl` lines. Nothing new on the schema registry side
except `CumulativeMemoryConfig` itself.

## 7. Workflow rule — `PATH_C_WARM`-only consumption

Locked rule: **cumulative memory is attached only to
`PATH_C_WARM` runs**, enforced at the caller surface (loader
entry, CLI, harness) — not in `run_session`.

- `BASELINE_STATIC` and `PATH_C_COLD` runs never receive a non-
  empty `initial_memory`. Their thesis-comparability invariant
  is preserved by never calling the loader for them, not by
  letting `run_session` silently reject an attachment.
- The first-cut runtime path is: caller constructs
  `CumulativeMemoryConfig` → caller calls
  `load_cumulative_memory(config) -> EpisodicMemory` → caller
  passes the result to
  `run_session(mode="PATH_C_WARM", initial_memory=...)`.
  **No new `run_session` kwarg.**
- A possible future reject-guard on `run_session` (raising if
  `initial_memory` is non-empty for non-`PATH_C_WARM` modes) is
  a separate owner-approved amendment. Slice 2A/2B does not
  propose it.

## 8. Digest contribution principles

Two axes of digest contribution:

1. **Content fingerprint.** Already captured by the pre-
   existing `initial_memory_digest` — a SHA-256 over
   `canonical_json(EpisodicMemory.snapshot()["records"])`. This
   input to `compute_session_id` changes automatically when the
   loader's output changes. No new code needed.

2. **Source-intent fingerprint.** Optional additional fragment
   in `config_for_digest`, emitted **only** when cumulative
   memory was actually invoked with a non-empty
   `CumulativeMemoryConfig`. Encodes the ordered list of prior
   `session_id` strings (or content digests, per §5). The
   fragment distinguishes two runs that, by coincidence, produce
   equal memory bytes from two intentionally different source
   sets. Mirrors the B1/B2 conditional fragments.

The `session_id` digest formula
(`sha256(f"{seed}|{config_digest}|{event_stream_digest}|{initial_memory_digest}")`)
is **not changed**. Only the inputs `config_for_digest`
synthesizes expand additively.

**Raw filesystem paths are explicitly forbidden as digest
ingredients** — see §5.

## 9. Bounded growth

- Module constant `MAX_CUMULATIVE_MEMORY_RECORDS: Final[int]`,
  suggested value `1000`. Hard cap — exceeding raises.
- The cap is measured on the **post-dedupe** record count.
- `CumulativeMemoryConfig.max_records` is an additional
  per-config narrower cap (≤ `MAX_CUMULATIVE_MEMORY_RECORDS`).

## 10. Eventual compare/report visibility (deferred, Slice 2C)

**This section is a forward-looking sketch. Slice 2A/2B does
NOT implement it.**

When Slice 2C lands (if the owner wants it), a conditional
sibling block on the compare report — tentatively
`cumulative_memory_summary` — would describe, per mode that ran
with cumulative memory:

- `prior_session_refs` (ordered list),
- `records_loaded` (post-dedupe count),
- `collisions_dropped` (duplicate-but-equal count),
- `per_prior_session_row_counts` (map from prior session id to
  row count contributed).

The block is conditional (absent when no cumulative memory was
attached anywhere), additive (no existing-field semantics
change), and does NOT bump `COMPARE_REPORT_SCHEMA_VERSION`
(mirroring B2's Slice 2C decision to keep it at `"1.1"`).

Rendering in the thesis markdown is a one-section addition
guarded by `if "cumulative_memory_summary" in compare_report`,
same pattern as the B2 correlation section. Strictly structural
content — no natural-language recap of prior sessions, no
per-row dumps that would invite B4-style interpretation.

## 11. Owner-fixed decisions (proposed for B3 Slice 1)

Parallel to `docs/B1_REPLAN_BOUNDARY.md §12`. Locking these
closes Slice 1's design surface. Full text of each decision lives
in `docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12`.

- **D1** — Dedupe-union, key =
  `(session_id, event_timestamp, event_id)`,
  policy = `drop_equal_raise_mismatch`.
- **D2** — Canonical source = `memory.jsonl` files resolved from
  prior-session refs; raw filesystem paths are a caller-side
  convenience only.
- **D3** — Raw `MemoryRecord` union is sufficient; no new
  wrapper schema.
- **D4** — First-cut runtime path uses the existing
  `run_session(initial_memory=...)` seam; no new kwarg.
- **D5** — `session_id` content fingerprint is already captured
  by `initial_memory_digest`. Source-intent fragments use
  ordered prior `session_id` strings (or ordered content
  digests). Raw filesystem paths are forbidden as digest input.
- **D6** — Bounded growth via `MAX_CUMULATIVE_MEMORY_RECORDS`;
  hard cap.
- **D7** — `PATH_C_WARM`-only mode gating, enforced at the
  caller surface; no `run_session` API change.
- **D8** — A future `run_session` reject-guard for non-
  `PATH_C_WARM` attachment is deferred; not in Slice 2A/2B.
- **D9** — Compare/report visibility is deferred to Slice 2C
  (optional). No `COMPARE_REPORT_SCHEMA_VERSION` bump.
- **D10** (locked Slice 2A.5) — Source resolution is a
  kwarg-only caller-supplied callable:
  `source_resolver: Callable[[str], list[MemoryRecord]]`.
  Required, no default. Loader never touches the filesystem;
  resolver is not a digest ingredient. See §5 above and
  `docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12 D10`.

## 12. Version-bump table for Slice 2A

| Record | Old | New | Nature |
|---|---|---|---|
| `CumulativeMemoryConfig` | — | `1.0` | New (frozen dataclass). |
| `MemoryRecord` | `1.0` | `1.0` | **No bump.** |
| `MemoryQuery` | `1.0` | `1.0` | **No bump.** |
| `MemorySummary` | `1.0` | `1.0` | **No bump.** |
| `SessionEventRecord` | `1.2` | `1.2` | **No bump.** |
| `SessionConfig` | `1.0` | `1.0` | **No bump.** |
| `SessionKPIs` | `1.1` | `1.1` | **No bump.** (No B3 KPI.) |
| `SessionArtifact` | `1.0` | `1.0` | **No bump.** |
| `COMPARE_REPORT_SCHEMA_VERSION` | `1.1` | `1.1` | **No bump.** |

## 13. Open decisions before Slice 2A

Defaults listed; none blocks Slice 1's docs.

- **O1 — Loader reads `memory.jsonl` directly vs via
  `session_manager.load_session`.** Default: **direct
  `memory.jsonl` read**, matching the canonical per-session
  artifact form; `load_session` is a heavier path. Slice 2B
  may revisit.
- **O2 — Where prior session `session_id` is sourced.** Default:
  **from the loaded rows themselves** (every `MemoryRecord` has
  `session_id`); if a caller supplies a dir without a readable
  memory file, the loader raises. Slice 2B may add a stricter
  canonicalization (e.g., require every line in a single file
  to agree on `session_id`).
- **O3 — Location of `MAX_CUMULATIVE_MEMORY_RECORDS`.** Default:
  **inside `src/learning/cumulative_memory.py`**, exported as a
  module constant. Not in `memory_schema.py`.
- **O4 — CLI flag name.** Default: **`--prior-session-dir`,
  repeatable** (mirrors `--correlator-pattern`'s repeatable
  pattern). Slice 2D work, not this doc.
- **O5 — Harness integration.** Default: **only `PATH_C_WARM`
  receives the loader output**; the synthetic warm-seed path
  remains available as an alternative when no prior session is
  supplied. Slice 2D work.
- **O6 — `cumulative_memory_summary` block shape.** Default:
  the sketch in §10. Slice 2C work.

None of these block Slice 1. They are inputs to Slice 2A+.
