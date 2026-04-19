# B5_BUNDLE_CONTRACT.md

Status: **B5 Phase-1 Slice 1 — bundle contract freeze.**
Authority: `B5_Fullstack_Surface_Strategy_and_Roadmap_v1_1.docx`,
`PATH_C_BOUNDARY.md §9`,
`PATH_C_SCHEMA_REGISTRY.md`.

Read-only contract consumed by the B5 backend / future frontend.
Does not introduce any write-path API. Does not change the runtime
artifact-producing files (`src/event_loop_c.py`,
`scripts/session_eval_harness.py`, `src/session/*`).

---

## 1. Bundle layout

A *bundle* is the minimum read-only unit the B5 surface consumes.
One bundle corresponds to exactly one eval run (one harness
invocation, or one fixture synthesis).

```
bundles/{bundle_id}/
  metadata.json
  sessions/{tag}/session_artifact.json
  sessions/{tag}/memory.jsonl      # optional, may be absent
  compare_report.json              # optional, may be absent
  thesis_report.md                 # optional, may be absent
```

- `{bundle_id}` is a caller-supplied stable string identifier.
- `{tag}` is the variant tag string as used by
  `scripts/session_eval_harness.py` (`baseline_static`,
  `path_c_cold`, `path_c_warm`, `path_c_warm_policy_only`,
  `path_c_warm_agent_visible_memory`). The bundle does not
  re-interpret those strings; it just preserves them.
- A session entry with no rows produces an empty `memory.jsonl`
  file or no file at all; both forms are valid and MUST be
  tolerated by the consumer.

## 2. Supported variant sets

The contract supports two canonical variant sets and MUST NOT
assume either is present.

- **Default 3-mode trio:**
  `baseline_static`, `path_c_cold`, `path_c_warm`.
- **B4 experiment triplet:**
  `baseline_static`, `path_c_warm_policy_only`,
  `path_c_warm_agent_visible_memory`.
  Note: `path_c_cold` is DELIBERATELY absent from this set.
  Any consumer that reads a bundle MUST handle the missing
  `path_c_cold` session cleanly.

Other variant sets (subsets, single-mode runs, future
experiment triplets) are permitted — the contract pins the file
layout, not the variant membership.

## 3. `metadata.json`

Canonical JSON, sorted keys, UTF-8. Top-level fields:

```
{
  "bundle_schema_version": "1.0",
  "bundle_id": "<string>",
  "variant_set": "default_3_mode" | "b4_experiment_triplet"
                 | "custom",
  "variant_tags": [ "<tag>", ... ],             // ordered, non-empty
  "session_ids": { "<tag>": "<session_id>" },   // keys subset of variant_tags
  "has_compare_report": bool,
  "has_thesis_report": bool,
  "source": {
    "kind": "harness_repackage" | "fixture_builder" | "unknown",
    "origin": "<free-form identifier>",         // harness out_dir name, fixture id, etc.
    "notes": "<free-form, may be empty>"
  },
  "produced_by": "<semver string of the bundler>",
  "warnings": [ "<string>", ... ]               // null-safe issues: missing memory.jsonl, etc.
}
```

Rules:

- `variant_set` is a hint, not a gate. A consumer MUST derive
  everything it needs from `variant_tags` + the on-disk session
  directories. If the caller cannot classify the set, `"custom"`
  is the safe value.
- `session_ids` may be partial — if a session directory fails to
  load its `session_artifact.json`, the corresponding entry is
  omitted and a warning is appended.
- `has_compare_report` / `has_thesis_report` are independently
  optional. Bundlers MUST NOT synthesize fake compare or thesis
  reports when the source lacks them.
- `warnings` is always present, possibly empty.

## 4. Null-safety invariants

The bundler and every read-only consumer MUST tolerate, without
raising:

1. A bundle with zero `memory.jsonl` files.
2. A bundle with a `memory.jsonl` present for some sessions but
   not others.
3. A bundle without `compare_report.json`.
4. A bundle without `thesis_report.md`.
5. A B4 triplet bundle that has no `path_c_cold` session.
6. A session directory whose `session_artifact.json` is missing
   or malformed — the session is excluded from
   `session_ids` and a warning is emitted; the overall bundle is
   still loadable.

## 5. Boundary rules

- The bundler is a repackager. It MUST NOT mutate the contents of
  `session_artifact.json`, `memory.jsonl`, `compare_report.json`,
  or `thesis_report.md`. Bytes are copied verbatim.
- The bundler MUST NOT invoke harness / runtime / session code
  paths. It reads JSON defensively.
- No write-path API: neither the bundler nor the backend exposes
  a way to modify an existing bundle in place. Re-running the
  bundler produces a fresh `metadata.json`; the session
  artifacts and compare/thesis reports are overwritten only when
  the caller explicitly points at the same destination.
- No backfill of missing compare semantics. If the source has
  no `compare_report.json`, the bundle has none. B5 backend
  models reflect that absence explicitly (`Optional[...]`).

## 6. Versioning

`bundle_schema_version` uses the same `MAJOR.MINOR` convention
as `PATH_C_SCHEMA_REGISTRY.md` §4. Initial version: `"1.0"`.

A MINOR bump adds a new optional `metadata.json` field with a
safe default. A MAJOR bump is any breaking shape change and
MUST be paired with a backend models update and a fixture
refresh in the same PR.

## 7. Cross-references

- `tools/bundler/` — authoritative bundler implementation.
- `backend/models/bundle_models.py` — read-only Pydantic
  response shapes over the contract.
- `backend/repository/bundle_repository.py` — null-safe
  normalization layer.
- `bundles/` — fixture bundle outputs (default + B4 triplet).
