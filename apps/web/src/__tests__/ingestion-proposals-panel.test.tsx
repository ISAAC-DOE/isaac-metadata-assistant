/*
 * The Ingestion Proposals panel.
 *
 * WHAT WOULD FAIL BEFORE THE BEHAVIOUR THESE TESTS DEFEND. Each item is a way the
 * panel could be built that passes a naive "does it render" test and still breaks the
 * feature's promise, and each names the test that catches it:
 *
 *   1. A card that shows the PROPOSED value under a heading implying it is what the
 *      record holds. The proposals payload carries a DIGEST of the target and not its
 *      value, so a side-by-side drawn from that payload alone would be fabricated.
 *      (`the proposed value is never presented as what the record holds`,
 *       `the current value is a separate read, from the route that owns the target`)
 *   2. `target_stale: null` or `still_current: null` rendered as `false` — "we could
 *      not look" collapsed into "nothing changed", which is the comfortable one of the
 *      two and is wrong exactly when it matters.
 *      (`a null target_stale is not rendered as unchanged`,
 *       `a null still_current is not rendered as still current`)
 *   3. An Accept control on a proposal whose acceptance is structurally impossible —
 *      the contract's §6 rule, and the shape `_UNACCEPTABLE_READER_PATHS` refuses at
 *      import time. (`Accept is withheld …` ×3)
 *   4. Accept PRE-DISABLED on the strength of `human_actor_required`, which is a fact
 *      about a deployment's configuration and is not observable from this payload.
 *      The refusal is reported when it arrives, specifically, and never assumed.
 *      (`Accept is offered even though every default deployment refuses it`,
 *       `a human_actor_required refusal is reported as configuration, not as failure`)
 *   5. `accept` sending the candidate value back, or `edited` sending none — the two
 *      are different claims and the server refuses the first with
 *      `value_is_not_the_candidate`. (`accepting as proposed sends no value at all`,
 *       `accepting a correction sends the corrected value`)
 *   6. A refusal collapsed to "could not be recorded (409)". Four different conditions
 *      arrive as 409 with completely different remedies — one permanent for the
 *      deployment, one cleared by re-reading, one permanent for the proposal.
 *      (`each refusal keeps the server's own distinction`)
 *   7. A background change-feed update that refetches the list and takes a
 *      half-written corrected value with it. `CLAUDE.md` §11 records this repository
 *      shipping that defect three times.
 *      (`a change-feed proposal entry refreshes the list …`, and its NEGATIVE CONTROL)
 *   8. A write with no `If-Match`, or a DELETE anywhere.
 *      (`every review carries the record's version and confirmed_by_user`,
 *       `no request this panel makes is a DELETE`)
 *
 * ASSERTIONS ARE ON BEHAVIOUR, NOT ON THE PRESENCE OF A STRING. Where a claim is about
 * what was SENT, the parsed request body is asserted; where it is about what was NOT
 * claimed, the assertion is the absence of the specific wrong sentence beside the
 * presence of the right one, so a build that renders both does not pass.
 *
 * Every fixture is synthetic and no test here reaches a backend.
 */
import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import {
  IngestionProposalsPanel,
  acceptUnavailableReason,
} from '../components/IngestionProposalsPanel';
import {
  PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
  PROPOSAL_TARGET_PATHS,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { RecordChangeSummary } from '../lib/recordChanges';
import type { ApiProposal, ApiProposalsResponse } from '../lib/types';

const EXP = 'demo';
const LIST = `GET /api/experiments/${EXP}/proposals`;
const RUN_ONE = '01RUNAAAAAAAAAAAAAAAAAAAA0';

/*
 * THE TWO PATHS UNDER TEST, AND THE SERVED SETS THEY COME FROM — MEASURED.
 *
 * The first version of this file used `system.domain` as a second record-scoped path.
 * **The server serves it as neither**: `PROPOSAL_TARGET_PATHS` holds 18 paths,
 * `system.domain` is not one of them, and exactly ONE of the 18 is record-scoped. So
 * the "Accept is withheld at a record-scoped path" test was pinning behaviour against
 * a server shape that does not exist, under a comment claiming it was the server's.
 *
 * The lists are imported from `test/apiFixtures.ts` rather than restated, so there is
 * ONE transcription of the server's answer in this tree and not two — and that one
 * carries the command to re-derive it, because the set is DERIVED server-side and can
 * widen without anything here changing.
 */
const RUN_PATH = 'sample.material.name';
const RECORD_PATH = 'system.technique';
/** A path the server admits as a target, applied through a RUN's writer. */
const TARGET_PATHS = PROPOSAL_TARGET_PATHS;
/** The one record-scoped target. Asserted below, so a drift here is loud. */
const RECORD_SCOPED = PROPOSAL_RECORD_SCOPED_TARGET_PATHS;

afterEach(() => {
  vi.unstubAllGlobals();
});

function proposalFixture(over: Partial<ApiProposal> = {}): ApiProposal {
  return {
    proposal_id: 'P1',
    experiment_id: EXP,
    note_id: 'N1',
    run_id: RUN_ONE,
    target_field_path: RUN_PATH,
    proposed_value: 'CuO',
    rule: 'The line "sample: CuO" names the material after a colon.',
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
    excerpt: 'sample: CuO',
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

/** Every POST this panel made, with its parsed body and `If-Match`. */
function posts(): { url: string; body: Record<string, unknown>; ifMatch?: string }[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls
    .filter(([, init]) => init?.method === 'POST')
    .map(([url, init]) => ({
      url: String(url),
      body: JSON.parse(String(init?.body)) as Record<string, unknown>,
      ifMatch: (init?.headers as Record<string, string> | undefined)?.['If-Match'],
    }));
}

/** Every request method this panel issued, so a DELETE anywhere is visible. */
function methods(): string[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls.map(([, init]) => (init?.method ?? 'GET').toUpperCase());
}

/** Every URL requested, so a paging cursor is assertable. */
function urls(): string[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls.map(([url]) => String(url));
}

/**
 * A FEED SUMMARY NAMING PROPOSALS, AT A POSITION.
 *
 * `proposalRev` is the field the panel actually keys its refresh on, and it defaults
 * to `highestRev` here because in the shape these tests build — proposals and nothing
 * else — the two are equal by construction. They diverge only when a batch also
 * carries a run or the record's own entry at a HIGHER position, which is the case
 * `keys its refresh on the PROPOSAL position, not the batch's furthest reach` builds
 * explicitly by passing them apart.
 */
function activityFor(
  ids: string[],
  highestRev: number,
  proposalRev: number = highestRev,
): RecordChangeSummary {
  return {
    recordMoved: false,
    runIds: [],
    proposalIds: ids,
    proposalStates: [],
    otherKinds: [],
    highestRev,
    runRev: -1,
    proposalRev,
  };
}

// --- 1. the honest read states -------------------------------------------------

describe('the read states', () => {
  it('says no proposals exist yet and names how one is created — PR-D corrected this claim', async () => {
    /*
     * "Nothing in this build creates one" was TRUE when this test was written and is
     * FALSE now: finalizing a transcript capture (PR-A) and "Propose a value from
     * this note" (PR-D) both mint proposals, and an MCP agent may call
     * `isaac_propose_field_value`. The empty state is corrected to name all three
     * rather than assert none exist.
     */
    stubFetchRoutes({ [LIST]: { body: page([]) } });
    renderPanel();

    await screen.findByText(/No proposals yet\. Capture notes above/);
    expect(
      screen.getByText(/ask a colleague’s agent to propose a value/),
    ).toBeTruthy();
    expect(screen.getByText(/isaac_propose_field_value/)).toBeTruthy();
    // An empty record must NOT offer a "show all" escape hatch — nothing is filtered.
    expect(screen.queryByRole('button', { name: 'Show All Proposals' })).toBeNull();
  });

  it('discloses stored entries it could not read, in the count line and the empty state', async () => {
    stubFetchRoutes({ [LIST]: { body: page([], { unreadable_entries: 2 }) } });
    renderPanel();

    await screen.findByText(/No proposals yet\. Capture notes above/);
    // BOTH surfaces carry it: an empty state is where a reader stops looking, so it
    // cannot be the one place the number is left out.
    const disclosures = screen.getAllByText(
      /2 stored entries this version cannot show as proposals/,
    );
    expect(disclosures.length).toBeGreaterThanOrEqual(2);
    // And it names BOTH causes rather than asserting the one that is wrong half the time.
    expect(
      screen.getAllByText(/either unreadable, or repeating an id another proposal already holds/)
        .length,
    ).toBeGreaterThanOrEqual(1);
  });

  it('renders the API down state rather than an empty list when the read fails', async () => {
    stubFetchRoutes({ [LIST]: { status: 500, body: {} } });
    renderPanel();

    // The honest down state, not "no proposals on this record" — which would tell a
    // reader their record holds none when nothing was read at all.
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.queryByText(/No ingestion proposals on this record/)).toBeNull();
  });

  it('states the record total, not the window size, while showing one window', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()], { total: 61, returned: 1, has_more: true, next_cursor: 'P1' }) },
    });
    renderPanel();

    await screen.findByText(/Showing 1 of 61 proposals on this record/);
  });
});

