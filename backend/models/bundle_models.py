"""B5 backend response models (read-only, GET-only).

These models describe the *backend response shapes*. They are NOT
a re-implementation of ``src/session/session_schema.py``. The
runtime session schema is intentionally not imported:

- the backend is a consumer of already-serialized JSON, not a
  re-validator of session runtime state,
- runtime schema MINOR bumps should not force a backend model
  bump,
- this keeps B5 structurally independent of Path C runtime
  files.

Any consumer wanting the full ``SessionArtifact`` can read the
raw `session_artifact.json` under `sessions/{tag}/` directly;
the backend surfaces only the shallow summary shape here.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


VariantSet = Literal["default_3_mode", "b4_experiment_triplet", "custom"]


# The single bundle-contract version this backend speaks. Tied 1:1
# to ``docs/B5_BUNDLE_CONTRACT.md §6``. Callers MUST treat any
# bundle whose on-disk ``metadata.bundle_schema_version`` differs
# from this as a contract mismatch (the repository surfaces that
# as a per-entry value on ``BundleIndexEntry.bundle_schema_version``).
SUPPORTED_BUNDLE_SCHEMA_VERSION: str = "1.0"


class BundleSourceRef(BaseModel):
    """Non-authoritative provenance for a bundle.

    `kind` is a hint, not a gate — consumers MUST NOT condition
    behavior on it. It is surfaced purely for display / debugging.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str
    origin: str
    notes: str = ""


class BundleMetadata(BaseModel):
    """Shallow metadata.json contents.

    Exactly the shape written by ``tools/bundler/bundler.build_metadata``.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_schema_version: str
    bundle_id: str
    variant_set: VariantSet
    variant_tags: list[str]
    session_ids: dict[str, str] = Field(default_factory=dict)
    has_compare_report: bool = False
    has_thesis_report: bool = False
    source: BundleSourceRef
    produced_by: str
    warnings: list[str] = Field(default_factory=list)


class SessionSummary(BaseModel):
    """Compact per-session summary surfaced in a bundle-detail response.

    Derived defensively from ``session_artifact.json``. Every
    numeric field is Optional because fixture bundles and pre-1.1
    artifacts may not carry every key. No field is *required* in
    the backend response — if the on-disk artifact is missing it,
    the backend returns ``None`` rather than a synthesized value.
    """

    model_config = ConfigDict(extra="forbid")

    variant_tag: str
    session_id: Optional[str] = None
    mode: Optional[str] = None
    events_observed: Optional[int] = None
    events_with_outcome: Optional[int] = None
    total_cost: Optional[float] = None
    avg_cost: Optional[float] = None
    sla_preservation_rate: Optional[float] = None
    auto_execute_success_rate: Optional[float] = None
    memory_jsonl_present: bool = False
    session_artifact_loadable: bool = True
    warnings: list[str] = Field(default_factory=list)


class BundleIndexEntry(BaseModel):
    """One row in the list of available bundles.

    ``bundle_schema_version`` is the contract version reported by
    the bundle's own ``metadata.json``. Different bundles can (in
    principle) advertise different versions; the top-level
    ``BundleIndexResponse.bundle_schema_version`` is NOT derived
    from these — it is the backend's single supported contract
    version. Callers compare the two to detect mismatches.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    variant_set: VariantSet
    variant_tags: list[str]
    has_compare_report: bool
    has_thesis_report: bool
    warning_count: int = 0
    bundle_schema_version: str


class BundleIndexResponse(BaseModel):
    """GET /bundles — index of known bundles.

    ``bundle_schema_version`` here names the **backend-supported**
    bundle-contract version (``SUPPORTED_BUNDLE_SCHEMA_VERSION``),
    not "the last bundle scanned". The value is constant for a
    given backend build. Per-bundle versions live on each
    ``BundleIndexEntry`` so downstream consumers can detect
    per-bundle drift.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_schema_version: str
    bundles: list[BundleIndexEntry]


class BundleDetailResponse(BaseModel):
    """GET /bundles/{bundle_id} — detail view over a single bundle.

    `compare_report_raw` and `thesis_report_raw_markdown` carry the
    source artifacts verbatim when present. The backend does NOT
    re-compute deltas, re-interpret diverged events, or otherwise
    touch compare semantics.
    """

    model_config = ConfigDict(extra="forbid")

    metadata: BundleMetadata
    sessions: list[SessionSummary]
    compare_report_raw: Optional[dict[str, Any]] = None
    thesis_report_raw_markdown: Optional[str] = None
    # Surfaces inconsistencies observed at load time that the
    # static ``metadata.warnings`` list cannot carry — e.g. the
    # metadata claims ``has_compare_report=True`` but the file
    # turned out to be unreadable at request time. Always
    # present, usually empty.
    load_warnings: list[str] = Field(default_factory=list)


class SessionArtifactResponse(BaseModel):
    """Raw contents of one session's ``session_artifact.json``.

    Phase 3A Session Runtime needs the event stream, which lives
    inside each session's artifact. Rather than widen the
    existing ``BundleDetailResponse`` (and pay for the full
    per-event payload on every catalog listing), this response
    returns one session artifact as an opaque dictionary under
    ``session_artifact_raw``.

    The backend does NOT reinterpret the event records here — it
    simply surfaces the already-serialized bytes. Frontend
    consumers read structural fields (``event_records``,
    ``baseline_event_result``, overlay fields) as-is. Any
    semantic interpretation remains forbidden at this layer.

    ``session_artifact_raw`` is ``None`` when the session's
    artifact is missing or not readable canonical JSON; a
    warning is appended to ``load_warnings`` in that case.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    variant_tag: str
    session_artifact_loadable: bool
    memory_jsonl_present: bool
    session_artifact_raw: Optional[dict[str, Any]] = None
    load_warnings: list[str] = Field(default_factory=list)
