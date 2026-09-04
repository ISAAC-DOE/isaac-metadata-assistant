/*
 * RUNS SECTION — TWO PATHS TO ONE BOUNDED SILENT RELOAD.
 *
 * WHAT THIS FILE IS FOR. `RunsSection` owns its own fetch (see its file header)
 * and is deliberately NOT one of the pollers on the record screen. It takes two
 * independent props: `activity` (a RUN-scoped change-feed summary — the FAST
 * path) and `recordVersion` (the record bundle's own version token — the
 * COMPLETENESS path). Both exist to trigger exactly one thing: a silent
 * first-page reload, the same kind `Add Run` and `Remove Run` already trigger
 * through `reloadNonce` + `silentRef`.
 *
 * WHY TWO PATHS, MEASURED RATHER THAN ASSUMED. An earlier version of this slice
 * used `activity` alone, keyed and gated on its `highestRev` field. An
 * independent review of the PRODUCER side (PR #224) found three defects in that
 * design, against the producer's actual contract:
 *
 *   (a) `highestRev` is a max over ALL surviving entries INCLUDING proposals, so
 *       a stale proposal position inflates it — drifting the dedupe key on every
 *       poll even when nothing about the runs changed (redundant reloads), and
 *       the OLD swallow branch RECORDED that inflated key, so a run change that
 *       arrived bundled with it could be lost permanently.
 *   (b) this section's own loaded rev is parsed from the bare REV half of
 *       `<generation>.<rev>`, so a signal after a generation change (`1.7` ->
 *       `2.0`) reads as "already seen" and is swallowed.
 *   (c) the change feed cannot report a run REMOVAL at all — only the record's
 *       own entry moves, never a `run` entry — so `activity` is empty for a
 *       removal, always.
 *
 * The fix is structural, not a smarter parse of `activity`: `activity` is now
 * keyed and gated on `runRev` (a RUN-scoped floor, never `highestRev`) and no
 * longer records the key when swallowing — closing (a). `recordVersion` closes
 * (b) and (c) independently, by plain STRING inequality against what this
 * section has itself loaded, which needs no rev arithmetic and is therefore
 * correct across a generation boundary and for a removal without this section
 * ever having to understand either. See `RunsSection`'s own prop comments for
 * the full argument; this file pins the observable behaviour.
 *
 * EVERY ASSERTION HERE IS ABOUT REQUEST COUNTS AND THE SIGNAL GATE, not about
 * the paging or search mechanics `run-browser.test.tsx` already owns — this
 * file mounts the section directly, the same way, for the same measured cost
 * reason (see that file's header), and reuses its harness shape rather than
 * duplicating a second one that drifts from it.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { RunsSection, RUNS_PAGE_SIZE, RUN_SEARCH_DEBOUNCE_MS } from '../components/RunsSection';
import type { RecordChangeSummary } from '../lib/recordChanges';
import { RUN_LIST_LIMIT_MAX } from '../lib/runPaging';
import { __resetRunAutosaveStore } from '../lib/runAutosaveStore';
import { runFixture, stubFetchRoutes } from '../test/apiFixtures';

// A debounce-driven wait (the search box's own 300ms) plus this file's
// paginated backend needs more headroom than the 1,000ms default under a
// loaded CI host — the same reasoning `run-browser.test.tsx` gives for the
// same setting.
configure({ asyncUtilTimeout: 5_000 });

/*
 * THE HARNESS DEADLINE, RAISED FOR THE SAME REASON `run-browser.test.tsx`
 * RAISES IT (see that file's own comment at the same call, which this one
 * does not repeat). The I2 over-cap test drives FOUR sequential Load More
 * round trips before the signal is even delivered and measured close to the
 * default 5,000ms budget on a quiet host; under contention it would time out
 * for a reason that has nothing to do with the assertion.
 */
vi.setConfig({ testTimeout: 30_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

type Run = ReturnType<typeof runFixture>;

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

/** A `RecordChangeSummary` as the runs fast path receives it, defaulted to "no
 *  news" so a test only names the
 *  fields it is about. `runRev` defaults to `-1` — never above any real loaded
 *  rev — so a test that forgets to set it fails closed (no request) rather
 *  than accidentally triggering one. */
function summary(over: Partial<RecordChangeSummary> = {}): RecordChangeSummary {
  return {
    recordMoved: false,
    runIds: [],
    proposalIds: [],
    proposalStates: [],
    otherKinds: [],
    highestRev: -1,
    proposalRev: -1,
    runRev: -1,
    ...over,
  };
}

/**
 * The runs-listing backend, held in a mutable box so a test can change what the
 * NEXT response contains — the shape a colleague's edit would produce — without
 * re-registering the stub.
 *
 * `hold` lets a test keep exactly one response open: while `true`, a request is
 * queued rather than answered, and `release()` answers the OLDEST queued one.
 * That is what makes the coalescing test possible — it has to observe "one
 * request is outstanding" as a fact, not assume it from timing.
 */
function stubRunsBackend(initial: { runs: Run[]; version: string }) {
  let box = initial;
  let hold = false;
  const queue: Array<() => void> = [];
  const calls: string[] = [];

  /*
   * HONOURS `limit`/`offset` LIKE `routes.py` DOES — review finding C-3,
   * fixed independently and the same way on `main` (PR #229) while this
   * branch was in flight; the two implementations are kept equivalent
   * below, `main`'s slightly terser parsing.
   *
   * This fixture used to answer every request with the WHOLE `box`
   * regardless of what was asked for, which let a test assert a shape the
   * real backend can never produce: a run created AFTER the reader's own
   * bounded reload (`limit = received`, `triggerBoundedSilentReload`)
   * rendering anyway, because the fixture handed back runs the request
   * never requested. `routes.py` slices `[offset:offset + limit]` and
   * reports the record's real `total`, and the difference is the one this
   * section's whole bounded-reload design turns on: a signal-driven
   * re-read asks for `limit = received`, so a run ADDED elsewhere while
   * the reader holds a full page produces a page of N out of a total of
   * N+1 — against the old body that state was unreachable, and a re-read
   * that silently grew the page it had promised to bound would have
   * looked identical to a correct one.
   *
   * `stubPagedRunsBackend` below already got this right for the I2/I3
   * tests it was built for; this merges the same slicing into THIS stub
   * too, so the property holds for every test in the file that uses it,
   * not only the ones that happened to reach for the paged one — and
   * `hold`/`release`/`outstanding`, which several tests below still need,
   * are unaffected. Every existing test in this file loads fewer runs than
   * `RUNS_PAGE_SIZE`, so slicing is the identity for them and no count
   * moves.
   */
  const respond = (path: string) => {
    const q = path.includes('?') ? path.slice(path.indexOf('?') + 1) : '';
    const params = new URLSearchParams(q);
    const offset = Number(params.get('offset') ?? 0);
    const limit = Number(params.get('limit') ?? box.runs.length);
    const page = box.runs.slice(offset, offset + limit);
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({
        runs: page,
        experiment_version: box.version,
        total: box.runs.length,
        matched: box.runs.length,
        returned: page.length,
        offset,
      }),
    };
  };

  stubFetchRoutes({});
  const inner = globalThis.fetch as unknown as (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => Promise<Response>;

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
      calls.push(path);
      if (!hold) return respond(path) as unknown as Response;
      return new Promise<Response>((resolve) => {
        /* The page is computed when the response is RELEASED, not when it was
           queued, which is what the real server does: a held request answers with
           what the record holds at the moment it is answered. */
        queue.push(() => resolve(respond(path) as unknown as Response));
      });
    }),
  );

  return {
    calls,
    setRuns: (runs: Run[], version: string) => {
      box = { runs, version };
    },
    setHold: (value: boolean) => {
      hold = value;
    },
    release: () => {
      const next = queue.shift();
      if (next) next();
    },
    outstanding: () => queue.length,
  };
}

