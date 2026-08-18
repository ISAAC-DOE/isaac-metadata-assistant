/*
 * REMOVING A RUN — the confirmation, the four recoveries, and the two refusals.
 *
 * WHAT THIS FILE IS FOR. The Run browser could add a run and never take one back
 * out, so a run created by a mis-click was permanent. The request itself is one
 * POST; everything below it is about the state a run leaves behind when its card
 * disappears — the `?run=` deep link, the `?compare=` selection, the module-level
 * autosave map keyed by run id, and the keyboard caret sitting on a control inside
 * the card that is about to unmount. Each of those, left alone, points at a run the
 * server has forgotten, and each is a defect the reader would blame on the record
 * rather than on the button they just pressed.
 *
 * THE NEGATIVE CONTROLS ARE NAMED, because this repository has shipped green tests
 * that protected nothing. Where an assertion would pass against a component that
 * did nothing at all, the test also asserts what was SENT (or that nothing was) —
 * a removal that renders correctly because the stub removed the run is
 * indistinguishable on screen from one that asked the server to.
 *
 * THE STUB IS A REAL LITTLE BACKEND for the three run operations this touches, so a
 * bug in the component produces a wrong LIST rather than a stub miss, and an
 * unrouted call still throws.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { RunsSection } from '../components/RunsSection';
import {
  __entryCount,
  __resetRunAutosaveStore,
  seedVersion,
} from '../lib/runAutosaveStore';
import { RECORD_COMPARE_PARAM, RECORD_RUN_PARAM } from '../lib/routes';
import { runFixture, stubFetchRoutes, VERSION_FIELDS } from '../test/apiFixtures';

configure({ asyncUtilTimeout: 5_000 });

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

/** One request this backend served, as the component actually sent it. */
interface Call {
  method: string;
  path: string;
  ifMatch: string | null;
  body: unknown;
}

interface Refusal {
  status: number;
  body: Record<string, unknown>;
}

/**
 * A small in-memory Run backend: list (filtered then paged), read one, remove one.
 *
 * `state.runs` is MUTATED by a successful removal, so what the component re-reads
 * afterwards is the consequence of the request it made rather than a second fixture
 * the test handed it. `state.refuse` makes the next removal fail with a chosen
 * status, which is the only way the refusal paths are reachable.
 */
function stubBackend(initial: Run[]) {
  const state = {
    runs: [...initial],
    version: VERSION_FIELDS.version,
    refuse: null as Refusal | null,
    calls: [] as Call[],
  };

  stubFetchRoutes({});
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const raw =
        typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const path = raw.replace(/^https?:\/\/[^/]+/, '');
      const method = init?.method ?? 'GET';
      const headers = (init?.headers ?? {}) as Record<string, string>;
      state.calls.push({
        method,
        path,
        ifMatch: headers['If-Match'] ?? null,
        body: init?.body === undefined ? undefined : JSON.parse(String(init.body)),
      });
      const json = (status: number, body: unknown) =>
        ({
          ok: status >= 200 && status < 300,
          status,
          headers: { get: () => null },
          json: async () => body,
          text: async () => JSON.stringify(body),
        }) as unknown as Response;

      const bare = path.split('?')[0];

      if (method === 'GET' && bare === `${BASE}/runs`) {
        const params = new URLSearchParams(path.split('?')[1] ?? '');
        const q = (params.get('q') ?? '').trim().toLowerCase();
        const matched =
          q === ''
            ? state.runs
            : state.runs.filter(
                (r) =>
                  String(r.label).toLowerCase().includes(q) ||
                  String(r.id).toLowerCase().includes(q),
              );
        const limit = params.get('limit') === null ? matched.length : Number(params.get('limit'));
        const offset = Number(params.get('offset') ?? '0');
        const page = matched.slice(offset, offset + limit);
        return json(200, {
          runs: page,
          experiment_version: state.version,
          total: state.runs.length,
          matched: matched.length,
          returned: page.length,
          offset,
        });
      }

      const removal = /^\/api\/experiments\/[^/]+\/runs\/([^/]+)\/remove$/.exec(bare);
      if (method === 'POST' && removal) {
        if (state.refuse !== null) {
          const refusal = state.refuse;
          state.refuse = null;
          return json(refusal.status, refusal.body);
        }
        const runId = removal[1];
        const run = state.runs.find((r) => r.id === runId);
        if (run === undefined) {
          return json(404, { error: 'run_not_found', experiment_id: ID, id: runId });
        }
        state.runs = state.runs.filter((r) => r.id !== runId);
        state.version = `${state.version}+`;
        return json(200, {
          removed_run_id: run.id,
          removed_run_label: run.label,
          removed_run_ordinal: run.ordinal,
          asset_references_dropped: [],
          remaining_run_count: state.runs.length,
          ordinals_compacted: false,
          experiment_version: state.version,
        });
      }

      const one = /^\/api\/experiments\/[^/]+\/runs\/([^/]+)$/.exec(bare);
      if (method === 'GET' && one) {
        const run = state.runs.find((r) => r.id === one[1]);
        return run === undefined
          ? json(404, { error: 'run_not_found', experiment_id: ID, id: one[1] })
          : json(200, { run });
      }

      throw new TypeError(`fetch stub: no route for ${method} ${path}`);
    }),
  );
  return state;
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="url">{`${location.pathname}${location.search}`}</div>;
}

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

