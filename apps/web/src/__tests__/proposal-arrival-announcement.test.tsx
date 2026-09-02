/*
 * A COLLEAGUE'S PROPOSAL ARRIVES — the announcement `IngestionProposalsPanel`
 * makes when a signal-driven silent reload turns up a NEW proposal awaiting
 * judgement, as opposed to one this reader's own review act just moved out of
 * that state.
 *
 * WHY THIS READS `by_state.open` RATHER THAN DIFFING THE LOADED WINDOW. The
 * obvious mechanism — "an id in the new page that was not in the old one" — was
 * checked against the server and rejected. `_sorted_proposals`
 * (`apps/api/isaac_api/workspace.py`) orders OLDEST FIRST
 * (`(proposed_utc, proposal_id)`), and `list_proposals` (`apps/api/isaac_api/routes.py`)
 * walks that order from the cursor forward. A newly arrived proposal has the
 * LATEST `proposed_utc` on the record, so it sorts LAST — and the panel's
 * default view (`cursor=null`) is the FIRST `_PROPOSAL_WINDOW_DEFAULT` (50)
 * entries, the OLDEST 50. On any record already holding 50+ proposals a new
 * arrival is never in that window at all, however many times it is re-read. So
 * this panel reads `by_state.open` instead, which `_proposals_payload` computes
 * over the WHOLE record on every response, regardless of filter or cursor — see
 * `IngestionProposalsPanel.tsx`'s own comment on `lastOpenCountRef` for the full
 * argument this file pins.
 *
 * Every fixture is synthetic; none of it reaches a backend.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { IngestionProposalsPanel } from '../components/IngestionProposalsPanel';
import { PROPOSAL_RECORD_SCOPED_TARGET_PATHS, PROPOSAL_TARGET_PATHS, stubFetchRoutes } from '../test/apiFixtures';
import type { RecordChangeSummary } from '../lib/recordChanges';
import type { ApiProposal, ApiProposalsResponse } from '../lib/types';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const EXP = 'demo';
const LIST = `GET /api/experiments/${EXP}/proposals`;
const RUN_ONE = '01RUNAAAAAAAAAAAAAAAAAAAA0';

const RUN_PATH = 'sample.material.name';
const TARGET_PATHS = PROPOSAL_TARGET_PATHS;
const RECORD_SCOPED = PROPOSAL_RECORD_SCOPED_TARGET_PATHS;

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * A DISTINCTIVE STRING THAT MUST NEVER APPEAR IN AN ARRIVAL SENTENCE — the
 * negative control for "no proposal content, ever". If this string turns up
 * anywhere the announcement is asserted, the mechanism leaked content it must
 * not have reached.
 */
const SENTINEL = 'SENTINEL_ARSENIC_K_EDGE_DO_NOT_ANNOUNCE';

function proposalFixture(over: Partial<ApiProposal> = {}): ApiProposal {
  return {
    proposal_id: 'P1',
    experiment_id: EXP,
    note_id: 'N1',
    run_id: RUN_ONE,
    target_field_path: RUN_PATH,
    proposed_value: SENTINEL,
    rule: SENTINEL,
    source: 'transcript',
    proposed_utc: '2026-09-01T10:00:00Z',
    base_rev: 3,
    target_digest: 'digest-at-proposal-time',
    start_char: 0,
    end_char: 11,
    client_request_key: null,
    state: 'open',
    subject: null,
    trust_basis: 'unattributed',
    accepted_value: null,
    accepted_from: null,
    applied_via: null,
    applied_run_id: null,
    applied_rev: null,
    applied_target_digest: null,
    history: [
      {
        action: 'propose',
        at: '2026-09-01T10:00:00Z',
        from_state: null,
        to_state: 'open',
        actor_trust_basis: 'unattributed',
        actor_subject: null,
        accepted_value: null,
        accepted_from: null,
        reason: null,
      },
    ],
    status: 'ingestion_proposal',
    verified: false,
    is_evidence: false,
    is_field_value: false,
    applied: false,
    current_target_digest: 'digest-at-proposal-time',
    target_stale: false,
    still_current: null,
    excerpt: SENTINEL,
    attributed: false,
    accepted_by: null,
    ...over,
  };
}

