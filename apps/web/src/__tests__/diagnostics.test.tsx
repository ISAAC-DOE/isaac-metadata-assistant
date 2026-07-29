import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import type { ReactNode } from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ApiError } from '../lib/api';
import { CopyDiagnostics, DiagnosticsPanel, DownTechnicalDetails } from '../components/FetchStates';
import {
  NOT_AVAILABLE,
  buildDiagnosticsReport,
  collectBrowserContext,
  diagnosticsAppFrom,
  diagnosticsFailureFrom,
  diagnosticsMemoryFrom,
  recordIdFromRoute,
  shortSha,
  summarizeBrowser,
  type DiagnosticsInput,
} from '../lib/diagnostics';
import { SettingsPage } from '../screens/SettingsPage';
import type { ApiGraphStatus } from '../lib/types';
import { ROUTES } from '../lib/routes';
import {
  aboutResponse,
  graphStatusAvailable,
  openApiFixture,
  stubFetchDown,
  stubFetchRoutes,
} from '../test/apiFixtures';

/*
 * COPY DIAGNOSTICS — the report's contents, its privacy boundary, and both mounts.
 *
 * The report is a deliberately BORING string, and that is what makes it
 * testable: `buildDiagnosticsReport` is pure, so every assertion below is about
 * bytes rather than about a component's incidental behaviour.
 *
 * The privacy tests are the load-bearing ones. A diagnostics feature is the
 * classic place a secret leaks: someone adds "and the request headers, that's
 * useful" and a bearer token ships to a Slack thread. So the suite plants a
 * `VITE_API_KEY`, a cookie, a bearer token in both web storages, and an
 * `ApiError.body` full of credentials, then asserts the generated report is free
 * of all of them — and it asserts that against BOTH mounts, not just the pure
 * function, because the mounts are what a reader actually activates.
 */

// --- the planted secrets ------------------------------------------------------
// Deliberately distinctive so a match cannot be a coincidence, and deliberately
// shaped like the real things: an env-injected key, a cookie, a bearer token.
const PLANTED_API_KEY = 'PLANTED-VITE-API-KEY-b3d1f0a9c7e5';
const PLANTED_COOKIE_VALUE = 'PLANTED-COOKIE-SESSION-9f8e7d6c5b4a';
const PLANTED_TOKEN = 'PLANTED-BEARER-TOKEN-1a2b3c4d5e6f';
const PLANTED_STORAGE_VALUE = 'PLANTED-LOCALSTORAGE-VALUE-0f1e2d3c';
const PLANTED_ERROR_BODY_SECRET = 'PLANTED-ERROR-BODY-SECRET-7a6b5c4d';

/** Every planted string, plus the header/scheme names that must never appear. */
const FORBIDDEN = [
  PLANTED_API_KEY,
  PLANTED_COOKIE_VALUE,
  PLANTED_TOKEN,
  PLANTED_STORAGE_VALUE,
  PLANTED_ERROR_BODY_SECRET,
  'Bearer',
  'Authorization',
  'authorization',
  'Cookie',
  'x-api-key',
];

function plantSecrets() {
  vi.stubEnv('VITE_API_KEY', PLANTED_API_KEY);
  try {
    document.cookie = `isaac_session=${PLANTED_COOKIE_VALUE}`;
    localStorage.setItem('isaac.authorization', `Bearer ${PLANTED_TOKEN}`);
    localStorage.setItem('isaac.note', PLANTED_STORAGE_VALUE);
    sessionStorage.setItem('isaac.token', PLANTED_TOKEN);
  } catch {
    /* a storage-less environment is fine — the point is that nothing reads it */
  }
}

function clearSecrets() {
  try {
    document.cookie = 'isaac_session=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    localStorage.clear();
    sessionStorage.clear();
  } catch {
    /* nothing to clear */
  }
}

/** Assert a rendered/generated string carries none of the planted secrets. */
function expectNoSecrets(text: string) {
  for (const needle of FORBIDDEN) {
    expect(text).not.toContain(needle);
  }
}

