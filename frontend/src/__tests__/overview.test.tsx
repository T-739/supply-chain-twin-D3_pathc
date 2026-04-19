import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AppShell } from '@/components/AppShell';
import { OverviewPage } from '@/components/OverviewPage';

import { defaultBundleDetail, fullIndex } from './fixtures';
import { installBffFetchMock } from './testHelpers';

describe('Overview route', () => {
  beforeEach(() => {
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        [defaultBundleDetail.metadata.bundle_id]: defaultBundleDetail,
      },
    });
  });

  it('renders the overview shell and all required sections', async () => {
    render(
      <AppShell
        initialIndex={fullIndex}
        initialSelectedBundleId={defaultBundleDetail.metadata.bundle_id}
      >
        <OverviewPage />
      </AppShell>,
    );

    // Page frame + required sections
    expect(screen.getByTestId('overview-page')).toBeInTheDocument();
    expect(screen.getByTestId('system-identity')).toBeInTheDocument();
    expect(screen.getByTestId('bundle-catalog')).toBeInTheDocument();
    expect(screen.getByTestId('reproducibility')).toBeInTheDocument();
    expect(screen.getByTestId('lineage-strip')).toBeInTheDocument();

    // Lineage lists the three repos in order.
    expect(screen.getByTestId('lineage-node-v1')).toHaveTextContent(
      'supply-chain-twin',
    );
    expect(screen.getByTestId('lineage-node-v2')).toHaveTextContent(
      'supply-chain-twin-D3',
    );
    expect(screen.getByTestId('lineage-node-pathc')).toHaveTextContent(
      'supply-chain-twin-D3_pathc',
    );

    // Bundle catalog renders both fixture bundles.
    expect(
      screen.getByTestId('bundle-row-fixture_default_3mode_v1'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('bundle-row-fixture_b4_triplet_v1'),
    ).toBeInTheDocument();

    // The summary card fetches detail for the selected bundle.
    await waitFor(() => {
      expect(screen.getByTestId('bundle-summary')).toBeInTheDocument();
    });
    expect(screen.getByTestId('bundle-summary-variant-set')).toHaveTextContent(
      'default_3_mode',
    );
    expect(screen.getByTestId('bundle-summary-reports')).toHaveTextContent(
      /Compare report: present/,
    );
    expect(screen.getByTestId('bundle-summary-reports')).toHaveTextContent(
      /Thesis report: present/,
    );
  });
});
