/*
 * P36R S1 — the shared content-width system.
 *
 * Before this slice `.placeholder` hard-capped Project Memory / Governance /
 * Settings at 640px inside a <main> that is far wider, while `.centered-col`
 * carried an unrelated 1040/720px pair — two competing width idioms and no
 * single truthful system. AppShell now publishes ONE opt-in token
 * (`data-width` → `--content-max`) and the measure wrappers consume it.
 *
 * jsdom applies no CSS, so this file splits the contract in two:
 *   - DOM assertions for what React actually renders (the attribute, the class
 *     the CSS selectors are written against, and every screen that opts in);
 *   - CSS-SOURCE assertions (via import.meta.glob '?raw', the same idiom as
 *     no-vertical-rail.test.ts) for the declarations themselves.
 *
 * The screens are asserted by RENDERING rather than by grepping their source:
 * a source grep would pass even if the prop were on a dead branch, whereas
 * these renders drive the record screens all the way to their LOADED shell —
 * the branch a user actually sees.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

import { AppShell } from '../components/AppShell';
import { AppRoutes } from '../App';
import { GovernancePage } from '../screens/GovernancePage';
import { ProjectMemory } from '../screens/ProjectMemory';
import { SettingsPage } from '../screens/SettingsPage';
import { StatisticsPage } from '../screens/statistics/StatisticsPage';
import {
  aboutResponse,
  bundleRoutes,
  exportReadyRoutes,
  graphStatusAvailable,
  memoryConceptsAvailable,
  memoryFilesAvailable,
  openApiFixture,
  statisticsRoutes,
  stubFetchRoutes,
} from '../test/apiFixtures';

/* EVERY stylesheet, not just the two this slice edited: a re-hardcoded measure
   or a global prose cap is just as damaging in a component stylesheet. */
const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const cssByName = (name: string): string =>
  Object.entries(cssFiles).find(([path]) => path.endsWith(`/${name}`))?.[1] ?? '';

/** Collapse whitespace so selector/declaration assertions survive reformatting. */
const squash = (source: string): string => source.replace(/\s+/g, ' ');

/**
 * Parse a stylesheet into flat {selector, body} rules, comments removed so a
 * guard can never be fooled by prose that merely quotes a declaration. The
 * `[^{}]` classes mean at-rule wrappers (`@media … {`) are stepped over and the
 * rules INSIDE them are still yielded — the case the old `(^|})`-anchored regex
 * silently missed.
 */
