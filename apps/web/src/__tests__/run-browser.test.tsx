/*
 * THE BOUNDED RUN BROWSER — paging, search, filters, Focus Run, and the counts.
 *
 * WHAT THIS FILE IS FOR. `docs/run-scale-measurements.md` measured a 7.47 MiB
 * response at 1000 runs and ruled virtualization out; the fix is to stop
 * downloading the whole list. Every assertion here is written so that it would
 * FAIL against the unpaged component this replaced — a test that passes both
 * before and after is not a test of this slice, and this repository has shipped
 * green tests that protected nothing before (including a disclosure test that
 * passed with inverted polarity). The negative controls are named in the test
 * titles where they are not obvious.
 *
 * THE ONE THAT MATTERS MOST is the pair of totals. `matched` (how many runs
 * satisfy the current search) and `total` (how many runs the record HAS) are
 * equal until someone types in the search box, which is exactly why conflating
 * them is invisible in a fixture and catastrophic on a real record. Two tests
 * below exist only to hold them apart, and both use a query that matches a
 * PROPER SUBSET so the numbers actually differ.
 *
 * THE FETCH STUB IS QUERY-AWARE, and it has to be: the shared
 * `stubFetchRoutes` keys routes on the whole URL, so a route registered for
 * `GET …/runs` cannot answer `?limit=50&offset=0` differently from
 * `?limit=50&offset=50`. The wrapper below serves the runs listing from a real
 * in-memory list, applying the same filter-then-page order the backend
 * documents, and delegates every other call to the shared stub. That means a
 * paging bug in the component produces a wrong LIST here, not a stub miss — and
 * an unrouted call still throws, so nothing passes by accident.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { RunsSection, RUNS_PAGE_SIZE, RUN_SEARCH_DEBOUNCE_MS } from '../components/RunsSection';
import { AUTOSAVE_DEBOUNCE_MS } from '../lib/useRunAutosave';
import { __resetRunAutosaveStore, snapshotFor } from '../lib/runAutosaveStore';
import { RECORD_RUN_PARAM, ROUTES } from '../lib/routes';
import {
  runFixture,
  stubFetchRoutes,
  VERSION_FIELDS,
  type RouteEntry,
} from '../test/apiFixtures';

// A CEILING, NOT A DELAY. Several tests here render a hundred cards, and a shared
// CI runner has been measured taking 25 s over a file of this kind while it took
// 7 s locally; testing-library's default budget is 1,000 ms, which is an assumption
// about the host rather than an assertion about the product. Every `find*`/`waitFor`
// still resolves as soon as the DOM is ready, and a page that never arrives still
// never arrives.
configure({ asyncUtilTimeout: 5_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

type Run = ReturnType<typeof runFixture>;

/**
 * One cheap run. `inherited` is emptied deliberately: the inherited block is what
 * makes a real response large, and this file is about how MANY runs cross the
 * wire, not what is in one.
 */
function mkRun(n: number, over: Record<string, unknown> = {}): Run {
  return runFixture({
    id: `RUN${String(n).padStart(3, '0')}`,
    label: `Run ${n}`,
    ordinal: n,
    version: `r${n}.0`,
    fields: {},
    inherited: {},
    ...over,
  });
}

interface RunsQuery {
  limit: number | null;
  offset: number;
  q: string | null;
  overrides: string | null;
  exported: string | null;
}

/** Every runs-listing request, as the component actually sent it. */
interface RunsCall {
  url: string;
  query: RunsQuery;
}

function parseQuery(url: string): RunsQuery {
  const params = new URLSearchParams(url.split('?')[1] ?? '');
  const limit = params.get('limit');
  return {
    limit: limit === null ? null : Number(limit),
    offset: Number(params.get('offset') ?? '0'),
    q: params.get('q'),
    overrides: params.get('overrides'),
    exported: params.get('exported'),
  };
}

/**
 * The backend's documented behaviour, in fifteen lines: FILTER FIRST, THEN PAGE.
 * The order is load-bearing — paging before filtering would make `matched` a
 * property of the page rather than of the record, which is precisely the
 * conflation the counts are meant to prevent.
 */
function serveRuns(all: Run[], query: RunsQuery) {
  const q = (query.q ?? '').trim().toLowerCase();
  let matched = all;
  if (q !== '') {
    matched = matched.filter(
      (r) =>
        r.label.toString().toLowerCase().includes(q) ||
        r.id.toString().toLowerCase().includes(q) ||
        (/^\d+$/.test(q) && String(r.ordinal) === q),
    );
  }
  if (query.overrides !== null) {
    const has = (r: Run) => Object.keys(r.inherited as object).length > 0;
    matched = matched.filter((r) => (query.overrides === 'any' ? has(r) : !has(r)));
  }
  if (query.exported !== null) {
    const want = query.exported === 'true';
    matched = matched.filter((r) => (r.record_id !== null) === want);
  }
  const limit = query.limit ?? matched.length;
  const page = matched.slice(query.offset, query.offset + limit);
  return {
    runs: page,
    experiment_version: VERSION_FIELDS.version,
    total: all.length,
    matched: matched.length,
    returned: page.length,
    offset: query.offset,
  };
}

/**
 * Stub `fetch`, serving the runs LISTING from `handler` and routing every other
 * call through the shared stub with the `extra` routes this test registered.
 *
 * Returns the list of runs-listing calls, so a test can assert WHAT WAS ASKED FOR
 * and not merely what came back. That distinction is the negative control for
 * bounding: a component that renders 50 of 120 runs because the stub only gave it
 * 50 looks identical on screen to one that asked for 50.
 */
function stubBackend(
  handler: (query: RunsQuery) => unknown,
  extra: Record<string, RouteEntry> = {},
): RunsCall[] {
  stubFetchRoutes(extra);
  const inner = globalThis.fetch as unknown as (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => Promise<Response>;
  const calls: RunsCall[] = [];

  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const raw =
        typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const path = raw.replace(/^https?:\/\/[^/]+/, '');
      const method = init?.method ?? 'GET';
      const isListing =
        method === 'GET' && (path === `${BASE}/runs` || path.startsWith(`${BASE}/runs?`));
      if (!isListing) return inner(input, init);
      const query = parseQuery(path);
      calls.push({ url: path, query });
      const body = handler(query);
      return {
        ok: true,
        status: 200,
        headers: { get: () => null },
        json: async () => body,
      } as unknown as Response;
    }),
  );
  return calls;
}

