/*
 * WCAG 2.4.2 *Page Titled* — every route, and the two ways a title can lie.
 *
 * ── WHAT WAS TRUE BEFORE THIS FILE EXISTED ──────────────────────────────────
 *
 * Nothing. Measured 2026-09-12 and again 2026-09-13:
 * `grep -ran 'document\.title\|useDocumentTitle' apps/web/src/` returned **0
 * hits**, so all eleven routes announced the same static eight words from
 * `index.html` to a screen reader, a tab strip, a bookmark and a window
 * switcher. There was no failing test to invert here; there was no test.
 *
 * ── WHY EACH ASSERTION IS HERE ──────────────────────────────────────────────
 *
 * 1. §1 pins a DISTINCT title per route, derived from `ROUTE_PATTERNS` rather
 *    than from a hand-written list — so a twelfth route with no title fails
 *    here instead of shipping with the eleventh's name in the tab strip.
 * 2. §2 reads `index.html` off disk rather than trusting `APP_TITLE`. The first
 *    paint, before React mounts, uses the HTML; if the two drift, the suffix
 *    changes under the reader at mount for no reason they can see.
 * 3. §3 pins the record REFINEMENT: the record's own name reaches the title.
 * 4. §4 is the one that exists because of a specific measured trap, not a
 *    hypothesis — see its own comment. It is the reason `useDocumentTitle`'s
 *    dependency list carries the location it does not read.
 * 5. §5 pins that the route-derived FLOOR and the SCREEN agree about which
 *    workspace a URL resolves to. A title naming a workspace the screen is not
 *    rendering is a false claim about the page in the one place a reader cannot
 *    see the page to check it.
 * 6. §6 is POLARITY. This repository has shipped an inverted disclosure guard
 *    before, and §11's durable rule is that a test which cannot fail is not
 *    evidence. Each of the three central properties is re-checked against a
 *    deliberately WRONG implementation and must reject it.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { AppRoutes } from '../App';
import {
  bundleRoutes,
  runFixture,
  runsPage,
  stubFetchRoutes,
} from '../test/apiFixtures';
import {
  APP_TITLE,
  composeDocumentTitle,
  routeDocumentTitle,
  recordWorkspaceTitleSegment,
} from '../lib/documentTitle';
import { RECORD_VIEW_IDS, ROUTE_PATTERNS, resolveRecordView } from '../lib/routes';
import { LABELS } from '../lib/labels';

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

function Nav() {
  const loc = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <span data-testid="address">{`${loc.pathname}${loc.search}`}</span>
      <button
        type="button"
        data-testid="next-run"
        onClick={() => navigate(`/record/${ID}?view=runs&run=RUNBBB`)}
      >
        next run
      </button>
      <button type="button" data-testid="go-graph" onClick={() => navigate(`/record/${ID}?view=graph`)}>
        graph
      </button>
    </>
  );
}

function renderAt(path: string) {
  stubFetchRoutes({
    ...bundleRoutes(ID),
    [`GET ${BASE}/runs`]: { body: runsPage([runFixture({ id: 'RUNAAA', label: 'Run 1' })]) },
  } as never);
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Nav />
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.title = APP_TITLE;
});

/* ── §1 · every route has its own title ─────────────────────────────────── */