// --- 2. paging -----------------------------------------------------------------

describe('paging over a bounded list', () => {
  it('walks forward with the server cursor and back again, and asks for nothing it invented', async () => {
    const first = page([proposalFixture({ proposal_id: 'P1' })], {
      total: 2,
      returned: 1,
      has_more: true,
      next_cursor: 'P1',
    });
    const second = page([proposalFixture({ proposal_id: 'P2' })], {
      total: 2,
      returned: 1,
      has_more: false,
      next_cursor: null,
    });
    stubFetchRoutes({
      [LIST]: { body: first },
      [`${LIST}?after=P1`]: { body: second },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Next Page' }));

    await waitFor(() =>
      expect(urls().some((u) => u.endsWith('/proposals?after=P1'))).toBe(true),
    );
    // The FIRST request carried no cursor at all — the client never invents one.
    expect(urls()[0].endsWith('/proposals')).toBe(true);

    fireEvent.click(await screen.findByRole('button', { name: 'Previous Page' }));
    await waitFor(() =>
      expect(urls().filter((u) => u.endsWith('/proposals')).length).toBeGreaterThan(1),
    );
  });

  it('offers no pager at all when the record fits in one window', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel();

    await screen.findByText(/Proposed value/);
    expect(screen.queryByRole('button', { name: 'Next Page' })).toBeNull();
  });
});

// --- 2b. which END of the list the window comes from ---------------------------
//
// THE GAP. `workspace.py::_sorted_proposals` orders `(proposed_utc, proposal_id)`
// oldest first and `routes.py::list_proposals` walks that order forward, so a freshly
// created proposal — carrying the LATEST `proposed_utc` on the record — sorts LAST.
// The panel's default view is the first window, so on a record already holding a full
// one the newest proposal is not on screen and no re-read puts it there.

describe('the order control', () => {
  it('is a labelled, keyboard-reachable control that defaults to the SERVER default and sends nothing', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel();

    await screen.findByText('Proposed value');
    const control = screen.getByLabelText('Order') as HTMLSelectElement;
    expect(control.tagName).toBe('SELECT');
    expect(control.value).toBe('oldest_first');
    // THE DEFAULT IS THE SERVER'S AND IS NOT RESTATED. A client that sent
    // `order=oldest_first` would be keeping a second copy of a default it does not own.
    expect(urls().every((u) => !u.includes('order='))).toBe(true);
  });

  it('changing it asks the server for the other direction, from the FIRST window', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel();

    await screen.findByText('Proposed value');
    fireEvent.change(screen.getByLabelText('Order'), { target: { value: 'newest_first' } });

    await waitFor(() =>
      expect(urls().some((u) => u.endsWith('/proposals?order=newest_first'))).toBe(true),
    );
    // NO CURSOR RIDES ALONG. A `next_cursor` belongs to the order it was issued
    // under and the server refuses one from the other direction
    // (`422 cursor_order_mismatch`), so carrying it would turn the next read into a
    // refusal — and the front of the other direction is what was asked for anyway.
    expect(urls().some((u) => u.includes('order=newest_first') && u.includes('after='))).toBe(
      false,
    );
  });

  it('drops a cursor already held rather than replaying it in the other order', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ proposal_id: 'P1' })], {
          total: 2,
          returned: 1,
          has_more: true,
          next_cursor: 'P1',
        }),
      },
      [`${LIST}?after=P1`]: {
        body: page([proposalFixture({ proposal_id: 'P2' })], { total: 2, returned: 1 }),
      },
      [`${LIST}?order=newest_first`]: {
        body: page([proposalFixture({ proposal_id: 'P2' })], {
          total: 2,
          returned: 1,
          order: 'newest_first',
        }),
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Next Page' }));
    await waitFor(() => expect(urls().some((u) => u.endsWith('?after=P1'))).toBe(true));

    fireEvent.change(screen.getByLabelText('Order'), { target: { value: 'newest_first' } });
    await waitFor(() =>
      expect(urls().some((u) => u.endsWith('/proposals?order=newest_first'))).toBe(true),
    );
    // The one request shape that would have been refused: the held cursor replayed.
    expect(urls().some((u) => u.includes('after=P1') && u.includes('order='))).toBe(false);
  });

  it('states the order in the COUNT LINE, in both directions, and raises no second live region', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()], { total: 61, returned: 1 }) },
      [`${LIST}?order=newest_first`]: {
        body: page([proposalFixture()], {
          total: 61,
          returned: 1,
          // THE STUB ANSWERS THE ORDER IT WAS ASKED FOR, exactly as the server
          // does. It has to: the count line is built from `loaded.order`, so a
          // fixture that echoed the default here would prove only that the panel
          // renders a constant.
          order: 'newest_first',
        }),
      },
    });
    renderPanel();

    // SAID IN BOTH DIRECTIONS, INCLUDING THE DEFAULT: a clause present only for the
    // non-default would make "oldest first" an inference from an absence.
    const line = await screen.findByText(/Showing 1 of 61 proposals on this record · oldest first/);
    expect(line.getAttribute('aria-live')).toBe('polite');

    fireEvent.change(screen.getByLabelText('Order'), { target: { value: 'newest_first' } });
    await screen.findByText(/Showing 1 of 61 proposals on this record · newest first/);

    // ONE live region for this fact, not two. `role="status"` here is the ACT
    // region and it must stay silent — the order changed nothing on the record.
    expect(screen.getByRole('status').textContent ?? '').toBe('');
  });

  /*
   * THE COUNT LINE DESCRIBES THE LOADED WINDOW, NEVER THE REQUEST.
   *
   * `shown` is response state and `loaded` falls back to the last SUCCESSFUL window,
   * so a clause built from request state describes a window the numbers beside it
   * are not from. `.proposals-count` is `aria-live`, which is what turns that from
   * cosmetic into an honesty defect: the one utterance a screen reader receives is
   * the one made while the claim is false, and there is no second utterance when it
   * becomes true because by then the text no longer changes.
   */
  it('an order change whose read FAILS leaves the line describing the last window that loaded', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()], { total: 61, returned: 1 }) },
      [`${LIST}?order=newest_first`]: { status: 503, body: {} },
    });
    renderPanel();

    await screen.findByText(/Showing 1 of 61 proposals on this record · oldest first/);
    fireEvent.change(screen.getByLabelText('Order'), { target: { value: 'newest_first' } });

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    // MUTANT: `orderClause(order)` — the line reads "· newest first" over zero
    // cards, and keeps reading it until Retry. Nothing was read in that direction,
    // so nothing may be described in it.
    expect(
      screen.getByText(/Showing 1 of 61 proposals on this record · oldest first/),
    ).toBeTruthy();
    expect(screen.queryByText(/newest first/)).toBeNull();
  });

  it('does not change the clause IN FLIGHT — it moves when the response lands, not when the control does', async () => {
    let release: (() => void) | null = null;
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()], { total: 61, returned: 1 }) },
      [`${LIST}?order=newest_first`]: async () => {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return {
          body: page([proposalFixture()], {
            total: 61,
            returned: 1,
            order: 'newest_first',
          }),
        };
      },
    });
    renderPanel();

    await screen.findByText(/· oldest first/);
    fireEvent.change(screen.getByLabelText('Order'), { target: { value: 'newest_first' } });
    await waitFor(() => expect(release).not.toBeNull());

    // The control already says `newest_first` and the rows on screen are still the
    // oldest-first ones. MUTANT: the line claims "newest first" over them here.
    expect((screen.getByLabelText('Order') as HTMLSelectElement).value).toBe('newest_first');
    expect(screen.getByText(/· oldest first/)).toBeTruthy();

    release!();
    await screen.findByText(/· newest first/);
  });

  it('does not blank the list, so an open editor survives the change', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`${LIST}?order=newest_first`]: {
        body: page([proposalFixture()], { order: 'newest_first' }),
      },
    });
    renderPanel();

    await screen.findByText('Proposed value');
    fireEvent.change(screen.getByLabelText('Order'), { target: { value: 'newest_first' } });
    // THE DEFECT THIS CATCHES is rule 5 in this component's header: a reload that
    // blanks the list unmounts every card and takes a half-written value with it.
    expect(screen.queryByText(/Loading this record’s ingestion proposals/)).toBeNull();
    expect(screen.getByText('Proposed value')).toBeTruthy();

    // Settle the read this change started, so the assertion above is about the
    // moment BEFORE it lands rather than about a request that never happened.
    await waitFor(() =>
      expect(urls().some((u) => u.endsWith('?order=newest_first'))).toBe(true),
    );
    expect(screen.getByText('Proposed value')).toBeTruthy();
  });
});

