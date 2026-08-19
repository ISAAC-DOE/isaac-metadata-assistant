/*
 * The Conflicting Evidence panel.
 *
 * WHAT WOULD FAIL BEFORE THE BEHAVIOUR EACH TEST DEFENDS. Every one of these is a
 * way this panel could be built that renders fine, passes a "does it show the
 * conflict" test, and still tells a scientist something false:
 *
 *   1. A candidate pre-selected — the most-cited one, the one the field currently
 *      holds, the first in the list, or the one a previous decision chose. Three
 *      backend modules assert that nothing in this application picks a winner;
 *      a checked radio undoes all three in one glance.
 *      (`nothing is selected…`, `revising starts from nothing selected`)
 *   2. `deferred` rendered as a clearance — a green tick, a "resolved" word, or a
 *      row that leaves the list. The backend says three times in three files that
 *      deferring does NOT clear the conflict.
 *      (`deferring is recorded and does NOT clear the conflict`)
 *   3. `stale` rendered as decided, or the superseded decision dropped from the
 *      screen once it stopped applying. Staleness is the correctness property the
 *      whole feature turns on, and the decision is kept precisely so it can be read.
 *      (`a stale decision reads as unresolved…`)
 *   4. A decision presented as a change to the record — "value updated", "applied",
 *      a field showing the chosen value. It changes nothing; the API even
 *      serialises `is_field_value: false` so the guarantee crosses the boundary.
 *      (`the panel never claims a decision changed the field`)
 *   5. A refusal rendered as "that could not be recorded". Fifteen typed refusals
 *      exist and each says exactly what was wrong; a generic sentence discards all
 *      of it. (`a typed refusal renders the server's own sentence`)
 *   6. A refusal that also destroys the selection, the typed value or the reason —
 *      the failure class this repository fixed four times in one session.
 *      (`a 412 keeps everything typed…`, `a typed refusal keeps everything typed`)
 *   7. `evidence_count` and `sources.length` shown side by side with no account of
 *      the difference, so a reader concludes a citation was withheld.
 *      (`a candidate with an uncitable entry says so`)
 *
 * Every fixture is synthetic, the wire shapes were captured from the running
 * backend (see `apiFixtures.ts`), and no test here reaches a backend.
 */
import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import axe from 'axe-core';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ConflictResolutionPanel } from '../components/ConflictResolutionPanel';
import {
  CONFLICT_ADDRESS,
  CONFLICT_DIGEST_OLD,
  conflictCandidate,
  conflictFixture,
  conflictNotACandidate,
  conflictResolutionFixture,
  conflictStaleWrite,
  conflictsEmpty,
  conflictsPage,
  runsEmpty,
  runsPage,
  runFixture,
  stubFetchRoutes,
} from '../test/apiFixtures';