describe('every route is titled, and no two routes share a title', () => {
  /*
   * DERIVED FROM THE ROUTE TABLE, not from a hand-written list. `:id` is
   * substituted rather than pattern-matched, because `routeDocumentTitle` takes
   * a real pathname.
   *
   * `/` and the `*` fallback are deliberately absent: both `<Navigate replace>`
   * elsewhere, and `routeDocumentTitle` answers `null` for them so the title of
   * a page nobody is on is never written. §1c pins that null.
   */
  const paths = Object.values(ROUTE_PATTERNS).map((p) => p.replace(':id', ID));

  it('resolves a title for every pattern in ROUTE_PATTERNS', () => {
    for (const path of paths) {
      const title = routeDocumentTitle(path, '');
      expect(title, `no document title for route ${path}`).not.toBeNull();
      expect(title).toContain(APP_TITLE);
      // The page name must actually be there — a bare site name satisfies the
      // letter of "has a title" and none of its purpose.
      expect(title).not.toBe(APP_TITLE);
    }
  });

  it('gives every route a DISTINCT title', () => {
    const titles = paths.map((p) => routeDocumentTitle(p, ''));
    expect(new Set(titles).size).toBe(paths.length);
  });

  /*
   * QA-020 — THIS TEST IS INVERTED IN HALF, NOT DELETED. It used to read
   * "answers null for the routes that redirect elsewhere" and assert null for BOTH
   * `/` and `/not-a-route`. That was correct when `path="*"` was
   * `<Navigate to={ROUTES.experiments} replace />`, and it was pinning the defect:
   * an unrecognised address silently became My Experiments.
   *
   * `/` STILL redirects and still owes no title — the reader is never on it.
   * `/not-a-route` now RENDERS `screens/NotFound`, which is a real destination a
   * reader sits on and reads a browser tab for, so WCAG 2.4.2 applies to it like
   * any other screen. Returning null there would leave the PREVIOUS screen's title
   * in the tab while a not-found page is on screen — a false claim in the one place
   * the reader cannot see the page to check it.
   */
  it('answers null for `/`, which redirects — but TITLES the not-found screen, which does not', () => {
    expect(routeDocumentTitle('/', '')).toBeNull();

    const notFound = routeDocumentTitle('/not-a-route', '');
    expect(notFound).not.toBeNull();
    expect(notFound).toContain(LABELS.screenNotFound);
    expect(notFound).toContain(APP_TITLE);

    // MUTATION GUARD: the not-found title must not be reachable by any RECOGNISED
    // address. If a real route ever falls through to the `default` branch it would
    // be titled "Page not found" while rendering correctly, and the §1 sweep over
    // every declared route below is what catches that — this asserts the converse,
    // that several unrelated unrecognised shapes all land on the same honest title.
    for (const p of ['/validator', '/record', '/settings/extra', '/a/b/c', '/Experiments']) {
      expect(routeDocumentTitle(p, ''), p).toBe(notFound);
    }
  });

  it('names each of the four record workspaces', () => {
    const titles = RECORD_VIEW_IDS.map((v) =>
      routeDocumentTitle(`/record/${ID}`, `?view=${v}`),
    );
    expect(new Set(titles).size).toBe(RECORD_VIEW_IDS.length);
    for (const v of RECORD_VIEW_IDS) {
      expect(routeDocumentTitle(`/record/${ID}`, `?view=${v}`)).toContain(
        recordWorkspaceTitleSegment(v),
      );
    }
  });

  it('drops empty segments rather than emitting a dangling separator', () => {
    expect(composeDocumentTitle(['Runs', null])).toBe(`Runs · ${APP_TITLE}`);
    expect(composeDocumentTitle([null, undefined, '   '])).toBe(APP_TITLE);
    expect(composeDocumentTitle(['Runs', 'CuO'])).toBe(`Runs · CuO · ${APP_TITLE}`);
  });
});

/* ── §2 · the first paint and the mounted app agree ─────────────────────── */

describe('the static HTML title and APP_TITLE', () => {
  it('are the same string, read from index.html rather than trusted', () => {
    const html = readFileSync(resolve(__dirname, '../../index.html'), 'utf-8');
    const match = /<title>([^<]*)<\/title>/.exec(html);
    expect(match, 'index.html has no <title>').not.toBeNull();
    expect(match?.[1]).toBe(APP_TITLE);
  });
});

/* ── §3 · the record screen refines the title with the record's name ────── */