// --- 3. the proposal is never the record's value -------------------------------

describe('a proposal is never presented as the field value', () => {
  it('labels the proposed value as proposed and says it is not the value or evidence', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel();

    await screen.findByText('Proposed value');
    expect(
      screen.getByText(/It is not the field’s value and not evidence for it\./),
    ).toBeTruthy();
    // The DEFECT this catches: a heading that presents the suggestion as current.
    expect(screen.queryByText(/^Current value$/)).toBeNull();
    expect(screen.queryByText(/The record holds/)).toBeNull();
  });

  it('reads the current value from the RUN route for a run-scoped proposal, on demand', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`GET /api/experiments/${EXP}/runs/${RUN_ONE}`]: {
        body: {
          run: {
            id: RUN_ONE,
            experiment_id: EXP,
            label: 'Run 1',
            ordinal: 1,
            created_utc: '2026-09-01T09:00:00Z',
            updated_utc: '2026-09-01T09:00:00Z',
            rev: 2,
            version: '1.2',
            record_id: null,
            fields: { [RUN_PATH]: { value: 'Cu2O' } },
            inherited: {},
          },
        },
      },
    });
    renderPanel();

    await screen.findByText('Proposed value');
    // NOT read on mount: a panel whose ordinary state is empty must not issue N reads.
    expect(urls().some((u) => u.includes('/runs/'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Show What the Record Holds Now' }));

    await screen.findByText("This run's own value, read just now");
    expect(screen.getByText('Cu2O')).toBeTruthy();
    // The RECORD's draft was NOT read for a run-scoped target: it would report a value
    // this run may not have, which is a fabrication rather than an inaccuracy.
    expect(urls().some((u) => u.endsWith('/draft'))).toBe(false);
  });

  it('M6: a run override wins over the run\'s own field map, as the server resolves it', async () => {
    /*
     * `workspace.resolved_run_draft` composes a run in four layers and says the order
     * IS the rule: *"layer 2 is applied ON TOP of layer 1, so if a run's own draft
     * somehow carries an experiment-level field directly, the resolution wins"*. The
     * first version of this panel read `run.fields[path]` FIRST and reported it as
     * "this run's own value" without consulting `inherited` at all — so for a target
     * reachable as a `field:` override it displayed the LOSING value under a heading
     * claiming it was what the record holds.
     */
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`GET /api/experiments/${EXP}/runs/${RUN_ONE}`]: {
        body: {
          run: {
            id: RUN_ONE,
            experiment_id: EXP,
            label: 'Run 1',
            ordinal: 1,
            created_utc: '2026-09-01T09:00:00Z',
            updated_utc: '2026-09-01T09:00:00Z',
            rev: 2,
            version: '1.2',
            record_id: null,
            // BOTH are present, which is exactly the case the precedence decides.
            fields: { [RUN_PATH]: { value: 'the-losing-value' } },
            inherited: {
              [`field:${RUN_PATH}`]: {
                state: 'overridden',
                payload: { value: 'the-resolved-value' },
                inherited_payload: { value: 'the-record-value' },
                overridable: true,
              },
            },
          },
        },
      },
    });
    renderPanel();

    await screen.findByText('Proposed value');
    fireEvent.click(screen.getByRole('button', { name: 'Show What the Record Holds Now' }));

    await screen.findByText("This run's override of the record's value, read just now");
    expect(screen.getByText('the-resolved-value')).toBeTruthy();
    expect(screen.queryByText('the-losing-value')).toBeNull();
    expect(screen.queryByText("This run's own value, read just now")).toBeNull();
  });

  it('M6: the run\'s own field is reported only when the resolution carries nothing', async () => {
    // `resolved_run_draft` SKIPS a resolution whose `payload is None`, so this is the
    // one case in which the run's own map survives — and it must still be reported.
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`GET /api/experiments/${EXP}/runs/${RUN_ONE}`]: {
        body: {
          run: {
            id: RUN_ONE,
            experiment_id: EXP,
            label: 'Run 1',
            ordinal: 1,
            created_utc: '2026-09-01T09:00:00Z',
            updated_utc: '2026-09-01T09:00:00Z',
            rev: 2,
            version: '1.2',
            record_id: null,
            fields: { [RUN_PATH]: { value: 'Cu2O' } },
            inherited: {
              [`field:${RUN_PATH}`]: {
                state: 'absent',
                payload: null,
                inherited_payload: null,
                overridable: true,
              },
            },
          },
        },
      },
    });
    renderPanel();

    await screen.findByText('Proposed value');
    fireEvent.click(screen.getByRole('button', { name: 'Show What the Record Holds Now' }));

    await screen.findByText("This run's own value, read just now");
    expect(screen.getByText('Cu2O')).toBeTruthy();
  });

  it('reads the current value from the DRAFT route for a record-scoped proposal', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ run_id: null, target_field_path: RECORD_PATH })]),
      },
      [`GET /api/experiments/${EXP}/draft`]: {
        body: {
          groups: [
            {
              title: 'System',
              fields: [
                {
                  path: RECORD_PATH,
                  label: 'Technique',
                  value: 'xas_xanes',
                  status: 'verified',
                  evidence_count: 1,
                  source_types: [],
                  present: true,
                },
              ],
            },
          ],
          record_blocks: {},
        },
      },
    });
    renderPanel();

    await screen.findByText('Proposed value');
    fireEvent.click(screen.getByRole('button', { name: 'Show What the Record Holds Now' }));

    await screen.findByText("The record's own draft, read just now");
    expect(screen.getByText('xas_xanes')).toBeTruthy();
    expect(urls().some((u) => u.includes('/runs/'))).toBe(false);
  });

  it('says a skeleton row holds no value rather than showing its shape as a value', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ run_id: null, target_field_path: RECORD_PATH })]),
      },
      [`GET /api/experiments/${EXP}/draft`]: {
        body: {
          groups: [
            {
              title: 'System',
              fields: [
                {
                  path: RECORD_PATH,
                  label: 'Technique',
                  value: null,
                  status: 'missing',
                  evidence_count: 0,
                  source_types: [],
                  present: false,
                },
              ],
            },
          ],
          record_blocks: {},
        },
      },
    });
    renderPanel();

    await screen.findByText('Proposed value');
    fireEvent.click(screen.getByRole('button', { name: 'Show What the Record Holds Now' }));

    await screen.findByText('No value is stored at this field path.');
  });
});