function page(
  proposals: ApiProposal[],
  over: Partial<ApiProposalsResponse> = {},
): ApiProposalsResponse {
  return {
    proposals,
    total: proposals.length,
    returned: proposals.length,
    by_state: {
      open: proposals.filter((p) => p.state === 'open').length,
      accepted: proposals.filter((p) => p.state === 'accepted').length,
      rejected: proposals.filter((p) => p.state === 'rejected').length,
      superseded: proposals.filter((p) => p.state === 'superseded').length,
      withdrawn: proposals.filter((p) => p.state === 'withdrawn').length,
    },
    has_more: false,
    next_cursor: null,
    // THE SERVER STATES THE ORDER AND THIS FIXTURE STATES IT TOO, defaulting to
    // the server's own default. It is deliberately not optional in
    // `ApiProposalsResponse`: a test that wants to model a newest-first window has
    // to say so, which is what makes "the count line describes the LOADED window"
    // assertable at all.
    order: 'oldest_first' as const,
    window_default: 50,
    window_max: 200,
    max_per_record: 1000,
    unreadable_entries: 0,
    target_field_paths: TARGET_PATHS,
    record_scoped_target_field_paths: RECORD_SCOPED,
    states: ['open', 'accepted', 'rejected', 'superseded', 'withdrawn'],
    review_actions: ['accept', 'reject', 'supersede', 'withdraw'],
    accepted_from_values: ['candidate', 'edited'],
    experiment_version: '1.7',
    ...over,
  };
}

/**
 * `by_state.open` OVERRIDDEN INDEPENDENTLY OF `proposals`, on purpose. The
 * mechanism under test reads `by_state.open`, which the real server computes
 * over the WHOLE record and not merely the window this panel happens to be
 * showing — so a fixture that derived it only from the visible `proposals`
 * array could never model "the record holds more open proposals than are in
 * this window", which is the ordinary case the mechanism exists for.
 */
function pageWithOpenCount(
  proposals: ApiProposal[],
  openCount: number,
  over: Partial<ApiProposalsResponse> = {},
): ApiProposalsResponse {
  const built = page(proposals, over);
  return { ...built, by_state: { ...built.by_state, open: openCount } };
}

function renderPanel(activity: RecordChangeSummary | null = null) {
  return render(
    <MemoryRouter
      initialEntries={['/']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <IngestionProposalsPanel experimentId={EXP} activity={activity} />
    </MemoryRouter>,
  );
}

function rerenderWith(view: ReturnType<typeof renderPanel>, activity: RecordChangeSummary | null) {
  view.rerender(
    <MemoryRouter
      initialEntries={['/']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <IngestionProposalsPanel experimentId={EXP} activity={activity} />
    </MemoryRouter>,
  );
}

function activityFor(ids: string[], highestRev: number, proposalRev: number = highestRev): RecordChangeSummary {
  return {
    recordMoved: false,
    runIds: [],
    proposalIds: ids,
    proposalStates: [],
    otherKinds: [],
    highestRev,
    // `-1` IS THE "NO RUN ENTRY SURVIVED" VALUE (`recordChanges.ts`), not a filler:
    // every batch this file builds names proposals only. The field arrived with the
    // bounded live-refresh work on `main`, which updated the identical helper in
    // `ingestion-proposals-panel.test.tsx` and not this copy — the typechecker
    // caught it on the merge rather than a test doing so, because a summary this
    // panel reads for `proposalRev` alone behaves the same either way.
    runRev: -1,
    proposalRev,
  };
}

/** The visible arrival note's text, or `null` if none is rendered. */
function arrivalNoteText(): string | null {
  const el = document.querySelector('.proposals-arrival-note-text');
  return el === null ? null : (el.textContent ?? '');
}

/** The sr-only status region's text (act confirmations AND arrivals share it). */
function statusText(): string {
  return screen.getByRole('status').textContent ?? '';
}

// ---------------------------------------------------------------------------

describe('an arrival is announced', () => {
  it('announces once, visibly and in the live region, with the right shape of sentence', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return {
          body:
            reads === 1
              ? pageWithOpenCount([proposalFixture()], 1)
              : pageWithOpenCount([proposalFixture(), proposalFixture({ proposal_id: 'P2' })], 2),
        };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');
    expect(arrivalNoteText()).toBeNull();

    rerenderWith(view, activityFor(['P2'], 9));
    await waitFor(() => expect(reads).toBe(2));

    await waitFor(() =>
      expect(arrivalNoteText()).toBe('At least 1 proposed change arrived and is ready to review.'),
    );
    expect(statusText()).toContain('At least 1 proposed change arrived and is ready to review.');
  });

  it('pluralises for more than one', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return {
          body:
            reads === 1
              ? pageWithOpenCount([proposalFixture()], 1)
              : pageWithOpenCount(
                  [proposalFixture(), proposalFixture({ proposal_id: 'P2' }), proposalFixture({ proposal_id: 'P3' })],
                  3,
                ),
        };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    rerenderWith(view, activityFor(['P2', 'P3'], 9));
    await waitFor(() =>
      expect(arrivalNoteText()).toBe('At least 2 proposed changes arrived and are ready to review.'),
    );
  });

  it('the same signal again does not re-announce — it is deduped upstream, before a second read', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return {
          body:
            reads === 1
              ? pageWithOpenCount([proposalFixture()], 1)
              : pageWithOpenCount([proposalFixture(), proposalFixture({ proposal_id: 'P2' })], 2),
        };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    const sig = activityFor(['P2'], 9);
    rerenderWith(view, sig);
    await waitFor(() => expect(reads).toBe(2));
    await waitFor(() => expect(arrivalNoteText()).not.toBeNull());

    // The identical signal, delivered again — the panel's own `proposalSignal`
    // dedupe (keyed on `proposalRev:ids`) must not even issue a second read.
    rerenderWith(view, { ...sig });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(reads).toBe(2);
  });
});