/** The current URL, so a test can assert that focus is really in it. */
function LocationProbe() {
  const location = useLocation();
  return <div data-testid="url">{`${location.pathname}${location.search}`}</div>;
}

/**
 * THE SECTION IS MOUNTED DIRECTLY, NOT THROUGH THE RECORD SCREEN, and that is a
 * cost decision with a measured reason rather than a shortcut.
 *
 * Several tests here render a hundred run cards; mounting the whole record
 * screen adds a six-endpoint bundle and a field workbench to each of them, and
 * the file went from passing alone to timing out when the full suite ran it
 * alongside 140 others on the same host. The integration this skips — that
 * `RecordWorkbench` mounts this section and disposes the autosave store on the
 * way out — is already covered by `run-workspace.test.tsx`, which mounts the
 * real screen. What is under test HERE is the browser itself.
 *
 * `MemoryRouter` is still real, because the URL is part of the feature: Focus
 * Run is a query parameter, and `useSearchParams` needs a router to read it.
 */
function renderAt(entry: string) {
  return render(
    <MemoryRouter
      initialEntries={[entry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <RunsSection experimentId={ID} />
      <LocationProbe />
    </MemoryRouter>,
  );
}

const renderRecord = () => renderAt(`/record/${ID}`);

/** Every run card currently in the document, by id, in DOM order. */
function renderedIds(): string[] {
  return [...document.querySelectorAll('[data-run-id]')].map(
    (el) => el.getAttribute('data-run-id') ?? '',
  );
}

function countText(): string {
  const el = document.querySelector('.runs-count');
  if (el === null) throw new Error('no .runs-count rendered');
  return el.textContent ?? '';
}

const loadMoreButton = () => screen.queryByRole('button', { name: /Load more runs/ });

/**
 * Wait for the section's own read to have landed.
 *
 * The COUNT is the signal and `Add Run` is not, which is a change this slice
 * forced: a deep link that arrives already focused renders `Back to all runs`
 * where `Add Run` would be, so waiting on the create control would hang on
 * exactly the states the focus tests are about. The count region exists in every
 * mode and only once the list is loaded.
 */
async function waitForList() {
  await waitFor(() => expect(document.querySelector('.runs-count')).not.toBeNull());
}

/** Let pending microtasks (the fetch stub's promise chain) settle under fake timers. */
async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(async () => {
      await Promise.resolve();
    });
  }
}

beforeEach(() => {
  vi.useRealTimers();
  __resetRunAutosaveStore();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// 1 — the read is bounded
// ---------------------------------------------------------------------------

describe('the initial read', () => {
  /*
   * THE NEGATIVE CONTROL IS THE QUERY STRING, NOT THE CARD COUNT. The old
   * component issued `GET …/runs` with no query at all and rendered every run it
   * was given; asserting "50 cards" against a stub that only returns 50 would pass
   * for both. So this asserts `limit` was SENT, which the unpaged component never
   * did, and that the response was in fact a page of a longer list.
   */
  it('asks for a bounded page — `limit` is on the wire, and it is not a full download', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    const calls = stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(RUNS_PAGE_SIZE));

    expect(calls).toHaveLength(1);
    expect(calls[0].query.limit).toBe(RUNS_PAGE_SIZE);
    expect(calls[0].query.offset).toBe(0);
    expect(calls[0].url).toContain('limit=');
    // No search and no filter were applied, so none of them may be on the wire —
    // an always-sent `q=` would make "was a search performed?" unanswerable.
    expect(calls[0].query.q).toBeNull();
    expect(calls[0].query.overrides).toBeNull();
    expect(calls[0].query.exported).toBeNull();

    expect(renderedIds()[0]).toBe('RUN001');
    expect(renderedIds()[RUNS_PAGE_SIZE - 1]).toBe('RUN050');
  });

  it('states the loaded count AND the record total, never the loaded count alone', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(RUNS_PAGE_SIZE));

    // The old toolbar rendered `{runs.length} runs`, which on this record would
    // read "50 runs" — a false statement about a record that has 120.
    expect(countText()).toBe('Showing 50 of 120 runs');
    expect(countText()).not.toBe('50 runs');
  });

  it('announces the counts politely, so a change is not silent to a screen reader', async () => {
    const all = Array.from({ length: 60 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    const region = document.querySelector('.runs-count');
    expect(region?.getAttribute('aria-live')).toBe('polite');
    expect(region?.getAttribute('aria-atomic')).toBe('true');
  });
});

// ---------------------------------------------------------------------------
// 2 — Load More
// ---------------------------------------------------------------------------

