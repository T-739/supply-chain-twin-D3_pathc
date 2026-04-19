import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AppShell } from '@/components/AppShell';
import { OverviewPage } from '@/components/OverviewPage';

import { b4BundleDetail, fullIndex } from './fixtures';
import { installBffFetchMock } from './testHelpers';

describe('B4 triplet bundle', () => {
  beforeEach(() => {
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        [b4BundleDetail.metadata.bundle_id]: b4BundleDetail,
      },
    });
  });

  it('renders without assuming path_c_cold exists', async () => {
    render(
      <AppShell
        initialIndex={fullIndex}
        initialSelectedBundleId={b4BundleDetail.metadata.bundle_id}
      >
        <OverviewPage />
      </AppShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('bundle-summary')).toBeInTheDocument();
    });

    // Variant set is the B4 triplet and the three expected tags
    // are shown — path_c_cold is NOT one of them.
    expect(screen.getByTestId('bundle-summary-variant-set')).toHaveTextContent(
      'b4_experiment_triplet',
    );
    const tagList = screen.getByTestId('bundle-summary-tags');
    expect(tagList).toHaveTextContent('baseline_static');
    expect(tagList).toHaveTextContent('path_c_warm_policy_only');
    expect(tagList).toHaveTextContent('path_c_warm_agent_visible_memory');
    expect(tagList).not.toHaveTextContent('path_c_cold');

    // Session table also avoids path_c_cold.
    const sessions = screen.getByTestId('bundle-summary-sessions');
    expect(within(sessions).queryByText('path_c_cold')).toBeNull();

    // Thesis report absence is made explicit.
    expect(screen.getByTestId('bundle-summary-reports')).toHaveTextContent(
      /Thesis report: absent/,
    );

    // Warnings from metadata are surfaced.
    const warningsList = screen.getByTestId('bundle-summary-warnings');
    expect(warningsList).toHaveTextContent(
      /path_c_cold variant intentionally absent/,
    );
  });
});
