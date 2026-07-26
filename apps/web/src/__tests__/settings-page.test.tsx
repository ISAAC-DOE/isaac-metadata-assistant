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
 * P36.4 gave Settings two functional sections; P36R Slice 9 reorganises the
 * surface into four local page tabs — Overview · Data & Privacy · About · API —
 * and turns the API section into a master-detail browser over `GET /api/openapi`
 * (the app's real generated contract: no CDN, no Swagger UI / ReDoc).
 *
 * Guards preserved from P36.4: the honest `not set` build-commit branch, the
 * truth-vs-memory + no-guessing copy, `IN_REPO_DOCS` rendered as inert names,
 * the HTTP method conveyed by TEXT, and the honest `No parameters.` state.
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

const tab = (name: string) => screen.getByRole('tab', { name });

/** Switch tabs the way a user does — by activating the tab button. */
function openTab(name: string) {
  fireEvent.click(tab(name));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- tab structure ------------------------------------------------------------

describe('Settings — tabs', () => {
  it('renders exactly the four specified tabs, with Overview selected by default', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual([
      'Overview',
      'Data & Privacy',
      'About',
      'API',
    ]);
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'settings-tabpanel-overview');
  });

  it('uses a roving tabindex: only the selected tab is in the tab order', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(tab('Overview')).toHaveAttribute('tabindex', '0');
    expect(tab('API')).toHaveAttribute('tabindex', '-1');
    expect(screen.getAllByRole('tab').filter((t) => t.getAttribute('tabindex') === '0')).toHaveLength(1);
  });

  it('only the selected tab points at a panel via aria-controls', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(tab('Overview')).toHaveAttribute('aria-controls', 'settings-tabpanel-overview');
    expect(tab('About')).not.toHaveAttribute('aria-controls');
  });

  it('clicking a tab switches the rendered panel', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('About');
    expect(tab('About')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'settings-tabpanel-about');
  });

  it('Arrow / Home / End move the selection (automatic activation)', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();

    fireEvent.keyDown(tab('Overview'), { key: 'ArrowRight' });
    expect(tab('Data & Privacy')).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(tab('Data & Privacy'), { key: 'End' });
    expect(tab('API')).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(tab('API'), { key: 'Home' });
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(tab('Overview'), { key: 'ArrowLeft' });
    expect(tab('API')).toHaveAttribute('aria-selected', 'true');
  });

  it('states plainly that there is nothing to configure (no invented settings)', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(screen.getByText(/no user-adjustable settings/i)).toBeInTheDocument();
    // Nothing on this page is an input except the API search field.
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });
});

// --- Overview -----------------------------------------------------------------