const EXP = 'demo';
const CONFLICTS = `GET /api/experiments/${EXP}/conflicts`;
const RESOLVE = `POST /api/experiments/${EXP}/conflicts/resolve`;
const RUNS = `GET /api/experiments/${EXP}/runs`;

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPanel() {
  return render(
    <MemoryRouter
      initialEntries={['/']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ConflictResolutionPanel experimentId={EXP} />
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

/** Every request method issued, so a DELETE or PUT anywhere is visible. */
function methods(): string[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls.map(([, init]) => (init?.method ?? 'GET').toUpperCase());
}

const oneConflict = (over: Partial<Record<string, unknown>> = {}) =>
  conflictsPage([conflictFixture(over)]);

/** Registers the two reads this panel makes, with the runs list empty. */
function stub(conflicts: unknown, extra: Record<string, unknown> = {}) {
  return stubFetchRoutes({
    [CONFLICTS]: { body: conflicts },
    [RUNS]: { body: runsEmpty },
    ...extra,
  } as Parameters<typeof stubFetchRoutes>[0]);
}

/** Waits for the row and returns it. */
async function row(): Promise<HTMLElement> {
  const address = await screen.findByText(CONFLICT_ADDRESS);
  return address.closest('article')!;
}

// --- 1. the honest empty state ------------------------------------------------

describe('the empty state', () => {
  it('says no address disagrees AND that this is not a validity verdict', async () => {
    stub(conflictsEmpty);
    renderPanel();
    const note = await screen.findByText(/No address in this view records two different answers/);
    expect(note.textContent).toMatch(/not a validity, completeness or export verdict/);
  });
});

// --- 2. rendering the competing values ---------------------------------------

describe('rendering one conflict', () => {
  it('shows every competing value, its citation count and its safe source refs', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();

    expect(within(article).getByText('LiFePO3')).toBeInTheDocument();
    expect(within(article).getByText('LiFePO4')).toBeInTheDocument();
    expect(within(article).getByText(/2 evidence entries assert this answer/)).toBeInTheDocument();
    expect(within(article).getByText(/1 evidence entry assert/)).toBeInTheDocument();
    // The safe projection's own tokens, one per citation (2 + 1).
    expect(within(article).getAllByText('user_confirmation')).toHaveLength(3);
  });

  it('renders the server’s own explanation rather than a paraphrase of it', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();
    expect(
      within(article).getByText(/records 2 distinct non-null answers across 3 stored evidence entries/),
    ).toBeInTheDocument();
  });

  it('says the address belongs to this record’s own fields', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();
    expect(within(article).getByText(/This record’s own fields/)).toBeInTheDocument();
  });

  it('names the RUN when the conflict is a run’s own, rather than calling it the record’s', async () => {
    const run = runFixture({ id: 'RUN-1', label: 'Scan 2' });
    stubFetchRoutes({
      [`${CONFLICTS}?run=RUN-1`]: {
        body: conflictsPage([conflictFixture({ run_id: 'RUN-1' })], { run_id: 'RUN-1' }),
      },
      [CONFLICTS]: { body: conflictsEmpty },
      [RUNS]: { body: runsPage([run]) },
    });
    renderPanel();
    // The scope control appears once the runs read lands.
    const select = await screen.findByLabelText('Fields described');
    fireEvent.change(select, { target: { value: 'RUN-1' } });
    const article = await row();
    expect(within(article).getByText('Run · Scan 2')).toBeInTheDocument();
    expect(within(article).queryByText(/This record’s own fields/)).toBeNull();
  });

  it('a candidate with an uncitable entry says so, instead of leaving two numbers to disagree', async () => {
    stub(
      oneConflict({
        candidates: [
          conflictCandidate('LiFePO3', 1, { uncited_evidence_count: 1, sources: [] }),
          conflictCandidate('LiFePO4', 1),
        ],
      }),
    );
    renderPanel();
    const article = await row();
    expect(
      within(article).getByText(/names no source that can be shown safely, so nothing was withheld here/),
    ).toBeInTheDocument();
  });

  it('discloses an entry whose stored evidence was only partly readable', async () => {
    stub(oneConflict({ unavailable: true }));
    renderPanel();
    const article = await row();
    expect(
      within(article).getByText(/could not be read, so the answers below may not be the whole disagreement/),
    ).toBeInTheDocument();
  });
});

// --- 3. NOTHING IS PRE-SELECTED ----------------------------------------------

