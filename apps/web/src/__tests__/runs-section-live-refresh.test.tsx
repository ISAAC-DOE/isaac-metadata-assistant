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
import { act, configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { RunsSection, RUNS_PAGE_SIZE } from '../components/RunsSection';
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

  const respond = () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: async () => ({
      runs: box.runs,
      experiment_version: box.version,
      total: box.runs.length,
      matched: box.runs.length,
      returned: box.runs.length,
      offset: 0,
    }),
  });

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
      if (!hold) return respond() as unknown as Response;
      return new Promise<Response>((resolve) => {
        queue.push(() => resolve(respond() as unknown as Response));
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
  it('a created run becomes visible after a signal', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1), mkRun(2)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));
    expect(backend.calls).toHaveLength(1);

    // The colleague's create advanced the record to rev 1, and a third run now
    // exists on the server the section has not yet read.
    backend.setRuns([mkRun(1), mkRun(2), mkRun(3)], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN003'], runRev: 1 })} />);

    await waitFor(() => expect(backend.calls).toHaveLength(2));
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
  it('search text and expanded state survive the SIGNAL-driven silent reload', async () => {
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

    // The accordion header specifically — `.run-card-focus` and `.run-card-compare`
    // also carry "Run 1" in their accessible name, so a role/name query is ambiguous
    // here in a way it is not for the rest of this suite. Captured only now,
    // AFTER the search reload's own (non-silent) remount has already happened.
    const card = document.querySelector('[data-run-id="RUN001"]');
    if (card === null) throw new Error('RUN001 card not rendered');
    const toggle = card.querySelector('.run-card-header') as HTMLElement;
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');

    backend.setRuns([mkRun(1), mkRun(2)], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN001'], runRev: 1 })} />);
    // Request #3 — unambiguously the SIGNAL's, because #2 already happened and
    // settled above.
    await waitFor(() => expect(backend.calls).toHaveLength(3));
    await flush();

    expect(search.value).toBe('Run 1');
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
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
function stubPagedRunsBackend(all: Run[], version: string) {
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
      const limit = q.limit ?? all.length;
      const page = all.slice(q.offset, q.offset + limit);
      return {
        ok: true,
        status: 200,
        headers: { get: () => null },
        json: async () => ({
          runs: page,
          experiment_version: version,
          total: all.length,
          matched: all.length,
          returned: page.length,
          offset: q.offset,
        }),
      } as unknown as Response;
    }),
  );
  return { calls };
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