// --- 4. null is not false ------------------------------------------------------

describe('the three-valued derived reads', () => {
  it('a null target_stale is not rendered as unchanged', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ target_stale: null, current_target_digest: null })]),
      },
    });
    renderPanel();

    await screen.findByText(/CANNOT BE ANSWERED: the run this proposal names is no longer/);
    // THE DEFECT: rendering `null` with the `false` sentence. Asserting the right
    // sentence alone would pass on a build that showed both.
    expect(screen.queryByText(/was unchanged since this proposal was made/)).toBeNull();
    expect(screen.queryByText(/had CHANGED since this proposal was made/)).toBeNull();
  });

  it('a true target_stale says accepting is refused while that is so', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture({ target_stale: true })]) } });
    renderPanel();

    await screen.findByText(/had CHANGED since this proposal was made/);
    expect(screen.queryByText(/was unchanged since this proposal was made/)).toBeNull();
  });

  it('a null still_current is not rendered as still current', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposalFixture({
            state: 'accepted',
            applied: true,
            accepted_value: 'CuO',
            accepted_from: 'candidate',
            applied_via: 'run_field',
            applied_run_id: RUN_ONE,
            applied_rev: 4,
            applied_target_digest: 'after-the-write',
            still_current: null,
            target_stale: null,
            current_target_digest: null,
          }),
        ]),
      },
    });
    renderPanel();

    await screen.findByText(
      /Whether the record still holds what this acceptance wrote CANNOT BE ANSWERED/,
    );
    expect(screen.queryByText(/the record still held what this acceptance wrote/)).toBeNull();
    expect(
      screen.queryByText(/NO LONGER held what this acceptance wrote/),
    ).toBeNull();
  });

  it('I3: a RECORD-scoped accepted proposal does not blame a run it never named', async () => {
    /*
     * `still_current: null` with `run_id: null` is reachable — `applied_target_digest`
     * is `str | None` on the model and `_current_target_digest` answers `null` whenever
     * the target could not be digested, not only when a run was removed. The first
     * version of `AcceptanceRecord` stated "the run it names is no longer on this
     * record" unconditionally, which asserts a run that may never have existed.
     * `TargetState` already branched correctly; the two renderers of one derived read
     * must not disagree about what `null` means.
     */
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposalFixture({
            run_id: null,
            target_field_path: RECORD_PATH,
            state: 'accepted',
            applied: true,
            accepted_value: 'xas_xanes',
            accepted_from: 'candidate',
            applied_via: 'record_enum_fields',
            applied_rev: 4,
            applied_target_digest: 'after-the-write',
            still_current: null,
            target_stale: null,
            current_target_digest: null,
          }),
        ]),
      },
    });
    renderPanel();

    await screen.findByText(
      /CANNOT BE ANSWERED: the content at its field path could not be read back/,
    );
    // THE DEFECT: naming a run on a proposal that names none.
    expect(
      screen.queryByText(/the run this proposal names is no longer on this record/i),
    ).toBeNull();
  });

  it('an accepted proposal still says it is not the field value', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposalFixture({
            state: 'accepted',
            applied: true,
            accepted_value: 'CuO',
            accepted_from: 'candidate',
            applied_via: 'run_field',
            applied_rev: 4,
            applied_target_digest: 'after-the-write',
            still_current: true,
          }),
        ]),
      },
    });
    renderPanel();

    // `is_field_value` is false for an ACCEPTED proposal too, and the card says so.
    await screen.findByText(/It is not the field’s value and not evidence for it\./);
    expect(screen.getByText('Value that was written')).toBeTruthy();
    expect(screen.getByText(/the record still held what this acceptance wrote/)).toBeTruthy();
  });

  it('names no actor when the accept was unattributed, and substitutes no placeholder', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposalFixture({
            state: 'accepted',
            applied: true,
            accepted_value: 'CuO',
            accepted_from: 'candidate',
            applied_via: 'run_field',
            applied_rev: 4,
            applied_target_digest: 'after-the-write',
            still_current: true,
            accepted_by: {
              subject: null,
              trust_basis: 'unattributed',
              attributed: false,
              at: '2026-09-01T11:00:00Z',
            },
          }),
        ]),
      },
    });
    renderPanel();

    await screen.findByText(/recorded without an attributed actor — no name is substituted/);
  });
});

// --- 5. the Accept control, and the two different rules about it ---------------

describe('when Accept is withheld, and when it is not', () => {
  it('Accept is withheld for a path outside the served target set, and the three refusing acts remain', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ target_field_path: 'timestamps.created_utc' })]),
      },
    });
    renderPanel();

    await screen.findByText(/No write operation in this build accepts a value at this field path/);
    expect(screen.queryByRole('button', { name: 'Accept as Proposed' })).toBeNull();
    // A proposal that cannot be applied must still be CLEARABLE — gating the three
    // refusing acts would leave the queue permanently stuck. Supersede and Withdraw
    // sit behind "More Actions" (P2 resolution); Reject stays top-level.
    expect(screen.getByRole('button', { name: 'Reject…' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'More Actions' }));
    expect(screen.getByRole('button', { name: 'Withdraw…' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Supersede…' })).toBeTruthy();
    // And the refusal is about THIS BUILD, never about the official schema.
    expect(
      screen.getByText(/NOT a statement about the official ISAAC schema/),
    ).toBeTruthy();
  });

  it('Accept is withheld when the proposal names a run at a record-scoped path', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ target_field_path: RECORD_PATH, run_id: RUN_ONE })]),
      },
    });
    renderPanel();

    await screen.findByText(/written on the RECORD, and this proposal names a run/);
    expect(screen.queryByRole('button', { name: 'Accept as Proposed' })).toBeNull();
    // DEC-9, pinned in all three withheld cases rather than only the first: gating the
    // refusing acts on the same condition would leave the queue permanently
    // unclearable, which is the exact defect `conflict_resolution.py` was built to fix.
    expect(screen.getByRole('button', { name: 'Reject…' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'More Actions' }));
    expect(screen.getByRole('button', { name: 'Supersede…' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Withdraw…' })).toBeTruthy();
  });

  it('the served sets these tests run against are the ones the server actually serves', () => {
    /*
     * I1 — THE FIXTURE ITSELF, PINNED. The first version of this file used
     * `system.domain` as a second record-scoped path; the server serves it as NEITHER a
     * target nor a record-scoped one. Every "Accept is withheld" test above is only as
     * good as the sets it runs against, so the sets get their own assertions — and the
     * shared fixture carries the command to re-derive them, because the server DERIVES
     * this set and it widens on its own.
     */
    expect(TARGET_PATHS).toHaveLength(18);
    expect(RECORD_SCOPED).toEqual(['system.technique']);
    expect(TARGET_PATHS).not.toContain('system.domain');
    // The two paths these tests pick out, and the scope split they depend on.
    expect(TARGET_PATHS).toContain(RUN_PATH);
    expect(RECORD_SCOPED).not.toContain(RUN_PATH);
    expect(TARGET_PATHS).toContain(RECORD_PATH);
    expect(RECORD_SCOPED).toContain(RECORD_PATH);
    // And the path the "no write route" test uses really is outside the served set.
    expect(TARGET_PATHS).not.toContain('timestamps.created_utc');
  });

  it('Accept is withheld when the run this proposal names has been removed', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposalFixture({ current_target_digest: null, target_stale: null })]),
      },
    });
    renderPanel();

    // THE REASON IS HEDGED, NOT ASSERTED. `_current_target_digest` answers `null` for
    // three reasons and only one of them is the removed run, so the copy names it as
    // the reachable cause. Withholding Accept is right in all three.
    await screen.findByText(
      /current content at this proposal’s target could not be read, so accepting it is withheld/,
    );
    expect(screen.getByText(/the reachable cause is that the run is no longer on this record/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Accept as Proposed' })).toBeNull();
    // DEC-9: a proposal that cannot be applied must still be CLEARABLE.
    expect(screen.getByRole('button', { name: 'Reject…' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'More Actions' }));
    expect(screen.getByRole('button', { name: 'Withdraw…' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Supersede…' })).toBeTruthy();
  });

  it('Accept IS offered on an ordinary open proposal, even though every default deployment refuses it', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel();

    // `human_actor_required` is a fact about CONFIGURATION, not about the build, and it
    // is not observable from this payload. Pre-disabling would assert knowledge of the
    // deployment this surface does not have — the over-claim `identity.py` withdrew.
    const accept = await screen.findByRole('button', { name: 'Accept as Proposed' });
    expect((accept as HTMLButtonElement).disabled).toBe(false);
  });

  it('offers only the review acts the SERVER reported', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()], { review_actions: ['reject'] }) },
    });
    renderPanel();

    await screen.findByRole('button', { name: 'Reject…' });
    expect(screen.queryByRole('button', { name: 'Accept as Proposed' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Withdraw…' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Supersede…' })).toBeNull();
  });

  it('offers no plain Accept when the server does not report `candidate`', async () => {
    /*
     * M2 — THE OTHER HALF OF THE GATE, AND IT WAS UNPINNED. Mutating
     * `acceptedFromValues.includes('candidate')` to `true` SURVIVED all 47 tests: only
     * the `edited` half was checked, and it was checked through a conjunction that
     * already required `candidate`. A server that serves `['edited']` is saying the
     * proposed value must be corrected before it is written, and offering "Accept as
     * Proposed" against that would send an `accepted_from` it does not accept.
     */
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()], { accepted_from_values: ['edited'] }) },
    });
    renderPanel();

    // The correction path IS offered — the two halves are independent, and a server
    // that offers only `edited` must not lose its accept control entirely. It sits
    // behind "More Actions" now (P2 resolution).
    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    await screen.findByRole('button', { name: 'Correct the Value, Then Accept' });
    expect(screen.queryByRole('button', { name: 'Accept as Proposed' })).toBeNull();
  });

  it('offers no correction path when the server does not report `edited`', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()], { accepted_from_values: ['candidate'] }) },
    });
    renderPanel();

    await screen.findByRole('button', { name: 'Accept as Proposed' });
    expect(screen.queryByRole('button', { name: 'Correct the Value, Then Accept' })).toBeNull();
  });

  it('the availability rule is fail-OPEN when the server reported no target set', () => {
    // A set we did not receive is not evidence of a limitation. Withholding a control
    // on the strength of one would be the same over-claim in the other direction.
    expect(acceptUnavailableReason(proposalFixture(), {})).toBeNull();
    expect(
      acceptUnavailableReason(proposalFixture(), { targetFieldPaths: [] }),
    ).toBeNull();
  });
});

