'use client';

import type { AgentMemoryExperimentSummary } from '@/lib/types';
import { B4ExperimentBlock } from '../compare/B4ExperimentBlock';

export interface AgentMemoryExperimentLensProps {
  summary: AgentMemoryExperimentSummary | undefined;
}

/**
 * B4 · Agent-visible memory experiment lens.
 *
 * This is a thin wrapper over the already-built
 * `B4ExperimentBlock` so B4 has one visual identity across the
 * Compare Lab and the Advanced Lenses surface. Both surfaces
 * must:
 *
 *   - always show the `experiment / default-off / compare-only`
 *     ribbon (even in the absent state);
 *   - be visually isolated from the other lenses;
 *   - never merge with B1 / B2 / B3 presentation.
 *
 * Centralising the render here means any future tightening of
 * the B4 framing lands in one place.
 */
export function AgentMemoryExperimentLens({
  summary,
}: AgentMemoryExperimentLensProps) {
  return (
    <div
      className="lens lens--b4"
      data-testid="agent-memory-lens"
      aria-label="B4 agent-visible memory experiment"
    >
      <B4ExperimentBlock summary={summary} />
    </div>
  );
}
