"""agent_memory/agent_memory_builder.py — Path C B4 Slice 2A builder.

Pure function that projects an ``EpisodicMemory`` + ``MemoryQuery``
+ ``AgentMemoryExperimentConfig`` into an ``AgentMemoryContext``.
The builder is the single allowed assembly boundary for the B4
agent-visible contract surface.

Slice 2A scope (locked by R1–R7 in the Slice 2A prompt):

- **R1** — signature is
  ``build_agent_memory_context(memory, query, config) -> AgentMemoryContext``.
- **R2** — reads only ``src/learning/episodic_memory.py``,
  ``src/learning/memory_schema.py``,
  ``src/learning/memory_summarizer.py``, and its sibling
  ``agent_memory`` modules. No other dependency is admissible.
- **R3** — ``AgentMemoryContext.cold_start`` in B4 is
  ``matched_records == 0``. This is *structurally independent* of
  the adaptive gate's cold-start threshold — B4 does not import
  ``AdaptivePolicyGateConfig`` and must not inherit the policy
  path's threshold semantics. We call the shared
  ``summarize_records`` helper only for its aggregate fields
  (rates, distribution, avg cost, signature); its
  ``MemorySummary.cold_start`` value is deliberately discarded.
- **R4** — ``recent_examples`` are the last
  ``config.max_recent_examples`` rows of the canonical-order
  matched list, preserving the canonical
  ``(event_timestamp, event_id)`` sort — i.e. oldest-to-newest
  within the selected tail.
- **R7** — no digest contribution, no overlay write-back,
  no session-level side effect.

This module does NOT:

- call ``datetime.now`` / ``utcnow`` / ``time.time`` /
  ``uuid.uuid4``;
- read ``data/cases/*.json``;
- import ``evaluation`` or ``action_code_mapper``;
- import from ``src/agents/*``, ``src/adaptive/*``,
  ``src/replan/*``, ``src/correlator/*``,
  ``src/learning/cumulative_memory.py``, or ``src/session/*``;
- mutate any ``EpisodicMemory`` / ``MemoryRecord`` instance.
"""

from __future__ import annotations

from agent_memory.agent_memory_config import AgentMemoryExperimentConfig
from agent_memory.agent_memory_schema import (
    AgentMemoryContext,
    AgentMemoryExampleRef,
)
from learning.episodic_memory import EpisodicMemory
from learning.memory_schema import MemoryQuery, MemoryRecord
from learning.memory_summarizer import summarize_records


#: Threshold passed into the shared ``summarize_records`` helper.
#: B4 immediately overrides ``cold_start`` per R3, so this value
#: does not shape B4 semantics — it only satisfies the helper's
#: required argument. We deliberately choose ``1`` rather than the
#: adaptive gate's ``min_records_for_shift`` to avoid importing
#: ``AdaptivePolicyGateConfig`` and to make the structural
#: independence of the two consumer paths obvious at the call
#: site.
_SUMMARIZER_THRESHOLD_PLACEHOLDER: int = 1


def build_agent_memory_context(
    memory: EpisodicMemory,
    query: MemoryQuery,
    config: AgentMemoryExperimentConfig,
) -> AgentMemoryContext:
    """Project memory state into an ``AgentMemoryContext``.

    The builder is a pure function of its three inputs. Calling
    it twice with the same inputs returns two
    ``AgentMemoryContext`` instances whose ``model_dump()`` is
    byte-equal.

    Parameters
    ----------
    memory
        The already-assembled ``EpisodicMemory`` the caller
        wants the agent to see. B4 never assembles memory
        itself; if B3 cumulative memory is in use, the caller
        is responsible for building the merged memory and
        passing it here unchanged.
    query
        The structured query the agent is about to reason
        about. Used both for filtering (delegated to
        ``EpisodicMemory.query``) and for the
        ``query_signature`` string (delegated to
        ``memory_summarizer.query_signature`` via
        ``summarize_records``).
    config
        The frozen Slice 1 config. Only ``max_recent_examples``
        is read in Slice 2A. ``enable_agent_visible_memory`` is
        *not* checked inside the builder — gating lives at the
        caller layer (future slice). The builder always
        produces a valid context; refusing to call it is the
        caller's responsibility.

    Returns
    -------
    AgentMemoryContext
        Frozen pydantic instance whose ``recent_examples`` list
        has length in ``[0, config.max_recent_examples]``. An
        empty ``recent_examples`` list paired with
        ``cold_start=True`` is valid (captures the no-match
        case structurally).
    """
    matched: list[MemoryRecord] = memory.query(query)

    # summarize_records supplies aggregate-only fields. We
    # discard its cold_start per R3.
    summary = summarize_records(
        matched, query, threshold=_SUMMARIZER_THRESHOLD_PLACEHOLDER
    )

    # R4: take the most-recent max_recent_examples rows. matched
    # is already in canonical (event_timestamp, event_id) order;
    # a trailing slice preserves that order within the selected
    # tail (oldest-to-newest).
    cap = int(config.max_recent_examples)
    tail = matched[-cap:] if cap > 0 else []

    recent_examples = [
        AgentMemoryExampleRef(
            event_id=r.event_id,
            event_type=r.event_type,
            source_session_id=r.session_id,
            action_taken=r.action_taken,
            final_route=r.final_route,
            execution_status=r.execution_status,
            cost_incurred=r.cost_incurred,
            sla_preserved=r.sla_preserved,
        )
        for r in tail
    ]

    matched_records = summary.matched_records
    return AgentMemoryContext(
        matched_records=matched_records,
        cold_start=(matched_records == 0),  # R3
        query_signature=summary.query_signature,
        auto_execute_success_rate=summary.auto_execute_success_rate,
        sla_preservation_rate=summary.sla_preservation_rate,
        avg_cost=summary.avg_cost,
        action_type_distribution=dict(summary.action_type_distribution),
        recent_examples=recent_examples,
    )