// --- 6. what each act actually sends -------------------------------------------

describe('the review write', () => {
  function reviewedBody(over: Partial<ApiProposal> = {}) {
    return { proposal: proposalFixture(over), experiment_version: '1.8' };
  }

  it('accepting as proposed sends accepted_from candidate and NO value at all', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: {
        body: reviewedBody({ state: 'accepted' }),
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Accept as Proposed' }));
    await waitFor(() => expect(posts().length).toBe(1));

    const [sent] = posts();
    expect(sent.body.action).toBe('accept');
    expect(sent.body.accepted_from).toBe('candidate');
    // THE DEFECT: echoing the candidate back. The server refuses a `value` that differs
    // (`value_is_not_the_candidate`), and re-sending one this client has no reason to
    // re-send is how that refusal is manufactured.
    expect('value' in sent.body).toBe(false);
    expect('reason' in sent.body).toBe(false);
    /*
     * MEASURED, AND THE FIRST TWO MUTATIONS SURVIVED — recorded because the reason is
     * the interesting part and a future reader would otherwise re-derive it.
     *
     *  (1) `api.reviewProposal` unconditionally `body.value = opts.value`: SURVIVED.
     *      `opts.value` is `undefined` on this path and `JSON.stringify` OMITS an
     *      `undefined` property, so the request is byte-identical. An equivalent
     *      mutant, not a hole.
     *  (2) the caller passing `{ acceptedFrom: 'candidate', value: proposal.proposed_value }`:
     *      SURVIVED — the api layer's `if (acceptedFrom === 'edited')` drops it.
     *  (3) BOTH mutated together: CAUGHT here (`expected true to be false`).
     *
     * So the two are defence in depth and each alone neutralises the other; only the
     * pair changes the wire, and the pair is what this assertion catches.
     */
  });

  it('accepting a correction sends accepted_from edited WITH the corrected value', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: {
        body: reviewedBody({ state: 'accepted' }),
      },
    });
    renderPanel();

    // Behind "More Actions" now (P2 resolution) — opened before it is queried.
    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Correct the Value, Then Accept' }),
    );
    const box = screen.getByLabelText('The corrected value, as JSON') as HTMLTextAreaElement;
    // Prefilled with the candidate as JSON, so the type is never guessed.
    expect(box.value).toBe('"CuO"');
    fireEvent.change(box, { target: { value: '"Cu2O"' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));

    await waitFor(() => expect(posts().length).toBe(1));
    const [sent] = posts();
    expect(sent.body.accepted_from).toBe('edited');
    expect(sent.body.value).toBe('Cu2O');
  });

  it('refuses to send an unparseable correction, and says nothing was written', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel();

    // Behind "More Actions" now (P2 resolution) — opened before it is queried.
    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Correct the Value, Then Accept' }),
    );
    fireEvent.change(screen.getByLabelText('The corrected value, as JSON'), {
      target: { value: 'Cu2O' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));

    await screen.findByText(/That is not valid JSON, so it was not sent/);
    // The request was never made — this is a client-side refusal, not a server one.
    expect(posts().length).toBe(0);
  });

  it('refuses to send a null correction, because a null would clear the field', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel();

    // Behind "More Actions" now (P2 resolution) — opened before it is queried.
    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Correct the Value, Then Accept' }),
    );
    fireEvent.change(screen.getByLabelText('The corrected value, as JSON'), {
      target: { value: 'null' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));

    await screen.findByText(/A null would CLEAR the field/);
    expect(posts().length).toBe(0);
  });

  it('rejects WITHOUT a reason when none was written, and never composes one', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: {
        body: reviewedBody({ state: 'rejected' }),
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Reject…' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Reject' }));

    await waitFor(() => expect(posts().length).toBe(1));
    expect(posts()[0].body.action).toBe('reject');
    // A justification nobody wrote is not invented on their behalf, and `""` would be
    // refused by the server rather than stored as an empty one.
    expect('reason' in posts()[0].body).toBe(false);
  });

  it('rejects WITH the reason when one was written', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: {
        body: reviewedBody({ state: 'rejected' }),
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Reject…' }));
    fireEvent.change(screen.getByLabelText('Reason (optional)'), {
      target: { value: 'the sheet says Cu2O' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Reject' }));

    await waitFor(() => expect(posts().length).toBe(1));
    expect(posts()[0].body.reason).toBe('the sheet says Cu2O');
  });

  it("every review carries the record's version and confirmed_by_user", async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: {
        body: reviewedBody({ state: 'withdrawn' }),
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    fireEvent.click(screen.getByRole('button', { name: 'Withdraw…' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Withdraw' }));

    await waitFor(() => expect(posts().length).toBe(1));
    expect(posts()[0].ifMatch).toBe('"1.7"');
    expect(posts()[0].body.confirmed_by_user).toBe(true);
  });

  it('no request this panel makes is a DELETE', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: {
        body: reviewedBody({ state: 'rejected' }),
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Reject…' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Reject' }));
    await waitFor(() => expect(posts().length).toBe(1));

    expect(methods()).not.toContain('DELETE');
  });
});

// --- 7. every refusal keeps the server's own distinction ------------------------

describe('each refusal keeps the server\'s own distinction', () => {
  async function refuse(status: number, body: unknown) {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: { status, body },
    });
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Accept as Proposed' }));
    return screen.findByRole('alert');
  }

  it('a human_actor_required refusal is reported as configuration, not as failure', async () => {
    const alert = await refuse(409, { error: 'human_actor_required', message: 'no actor' });

    expect(alert.textContent).toMatch(/NOTHING WAS WRITTEN/);
    expect(alert.textContent).toMatch(
      /fact about how this deployment is configured, not a fault in this record/,
    );
    // It must say the retry cannot work — reporting a permanent condition as transient
    // is the loop `CLAUDE.md` §11 records the reset paying for.
    expect(alert.textContent).toMatch(/retrying will not change it/);
    // And it must not leave a success claim anywhere on the card.
    expect(screen.queryByText('Value that was written')).toBeNull();
  });

  it('a proposal_stale 409 is not the same sentence as a stale If-Match 412', async () => {
    const alert = await refuse(409, { error: 'proposal_stale', message: 'moved' });

    expect(alert.textContent).toMatch(/has changed since this proposal was made/);
    expect(alert.textContent).toMatch(/withdraw it, supersede it, or make a new one/);
    // THE DEFECT: reporting a target that moved as a record-version conflict, whose
    // remedy ("this section has picked up the current version, try again") is false here.
    expect(alert.textContent).not.toMatch(/picked up the current version/);
  });

  it('a target_run_removed 409 says it is never re-aimed at another run', async () => {
    const alert = await refuse(409, { error: 'target_run_removed', run_id: RUN_ONE });
    expect(alert.textContent).toMatch(/not re-aimed at another run/);
  });

  it('a proposal_not_open 422 says the recorded judgement stands', async () => {
    const alert = await refuse(422, { error: 'proposal_not_open', state: 'rejected' });
    expect(alert.textContent).toMatch(/already been reviewed/);
    expect(alert.textContent).toMatch(/a later view is a new proposal/);
  });

  it('a not_an_allowed_value 422 quotes the schema\'s own list', async () => {
    const alert = await refuse(422, {
      error: 'not_an_allowed_value',
      allowed: ['xas_xanes', 'xas_exafs'],
    });
    expect(alert.textContent).toMatch(/xas_xanes, xas_exafs/);
  });

  it('a 412 is recognised as a stale validator and the next attempt is not refused again', async () => {
    let attempts = 0;
    let reads = 0;
    stubFetchRoutes({
      // The refusal is followed by a SILENT re-read, and the server's list read is the
      // freshest statement of the record's version — so the sequence a real deployment
      // produces is 1.7, refusal, 2.4.
      [LIST]: () => {
        reads += 1;
        return { body: page([proposalFixture()], { experiment_version: reads === 1 ? '1.7' : '2.4' }) };
      },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: () => {
        attempts += 1;
        return attempts === 1
          ? { status: 412, body: { error: 'stale_write', current_version: '2.4' } }
          : { body: { proposal: proposalFixture({ state: 'withdrawn' }), experiment_version: '2.5' } };
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    fireEvent.click(screen.getByRole('button', { name: 'Withdraw…' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Withdraw' }));

    // THE COPY IS THE BEHAVIOUR ASSERTION: this sentence is reachable ONLY through
    // `staleWriteCurrentVersion`, i.e. only when the 412's `current_version` was read.
    // A build that ignored the body would fall through to the generic refusal copy.
    await screen.findByText(/picked up the current version and what you typed is still here/);
    expect(posts()[0].ifMatch).toBe('"1.7"');
    // And the refusal is NOT reported as one of the four 409s, whose remedies differ.
    expect(screen.getByRole('alert').textContent).not.toMatch(/deployment is configured/);

    // THE DEAD END THIS CLOSES: without picking the current version back up, the next
    // attempt re-sends the stale validator and is refused again, forever.
    await waitFor(() => expect(reads).toBe(2));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Withdraw' }));
    await waitFor(() => expect(posts().length).toBe(2));
    expect(posts()[1].ifMatch).toBe('"2.4"');
  });

  /*
   * I2 — THE 412 PATH'S OWN PROMISE, AND WHY A NAIVE TEST OF IT IS VACUOUS.
   *
   * `STALE_REVIEW_COPY` tells the reader, in so many words, that "what you typed is
   * still here". Nothing checked it: the refusal test above uses a 409, which never
   * reloads at all, and the 412 test asserts only that the sentence appears. Mutating
   * `recoverFromStale`'s `reload(true)` to `reload(false)` — which blanks the list,
   * unmounts every card and destroys exactly what the sentence promises survives —
   * PASSED ALL 47 TESTS.
   *
   * AND THE OBVIOUS TEST STILL PASSES AGAINST THAT MUTANT. `stubFetchRoutes` resolves
   * a route in a microtask, so `setList({status:'loading'})` and the `setList` that
   * replaces it land in one React batch: the loading state is never committed, the
   * card is never unmounted, and its state survives a reload that would have destroyed
   * it in a browser. The blanking is real and the test cannot see it.
   *
   * SO THE SECOND READ IS DELAYED. With a real gap between the two commits React
   * flushes the loading state, `LoadingPanel` replaces the list, and the difference
   * between a silent refresh and a blanking one becomes observable — which is the only
   * condition under which this assertion means anything. Measured: this test FAILS
   * against the mutation and passes without it.
   */
  it('I2: a 412 refresh keeps the in-progress correction — with a delayed second read', async () => {
    let reads = 0;
    let attempts = 0;
    stubFetchRoutes({
      [LIST]: async () => {
        reads += 1;
        // THE DELAY IS THE TEST. Without it the loading commit is coalesced away and a
        // blanking reload is indistinguishable from a silent one.
        if (reads > 1) await new Promise((resolve) => setTimeout(resolve, 25));
        return { body: page([proposalFixture()], { experiment_version: reads === 1 ? '1.7' : '2.4' }) };
      },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: () => {
        attempts += 1;
        return attempts === 1
          ? { status: 412, body: { error: 'stale_write', current_version: '2.4' } }
          : { body: { proposal: proposalFixture({ state: 'accepted' }), experiment_version: '2.5' } };
      },
    });
    renderPanel();

    // Behind "More Actions" now (P2 resolution) — opened before it is queried.
    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Correct the Value, Then Accept' }),
    );
    fireEvent.change(screen.getByLabelText('The corrected value, as JSON'), {
      target: { value: '"Cu2O-corrected-by-a-scientist"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));

    await screen.findByText(/picked up the current version and what you typed is still here/);
    // Wait for the DELAYED reload to have both started and finished, so the assertion
    // below is made after every commit the refresh produces — not before them.
    await waitFor(() => expect(reads).toBe(2));
    await waitFor(() => expect(screen.getByLabelText('Show')).toBeTruthy());

    // THE PROMISE, ASSERTED AS THE LIVE VALUE OF THE REAL TEXTAREA.
    expect(
      (screen.getByLabelText('The corrected value, as JSON') as HTMLTextAreaElement).value,
    ).toBe('"Cu2O-corrected-by-a-scientist"');
  });

  it('a refusal does not close the editor or discard what was typed', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()]) },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: {
        status: 409,
        body: { error: 'human_actor_required' },
      },
    });
    renderPanel();

    // Behind "More Actions" now (P2 resolution) — opened before it is queried.
    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Correct the Value, Then Accept' }),
    );
    fireEvent.change(screen.getByLabelText('The corrected value, as JSON'), {
      target: { value: '"Cu2O"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));
    await screen.findByRole('alert');

    // The proposal surviving is not the promise; what they typed surviving is.
    expect(
      (screen.getByLabelText('The corrected value, as JSON') as HTMLTextAreaElement).value,
    ).toBe('"Cu2O"');
  });
});

// --- 8. a closed proposal --------------------------------------------------------

describe('a closed proposal', () => {
  it('is still listed, offers no review act, and shows its history', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposalFixture({
            state: 'rejected',
            history: [
              ...proposalFixture().history,
              {
                action: 'reject',
                at: '2026-09-01T12:00:00Z',
                from_state: 'open',
                to_state: 'rejected',
                actor_trust_basis: 'unattributed',
                actor_subject: null,
                accepted_value: null,
                accepted_from: null,
                reason: 'the sheet says Cu2O',
              },
            ],
          }),
        ]),
      },
    });
    renderPanel();

    await screen.findByText('Rejected — kept on the record');
    expect(screen.queryByRole('button', { name: 'Reject…' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Accept as Proposed' })).toBeNull();

    // The history is COLLAPSED until asked for, and both acts are in it once opened —
    // a history that dropped the opening `propose` would read as starting at the
    // refusal, which is exactly the record it exists to keep complete.
    expect(screen.queryByText(/reason: the sheet says Cu2O/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Show history \(2 acts\)/ }));
    expect(screen.getByText('propose')).toBeTruthy();
    expect(screen.getByText('reject')).toBeTruthy();
    // The reason a person gave is in the history, verbatim.
    expect(screen.getByText(/reason: the sheet says Cu2O/)).toBeTruthy();
  });

  it('never presents a closed state as a deletion', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture({ state: 'withdrawn' })]) },
    });
    renderPanel();

    await screen.findByText('Withdrawn — kept on the record');
    // The proposal's own content is still on screen. A card that hid it would be
    // presenting a state as a removal, which is the one thing none of these states is.
    expect(screen.getByText('Proposed value')).toBeTruthy();
    expect(screen.getByText('CuO')).toBeTruthy();
  });
});