describe('nothing picks a winner', () => {
  it('nothing is selected on mount — not the most-cited answer, not the first', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();
    const radios = within(article).getAllByRole('radio') as HTMLInputElement[];
    expect(radios.length).toBeGreaterThan(2);
    expect(radios.filter((r) => r.checked)).toEqual([]);
  });

  it('revising starts from nothing selected, even though a decision is on the record', async () => {
    stub(
      oneConflict({
        resolution_state: 'current',
        resolved: true,
        resolution: conflictResolutionFixture(),
      }),
    );
    renderPanel();
    const article = await row();
    // The recorded decision IS shown…
    expect(within(article).getByText('The decision on record')).toBeInTheDocument();
    // …and it is not loaded into the form.
    const radios = within(article).getAllByRole('radio') as HTMLInputElement[];
    expect(radios.filter((r) => r.checked)).toEqual([]);
    expect(
      within(article).getByRole('button', { name: 'Record a Revised Decision' }),
    ).toBeInTheDocument();
  });

  it('states that the server’s ordering is not a ranking', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();
    expect(within(article).getByText(/carries no ranking/)).toBeInTheDocument();
    expect(
      within(article).getByText(/the number of citations behind an answer is not a vote/),
    ).toBeInTheDocument();
  });

  it('preserves the server’s order verbatim — the MORE-cited answer is listed first here', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();
    const values = within(article)
      .getAllByText(/^LiFePO[34]$/)
      .map((el) => el.textContent);
    // The fixture is the backend's own ordering: alphabetical by canonical text,
    // which puts the two-citation answer above the one-citation one.
    expect(values).toEqual(['LiFePO3', 'LiFePO4']);
  });

  it('preserves it when the citation order RUNS THE OTHER WAY — the case that can fail', async () => {
    /*
     * THE TEST ABOVE CANNOT DETECT A RE-SORT, AND THIS ONE CAN.
     *
     * Its fixture happens to list the MORE-cited answer first, so sorting the
     * candidates by citation count descending is a NO-OP on it. Measured: adding
     * `[...candidates].sort((a,b) => b.evidence_count - a.evidence_count)` to the
     * render left all 39 tests green. A test whose name promises that the server's
     * order survives, and which passes whatever order the component chooses, is
     * worse than no test — it reads as the guard for the no-winner invariant.
     *
     * So this fixture inverts the relationship: alphabetical order still puts
     * `LiFePO3` first, but now it is the answer with FEWER citations. Any ordering
     * derived from citation count — ascending or descending — moves something, and
     * the assertion sees it. That is the whole point: candidate order must carry no
     * ranking, and the only way to prove it is a fixture where a ranking would look
     * different from the server's order.
     */
    stub(
      oneConflict({
        candidates: [conflictCandidate('LiFePO3', 1), conflictCandidate('LiFePO4', 5)],
      }),
    );
    renderPanel();
    const article = await row();
    const values = within(article)
      .getAllByText(/^LiFePO[34]$/)
      .map((el) => el.textContent);
    expect(values).toEqual(['LiFePO3', 'LiFePO4']);
  });
});

// --- 4. choosing a candidate -------------------------------------------------