describe('Load More', () => {
  it('appends the next page with no duplicates and no gaps, from the right offset', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    const calls = stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(100));

    expect(calls).toHaveLength(2);
    expect(calls[1].query.offset).toBe(50);
    expect(calls[1].query.limit).toBe(RUNS_PAGE_SIZE);

    // NO GAPS and STABLE ORDER: the accumulated list is exactly runs 1..100 in
    // canonical order. A wrong offset shows up here as a missing or repeated run
    // rather than as a count that happens to add up.
    const expected = all.slice(0, 100).map((r) => r.id);
    expect(renderedIds()).toEqual(expected);
    expect(new Set(renderedIds()).size).toBe(100);
    expect(countText()).toBe('Showing 100 of 120 runs');
  });

  it('renders a run once when a second page re-delivers it — offset paging is not a snapshot', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    /*
     * THE RACE, MODELLED RATHER THAN DESCRIBED. A run deleted between the two
     * reads shifts everything after it one place earlier, so the second page
     * legitimately begins with a run that is already on screen. Two cards for one
     * run means two autosave readouts and two sets of controls over one document.
     */
    const calls = stubBackend((q) => {
      const page = serveRuns(all, q);
      if (q.offset === 50) {
        page.runs = [all[49], ...page.runs.slice(0, page.runs.length - 1)];
      }
      return page;
    });
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await waitFor(() => expect(renderedIds().length).toBeGreaterThan(50));

    expect(document.querySelectorAll('[data-run-id="RUN050"]')).toHaveLength(1);
    expect(new Set(renderedIds()).size).toBe(renderedIds().length);
    expect(calls[1].query.offset).toBe(50);
    /*
     * AND THE NEXT OFFSET IS STILL 100. The duplicate was discarded from the
     * LIST, not from the count of what the server handed over — paging from the
     * array length instead would re-request the same overlapping window.
     */
    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await waitFor(() => expect(calls).toHaveLength(3));
    expect(calls[2].query.offset).toBe(100);
  });

  it('does not become a dead button after a duplicate — it stops when the CURSOR is exhausted', async () => {
    /*
     * A CONTROL THAT COULD NEVER DO ANYTHING AGAIN, offered indefinitely.
     *
     * The button was gated on `runs.length < matched` while the cursor it pages
     * from is `received`. The dedupe drops a re-delivered run from the array but
     * not from what the server handed over, so ONE duplicate makes `runs.length`
     * trail `received` permanently and the gate can never close. Measured on this
     * same fixture by clicking further than the dedupe test does: click 3 requests
     * offset 120, and so do clicks 4 through 8 — the same empty window, forever,
     * with nothing changing on screen and no message. Reachable in production
     * whenever a run is created or deleted while a reader is paging.
     *
     * The negative control is the OFFSET LIST. A build that merely stopped
     * rendering the button after some count would show the same card total; what
     * this asserts is that no fourth request was ever made, and that the reader is
     * told why the list is one run short instead of being handed a button.
     */
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    const calls = stubBackend((q) => {
      const page = serveRuns(all, q);
      if (q.offset === 50) {
        page.runs = [all[49], ...page.runs.slice(0, page.runs.length - 1)];
      }
      return page;
    });
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(99));

    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(119));

    /*
     * 120 runs have been RECEIVED and 119 are distinct. There is no further page,
     * so there is no further button — asserted directly rather than through
     * `waitFor`, because the render that put the 119th card on screen is the same
     * one that advanced the cursor. Against the old gate this is an immediate,
     * legible failure instead of a five-second timeout.
     */
    expect(loadMoreButton()).toBeNull();
    expect(calls.map((c) => c.query.offset)).toEqual([0, 50, 100]);

    // The count states what is on screen and what the record holds — both true,
    // and neither claims the missing run is rendered.
    expect(countText()).toBe('Showing 119 of 120 runs');

    // And the shortfall is SAID. The warning beside the button was about exactly
    // this event; withdrawing the button must not withdraw the explanation.
    expect(
      screen.getByText(/All pages have been read, but 1 matching run never arrived/),
    ).toBeInTheDocument();
  });

  it('disappears once everything matching is loaded', async () => {
    const all = Array.from({ length: 60 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));
    expect(loadMoreButton()).not.toBeNull();

    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(60));
    expect(loadMoreButton()).toBeNull();
    expect(countText()).toBe('Showing 60 of 60 runs');
  });

  it('is keyboard-operable and does not throw focus to the top of the page', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    const button = loadMoreButton()!;
    button.focus();
    expect(document.activeElement).toBe(button);
    await act(async () => {
      // `click` is what both Enter and Space dispatch on a real <button>; the
      // point of the assertion is that this is a BUTTON and not a div with an
      // onClick, which is what would make it unreachable.
      expect(button.tagName).toBe('BUTTON');
      fireEvent.click(button);
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(100));

    // More remains, so the control survives and keeps the caret.
    expect(loadMoreButton()).not.toBeNull();
    expect(document.activeElement).toBe(loadMoreButton());
    expect(document.activeElement).not.toBe(document.body);
  });

  it('moves focus into the list when the last page removes the button', async () => {
    const all = Array.from({ length: 60 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    loadMoreButton()!.focus();
    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await waitFor(() => expect(loadMoreButton()).toBeNull());

    // The button the caret was on is gone. It must not have fallen to <body>.
    await waitFor(() => expect(document.activeElement).not.toBe(document.body));
    const card = document.querySelector('[data-run-id="RUN051"]');
    expect(card?.contains(document.activeElement)).toBe(true);
  });

  it('surfaces a failed page without discarding the runs already loaded', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => {
      if (q.offset > 0) throw new TypeError('Failed to fetch');
      return serveRuns(all, q);
    });
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await screen.findByRole('alert');
    expect(renderedIds()).toHaveLength(50);
    expect(countText()).toBe('Showing 50 of 120 runs');
    // And the control is still offered, because retrying is the remedy.
    expect(loadMoreButton()).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 3 — search
// ---------------------------------------------------------------------------

describe('search', () => {
  it('keeps the search box mounted while its own request is in flight', async () => {
    /*
     * A REAL DEFECT, FOUND BY A TEST WRITTEN FOR SOMETHING ELSE.
     *
     * The controls row was gated on the CURRENT read having landed, and a criteria
     * change sets the list to `loading` — so ~300 ms after a scientist stopped
     * typing, the field they had just typed into unmounted, and came back only when
     * the response arrived. A second search term entered in that window went
     * nowhere, and the caret was lost with the element.
     *
     * Nothing caught it: every other test in this file answers instantly, so the
     * gap between "request sent" and "response rendered" was never open long enough
     * to look at. It appeared only when a test held a response deliberately.
     *
     * The list is still allowed to blank — that is honest, the runs really are
     * unknown mid-read. Only the furniture persists.
     */
    const all = Array.from({ length: 30 }, (_, i) => mkRun(i + 1));
    let release: (() => void) | null = null;
    stubBackend((q) => {
      const body = serveRuns(all, q);
      if ((q.q ?? '') === '') return body;
      return new Promise((resolve) => {
        release = () => resolve(body);
      });
    });

    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(30));

    const box = screen.getByLabelText('Search runs');
    await act(async () => {
      fireEvent.change(box, { target: { value: 'Run 3' } });
    });
    await waitFor(() => expect(release).not.toBeNull());

    // MID-FLIGHT: the response is still held open, and the box must still be here.
    expect(screen.queryByLabelText('Search runs')).not.toBeNull();
    expect(screen.getByLabelText('Search runs')).toBe(box);
    expect((box as HTMLInputElement).value).toBe('Run 3');

    await act(async () => {
      release!();
      await Promise.resolve();
    });
    await flush();
    expect(screen.queryByLabelText('Search runs')).not.toBeNull();
  });

  it('keeps the count region the SAME live node across a search, so its own result is announced', async () => {
    /*
     * THE HALF OF THE UNMOUNTING DEFECT THAT WAS LEFT STANDING, and the more
     * consequential half. The controls row was fixed; the TOOLBAR was not, and the
     * toolbar is what holds the `aria-live` count region. A criteria change sets
     * the list to `loading`, so the region was destroyed and a new one built when
     * the response arrived — and a live region that arrives already carrying its
     * text is generally not announced at all. The count change a reader most needs
     * spoken, the one their own search caused, was the one least likely to be
     * spoken. The component's own comment claimed the node "survives … searching
     * and paging"; measured, it did not.
     *
     * NODE IDENTITY IS THE ASSERTION, not the presence of a `.runs-count`. A
     * remount produces an element that passes every text and attribute check and
     * still announces nothing, which is exactly how this survived a suite that
     * asserts both.
     */
    const all = Array.from({ length: 30 }, (_, i) => mkRun(i + 1));
    let release: (() => void) | null = null;
    stubBackend((q) => {
      const body = serveRuns(all, q);
      if ((q.q ?? '') === '') return body;
      return new Promise((resolve) => {
        release = () => resolve(body);
      });
    });

    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(30));

    const region = document.querySelector('.runs-count')!;
    expect(region.textContent).toBe('Showing 30 of 30 runs');

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'Run 3' } });
    });
    await waitFor(() => expect(release).not.toBeNull());

    // MID-FLIGHT. The same node, still the only one — `e2e/mutation/runs.spec.ts`
    // addresses it with a bare `.runs-count` locator, which a second copy would
    // break on strict mode.
    expect(document.querySelectorAll('.runs-count')).toHaveLength(1);
    expect(document.querySelector('.runs-count')).toBe(region);
    // And it states nothing it cannot know: the list it labels is not on screen.
    expect(region.textContent).toBe('');
    /*
     * THE CONTRACT THIS FIX MUST NOT BUY ITSELF WITH. "`Add Run` on screen means
     * the runs are loaded" is what ~18 tests here and `openRunsSection` in the
     * browser suite use to know the section is ready, and there is no experiment
     * version to send with a create mid-read. The furniture persists; the control
     * does not.
     */
    expect(screen.queryByRole('button', { name: /Add Run/ })).toBeNull();

    await act(async () => {
      release!();
      await Promise.resolve();
    });
    await flush();

    // The SAME node now carries the new count — which is what makes it an
    // announcement rather than markup.
    expect(document.querySelector('.runs-count')).toBe(region);
    expect(region.textContent).toBe('Showing 2 of 2 matching · 30 runs in this record');
    expect(screen.queryByRole('button', { name: /Add Run/ })).not.toBeNull();
  });

  it('sends nothing until the debounce has ELAPSED, then exactly one request', async () => {
    /*
     * THIS TEST USED TO PROVE NOTHING ABOUT THE DEBOUNCE. It fired three
     * `fireEvent.change` calls inside ONE `act()`, so React's own batching
     * collapsed them into a single render and a single request — with
     * `RUN_SEARCH_DEBOUNCE_MS` set to 0 it stayed green. What it measured was
     * batching, not elapsed time.
     *
     * So the clock is frozen and moved deliberately: each keystroke RESTARTS the
     * window (trailing edge), nothing leaves before it closes, and exactly one
     * request leaves when it does. Verified against the mutant the old version
     * passed: with the constant set to 0 the very first in-loop assertion fails
     * (three requests where two were expected).
     *
     * The rest of what this test always asserted is unchanged and still here: the
     * query on the wire, and that a search RESETS an accumulated list to a first
     * page rather than searching within it.
     */
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    const calls = stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));
    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(100));
    const before = calls.length;

    vi.useFakeTimers();
    const box = screen.getByLabelText('Search runs');

    // Three keystrokes, each well inside the window of the last.
    for (const value of ['R', 'RU', 'RUN11']) {
      // eslint-disable-next-line no-await-in-loop
      await act(async () => {
        fireEvent.change(box, { target: { value } });
        // A keystroke is not a query: nothing may leave on this tick.
        await vi.advanceTimersByTimeAsync(0);
      });
      // eslint-disable-next-line no-await-in-loop
      await flush();
      expect(calls.length).toBe(before);
      // eslint-disable-next-line no-await-in-loop
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });
    }

    // 100 ms after the LAST keystroke — the two earlier windows were restarted,
    // not merely coalesced, so still nothing has been sent.
    await flush();
    expect(calls.length).toBe(before);

    // One tick past the debounce, and exactly one request goes out.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RUN_SEARCH_DEBOUNCE_MS - 100 + 1);
    });
    await flush();
    expect(calls.length).toBe(before + 1);
    expect(calls[before].query.q).toBe('RUN11');
    // RESET, not append: the new read starts at zero.
    expect(calls[before].query.offset).toBe(0);
    expect(calls[before].query.limit).toBe(RUNS_PAGE_SIZE);

    // RUN110..RUN119 — ten of a hundred and twenty.
    expect(renderedIds()).toHaveLength(10);
    expect(renderedIds()[0]).toBe('RUN110');

    // And the settled query is not re-sent on every later tick.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RUN_SEARCH_DEBOUNCE_MS * 4);
    });
    await flush();
    expect(calls.length).toBe(before + 1);
  });

  it('discards an in-flight Load More page when the criteria change under it', async () => {
    /*
     * THE GENERATION GUARD, WHICH HAD NO TEST AND WAS THEREFORE DELETABLE.
     *
     * An independent mutation run removed both `generation !== generationRef.current`
     * checks and the whole suite stayed green: 91 of 91.
     *
     * THE FIRST ATTEMPT AT THIS TEST RACED TWO SEARCHES AND DID NOT KILL THE MUTANT,
     * which is worth recording because it says exactly what the guard is FOR. The
     * first-page effect has a second, independent defence: its cleanup sets `alive`
     * to false when the effect re-runs, so a superseded first-page response is
     * already discarded without consulting `generation` at all. Racing two searches
     * therefore proves nothing about this guard.
     *
     * LOAD MORE IS WHERE IT IS THE ONLY DEFENCE. It is not an effect, it has no
     * cleanup and no `alive` flag — a `generation` comparison is all that stands
     * between a page requested under the old criteria and the list rendered under
     * the new ones. Without it the stale page APPENDS: runs that do not match the
     * active search are spliced onto the end of the filtered list, `received` is
     * advanced past them, and every subsequent offset is wrong. The counts stay
     * self-consistent throughout, so nothing on screen looks broken.
     */
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    let releaseMore: (() => void) | null = null;
    const calls = stubBackend((q) => {
      const body = serveRuns(all, q);
      // Hold ONLY the unfiltered second page — the one Load More asks for.
      if ((q.q ?? '') === '' && q.offset > 0) {
        return new Promise((resolve) => {
          releaseMore = () => resolve(body);
        });
      }
      return body;
    });

    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    // Load More leaves, and is held open.
    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await waitFor(() => expect(releaseMore).not.toBeNull());
    const beforeSearch = calls.length;

    // The criteria move on while that page is still in flight.
    await act(async () => {
      fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'RUN11' } });
    });
    await waitFor(() => expect(calls.length).toBe(beforeSearch + 1));
    await waitFor(() => expect(renderedIds()).toHaveLength(10));

    // NOW the stale page lands.
    await act(async () => {
      releaseMore!();
      await Promise.resolve();
    });
    await flush();

    // "RUN11" matches RUN110..RUN119 — exactly ten, and the stale page carried
    // fifty runs that match nothing the reader asked for.
    expect(renderedIds()).toHaveLength(10);
    expect(renderedIds()[0]).toBe('RUN110');
    expect(countText()).toContain('10');
  });

  it('says what it searches, in a real label rather than a placeholder', async () => {
    const all = Array.from({ length: 10 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();

    const box = screen.getByLabelText('Search runs') as HTMLInputElement;
    expect(box.getAttribute('placeholder')).toBeNull();
    const hintId = box.getAttribute('aria-describedby');
    const hint = document.getElementById(hintId ?? '');
    // The honest scope, and no claim of fuzziness or meaning.
    expect(hint?.textContent).toContain('Not the scientific values inside a run');
    expect(hint?.textContent ?? '').not.toMatch(/fuzzy|semantic|smart/i);
  });

  /*
   * THE NEGATIVE CONTROL AGAINST CONFLATING `matched` AND `total`.
   *
   * A build that showed the filtered count as the record's size would render "0
   * runs" here and read as though the record had been emptied. Both halves are
   * asserted: the empty state names the record's real total, and the count line
   * keeps it visible too.
   */
  it('shows an honest empty state for no matches, and STILL shows the record total', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Search runs'), {
        target: { value: 'no-such-run' },
      });
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(0));

    expect(screen.getByText(/No run matches this search or these filters/)).toBeInTheDocument();
    expect(screen.getByText(/This record has 120 runs/)).toBeInTheDocument();
    expect(countText()).toBe('Showing 0 of 0 matching · 120 runs in this record');
    // The record is NOT empty, so the empty-record copy must not appear.
    expect(screen.queryByText(/No runs yet\./)).toBeNull();
  });

  it('counts a partial match as matched-of-total, with the record total beside it', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'RUN11' } });
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(10));
    expect(countText()).toBe('Showing 10 of 10 matching · 120 runs in this record');
    expect(countText()).toContain('120 runs in this record');
  });

  it('clears back to the whole record', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'RUN11' } });
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(10));

    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: 'Clear search and filters' })[0]);
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(50));
    expect(countText()).toBe('Showing 50 of 120 runs');
  });
});

