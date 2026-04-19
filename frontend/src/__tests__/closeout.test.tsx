import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { AppShell } from '@/components/AppShell';
import { AdvancedLensesPage } from '@/components/AdvancedLensesPage';
import { CompareLabPage } from '@/components/CompareLabPage';
import { LegacyV2Page } from '@/components/LegacyV2Page';
import { OverviewPage } from '@/components/OverviewPage';
import { SessionRuntimePage } from '@/components/SessionRuntimePage';

import {
  defaultBundleDetail,
  defaultBundleDetailWithLenses,
  emptyIndex,
  fullIndex,
} from './fixtures';
import { artifactKey, installBffFetchMock } from './testHelpers';

/**
 * Phase-closing polish checks. No new product semantics — these
 * tests guard the cross-cutting invariants that every prior
 * phase has relied on: shell consistency, GET-only selection
 * continuity, B4 experiment isolation, Legacy V2 read-only
 * framing, and the absence of any remaining placeholder route.
 */

describe('App shell consistency across all five real routes', () => {
  beforeEach(() => {
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        'fixture_default_3mode_v1': defaultBundleDetail,
      },
      sessionArtifactsByKey: {
        [artifactKey('fixture_default_3mode_v1', 'baseline_static')]: {
          bundle_id: 'fixture_default_3mode_v1',
          variant_tag: 'baseline_static',
          session_artifact_loadable: true,
          memory_jsonl_present: true,
          session_artifact_raw: {
            session_id: 'FIXTURE-DEFAULT-BASELINE_STATIC',
            config: { mode: 'BASELINE_STATIC', seed: 42, events_source: 'x' },
            event_records: [],
            memory_snapshot: {},
            kpis: {},
          },
          load_warnings: [],
        },
        [artifactKey('fixture_default_3mode_v1', 'path_c_cold')]: {
          bundle_id: 'fixture_default_3mode_v1',
          variant_tag: 'path_c_cold',
          session_artifact_loadable: true,
          memory_jsonl_present: true,
          session_artifact_raw: {
            session_id: 'FIXTURE-DEFAULT-PATH_C_COLD',
            config: { mode: 'PATH_C_COLD' },
            event_records: [],
            memory_snapshot: {},
            kpis: {},
          },
          load_warnings: [],
        },
        [artifactKey('fixture_default_3mode_v1', 'path_c_warm')]: {
          bundle_id: 'fixture_default_3mode_v1',
          variant_tag: 'path_c_warm',
          session_artifact_loadable: true,
          memory_jsonl_present: true,
          session_artifact_raw: {
            session_id: 'FIXTURE-DEFAULT-PATH_C_WARM',
            config: { mode: 'PATH_C_WARM' },
            event_records: [],
            memory_snapshot: {},
            kpis: {},
          },
          load_warnings: [],
        },
      },
    });
  });

  const pages: Array<{ name: string; Page: () => JSX.Element }> = [
    { name: 'Overview', Page: () => <OverviewPage /> },
    {
      name: 'Session Runtime',
      Page: () => <SessionRuntimePage />,
    },
    { name: 'Compare Lab', Page: () => <CompareLabPage /> },
    { name: 'Advanced Lenses', Page: () => <AdvancedLensesPage /> },
    { name: 'Legacy V2', Page: () => <LegacyV2Page /> },
  ];

  for (const { name, Page } of pages) {
    it(`${name} renders inside the standard shell with exactly one h1`, async () => {
      await act(async () => {
        render(
          <AppShell
            initialIndex={fullIndex}
            initialSelectedBundleId="fixture_default_3mode_v1"
          >
            <Page />
          </AppShell>,
        );
      });
      // Shell anchors are present on every page.
      expect(screen.getByTestId('app-main')).toBeInTheDocument();
      expect(screen.getByTestId('app-shell-footer')).toBeInTheDocument();
      expect(screen.getByTestId('app-shell-skip-link')).toBeInTheDocument();
      // Exactly one h1 per page.
      await waitFor(() => {
        const h1s = screen.getAllByRole('heading', { level: 1 });
        expect(h1s).toHaveLength(1);
      });
      // Nav tabs are visible on every page.
      expect(screen.getByTestId('nav-tab-overview')).toBeInTheDocument();
      expect(
        screen.getByTestId('nav-tab-session-runtime'),
      ).toBeInTheDocument();
      expect(screen.getByTestId('nav-tab-compare-lab')).toBeInTheDocument();
      expect(
        screen.getByTestId('nav-tab-advanced-lenses'),
      ).toBeInTheDocument();
      expect(screen.getByTestId('nav-tab-legacy-v2')).toBeInTheDocument();
      // No placeholder testid remains on any real route.
      expect(screen.queryByTestId('placeholder-page')).toBeNull();
    });
  }
});

describe('Nav tabs no longer expose a placeholder badge', () => {
  it('every nav tab renders as a real route (no "placeholder" badge)', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <OverviewPage />
      </AppShell>,
    );
    for (const path of [
      'overview',
      'session-runtime',
      'compare-lab',
      'advanced-lenses',
      'legacy-v2',
    ]) {
      const tab = screen.getByTestId(`nav-tab-${path}`);
      // The NavTabs component appends "placeholder" badges for
      // disabled tabs. No tab should carry that badge anymore.
      expect(tab.textContent ?? '').not.toMatch(/placeholder/);
    }
  });
});

