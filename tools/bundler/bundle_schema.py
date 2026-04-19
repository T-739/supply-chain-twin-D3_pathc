"""Bundle contract constants + canonical variant-set classification.

See ``docs/B5_BUNDLE_CONTRACT.md`` for the authoritative spec.

Boundary note: this module is deliberately import-light. It does
not depend on ``src/session/*``, ``src/event_loop_c.py``, or any
other runtime module. The bundle contract is a surface over
on-disk JSON, not a re-export of runtime schemas.
"""

from __future__ import annotations

from typing import Literal, Sequence


BUNDLE_SCHEMA_VERSION: str = "1.0"
BUNDLER_SEMVER: str = "0.1.0"

# Default 3-mode trio (matches scripts/session_eval_harness.py
# pre-B4 output tags). Ordered.
DEFAULT_3_MODE_TAGS: tuple[str, ...] = (
    "baseline_static",
    "path_c_cold",
    "path_c_warm",
)

# B4 experiment triplet. Deliberately does NOT contain
# ``path_c_cold``. Matches the locked tag list in
# ``scripts/session_eval_harness._B4_EXPERIMENT_VARIANT_TAGS``.
B4_TRIPLET_TAGS: tuple[str, ...] = (
    "baseline_static",
    "path_c_warm_policy_only",
    "path_c_warm_agent_visible_memory",
)

VariantSet = Literal["default_3_mode", "b4_experiment_triplet", "custom"]


def classify_variant_set(variant_tags: Sequence[str]) -> VariantSet:
    """Classify a set of on-disk variant tags.

    Returns ``"default_3_mode"`` iff the tags, compared as a set,
    equal the default 3-mode tags. Returns
    ``"b4_experiment_triplet"`` iff the tags equal the B4 triplet.
    Anything else returns ``"custom"`` — explicitly including the
    2-variant subsets, single-variant bundles, and any future
    experiment sets. Callers MUST NOT treat ``"custom"`` as an
    error condition.
    """
    s = set(variant_tags)
    if s == set(DEFAULT_3_MODE_TAGS):
        return "default_3_mode"
    if s == set(B4_TRIPLET_TAGS):
        return "b4_experiment_triplet"
    return "custom"
