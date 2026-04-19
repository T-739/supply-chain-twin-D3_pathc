'use client';

import type { DivergedEventEntry } from '@/lib/types';
import { CollapsibleJson } from '../CollapsibleJson';

export interface DivergedEventsViewProps {
  divergedEvents: DivergedEventEntry[] | undefined;
  sessionsCompared: string[];
}

function PerModeTriplet({
  label,
  bag,
  modes,
}: {
  label: string;
  bag: Record<string, string | null> | undefined;
  modes: string[];
}) {
  if (!bag) return null;
  return (
    <div className="diverged-events__per-mode">
      <span className="diverged-events__per-mode-label">{label}</span>
      <ul className="diverged-events__per-mode-list">
        {modes.map((m) => {
          const v = bag[m];
          return (
            <li key={m}>
              <code>{m}</code>:{' '}
              {v === null || v === undefined ? (
                <span className="compare-lab__absent">—</span>
              ) : (
                <code>{v}</code>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * Canonical diverged-events viewer.
 *
 * Renders the list as-is: each entry shows its index, event_id,
 * and the per-mode `routes`, `actions`, `statuses` triplet that
 * session_compare emits. Adjustment provenance (rule_id /
 * adjustment_type / pre→post) is shown structurally when
 * `adjustment_ref` is present. Raw JSON is available per entry
 * for transparency.
 *
 * This view does NOT attempt to explain "why" a divergence
 * occurred. Causality lives in the adaptive adjustment record
 * itself; B5 surfaces it, it does not re-narrate it.
 */
export function DivergedEventsView({
  divergedEvents,
  sessionsCompared,
}: DivergedEventsViewProps) {
  const events = Array.isArray(divergedEvents) ? divergedEvents : [];
  if (events.length === 0) {
    return (
      <p
        className="compare-lab__absent"
        data-testid="diverged-events-empty"
      >
        No diverged events were recorded on this compare report.
      </p>
    );
  }

  return (
    <ul className="diverged-events" data-testid="diverged-events">
      {events.map((e, i) => {
        const idx = typeof e.event_index === 'number' ? e.event_index : i;
        const eid = typeof e.event_id === 'string' ? e.event_id : null;
        const adj = e.adjustment_ref ?? null;
        const ruleId =
          (adj?.rule_id as string | undefined) ?? null;
        const adjType =
          (adj?.adjustment_type as string | undefined) ?? null;
        const pre =
          (adj?.pre_adjustment_risk as string | undefined) ?? null;
        const post =
          (adj?.post_adjustment_risk as string | undefined) ?? null;
        return (
          <li
            key={i}
            className="diverged-events__item"
            data-testid={`diverged-events-item-${i}`}
          >
            <header className="diverged-events__item-header">
              <span>
                <strong>#{idx}</strong>
                {eid ? (
                  <>
                    {' '}
                    · <code>{eid}</code>
                  </>
                ) : null}
              </span>
            </header>

            <PerModeTriplet
              label="final_route"
              bag={e.routes}
              modes={sessionsCompared}
            />
            <PerModeTriplet
              label="action_taken"
              bag={e.actions}
              modes={sessionsCompared}
            />
            <PerModeTriplet
              label="execution_status"
              bag={e.statuses}
              modes={sessionsCompared}
            />

            {adj !== null && (
              <div
                className="diverged-events__adjustment"
                data-testid={`diverged-events-adjustment-${i}`}
              >
                <span className="diverged-events__per-mode-label">
                  adjustment_ref
                </span>
                <dl className="diverged-events__adjustment-grid">
                  <div>
                    <dt>rule_id</dt>
                    <dd>
                      <code>{ruleId ?? '—'}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>adjustment_type</dt>
                    <dd>
                      <code>{adjType ?? '—'}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>pre → post risk</dt>
                    <dd>
                      <code>{pre ?? '—'}</code>
                      {' → '}
                      <code>{post ?? '—'}</code>
                    </dd>
                  </div>
                </dl>
                <CollapsibleJson
                  value={adj}
                  label="Full adjustment_ref JSON"
                  testid={`diverged-events-adjustment-json-${i}`}
                />
              </div>
            )}

            <CollapsibleJson
              value={e}
              label="Raw diverged event entry JSON"
              testid={`diverged-events-raw-${i}`}
            />
          </li>
        );
      })}
    </ul>
  );
}
