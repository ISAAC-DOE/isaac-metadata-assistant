/*
 * A DEEP LINK INTO ONE PROPOSAL — `?proposal=<id>`, read by
 * `IngestionProposalsPanel` off the record's own address.
 *
 * WHAT MAKES THIS HARD, AND WHAT EVERY TEST BELOW IS REALLY ABOUT. The proposals
 * list is a WINDOW: `_sorted_proposals` (`apps/api/isaac_api/workspace.py`) orders
 * OLDEST FIRST, `_PROPOSAL_WINDOW_DEFAULT` (`routes.py`) is 50, and this build has
 * no read-one-proposal route anywhere. So "the id is not in the rows I was served"
 * is evidence of exactly ONE thing, and "the record does not hold it" is a
 * different, stronger claim that a single page cannot support. A surface that
 * collapsed the two would tell a scientist a colleague's suggestion had vanished
 * when it was two pages away.
 *
 * So the panel has THREE verdicts, not two, and the tests are organised by them:
 *   · in the window  — mark the card, focus it once, say which field it is for
 *   · not in the window — say so, hedged, and offer the control that widens it
 *   · not in a window that PROVABLY covers the whole record — only here may it say
 *     the record does not hold it, and the four conditions are over-determined
 *     (`total`, `has_more`, the filter/cursor, and `unreadable_entries`, which is
 *     the one that is easy to forget: a stored entry this build could not present
 *     as a proposal is NOT counted in `total` and could carry the linked id)
 *
 * EVERY ASSERTION HERE IS BEHAVIOURAL EXCEPT ONE, WHICH IS LABELLED. The rendered
 * mark, the focused element, the announced sentence and the REQUEST the widening
 * control issues are all observed. The exception is the over-claim ban — a scan of
 * the rendered copy for phrasings that would assert non-existence — which is a
 * polarity guard of the kind `upload-claim-parity.test.tsx` already establishes
 * here, and it is named as structural rather than passed off as behaviour.
 *
 * THE RED PROOF FOR EVERY GUARD BELOW is recorded in the slice report: each was run
 * against a deliberately wrong panel (the parameter ignored; the mark applied to
 * every card; the hedged sentence replaced by "there is no such proposal"; the
 * focus latch removed; the whole-record claim made without the
 * `unreadable_entries` conjunct) and each reported RED.
 *
 * Every fixture is synthetic; none of it reaches a backend.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { IngestionProposalsPanel } from '../components/IngestionProposalsPanel';
import {
  PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
  PROPOSAL_TARGET_PATHS,
  bundleRoutes,
  runFixture,
  runsPage,
  stubFetchRoutes,
} from '../test/apiFixtures';
import { RECORD_PROPOSAL_PARAM, ROUTES } from '../lib/routes';
import type { RecordChangeSummary } from '../lib/recordChanges';
import type { ApiProposal, ApiProposalsResponse } from '../lib/types';

const EXP = 'demo';
const LIST = `GET /api/experiments/${EXP}/proposals`;
const RUN_ONE = '01RUNAAAAAAAAAAAAAAAAAAAA0';

const LINKED = 'P_LINKED';
const OTHER = 'P_OTHER';
const LINKED_PATH = 'sample.material.name';
const OTHER_PATH = 'sample.material.formula';

afterEach(() => {
  vi.unstubAllGlobals();
});

function proposalFixture(over: Partial<ApiProposal> = {}): ApiProposal {
  return {
    proposal_id: OTHER,
    experiment_id: EXP,
    note_id: 'N1',
    run_id: RUN_ONE,
    target_field_path: OTHER_PATH,
    proposed_value: 'a synthetic proposed value',
    rule: 'synthetic_rule',
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
    excerpt: 'a synthetic excerpt',
    attributed: false,
    accepted_by: null,
    ...over,
  };
}

/**
 * A window.
 *
 * `total` DEFAULTS TO THE NUMBER OF ROWS AND IS OVERRIDABLE INDEPENDENTLY, because
 * the server's `total` is `len(exp.proposals)` — the RECORD's count, never the
 * window's — and the whole point of the third verdict is the case where the two
 * differ. A fixture that derived one from the other could not model it.
 */
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
    order: 'oldest_first' as const,
    window_default: 50,
    window_max: 200,
    max_per_record: 1000,
    unreadable_entries: 0,
    target_field_paths: PROPOSAL_TARGET_PATHS,
    record_scoped_target_field_paths: PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
    states: ['open', 'accepted', 'rejected', 'superseded', 'withdrawn'],
    review_actions: ['accept', 'reject', 'supersede', 'withdraw'],
    accepted_from_values: ['candidate', 'edited'],
    experiment_version: '1.7',
    ...over,
  };
}