describe('an arrival is NOT announced', () => {
  it('on initial hydration, even though the record already holds open proposals', async () => {
    stubFetchRoutes({ [LIST]: { body: pageWithOpenCount([proposalFixture()], 2) } });
    renderPanel(null);
    await screen.findByText('Proposed value');

    expect(arrivalNoteText()).toBeNull();
    expect(statusText()).toBe('');
  });

  it('on a same-mount race where the signal-driven request settles BEFORE the ordinary first read has', async () => {
    /*
     * A mount whose FIRST render already carries a non-null `activity` fires two
     * requests in the same commit: the ordinary first read (`reloadNonce` starts
     * at 0) and, synchronously after it in the same effect flush, the
     * signal-driven one `proposalSignal`'s own effect triggers. If the SECOND
     * settles first, `lastOpenCountRef` has no baseline yet — `previousOpen` is
     * `null` — and there is nothing honest to compare its count against. This is
     * the one case `isArrivalReload` alone does not cover, because this request
     * genuinely IS signal-driven; the `previousOpen !== null` guard is what
     * closes it.
     */
    const resolvers: Array<() => void> = [];
    let seq = 0;
    const bodies = [
      pageWithOpenCount([proposalFixture()], 1),
      pageWithOpenCount([proposalFixture(), proposalFixture({ proposal_id: 'P2' })], 2),
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const raw =
          typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        const path = raw.replace(/^https?:\/\/[^/]+/, '');
        const method = init?.method ?? 'GET';
        const isList =
          method === 'GET' && path.startsWith(`/api/experiments/${EXP}/proposals`);
        if (!isList) throw new Error(`unrouted request: ${method} ${path}`);
        const index = seq;
        seq += 1;
        return new Promise<Response>((resolve) => {
          resolvers[index] = () =>
            resolve({
              ok: true,
              status: 200,
              headers: { get: () => null },
              json: async () => bodies[index] ?? bodies[bodies.length - 1],
            } as unknown as Response);
        });
      }),
    );

    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <IngestionProposalsPanel experimentId={EXP} activity={activityFor(['P2'], 5)} />
      </MemoryRouter>,
    );

    // Both requests are outstanding before either is released — the race this
    // test targets, made a fact rather than an assumption.
    await waitFor(() => expect(seq).toBe(2));

    // Release the SIGNAL-DRIVEN one (index 1) first.
    await act(async () => {
      resolvers[1]();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(arrivalNoteText()).toBeNull();

    await act(async () => {
      resolvers[0]();
      await Promise.resolve();
      await Promise.resolve();
    });
    // The ordinary first read landing afterwards must not retroactively announce
    // either — it is the one that ESTABLISHES the baseline, not one to compare
    // against it.
    expect(arrivalNoteText()).toBeNull();
  });

  it('on a reload this panel caused itself (a Reject), even when by_state.open happens to have gone UP', async () => {
    /*
     * A REAL RACE, MODELLED DELIBERATELY. This reader rejects P1; the response
     * to THAT SAME reload nonetheless reports a HIGHER open count than before
     * (2 -> 3), because a colleague's P3 landed at the same moment. If the gate
     * were "the count went up" alone, this would wrongly read as an arrival. It
     * must not: `arrivalReloadRef` is set ONLY by the change-feed signal effect,
     * never by `review()`'s own `reload(true)`, so a self-caused reload can never
     * raise the note — the mechanism this test pins.
     */
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return {
          body:
            reads === 1
              ? pageWithOpenCount([proposalFixture(), proposalFixture({ proposal_id: 'P2' })], 2)
              : pageWithOpenCount(
                  [
                    proposalFixture({ state: 'rejected' }),
                    proposalFixture({ proposal_id: 'P2' }),
                    proposalFixture({ proposal_id: 'P3' }),
                  ],
                  3,
                ),
        };
      },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: {
        body: { proposal: proposalFixture({ state: 'rejected' }), experiment_version: '1.8' },
      },
    });
    renderPanel(null);
    await screen.findAllByText('Proposed value');

    // Two cards, one per proposal, both built from the same fixture — reject the
    // FIRST (P1), leaving P2 open.
    const rejectButtons = await screen.findAllByRole('button', { name: 'Reject…' });
    fireEvent.click(rejectButtons[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Reject' }));

    // The ACT is announced (the panel's existing behaviour)…
    await waitFor(() =>
      expect(statusText()).toContain(`The proposal for ${RUN_PATH} was rejected and kept on the record.`),
    );
    // …and it is announced ALONE — no arrival note, and the sentence never
    // mentions an arrival, despite `by_state.open` having risen in that same
    // response.
    expect(arrivalNoteText()).toBeNull();
    expect(statusText()).not.toContain('arrived');
    await waitFor(() => expect(reads).toBe(2));
  });

  it('on a filter change, even though it is a silent reload of the same shape', async () => {
    stubFetchRoutes({
      [LIST]: { body: pageWithOpenCount([proposalFixture()], 1) },
    });
    renderPanel(null);
    await screen.findByText('Proposed value');

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'open' } });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(arrivalNoteText()).toBeNull();
  });

  it(
    'I1a: on a signal-driven reload whose open count did NOT rise — the mutant `>` -> `>=` ' +
      'would say "At least 0 proposed changes arrived"',
    async () => {
      let reads = 0;
      stubFetchRoutes({
        [LIST]: () => {
          reads += 1;
          // The count is IDENTICAL across both reads — nothing this panel can
          // read has moved, even though the signal is genuinely signal-driven.
          return { body: pageWithOpenCount([proposalFixture()], 1) };
        },
      });
      const view = renderPanel(null);
      await screen.findByText('Proposed value');

      rerenderWith(view, activityFor(['P1'], 9));
      await waitFor(() => expect(reads).toBe(2));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
      });

      expect(arrivalNoteText()).toBeNull();
      expect(statusText()).toBe('');
    },
  );

  it(
    'I3: a net-offset arrival (open goes 3 -> 3 because one proposal arrived while ' +
      'another was reviewed elsewhere) is invisible to this mechanism, and says nothing false',
    async () => {
      let reads = 0;
      stubFetchRoutes({
        [LIST]: () => {
          reads += 1;
          return {
            body:
              reads === 1
                ? pageWithOpenCount(
                    [
                      proposalFixture(),
                      proposalFixture({ proposal_id: 'P2' }),
                      proposalFixture({ proposal_id: 'P3' }),
                    ],
                    3,
                    { by_state: { open: 3, accepted: 0, rejected: 0, superseded: 0, withdrawn: 0 } },
                  )
                : // A colleague's P4 arrived (open would-be 4) at the same moment
                  // someone else accepted P1 elsewhere (open -1) — net 3 -> 3, and
                  // `by_state.accepted` moved to record that the OTHER shift was a
                  // real review act, not a fabricated "nothing happened" reading.
                  pageWithOpenCount(
                    [
                      proposalFixture({ state: 'accepted' }),
                      proposalFixture({ proposal_id: 'P2' }),
                      proposalFixture({ proposal_id: 'P3' }),
                      proposalFixture({ proposal_id: 'P4' }),
                    ],
                    3,
                    { by_state: { open: 3, accepted: 1, rejected: 0, superseded: 0, withdrawn: 0 } },
                  ),
          };
        },
      });
      const view = renderPanel(null);
      // Three cards on hydration — the heading is not unique.
      await screen.findAllByText('Proposed value');

      rerenderWith(view, activityFor(['P4'], 9));
      await waitFor(() => expect(reads).toBe(2));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
      });

      // Not "0 arrived", not "an arrival was missed" — nothing at all. The
      // mechanism cannot see a net-zero arrival, and it must not GUESS at one.
      expect(arrivalNoteText()).toBeNull();
      expect(statusText()).toBe('');
    },
  );
});