// --- a complete, fully-populated input ---------------------------------------

const FIXED_NOW = new Date('2026-07-28T09:41:07.000Z');

const CHROME_MAC_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36';

function fullInput(overrides: Partial<DiagnosticsInput> = {}): DiagnosticsInput {
  return {
    generatedAt: FIXED_NOW,
    apiBase: '/krish/api',
    deployment: 'hosted preview',
    location: { route: '/krish/record/EXP-XANES-0001/evidence', tab: null },
    browser: {
      userAgent: CHROME_MAC_UA,
      viewportWidth: 1440,
      viewportHeight: 900,
      devicePixelRatio: 2,
      online: true,
    },
    app: diagnosticsAppFrom(aboutResponse),
    memory: diagnosticsMemoryFrom(graphStatusAvailable as unknown as ApiGraphStatus),
    ...overrides,
  };
}

/** Every label the report is contracted to emit, in no particular order. */
const REQUIRED_LABELS = [
  'App Version',
  'Build Commit (Short)',
  'Build Commit (Full)',
  'Runtime Mode',
  'Data Regime',
  'Persistence',
  'Record Schema',
  'Deployment',
  'API Base',
  'Generated At',
  'Route',
  'Tab',
  'Record Id',
  'Browser',
  'Viewport',
  'Device Pixel Ratio',
  'Network State',
  'Availability',
  'Integrity',
  'Provider',
  'Source Commit',
  'Snapshot Fingerprint',
  'Policy Fingerprint',
  'Served File Count',
  'Snapshot Schema',
];

beforeEach(() => {
  plantSecrets();
});