// ---------------------------------------------------------------------------
// 4 — filters
// ---------------------------------------------------------------------------

describe('filters', () => {
  it('sends `overrides` and resets the accumulation', async () => {
    const all = Array.from({ length: 120 }, (_, i) =>
      mkRun(i + 1, i < 3 ? { inherited: { 'field:sample.material.name': { state: 'overridden' } } } : {}),
    );
    const calls = stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));
    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(100));
    const before = calls.length;

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Overrides'), { target: { value: 'any' } });
    });
    await waitFor(() => expect(calls.length).toBe(before + 1));
    expect(calls[before].query.overrides).toBe('any');
    expect(calls[before].query.offset).toBe(0);

    await waitFor(() => expect(renderedIds()).toHaveLength(3));
    expect(countText()).toBe('Showing 3 of 3 matching · 120 runs in this record');
  });

  it('sends `exported` as a boolean, and resets', async () => {
    const all = Array.from({ length: 40 }, (_, i) =>
      mkRun(i + 1, i < 2 ? { record_id: `REC${i}` } : {}),
    );
    const calls = stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(40));
    const before = calls.length;

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Export'), { target: { value: 'true' } });
    });
    await waitFor(() => expect(calls.length).toBe(before + 1));
    expect(calls[before].query.exported).toBe('true');
    expect(calls[before].query.offset).toBe(0);
    await waitFor(() => expect(renderedIds()).toHaveLength(2));

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Export'), { target: { value: 'false' } });
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(38));
    expect(calls[calls.length - 1].query.exported).toBe('false');
  });

  it('offers only the two axes the backend has — and no invented review state', async () => {
    const all = Array.from({ length: 5 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();

    const controls = document.querySelector('.runs-controls')!;
    const selects = controls.querySelectorAll('select');
    expect(selects).toHaveLength(2);
    // "Needs review" does not exist anywhere in this product; a control for it
    // would be a state the app invents and cannot answer for.
    expect(controls.textContent ?? '').not.toMatch(/needs review/i);
    for (const select of selects) {
      // A real label, associated — not a placeholder option doing label duty.
      const id = select.getAttribute('id');
      expect(document.querySelector(`label[for="${id}"]`)).not.toBeNull();
    }
  });
});