describe('I1b — the arrival flag does not leak onto a later, unrelated request', () => {
  it('a signal-driven reload followed by a filter-change reload whose count happens to rise does NOT announce', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        // Read 1: initial hydration, open=1.
        // Read 2: the SIGNAL-driven reload — open unchanged at 1 (no real arrival
        //         this time; the signal was for something else the panel still
        //         has to re-read, e.g. a state-only move that nets to zero).
        // Read 3: a FILTER CHANGE the reader makes right after — open coincidentally
        //         rises to 2. If `arrivalReloadRef.current = false` at the top of
        //         the fetch effect were ever deleted, this request would still be
        //         flagged as arrival-eligible from read 2's leftover `true`, and
        //         this filter change would wrongly announce an arrival it did not
        //         cause and cannot attribute.
        if (reads <= 2) return { body: pageWithOpenCount([proposalFixture()], 1) };
        return {
          body: pageWithOpenCount(
            [proposalFixture(), proposalFixture({ proposal_id: 'P2' })],
            2,
          ),
        };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    rerenderWith(view, activityFor(['P1'], 9));
    await waitFor(() => expect(reads).toBe(2));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(arrivalNoteText()).toBeNull();

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'open' } });
    await waitFor(() => expect(reads).toBe(3));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // The count DID rise on this third read (1 -> 2) — and it must still say
    // nothing, because this request was never signal-driven.
    expect(arrivalNoteText()).toBeNull();
    expect(statusText()).toBe('');
  });
});