afterEach(() => {
  clearSecrets();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// --- 1. the report contains every contracted field ---------------------------

describe('buildDiagnosticsReport — field coverage', () => {
  it('emits every contracted label, each exactly once', () => {
    const report = buildDiagnosticsReport(fullInput());
    for (const label of REQUIRED_LABELS) {
      const hits = report.split('\n').filter((line) => line.trim().startsWith(`${label} `)).length;
      expect(hits, `label "${label}" should appear on exactly one line`).toBe(1);
    }
  });

  it('emits the observed values, not placeholders, when they are available', () => {
    const report = buildDiagnosticsReport(fullInput());
    expect(report).toContain('App Version');
    expect(report).toContain(aboutResponse.app_version);
    // Short AND full SHA are BOTH required — the short one to read, the full one
    // to hand to `git show`.
    expect(report).toContain(shortSha(aboutResponse.build_commit));
    expect(report).toContain(aboutResponse.build_commit);
    expect(report).toContain(aboutResponse.runtime_mode);
    expect(report).toContain('hosted preview');
    expect(report).toContain('/krish/api');
    expect(report).toContain('2026-07-28T09:41:07.000Z');
    expect(report).toContain('Chrome 130 on macOS');
    expect(report).toContain('1440 x 900 px');
    expect(report).toContain('the browser reports online');
    expect(report).toContain(graphStatusAvailable.source_graph_commit);
    expect(report).toContain(graphStatusAvailable.served_manifest_fingerprint);
    expect(report).toContain(graphStatusAvailable.policy_fingerprint);
  });

  it('formats for Slack and GitHub: a heading plus one fenced block', () => {
    const report = buildDiagnosticsReport(fullInput());
    expect(report.split('\n')[0]).toBe('### ISAAC Diagnostics');
    // Exactly one fence pair, so a paste lands as ONE code block in either target
    // and the aligned columns survive.
    expect(report.match(/^```/gm)?.length).toBe(2);
    expect(report).toContain('```text');
  });

  it('says every unobtainable value is unavailable rather than inventing one', () => {
    // The failure mount's real situation: `GET /api/about` and
    // `GET /api/graph/status` have not answered.
    const report = buildDiagnosticsReport(
      fullInput({
        app: null,
        memory: null,
        browser: {
          userAgent: null,
          viewportWidth: null,
          viewportHeight: null,
          devicePixelRatio: null,
          online: null,
        },
      }),
    );
    for (const label of ['App Version', 'Runtime Mode', 'Viewport', 'Source Commit', 'Provider']) {
      const line = report.split('\n').find((l) => l.trim().startsWith(`${label} `));
      expect(line, `${label} should still be reported`).toBeDefined();
      expect(line).toContain(NOT_AVAILABLE);
    }
    // No zero, no empty string, no plausible-looking default anywhere.
    expect(report).not.toMatch(/^\s*Viewport\s+0 x 0/m);
  });

  it('reports device pixel ratio and never a zoom level it cannot measure', () => {
    const report = buildDiagnosticsReport(fullInput());
    expect(report).toContain('Device Pixel Ratio');
    // devicePixelRatio conflates page zoom with display density and OS scaling,
    // and visualViewport.scale ignores desktop page zoom entirely — so no field
    // may claim to report zoom.
    expect(report).not.toMatch(/zoom/i);
  });

  it('collapses a multi-line server value so it cannot break the report structure', () => {
    const report = buildDiagnosticsReport(
      fullInput({
        memory: {
          ...diagnosticsMemoryFrom(graphStatusAvailable as unknown as ApiGraphStatus),
          provider: 'snapshot\nFAILURE SIGNALS\n  Injected  yes',
        },
      }),
    );
    expect(report).toContain('snapshot FAILURE SIGNALS Injected yes');
    // The injected group title did not become a group.
    expect(report.match(/^FAILURE SIGNALS$/gm)).toBeNull();
  });
});

// --- 2. failure signals, and the ApiError.body exclusion ---------------------

describe('buildDiagnosticsReport — failure signals', () => {
  const error = new ApiError('boom', {
    status: 503,
    unreachable: false,
    htmlIntercept: false,
    contentType: 'application/json',
    path: '/experiments/EXP-XANES-0001',
    // The reason `body` is excluded by TYPE: it is `unknown` and comes from a
    // response this app does not control, so it could hold anything at all.
    body: {
      authorization: `Bearer ${PLANTED_TOKEN}`,
      api_key: PLANTED_API_KEY,
      detail: PLANTED_ERROR_BODY_SECRET,
    },
  });

  it('reports the five observable signals', () => {
    const report = buildDiagnosticsReport(
      fullInput({ failure: diagnosticsFailureFrom(error) }),
    );
    expect(report).toContain('FAILURE SIGNALS');
    expect(report).toContain('HTTP Status');
    expect(report).toContain('503');
    expect(report).toContain('Network-Level Failure');
    expect(report).toContain('HTML Intercept');
    expect(report).toContain('Response Content-Type');
    expect(report).toContain('application/json');
    expect(report).toContain('Request Path');
    expect(report).toContain('/experiments/EXP-XANES-0001');
  });

  it('renders the two boolean signals honestly, including when absent', () => {
    // Present-and-false must read `no`; ABSENT must read NOT_AVAILABLE, not a
    // plausible-looking `no`. `diagnosticsFailureFrom` always populates both
    // today, so this pins the invariant rather than a current behaviour.
    const both = (report: string, label: string) =>
      report.split('\n').find((l) => l.trim().startsWith(`${label} `));

    const populated = buildDiagnosticsReport(
      fullInput({ failure: diagnosticsFailureFrom(error) }),
    );
    expect(both(populated, 'Network-Level Failure')).toContain('no');
    expect(both(populated, 'HTML Intercept')).toContain('no');

    const partial = buildDiagnosticsReport(
      fullInput({ failure: { status: 503, contentType: null, path: null } }),
    );
    expect(both(partial, 'Network-Level Failure')).toContain(NOT_AVAILABLE);
    expect(both(partial, 'HTML Intercept')).toContain(NOT_AVAILABLE);
  });

  it('never carries ApiError.body — the mapper cannot pass it on', () => {
    const mapped = diagnosticsFailureFrom(error);
    expect('body' in mapped).toBe(false);
    const report = buildDiagnosticsReport(fullInput({ failure: mapped }));
    expect(report).not.toContain(PLANTED_ERROR_BODY_SECRET);
    expect(report).not.toContain(PLANTED_TOKEN);
    expect(report).not.toContain(PLANTED_API_KEY);
    expectNoSecrets(report);
  });

  it('omits the failure group entirely when nothing failed', () => {
    const report = buildDiagnosticsReport(fullInput());
    expect(report).not.toContain('FAILURE SIGNALS');
  });
});

// --- 3. REDACTION: the hard privacy boundary --------------------------------

describe('diagnostics privacy boundary', () => {
  it('contains no API key, bearer token, cookie, storage content or header name', () => {
    // Sanity: the secrets really are present in this environment, so the
    // assertions below are meaningful rather than vacuously true.
    expect(import.meta.env.VITE_API_KEY).toBe(PLANTED_API_KEY);
    expect(document.cookie).toContain(PLANTED_COOKIE_VALUE);
    expect(localStorage.getItem('isaac.authorization')).toContain(PLANTED_TOKEN);
    expect(sessionStorage.getItem('isaac.token')).toBe(PLANTED_TOKEN);

    expectNoSecrets(buildDiagnosticsReport(fullInput()));
  });

  it("holds for the failure mount's rendered report, not just the generator", async () => {
    const error = new ApiError('boom', {
      status: 401,
      path: '/experiments',
      contentType: 'text/html',
      htmlIntercept: true,
      body: { token: `Bearer ${PLANTED_TOKEN}`, note: PLANTED_ERROR_BODY_SECRET },
    });
    const writeText = vi.fn(async (_text: string) => {});
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText }, onLine: true });

    const view = render(<DownTechnicalDetails error={error} />);
    fireEvent.click(view.getByRole('button', { name: /Copy Diagnostics/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));

    const copied = writeText.mock.calls[0][0];
    expectNoSecrets(copied);
    // The whole rendered box, too — including the box's own rows.
    expectNoSecrets(view.container.textContent ?? '');
  });

  it("holds for the normal-state mount's rendered report", async () => {
    const writeText = vi.fn(async (_text: string) => {});
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText }, onLine: true });
    const view = render(
      <DiagnosticsPanel
        app={diagnosticsAppFrom(aboutResponse)}
        memory={diagnosticsMemoryFrom(graphStatusAvailable as unknown as ApiGraphStatus)}
        route="/settings"
        tab="about"
      />,
    );
    fireEvent.click(view.getByRole('button', { name: /Copy Diagnostics/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expectNoSecrets(writeText.mock.calls[0][0]);
  });

  it('reads nothing beyond the four browser measurements it declares', () => {
    // `collectBrowserContext` is the ONLY impure reader. Its return type has
    // exactly these keys, so a future edit that starts reading storage or cookies
    // has nowhere to put the result without changing the contract.
    expect(Object.keys(collectBrowserContext()).sort()).toEqual([
      'devicePixelRatio',
      'online',
      'userAgent',
      'viewportHeight',
      'viewportWidth',
    ]);
  });

  it('performs no network request when generating or copying', async () => {
    const fetchSpy = vi.fn(async () => {
      throw new Error('diagnostics must never fetch');
    });
    vi.stubGlobal('fetch', fetchSpy);
    const writeText = vi.fn(async (_text: string) => {});
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText }, onLine: true });

    const view = render(<CopyDiagnostics build={() => buildDiagnosticsReport(fullInput())} />);
    fireEvent.click(view.getByRole('button', { name: /Copy Diagnostics/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

// --- 4. the record id: present on a record route, never fabricated ----------

describe('record id derivation', () => {
  it('extracts the id from every record route, with or without a base path', () => {
    expect(recordIdFromRoute('/record/EXP-XANES-0001')).toBe('EXP-XANES-0001');
    expect(recordIdFromRoute('/record/EXP-XANES-0001/complete')).toBe('EXP-XANES-0001');
    expect(recordIdFromRoute('/krish/record/EXP-XANES-0001/export')).toBe('EXP-XANES-0001');
  });

  it('returns null — never a guess — for a non-record route', () => {
    for (const route of ['/experiments', '/settings', '/memory', '/governance', '/load', '/']) {
      expect(recordIdFromRoute(route)).toBeNull();
    }
  });

  it('reports the id on a record route and "not applicable" elsewhere', () => {
    const onRecord = buildDiagnosticsReport(
      fullInput({ location: { route: '/krish/record/EXP-XANES-0001/evidence' } }),
    );
    expect(onRecord).toMatch(/Record Id\s+EXP-XANES-0001/);

    const offRecord = buildDiagnosticsReport(fullInput({ location: { route: '/settings' } }));
    expect(offRecord).toMatch(/Record Id\s+not applicable/);
    expect(offRecord).not.toContain('EXP-XANES-0001');
  });

  it('reports the active tab when one applies and "not applicable" when none does', () => {
    expect(
      buildDiagnosticsReport(fullInput({ location: { route: '/settings', tab: 'about' } })),
    ).toMatch(/Tab\s+about/);
    expect(buildDiagnosticsReport(fullInput({ location: { route: '/experiments' } }))).toMatch(
      /Tab\s+not applicable/,
    );
  });
});

// --- 5. browser identification ---------------------------------------------

describe('summarizeBrowser', () => {
  it('is concise: family, major version and OS family', () => {
    expect(summarizeBrowser(CHROME_MAC_UA)).toBe('Chrome 130 on macOS');
    expect(
      summarizeBrowser(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0',
      ),
    ).toBe('Edge 129 on Windows');
    expect(
      summarizeBrowser('Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0'),
    ).toBe('Firefox 131 on Linux');
    expect(
      summarizeBrowser(
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15',
      ),
    ).toBe('Safari 17 on macOS');
  });

  it('reports the raw string for an unrecognised agent rather than guessing', () => {
    const summary = summarizeBrowser('SomeNewBrowser/1 (Windows NT 10.0)');
    expect(summary).toContain('unrecognised');
    expect(summary).toContain('SomeNewBrowser/1');
  });

  it('is explicit when there is no user agent at all', () => {
    expect(summarizeBrowser(null)).toBe(NOT_AVAILABLE);
    expect(summarizeBrowser('   ')).toBe(NOT_AVAILABLE);
  });
});

// --- 6. the control: clipboard success, clipboard failure, keyboard, a11y ----

describe('CopyDiagnostics — activation', () => {
  const build = () => buildDiagnosticsReport(fullInput());

  it('generates nothing until explicitly activated', () => {
    const spy = vi.fn(build);
    render(<CopyDiagnostics build={spy} />);
    expect(spy).not.toHaveBeenCalled();
  });

  it('SUCCESS: writes the report to the clipboard and announces it', async () => {
    const writeText = vi.fn(async (_text: string) => {});
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText }, onLine: true });

    const view = render(<CopyDiagnostics build={build} />);
    const button = view.getByRole('button', { name: /Copy Diagnostics/ });
    fireEvent.click(button);

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(build()));
    // Announced to assistive tech through a live region…
    const status = await waitFor(() => {
      const node = view.container.querySelector('[role="status"]');
      expect(node?.textContent).toContain('copied to the clipboard');
      return node;
    });
    expect(status).not.toBeNull();
    // …and signalled VISIBLY by the label, not by colour alone.
    expect(view.getByRole('button', { name: /Diagnostics Copied/ })).toBeInTheDocument();
    // The success path does not dump the report onto the page.
    expect(view.container.querySelector('.fetch-state-diagnostics-block')).toBeNull();
  });

  it('FAILURE (writeText rejects): falls back to selectable text', async () => {
    const writeText = vi.fn(async () => {
      throw new Error('NotAllowedError');
    });
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText }, onLine: true });

    const view = render(<CopyDiagnostics build={build} />);
    fireEvent.click(view.getByRole('button', { name: /Copy Diagnostics/ }));

    const block = await waitFor(() => {
      const node = view.container.querySelector('.fetch-state-diagnostics-block');
      expect(node).not.toBeNull();
      return node as HTMLElement;
    });
    // The whole report is on the page, selectable and focusable.
    expect(block.textContent).toBe(build());
    expect(block.getAttribute('tabindex')).toBe('0');
    expect(block.tagName).toBe('PRE');
    // The reason is stated in words, in the live region AND visibly.
    expect(view.container.querySelector('[role="status"]')?.textContent).toMatch(
      /Clipboard access is unavailable/,
    );
    // Stated twice on purpose, and that is the assertion: once in the live
    // region (announced) and once visibly (readable without assistive tech).
    const stated = view.getAllByText(/Select it and copy it manually/);
    expect(stated).toHaveLength(2);
    expect(stated.some((node) => node.className === 'sr-only')).toBe(true);
    expect(
      stated.some((node) => node.className === 'fetch-state-diagnostics-fallback'),
    ).toBe(true);
    // Not falsely reported as copied.
    expect(view.queryByRole('button', { name: /Diagnostics Copied/ })).toBeNull();
  });

  it('FAILURE (no Clipboard API at all): falls back to selectable text', async () => {
    vi.stubGlobal('navigator', { ...navigator, clipboard: undefined, onLine: true });

    const view = render(<CopyDiagnostics build={build} />);
    fireEvent.click(view.getByRole('button', { name: /Copy Diagnostics/ }));

    const block = await waitFor(() => {
      const node = view.container.querySelector('.fetch-state-diagnostics-block');
      expect(node).not.toBeNull();
      return node as HTMLElement;
    });
    expect(block.textContent).toBe(build());
  });

  it('is keyboard-operable: a real focusable button, activated by Enter/Space', async () => {
    const writeText = vi.fn(async (_text: string) => {});
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText }, onLine: true });

    const view = render(<CopyDiagnostics build={build} />);
    const button = view.getByRole('button', { name: /Copy Diagnostics/ });
    // A native <button type="button"> with no role or tabindex override, so
    // Enter/Space activation is the platform's, not a hand-rolled key handler
    // that could miss a case.
    expect(button.tagName).toBe('BUTTON');
    expect(button.getAttribute('type')).toBe('button');
    expect(button.hasAttribute('tabindex')).toBe(false);
    button.focus();
    expect(document.activeElement).toBe(button);
    // Enter on a focused submit-less button dispatches a click in every browser;
    // jsdom does not synthesise that, so the click is dispatched directly on the
    // FOCUSED element to prove no pointer-only handler is in the way.
    fireEvent.click(document.activeElement as HTMLElement);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  });

  it('has a live region present before the first activation, so the update is announced', () => {
    const view = render(<CopyDiagnostics build={build} />);
    const status = view.container.querySelector('[role="status"]');
    expect(status).not.toBeNull();
    expect(status?.textContent).toBe('');
  });
});