describe('Settings — Overview', () => {
  it('shows a loading state before the fetch resolves', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(screen.getByText('Loading app info…')).toBeInTheDocument();
  });

  it('summarizes the runtime from the live endpoint, never a hardcoded claim', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(await screen.findByText('0.1.0')).toBeInTheDocument();
    expect(screen.getByText('v1.05')).toBeInTheDocument();
    expect(screen.getByText('ephemeral')).toBeInTheDocument();
    expect(screen.getByText('isaac_records')).toBeInTheDocument();
    // runtime_mode and data_regime are distinct fields that happen to share a value.
    expect(screen.getAllByText('synthetic-only')).toHaveLength(2);
  });

  it('names the boundaries: synthetic data, ephemeral state, no telemetry, no sign-in, record truth', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    expect(screen.getByText(/only unmistakably synthetic data is in scope/i)).toBeInTheDocument();
    expect(screen.getByText(/there is no database/i)).toBeInTheDocument();
    expect(screen.getByText(/no analytics, no usage tracking/i)).toBeInTheDocument();
    expect(screen.getByText(/no sign-in flow, no accounts/i)).toBeInTheDocument();
    expect(screen.getByText(/decided by the deterministic core/i)).toBeInTheDocument();
  });

  /**
   * Anti-overstatement guards. Each of these three sentences replaced a claim
   * the backend falsifies, so they are asserted here to keep the stronger,
   * false version from coming back:
   *   - persistence is a FILESYSTEM workspace, not process memory;
   *   - `ApiKeyAuthMiddleware` is live in-application auth, so restriction is
   *     not necessarily external and this screen cannot tell either way;
   *   - there is NO real-vs-synthetic detector anywhere in the backend.
   */
  it('does not claim a restart clears state, nor that access restriction is always external', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');

    expect(
      screen.getByText(/restarting the backend process does not by itself clear it/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/gone when it restarts/i)).not.toBeInTheDocument();

    expect(screen.getByText(/cannot report whether either is in force/i)).toBeInTheDocument();
    expect(screen.queryByText(/outside the application/i)).not.toBeInTheDocument();
  });

  it('says the app enforces the mode, not the contents, and cannot detect real data', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    expect(screen.getByText(/it cannot tell real data from synthetic/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/refused before anything is read or extracted/i),
    ).not.toBeInTheDocument();
  });

  it('falls back to naming the reported value rather than repeating a claim the API contradicts', async () => {
    stubFetchRoutes({
      [ABOUT_URL]: { body: { ...aboutResponse, data_regime: 'mixed-somehow' } },
      [OPENAPI_URL]: { body: openApiFixture },
    });
    renderSettings();
    expect(
      await screen.findByText(/reports the data regime as "mixed-somehow"/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/only unmistakably synthetic data is in scope/i)).not.toBeInTheDocument();
  });

  it('drops the ephemeral-storage sentence when the backend reports another persistence', async () => {
    stubFetchRoutes({
      [ABOUT_URL]: { body: { ...aboutResponse, persistence: 'durable' } },
      [OPENAPI_URL]: { body: openApiFixture },
    });
    renderSettings();
    expect(await screen.findByText(/reports persistence as "durable"/i)).toBeInTheDocument();
    expect(screen.queryByText(/there is no database/i)).not.toBeInTheDocument();
  });

  it('links into the deeper tabs', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    fireEvent.click(screen.getByRole('button', { name: /browse the api/i }));
    expect(tab('API')).toHaveAttribute('aria-selected', 'true');
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
    expect(alerts[0]).toHaveTextContent(/not running|unreachable/i);
  });
});

// --- Data & Privacy -----------------------------------------------------------

describe('Settings — Data & Privacy', () => {
  it('covers storage, reset, telemetry, models, memory, truth, and access', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Data & Privacy');
    await screen.findByText(/only the synthetic workspace/i);

    expect(screen.getByRole('heading', { name: 'Synthetic data only' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'No real experiment data' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What is stored' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What resets' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'No telemetry or analytics' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'No external model calls' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Project Memory boundary' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Record truth boundary' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Authentication boundary' })).toBeInTheDocument();
  });

  it('says there is no language model and nothing typed leaves the app', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Data & Privacy');
    expect(
      await screen.findByText(/there is no language model in this build/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/never written down or logged/i)).toBeInTheDocument();
  });

  /** The Data & Privacy half of the same three anti-overstatement guards. */
  it('states only what the code enforces about uploads, storage lifetime, and access', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Data & Privacy');
    await screen.findByText(/only the synthetic workspace/i);

    // Governance: refusal is a blanket upload block, NOT real-data detection —
    // the CSV preview and record validator really do read what they are given.
    expect(
      screen.getByText(/nothing in the app inspects that text to judge whether it is real/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/real-looking upload is intercepted/i),
    ).not.toBeInTheDocument();

    // Persistence: filesystem workspace, not process memory.
    expect(
      screen.getByText(/restarting the backend process does not by itself clear it/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/gone when it restarts/i)).not.toBeInTheDocument();

    // Auth: an in-application shared key is possible, so no categorical "any".
    expect(
      screen.getByText(/no way to report whether either restriction is active/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/it stores no\s+credentials/i)).not.toBeInTheDocument();
  });

  it('keeps Project Memory advisory and the schema authoritative', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Data & Privacy');
    expect(
      await screen.findByText(/never a correctness ruling — and it cannot mark a record valid/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/decided only by the official isaac v1\.05 schema/i)).toBeInTheDocument();
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    openTab('Data & Privacy');
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
  });
});

// --- About --------------------------------------------------------------------

