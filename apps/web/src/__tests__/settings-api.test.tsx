import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { SettingsPage } from '../screens/SettingsPage';
import { flattenOpenApi, quickStartFacts } from '../lib/apiDocsModel';
import type { ApiOpenApiResponse } from '../lib/types';
import { stubFetchRoutes, aboutResponse, openApiFixture } from '../test/apiFixtures';

/**
 * Settings → API (P36V PR3 slice C): the sub-navigation, the honest API-Keys
 * unavailable state, Quick Start, the refined Endpoint Explorer detail pane, the
 * generated code examples, and Connect an Agent.
 *
 * The two hardest things this file pins down are truthfulness claims that no
 * amount of rendering correctness would catch on its own:
 *
 *  1. API KEYS ARE UNAVAILABLE, and the screen says so. `apps/api/isaac_api/
 *     auth.py` is one process-wide shared credential read from the environment;
 *     grepping `apps/api` finds no operation that creates, lists, revokes or
 *     rotates one, and the generated contract this very tab renders lists every
 *     operation the API has. So there is nothing to manage — and this suite
 *     fails if a key is ever generated, masked, stored, or implied.
 *  2. GROUPING COMES FROM THE DOCUMENT'S REAL TAGS. The predecessor inferred a
 *     group from the path segment after `/api/` while asserting in a docstring
 *     that the backend assigned no tags. It now does. The group names and their
 *     ORDER asserted below are obtainable only from the document's `tags` array,
 *     so a revert to segment inference fails here.
 *
 * The forbidden-infrastructure-substring guard for both sub-tabs lives in
 * `settings-page.test.tsx`, alongside the same guard for the other three tabs.
 */

const ABOUT_URL = 'GET /api/about';
const OPENAPI_URL = 'GET /api/openapi';

const fixture = openApiFixture as unknown as ApiOpenApiResponse;
const ROWS = flattenOpenApi(fixture);
const FACTS = quickStartFacts(fixture, ROWS);

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

function routes() {
  return { [ABOUT_URL]: { body: aboutResponse }, [OPENAPI_URL]: { body: openApiFixture } };
}

/** Open Settings on the API tab, whose default sub-tab is API Keys. */
async function openApiKeys() {
  stubFetchRoutes(routes());
  const view = renderSettings();
  fireEvent.click(screen.getByRole('tab', { name: 'API' }));
  await screen.findByText('No keys to show.');
  return view;
}

/** Open Settings on API → Documentation. */
async function openDocumentation() {
  const view = await openApiKeys();
  fireEvent.click(screen.getByRole('tab', { name: 'Documentation' }));
  await screen.findByRole('heading', { name: 'Quick Start' });
  return view;
}

const detailPane = () => document.getElementById('settings-api-detail') as HTMLElement;

const groupHeadings = () =>
  Array.from(document.querySelectorAll('.api-browser-group-heading')).map((h) =>
    (h.firstChild?.textContent ?? '').trim(),
  );

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn() } });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// --- sub-navigation -----------------------------------------------------------