// --- 7. both mounts exist ---------------------------------------------------

describe('the two mounts', () => {
  it('the failure state offers it inside the existing Technical Details box', () => {
    const view = render(
      <DownTechnicalDetails error={new ApiError('down', { unreachable: true, path: '/experiments' })} />,
    );
    // Extended, not duplicated: the same <details> still carries the original rows.
    expect(view.container.querySelector('details.fetch-state-technical')).not.toBeNull();
    expect(view.getByText('HTTP Status')).toBeInTheDocument();
    expect(view.getByRole('button', { name: /Copy Diagnostics/ })).toBeInTheDocument();
  });

  it('Settings → About offers it when nothing is broken', async () => {
    stubFetchRoutes({
      'GET /api/about': { body: aboutResponse },
      'GET /api/openapi': { body: openApiFixture },
      'GET /api/graph/status': { body: graphStatusAvailable },
    });
    const view = render(
      <MemoryRouter
        initialEntries={[ROUTES.settingsTab('about')]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <SettingsPage />
      </MemoryRouter>,
    );
    const button = await view.findByRole('button', { name: /Copy Diagnostics/ });
    expect(button).toBeInTheDocument();
    // Never the error state — this mount exists precisely so the report is
    // reachable while the app is healthy.
    expect(view.container.querySelector('.fetch-state.error')).toBeNull();
  });

  it('Settings → About still offers it, with honest memory rows, when graph status fails', async () => {
    const writeText = vi.fn(async (_text: string) => {});
    stubFetchRoutes({
      'GET /api/about': { body: aboutResponse },
      'GET /api/openapi': { body: openApiFixture },
      'GET /api/graph/status': { status: 503, body: { error: 'nope' } },
    });
    const view = render(
      <MemoryRouter
        initialEntries={[ROUTES.settingsTab('about')]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <SettingsPage />
      </MemoryRouter>,
    );
    const button = await view.findByRole('button', { name: /Copy Diagnostics/ });
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText }, onLine: true });
    fireEvent.click(button);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const report = writeText.mock.calls[0][0];
    // The build facts are real…
    expect(report).toContain(aboutResponse.build_commit);
    // …and the memory rows say so rather than showing a stale or invented value.
    expect(report).toMatch(/Source Commit\s+not available/);
    expect(report).toMatch(/Snapshot Fingerprint\s+not available/);
  });
});