/** The panel, mounted at a record address carrying whatever query is given. */
function renderPanel(query: string, activity: RecordChangeSummary | null = null) {
  return render(
    <MemoryRouter
      initialEntries={[`/record/${EXP}${query}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <IngestionProposalsPanel experimentId={EXP} activity={activity} />
    </MemoryRouter>,
  );
}

function rerenderWith(
  view: ReturnType<typeof renderPanel>,
  query: string,
  activity: RecordChangeSummary | null,
) {
  view.rerender(
    <MemoryRouter
      initialEntries={[`/record/${EXP}${query}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <IngestionProposalsPanel experimentId={EXP} activity={activity} />
    </MemoryRouter>,
  );
}

function activityFor(ids: string[], rev: number): RecordChangeSummary {
  return {
    recordMoved: false,
    runIds: [],
    proposalIds: ids,
    proposalStates: [],
    otherKinds: [],
    highestRev: rev,
    /* `-1` is `recordChanges.ts`'s own "no run entry survived" sentinel, not a
       filler: every batch this file builds names proposals only. */
    runRev: -1,
    proposalRev: rev,
  };
}

/** Every card the link is marking, by the attribute the stylesheet keys on. */
function markedCards(): Element[] {
  return [...document.querySelectorAll('[data-linked-proposal="true"]')];
}

/** The deep-link notice's full text, or `null` if none is rendered. */
function noticeText(): string | null {
  const el = document.querySelector('.proposals-deep-link-notice');
  return el === null ? null : (el.textContent ?? '');
}

/** The sr-only status region — act confirmations, arrivals and this share it. */
function statusText(): string {
  return screen.getByRole('status').textContent ?? '';
}

/** Every proposals request the panel issued, in order, query string included. */
function listRequests(calls: string[]): string[] {
  return calls.filter((key) => key.startsWith(LIST));
}

// ---------------------------------------------------------------------------

describe('the parameter itself', () => {
  /*
   * PINNED HERE RATHER THAN TRUSTED, because every link this feature produces is
   * built from it — including one built in another language, which cannot import
   * the constant and can only copy the literal.
   */
  it('is `proposal`, and the helper mints a link that names the capture workspace', () => {
    expect(RECORD_PROPOSAL_PARAM).toBe('proposal');
    expect(ROUTES.recordProposal('REC1', 'P1')).toBe('/record/REC1?view=capture&proposal=P1');
  });

  it('encodes an id that would otherwise change the shape of the query string', () => {
    expect(ROUTES.recordProposal('REC1', 'a&b=c d')).toBe(
      '/record/REC1?view=capture&proposal=a%26b%3Dc%20d',
    );
  });
});

describe('a deep link that names a proposal IN the loaded window', () => {
  it('marks exactly that card and no other', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposalFixture(),
          proposalFixture({ proposal_id: LINKED, target_field_path: LINKED_PATH }),
        ]),
      },
    });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await screen.findByLabelText(`Proposal for ${LINKED_PATH} — Awaiting your judgement`);

    await waitFor(() => expect(markedCards()).toHaveLength(1));
    expect(markedCards()[0].getAttribute('aria-label')).toBe(
      `Proposal for ${LINKED_PATH} — Awaiting your judgement`,
    );
    /* The OTHER card must carry the attribute at all, not merely carry it as
       `"false"` — the stylesheet and this assertion both key on presence. */
    const other = screen.getByLabelText(`Proposal for ${OTHER_PATH} — Awaiting your judgement`);
    expect(other.hasAttribute('data-linked-proposal')).toBe(false);
  });

  it('moves focus onto that card, so its accessible name is what a reader lands on', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposalFixture(),
          proposalFixture({ proposal_id: LINKED, target_field_path: LINKED_PATH }),
        ]),
      },
    });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await screen.findByLabelText(`Proposal for ${LINKED_PATH} — Awaiting your judgement`);

    await waitFor(() =>
      expect(document.activeElement?.getAttribute('aria-label')).toBe(
        `Proposal for ${LINKED_PATH} — Awaiting your judgement`,
      ),
    );
  });

  it('announces WHICH FIELD the linked proposal is for, through the region the panel already owns', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ proposal_id: LINKED, target_field_path: LINKED_PATH })]),
      },
    });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await screen.findByText('Proposed value');

    await waitFor(() =>
      expect(statusText()).toContain(
        `The proposal this link names is shown below — ${LINKED_PATH}.`,
      ),
    );
    /*
     * ONE region for this fact, not a second one of its own.
     *
     * ASSERTED AS A DELTA, NOT AS A TOTAL, and the first version of this
     * assertion got that wrong — it required exactly two live regions and
     * measured three, because every `CurrentValue` on every card carries one of
     * its own. A fixed total is a claim about the whole panel and would have to
     * change whenever an unrelated card gained a region; the invariant this
     * slice actually owes is that rendering the notice adds NONE.
     */
    const withNotice = document.querySelectorAll('[aria-live]').length;
    const notice = document.querySelector('.proposals-deep-link-notice');
    expect(notice).not.toBeNull();
    expect(notice?.hasAttribute('aria-live')).toBe(false);
    expect(notice?.hasAttribute('role')).toBe(false);

    cleanup();
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ proposal_id: LINKED, target_field_path: LINKED_PATH })]),
      },
    });
    renderPanel('');
    await screen.findByText('Proposed value');
    expect(document.querySelector('.proposals-deep-link-notice')).toBeNull();
    expect(document.querySelectorAll('[aria-live]')).toHaveLength(withNotice);
  });

  it('explains the outline visibly, without repeating the announcement', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ proposal_id: LINKED, target_field_path: LINKED_PATH })]),
      },
    });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() => expect(noticeText()).not.toBeNull());

    expect(noticeText()).toContain('This link names the proposal outlined below.');
    /* The id is on the notice: it is the reader's only way to tell which link
       they followed, and this surface did not author it. */
    expect(document.querySelector('.proposals-deep-link-id')?.textContent).toBe(LINKED);
    /* No widening control — there is nothing to widen to. */
    expect(screen.queryByRole('button', { name: 'Show All, Newest First' })).toBeNull();
  });

  it('does NOT re-focus the card on a silent background reload', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return {
          body: page([proposalFixture({ proposal_id: LINKED, target_field_path: LINKED_PATH })]),
        };
      },
    });
    const view = renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`, null);
    await screen.findByLabelText(`Proposal for ${LINKED_PATH} — Awaiting your judgement`);
    await waitFor(() => expect(markedCards()).toHaveLength(1));

    /*
     * THE READER MOVES THEIR OWN FOCUS, and then a colleague's act arrives over
     * the change feed. The panel reloads SILENTLY and re-renders the same card,
     * with a fresh `proposal` object; an effect that re-ran on that would yank
     * the caret back, on a schedule the reader did not set.
     *
     * WHAT THIS PINS IS THE DEPENDENCY ARRAY, and that is a correction. The
     * panel's first version defended this with a ref latch and this test was
     * written for it — removing the latch left this test GREEN, i.e. it was an
     * equivalent mutant and the assertion was true by construction. The latch is
     * gone (see `ProposalCard`'s own note) and the RED proof for this test is now
     * a mutation of the real mechanism: widening the effect's dependencies to
     * `[linked, proposal]` makes it re-run on every silent reload, and this fails.
     */
    const filterControl = screen.getByLabelText('Show');
    filterControl.focus();
    expect(document.activeElement).toBe(filterControl);

    rerenderWith(view, `?${RECORD_PROPOSAL_PARAM}=${LINKED}`, activityFor([OTHER], 9));
    await waitFor(() => expect(reads).toBe(2));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(document.activeElement).toBe(filterControl);
    /* …and the mark is still there. The latch stops the FOCUS, never the mark. */
    expect(markedCards()).toHaveLength(1);
  });
});

describe('a deep link the loaded window does not contain', () => {
  /**
   * A window that is a SLICE: more pages behind it, and a record total larger than
   * the rows returned. Nothing here can support a claim about the whole record.
   */
  function sliceRoutes() {
    return stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture()], {
          total: 120,
          returned: 1,
          has_more: true,
          next_cursor: 'CURSOR_2',
        }),
      },
    });
  }

  it('marks no card at all', async () => {
    sliceRoutes();
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await screen.findByText('Proposed value');
    await waitFor(() => expect(noticeText()).not.toBeNull());

    expect(markedCards()).toHaveLength(0);
  });

  it('says it is not in THIS WINDOW, names the id, and hedges on why', async () => {
    sliceRoutes();
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() => expect(noticeText()).not.toBeNull());

    const text = noticeText() ?? '';
    expect(text).toContain('is not in the window shown here');
    expect(text).toContain('may be on another page');
    expect(text).toContain('or it may not be on this record at all');
    expect(text).toContain('cannot tell those apart, so it does not guess');
    /* The id is LABELLED, not dangling: an opaque token with nothing saying what
       it is tells the reader less than no token at all. */
    expect(text).toContain('Link target:');
    expect(document.querySelector('.proposals-deep-link-id')?.textContent).toBe(LINKED);
    /* Nothing was written, and the notice says so — following a link is a read. */
    expect(text).toContain('Nothing was changed by following the link.');
  });

  it('announces the same hedged fact once, and does not repeat it on a reload', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return {
          body: page([proposalFixture()], {
            total: 120,
            returned: 1,
            has_more: true,
            next_cursor: 'CURSOR_2',
          }),
        };
      },
    });
    const view = renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`, null);
    await waitFor(() => expect(statusText()).toContain('is not in the window shown here'));

    /*
     * `announce()` appends an alternating NO-BREAK SPACE so a byte-identical
     * sentence is still audible. So "not repeated" cannot be asserted by
     * comparing the region's text to itself — it is asserted by the region
     * holding the sentence exactly ONCE after a second read.
     */
    rerenderWith(view, `?${RECORD_PROPOSAL_PARAM}=${LINKED}`, activityFor([OTHER], 9));
    await waitFor(() => expect(reads).toBe(2));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    const occurrences = statusText().split('is not in the window shown here').length - 1;
    expect(occurrences).toBe(1);
  });

  /**
   * THE ONE STRUCTURAL GUARD IN THIS FILE, AND IT IS LABELLED AS ONE.
   *
   * It scans the rendered copy for every phrasing that would assert the proposal
   * does not exist. That is a string scan and it proves nothing about behaviour —
   * but the claim it protects is a COPY claim, and the established remedy here for
   * a copy claim is a polarity guard over every plausible rephrasing
   * (`upload-claim-parity.test.tsx`, whose own first widening caught 1 of 8).
   * Enumerated rather than keyword-blacklisted, so a one-word edit does not walk
   * through it.
   */
  it('STRUCTURAL · never asserts the proposal does not exist', async () => {
    sliceRoutes();
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() => expect(noticeText()).not.toBeNull());

    const text = (noticeText() ?? '').toLowerCase();
    const overclaims = [
      'no such proposal',
      'does not exist',
      'no longer exists',
      'was deleted',
      'has been deleted',
      'was removed',
      'is not on this record.',
      'this record does not hold',
      'not found',
      'unknown proposal',
      'could not be found',
      'is gone',
    ];
    for (const phrase of overclaims) {
      expect(text, `the hedged notice must not contain "${phrase}"`).not.toContain(phrase);
    }
  });

  it('offers the widening control, and it re-reads with order=newest_first, no state filter and no cursor', async () => {
    const calls = sliceRoutes();
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() => expect(noticeText()).not.toBeNull());

    expect(listRequests(calls)).toHaveLength(1);
    /* The default view is the SERVER's, so the first read carries no parameters
       at all — this is the baseline the click has to move. */
    expect(listRequests(calls)[0]).toBe(LIST);

    fireEvent.click(screen.getByRole('button', { name: 'Show All, Newest First' }));

    await waitFor(() => expect(listRequests(calls)).toHaveLength(2));
    const second = listRequests(calls)[1];
    expect(second).toContain('order=newest_first');
    expect(second).not.toContain('state=');
    expect(second).not.toContain('after=');
  });

  it('does NOT narrow to open — a link may name a proposal somebody has since rejected', async () => {
    const calls = stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ state: 'rejected' })], {
          total: 120,
          returned: 1,
          has_more: true,
          next_cursor: 'CURSOR_2',
        }),
      },
    });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() => expect(noticeText()).not.toBeNull());

    fireEvent.click(screen.getByRole('button', { name: 'Show All, Newest First' }));
    await waitFor(() => expect(listRequests(calls)).toHaveLength(2));

    /*
     * The arrival note's own control beside this one DOES set `state=open`, and
     * it is right to: it counts arrivals, which are `open` by construction. A
     * deep link is followed at an arbitrary later time, so narrowing to `open`
     * would hide exactly the case it was most likely followed for.
     */
    expect(listRequests(calls)[1]).not.toContain('state=open');
  });

  it('withholds the widening control when the view it would produce is already on screen', async () => {
    const calls = stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture()], {
          total: 120,
          returned: 1,
          has_more: true,
          next_cursor: 'CURSOR_2',
          order: 'newest_first',
        }),
      },
    });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() => expect(noticeText()).not.toBeNull());

    /* Ask for the view the control would produce, through the ordinary control. */
    fireEvent.change(screen.getByLabelText('Order'), { target: { value: 'newest_first' } });
    await waitFor(() => expect(listRequests(calls)).toHaveLength(2));

    /* A control that changes no state issues no read and therefore does nothing
       — it must not be offered as though it were an answer. */
    expect(screen.queryByRole('button', { name: 'Show All, Newest First' })).toBeNull();
    /* …and the hedged sentence is still there: nothing has become claimable. */
    expect(noticeText()).toContain('is not in the window shown here');
  });
});

