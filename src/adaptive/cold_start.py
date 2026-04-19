"""adaptive/cold_start.py — Path C Phase 2 cold-start guard.

Pure helpers:

  - ``is_cold_start(matched_records, min_records_for_shift) -> bool``
  - ``build_cold_start_adjustment(...) -> AdaptivePolicyAdjustment``

Semantics (Roadmap §1.D + §2.D, owner point v2.1-D):
  The canonical owner of the threshold is
  ``AdaptivePolicyGateConfig.min_records_for_shift``. Cold start fires
  iff ``matched_records < threshold``. When cold start fires, the
  policy decision is the *baseline* static policy (no risk shift) and
  the overlay records an ``AdaptivePolicyAdjustment`` of type
  ``COLD_START_FALLBACK`` so the event is auditable.

No wall-clock, no uuid4, no data/cases access, no decision on rounded
values.
"""

from __future__ import annotations

from typing import Any

from adaptive.adaptive_schema import AdaptivePolicyAdjustment
from learning.memory_schema import MemorySummary


COLD_START_RULE_ID: str = "cold_start_guard_v1"


def is_cold_start(matched_records: int, min_records_for_shift: int) -> bool:
    """True iff memory is too sparse to drive a risk shift for this query."""
    return int(matched_records) < int(min_records_for_shift)


def build_cold_start_adjustment(
    *,
    risk_level: str,
    summary: MemorySummary,
    min_records_for_shift: int,
) -> AdaptivePolicyAdjustment:
    """Construct the COLD_START_FALLBACK adjustment.

    ``pre_adjustment_risk == post_adjustment_risk`` by construction —
    cold start is explicitly a *no-shift* overlay. The adjustment exists
    purely so the overlay is auditable.
    """
    return AdaptivePolicyAdjustment(
        rule_id=COLD_START_RULE_ID,
        adjustment_type="COLD_START_FALLBACK",
        pre_adjustment_risk=risk_level,
        post_adjustment_risk=risk_level,
        query_signature=summary.query_signature,
        memory_evidence={
            "matched_records": summary.matched_records,
            "min_records_for_shift": int(min_records_for_shift),
        },
        notes=(
            f"Cold-start fallback: matched_records="
            f"{summary.matched_records} < min_records_for_shift="
            f"{int(min_records_for_shift)}. Applied baseline static policy."
        ),
    )