function cssRules(source: string): { selector: string; body: string }[] {
  const withoutComments = source.replace(/\/\*[\s\S]*?\*\//g, '');
  return [...withoutComments.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim(),
    body: m[2],
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function routerRender(ui: ReactNode, path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      {ui}
    </MemoryRouter>,
  );
}

const mainOf = (container: HTMLElement): HTMLElement => {
  const main = container.querySelector('main');
  expect(main, 'AppShell must render a <main>').not.toBeNull();
  return main as HTMLElement;
};

// --- 1. AppShell publishes the mode ---------------------------------------

describe('AppShell — data-width on <main>', () => {
  it.each(['readable', 'wide', 'full'] as const)('renders data-width="%s"', (width) => {
    const { container } = routerRender(
      <AppShell variant="full" topBar={null} width={width}>
        <p>content</p>
      </AppShell>,
      '/',
    );
    expect(mainOf(container).getAttribute('data-width')).toBe(width);
  });

  /*
   * The whole system hangs off the COMPOUND selector `.screen-main[data-width]`.
   * Asserting the attribute alone would still pass if `mainClass` were renamed,
   * which would silently detach every mode from its declarations. Query the
   * exact compound the stylesheet is written against instead.
   */
  it.each(['readable', 'wide', 'full'] as const)(
    'renders <main> as the compound the CSS targets: main.screen-main[data-width="%s"]',
    (width) => {
      const { container } = routerRender(
        <AppShell variant="full" topBar={null} width={width} mainPad="pad">
          <p>content</p>
        </AppShell>,
        '/',
      );
      expect(
        container.querySelector(`main.screen-main[data-width='${width}']`),
        `chrome.css declares .screen-main[data-width='${width}'] — <main> must match it`,
      ).not.toBeNull();
      // `.screen-main.pad` carries the standardised gutter; same rename hazard.
      expect(container.querySelector('main.screen-main.pad')).not.toBeNull();
    },
  );

  it('OMITS the attribute entirely when no width is given (opt-in, not default)', () => {
    const { container } = routerRender(
      <AppShell variant="full" topBar={null}>
        <p>content</p>
      </AppShell>,
      '/',
    );
    const main = mainOf(container);
    expect(main.hasAttribute('data-width')).toBe(false);
    // …but it is still the element the width CSS is written against.
    expect(main.classList.contains('screen-main')).toBe(true);
  });
});

// --- 2/3. the CSS contract -------------------------------------------------

describe('chrome.css — the width-mode tokens', () => {
  const chrome = squash(cssByName('chrome.css'));

  it.each([
    ['readable', '760px'],
    ['wide', '1200px'],
    ['full', 'none'],
  ])('declares --content-max for data-width="%s" (= %s)', (mode, value) => {
    expect(chrome).toContain(`.screen-main[data-width='${mode}'] { --content-max: ${value}; }`);
  });

  /*
   * P36V1 S6 updated the two padding literals asserted here, and this test was
   * updated with them rather than deleted. The horizontal contract it was
   * written to protect is unchanged and still asserted: --main-gutter is 28px,
   * it is used for the INLINE padding only, and it stays in the 24–32px band.
   * What changed is the VERTICAL side — the old `22px` top literal became the
   * shared `--main-top-gutter`, so `.pad` is no longer the only preset with an
   * answer for "how far below the TopBar does content start?". The bottom
   * padding is still 22px.
   */
  it('names the main→rail gutter as a token and uses it for the inline padding only', () => {
    expect(chrome).toContain('--main-gutter: 28px;');
    expect(chrome).toContain(
      '.screen-main.pad { padding: var(--main-top-gutter) var(--main-gutter) 22px; }',
    );
    // the horizontal token stays in 24–32px
    const gutter = Number(/--main-gutter:\s*(\d+)px/.exec(chrome)?.[1]);
    expect(gutter).toBeGreaterThanOrEqual(24);
    expect(gutter).toBeLessThanOrEqual(32);
  });

  it('.centered-col consumes the token while keeping its historic fallbacks', () => {
    expect(chrome).toContain('max-width: var(--content-max, 1040px);');
    expect(chrome).toContain('max-width: var(--content-max, 720px);');
  });

  it('takes no unreachable --main-gutter fallback (.centered-col is always inside .screen-main)', () => {
    // P36V1 S6: the 24px top literal became the shared --main-top-gutter (the
    // 24px bottom is the column's own trailing space and stayed a literal).
    // The point of this test — that neither shell token carries a fallback,
    // because `.centered-col` only ever mounts inside `.screen-main` — is
    // unchanged and now covers both tokens.
    expect(chrome).toContain('padding: var(--main-top-gutter) var(--main-gutter) 24px;');
    expect(chrome).not.toContain('var(--main-gutter, ');
    expect(chrome).not.toContain('var(--main-top-gutter, ');
  });
});

describe('screens.css — .placeholder', () => {
  const screens = squash(cssByName('screens.css'));

  it('consumes --content-max', () => {
    expect(screens).toContain('.placeholder { max-width: var(--content-max, 640px); }');
  });

  /*
   * Guard, not a string match: the previous form only caught the one exact
   * `.placeholder { max-width: 640px; }` spelling, so a missing semicolon, a
   * reordered block, an at-rule override or a later more-specific selector
   * (`.screen-main .placeholder { max-width: 640px }`) would all have slipped
   * through and silently re-pinned the page to its old measure.
   */
  it('never re-hardcodes a bare 640px measure in ANY .placeholder rule form', () => {
    const offenders = cssRules(cssByName('screens.css'))
      .filter((r) => r.selector.includes('.placeholder') && /max-width\s*:\s*640px/.test(r.body))
      .map((r) => `${r.selector} { ${r.body.trim()} }`);
    expect(offenders, `re-hardcoded .placeholder measure:\n${offenders.join('\n')}`).toEqual([]);
  });

  it('caps long-form prose narrowly (direct child <p> only) inside wide/full', () => {
    expect(screens).toContain(
      ".screen-main[data-width='wide'] .placeholder > p, .screen-main[data-width='full'] .placeholder > p { max-width: 68ch; }",
    );
  });
});

describe('no stylesheet imposes a GLOBAL prose measure', () => {
  /*
   * A bare `p { max-width }` anywhere in the app would re-cap paragraphs that
   * already sit in bounded cards, grids, tab panels and detail panels. Scanned
   * across every stylesheet (not just screens.css), with comments stripped and
   * at-rule bodies included.
   */
  it('no `p { … max-width … }` rule exists in any apps/web/src/**/*.css', () => {
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(cssFiles)) {
      for (const rule of cssRules(source)) {
        const targetsBareP = rule.selector.split(',').some((s) => s.trim() === 'p');
        if (targetsBareP && /max-width\s*:/.test(rule.body)) {
          offenders.push(`${path}: ${rule.selector} { ${rule.body.trim()} }`);
        }
      }
    }
    expect(offenders, `global paragraph measure found:\n${offenders.join('\n')}`).toEqual([]);
  });
});

describe('component-level caps join the system instead of stair-stepping', () => {
  /*
   * The defect this guards: the page wrapper widened to 1200px while three
   * component caps stayed at their literals, so at 1920px the Validator card
   * ended 440px short of the tab underline above it, the Schema browser 280px
   * short, and the Settings cards 340px short of the version card. Each keeps
   * its literal as the FALLBACK so a mount outside a width mode is unchanged.
   */
  it.each([
    ['record-validator.css', '.rec-val', '760px'],
    ['schema-browser.css', '.schema-browser', '920px'],
  ])('%s — %s consumes --content-max (fallback %s)', (file, selector, fallback) => {
    const rule = cssRules(cssByName(file)).find((r) => r.selector === selector);
    expect(rule, `${file} must declare ${selector}`).toBeDefined();
    expect(rule?.body).toMatch(
      new RegExp(`max-width\\s*:\\s*var\\(--content-max,\\s*${fallback}\\)`),
    );
  });

  it('screens.css — .settings-card consumes --content-max (fallback 860px)', () => {
    const rule = cssRules(cssByName('screens.css')).find((r) => r.selector === '.settings-card');
    expect(rule, 'screens.css must declare .settings-card').toBeDefined();
    expect(rule?.body).toMatch(/max-width\s*:\s*var\(--content-max,\s*860px\)/);
  });

  it('screens.css — .governance-panel shares the page measure', () => {
    const rule = cssRules(cssByName('screens.css')).find((r) => r.selector === '.governance-panel');
    expect(rule, 'screens.css must declare .governance-panel').toBeDefined();
    expect(rule?.body).toMatch(/max-width\s*:\s*var\(--content-max,\s*640px\)/);
  });
});

// --- 4. every screen that was mapped actually opts in ----------------------

describe('screens opt into the width system', () => {
  it('Project Memory renders wide', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusAvailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
    });
    const { container, findByText } = routerRender(<ProjectMemory />, '/memory');
    await findByText('Memory Available');
    expect(mainOf(container).getAttribute('data-width')).toBe('wide');
  });

  it('Governance & Safety renders wide', () => {
    // The default Policy tab issues no request; Validator / Schema mount lazily.
    stubFetchRoutes({});
    const { container } = routerRender(<GovernancePage />, '/governance');
    expect(mainOf(container).getAttribute('data-width')).toBe('wide');
  });

  it('Settings renders wide', async () => {
    stubFetchRoutes({
      'GET /api/about': { body: aboutResponse },
      'GET /api/openapi': { body: openApiFixture },
    });
    const { container, findByText } = routerRender(<SettingsPage />, '/settings');
    await findByText('0.1.0'); // Help/About resolved — settles both card fetches
    expect(mainOf(container).getAttribute('data-width')).toBe('wide');
  });

  it('Statistics renders wide', async () => {
    stubFetchRoutes(statisticsRoutes());
    const { container, findByText } = routerRender(<StatisticsPage />, '/statistics');
    await findByText('Synthetic-Only'); // the /api/about card resolved
    expect(mainOf(container).getAttribute('data-width')).toBe('wide');
  });

  it('Guided Completion renders readable — on the LOADED shell', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container } = routerRender(<AppRoutes />, '/record/demo/complete');
    // `.centered-col.narrow` exists only on the loaded branch, so waiting on it
    // proves we are asserting the real surface and not the loading fallback.
    await waitFor(() => expect(container.querySelector('.centered-col.narrow')).not.toBeNull());
    expect(mainOf(container).getAttribute('data-width')).toBe('readable');
  });
});

