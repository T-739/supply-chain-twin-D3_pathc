"""learning/cumulative_memory.py — Path C B3 cumulative-memory
contract module + runtime loader.

Slice 2A landed the contract surface (``CumulativeMemoryConfig``,
closed dedupe-policy Literal, ``MAX_CUMULATIVE_MEMORY_RECORDS``,
``CumulativeMemoryCollisionError``, the kwarg-only
``source_resolver`` contract). **Slice 2B (this file now) lands
the ``load_cumulative_memory`` runtime body** — dedupe-union,
cap enforcement, and fresh-``EpisodicMemory`` assembly — while
keeping the loader pure and deterministic.

Owner-fixed decisions (see
``docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12`` and
``docs/B3_CUMULATIVE_MEMORY_CONTRACT_DRAFT.md §11``):

  D1 : Dedupe-union, keyed by
       ``(session_id, event_timestamp, event_id)``; policy
       ``drop_equal_raise_mismatch`` — same triple + equal row
       silently drop; same triple + non-equal row raises
       ``CumulativeMemoryCollisionError``.

  D2 : Canonical prior-memory source is per-session
       ``memory.jsonl``. **The loader does NOT touch the
       filesystem itself.** It receives a caller-supplied
       ``source_resolver`` callable (kwarg-only, required) that
       maps each canonical prior ``session_id`` ref to a list of
       validated ``MemoryRecord`` instances. The Slice 2D CLI
       and the Slice 2B.5 test helpers each supply their own
       concrete resolver — the CLI layer resolves paths to
       rows; tests resolve in-memory fixtures to rows. **Raw
       filesystem paths never enter this module, the
       ``CumulativeMemoryConfig``, or any digest fragment.**

  D3 : Raw ``MemoryRecord`` union is sufficient. No wrapper
       class. ``MemoryRecord.session_id`` already carries
       per-row provenance.

  D4 : First-cut runtime path reuses the existing
       ``run_session(initial_memory=...)`` seam. The loader
       returns an ``EpisodicMemory``; no new ``run_session``
       kwarg in Slice 2A/2B.

  D5 : ``session_id`` content fingerprint is already captured by
       the pre-existing ``initial_memory_digest``. Any source-
       intent fragment added to ``config_for_digest`` in a later
       slice encodes ordered prior ``session_id`` strings or
       ordered content digests — never filesystem paths.

  D6 : Hard cap via ``MAX_CUMULATIVE_MEMORY_RECORDS``.

  D7 : ``PATH_C_WARM``-only attachment is a caller-side
       workflow rule, NOT a core API change. This module does
       not know about ``SessionMode``.

This module does NOT:
  - import ``src/agents/*``, ``src/adaptive/*``, ``src/replan/*``,
    ``src/correlator/*``, ``src/llm_backend``, ``src/llm_providers``
  - import ``evaluation`` or ``action_code_mapper``
  - read or write ``data/cases/*.json``
  - call ``datetime.now`` / ``utcnow`` / ``time.time`` /
    ``uuid.uuid4``
  - construct prompt-like strings or reference any natural-
    language governance field name (``cost_summary``,
    ``confidence_note``, ``rationale_trace``,
    ``situational_explanation``, ``alternative_actions``)
  - mutate any existing ``EpisodicMemory`` instance (the Slice 2B
    loader will always return a fresh one)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Final, Literal

from learning.episodic_memory import EpisodicMemory
from learning.memory_schema import MemoryRecord


# ---------------------------------------------------------------------------
# Source-resolution type alias (D10, Slice 2A.5)
# ---------------------------------------------------------------------------

#: Callable that resolves one canonical prior-session reference
#: (the string carried in ``CumulativeMemoryConfig.prior_session_refs``)
#: to the list of ``MemoryRecord`` instances that reference
#: identifies. Each implementation (CLI, test, harness) plugs in
#: its own resolver — the loader never touches the filesystem
#: itself. See ``docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12 D10``
#: and ``docs/B3_CUMULATIVE_MEMORY_CONTRACT_DRAFT.md §5``.
#:
#: The resolver is a **pure function**:
#:   - same input ref → same output rows, byte-for-byte;
#:   - no wall-clock input;
#:   - no hidden global state read that can drift between calls.
#:
#: The loader iterates ``config.prior_session_refs`` in order and
#: calls the resolver once per ref. Any exception the resolver
#: raises propagates to the loader caller unchanged.
CumulativeMemorySourceResolver = Callable[[str], list[MemoryRecord]]


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

CUMULATIVE_MEMORY_SCHEMA_VERSION: str = "1.0"


# ---------------------------------------------------------------------------
# Module-level constants (closed)
# ---------------------------------------------------------------------------

#: Hard cap on the post-dedupe record count returned by
#: ``load_cumulative_memory``. The loader raises when the cap is
#: exceeded — no soft truncate. Raising this is a documented MINOR
#: bump; see ``docs/B3_CUMULATIVE_MEMORY_BOUNDARY.md §12 D6``.
MAX_CUMULATIVE_MEMORY_RECORDS: Final[int] = 1000


# ---------------------------------------------------------------------------
# Closed Literal (D1)
# ---------------------------------------------------------------------------

#: Closed dedupe-policy set. Slice 2A admits exactly one policy.
#: Opening this set is a MINOR bump on the Literal + a same-PR
#: registry update.
CUMULATIVE_MEMORY_DEDUPE_POLICY = Literal[
    "drop_equal_raise_mismatch",
]


#: Registry of known dedupe-policy string values. Kept as a
#: ``frozenset`` for ``__post_init__`` membership testing alongside
#: the Literal's static-type check.
KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES: frozenset[str] = frozenset({
    "drop_equal_raise_mismatch",
})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CumulativeMemoryCollisionError(ValueError):
    """Raised when the dedupe rule detects a same-triple,
    non-equal row collision across prior-session sources.

    The triple is ``(session_id, event_timestamp, event_id)`` —
    the same primary key as ``session.digests.memory_record_id``.
    Same triple + equal row content is a silent drop (caller
    legitimately passed the same prior session twice); same
    triple + non-equal content is a hard error because it means
    two sources disagree on what happened at that point and the
    adaptive gate would see silently contradictory history.
    """


# ---------------------------------------------------------------------------
# CumulativeMemoryConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CumulativeMemoryConfig:
    """Configuration for cross-session cumulative memory loading.

    Frozen dataclass — mirrors the ``ReplanConfig`` /
    ``CorrelatorConfig`` precedent. No pydantic because the
    downstream consumer (the Slice 2B loader) is a pure function,
    not a schema boundary serialized to disk.

    Fields
    ------
    prior_session_refs
        Ordered tuple of prior-session references. Each entry is a
        canonical prior-session ``session_id`` string or an
        equivalent content-addressed reference the loader can
        resolve to exactly one ``memory.jsonl`` record set. **Not
        filesystem paths.** The CLI / harness layer (Slice 2D)
        resolves user-supplied directories into these refs before
        constructing the config.

        An empty tuple is legal — the Slice 2B loader will return
        an empty ``EpisodicMemory``.
    dedupe_policy
        Closed Literal. Slice 2A admits exactly
        ``"drop_equal_raise_mismatch"``.
    max_records
        Per-config cap on the post-dedupe record count. Must be in
        ``[1, MAX_CUMULATIVE_MEMORY_RECORDS]``. The Slice 2B
        loader raises ``CumulativeMemoryCollisionError`` (or a
        sibling subclass) when this cap is exceeded.
    schema_version
        Version pin for the config record. Stays at
        ``CUMULATIVE_MEMORY_SCHEMA_VERSION`` (1.0).
    """

    prior_session_refs: tuple[str, ...] = field(default_factory=tuple)
    dedupe_policy: str = "drop_equal_raise_mismatch"
    max_records: int = MAX_CUMULATIVE_MEMORY_RECORDS
    schema_version: str = CUMULATIVE_MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        # --- prior_session_refs: normalize + validate ---
        refs = self.prior_session_refs
        if isinstance(refs, tuple):
            normalized: tuple[str, ...] = refs
        else:
            # Accept list / other iterable of strings; normalize to
            # tuple for frozen-dataclass immutability.
            try:
                normalized = tuple(refs)
            except TypeError as exc:
                raise TypeError(
                    "prior_session_refs must be a tuple or iterable "
                    f"of strings, got {type(refs).__name__}"
                ) from exc
            object.__setattr__(self, "prior_session_refs", normalized)
        for ref in normalized:
            if not isinstance(ref, str):
                raise TypeError(
                    "every prior_session_refs entry must be a string, "
                    f"got {type(ref).__name__}: {ref!r}"
                )
            if not ref.strip():
                raise ValueError(
                    "prior_session_refs entries must be non-empty "
                    "strings (whitespace is not a valid reference)"
                )

        # --- dedupe_policy: closed membership ---
        if self.dedupe_policy not in KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES:
            raise ValueError(
                f"dedupe_policy must be one of "
                f"{sorted(KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES)!r}, "
                f"got {self.dedupe_policy!r}"
            )

        # --- max_records: range ---
        if not isinstance(self.max_records, int) or isinstance(
            self.max_records, bool
        ):
            raise TypeError(
                "max_records must be int, got "
                f"{type(self.max_records).__name__}"
            )
        if self.max_records < 1:
            raise ValueError(
                f"max_records must be >= 1, got {self.max_records}"
            )
        if self.max_records > MAX_CUMULATIVE_MEMORY_RECORDS:
            raise ValueError(
                f"max_records={self.max_records} exceeds hard cap "
                f"MAX_CUMULATIVE_MEMORY_RECORDS="
                f"{MAX_CUMULATIVE_MEMORY_RECORDS}"
            )

        # --- schema_version: pin ---
        if self.schema_version != CUMULATIVE_MEMORY_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be "
                f"{CUMULATIVE_MEMORY_SCHEMA_VERSION!r}, "
                f"got {self.schema_version!r}"
            )


# ---------------------------------------------------------------------------
# Loader entrypoint — signature only in Slice 2A
# ---------------------------------------------------------------------------


def load_cumulative_memory(
    config: CumulativeMemoryConfig,
    *,
    source_resolver: CumulativeMemorySourceResolver,
) -> EpisodicMemory:
    """Load cross-session cumulative memory into a fresh
    ``EpisodicMemory``.

    Body (Slice 2B):

      1. For each ref in ``config.prior_session_refs`` (in order),
         call ``source_resolver(ref)`` to obtain a list of
         validated ``MemoryRecord`` instances. The loader itself
         does NOT read any filesystem, parse any JSONL, or touch
         ``data/cases/*``.
      2. Dedupe-union all returned rows by
         ``(session_id, event_timestamp, event_id)`` under the
         ``drop_equal_raise_mismatch`` policy — equal duplicates
         silently drop, non-equal duplicates raise
         ``CumulativeMemoryCollisionError``.
      3. Enforce ``len(rows) <= config.max_records`` and
         ``<= MAX_CUMULATIVE_MEMORY_RECORDS`` — raise above
         either cap (no soft truncate).
      4. Return a fresh ``EpisodicMemory`` constructed from the
         deduped rows. The caller (test / CLI / harness) then
         passes this via the existing
         ``run_session(initial_memory=...)`` seam for
         ``PATH_C_WARM`` runs only (D7).

    Source-resolution contract (D2 / D10, Slice 2A.5):

      - ``source_resolver`` is **kwarg-only** and **required**.
        No default is provided so accidental callers cannot
        silently feed the loader an implicit global-path lookup.
      - ``source_resolver`` is a **pure function** of its input
        ref. Concrete resolvers live *outside* this module:
          * the Slice 2D CLI helper resolves user-supplied dirs
            into refs and provides a resolver that reads the
            corresponding ``memory.jsonl`` from disk;
          * Slice 2B / 2B.5 tests supply an in-memory resolver
            that maps refs to fixture rows directly.
      - ``config.prior_session_refs`` is the **only** digest
        ingredient. The resolver itself is not part of any
        session_id digest fragment — two callers that supply
        different resolvers for equivalent row content produce
        byte-identical ``EpisodicMemory.snapshot()`` output and
        therefore identical ``initial_memory_digest``.
      - Filesystem paths, file handles, or any other non-
        content-addressed identifier are **never** passed into
        this function. The resolver may internally consult
        paths; the loader does not.

    Purity contract (to be enforced in Slice 2B tests):

      - No ``datetime.now`` / ``time.time`` / ``uuid4``.
      - No read of ``data/cases/*``.
      - No mutation of any existing ``EpisodicMemory``.
      - No agent-prompt construction.
      - Deterministic output across fresh subprocesses with varied
        ``PYTHONHASHSEED``, given a deterministic ``source_resolver``.

    Parameters
    ----------
    config
        A validated ``CumulativeMemoryConfig``. Empty
        ``prior_session_refs`` is legal and will produce an empty
        ``EpisodicMemory`` in Slice 2B (``source_resolver`` is
        never called in that case, but is still required to be
        supplied so the contract stays explicit).
    source_resolver
        Kwarg-only, required. Called once per ref in
        ``config.prior_session_refs``, in order. Must return a
        ``list[MemoryRecord]``.

    Returns
    -------
    EpisodicMemory
        A fresh ``EpisodicMemory`` with the deduped row set.

    Raises
    ------
    TypeError
        When the resolver returns something other than a ``list``,
        or when a returned entry is not a ``MemoryRecord`` instance.
    CumulativeMemoryCollisionError
        When the dedupe rule detects a same-triple non-equal
        collision across sources.
    ValueError
        When the post-dedupe row count exceeds
        ``config.max_records`` or ``MAX_CUMULATIVE_MEMORY_RECORDS``.
    """
    # Iterate refs in declared order; first occurrence of a given
    # triple wins on equal duplicates. Dict insertion order is the
    # resolver-call order (Python 3.7+). EpisodicMemory canonical
    # ordering re-sorts by (event_timestamp, event_id) on read.
    #
    # Alias-safety hardening (Slice 2B.5): every kept row is stored
    # as a fresh ``MemoryRecord.model_copy()``. The returned
    # ``EpisodicMemory`` therefore does not share object identity
    # with resolver-returned rows. This defensively decouples the
    # loader's output from any post-load mutation of the caller's
    # own ``MemoryRecord`` instances — ``MemoryRecord`` has
    # ``frozen=False`` in its pydantic config, so direct attribute
    # assignment on a caller's row is technically possible, and we
    # do not want that to leak into a previously-loaded memory.
    seen: dict[tuple[str, str, str], MemoryRecord] = {}
    for ref in config.prior_session_refs:
        rows = source_resolver(ref)
        if not isinstance(rows, list):
            raise TypeError(
                f"source_resolver({ref!r}) must return a list of "
                f"MemoryRecord, got {type(rows).__name__}"
            )
        for row in rows:
            if not isinstance(row, MemoryRecord):
                raise TypeError(
                    f"source_resolver({ref!r}) returned a non-MemoryRecord "
                    f"entry of type {type(row).__name__}"
                )
            key = (row.session_id, row.event_timestamp, row.event_id)
            existing = seen.get(key)
            if existing is None:
                # Defensive copy: isolate the loader's output from
                # any subsequent mutation of the caller's original
                # row object.
                seen[key] = row.model_copy()
                continue
            # Same triple already present. D1 policy:
            # drop if equal, raise if mismatched.
            if existing.model_dump() == row.model_dump():
                # silently drop the equal duplicate
                continue
            raise CumulativeMemoryCollisionError(
                f"same-triple non-equal row collision on "
                f"(session_id={key[0]!r}, event_timestamp={key[1]!r}, "
                f"event_id={key[2]!r}) across prior-session sources"
            )

    # Bounded-growth enforcement (D6). Check both the hard module
    # cap and the per-config cap; raise on the stricter one when
    # both are breached. No soft truncate.
    count = len(seen)
    if count > MAX_CUMULATIVE_MEMORY_RECORDS:
        raise ValueError(
            f"post-dedupe cumulative memory size {count} exceeds "
            f"hard cap MAX_CUMULATIVE_MEMORY_RECORDS="
            f"{MAX_CUMULATIVE_MEMORY_RECORDS}"
        )
    if count > config.max_records:
        raise ValueError(
            f"post-dedupe cumulative memory size {count} exceeds "
            f"config.max_records={config.max_records}"
        )

    return EpisodicMemory(records=list(seen.values()))


__all__ = [
    "CUMULATIVE_MEMORY_DEDUPE_POLICY",
    "CUMULATIVE_MEMORY_SCHEMA_VERSION",
    "CumulativeMemoryCollisionError",
    "CumulativeMemoryConfig",
    "CumulativeMemorySourceResolver",
    "KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES",
    "MAX_CUMULATIVE_MEMORY_RECORDS",
    "load_cumulative_memory",
]
