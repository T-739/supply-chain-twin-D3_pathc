"""adaptive/preflight.py — Path C Phase 2 governance-metadata preflight.

Validates the *structured* governance identity metadata
(``_governance_meta``) *before* any Path C main-path execution. This is
the structural explainability gate (owner point 7) that lets Path C's
execution path be metadata-mandatory (owner point 6).

Contract (Roadmap §2.D, §2.E):
  - ``recommended_candidate_type`` must be a non-empty string and one of
    the four operational literals: EXPEDITE / TRANSFER / COMPENSATE /
    NO_ACTION.
  - ``recommended_candidate_id`` must be a non-empty string.
  - Forbidden tokens from other layers (APPROVE/VERIFY/OVERRIDE on
    supervision layer, AI/ALT1/ALT2 on evaluation layer) are rejected
    explicitly.
  - Failure raises ``GovernanceMetaPreflightError`` — never a silent
    default. The caller (``event_loop_c``) converts the exception into
    ``EffectiveDecisionRef.execution_status = "preflight_failed"`` and
    records a diagnostic note; it never writes into
    ``baseline_event_result``.

This module is pure: no I/O, no wall-clock, no uuid4.
"""

from __future__ import annotations

from typing import Any


OPERATIONAL_LITERALS: frozenset[str] = frozenset({
    "EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION",
})

_FORBIDDEN_SUPERVISION: frozenset[str] = frozenset({"APPROVE", "VERIFY", "OVERRIDE"})
_FORBIDDEN_EVALUATION: frozenset[str] = frozenset({"AI", "ALT1", "ALT2"})


class GovernanceMetaPreflightError(ValueError):
    """_governance_meta does not meet the Path C main-path structural contract."""


def validate_governance_meta(meta: Any) -> None:
    """Validate ``_governance_meta``. Raises on failure; returns None on success.

    The accepted shape is the same ``_governance_meta`` shape produced
    by the Path B ``governance_agent`` (three-field identity metadata).
    """
    if not isinstance(meta, dict):
        raise GovernanceMetaPreflightError(
            f"_governance_meta must be a dict, got {type(meta).__name__}"
        )

    t = meta.get("recommended_candidate_type")
    if not isinstance(t, str) or not t.strip():
        raise GovernanceMetaPreflightError(
            f"recommended_candidate_type must be a non-empty string, got {t!r}"
        )
    t_up = t.strip().upper()
    if t_up in _FORBIDDEN_SUPERVISION:
        raise GovernanceMetaPreflightError(
            f"recommended_candidate_type={t!r} is a supervision-layer token; "
            f"operational layer required"
        )
    if t_up in _FORBIDDEN_EVALUATION:
        raise GovernanceMetaPreflightError(
            f"recommended_candidate_type={t!r} is an evaluation-layer token; "
            f"operational layer required"
        )
    if t_up not in OPERATIONAL_LITERALS:
        raise GovernanceMetaPreflightError(
            f"recommended_candidate_type={t!r} is not one of "
            f"{sorted(OPERATIONAL_LITERALS)}"
        )

    cid = meta.get("recommended_candidate_id")
    if not isinstance(cid, str) or not cid.strip():
        raise GovernanceMetaPreflightError(
            f"recommended_candidate_id must be a non-empty string, got {cid!r}"
        )