describe('all four Governance regions share one measure', () => {
  /*
   * The header and the Policy panel are `.placeholder`; the Validator and
   * Schema panels host whole components and are `.governance-panel`. Both
   * classes read the SAME `--content-max`, so the tab underline can no longer
   * run 440px wider than the card beneath it. `.governance-panel` is used in
   * place of `.placeholder` on purpose: `.placeholder p` (0-1-1) would beat the
   * components' own 0-1-0 paragraph classes and restyle their body text.
   */
  it('the Validator panel is a measured wrapper, not a bare inline-styled div', () => {
    stubFetchRoutes({});
    const { container } = routerRender(<GovernancePage />, '/governance');
    const panel = container.querySelector('#governance-tabpanel-policy');
    expect(panel?.className).toBe('placeholder');
  });

  /** The panel must carry the shared measure as a CLASS, with no inline literal. */
  const expectMeasuredPanel = (container: HTMLElement, tab: string) => {
    const panel = container.querySelector(`#governance-tabpanel-${tab}`) as HTMLElement | null;
    expect(panel, `#governance-tabpanel-${tab} must render`).not.toBeNull();
    expect(panel?.classList.contains('governance-panel')).toBe(true);
    expect(panel?.style.marginTop, 'offset belongs in the class, not an inline style').toBe('');
  };

  it('the Validator tab panel uses .governance-panel', () => {
    stubFetchRoutes({}); // the Validator issues no request until Validate is pressed
    const { container, getByRole } = routerRender(<GovernancePage />, '/governance');
    fireEvent.click(getByRole('tab', { name: 'Validator' }));
    expectMeasuredPanel(container, 'validator');
  });

  it('the Schema Reference tab panel uses .governance-panel', async () => {
    stubFetchRoutes({
      'GET /api/schema': {
        body: {
          schema_title: 't',
          schema_version: '1.05',
          schema: { properties: {} },
          vocabularies: {},
        },
      },
    });
    const { container, getByRole, findByRole } = routerRender(<GovernancePage />, '/governance');
    fireEvent.click(getByRole('tab', { name: 'Schema Reference' }));
    // settle the lazy schema fetch so the assertion runs against the loaded panel
    await findByRole('heading', { name: 'Schema Reference', level: 2 });
    expectMeasuredPanel(container, 'schema');
  });
});

