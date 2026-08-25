import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  bundleRoutes,
  completePendingPage,
  experimentDetail,
  stubFetchRoutes,
} from '../test/apiFixtures';

/**
 * THE COMPLETION SCREEN HOLDS A PAGE OF THE RECORD'S QUESTIONS, AND SAYS SO.
 *
 * WHY THIS FILE EXISTS. `GET /pending` served every open blocking question of the
 * whole record and this screen fetched all of them, rendering one `.upcoming-row` per
 * entry and one `.progress-seg` per question. A record's question count is `3 x runs`;
 * measured in-process over HTTP on `c153ec9`, the read was 1,772,692 bytes over 3,000
 * entries at 1,000 runs, and every mutation response carried the same list back.
 *
 * The screen now asks for a WINDOW. That is only safe if three things hold, and each
 * is a test below rather than a comment:
 *
 *  1. EVERY COUNTER STILL SPEAKS FOR THE RECORD. `total`/`remaining` come from the
 *     server's `pending_page.total`, never from the length of the page. Reading them
 *     off the page would understate the outstanding work by exactly what was withheld
 *     — a screen answering less than it claims, which is the failure the whole bounded
 *     contract exists to prevent.
 *  2. THE WITHHELD QUESTIONS ARE NAMED AND REACHABLE. No blocker may become
 *     undiscoverable.
 *  3. THE "EVERY QUESTION REVIEWED THIS VISIT" PANEL DOES NOT FIRE OVER A PAGE. It was
 *     true only while the list WAS the record; with a page held, "every question" means
 *     "every question I happened to be shown".
 */

const RUN_LABEL = (i: number) => `Run ${i + 1}`;

/** One run-owned series question, shaped as `serialize.pending_to_list` emits it. */
function seriesQuestion(i: number) {
  const runId = `01RUN${String(i).padStart(21, '0')}`;
  return {
    id: 'series',
    blocker_key: `${runId}:series`,
    run_id: runId,
    run_label: RUN_LABEL(i),
    kind: 'series',
    question: `Provide the reduced spectrum for ${RUN_LABEL(i)}.`,
    about: 'reduced_spectrum',
    demo_answer: null,
    inferability: {
      field: 'reduced_spectrum',
      state: 'needs_user_input' as const,
      explanation: 'The values exist only in the reduction product.',
      value: null,
      provenance: null,
      detail: {},
    },
  };
}

/** 120 open questions, of which the server returns 50 at a time. */
const ALL = Array.from({ length: 120 }, (_, i) => seriesQuestion(i));
const PAGE = 50;

/** The `pending_page` for a slice of `ALL` starting at `offset`. */
function pageBlock(offset: number, returned: number) {
  return {
    total: ALL.length,
    returned,
    offset,
    limit: PAGE,
    withheld: Math.max(ALL.length - offset - returned, 0),
    complete: false,
    run_id: null,
    record_total: ALL.length,
  };
}

/** The pending route as the server behaves: complete when unbounded, paged when not. */
function pagedPendingRoute() {
  return (_init?: RequestInit, path?: string) => {
    const query = path?.includes('?') ? path.slice(path.indexOf('?') + 1) : '';
    if (!query) return { body: { pending: ALL } };
    const params = new URLSearchParams(query);
    const offset = Number(params.get('offset') ?? 0);
    const limit = Number(params.get('limit') ?? PAGE);
    const window = ALL.slice(offset, offset + limit);
    return { body: { pending: window, pending_page: pageBlock(offset, window.length) } };
  };
}

function routes(overrides: Record<string, unknown> = {}) {
  return {
    ...bundleRoutes('demo'),
    // Coherent with the paged list: a detail claiming 5 while the list reports 120
    // would let a passing assertion come from the wrong number.
    'GET /api/experiments/demo': {
      body: { ...experimentDetail, id: 'demo', pending_count: ALL.length },
    },
    'GET /api/experiments/demo/pending': pagedPendingRoute(),
    ...overrides,
  };
}

