'use client';

import { useEffect, useState } from 'react';

import { fetchBundleDetail, BffError } from '@/lib/bff';
import { useBundleContext } from './BundleContext';
import type { BundleDetailResponse } from '@/lib/types';

/**
 * Summary card for the currently selected bundle. Consumes
 * `/bundles/{bundle_id}` via the BFF adapter only.
 *
 * Answers:
 *   - what variants this bundle carries (variant_tags)
 *   - whether compare / thesis are present
 *   - every warning on the bundle (metadata + load-time)
 *   - per-session shallow summary
 *
 * Null-safety:
 *   - no selection → renders a prompt, does not crash
 *   - 404 / network failure → renders the error in place
 *   - absence of `path_c_cold` on B4 triplet → handled
 *     implicitly: we iterate variant_tags, never index by name.
 */
export function BundleSummaryCard() {
  const { selectedBundleId } = useBundleContext();

  const [detail, setDetail] = useState<BundleDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setDetail(null);
    if (!selectedBundleId) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    fetchBundleDetail(selectedBundleId)
      .then((payload) => {
        if (!cancelled) setDetail(payload);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof BffError) {
          setError(err.message);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedBundleId]);

  if (!selectedBundleId) {
    return (
      <section
        className="bundle-summary bundle-summary--empty"
        data-testid="bundle-summary-empty"
        aria-label="Selected bundle"
      >
        <h2>Selected bundle</h2>
        <p>No bundle is selected. Pick one from the catalog above.</p>
      </section>
    );
  }

  if (isLoading) {
    return (
      <section
        className="bundle-summary"
        data-testid="bundle-summary-loading"
        aria-label="Selected bundle"
      >
        <h2>Selected bundle</h2>
        <p>Loading bundle detail…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section
        className="bundle-summary bundle-summary--error"
        data-testid="bundle-summary-error"
        aria-label="Selected bundle"
      >
        <h2>Selected bundle</h2>
        <p role="alert">Could not load bundle {selectedBundleId}: {error}</p>
      </section>
    );
  }

  if (!detail) {
    return null;
  }

  const { metadata, sessions, load_warnings } = detail;
  const allWarnings = [...metadata.warnings, ...load_warnings];

  return (
    <section
      className="bundle-summary"
      data-testid="bundle-summary"
      aria-label="Selected bundle"
    >
      <header className="bundle-summary__header">
        <h2>
          <code>{metadata.bundle_id}</code>
        </h2>
        <dl className="bundle-summary__meta">
          <div>
            <dt>Variant set</dt>
            <dd data-testid="bundle-summary-variant-set">
              {metadata.variant_set}
            </dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>
              {metadata.source.kind} · <code>{metadata.source.origin}</code>
            </dd>
          </div>
          <div>
            <dt>Produced by</dt>
            <dd>
              bundler <code>{metadata.produced_by}</code>
            </dd>
          </div>
          <div>
            <dt>Contract</dt>
            <dd>v{metadata.bundle_schema_version}</dd>
          </div>
        </dl>
      </header>

      <div className="bundle-summary__section">
        <h3>Variant tags</h3>
        <ul
          className="bundle-summary__tags"
          data-testid="bundle-summary-tags"
        >
          {metadata.variant_tags.map((tag) => (
            <li key={tag}>
              <code>{tag}</code>
            </li>
          ))}
        </ul>
      </div>

      <div className="bundle-summary__section">
        <h3>Reports</h3>
        <p data-testid="bundle-summary-reports">
          Compare report:{' '}
          <strong>{metadata.has_compare_report ? 'present' : 'absent'}</strong>
          {' · '}
          Thesis report:{' '}
          <strong>{metadata.has_thesis_report ? 'present' : 'absent'}</strong>
        </p>
        {metadata.has_compare_report && !detail.compare_report_raw && (
          <p className="bundle-summary__inconsistency" role="alert">
            Metadata claims a compare report but the file could not be read.
          </p>
        )}
        {metadata.has_thesis_report && !detail.thesis_report_raw_markdown && (
          <p className="bundle-summary__inconsistency" role="alert">
            Metadata claims a thesis report but the file could not be read.
          </p>
        )}
      </div>

      <div className="bundle-summary__section">
        <h3>Sessions in this bundle</h3>
        <table
          className="bundle-summary__sessions"
          data-testid="bundle-summary-sessions"
        >
          <thead>
            <tr>
              <th>Tag</th>
              <th>Mode</th>
              <th>Session id</th>
              <th>Events</th>
              <th>memory.jsonl</th>
              <th>loadable</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.variant_tag} data-testid={`session-row-${s.variant_tag}`}>
                <td>
                  <code>{s.variant_tag}</code>
                </td>
                <td>{s.mode ?? '—'}</td>
                <td>{s.session_id ? <code>{s.session_id}</code> : '—'}</td>
                <td>{s.events_observed ?? '—'}</td>
                <td>{s.memory_jsonl_present ? 'present' : 'absent'}</td>
                <td>{s.session_artifact_loadable ? 'yes' : 'no'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bundle-summary__section">
        <h3>Warnings</h3>
        {allWarnings.length === 0 ? (
          <p data-testid="bundle-summary-no-warnings">No warnings.</p>
        ) : (
          <ul
            className="bundle-summary__warnings"
            data-testid="bundle-summary-warnings"
          >
            {allWarnings.map((w, i) => (
              <li key={`${i}-${w}`}>{w}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
