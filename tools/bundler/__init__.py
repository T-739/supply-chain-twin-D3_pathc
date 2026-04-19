"""tools/bundler — B5 Phase-1 bundle repackager.

Read-only repackager that converts a harness output directory
(the existing shape produced by ``scripts/session_eval_harness.py``)
into the canonical B5 bundle layout described in
``docs/B5_BUNDLE_CONTRACT.md``.

This package MUST NOT import any runtime decision logic. It
reads JSON defensively and copies bytes verbatim.
"""

from tools.bundler.bundle_schema import (
    BUNDLE_SCHEMA_VERSION,
    BUNDLER_SEMVER,
    DEFAULT_3_MODE_TAGS,
    B4_TRIPLET_TAGS,
    classify_variant_set,
)
from tools.bundler.bundler import (
    BundlerError,
    build_bundle_from_harness_dir,
    build_metadata,
)

__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "BUNDLER_SEMVER",
    "DEFAULT_3_MODE_TAGS",
    "B4_TRIPLET_TAGS",
    "classify_variant_set",
    "BundlerError",
    "build_bundle_from_harness_dir",
    "build_metadata",
]
