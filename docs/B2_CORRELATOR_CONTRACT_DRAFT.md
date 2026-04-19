# B2_CORRELATOR_CONTRACT_DRAFT.md

Status: **B2 Slice 1 draft.** Decisions D1–D5 in §7 are **proposed**
and, once accepted, will be treated as LOCKED in parallel with the
B1 D1–D5 pattern. Runtime logic (the match function and the
integration in `event_loop_c.py`) is deferred to Slice 2+.
Authority: `docs/B2_CORRELATOR_BOUNDARY.md`, `PATH_C_BOUNDARY.md`,
`PATH_C_SCHEMA_REGISTRY.md`.

This document enumerates the minimal schema surface that B2 Slice 1
needs. It is the parallel of `docs/B1_REPLAN_CONTRACT_DRAFT.md` for
the correlator branch. It does NOT propose runtime behavior.

---

## 1. `CorrelationSignal` — candidate contract

The evidence record for a single matched compound pattern. One
correlation event produces exactly one `CorrelationSignal`. If two
distinct patterns match on the same event, two distinct signals are
emitted.

### 1.1 Why this has to exist as a structured value

The correlator must be explainable. Today the only candidates for
"explaining" a compound disruption are either:

- free text in governance / cost / operations NL fields (forbidden
  as authoritative truth — see `docs/B1_REPLAN_BOUNDARY.md §8 R1`),
  or
- a synthetic `EventType` value (forbidden by
  `docs/B2_CORRELATOR_BOUNDARY.md §4.1`).

Neither is admissible. A dedicated structural record is the only
acceptable home for the evidence chain.

### 1.2 Proposed fields

Pydantic model with `ConfigDict(extra="forbid")`, frozen
immutable semantics, no defaults on required fields.

| Field | Type | Notes |
|---|---|---|
| `pattern_id` | `CORRELATOR_PATTERN_ID` Literal | Closed set; see §5. Opening the set is a MINOR bump. |
| `participant_event_ids` | `tuple[str, ...]` | Length ≥ 2. Stream-ordinal order. Strings, frozen tuple so the signal is hashable. |
| `shared_entities` | `tuple[AffectedEntityRef, ...]` | Reused from `src/event_schema.py`. May be an empty tuple if and only if the pattern explicitly declares itself entity-free (see §5 P3). Otherwise ≥ 1. |
| `window_start_ordinal` | `int` | Index (0-based, session-scoped) of the earliest participating event. |
| `window_end_ordinal` | `int` | Index of the latest participating event. Always ≥ `window_start_ordinal`. |
| `window_size` | `int` | Config value in force at detection time. Redundant with `CorrelatorConfig` but pinned to the signal for audit. |
| `matched_conditions` | `tuple[CORRELATOR_MATCHED_CONDITION, ...]` | Closed Literal set (§2). Non-empty. Captures the structured reasons the pattern fired (e.g. `SHARED_ETA_PATH`, `SAME_ENTITY_ID`, `SEVERITY_HIGH_CONCURRENCE`). |
| `schema_version` | `str` | Default `"1.0"`. |

Explicitly NOT on `CorrelationSignal`:

- Free-text "explanation" field.
- Confidence / probability.
- Cost, SLA, or any outcome-domain field.
- Agent output references.

### 1.3 Invariants (tested in Slice 1)

- `len(participant_event_ids) >= 2`.
- `window_end_ordinal >= window_start_ordinal`.
- `(window_end_ordinal - window_start_ordinal + 1) <= window_size`.
- `matched_conditions` is non-empty.
- `pattern_id` is a value of `CORRELATOR_PATTERN_ID`.
- `extra='forbid'` on all models (same convention as
  `SessionEventRecord` / `ReplanAttemptRecord`).

## 2. Closed Literal surfaces

Two closed Literals are introduced in Slice 1. Both live in
`src/correlator/correlator_schema.py` (not in `correlator_patterns.py`,
so the schema module has no runtime-behavior dependency).

