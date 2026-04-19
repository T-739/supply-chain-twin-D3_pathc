"""Read-only artifact repository over a ``bundles/`` root.

Consumes the on-disk layout defined in
``docs/B5_BUNDLE_CONTRACT.md`` and normalizes it into the
response models under ``backend.models``.

Rules:
  - never writes
  - never mutates input bytes
  - defensive JSON reading; malformed artifacts surface as
    warnings rather than exceptions (except for `metadata.json`,
    which is load-bearing — a malformed metadata.json raises
    ``MalformedBundleError``)
  - missing optional artifacts (memory.jsonl, compare_report.json,
    thesis_report.md) produce Optional/None fields, not errors
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable, Optional

from backend.models.bundle_models import (
    SUPPORTED_BUNDLE_SCHEMA_VERSION,
    BundleDetailResponse,
    BundleIndexEntry,
    BundleIndexResponse,
    BundleMetadata,
    SessionArtifactResponse,
    SessionSummary,
)


METADATA_FILENAME = "metadata.json"
COMPARE_FILENAME = "compare_report.json"
THESIS_FILENAME = "thesis_report.md"
SESSION_ARTIFACT_FILENAME = "session_artifact.json"
MEMORY_FILENAME = "memory.jsonl"


class BundleNotFoundError(Exception):
    """Requested bundle_id does not exist under the configured root."""


class MalformedBundleError(Exception):
    """Bundle exists but its metadata.json is unreadable or shape-invalid."""


class BundleRepository:
    """Read-only facade over a ``bundles/`` root directory."""

    def __init__(self, bundles_root: str | os.PathLike) -> None:
        self._root = os.fspath(bundles_root)

    # ----- root discovery -----

    @property
    def root(self) -> str:
        return self._root

    def list_bundle_ids(self) -> list[str]:
        """Return sorted bundle_ids discovered under the root."""
        if not os.path.isdir(self._root):
            return []
        out: list[str] = []
        for entry in sorted(os.listdir(self._root)):
            full = os.path.join(self._root, entry)
            if not os.path.isdir(full):
                continue
            if os.path.isfile(os.path.join(full, METADATA_FILENAME)):
                out.append(entry)
        return out

    # ----- index -----

    def build_index(self) -> BundleIndexResponse:
        """Return the index of all known bundles.

        Bundles whose metadata.json is malformed are skipped
        silently in the index (they remain addressable via
        :meth:`load_detail`, which will raise
        :class:`MalformedBundleError`). This keeps the index
        endpoint null-safe — one broken bundle does not break
        the whole listing.
        """
        entries: list[BundleIndexEntry] = []
        for bid in self.list_bundle_ids():
            try:
                meta = self._load_metadata(bid)
            except MalformedBundleError:
                continue
            entries.append(BundleIndexEntry(
                bundle_id=meta.bundle_id,
                variant_set=meta.variant_set,
                variant_tags=list(meta.variant_tags),
                has_compare_report=meta.has_compare_report,
                has_thesis_report=meta.has_thesis_report,
                warning_count=len(meta.warnings),
                bundle_schema_version=meta.bundle_schema_version,
            ))
        # The top-level ``bundle_schema_version`` on the response is
        # the backend's single supported contract version — it is
        # NOT derived from whichever bundle happened to be scanned
        # last. Per-bundle versions are carried on each entry so
        # drift is observable to the caller.
        return BundleIndexResponse(
            bundle_schema_version=SUPPORTED_BUNDLE_SCHEMA_VERSION,
            bundles=entries,
        )

    # ----- detail -----

    def load_detail(self, bundle_id: str) -> BundleDetailResponse:
        meta = self._load_metadata(bundle_id)
        bundle_dir = os.path.join(self._root, bundle_id)

        sessions: list[SessionSummary] = []
        for tag in meta.variant_tags:
            sessions.append(
                self._summarize_session(bundle_dir=bundle_dir, tag=tag)
            )

        load_warnings: list[str] = []

        compare: Optional[dict[str, Any]] = None
        if meta.has_compare_report:
            compare_path = os.path.join(bundle_dir, COMPARE_FILENAME)
            compare = self._read_json_safe(compare_path)
            if compare is None:
                load_warnings.append(
                    "metadata.has_compare_report=True but "
                    f"{COMPARE_FILENAME} is missing or unreadable at "
                    "load time"
                )

        thesis_md: Optional[str] = None
        if meta.has_thesis_report:
            thesis_path = os.path.join(bundle_dir, THESIS_FILENAME)
            thesis_md = self._read_text_safe(thesis_path)
            if thesis_md is None:
                load_warnings.append(
                    "metadata.has_thesis_report=True but "
                    f"{THESIS_FILENAME} is missing or unreadable at "
                    "load time"
                )

        return BundleDetailResponse(
            metadata=meta,
            sessions=sessions,
            compare_report_raw=compare,
            thesis_report_raw_markdown=thesis_md,
            load_warnings=load_warnings,
        )

    # ----- session artifact (raw) -----

    def load_session_artifact(
        self, bundle_id: str, variant_tag: str,
    ) -> SessionArtifactResponse:
        """Return one session's ``session_artifact.json`` verbatim.

        Phase 3A Session Runtime data source. The returned
        ``session_artifact_raw`` is the exact dict parsed from
        disk — the backend does not reinterpret event records or
        overlay fields here.

        Raises :class:`BundleNotFoundError` when either the
        bundle or the named variant tag is not present. A
        present-but-unreadable session artifact yields
        ``session_artifact_loadable=False`` and a load warning
        rather than an exception, matching the null-safety rule
        in :meth:`load_detail`.
        """
        meta = self._load_metadata(bundle_id)
        if variant_tag not in meta.variant_tags:
            raise BundleNotFoundError(
                f"variant tag {variant_tag!r} not present in bundle "
                f"{bundle_id!r} (known tags: {list(meta.variant_tags)})"
            )

        bundle_dir = os.path.join(self._root, bundle_id)
        session_dir = os.path.join(bundle_dir, "sessions", variant_tag)
        artifact_path = os.path.join(session_dir, SESSION_ARTIFACT_FILENAME)
        memory_path = os.path.join(session_dir, MEMORY_FILENAME)
        memory_present = os.path.isfile(memory_path)

        load_warnings: list[str] = []

        if not os.path.isfile(artifact_path):
            load_warnings.append(
                f"{SESSION_ARTIFACT_FILENAME} is missing for variant "
                f"{variant_tag!r}"
            )
            return SessionArtifactResponse(
                bundle_id=bundle_id,
                variant_tag=variant_tag,
                session_artifact_loadable=False,
                memory_jsonl_present=memory_present,
                session_artifact_raw=None,
                load_warnings=load_warnings,
            )

        raw = self._read_json_safe(artifact_path)
        if raw is None:
            load_warnings.append(
                f"{SESSION_ARTIFACT_FILENAME} is unreadable or not "
                f"canonical JSON for variant {variant_tag!r}"
            )
            return SessionArtifactResponse(
                bundle_id=bundle_id,
                variant_tag=variant_tag,
                session_artifact_loadable=False,
                memory_jsonl_present=memory_present,
                session_artifact_raw=None,
                load_warnings=load_warnings,
            )

        return SessionArtifactResponse(
            bundle_id=bundle_id,
            variant_tag=variant_tag,
            session_artifact_loadable=True,
            memory_jsonl_present=memory_present,
            session_artifact_raw=raw,
            load_warnings=load_warnings,
        )

    # ----- helpers -----

    def _load_metadata(self, bundle_id: str) -> BundleMetadata:
        bundle_dir = os.path.join(self._root, bundle_id)
        path = os.path.join(bundle_dir, METADATA_FILENAME)
        if not os.path.isfile(path):
            raise BundleNotFoundError(
                f"bundle {bundle_id!r} not found under {self._root!r}"
            )
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise MalformedBundleError(
                f"metadata.json unreadable for bundle {bundle_id!r}: {exc}"
            ) from exc
        try:
            return BundleMetadata.model_validate(raw)
        except Exception as exc:
            raise MalformedBundleError(
                f"metadata.json shape invalid for bundle {bundle_id!r}: {exc}"
            ) from exc

    def _summarize_session(self, *, bundle_dir: str, tag: str) -> SessionSummary:
        session_dir = os.path.join(bundle_dir, "sessions", tag)
        artifact_path = os.path.join(session_dir, SESSION_ARTIFACT_FILENAME)
        memory_path = os.path.join(session_dir, MEMORY_FILENAME)
        memory_present = os.path.isfile(memory_path)

        warnings: list[str] = []
        if not os.path.isfile(artifact_path):
            warnings.append("session_artifact.json is missing")
            return SessionSummary(
                variant_tag=tag,
                session_artifact_loadable=False,
                memory_jsonl_present=memory_present,
                warnings=warnings,
            )

        data = self._read_json_safe(artifact_path)
        if data is None:
            warnings.append(
                "session_artifact.json is unreadable or not canonical JSON"
            )
            return SessionSummary(
                variant_tag=tag,
                session_artifact_loadable=False,
                memory_jsonl_present=memory_present,
                warnings=warnings,
            )

        sid = data.get("session_id") if isinstance(data, dict) else None
        cfg = data.get("config") if isinstance(data, dict) else None
        mode = cfg.get("mode") if isinstance(cfg, dict) else None
        kpis = data.get("kpis") if isinstance(data, dict) else None

        def _nopt(key: str) -> Any:
            if not isinstance(kpis, dict):
                return None
            return kpis.get(key)

        return SessionSummary(
            variant_tag=tag,
            session_id=sid if isinstance(sid, str) else None,
            mode=mode if isinstance(mode, str) else None,
            events_observed=_nopt("events_observed"),
            events_with_outcome=_nopt("events_with_outcome"),
            total_cost=_nopt("total_cost"),
            avg_cost=_nopt("avg_cost"),
            sla_preservation_rate=_nopt("sla_preservation_rate"),
            auto_execute_success_rate=_nopt("auto_execute_success_rate"),
            memory_jsonl_present=memory_present,
            session_artifact_loadable=True,
            warnings=warnings,
        )

    @staticmethod
    def _read_json_safe(path: str) -> Optional[dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _read_text_safe(path: str) -> Optional[str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None