function renderComplete() {
  return render(
    <MemoryRouter
      initialEntries={['/record/demo/complete']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the completion screen bounds what it asks for', () => {
  it('asks for a page rather than the whole list', async () => {
    const calls = stubFetchRoutes(routes());
    const screen = renderComplete();
    await screen.findByText(/Provide the reduced spectrum for Run 1\./);

    // THE BOUNDED KEY, with the limit on it. An unbounded read HERE would be the
    // defect this screen was changed for: 3,000 entries on a 1,000-run record, to
    // answer one question at a time.
    expect(calls).toContain(`GET /api/experiments/demo/pending?limit=${PAGE}`);

    /*
     * A SECOND, UNBOUNDED READ STILL HAPPENS, AND IT IS NOT THIS SCREEN'S. Measured
     * here, the full call list on mount is:
     *
     *   GET /api/health
     *   GET /api/experiments/demo
     *   GET /api/experiments/demo/pending?limit=50      <- this screen
     *   GET /api/experiments/demo/pending               <- useRecordSession
     *   GET /api/experiments/demo/evidence-classification
     *
     * `useRecordSession` is the SHARED record-session owner mounted on all four record
     * surfaces, and it reads the complete list to build the assistant's AgentContext.
     * Bounding it is a separate decision with a separate blast radius — the context's
     * `pending` is what routes a staged proposal to the run that owns its question —
     * so it was deliberately left alone rather than changed as a side effect here.
     *
     * It is NOT asserted, deliberately: pinning the presence of an unbounded call
     * would turn fixing it into a test failure. The measurement is recorded so the
     * next reader knows the screen is not yet end-to-end bounded, and why.
     */
  });

  /*
   * THIS ONE PASSES ON THE PARENT COMMIT TOO, and saying so is the point of the note.
   * The old screen fetched the WHOLE list, so `pending.length` was 120 and the counter
   * was right by accident. What it pins is that the counter's VALUE did not move for a
   * complete list — a control, not the guard. The guard is the last test in this file,
   * where the server returns a window and `pending.length` is 51: that one reports 120
   * only if `pending_page.total` is being read, and it fails without this change.
   */
  it('counts the RECORD, not the page it is holding', async () => {
    stubFetchRoutes(routes());
    const screen = renderComplete();
    await screen.findByText(/Provide the reduced spectrum for Run 1\./);

    // 120, not 50. The heading, the counter and the status bar all state the record's
    // real outstanding work; before `pending_page.total` was adopted these would have
    // read 50, and a scientist would have been told they were 70 questions further on
    // than they were.
    expect(screen.getByText('Answer 120 Questions to Finish This Record')).toBeInTheDocument();
    expect(screen.getByText('0 / 120')).toBeInTheDocument();
    expect(screen.getByText('120 of 120 fields still to confirm')).toBeInTheDocument();
  });

  it('names the questions it is withholding, and does not claim the visit is finished', async () => {
    stubFetchRoutes(routes());
    const screen = renderComplete();
    await screen.findByText(/Provide the reduced spectrum for Run 1\./);

    expect(screen.getByText('70 more open questions are not shown here.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show more questions' })).toBeInTheDocument();
    // The all-reviewed panel must not appear over a page — see (3) in the file header.
    expect(screen.queryByText(/Every question reviewed this visit/)).toBeNull();
  });

  it('Show more fetches the NEXT page and appends it', async () => {
    const calls = stubFetchRoutes(routes());
    const screen = renderComplete();
    await screen.findByText(/Provide the reduced spectrum for Run 1\./);
    // Run 51 is the first entry of the second page, so its absence is what makes the
    // append assertion below non-trivial.
    expect(screen.queryByText(/Provide the reduced spectrum for Run 51\./)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Show more questions' }));
    await screen.findByText(/Provide the reduced spectrum for Run 51\./);

    expect(calls).toContain(`GET /api/experiments/demo/pending?offset=${PAGE}&limit=${PAGE}`);
    // APPENDED, not replaced: the first page is still on screen, and the disclosure
    // has counted down rather than disappearing.
    expect(screen.getByText(/Provide the reduced spectrum for Run 2\./)).toBeInTheDocument();
    expect(screen.getByText('20 more open questions are not shown here.')).toBeInTheDocument();
  });

  it('caps the progress bar without misstating the total', async () => {
    stubFetchRoutes(routes());
    const screen = renderComplete();
    await screen.findByText(/Provide the reduced spectrum for Run 1\./);

    const bar = screen.container.querySelector('.progress');
    // One `<span>` per question was 3,000 nodes on a 1,000-run record.
    expect(bar?.querySelectorAll('.progress-seg').length).toBe(60);
    // And the accessible statement is the record's real one, uncapped.
    expect(bar?.getAttribute('aria-label')).toBe('0 of 120 answered');
  });

  it('adopts the total from a MUTATION response, not the length of its window', async () => {
    const answered = ALL.slice(1);
    stubFetchRoutes(
      routes({
        'GET /api/experiments/demo/runs/01RUN000000000000000000000': {
          body: { run: { id: '01RUN000000000000000000000', version: 'run.1', fields: {}, inherited: {} } },
        },
        'POST /api/experiments/demo/runs/01RUN000000000000000000000/answers': {
          body: {
            // The server's WINDOW — 50 of the 119 questions that remain.
            pending: answered.slice(0, PAGE),
            pending_page: {
              ...completePendingPage(answered.slice(0, PAGE)),
              total: answered.length,
              withheld: answered.length - PAGE,
              complete: false,
            },
            status: 'needs_attention',
            rev: 4,
            updated_utc: '2099-04-02T09:16:00Z',
            version: '1.1',
            workflow: experimentDetail.workflow,
            invalidation: {
              changed: true,
              rev: 4,
              changed_fields: ['series'],
              reopened_steps: [],
              artifact: { state: 'none' as const, reason: null },
              reason: 'Updated 1 field(s); no downstream steps reopened.',
            },
          },
        },
      }),
    );
    const screen = renderComplete();
    await screen.findByText(/Provide the reduced spectrum for Run 1\./);

    fireEvent.change(screen.getByLabelText(/series json/i), {
      target: { value: '[{"series_id":"s"}]' },
    });
    fireEvent.click(screen.getByText('Confirm'));

    // 1 answered + 119 still open = 120. Reading `resp.pending.length` instead would
    // have reported 51 and told the scientist 69 questions had vanished.
    expect(await screen.findByText('1 / 120')).toBeInTheDocument();
    expect(screen.getByText('119 of 120 fields still to confirm')).toBeInTheDocument();
  });

  it('pages from the CONTIGUOUS head after an anchored mutation window, skipping nothing', async () => {
    /*
     * THE GAP THIS PINS, which is invisible from the client's side of the wire.
     *
     * A mutation returns an ANCHORED window: the first 50 of the record's list PLUS the
     * written unit's own still-open questions, which on a large record come from far
     * down it. So the held list can be 52 entries covering offsets 0-49 plus two
     * distant ones — and "load more from `pending.length`" would have asked for
     * `offset=52` and walked straight past offsets 50 and 51. Two questions, silently
     * unreachable from this screen, on the exact path a scientist takes.
     *
     * The fix reads the contiguous head off the page block (`limit`, not `returned`).
     * This asserts the REQUEST, because that is where the arithmetic lives, and then
     * asserts that the skipped entry actually arrives.
     */
    const remaining = ALL.slice(1);
    const anchored = [...remaining.slice(0, PAGE), ...remaining.slice(110)]; // 50 + 10
    const calls = stubFetchRoutes(
      routes({
        'GET /api/experiments/demo/runs/01RUN000000000000000000000': {
          body: { run: { id: '01RUN000000000000000000000', version: 'run.1', fields: {}, inherited: {} } },
        },
        'POST /api/experiments/demo/runs/01RUN000000000000000000000/answers': {
          body: {
            pending: anchored,
            pending_page: {
              total: remaining.length,
              returned: anchored.length, // 60 — MORE than the limit, by the anchor
              offset: 0,
              limit: PAGE, // the contiguous head is 50, not 60
              withheld: remaining.length - anchored.length,
              complete: false,
              run_id: null,
              record_total: remaining.length,
            },
            status: 'needs_attention',
            rev: 4,
            updated_utc: '2099-04-02T09:16:00Z',
            version: '1.1',
            workflow: experimentDetail.workflow,
            invalidation: {
              changed: true,
              rev: 4,
              changed_fields: ['series'],
              reopened_steps: [],
              artifact: { state: 'none' as const, reason: null },
              reason: 'Updated 1 field(s); no downstream steps reopened.',
            },
          },
        },
      }),
    );
    const screen = renderComplete();
    await screen.findByText(/Provide the reduced spectrum for Run 1\./);
    fireEvent.change(screen.getByLabelText(/series json/i), {
      target: { value: '[{"series_id":"s"}]' },
    });
    fireEvent.click(screen.getByText('Confirm'));
    await screen.findByText('1 / 120');

    fireEvent.click(screen.getByRole('button', { name: 'Show more questions' }));
    // `offset=50`, the contiguous head — NOT `offset=60`, the length of what is held.
    await screen.findByText(/Provide the reduced spectrum for Run 52\./);
    expect(calls).toContain(`GET /api/experiments/demo/pending?offset=${PAGE}&limit=${PAGE}`);
    expect(calls).not.toContain(
      `GET /api/experiments/demo/pending?offset=${anchored.length}&limit=${PAGE}`,
    );
  });
});