describe('no proposal content ever reaches the announcement', () => {
  it('the sentence names only a count — never the value, path, rule, note or excerpt', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return {
          body:
            reads === 1
              ? pageWithOpenCount([proposalFixture()], 1)
              : pageWithOpenCount([proposalFixture(), proposalFixture({ proposal_id: 'P2' })], 2),
        };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    rerenderWith(view, activityFor(['P2'], 9));
    await waitFor(() => expect(arrivalNoteText()).not.toBeNull());

    expect(arrivalNoteText()).not.toContain(SENTINEL);
    expect(statusText()).not.toContain(SENTINEL);
    expect(arrivalNoteText()).not.toContain(RUN_PATH);
    expect(statusText()).not.toMatch(/P1|P2/);
  });
});

describe('the visible note', () => {
  it('is dismissible, and Dismiss is a real keyboard-reachable button', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return {
          body:
            reads === 1
              ? pageWithOpenCount([proposalFixture()], 1)
              : pageWithOpenCount([proposalFixture(), proposalFixture({ proposal_id: 'P2' })], 2),
        };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    rerenderWith(view, activityFor(['P2'], 9));
    await waitFor(() => expect(arrivalNoteText()).not.toBeNull());

    const dismiss = screen.getByRole('button', { name: 'Dismiss' });
    // A real <button>, not a div with a click handler — Enter and Space both
    // dispatch `click` on a native button; that is what makes this reachable
    // without a pointer, the same convention `run-browser.test.tsx` uses for
    // Load More.
    expect(dismiss.tagName).toBe('BUTTON');
    dismiss.focus();
    expect(document.activeElement).toBe(dismiss);
    fireEvent.click(dismiss);

    expect(arrivalNoteText()).toBeNull();
    // Dismissing clears only the visible note. The one-shot sr-only utterance is
    // not retracted — it was already spoken and there is nothing to take back.
    expect(statusText()).toContain('arrived');
  });

  it('M3: two arrivals before a Dismiss accumulate into ONE running total, not two identical notes', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        if (reads === 1) return { body: pageWithOpenCount([proposalFixture()], 1) };
        if (reads === 2) {
          return {
            body: pageWithOpenCount(
              [proposalFixture(), proposalFixture({ proposal_id: 'P2' })],
              2,
            ),
          };
        }
        return {
          body: pageWithOpenCount(
            [
              proposalFixture(),
              proposalFixture({ proposal_id: 'P2' }),
              proposalFixture({ proposal_id: 'P3' }),
            ],
            3,
          ),
        };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    // Arrival 1: open 1 -> 2.
    rerenderWith(view, activityFor(['P2'], 9));
    await waitFor(() =>
      expect(arrivalNoteText()).toBe('At least 1 proposed change arrived and is ready to review.'),
    );

    // Arrival 2, WITHOUT a Dismiss in between: open 2 -> 3.
    rerenderWith(view, activityFor(['P3'], 12));
    await waitFor(() =>
      expect(arrivalNoteText()).toBe(
        'At least 2 proposed changes arrived and are ready to review.',
      ),
    );

    // Dismiss resets the running total — a THIRD arrival after it starts fresh
    // at 1, not 3.
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(arrivalNoteText()).toBeNull();
  });

  it('does not steal focus when it appears', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return {
          body:
            reads === 1
              ? pageWithOpenCount([proposalFixture()], 1)
              : pageWithOpenCount([proposalFixture(), proposalFixture({ proposal_id: 'P2' })], 2),
        };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    const filterSelect = screen.getByLabelText('Show');
    filterSelect.focus();
    expect(document.activeElement).toBe(filterSelect);

    rerenderWith(view, activityFor(['P2'], 9));
    await waitFor(() => expect(arrivalNoteText()).not.toBeNull());

    expect(document.activeElement).toBe(filterSelect);
  });
});

