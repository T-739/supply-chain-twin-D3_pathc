'use client';

import type { SessionEventRecordRaw } from '@/lib/types';
import { CollapsibleJson } from './CollapsibleJson';
import { EventOverlayPanel } from './EventOverlayPanel';
import { EventExtensionsPanel } from './EventExtensionsPanel';

export interface EventDetailProps {
  event: SessionEventRecordRaw | null;
  eventIndex: number | null;
  totalEvents: number;
  onNavigate?: (newIndex: number) => void;
}

/**
 * Three-layer event detail:
 *   Layer 1 — Path B raw        (baseline_event_result verbatim)
 *   Layer 2 — Path C overlay    (structured via EventOverlayPanel)
 *   Layer 3 — Extensions        (structured via EventExtensionsPanel)
 *
 * 3B deepens layers 2 and 3 asymmetrically:
 *   - Layer 2 renders the dual-track contract as two side-by-side
 *     panels so governance truth never visually collapses into
 *     the effective decision.
 *   - Layer 3 shows B1 replan trace / triggers as tables,
 *     B2 correlation_context as window metadata + signals table,
 *     B3 as a session-level explainer (never fabricated
 *     per-event), and B4 as a fixed experiment / default-off /
 *     compare-only label block.
 *
 * Still no compare math, no new KPIs, no interpretive narrative.
 */
export function EventDetail({
  event,
  eventIndex,
  totalEvents,
  onNavigate,
}: EventDetailProps) {
  if (!event || eventIndex === null) {
    return (
      <section
        className="event-detail event-detail--empty"
        data-testid="event-detail-empty"
        aria-label="Event detail"
      >
        <p>Select an event from the list above to see its three-layer detail.</p>
      </section>
    );
  }

  const baseline = event.baseline_event_result ?? null;
  const eventId = baseline?.event_id;

  const canPrev = onNavigate !== undefined && eventIndex > 0;
  const canNext =
    onNavigate !== undefined && eventIndex < Math.max(totalEvents - 1, 0);

  return (
    <section
      className="event-detail"
      data-testid="event-detail"
      aria-label={`Event detail for index ${eventIndex}`}
    >
      <header className="event-detail__header">
        <div className="event-detail__title-row">
          <h3 className="event-detail__title">
            Event {eventIndex + 1} of {totalEvents}
            {eventId ? (
              <>
                {' · '}
                <code>{eventId}</code>
              </>
            ) : null}
          </h3>
          {onNavigate && (
            <div
              className="event-detail__nav"
              data-testid="event-detail-nav"
              role="group"
              aria-label="Event navigation"
            >
              <button
                type="button"
                disabled={!canPrev}
                onClick={() => canPrev && onNavigate(eventIndex - 1)}
                data-testid="event-detail-prev"
                aria-label="Previous event"
              >
                ← Prev
              </button>
              <button
                type="button"
                disabled={!canNext}
                onClick={() => canNext && onNavigate(eventIndex + 1)}
                data-testid="event-detail-next"
                aria-label="Next event"
              >
                Next →
              </button>
            </div>
          )}
        </div>
        <p className="event-detail__subtitle">
          Structural three-layer view. Dual-track truth is rendered
          side-by-side and never collapsed. No compare math is performed
          on this page.
        </p>
      </header>

      {/* ---------- Layer 1: Path B raw ---------- */}
      <div
        className="event-detail__layer"
        data-testid="event-detail-path-b"
      >
        <h4>Path B raw</h4>
        <p className="event-detail__layer-note">
          The deterministic per-event Path B record, surfaced verbatim.
        </p>
        {baseline ? (
          <CollapsibleJson
            value={baseline}
            label="baseline_event_result JSON"
            defaultOpen
            testid="event-detail-path-b-json"
          />
        ) : (
          <p>baseline_event_result is absent on this record.</p>
        )}
      </div>

      {/* ---------- Layer 2: Path C overlay (structured) ---------- */}
      <div
        className="event-detail__layer"
        data-testid="event-detail-path-c"
      >
        <h4>Path C overlay</h4>
        <p className="event-detail__layer-note">
          Adaptive-overlay sibling fields. Governance truth and effective
          decision are rendered as two distinct tracks — they never
          collapse under the dual-track contract.
        </p>
        <EventOverlayPanel event={event} />
      </div>

      {/* ---------- Layer 3: Extensions (structured) ---------- */}
      <div
        className="event-detail__layer"
        data-testid="event-detail-extensions"
      >
        <h4>Extensions</h4>
        <p className="event-detail__layer-note">
          Structural view of event-level overlay extensions. B1 / B2 deepen
          when the serialized event carries their fields; B3 remains a
          session-level provenance concept; B4 remains an experiment
          branch (default-off, compare-only) and is not promoted into a
          normal per-event layer.
        </p>
        <EventExtensionsPanel event={event} />
      </div>
    </section>
  );
}
