import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AppShell } from '@/components/AppShell';
import { OverviewPage } from '@/components/OverviewPage';

import { emptyIndex } from './fixtures';
import { installBffFetchMock } from './testHelpers';

describe('Empty bundle index', () => {
  beforeEach(() => {
    installBffFetchMock({ index: emptyIndex });
  });

  it('renders the empty-catalog hint and keeps the shell alive', () => {
    render(
      <AppShell initialIndex={emptyIndex}>
        <OverviewPage />
      </AppShell>,
    );

    // Shell + sections still render.
    expect(screen.getByTestId('overview-page')).toBeInTheDocument();
    expect(screen.getByTestId('system-identity')).toBeInTheDocument();
    expect(screen.getByTestId('reproducibility')).toBeInTheDocument();
    expect(screen.getByTestId('lineage-strip')).toBeInTheDocument();

    // Catalog shows the empty-state hint.
    expect(screen.getByTestId('bundle-catalog-empty')).toBeInTheDocument();
    // User-facing copy (Phase 3A cleanup fix).
    expect(screen.getByTestId('bundle-catalog-empty')).toHaveTextContent(
      /No evaluation bundles are available yet/,
    );

    // Summary card has no selection.
    expect(screen.getByTestId('bundle-summary-empty')).toBeInTheDocument();

    // Bundle selector is disabled (no options).
    const select = screen.getByTestId('bundle-select') as HTMLSelectElement;
    expect(select).toBeDisabled();
    expect(select.options[0].textContent).toMatch(/No bundles available/);
  });
});