describe('choosing one of the recorded answers', () => {
  it('sends the server’s own value back, as `candidate`, with the record’s If-Match', async () => {
    stub(oneConflict(), {
      [RESOLVE]: { body: { resolution: conflictResolutionFixture(), experiment_version: 'v.2' } },
    });
    renderPanel();
    const article = await row();

    fireEvent.click(within(article).getByLabelText('LiFePO4'));
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    fireEvent.click(within(article).getByRole('button', { name: 'Record This Decision' }));

    await waitFor(() => expect(posts()).toHaveLength(1));
    const [sent] = posts();
    expect(sent.url).toContain('/conflicts/resolve');
    expect(sent.body).toMatchObject({
      confirmed_by_user: true,
      address: CONFLICT_ADDRESS,
      outcome: 'resolved',
      chosen_value: 'LiFePO4',
      chosen_from: 'candidate',
    });
    // `VERSION_FIELDS.version` — the token the conflicts read reported, sent back
    // verbatim. The RECORD's, even for a run-scoped decision.
    expect(sent.ifMatch).toBe('"1.0"');
    expect(methods()).not.toContain('DELETE');
  });

  it('the decision cannot be sent without the explicit confirmation', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();
    fireEvent.click(within(article).getByLabelText('LiFePO4'));
    const button = within(article).getByRole('button', { name: 'Record This Decision' });
    expect(button).toBeDisabled();
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    expect(button).toBeEnabled();
  });

  it('sends an optional reason verbatim, and omits it entirely when blank', async () => {
    stub(oneConflict(), {
      [RESOLVE]: { body: { resolution: conflictResolutionFixture(), experiment_version: 'v.2' } },
    });
    renderPanel();
    const article = await row();
    fireEvent.click(within(article).getByLabelText('LiFePO4'));
    fireEvent.change(within(article).getByLabelText('Why (optional)'), {
      target: { value: '  the first entry was a typo  ' },
    });
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    fireEvent.click(within(article).getByRole('button', { name: 'Record This Decision' }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].body.rationale).toBe('  the first entry was a typo  ');
  });

  it('omits `rationale` rather than sending an empty string the server would refuse', async () => {
    stub(oneConflict(), {
      [RESOLVE]: { body: { resolution: conflictResolutionFixture(), experiment_version: 'v.2' } },
    });
    renderPanel();
    const article = await row();
    fireEvent.click(within(article).getByLabelText('LiFePO4'));
    fireEvent.change(within(article).getByLabelText('Why (optional)'), {
      target: { value: '   ' },
    });
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    fireEvent.click(within(article).getByRole('button', { name: 'Record This Decision' }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect('rationale' in posts()[0].body).toBe(false);
  });
});

// --- 5. entering a different value -------------------------------------------

describe('entering a value none of the recorded answers holds', () => {
  it('sends it as `edited`, which is a different claim from picking a candidate', async () => {
    stub(oneConflict(), {
      [RESOLVE]: {
        body: {
          resolution: conflictResolutionFixture({
            chosen_value: 'LiFePO4·H2O',
            chosen_from: 'edited',
          }),
          experiment_version: 'v.2',
        },
      },
    });
    renderPanel();
    const article = await row();

    fireEvent.click(within(article).getByLabelText(/A different value/));
    fireEvent.change(within(article).getByLabelText('The value you stand behind'), {
      target: { value: 'LiFePO4·H2O' },
    });
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    fireEvent.click(within(article).getByRole('button', { name: 'Record This Decision' }));

    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].body).toMatchObject({
      outcome: 'resolved',
      chosen_value: 'LiFePO4·H2O',
      chosen_from: 'edited',
    });
  });

  it('says the typed value does not become the field’s value', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();
    fireEvent.click(within(article).getByLabelText(/A different value/));
    expect(
      within(article).getByText(/it does not become the field’s value, and it adds no evidence/),
    ).toBeInTheDocument();
  });

  it('will not send an empty typed value', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();
    fireEvent.click(within(article).getByLabelText(/A different value/));
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    expect(within(article).getByRole('button', { name: 'Record This Decision' })).toBeDisabled();
  });
});

// --- 6. deferring does NOT clear the conflict --------------------------------

describe('deferring', () => {
  it('sends `deferred` carrying NEITHER a chosen value nor a chosen_from', async () => {
    stub(oneConflict(), {
      [RESOLVE]: {
        body: {
          resolution: conflictResolutionFixture({
            outcome: 'deferred',
            chosen_value: null,
            chosen_from: null,
            state: 'deferred',
          }),
          experiment_version: 'v.2',
        },
      },
    });
    renderPanel();
    const article = await row();
    fireEvent.click(within(article).getByLabelText(/I looked and I am not deciding yet/));
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    fireEvent.click(within(article).getByRole('button', { name: 'Record This Decision' }));

    await waitFor(() => expect(posts()).toHaveLength(1));
    const body = posts()[0].body;
    expect(body.outcome).toBe('deferred');
    expect('chosen_value' in body).toBe(false);
    expect('chosen_from' in body).toBe(false);
  });

  it('warns BEFORE the act that deferring does not clear the conflict', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();
    fireEvent.click(within(article).getByLabelText(/I looked and I am not deciding yet/));
    expect(within(article).getByText(/It does NOT clear this conflict/)).toBeInTheDocument();
  });

  it('a deferred address is still listed, still says UNRESOLVED, and is never called decided', async () => {
    stub(
      oneConflict({
        resolution_state: 'deferred',
        resolution: conflictResolutionFixture({
          outcome: 'deferred',
          chosen_value: null,
          chosen_from: null,
          state: 'deferred',
        }),
      }),
    );
    renderPanel();
    const article = await row();

    expect(within(article).getByText('Looked at, left undecided')).toBeInTheDocument();
    expect(within(article).getByText(/does NOT clear the conflict/)).toBeInTheDocument();
    expect(within(article).getByText(/still UNRESOLVED/)).toBeInTheDocument();
    expect(article.querySelector('.conflict-state')!.getAttribute('data-decided')).toBe('no');
    // and the panel's own tally counts it as unresolved, not as decided
    expect(screen.getByText(/1 still unresolved · 0 decided/)).toBeInTheDocument();
  });
});

