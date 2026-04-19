import { act, render, screen, waitFor } from '@testing-library/react';
import ReactDOMServer from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from '@/components/AppShell';
import { BundleSummaryCard } from '@/components/BundleSummaryCard';
import { OverviewPage } from '@/components/OverviewPage';

import {
  defaultBundleDetail,
  emptyIndex,
  fullIndex,
} from './fixtures';
import { installBffFetchMock } from './testHelpers';

/**
 * Regression pins for a production hydration mismatch observed on
 * Overview when `demo_showcase_default_trio_v1` was the
 * localStorage-remembered bundle:
 *
 *   Text content did not match.
 *   Server: 'Selected bundle' Client: 'Why the outputs are trustworthy'
 *
 * Root cause had two parts:
 *   (a) BundleContext was reading localStorage inside its
 *       useState initializer. The Next.js server had no window
 *       so it committed `null`; the client re-ran the
 *       initializer during hydration, read the stored id, and
 *       diverged.
 *   (b) BundleSummaryCard returned bare `null` for the transient
 *       "selection exists but detail fetch hasn't started"
 *       state. The card disappeared on the client, shifting
 *       every later <h2> up one slot — and React's hydration
 *       diff reported the text-content error above.
 *
 * These tests freeze both invariants.
 *
 * Direct `window.localStorage.setItem` is unreliable across
 * tests in this jsdom/vitest setup (the closeout suite already
 * works around the same quirk). Instead we spy on
 * `Storage.prototype.getItem` — that IS the only method the
 * hydration-time provider code path invokes.
 */

function stubStoredBundleId(id: string | null): void {
  // Clear any leftover spy from a prior test before installing
  // this one. `vi.spyOn(Storage.prototype, …)` stacks otherwise
  // and the second call just layers a new mockImplementation
  // over stale wiring.
  vi.restoreAllMocks();
  const spy = vi.spyOn(Storage.prototype, 'getItem');
  spy.mockImplementation((key: string): string | null => {
    if (key === 'b5.selectedBundleId') return id;
    return null;
  });
}

describe('Hydration safety', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    installBffFetchMock({ index: emptyIndex });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('provider first render is identical whether a stored id exists or not', () => {
    // Snapshot 1: no stored id.
    stubStoredBundleId(null);
    const htmlEmpty = ReactDOMServer.renderToString(
      <AppShell initialIndex={fullIndex}>
        <OverviewPage />
      </AppShell>,
    );
    vi.restoreAllMocks();

    // Snapshot 2: stored id present. The fix makes the first
    // render ignore it (restoration happens in a post-mount
    // effect), so both snapshots must be identical.
    stubStoredBundleId('fixture_default_3mode_v1');
    const htmlStored = ReactDOMServer.renderToString(
      <AppShell initialIndex={fullIndex}>
        <OverviewPage />
      </AppShell>,
    );
    vi.restoreAllMocks();

    expect(htmlStored).toBe(htmlEmpty);
    // And both first renders must emit the BundleSummaryCard
    // shell (not `null`) so no sibling h2 shifts.
    expect(htmlEmpty).toContain('bundle-summary-empty');
  });

  it('BundleSummaryCard never returns null in any render state', () => {
    // State: selection present but detail fetch has not resolved.
    // Use a fetch that never resolves so we stay in that window.
    type Resolver = (value: Response) => void;
    let _resolve: Resolver = () => {};
    const pending = new Promise<Response>((res) => {
      _resolve = res;
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(() => pending),
    );

    render(
      <AppShell
        initialIndex={fullIndex}
        initialSelectedBundleId="fixture_default_3mode_v1"
      >
        <BundleSummaryCard />
      </AppShell>,
    );

    // Either the loading branch or the already-resolved branch
    // is acceptable; what is NOT acceptable is an absent card.
    const card =
      screen.queryByTestId('bundle-summary-loading') ??
      screen.queryByTestId('bundle-summary');
    expect(card).not.toBeNull();
    // Canonical "Selected bundle" h2 is always present on the
    // shell variants so sibling h2 slots stay stable.
    expect(
      screen.getByRole('heading', { name: 'Selected bundle', level: 2 }),
    ).toBeInTheDocument();

    // Let the pending promise resolve so no Node warning leaks.
    _resolve(
      new Response(JSON.stringify(defaultBundleDetail), { status: 200 }),
    );
  });

  it('stored selection is restored after mount (post-hydration effect)', async () => {
    stubStoredBundleId('fixture_b4_triplet_v1');
    await act(async () => {
      render(
        <AppShell initialIndex={fullIndex}>
          <OverviewPage />
        </AppShell>,
      );
    });
    await waitFor(() => {
      expect(
        (screen.getByTestId('bundle-select') as HTMLSelectElement).value,
      ).toBe('fixture_b4_triplet_v1');
    });
    vi.restoreAllMocks();
  });

  it('selected-bundle h2 is always present on Overview (slot count never dips)', () => {
    // Complements the HTML-snapshot test: assert the
    // BundleSummaryCard's "Selected bundle" h2 exists on the
    // pre-restore render. If the card went back to returning
    // null, Overview's h2 sequence would shift and sibling
    // section headings would mis-hydrate — which is exactly
    // the production bug this suite is pinning.
    stubStoredBundleId('fixture_default_3mode_v1');
    render(
      <AppShell initialIndex={fullIndex}>
        <OverviewPage />
      </AppShell>,
    );
    expect(
      screen.getByRole('heading', { name: 'Selected bundle', level: 2 }),
    ).toBeInTheDocument();
    // And the section immediately after Overview's bundle-summary
    // slot must still be ReproducibilitySection — confirming the
    // structural order Overview commits to.
    const h2s = screen
      .getAllByRole('heading', { level: 2 })
      .map((h) => (h.textContent ?? '').trim());
    const selectedIdx = h2s.indexOf('Selected bundle');
    expect(selectedIdx).toBeGreaterThan(-1);
    expect(h2s[selectedIdx + 1]).toBe('Why the outputs are trustworthy');
  });
});
