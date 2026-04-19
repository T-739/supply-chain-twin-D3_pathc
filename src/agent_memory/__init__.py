"""agent_memory/ — Path C B4 subpackage (Slice 1 contracts +
Slice 2A pure builder / deterministic renderer).

Slice 1 landed the frozen contract surface
(``AgentMemoryExampleRef``, ``AgentMemoryContext``,
``AgentMemoryExperimentConfig``).

Slice 2A adds two **pure functions** only —
``build_agent_memory_context`` and
``render_agent_memory_context``. They are reachable from
``tests/`` but are NOT wired into any agent, ``event_loop_c``,
session overlay, compare report, harness, or CLI. No runtime
caller exists yet.

Neither slice:

- modifies any agent module (``src/agents/*``);
- wires anything into ``src/event_loop_c.py``, ``src/session/*``,
  ``scripts/*``, or any CLI / harness surface;
- adds any KPI, any compare-report block, or any
  ``SessionEventRecord`` field;
- imports ``src/learning/cumulative_memory.py`` or
  ``src/correlator/*``;
- imports ``evaluation`` or ``action_code_mapper``;
- reads ``data/cases/*.json``;
- calls ``datetime.now`` / ``utcnow`` / ``time.time`` /
  ``uuid.uuid4``.

Design anchors (see docs/B4_AGENT_VISIBLE_MEMORY_BOUNDARY.md,
docs/B4_AGENT_VISIBLE_MEMORY_CONTRACT_DRAFT.md,
docs/B4_AGENT_VISIBLE_MEMORY_FILE_MAP.md):

- **D1** — First experiment target is ``operations`` agent only.
- **D2** — ``AgentMemoryContext`` is the single agent-visible
  contract surface (no free text, no raw ``MemoryRecord`` dump,
  no cumulative-memory loader semantics exposed).
- **D3** — ``AgentMemoryContext`` = aggregate summary fields +
  capped ``recent_examples`` (hard cap 3). No free-text
  explanation, confidence, or rationale field.
- **D4** — Placement is this new subpackage. Slice 1 ships the
  contract only; the single future operations-agent injection
  seam is out-of-scope here.
- **D5** — Gating via ``AgentMemoryExperimentConfig``;
  ``enable_agent_visible_memory`` defaults to ``False``;
  ``target_agent`` is ``operations`` only;
  ``allowed_modes`` defaults to ``frozenset({"PATH_C_WARM"})``;
  ``context_source`` is
  ``"structured_summary_plus_recent_examples"``.
- **D6** — No ``SessionEventRecord`` bump in Slice 1; no
  compare-report block; no KPI.
- **D7** — Future three-variant compare surface
  (``baseline_static`` / ``path_c_warm`` policy-only /
  ``path_c_warm`` + B4) is recorded in the docs; no code here.
"""

from agent_memory.agent_memory_builder import build_agent_memory_context
from agent_memory.agent_memory_config import (
    AgentMemoryExperimentConfig,
    KNOWN_AGENT_MEMORY_CONTEXT_SOURCES,
    KNOWN_AGENT_MEMORY_TARGETS,
    MAX_AGENT_MEMORY_EXAMPLES,
)
from agent_memory.agent_memory_renderer import render_agent_memory_context
from agent_memory.agent_memory_schema import (
    AGENT_MEMORY_SCHEMA_VERSION,
    AgentMemoryContext,
    AgentMemoryExampleRef,
)

__all__ = [
    "AGENT_MEMORY_SCHEMA_VERSION",
    "AgentMemoryContext",
    "AgentMemoryExampleRef",
    "AgentMemoryExperimentConfig",
    "KNOWN_AGENT_MEMORY_CONTEXT_SOURCES",
    "KNOWN_AGENT_MEMORY_TARGETS",
    "MAX_AGENT_MEMORY_EXAMPLES",
    "build_agent_memory_context",
    "render_agent_memory_context",
]