// ---------------------------------------------------------------------------
// 5 — Focus Run
// ---------------------------------------------------------------------------

describe('Focus Run', () => {
  it('isolates one run, puts it in the URL, and leaving returns the list unchanged', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    const calls = stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    // Reach a list state worth preserving: a search and a second page.
    //
    // THE BASELINE IS TAKEN AFTER THE DEBOUNCED FETCH HAS LANDED, and that is a flake
    // fix rather than a flourish. `RUN_SEARCH_DEBOUNCE_MS` is 300, and the unfiltered
    // page is ALSO 50 rows — so `waitFor(renderedIds()).toHaveLength(50)` can be
    // satisfied by the list that was already on screen, before the search request is
    // issued at all. `callsBefore` was then captured too early, the debounced fetch
    // landed between it and the final `expect(calls.length).toBe(callsBefore)`, and the
    // assertion failed with `expected 2 to be 1`. Measured on CI, where the machine is
    // slow enough for the two events to separate; it passes locally every time.
    //
    // Waiting for the call COUNT to move first makes the baseline mean what the final
    // assertion needs it to mean: the number of reads before focusing, with nothing
    // still in flight.
    const callsBeforeTyping = calls.length;
    await act(async () => {
      fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'RUN0' } });
    });
    await waitFor(() => expect(calls.length).toBeGreaterThan(callsBeforeTyping));
    await waitFor(() => expect(renderedIds()).toHaveLength(50));
    const listBefore = renderedIds();
    const callsBefore = calls.length;

    const card = document.querySelector('[data-run-id="RUN003"]')!;
    await act(async () => {
      fireEvent.click(within(card as HTMLElement).getByRole('button', { name: /^Focus run/ }));
    });

    await waitFor(() => expect(renderedIds()).toEqual(['RUN003']));
    expect(screen.getByTestId('url').textContent).toBe(
      `/record/${ID}?${RECORD_RUN_PARAM}=RUN003`,
    );
    expect(countText()).toBe('Viewing one run · 120 runs in this record');
    // Focused means EDITABLE: the run's own fields are on screen and writable.
    expect(screen.getByLabelText('Temperature (K)')).toBeEnabled();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Back to all runs' }));
    });
    await waitFor(() => expect(renderedIds()).toEqual(listBefore));
    // The search was NOT mutated by focusing, and no re-read was needed.
    expect((screen.getByLabelText('Search runs') as HTMLInputElement).value).toBe('RUN0');
    expect(calls.length).toBe(callsBefore);
    expect(screen.getByTestId('url').textContent).toBe(`/record/${ID}`);
  });

  it('survives a remount: a deep link lands straight on the run', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q), {
      [`GET ${BASE}/runs/RUN003`]: { body: { run: mkRun(3) } },
    });
    renderAt(ROUTES.recordRun(ID, 'RUN003'));
    await waitForList();

    await waitFor(() => expect(renderedIds()).toEqual(['RUN003']));
    expect(screen.getByRole('button', { name: 'Back to all runs' })).toBeInTheDocument();
  });

  it('reads a focused run directly when it is not on the loaded page', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    let direct = 0;
    stubBackend((q) => serveRuns(all, q), {
      [`GET ${BASE}/runs/RUN110`]: () => {
        direct += 1;
        return { body: { run: mkRun(110) } };
      },
    });
    // RUN110 is on page three. A list-only resolver would answer "not found".
    renderAt(ROUTES.recordRun(ID, 'RUN110'));
    await waitForList();

    await waitFor(() => expect(renderedIds()).toEqual(['RUN110']));
    expect(direct).toBe(1);
    expect(within(document.querySelector('[data-run-id="RUN110"]')!).getByText('Run 110'))
      .toBeInTheDocument();
  });

  it('degrades honestly when the run id does not exist — no blank screen, no false 404 of the record', async () => {
    const all = Array.from({ length: 20 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q), {
      [`GET ${BASE}/runs/RUNGHOST`]: { status: 404, body: { error: 'run_not_found' } },
    });
    renderAt(ROUTES.recordRun(ID, 'RUNGHOST'));
    await waitForList();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('RUNGHOST');
    expect(alert.textContent).toContain('Everything else on this record is unaffected');
    expect(within(alert).getByRole('button', { name: 'Back to all runs' })).toBeInTheDocument();
    expect(renderedIds()).toHaveLength(0);

    // The record screen around it is intact — this is a missing RUN, not a
    // missing record.
    expect(screen.getByRole('heading', { name: 'Runs' })).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(within(alert).getByRole('button', { name: 'Back to all runs' }));
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(20));
  });

  it('never announces "Viewing one run" for a run that is not there — 404 or malformed', async () => {
    /*
     * TWO SURFACES, ONE SCREEN, CONTRADICTING EACH OTHER. The count line branched
     * on whether a run id was in the URL, so a deep link to an id the record does
     * not hold rendered the alert "No run with the id … is in this record" while
     * the `aria-live` region simultaneously announced "Viewing one run · 20 runs in
     * this record". The false half is the half a screen reader speaks, and the test
     * that covers this alert thoroughly stopped without ever looking at the count.
     *
     * BOTH REFUSALS ARE EXERCISED, because they arrive as different statuses and
     * the copy branches on 404: a run id that does not exist (404) and one the
     * server will not accept at all (400). Neither is a run being viewed.
     */
    const all = Array.from({ length: 20 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q), {
      [`GET ${BASE}/runs/RUNGHOST`]: { status: 404, body: { error: 'run_not_found' } },
    });
    renderAt(ROUTES.recordRun(ID, 'RUNGHOST'));
    await waitForList();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('RUNGHOST');
    // Asserted directly: the render that puts the alert on screen is the render
    // that settles the count, so a `waitFor` here would turn the old behaviour
    // into a timeout instead of naming the sentence it wrongly announced.
    expect(countText()).toBe('No run with that id · 20 runs in this record');
    expect(countText()).not.toContain('Viewing one run');
    // The record's own total is still stated — a missing RUN says nothing about
    // how many runs the record has.
    expect(countText()).toContain('20 runs in this record');
  });

  it('says the same thing when the server refuses the id outright, not only when it is absent', async () => {
    const all = Array.from({ length: 20 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q), {
      [`GET ${BASE}/runs/not-a-run-id`]: { status: 400, body: { error: 'malformed_run_id' } },
    });
    renderAt(ROUTES.recordRun(ID, 'not-a-run-id'));
    await waitForList();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('not-a-run-id');
    // The non-404 branch names what the server said, and the count still refuses
    // to claim a run is being viewed.
    expect(alert.textContent).toMatch(/The server said:/);
    expect(countText()).toBe('No run with that id · 20 runs in this record');
  });

  it('is offered on a collapsed card, so no run is reachable only by expanding it', async () => {
    const all = Array.from({ length: 3 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q));
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(3));

    for (const id of renderedIds()) {
      const card = document.querySelector(`[data-run-id="${id}"]`) as HTMLElement;
      const header = within(card).getByRole('button', { name: /^Run \d/ });
      expect(header).toHaveAttribute('aria-expanded', 'false');
      const focusButton = within(card).getByRole('button', { name: /^Focus run/ });
      expect(focusButton.tagName).toBe('BUTTON');
      /*
       * A SIBLING OF THE HEADER, NOT A CHILD OF IT — asserted because a mutation
       * run nested it inside and the whole suite stayed green (91 of 91). jsdom
       * renders a button inside a button happily and React only logs a
       * `validateDOMNesting` warning, which nothing here was reading.
       *
       * The a11y e2e sweep cannot cover this either, and the reason is structural
       * rather than a thoroughness problem: its record surface has no runs, so a
       * Focus control never renders there at all. That makes this the only layer
       * where the invariant can be pinned.
       *
       * It matters because the HTML parser does not nest interactive content: a
       * real browser would close the outer button before the inner one, which puts
       * the Focus control OUTSIDE the accordion in the accessibility tree while it
       * still looks nested on screen — and the collapsed-card guarantee this very
       * test asserts would quietly stop meaning what it says.
       */
      expect(header.contains(focusButton)).toBe(false);
      expect(focusButton.closest('button')).toBe(focusButton);
      // The accessible name names WHICH run, so fifty of these are fifty
      // distinguishable controls rather than fifty called "Focus".
      expect(focusButton.getAttribute('aria-label')).toContain(
        card.querySelector('.run-card-name')?.textContent,
      );
    }
  });
});