describe('Settings → API — sub-navigation', () => {
  it('adds exactly two sub-tabs inside the API tab, not a new sidebar destination', async () => {
    await openApiKeys();
    const list = screen.getByRole('tablist', { name: 'API sections' });
    expect(within(list).getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'API Keys',
      'Documentation',
    ]);
    // The page-level tablist is untouched: still four destinations.
    const pageTabs = screen.getByRole('tablist', { name: 'Settings sections' });
    expect(within(pageTabs).getAllByRole('tab')).toHaveLength(4);
  });

  it('uses the same accessible tab contract as the page tabs', async () => {
    await openApiKeys();
    const keys = screen.getByRole('tab', { name: 'API Keys' });
    const docs = screen.getByRole('tab', { name: 'Documentation' });

    expect(keys).toHaveAttribute('aria-selected', 'true');
    expect(keys).toHaveAttribute('aria-controls', 'settings-api-subpanel-keys');
    expect(keys).toHaveAttribute('tabindex', '0');
    expect(docs).toHaveAttribute('aria-selected', 'false');
    expect(docs).not.toHaveAttribute('aria-controls');
    expect(docs).toHaveAttribute('tabindex', '-1');

    const panel = document.getElementById('settings-api-subpanel-keys') as HTMLElement;
    expect(panel).toHaveAttribute('role', 'tabpanel');
    expect(panel).toHaveAttribute('aria-labelledby', 'settings-api-subtab-keys');
  });

  it('Arrow / Home / End move the sub-tab selection', async () => {
    await openApiKeys();
    fireEvent.keyDown(screen.getByRole('tab', { name: 'API Keys' }), { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: 'Documentation' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Documentation' }), { key: 'Home' });
    expect(screen.getByRole('tab', { name: 'API Keys' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(screen.getByRole('tab', { name: 'API Keys' }), { key: 'End' });
    expect(screen.getByRole('tab', { name: 'Documentation' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('only Documentation issues/consumes the contract fetch state', async () => {
    stubFetchRoutes(routes());
    renderSettings();
    fireEvent.click(screen.getByRole('tab', { name: 'API' }));
    // API Keys needs no data, so it never shows a loading panel.
    expect(screen.queryByText('Loading API documentation…')).not.toBeInTheDocument();
    expect(await screen.findByText('No keys to show.')).toBeInTheDocument();
  });
});

// --- API Keys: the honest unavailable state -----------------------------------

describe('Settings → API → API Keys — an honest unavailable state', () => {
  it('renders all four regions, visually complete rather than broken', async () => {
    await openApiKeys();
    const panel = document.getElementById('settings-api-subpanel-keys') as HTMLElement;
    expect(
      Array.from(panel.querySelectorAll('h3')).map((h) => h.textContent),
    ).toEqual(['API Access', 'Create API Key', 'Your API Keys', 'What Would Be Required']);
    // Not an error state and not a fake loading failure: no alert, and nothing
    // claims something went wrong or invites a retry. (The copy DOES say
    // "nothing failed to load" — that is the opposite claim, so the negatives
    // below are phrased to catch a real failure claim, not that reassurance.)
    expect(within(panel).queryByRole('alert')).not.toBeInTheDocument();
    expect(panel.textContent).not.toMatch(
      /something went wrong|could not load|try again|retry|temporarily unavailable/i,
    );
  });

  it('answers the four capability questions, classifying key management as unavailable', async () => {
    await openApiKeys();
    const panel = document.getElementById('settings-api-subpanel-keys') as HTMLElement;
    expect(
      Array.from(panel.querySelectorAll('.api-keys-row dt')).map((dt) => dt.textContent),
    ).toEqual([
      'What an API Key Would Enable',
      'Authentication That Applies Today',
      'Key Management',
      'External Agent Access',
    ]);
    expect(
      within(panel).getByText(/Unavailable\. This API has no operation that creates, lists, revokes, or rotates a credential/i),
    ).toBeInTheDocument();
    expect(
      within(panel).getByText(/One credential belonging to the whole deployment/i),
    ).toBeInTheDocument();
    expect(
      within(panel).getByText(/Not through anything you can obtain here/i),
    ).toBeInTheDocument();
    // It never claims keys are available.
    expect(panel.textContent).not.toMatch(/your key is|key created|copy your key/i);
  });

  it('the Create control is really disabled and announces WHY', async () => {
    await openApiKeys();
    const create = screen.getByRole('button', { name: /Create API Key/i });
    expect(create).toBeDisabled();

    const describedBy = create.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    const reason = document.getElementById(describedBy as string) as HTMLElement;
    expect(reason).not.toBeNull();
    expect(reason.textContent).toMatch(
      /the API has no operation that issues a credential, so there is nothing this button could call/i,
    );
    // The reason is also always visible, not only programmatic.
    expect(reason.closest('details')).toBeNull();
  });

  it('generates no key, masks no key, and offers nothing to reveal or copy', async () => {
    await openApiKeys();
    const panel = document.getElementById('settings-api-subpanel-keys') as HTMLElement;
    const text = panel.textContent ?? '';

    // No key-shaped string anywhere (no 24+ run of credential characters).
    expect(text).not.toMatch(/[A-Za-z0-9_-]{24,}/);
    // No masked placeholder standing in for a real value.
    expect(text).not.toMatch(/[•*·]{4,}/);
    expect(text).not.toMatch(/sk-|\bBearer\s+\S/);
    // Nothing to reveal, regenerate, or copy — those controls do not exist.
    expect(panel.querySelectorAll('input')).toHaveLength(0);
    expect(panel.querySelectorAll('pre')).toHaveLength(0);
    expect(within(panel).queryByRole('button', { name: /copy|reveal|show|regenerate|rotate|revoke/i }))
      .not.toBeInTheDocument();
    // The only button on this surface besides the disabled one is the nav link.
    expect(
      within(panel).getAllByRole('button').map((b) => b.textContent?.trim()),
    ).toEqual(['Create API Key', 'Read the API Documentation']);
  });

  it('writes nothing to browser storage or cookies', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    const removeItem = vi.spyOn(Storage.prototype, 'removeItem');
    const cookieBefore = document.cookie;

    await openApiKeys();
    // ...and after interacting with everything interactive on the surface.
    fireEvent.click(screen.getByRole('button', { name: /Create API Key/i }));

    expect(setItem).not.toHaveBeenCalled();
    expect(removeItem).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(document.cookie).toBe(cookieBefore);
  });

  it('shows a polished empty state that says the list is empty BY DESIGN', async () => {
    await openApiKeys();
    expect(screen.getByText('No keys to show.')).toBeInTheDocument();
    expect(
      screen.getByText(/empty by design, not by circumstance — nothing failed to load/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no place in this build where a key could be created or kept/i),
    ).toBeInTheDocument();
  });

  it('states the backend and security contract that would be required first', async () => {
    await openApiKeys();
    const items = Array.from(document.querySelectorAll('.api-keys-requirements li')).map(
      (li) => li.textContent ?? '',
    );
    expect(items).toHaveLength(5);
    expect(items.join(' ')).toMatch(/holding a hash rather than the value/i);
    expect(items.join(' ')).toMatch(/Per-key identity/i);
    expect(items.join(' ')).toMatch(/Revocation and expiry/i);
    expect(items.join(' ')).toMatch(/Scopes/i);
    expect(
      screen.getByText(/belong to a later, separately authorized phase/i),
    ).toBeInTheDocument();
  });

  it('links into Documentation', async () => {
    await openApiKeys();
    fireEvent.click(screen.getByRole('button', { name: /Read the API Documentation/i }));
    expect(screen.getByRole('tab', { name: 'Documentation' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(await screen.findByRole('heading', { name: 'Quick Start' })).toBeInTheDocument();
  });
});

// --- Quick Start --------------------------------------------------------------

describe('Settings → API → Documentation — Quick Start', () => {
  it('reports the base URL as a RELATIVE path, never an origin', async () => {
    await openDocumentation();
    const rows = Array.from(document.querySelectorAll('.api-quickstart-row'));
    const baseRow = rows.find((r) => r.querySelector('dt')?.textContent === 'Base URL') as HTMLElement;
    expect(baseRow).toBeTruthy();
    expect(within(baseRow).getByText('/api')).toBeInTheDocument();
    expect(FACTS.basePath).toBe('/api');
    expect(baseRow.textContent).toMatch(/Relative to the origin serving this page/i);
    // No scheme or host literal anywhere on the whole sub-tab.
    const panel = document.getElementById('settings-api-subpanel-docs') as HTMLElement;
    expect(panel.textContent ?? '').not.toMatch(/https?:\/\//);
  });

  it('reports only values the running app can actually report', async () => {
    await openDocumentation();
    const rows = Array.from(document.querySelectorAll('.api-quickstart-row')).map((r) => ({
      label: r.querySelector('dt')?.textContent,
      text: r.textContent ?? '',
    }));
    expect(rows.map((r) => r.label)).toEqual([
      'Base URL',
      'API Version',
      'Authentication',
      'Content Type',
    ]);
    expect(rows[1].text).toContain(`v${FACTS.apiVersion}`);
    expect(rows[1].text).toContain(FACTS.openApiVersion);
    expect(rows[2].text).toContain('Authorization: Bearer');
    expect(rows[2].text).toContain(
      `${FACTS.authRequiredCount} of ${FACTS.operationCount} operations document a 401`,
    );
    expect(rows[3].text).toContain('application/json');
    // Provenance: the contract's own identity line, verbatim.
    expect(screen.getByText(FACTS.contractLine)).toBeInTheDocument();
  });

  it('proposes a first request the reader can actually make, and says why that one', async () => {
    await openDocumentation();
    const first = document.querySelector('.api-quickstart-first') as HTMLElement;
    expect(first).toBeTruthy();
    expect(within(first).getByText('/api/health')).toBeInTheDocument();
    expect(within(first).getByText('GET')).toBeInTheDocument();
    expect(first.querySelector('pre')?.textContent).toBe('curl "$ISAAC_BASE_URL/api/health"');
    expect(first.textContent).toMatch(/contract documents no 401 for it/i);
    expect(first.textContent).toMatch(/stands for the origin serving this page/i);
  });

  it('the first-request sample is copyable, with an accessible name and a spoken confirmation', async () => {
    await openDocumentation();
    const first = document.querySelector('.api-quickstart-first') as HTMLElement;
    const copy = within(first).getByRole('button', { name: 'Copy the first-request sample' });
    fireEvent.click(copy);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      'curl "$ISAAC_BASE_URL/api/health"',
    );
    // Non-visual signal: a polite status region, not colour or an icon alone.
    const status = document.querySelector('[role="status"]') as HTMLElement;
    expect(status.textContent).toBe('Copied the first-request sample.');
    // Visual signal too.
    expect(within(first).getByRole('button', { name: 'Copied the first-request sample' })).toBeInTheDocument();
  });

  it('links to API Keys and opens Connect an Agent', async () => {
    await openDocumentation();
    const connect = document.querySelector('details.api-connect') as HTMLDetailsElement;
    expect(connect.open).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Connect an Agent' }));
    expect((document.querySelector('details.api-connect') as HTMLDetailsElement).open).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'API Keys' }));
    expect(screen.getByRole('tab', { name: 'API Keys' })).toHaveAttribute('aria-selected', 'true');
  });
});

// --- Endpoint Explorer: tag grouping + detail ---------------------------------

describe('Settings → API → Documentation — Endpoint Explorer', () => {
  it('groups by the document’s REAL tags, in the document’s registration order', async () => {
    await openDocumentation();
    expect(groupHeadings()).toEqual([
      'Health & Meta',
      'Experiments',
      'Drafts & Answers',
      'Uploads',
      'Validation',
      'Other Operations',
    ]);
    // A registered tag carried by no operation creates no group.
    expect(groupHeadings()).not.toContain('Schema & Vocabulary');
    // The stale path-segment groups appear nowhere.
    for (const stale of ['health', 'about', 'experiments', 'answers', 'uploads', 'validate']) {
      expect(groupHeadings()).not.toContain(stale);
    }
    // Registration order is not alphabetical, so this can only come from `tags`.
    expect([...groupHeadings()].sort()).not.toEqual(groupHeadings());
  });

  it('counts every operation and reports the number of groups', async () => {
    await openDocumentation();
    expect(screen.getByText(`${ROWS.length} of ${ROWS.length} endpoints`)).toBeInTheDocument();
    expect(screen.getByText('6 groups')).toBeInTheDocument();
  });

  it('search matches path, summary, group and method', async () => {
    await openDocumentation();
    const search = screen.getByLabelText('Search endpoints') as HTMLInputElement;

    fireEvent.change(search, { target: { value: 'drafts' } });
    expect(await screen.findByText(`1 of ${ROWS.length} endpoints`)).toBeInTheDocument();
    expect(groupHeadings()).toEqual(['Drafts & Answers']);

    fireEvent.change(search, { target: { value: 'liveness' } });
    expect(await screen.findByText(`1 of ${ROWS.length} endpoints`)).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'nothing-here-xyz' } });
    expect(await screen.findByText(/no endpoints match/i)).toBeInTheDocument();
    expect(screen.getByText(`0 of ${ROWS.length} endpoints`)).toBeInTheDocument();
  });

  it('names the selected operation’s group and renders that tag’s registered description', async () => {
    await openDocumentation();
    // Default selection is the first row: GET /api/about, in Health & Meta.
    expect(within(detailPane()).getByText('Health & Meta')).toBeInTheDocument();
    expect(
      within(detailPane()).getByText(/Liveness, deployment identity, and this API/i),
    ).toBeInTheDocument();

    // A registered tag with NO description renders the chip and invents nothing.
    fireEvent.click(screen.getByText('/api/experiments/{id}'));
    expect(within(detailPane()).getByText('Experiments')).toBeInTheDocument();
    expect(detailPane().querySelector('.api-browser-detail-groupdesc')).toBeNull();
  });

  it('renders Purpose, the authentication requirement, parameters and both response groups', async () => {
    await openDocumentation();
    fireEvent.click(screen.getByText('/api/experiments/{id}'));
    const detail = detailPane();

    expect(
      Array.from(detail.querySelectorAll('h5')).map((h) => h.textContent),
    ).toEqual([
      'Purpose',
      'Authentication',
      'Parameters',
      'Request Body',
      'Responses',
      'Error States',
    ]);
    expect(within(detail).getByText(/fetch one experiment detail by id/i)).toBeInTheDocument();
    expect(
      within(detail).getByText(/A credential is required when this deployment enables authentication/i),
    ).toBeInTheDocument();

    // Parameters now carry the contract's own descriptions.
    const paramHeaders = Array.from(detail.querySelectorAll('th')).map((th) => th.textContent);
    expect(paramHeaders).toEqual(['Name', 'In', 'Required', 'Description']);
    expect(within(detail).getByText('The id of an experiment.')).toBeInTheDocument();

    // 200 under Responses; 401/404 under Error States — never mixed.
    const sections = Array.from(detail.querySelectorAll('.api-browser-section'));
    const responses = sections.find((s) => s.querySelector('h5')?.textContent === 'Responses');
    const errors = sections.find((s) => s.querySelector('h5')?.textContent === 'Error States');
    expect(Array.from(responses!.querySelectorAll('.api-browser-status')).map((s) => s.textContent)).toEqual(['200']);
    expect(Array.from(errors!.querySelectorAll('.api-browser-status')).map((s) => s.textContent)).toEqual(['401', '404']);
  });

  it('states the authentication requirement honestly for the one operation with no 401', async () => {
    await openDocumentation();
    fireEvent.click(within(document.querySelector('.api-browser-list') as HTMLElement).getByText('/api/health'));
    expect(
      within(detailPane()).getByText(/contract documents no 401 for this operation, so it stays reachable without a credential/i),
    ).toBeInTheDocument();
  });

  it('says a write operation declares NO request-body schema instead of inventing one', async () => {
    await openDocumentation();
    fireEvent.click(screen.getByText('/api/validate/record'));
    const detail = detailPane();
    expect(
      within(detail).getByText(
        /The contract declares no request body for this operation\. Where one is expected, it is described under Purpose rather than as a schema/i,
      ),
    ).toBeInTheDocument();
    // No fabricated media type or schema disclosure for it.
    expect(detail.querySelectorAll('.api-browser-mediatype')).toHaveLength(0);
  });

  it('renders a documented-but-never-produced 200 in the contract’s own words', async () => {
    await openDocumentation();
    fireEvent.click(screen.getByText('/api/uploads'));
    const detail = detailPane();
    // The 200 is listed, and its description says it never happens. No heading
    // anywhere calls it a success.
    expect(
      within(detail).getByText(/Not produced by this operation — every request is refused with the 403\./i),
    ).toBeInTheDocument();
    expect(within(detail).getByText(/This is the only outcome\./i)).toBeInTheDocument();
    expect(Array.from(detail.querySelectorAll('h5')).map((h) => h.textContent)).not.toContain('Success');
    expect(detail.textContent).not.toMatch(/successful response/i);
  });

  it('keeps raw JSON behind a Technical Schema disclosure, collapsed', async () => {
    await openDocumentation();
    fireEvent.click(screen.getByText('/api/experiments/{id}/answers'));
    const detail = detailPane();

    const disclosures = Array.from(detail.querySelectorAll('details')) as HTMLDetailsElement[];
    expect(disclosures.length).toBeGreaterThanOrEqual(4);
    disclosures.forEach((d) => expect(d.open).toBe(false));

    const schema = within(detail).getAllByText('Technical Schema')[0];
    expect(within(detail).queryByText('Schema')).not.toBeInTheDocument();
    fireEvent.click(schema);
    expect((schema.closest('details') as HTMLDetailsElement).open).toBe(true);
    expect(within(detail).getByText(/SyntheticAnswersBody/)).toBeInTheDocument();
  });
});

// --- generated code examples ---------------------------------------------------

describe('Settings → API → Documentation — code examples', () => {
  async function openSamples() {
    await openDocumentation();
    fireEvent.click(screen.getByText('/api/experiments/{id}/answers'));
    const details = detailPane().querySelector('details.api-samples') as HTMLDetailsElement;
    expect(details.open).toBe(false);
    fireEvent.click(details.querySelector('summary') as HTMLElement);
    return details;
  }

  it('is collapsed by default and offers three compact language tabs', async () => {
    const samples = await openSamples();
    const list = within(samples).getByRole('tablist', { name: 'Code example language' });
    expect(within(list).getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'cURL',
      'Python',
      'JavaScript',
    ]);
    expect(within(list).getAllByRole('tab').filter((t) => t.getAttribute('tabindex') === '0')).toHaveLength(1);
    expect(within(list).getByRole('tab', { name: 'cURL' })).toHaveAttribute('aria-selected', 'true');
  });

  it('shows one language at a time, generated from the endpoint contract', async () => {
    const samples = await openSamples();
    const code = () => samples.querySelector('pre')?.textContent ?? '';

    expect(code()).toContain('curl -X POST "$ISAAC_BASE_URL/api/experiments/{id}/answers"');
    expect(code()).toContain('-H "Authorization: Bearer $ISAAC_API_CREDENTIAL"');
    expect(code()).toContain('-H "Content-Type: application/json"');
    expect(code()).toContain('--data "$ISAAC_REQUEST_BODY"');

    fireEvent.click(within(samples).getByRole('tab', { name: 'Python' }));
    expect(code()).toContain('import urllib.request');
    expect(code()).toContain('/api/experiments/{id}/answers');
    expect(code()).not.toContain('curl');

    fireEvent.click(within(samples).getByRole('tab', { name: 'JavaScript' }));
    expect(code()).toContain('await fetch(url');
    expect(code()).not.toContain('import urllib.request');
  });

  it('references no SDK, no dependency, and no host', async () => {
    const samples = await openSamples();
    for (const label of ['cURL', 'Python', 'JavaScript']) {
      fireEvent.click(within(samples).getByRole('tab', { name: label }));
      const code = samples.querySelector('pre')?.textContent ?? '';
      expect(code).not.toMatch(/pip install|npm install|axios|requests\.|isaac[-_]client|@isaac/);
      expect(code).not.toMatch(/https?:\/\/|127\.0\.0\.1/);
      expect(code.toLowerCase()).not.toContain('localhost');
    }
    expect(samples.textContent).toMatch(/Standard library only — no client library exists for this API/i);
  });

  it('the code panel is a real tabpanel wired to its tab', async () => {
    const samples = await openSamples();
    const panel = within(samples).getByRole('tabpanel');
    const tab = within(samples).getByRole('tab', { name: 'cURL' });
    expect(tab).toHaveAttribute('aria-controls', panel.id);
    expect(panel).toHaveAttribute('aria-labelledby', tab.id);
  });

  it('copies the shown sample, naming it, with a spoken confirmation', async () => {
    const samples = await openSamples();
    fireEvent.click(within(samples).getByRole('tab', { name: 'Python' }));
    const copy = within(samples).getByRole('button', { name: 'Copy the Python sample' });
    fireEvent.click(copy);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('import urllib.request'),
    );
    expect((document.querySelector('[role="status"]') as HTMLElement).textContent).toBe(
      'Copied the Python sample.',
    );
  });

  it('adds no second live region per copy button', async () => {
    await openSamples();
    // One `aria-live` (the result count) plus ONE shared `role="status"`.
    expect(document.querySelectorAll('[aria-live]')).toHaveLength(1);
    expect(document.querySelectorAll('[role="status"]')).toHaveLength(1);
  });
});

// --- Connect an Agent ----------------------------------------------------------

describe('Settings → API → Documentation — Connect an Agent', () => {
  async function openConnect() {
    await openDocumentation();
    const connect = document.querySelector('details.api-connect') as HTMLDetailsElement;
    fireEvent.click(connect.querySelector('summary') as HTMLElement);
    return connect;
  }

  it('is a collapsed disclosure whose summary keeps the real heading', async () => {
    await openDocumentation();
    const connect = document.querySelector('details.api-connect') as HTMLDetailsElement;
    expect(connect.open).toBe(false);
    const heading = screen.getByRole('heading', { name: 'Connect an Agent' });
    expect(heading.tagName).toBe('H3');
    expect(heading.closest('summary')).not.toBeNull();
  });

  it('carries exactly the eight required sections, in order', async () => {
    const connect = await openConnect();
    expect(
      Array.from(connect.querySelectorAll('h4')).map((h) => h.textContent),
    ).toEqual([
      'Choose an Endpoint',
      'Set the Base URL',
      'Configure Authentication',
      'Send Structured Requests',
      'Respect Read and Write Boundaries',
      'Validate Responses',
      'Handle Errors',
      'Protect Credentials',
    ]);
  });

  it('states the advisory / authoritative / memory boundaries accurately', async () => {
    const connect = await openConnect();
    const text = (connect.textContent ?? '').replace(/\s+/g, ' ');
    expect(text).toMatch(/official ISAAC schema and the deterministic validators are the only authority/i);
    expect(text).toMatch(/Assistant operations are advisory/i);
    expect(text).toMatch(/Project Memory returns leads to confirm against the cited files, and is not record truth/i);
    expect(text).toMatch(/Writes change a record and require explicit user intent/i);
  });

  it('states the credential-hygiene rules', async () => {
    const connect = await openConnect();
    const text = (connect.textContent ?? '').replace(/\s+/g, ' ');
    expect(text).toMatch(/Never place it in a prompt, in source control, in a log line, or in a screenshot/i);
    expect(text).toMatch(/never echo it back in output/i);
    expect(text).toMatch(/API keys are unavailable here .* because this API has no operation that issues one/i);
  });

  it('states the hosted-access caveat WITHOUT naming any provider or host', async () => {
    const connect = await openConnect();
    const text = (connect.textContent ?? '').replace(/\s+/g, ' ');
    // The substance: a browser session is not a headless credential.
    expect(text).toMatch(
      /Signing in through a deployment's identity layer with a browser is not the same thing as headless authentication/i,
    );
    expect(text).toMatch(/an interactive session, not a credential a program can present on its own/i);
    // Provider-neutral: no vendor, no host, no platform name.
    const lower = (connect.textContent ?? '').toLowerCase();
    for (const needle of ['authentik', 'ingress', 'k8s', 'kubernetes', 'vercel', 'railway', 'oauth', 'saml', 'sso']) {
      expect(lower.includes(needle), `named provider or protocol: ${needle}`).toBe(false);
    }
  });

  it('derives its authentication and error facts from the contract', async () => {
    const connect = await openConnect();
    const text = (connect.textContent ?? '').replace(/\s+/g, ' ');
    expect(text).toContain(
      `${FACTS.authRequiredCount} of ${FACTS.operationCount} operations document a 401`,
    );
    expect(text).toContain(FACTS.errorCodes.join(', '));
    expect(text).toContain(FACTS.requestMediaTypes.join(', '));
  });

  it('states no universal rule about unnamed request-body fields', async () => {
    // P36V — this clause used to say an unnamed key "is dropped rather than
    // interpreted". FALSE for a mutating operation: `DemoResetRequest` sets
    // extra="forbid", so POST /api/demo/reset rejects an unnamed key with 422,
    // and that operation's own generated description — rendered on THIS tab two
    // sections above — says "Any other field is rejected." One screen, two
    // contradictory rules. Extra-field handling varies per model and the document
    // exposes no signal a caller could read off, so the guide must not generalise.
    const connect = await openConnect();
    const text = (connect.textContent ?? '').replace(/\s+/g, ' ');
    expect(text).not.toMatch(/is dropped rather than interpreted/i);
    expect(text).not.toMatch(/unnamed (key|field)s? (is|are) (dropped|ignored)\b/i);
    // …and it must still tell the reader where the real answer lives.
    expect(text).toMatch(/reject an unnamed key outright and others ignore it/i);
    expect(text).toMatch(/Endpoint Explorer is the authority/i);
  });

  it('invents no capability this build lacks', async () => {
    const connect = await openConnect();
    const lower = (connect.textContent ?? '').toLowerCase();
    for (const needle of ['sdk', 'rate limit', 'scope', 'streaming', 'webhook', 'refresh']) {
      expect(lower.includes(needle), `invented capability: ${needle}`).toBe(false);
    }
  });
});

// --- accessibility of the whole API tab ---------------------------------------

describe('Settings → API — accessibility', () => {
  it('never skips a heading level on either sub-tab', async () => {
    for (const open of [openApiKeys, openDocumentation]) {
      const view = await open();
      const levels = Array.from(view.container.querySelectorAll('h1, h2, h3, h4, h5, h6')).map(
        (h) => Number(h.tagName[1]),
      );
      expect(levels.length).toBeGreaterThan(0);
      for (let i = 1; i < levels.length; i += 1) {
        expect(levels[i] - levels[i - 1], `outline: ${levels.join(',')}`).toBeLessThanOrEqual(1);
      }
      view.unmount();
    }
  });

  it('renders no external URL, script, or iframe on either sub-tab', async () => {
    for (const open of [openApiKeys, openDocumentation]) {
      const view = await open();
      expect(view.container.querySelectorAll('script')).toHaveLength(0);
      expect(view.container.querySelectorAll('iframe')).toHaveLength(0);
      for (const el of Array.from(view.container.querySelectorAll('[href], [src]'))) {
        const url = el.getAttribute('href') ?? el.getAttribute('src') ?? '';
        expect(/^(https?:)?\/\//.test(url), `external URL: ${url}`).toBe(false);
      }
      const lower = (view.container.textContent ?? '').toLowerCase();
      for (const needle of ['swagger', 'redoc', 'unpkg']) expect(lower).not.toContain(needle);
      view.unmount();
    }
  });

  it('the endpoint list keeps its roving tabindex across the tag groups', async () => {
    await openDocumentation();
    const rows = () => Array.from(document.querySelectorAll('.api-browser-rowbtn')) as HTMLButtonElement[];
    expect(rows()).toHaveLength(ROWS.length);
    expect(rows().filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1);
    expect(rows()[0]).toHaveAttribute('tabindex', '0');

    fireEvent.keyDown(rows()[0], { key: 'End' });
    expect(rows()[ROWS.length - 1]).toHaveAttribute('tabindex', '0');
    expect(rows().filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1);
    // Moving the cursor across a group boundary still does not select.
    expect(rows()[0]).toHaveAttribute('aria-current', 'true');
  });
});