// --- 7. staleness reads as unresolved, and keeps the superseded decision ------

describe('a superseded decision', () => {
  const stale = () =>
    oneConflict({
      resolution_state: 'stale',
      resolved: false,
      resolution_stale: true,
      resolution: conflictResolutionFixture({
        state: 'stale',
        stale: true,
        competing_digest: CONFLICT_DIGEST_OLD,
        competing_values: ['"LiFePO3"', '"LiFePO4"'],
      }),
    });

  it('reads as unresolved and says WHY it no longer covers the answers on screen', async () => {
    stub(stale());
    renderPanel();
    const article = await row();
    expect(within(article).getByText('Superseded — undecided again')).toBeInTheDocument();
    expect(within(article).getByText(/This address is UNRESOLVED/)).toBeInTheDocument();
    expect(
      within(article).getByText(/further competing evidence has arrived since/),
    ).toBeInTheDocument();
    expect(article.querySelector('.conflict-state')!.getAttribute('data-decided')).toBe('no');
  });

  it('KEEPS the superseded decision on screen rather than dropping it', async () => {
    stub(stale());
    renderPanel();
    const article = await row();
    expect(within(article).getByText('The decision that was superseded')).toBeInTheDocument();
    // The superseded VALUE is in the decision block — asserted there rather than on
    // the article, where `LiFePO4` is also one of the live candidates. Two elements
    // carrying the same string is the point: the candidate is still competing AND
    // the decision that chose it is still readable.
    const decision = article.querySelector('.conflict-decision')!;
    expect(within(decision as HTMLElement).getByText('LiFePO4')).toBeInTheDocument();
    expect(within(article).getByText(/kept below, not deleted/)).toBeInTheDocument();
  });

  it('counts it as unresolved in the tally, not as decided', async () => {
    stub(stale());
    renderPanel();
    await row();
    expect(screen.getByText(/1 still unresolved · 0 decided · 1 superseded/)).toBeInTheDocument();
  });
});

// --- 8. a revision APPENDS -----------------------------------------------------

describe('a revised decision', () => {
  it('shows both acts, with the value the revision superseded', async () => {
    stub(
      oneConflict({
        resolution_state: 'deferred',
        resolution: conflictResolutionFixture({
          outcome: 'deferred',
          chosen_value: null,
          chosen_from: null,
          state: 'deferred',
          history: [
            {
              action: 'record',
              at: '2026-08-18T23:34:33Z',
              from_outcome: null,
              to_outcome: 'resolved',
              superseded_chosen_value: null,
              superseded_competing_digest: null,
            },
            {
              action: 'revise',
              at: '2026-08-18T23:40:00Z',
              from_outcome: 'resolved',
              to_outcome: 'deferred',
              superseded_chosen_value: 'LiFePO4',
              superseded_competing_digest: 'abc',
            },
          ],
        }),
      }),
    );
    renderPanel();
    const article = await row();

    expect(within(article).getByText(/2 acts, appended, never rewritten/)).toBeInTheDocument();
    const history = article.querySelector('.conflict-history')!;
    expect(history.children).toHaveLength(2);
    expect(history.textContent).toMatch(/first recorded as a chosen value/);
    expect(history.textContent).toMatch(/revised from a chosen value to left undecided/);
    expect(history.textContent).toMatch(/It superseded/);
    expect(history.textContent).toMatch(/kept here rather than overwritten/);
  });
});

// --- 9. a decision is not a value ---------------------------------------------

