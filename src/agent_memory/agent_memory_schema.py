"""agent_memory/agent_memory_schema.py — Path C B4 Slice 1 schema skeletons.

Classes + closed Literals only. No runtime behavior — no builder,
no renderer, no prompt assembly, no event_loop hook. Matching
entries live in ``PATH_C_SCHEMA_REGISTRY.md`` under the B4
Slice 1 section.

Owner-fixed decisions (see docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md §12
and docs/B4_AGENT_VISIBLE_MEMORY_CONTRACT_DRAFT.md §11):

  D1 : First experiment target is ``operations`` agent only. The
       governance agent is not touched in B4 v1.

  D2 : ``AgentMemoryContext`` is the single agent-visible contract
       surface. Free text, raw ``MemoryRecord`` dumps, and direct
       cumulative-memory loader outputs are NOT admissible surfaces.

  D3 : ``AgentMemoryContext`` carries *aggregate summary fields* +
       a *capped list of recent examples*. The cap is
       ``MAX_AGENT_MEMORY_EXAMPLES`` (= 3). No free-text
       explanation, no confidence / probability, no rationale
       paragraph.

  D6 : ``SessionEventRecord`` is NOT bumped in Slice 1 — no
       ``agent_memory_context`` overlay field, no compare-report
       block. The contracts here stand alone until a later slice
       owns that wiring.

Structural explainability (enforced here):

- ``AgentMemoryExampleRef`` carries closed Literals for
  ``action_taken`` / ``final_route`` / ``execution_status``. These
  Literals are **locally redefined** (not imported from
  ``session.session_schema``) to avoid a circular import — the same
  workaround used by ``replan.replan_schema`` for
  ``ReplanAttemptRecord``. The domains mirror the Path B / Path C
  values exactly.
- ``AgentMemoryContext.recent_examples`` is length-capped to
  ``MAX_AGENT_MEMORY_EXAMPLES``; an empty list is explicitly valid
  (captures the cold-start / no-match case structurally).
- No ``confidence`` / ``rationale`` / ``explanation`` field, no
  ``correlation_context`` field, no ``baseline_event_result``
  write surface.

This module does NOT:

- import ``evaluation`` or ``action_code_mapper``;
- read ``data/cases/*.json``;
- call ``datetime.now`` / ``utcnow`` / ``time.time`` /
  ``uuid.uuid4``;
- import from ``src/agents/*``, ``src/adaptive/*``,
  ``src/replan/*``, ``src/correlator/*``,
  ``src/learning/cumulative_memory.py``, or
  ``src/session/*``.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_memory.agent_memory_config import MAX_AGENT_MEMORY_EXAMPLES


AGENT_MEMORY_SCHEMA_VERSION: str = "1.0"


# ---------------------------------------------------------------------------
# Locally-redefined Literals (parallel to replan.replan_schema)
#
# These mirror the closed domains in session.session_schema /
# learning.memory_schema exactly. They are redefined here (rather
# than imported) to keep the B4 subpackage structurally independent
# of session.session_schema; see the docstring above for the same
# reasoning used by B1's replan_schema.
# ---------------------------------------------------------------------------

_AGENT_MEMORY_ACTION_TAKEN = Literal[
    "EXPEDITE", "TRANSFER", "COMPENSATE", "NO_ACTION"
]
_AGENT_MEMORY_FINAL_ROUTE = Literal["AUTO_EXECUTE", "HUMAN_REQUIRED"]
_AGENT_MEMORY_EXECUTION_STATUS = Literal[
    "executed",
    "executed_via_demo_override",
    "awaiting_human_review",
    "execution_failed",
    "unknown_route",
    "preflight_failed",
]


# ---------------------------------------------------------------------------
# AgentMemoryExampleRef
# ---------------------------------------------------------------------------


class AgentMemoryExampleRef(BaseModel):
    """Structured reference to one historical memory row, included
    in an ``AgentMemoryContext`` as one of the capped
    ``recent_examples``.

    Carries only structured facts about a past operational attempt
    — never a free-text recap, never a confidence scalar, never a
    copy of any natural-language governance field. Readers
    (a future B4 prompt renderer) may format this into structured
    prompt text, but the *data* on this schema is the authoritative
    record of what was shown to the agent.

    ``source_session_id`` is the session in which the referenced
    row was originally appended to episodic memory. It mirrors
    ``MemoryRecord.session_id`` and preserves cross-session
    provenance when the underlying ``EpisodicMemory`` was assembled
    from cumulative memory (B3). B4 itself does not distinguish
    self-session from cross-session rows — the provenance flows
    through the same field verbatim.

    Invariants (structural):

    - ``event_id``, ``event_type``, ``source_session_id`` are
      non-empty strings;
    - ``final_route`` and ``execution_status`` are closed Literals;
    - ``action_taken`` is either a closed Literal or ``None`` (to
      represent the no-action / not-yet-acted cases already
      admissible on ``MemoryRecord``).
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    source_session_id: str
    action_taken: Optional[_AGENT_MEMORY_ACTION_TAKEN] = None
    final_route: _AGENT_MEMORY_FINAL_ROUTE
    execution_status: _AGENT_MEMORY_EXECUTION_STATUS
    cost_incurred: Optional[float] = None
    sla_preserved: Optional[bool] = None
    schema_version: str = Field(default=AGENT_MEMORY_SCHEMA_VERSION)

    @field_validator("event_id")
    @classmethod
    def _event_id_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("event_id must be a non-empty string")
        return v

    @field_validator("event_type")
    @classmethod
    def _event_type_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("event_type must be a non-empty string")
        return v

    @field_validator("source_session_id")
    @classmethod
    def _source_session_id_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("source_session_id must be a non-empty string")
        return v