describe('Settings — About', () => {
  it('renders app version, build commit, and record schema version from the live endpoint', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('About');
    expect(await screen.findByText('0.1.0')).toBeInTheDocument();
    expect(screen.getByText('fakecommit0000settingsp364')).toBeInTheDocument();
    expect(screen.getByText('v1.05')).toBeInTheDocument();
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
    openTab('About');
    expect(await screen.findByText(/not set \(no build identity injected\)/i)).toBeInTheDocument();
  });

  it('states the truth-vs-memory authority boundary and the no-guessing policy', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('About');
    await screen.findByText('0.1.0');
    expect(screen.getByText(/never by the assistant or by project memory/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing scientific is invented/i)).toBeInTheDocument();
  });

  it('lists in-repo documentation as plain references, not fetched/rendered content', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('About');
    await screen.findByText('0.1.0');
    expect(screen.getByText('CLAUDE.md')).toBeInTheDocument();
    expect(screen.getByText('AGENTS.md')).toBeInTheDocument();
    // Inert names: no links, and the doc names are not anchors.
    expect(screen.getByText('CLAUDE.md').tagName).toBe('CODE');
    expect(screen.getByText(/not served as pages by this app/i)).toBeInTheDocument();
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    openTab('About');
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
  });
});

// --- API browser --------------------------------------------------------------

async function openApiTab() {
  openTab('API');
  return screen.findByText('/api/health');
}

