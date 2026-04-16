"""
action_code_mapper.py — Phase 1 evaluation bridge adapter (hardened).

Maps a supervisor decision (APPROVE / VERIFY / OVERRIDE) plus the loaded
case JSON into a single canonical evaluation action code (AI / ALT1 / ALT2).

Layer discipline
----------------
This module is the ONLY sanctioned bridge between the supervision layer
(APPROVE/VERIFY/OVERRIDE) and the evaluation layer (AI/ALT1/ALT2).

It does NOT:
  - Read operational identifiers (EXPEDITE/TRANSFER/COMPENSATE/NO_ACTION)
    as a source of truth.
  - Invent new action codes.
  - Mutate the case dict, supervisor output, or evaluation semantics.

Hardening (Phase 1 patch)
-------------------------
- OVERRIDE requires an explicit, exact-match `_override_target_label`.
- Substring / prefix / generic-alternative fallbacks are removed so that
  ambiguous or missing targets raise ActionCodeMappingError instead of
  silently collapsing to `alternative_plan` / `ALT2`.
- OVERRIDE mapping to an `approve`-type option is rejected; a real
  OVERRIDE must never resolve back to AI.

Source of truth
---------------
The case JSON's `decision_options` list (and `agent_recommendation_action_code`
as a fallback for APPROVE only). Supervisor operational identifiers are
never read as evaluation codes.
"""

from __future__ import annotations

from typing import Any, Literal

from evaluation import normalize_action_code

ActionCode = Literal["AI", "ALT1", "ALT2"]

_APPROVE_DECISION_TYPES = frozenset({"approve"})
_VERIFY_DECISION_TYPES = frozenset({"verify_pause", "verify"})


class ActionCodeMappingError(ValueError):
    """Raised when a supervisor decision cannot be mapped to AI/ALT1/ALT2."""


def _norm_label(s: Any) -> str:
    return str(s or "").strip().casefold()


def _find_by_decision_type(
    decision_options: list[dict[str, Any]],
    decision_types: frozenset[str],
) -> dict[str, Any] | None:
    for opt in decision_options:
        dt = str(opt.get("decision_type", "")).strip().lower()
        if dt in decision_types:
            return opt
    return None


def _exact_match_by_label(
    decision_options: list[dict[str, Any]],
    target_label: str,
) -> list[dict[str, Any]]:
    """Return all decision_options whose action_label matches target exactly
    (case-insensitive, whitespace-trimmed). No substring fallback."""
    needle = _norm_label(target_label)
    if not needle:
        return []
    return [
        opt for opt in decision_options
        if _norm_label(opt.get("action_label")) == needle
    ]


def map_supervisor_to_action_code(
    supervisor_output: dict[str, Any],
    case: dict[str, Any],
) -> ActionCode:
    """Map a SupervisorDecision dict + case JSON to an AI/ALT1/ALT2 code.

    Parameters
    ----------
    supervisor_output:
        Serialized SupervisorDecision-compatible dict. For OVERRIDE, callers
        MUST attach `_override_target_label` (the exact `action_label` from
        case.decision_options).
    case:
        Parsed case JSON with `decision_options` and
        `agent_recommendation_action_code`.

    Returns
    -------
    One of "AI" / "ALT1" / "ALT2".

    Raises
    ------
    ActionCodeMappingError
        If the supervisor decision cannot be resolved to an action code,
        is ambiguous, or would silently collapse an OVERRIDE into an approve.
    """
    if not isinstance(supervisor_output, dict):
        raise ActionCodeMappingError("supervisor_output must be a dict")
    if not isinstance(case, dict):
        raise ActionCodeMappingError("case must be a dict")

    decision_type_raw = supervisor_output.get("supervisor_decision_type", "")
    decision_type = str(decision_type_raw).strip().upper()

    decision_options = case.get("decision_options", []) or []
    if not isinstance(decision_options, list) or not decision_options:
        raise ActionCodeMappingError(
            "case.decision_options missing or empty; cannot map supervisor decision"
        )

    if decision_type == "APPROVE":
        opt = _find_by_decision_type(decision_options, _APPROVE_DECISION_TYPES)
        if opt is not None:
            return normalize_action_code(opt.get("action_code"))
        # Fall back to case-declared agent recommendation (canonical default "AI").
        raw = case.get("agent_recommendation_action_code", "AI")
        return normalize_action_code(raw)

    if decision_type == "VERIFY":
        opt = _find_by_decision_type(decision_options, _VERIFY_DECISION_TYPES)
        if opt is None:
            raise ActionCodeMappingError(
                "VERIFY supervision chosen but no verify_pause option exists "
                "in case.decision_options"
            )
        return normalize_action_code(opt.get("action_code"))

    if decision_type == "OVERRIDE":
        target_label = supervisor_output.get("_override_target_label", "") or ""
        if not _norm_label(target_label):
            raise ActionCodeMappingError(
                "OVERRIDE supervision requires an explicit _override_target_label "
                "matching an action_label in case.decision_options. "
                "Silent fallbacks are disabled to protect thesis metrics."
            )

        matches = _exact_match_by_label(decision_options, target_label)
        if len(matches) == 0:
            available = [o.get("action_label", "") for o in decision_options]
            raise ActionCodeMappingError(
                f"OVERRIDE target_action_label '{target_label}' not found in "
                f"case.decision_options action_labels {available!r}. "
                "Exact match is required; substring/partial matching is disabled."
            )
        if len(matches) > 1:
            raise ActionCodeMappingError(
                f"OVERRIDE target_action_label '{target_label}' is ambiguous; "
                f"{len(matches)} decision_options share this label."
            )

        opt = matches[0]
        opt_type = str(opt.get("decision_type", "")).strip().lower()
        if opt_type in _APPROVE_DECISION_TYPES:
            raise ActionCodeMappingError(
                f"OVERRIDE target '{target_label}' resolves to an 'approve' "
                "option; an OVERRIDE must never collapse to AI."
            )
        code = normalize_action_code(opt.get("action_code"))
        if code == "AI":
            raise ActionCodeMappingError(
                f"OVERRIDE target '{target_label}' resolves to action_code 'AI'; "
                "an OVERRIDE must never evaluate as AI."
            )
        return code

    raise ActionCodeMappingError(
        f"Unknown supervisor_decision_type '{decision_type_raw}'. "
        "Expected APPROVE / VERIFY / OVERRIDE."
    )


# ---------------------------------------------------------------------------
# Batch helper — exposed so scripts/batch_eval_runner.py does not need to
# reimplement the "find the alternative_plan label" rule.
# ---------------------------------------------------------------------------


def find_override_target_label(case: dict[str, Any]) -> str | None:
    """Return the exact `action_label` of the case's non-approve, non-verify
    override target (the `alternative_plan` option), or None if absent.

    Intended for deterministic batch replay where the "real" override target
    is whichever alternative_plan option the case itself declares. If a case
    has no such option, callers should skip it rather than force a mapping.
    """
    if not isinstance(case, dict):
        return None
    opts = case.get("decision_options", []) or []
    # Prefer a decision_type of alternative_plan / alternative.
    preferred = {"alternative_plan", "alternative"}
    for opt in opts:
        dt = str(opt.get("decision_type", "")).strip().lower()
        if dt in preferred:
            label = str(opt.get("action_label", "")).strip()
            return label or None
    return None
