'use client';

import { useEffect, useState } from 'react';

import { BffError, fetchBundleDetail } from '@/lib/bff';
import type { BundleDetailResponse, CompareReportRaw } from '@/lib/types';
import { useBundleContext } from './BundleContext';
import { AgentMemoryExperimentLens } from './lenses/AgentMemoryExperimentLens';
import { CorrelationLens } from './lenses/CorrelationLens';
import { CumulativeMemoryLens } from './lenses/CumulativeMemoryLens';
import { ReplanLens } from './lenses/ReplanLens';

/**
 * Phase 5A Advanced Lenses — conditional / observability-only
 * sibling blocks from `compare_report.json`.
 *
 * These lenses are explicitly NOT the main compare story. The
 * main compare KPI matrix / deltas / diverged events / thesis
 * live in the Compare Lab page. The lenses below supplement
 * that with structural views of the additive sibling blocks
 * (`replan_trace_summary`, `correlation_summary`,
 * `cumulative_memory_summary`, `agent_memory_experiment_summary`)
 * the compare report already commits to, rendered as-is.
 *
 * Null-safety: every lens tolerates a missing sibling block,
 * a missing sub-field, and a sparse compare report. The page
 * as a whole remains non-crashing when no compare report is
 * available at all.
 */
export function AdvancedLensesPage() {
  const { selectedBundleId } = useBundleContext();

  const [detail, setDetail] = useState<BundleDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setError(null);
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
        setError(
          err instanceof BffError
            ? err.message
            : err instanceof Error
              ? err.message
              : String(err),
        );
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedBundleId]);

  return (
    <div className="advanced-lenses-page" data-testid="advanced-lenses-page">
      <header className="advanced-lenses-page__header">
        <h1>Advanced Lenses</h1>
        <p className="advanced-lenses-page__lede">
          Supplementary observability views over the conditional sibling
          blocks that <code>session_compare.build_compare_report</code>{' '}
          can emit. Each lens is a structural window on an existing
          compare artifact — <strong>not</strong> a new runtime
          computation, and <strong>not</strong> a substitute for the
          Compare Lab&apos;s main KPI / delta / thesis story.
        </p>
        <dl className="advanced-lenses-page__meta">
          <div>
            <dt>Selected bundle</dt>
            <dd>
              {selectedBundleId ? (
                <code data-testid="lenses-bundle-id">
                  {selectedBundleId}
                </code>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div>
            <dt>Variant set</dt>
            <dd data-testid="lenses-variant-set">
              {detail?.metadata.variant_set ?? '—'}
            </dd>
          </div>
          <div>
            <dt>Compare report</dt>
            <dd data-testid="lenses-has-compare">
              {detail
                ? detail.metadata.has_compare_report
                  ? 'present (metadata)'
                  : 'absent (metadata)'
                : '—'}
            </dd>
          </div>
        </dl>
      </header>

      {!selectedBundleId && (
        <div
          className="advanced-lenses-page__notice"
          data-testid="lenses-no-bundle"
        >
          <p>
            No bundle is currently selected. Pick one from the bundle
            selector in the app header to populate the lenses.
          </p>
        </div>
      )}

      {isLoading && (
        <p
          data-testid="lenses-loading"
          role="status"
          aria-live="polite"
        >
          Loading bundle detail…
        </p>
      )}

      {error && (
        <div
          className="advanced-lenses-page__error"
          role="alert"
          data-testid="lenses-error"
        >
          Could not load bundle detail: {error}
        </div>
      )}

      {detail && <AdvancedLensesBody detail={detail} />}
    </div>
  );
}

function AdvancedLensesBody({ detail }: { detail: BundleDetailResponse }) {
  const compare: CompareReportRaw | null = detail.compare_report_raw ?? null;
  const metaClaimsCompare = detail.metadata.has_compare_report;
  const allWarnings = [
    ...detail.metadata.warnings,
    ...detail.load_warnings,
  ];

  if (!metaClaimsCompare) {
    return (
      <>
        {allWarnings.length > 0 && (
          <section
            className="advanced-lenses-page__warnings"
            data-testid="lenses-warnings"
          >
            <h2>Warnings</h2>
            <ul>
              {allWarnings.map((w, i) => (
                <li key={`${i}-${w}`}>{w}</li>
              ))}
            </ul>
          </section>
        )}
        <div
          className="advanced-lenses-page__notice"
          data-testid="lenses-compare-absent"
        >
          <p>
            This bundle does not carry a <code>compare_report.json</code>.
            Advanced Lenses renders conditional blocks from the compare
            artifact only — without a compare report there is nothing to
            surface.
          </p>
        </div>
      </>
    );
  }

  if (compare === null) {
    return (
      <>
        {allWarnings.length > 0 && (
          <section
            className="advanced-lenses-page__warnings"
            data-testid="lenses-warnings"
          >
            <h2>Warnings</h2>
            <ul>
              {allWarnings.map((w, i) => (
                <li key={`${i}-${w}`}>{w}</li>
              ))}
            </ul>
          </section>
        )}
        <div
          className="advanced-lenses-page__notice"
          data-testid="lenses-compare-unreadable"
        >
          <p>
            Bundle metadata claims a compare report, but the backend could
            not deliver <code>compare_report_raw</code>. No lens blocks
            can be rendered until the compare artifact is loadable.
          </p>
        </div>
      </>
    );
  }

  const hasAnyBlock =
    !!compare.replan_trace_summary ||
    !!compare.correlation_summary ||
    !!compare.cumulative_memory_summary ||
    !!compare.agent_memory_experiment_summary;

  return (
    <>
      {allWarnings.length > 0 && (
        <section
          className="advanced-lenses-page__warnings"
          data-testid="lenses-warnings"
        >
          <h2>Warnings</h2>
          <ul>
            {allWarnings.map((w, i) => (
              <li key={`${i}-${w}`}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      {!hasAnyBlock && (
        <div
          className="advanced-lenses-page__notice"
          data-testid="lenses-no-sibling-blocks"
        >
          <p>
            This compare report carries no conditional sibling blocks
            (no <code>replan_trace_summary</code>,{' '}
            <code>correlation_summary</code>,{' '}
            <code>cumulative_memory_summary</code>, or{' '}
            <code>agent_memory_experiment_summary</code>). The main
            compare surface in the Compare Lab still renders the KPI
            matrix, deltas, diverged events, and thesis.
          </p>
        </div>
      )}

      <ReplanLens summary={compare.replan_trace_summary} />
      <CorrelationLens summary={compare.correlation_summary} />
      <CumulativeMemoryLens summary={compare.cumulative_memory_summary} />
      <AgentMemoryExperimentLens
        summary={compare.agent_memory_experiment_summary}
      />
    </>
  );
}
