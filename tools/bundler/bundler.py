"""Bundler core — repackages a harness output directory into the
canonical B5 bundle layout.

Read-only semantics:
  - no mutation of harness output
  - no import of runtime decision code
  - byte-for-byte copy of session_artifact.json / memory.jsonl /
    compare_report.json / thesis_report.md
  - metadata.json is synthesized from on-disk shape only

Null-safety:
  - missing compare_report.json is tolerated and flagged
  - missing thesis_report.md is tolerated and flagged
  - missing memory.jsonl is tolerated per-session and flagged
  - malformed session_artifact.json excludes the session from
    session_ids and emits a warning; bundle remains loadable
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any, Iterable

from tools.bundler.bundle_schema import (
    BUNDLE_SCHEMA_VERSION,
    BUNDLER_SEMVER,
    classify_variant_set,
)


_SESSION_ARTIFACT_FILENAME = "session_artifact.json"
_MEMORY_FILENAME = "memory.jsonl"
_COMPARE_FILENAME = "compare_report.json"
_THESIS_FILENAME = "thesis_report.md"


class BundlerError(Exception):
    """Raised for bundler misuse (bad inputs, unwritable targets).

    Missing optional artifacts DO NOT raise — they produce
    warnings in ``metadata.json``. This exception is reserved
    for errors the caller can correct (no such source dir,
    empty variant set, etc.)."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_bundle_from_harness_dir(
    *,
    harness_dir: str | os.PathLike,
    bundles_root: str | os.PathLike,
    bundle_id: str,
    variant_tags: Iterable[str] | None = None,
    source_notes: str = "",
) -> dict[str, Any]:
    """Repackage a harness output dir into ``{bundles_root}/{bundle_id}/``.

    Parameters
    ----------
    harness_dir:
        Existing harness output directory. Must contain one
        subdirectory per variant tag, each holding a
        ``session_artifact.json`` (and optionally a
        ``memory.jsonl``). May also contain top-level
        ``compare_report.json`` / ``thesis_report.md``.
    bundles_root:
        Directory under which ``{bundle_id}/`` is created.
    bundle_id:
        Stable bundle identifier. Used as the on-disk
        subdirectory name and as ``metadata.bundle_id``.
    variant_tags:
        Explicit ordered list of variant tags to include. When
        ``None`` (default), tags are discovered by scanning
        ``harness_dir`` for subdirectories containing a
        ``session_artifact.json``. Discovery order is
        alphabetical for determinism.
    source_notes:
        Free-form note recorded under ``metadata.source.notes``.

    Returns the metadata dict that was written.
    """
    harness_dir = os.fspath(harness_dir)
    bundles_root = os.fspath(bundles_root)

    if not bundle_id or not isinstance(bundle_id, str):
        raise BundlerError("bundle_id must be a non-empty string")
    if not os.path.isdir(harness_dir):
        raise BundlerError(
            f"harness_dir does not exist or is not a directory: {harness_dir!r}"
        )

    if variant_tags is None:
        discovered = _discover_variant_tags(harness_dir)
    else:
        discovered = list(variant_tags)
    if not discovered:
        raise BundlerError(
            f"no variant tags discovered under {harness_dir!r} "
            f"(no subdirectory with a {_SESSION_ARTIFACT_FILENAME})"
        )

    # Stale-output guard: every write goes into a sibling staging
    # directory under ``bundles_root`` (same filesystem so the
    # final swap is atomic). If a previous run left ``{bundle_id}``
    # on disk with extra session subdirectories or a
    # ``thesis_report.md`` that this run no longer produces, the
    # rmtree-then-rename at the end replaces it wholesale. On
    # failure, the staging dir is cleaned up and the existing
    # bundle (if any) is left untouched.
    final_bundle_dir = os.path.join(bundles_root, bundle_id)
    os.makedirs(bundles_root, exist_ok=True)
    staging_dir = tempfile.mkdtemp(
        prefix=f".{bundle_id}.staging.", dir=bundles_root,
    )

    try:
        bundle_dir = staging_dir
        sessions_root = os.path.join(bundle_dir, "sessions")
        os.makedirs(sessions_root, exist_ok=True)

        warnings: list[str] = []
        session_ids: dict[str, str] = {}
        kept_tags: list[str] = []

        for tag in discovered:
            src = os.path.join(harness_dir, tag)
            if not os.path.isdir(src):
                warnings.append(
                    f"variant tag {tag!r}: source subdirectory not found; "
                    f"skipping"
                )
                continue
            dst = os.path.join(sessions_root, tag)
            os.makedirs(dst, exist_ok=True)

            artifact_src = os.path.join(src, _SESSION_ARTIFACT_FILENAME)
            if not os.path.isfile(artifact_src):
                warnings.append(
                    f"variant tag {tag!r}: {_SESSION_ARTIFACT_FILENAME} missing"
                )
                continue
            artifact_dst = os.path.join(dst, _SESSION_ARTIFACT_FILENAME)
            shutil.copyfile(artifact_src, artifact_dst)

            sid = _read_session_id_safe(artifact_dst)
            if sid is None:
                warnings.append(
                    f"variant tag {tag!r}: {_SESSION_ARTIFACT_FILENAME} is not "
                    f"readable canonical JSON or has no session_id; excluded "
                    f"from session_ids"
                )
            else:
                session_ids[tag] = sid

            memory_src = os.path.join(src, _MEMORY_FILENAME)
            if os.path.isfile(memory_src):
                shutil.copyfile(memory_src, os.path.join(dst, _MEMORY_FILENAME))
            else:
                warnings.append(
                    f"variant tag {tag!r}: {_MEMORY_FILENAME} absent"
                )

            kept_tags.append(tag)

        if not kept_tags:
            raise BundlerError(
                f"no variant produced a usable session_artifact.json under "
                f"{harness_dir!r}; refusing to write an empty bundle"
            )

        # ---- optional bundle-level artifacts ----
        compare_src = os.path.join(harness_dir, _COMPARE_FILENAME)
        has_compare = os.path.isfile(compare_src)
        if has_compare:
            shutil.copyfile(
                compare_src, os.path.join(bundle_dir, _COMPARE_FILENAME),
            )
        else:
            warnings.append(f"{_COMPARE_FILENAME} absent from harness dir")

        thesis_src = os.path.join(harness_dir, _THESIS_FILENAME)
        has_thesis = os.path.isfile(thesis_src)
        if has_thesis:
            shutil.copyfile(
                thesis_src, os.path.join(bundle_dir, _THESIS_FILENAME),
            )
        else:
            warnings.append(f"{_THESIS_FILENAME} absent from harness dir")

        metadata = build_metadata(
            bundle_id=bundle_id,
            variant_tags=kept_tags,
            session_ids=session_ids,
            has_compare_report=has_compare,
            has_thesis_report=has_thesis,
            source_kind="harness_repackage",
            source_origin=os.path.basename(os.path.abspath(harness_dir)),
            source_notes=source_notes,
            warnings=warnings,
        )
        _write_metadata(bundle_dir, metadata)
    except BaseException:
        # Leave the existing final bundle (if any) untouched; only
        # the staging tree is discarded.
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    # Atomic swap: rmtree the previous final dir (if any), then
    # rename the staging dir into place. On POSIX, ``os.rename``
    # on a non-existent target is atomic; the gap between rmtree
    # and rename is the only non-atomic window, and it is
    # acceptable for this offline repackaging tool.
    if os.path.isdir(final_bundle_dir):
        shutil.rmtree(final_bundle_dir)
    os.rename(staging_dir, final_bundle_dir)
    return metadata