describe('screens that were NOT mapped keep their historic width', () => {
  it('Experiments home publishes no width mode', async () => {
    stubFetchRoutes(bundleRoutes());
    const { container } = routerRender(<AppRoutes />, '/experiments');
    await waitFor(() => expect(container.querySelector('main')).not.toBeNull());
    expect(mainOf(container).hasAttribute('data-width')).toBe(false);
  });

  it('New Record (centered-col, 1040px) publishes no width mode', () => {
    stubFetchRoutes({});
    const { container } = routerRender(<AppRoutes />, '/load');
    expect(mainOf(container).hasAttribute('data-width')).toBe(false);
  });

  /*
   * Replaces the previous `Export Readiness renders full` assertion, which was
   * tautological (`full` == `--content-max: none` == the uncapped behaviour the
   * screen already had) AND a trap: `--content-max: none` is inherited, so any
   * future card with its own cap would have rendered uncapped here. The screen
   * now opts out; this locks that in on the LOADED shell.
   */
  it('Export Readiness publishes no width mode — it is uncapped by structure, not by a token', async () => {
    stubFetchRoutes(exportReadyRoutes('demo'));
    const { container } = routerRender(<AppRoutes />, '/record/demo/export');
    // The StatusBar mounts only on the loaded branch.
    await waitFor(() => expect(container.querySelector('.statusbar')).not.toBeNull());
    const main = mainOf(container);
    expect(main.hasAttribute('data-width')).toBe(false);
    // and it genuinely has no measure wrapper to cap
    expect(container.querySelector('main .placeholder, main .centered-col')).toBeNull();
  });
});