function Harness({
  activity,
  recordVersion,
}: {
  activity: RecordChangeSummary | null;
  recordVersion?: string | null;
}) {
  return (
    <MemoryRouter
      initialEntries={[`/record/${ID}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <RunsSection experimentId={ID} activity={activity} recordVersion={recordVersion ?? null} />
    </MemoryRouter>
  );
}

async function waitForList() {
  await waitFor(() => expect(document.querySelector('.runs-count')).not.toBeNull());
}

function renderedIds(): string[] {
  return [...document.querySelectorAll('[data-run-id]')].map(
    (el) => el.getAttribute('data-run-id') ?? '',
  );
}

/** Let pending microtasks (the fetch stub's promise chain) settle. */
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
// The fast path (`activity`)
// ---------------------------------------------------------------------------

describe('a run that arrived through the change feed (fast path)', () => {
  /*
   * REWRITTEN INDEPENDENTLY, THE SAME WAY, ON BOTH BRANCHES — fix round,
   * review finding C-3 here; `main`'s own PR #229 rewrite carries the fuller
   * account and is kept below rather than this branch's shorter one. Both
   * used to assert that a run CREATED after this section's own bounded
   * reload (`limit = received`) rendered anyway — a shape the real backend
   * can never produce: `received` is 2 here, so the reload's own request
   * asks for exactly 2, and a third run appended after the two already
   * loaded is outside that page by construction. It only ever passed
   * because `stubRunsBackend` ignored `limit` and answered with the whole
   * box regardless of what was asked for — fixed above, in the fixture
   * itself, the same way on both branches.
   */
  it('a colleague CREATING a run is reported by a signal — the total moves and Load More appears, and the bounded re-read does NOT smuggle it onto the page', async () => {
    /*
     * ── THIS TEST REPLACES ONE WHOSE PREMISE WAS FALSE, AND THE FALSE PREMISE IS
     * ── THE USEFUL PART. ───────────────────────────────────────────────────────
     *
     * ~~`a created run becomes visible after a signal`~~ loaded two runs, had a
     * colleague create a third, and asserted that all THREE rendered. It passed for
     * one reason: `stubRunsBackend` returned every run whatever `limit` was asked
     * for. The real route slices `[offset:offset + limit]`, and a signal-driven
     * re-read asks for `limit = received` — `triggerBoundedSilentReload` sets
     * `pendingSignalLimitRef` to exactly what is on screen — so the response can
     * never contain a run the page did not already have room for. **There is no
     * page size at which it could**: the bound IS the received count, so a created
     * run is structurally outside every bounded re-read, at every list length.
     *
     * So the old assertion was reading the fixture, not the product, and the
     * property it named does not exist. What DOES exist is better than nothing and
     * is what a scientist actually needs: the re-read is what tells the section the
     * record's `total` has moved, so the count line stops claiming the record has
     * two runs and Load More becomes reachable. Nothing is silently dropped and
     * nothing is silently added.
     *
     * MUTATION CONTROL, RUN AND REVERTED:
     *   · revert `stubRunsBackend.respond` to the old body (return `box.runs`, report
     *     `total` as its length) -> THIS TEST FAILS: three cards render and the count
     *     reads "Showing 3 of 3 runs", which is the old test passing again and is
     *     exactly the behaviour no server produces.
     */
    const backend = stubRunsBackend({ runs: [mkRun(1), mkRun(2)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));
    expect(backend.calls).toHaveLength(1);
    expect(document.querySelector('.runs-count')?.textContent).toBe('Showing 2 of 2 runs');
    expect(screen.queryByRole('button', { name: /Load more runs/ })).toBeNull();

    // The colleague's create advanced the record to rev 1, and a third run now
    // exists on the server the section has not yet read.
    backend.setRuns([mkRun(1), mkRun(2), mkRun(3)], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN003'], runRev: 1 })} />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));

    // THE BOUNDED REQUEST ASKED FOR EXACTLY WHAT WAS ON SCREEN, never the
    // server's new total: a page of two, out of a record of three — so the
    // two rows already loaded still dedupe to exactly themselves, and the
    // honest "2 of 3" replaces the stale "2 of 2" rather than a fabricated
    // third row appearing.
    expect(new URLSearchParams(backend.calls[1].split('?')[1]).get('limit')).toBe('2');
    await waitFor(() =>
      expect(document.querySelector('.runs-count')?.textContent).toBe('Showing 2 of 3 runs'),
    );
    expect(renderedIds()).toEqual(['RUN001', 'RUN002']);

    // Reachable, not dropped — and one press really does bring it.
    expect(screen.getByRole('button', { name: /Load more runs/ })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: /Load more runs/ }));
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002', 'RUN003']));
  });

  it('an updated run changes in place', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await screen.findByText('Run 1');

    backend.setRuns([mkRun(1, { label: 'Run 1 — recalibrated' })], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN001'], runRev: 1 })} />);

    await screen.findByText('Run 1 — recalibrated');
    // Still one card, not two — the list is REPLACED from the response, never
    // appended, so a re-delivered run cannot render twice.
    expect(renderedIds()).toEqual(['RUN001']);
  });
});

describe('signals that must NOT cause a request (fast path)', () => {
  it('a proposal-only signal makes no request', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    rerender(
      <Harness activity={summary({ proposalIds: ['P1'], proposalRev: 4, highestRev: 4 })} />,
    );
    await flush();
    expect(backend.calls).toHaveLength(1);
  });

  it('a signal at or below the loaded rev makes no request — this is the section’s own Add/Remove Run', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.5' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    rerender(<Harness activity={summary({ runIds: ['RUN001'], runRev: 5 })} />);
    await flush();
    expect(backend.calls).toHaveLength(1);

    rerender(<Harness activity={summary({ runIds: ['RUN001'], runRev: 3 })} />);
    await flush();
    expect(backend.calls).toHaveLength(1);
  });

  it('the identical signal twice makes exactly one request', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    const sig = summary({ runIds: ['RUN002'], runRev: 1 });
    rerender(<Harness activity={sig} />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));

    // The SAME object, and then an equal-but-distinct object — the key is what is
    // deduped, not the reference.
    rerender(<Harness activity={sig} />);
    await flush();
    expect(backend.calls).toHaveLength(2);

    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 1 })} />);
    await flush();
    expect(backend.calls).toHaveLength(2);
  });
});

describe('defect (a) — the dedupe key and the gate use runRev, never highestRev', () => {
  it('a stale, drifting highestRev (proposal noise) does not re-key an otherwise-identical run signal', async () => {
    /*
     * MEASURED AGAINST THE PRODUCER'S ACTUAL CONTRACT: `activity.highestRev` is
     * a max over ALL surviving entries INCLUDING proposals, so it can keep
     * moving on every poll even when the RUN news is exactly the same. If the
     * dedupe key included it, each poll would look like a "new" signal and
     * reload again — this is the redundant-reload half of defect (a).
     */
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 1, highestRev: 10 })} />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));

    // SAME runRev, SAME runIds — but `highestRev` has drifted upward, as an
    // unrelated proposal entry riding in the same batch would make it do.
    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 1, highestRev: 55 })} />);
    await flush();
    expect(backend.calls).toHaveLength(2);
  });

  it('a run signal already covered by the loaded rev makes no request, even when highestRev is far above it', async () => {
    /*
     * THE LOST-UPDATE HALF OF DEFECT (a), IN THE OTHER DIRECTION: a signal
     * whose `runRev` is genuinely already loaded must be swallowed — the gate
     * must not be fooled into treating it as news just because a stale
     * proposal position inflated `highestRev` far past the loaded rev.
     */
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.5' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    rerender(<Harness activity={summary({ runIds: ['RUN003'], runRev: 2, highestRev: 99 })} />);
    await flush();
    expect(backend.calls).toHaveLength(1);
  });
});

describe('coalescing while a reload is in flight', () => {
  it('two signals during an in-flight reload produce exactly one follow-up request', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    backend.setHold(true);
    // Signal 1 starts the (held-open) reload — this is request #2.
    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 1 })} />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await waitFor(() => expect(backend.outstanding()).toBe(1));

    // Two MORE signals arrive while #2 is still outstanding.
    rerender(<Harness activity={summary({ runIds: ['RUN002', 'RUN003'], runRev: 2 })} />);
    await flush();
    rerender(
      <Harness activity={summary({ runIds: ['RUN002', 'RUN003', 'RUN004'], runRev: 3 })} />,
    );
    await flush();
    // Neither started a THIRD request — they were coalesced, not queued.
    expect(backend.calls).toHaveLength(2);

    // Let #2 settle. Exactly one follow-up should now fire — request #3 — never
    // one per coalesced signal.
    backend.setRuns([mkRun(1), mkRun(2)], '1.1');
    backend.release();
    await waitFor(() => expect(backend.calls).toHaveLength(3));
    // No fourth request follows once the follow-up itself settles.
    await flush();
    expect(backend.calls).toHaveLength(3);
  });
});

describe('remount hygiene', () => {
  it('a fresh mount starts with no memory of a previous one', async () => {
    const sig = summary({ runIds: ['RUN002'], runRev: 1 });

    // Mount #1 consumes this exact key — its dedupe ref now holds it.
    const first = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender: rerenderFirst, unmount } = render(<Harness activity={null} />);
    await waitForList();
    first.setRuns([mkRun(1), mkRun(2)], '1.1');
    rerenderFirst(<Harness activity={sig} />);
    await waitFor(() => expect(first.calls).toHaveLength(2));
    unmount();

    // Mount #2 is a BRAND NEW component tree with its own fresh `useRef`s (a real
    // remount, not merely a rerender) and its own backend starting back at rev 0
    // — a true `key` change would look identical from this component's own point
    // of view. If the dedupe ref lived anywhere other than this instance's own
    // memory, the identical `sig` object below would be silently swallowed.
    const second = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(second.calls).toHaveLength(1);

    second.setRuns([mkRun(1), mkRun(2)], '1.1');
    rerender(<Harness activity={sig} />);
    await waitFor(() => expect(second.calls).toHaveLength(2));
  });

  it('unmounting mid-reload updates no state and throws no act warning', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender, unmount } = render(<Harness activity={null} />);
    await waitForList();

    backend.setHold(true);
    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 1 })} />);
    await waitFor(() => expect(backend.outstanding()).toBe(1));

    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    unmount();
    backend.setRuns([mkRun(1), mkRun(2)], '1.1');
    backend.release();
    await flush();

    const actWarning = errorSpy.mock.calls.some((args) =>
      String(args[0]).includes('not wrapped in act'),
    );
    expect(actWarning).toBe(false);
    errorSpy.mockRestore();
  });
});

describe('what a silent reload must not disturb', () => {
  it('search text and focus survive the SIGNAL-driven silent reload, and the editor stays open', async () => {
    /*
     * I4 — THE PREVIOUS VERSION OF THIS TEST WAS VACUOUS, AND AN INDEPENDENT
     * REVIEW CAUGHT IT. Typing into the search box starts its OWN 300ms
     * debounced reload (request #2), entirely independent of the signal. The
     * old assertion — `waitFor(() => calls.toHaveLength(2))` right after
     * delivering the signal — was satisfied by THAT reload alone, on a build
     * where the signal effect did nothing at all: the search text and the
     * `aria-expanded` value it checked were never touched by either reload,
     * so the test passed for a reason that had nothing to do with the code
     * this file exists to pin.
     *
     * The fix is to let the search's own reload settle FIRST, as request #2,
     * BEFORE the signal is delivered — so the signal's own reload is
     * unambiguously request #3, and the toggle/search assertions are made
     * against state that has already survived one non-signal reload.
     */
    const backend = stubRunsBackend({ runs: [mkRun(1), mkRun(2)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));
    expect(backend.calls).toHaveLength(1);

    const search = screen.getByLabelText('Search runs') as HTMLInputElement;
    fireEvent.change(search, { target: { value: 'Run 1' } });
    expect(search.value).toBe('Run 1');

    // Request #2 — the SEARCH's own debounced reload. Waited for and settled
    // BEFORE anything else happens, so it cannot be mistaken for the signal's.
    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));

    /*
     * MASTER-DETAIL: a compact row's own open control carries no
     * `aria-expanded` at all (see `run-browser.test.tsx`'s "is reachable on
     * a collapsed card" test). THE FOCUSED EDITOR NO LONGER HAS ONE EITHER
     * (fix round, review finding m-2: the only open editor on screen must
     * not be able to collapse into nothing), so the persistent state a
     * silent reload must not disturb is down to ONE thing — which run is
     * focused (the URL) — and the property worth proving about the editor
     * itself is that it STAYS OPEN across the reload, not that some toggled
     * state survives it (there is no longer a toggle to survive).
     */
    const compactCard = document.querySelector('[data-run-id="RUN001"]');
    if (compactCard === null) throw new Error('RUN001 row not rendered');
    /*
     * ANCHORED ON THE VERB (fix round, review finding m-8): the compact
     * row's own open control carries an `.sr-only` "Open " prefix ahead of
     * the run's label (I-3), so its accessible name begins `Open Run 1 …`.
     * Role + name, not a raw `.run-card-header` class query — that class
     * also matches the FOCUSED editor's own plain `<h3>` heading
     * (`RunCard.tsx`'s m-2 note), and this click is only ever made while
     * compact.
     */
    fireEvent.click(
      within(compactCard as HTMLElement).getByRole('button', { name: /^Open Run \d/ }),
    );
    await waitFor(() => expect(screen.getByRole('button', { name: 'Back to all runs' })).toBeTruthy());

    const card = document.querySelector('[data-run-id="RUN001"]');
    if (card === null) throw new Error('RUN001 card not rendered once focused');
    // It opens with its field panel already present — the reader just asked
    // for this one run, and it can no longer be collapsed at all.
    expect(card.querySelector('.run-card-body')).not.toBeNull();

    backend.setRuns([mkRun(1), mkRun(2)], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN001'], runRev: 1 })} />);
    // Request #3 — unambiguously the SIGNAL's, because #2 already happened and
    // settled above.
    await waitFor(() => expect(backend.calls).toHaveLength(3));
    await flush();

    // THE EDITOR STAYED OPEN across the reload — the invariant m-2 exists to
    // guarantee, checked here rather than assumed.
    const cardAfter = document.querySelector('[data-run-id="RUN001"]');
    expect(cardAfter?.querySelector('.run-card-body')).not.toBeNull();
    // RUN001 is still the focused run — the reload did not bounce the reader
    // back to the list.
    expect(screen.getByRole('button', { name: 'Back to all runs' })).toBeTruthy();

    /*
     * AND THE SEARCH TEXT — NOW CHECKED BY LEAVING FOCUS, NOT BY READING A
     * STALE DETACHED NODE. The search box is withheld entirely while a run is
     * focused (`RunsSection`'s own controls gate), so `search.value` on the
     * variable captured before focusing would still read "Run 1" even if the
     * criteria state had been reset — a detached DOM node's `.value` property
     * does not change on its own, so that read would be vacuous. Leaving
     * focus and querying the box FRESH is what actually proves the criteria
     * survived, on screen, rather than merely surviving in an object nobody
     * can see.
     */
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Back to all runs' }));
    });
    expect((screen.getByLabelText('Search runs') as HTMLInputElement).value).toBe('Run 1');
  });
});

// ---------------------------------------------------------------------------
// The completeness path (`recordVersion`)
// ---------------------------------------------------------------------------

describe('the completeness path closes what the fast path structurally cannot', () => {
  it('required test 1 — a recordVersion change with no activity performs ONE bounded reload (the removal case)', async () => {
    // The feed cannot report a deletion: only the record's own entry moves.
    // `activity` stays `null` throughout this test — the removal is visible
    // ONLY through `recordVersion`.
    const backend = stubRunsBackend({ runs: [mkRun(1), mkRun(2)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} recordVersion="1.0" />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));
    expect(backend.calls).toHaveLength(1);

    backend.setRuns([mkRun(1)], '1.1');
    rerender(<Harness activity={null} recordVersion="1.1" />);

    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001']));
  });

  it('required test 4 — a generation change (1.7 -> 2.0) reloads via the version path', async () => {
    /*
     * DEFECT (b): the fast path's own rev parse discards the generation, so a
     * `runRev` that is numerically BEHIND a new generation's reset counter
     * would read as "already seen". This test does not even exercise the fast
     * path — it proves the version path recovers the case on its own, by
     * plain string inequality, needing no generation arithmetic at all.
     */
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.7' });
    const { rerender } = render(<Harness activity={null} recordVersion="1.7" />);
    await waitForList();
    await screen.findByText('Run 1');
    expect(backend.calls).toHaveLength(1);

    // A new generation — content changes too, so the assertion is not merely
    // "a request happened" but "the reload actually reflects the new state".
    backend.setRuns([mkRun(1, { label: 'Run 1 — new generation' })], '2.0');
    rerender(<Harness activity={null} recordVersion="2.0" />);

    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await screen.findByText('Run 1 — new generation');
  });

  it('a recordVersion equal to what is already loaded makes no request', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} recordVersion="1.0" />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    // The SAME token delivered again — nothing to reconcile.
    rerender(<Harness activity={null} recordVersion="1.0" />);
    await flush();
    expect(backend.calls).toHaveLength(1);
  });

  it('this section’s OWN version advancing (e.g. Add Run) does not, by itself, look like a new recordVersion delivery', async () => {
    /*
     * `lastRecordVersionRef` exists for exactly this: without it, this
     * section's own `experimentVersion` moving (from ANY reload) would make a
     * STALE, unchanged `recordVersion` prop suddenly look "different" from the
     * new `experimentVersion`, and fire a redundant reload for content that
     * never actually needed reconciling.
     */
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} recordVersion="1.0" />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    // A fast-path signal advances this section's OWN experimentVersion to
    // '1.1' — `recordVersion` (the prop) stays '1.0', UNCHANGED.
    backend.setRuns([mkRun(1), mkRun(2)], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 1 })} recordVersion="1.0" />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await flush();

    // Still 2 — the unchanged `recordVersion` prop did not ALSO fire a
    // completeness-path reload just because this section's own version moved
    // out from under it.
    expect(backend.calls).toHaveLength(2);
  });
});

describe('the two paths dedupe against each other by token equality — no shared state needed', () => {
  it('required test 2 — fast path fires first; recordVersion then arrives already matching → exactly 1 extra request', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} recordVersion="1.0" />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    // The fast path fires — request #2 — and adopts '1.1'.
    backend.setRuns([mkRun(1), mkRun(2)], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 1 })} recordVersion="1.0" />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await flush();

    // The parent bundle catches up: `recordVersion` NOW equals '1.1', which
    // this section already adopted via the fast path. Token equality means the
    // completeness path's own gate is already satisfied — no third request.
    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 1 })} recordVersion="1.1" />);
    await flush();
    expect(backend.calls).toHaveLength(2);
  });

  it('required test 3 — recordVersion fires first; the fast path then delivers a now-covered signal → exactly 1 extra request', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} recordVersion="1.0" />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    // The version path fires first — request #2 — and adopts '1.1'.
    backend.setRuns([mkRun(1), mkRun(2)], '1.1');
    rerender(<Harness activity={null} recordVersion="1.1" />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await flush();

    // The SAME batch's `activity` now arrives, naming the run that just moved
    // — but its `runRev` (1) is already covered by what this section adopted
    // via the version path. The fast path's own `runRev <= loadedRev` gate
    // swallows it; no third request.
    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 1 })} recordVersion="1.1" />);
    await flush();
    expect(backend.calls).toHaveLength(2);
  });
});

describe('required test 5 — a proposal-only signal, and the disclosed cost of the version bump it causes', () => {
  it('a proposal-only activity makes no request BY ITSELF', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} recordVersion="1.0" />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    rerender(
      <Harness
        activity={summary({ proposalIds: ['P1'], proposalRev: 9, highestRev: 9 })}
        recordVersion="1.0"
      />,
    );
    await flush();
    expect(backend.calls).toHaveLength(1);
  });

  it(
    'the SAME proposal act, once it bumps recordVersion, costs exactly ONE bounded read — ' +
      'a disclosed cost, not a defect',
    async () => {
      /*
       * A proposal act advances the record's own `rev` (contract DEC-10)
       * exactly like a run edit does, and nothing in the wire contract lets a
       * reader distinguish "this version bump was a proposal act" from "it was
       * a run edit" without re-reading — the feed's own page order cannot
       * prove which. Guessing wrong in the direction of NOT reading is how a
       * real run change gets missed, so this section pays one bounded list
       * read on every version change it did not itself cause, proposal-only
       * or not. That is the price named in `RunsSection`'s own comment on
       * `recordVersion`, and this test shows it is paid ONCE, not repeatedly,
       * for one such bump.
       */
      const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
      const { rerender } = render(<Harness activity={null} recordVersion="1.0" />);
      await waitForList();
      expect(backend.calls).toHaveLength(1);

      // The proposal-only activity itself: no request.
      const proposalActivity = summary({ proposalIds: ['P1'], proposalRev: 9, highestRev: 9 });
      rerender(<Harness activity={proposalActivity} recordVersion="1.0" />);
      await flush();
      expect(backend.calls).toHaveLength(1);

      // The SAME act bumped the record's version — the parent's bundle
      // catches up and hands down the new token. Content is UNCHANGED (no run
      // was touched), but this section cannot know that without reading.
      rerender(<Harness activity={proposalActivity} recordVersion="1.1" />);
      await waitFor(() => expect(backend.calls).toHaveLength(2));
      await flush();
      // Exactly one — not one per render, not one per poll while the prop
      // stays at '1.1'.
      expect(backend.calls).toHaveLength(2);
    },
  );
});

// ---------------------------------------------------------------------------
// I2 — a signal-driven reload must not truncate what Load More already loaded
// ---------------------------------------------------------------------------

interface PagedRunsQuery {
  limit: number | null;
  offset: number;
}

function parsePagedQuery(url: string): PagedRunsQuery {
  const params = new URLSearchParams(url.split('?')[1] ?? '');
  const limit = params.get('limit');
  return { limit: limit === null ? null : Number(limit), offset: Number(params.get('offset') ?? '0') };
}

/**
 * A REAL, OFFSET-AWARE runs backend — unlike `stubRunsBackend` above, which
 * ignores `limit`/`offset` entirely and always answers with the whole `box`.
 * I2 is specifically about what LIMIT a signal-driven request asks for and
 * whether the response actually reflects it, so a backend that cannot
 * distinguish "asked for 50" from "asked for 100" cannot pin the fix.
 */
/**
 * A REAL, OFFSET-AWARE runs backend that also HONOURS A LIVE UPDATE —
 * `setRuns`, added for the "2 of 2 loaded, a colleague adds a third" case
 * (I3 below). It could not be proven against `stubPagedRunsBackend`'s
 * original, immutable `all` array: that fixture answered every `limit`
 * correctly but could never change what it held after construction, so a
 * test could not represent "the record now has one more run than this
 * screen has loaded" without rebuilding the whole backend (and losing the
 * call log). `box` makes the held set mutable, matching `stubRunsBackend`'s
 * own `setRuns` shape one section up — the two fixtures now differ only in
 * whether they honour `limit`/`offset`, which is exactly the axis I3 needs.
 */
function stubPagedRunsBackend(all: Run[], version: string) {
  let box = { all, version };
  const calls: PagedRunsQuery[] = [];
  stubFetchRoutes({});
  const inner = globalThis.fetch as unknown as (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => Promise<Response>;

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
      const q = parsePagedQuery(path);
      calls.push(q);
      const limit = q.limit ?? box.all.length;
      const page = box.all.slice(q.offset, q.offset + limit);
      return {
        ok: true,
        status: 200,
        headers: { get: () => null },
        json: async () => ({
          runs: page,
          experiment_version: box.version,
          total: box.all.length,
          matched: box.all.length,
          returned: page.length,
          offset: q.offset,
        }),
      } as unknown as Response;
    }),
  );
  return {
    calls,
    setRuns: (next: Run[], nextVersion: string) => {
      box = { all: next, version: nextVersion };
    },
  };
}

async function clickLoadMore() {
  const button = await screen.findByRole('button', { name: 'Load more runs' });
  fireEvent.click(button);
}

describe('I2 — a signal-driven reload re-reads what is on screen, not the plain first page', () => {
  it('a 100-loaded / 120-total list keeps 100 cards after a signal — ONE bounded request, not a truncation to 50', async () => {
    /*
     * MEASURED ON THE PRE-FIX BUILD: 100 loaded cards became 50 after a
     * signal, because the reload always asked for exactly `RUNS_PAGE_SIZE`
     * and replaced the list with that first page. A colleague's unrelated
     * edit — updating a run this reader was not even looking at — silently
     * discarded the half of the list Load More had already fetched. This test
     * pins the fix: the signal-driven request's own `limit` is `received`
     * (100), not `RUNS_PAGE_SIZE` (50), and the response is applied whole.
     */
    const all = Array.from({ length: 120 }, (_, i) => mkRun(i + 1));
    const backend = stubPagedRunsBackend(all, '1.0');
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(RUNS_PAGE_SIZE));
    expect(backend.calls).toHaveLength(1);
    expect(backend.calls[0]).toEqual({ limit: RUNS_PAGE_SIZE, offset: 0 });

    await clickLoadMore();
    await waitFor(() => expect(renderedIds()).toHaveLength(100));
    expect(backend.calls).toHaveLength(2);

    // A colleague updates RUN001 — the signal arrives with 100 runs already on
    // screen.
    rerender(<Harness activity={summary({ runIds: ['RUN001'], runRev: 1 })} />);

    await waitFor(() => expect(backend.calls).toHaveLength(3));
    // THE ASSERTION THIS TEST EXISTS FOR: the signal's own request asked for
    // exactly what was on screen, in one bounded request — never the plain
    // `RUNS_PAGE_SIZE` page.
    expect(backend.calls[2]).toEqual({ limit: 100, offset: 0 });

    await waitFor(() => expect(renderedIds()).toHaveLength(100));
    // Not merely "100 cards" — the SAME 100, still in canonical order, not a
    // truncated-then-reassembled set.
    expect(renderedIds()).toEqual(all.slice(0, 100).map((r) => r.id));
  });
});

describe('I2 — over the cap, this section refuses to guess and asks the reader to Refresh', () => {
  /*
   * A PER-TEST TIMEOUT OVERRIDE (the `60_000` third argument below), because
   * this ONE test does genuinely more sequential work than any other in this
   * file: 5 `listRuns` round trips before the signal is even delivered
   * (initial load, 4 Load Mores), plus the Refresh round trip after. It
   * measured within a few seconds of the file's shared 30,000ms budget even
   * on a quiet host. The override widens THIS test's own room without
   * loosening the budget every other test here is still held to.
   */
  it('shows a note and makes NO request until Refresh, once more than RUN_LIST_LIMIT_MAX runs are loaded', async () => {
    const all = Array.from({ length: 300 }, (_, i) => mkRun(i + 1));
    const backend = stubPagedRunsBackend(all, '1.0');
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toHaveLength(RUNS_PAGE_SIZE));

    // Load More four times: 50 -> 100 -> 150 -> 200 -> 250. 250 exceeds
    // `RUN_LIST_LIMIT_MAX` (200); 200 itself would not.
    for (let i = 0; i < 4; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await clickLoadMore();
    }
    await waitFor(() => expect(renderedIds()).toHaveLength(250));
    expect(250).toBeGreaterThan(RUN_LIST_LIMIT_MAX);
    const callsBeforeSignal = backend.calls.length;

    rerender(<Harness activity={summary({ runIds: ['RUN001'], runRev: 1 })} />);

    // THE NOTE APPEARS…
    await screen.findByText('Runs changed elsewhere. Refresh to see the current list.');
    // …AND NO REQUEST WAS MADE FOR IT. A single bounded re-read of 250 runs
    // would exceed the server's own `RUN_PAGE_MAX`, and paging several
    // requests together behind the reader's back is the same "guess at a
    // limit" this whole path exists to avoid.
    await flush();
    expect(backend.calls.length).toBe(callsBeforeSignal);
    // The 250 cards already on screen are UNTOUCHED — nothing was truncated
    // or blanked to produce the notice.
    expect(renderedIds()).toHaveLength(250);

    // A SECOND signal while the notice stands changes nothing either.
    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 2 })} />);
    await flush();
    expect(backend.calls.length).toBe(callsBeforeSignal);

    // Refresh: a NORMAL (non-silent) reload — the note clears, exactly one
    // request is made, and the section returns to the ordinary first page.
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(backend.calls.length).toBe(callsBeforeSignal + 1));
    expect(backend.calls[backend.calls.length - 1]).toEqual({
      limit: RUNS_PAGE_SIZE,
      offset: 0,
    });
    await waitFor(() => expect(renderedIds()).toHaveLength(RUNS_PAGE_SIZE));
    expect(
      screen.queryByText('Runs changed elsewhere. Refresh to see the current list.'),
    ).toBeNull();
  }, 60_000);
});

// ---------------------------------------------------------------------------
// I3 — live refresh against the PR-C master-detail slice: `received === matched`,
// a proposal-driven run change, no duplicate rows from a redundant signal, no
// request from an unrelated one, and no leaked timer/subscription on unmount.
// Each is proven with a mutation control — see the report for the exact break
// and the failing assertion it produced.
// ---------------------------------------------------------------------------

describe('I3 — a colleague adds a run while every match already loaded (received === matched)', () => {
  it('shows "Showing 2 of 3", offers Load More, and does not duplicate the two already-loaded rows', async () => {
    /*
     * THE CASE THE OTHER SIGNAL TESTS DO NOT COVER. Every existing fast-path
     * test either starts under `RUNS_PAGE_SIZE` (so `received === matched`
     * trivially, with room to spare) or is the I2 over-the-cap case. This is
     * the boundary between them: the reader has loaded EXACTLY what matched
     * (2 of 2, Load More absent), and a colleague adds a THIRD run — so the
     * silent reload's own bounded request (`limit = received`, per
     * `triggerBoundedSilentReload`) asks for 2 while the server now HAS 3.
     * The honest answer is "2 of 3, Load More is back", never a request for
     * a run this section did not ask for and never a duplicated row.
     */
    const backend = stubPagedRunsBackend([mkRun(1), mkRun(2)], '1.0');
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));
    expect(backend.calls).toHaveLength(1);
    expect(backend.calls[0]).toEqual({ limit: RUNS_PAGE_SIZE, offset: 0 });
    // received === matched === total: Load More is honestly absent.
    expect(screen.queryByRole('button', { name: 'Load more runs' })).toBeNull();
    expect(document.querySelector('.runs-count')?.textContent).toBe('Showing 2 of 2 runs');

    backend.setRuns([mkRun(1), mkRun(2), mkRun(3)], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN003'], runRev: 1 })} />);

    await waitFor(() => expect(backend.calls).toHaveLength(2));
    // THE BOUNDED REQUEST ASKED FOR EXACTLY WHAT WAS ON SCREEN — 2, never the
    // server's new total and never the plain first-page size.
    expect(backend.calls[1]).toEqual({ limit: 2, offset: 0 });

    await waitFor(() =>
      expect(document.querySelector('.runs-count')?.textContent).toBe('Showing 2 of 3 runs'),
    );
    // The two already-loaded runs did not duplicate — still exactly one row
    // each, in canonical order — and the third is honestly NOT claimed to be
    // on screen: Load More is back, because a bounded 2-run request cannot
    // also fetch the run it does not yet know exists.
    expect(renderedIds()).toEqual(['RUN001', 'RUN002']);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Load more runs' })).toBeInTheDocument(),
    );

    await clickLoadMore();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002', 'RUN003']));
    expect(screen.queryByRole('button', { name: 'Load more runs' })).toBeNull();
  });
});

describe('I3 — an accepted run-scoped proposal reads the same way a direct edit does', () => {
  it("the target run's row re-reads once the acceptance's own signal arrives", async () => {
    /*
     * THE WIRE CANNOT DISTINGUISH THE TWO, AND THAT IS THE POINT — see this
     * file's own header on `runRev`/`activity`: a run entry in the change
     * feed names a run that moved, never WHY it moved. Accepting an
     * ingestion proposal that targets a run is, from this section's own
     * fetch, indistinguishable from a scientist editing the run directly —
     * both produce a `RecordChangeSummary` naming the run's id at an
     * advanced `runRev`. So the fast path this file already pins for a
     * direct edit is EXACTLY the mechanism a proposal acceptance relies on;
     * this test names that scenario explicitly rather than leaving it
     * implicit in a differently-titled test.
     */
    const backend = stubRunsBackend({
      runs: [mkRun(1, { fields: { 'context.temperature_K': { value: 298, status: 'verified', evidence: [] } } })],
      version: '1.0',
    });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await screen.findByText('Run 1');
    expect(document.querySelector('[data-run-id="RUN001"]')?.textContent).toContain('298 K');

    // The proposal acceptance wrote the run's temperature and advanced the
    // record — the section reads it back through the SAME bounded reload
    // path a direct edit's signal triggers.
    backend.setRuns(
      [mkRun(1, { fields: { 'context.temperature_K': { value: 310, status: 'verified', evidence: [] } } })],
      '1.1',
    );
    rerender(<Harness activity={summary({ runIds: ['RUN001'], runRev: 1 })} />);

    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await waitFor(() =>
      expect(document.querySelector('[data-run-id="RUN001"]')?.textContent).toContain('310 K'),
    );
    // Still one row, not two — the accepted proposal's target re-READS, it
    // does not duplicate.
    expect(renderedIds()).toEqual(['RUN001']);
  });
});

describe('I3 — a duplicate signal does not duplicate rows, and an unrelated one issues no request', () => {
  /*
   * REWRITTEN, NOT DELETED (fix round, review finding C-3). This used to
   * start with ONE run loaded and have a colleague ADD a second, then assert
   * both rendered after the signal — the exact structurally-impossible shape
   * named above: `received` is 1 at the moment of the signal, so the bounded
   * reload's own request asks for exactly 1, and a run created after it is
   * outside that page by construction. It only ever passed because
   * `stubRunsBackend` ignored `limit`; the fixture is fixed above, and this
   * test is now about the property its own title names — dedupe — with the
   * signal an EDIT to an EXISTING run, which is reachable through a bounded
   * reload honestly.
   */
  it('a duplicate signal produces no third request, and exactly one node per run', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1), mkRun(2)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));
    expect(backend.calls).toHaveLength(1);

    // A colleague edits RUN002 IN PLACE — no run count change.
    backend.setRuns([mkRun(1), mkRun(2, { label: 'Run 2 — recalibrated' })], '1.1');
    const sig = summary({ runIds: ['RUN002'], runRev: 1 });
    rerender(<Harness activity={sig} />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await screen.findByText('Run 2 — recalibrated');
    expect(renderedIds()).toEqual(['RUN001', 'RUN002']);

    // The IDENTICAL signal object, delivered again — the dedupe key must
    // swallow it: no third request, and critically, no duplicate row from a
    // list that got re-applied on top of itself.
    rerender(<Harness activity={sig} />);
    await flush();
    expect(backend.calls).toHaveLength(2);
    expect(renderedIds()).toEqual(['RUN001', 'RUN002']);
    // Not merely two ids — exactly ONE DOM node per run. A dedupe defect
    // that re-triggered the reload without a NEW request (impossible here,
    // but the shape a rendering-side duplicate would take) would still be
    // caught by counting nodes rather than trusting the id array's own
    // length.
    expect(document.querySelectorAll('[data-run-id="RUN001"]')).toHaveLength(1);
    expect(document.querySelectorAll('[data-run-id="RUN002"]')).toHaveLength(1);
  });

  it('a signal naming no run news (proposal-only) makes no request at all', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    // `runIds: []` is the producer's own contract for "no RUN news" — see
    // `RunsSection`'s file header. A proposal-only batch, an other-kind-only
    // batch, or simply nothing having changed all take this shape.
    rerender(
      <Harness activity={summary({ proposalIds: ['P1'], proposalRev: 4, highestRev: 4 })} />,
    );
    await flush();
    expect(backend.calls).toHaveLength(1);
  });
});

describe('I3 — timers and subscriptions do not outlive the component', () => {
  it('unmounting while the search debounce is pending clears the timer, not merely fires no request', async () => {
    /*
     * THE SEARCH BOX'S OWN 300ms DEBOUNCE (`RUN_SEARCH_DEBOUNCE_MS`) is a
     * `setTimeout` this section owns. If its cleanup effect ever dropped the
     * `clearTimeout`, a keystroke followed immediately by leaving the record
     * screen would leave a timer callback scheduled against an unmounted
     * component — invisible to every test that lets the debounce elapse
     * before moving on, which is every other search test in this file.
     *
     * ASSERTING "NO REQUEST FOLLOWED" IS NOT ENOUGH, and an earlier version
     * of this test did only that — it passed even with the `clearTimeout`
     * deliberately removed (mutation-tested), because the timer's callback
     * is `setQuery(trimmed)`, and React 18 silently no-ops a state update
     * dispatched against an unmounted fiber: no request follows, no
     * `console.error`, nothing to observe from outside. So a real regression
     * would be invisible to this test. Fake timers close it: `vi.getTimerCount()`
     * reads the scheduler directly, independent of what React does with a
     * timer's callback once it fires — it is sensitive to the mutation the
     * request-count form was not.
     */
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { unmount } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'Run 1' } });
    const withPendingDebounce = vi.getTimerCount();
    expect(withPendingDebounce, 'the debounce must have scheduled a timer').toBeGreaterThan(0);

    unmount();
    expect(
      vi.getTimerCount(),
      'a timer survived unmount — the debounce effect did not clear it',
    ).toBe(withPendingDebounce - 1);

    // And, as a corollary rather than the load-bearing assertion: advancing
    // past the debounce window now fires nothing, because there is no timer
    // left to fire.
    await vi.advanceTimersByTimeAsync(RUN_SEARCH_DEBOUNCE_MS + 50);
    expect(backend.calls).toHaveLength(1);
    vi.useRealTimers();
  });

  it('unmounting while a signal-driven reload is in flight settles with no state update and no act warning', async () => {
    /*
     * THE SAME PROPERTY `coalescing while a reload is in flight` PROVES FOR A
     * MID-FLIGHT UNMOUNT, restated here beside the other cleanup guarantees
     * this describe block collects, and pinned against the signal path
     * specifically (the other unmount test above covers the debounce path).
     */
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender, unmount } = render(<Harness activity={null} />);
    await waitForList();

    backend.setHold(true);
    rerender(<Harness activity={summary({ runIds: ['RUN002'], runRev: 1 })} />);
    await waitFor(() => expect(backend.outstanding()).toBe(1));

    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    unmount();
    backend.setRuns([mkRun(1), mkRun(2)], '1.1');
    backend.release();
    await flush();

    const actWarning = errorSpy.mock.calls.some((args) =>
      String(args[0]).includes('not wrapped in act'),
    );
    expect(actWarning).toBe(false);
    errorSpy.mockRestore();
  });
});