describe('the record screen', () => {
  it('adds the record name to the title once the bundle has loaded', async () => {
    renderAt(`/record/${ID}`);
    await screen.findByRole('heading', { level: 1 });
    await waitFor(() => {
      expect(document.title).toContain(recordWorkspaceTitleSegment('fields'));
    });
    // The name comes from loaded data. It is asserted against the SAME visible
    // heading text rather than against a literal, so a fixture rename moves both.
    const h1 = screen.getByRole('heading', { level: 1 }).textContent ?? '';
    const name = h1.replace(recordWorkspaceTitleSegment('fields'), '').trim();
    expect(name.length).toBeGreaterThan(0);
    await waitFor(() => expect(document.title).toContain(name));
    expect(document.title).toContain(APP_TITLE);
  });

  it('titles the not-yet-loaded record by its workspace and never guesses a name', () => {
    // No fetch stub: the bundle cannot reach `data`, which is the state under
    // test. The floor still titles the page, and says nothing about the record.
    render(
      <MemoryRouter
        initialEntries={[`/record/${ID}?view=runs`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    expect(document.title).toBe(
      `${recordWorkspaceTitleSegment('runs')} · ${APP_TITLE}`,
    );
    expect(document.title).not.toMatch(/loading|undefined|null|demo/i);
  });
});

/* ── §4 · the measured trap ─────────────────────────────────────────────── */

describe('a navigation that changes only a non-view parameter', () => {
  /*
   * THE REASON `useDocumentTitle` DEPENDS ON THE LOCATION IT DOES NOT READ —
   * and the scenario had to be corrected before it caught anything.
   *
   * ── THE FIRST VERSION OF THIS TEST DID NOT FAIL ON THE DEFECT ────────────
   *
   * It navigated from a bare `/record/<id>` to `?run=RUNAAA` and asserted the
   * name survived. Run against a MUTANT whose refinement dependency list was
   * `[composed]` alone — the exact implementation this test exists to reject —
   * it **PASSED, 18/18**. The reason is that `?run=` with no `?view=` resolves
   * to the `runs` workspace, so `composed` changed too and the refinement
   * re-ran for an unrelated reason. A test whose navigation happens to move the
   * value it is watching cannot see whether the location mattered.
   *
   * ── THE NAVIGATION THAT ACTUALLY ISOLATES IT ─────────────────────────────
   *
   * Run A → run B, both on `?view=runs`. The workspace label is unchanged and
   * the record is unchanged, so the refinement's `composed` is byte-identical
   * while `search` moves — which is precisely the case where the floor writes
   * last and the record's name disappears from the tab strip. It is a real user
   * action: `RunsSection`'s Previous/Next controls push exactly this.
   *
   * Verified: the `[composed]` mutant FAILS this assertion, and the shipped
   * `[composed, pathname, search]` passes it.
   */
  it('keeps the record name in the title across a run-to-run switch', async () => {
    renderAt(`/record/${ID}?view=runs&run=RUNAAA`);
    await screen.findByRole('heading', { level: 1 });
    const h1 = screen.getByRole('heading', { level: 1 }).textContent ?? '';
    const name = h1.replace(recordWorkspaceTitleSegment('runs'), '').trim();
    expect(name.length).toBeGreaterThan(0);
    await waitFor(() => expect(document.title).toContain(name));

    fireEvent.click(screen.getByTestId('next-run'));
    await waitFor(() =>
      expect(screen.getByTestId('address').textContent).toBe(
        `/record/${ID}?view=runs&run=RUNBBB`,
      ),
    );
    // The floor has certainly re-run (its deps include `search`); the question
    // is whether the refinement re-ran after it.
    expect(routeDocumentTitle(`/record/${ID}`, '?view=runs&run=RUNBBB')).not.toContain(name);
    await waitFor(() => expect(document.title).toContain(name));
  });

  it('follows the workspace when the view DOES change', async () => {
    renderAt(`/record/${ID}`);
    await screen.findByRole('heading', { level: 1 });
    fireEvent.click(screen.getByTestId('go-graph'));
    await waitFor(() =>
      expect(document.title).toContain(recordWorkspaceTitleSegment('graph')),
    );
    expect(document.title).not.toContain(recordWorkspaceTitleSegment('fields'));
  });
});

/* ── §5 · the floor and the screen resolve the same workspace ───────────── */

describe('the route-derived floor and the record screen', () => {
  /*
   * ONE FUNCTION, ASSERTED AS ONE. `resolveRecordView` is what both call; this
   * pins the CONSEQUENCE — that a run deep link with no `?view=` is titled
   * `Runs` — so that inlining the rule back into either caller fails here.
   */
  it('agree that a bare run address resolves to Runs', () => {
    expect(resolveRecordView('?run=RUNAAA')).toBe('runs');
    expect(routeDocumentTitle(`/record/${ID}`, '?run=RUNAAA')).toBe(
      `${recordWorkspaceTitleSegment('runs')} · ${APP_TITLE}`,
    );
    expect(resolveRecordView('?compare=A&compare=B')).toBe('runs');
    expect(routeDocumentTitle(`/record/${ID}`, '?compare=A&compare=B')).toBe(
      `${recordWorkspaceTitleSegment('runs')} · ${APP_TITLE}`,
    );
  });

  it('agree that an unrecognised view falls back to Record Fields', () => {
    expect(resolveRecordView('?view=nonsense')).toBe('fields');
    expect(routeDocumentTitle(`/record/${ID}`, '?view=nonsense')).toBe(
      `${recordWorkspaceTitleSegment('fields')} · ${APP_TITLE}`,
    );
  });

  it('agree that an explicit view beats a run address', () => {
    expect(resolveRecordView('?view=graph&run=RUNAAA')).toBe('graph');
    expect(routeDocumentTitle(`/record/${ID}`, '?view=graph&run=RUNAAA')).toBe(
      `${recordWorkspaceTitleSegment('graph')} · ${APP_TITLE}`,
    );
  });

  it('titles a record SUB-ROUTE by the destination, not by a workspace', () => {
    // `/record/:id/export` is a different screen, not a fifth workspace. Its
    // title must not be produced by the `?view=` branch, which would answer
    // `Record Fields` for it.
    const title = routeDocumentTitle(`/record/${ID}/export`, '');
    expect(title).not.toContain(recordWorkspaceTitleSegment('fields'));
    expect(title).not.toBeNull();
  });
});

/* ── §6 · POLARITY — recorded honestly, after a review showed it was not ──── */

/*
 * *** THIS BLOCK USED TO BE FOUR CLOSED-FORM TAUTOLOGIES, AND AN INDEPENDENT
 * REVIEW WAS RIGHT TO SAY SO. ***
 *
 * Each old "polarity" test defined a WRONG implementation inline and then
 * asserted that the wrong implementation was wrong — e.g. `wrong = () =>
 * APP_TITLE`, then `expect(paths.filter(p => wrong(p) === APP_TITLE)).toHaveLength(
 * paths.length)`. That is true by construction. It exercised none of the
 * assertions in §1–§5, so it could not establish that any of them would notice a
 * defect. It read like a mutation proof and was arithmetic about a local variable.
 *
 * **THE REAL MUTATION PROOF WAS RUN, AND IT LIVES IN THE COMMIT MESSAGE RATHER
 * THAN HERE, BECAUSE THAT IS WHERE IT CAN BE HONEST.** Six mutants were applied
 * to the actual implementation files and the suite re-run each time:
 *
 *     M1  refinement deps `[composed]` only        -> 1 failed  (§4)
 *     M2  every title is the site name alone       -> 12 failed (§1)
 *     M3  record branch ignores `?view=`           -> 4 failed  (§1, §5)
 *     M4  the `*` fallback route gets a title      -> 1 failed  (§1c)
 *     M5  `<DocumentTitle />` not mounted          -> 1 failed  (§3b)
 *     M6  the `/export` sub-route branch removed   -> 2 failed  (§5)
 *     baseline (all restored)                      -> 18 passed
 *
 * Every one was caught by a NAMED assertion in §1–§5. So the guards are
 * load-bearing; what was worthless was the block that claimed to prove it.
 *
 * ── WHAT REPLACES IT, AND WHY THIS IS NOT THE SAME MISTAKE ─────────────────
 *
 * One test, which mutates nothing and asserts nothing about a local variable. It
 * pins the two STRUCTURAL properties that make M1–M6 catchable at all, and both
 * are read out of the real modules:
 *
 *   · `useDocumentTitle`'s effect depends on the location it does not read —
 *     without that, M1 is invisible (§4's scenario proves the behaviour; this
 *     proves the mechanism is still present to be depended on).
 *   · `<DocumentTitle />` precedes `<Routes />` in `App.tsx` — the ordering the
 *     refinement's precedence rests on, which no rendering assertion can see
 *     because both orders render identically on a first paint.
 *
 * Read as SOURCE TEXT deliberately. These are facts about how the modules are
 * written, not about what they render, and a test that pretended to derive them
 * from the DOM would be the same category error as the block it replaces.
 */

describe('§6 the two structural properties the mutation proofs depend on', () => {
  it('useDocumentTitle depends on the location it does not read', () => {
    const src = readFileSync(resolve(__dirname, '../lib/useDocumentTitle.ts'), 'utf-8');
    // The refinement effect's dependency array. `composed` alone is mutant M1.
    expect(src).toMatch(/\}, \[composed, pathname, search\]\);/);
    expect(src).not.toMatch(/\}, \[composed\]\);/);
  });

  it('DocumentTitle precedes Routes in App.tsx, which is what makes refinement win', () => {
    const app = readFileSync(resolve(__dirname, '../App.tsx'), 'utf-8');
    const floor = app.indexOf('<DocumentTitle />');
    const routes = app.indexOf('<Routes>');
    expect(floor, '<DocumentTitle /> is not mounted at all — mutant M5').toBeGreaterThan(-1);
    expect(routes).toBeGreaterThan(-1);
    expect(
      floor,
      'swapping these two lines silently reverses title precedence: the route-derived ' +
        'floor would run AFTER a screen refinement and overwrite the record name',
    ).toBeLessThan(routes);
  });
});

