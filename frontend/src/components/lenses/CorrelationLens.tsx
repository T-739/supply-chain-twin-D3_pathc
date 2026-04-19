'use client';

import type { CorrelationSummary } from '@/lib/types';
import { CollapsibleJson } from '../CollapsibleJson';

export interface CorrelationLensProps {
  summary: CorrelationSummary | undefined;
}

function sortedPatternIds(
  summary: CorrelationSummary,
): string[] {
  const out = new Set<string>();
  for (const p of Object.keys(summary.overall_pattern_counts ?? {})) {
    out.add(p);
  }
  for (const bag of Object.values(summary.per_session ?? {})) {
    for (const p of Object.keys(bag?.pattern_counts ?? {})) {
      out.add(p);
    }
  }
  return [...out].sort();
}

/**
 * B2 · Correlator lens — renders the `correlation_summary`
 * sibling block verbatim.
 *
 * The correlator is observability-only at session_compare level
 * (see `src/correlator/correlator_schema.py` + §2C boundary).
 * This lens keeps that framing: it shows counts, pattern ids,
 * and per-session breakdowns without labeling any event as
 * "alert", "severe", or similar — the semantics stay exactly
 * what the artifact committed to.
 */
export function CorrelationLens({ summary }: CorrelationLensProps) {
  if (!summary) {
    return (
      <div className="lens lens--absent" data-testid="correlation-lens-absent">
        <header className="lens__header">
          <h3>B2 · Correlator</h3>
          <span className="lens__tag">observability</span>
        </header>
        <p className="compare-lab__absent">
          This compare report does not carry a{' '}
          <code>correlation_summary</code> sibling block. No compared
          session in this bundle was run with{' '}
          <code>CorrelatorConfig.enable_correlator=True</code>, so
          there is no correlation data to surface.
        </p>
      </div>
    );
  }

  const sessions = summary.sessions_with_correlation_data ?? [];
  const perSession = summary.per_session ?? {};
  const overall = summary.overall_pattern_counts ?? {};
  const allEventIds = summary.all_correlated_event_ids ?? [];
  const patternIds = sortedPatternIds(summary);

  return (
    <section className="lens" data-testid="correlation-lens">
      <header className="lens__header">
        <h3>B2 · Correlator</h3>
        <span className="lens__tag">observability</span>
      </header>

      <dl className="lens__facts">
        <div>
          <dt>sessions_with_correlation_data</dt>
          <dd data-testid="correlation-lens-sessions">
            {sessions.length === 0 ? (
              <span className="compare-lab__absent">—</span>
            ) : (
              <ul className="lens__chips">
                {sessions.map((m) => (
                  <li key={m}>
                    <code>{m}</code>
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
      </dl>

      {sessions.length > 0 && (
        <>
          <h4 className="lens__sub-heading">Per-session counts</h4>
          <table
            className="lens__table"
            data-testid="correlation-lens-table"
          >
            <thead>
              <tr>
                <th>mode</th>
                <th>events_with_context</th>
                <th>events_with_signals</th>
                <th>total_signals</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((m) => {
                const row = perSession[m] ?? {};
                return (
                  <tr
                    key={m}
                    data-testid={`correlation-lens-row-${m}`}
                  >
                    <td>
                      <code>{m}</code>
                    </td>
                    <td>{row.events_with_context ?? '—'}</td>
                    <td>{row.events_with_signals ?? '—'}</td>
                    <td>{row.total_signals ?? '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}

      {patternIds.length > 0 && (
        <>
          <h4 className="lens__sub-heading">Pattern counts</h4>
          <table
            className="lens__table"
            data-testid="correlation-lens-pattern-table"
          >
            <thead>
              <tr>
                <th>pattern_id</th>
                <th>overall</th>
                {sessions.map((m) => (
                  <th key={m}>
                    <code>{m}</code>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {patternIds.map((pid) => (
                <tr
                  key={pid}
                  data-testid={`correlation-lens-pattern-row-${pid}`}
                >
                  <td>
                    <code>{pid}</code>
                  </td>
                  <td>{overall[pid] ?? 0}</td>
                  {sessions.map((m) => {
                    const row = perSession[m] ?? {};
                    const bag = row.pattern_counts ?? {};
                    return <td key={m}>{bag[pid] ?? 0}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {allEventIds.length > 0 && (
        <div
          className="lens__event-ids"
          data-testid="correlation-lens-event-ids"
        >
          <h4 className="lens__sub-heading">
            Correlated event ids (union across sessions)
          </h4>
          <ul className="lens__chips">
            {allEventIds.map((eid) => (
              <li key={eid}>
                <code>{eid}</code>
              </li>
            ))}
          </ul>
        </div>
      )}

      <CollapsibleJson
        value={summary}
        label="Raw correlation_summary JSON"
        testid="correlation-lens-raw-json"
      />
    </section>
  );
}