```
CORRELATOR_PATTERN_ID = Literal[
    "ETA_PATH_COMPOUND",
    "SUPPLY_DEMAND_MISMATCH",
    "CARRIER_DOUBLE_HIT",
]

CORRELATOR_MATCHED_CONDITION = Literal[
    "SHARED_ETA_PATH",
    "SAME_ENTITY_ID",
    "SAME_CUSTOMER_ZONE",
    "SAME_WAREHOUSE",
    "SEVERITY_HIGH_CONCURRENCE",
    "STREAM_ADJACENT",
]
```

The exact membership of each set is finalized in §5. Any future
additional pattern or matched-condition is a MINOR bump on the
Literal and a same-PR registry update.

## 3. `CorrelationContext` — per-event sideband

The container that lives on `SessionEventRecord`.

| Field | Type | Notes |
|---|---|---|
| `signals` | `tuple[CorrelationSignal, ...]` | Possibly empty. Ordering is pattern-catalog registration order, then stream-ordinal order. |
| `window_size` | `int` | Config value in force at emission time. |
| `window_events_considered` | `int` | Count of finalized records actually inspected (≤ `window_size`). |
| `schema_version` | `str` | Default `"1.0"`. |

Ordering in `signals` is deterministic: iterate pattern catalog in
declaration order; within each pattern, iterate matches in
`window_start_ordinal` ascending order.

An empty `CorrelationContext` (`signals = ()`) is a valid, emitted
value when the correlator runs but finds nothing. This is distinct
from `correlation_context = None` on `SessionEventRecord`, which
means the correlator did not run (`enable_correlator=False`).

## 4. `CorrelatorConfig` — dataclass

`frozen=True` pydantic model or `@dataclass(frozen=True)` — match
the B1 `ReplanConfig` style for consistency.

| Field | Type | Default | Notes |
|---|---|---|---|
| `enable_correlator` | `bool` | `False` | Default OFF to preserve byte identity. |
| `window_size` | `int` | `3` | Must satisfy `1 <= window_size <= MAX_CORRELATOR_WINDOW`. |
| `enabled_patterns` | `frozenset[str]` | all three pattern ids | Members must be in `CORRELATOR_PATTERN_ID`. Subset selection enables a future slice to A/B patterns. |
| `schema_version` | `str` | `"1.0"` | |

Module constants:

```
MAX_CORRELATOR_WINDOW: Final[int] = 6
KNOWN_CORRELATOR_PATTERN_IDS: frozenset[str] = frozenset(...)
```

`__post_init__` validation rejects:

- `window_size < 1` or `> MAX_CORRELATOR_WINDOW`;
- any `enabled_patterns` member not in `KNOWN_CORRELATOR_PATTERN_IDS`;
- any duplicate entry (frozenset handles this, but the validator
  explicitly confirms incoming iterables dedupe cleanly).

## 5. Proposed first-cut pattern catalog (Slice 1)

Three patterns. Each is a pure function over a bounded window of
finalized `SessionEventRecord`s. Each declares its required
structured signals and its closed `matched_conditions` vocabulary.
All three are high-value for thesis-style observability and stay
strictly inside B2 (no cross-session state, no agent contact, no
policy influence).

### P1 — `ETA_PATH_COMPOUND`

- **Intent.** Detect when `CARRIER_DELAY_ESCALATION` and
  `WEATHER_WORSENING` appear together inside the window and jointly
  pressure planned ETA.
- **Why it's high-value.** This is the canonical compound pattern
  in supply-chain twin literature: two independent signals stacking
  on the same latent variable (ETA). If the twin ever ignores this
  compound marker, the thesis report needs to say so.
- **Required structured signals.**
  - at least one `CARRIER_DELAY_ESCALATION` and at least one
    `WEATHER_WORSENING` inside the window;
  - the carrier-delay event's `affected_entities` targets
    `entity_type="carrier"` with `field="transit_time_hours"`;
  - the weather event targets `entity_type="twin"`,
    `entity_id="planned_eta"`.
- **Matched conditions emitted (closed subset).**
  `SHARED_ETA_PATH`, optionally `STREAM_ADJACENT` when the
  participant ordinals differ by exactly 1.
- **`shared_entities`.** Empty tuple is admissible here because
  the shared latent is the twin's ETA, which is not an
  `AffectedEntityRef` on the carrier side. P1 is the only entity-
  free pattern in Slice 1 and must be whitelisted by the schema
  invariant in §1.3.
