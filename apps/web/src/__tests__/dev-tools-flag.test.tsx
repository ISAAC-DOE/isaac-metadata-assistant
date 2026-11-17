/**
 * THE DEVELOPER SURFACES ARE BEHIND `VITE_ISAAC_DEV_TOOLS=1` (2026-11-16).
 *
 * Statistics → Build & Verification, Settings → Advanced (the Endpoint Explorer and the
 * Project Memory link) and Project Memory's search leads are developer tools. Without the
 * flag they are not offered and their old `?tab=` values resolve to a sensible tab; with
 * it, they are exactly as before. Both halves are pinned, so the flag can neither leak a
 * developer surface into the scientist UI nor quietly delete one.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { SettingsPage } from '../screens/SettingsPage';
import { StatisticsPage } from '../screens/statistics/StatisticsPage';
import { resolveSettingsTab } from '../lib/routes';
import { devToolsEnabled } from '../lib/devTools';
import { stubFetchDown } from '../test/apiFixtures';

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

function renderPage(page: 'settings' | 'statistics', search: string) {
  stubFetchDown();
  return render(
    <MemoryRouter initialEntries={[`/${page}${search}`]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      {page === 'settings' ? <SettingsPage /> : <StatisticsPage />}
      <LocationProbe />
    </MemoryRouter>,
  );
}

const tabNames = (label: string) =>
  within(screen.getByRole('tablist', { name: label }))
    .getAllByRole('tab')
    .map((tab) => tab.textContent);

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('the flag itself', () => {
  it('is off unless the variable is exactly "1"', () => {
    expect(devToolsEnabled()).toBe(false);
    vi.stubEnv('VITE_ISAAC_DEV_TOOLS', 'true');
    expect(devToolsEnabled()).toBe(false);
    vi.stubEnv('VITE_ISAAC_DEV_TOOLS', '1');
    expect(devToolsEnabled()).toBe(true);
  });
});

describe('Settings without the flag', () => {
  it('offers Overview and Integrations only', () => {
    renderPage('settings', '');
    expect(tabNames('Settings sections')).toEqual(['Overview', 'Integrations']);
    expect(screen.queryByRole('heading', { name: 'Endpoint Explorer' })).toBeNull();
  });

  it('?tab=advanced lands on Overview, and ?tab=explorer on Integrations', () => {
    renderPage('settings', '?tab=advanced');
    expect(screen.getByRole('tab', { selected: true }).textContent).toBe('Overview');
    expect(screen.queryByRole('link', { name: /Project Memory/ })).toBeNull();
  });

  it('?tab=explorer lands on Integrations, and no control offers an explorer', () => {
    renderPage('settings', '?tab=explorer');
    expect(screen.getByRole('tab', { selected: true }).textContent).toBe('Integrations');
    expect(screen.queryByRole('button', { name: /Endpoint Explorer|Browse Every Endpoint/ })).toBeNull();
  });

  it('resolves the retired ids the same way in the pure helper', () => {
    expect(resolveSettingsTab('advanced', { advanced: false })).toEqual({ tab: 'overview', widget: null });
    expect(resolveSettingsTab('explorer', { advanced: false })).toEqual({
      tab: 'integrations',
      widget: 'settings-apiaccess-heading',
    });
    // Every other value resolves as it always has.
    expect(resolveSettingsTab('mcp', { advanced: false })).toEqual(resolveSettingsTab('mcp'));
    expect(resolveSettingsTab('nonsense', { advanced: false })).toEqual({ tab: 'overview', widget: null });
  });
});

describe('Settings with the flag', () => {
  it('offers Advanced, and ?tab=explorer opens it', () => {
    vi.stubEnv('VITE_ISAAC_DEV_TOOLS', '1');
    renderPage('settings', '?tab=explorer');
    expect(tabNames('Settings sections')).toEqual(['Overview', 'Integrations', 'Advanced']);
    expect(screen.getByRole('tab', { selected: true }).textContent).toBe('Advanced');
    expect(screen.getByRole('heading', { name: 'Endpoint Explorer' })).toBeTruthy();
  });
});

describe('Statistics without the flag', () => {
  it('?tab=build shows Overview, with no Build & Verification tab anywhere', () => {
    renderPage('statistics', '?tab=build');
    expect(screen.queryByRole('tab', { name: 'Build & Verification' })).toBeNull();
    // With My Stats unavailable too, Overview is the whole page: no one-tab tablist.
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(document.getElementById('statistics-tabpanel-general')).not.toBeNull();
    expect(document.getElementById('statistics-tabpanel-build')).toBeNull();
  });
});

describe('Statistics with the flag', () => {
  it('offers Build & Verification at ?tab=build', () => {
    vi.stubEnv('VITE_ISAAC_DEV_TOOLS', '1');
    renderPage('statistics', '?tab=build');
    expect(screen.getByRole('tab', { name: 'Build & Verification', selected: true })).toBeTruthy();
    expect(document.getElementById('statistics-tabpanel-build')).not.toBeNull();
  });
});