// --- 9. the change feed, and the input it must not destroy ----------------------

describe('a background change-feed update', () => {
  it('refreshes the list, updates it visibly, and does NOT destroy an in-progress edit', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return {
          body:
            reads === 1
              ? page([proposalFixture()], { total: 1 })
              : page([proposalFixture()], { total: 4 }),
        };
      },
    });
    const view = renderPanel(null);

    // Behind "More Actions" now (P2 resolution) — opened before it is queried.
    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Correct the Value, Then Accept' }),
    );
    fireEvent.change(screen.getByLabelText('The corrected value, as JSON'), {
      target: { value: '"half-typed-by-a-scien' },
    });
    await screen.findByText(/Showing 1 of 1 proposal on this record/);

    // A `proposal` feed entry arrives. It carries ids and states only — no content —
    // so the only honest response is to re-read the list.
    view.rerender(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <IngestionProposalsPanel experimentId={EXP} activity={activityFor(['P1'], 9)} />
      </MemoryRouter>,
    );

    // VISIBLY UPDATED: the count line moves to what the second read reported.
    await screen.findByText(/Showing 1 of 4 proposals on this record/);
    expect(reads).toBe(2);

    // AND THE LIVE VALUE OF THE REAL TEXTAREA IS UNTOUCHED. Not a class name, not a
    // banner's presence, not a mock's call count.
    expect(
      (screen.getByLabelText('The corrected value, as JSON') as HTMLTextAreaElement).value,
    ).toBe('"half-typed-by-a-scien');
  });

  it('raises no notice of its own — the record activity note already carries that fact', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    view.rerender(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <IngestionProposalsPanel experimentId={EXP} activity={activityFor(['P1'], 9)} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(urls().length).toBeGreaterThan(1));
    // Two notices for one fact is the defect; this panel refreshes silently.
    expect(screen.queryByRole('alert')).toBeNull();
    const status = screen.getByRole('status');
    expect(status.textContent).toBe('');
  });

  it('does not re-read when the same batch is reported twice', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return { body: page([proposalFixture()]) };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');
    expect(reads).toBe(1);

    const same = activityFor(['P1'], 9);
    for (const activity of [same, { ...same }]) {
      view.rerender(
        <MemoryRouter
          initialEntries={['/']}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <IngestionProposalsPanel experimentId={EXP} activity={activity} />
        </MemoryRouter>,
      );
    }

    // A duplicated batch (the same ids at the same position) is not news, so it must
    // not produce a second read — and it must certainly not produce a second notice.
    await waitFor(() => expect(reads).toBe(2));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(reads).toBe(2);
  });

  it('re-reads when the SAME proposal moves again at a later position', async () => {
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return { body: page([proposalFixture()]) };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');

    for (const rev of [9, 11]) {
      view.rerender(
        <MemoryRouter
          initialEntries={['/']}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <IngestionProposalsPanel experimentId={EXP} activity={activityFor(['P1'], rev)} />
        </MemoryRouter>,
      );
    }

    // Created then reviewed is ONE id at TWO positions. Keying on the ids alone would
    // leave the second move unread.
    await waitFor(() => expect(reads).toBe(3));
  });

  it('keys its refresh on the PROPOSAL position, not the batch\'s furthest reach', async () => {
    /*
     * THE PAGE-BOUNDARY CASE, ASSERTED AS A COUNTED REQUEST.
     *
     * The key used to be `highestRev` — how far the whole batch reached — and that is
     * wrong in the direction that LOSES a change. The feed is ordered
     * `(changed_at_rev, kind, entity_id)` and a page boundary may fall anywhere, so one
     * page can end `[proposal@4, experiment@9]` and the next begin `[proposal@9]`
     * (`'experiment' < 'proposal'` decides the tie at rev 9). Under `highestRev` both
     * batches key `9:P1`, the key does not change, and P1's SECOND move is never read.
     *
     * The two batches below are exactly that: the same `highestRev`, different
     * `proposalRev`. The assertion is the number of `GET .../proposals` the panel
     * issued — not that a card appeared, which a stale list would also produce.
     */
    let reads = 0;
    stubFetchRoutes({
      [LIST]: () => {
        reads += 1;
        return { body: page([proposalFixture()]) };
      },
    });
    const view = renderPanel(null);
    await screen.findByText('Proposed value');
    expect(reads).toBe(1);

    for (const proposalRev of [4, 9]) {
      view.rerender(
        <MemoryRouter
          initialEntries={['/']}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <IngestionProposalsPanel
            experimentId={EXP}
            activity={activityFor(['P1'], 9, proposalRev)}
          />
        </MemoryRouter>,
      );
    }

    await waitFor(() => expect(reads).toBe(3));
  });

  /*
   * THE NEGATIVE CONTROL, and it is part of the guarantee rather than decoration.
   *
   * Without it a passing suite cannot distinguish "the input is protected" from "the
   * refresh never happened", and the second reads identically to the first. The only
   * way a test can destroy state owned by the card from outside is to unmount it — a
   * blanking (non-silent) reload would do exactly that to every card in the list — so
   * the control performs that unmount and proves the assertion above FAILS against it.
   */
  it('NEGATIVE CONTROL: the same assertion fails when the card is unmounted', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    const view = renderPanel(null);

    // Behind "More Actions" now (P2 resolution) — opened before it is queried.
    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Correct the Value, Then Accept' }),
    );
    fireEvent.change(screen.getByLabelText('The corrected value, as JSON'), {
      target: { value: '"half-typed-by-a-scien' },
    });

    view.unmount();
    renderPanel(null);
    await screen.findByText('Proposed value');

    // The editor is not even open, let alone holding what was typed. This is what the
    // positive test above would look like on a build that blanked the list to refresh.
    expect(screen.queryByLabelText('The corrected value, as JSON')).toBeNull();
  });
});