/*
 * THE ACTION THAT MAKES THE SENTENCE REACHABLE.
 *
 * Everything above pins that the arrival is DETECTED and SAID. None of it pins that
 * the reader can then SEE the thing that arrived — and on the records this mechanism
 * was written for they could not. The arrival is detected from `by_state.open`, which
 * is the whole record; the window it is announced into is the OLDEST 50; and the
 * arrival, carrying the latest `proposed_utc`, sorts LAST. So the note could be
 * truthful and still be a dead end.
 */
describe('the arrival note leads somewhere', () => {
  /** The list URLs the panel actually requested, in order. */
  function urls(): string[] {
    const calls = (globalThis.fetch as unknown as { mock: { calls: [string][] } }).mock.calls;
    return calls.map(([url]) => String(url));
  }

  /** The value only the NEWEST-first window renders. */
  const NEWEST_VALUE = 'NEWEST_ARRIVAL_VALUE';

  /**
   * A record holding MORE OPEN PROPOSALS THAN THE WINDOW SHOWS, answering each
   * order from its own end — which is the situation the whole feature is for, and
   * which a fixture that served one page for every query could not model.
   *
   * The oldest-first window renders `SENTINEL`; the newest-first window renders
   * `NEWEST_VALUE`. They are DISJOINT on purpose: an assertion that `NEWEST_VALUE`
   * is on screen is then satisfiable only by a request that actually asked for the
   * other direction, so a build that flipped the order client-side, or that ignored
   * `order` entirely, cannot pass.
   *
   * `bump()` RAISES `by_state.open`, and it is a separate act rather than a read
   * counter for a reason this fixture got wrong first time: the arrival mechanism
   * compares against the count from the LAST successful read, whatever caused it, so
   * a counter keyed on "the second read" makes the arrival land on a page change and
   * leaves nothing for the signal to detect.
   */
  function stubBothOrders(): { bump: () => void } {
    let open = 60;
    stubFetchRoutes({
      [LIST]: (_init, key) => {
        const newest = String(key).includes('order=newest_first');
        const shown = newest
          ? [proposalFixture({ proposal_id: 'NEW_9', proposed_value: NEWEST_VALUE })]
          : [proposalFixture({ proposal_id: 'OLD_1' })];
        return {
          body: pageWithOpenCount(shown, open, {
            total: 61,
            returned: 1,
            has_more: !newest,
            next_cursor: newest ? null : 'OLD_1',
            // ANSWERED FROM THE KEY, as the server answers it from the query: the
            // count line is built from `loaded.order`, so a stub that always
            // returned the default would prove only that the panel renders a
            // constant.
            order: newest ? 'newest_first' : 'oldest_first',
          }),
        };
      },
    });
    return {
      bump: () => {
        open += 1;
      },
    };
  }

  it('offers an action that puts the arrival in the FIRST window, and names both things it does', async () => {
    const { bump } = stubBothOrders();
    const view = renderPanel(null);
    await screen.findByText('Proposed value');
    // Before: the oldest window, and the arrival is not in it.
    expect(screen.queryByText(NEWEST_VALUE)).toBeNull();

    bump();
    rerenderWith(view, activityFor(['NEW_9'], 9));
    await waitFor(() => expect(arrivalNoteText()).not.toBeNull());

    // THE LABEL NAMES BOTH ACTS. It changes the order AND the state filter, and a
    // control that discarded the reader's filter without saying so is the quiet
    // side effect `EmptyProposals`' two-handler split exists to avoid.
    const action = screen.getByRole('button', { name: 'Show Open, Newest First' });
    fireEvent.click(action);

    await waitFor(() =>
      expect(
        urls().some((u) => u.includes('order=newest_first') && u.includes('state=open')),
      ).toBe(true),
    );
    // THE MEASUREMENT THIS SLICE EXISTS FOR: the arrived proposal is now on screen,
    // and it is on screen only because the OTHER direction was requested.
    await screen.findByText(NEWEST_VALUE);
  });

  it('asks from the FIRST window, carrying no cursor the server would refuse', async () => {
    const { bump } = stubBothOrders();
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    // Page forward first, so the panel is holding a cursor when the note arrives.
    fireEvent.click(screen.getByRole('button', { name: 'Next Page' }));
    await waitFor(() => expect(urls().some((u) => u.includes('after=OLD_1'))).toBe(true));

    bump();
    rerenderWith(view, activityFor(['NEW_9'], 9));
    await waitFor(() => expect(arrivalNoteText()).not.toBeNull());
    fireEvent.click(screen.getByRole('button', { name: 'Show Open, Newest First' }));

    await waitFor(() => expect(urls().some((u) => u.includes('order=newest_first'))).toBe(true));
    // A cursor from an oldest-first window is refused `422 cursor_order_mismatch`
    // in the other order — so the one request shape that must never be built is
    // one carrying both.
    expect(urls().some((u) => u.includes('order=newest_first') && u.includes('after='))).toBe(
      false,
    );
  });

  it('is keyboard operable and does not steal focus, exactly as Dismiss is', async () => {
    const { bump } = stubBothOrders();
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    const filterSelect = screen.getByLabelText('Show');
    filterSelect.focus();

    bump();
    rerenderWith(view, activityFor(['NEW_9'], 9));
    await waitFor(() => expect(arrivalNoteText()).not.toBeNull());
    // Appearing next to a focused control must not move focus off it.
    expect(document.activeElement).toBe(filterSelect);

    const action = screen.getByRole('button', { name: 'Show Open, Newest First' });
    expect(action.tagName).toBe('BUTTON');
    action.focus();
    expect(document.activeElement).toBe(action);
    fireEvent.click(action);

    // Activating it clears the note — the reader is being taken to the thing it
    // was about, so leaving it standing would be a notice about a done act.
    await waitFor(() => expect(arrivalNoteText()).toBeNull());
  });

  it('says the order in the count line and utters nothing new — one event, one utterance', async () => {
    const { bump } = stubBothOrders();
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    bump();
    rerenderWith(view, activityFor(['NEW_9'], 9));
    await waitFor(() => expect(arrivalNoteText()).not.toBeNull());
    const spokenAtArrival = statusText();

    fireEvent.click(screen.getByRole('button', { name: 'Show Open, Newest First' }));
    await screen.findByText(/Showing 1 of 61 proposals on this record · newest first/);

    // THE sr-only REGION IS UNTOUCHED BY THE ACT. It already spoke this arrival
    // once; a second utterance from a control that only changed a view would be
    // the twice-for-one-event defect this note's own comment records avoiding.
    expect(statusText()).toBe(spokenAtArrival);
    // And no proposal content ever reaches either surface.
    expect(statusText()).not.toContain(SENTINEL);
    expect(document.querySelector('.proposals-count')?.textContent ?? '').not.toContain(SENTINEL);
  });

  it('CLEARS THE RUNNING TOTAL, so the next arrival counts from there and not from before it', async () => {
    /*
     * `arrivalTotalRef` accumulates arrivals the reader has not ACKNOWLEDGED — not
     * arrivals they have not reviewed; Dismiss's own comment is explicit that it
     * marks nothing reviewed, and neither does this. Being taken to the window that
     * HOLDS them is an acknowledgement, so the total has to reset here for the same
     * reason it resets on Dismiss.
     *
     * MUTATION: deleted `arrivalTotalRef.current = 0` from the action's handler.
     * Before this test the whole file passed 82/82 with the line gone — the reset
     * was unpinned. With it, the second arrival reads "At least 2", counting one the
     * reader had already been shown.
     */
    const { bump } = stubBothOrders();
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    bump();
    rerenderWith(view, activityFor(['NEW_9'], 9));
    await waitFor(() =>
      expect(arrivalNoteText()).toBe('At least 1 proposed change arrived and is ready to review.'),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Show Open, Newest First' }));
    await waitFor(() => expect(arrivalNoteText()).toBeNull());
    // The reader has now SEEN that arrival — the window it is in is on screen.
    await screen.findByText(NEWEST_VALUE);

    // A SECOND, GENUINELY NEW arrival. It is one proposal, and the note must say so.
    bump();
    rerenderWith(view, activityFor(['NEW_10'], 14));
    await waitFor(() => expect(arrivalNoteText()).not.toBeNull());
    expect(arrivalNoteText()).toBe(
      'At least 1 proposed change arrived and is ready to review.',
    );
    expect(arrivalNoteText()).not.toContain('At least 2');
  });

  it('NEGATIVE CONTROL: with no arrival there is no action to activate', async () => {
    stubFetchRoutes({ [LIST]: { body: pageWithOpenCount([proposalFixture()], 2) } });
    renderPanel(null);
    await screen.findByText('Proposed value');

    expect(arrivalNoteText()).toBeNull();
    expect(screen.queryByRole('button', { name: 'Show Open, Newest First' })).toBeNull();
    // The ORDER CONTROL is still there — it is not part of the note and a reader
    // may reach the other direction whenever they like.
    expect((screen.getByLabelText('Order') as HTMLSelectElement).value).toBe('oldest_first');
  });
});

describe('layout — no fixed pixel width, no animation added', () => {
  it('the arrival note CSS is flex/wrap only, matching every other toolbar row in this file', () => {
    const css = fs.readFileSync(
      path.resolve(__dirname, '../components/ingestionProposals.css'),
      'utf8',
    );
    const match = css.match(/\.proposals-arrival-note\s*\{([^}]*)\}/);
    expect(match).not.toBeNull();
    const body = match ? match[1] : '';
    expect(body).toMatch(/display:\s*flex/);
    expect(body).toMatch(/flex-wrap:\s*wrap/);
    // No fixed pixel WIDTH was added — narrow-viewport safety is the wrap rule
    // above, not a clamp.
    expect(body).not.toMatch(/(?<!max-)width\s*:\s*\d/);
    // No animation or transition was added, so `prefers-reduced-motion` needs no
    // special handling here — there is nothing to reduce.
    expect(body).not.toMatch(/animation|transition/);
  });
});