// --- 8. the corrected hosted-truthfulness strings ---------------------------

/**
 * Load the app as a HOSTED build. `isHostedBuild` compares two compile-time
 * literals that Vite folds at build time, so a fresh module registry with
 * `VITE_API_BASE` stubbed is the only faithful way to exercise the hosted branch
 * — the technique `hosted-truthfulness.test.tsx` and `backend-down-state.test.tsx`
 * already use.
 */
async function loadHosted() {
  vi.resetModules();
  vi.stubEnv('VITE_API_BASE', '/krish/api');
  const [{ AppRoutes }, { ProjectMemory }, { RecordValidator }, api] = await Promise.all([
    import('../App'),
    import('../screens/ProjectMemory'),
    import('../components/RecordValidator'),
    import('../lib/api'),
  ]);
  return { AppRoutes, ProjectMemory, RecordValidator, isHostedBuild: api.isHostedBuild };
}

/**
 * Every way this app's copy has claimed "you are running this on your own
 * machine" — the SAME expression `hosted-truthfulness.test.tsx` pins for the
 * chrome, applied here to the screens.
 */
const LOCAL_DEV_CLAIM =
  /\blocal\b|\blocally\b|localhost|127\.0\.0\.1|uvicorn|\boffline\b|your (own )?(machine|laptop|computer)/i;