describe('Settings — API browser', () => {
  it('shows a loading state before the fetch resolves', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('API');
    expect(screen.getByText('Loading API documentation…')).toBeInTheDocument();
  });

  it('renders the endpoints grouped, with the method as TEXT', async () => {
    const hits = stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();

    // `/api/about` sorts first, so it is the default selection and appears
    // twice: once in the master list, once in the detail pane.
    expect(screen.getAllByText('/api/about')).toHaveLength(2);
    expect(screen.getByText('/api/experiments/{id}')).toBeInTheDocument();
    expect(screen.getByText('/api/experiments/{id}/answers')).toBeInTheDocument();
    // Group headings come from the segment after /api/ — derived, not hand-maintained.
    expect(screen.getByRole('heading', { name: /^about/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^health/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^experiments/ })).toBeInTheDocument();
    // Method conveyed by TEXT, not color alone.
    expect(screen.getAllByText('GET').length).toBeGreaterThan(0);
    expect(screen.getAllByText('POST').length).toBeGreaterThan(0);
    expect(hits).toEqual(expect.arrayContaining([ABOUT_URL, OPENAPI_URL]));
  });

  it('renders the total endpoint count in the single polite live region', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();
    const count = screen.getByText('4 of 4 endpoints');
    expect(count).toBeInTheDocument();
    expect(count).toHaveAttribute('aria-live', 'polite');
    // Exactly one live region on the loaded surface.
    expect(document.querySelectorAll('[aria-live]')).toHaveLength(1);
  });

  it('shows the OpenAPI contract identity verbatim, never a hand-written duplicate', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();
    expect(
      screen.getByText(/OpenAPI 3\.1\.0 · ISAAC Metadata Assistant — local UI backend · v0\.1\.0/),
    ).toBeInTheDocument();
    expect(screen.getByText(/this app's own\s+generated contract/i)).toBeInTheDocument();
  });

  it('the search box filters endpoints by path/summary, client-side, deterministically', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();

    const search = screen.getByLabelText('Search endpoints') as HTMLInputElement;
    expect(search.tagName).toBe('INPUT');
    expect(search).toHaveAttribute('type', 'search');

    fireEvent.change(search, { target: { value: 'answers' } });

    expect(await screen.findByText('1 of 4 endpoints')).toBeInTheDocument();
    // The one survivor becomes the selection, so it renders in the master list
    // AND in the detail pane; the filtered-out paths render nowhere.
    expect(screen.getAllByText('/api/experiments/{id}/answers')).toHaveLength(2);
    expect(screen.queryByText('/api/health')).not.toBeInTheDocument();
    expect(screen.queryByText('/api/about')).not.toBeInTheDocument();
  });

  it('an unmatched search shows an honest empty state, never fabricated rows', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();

    fireEvent.change(screen.getByLabelText('Search endpoints'), {
      target: { value: 'nonexistent-route-xyz' },
    });

    expect(await screen.findByText(/no endpoints match/i)).toBeInTheDocument();
    expect(screen.getByText('0 of 4 endpoints')).toBeInTheDocument();
  });

  it('is master-detail: one detail pane, not every endpoint expanded at once', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();

    const detail = document.getElementById('settings-api-detail') as HTMLElement;
    expect(detail).not.toBeNull();
    expect(detail).toHaveAttribute('role', 'region');
    expect(detail).toHaveAttribute('tabindex', '-1');
    expect(detail).toHaveAttribute('aria-labelledby', 'settings-api-detail-name');

    // The first visible endpoint is selected by default, and ONLY its detail
    // renders — the other three paths appear once each, in the master list.
    expect(within(detail).getByText('/api/about')).toBeInTheDocument();
    expect(screen.getAllByText('/api/experiments/{id}')).toHaveLength(1);
    // Nothing renders a per-row <details> accordion any more.
    expect(detail.closest('.settings-card')?.querySelectorAll('.api-browser-row details')).toHaveLength(0);
  });

  it('selecting an endpoint renders its detail: summary, description, and parameters', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();

    fireEvent.click(screen.getByText('/api/experiments/{id}'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;

    expect(within(detail).getByText('Get Experiment')).toBeInTheDocument();
    expect(within(detail).getByText(/fetch one experiment detail by id/i)).toBeInTheDocument();
    expect(within(detail).getByText('id')).toBeInTheDocument();
    expect(within(detail).getByText('path')).toBeInTheDocument();
    expect(within(detail).getByText('Yes')).toBeInTheDocument();
  });

  it('an endpoint with no parameters says so honestly rather than showing an empty table', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();

    fireEvent.click(screen.getByText('/api/health'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;
    expect(within(detail).getByText('No parameters.')).toBeInTheDocument();
    expect(within(detail).queryByRole('table')).not.toBeInTheDocument();
  });

  it('renders request body and responses when the contract supplies them, collapsed by default', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();

    fireEvent.click(screen.getByText('/api/experiments/{id}/answers'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;

    expect(within(detail).getByRole('heading', { name: 'Request body' })).toBeInTheDocument();
    expect(within(detail).getByText('Required.')).toBeInTheDocument();
    expect(within(detail).getByRole('heading', { name: 'Responses' })).toBeInTheDocument();
    expect(within(detail).getByText('200')).toBeInTheDocument();
    expect(within(detail).getByText('422')).toBeInTheDocument();
    expect(within(detail).getByText('Validation Error')).toBeInTheDocument();

    // Schemas/examples are collapsible and start closed — no JSON wall.
    const disclosures = Array.from(detail.querySelectorAll('details')) as HTMLDetailsElement[];
    expect(disclosures.length).toBeGreaterThanOrEqual(4); // req schema+example, 200, 422
    disclosures.forEach((d) => expect(d.open).toBe(false));

    const schemaSummary = within(detail).getAllByText('Schema')[0];
    fireEvent.click(schemaSummary);
    expect((schemaSummary.closest('details') as HTMLDetailsElement).open).toBe(true);
    expect(within(detail).getByText(/SyntheticAnswersBody/)).toBeInTheDocument();
    expect(within(detail).getAllByText('Example').length).toBeGreaterThan(0);
  });

  it('resolves a local $ref one level and names what it resolved', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();

    fireEvent.click(screen.getByText('/api/experiments/{id}/answers'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;
    expect(within(detail).getByText('SyntheticFixtureError')).toBeInTheDocument();
  });

  it('shows an unresolvable $ref verbatim instead of inventing a shape for it', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();

    fireEvent.click(screen.getByText('/api/experiments/{id}/answers'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;

    // The 404 response names a schema that is absent from `components`.
    const raw = Array.from(detail.querySelectorAll('pre'))
      .map((p) => p.textContent ?? '')
      .find((t) => t.includes('SyntheticFixtureAbsentTarget'));
    expect(raw).toBeDefined();
    expect(JSON.parse(raw as string)).toEqual({
      $ref: '#/components/schemas/SyntheticFixtureAbsentTarget',
    });

    // ...and it is NOT labelled as a resolved reference, unlike the 422.
    const tags = Array.from(detail.querySelectorAll('.api-browser-reftag')).map(
      (t) => t.textContent,
    );
    expect(tags).toContain('SyntheticFixtureError');
    expect(tags).not.toContain('SyntheticFixtureAbsentTarget');
  });

  it('the endpoint list is a roving-tabindex list: exactly one row is tabbable', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();

    const rows = Array.from(
      document.querySelectorAll('.api-browser-rowbtn'),
    ) as HTMLButtonElement[];
    expect(rows).toHaveLength(4);
    expect(rows.filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1);
    expect(rows[0]).toHaveAttribute('tabindex', '0');

    fireEvent.keyDown(rows[0], { key: 'ArrowDown' });
    const after = Array.from(
      document.querySelectorAll('.api-browser-rowbtn'),
    ) as HTMLButtonElement[];
    expect(after[1]).toHaveAttribute('tabindex', '0');
    expect(after.filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1);
    // Moving the cursor must NOT change the selection.
    expect(after[0]).toHaveAttribute('aria-current', 'true');
  });

  it('rows are native buttons wired to the detail pane', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiTab();
    const rows = Array.from(
      document.querySelectorAll('.api-browser-rowbtn'),
    ) as HTMLButtonElement[];
    rows.forEach((r) => {
      expect(r.tagName).toBe('BUTTON');
      expect(r).toHaveAttribute('aria-controls', 'settings-api-detail');
    });
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    openTab('API');
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
  });
});

// --- safety: no sensitive infrastructure detail, no external URL --------------

/** The SAME forbidden list `apps/api/tests/test_about_and_openapi.py` enforces
 *  on `GET /api/about` — re-asserted here so the client copy cannot reintroduce
 *  what the backend deliberately withholds. */
const FORBIDDEN = [
  'authentik',
  'ingress',
  'k8s',
  'kubernetes',
  'railway.app',
  'vercel.app',
  '127.0.0.1',
  'localhost',
  'secret',
  'password',
  'token',
  'api_key',
  'apikey',
  '/Users/',
  '/home/',
  'C:\\',
];

/** A string that only appears once the tab's own content has rendered. */
const SETTLED: Record<string, string | RegExp> = {
  Overview: '0.1.0',
  'Data & Privacy': /only the synthetic workspace/i,
  About: '0.1.0',
  API: '/api/health',
};

describe('Settings — no sensitive infrastructure detail is rendered', () => {
  it.each(['Overview', 'Data & Privacy', 'About', 'API'])(
    'the %s tab leaks none of the backend-forbidden substrings',
    async (name) => {
      stubFetchRoutes(fullRoutes());
      const { container } = renderSettings();
      openTab(name);
      await screen.findByText(SETTLED[name]);

      const text = (container.textContent ?? '').toLowerCase();
      for (const needle of FORBIDDEN) {
        expect(text.includes(needle.toLowerCase()), `unexpected leak: ${needle}`).toBe(false);
      }
    },
  );

  it('renders no external/CDN URL anywhere (no Swagger UI, no ReDoc, no script tag)', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await screen.findByText('0.1.0');
    openTab('API');
    await screen.findByText('/api/health');

    expect(container.querySelectorAll('script')).toHaveLength(0);
    expect(container.querySelectorAll('iframe')).toHaveLength(0);
    for (const el of Array.from(container.querySelectorAll('[href], [src]'))) {
      const url = el.getAttribute('href') ?? el.getAttribute('src') ?? '';
      expect(/^(https?:)?\/\//.test(url), `external URL rendered: ${url}`).toBe(false);
    }
    expect((container.textContent ?? '').toLowerCase()).not.toContain('swagger');
    expect((container.textContent ?? '').toLowerCase()).not.toContain('redoc');
    expect((container.textContent ?? '').toLowerCase()).not.toContain('unpkg');
  });
});