describe('the one case where "this record does not hold it" is claimable', () => {
  it('says it when the window provably covers the whole record', async () => {
    stubFetchRoutes({
      /* No filter, no cursor, `has_more: false`, `returned === total`, and
         `unreadable_entries: 0` — every conjunct the panel requires. */
      [LIST]: { body: page([proposalFixture()]) },
    });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() => expect(noticeText()).not.toBeNull());

    const text = noticeText() ?? '';
    expect(text).toContain('This link names a proposal this record does not hold.');
    expect(text).toContain('the whole of this record’s proposal list');
    expect(text).toContain(LINKED);
    /* There is nothing to widen to, so nothing is offered. */
    expect(screen.queryByRole('button', { name: 'Show All, Newest First' })).toBeNull();
    expect(markedCards()).toHaveLength(0);
  });

  it('announces the stronger claim, not the hedged one', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() =>
      expect(statusText()).toContain('This link names a proposal this record does not hold.'),
    );
    expect(statusText()).not.toContain('is not in the window shown here');
  });

  it('RETREATS TO THE HEDGE when a stored entry could not be read', async () => {
    /*
     * THE CONJUNCT THAT IS EASY TO FORGET, AND THE REASON IT IS NOT OPTIONAL.
     * `total` is `len(exp.proposals)` — the proposals the server could PRESENT.
     * A stored entry this build refused, or one repeating an id another proposal
     * already holds, is preserved on the record and counted only in
     * `unreadable_entries`. So every other conjunct can hold while an entry
     * carrying the linked id sits on the record unshown.
     */
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()], { unreadable_entries: 1 }) } });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() => expect(noticeText()).not.toBeNull());

    expect(noticeText()).toContain('is not in the window shown here');
    expect(noticeText()).not.toContain('this record does not hold');
  });

  it('RETREATS TO THE HEDGE when a filter is narrowing the window', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() => expect(noticeText()).toContain('this record does not hold'));

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'accepted' } });

    await waitFor(() => expect(noticeText()).toContain('is not in the window shown here'));
    expect(noticeText()).not.toContain('this record does not hold');
    /* And the stronger claim having been made first does not suppress the
       hedge's own announcement — the verdict, not just the id, is what the
       announcer latches on. */
    expect(statusText()).toContain('is not in the window shown here');
  });

  it('RETREATS TO THE HEDGE when there is a further page', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture()], { has_more: true, next_cursor: 'CURSOR_2' }),
      },
    });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() => expect(noticeText()).not.toBeNull());

    expect(noticeText()).toContain('is not in the window shown here');
    expect(noticeText()).not.toContain('this record does not hold');
  });
});