// ---------------------------------------------------------------------------
// 6 — Add Run against an active filter
// ---------------------------------------------------------------------------

describe('Add Run while filtering', () => {
  it('clears the criteria, says so, and shows the run it created', async () => {
    const all = Array.from({ length: 8 }, (_, i) => mkRun(i + 1));
    const created = mkRun(9);
    const calls = stubBackend((q) => serveRuns(all, q), {
      [`POST ${BASE}/runs`]: () => {
        all.push(created);
        return { status: 201, body: { run: created, experiment_version: '1.1' } };
      },
    });
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(8));

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'RUN001' } });
    });
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001']));
    const before = calls.length;

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Add Run/ }));
    });

    // The run exists and is visible; the filter that would have hidden it is gone.
    await waitFor(() => expect(renderedIds()).toContain('RUN009'));
    expect((screen.getByLabelText('Search runs') as HTMLInputElement).value).toBe('');
    expect(calls[calls.length - 1].query.q).toBeNull();
    expect(calls.length).toBeGreaterThan(before);
    // And the clearing is SAID, not merely done.
    expect(
      screen.getByText(/The search and filters were cleared so the new run is not hidden/),
    ).toBeInTheDocument();
  });

  it('does not hijack a later search with a create whose own reload was superseded', async () => {
    /*
     * THE READER WAS TELEPORTED INTO FOCUS RUN ON A RUN THEY WERE NOT LOOKING FOR,
     * and their query was discarded on the way.
     *
     * The first-page effect returned on a generation mismatch BEFORE clearing the
     * pending create, so a create whose reload was superseded stayed pending and
     * was consumed by whatever landed next. Measured: Add Run on a 120-run record,
     * then type `Run 3` while the post-create reload is still in flight. Result —
     * URL `/record/demo?run=RUN121`, the count reading "Viewing one run · 121 runs
     * in this record", and the search box gone from the screen.
     *
     * The create-to-focus behaviour it must not cost: a new run is LAST, so on a
     * record this size it is not on the first page and focusing it is the only way
     * the reader sees the run they just asked for. That is covered by the test
     * above; what is asserted here is that a SUPERSEDED create cannot do it to a
     * read that had nothing to do with the create.
     */
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    const created = mkRun(121);
    let releaseReload: (() => void) | null = null;
    let unfilteredReads = 0;
    stubBackend(
      (q) => {
        const body = serveRuns(all, q);
        // Hold the SECOND unfiltered first-page read: the one Add Run triggers.
        if ((q.q ?? '') === '' && q.offset === 0) {
          unfilteredReads += 1;
          if (unfilteredReads === 2) {
            return new Promise((resolve) => {
              releaseReload = () => resolve(body);
            });
          }
        }
        return body;
      },
      {
        [`POST ${BASE}/runs`]: () => {
          all.push(created);
          return { status: 201, body: { run: created, experiment_version: '1.1' } };
        },
      },
    );

    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Add Run/ }));
    });
    await waitFor(() => expect(releaseReload).not.toBeNull());

    // The reader moves on while that reload is still in flight.
    await act(async () => {
      fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'Run 3' } });
    });
    // `Run 3` matches Run 3 and Run 30..Run 39 — eleven of a hundred and twenty-one.
    await waitFor(() => expect(renderedIds()).toHaveLength(11));

    // NOW the superseded reload lands.
    await act(async () => {
      releaseReload!();
      await Promise.resolve();
    });
    await flush();

    // The reader is still where they put themselves.
    expect(screen.getByTestId('url').textContent).toBe(`/record/${ID}`);
    expect((screen.getByLabelText('Search runs') as HTMLInputElement).value).toBe('Run 3');
    expect(renderedIds()).toHaveLength(11);
    expect(renderedIds()).not.toContain('RUN121');
    expect(screen.queryByRole('button', { name: 'Back to all runs' })).toBeNull();
    expect(countText()).toBe('Showing 11 of 11 matching · 121 runs in this record');
  });

  it('preserves the 412 stale-version refusal and its Reload This Section remedy', async () => {
    const all = Array.from({ length: 3 }, (_, i) => mkRun(i + 1));
    stubBackend((q) => serveRuns(all, q), {
      [`POST ${BASE}/runs`]: { status: 412, body: { error: 'stale_write' } },
    });
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(3));

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Add Run/ }));
    });

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('The experiment has changed since this list was loaded');
    expect(alert.textContent).toContain('this can be your own edit elsewhere on this screen');
    expect(within(alert).getByRole('button', { name: 'Reload This Section' })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 7 — an edit in flight survives everything that unmounts a card
// ---------------------------------------------------------------------------

/*
 * WHY THIS IS ASSERTED AGAINST `runAutosaveStore` AND NOT AGAINST THE SCREEN.
 *
 * The store is the thing that makes the claim true: save state lives in a
 * module-level map keyed `<experimentId>/<runId>` and is disposed only when the
 * RECORD screen unmounts. Paging, searching and filtering all unmount cards, so
 * every one of them would have destroyed a held edit under the old
 * card-owns-its-refs design. Asserting through the store proves the edit is still
 * held and still sent; asserting only that the card looks fine after it comes back
 * would pass even if the write had been silently dropped.
 */
describe('an edit in flight', () => {
  async function typeIntoFirstRun() {
    const card = document.querySelector('[data-run-id="RUN001"]') as HTMLElement;
    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: /^Run \d/ }));
    });
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Temperature (K)'), {
        target: { value: '277.15' },
      });
    });
  }

  /*
   * FAKE TIMERS FROM THE MOMENT OF TYPING, and the reason is a false negative
   * rather than convenience. On real timers the 600 ms autosave debounce elapses
   * inside the `waitFor` that watches for the next page, so the edit is SENT
   * before the assertion runs and `pendingCount` is legitimately 0 — a passing
   * save read as a lost edit. Freezing the clock is what makes "still held while
   * the card is gone" observable at all.
   */
  it('is not lost when a filter change unmounts the card, and is still sent', async () => {
    const all = Array.from({ length: 40 }, (_, i) => mkRun(i + 1));
    const patched: unknown[] = [];
    stubBackend((q) => serveRuns(all, q), {
      [`PATCH ${BASE}/runs/RUN001`]: (init) => {
        patched.push(init?.body ? JSON.parse(String(init.body)) : undefined);
        return { body: { run: mkRun(1, { version: 'r1.1' }) } };
      },
    });
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(40));

    vi.useFakeTimers();
    await typeIntoFirstRun();

    // Held, not yet sent — the autosave debounce has not elapsed.
    expect(snapshotFor(ID, 'RUN001').pendingCount).toBe(1);
    expect(patched).toHaveLength(0);

    // Filter the card off the screen. `RUN001` carries no override, so it is gone.
    await act(async () => {
      fireEvent.change(screen.getByLabelText('Overrides'), { target: { value: 'any' } });
    });
    await flush();
    expect(renderedIds()).toHaveLength(0);

    /*
     * THE EDIT LEFT THE MOMENT THE CARD DID, and the clock has not moved — 0 ms
     * of the 600 ms debounce have elapsed. `useRunAutosave`'s teardown calls
     * `flushPending`, so filtering a card off the screen DISPATCHES the held
     * edit rather than dropping it. This is the assertion the slice needs: it
     * fails if the store were ever moved back inside the card, because there
     * would be nothing left to flush and nothing left to report the outcome to.
     */
    expect(patched).toHaveLength(1);
    expect(patched[0]).toMatchObject({ fields: { 'context.temperature_K': 277.15 } });
    expect(snapshotFor(ID, 'RUN001').status).toBe('saved');

    // Nothing is sent twice when the debounce that was already flushed comes due.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    await flush();
    expect(patched).toHaveLength(1);
  });

  it('is not lost across Load More or a search', async () => {
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    const patched: unknown[] = [];
    stubBackend((q) => serveRuns(all, q), {
      [`PATCH ${BASE}/runs/RUN001`]: (init) => {
        patched.push(init?.body ? JSON.parse(String(init.body)) : undefined);
        return { body: { run: mkRun(1, { version: 'r1.1' }) } };
      },
    });
    renderRecord();
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(50));

    vi.useFakeTimers();
    await typeIntoFirstRun();
    expect(snapshotFor(ID, 'RUN001').pendingCount).toBe(1);

    await act(async () => {
      fireEvent.click(loadMoreButton()!);
    });
    await flush();
    // LOAD MORE APPENDS, so RUN001's card is still mounted and the edit is still
    // held — the debounce has not run and nothing has been sent.
    expect(renderedIds()).toHaveLength(100);
    expect(snapshotFor(ID, 'RUN001').pendingCount).toBe(1);
    expect(patched).toHaveLength(0);

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'RUN110' } });
      // The SEARCH debounce only — 300 ms, inside the 600 ms autosave window, so
      // nothing here is a timer coincidence: what sends the edit is the unmount.
      await vi.advanceTimersByTimeAsync(RUN_SEARCH_DEBOUNCE_MS + 10);
    });
    await flush();
    expect(renderedIds()).toEqual(['RUN110']);

    // A search that filters the card away DISPATCHES the edit rather than losing it.
    expect(patched).toHaveLength(1);
    expect(patched[0]).toMatchObject({ fields: { 'context.temperature_K': 277.15 } });
    expect(snapshotFor(ID, 'RUN001').status).toBe('saved');
  });
});
