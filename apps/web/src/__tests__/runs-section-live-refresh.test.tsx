/*
 * RUNS SECTION — THE CHANGE-FEED `activity` PROP.
 *
 * WHAT THIS FILE IS FOR. `RunsSection` owns its own fetch (see its file header)
 * and is deliberately NOT one of the pollers on the record screen. This slice
 * gives it an optional `activity` prop — a `RecordChangeSummary` a parent screen
 * already holds — and asks it to do exactly one thing when that summary reports
 * a run or the record moved: perform ONE SILENT first-page reload, the same kind
 * `Add Run` and `Remove Run` already trigger through `reloadNonce` + `silentRef`.
 *
 * EVERY ASSERTION HERE IS ABOUT REQUEST COUNTS AND THE SIGNAL GATE, not about the
 * paging or search mechanics `run-browser.test.tsx` already owns — this file
 * mounts the section directly, the same way, for the same measured cost reason
 * (see that file's header), and reuses its harness shape rather than duplicating
 * a second one that drifts from it.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { RunsSection } from '../components/RunsSection';
import { __resetRunAutosaveStore } from '../lib/runAutosaveStore';
import type { RecordChangeSummary } from '../lib/recordChanges';
import { runFixture, stubFetchRoutes } from '../test/apiFixtures';

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

/** A `RecordChangeSummary`, defaulted to "no news" so a test only names the
 *  fields it is about. */
function summary(over: Partial<RecordChangeSummary> = {}): RecordChangeSummary {
  return {
    recordMoved: false,
    runIds: [],
    proposalIds: [],
    proposalStates: [],
    otherKinds: [],
    highestRev: -1,
    proposalRev: -1,
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

function Harness({ activity }: { activity: RecordChangeSummary | null }) {
  return (
    <MemoryRouter
      initialEntries={[`/record/${ID}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <RunsSection experimentId={ID} activity={activity} />
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

describe('a run that arrived through the change feed', () => {
  it('a created run becomes visible after a signal', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1), mkRun(2)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));
    expect(backend.calls).toHaveLength(1);

    // The colleague's create advanced the record to rev 1, and a third run now
    // exists on the server the section has not yet read.
    backend.setRuns([mkRun(1), mkRun(2), mkRun(3)], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN003'], highestRev: 1 })} />);

    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002', 'RUN003']));
  });

  it('an updated run changes in place', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await screen.findByText('Run 1');

    backend.setRuns([mkRun(1, { label: 'Run 1 — recalibrated' })], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN001'], highestRev: 1 })} />);

    await screen.findByText('Run 1 — recalibrated');
    // Still one card, not two — the list is REPLACED from the response, never
    // appended, so a re-delivered run cannot render twice.
    expect(renderedIds()).toEqual(['RUN001']);
  });

  it('a removed run disappears on a recordMoved signal — the feed cannot report a deletion directly', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1), mkRun(2)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));

    // A run removed elsewhere moves the record's OWN entry; runIds stays empty by
    // construction (see the file header on `RunsSection` and `RecordChangeSummary`).
    backend.setRuns([mkRun(1)], '1.1');
    rerender(<Harness activity={summary({ recordMoved: true, runIds: [], highestRev: 1 })} />);

    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001']));
  });
});

describe('signals that must NOT cause a request', () => {
  it('a proposal-only signal makes no request', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    rerender(
      <Harness
        activity={summary({ proposalIds: ['P1'], proposalRev: 4, highestRev: 4 })}
      />,
    );
    await flush();
    expect(backend.calls).toHaveLength(1);
  });

  it('a signal at or below the loaded rev makes no request — this is the section’s own Add/Remove Run', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.5' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    rerender(<Harness activity={summary({ runIds: ['RUN001'], highestRev: 5 })} />);
    await flush();
    expect(backend.calls).toHaveLength(1);

    rerender(<Harness activity={summary({ runIds: ['RUN001'], highestRev: 3 })} />);
    await flush();
    expect(backend.calls).toHaveLength(1);
  });

  it('the identical signal twice makes exactly one request', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    expect(backend.calls).toHaveLength(1);

    const sig = summary({ runIds: ['RUN002'], highestRev: 1 });
    rerender(<Harness activity={sig} />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));

    // The SAME object, and then an equal-but-distinct object — the key is what is
    // deduped, not the reference.
    rerender(<Harness activity={sig} />);
    await flush();
    expect(backend.calls).toHaveLength(2);

    rerender(<Harness activity={summary({ runIds: ['RUN002'], highestRev: 1 })} />);
    await flush();
    expect(backend.calls).toHaveLength(2);
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
    rerender(<Harness activity={summary({ runIds: ['RUN002'], highestRev: 1 })} />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await waitFor(() => expect(backend.outstanding()).toBe(1));

    // Two MORE signals arrive while #2 is still outstanding.
    rerender(<Harness activity={summary({ runIds: ['RUN002', 'RUN003'], highestRev: 2 })} />);
    await flush();
    rerender(
      <Harness activity={summary({ runIds: ['RUN002', 'RUN003', 'RUN004'], highestRev: 3 })} />,
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
    const sig = summary({ runIds: ['RUN002'], highestRev: 1 });

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
    rerender(<Harness activity={summary({ runIds: ['RUN002'], highestRev: 1 })} />);
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
  it('search text and expanded state survive the silent reload', async () => {
    const backend = stubRunsBackend({ runs: [mkRun(1), mkRun(2)], version: '1.0' });
    const { rerender } = render(<Harness activity={null} />);
    await waitForList();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));

    const search = screen.getByLabelText('Search runs') as HTMLInputElement;
    fireEvent.change(search, { target: { value: 'Run 1' } });
    expect(search.value).toBe('Run 1');

    // The accordion header specifically — `.run-card-focus` and `.run-card-compare`
    // also carry "Run 1" in their accessible name, so a role/name query is ambiguous
    // here in a way it is not for the rest of this suite.
    const card = document.querySelector('[data-run-id="RUN001"]');
    if (card === null) throw new Error('RUN001 card not rendered');
    const toggle = card.querySelector('.run-card-header') as HTMLElement;
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');

    backend.setRuns([mkRun(1), mkRun(2)], '1.1');
    rerender(<Harness activity={summary({ runIds: ['RUN001'], highestRev: 1 })} />);
    await waitFor(() => expect(backend.calls).toHaveLength(2));
    await flush();

    expect(search.value).toBe('Run 1');
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
  });
});