describe('an absent or empty parameter degrades to "not focused", with no dead route', () => {
  it('renders no notice and marks no card when there is no parameter', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture(), proposalFixture({ proposal_id: LINKED })]) },
    });
    renderPanel('');
    await screen.findAllByText('Proposed value');

    expect(noticeText()).toBeNull();
    expect(markedCards()).toHaveLength(0);
    expect(statusText()).toBe('');
  });

  it('treats `?proposal=` with nothing after it as no parameter at all', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture(), proposalFixture({ proposal_id: LINKED })]) },
    });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=`);
    await screen.findAllByText('Proposed value');

    expect(noticeText()).toBeNull();
    expect(markedCards()).toHaveLength(0);
  });

  it('claims nothing before a window has ever loaded', async () => {
    /*
     * "Not in the window shown here" is a claim ABOUT A WINDOW. A first read that
     * failed has produced none, so the notice must be absent rather than
     * describing a window that does not exist — the panel's own `BackendDown`
     * says what happened.
     */
    stubFetchRoutes({ [LIST]: { status: 503, body: { error: 'unavailable' } } });
    renderPanel(`?${RECORD_PROPOSAL_PARAM}=${LINKED}`);
    await waitFor(() =>
      expect(document.querySelector('.proposals-deep-link-notice')).toBeNull(),
    );
    await screen.findByRole('button', { name: 'Retry' });

    expect(noticeText()).toBeNull();
    expect(markedCards()).toHaveLength(0);
  });
});

describe('the record screen resolves a bare ?proposal= to the workspace that can honour it', () => {
  /*
   * WHY THIS TEST IS AT THE SCREEN AND NOT THE PANEL. `IngestionProposalsPanel` is
   * mounted only on the `capture` workspace, so a URL carrying `?proposal=` and no
   * `?view=` would open Record Fields and the parameter would be silently inert —
   * a link that resolves to a page which cannot honour it. `ROUTES.recordProposal`
   * mints `view=capture` so new links are self-describing; `RecordWorkbench`
   * resolves a bare one for every link that helper did not mint, which is the case
   * an agent building a relative path in another language actually produces.
   */
  function renderAt(path: string) {
    stubFetchRoutes({
      ...bundleRoutes(EXP),
      [`GET /api/experiments/${EXP}/runs`]: {
        body: runsPage([runFixture({ id: 'RUNAAA', label: 'Run 1' })]),
      },
    } as never);
    return render(
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
  }

  it('opens Capture & Proposals, and the panel honours the id it was sent', async () => {
    renderAt(`/record/${EXP}?${RECORD_PROPOSAL_PARAM}=${LINKED}`);

    /* The panel is MOUNTED — which is the thing a bare `?proposal=` used not to
       achieve — and it has resolved the id against the window it was served. */
    await screen.findByRole('heading', { name: 'Ingestion Proposals' });
    await waitFor(() => expect(noticeText()).not.toBeNull());
    expect(noticeText()).toContain(LINKED);
  });

  it('a run address still wins, so no link that worked yesterday moves', async () => {
    renderAt(`/record/${EXP}?run=RUNAAA&${RECORD_PROPOSAL_PARAM}=${LINKED}`);

    /* `?run=` resolved to the Runs workspace before this parameter existed, and
       a URL carrying both must keep landing exactly where it landed. The
       proposal parameter is not lost — it survives on the address. */
    await screen.findByRole('heading', { name: 'Runs' });
    expect(screen.queryByRole('heading', { name: 'Ingestion Proposals' })).toBeNull();
  });

  it('no parameter still opens Record Fields', async () => {
    renderAt(`/record/${EXP}`);
    await screen.findByRole('link', { name: 'Record Fields' });
    expect(screen.queryByRole('heading', { name: 'Ingestion Proposals' })).toBeNull();
  });
});