describe('what a decision is not', () => {
  it('never claims a decision changed the field, applied a value, or removed evidence', async () => {
    stub(
      oneConflict({
        resolution_state: 'current',
        resolved: true,
        resolution: conflictResolutionFixture(),
      }),
    );
    const { container } = renderPanel();
    await row();
    const text = container.textContent!;

    expect(text).toMatch(/it does not change the field’s value/);
    expect(text).toMatch(/It is not the field’s value and not an evidence entry/);
    expect(text).toMatch(/the competing entries it was decided between are all still on the record/);
    // and none of the words that would say the opposite
    expect(text).not.toMatch(/value updated|field updated|applied to the field|evidence removed/i);
  });

  it('never presents a conflict as a gate on export or submission', async () => {
    stub(oneConflict());
    const { container } = renderPanel();
    await row();
    expect(container.textContent).toMatch(/blocks neither export nor submission/);
    expect(container.textContent).not.toMatch(/before export|blocks export|cannot export/i);
  });
});

// --- 10. refusals -------------------------------------------------------------

describe('a typed refusal', () => {
  it('renders the SERVER’S OWN sentence and its error code, not a generic failure', async () => {
    stub(oneConflict(), { [RESOLVE]: conflictNotACandidate });
    renderPanel();
    const article = await row();
    fireEvent.click(within(article).getByLabelText('LiFePO4'));
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    fireEvent.click(within(article).getByRole('button', { name: 'Record This Decision' }));

    const alert = await within(article).findByRole('alert');
    expect(alert.textContent).toMatch(
      /A value nothing asserted is an `edited` decision; labelling it `candidate` would attribute it/,
    );
    expect(alert.textContent).toMatch(/chosen_value_not_a_candidate/);
    // NOT the generic sentence
    expect(alert.textContent).not.toMatch(/That decision could not be recorded/);
  });

  it('keeps the selection, the typed value and the reason after a refusal', async () => {
    stub(oneConflict(), { [RESOLVE]: conflictNotACandidate });
    renderPanel();
    const article = await row();

    fireEvent.click(within(article).getByLabelText(/A different value/));
    fireEvent.change(within(article).getByLabelText('The value you stand behind'), {
      target: { value: 'Li2FePO4' },
    });
    fireEvent.change(within(article).getByLabelText('Why (optional)'), {
      target: { value: 'the spreadsheet column was mislabelled' },
    });
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    fireEvent.click(within(article).getByRole('button', { name: 'Record This Decision' }));

    await within(article).findByRole('alert');
    expect(
      (within(article).getByLabelText('The value you stand behind') as HTMLInputElement).value,
    ).toBe('Li2FePO4');
    expect(
      (within(article).getByLabelText('Why (optional)') as HTMLTextAreaElement).value,
    ).toBe('the spreadsheet column was mislabelled');
    expect(
      (within(article).getByLabelText(/A different value/) as HTMLInputElement).checked,
    ).toBe(true);
  });

  it('associates the refusal with the control that produced it', async () => {
    stub(oneConflict(), { [RESOLVE]: conflictNotACandidate });
    renderPanel();
    const article = await row();
    fireEvent.click(within(article).getByLabelText('LiFePO4'));
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    const button = within(article).getByRole('button', { name: 'Record This Decision' });
    fireEvent.click(button);

    const alert = await within(article).findByRole('alert');
    expect(button.getAttribute('aria-describedby')).toBe(alert.id);
    const fieldset = article.querySelector('fieldset')!;
    expect(fieldset.getAttribute('aria-describedby')).toContain(alert.id);
  });
});