# ---------------------------------------------------------------------------
# AgentMemoryContext
# ---------------------------------------------------------------------------


class AgentMemoryContext(BaseModel):
    """The single B4 agent-visible contract surface (D2).

    The future B4 builder will project an ``EpisodicMemory`` +
    an ``AgentMemoryExperimentConfig`` into one of these. A future
    renderer will format it into structured prompt text. Both of
    those components are out-of-scope for Slice 1; this class
    freezes only the *shape* the agent is ever allowed to see.

    Shape is fixed by D3: aggregate summary fields + capped
    ``recent_examples``. No free-text explanation, confidence
    scalar, rationale paragraph, or LLM-written memory summary
    field is admissible on this surface.

    Semantic parallels (deliberately structured, **not**
    inheritance):

    - The aggregate block mirrors ``MemorySummary`` 1.0 field
      shapes (``matched_records``, ``cold_start``,
      ``auto_execute_success_rate``, ``sla_preservation_rate``,
      ``action_type_distribution``, ``avg_cost``,
      ``query_signature``). Using the same field names keeps the
      structural contract readable against the existing adaptive-
      gate consumer path, but we do NOT inherit from
      ``MemorySummary`` — the two surfaces serve different
      consumers (policy gate vs. agent prompt) and must be able
      to evolve independently under their own boundary rules.
    - ``recent_examples`` is the per-row projection, hard-capped
      by ``MAX_AGENT_MEMORY_EXAMPLES`` (= 3) and validated on
      construction.

    Invariants (structural):

    - ``matched_records >= 0``;
    - ``0 <= len(recent_examples) <= MAX_AGENT_MEMORY_EXAMPLES``
      (empty list is valid and common under cold-start);
    - ``query_signature`` is a non-empty string (a content-
      addressed signature that identifies *what* was queried, not
      *why*; it never carries free text). An empty signature is
      rejected to keep the surface auditable.

    Explicitly NOT on this schema (enforced via ``extra='forbid'``
    and the B4 no-truth-write test):

    - ``rationale`` / ``rationale_trace`` / ``explanation`` /
      ``confidence`` / ``confidence_note`` / ``cost_summary`` /
      ``situational_explanation`` / ``alternative_actions``;
    - ``correlation_context`` (B2 sideband stays separate);
    - ``baseline_event_result`` or any Path B raw write surface;
    - ``risk_level`` or ``recommended_action`` (governance truth
      surface is frozen).
    """

    model_config = ConfigDict(extra="forbid")

    matched_records: int
    cold_start: bool
    query_signature: str
    auto_execute_success_rate: Optional[float] = None
    sla_preservation_rate: Optional[float] = None
    avg_cost: Optional[float] = None
    action_type_distribution: dict[str, int] = Field(default_factory=dict)
    recent_examples: list[AgentMemoryExampleRef] = Field(default_factory=list)
    schema_version: str = Field(default=AGENT_MEMORY_SCHEMA_VERSION)

    @field_validator("matched_records")
    @classmethod
    def _matched_non_negative(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("matched_records must be an int")
        if v < 0:
            raise ValueError(f"matched_records must be >= 0, got {v}")
        return v

    @field_validator("query_signature")
    @classmethod
    def _query_signature_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("query_signature must be a non-empty string")
        return v

    @field_validator("auto_execute_success_rate")
    @classmethod
    def _auto_rate_bounded(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("auto_execute_success_rate must be a float or None")
        v = float(v)
        if v < 0.0 or v > 1.0:
            raise ValueError(
                f"auto_execute_success_rate must be in [0.0, 1.0], got {v}"
            )
        return v

    @field_validator("sla_preservation_rate")
    @classmethod
    def _sla_rate_bounded(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("sla_preservation_rate must be a float or None")
        v = float(v)
        if v < 0.0 or v > 1.0:
            raise ValueError(
                f"sla_preservation_rate must be in [0.0, 1.0], got {v}"
            )
        return v

    @field_validator("action_type_distribution")
    @classmethod
    def _dist_int_counts(cls, v: dict[str, int]) -> dict[str, int]:
        if not isinstance(v, dict):
            raise ValueError("action_type_distribution must be a dict")
        for k, n in v.items():
            if not isinstance(k, str) or not k:
                raise ValueError(
                    "action_type_distribution keys must be non-empty strings"
                )
            if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                raise ValueError(
                    "action_type_distribution values must be non-negative ints"
                )
        return v

    @field_validator("recent_examples")
    @classmethod
    def _examples_capped(
        cls, v: list[AgentMemoryExampleRef]
    ) -> list[AgentMemoryExampleRef]:
        if not isinstance(v, list):
            raise ValueError("recent_examples must be a list")
        if len(v) > MAX_AGENT_MEMORY_EXAMPLES:
            raise ValueError(
                f"recent_examples length {len(v)} exceeds hard cap "
                f"MAX_AGENT_MEMORY_EXAMPLES={MAX_AGENT_MEMORY_EXAMPLES}"
            )
        return v