describe('Bundle selection continuity', () => {
  it('selecting a bundle persists across a shell remount', async () => {
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        'fixture_default_3mode_v1': defaultBundleDetail,
      },
    });
    const user = userEvent.setup();

    const { unmount } = render(
      <AppShell
        initialIndex={fullIndex}
        initialSelectedBundleId="fixture_default_3mode_v1"
      >
        <OverviewPage />
      </AppShell>,
    );
    // Change selection to the B4 triplet via the global selector.
    const select = screen.getByTestId('bundle-select') as HTMLSelectElement;
    await user.selectOptions(select, 'fixture_b4_triplet_v1');
    await waitFor(() => {
      expect(
        (screen.getByTestId('bundle-select') as HTMLSelectElement).value,
      ).toBe('fixture_b4_triplet_v1');
    });
    // Now simulate a page reload: unmount + remount with NO
    // initialSelectedBundleId. The provider should restore the
    // selection from localStorage.
    unmount();
    render(
      <AppShell initialIndex={fullIndex}>
        <OverviewPage />
      </AppShell>,
    );
    await waitFor(() => {
      expect(
        (screen.getByTestId('bundle-select') as HTMLSelectElement).value,
      ).toBe('fixture_b4_triplet_v1');
    });
  });

  it('a stale selected id is replaced by the first bundle once the index loads', async () => {
    // Simulates "localStorage had a stale value" via the
    // equivalent public seam: pass a `initialSelectedBundleId`
    // that does not appear in the index and let `load()` run.
    // The provider must clear the stale id and auto-select the
    // first bundle the index actually carries.
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        'fixture_default_3mode_v1': defaultBundleDetail,
      },
    });
    await act(async () => {
      render(
        <AppShell
          initialSelectedBundleId="bundle_that_no_longer_exists"
        >
          <OverviewPage />
        </AppShell>,
      );
    });
    await waitFor(() => {
      const select = screen.getByTestId('bundle-select') as HTMLSelectElement;
      // Alphabetized first entry of the index fixture.
      expect(select.value).toBe('fixture_b4_triplet_v1');
    });
  });
});

describe('Representative empty/loading/error states still render honestly', () => {
  it('Overview: empty index still shows the system identity frame', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <OverviewPage />
      </AppShell>,
    );
    expect(screen.getByTestId('system-identity')).toBeInTheDocument();
    expect(screen.getByTestId('bundle-catalog-empty')).toBeInTheDocument();
  });

  it('Session Runtime: no-bundle notice still renders the honest state', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <SessionRuntimePage />
      </AppShell>,
    );
    expect(screen.getByTestId('runtime-no-bundle')).toBeInTheDocument();
  });

  it('Compare Lab: no-bundle notice still renders the honest state', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <CompareLabPage />
      </AppShell>,
    );
    expect(screen.getByTestId('compare-no-bundle')).toBeInTheDocument();
  });

  it('Advanced Lenses: no-bundle notice still renders the honest state', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <AdvancedLensesPage />
      </AppShell>,
    );
    expect(screen.getByTestId('lenses-no-bundle')).toBeInTheDocument();
  });
});

describe('B4 experiment framing remains isolated', () => {
  it('Advanced Lenses B4 block carries experiment / default-off / compare-only on every render', async () => {
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        'fixture_default_3mode_v1': defaultBundleDetailWithLenses,
      },
    });
    render(
      <AppShell
        initialIndex={fullIndex}
        initialSelectedBundleId="fixture_default_3mode_v1"
      >
        <AdvancedLensesPage />
      </AppShell>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('agent-memory-lens')).toBeInTheDocument();
    });
    const labels = screen.getByTestId('b4-experiment-labels');
    expect(labels).toHaveTextContent('experiment');
    expect(labels).toHaveTextContent('default-off');
    expect(labels).toHaveTextContent('compare-only');
    // And none of the other lenses borrow those labels — they
    // belong exclusively to the B4 block.
    for (const otherLens of [
      'replan-lens',
      'correlation-lens',
      'cumulative-lens',
    ]) {
      const node = screen.queryByTestId(otherLens);
      if (node) {
        expect(node.textContent ?? '').not.toMatch(/default-off/);
        expect(node.textContent ?? '').not.toMatch(/compare-only/);
      }
    }
  });
});

describe('Legacy V2 remains read-only', () => {
  it('exposes no executable controls', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <LegacyV2Page />
      </AppShell>,
    );
    const page = screen.getByTestId('legacy-v2-page');
    // Re-assert the read-only invariant in one place.
    expect(page.querySelectorAll('button')).toHaveLength(0);
    expect(page.querySelectorAll('input')).toHaveLength(0);
    expect(page.querySelectorAll('textarea')).toHaveLength(0);
    expect(page.querySelectorAll('form')).toHaveLength(0);
  });
});

describe('A11y basics present app-wide', () => {
  it('skip link lands on #app-main and the main element is focusable', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <OverviewPage />
      </AppShell>,
    );
    const skip = screen.getByTestId('app-shell-skip-link');
    expect(skip.getAttribute('href')).toBe('#app-main');
    const main = screen.getByTestId('app-main');
    expect(main.id).toBe('app-main');
    expect(main.tabIndex).toBe(-1);
  });
});