// --- 9b. the live region, and the paging control that must not reset a filter ----

describe('the act announcement', () => {
  it('M4: two consecutive acts are each announced, even when the sentence repeats', async () => {
    /*
     * A `role="status"` region announces a CHANGE to its content. Withdrawing two
     * proposals AT THE SAME FIELD PATH produces a byte-identical sentence, React
     * mutates no text node, and the second act is announced to nobody — the reader who
     * most depends on the confirmation gets it once and then silence.
     *
     * ASSERTED AS AN INEQUALITY BETWEEN TWO OBSERVED CONTENTS, not as the presence of a
     * marker character: what matters is that the region's content CHANGED, and any
     * mechanism that achieves it passes.
     */
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposalFixture({ proposal_id: 'P1' }),
          proposalFixture({ proposal_id: 'P2' }),
        ]),
      },
      [`POST /api/experiments/${EXP}/proposals/P1/review`]: {
        body: { proposal: proposalFixture({ proposal_id: 'P1' }), experiment_version: '1.8' },
      },
      [`POST /api/experiments/${EXP}/proposals/P2/review`]: {
        body: { proposal: proposalFixture({ proposal_id: 'P2' }), experiment_version: '1.9' },
      },
    });
    renderPanel();

    // Each card carries its own "More Actions" disclosure — both are opened
    // before either card's Withdraw is reachable.
    for (const toggle of await screen.findAllByRole('button', { name: 'More Actions' })) {
      fireEvent.click(toggle);
    }
    const withdrawFirst = screen.getAllByRole('button', { name: 'Withdraw…' })[0];
    fireEvent.click(withdrawFirst);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Withdraw' }));
    await waitFor(() => expect(screen.getByRole('status').textContent).not.toBe(''));
    const first = screen.getByRole('status').textContent;

    const withdrawSecond = screen.getAllByRole('button', { name: 'Withdraw…' })[1];
    fireEvent.click(withdrawSecond);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Withdraw' }));
    await waitFor(() => expect(posts().length).toBe(2));

    await waitFor(() =>
      expect(screen.getByRole('status').textContent).not.toBe(first),
    );
    // Both sentences still say the same true thing — nothing was renamed to force a
    // difference, and neither carries a spoken counter.
    expect(screen.getByRole('status').textContent).toMatch(/was withdrawn and kept on the record/);
  });
});

