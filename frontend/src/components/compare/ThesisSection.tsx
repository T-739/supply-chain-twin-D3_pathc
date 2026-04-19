'use client';

import type { ThesisClaimSupportBlock } from '@/lib/types';

export interface ThesisSectionProps {
  claimSupport: ThesisClaimSupportBlock | undefined;
  thesisMarkdown: string | null;
  hasThesisReport: boolean;
}

function fmtDelta(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'null';
  if (typeof v !== 'number' || !Number.isFinite(v)) return 'null';
  return v.toFixed(4);
}

function fmtSupport(v: boolean | null | undefined): string {
  if (v === null || v === undefined) return 'null';
  return v ? 'true' : 'false';
}

/**
 * Canonical thesis viewer.
 *
 * Two presentations of the same canonical truth, side by side:
 *
 *   1. `ThesisClaimSupport` — the structured block already
 *      emitted by `session_compare._build_thesis_claim_support`.
 *      Surfaced as labeled rows. The `supports_claim` verdict
 *      is shown exactly as the artifact committed to it;
 *      nothing is re-decided here.
 *
 *   2. `thesis_report.md` — the deterministic markdown rendered
 *      by `session_compare.render_thesis_markdown`, displayed
 *      verbatim as preformatted text. No paraphrasing, no
 *      re-summarising. This is the "paper trail" view.
 */
export function ThesisSection({
  claimSupport,
  thesisMarkdown,
  hasThesisReport,
}: ThesisSectionProps) {
  return (
    <section
      className="thesis-section"
      data-testid="thesis-section"
      aria-label="Thesis"
    >
      <h3 className="thesis-section__heading">Thesis claim support</h3>
      {!claimSupport ? (
        <p
          className="compare-lab__absent"
          data-testid="thesis-claim-support-absent"
        >
          The compare report does not include a
          <code> thesis_claim_support </code>
          block.
        </p>
      ) : (
        <div
          className="thesis-section__claim"
          data-testid="thesis-claim-support"
        >
          {claimSupport.claim ? (
            <blockquote
              className="thesis-section__claim-quote"
              data-testid="thesis-claim-support-claim"
            >
              {claimSupport.claim}
            </blockquote>
          ) : null}
          <dl className="thesis-section__grid">
            <div>
              <dt>warm_calibrated_autonomy_delta</dt>
              <dd data-testid="thesis-claim-cas">
                {fmtDelta(claimSupport.warm_calibrated_autonomy_delta)}
              </dd>
            </div>
            <div>
              <dt>warm_sla_preservation_delta</dt>
              <dd data-testid="thesis-claim-sla">
                {fmtDelta(claimSupport.warm_sla_preservation_delta)}
              </dd>
            </div>
            <div>
              <dt>warm_cost_delta</dt>
              <dd data-testid="thesis-claim-cost">
                {fmtDelta(claimSupport.warm_cost_delta)}
              </dd>
            </div>
            <div>
              <dt>supports_claim</dt>
              <dd data-testid="thesis-claim-supports">
                <strong>{fmtSupport(claimSupport.supports_claim)}</strong>
              </dd>
            </div>
          </dl>
          {claimSupport.notes ? (
            <p
              className="thesis-section__notes"
              data-testid="thesis-claim-notes"
            >
              {claimSupport.notes}
            </p>
          ) : null}
        </div>
      )}

      <h3 className="thesis-section__heading">Thesis report (raw markdown)</h3>
      {!hasThesisReport ? (
        <p
          className="compare-lab__absent"
          data-testid="thesis-markdown-absent-metadata"
        >
          This bundle does not carry a <code>thesis_report.md</code>.
        </p>
      ) : thesisMarkdown === null ? (
        <p
          className="compare-lab__absent"
          data-testid="thesis-markdown-unreadable"
        >
          The bundle metadata claims a thesis report, but the file could
          not be loaded. See <code>load_warnings</code> above.
        </p>
      ) : (
        <pre
          className="thesis-section__markdown"
          data-testid="thesis-markdown"
          aria-label="thesis_report.md verbatim"
        >
          {thesisMarkdown}
        </pre>
      )}
    </section>
  );
}
