'use client';

import type { SessionEventRecordRaw } from '@/lib/types';

export interface EventListProps {
  events: SessionEventRecordRaw[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}

function pickEventId(rec: SessionEventRecordRaw): string {
  const id = rec?.baseline_event_result?.event_id;
  return typeof id === 'string' && id.length > 0 ? id : '—';
}

function pickEventType(rec: SessionEventRecordRaw): string {
  const t = rec?.baseline_event_result?.event_type;
  return typeof t === 'string' && t.length > 0 ? t : '—';
}

function pickRoute(rec: SessionEventRecordRaw): string {
  const r = rec?.effective_decision?.final_route;
  return typeof r === 'string' && r.length > 0 ? r : '—';
}

function pickStatus(rec: SessionEventRecordRaw): string {
  const s = rec?.effective_decision?.execution_status;
  return typeof s === 'string' && s.length > 0 ? s : '—';
}

/**
 * Shallow event list. Does NOT interpret any field — every cell
 * is pulled from a canonical path on the already-serialized
 * event record. Falls back to "—" for any missing value so the
 * list never crashes on a sparse artifact.
 */
export function EventList({
  events,
  selectedIndex,
  onSelect,
}: EventListProps) {
  if (events.length === 0) {
    return (
      <div
        className="event-list event-list--empty"
        data-testid="event-list-empty"
      >
        <p>No events are present on this session artifact.</p>
        <p className="event-list__hint">
          An empty event stream is a valid state — the session
          ran but produced zero event records.
        </p>
      </div>
    );
  }

  return (
    <table className="event-list" data-testid="event-list">
      <thead>
        <tr>
          <th>#</th>
          <th>event_id</th>
          <th>event_type</th>
          <th>route</th>
          <th>execution_status</th>
          <th>Select</th>
        </tr>
      </thead>
      <tbody>
        {events.map((rec, idx) => {
          const isSelected = idx === selectedIndex;
          return (
            <tr
              key={idx}
              className={
                'event-list__row' +
                (isSelected ? ' event-list__row--selected' : '')
              }
              data-testid={`event-row-${idx}`}
              aria-selected={isSelected}
            >
              <td>{idx}</td>
              <td>
                <code>{pickEventId(rec)}</code>
              </td>
              <td>{pickEventType(rec)}</td>
              <td>{pickRoute(rec)}</td>
              <td>{pickStatus(rec)}</td>
              <td>
                <button
                  type="button"
                  onClick={() => onSelect(idx)}
                  disabled={isSelected}
                  data-testid={`select-event-${idx}`}
                >
                  {isSelected ? 'Selected' : 'Select'}
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