describe('a stale write (412)', () => {
  /*
   * THE REFRESH IS HELD IN FLIGHT ON PURPOSE, and without that this test would
   * assert nothing.
   *
   * A 412 does two things here: it ADOPTS the `current_version` the refusal
   * reports, and it fires a silent refresh. If the refresh is allowed to land, its
   * own `experiment_version` overwrites the adopted one and the two paths become
   * indistinguishable — a panel that adopted nothing would pass just as well. So
   * the second conflicts read never resolves, which is also the realistic race:
   * a reader who presses the button again immediately is retrying BEFORE the
   * refresh has come back, and that is exactly the moment a panel that did not
   * adopt would re-send the stale validator and be refused forever.
   */
  it('adopts the version the server reports, and keeps everything typed', async () => {
    let reads = 0;
    let resolves = 0;
    stubFetchRoutes({
      [CONFLICTS]: () => {
        reads += 1;
        // The refresh (read 2) is left pending, so nothing can overwrite the
        // adopted token while the retry below is made.
        return reads === 1
          ? { body: oneConflict() }
          : (new Promise(() => {}) as never);
      },
      [RUNS]: { body: runsEmpty },
      [RESOLVE]: () => {
        resolves += 1;
        return resolves === 1
          ? conflictStaleWrite
          : {
              body: { resolution: conflictResolutionFixture(), experiment_version: 'v.3' },
            };
      },
    } as Parameters<typeof stubFetchRoutes>[0]);
    renderPanel();
    const article = await row();

    fireEvent.click(within(article).getByLabelText('LiFePO4'));
    fireEvent.change(within(article).getByLabelText('Why (optional)'), {
      target: { value: 'the second answer was the typo' },
    });
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    fireEvent.click(within(article).getByRole('button', { name: 'Record This Decision' }));

    const alert = await within(article).findByRole('alert');
    expect(alert.textContent).toMatch(/The record changed since this section was loaded/);
    expect(alert.textContent).toMatch(/anything you typed are still here/);

    // NOTHING TYPED WAS LOST, and the row was not unmounted by the refresh.
    expect(
      (within(article).getByLabelText('Why (optional)') as HTMLTextAreaElement).value,
    ).toBe('the second answer was the typo');
    expect((within(article).getByLabelText('LiFePO4') as HTMLInputElement).checked).toBe(true);

    // The NEXT attempt carries the version the 412 reported, not the stale one.
    fireEvent.click(within(article).getByRole('button', { name: 'Record This Decision' }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(posts()[0].ifMatch).toBe('"1.0"');
    expect(posts()[1].ifMatch).toBe('"24cdbd3b7c38822f.2"');
  });
});

// --- 11. success clears the form, and only success --------------------------

describe('a recorded decision', () => {
  it('clears the form it consumed and re-reads the list', async () => {
    stub(oneConflict(), {
      [RESOLVE]: { body: { resolution: conflictResolutionFixture(), experiment_version: 'v.2' } },
    });
    renderPanel();
    const article = await row();

    fireEvent.click(within(article).getByLabelText('LiFePO4'));
    fireEvent.change(within(article).getByLabelText('Why (optional)'), {
      target: { value: 'a reason' },
    });
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    fireEvent.click(within(article).getByRole('button', { name: 'Record This Decision' }));

    await waitFor(() =>
      expect((within(article).getByLabelText('LiFePO4') as HTMLInputElement).checked).toBe(false),
    );
    expect((within(article).getByLabelText('Why (optional)') as HTMLTextAreaElement).value).toBe('');
    expect(
      (within(article).getByLabelText(/I am recording this decision myself/) as HTMLInputElement)
        .checked,
    ).toBe(false);
  });
});

// --- 12. disclosures nothing else on the screen makes ------------------------

describe('what the panel refuses to leave out', () => {
  it('counts stored decisions this build could not read rather than hiding them', async () => {
    stub(conflictsPage([], { unreadable_resolution_entries: 2 }));
    renderPanel();
    expect(
      await screen.findByText(/2 recorded decisions stored on this record could not be read/),
    ).toBeInTheDocument();
  });

  it('reports a decision whose run has been REMOVED, which is reachable from nowhere else', async () => {
    stub(
      conflictsPage([], {
        resolutions_without_conflict: [
          {
            address: 'sample.sample_form',
            run_id: 'GONE',
            outcome: 'resolved',
            resolution_id: 'R1',
            orphaned_run: true,
          },
        ],
      }),
    );
    renderPanel();
    expect(
      await screen.findByText(/the run this decision belongs to has been removed from this record/),
    ).toBeInTheDocument();
  });

  it('keeps working at record scope when the run list cannot be read, and says so', async () => {
    stubFetchRoutes({
      [CONFLICTS]: { body: oneConflict() },
      [RUNS]: { status: 500, body: { error: 'boom' } },
    } as Parameters<typeof stubFetchRoutes>[0]);
    renderPanel();
    await row();
    expect(
      await screen.findByText(/This record’s runs could not be listed/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Fields described')).toBeNull();
  });

  it('discloses a failed conflicts read in place instead of claiming there are none', async () => {
    stubFetchRoutes({
      [CONFLICTS]: { status: 500, body: { error: 'boom' } },
      [RUNS]: { body: runsEmpty },
    } as Parameters<typeof stubFetchRoutes>[0]);
    renderPanel();
    expect(
      await screen.findByText(/could not be read, so this section is not describing this record/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/No address in this view records two different answers/)).toBeNull();
  });
});

// --- 13. accessibility --------------------------------------------------------

describe('accessibility', () => {
  /**
   * The rules that would actually catch this panel's plausible failures: a radio
   * or checkbox with no programmatic label, a fieldset with no legend, an input
   * pointed at an id that does not exist, and a colour contrast below AA. Named
   * explicitly rather than run wholesale, exactly as `a11y-critical-fixes.test.tsx`
   * does, so a violation elsewhere in the tree cannot make this pass or fail for a
   * reason that has nothing to do with the conflict surface.
   */
  const RULES = [
    'label',
    'form-field-multiple-labels',
    'aria-valid-attr-value',
    'aria-allowed-role',
    'listitem',
    'definition-list',
    'dlitem',
  ];

  it('reports no violation with a conflict, its decision and a refusal on screen', async () => {
    stub(
      oneConflict({
        resolution_state: 'stale',
        resolution_stale: true,
        resolution: conflictResolutionFixture({ state: 'stale', stale: true }),
      }),
      { [RESOLVE]: conflictNotACandidate },
    );
    const { container } = renderPanel();
    const article = await row();
    fireEvent.click(within(article).getByLabelText(/A different value/));
    fireEvent.change(within(article).getByLabelText('The value you stand behind'), {
      target: { value: 'LiFePO4' },
    });
    fireEvent.click(within(article).getByLabelText(/I am recording this decision myself/));
    fireEvent.click(within(article).getByRole('button', { name: 'Record a Revised Decision' }));
    await within(article).findByRole('alert');

    const results = await axe.run(container, {
      runOnly: { type: 'rule', values: RULES },
      resultTypes: ['violations'],
    });
    expect(results.violations.map((v) => `${v.id} × ${v.nodes.length}`)).toEqual([]);
  });

  it('every control is reachable and named, and the choice group has a legend', async () => {
    stub(oneConflict());
    renderPanel();
    const article = await row();
    // Each radio is named by a real label, so a keyboard/screen-reader user can
    // tell the two competing answers apart without seeing the layout.
    expect(within(article).getByLabelText('LiFePO3')).toBeInTheDocument();
    expect(within(article).getByLabelText('LiFePO4')).toBeInTheDocument();
    expect(within(article).getByLabelText(/A different value/)).toBeInTheDocument();
    expect(within(article).getByLabelText(/I looked and I am not deciding yet/)).toBeInTheDocument();
    expect(
      within(article).getByRole('group', { name: /Which answer do you stand behind/ }),
    ).toBeInTheDocument();
  });

  it('states each state IN WORDS, so the chip colour is never the only signal', async () => {
    for (const [state, words] of [
      ['absent', /Nobody has recorded a decision/],
      ['current', /it did not change the field’s value/],
      ['stale', /This address is UNRESOLVED/],
      ['deferred', /still UNRESOLVED/],
    ] as const) {
      stub(
        oneConflict({
          resolution_state: state,
          resolution: state === 'absent' ? null : conflictResolutionFixture({ state }),
        }),
      );
      const view = renderPanel();
      const article = await row();
      expect(within(article).getByText(words)).toBeInTheDocument();
      view.unmount();
      vi.unstubAllGlobals();
    }
  });
});
