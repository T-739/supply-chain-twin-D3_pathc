'use client';

import type { AgentMemoryExperimentSummary } from '@/lib/types';
import { CollapsibleJson } from '../CollapsibleJson';

export interface B4ExperimentBlockProps {
  summary: AgentMemoryExperimentSummary | undefined;
}

/**
 * Render of the B4 `agent_memory_experiment_summary` sibling
 * block.
 *
 * Three invariants are load-bearing:
 *
 *   1. It is surfaced only when the compare report actually
 *      carries the block. Absence is a valid state — we do NOT
 *      fabricate a B4 interpretation from a missing block.
 *
 *   2. Visually isolated from the mainline compare surface.
 *      The experiment ribbon ("experiment · default-off ·
 *      compare-only") is always present while the block is
 *      rendered. KPI matrix, deltas, thesis claim support
 *      remain the canonical story.
 *
 *   3. Structural only. We render the tag list, the per-tag
 *      session-id map, and the diverged-event-id list exactly
 *      as the artifact committed to them — no KPI merging, no
 *      NL paraphrase.
 */
export function B4ExperimentBlock({ summary }: B4ExperimentBlockProps) {
  if (!summary) {
    return (
      <section
        className="b4-experiment b4-experiment--absent"
        data-testid="b4-experiment-absent"
        aria-label="B4 agent-visible memory experiment (absent)"
      >
        <header className="b4-experiment__ribbon">
          <strong>B4 · Agent-visible memory (experiment)</strong>
          <ul className="b4-experiment__labels" data-testid="b4-experiment-labels">
            <li>experiment</li>
            <li>default-off</li>
            <li>compare-only</li>
          </ul>
        </header>
        <p className="compare-lab__absent">
          This compare report does not carry the{' '}
          <code>agent_memory_experiment_summary</code> sibling block. B4
          is opt-in on the harness and its compare-level footprint only
          appears on bundles produced with{' '}
          <code>--enable-agent-visible-memory</code>.
        </p>
      </section>
    );
  }

  const variantTags = Array.isArray(summary.variant_tags)
    ? summary.variant_tags
    : [];
  const sessionIds = summary.session_ids_by_variant ?? {};
  const diverged = Array.isArray(
    summary.agent_visible_vs_policy_only_diverged_event_ids,
  )
    ? summary.agent_visible_vs_policy_only_diverged_event_ids
    : [];

  return (
    <section
      className="b4-experiment"
      data-testid="b4-experiment"
      aria-label="B4 agent-visible memory experiment"
    >
      <header className="b4-experiment__ribbon">
        <strong>B4 · Agent-visible memory (experiment)</strong>
        <ul
          className="b4-experiment__labels"
          data-testid="b4-experiment-labels"
        >
          <li>experiment</li>
          <li>default-off</li>
          <li>compare-only</li>
        </ul>
      </header>
      <p className="b4-experiment__framing">
        Opt-in compare-only sibling block emitted by
        <code> session_compare.build_compare_report </code>
        when the harness passes
        <code> agent_memory_variant_tags</code>. Kept visually distinct
        from the mainline compare surface. Not a runtime/session feature.
      </p>

      <div className="b4-experiment__grid">
        <div>
          <dt>schema_version</dt>
          <dd data-testid="b4-experiment-schema">
            <code>v{summary.schema_version ?? '—'}</code>
          </dd>
        </div>
        <div>
          <dt>variant_tags</dt>
          <dd>
            {variantTags.length === 0 ? (
              <span className="compare-lab__absent">—</span>
            ) : (
              <ul
                className="b4-experiment__tags"
                data-testid="b4-experiment-variant-tags"
              >
                {variantTags.map((t) => (
                  <li key={t}>
                    <code>{t}</code>
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
      </div>

      <h4 className="b4-experiment__sub-heading">session_ids_by_variant</h4>
      {Object.keys(sessionIds).length === 0 ? (
        <p className="compare-lab__absent">—</p>
      ) : (
        <table
          className="b4-experiment__table"
          data-testid="b4-experiment-session-ids"
        >
          <thead>
            <tr>
              <th>variant</th>
              <th>session_id</th>
            </tr>
          </thead>
          <tbody>
            {Object.keys(sessionIds)
              .sort()
              .map((tag) => (
                <tr key={tag} data-testid={`b4-experiment-row-${tag}`}>
                  <td>
                    <code>{tag}</code>
                  </td>
                  <td>
                    <code>{sessionIds[tag]}</code>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      )}

      <h4 className="b4-experiment__sub-heading">
        diverged event_ids (policy-only vs agent-visible)
      </h4>
      {diverged.length === 0 ? (
        <p
          className="compare-lab__absent"
          data-testid="b4-experiment-diverged-empty"
        >
          No event diverged between the two PATH_C_WARM variants on this
          compare report.
        </p>
      ) : (
        <ul
          className="b4-experiment__diverged"
          data-testid="b4-experiment-diverged"
        >
          {diverged.map((eid) => (
            <li key={eid}>
              <code>{eid}</code>
            </li>
          ))}
        </ul>
      )}

      {summary.notes ? (
        <p
          className="b4-experiment__notes"
          data-testid="b4-experiment-notes"
        >
          {summary.notes}
        </p>
      ) : null}

      <CollapsibleJson
        value={summary}
        label="Raw agent_memory_experiment_summary JSON"
        testid="b4-experiment-raw-json"
      />
    </section>
  );
}
