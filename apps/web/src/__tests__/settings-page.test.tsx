import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { SettingsPage } from '../screens/SettingsPage';
import { titleCase } from '../lib/labels';
import {
  ABOUT_RESPONSE_FIELDS,
  REPO_DOCS,
  SETTINGS_SOURCE_ENDPOINTS,
  settingsAboutCopy,
  settingsConcepts,
  settingsFactsFrom,
} from '../lib/settingsContent';
import {
  stubFetchRoutes,
  stubFetchDown,
  aboutResponse,
  aboutResponseNoCommit,
  openApiFixture,
} from '../test/apiFixtures';

/**
 * P36.4 gave Settings two functional sections; P36R Slice 9 reorganised the
 * surface into four local page tabs — Overview · Data & Privacy · About · API —
 * and turned the API section into a master-detail browser over `GET /api/openapi`
 * (the app's real generated contract: no CDN, no Swagger UI / ReDoc).
 *
 * P36V PR3 slice B deduplicated the copy: six claims were authored two or three
 * times across the tabs (two of them character-for-character), so every
 * canonical definition now lives once in `lib/settingsContent.ts` and Overview
 * renders only ONE-LINE summaries of them. The anti-regression guard for that
 * whole slice is the "appears exactly once" suite at the bottom of this file —
 * it counts each canonical string across all four tabs and requires exactly 1.
 *
 * Guards preserved from P36.4/P36R: the honest `not set` build-commit branch,
 * the truth-vs-memory + no-guessing copy, the repository doc names rendered as
 * inert `<code>`, the HTTP method conveyed by TEXT, the honest `No parameters.`
 * state, and — unweakened — the forbidden-infrastructure-substring list.
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

/** Rendered text and authored strings compared on equal terms: JSX collapses a
 *  wrapped literal to single spaces, so both sides are normalized the same way. */
const norm = (s: string) => s.replace(/\s+/g, ' ').trim();

