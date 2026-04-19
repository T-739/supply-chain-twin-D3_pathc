'use client';

import { BundleCatalog } from './BundleCatalog';
import { BundleSummaryCard } from './BundleSummaryCard';
import { LineageStrip } from './LineageStrip';
import { ReproducibilitySection } from './ReproducibilitySection';
import { SystemIdentitySection } from './SystemIdentitySection';

/**
 * Overview — the only real page in Phase 2.
 *
 * Section order is deliberate and matches the narrative the
 * roadmap asks the Overview to answer:
 *   1. what the system IS            → SystemIdentitySection
 *   2. where this view comes from    → BundleCatalog
 *   3. what is in the selected       → BundleSummaryCard
 *      bundle (variants, warnings,     (pulls live detail via BFF)
 *      compare/thesis availability)
 *   4. why it is trustworthy         → ReproducibilitySection
 *   5. how V2 / D3 Path B /          → LineageStrip
 *      D3_pathc relate
 */
export function OverviewPage() {
  return (
    <div className="overview-page" data-testid="overview-page">
      <header className="overview-page__header">
        <h1>Overview</h1>
        <p className="overview-page__lede">
          A read-only window onto the supply-chain digital twin. The
          runtime is deterministic and lives outside this surface; the
          B5 frontend only consumes already-produced session bundles
          through the backend-for-frontend (BFF) contract.
        </p>
      </header>

      <SystemIdentitySection />
      <BundleCatalog />
      <BundleSummaryCard />
      <ReproducibilitySection />
      <LineageStrip />
    </div>
  );
}