describe('the empty window', () => {
  it('M5: Back to the First Page rewinds the window and does NOT clear the filter', async () => {
    const first = page([proposalFixture({ proposal_id: 'P1', state: 'open' })], {
      total: 2,
      returned: 1,
      has_more: true,
      next_cursor: 'P1',
    });
    const emptySecond = page([], { total: 2, returned: 0 });
    stubFetchRoutes({
      [LIST]: { body: first },
      [`${LIST}?state=open`]: { body: first },
      [`${LIST}?state=open&after=P1`]: { body: emptySecond },
    });
    renderPanel();

    await screen.findByLabelText('Show');
    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'open' } });
    fireEvent.click(await screen.findByRole('button', { name: 'Next Page' }));

    // Past the end of a FILTERED walk. Both controls are offered and they differ.
    await screen.findByText(/This window holds no proposals/);
    expect(screen.getByText(/The state filter is still applied\./)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Back to the First Page' }));

    // THE DEFECT: a control that promises paging silently discarding the filter.
    await waitFor(() =>
      expect((screen.getByLabelText('Show') as HTMLSelectElement).value).toBe('open'),
    );
    expect(urls().some((u) => u.endsWith('/proposals?state=open&after=P1'))).toBe(true);
  });

  it('M5: Show All Proposals is the control that clears the filter', async () => {
    const first = page([proposalFixture({ proposal_id: 'P1', state: 'open' })], {
      total: 2,
      returned: 1,
      has_more: true,
      next_cursor: 'P1',
    });
    stubFetchRoutes({
      [LIST]: { body: first },
      [`${LIST}?state=open`]: { body: first },
      [`${LIST}?state=open&after=P1`]: { body: page([], { total: 2, returned: 0 }) },
    });
    renderPanel();

    await screen.findByLabelText('Show');
    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'open' } });
    fireEvent.click(await screen.findByRole('button', { name: 'Next Page' }));
    await screen.findByText(/This window holds no proposals/);

    fireEvent.click(screen.getByRole('button', { name: 'Show All Proposals' }));
    await waitFor(() =>
      expect((screen.getByLabelText('Show') as HTMLSelectElement).value).toBe('all'),
    );
  });
});

// --- 10. the filter -------------------------------------------------------------

describe('the state filter', () => {
  it('starts at All, so a closed proposal is never hidden by default', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture({ state: 'rejected' })]) } });
    renderPanel();

    const select = (await screen.findByLabelText('Show')) as HTMLSelectElement;
    expect(select.value).toBe('all');
    // The FIRST read asked for no state at all.
    expect(urls()[0].endsWith('/proposals')).toBe(true);
    expect(screen.getByText('Rejected — kept on the record')).toBeTruthy();
  });

  it('offers exactly the states the SERVER reported, with its own counts', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()], { states: ['open', 'accepted'] }) },
    });
    renderPanel();

    const select = (await screen.findByLabelText('Show')) as HTMLSelectElement;
    const options = within(select)
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value);
    // Nothing this client invented: `rejected`, `superseded` and `withdrawn` were not
    // served, so they are not offered.
    expect(options).toEqual(['all', 'open', 'accepted']);
  });

  it('a filtered window still states the record\'s true total', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposalFixture()], { total: 9, returned: 1 }) },
      [`${LIST}?state=open`]: {
        body: page([proposalFixture()], { total: 9, returned: 1 }),
      },
    });
    renderPanel();

    await screen.findByLabelText('Show');
    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'open' } });

    // THE DEFECT: showing the filtered count as the record's size, which lets a
    // scientist read "1 proposal" off a record that holds nine.
    await screen.findByText(/Showing 1 of 9 proposals on this record/);
    expect(urls().some((u) => u.endsWith('/proposals?state=open'))).toBe(true);
  });
});

// --- I5, independent review of PR-D: "Fewer Actions" must never orphan an open editor ---

describe('"Fewer Actions" cannot discard an open Supersede/Withdraw or Correct-the-Value editor', () => {
  it('MUTATION-GUARDED: the collapse control is disabled while "Correct the Value" is open, and re-enables only once it is closed, with the typed text intact throughout', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    const fewerActions = screen.getByRole('button', { name: 'Fewer Actions' });
    expect(fewerActions).not.toBeDisabled();

    fireEvent.click(
      screen.getByRole('button', { name: 'Correct the Value, Then Accept' }),
    );
    const editorBox = (await screen.findByLabelText(
      'The corrected value, as JSON',
    )) as HTMLTextAreaElement;
    fireEvent.change(editorBox, { target: { value: '"CuO2"' } });

    // The group's own collapse control is now disabled — clicking it (even if a
    // test bypassed the disabled attribute) must not be reachable at all, and the
    // editor and its typed text must both still be in the document.
    expect(screen.getByRole('button', { name: 'Fewer Actions' })).toBeDisabled();
    expect(
      (screen.getByLabelText('The corrected value, as JSON') as HTMLTextAreaElement).value,
    ).toBe('"CuO2"');
    // The disclosure region itself — "More Actions"'s own group — is untouched.
    expect(screen.getByRole('group', { name: 'More actions' })).toBeInTheDocument();

    // Cancelling the editor (the same way every other editor on this card is
    // ever cleared) is what re-enables the collapse — not a forced unmount.
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByLabelText('The corrected value, as JSON')).toBeNull();
    expect(screen.getByRole('button', { name: 'Fewer Actions' })).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Fewer Actions' }));
    expect(screen.queryByRole('button', { name: 'More Actions' })).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'More actions' })).toBeNull();
  });

  it('MUTATION-GUARDED: the same protection holds for an open Supersede reason box, and a typed reason survives', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposalFixture()]) } });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'More Actions' }));
    fireEvent.click(screen.getByRole('button', { name: 'Supersede…' }));
    const reasonBox = await screen.findByLabelText('Reason (optional)');
    fireEvent.change(reasonBox, { target: { value: 'A later run redid this measurement.' } });

    expect(screen.getByRole('button', { name: 'Fewer Actions' })).toBeDisabled();
    expect((screen.getByLabelText('Reason (optional)') as HTMLInputElement).value).toBe(
      'A later run redid this measurement.',
    );

    // Reject's own editor is NOT in this group (it lives in the top-level row)
    // and must never be protected by it — opening Reject's editor instead must
    // leave "Fewer Actions" collapsible, because there is nothing of THIS
    // group's to lose.
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Fewer Actions' })).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Reject…' }));
    expect(screen.getByRole('button', { name: 'Fewer Actions' })).not.toBeDisabled();
  });
});
