'use client';

import { useEffect, useState } from 'react';

import { BffError, fetchBundleDetail } from '@/lib/bff';
import type { BundleDetailResponse, CompareReportRaw } from '@/lib/types';
import { useBundleContext } from './BundleContext';
import { CollapsibleJson } from './CollapsibleJson';
import { B4ExperimentBlock } from './compare/B4ExperimentBlock';
import { DeltasView } from './compare/DeltasView';
import { DivergedEventsView } from './compare/DivergedEventsView';
import { KpiMatrixView } from './compare/KpiMatrixView';
import { ThesisSection } from './compare/ThesisSection';

/**
 * Phase 4A Compare Lab — canonical viewer over
 * `compare_report.json` + `thesis_report.md`.
 *
 * The frontend does NOT recompute deltas, re-derive KPI math,
 * or paraphrase thesis meaning. Every section is a window onto
 * what the artifact already committed to, rendered structurally
 * so a reader can verify the compare without downloading the
 * raw JSON — raw JSON remains available as a collapsible
 * fallback for full transparency.
 */
export function CompareLabPage() {
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
    <div className="compare-lab-page" data-testid="compare-lab-page">
      <header className="compare-lab-page__header">
        <h1>Compare Lab</h1>
        <p className="compare-lab-page__lede">
          Read-only canonical viewer over{' '}
          <code>compare_report.json</code> and{' '}
          <code>thesis_report.md</code>. Deltas, KPI cells, and the
          claim-support verdict are rendered exactly as the compare
          artifact committed to them — this page does not recompute
          them.
        </p>
        <dl className="compare-lab-page__header-meta">
          <div>
            <dt>Selected bundle</dt>
            <dd>
              {selectedBundleId ? (
                <code data-testid="compare-bundle-id">
                  {selectedBundleId}
                </code>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div>
            <dt>Variant set</dt>
            <dd data-testid="compare-variant-set">
              {detail?.metadata.variant_set ?? '—'}
            </dd>
          </div>
          <div>
            <dt>Compare report</dt>
            <dd data-testid="compare-has-compare">
              {detail
                ? detail.metadata.has_compare_report
                  ? 'present (metadata)'
                  : 'absent (metadata)'
                : '—'}
            </dd>
          </div>
          <div>
            <dt>Thesis report</dt>
            <dd data-testid="compare-has-thesis">
              {detail
                ? detail.metadata.has_thesis_report
                  ? 'present (metadata)'
                  : 'absent (metadata)'
                : '—'}
            </dd>
          </div>
        </dl>
      </header>

      {!selectedBundleId && (
        <div
          className="compare-lab-page__notice"
          data-testid="compare-no-bundle"
        >
          <p>
            No bundle is currently selected. Pick one from the bundle
            selector in the app header to populate Compare Lab.
          </p>
        </div>
      )}

      {isLoading && (
        <p
          data-testid="compare-loading"
          role="status"
          aria-live="polite"
        >
          Loading bundle detail…
        </p>
      )}

      {error && (
        <div
          className="compare-lab-page__error"
          role="alert"
          data-testid="compare-error"
        >
          Could not load bundle detail: {error}
        </div>
      )}

      {detail && (
        <CompareLabBody detail={detail} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Body — split out so the empty / loading / error frames stay compact
// ---------------------------------------------------------------------------

function CompareLabBody({ detail }: { detail: BundleDetailResponse }) {
  const compare: CompareReportRaw | null = detail.compare_report_raw ?? null;
  const metaClaimsCompare = detail.metadata.has_compare_report;
  const allWarnings = [
    ...detail.metadata.warnings,
    ...detail.load_warnings,
  ];

  return (
    <>
      {/* Warnings block — one line per metadata/load warning */}
      {allWarnings.length > 0 && (
        <section
          className="compare-lab-page__warnings"
          data-testid="compare-warnings"
          aria-label="Bundle warnings"
        >
          <h2>Warnings</h2>
          <ul>
            {allWarnings.map((w, i) => (
              <li key={`${i}-${w}`}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Shallow bundle summary */}
      <section
        className="compare-lab-page__summary"
        data-testid="compare-summary"
        aria-label="Bundle compare summary"
      >
        <h2>Bundle compare summary</h2>
        <div className="compare-lab-page__summary-grid">
          <div>
            <dt>variant_tags</dt>
            <dd data-testid="compare-variant-tags">
              <ul className="compare-lab-page__tags">
                {detail.metadata.variant_tags.map((t) => (
                  <li key={t}>
                    <code>{t}</code>
                  </li>
                ))}
              </ul>
            </dd>
          </div>
          <div>
            <dt>variant_set</dt>
            <dd>
              <code>{detail.metadata.variant_set}</code>
            </dd>
          </div>
          <div>
            <dt>sessions_compared (from compare_report)</dt>
            <dd data-testid="compare-sessions-compared">
              {compare?.sessions_compared ? (
                <ul className="compare-lab-page__tags">
                  {compare.sessions_compared.map((t) => (
                    <li key={t}>
                      <code>{t}</code>
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="compare-lab__absent">—</span>
              )}
            </dd>
          </div>
          <div>
            <dt>baseline_mode</dt>
            <dd data-testid="compare-baseline-mode">
              {compare?.baseline_mode ? (
                <code>{compare.baseline_mode}</code>
              ) : (
                <span className="compare-lab__absent">—</span>
              )}
            </dd>
          </div>
          <div>
            <dt>schema_version</dt>
            <dd data-testid="compare-schema-version">
              {compare?.schema_version ? (
                <code>v{compare.schema_version}</code>
              ) : (
                <span className="compare-lab__absent">—</span>
              )}
            </dd>
          </div>
        </div>
      </section>

      {/* Compare-absent state */}
      {metaClaimsCompare && compare === null && (
        <section
          className="compare-lab-page__notice"
          data-testid="compare-raw-unreadable"
        >
          <p>
            The bundle metadata claims a compare report, but the
            backend could not deliver <code>compare_report_raw</code>
            at load time (see Warnings above). The thesis section
            below may still render if <code>thesis_report.md</code>
            was loadable.
          </p>
        </section>
      )}
      {!metaClaimsCompare && (
        <section
          className="compare-lab-page__notice"
          data-testid="compare-absent"
        >
          <p>
            This bundle does not carry a <code>compare_report.json</code>.
            Compare surfaces below are omitted; the thesis section will
            render whatever thesis_report.md is present (if any).
          </p>
        </section>
      )}

      {compare && (
        <>
          {/* KPI matrix */}
          <section className="compare-lab-page__section">
            <h2>KPI matrix</h2>
            <p className="compare-lab-page__section-note">
              Canonical <code>kpi_matrix</code> block — one table per
              segment. Values are rendered as-is; empty segments render
              an honest "no data" notice rather than a zeroed row set.
            </p>
            <KpiMatrixView
              kpiMatrix={compare.kpi_matrix}
              sessionsCompared={compare.sessions_compared ?? []}
            />
          </section>

          {/* Deltas */}
          <section className="compare-lab-page__section">
            <h2>Deltas</h2>
            <p className="compare-lab-page__section-note">
              Canonical <code>deltas</code> block — one table per
              non-baseline mode. Null deltas render literally as{' '}
              <code>null</code>; they are not coerced to zero and not
              recolored as good or bad.
            </p>
            <DeltasView deltas={compare.deltas} />
          </section>

          {/* Diverged events */}
          <section className="compare-lab-page__section">
            <h2>Diverged events</h2>
            <p className="compare-lab-page__section-note">
              Canonical <code>diverged_events</code> list — per-mode
              route / action / status triplet plus structured adjustment
              reference when present.
            </p>
            <DivergedEventsView
              divergedEvents={compare.diverged_events}
              sessionsCompared={compare.sessions_compared ?? []}
            />
          </section>

          {/* Thesis */}
          <section className="compare-lab-page__section">
            <h2>Thesis</h2>
            <ThesisSection
              claimSupport={compare.thesis_claim_support}
              thesisMarkdown={detail.thesis_report_raw_markdown}
              hasThesisReport={detail.metadata.has_thesis_report}
            />
          </section>

          {/* B4 experiment block — shown only when the sibling block
              is emitted on the compare artifact. Always rendered
              inside its own isolated panel below the mainline
              compare. */}
          <section className="compare-lab-page__section">
            <h2>B4 agent-visible memory experiment (compare-only)</h2>
            <B4ExperimentBlock
              summary={compare.agent_memory_experiment_summary}
            />
          </section>

          {/* Raw compare JSON fallback */}
          <section className="compare-lab-page__section">
            <h2>Raw compare report</h2>
            <CollapsibleJson
              value={compare}
              label="Full compare_report.json"
              testid="compare-raw-json"
            />
          </section>
        </>
      )}

      {/* If compare is absent but thesis may exist, still try to
          render the thesis section. It will either display the
          markdown or its honest-absent state. */}
      {!compare && (
        <section className="compare-lab-page__section">
          <h2>Thesis</h2>
          <ThesisSection
            claimSupport={undefined}
            thesisMarkdown={detail.thesis_report_raw_markdown}
            hasThesisReport={detail.metadata.has_thesis_report}
          />
        </section>
      )}
    </>
  );
}