def build_metadata(
    *,
    bundle_id: str,
    variant_tags: list[str],
    session_ids: dict[str, str],
    has_compare_report: bool,
    has_thesis_report: bool,
    source_kind: str,
    source_origin: str,
    source_notes: str = "",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Pure metadata.json builder. No filesystem side effects."""
    variant_set = classify_variant_set(variant_tags)
    return {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "variant_set": variant_set,
        "variant_tags": list(variant_tags),
        "session_ids": dict(session_ids),
        "has_compare_report": bool(has_compare_report),
        "has_thesis_report": bool(has_thesis_report),
        "source": {
            "kind": source_kind,
            "origin": source_origin,
            "notes": source_notes,
        },
        "produced_by": BUNDLER_SEMVER,
        "warnings": list(warnings or []),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _discover_variant_tags(harness_dir: str) -> list[str]:
    out: list[str] = []
    for entry in sorted(os.listdir(harness_dir)):
        sub = os.path.join(harness_dir, entry)
        if not os.path.isdir(sub):
            continue
        if os.path.isfile(os.path.join(sub, _SESSION_ARTIFACT_FILENAME)):
            out.append(entry)
    return out


def _read_session_id_safe(artifact_path: str) -> str | None:
    try:
        with open(artifact_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    sid = data.get("session_id") if isinstance(data, dict) else None
    return sid if isinstance(sid, str) and sid else None


def _write_metadata(bundle_dir: str, metadata: dict[str, Any]) -> None:
    path = os.path.join(bundle_dir, "metadata.json")
    payload = json.dumps(metadata, sort_keys=True, indent=2, ensure_ascii=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write(payload)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
