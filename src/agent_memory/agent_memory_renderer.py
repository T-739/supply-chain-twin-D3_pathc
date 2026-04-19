"""agent_memory/agent_memory_renderer.py — Path C B4 Slice 2A renderer.

Pure function that formats an ``AgentMemoryContext`` into a
fixed-layout plain-text block. The renderer is the only admitted
path from the B4 contract surface to agent-visible prompt text.

Slice 2A scope (locked by R5 + R6 in the Slice 2A prompt):

- **R5** — signature is
  ``render_agent_memory_context(context, config) -> str``. Output
  is deterministic; no value-dependent branching on templates;
  no free-form narrative; no "recommendation" / "conclusion" /
  "therefore" sentences.
- **R6** — format rules:
    * ``matched_records`` / ``cold_start`` / ``query_signature``
      first, in this order;
    * rate-like numeric fields (``auto_execute_success_rate``,
      ``sla_preservation_rate``, ``avg_cost``) emit ``n/a`` if
      ``None`` else ``str(round(x, 4))``;
    * ``action_type_distribution`` keys are emitted in
      lexicographic order;
    * ``recent_examples`` are numbered ``1..N`` with a fixed
      field layout; empty list emits a literal empty marker.

The renderer does NOT:

- call ``datetime.now`` / ``utcnow`` / ``time.time`` /
  ``uuid.uuid4``;
- read the ``EpisodicMemory`` (it only reads its
  ``AgentMemoryContext`` argument);
- import ``evaluation`` or ``action_code_mapper``;
- import from ``src/agents/*``, ``src/adaptive/*``,
  ``src/replan/*``, ``src/correlator/*``,
  ``src/learning/cumulative_memory.py``, or ``src/session/*``;
- branch on values to produce a different template.
"""

from __future__ import annotations

from typing import Optional

from agent_memory.agent_memory_config import AgentMemoryExperimentConfig
from agent_memory.agent_memory_schema import (
    AgentMemoryContext,
    AgentMemoryExampleRef,
)


#: Emitted for numeric rate / cost fields when the value is
#: ``None`` — denominator-was-zero cases surface as this token
#: (mirrors the MemorySummary-level ``None`` convention).
_NONE_TOKEN: str = "n/a"

#: Emitted for the ``recent_examples`` section when the context
#: has no rows to display. Chosen to be unambiguous and
#: grep-stable; never value-derived.
_EMPTY_EXAMPLES_MARKER: str = "recent_examples: none"

#: Rate / avg_cost rounding precision. Matches the Path C
#: serialization-boundary rule (round-at-reporting only); we do
#: not round values inside the ``AgentMemoryContext`` itself,
#: only at render time.
_NUMERIC_PRECISION: int = 4

#: Title line. Always first. Never omitted.
_HEADER_LINE: str = "AGENT_MEMORY_CONTEXT"


def _render_optional_number(value: Optional[float]) -> str:
    if value is None:
        return _NONE_TOKEN
    return str(round(float(value), _NUMERIC_PRECISION))


def _render_example(index: int, ex: AgentMemoryExampleRef) -> str:
    # Fixed field order. Field names are never omitted. Values
    # that are ``None`` render as ``n/a`` so readers can
    # distinguish "unknown" from "false" / "0". No branching on
    # values beyond the uniform None→n/a rule.
    def tok(v: object) -> str:
        if v is None:
            return _NONE_TOKEN
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)

    parts = [
        f"event_id={tok(ex.event_id)}",
        f"event_type={tok(ex.event_type)}",
        f"source_session_id={tok(ex.source_session_id)}",
        f"action_taken={tok(ex.action_taken)}",
        f"final_route={tok(ex.final_route)}",
        f"execution_status={tok(ex.execution_status)}",
        f"cost_incurred={tok(ex.cost_incurred)}",
        f"sla_preserved={tok(ex.sla_preserved)}",
    ]
    return f"  {index}. " + " | ".join(parts)


def render_agent_memory_context(
    context: AgentMemoryContext,
    config: AgentMemoryExperimentConfig,
) -> str:
    """Render an ``AgentMemoryContext`` into deterministic
    plain text.

    The ``config`` argument is accepted for symmetry with the
    builder and for future slices that may gate rendering
    details behind config knobs; Slice 2A consumes no field
    from it. Passing a different config must not change output
    bytes for the same context — this is enforced by the
    renderer determinism test.

    The returned string carries no trailing newline so callers
    can safely join it with other structured-text blocks.
    """
    # Explicitly consume config to keep readers honest about
    # the signature; no value read in Slice 2A per R5 / R6.
    _ = config

    lines: list[str] = []
    lines.append(_HEADER_LINE)
    lines.append(f"matched_records: {context.matched_records}")
    lines.append(
        "cold_start: " + ("true" if context.cold_start else "false")
    )
    lines.append(f"query_signature: {context.query_signature}")
    lines.append(
        "auto_execute_success_rate: "
        + _render_optional_number(context.auto_execute_success_rate)
    )
    lines.append(
        "sla_preservation_rate: "
        + _render_optional_number(context.sla_preservation_rate)
    )
    lines.append("avg_cost: " + _render_optional_number(context.avg_cost))

    # action_type_distribution — lexicographic key order; empty
    # dict emits a literal empty marker so there is never a
    # value-dependent skip.
    if context.action_type_distribution:
        lines.append("action_type_distribution:")
        for key in sorted(context.action_type_distribution.keys()):
            lines.append(f"  {key}: {context.action_type_distribution[key]}")
    else:
        lines.append("action_type_distribution: (none)")

    # recent_examples — numbered 1..N, uniform field layout;
    # empty list emits the fixed empty marker.
    if context.recent_examples:
        lines.append("recent_examples:")
        for i, ex in enumerate(context.recent_examples, start=1):
            lines.append(_render_example(i, ex))
    else:
        lines.append(_EMPTY_EXAMPLES_MARKER)

    return "\n".join(lines)