- **Why it stays inside B2.** Purely a same-session observability
  marker. No agent input, no policy feedback, no cross-session
  state, no replan coupling in Slice 1.

### P2 — `SUPPLY_DEMAND_MISMATCH`

- **Intent.** Detect a `DEMAND_SPIKE` and an
  `INVENTORY_DISCREPANCY` inside the window where the warehouse
  feeding the spike's customer zone is the warehouse whose
  inventory was just corrected.
- **Why it's high-value.** This is the pattern where naive,
  single-event decisions most visibly miscalibrate — each event
  alone looks routine, together they describe a stockout risk
  that the system should at least *record* seeing.
- **Required structured signals.**
  - at least one `DEMAND_SPIKE` with `entity_type="customer_zone"`,
    `field="demand_units"`;
  - at least one `INVENTORY_DISCREPANCY` with
    `entity_type="warehouse"`, `field="current_inventory"`;
  - `shared_entities` is derived from the pattern's own relational
    mapping (zone ↔ warehouse). Slice 1 uses a static topology
    table exposed by the baseline twin (the 2x2x2x2 network); any
    pattern that cannot resolve a concrete
    `(warehouse, customer_zone)` pair produces **no signal**, not
    a guess.
- **Matched conditions emitted.**
  `SAME_WAREHOUSE`, `SAME_CUSTOMER_ZONE`, optionally
  `SEVERITY_HIGH_CONCURRENCE` when both participants have
  `severity >= MEDIUM` (see §6 on severity thresholds).
- **`shared_entities`.** Non-empty: both the warehouse and the
  customer-zone entity refs are included, in pattern-catalog-
  declared order (warehouse first, zone second).
- **Why it stays inside B2.** No cross-session memory, no action
  recommendation, no new adjustment. The signal is observational
  only; a future slice may feed it to the policy gate, and that is
  what keeps it out of B1.

### P3 — `CARRIER_DOUBLE_HIT`

- **Intent.** Detect a `CARRIER_DELAY_ESCALATION` and a
  `COMPLIANCE_HOLD` inside the window where both target the same
  carrier entity.
- **Why it's high-value.** Two qualitatively different shocks on
  the same carrier is the scenario where routing to the peer
  carrier is most clearly calibrated — and where the twin's
  compound-event awareness is most visibly missing if not recorded.
- **Required structured signals.**
  - at least one `CARRIER_DELAY_ESCALATION` with
    `entity_type="carrier"`;
  - at least one `COMPLIANCE_HOLD` with `entity_type="carrier"`;
  - both events' `AffectedEntityRef.entity_id` are equal.
- **Matched conditions emitted.**
  `SAME_ENTITY_ID`, optionally `SEVERITY_HIGH_CONCURRENCE`.
- **`shared_entities`.** Non-empty: a single `AffectedEntityRef`
  naming the common carrier (`entity_type="carrier"`,
  `entity_id=<shared>`, `field=None`).
- **Why it stays inside B2.** Same-session, structural, and
  evidence-chain-complete. It does not drive any action in Slice 1.

### Why not more patterns

A fourth candidate (`CANCELLATION_AFTER_SPIKE` — same zone, demand
spike then customer cancellation) was considered and deferred. It
risks being noise under the current deterministic demo stream
(the demo contains exactly one of each event), and its observability
value is marginal compared to P1–P3. Adding it is a MINOR bump and
can happen later without destabilizing Slice 1.

## 6. Severity threshold for `SEVERITY_HIGH_CONCURRENCE`

Structural rule (no heuristic): the condition is emitted iff all
participating events of the pattern have
`severity in {EventSeverity.MEDIUM, EventSeverity.HIGH}`. The
threshold is a module constant in `correlator_patterns.py` and is
explicitly **not** a free parameter — changing it is a MINOR bump.

## 7. Owner-fixed decisions (proposed for B2 Slice 1)

Parallel to `docs/B1_REPLAN_BOUNDARY.md §12`. Locking these closes
Slice 1's design surface.

- **D1 — Sideband, not `EventType`.** B2 ships the
  `correlation_context` sideband, never a compound `EventType`
  value. Structural enforcement: `src/event_schema.py` is in the
  forbidden-modification list; `CORRELATOR_PATTERN_ID` lives
  inside `src/correlator/`.