function renderHosted(ui: ReactNode, path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      {ui}
    </MemoryRouter>,
  );
}

describe('hosted truthfulness — the four record loading labels', () => {
  /*
   * These four labels read "…from the local backend…" on every build, including
   * the SLAC-hosted deployment, where the backend is not the reader's machine.
   * They now name the thing being talked to (the ISAAC API) and stop claiming
   * where it runs — a fact the frontend cannot observe either way.
   *
   * `stubFetchDown` makes every request fail, which is the cheapest way to hold a
   * screen in its LOADING branch for one synchronous assertion; the down state is
   * then awaited so the state update settles inside `act`.
   */
  const CASES: { route: string; label: string; down: string }[] = [
    {
      route: '/record/demo',
      label: 'Loading the record from the ISAAC API…',
      down: 'ISAAC Is Not Responding',
    },
    {
      route: '/record/demo/complete',
      label: 'Loading the blockers from the ISAAC API…',
      down: 'ISAAC Is Not Responding',
    },
    {
      route: '/record/demo/evidence',
      label: 'Loading the evidence trail from the ISAAC API…',
      down: 'ISAAC Is Not Responding',
    },
    {
      route: '/record/demo/export',
      label: 'Loading validation, coverage and advisory from the ISAAC API…',
      down: 'ISAAC Is Not Responding',
    },
  ];

  for (const testCase of CASES) {
    it(`${testCase.route} claims no locality while loading, on a hosted build`, async () => {
      const hosted = await loadHosted();
      expect(hosted.isHostedBuild).toBe(true);
      stubFetchDown();
      const view = renderHosted(<hosted.AppRoutes />, testCase.route);
      const panel = view.getByRole('status');
      expect(panel.textContent).toBe(testCase.label);
      expect(panel.textContent).not.toMatch(LOCAL_DEV_CLAIM);
      // Settle the failing fetch so the update happens inside act().
      await view.findByText(testCase.down);
    });
  }
});

