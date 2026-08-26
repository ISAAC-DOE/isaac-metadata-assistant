import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
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
     * THE SECOND READ IS ALSO BOUNDED NOW, AND IT IS NOT THIS SCREEN'S. Measured here,
     * the full call list on mount is:
     *
     *   GET /api/health
     *   GET /api/experiments/demo
     *   GET /api/experiments/demo/pending?limit=50      <- this screen
     *   GET /api/experiments/demo/pending?limit=50      <- useRecordSession
     *   GET /api/experiments/demo/evidence-classification
     *
     * `useRecordSession` is the SHARED record-session owner mounted on all four record
     * surfaces, and it builds the assistant's AgentContext. The fourth line USED TO READ
     * `GET /api/experiments/demo/pending` — the complete list, 1,772,692 bytes at 1,000
     * runs, fetched again after every accepted answer because that effect keys on
     * `version`. The history is kept in the next test, which is the same test inverted.
     *
     * ~~Bounding it is a separate decision with a separate blast radius — the context's
     * `pending` is what decides whether a staged proposal is ANSWERED or CORRECTED — so
     * it was deliberately left alone.~~ It was the right reason and it has been
     * discharged rather than waived: that decision now belongs to the server, which
     * refuses the wrong route without writing and names the right one
     * (`assistant-answer-routing.test.ts`). Membership in this list is a hint.
     *
     * AND `api.getPending` — the unbounded reader — STILL EXISTS AND IS STILL RIGHT
     * TWICE. `api.getRecordBundle` and `api.getExportReadiness` (`lib/api.ts`) call it
     * for the Review Record and Export Readiness screens, deliberately: a screen
     * reporting what is unresolved would UNDERSTATE it from a page, which is why
     * `getPending` sends no parameters at all. Those two are not a residue and must not
     * be "fixed".
     */
  });

  it('the AgentContext read still repeats after every submission — BOUNDED', async () => {
    /*
     * THIS TEST IS INVERTED, NOT REWRITTEN, AND THE OLD NUMBERS ARE KEPT BECAUSE THEY
     * ARE THE MEASUREMENT.
     *
     * It used to read `it('the unbounded AgentContext read REPEATS after every
     * submission')` and assert **1 unbounded read on mount, 2 after one accepted
     * answer** — pinning the defect with its exact numbers, and saying in its own note:
     * *"WHEN THE AGENTCONTEXT READ IS BOUNDED, INVERT THIS TEST — do not delete it."*
     * That is this repository's established remedy for a test that pins a defect
     * (`CLAUDE.md` §11, session of 2026-08-18). This is that inversion.
     *
     * WHAT WAS FIXED, AND WHAT DELIBERATELY WAS NOT. The repeat was never the defect.
     * `useRecordSession`'s AgentContext effect is keyed on `[id, version, active,
     * refreshNonce]` and must re-derive when the record advances, or the assistant
     * reasons over a revision that no longer exists — so it SHOULD fire again after an
     * accepted answer, and it still does, which is what the counts below assert. The
     * defect was its SIZE: `api.getPending(id)` served the whole record's question list,
     * 1,772,692 bytes at 1,000 runs, per submission. It now asks for the same 50-entry
     * window the screen does — 29,590 B, flat — so the two pending payloads of one
     * accepted answer go 3,545,986 B -> 61,558 B (98.3%), where bounding the mutation
     * alone had reached 1,804,660 B (49.1%).
     *
     * WHY IT COULD NOT BE BOUNDED BEFORE is worth keeping too, because it constrains
     * anyone changing either side: `confirmProposal` decided `submitAnswer` vs
     * `editField` from MEMBERSHIP in this list, so a question outside the window read as
     * "already answered" and took the edit route — `422 unrecognized_field` on a
     * legitimate first answer. That decision is now the server's
     * (`assistant-answer-routing.test.ts`), which is what made the bound safe rather
     * than merely cheap.
     */
    const answered = ALL.slice(1);
    const calls = stubFetchRoutes(
      routes({
        'GET /api/experiments/demo/runs/01RUN000000000000000000000': {
          body: {
            run: {
              id: '01RUN000000000000000000000',
              version: 'run.1',
              fields: {},
              inherited: {},
            },
          },
        },
        'POST /api/experiments/demo/runs/01RUN000000000000000000000/answers': {
          body: {
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

    const unbounded = () =>
      calls.filter((c) => c === 'GET /api/experiments/demo/pending').length;
    /* BOTH readers ask for the same window, so this counts them together — the screen's
       own page and the AgentContext's. That is not a loss of resolution: the assertion
       that matters is that NEITHER of them is the parameterless call above, and the
       total moving by one per submission is the repeat this test is named for. */
    const bounded = () =>
      calls.filter((c) => c === `GET /api/experiments/demo/pending?limit=${PAGE}`).length;
    /*
     * WAITED FOR, NOT SAMPLED — and this was a MEASURED FLAKE, not a precaution.
     *
     * The two mount reads come from two independent effects: the screen's own page, and
     * `useRecordSession`'s AgentContext effect keyed on `[id, version, active,
     * refreshNonce]`. `findByText` above resolves when the SCREEN's page has rendered,
     * which says nothing about whether the other effect has settled. Sampling the
     * counter at that instant therefore reads 2 on a fast machine and 1 on a slow one.
     * It read 1 in GitHub Actions (`expected 1 to be 2`, run 32926966992) while passing
     * every local run, which is the classic shape of an ordering assumption dressed up
     * as an assertion.
     *
     * The claim is unchanged — two windows on mount, a third after one accepted answer —
     * and `waitFor` states it without the assumption. The plain `expect` AFTER each
     * `waitFor` is not redundant: `waitFor` succeeds on the first tick the count matches,
     * so an over-count arriving later would slip past it. Re-asserting once the tree has
     * settled catches 3-on-mount, which would be a real regression and is the failure
     * this test would otherwise stop seeing.
     *
     * MECHANISM PROVEN, NOT INFERRED. A throwaway probe delayed every bounded read after
     * the first by 120 ms, so the AgentContext's mount read could not have landed by the
     * time `findByText` resolved. The sampled form then failed with EXACTLY the CI text —
     * `expected 1 to be 2` — and this `waitFor` form passed under the same delay. The
     * probe is not committed; it belongs in the diagnosis, not in the suite.
     */
    await waitFor(() => expect(bounded()).toBe(2));
    const beforeSubmit = unbounded();
    const boundedBefore = bounded();

    fireEvent.change(screen.getByLabelText(/series json/i), {
      target: { value: '[{"series_id":"s"}]' },
    });
    fireEvent.click(screen.getByText('Confirm'));
    await screen.findByText('1 / 120');
    await waitFor(() => expect(bounded()).toBe(3));

    // THE INVERSION. It was 1 on mount and 2 after one answer; it is now 0 and 0 — the
    // parameterless read is not made by this screen or by the session hook at all.
    expect(beforeSubmit).toBe(0);
    expect(unbounded()).toBe(0);
    // AND THE REPEAT IS STILL THERE, still counted, just bounded: two windows on mount
    // (the screen's page and the AgentContext's), a third after the accepted answer.
    expect(boundedBefore).toBe(2);
    expect(bounded()).toBe(3);
    // And the write itself carried a bounded list — the half that was fixed first.
    expect(screen.getByText('119 of 120 fields still to confirm')).toBeInTheDocument();
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

  it('a mutation body with no page block does not report a SUCCESSFUL write as failed', async () => {
    /*
     * THE HONESTY PROPERTY THIS SCREEN IS BUILT AROUND, INVERTED.
     *
     * Both mutation handlers read `resp.pending_page.total` unguarded. The key is
     * type-required and the server sends it on every mutation, so no reachable case is
     * known — but the consequence if one existed is the worst class this screen has:
     * the read throws INSIDE `.then()`, lands in `.catch()`, and paints "That answer
     * could not be applied" over a write the server ACCEPTED. Every other guard here
     * stops the screen claiming a value landed when it did not; this one made it claim
     * the opposite.
     *
     * The response below is a real accepted answer — `invalidation.changed: true`, the
     * question gone from the list — missing only the page block. Before the guard this
     * test paints the failure banner and pushes no answered row; after it, the write is
     * reported as what it was.
     */
    const answered = ALL.slice(1);
    stubFetchRoutes(
      routes({
        'GET /api/experiments/demo/runs/01RUN000000000000000000000': {
          body: {
            run: {
              id: '01RUN000000000000000000000',
              version: 'run.1',
              fields: {},
              inherited: {},
            },
          },
        },
        'POST /api/experiments/demo/runs/01RUN000000000000000000000/answers': {
          body: {
            // NO `pending_page`. Everything else is a normal accepted answer.
            pending: answered,
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

    // The write is reported as applied: the counter moves and the answered row exists.
    // `119` is `resp.pending.length`, which is the CONTRACT's reading of an absent page
    // block ("the list is the set") rather than a number invented to fill the gap.
    expect(await screen.findByText('1 / 120')).toBeInTheDocument();
    // AND NO FAILURE IS CLAIMED. This is the assertion that fails without the guard.
    expect(screen.queryByText(/That answer could not be applied/)).toBeNull();
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