function renderedIds(): string[] {
  return [...document.querySelectorAll('[data-run-id]')].map(
    (el) => el.getAttribute('data-run-id') ?? '',
  );
}

const cardFor = (runId: string) =>
  document.querySelector(`[data-run-id="${runId}"]`) as HTMLElement;

async function waitForList() {
  await waitFor(() => expect(document.querySelector('.runs-count')).not.toBeNull());
}

/** Open one run's card and return its Remove Run trigger. */
async function openRemove(runId: string, label: string): Promise<HTMLElement> {
  const card = cardFor(runId);
  fireEvent.click(within(card).getByRole('button', { expanded: false }));
  return within(cardFor(runId)).findByRole('button', {
    name: `Remove run ${label} from this record`,
  });
}

const removalCalls = (state: ReturnType<typeof stubBackend>) =>
  state.calls.filter((c) => c.method === 'POST' && c.path.endsWith('/remove'));

beforeEach(() => {
  vi.useRealTimers();
  __resetRunAutosaveStore();
});

afterEach(() => {
  vi.unstubAllGlobals();
  __resetRunAutosaveStore();
});

// ---------------------------------------------------------------------------
// 1 — nothing destructive happens without a confirmation
// ---------------------------------------------------------------------------

describe('the confirmation', () => {
  it('THE NEGATIVE CONTROL: opening the panel sends NOTHING', async () => {
    const state = stubBackend([mkRun(1), mkRun(2)]);
    renderRecord();
    await waitForList();

    const trigger = await openRemove('RUN001', 'Run 1');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(trigger);

    // The panel is open, its copy is on screen, and the run is still in the list.
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(
      within(cardFor('RUN001')).getByText(/takes this run out of the record/),
    ).toBeTruthy();
    expect(removalCalls(state)).toHaveLength(0);
    expect(renderedIds()).toEqual(['RUN001', 'RUN002']);
  });

  it('names what goes and what does not, and never claims a file was deleted', async () => {
    stubBackend([mkRun(1)]);
    renderRecord();
    await waitForList();
    fireEvent.click(await openRemove('RUN001', 'Run 1'));

    const panel = cardFor('RUN001').querySelector('.run-card-remove') as HTMLElement;
    const copy = panel.textContent ?? '';
    // What it must say.
    expect(copy).toContain('The record’s own values are unchanged');
    expect(copy).toContain('no other run is changed');
    expect(copy).toContain('files themselves are not touched');
    expect(copy).toContain('keep their numbers');
    // THE ASSET LIBRARY SURVIVES, AND THE CONFIRMATION SAYS SO. Independent
    // review found the panel listing "the files it cites" among what goes, while
    // only the POST-HOC note mentioned that the record still lists them — so the
    // one surface where understatement matters, the panel a reader reads BEFORE
    // a destructive act, let them conclude the library entries go too.
    expect(copy).toContain('still names them');
    // AND NO IMPLIED REMEDY. It read "cannot be undone from this screen", which
    // implies one exists elsewhere. Nothing in this application restores a
    // removed run.
    expect(copy).toContain('cannot be undone');
    expect(copy).not.toMatch(/undone from this screen/i);
    // What it must NOT say. A removal deletes no file and touches no published
    // record; copy that implied either would be false, and false in the one
    // direction that makes a scientist hesitate to use a safe control.
    expect(copy).not.toMatch(/delete[sd]? the file/i);
    expect(copy).not.toMatch(/exported record/i);
    expect(copy).not.toMatch(/submission/i);
  });

  it('Cancel closes the panel, sends nothing, and returns the caret to the trigger', async () => {
    const state = stubBackend([mkRun(1)]);
    renderRecord();
    await waitForList();
    const trigger = await openRemove('RUN001', 'Run 1');
    fireEvent.click(trigger);

    fireEvent.click(within(cardFor('RUN001')).getByRole('button', { name: 'Cancel' }));

    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(removalCalls(state)).toHaveLength(0);
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});

// ---------------------------------------------------------------------------
// 2 — the request, and the one token that is correct
// ---------------------------------------------------------------------------

describe('the request', () => {
  it("carries the RECORD's version, not the run's, and confirms explicitly", async () => {
    const state = stubBackend([mkRun(1), mkRun(2)]);
    renderRecord();
    await waitForList();
    fireEvent.click(await openRemove('RUN001', 'Run 1'));
    fireEvent.click(
      within(cardFor('RUN001')).getByRole('button', { name: 'Remove This Run' }),
    );

    await waitFor(() => expect(removalCalls(state)).toHaveLength(1));
    const call = removalCalls(state)[0];
    expect(call.path).toBe(`${BASE}/runs/RUN001/remove`);
    // THE TRAP THIS PINS: a run lives inside the record's document, so removing one
    // rewrites the RECORD. Sending `r1.0` — the run's own token — would be a 412 the
    // reader would be told to fix by refreshing something that was never stale.
    expect(call.ifMatch).toBe(`"${VERSION_FIELDS.version}"`);
    expect(call.ifMatch).not.toBe('"r1.0"');
    expect(call.body).toEqual({ confirmed_by_user: true });
  });

  it('removes the card, re-reads the list, and announces the SERVER’s count', async () => {
    stubBackend([mkRun(1), mkRun(2), mkRun(3)]);
    renderRecord();
    await waitForList();
    fireEvent.click(await openRemove('RUN002', 'Run 2'));
    fireEvent.click(
      within(cardFor('RUN002')).getByRole('button', { name: 'Remove This Run' }),
    );

    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN003']));
    // The note is a live region and states the count the server reported.
    const note = await screen.findByText(/Removed Run 2\./);
    expect(note.getAttribute('role')).toBe('status');
    expect(note.textContent).toContain('2 runs remain in this record');
    // The numbering clause is read off the server's `ordinals_compacted`, not
    // restated by this build — see where the note is assembled.
    expect(note.textContent).toContain('The others keep their numbers.');
    // And the section really re-read rather than splicing its own array: the count
    // line is the server's `total`, which only a fresh read can move.
    expect(document.querySelector('.runs-count')?.textContent).toContain('of 2');
  });

  it('adopts the new record version, so a SECOND removal is not a stale write', async () => {
    const state = stubBackend([mkRun(1), mkRun(2), mkRun(3)]);
    renderRecord();
    await waitForList();

    fireEvent.click(await openRemove('RUN001', 'Run 1'));
    fireEvent.click(
      within(cardFor('RUN001')).getByRole('button', { name: 'Remove This Run' }),
    );
    await waitFor(() => expect(renderedIds()).toEqual(['RUN002', 'RUN003']));

    fireEvent.click(await openRemove('RUN002', 'Run 2'));
    fireEvent.click(
      within(cardFor('RUN002')).getByRole('button', { name: 'Remove This Run' }),
    );
    await waitFor(() => expect(removalCalls(state)).toHaveLength(2));

    const [first, second] = removalCalls(state);
    // The stub appends a character per removal, so the SECOND request must carry
    // the version the FIRST response returned — not the one the section started
    // with, and not the one the record has now.
    expect(first.ifMatch).toBe(`"${VERSION_FIELDS.version}"`);
    expect(second.ifMatch).toBe(`"${VERSION_FIELDS.version}+"`);
    expect(second.ifMatch).not.toBe(first.ifMatch);
  });
});

// ---------------------------------------------------------------------------
// 3 — the four recoveries
// ---------------------------------------------------------------------------

describe('Focus Run recovery', () => {
  it('leaves the focused view rather than stranding the reader on a dead id', async () => {
    stubBackend([mkRun(1), mkRun(2)]);
    renderAt(`/record/${ID}?${RECORD_RUN_PARAM}=RUN001`);
    await waitForList();
    // The focused card opens expanded, so its Remove control is already reachable.
    const trigger = await within(cardFor('RUN001')).findByRole('button', {
      name: 'Remove run Run 1 from this record',
    });
    fireEvent.click(trigger);
    fireEvent.click(
      within(cardFor('RUN001')).getByRole('button', { name: 'Remove This Run' }),
    );

    // THE DEFECT THIS PREVENTS: `?run=RUN001` surviving the removal renders "No run
    // with the id RUN001 is in this record" — a true sentence the app produced about
    // its own act, over a screen with no way out but Back.
    await waitFor(() =>
      expect(screen.getByTestId('url').textContent).not.toContain(RECORD_RUN_PARAM),
    );
    expect(screen.queryByText(/is in this record\./)).toBeNull();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN002']));
    // The caret is on the section's own furniture, not lost to the document body.
    await waitFor(() => expect(document.activeElement).not.toBe(document.body));
  });

  it('takes the run out of the COMPARISON selection too', async () => {
    stubBackend([mkRun(1), mkRun(2), mkRun(3)]);
    renderAt(
      `/record/${ID}?${RECORD_COMPARE_PARAM}=RUN001&${RECORD_COMPARE_PARAM}=RUN003`,
    );
    await waitForList();
    fireEvent.click(await openRemove('RUN001', 'Run 1'));
    fireEvent.click(
      within(cardFor('RUN001')).getByRole('button', { name: 'Remove This Run' }),
    );

    await waitFor(() => expect(renderedIds()).toEqual(['RUN002', 'RUN003']));
    // WAITED FOR, not read once. The list re-render and the URL rewrite are
    // separate effects, so a synchronous read after the list settles is a race:
    // it passed this file alone and with one sibling, and failed in the full
    // suite, which is the signature of an ordering-sensitive assertion rather
    // than of a product defect.
    await waitFor(() => {
      const url = screen.getByTestId('url').textContent ?? '';
      expect(url).not.toContain('RUN001');
      // The other selection is untouched — a removal takes out one run, not the
      // reader's whole comparison.
      expect(url).toContain('RUN003');
    });
  });
});

describe('list and search recovery', () => {
  it('KEEPS the search rather than clearing it, and re-reads with it still on the wire', async () => {
    const state = stubBackend([
      mkRun(1, { label: 'alpha' }),
      mkRun(2, { label: 'alpha two' }),
      mkRun(3, { label: 'beta' }),
    ]);
    renderRecord();
    await waitForList();

    fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'alpha' } });
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN002']));

    fireEvent.click(await openRemove('RUN001', 'alpha'));
    fireEvent.click(
      within(cardFor('RUN001')).getByRole('button', { name: 'Remove This Run' }),
    );
    await waitFor(() => expect(renderedIds()).toEqual(['RUN002']));

    // THE CONTRAST WITH `Add Run`, which CLEARS the criteria because a new run
    // usually does not match them. A removal cannot produce that problem, so
    // discarding the reader's search would be a change nobody asked for.
    expect((screen.getByLabelText('Search runs') as HTMLInputElement).value).toBe('alpha');
    const last = state.calls.filter((c) => c.method === 'GET' && c.path.includes('/runs?')).pop();
    expect(last?.path).toContain('q=alpha');
    // Both counts moved: one matching run of two in the record.
    expect(document.querySelector('.runs-count')?.textContent).toBe(
      'Showing 1 of 1 matching · 2 runs in this record',
    );
  });

  it('a search that now matches nothing says so WITHOUT claiming the record is empty', async () => {
    stubBackend([mkRun(1, { label: 'alpha' }), mkRun(2, { label: 'beta' })]);
    renderRecord();
    await waitForList();
    fireEvent.change(screen.getByLabelText('Search runs'), { target: { value: 'alpha' } });
    await waitFor(() => expect(renderedIds()).toEqual(['RUN001']));

    fireEvent.click(await openRemove('RUN001', 'alpha'));
    fireEvent.click(
      within(cardFor('RUN001')).getByRole('button', { name: 'Remove This Run' }),
    );

    await waitFor(() => expect(renderedIds()).toEqual([]));
    expect(screen.getByText(/No run matches this search or these filters/)).toBeTruthy();
    expect(screen.getByText(/This record has 1 run\./)).toBeTruthy();
    expect(screen.queryByText(/No runs yet\./)).toBeNull();
    // And the way out is offered rather than left to be guessed. There are TWO —
    // the controls row keeps its own while filtering, and the empty state adds one
    // where the reader is looking — so this asserts the pair rather than picking
    // one and pretending the other is a duplicate.
    expect(screen.getAllByRole('button', { name: 'Clear search and filters' })).toHaveLength(2);
  });

  it('moves the caret to the run below, so a keyboard reader is not dropped to the top', async () => {
    stubBackend([mkRun(1), mkRun(2), mkRun(3)]);
    renderRecord();
    await waitForList();
    fireEvent.click(await openRemove('RUN002', 'Run 2'));
    fireEvent.click(
      within(cardFor('RUN002')).getByRole('button', { name: 'Remove This Run' }),
    );

    await waitFor(() => expect(renderedIds()).toEqual(['RUN001', 'RUN003']));
    await waitFor(() =>
      expect(document.activeElement).toBe(
        within(cardFor('RUN003')).getByRole('button', { expanded: false }),
      ),
    );
  });

  it('stops holding autosave state for a run that no longer exists', async () => {
    stubBackend([mkRun(1), mkRun(2)]);
    renderRecord();
    await waitForList();
    // A card that has been edited has an entry in the module map; the map outlives
    // the card by design, so nothing else would ever drop this one.
    seedVersion(ID, 'RUN001', 'r1.0');
    const before = __entryCount();
    expect(before).toBeGreaterThan(0);

    fireEvent.click(await openRemove('RUN001', 'Run 1'));
    fireEvent.click(
      within(cardFor('RUN001')).getByRole('button', { name: 'Remove This Run' }),
    );
    await waitFor(() => expect(renderedIds()).toEqual(['RUN002']));

    await waitFor(() => expect(__entryCount()).toBe(before - 1));
  });
});

