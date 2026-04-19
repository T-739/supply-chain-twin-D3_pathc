import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AppShell } from '@/components/AppShell';
import { LegacyV2Page } from '@/components/LegacyV2Page';

import {
  defaultBundleDetail,
  emptyIndex,
  fullIndex,
} from './fixtures';
import { installBffFetchMock } from './testHelpers';

describe('Legacy V2 route', () => {
  it('loads as a real page with appendix framing labels', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <LegacyV2Page />
      </AppShell>,
    );
    expect(screen.getByTestId('legacy-v2-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Legacy V2', level: 1 }),
    ).toBeInTheDocument();

    // Framing labels (appendix / baseline / historical) are present.
    const labels = screen.getByTestId('legacy-v2-labels');
    expect(labels).toHaveTextContent('appendix');
    expect(labels).toHaveTextContent('baseline');
    expect(labels).toHaveTextContent('historical');
  });

  it('lineage section covers the three repo / project stages', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <LegacyV2Page />
      </AppShell>,
    );
    const lineage = screen.getByTestId('legacy-v2-lineage');
    expect(within(lineage).getByTestId('legacy-v2-lineage-node-v1'))
      .toHaveTextContent('supply-chain-twin');
    expect(within(lineage).getByTestId('legacy-v2-lineage-node-v2'))
      .toHaveTextContent('supply-chain-twin-D3');
    expect(within(lineage).getByTestId('legacy-v2-lineage-node-pathc'))
      .toHaveTextContent('supply-chain-twin-D3_pathc');
  });

  it('capability appendix covers the V2 surfaces explanatorily', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <LegacyV2Page />
      </AppShell>,
    );
    for (const id of ['retrieval', 'agents', 'evaluation', 'api', 'supervision']) {
      expect(
        screen.getByTestId(`legacy-v2-capability-${id}`),
      ).toBeInTheDocument();
    }
    // The API capability row explicitly references the legacy surfaces
    // without revealing them as operational.
    const api = screen.getByTestId('legacy-v2-capability-api');
    expect(api).toHaveTextContent('src/api');
    expect(api).toHaveTextContent('app.py');
    expect(api).toHaveTextContent(/does NOT revive/i);
  });

  it('boundary note states the page is not an active legacy runtime', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <LegacyV2Page />
      </AppShell>,
    );
    const boundary = screen.getByTestId('legacy-v2-boundary');
    expect(boundary).toHaveTextContent(/does NOT expose an active legacy runtime/i);
    expect(boundary).toHaveTextContent(/historical/i);
    expect(boundary).toHaveTextContent(/baseline/i);
    // No action button / no link that would imply a runtime call.
    expect(within(boundary).queryByRole('button')).toBeNull();
    expect(within(boundary).queryAllByRole('link')).toHaveLength(0);
  });

  it('renders without a selected bundle (empty bundle context)', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <LegacyV2Page />
      </AppShell>,
    );
    // Bundle hint honestly reports the empty context.
    expect(screen.getByTestId('legacy-v2-bundle-hint')).toHaveTextContent(
      /No evaluation bundle is currently selected/,
    );
    // Every section still renders.
    expect(screen.getByTestId('legacy-v2-identity')).toBeInTheDocument();
    expect(screen.getByTestId('legacy-v2-why')).toBeInTheDocument();
    expect(screen.getByTestId('legacy-v2-lineage')).toBeInTheDocument();
    expect(screen.getByTestId('legacy-v2-capabilities')).toBeInTheDocument();
    expect(screen.getByTestId('legacy-v2-boundary')).toBeInTheDocument();
  });

  it('optionally references the selected bundle without depending on it', async () => {
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        'fixture_default_3mode_v1': defaultBundleDetail,
      },
    });
    render(
      <AppShell
        initialIndex={fullIndex}
        initialSelectedBundleId="fixture_default_3mode_v1"
      >
        <LegacyV2Page />
      </AppShell>,
    );
    expect(screen.getByTestId('legacy-v2-bundle-hint')).toHaveTextContent(
      'fixture_default_3mode_v1',
    );
    // The appendix content is identical regardless of bundle.
    expect(screen.getByTestId('legacy-v2-identity')).toBeInTheDocument();
    expect(screen.getByTestId('legacy-v2-capabilities')).toBeInTheDocument();
  });
});

describe('Legacy V2 boundary surface', () => {
  beforeEach(() => {
    installBffFetchMock({ index: emptyIndex });
  });

  it('contains no buttons or forms that would suggest an active runtime', () => {
    render(
      <AppShell initialIndex={emptyIndex}>
        <LegacyV2Page />
      </AppShell>,
    );
    const page = screen.getByTestId('legacy-v2-page');
    // A read-only appendix must not present executable controls.
    expect(within(page).queryAllByRole('button')).toHaveLength(0);
    expect(within(page).queryAllByRole('textbox')).toHaveLength(0);
    expect(within(page).queryAllByRole('combobox')).toHaveLength(0);
    expect(
      within(page).queryAllByRole('form', { hidden: true }),
    ).toHaveLength(0);
  });
});
