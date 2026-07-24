import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { SettingsPage } from '../screens/SettingsPage';
import {
  stubFetchRoutes,
  stubFetchDown,
  aboutResponse,
  aboutResponseNoCommit,
  openApiFixture,
} from '../test/apiFixtures';

/**
 * P36.4 — Settings gets two functional sections: Help / About (live app
 * metadata from `GET /api/about`) and API Documentation (a searchable,
 * self-contained reference rendered from `GET /api/openapi`, the app's real
 * generated OpenAPI schema — no CDN, no Swagger UI / ReDoc).
 */

const ABOUT_URL = 'GET /api/about';
const OPENAPI_URL = 'GET /api/openapi';

function renderSettings() {
  return render(
    <MemoryRouter
      initialEntries={['/settings']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <SettingsPage />
    </MemoryRouter>,
  );
}

function fullRoutes() {
  return { [ABOUT_URL]: { body: aboutResponse }, [OPENAPI_URL]: { body: openApiFixture } };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- Help / About ------------------------------------------------------------

describe('Settings — Help / About', () => {
  it('shows a loading state before the fetch resolves', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(screen.getByText('Loading app info…')).toBeInTheDocument();
  });

  it('renders app version, build commit, and record schema version from the live endpoint', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(await screen.findByText('0.1.0')).toBeInTheDocument();
    expect(screen.getByText('fakecommit0000settingsp364')).toBeInTheDocument();
    expect(screen.getByText('v1.05')).toBeInTheDocument();
    // Both `runtime_mode` and `data_regime` render "synthetic-only" (distinct
    // fields, same current value) — assert there are two, not exactly one.
    expect(screen.getAllByText('synthetic-only')).toHaveLength(2);
    expect(screen.getByText('ephemeral')).toBeInTheDocument();
    expect(screen.getByText('isaac_records')).toBeInTheDocument();
  });

  it('renders an honest "not set" state when no build commit was injected (never fabricates one)', async () => {
    stubFetchRoutes({
      [ABOUT_URL]: { body: aboutResponseNoCommit },
      [OPENAPI_URL]: { body: openApiFixture },
    });
    renderSettings();
    expect(await screen.findByText(/not set/i)).toBeInTheDocument();
  });

  it('states the truth-vs-memory authority boundary and the no-guessing policy', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    expect(screen.getByText(/never by the assistant or by project memory/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing scientific is invented/i)).toBeInTheDocument();
  });

  it('lists in-repo documentation as plain references, not fetched/rendered content', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    expect(screen.getByText('CLAUDE.md')).toBeInTheDocument();
    expect(screen.getByText('AGENTS.md')).toBeInTheDocument();
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
    expect(alerts[0]).toHaveTextContent(/not running|unreachable/i);
  });
});

// --- API Documentation --------------------------------------------------------

describe('Settings — API Documentation', () => {
  it('shows a loading state before the fetch resolves', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(screen.getByText('Loading API documentation…')).toBeInTheDocument();
  });

  it('renders endpoints from the stubbed OpenAPI schema, grouped, with method + path + summary', async () => {
    const hits = stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(await screen.findByText('/api/health')).toBeInTheDocument();
    expect(screen.getByText('/api/about')).toBeInTheDocument();
    expect(screen.getByText('/api/experiments/{id}')).toBeInTheDocument();
    expect(screen.getByText('/api/experiments/{id}/answers')).toBeInTheDocument();
    expect(screen.getByText('Health')).toBeInTheDocument();
    expect(screen.getByText('Submit Answers')).toBeInTheDocument();
    // Method conveyed by TEXT, not color alone.
    expect(screen.getAllByText('GET').length).toBeGreaterThan(0);
    expect(screen.getByText('POST')).toBeInTheDocument();
    expect(hits).toEqual(expect.arrayContaining([ABOUT_URL, OPENAPI_URL]));
  });

  it('renders the total endpoint count', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(await screen.findByText('4 of 4 endpoints')).toBeInTheDocument();
  });

  it('the search box filters endpoints by path/summary, client-side, deterministically', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('/api/health');

    const search = screen.getByLabelText('Search endpoints') as HTMLInputElement;
    fireEvent.change(search, { target: { value: 'answers' } });

    expect(await screen.findByText('1 of 4 endpoints')).toBeInTheDocument();
    expect(screen.getByText('/api/experiments/{id}/answers')).toBeInTheDocument();
    expect(screen.queryByText('/api/health')).not.toBeInTheDocument();
    expect(screen.queryByText('/api/about')).not.toBeInTheDocument();
  });

  it('an unmatched search shows an honest empty state, never fabricated rows', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('/api/health');

    const search = screen.getByLabelText('Search endpoints');
    fireEvent.change(search, { target: { value: 'nonexistent-route-xyz' } });

    expect(await screen.findByText(/no endpoints match/i)).toBeInTheDocument();
    expect(screen.getByText('0 of 4 endpoints')).toBeInTheDocument();
  });

  it('search is keyboard-reachable (a native, labeled text input)', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('/api/health');
    const search = screen.getByLabelText('Search endpoints');
    expect(search.tagName).toBe('INPUT');
    expect(search).toHaveAttribute('type', 'search');
  });

  it('a row expands (native <details>) to show its description and parameters', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    const summary = await screen.findByText('Get Experiment');
    const row = summary.closest('details') as HTMLDetailsElement;
    expect(row).not.toBeNull();
    expect(row.open).toBe(false);

    // Native <details>/<summary> is keyboard-operable: click the summary (jsdom
    // toggles `open` on a real <summary> click just like Enter/Space would).
    fireEvent.click(summary);
    expect(row.open).toBe(true);
    expect(within(row).getByText(/fetch one experiment detail by id/i)).toBeInTheDocument();
    expect(within(row).getByText('id')).toBeInTheDocument();
    expect(within(row).getByText('path')).toBeInTheDocument();
    expect(within(row).getByText('Yes')).toBeInTheDocument();
  });

  it('a row with no parameters says so honestly rather than showing an empty table', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    const summary = await screen.findByText('About');
    const row = summary.closest('details') as HTMLDetailsElement;
    fireEvent.click(summary);
    expect(within(row).getByText('No parameters.')).toBeInTheDocument();
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
  });
});