function countOccurrences(haystack: string, needle: string): number {
  let count = 0;
  let from = 0;
  for (;;) {
    const at = haystack.indexOf(needle, from);
    if (at < 0) return count;
    count += 1;
    from = at + needle.length;
  }
}

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
    // P36V PR3: Build Commit joined the runtime snapshot — SHORT sha only.
    expect(screen.getByText('fakecommit00')).toBeInTheDocument();
  });

  /**
   * P36V PR3 — Overview is a SUMMARY. Each boundary appears as its one-line
   * `summary`, and the canonical definitions (asserted in the Data & Privacy
   * suite, and counted in the "appears exactly once" suite) render nowhere here.
   */
  it('names every boundary as a one-line summary, not a second copy of the definition', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await screen.findByText('0.1.0');

    const concepts = settingsConcepts(settingsFactsFrom(aboutResponse));
    const text = norm(container.textContent ?? '');
    for (const concept of concepts) {
      expect(text, `Overview must summarize "${concept.heading}"`).toContain(norm(concept.summary));
      expect(text, `Overview must NOT define "${concept.heading}"`).not.toContain(
        norm(concept.detail),
      );
    }
    // Every boundary is labelled, so a summary is never an orphan sentence.
    for (const concept of concepts) {
      expect(screen.getByText(concept.heading)).toBeInTheDocument();
    }
  });

  /**
   * Anti-overstatement guards. Each of these sentences replaced a claim the
   * backend falsifies, so they are asserted here to keep the stronger, false
   * version from coming back:
   *   - persistence is a FILESYSTEM workspace, not process memory (Overview says
   *     "no database", the filesystem detail lives in Data & Privacy);
   *   - `ApiKeyAuthMiddleware` is live in-application auth, so restriction is
   *     not necessarily external and this screen cannot tell either way;
   *   - there is NO real-vs-synthetic detector anywhere in the backend.
   */
  it('does not claim a restart clears state, nor that access restriction is always external', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');

    expect(screen.getByText(/no database — the workspace is files on the server/i)).toBeInTheDocument();
    expect(screen.queryByText(/gone when it restarts/i)).not.toBeInTheDocument();
    // The filesystem-lifetime detail is Data & Privacy's, and only its.
    expect(
      screen.queryByText(/restarting the backend process does not by itself clear it/i),
    ).not.toBeInTheDocument();

    expect(
      screen.getByText(/this screen cannot report whether access is restricted/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/outside the application/i)).not.toBeInTheDocument();
  });

  /**
   * Authentication has no STATUS row and never will: the shared key is
   * configured where the browser cannot see it, so Overview states the
   * uncertainty instead of an "active"/"inactive" claim it cannot verify.
   */
  it('never claims authentication is active or inactive', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await screen.findByText('0.1.0');

    const labels = Array.from(container.querySelectorAll('.settings-figure dt')).map(
      (dt) => dt.textContent,
    );
    expect(labels).toEqual([
      'App Version',
      'Build Commit',
      'Record Schema',
      'Runtime Mode',
      'Data Regime',
      'Persistence',
      'Core',
    ]);
    const text = norm(container.textContent ?? '').toLowerCase();
    expect(text).not.toContain('authentication: active');
    expect(text).not.toContain('authentication is active');
    expect(text).not.toContain('access is restricted by');
    expect(text).not.toContain('unrestricted');
  });

  it('says the app enforces the mode, not the contents, and cannot detect real data', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    expect(screen.getByText(/cannot tell real data from synthetic/i)).toBeInTheDocument();
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
  it('covers storage, reset, telemetry, models, memory, truth, and access — in Title Case', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Data & Privacy');
    await screen.findByText(/only the synthetic workspace/i);

    const concepts = settingsConcepts(settingsFactsFrom(aboutResponse));
    expect(concepts.map((c) => c.heading)).toEqual([
      'Synthetic Data Only',
      'No Real Experiment Data',
      'What Is Stored',
      'What Resets',
      'No Telemetry or Analytics',
      'No External Model Calls',
      'Project Memory Boundary',
      'Record Truth Boundary',
      'Authentication Boundary',
    ]);
    for (const concept of concepts) {
      // The canonical definition is HERE, under its own heading, exactly once.
      const heading = screen.getByRole('heading', { name: concept.heading });
      expect(heading).toBeInTheDocument();
      expect(heading.tagName).toBe('H3');
      expect(screen.getByText(concept.detail)).toBeInTheDocument();
    }
  });

  /** Data & Privacy owns the paragraphs Overview used to duplicate verbatim or
   *  paraphrase: the synthetic-data claim, telemetry, and authentication. */
  it('is the one canonical home of the definitions Overview only summarizes', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Data & Privacy');
    await screen.findByText(/only the synthetic workspace/i);

    expect(screen.getByText(/only unmistakably synthetic data is in scope/i)).toBeInTheDocument();
    expect(screen.getByText(/there is no database/i)).toBeInTheDocument();
    expect(screen.getByText(/no analytics, no usage tracking/i)).toBeInTheDocument();
    expect(screen.getByText(/no accounts, no sign-in, and no user profiles/i)).toBeInTheDocument();
    expect(
      screen.getByText(/decided only by the official isaac v1\.05 schema/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no advisory surface — not the assistant, not project memory/i),
    ).toBeInTheDocument();
  });

  /** Progressive disclosure is for EDGE CASES only — never for a caveat that
   *  keeps the visible sentence from overstating what the code does. */
  it('puts only secondary edge cases behind collapsed disclosures', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('Data & Privacy');
    await screen.findByText(/only the synthetic workspace/i);

    const disclosures = Array.from(
      container.querySelectorAll('details.settings-more'),
    ) as HTMLDetailsElement[];
    expect(disclosures.map((d) => d.querySelector('summary')?.textContent)).toEqual([
      'What the Workspace Contains',
      'Assistant Conversations',
      'About That Shared Key',
    ]);
    disclosures.forEach((d) => expect(d.open).toBe(false));

    // The honesty caveats stay in the ALWAYS-VISIBLE paragraph, not in a drawer.
    const hidden = norm(disclosures.map((d) => d.textContent ?? '').join(' '));
    expect(hidden).not.toContain('cannot tell real data from synthetic');
    expect(hidden).not.toContain('to judge whether it is real');
    expect(hidden).not.toContain('no way to report whether either restriction is active');
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
  /**
   * P36V PR3: About is IDENTITY and PROVENANCE only. Runtime Mode / Data Regime
   * / Persistence used to be repeated here as three of six identical rows —
   * they are runtime status, so they now live on Overview alone.
   */
  it('renders identity only: version, short commit, schema, core — no runtime status', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('About');
    expect(await screen.findByText('0.1.0')).toBeInTheDocument();
    expect(screen.getByText('v1.05')).toBeInTheDocument();
    expect(screen.getByText('isaac_records')).toBeInTheDocument();

    expect(
      Array.from(container.querySelectorAll('.settings-figure dt')).map((dt) => dt.textContent),
    ).toEqual(['App Version', 'Build Commit', 'ISAAC Record Schema', 'Core']);
    // The runtime values Overview owns are not restated here.
    expect(screen.queryAllByText('synthetic-only')).toHaveLength(0);
    expect(screen.queryByText('ephemeral')).not.toBeInTheDocument();
  });

  /**
   * The short sha is prominent; the FULL sha renders in exactly one place on the
   * whole page — inside this collapsed disclosure. Rendering it inline again
   * fails this test.
   */
  it('shows the short commit inline and the full SHA only inside Technical Details', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('About');
    await screen.findByText('0.1.0');

    const short = screen.getByText('fakecommit00');
    expect(short.closest('details')).toBeNull();

    const full = screen.getAllByText('fakecommit0000settingsp364');
    expect(full).toHaveLength(1);
    const drawer = container.querySelector('details.settings-technical') as HTMLDetailsElement;
    expect(drawer).not.toBeNull();
    expect(drawer.open).toBe(false);
    expect(drawer.querySelector('summary')?.textContent).toBe('Technical Details'); // Title Case
    expect(full[0].closest('details')).toBe(drawer);
  });

  it('Technical Details carries the raw field names, source endpoints, and doc paths', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('About');
    await screen.findByText('0.1.0');

    const drawer = container.querySelector('details.settings-technical') as HTMLElement;
    const labels = Array.from(drawer.querySelectorAll('dt')).map((dt) => dt.textContent);
    expect(labels).toEqual([
      'Build Commit (Full)',
      'Response Fields',
      'Source Endpoints',
      'Repository Documentation',
    ]);
    for (const field of [...ABOUT_RESPONSE_FIELDS, ...SETTINGS_SOURCE_ENDPOINTS, ...REPO_DOCS]) {
      const el = within(drawer).getByText(field);
      // Raw identifiers render verbatim as inert <code>, never re-cased or linked.
      expect(el.tagName).toBe('CODE');
      expect(el.closest('a')).toBeNull();
    }
    // The visible surface keeps the provenance CLAIM; only the raw path moved.
    expect(
      screen.getByText(/rendered verbatim — this screen computes none of these values/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/not served as pages by this app/i)).toBeInTheDocument();
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
    const copy = settingsAboutCopy(settingsFactsFrom(aboutResponse));
    expect(screen.getByText('Truth vs. Memory.')).toBeInTheDocument();
    expect(screen.getByText(norm(copy.truthVsMemory))).toBeInTheDocument();
    expect(screen.getByText('No-Guessing.')).toBeInTheDocument();
    expect(screen.getByText(/nothing scientific is invented/i)).toBeInTheDocument();
    // About names the two PLANES; it does not restate Data & Privacy's rulings.
    expect(screen.getByText(/is the truth plane/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/decided only by the official isaac v1\.05 schema/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/never a correctness ruling — and it cannot mark a record valid/i),
    ).not.toBeInTheDocument();
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

/**
 * P36V PR3 slice C split the API tab into two sub-surfaces — API Keys (an honest
 * unavailable state) and Documentation (Quick Start + Endpoint Explorer +
 * Connect an Agent) — and replaced the path-segment group inference with the
 * document's REAL `tags`. The suite below keeps every P36R guard and tightens
 * the grouping one: the group names and their ORDER asserted here are obtainable
 * only from the document's `tags` array, so a revert to segment inference fails.
 *
 * The API-Keys surface, Quick Start, the generated code samples and Connect an
 * Agent have their own file: `settings-api.test.tsx`.
 */
const ENDPOINT_COUNT = 7;

/** Open API → Documentation, where the Endpoint Explorer lives. */
async function openApiDocs() {
  openTab('API');
  fireEvent.click(tab('Documentation'));
  return screen.findByRole('heading', { name: 'Endpoint Explorer' });
}

/** The endpoint list, scoped: several paths also appear in Quick Start. */
const endpointList = () => document.querySelector('.api-browser-list') as HTMLElement;

const groupNames = () =>
  Array.from(document.querySelectorAll('.api-browser-group-heading')).map((h) =>
    (h.firstChild?.textContent ?? '').trim(),
  );

describe('Settings — API browser', () => {
  it('shows a loading state before the fetch resolves', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('API');
    fireEvent.click(tab('Documentation'));
    expect(screen.getByText('Loading API documentation…')).toBeInTheDocument();
  });

  it('groups the endpoints by the document’s REAL tags, with the method as TEXT', async () => {
    const hits = stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    // `/api/about` is the first row of the first registered tag, so it is the
    // default selection and appears twice: once in the list, once in the detail.
    expect(screen.getAllByText('/api/about')).toHaveLength(2);
    expect(within(endpointList()).getByText('/api/experiments/{id}')).toBeInTheDocument();
    expect(within(endpointList()).getByText('/api/experiments/{id}/answers')).toBeInTheDocument();

    // Group headings are the registered tag NAMES, in the document's own
    // registration order — which is deliberately not alphabetical.
    expect(groupNames()).toEqual([
      'Health & Meta',
      'Experiments',
      'Drafts & Answers',
      'Uploads',
      'Validation',
      'Other Operations',
    ]);
    expect([...groupNames()].sort()).not.toEqual(groupNames());
    // The path segments the previous helper inferred appear nowhere.
    for (const stale of ['health', 'about', 'experiments', 'answers', 'uploads', 'validate']) {
      expect(groupNames(), `stale inferred group: ${stale}`).not.toContain(stale);
    }
    // A registered tag no operation carries creates no group.
    expect(groupNames()).not.toContain('Schema & Vocabulary');

    // Method conveyed by TEXT, not color alone.
    expect(screen.getAllByText('GET').length).toBeGreaterThan(0);
    expect(screen.getAllByText('POST').length).toBeGreaterThan(0);
    expect(hits).toEqual(expect.arrayContaining([ABOUT_URL, OPENAPI_URL]));
  });

  it('renders the total endpoint count in its own explicit polite live region', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();
    const count = screen.getByText(`${ENDPOINT_COUNT} of ${ENDPOINT_COUNT} endpoints`);
    expect(count).toBeInTheDocument();
    expect(count).toHaveAttribute('aria-live', 'polite');
    // Exactly one `aria-live` region, plus exactly one shared `role="status"`
    // for every copy button on the surface — never one live region per button.
    expect(document.querySelectorAll('[aria-live]')).toHaveLength(1);
    expect(document.querySelectorAll('[role="status"]')).toHaveLength(1);
  });

  it('shows the OpenAPI contract identity verbatim, never a hand-written duplicate', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();
    expect(
      screen.getByText(/OpenAPI 3\.1\.0 · ISAAC Metadata Assistant — local UI backend · v0\.1\.0/),
    ).toBeInTheDocument();
    expect(screen.getByText(/this app's own\s+generated contract/i)).toBeInTheDocument();
  });

  it('the search box filters endpoints by path/summary/group, client-side, deterministically', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    const search = screen.getByLabelText('Search endpoints') as HTMLInputElement;
    expect(search.tagName).toBe('INPUT');
    expect(search).toHaveAttribute('type', 'search');

    fireEvent.change(search, { target: { value: 'answers' } });

    expect(await screen.findByText(`1 of ${ENDPOINT_COUNT} endpoints`)).toBeInTheDocument();
    // The one survivor becomes the selection, so it renders in the master list
    // AND in the detail pane; the filtered-out paths render nowhere in the list.
    expect(screen.getAllByText('/api/experiments/{id}/answers')).toHaveLength(2);
    expect(within(endpointList()).queryByText('/api/health')).not.toBeInTheDocument();
    expect(screen.queryByText('/api/about')).not.toBeInTheDocument();
  });

  it('an unmatched search shows an honest empty state, never fabricated rows', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.change(screen.getByLabelText('Search endpoints'), {
      target: { value: 'nonexistent-route-xyz' },
    });

    expect(await screen.findByText(/no endpoints match/i)).toBeInTheDocument();
    expect(screen.getByText(`0 of ${ENDPOINT_COUNT} endpoints`)).toBeInTheDocument();
  });

  it('is master-detail: one detail pane, not every endpoint expanded at once', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    const detail = document.getElementById('settings-api-detail') as HTMLElement;
    expect(detail).not.toBeNull();
    expect(detail).toHaveAttribute('role', 'region');
    expect(detail).toHaveAttribute('tabindex', '-1');
    expect(detail).toHaveAttribute('aria-labelledby', 'settings-api-detail-name');

    // The first visible endpoint is selected by default, and ONLY its detail
    // renders — every other path appears once, in the master list.
    expect(within(detail).getByText('/api/about')).toBeInTheDocument();
    expect(screen.getAllByText('/api/experiments/{id}')).toHaveLength(1);
    // Nothing renders a per-row <details> accordion any more.
    expect(
      detail.closest('.settings-card')?.querySelectorAll('.api-browser-row details'),
    ).toHaveLength(0);
  });

  it('selecting an endpoint renders its detail: summary, purpose, and parameters', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.click(within(endpointList()).getByText('/api/experiments/{id}'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;

    expect(within(detail).getByText('Get Experiment')).toBeInTheDocument();
    expect(within(detail).getByText(/fetch one experiment detail by id/i)).toBeInTheDocument();
    expect(within(detail).getByRole('heading', { name: 'Purpose' })).toBeInTheDocument();
    expect(within(detail).getByText('id')).toBeInTheDocument();
    expect(within(detail).getByText('path')).toBeInTheDocument();
    expect(within(detail).getByText('Yes')).toBeInTheDocument();
    // The parameter's own description, not a re-worded one.
    expect(within(detail).getByText('The id of an experiment.')).toBeInTheDocument();
  });

  it('an endpoint with no parameters says so honestly rather than showing an empty table', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.click(within(endpointList()).getByText('/api/health'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;
    expect(within(detail).getByText('No parameters.')).toBeInTheDocument();
    expect(within(detail).queryByRole('table')).not.toBeInTheDocument();
  });

  it('renders request body and responses when the contract supplies them, collapsed by default', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.click(within(endpointList()).getByText('/api/experiments/{id}/answers'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;

    expect(within(detail).getByRole('heading', { name: 'Request Body' })).toBeInTheDocument();
    expect(within(detail).getByText('Required.')).toBeInTheDocument();
    expect(within(detail).getByRole('heading', { name: 'Responses' })).toBeInTheDocument();
    expect(within(detail).getByRole('heading', { name: 'Error States' })).toBeInTheDocument();
    expect(within(detail).getByText('200')).toBeInTheDocument();
    expect(within(detail).getByText('422')).toBeInTheDocument();
    expect(within(detail).getByText('Validation Error')).toBeInTheDocument();

    // Schemas/examples/samples are collapsible and start closed — no JSON wall,
    // and the raw schema is explicitly labelled TECHNICAL so it never leads.
    const disclosures = Array.from(detail.querySelectorAll('details')) as HTMLDetailsElement[];
    expect(disclosures.length).toBeGreaterThanOrEqual(5); // req schema+example, 200, 422, samples
    disclosures.forEach((d) => expect(d.open).toBe(false));

    const schemaSummary = within(detail).getAllByText('Technical Schema')[0];
    expect(within(detail).queryByText('Schema')).not.toBeInTheDocument();
    fireEvent.click(schemaSummary);
    expect((schemaSummary.closest('details') as HTMLDetailsElement).open).toBe(true);
    expect(within(detail).getByText(/SyntheticAnswersBody/)).toBeInTheDocument();
    expect(within(detail).getAllByText('Example').length).toBeGreaterThan(0);
  });

  it('resolves a local $ref one level and names what it resolved', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.click(within(endpointList()).getByText('/api/experiments/{id}/answers'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;
    expect(within(detail).getByText('SyntheticFixtureError')).toBeInTheDocument();
  });

  it('shows an unresolvable $ref verbatim instead of inventing a shape for it', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.click(within(endpointList()).getByText('/api/experiments/{id}/answers'));
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
    await openApiDocs();

    const rows = Array.from(
      document.querySelectorAll('.api-browser-rowbtn'),
    ) as HTMLButtonElement[];
    expect(rows).toHaveLength(ENDPOINT_COUNT);
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
    await openApiDocs();
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
    fireEvent.click(tab('Documentation'));
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
  });
});

// --- safety: no sensitive infrastructure detail, no external URL --------------

/** The SAME forbidden list `apps/api/tests/test_about_and_openapi.py` enforces
 *  on `GET /api/about` — re-asserted here so the client copy cannot reintroduce
 *  what the backend deliberately withholds. Naming a provider or a host in
 *  client copy discloses infrastructure topology.
 *
 *  Slice C note: `API Key` with a space is fine; `api_key` / `apikey` are not,
 *  which is why no surface prints the deployment's own environment-variable name
 *  and the generated samples use `$ISAAC_API_CREDENTIAL` instead. */
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

/**
 * Every distinct Settings surface, with a string that only appears once that
 * surface's own content has rendered. The API tab is TWO surfaces since slice C,
 * and both are covered: the sub-tab that shows an unavailable state and the one
 * that renders the whole generated contract plus the code samples.
 */
const SURFACES: { name: string; open: () => void; settled: string | RegExp }[] = [
  { name: 'Overview', open: () => openTab('Overview'), settled: '0.1.0' },
  {
    name: 'Data & Privacy',
    open: () => openTab('Data & Privacy'),
    settled: /only the synthetic workspace/i,
  },
  { name: 'About', open: () => openTab('About'), settled: '0.1.0' },
  { name: 'API · API Keys', open: () => openTab('API'), settled: 'No keys to show.' },
  {
    name: 'API · Documentation',
    open: () => {
      openTab('API');
      fireEvent.click(tab('Documentation'));
    },
    settled: 'Endpoint Explorer',
  },
];

describe('Settings — no sensitive infrastructure detail is rendered', () => {
  it.each(SURFACES.map((s) => [s.name, s] as const))(
    'the %s surface leaks none of the backend-forbidden substrings',
    async (_name, surface) => {
      stubFetchRoutes(fullRoutes());
      const { container } = renderSettings();
      surface.open();
      await screen.findByText(surface.settled);

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
    fireEvent.click(tab('Documentation'));
    await screen.findByText('Endpoint Explorer');

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

// --- P36V PR3: single-source contract ----------------------------------------

/** Normalized rendered text of each surface, mounted one at a time (only the
 *  active panel is ever in the DOM, so cross-surface duplication has to be
 *  counted this way rather than read off a single render). */
async function textOfEverySurface(): Promise<string[]> {
  const out: string[] = [];
  for (const surface of SURFACES) {
    stubFetchRoutes(fullRoutes());
    const view = renderSettings();
    surface.open();
    await screen.findByText(surface.settled);
    out.push(norm(view.container.textContent ?? ''));
    view.unmount();
  }
  return out;
}

/**
 * THE anti-regression guard for the deduplication slice. Six claims used to be
 * authored two or three times across these tabs — two of them character-for-
 * character. Every canonical string is now counted across every surface and must
 * appear exactly once: copying a definition back into Overview or About, or
 * paraphrasing one into a second tab (including either API sub-tab) under a
 * different heading, fails here.
 */
describe('Settings — every canonical string appears exactly once across the tabs', () => {
  const facts = settingsFactsFrom(aboutResponse);
  const concepts = settingsConcepts(facts);
  const about = settingsAboutCopy(facts);

  const canonical: { what: string; text: string }[] = [
    ...concepts.map((c) => ({ what: `${c.heading} — summary`, text: c.summary })),
    ...concepts.map((c) => ({ what: `${c.heading} — definition`, text: c.detail })),
    ...concepts
      .filter((c) => c.more)
      .map((c) => ({ what: `${c.heading} — ${c.more!.label}`, text: c.more!.text })),
    { what: 'About — truth vs. memory', text: about.truthVsMemory },
    { what: 'About — no-guessing', text: about.noGuessing },
    { what: 'About — identity caption', text: about.identityCaption },
  ];

  it.each(canonical.map((c) => [c.what, c.text]))('%s is rendered exactly once', async (_what, text) => {
    const perSurface = await textOfEverySurface();
    const counts = perSurface.map((t) => countOccurrences(t, norm(text as string)));
    const total = counts.reduce((a, b) => a + b, 0);
    expect(
      total,
      `rendered ${total}x — per surface [${SURFACES.map((s, i) => `${s.name}:${counts[i]}`).join(', ')}]`,
    ).toBe(1);
  });

  it('the full commit SHA is rendered exactly once, on About', async () => {
    const perSurface = await textOfEverySurface();
    const counts = perSurface.map((t) => countOccurrences(t, aboutResponse.build_commit));
    expect(counts).toEqual([0, 0, 1, 0, 0]);
  });

  it('Overview renders no definition, and About renders no data/privacy definition', async () => {
    const [overview, , about_] = await textOfEverySurface();
    for (const concept of concepts) {
      expect(overview, `Overview leaked "${concept.heading}"`).not.toContain(norm(concept.detail));
      expect(about_, `About leaked "${concept.heading}"`).not.toContain(norm(concept.detail));
    }
  });

  it('every card/label heading in the content module is Title Case', () => {
    for (const concept of concepts) {
      expect(titleCase(concept.heading)).toBe(concept.heading);
      if (concept.more) expect(titleCase(concept.more.label)).toBe(concept.more.label);
    }
    expect(titleCase(about.truthVsMemoryLabel)).toBe(about.truthVsMemoryLabel);
    expect(titleCase(about.noGuessingLabel)).toBe(about.noGuessingLabel);
  });

  it('the page introduction is the single agreed sentence, under an accurate eyebrow', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(
      screen.getByText(
        "View this build's runtime status, data boundaries, provenance, and API access.",
      ),
    ).toBeInTheDocument();
    // Slice C: the eyebrow no longer promises configuration this page does not
    // offer — the "nothing to configure" claim below is what the page really is.
    expect(screen.getByText('About This Build')).toBeInTheDocument();
    expect(screen.queryByText('Local Configuration')).not.toBeInTheDocument();
    // The "nothing to configure" claim was not deleted — it moved into Overview.
    expect(screen.getByText(/no user-adjustable settings/i)).toBeInTheDocument();
  });

  it('the heading outline never skips a level on any surface', async () => {
    for (const surface of SURFACES) {
      stubFetchRoutes(fullRoutes());
      const view = renderSettings();
      surface.open();
      await screen.findByText(surface.settled);
      const levels = Array.from(
        view.container.querySelectorAll('h1, h2, h3, h4, h5, h6'),
      ).map((h) => Number(h.tagName[1]));
      expect(levels.length, `${surface.name}: no headings`).toBeGreaterThan(0);
      for (let i = 1; i < levels.length; i += 1) {
        expect(levels[i] - levels[i - 1], `${surface.name}: ${levels.join(',')}`).toBeLessThanOrEqual(1);
      }
      view.unmount();
    }
  });
});