/* ── §7 · an empty parameter is absent, on BOTH halves of the run check ───── */

describe('§7 resolveRecordView treats an empty parameter as absent', () => {
  /*
   * FOUND BY INDEPENDENT REVIEW, 2026-09-13. The two halves of the run-address
   * check disagreed: `run` used `(get(...) ?? '') !== ''` (empty is absent —
   * right), while `compare` used `getAll(...).length > 0`, and `getAll` returns
   * `['']` for `?compare=`. So an EMPTY compare counted as a run address and an
   * empty run did not.
   *
   * Small but real: a link carrying a valueless `?compare=` opened Runs with
   * nothing selected, and out-ranked a `?proposal=` that did name something.
   */
  it('an empty compare is ignored, exactly as an empty run already was', () => {
    expect(resolveRecordView('?run=&proposal=X')).toBe('capture');
    // The defect: this used to be 'runs'.
    expect(resolveRecordView('?compare=&proposal=X')).toBe('capture');
    expect(resolveRecordView('?compare=')).toBe('fields');
    expect(resolveRecordView('?run=')).toBe('fields');
  });

  it('a NON-empty compare still wins, so the fix did not disable the branch', () => {
    expect(resolveRecordView('?compare=A&proposal=X')).toBe('runs');
    expect(resolveRecordView('?run=A&proposal=X')).toBe('runs');
    expect(resolveRecordView('?compare=A&compare=B')).toBe('runs');
    // A mix of empty and real: the real one decides.
    expect(resolveRecordView('?compare=&compare=B')).toBe('runs');
  });

  it('the title floor agrees, because it is the same function', () => {
    expect(routeDocumentTitle('/record/demo', '?compare=&proposal=X')).toBe(
      `${recordWorkspaceTitleSegment('capture')} · ${APP_TITLE}`,
    );
    expect(routeDocumentTitle('/record/demo', '?compare=A')).toBe(
      `${recordWorkspaceTitleSegment('runs')} · ${APP_TITLE}`,
    );
  });
});