- **D2 — Placement A: `SessionEventRecord`.** The correlator
  attaches only via
  `SessionEventRecord.correlation_context: Optional[CorrelationContext] = None`.
  MINOR bump 1.1 → 1.2. No sibling artifact, no new top-level
  `SessionArtifact` field, no new per-session correlator log.

- **D3 — Observability-only, no KPI bump.** Slice 1 changes no
  `SessionKPIs` field. `src/session/kpi_calculator.py` is on the
  forbidden-modification list for Slice 1. A later slice may add
  `compound_event_rate` / `cascade_coverage` if the owner finds
  the runs warrant it.

- **D4 — Ordinal sliding window.**
  `CorrelatorConfig.window_size: int`. Window bounds are
  event-stream ordinals, not wall-clock durations.
  `max_window_size = 6`.

- **D5 — Closed 3-pattern catalog.** Slice 1 ships exactly P1, P2,
  P3 from §5. Enforced by the closed Literal
  `CORRELATOR_PATTERN_ID`.

## 8. Version-bump table for Slice 1

| Record | Old | New | Nature |
|---|---|---|---|
| `SessionEventRecord` | `1.1` | `1.2` | Additive optional `correlation_context: Optional[CorrelationContext] = None`. |
| `CorrelationSignal` | — | `1.0` | New. |
| `CorrelationContext` | — | `1.0` | New. |
| `CorrelatorConfig` | — | `1.0` | New. |
| `SessionKPIs` | `1.1` | `1.1` | **No bump.** Slice 1 adds no KPIs. |
| `SessionArtifact` | `1.0` | `1.0` | **No bump.** |
| `ReplanAttemptRecord` | `1.0` | `1.0` | **No bump.** |
| `MemoryRecord` | `1.0` | `1.0` | **No bump.** |
| `GovernanceTruthRef` | `1.0` | `1.0` | **No bump.** |
| `EffectiveDecisionRef` | `1.0` | `1.0` | **No bump.** |

Safe defaults ensure that, when `enable_correlator=False`:

- `correlation_context` is `None`;
- serialized `SessionEventRecord` bytes match pre-B2 to the
  serialization boundary, except for the `schema_version` string
  change to `"1.2"` — which is the documented, owner-approved
  MINOR-bump contract.

If retaining literal byte identity for `enable_correlator=False`
versus pre-B2 `main` is preferred over recording the schema
version bump, the alternative is to keep `SessionEventRecord` at
`1.1` and nest correlator data inside a `CorrelationContext` that
is itself version-stamped. This alternative is available but not
recommended, because the registry convention in this project is
that *any* additive optional field on a frozen schema MINOR-bumps
that schema. The owner decides — tracked as O1 in §9 below.

## 9. Open decisions before Slice 2 (do not block Slice 1)

- **O1 — SessionEventRecord version handling.** MINOR bump to 1.2
  (preferred, consistent with B1's 1.0 → 1.1 precedent) vs
  stay-at-1.1 with version encoded inside `CorrelationContext`.
  Default: **bump to 1.2**.
- **O2 — Fourth pattern (`CANCELLATION_AFTER_SPIKE`).** Ship in
  Slice 1 or defer. Default: **defer**.
- **O3 — Topology source for P2 zone↔warehouse.** Static baseline
  table in `correlator_patterns.py` (preferred) vs pull from
  `TwinState` at correlator invocation time. Default: **static
  table**, matches deterministic-first rule without coupling to
  runtime state mutation.
- **O4 — Compare-report block shape.** `correlation_summary` as a
  per-pattern `{pattern_id: {fire_count, events: [...]}}` map
  (preferred) vs a flat list of signals. Default: **map**.
- **O5 — Harness flag ergonomics.** `--enable-correlator` only,
  vs `--correlator-window-size N`, vs
  `--correlator-patterns ETA_PATH_COMPOUND,...`. Default:
  **only `--enable-correlator` in Slice 1**, with window and
  pattern selection staying at compile defaults until real runs
  demand otherwise.

None of these block Slice 1. They are inputs to either the
Slice 1 implementation PR or a Slice 2 follow-up.
