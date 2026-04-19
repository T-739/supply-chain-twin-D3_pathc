'use client';

import { useEffect, useMemo, useState } from 'react';

import { BffError, fetchBundleDetail, fetchSessionArtifact } from '@/lib/bff';
import type {
  BundleDetailResponse,
  SessionArtifactResponse,
  SessionEventRecordRaw,
} from '@/lib/types';
import { useBundleContext } from './BundleContext';
import { EventDetail } from './EventDetail';
import { EventList } from './EventList';
import { SessionFocusSelector } from './SessionFocusSelector';
import { SessionSummaryStrip } from './SessionSummaryStrip';

/**
 * Phase 3A Session Runtime walking skeleton.
 *
 * Data flow:
 *   1. global bundle selection lives in BundleContext
 *      (from Overview phase).
 *   2. on bundle change, fetch the shallow detail to learn the
 *      available variant tags + per-session summary.
 *   3. on session focus change, fetch the raw session artifact
 *      and expose its event_records.
 *   4. on event selection, surface the three-layer detail view.
 *
 * Every step is null-safe. The page renders a meaningful frame
 * even when no bundle is selected, the bundle has zero
 * sessions, the session is unloadable, or the artifact has
 * zero event records.
 */
export function SessionRuntimePage() {
  const { selectedBundleId } = useBundleContext();

  const [bundleDetail, setBundleDetail] =
    useState<BundleDetailResponse | null>(null);
  const [bundleDetailError, setBundleDetailError] = useState<string | null>(
    null,
  );

  const [focusedTag, setFocusedTag] = useState<string | null>(null);

  const [artifactResponse, setArtifactResponse] =
    useState<SessionArtifactResponse | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [artifactLoading, setArtifactLoading] = useState<boolean>(false);

  const [selectedEventIndex, setSelectedEventIndex] = useState<number | null>(
    null,
  );

  // ---- fetch bundle detail on bundle change ----
  useEffect(() => {
    let cancelled = false;
    setBundleDetail(null);
    setBundleDetailError(null);
    setFocusedTag(null);
    setArtifactResponse(null);
    setSelectedEventIndex(null);
    if (!selectedBundleId) return;
    fetchBundleDetail(selectedBundleId)
      .then((payload) => {
        if (cancelled) return;
        setBundleDetail(payload);
        // Auto-focus the first variant tag if any — works for
        // both default_3_mode and b4_experiment_triplet; we
        // never look up `path_c_cold` by name.
        const firstTag = payload.metadata.variant_tags[0] ?? null;
        setFocusedTag(firstTag);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setBundleDetailError(
          err instanceof BffError
            ? err.message
            : err instanceof Error
              ? err.message
              : String(err),
        );
      });
    return () => {
      cancelled = true;
    };
  }, [selectedBundleId]);

  // ---- fetch session artifact on focus change ----
  useEffect(() => {
    let cancelled = false;
    setArtifactResponse(null);
    setArtifactError(null);
    setSelectedEventIndex(null);
    if (!selectedBundleId || !focusedTag) {
      setArtifactLoading(false);
      return;
    }
    setArtifactLoading(true);
    fetchSessionArtifact(selectedBundleId, focusedTag)
      .then((payload) => {
        if (cancelled) return;
        setArtifactResponse(payload);
        // Auto-select the first event iff the artifact loaded
        // cleanly and there is at least one event.
        const events = Array.isArray(
          payload.session_artifact_raw?.event_records,
        )
          ? (payload.session_artifact_raw!.event_records as unknown[])
          : [];
        setSelectedEventIndex(events.length > 0 ? 0 : null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setArtifactError(
          err instanceof BffError
            ? err.message
            : err instanceof Error
              ? err.message
              : String(err),
        );
      })
      .finally(() => {
        if (!cancelled) setArtifactLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedBundleId, focusedTag]);

  const focusedSessionSummary = useMemo(() => {
    if (!bundleDetail || !focusedTag) return null;
    return (
      bundleDetail.sessions.find((s) => s.variant_tag === focusedTag) ?? null
    );
  }, [bundleDetail, focusedTag]);

  const events: SessionEventRecordRaw[] = useMemo(() => {
    const raw = artifactResponse?.session_artifact_raw?.event_records;
    return Array.isArray(raw) ? (raw as SessionEventRecordRaw[]) : [];
  }, [artifactResponse]);

  const selectedEvent: SessionEventRecordRaw | null = useMemo(() => {
    if (selectedEventIndex === null) return null;
    if (selectedEventIndex < 0 || selectedEventIndex >= events.length)
      return null;
    return events[selectedEventIndex] ?? null;
  }, [events, selectedEventIndex]);

  // ---- render ----

  return (
    <div
      className="session-runtime-page"
      data-testid="session-runtime-page"
    >
      <header className="session-runtime-page__header">
        <h1>Session Runtime</h1>
        <p className="session-runtime-page__lede">
          A read-only view over serialized session artifacts. The twin
          is not re-run here — every field below is pulled directly
          from the bundle&apos;s <code>session_artifact.json</code> via
          the BFF.
        </p>
        <dl
          className="session-runtime-page__header-meta"
          data-testid="session-runtime-header-meta"
        >
          <div>
            <dt>Selected bundle</dt>
            <dd>
              {selectedBundleId ? (
                <code data-testid="header-bundle-id">{selectedBundleId}</code>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div>
            <dt>Session focus</dt>
            <dd>
              {focusedTag ? (
                <code data-testid="header-focus-tag">{focusedTag}</code>
              ) : (
                '—'
              )}
            </dd>
          </div>
        </dl>
        <SessionFocusSelector
          bundleDetail={bundleDetail}
          focusedTag={focusedTag}
          onFocusChange={setFocusedTag}
        />
      </header>

      {!selectedBundleId && (
        <div
          className="session-runtime-page__notice"
          data-testid="runtime-no-bundle"
        >
          <p>
            No bundle is currently selected. Pick one from the bundle
            selector in the app header to populate this page.
          </p>
        </div>
      )}

      {bundleDetailError && (
        <div
          className="session-runtime-page__error"
          role="alert"
          data-testid="runtime-bundle-error"
        >
          Could not load bundle detail: {bundleDetailError}
        </div>
      )}

      {selectedBundleId &&
        bundleDetail &&
        bundleDetail.metadata.variant_tags.length === 0 && (
          <div
            className="session-runtime-page__notice"
            data-testid="runtime-no-sessions"
          >
            <p>
              This bundle is registered but contains no sessions. Select a
              different bundle to continue.
            </p>
          </div>
        )}

      {focusedTag && (
        <>
          <h2 className="session-runtime-page__section-heading">
            Session summary
          </h2>
          <SessionSummaryStrip
            summary={focusedSessionSummary}
            artifactResponse={artifactResponse}
          />
        </>
      )}

      {focusedTag && (
        <>
          <h2 className="session-runtime-page__section-heading">
            Event stream
          </h2>
          {artifactLoading && (
            <p
              data-testid="artifact-loading"
              role="status"
              aria-live="polite"
            >
              Loading session artifact for <code>{focusedTag}</code>…
            </p>
          )}
          {artifactError && (
            <div
              className="session-runtime-page__error"
              role="alert"
              data-testid="artifact-error"
            >
              Could not load session artifact: {artifactError}
            </div>
          )}
          {artifactResponse &&
            !artifactResponse.session_artifact_loadable && (
              <div
                className="session-runtime-page__notice"
                data-testid="runtime-artifact-unloadable"
              >
                <p>
                  The session artifact for <code>{focusedTag}</code> could
                  not be loaded. This is a valid bundle state — the
                  session is registered but its JSON file is missing or
                  unreadable.
                </p>
              </div>
            )}
          {artifactResponse &&
            artifactResponse.session_artifact_loadable && (
              <EventList
                events={events}
                selectedIndex={selectedEventIndex}
                onSelect={setSelectedEventIndex}
              />
            )}
        </>
      )}

      {focusedTag &&
        artifactResponse?.session_artifact_loadable &&
        events.length > 0 && (
          <>
            <h2 className="session-runtime-page__section-heading">
              Event detail
            </h2>
            <EventDetail
              event={selectedEvent}
              eventIndex={selectedEventIndex}
              totalEvents={events.length}
              onNavigate={(newIndex) => {
                if (newIndex < 0 || newIndex >= events.length) return;
                setSelectedEventIndex(newIndex);
              }}
            />
          </>
        )}
    </div>
  );
}
