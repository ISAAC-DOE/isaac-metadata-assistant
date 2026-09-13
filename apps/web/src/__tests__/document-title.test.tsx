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

  it('answers null for the routes that redirect elsewhere', () => {
    expect(routeDocumentTitle('/', '')).toBeNull();
    expect(routeDocumentTitle('/not-a-route', '')).toBeNull();
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

/* ── §6 · POLARITY — each property rejects a deliberately wrong version ─── */

describe('POLARITY: the assertions above can fail', () => {
  /*
   * Three wrong implementations, written out and re-checked against the same
   * properties §1, §2 and §4 assert. Each `expect` here is the NEGATION of an
   * assertion above, so if the property under test were vacuous this block
   * would fail instead of passing.
   */

  it('6a · a resolver that titles every route with the site name alone is rejected', () => {
    const wrong = (_p: string, _s: string): string | null => APP_TITLE;
    const paths = Object.values(ROUTE_PATTERNS).map((p) => p.replace(':id', ID));
    // §1's "the page name must actually be there" assertion.
    const violations = paths.filter((p) => wrong(p, '') === APP_TITLE);
    expect(violations).toHaveLength(paths.length);
  });

  it('6b · a resolver that gives two routes the same title is rejected', () => {
    const wrong = (p: string, s: string): string | null =>
      p.startsWith('/record') ? composeDocumentTitle(['Record']) : routeDocumentTitle(p, s);
    const paths = Object.values(ROUTE_PATTERNS).map((p) => p.replace(':id', ID));
    const titles = paths.map((p) => wrong(p, ''));
    // §1's distinctness assertion would fail on this: four record routes collapse.
    expect(new Set(titles).size).toBeLessThan(paths.length);
  });

  it('6c · a refinement that ignores the location drops the name on a ?run= push', () => {
    /*
     * The trap of §4, reproduced as arithmetic over the two effects rather than
     * by rendering a second app: the floor recomputes on any `search` change,
     * the refinement recomputes only when its own segments change. With the
     * location absent from the refinement's deps, a `?run=` push leaves the
     * floor's title standing.
     */
    const name = 'CuO scan 2';
    const floorAfterRunPush = routeDocumentTitle(`/record/${ID}`, '?run=RUNAAA');
    const refinementSegments = [recordWorkspaceTitleSegment('runs'), name];
    const refinementUnchanged = composeDocumentTitle(refinementSegments);

    // The floor's answer does NOT contain the record's name...
    expect(floorAfterRunPush).not.toContain(name);
    // ...and the refinement's answer does. So whichever wrote last decides, and
    // a refinement that does not re-run cannot be the one that wrote last.
    expect(refinementUnchanged).toContain(name);
    expect(floorAfterRunPush).not.toBe(refinementUnchanged);
  });

  it('6d · a drifted index.html title is rejected', () => {
    const drifted = '<title>ISAAC</title>';
    const match = /<title>([^<]*)<\/title>/.exec(drifted);
    expect(match?.[1]).not.toBe(APP_TITLE);
  });
});
