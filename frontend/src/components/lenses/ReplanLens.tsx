'use client';

import type { ReplanTraceSummary } from '@/lib/types';
import { CollapsibleJson } from '../CollapsibleJson';

export interface ReplanLensProps {
  summary: ReplanTraceSummary | undefined;
}

function sortedTriggerTypes(
  triggerTypeCounts: Record<string, Record<string, number>> | undefined,
): string[] {
  const seen = new Set<string>();
  if (triggerTypeCounts) {
    for (const modeBag of Object.values(triggerTypeCounts)) {
      for (const t of Object.keys(modeBag)) seen.add(t);
    }
  }
  return [...seen].sort();
}

/**
 * B1 · Replan lens — renders the `replan_trace_summary` sibling
 * block exactly as `session_compare._build_replan_trace_summary`
 * committed to it.
 *
 * Structural only: counts, trigger-type tallies, and the
 * `replan_kpis_overall` bundle already present on `by_mode[*]`
 * are surfaced as-is. No new success judgment is made here —
 * in particular, we do not re-coerce `replan_recovery_rate` to
 * "good" or "bad".
 *
 * Honest absent state: when the sibling block is missing, the
 * artifact simply did not run any session with an enabled
 * `ReplanConfig`. B5 surfaces that directly rather than
 * fabricating zeros.
 */
export function ReplanLens({ summary }: ReplanLensProps) {
  if (!summary) {
    return (
      <div className="lens lens--absent" data-testid="replan-lens-absent">
        <header className="lens__header">
          <h3>B1 · Replan</h3>
          <span className="lens__tag">observability</span>
        </header>
        <p className="compare-lab__absent">
          This compare report does not carry a{' '}
          <code>replan_trace_summary</code> sibling block. No compared
          session in this bundle was run with{' '}
          <code>ReplanConfig.enable_replan=True</code>, so there is no
          replan data to surface.
        </p>
      </div>
    );
  }

  const sessionsWithReplan = summary.sessions_with_replan ?? [];
  const totalEvents =
    typeof summary.total_replan_events === 'number'
      ? summary.total_replan_events
      : null;
  const triggerTypeCounts = summary.trigger_type_counts ?? {};
  const recoveredEventsCount = summary.recovered_events_count ?? {};
  const byMode = summary.by_mode ?? {};
  const triggerTypes = sortedTriggerTypes(triggerTypeCounts);

  return (
    <section className="lens" data-testid="replan-lens">
      <header className="lens__header">
        <h3>B1 · Replan</h3>
        <span className="lens__tag">observability</span>
      </header>

      <dl className="lens__facts">
        <div>
          <dt>sessions_with_replan</dt>
          <dd data-testid="replan-lens-sessions">
            {sessionsWithReplan.length === 0 ? (
              <span className="compare-lab__absent">—</span>
            ) : (
              <ul className="lens__chips">
                {sessionsWithReplan.map((m) => (
                  <li key={m}>
                    <code>{m}</code>
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
        <div>
          <dt>total_replan_events</dt>
          <dd data-testid="replan-lens-total">
            {totalEvents === null ? (
              <span className="compare-lab__absent">—</span>
            ) : (
              totalEvents
            )}
          </dd>
        </div>
      </dl>

      {sessionsWithReplan.length > 0 && (
        <>
          <h4 className="lens__sub-heading">Per-mode</h4>
          <table className="lens__table" data-testid="replan-lens-table">
            <thead>
              <tr>
                <th>mode</th>
                <th>events_with_trace</th>
                <th>recovered_events</th>
                <th>replan_trigger_rate</th>
                <th>replan_recovery_rate</th>
              </tr>
            </thead>
            <tbody>
              {sessionsWithReplan.map((m) => {
                const row = byMode[m] ?? {};
                const kpis = (row.replan_kpis_overall ?? {}) as Record<
                  string,
                  unknown
                >;
                const trigRate = kpis['replan_trigger_rate'];
                const recRate = kpis['replan_recovery_rate'];
                return (
                  <tr key={m} data-testid={`replan-lens-row-${m}`}>
                    <td>
                      <code>{m}</code>
                    </td>
                    <td>{row.events_with_trace ?? '—'}</td>
                    <td>
                      {row.recovered_events ??
                        recoveredEventsCount[m] ??
                        '—'}
                    </td>
                    <td>
                      {trigRate === null ||
                      trigRate === undefined
                        ? 'null'
                        : typeof trigRate === 'number'
                          ? trigRate.toFixed(4)
                          : String(trigRate)}
                    </td>
                    <td>
                      {recRate === null || recRate === undefined
                        ? 'null'
                        : typeof recRate === 'number'
                          ? recRate.toFixed(4)
                          : String(recRate)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {triggerTypes.length > 0 && (
            <>
              <h4 className="lens__sub-heading">
                Trigger-type counts (attempt-0 fired trigger)
              </h4>
              <table
                className="lens__table"
                data-testid="replan-lens-trigger-table"
              >
                <thead>
                  <tr>
                    <th>mode</th>
                    {triggerTypes.map((t) => (
                      <th key={t}>
                        <code>{t}</code>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sessionsWithReplan.map((m) => {
                    const bag = triggerTypeCounts[m] ?? {};
                    return (
                      <tr
                        key={m}
                        data-testid={`replan-lens-trigger-row-${m}`}
                      >
                        <td>
                          <code>{m}</code>
                        </td>
                        {triggerTypes.map((t) => (
                          <td key={t}>{bag[t] ?? 0}</td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </>
      )}

      <CollapsibleJson
        value={summary}
        label="Raw replan_trace_summary JSON"
        testid="replan-lens-raw-json"
      />
    </section>
  );
}
