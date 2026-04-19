'use client';

import {
  LEGACY_V2_BOUNDARY_NOTE,
  LEGACY_V2_CAPABILITY_APPENDIX,
  LEGACY_V2_IDENTITY,
  LEGACY_V2_WHY_IT_MATTERS,
  LINEAGE_NODES,
} from '@/lib/constants';
import { useBundleContext } from './BundleContext';

/**
 * Phase 6A Legacy V2 — appendix / baseline-historical page.
 *
 * This is NOT an active runtime surface. It is a static
 * explanatory page grounded in what the repository already
 * carries (the V2 overview report, the D3 Path B full report,
 * PATH_C_BOUNDARY / PATH_C_SCHEMA_REGISTRY). It never imports
 * from `src/api/*`, never revives `app.py`, and never calls a
 * legacy runtime.
 *
 * The BundleSelector in the AppShell still works, but this
 * page renders meaningfully even when no bundle is selected —
 * the appendix content is independent of the evaluation bundle.
 */
export function LegacyV2Page() {
  const { selectedBundleId } = useBundleContext();

  return (
    <div className="legacy-v2-page" data-testid="legacy-v2-page">
      <header className="legacy-v2-page__header">
        <div className="legacy-v2-page__title-row">
          <h1>Legacy V2</h1>
          <ul
            className="legacy-v2-page__labels"
            data-testid="legacy-v2-labels"
            aria-label="Legacy V2 framing labels"
          >
            <li>appendix</li>
            <li>baseline</li>
            <li>historical</li>
          </ul>
        </div>
        <p className="legacy-v2-page__lede">{LEGACY_V2_IDENTITY.lede}</p>
        <p
          className="legacy-v2-page__bundle-hint"
          data-testid="legacy-v2-bundle-hint"
        >
          {selectedBundleId ? (
            <>
              Viewing the appendix in the context of bundle{' '}
              <code>{selectedBundleId}</code>. Legacy V2 content does not
              depend on this bundle — it is static historical framing.
            </>
          ) : (
            <>
              No evaluation bundle is currently selected. Legacy V2
              renders the same appendix content regardless; selecting a
              bundle is only needed for the other tabs.
            </>
          )}
        </p>
      </header>

      {/* 1. Identity */}
      <section
        className="legacy-v2-page__section"
        data-testid="legacy-v2-identity"
        aria-label="Legacy V2 identity"
      >
        <h2>Legacy V2 identity</h2>
        <ul className="legacy-v2-page__list">
          {LEGACY_V2_IDENTITY.whatItWas.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="legacy-v2-page__role">{LEGACY_V2_IDENTITY.role}</p>
      </section>

      {/* 2. Why V2 still matters */}
      <section
        className="legacy-v2-page__section"
        data-testid="legacy-v2-why"
        aria-label="Why Legacy V2 still matters"
      >
        <h2>Why V2 still matters</h2>
        <ul className="legacy-v2-page__why-list">
          {LEGACY_V2_WHY_IT_MATTERS.map((item) => (
            <li key={item.title}>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* 3. Evolution / lineage */}
      <section
        className="legacy-v2-page__section"
        data-testid="legacy-v2-lineage"
        aria-label="Repository evolution / lineage"
      >
        <h2>Evolution</h2>
        <p className="legacy-v2-page__section-note">
          Three repository / project stages. V2 is the middle stage;
          this repo (<code>supply-chain-twin-D3_pathc</code>) is the
          current stage and carries the B5 surface you are reading.
        </p>
        <ol className="legacy-v2-page__lineage">
          {LINEAGE_NODES.map((node, idx) => (
            <li
              key={node.id}
              data-testid={`legacy-v2-lineage-node-${node.id}`}
            >
              <div className="legacy-v2-page__lineage-heading">
                <span className="legacy-v2-page__lineage-title">
                  {node.title}
                </span>
                <span className="legacy-v2-page__lineage-subtitle">
                  {node.subtitle}
                </span>
              </div>
              <p>{node.role}</p>
              {idx < LINEAGE_NODES.length - 1 && (
                <span
                  aria-hidden="true"
                  className="legacy-v2-page__lineage-arrow"
                >
                  ↓
                </span>
              )}
            </li>
          ))}
        </ol>
      </section>

      {/* 4. Capability appendix */}
      <section
        className="legacy-v2-page__section"
        data-testid="legacy-v2-capabilities"
        aria-label="Legacy V2 capability appendix"
      >
        <h2>V2 capability appendix</h2>
        <p className="legacy-v2-page__section-note">
          Compact summary of what V2 provided. This is explanatory —
          none of these capabilities are called from B5.
        </p>
        <dl className="legacy-v2-page__capabilities">
          {LEGACY_V2_CAPABILITY_APPENDIX.map((cap) => (
            <div
              key={cap.id}
              data-testid={`legacy-v2-capability-${cap.id}`}
            >
              <dt>{cap.title}</dt>
              <dd>{cap.body}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* 5. Boundary note */}
      <section
        className="legacy-v2-page__boundary"
        data-testid="legacy-v2-boundary"
        aria-label="Legacy V2 boundary note"
        role="note"
      >
        <h2>Boundary note</h2>
        <p>{LEGACY_V2_BOUNDARY_NOTE}</p>
      </section>
    </div>
  );
}
