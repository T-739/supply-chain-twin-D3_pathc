'use client';

import type { CumulativeMemorySummary } from '@/lib/types';
import { CollapsibleJson } from '../CollapsibleJson';

export interface CumulativeMemoryLensProps {
  summary: CumulativeMemorySummary | undefined;
}

/**
 * B3 · Cumulative memory lens.
 *
 * Deliberately session / compare-level. B3 has no per-event
 * overlay and this lens must not fabricate one — every cell
 * below is an already-computed compare-report summary field
 * (`per_session.cumulative_row_count`, `.self_session_row_count`,
 * `.prior_session_refs`, …). The framing label on the header
 * makes that explicit so a reader can't mistake it for an
 * event-level lens.
 */
export function CumulativeMemoryLens({
  summary,
}: CumulativeMemoryLensProps) {
  if (!summary) {
    return (
      <div
        className="lens lens--absent"
        data-testid="cumulative-lens-absent"
      >
        <header className="lens__header">
          <h3>B3 · Cumulative memory</h3>
          <span className="lens__tag">session / compare-level</span>
        </header>
        <p className="compare-lab__absent">
          This compare report does not carry a{' '}
          <code>cumulative_memory_summary</code> sibling block. No
          compared session in this bundle was run with prior-session
          memory attached.
        </p>
      </div>
    );
  }

  const sessions = summary.sessions_with_cumulative_memory ?? [];
  const perSession = summary.per_session ?? {};
  const priorRefs = summary.all_prior_session_refs ?? [];
  const overallRows = summary.overall_rows_by_prior_session ?? {};

  return (
    <section className="lens" data-testid="cumulative-lens">
      <header className="lens__header">
        <h3>B3 · Cumulative memory</h3>
        <span
          className="lens__tag"
          data-testid="cumulative-lens-scope-label"
        >
          session / compare-level
        </span>
      </header>
      <p className="lens__framing">
        Cumulative (cross-session) prior memory is modelled as
        session-level provenance. This lens surfaces the already-
        serialized compare summary — it does not and cannot
        attribute cumulative memory to individual events.
      </p>

      <dl className="lens__facts">
        <div>
          <dt>sessions_with_cumulative_memory</dt>
          <dd data-testid="cumulative-lens-sessions">
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
          <h4 className="lens__sub-heading">Per-session row counts</h4>
          <table
            className="lens__table"
            data-testid="cumulative-lens-table"
          >
            <thead>
              <tr>
                <th>mode</th>
                <th>current_session_id</th>
                <th>self_session_row_count</th>
                <th>cumulative_row_count</th>
                <th>prior_session_refs</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((m) => {
                const row = perSession[m] ?? {};
                const refs = row.prior_session_refs ?? [];
                return (
                  <tr
                    key={m}
                    data-testid={`cumulative-lens-row-${m}`}
                  >
                    <td>
                      <code>{m}</code>
                    </td>
                    <td>
                      {row.current_session_id ? (
                        <code>{row.current_session_id}</code>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>{row.self_session_row_count ?? '—'}</td>
                    <td>{row.cumulative_row_count ?? '—'}</td>
                    <td>
                      {refs.length === 0 ? (
                        <span className="compare-lab__absent">—</span>
                      ) : (
                        <ul className="lens__chips">
                          {refs.map((r) => (
                            <li key={r}>
                              <code>{r}</code>
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}

      {priorRefs.length > 0 && (
        <>
          <h4 className="lens__sub-heading">
            Prior session refs (union across compared sessions)
          </h4>
          <table
            className="lens__table"
            data-testid="cumulative-lens-prior-table"
          >
            <thead>
              <tr>
                <th>prior_session_id</th>
                <th>total rows contributed</th>
              </tr>
            </thead>
            <tbody>
              {priorRefs.map((ref) => (
                <tr
                  key={ref}
                  data-testid={`cumulative-lens-prior-row-${ref}`}
                >
                  <td>
                    <code>{ref}</code>
                  </td>
                  <td>{overallRows[ref] ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <CollapsibleJson
        value={summary}
        label="Raw cumulative_memory_summary JSON"
        testid="cumulative-lens-raw-json"
      />
    </section>
  );
}