describe('hosted truthfulness — the standalone validator scope note', () => {
  it('claims a synthetic MODE, never the reader’s machine', async () => {
    const hosted = await loadHosted();
    const view = renderHosted(<hosted.RecordValidator />, '/experiments');
    const note = view.container.querySelector('.rec-val-scope-note');
    expect(note).not.toBeNull();
    expect(note!.textContent).not.toMatch(LOCAL_DEV_CLAIM);
    // The true half of the old sentence is preserved verbatim.
    expect(note!.textContent).toContain('the record is checked in memory and discarded');
    expect(note!.textContent).toContain('Nothing here is uploaded to a model, indexed, or stored');
    // Mode, not content: nothing here inspects a record to decide it is synthetic.
    expect(note!.textContent).toMatch(/Synthetic-mode validator/);
  });
});

describe('hosted truthfulness — the Project Memory unavailable state', () => {
  /*
   * The old copy said "the hosted demo does not currently ship the Graphify graph
   * artifacts; when run locally against local artifacts, Project Memory works".
   * Both halves were false: `apps/api/isaac_api/data/memory-snapshot.json` and
   * `memory-graph-detail.json` are tracked in git and ship in the image via the
   * Dockerfile's `COPY apps/api/ apps/api/`, and `memory.py::_resolve_reader_choice`
   * prefers that packaged snapshot. So the deployment DOES have memory, and the
   * new copy describes the condition that actually produces this panel.
   */
  async function renderUnavailable() {
    const hosted = await loadHosted();
    const { graphStatusUnavailable } = await import('../test/apiFixtures');
    stubFetchRoutes({ 'GET /krish/api/graph/status': { body: graphStatusUnavailable } });
    const view = renderHosted(<hosted.ProjectMemory />, '/memory');
    const panel = await waitFor(() => {
      const node = view.container.querySelector('.memory-unavailable');
      expect(node).not.toBeNull();
      return node as HTMLElement;
    });
    return { view, text: panel.textContent ?? '' };
  }

  it('claims no locality and does not send the reader to a local checkout', async () => {
    const { text } = await renderUnavailable();
    expect(text).not.toMatch(LOCAL_DEV_CLAIM);
    expect(text).not.toMatch(/hosted demo does not currently ship/i);
    expect(text).not.toMatch(/Graphify graph artifacts/i);
  });

  it('states that the artifacts ARE shipped, which is the verifiable fact', async () => {
    const { text } = await renderUnavailable();
    expect(text).toMatch(/ships its memory artifacts with the application/i);
    expect(text).toMatch(/an absent artifact is not the expected state/i);
  });

  it('names two possible conditions and asserts neither, having no signal to separate them', async () => {
    const { text } = await renderUnavailable();
    expect(text).toMatch(/cannot tell which of two conditions applies/i);
    expect(text).toMatch(/not included in this build/i);
    expect(text).toMatch(/configured to read a memory source that is not present/i);
  });

  it('uses the corrected access vocabulary and promises no login-gated service', async () => {
    const { text } = await renderUnavailable();
    expect(text).not.toMatch(/institution-hosted/i);
    expect(text).not.toMatch(/behind login/i);
    expect(text).toMatch(/controlled by the deployment where it is operated/i);
    expect(text).toMatch(/ISAAC manages no accounts or roles/i);
  });

  it('names no identity product, host or infrastructure component', async () => {
    const { text } = await renderUnavailable();
    for (const needle of ['authentik', 'ingress', 'kubernetes', 'k8s', 's3df']) {
      expect(text.toLowerCase()).not.toContain(needle);
    }
  });
});