// ---------------------------------------------------------------------------
// 4 — the refusals
// ---------------------------------------------------------------------------

describe('a refused removal', () => {
  it('a 412 keeps the run, explains it, and offers the one remedy that works', async () => {
    const state = stubBackend([mkRun(1), mkRun(2)]);
    state.refuse = {
      status: 412,
      body: { error: 'stale_write', experiment_id: ID, current_version: '2.0' },
    };
    renderRecord();
    await waitForList();
    fireEvent.click(await openRemove('RUN001', 'Run 1'));
    fireEvent.click(
      within(cardFor('RUN001')).getByRole('button', { name: 'Remove This Run' }),
    );

    const alert = await within(cardFor('RUN001')).findByRole('alert');
    expect(alert.textContent).toContain('the run was not removed');
    expect(alert.textContent).toContain('can be your own edit elsewhere on this screen');
    // The run is still there, and the panel stayed open over it.
    expect(renderedIds()).toEqual(['RUN001', 'RUN002']);
    expect(cardFor('RUN001').querySelector('.run-card-remove')).not.toBeNull();
    // Reloading the section is the remedy, and it is a control rather than an
    // instruction to reload the page and lose everything else on screen.
    const reload = within(alert).getByRole('button', { name: 'Reload This Section' });
    fireEvent.click(reload);
    await waitFor(() =>
      expect(state.calls.filter((c) => c.method === 'GET' && c.path.includes('/runs')).length)
        .toBeGreaterThan(1),
    );
  });

  it('the refusal is ASSOCIATED with the button that caused it, not merely nearby', async () => {
    const state = stubBackend([mkRun(1)]);
    state.refuse = { status: 500, body: { error: 'boom' } };
    renderRecord();
    await waitForList();
    fireEvent.click(await openRemove('RUN001', 'Run 1'));
    const confirm = within(cardFor('RUN001')).getByRole('button', {
      name: 'Remove This Run',
    });
    fireEvent.click(confirm);

    const alert = await within(cardFor('RUN001')).findByRole('alert');
    expect(alert.id).toBeTruthy();
    expect(confirm.getAttribute('aria-describedby')).toBe(alert.id);
    // NEVER COLOUR ALONE: the failure is words, and the glyph beside them is
    // decorative, so a reader who cannot see the tint still gets the whole message.
    expect((alert.textContent ?? '').trim().length).toBeGreaterThan(20);
    expect(alert.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
    // Nothing was removed.
    expect(renderedIds()).toEqual(['RUN001']);
  });

  it('a 409 is rendered in THIS CLIENT’s words, and the run stays', async () => {
    const state = stubBackend([mkRun(1)]);
    state.refuse = {
      status: 409,
      body: {
        error: 'run_exported',
        message:
          'This run has been exported to an official ISAAC record, so it cannot be removed.',
      },
    };
    renderRecord();
    await waitForList();
    fireEvent.click(await openRemove('RUN001', 'Run 1'));
    fireEvent.click(
      within(cardFor('RUN001')).getByRole('button', { name: 'Remove This Run' }),
    );

    const alert = await within(cardFor('RUN001')).findByRole('alert');
    // THE COPY IS THIS CLIENT'S, and the test says so rather than pretending it is
    // the server's. `mutationError` parses a body only for 400/412/422, so a 409's
    // `message` is the bare "Request failed (409)." — which names nothing a reader
    // can act on. This route has exactly one 409 (`run_exported`).
    expect(alert.textContent).toContain('official ISAAC record for this run already exists');
    expect(alert.textContent).not.toContain('Request failed');

    // IT MUST SAY *WHETHER*, NOT *WHEN* — AND THIS ASSERTION IS THE INVERSE OF THE
    // ONE IT REPLACES. This test used to REQUIRE the phrase "since this list was
    // loaded". An independent review showed that claim is false on the disk-only
    // refusal arm: a record and/or sidecar can sit in `records/` under the run's own
    // id with no persisted `record_id`, so the run view reports `record_id: null`,
    // the control is offered, the click 409s — and the export happened BEFORE the
    // read, not after. The test was pinning a false sentence as required copy, on a
    // destructive-action surface, which is the worst place for it.
    //
    // So the phrase is now FORBIDDEN rather than required. Asserting its absence is
    // deliberate: deleting the old assertion would have left nothing preventing the
    // sentence from coming back, and it came from a plausible-sounding argument that
    // someone could easily re-derive.
    expect(alert.textContent).not.toContain('since this list was loaded');
    expect(alert.textContent).not.toMatch(/\bsince\b/);

    // A 409 is not a staleness problem, so it must NOT offer the reload remedy — and
    // on the disk-only arm a reload would return an identical list, so the copy says
    // so outright rather than leaving the reader to discover it.
    expect(within(alert).queryByRole('button', { name: 'Reload This Section' })).toBeNull();
    expect(alert.textContent).toContain('Reloading will not change this');
    expect(renderedIds()).toEqual(['RUN001']);
  });
});

// ---------------------------------------------------------------------------
// 5 — an exported run is never offered a control that can only be refused
// ---------------------------------------------------------------------------

describe('an exported run', () => {
  it('is offered NO Remove control, and is told why instead', async () => {
    const state = stubBackend([
      mkRun(1, { record_id: '01EXPORTEDRECORD000000001' }),
      mkRun(2),
    ]);
    renderRecord();
    await waitForList();

    const card = cardFor('RUN001');
    fireEvent.click(within(card).getByRole('button', { expanded: false }));
    await waitFor(() =>
      expect(within(cardFor('RUN001')).getByText(/cannot be removed/)).toBeTruthy(),
    );
    expect(
      within(cardFor('RUN001')).queryByRole('button', {
        name: /Remove run Run 1/,
      }),
    ).toBeNull();
    // The reason names the record, so the reader can go and look at it.
    expect(cardFor('RUN001').textContent).toContain('01EXPORTEDRECORD000000001');
    expect(cardFor('RUN001').textContent).toContain('never rewritten');
    // Nothing was sent, and the SIBLING that has not been exported still offers it:
    // this is a per-run disclosure, not the control going missing.
    expect(removalCalls(state)).toHaveLength(0);
    const other = cardFor('RUN002');
    fireEvent.click(within(other).getByRole('button', { expanded: false }));
    expect(
      await within(cardFor('RUN002')).findByRole('button', {
        name: 'Remove run Run 2 from this record',
      }),
    ).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// 6 — accessibility of the control itself
// ---------------------------------------------------------------------------

describe('the control', () => {
  it('names the run it acts on, and still contains its own visible words', async () => {
    stubBackend([mkRun(1), mkRun(2)]);
    renderRecord();
    await waitForList();
    const trigger = await openRemove('RUN002', 'Run 2');

    // Fifty cards each offering "Remove Run" is fifty identically named controls in
    // a screen reader's list, so the accessible name carries the run...
    expect(trigger.getAttribute('aria-label')).toBe('Remove run Run 2 from this record');
    // ...and it CONTAINS the visible text verbatim, so WCAG 2.5.3 holds and speech
    // input still reaches it by saying the word on the control. This is the
    // assertion that forced the visible label to be ONE word: "Remove Run" is not
    // a substring of "Remove run Run 2 from this record", because the case differs
    // and 2.5.3 is about the literal string a speech user says.
    expect(trigger.textContent).toBe('Remove');
    expect(trigger.getAttribute('aria-label')).toContain(trigger.textContent);
  });

  it('is a real disclosure: `aria-controls` points at the panel it opens', async () => {
    stubBackend([mkRun(1)]);
    renderRecord();
    await waitForList();
    const trigger = await openRemove('RUN001', 'Run 1');
    expect(trigger.getAttribute('aria-controls')).toBeNull();

    fireEvent.click(trigger);
    const controls = trigger.getAttribute('aria-controls');
    expect(controls).toBeTruthy();
    expect(document.getElementById(controls as string)).toBe(
      cardFor('RUN001').querySelector('.run-card-remove'),
    );
  });

  it('is disabled while its own request is in flight, so one click is one removal', async () => {
    const state = stubBackend([mkRun(1), mkRun(2)]);
    let release = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const inner = globalThis.fetch as typeof fetch;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const raw =
          typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if ((init?.method ?? 'GET') === 'POST' && raw.endsWith('/remove')) await held;
        return inner(input, init);
      }),
    );

    renderRecord();
    await waitForList();
    fireEvent.click(await openRemove('RUN001', 'Run 1'));
    const confirm = within(cardFor('RUN001')).getByRole('button', {
      name: 'Remove This Run',
    });
    fireEvent.click(confirm);

    const busy = await within(cardFor('RUN001')).findByRole('button', { name: 'Removing…' });
    expect(busy).toBeDisabled();
    fireEvent.click(busy);
    release();
    await waitFor(() => expect(renderedIds()).toEqual(['RUN002']));
    expect(removalCalls(state)).toHaveLength(1);
  });
});
