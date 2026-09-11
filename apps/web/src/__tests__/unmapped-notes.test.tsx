/*
 * The Unmapped Notes panel.
 *
 * WHAT WOULD FAIL BEFORE THE CHANGE THESE TESTS DEFEND. Each of these is a way the
 * panel could be built that passes a naive "does it render" test and still breaks
 * the feature's promise:
 *
 *   1. A panel that hides dismissed notes by default, or that shows the filtered
 *      count as the record's size. Either lets a scientist read "no notes" off a
 *      record that holds several — in a feature whose entire premise is that nothing
 *      captured is silently lost.
 *      (`the filter starts at All…`, `a filtered page still states the record's true total`)
 *   2. A mapping control that pre-selects a plausible field, or that offers paths the
 *      client invented rather than the ones the server said it would accept.
 *      (`the field control offers exactly the server's paths, with nothing pre-selected`)
 *   3. A card that renders `display_text` alone after an edit, quietly replacing the
 *      verbatim capture on screen while the store still holds it.
 *      (`an edited note shows the corrected wording AND the original capture`)
 *   4. A "suggested field" rendered without the rule that produced it — an
 *      unexplained proposal, which is a guess wearing a field name.
 *      (`a candidate path is never shown without the rule that produced it`)
 *   5. Dismiss wired to a DELETE, or a review write that omits `If-Match` and
 *      silently overwrites a concurrent edit.
 *      (`dismissing sends a review act, never a delete`, `every write carries the record's version`)
 *
 * Every fixture is synthetic and no test here reaches a backend.
 */
import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { UnmappedNotesPanel } from '../components/UnmappedNotesPanel';
import type { RecordChangeSummary } from '../lib/recordChanges';
import {
  noteFixture,
  notesEmpty,
  notesPage,
  runFixture,
  runsPage,
  stubFetchRoutes,
} from '../test/apiFixtures';

const EXP = 'demo';
const NOTES = `GET /api/experiments/${EXP}/notes`;
const PROPOSALS = `GET /api/experiments/${EXP}/proposals`;
const CREATE_PROPOSAL = `POST /api/experiments/${EXP}/proposals`;
const RUNS = `GET /api/experiments/${EXP}/runs`;

/** The VISIBLE silent-refresh disclosure. Every assertion on its sentence needs
 *  this selector, because the same sentence is deliberately also pushed into the
 *  permanently-mounted `role="status"` region — see section 15. */
const NOTICE = '.notes-background-refresh-notice';

/** `GET .../proposals`'s served capability vocabulary — the two sets PR-D's
 *  "Propose a value from this note" form reads and never transcribes. */
function proposalsCapabilities(over: Partial<Record<string, unknown>> = {}) {
  return {
    proposals: [],
    total: 0,
    returned: 0,
    by_state: { open: 0, accepted: 0, rejected: 0, superseded: 0, withdrawn: 0 },
    has_more: false,
    next_cursor: null,
    order: 'oldest_first',
    window_default: 50,
    window_max: 200,
    max_per_record: 500,
    unreadable_entries: 0,
    target_field_paths: ['context.environment', 'system.technique'],
    record_scoped_target_field_paths: ['system.technique'],
    states: ['open', 'accepted', 'rejected', 'superseded', 'withdrawn'],
    review_actions: ['accept', 'reject', 'supersede', 'withdraw'],
    accepted_from_values: ['candidate', 'edited'],
    experiment_version: 'g1.4',
    ...over,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPanel(activity: RecordChangeSummary | null = null) {
  return render(
    <MemoryRouter
      initialEntries={['/']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <UnmappedNotesPanel experimentId={EXP} activity={activity} />
    </MemoryRouter>,
  );
}

/** A `recordMoved` summary at the given position — the shape `useRecordSession`
 *  delivers as `notesActivity`. No run/proposal ids: this panel's own effect
 *  reads only `recordMoved` and `highestRev`. */
function recordMovedActivityFor(highestRev: number): RecordChangeSummary {
  return {
    recordMoved: true,
    runIds: [],
    proposalIds: [],
    proposalStates: [],
    otherKinds: [],
    highestRev,
    runRev: -1,
    proposalRev: -1,
  };
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

// --- 1. the honest empty state ------------------------------------------------

describe('the empty state', () => {
  it('says the record has no notes AND that nothing is created or inferred for it', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesEmpty } });
    renderPanel();

    await screen.findByText(/No unmapped notes on this record/);
    // The claim that carries the meaning: this panel does not manufacture notes.
    expect(
      screen.getByText(/nothing is created\s+automatically, and nothing is inferred/),
    ).toBeTruthy();
    // An empty record must NOT offer a "show all" escape hatch — there is nothing
    // being filtered out, and offering one would imply there is.
    expect(screen.queryByRole('button', { name: 'Show All Notes' })).toBeNull();
  });

  it('distinguishes "no notes" from "none in this state", and never conflates them', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesEmpty },
      [`${NOTES}?state=dismissed`]: {
        body: notesPage([], {
          total: 3,
          by_state: { unreviewed: 2, mapped: 1, kept: 0, dismissed: 0 },
        }),
      },
    });
    renderPanel();
    await screen.findByText(/No unmapped notes on this record/);

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'dismissed' } });

    // The filtered empty state states the record's REAL size, so an empty page can
    // never be read as an empty record.
    await screen.findByText(/No notes are in this state\. This record holds 3 notes/);
    expect(screen.getByRole('button', { name: 'Show All Notes' })).toBeTruthy();
  });
});

// --- 2. dismissed notes are never hidden by default ---------------------------

describe('dismissal is a state, not a deletion', () => {
  it('the filter starts at All, so a dismissed note is on screen without being asked for', async () => {
    stubFetchRoutes({
      [NOTES]: {
        body: notesPage([noteFixture({ id: 'N-DIS', state: 'dismissed' })], {
          by_state: { unreviewed: 0, mapped: 0, kept: 0, dismissed: 1 },
        }),
      },
    });
    renderPanel();

    await screen.findByText('Dismissed — kept on the record');
    expect((screen.getByLabelText('Show') as HTMLSelectElement).value).toBe('all');
    // The state label itself corrects the likeliest misreading of this panel.
    expect(screen.getByText('Dismissed — kept on the record')).toBeTruthy();
  });

  it("a filtered page still states the record's true total, never the page size", async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesEmpty },
      [`${NOTES}?state=unreviewed`]: {
        body: notesPage([noteFixture()], {
          total: 4,
          by_state: { unreviewed: 1, mapped: 1, kept: 1, dismissed: 1 },
        }),
      },
    });
    renderPanel();
    await screen.findByText(/No unmapped notes/);

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'unreviewed' } });

    // "Showing 1 of 4 notes on this record" — two numbers, never one.
    await screen.findByText(/Showing 1 of 4 notes on this record/);
  });

  it('dismissing sends a review act, never a delete', async () => {
    let listed = 0;
    stubFetchRoutes({
      [NOTES]: () => {
        listed += 1;
        return {
          body:
            listed === 1
              ? notesPage([noteFixture()])
              : notesPage([noteFixture({ state: 'dismissed' })], {
                  by_state: { unreviewed: 0, mapped: 0, kept: 0, dismissed: 1 },
                }),
        };
      },
      [`POST /api/experiments/${EXP}/notes/${noteFixture().id}/review`]: {
        body: { note: noteFixture({ state: 'dismissed' }), experiment_version: '1.1' },
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss This Note' }));

    await screen.findByText('Dismissed — kept on the record');
    expect(methods()).not.toContain('DELETE');
    const [write] = posts();
    expect(write.url).toContain('/review');
    expect(write.body.action).toBe('dismiss');
    expect(write.body.confirmed_by_user).toBe(true);
  });

  it('an omitted dismissal reason is omitted, never sent as an empty string', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [`POST /api/experiments/${EXP}/notes/${noteFixture().id}/review`]: {
        body: { note: noteFixture({ state: 'dismissed' }), experiment_version: '1.1' },
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss This Note' }));
    await screen.findByRole('status');

    // A justification nobody wrote is not composed for them, and `""` would be
    // stored as though somebody had written something.
    expect(Object.keys(posts()[0].body)).not.toContain('reason');
  });
});

// --- 3. nothing is proposed ---------------------------------------------------

describe('no guessed schema target', () => {
  it("the field control offers exactly the server's paths, with nothing pre-selected", async () => {
    stubFetchRoutes({
      [NOTES]: {
        body: notesPage([noteFixture()], {
          mappable_field_paths: ['context.environment', 'sample.material.name'],
        }),
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Map to a field' }));
    const select = (await screen.findByLabelText(
      'Field this note belongs to',
    )) as HTMLSelectElement;

    // Nothing chosen for the scientist.
    expect(select.value).toBe('');
    // Exactly the server's list, plus the empty prompt — no path this client invented.
    const options = within(select)
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value);
    expect(options).toEqual(['', 'context.environment', 'sample.material.name']);
    // And the action stays unavailable until a person chooses one.
    expect(
      (screen.getByRole('button', { name: 'Map This Note' }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it('a note with no candidate shows no suggested field at all', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    renderPanel();

    await screen.findByText(noteFixture().text);
    // Absent, not a path-shaped blank.
    expect(screen.queryByText(/Suggested field/)).toBeNull();
  });

  it('a candidate path is never shown without the rule that produced it', async () => {
    stubFetchRoutes({
      [NOTES]: {
        body: notesPage([
          noteFixture({
            candidate_field_path: 'context.environment',
            candidate_rule: 'the CSV heading matched this path exactly',
          }),
        ]),
      },
    });
    renderPanel();

    const suggested = await screen.findByText(/Suggested field/);
    expect(suggested.textContent).toContain('context.environment');
    expect(suggested.textContent).toContain('the CSV heading matched this path exactly');
  });

  it('mapping says it records a target and writes no value', async () => {
    stubFetchRoutes({
      [NOTES]: {
        body: notesPage([noteFixture()], { mappable_field_paths: ['context.environment'] }),
      },
      [`POST /api/experiments/${EXP}/notes/${noteFixture().id}/review`]: {
        body: {
          note: noteFixture({ state: 'mapped', mapped_field_path: 'context.environment' }),
          experiment_version: '1.1',
        },
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Map to a field' }));
    expect(screen.getByText(/It does not write a value/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText('Field this note belongs to'), {
      target: { value: 'context.environment' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Map This Note' }));

    await screen.findByRole('status');
    expect(posts()[0].body).toMatchObject({
      action: 'map',
      field_path: 'context.environment',
      confirmed_by_user: true,
    });
  });
});

// --- 4. the verbatim capture stays visible ------------------------------------

describe('the verbatim capture', () => {
  it('an edited note shows the corrected wording AND the original capture', async () => {
    stubFetchRoutes({
      [NOTES]: {
        body: notesPage([
          noteFixture({
            text: 'orginal typo’d wording',
            revised_text: 'corrected wording',
            display_text: 'corrected wording',
          }),
        ]),
      },
    });
    renderPanel();

    await screen.findByText('corrected wording');
    // The promise this feature made is about the capture, so the capture is on screen.
    expect(screen.getByText(/orginal typo’d wording/)).toBeTruthy();
    expect(screen.getByText('Captured as:')).toBeTruthy();
  });

  it('the capture box says the text is stored word for word and never exported', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesEmpty } });
    renderPanel();

    await screen.findByLabelText('Capture a note');
    const hint = screen.getByText(/Stored word for word/);
    expect(hint.textContent).toContain('not a field value and not evidence');
    expect(hint.textContent).toContain('will not appear in an exported record');
  });

  it('captured text is sent untrimmed, exactly as it was typed', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesEmpty },
      [`POST /api/experiments/${EXP}/notes`]: {
        status: 201,
        body: { note: noteFixture(), experiment_version: '1.1' },
      },
    });
    renderPanel();

    const box = await screen.findByLabelText('Capture a note');
    fireEvent.change(box, { target: { value: '  leading and trailing  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Capture Note' }));

    await screen.findByRole('status');
    expect(posts()[0].body.text).toBe('  leading and trailing  ');
    expect(posts()[0].body.source).toBe('typed_note');
  });
});

// --- 5. "keep as note" is a first-class outcome -------------------------------

describe('keep as note', () => {
  it('is offered as a peer of the other three actions, not as a fallback', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    renderPanel();

    await screen.findByText(noteFixture().text);
    for (const name of ['Map to a field', 'Edit wording', 'Keep as note', 'Dismiss']) {
      expect(screen.getByRole('button', { name })).toBeTruthy();
    }
    // All four are real buttons, so they are keyboard operable without any extra work.
    for (const name of ['Map to a field', 'Edit wording', 'Keep as note', 'Dismiss']) {
      expect((screen.getByRole('button', { name }) as HTMLButtonElement).type).toBe(
        'button',
      );
    }
  });

  it('records the outcome and announces it as a decision rather than a skip', async () => {
    let listed = 0;
    stubFetchRoutes({
      [NOTES]: () => {
        listed += 1;
        return {
          body:
            listed === 1
              ? notesPage([noteFixture()])
              : notesPage([noteFixture({ state: 'kept' })], {
                  by_state: { unreviewed: 0, mapped: 0, kept: 1, dismissed: 0 },
                }),
        };
      },
      [`POST /api/experiments/${EXP}/notes/${noteFixture().id}/review`]: {
        body: { note: noteFixture({ state: 'kept' }), experiment_version: '1.1' },
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Keep as note' }));
    await screen.findByText('Kept as a note');

    expect(posts()[0].body.action).toBe('keep');
    const live = await screen.findByRole('status');
    expect(live.textContent).toContain('belongs to no field');
    expect(live.textContent).toContain('stays on the record');
  });
});

// --- 6. concurrency and disclosure --------------------------------------------

describe('the record is the one validator', () => {
  it("every write carries the record's version, wrapped as an ETag", async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [`POST /api/experiments/${EXP}/notes/${noteFixture().id}/review`]: {
        body: { note: noteFixture({ state: 'kept' }), experiment_version: '1.1' },
      },
      [`POST /api/experiments/${EXP}/notes`]: {
        status: 201,
        body: { note: noteFixture(), experiment_version: '1.1' },
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Keep as note' }));
    await screen.findByRole('status');

    // `notesPage` reports the fixture version; the client must quote it.
    expect(posts()[0].ifMatch).toBe('"1.0"');
  });

  /*
   * WHAT THIS PINS, STATED NARROWLY BECAUSE THE FIRST VERSION OF IT OVERCLAIMED.
   *
   * Reviewing a note advances the record, so a SECOND act must not still be quoting
   * the token the first one consumed. This models the server honestly — every read
   * reports the record's current version, exactly as the real route does — and
   * asserts the two consecutive writes quote different, current tokens.
   *
   * It does NOT isolate the `setVersion(written.experiment_version)` line in the
   * component: with a synchronous stub the refetch always lands before the second
   * click, so the refetch alone would satisfy this. That line closes the window
   * where a real refetch has not returned yet, and this suite has no way to hold a
   * response open without making the test about timers rather than about the
   * contract. Saying so is better than implying a coverage this does not have.
   */
  it('a second act quotes the version the first one produced, not the one it consumed', async () => {
    const a = noteFixture({ id: 'N-A' });
    const b = noteFixture({ id: 'N-B' });
    let version = '1.0';
    stubFetchRoutes({
      [NOTES]: () => ({
        body: {
          ...notesPage([a, b], {
            by_state: { unreviewed: 2, mapped: 0, kept: 0, dismissed: 0 },
          }),
          experiment_version: version,
        },
      }),
      [`POST /api/experiments/${EXP}/notes/N-A/review`]: () => {
        version = '1.1';
        return { body: { note: { ...a, state: 'kept' }, experiment_version: version } };
      },
      [`POST /api/experiments/${EXP}/notes/N-B/review`]: () => {
        version = '1.2';
        return { body: { note: { ...b, state: 'kept' }, experiment_version: version } };
      },
    });
    renderPanel();

    const keeps = await screen.findAllByRole('button', { name: 'Keep as note' });
    fireEvent.click(keeps[0]);
    await screen.findByRole('status');
    fireEvent.click(keeps[1]);
    await screen.findByRole('status');

    const [first, second] = posts();
    expect(first.ifMatch).toBe('"1.0"');
    // NOT '"1.0"' again: holding the consumed token would make this second act a
    // 412 that nothing was actually wrong with.
    expect(second.ifMatch).toBe('"1.1"');
  });

  it('a refused write leaves the note alone and says nothing was recorded', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [`POST /api/experiments/${EXP}/notes/${noteFixture().id}/review`]: {
        status: 412,
        body: { error: 'stale_write' },
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Keep as note' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBeTruthy();
    // The note is unchanged on screen — no optimistic state was applied.
    expect(screen.getByText('Not yet reviewed')).toBeTruthy();
  });
});

describe('what this build could not read is disclosed, not hidden', () => {
  it('counts unshowable stored entries and says they are kept unchanged', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()], { unreadable_entries: 2 }) },
    });
    renderPanel();

    const count = await screen.findByText(/stored entries this version cannot show/);
    expect(count.textContent).toContain('2 stored entries');
    expect(count.textContent).toContain('kept unchanged on the record');
  });

  /*
   * THE COUNT COVERS TWO DIFFERENT FACTS AND THE COPY MUST NOT PICK ONE.
   * `workspace._hydrate_notes` files a DUPLICATE-ID entry into the same number as an
   * entry the model refused, and this build reads a duplicate perfectly well — it
   * just cannot let two notes answer to one id. "cannot read" was false for half the
   * count, which is the kind of small confident wrongness this feature exists to end.
   */
  it('names both reasons an entry is not shown, and claims neither alone', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()], { unreadable_entries: 2 }) },
    });
    renderPanel();

    const count = await screen.findByText(/stored entries this version cannot show/);
    expect(count.textContent).toContain('either unreadable, or repeating an id');
    // The old wording asserted unreadability of every one of them.
    expect(count.textContent).not.toContain('cannot read');
  });

  it('says nothing about unreadable entries when there are none', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    renderPanel();

    await screen.findByText(noteFixture().text);
    expect(screen.queryByText(/cannot show/)).toBeNull();
  });

  /*
   * `total` COUNTS ONLY WHAT COULD BE HYDRATED, so "no notes on this record" and "N
   * notes in total" are both false while an unshowable entry exists. The count line
   * discloses it; the empty state is where a reader STOPS looking, so it cannot be
   * the one surface that leaves the number out.
   */
  it('the unfiltered empty state discloses entries that are stored but not shown', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([], { total: 0, unreadable_entries: 1 }) },
    });
    renderPanel();

    const empty = await screen.findByText(/No unmapped notes on this record/);
    expect(empty.textContent).toContain('1 stored entry this version cannot show');
    expect(empty.textContent).toContain('kept unchanged on the record');
  });

  it('the filtered empty state does not call a partial count the record’s total', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([], { total: 0 }) },
      [`${NOTES}?state=dismissed`]: {
        body: notesPage([], { total: 3, unreadable_entries: 2 }),
      },
    });
    renderPanel();
    await screen.findByText(/No unmapped notes on this record/);

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'dismissed' } });

    const empty = await screen.findByText(/No notes are in this state/);
    expect(empty.textContent).toContain('This record holds 3 notes in total');
    // "in total" is only true if what sits outside that total is said in the same breath.
    expect(empty.textContent).toContain('2 stored entries this version cannot show');
  });
});

// --- 8. a refused review keeps what was typed ---------------------------------

/*
 * WHY THESE EXIST, AND WHY THE ONE REFUSAL TEST ABOVE DID NOT COVER IT.
 *
 * `a refused write leaves the note alone` uses "Keep as note", which has no form and
 * no typed input — so a component that closed the form on failure and discarded the
 * scientist's text passed it. The failure it hides is expensive and quiet: a note
 * rewritten into three corrected paragraphs, a 412 from a capture in another tab,
 * a banner truthfully saying the NOTE is unchanged, and the paragraphs gone.
 *
 * Each of these fails if `close()` moves back onto the unconditional path.
 */
describe('a review that was refused keeps the scientist’s input', () => {
  const REVIEW = `POST /api/experiments/${EXP}/notes/${noteFixture().id}/review`;

  it('the edit form stays open with the rewritten wording still in it', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [REVIEW]: { status: 412, body: { error: 'stale_write' } },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Edit wording' }));
    const box = screen.getByLabelText('Corrected wording') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'three corrected paragraphs' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Wording' }));

    await screen.findByRole('alert');
    // Still mounted, still holding what was typed — not reset to `display_text`.
    const after = screen.getByLabelText('Corrected wording') as HTMLTextAreaElement;
    expect(after.value).toBe('three corrected paragraphs');
    expect(screen.getByRole('button', { name: 'Save Wording' })).toBeTruthy();
    // And re-submittable: the failure re-enabled the control rather than stranding it.
    expect(
      (screen.getByRole('button', { name: 'Save Wording' }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it('the dismiss form stays open with the typed reason still in it', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [REVIEW]: { status: 412, body: { error: 'stale_write' } },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }));
    const box = screen.getByLabelText('Why (optional)') as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'duplicated by the run-level remark' } });
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss This Note' }));

    await screen.findByRole('alert');
    const after = screen.getByLabelText('Why (optional)') as HTMLInputElement;
    expect(after.value).toBe('duplicated by the run-level remark');
    expect(screen.getByRole('button', { name: 'Dismiss This Note' })).toBeTruthy();
  });

  it('the mapping form stays open with the chosen field still selected', async () => {
    stubFetchRoutes({
      [NOTES]: {
        body: notesPage([noteFixture()], { mappable_field_paths: ['context.environment'] }),
      },
      [REVIEW]: { status: 412, body: { error: 'stale_write' } },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Map to a field' }));
    fireEvent.change(screen.getByLabelText('Field this note belongs to'), {
      target: { value: 'context.environment' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Map This Note' }));

    await screen.findByRole('alert');
    expect(
      (screen.getByLabelText('Field this note belongs to') as HTMLSelectElement).value,
    ).toBe('context.environment');
  });

  it('a review that WAS recorded still closes its form', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [REVIEW]: {
        body: { note: noteFixture({ state: 'dismissed' }), experiment_version: '1.1' },
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }));
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss This Note' }));

    await screen.findByRole('status');
    // The negative control for the three above: keeping the form open on SUCCESS
    // would satisfy them all and would be its own defect.
    expect(screen.queryByLabelText('Why (optional)')).toBeNull();
  });
});

// --- 9. focus is not dropped when a form closes -------------------------------

/*
 * A form unmounts while focus is on a button inside it, so focus falls to `<body>`
 * and a keyboard user reviewing the third note on a record is returned to the top of
 * the document. The contract is the one `NewExperimentForm` keeps: focus goes back
 * to the control that opened the form.
 */
describe('focus returns to the control that opened the form', () => {
  it('after Cancel', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    renderPanel();

    const trigger = await screen.findByRole('button', { name: 'Dismiss' });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(document.activeElement).toBe(trigger);
  });

  it('after a review that was recorded', async () => {
    stubFetchRoutes({
      [NOTES]: {
        body: notesPage([noteFixture()], { mappable_field_paths: ['context.environment'] }),
      },
      [`POST /api/experiments/${EXP}/notes/${noteFixture().id}/review`]: {
        body: {
          note: noteFixture({ state: 'mapped', mapped_field_path: 'context.environment' }),
          experiment_version: '1.1',
        },
      },
    });
    renderPanel();

    const trigger = await screen.findByRole('button', { name: 'Map to a field' });
    fireEvent.click(trigger);
    fireEvent.change(screen.getByLabelText('Field this note belongs to'), {
      target: { value: 'context.environment' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Map This Note' }));

    await screen.findByRole('status');
    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: 'Map to a field' }),
    );
    expect(document.activeElement).not.toBe(document.body);
  });

  it('and is NOT stolen on first render, when nobody opened anything', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    renderPanel();

    await screen.findByText(noteFixture().text);
    // A first paint that focuses a button nobody pressed is its own defect.
    expect(document.activeElement).toBe(document.body);
  });
});

// --- 10. the mappable list is disclosed as a subset ---------------------------

/*
 * The server offers the 25 paths THIS BUILD can map a note to, which is fewer than
 * the official ISAAC schema defines (`sample.sample_id`, `measurement.qc`,
 * `attribution.uploaded_by`, `links`, `tags` and more are all real and all absent).
 * A scientist who does not find their target and is not told why concludes the note
 * has no home and dismisses it.
 */
describe('the field list says it is a subset', () => {
  it('discloses the shortfall at the control, and names keeping the note instead', async () => {
    stubFetchRoutes({
      [NOTES]: {
        body: notesPage([noteFixture()], { mappable_field_paths: ['context.environment'] }),
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Map to a field' }));
    const hint = await screen.findByText(/not every field in the ISAAC schema/);
    expect(hint.textContent).toContain('the set this version can map a note to');
    // It must not let a missing path be read as a missing schema field…
    expect(hint.textContent).toContain('does not mean the schema has no such field');
    // …and it points at the outcome that loses nothing.
    expect(hint.textContent).toContain('keep it as a note');
  });
});

// --- 7. accessibility ---------------------------------------------------------

describe('accessibility', () => {
  it('the panel is a labelled section with a heading, and the counts are a live region', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    const { container } = renderPanel();

    await screen.findByText(noteFixture().text);
    const section = container.querySelector('section.notes-section');
    expect(section?.getAttribute('aria-labelledby')).toBe('unmapped-notes-heading');
    expect(screen.getByRole('heading', { name: 'Unmapped Notes' })).toBeTruthy();

    const count = container.querySelector('.notes-count');
    expect(count?.getAttribute('aria-live')).toBe('polite');
    expect(count?.getAttribute('aria-atomic')).toBe('true');
  });

  it('the act announcement is a separate live region that exists before it has anything to say', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    renderPanel();

    await screen.findByText(noteFixture().text);
    // MOUNTED while empty. A live region created together with its content is not
    // announced, so this node has to be in the tree from the start.
    const live = screen.getByRole('status');
    expect(live.getAttribute('aria-live')).toBe('polite');
    expect(live.textContent).toBe('');
  });

  it('each action form is a disclosure whose button reports its own state', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    renderPanel();

    const map = await screen.findByRole('button', { name: 'Map to a field' });
    expect(map.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(map);
    expect(map.getAttribute('aria-expanded')).toBe('true');
    // The button points at the form it controls, so the two are associated.
    const controls = map.getAttribute('aria-controls');
    expect(controls).toBeTruthy();
    expect(document.getElementById(controls as string)).toBeTruthy();
  });
});

// --- 12. D2/D3 — a refusal is recoverable, and nothing typed is destroyed -----

/*
 * TWO DEFECTS THAT EVERY TEST ABOVE PASSED THROUGH, and they compounded.
 *
 * D2 — A 412 WAS AN UNRECOVERABLE DEAD END. The success path adopted the new version
 * token from the write's own response; the failure path did not. So one refusal left
 * the held token permanently one revision behind: the next attempt re-sent the same
 * stale validator, was refused again, and there was no gesture on screen that could
 * ever make it succeed. Section 8 above proves the typed text SURVIVES the refusal —
 * which it did — and says nothing about whether the reader can then do anything with
 * it. They could not.
 *
 * AND THE ONE EXIT OFFERED DESTROYED THE TEXT. `Reload This Section` called
 * `reload(false)`, which sets `{status:'loading'}`, unmounts the `<ul>` of note cards,
 * and takes the rewritten wording with it. Changing the `Show` filter still does this,
 * deliberately — see the last test here.
 *
 * D3 — RE-OPENING `Edit wording` OVERWROTE THE REWRITE. The trigger ran
 * `setEditText(note.display_text)` before opening, and `close()` reset every input, so
 * a reader who rewrote a paragraph, checked something under `Dismiss`, and came back
 * lost it — silently, with no confirmation.
 */
describe('a refused review is recoverable, and no gesture destroys what was typed', () => {
  const REVIEW = `POST /api/experiments/${EXP}/notes/${noteFixture().id}/review`;
  /** Set by the review stub in the last case, so the LIST can answer differently
   *  afterwards — the server having moved on is the whole point of that test. */
  let posted = false;
  afterEach(() => {
    posted = false;
  });

  it('adopts the version the 412 reported, so the very next attempt is not refused', async () => {
    let attempts = 0;
    let listReads = 0;
    const ifMatches: (string | undefined)[] = [];
    stubFetchRoutes({
      /*
       * THE FIRST LIST READ ANSWERS; THE REFRESH THE REFUSAL TRIGGERS NEVER DOES, and
       * that is what makes this test about the 412 body rather than about the refresh.
       *
       * A refusal does two things: it adopts the token the server REPORTED, and it
       * kicks off a silent re-read which will bring an even fresher one. If both
       * resolved here, this test would pass on the re-read alone and would prove
       * nothing about the body — so the re-read is held open, which is also a real
       * state: a reader can press the button again before it lands.
       */
      [NOTES]: () => {
        listReads += 1;
        if (listReads === 1) return { body: notesPage([noteFixture()]) };
        return new Promise(() => {}) as never;
      },
      [REVIEW]: (init?: RequestInit) => {
        attempts += 1;
        ifMatches.push((init?.headers as Record<string, string> | undefined)?.['If-Match']);
        // Refused once, with the server's own `current_version` — the same payload
        // `_stale_write` sends, and the same value it echoes as a strong ETag.
        if (attempts === 1) {
          return {
            status: 412,
            body: { error: 'stale_write', current_version: '9.9', current_rev: 9 },
          };
        }
        return {
          body: { note: noteFixture({ state: 'dismissed' }), experiment_version: '9.10' },
        };
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }));
    fireEvent.change(screen.getByLabelText('Why (optional)'), {
      target: { value: 'superseded by the run remark' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss This Note' }));
    const banner = await screen.findByRole('alert');
    expect(banner.textContent ?? '').toMatch(/has picked up the current version/);

    // The retry is the SAME gesture, with nothing reloaded and nothing retyped.
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss This Note' }));
    await screen.findByRole('status');

    expect(attempts).toBe(2);
    // THE ASSERTION THAT CATCHES THE DEFECT: the second write carried the token the
    // server reported, not the stale one it had already refused.
    expect(ifMatches[1]).toBe('"9.9"');
    expect(ifMatches[1]).not.toBe(ifMatches[0]);
  });

  it('says nothing about picking up a version when the refusal did not report one', async () => {
    // The negative control for the test above: a failure that carries no
    // `current_version` must not be reported as a recovery that did not happen.
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [REVIEW]: { status: 500, body: {} },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }));
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss This Note' }));
    const banner = await screen.findByRole('alert');
    expect(banner.textContent ?? '').toMatch(/could not be recorded/);
    expect(banner.textContent ?? '').not.toMatch(/picked up the current version/);
  });

  it('Reload This Section keeps the rewritten wording on screen', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [REVIEW]: { status: 412, body: { error: 'stale_write' } },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Edit wording' }));
    fireEvent.change(screen.getByLabelText('Corrected wording'), {
      target: { value: 'three corrected paragraphs' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Wording' }));
    await screen.findByRole('alert');

    fireEvent.click(screen.getByRole('button', { name: 'Reload This Section' }));
    // The remedy refreshed the list without blanking it, so the card — and the
    // rewrite inside it — was never unmounted.
    expect(
      (await screen.findByLabelText('Corrected wording')) as HTMLTextAreaElement,
    ).toHaveValue('three corrected paragraphs');
  });

  it('re-opening Edit wording finds the rewrite, not the stored wording', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Edit wording' }));
    fireEvent.change(screen.getByLabelText('Corrected wording'), {
      target: { value: 'realigned after scan 3, not before it' },
    });
    // Off to check something else — the gesture that used to lose it.
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByLabelText('Corrected wording')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Edit wording' }));

    expect(screen.getByLabelText('Corrected wording')).toHaveValue(
      'realigned after scan 3, not before it',
    );
  });

  it('Cancel — and only Cancel — discards it', async () => {
    // The negative control: "nothing is ever discarded" would be its own defect,
    // because then there would be no way to abandon an edit at all.
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Edit wording' }));
    fireEvent.change(screen.getByLabelText('Corrected wording'), {
      target: { value: 'abandoned' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    fireEvent.click(screen.getByRole('button', { name: 'Edit wording' }));

    expect(screen.getByLabelText('Corrected wording')).toHaveValue(
      noteFixture().display_text as string,
    );
  });

  it('a recorded edit lets the SERVER’s new wording replace the box', async () => {
    // The other negative control, and the reason the resync exists: once a write has
    // landed the server is authoritative, so a held draft must not outlive it.
    const revised = 'realigned after scan 3, not before it';
    stubFetchRoutes({
      [NOTES]: {
        body: () =>
          notesPage([
            noteFixture(posted ? { revised_text: revised, display_text: revised } : {}),
          ]),
      },
      [REVIEW]: () => {
        posted = true;
        return {
          body: {
            note: noteFixture({ revised_text: revised, display_text: revised }),
            experiment_version: '1.1',
          },
        };
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Edit wording' }));
    fireEvent.change(screen.getByLabelText('Corrected wording'), {
      target: { value: revised },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Wording' }));
    await screen.findByRole('status');

    fireEvent.click(screen.getByRole('button', { name: 'Edit wording' }));
    expect(screen.getByLabelText('Corrected wording')).toHaveValue(revised);
  });
});

// --- 11. the value hint is true of the path in front of the reader ------------

/*
 * D1. This hint used to read, for all 25 mappable paths: "This records where the
 * content belongs. It does not write a value — a value still has to be entered and
 * confirmed on the field itself." Measured over HTTP against every write route the
 * API has, SEVEN of the 25 — the six `system.configuration.*` paths and
 * `timestamps.created_utc` — are refused by all of them. So the panel whose whole
 * purpose is to stop captured content being thrown away told the scientist to go and
 * perform an action the product refuses, and the only thing they could conclude on
 * finding the door locked is that the note has no home.
 *
 * The server now answers per path in `value_writable_field_paths`. These tests assert
 * BOTH polarities, because a hint hard-coded to either sentence would pass a test
 * that only checked one.
 */
describe('the value hint is per path, not on average', () => {
  const MIXED = {
    mappable_field_paths: ['sample.material.name', 'system.configuration.detector_model'],
    value_writable_field_paths: ['sample.material.name'],
  };

  async function openMap() {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()], MIXED) } });
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Map to a field' }));
    return (await screen.findByLabelText('Field this note belongs to')) as HTMLSelectElement;
  }

  it('says nothing about entering a value until a field is chosen', async () => {
    await openMap();
    // The half that is true of every path, and no more. Naming a place to enter a
    // value before a path is chosen would be a claim about a field nobody picked.
    const hint = screen.getByText(/It does not write a value\.$/);
    expect(hint.textContent).toContain('This records where the content belongs');
    expect(hint.textContent).not.toContain('on a run of this record');
    expect(hint.textContent).not.toContain('nowhere to enter one');
  });

  it('for a run-level path, names the RUN as where the value is entered', async () => {
    const select = await openMap();
    fireEvent.change(select, { target: { value: 'sample.material.name' } });

    const hint = screen.getByText(/It does not write a value/);
    // "on a run of this record" — not "on the field itself", which named no screen.
    // This path's only accepting route IS a run's (`POST .../runs/{id}/overrides`),
    // which is why the run sentence is the correct one HERE and not everywhere.
    expect(hint.textContent).toContain('entered and confirmed on a run of this record');
    expect(hint.textContent).not.toContain('nowhere to enter one');
    expect(hint.textContent).not.toContain('No run is needed');
  });

  it('for a path NO write route accepts, says so instead of sending them nowhere', async () => {
    const select = await openMap();
    fireEvent.change(select, { target: { value: 'system.configuration.detector_model' } });

    const hint = screen.getByText(/It does not write a value/);
    expect(hint.textContent).toContain('this version has nowhere to enter one for this field');
    // And it says what mapping DID achieve, so the outcome does not read as a failure.
    expect(hint.textContent).toContain('keeps its text on the record in full');
    // The promise that was false for this path must not survive anywhere in it.
    expect(hint.textContent).not.toContain('on a run of this record');
  });

  it('mapping is still offered and still performed for a path with no write route', async () => {
    const select = await openMap();
    fireEvent.change(select, { target: { value: 'system.configuration.detector_model' } });

    const map = screen.getByRole('button', { name: 'Map This Note' }) as HTMLButtonElement;
    // The honest sentence is a DISCLOSURE, not a new gate: refusing the mapping would
    // discard a scientist's own judgement about where their prose belongs.
    expect(map.disabled).toBe(false);
  });

  /*
   * D2 (2026-08-29). The run sentence above was true of ALL 18 writable paths when it
   * was written, and stopped being true for one of them. `system.technique` is answered
   * at `POST /api/experiments/{id}/answers` and corrected at `.../edit`, which are the
   * RECORD's — measured over HTTP, `{"system.technique": "XAS"}` returns 200 on a record
   * with ZERO runs. So a scientist mapping a note there was told to go and use a run
   * they do not need and may not have. The server now answers per path in
   * `record_writable_field_paths`, and the three outcomes are asserted separately.
   */
  const WITH_RECORD_LEVEL = {
    mappable_field_paths: [
      'system.technique',
      'sample.material.name',
      'system.configuration.detector_model',
    ],
    value_writable_field_paths: ['system.technique', 'sample.material.name'],
    record_writable_field_paths: ['system.technique'],
  };

  async function openMapWith(over: Record<string, string[]>) {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()], over) } });
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Map to a field' }));
    return (await screen.findByLabelText('Field this note belongs to')) as HTMLSelectElement;
  }

  it('for a RECORD-level path, does not send the reader to a run they do not need', async () => {
    const select = await openMapWith(WITH_RECORD_LEVEL);
    fireEvent.change(select, { target: { value: 'system.technique' } });

    const hint = screen.getByText(/It does not write a value/);
    expect(hint.textContent).toContain('entered and confirmed on this record');
    expect(hint.textContent).toContain('No run is needed');
    // THE ASSERTION THAT CARRIES THE FIX. The false sentence must not survive for this
    // path in any form — "on this record" alone would still pass if the run sentence
    // sat beside it, which is how a correction gets rendered next to the claim it
    // retracts.
    expect(hint.textContent).not.toContain('on a run of this record');
    expect(hint.textContent).not.toContain('nowhere to enter one');
  });

  it('and the run-level paths in the SAME payload still say a run', async () => {
    // BOTH POLARITIES FROM ONE SERVER ANSWER, so the record sentence cannot have been
    // achieved by making every hint say it.
    const select = await openMapWith(WITH_RECORD_LEVEL);
    fireEvent.change(select, { target: { value: 'sample.material.name' } });

    const hint = screen.getByText(/It does not write a value/);
    expect(hint.textContent).toContain('entered and confirmed on a run of this record');
    expect(hint.textContent).not.toContain('No run is needed');
  });

  it('a path the server calls record-writable but NOT value-writable still says nowhere', async () => {
    // FAIL-CLOSED ON AN INCONSISTENT SERVER. The real server derives
    // `record_writable_field_paths` as a subset, so this payload cannot occur — but the
    // ORDER the client reads the two keys in decides what happens if it ever does, and
    // the safe answer is the honest one, never "enter it on this record" for a path
    // nothing accepts. That is the locked-door failure this whole hint exists to end.
    const select = await openMapWith({
      mappable_field_paths: ['system.configuration.detector_model'],
      value_writable_field_paths: [],
      record_writable_field_paths: ['system.configuration.detector_model'],
    });
    fireEvent.change(select, { target: { value: 'system.configuration.detector_model' } });

    const hint = screen.getByText(/It does not write a value/);
    expect(hint.textContent).toContain('this version has nowhere to enter one for this field');
    expect(hint.textContent).not.toContain('No run is needed');
  });

  it('the hint the client renders comes from the SERVER, never from a client-side list', async () => {
    // NEGATIVE CONTROL ON THE SOURCE. The server is the only thing that knows which
    // paths a write route accepts; a client that decided for itself would be free to
    // drift the moment either route's admissible set changed. Here the server calls a
    // path writable that a hard-coded client list could not possibly know about.
    stubFetchRoutes({
      [NOTES]: {
        body: notesPage([noteFixture()], {
          mappable_field_paths: ['system.configuration.detector_model'],
          value_writable_field_paths: ['system.configuration.detector_model'],
        }),
      },
    });
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Map to a field' }));
    const select = (await screen.findByLabelText(
      'Field this note belongs to',
    )) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'system.configuration.detector_model' } });

    expect(screen.getByText(/It does not write a value/).textContent).toContain(
      'entered and confirmed on a run of this record',
    );
  });
});

// --- 10. "Propose a value from this note" (PR-D) -------------------------------

describe('propose a value from this note', () => {
  it('happy path: a record-scoped path needs no run, and the write is exactly-once by construction', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { body: proposalsCapabilities() },
      [CREATE_PROPOSAL]: {
        body: {
          proposal: { proposal_id: 'p1', target_field_path: 'system.technique' },
          deduplicated: false,
          experiment_version: 'g1.5',
        },
      },
    });
    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Propose a value from this note' }),
    );
    const fieldSelect = (await screen.findByLabelText(
      'Field this value is for',
    )) as HTMLSelectElement;
    // The server's own list — the paths this build can target — never hardcoded.
    expect(
      within(fieldSelect)
        .getAllByRole('option')
        .map((o) => (o as HTMLOptionElement).value),
    ).toEqual(['', 'context.environment', 'system.technique']);
    fireEvent.change(fieldSelect, { target: { value: 'system.technique' } });
    // Record-scoped: no run selector is offered for it.
    expect(screen.queryByLabelText('Run this value is about')).toBeNull();

    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XAS"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Propose This Value' }));

    await screen.findByText(/Proposal stored\. Review it in Ingestion Proposals\./);
    const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
    const create = calls.find(([, init]) => init?.method === 'POST');
    expect(create).toBeDefined();
    const [, init] = create!;
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    expect(body.note_id).toBe(noteFixture().id);
    expect(body.target_field_path).toBe('system.technique');
    expect(body.proposed_value).toBe('XAS');
    expect(body.run_id).toBeUndefined();
    expect(typeof body.rule).toBe('string');
    expect((body.rule as string).length).toBeGreaterThan(0);
    expect(typeof body.client_request_key).toBe('string');
    expect((init?.headers as Record<string, string>)['If-Match']).toBe('"1.0"');
    // The panel writes NOTHING else — no note review, no field write.
    expect(calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(1);
  });

  it('a run-scoped path requires choosing a run, never inferred from the only one', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { body: proposalsCapabilities() },
      [RUNS]: { body: runsPage([runFixture({ id: 'run-1', label: 'Run 1' })]) },
    });
    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Propose a value from this note' }),
    );
    fireEvent.change(await screen.findByLabelText('Field this value is for'), {
      target: { value: 'context.environment' },
    });
    const runSelect = (await screen.findByLabelText(
      'Run this value is about',
    )) as HTMLSelectElement;
    expect(runSelect.value).toBe('');
    // m13, independent review of PR-D: `context.environment` is a RUN_FIELDS
    // spec (an enum), so it now renders as the typed "Environment" select —
    // never the JSON textarea fallback, which is reserved for paths with no
    // spec at all.
    fireEvent.change(screen.getByLabelText('Environment'), {
      target: { value: 'in_situ' },
    });
    // Submit stays unavailable until a run is chosen — it is required, not optional.
    expect(
      (screen.getByRole('button', { name: 'Propose This Value' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.change(runSelect, { target: { value: 'run-1' } });
    expect(
      (screen.getByRole('button', { name: 'Propose This Value' }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });

  it('F2, INDEPENDENT REVIEW OF PR-D (post-merge): the run picker\'s read is BOUNDED — it asks for RUNS_PAGE_SIZE, never every run on the record', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { body: proposalsCapabilities() },
      [RUNS]: { body: runsPage([runFixture({ id: 'run-1', label: 'Run 1' })]) },
    });
    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Propose a value from this note' }),
    );
    fireEvent.change(await screen.findByLabelText('Field this value is for'), {
      target: { value: 'context.environment' },
    });
    await screen.findByLabelText('Run this value is about');

    const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
    const runsCall = calls.find(([url]) => String(url).includes('/runs'));
    expect(runsCall, 'no request to /runs was made at all').toBeDefined();
    expect(String(runsCall?.[0])).toContain('limit=50');
  });

  it('a run-scoped path with no runs on the record refuses honestly, offering no submit', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { body: proposalsCapabilities() },
      [RUNS]: { body: runsPage([]) },
    });
    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Propose a value from this note' }),
    );
    fireEvent.change(await screen.findByLabelText('Field this value is for'), {
      target: { value: 'context.environment' },
    });
    await screen.findByText(/this record has no runs yet \(or they could not be read\)/);
    expect(screen.queryByLabelText('Run this value is about')).toBeNull();
  });

  it('control absent, with a reason, when this build has no proposable paths', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { body: proposalsCapabilities({ target_field_paths: [] }) },
    });
    renderPanel();

    await screen.findByText(noteFixture().text);
    expect(
      screen.queryByRole('button', { name: 'Propose a value from this note' }),
    ).toBeNull();
    expect(
      await screen.findByText(/this build accepts no proposal target yet/),
    ).toBeInTheDocument();
  });

  it('control absent, with a different reason, when the capability read fails', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { status: 503, body: { error: 'experiment_storage_unavailable' } },
    });
    renderPanel();

    await screen.findByText(noteFixture().text);
    expect(
      screen.queryByRole('button', { name: 'Propose a value from this note' }),
    ).toBeNull();
    expect(
      await screen.findByText(/the set of proposable fields could not be read/),
    ).toBeInTheDocument();
  });

  it('a double submit dedupes to one proposal — the server’s own client_request_key guarantee', async () => {
    // I3b, independent review of PR-D: `creates > 1` only proved a COUNT
    // shape, never the KEY the server actually dedupes on. This now captures
    // both request bodies and pins the property that matters — the identical
    // second submit sends the SAME `client_request_key` as the first, and (in
    // the follow-up case below) a genuinely CHANGED value sends a DIFFERENT
    // one. A mutant that built the key from, say, `Date.now()` would still
    // pass the old assertion (the stub still returns `deduplicated: creates >
    // 1` on the second call) but fails this one.
    // `deduplicated` is now keyed off the ACTUAL `client_request_key` the
    // component sends, not a call counter — so a third submit carrying a
    // genuinely different value (a different key) is correctly answered as a
    // fresh create, not as a repeat of the first.
    const seenKeys = new Set<string>();
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { body: proposalsCapabilities() },
      [CREATE_PROPOSAL]: (init) => {
        const requestBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
        const key = String(requestBody.client_request_key);
        const dup = seenKeys.has(key);
        seenKeys.add(key);
        return {
          body: {
            proposal: { proposal_id: 'p1', target_field_path: 'system.technique' },
            deduplicated: dup,
            experiment_version: 'g1.5',
          },
        };
      },
    });
    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Propose a value from this note' }),
    );
    fireEvent.change(await screen.findByLabelText('Field this value is for'), {
      target: { value: 'system.technique' },
    });
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XAS"' },
    });
    const submit = screen.getByRole('button', { name: 'Propose This Value' });
    fireEvent.click(submit);
    await screen.findByText(/Proposal stored\. Review it in Ingestion Proposals\./);

    // A second identical submit (e.g. the form re-opened and re-sent) is answered
    // `deduplicated: true`, and the panel says so rather than claiming a second
    // create.
    fireEvent.click(
      await screen.findByRole('button', { name: 'Propose a value from this note' }),
    );
    fireEvent.change(await screen.findByLabelText('Field this value is for'), {
      target: { value: 'system.technique' },
    });
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XAS"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Propose This Value' }));
    await screen.findByText(/This value was already proposed from this note/);

    const postCalls = (
      (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][]
    ).filter(([, init]) => init?.method === 'POST');
    expect(postCalls).toHaveLength(2);
    const [firstBody, secondBody] = postCalls.map(
      ([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>,
    );
    expect(typeof firstBody.client_request_key).toBe('string');
    expect(secondBody.client_request_key).toBe(firstBody.client_request_key);

    // Now change the value and submit again — a genuinely different value
    // must mint a genuinely different key, never the one above.
    fireEvent.click(
      await screen.findByRole('button', { name: 'Propose a value from this note' }),
    );
    fireEvent.change(await screen.findByLabelText('Field this value is for'), {
      target: { value: 'system.technique' },
    });
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XRD"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Propose This Value' }));
    await screen.findByText(/Proposal stored\. Review it in Ingestion Proposals\./);

    const postCallsAfterChange = (
      (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][]
    ).filter(([, init]) => init?.method === 'POST');
    expect(postCallsAfterChange).toHaveLength(3);
    const thirdBody = JSON.parse(
      String(postCallsAfterChange[2][1]?.body),
    ) as Record<string, unknown>;
    expect(thirdBody.client_request_key).not.toBe(firstBody.client_request_key);
  });

  it('a 412 reloads the version and says so — nothing is silently lost', async () => {
    let attempts = 0;
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { body: proposalsCapabilities() },
      [CREATE_PROPOSAL]: () => {
        attempts += 1;
        return attempts === 1
          ? { status: 412, body: { error: 'stale_write', current_version: 'g2.0' } }
          : {
              body: {
                proposal: { proposal_id: 'p1', target_field_path: 'system.technique' },
                deduplicated: false,
                experiment_version: 'g2.1',
              },
            };
      },
    });
    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Propose a value from this note' }),
    );
    fireEvent.change(await screen.findByLabelText('Field this value is for'), {
      target: { value: 'system.technique' },
    });
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XAS"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Propose This Value' }));

    await screen.findByText(/picked up the current version and what you typed is still here/);
    // The form is NOT closed and NOT cleared by a refusal — it can be retried.
    expect(
      (screen.getByLabelText('The value, as JSON') as HTMLTextAreaElement).value,
    ).toBe('"XAS"');
  });

  it('refuses a null value locally, without sending a request', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { body: proposalsCapabilities() },
    });
    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Propose a value from this note' }),
    );
    fireEvent.change(await screen.findByLabelText('Field this value is for'), {
      target: { value: 'system.technique' },
    });
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: 'null' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Propose This Value' }));

    await screen.findByText(/A null value cannot be proposed here/);
    const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
    expect(calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(0);
  });

  /*
   * MUTATION-GUARDED. Removing the lazy-fetch guard in `ensureRunsForPropose`
   * (`runsForProposeFetchedRef`) would issue a SECOND `GET .../runs` for the
   * SAME mount the moment a reader closed and reopened the propose form — this
   * is the negative control pinning that it stays at one.
   */
  it('MUTATION-GUARDED: the run list is fetched at most once per mount, even across repeated opens', async () => {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { body: proposalsCapabilities() },
      [RUNS]: { body: runsPage([runFixture({ id: 'run-1', label: 'Run 1' })]) },
    });
    renderPanel();

    const openClose = async () => {
      fireEvent.click(
        await screen.findByRole('button', { name: 'Propose a value from this note' }),
      );
      fireEvent.change(await screen.findByLabelText('Field this value is for'), {
        target: { value: 'context.environment' },
      });
      await screen.findByLabelText('Run this value is about');
      fireEvent.click(
        screen.getByRole('button', { name: 'Propose a value from this note' }),
      );
    };
    await openClose();
    await openClose();

    await waitFor(() => {
      const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
      const runReads = calls.filter(([url]) => String(url).includes('/runs'));
      expect(runReads.length).toBe(1);
    });
  });

  it('the run list is NOT fetched at all when nothing has opened the propose form', async () => {
    // The regression this guards: an eager mount-time fetch here doubled the read
    // `RunsSection` already performs on the real Record Workbench, breaking
    // `runs-live-refresh-integration.test.tsx`'s "first paint reads the runs ONCE".
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture()]) },
      [PROPOSALS]: { body: proposalsCapabilities() },
    });
    renderPanel();
    await screen.findByText(noteFixture().text);

    const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
    expect(calls.some(([url]) => String(url).includes('/runs'))).toBe(false);
  });
});

// --- F-1: a note minted elsewhere on this screen appears without a manual reload --
//
// `docs/session-closure-2026-09-03.md` §8 named this residue: a note minted by a
// Finalize on `TranscriptCapturePanel` — a SIBLING panel on the same screen — used
// to appear here only after a manual reload, while the proposals that same
// Finalize mints appeared live on `IngestionProposalsPanel`. `activity` is the
// shared `useChangeFeed` summary threaded from `RecordWorkbench` via
// `useRecordSession.notesActivity` — never a second poller instantiated by this
// panel. See `UnmappedNotesPanel`'s own doc comment on the prop for the full
// argument, including why the underlying signal is a deliberately IMPRECISE one
// (there is no `note` change-feed kind; this rides on the record's own
// `experiment` entry).
describe('F-1: a change-feed record-moved entry refreshes the notes list', () => {
  /*
   * INDEPENDENT REVIEW (I-1): THE "REPRODUCTION" TEST THAT USED TO OPEN THIS BLOCK
   * IS REMOVED, NOT RENAMED. It asserted that a component given NO signal issues
   * no second read — true by construction of the prop contract, and true on the
   * FIXED build exactly as it would have been on a hypothetical unfixed one, so it
   * could never fail and was not a reproduction. F-1 is a defect in the SCREEN's
   * wiring (`RecordWorkbench` never threaded a prop for this panel to react to at
   * all), and only a test that mounts the real screen can fail on the unfixed
   * shape and pass on the fixed one — see
   * `apps/web/src/__tests__/notes-live-refresh-integration.test.tsx`, modelled on
   * `runs-live-refresh-integration.test.tsx`'s own header for exactly this
   * distinction ("a colleague's run edit moved no pixel... neither branch's tests
   * mount the screen that wires them").
   */
  it('THE FIX: a record-moved entry refreshes the list, updates it visibly, and does NOT destroy a half-typed capture', async () => {
    let reads = 0;
    stubFetchRoutes({
      [NOTES]: () => {
        reads += 1;
        return {
          body:
            reads === 1
              ? notesPage([noteFixture()], { total: 1 })
              : notesPage([noteFixture(), noteFixture({ id: 'second-note' })], { total: 2 }),
        };
      },
    });
    const view = renderPanel(null);
    await screen.findByText(/1 note on this record/);

    // A scientist is mid-way through typing an unrelated note when the arrival
    // happens — this is the exact promise `CLAUDE.md` §11 records this repository
    // breaking three times: an input must survive a background refresh.
    fireEvent.change(screen.getByLabelText('Capture a note'), {
      target: { value: 'half-typed note about the beam' },
    });

    // The change-feed delivers a `recordMoved` summary — the shape
    // `useRecordSession.notesActivity` produces.
    view.rerender(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <UnmappedNotesPanel experimentId={EXP} activity={recordMovedActivityFor(9)} />
      </MemoryRouter>,
    );

    // VISIBLY UPDATED: the count line moves to what the second read reported.
    await screen.findByText(/2 notes on this record/);
    expect(reads).toBe(2);

    // AND THE LIVE VALUE OF THE REAL TEXTAREA IS UNTOUCHED.
    expect(
      (screen.getByLabelText('Capture a note') as HTMLTextAreaElement).value,
    ).toBe('half-typed note about the beam');
    view.unmount();
  });

  it('raises no notice of its own — the existing live count line already speaks the new total', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()], { total: 1 }) } });
    const view = renderPanel(null);
    await screen.findByText(/1 note on this record/);

    view.rerender(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <UnmappedNotesPanel experimentId={EXP} activity={recordMovedActivityFor(9)} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
      expect(calls.filter(([url]) => String(url).endsWith('/notes')).length).toBe(2);
    });

    // Two notices for one fact would be the defect; this panel refreshes silently
    // and the sr-only act-announcement region stays exactly what it was — empty.
    expect(screen.queryByRole('alert')).toBeNull();
    const status = screen.getByRole('status');
    expect(status.textContent).toBe('');
    view.unmount();
  });

  it('does not re-read when the same position is reported twice', async () => {
    let reads = 0;
    stubFetchRoutes({
      [NOTES]: () => {
        reads += 1;
        return { body: notesPage([noteFixture()]) };
      },
    });
    const view = renderPanel(null);
    await screen.findByText(noteFixture().text);
    expect(reads).toBe(1);

    const same = recordMovedActivityFor(9);
    for (const activity of [same, { ...same }]) {
      view.rerender(
        <MemoryRouter
          initialEntries={['/']}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <UnmappedNotesPanel experimentId={EXP} activity={activity} />
        </MemoryRouter>,
      );
    }

    await waitFor(() => expect(reads).toBe(2));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(reads).toBe(2); // the duplicate delivered no news, so no second read
    view.unmount();
  });

  it('re-reads when the record moves again at a later position', async () => {
    let reads = 0;
    stubFetchRoutes({
      [NOTES]: () => {
        reads += 1;
        return { body: notesPage([noteFixture()]) };
      },
    });
    const view = renderPanel(null);
    await screen.findByText(noteFixture().text);

    for (const rev of [9, 11]) {
      view.rerender(
        <MemoryRouter
          initialEntries={['/']}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <UnmappedNotesPanel experimentId={EXP} activity={recordMovedActivityFor(rev)} />
        </MemoryRouter>,
      );
    }

    await waitFor(() => expect(reads).toBe(3));
    view.unmount();
  });

  it('a caller that never threads the prop at all (activity omitted) behaves exactly as `activity={null}`', async () => {
    // `activity` is optional on `UnmappedNotesPanel` itself (not just on
    // `NotesBrowser`), so a mount that predates this change — or a test that never
    // updates its call site — degrades to manual-reload-only rather than crashing.
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <UnmappedNotesPanel experimentId={EXP} />
      </MemoryRouter>,
    );
    await screen.findByText(noteFixture().text);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  /*
   * THE NEGATIVE CONTROL, and it is part of the guarantee rather than decoration.
   *
   * Without it a passing suite cannot distinguish "the input is protected" from
   * "the refresh never happened", and the second reads identically to the first.
   * The only way a test can destroy state owned by `CaptureNote` from outside is
   * to unmount it — a blanking (non-silent) reload would do exactly that — so the
   * control performs that unmount and proves the positive assertion above FAILS
   * against it.
   */
  it('NEGATIVE CONTROL: the same assertion fails when the panel is unmounted', async () => {
    stubFetchRoutes({ [NOTES]: { body: notesPage([noteFixture()]) } });
    const view = renderPanel(null);
    fireEvent.change(await screen.findByLabelText('Capture a note'), {
      target: { value: 'half-typed note about the beam' },
    });

    view.unmount();
    renderPanel(null);
    await screen.findByText(noteFixture().text);

    // The box is not even on screen with its old value — this is what the positive
    // test above would look like on a build that blanked the panel to refresh.
    expect(
      (screen.getByLabelText('Capture a note') as HTMLTextAreaElement).value,
    ).toBe('');
  });

  /*
   * I-2, INDEPENDENT REVIEW. Before this fix, `UnmappedNotesPanel.tsx`'s fetch
   * effect set `{status: 'error'}` on ANY failure, silent or not — so a background
   * reload that failed replaced the whole `<ul>` with `BackendDown`, taking an
   * open "Edit wording" box and its rewrite down with it, reachable with no
   * reader action at all. The comment directly above the change-feed effect
   * claimed this could not happen ("never blanks it"); the reviewer measured that
   * the claim was false for the failure path. This test is what makes the claim
   * true: a silent reload that fails must leave everything open and typed exactly
   * where it was, in BOTH places that hold unsaved input — the composer and an
   * open editor — and must disclose the failure without destroying anything.
   */
  it('I-2: a background reload that FAILS does not destroy an open editor or the composer', async () => {
    let reads = 0;
    stubFetchRoutes({
      [NOTES]: () => {
        reads += 1;
        // First read (mount) succeeds; every read after that — which is the
        // activity-triggered background one — fails.
        if (reads === 1) return { body: notesPage([noteFixture()]) };
        return { status: 503, body: { error: 'experiment_storage_unavailable' } };
      },
    });
    const view = renderPanel(null);
    await screen.findByText(noteFixture().text);

    // Unsaved input in TWO places: the always-visible composer, and an open
    // per-note form.
    fireEvent.change(screen.getByLabelText('Capture a note'), {
      target: { value: 'half-typed note about the beam' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Edit wording' }));
    fireEvent.change(screen.getByLabelText('Corrected wording'), {
      target: { value: 'a half-written rewrite, not yet saved' },
    });

    // The change feed delivers a record-moved summary — the same trigger the
    // positive `THE FIX` test above uses — and this read is stubbed to fail.
    view.rerender(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <UnmappedNotesPanel experimentId={EXP} activity={recordMovedActivityFor(9)} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(reads).toBe(2));

    // NOTHING WAS DESTROYED. The original note is still on screen (not replaced
    // by `BackendDown`), and both unsaved inputs survive verbatim.
    expect(screen.getByText(noteFixture().text)).toBeTruthy();
    expect(
      (screen.getByLabelText('Capture a note') as HTMLTextAreaElement).value,
    ).toBe('half-typed note about the beam');
    expect(
      (screen.getByLabelText('Corrected wording') as HTMLTextAreaElement).value,
    ).toBe('a half-written rewrite, not yet saved');

    // AND THE FAILURE IS DISCLOSED, not silent about being silent — visibly, and
    // (since the C1 fix below) spoken through the permanently-mounted
    // `role="status"` region too, which is why the sentence is now matched with a
    // selector: it is deliberately on screen in two places at once.
    expect(
      await screen.findByText(/A background refresh of this list did not complete/, {
        selector: NOTICE,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole('status').textContent).toMatch(
      /A background refresh of this list did not complete/,
    );
    view.unmount();
  });

  /*
   * THE NEGATIVE CONTROL for I-2 — without it, a build that (wrongly) treated
   * every failure as loud would ALSO leave `noteFixture().text` findable, because
   * `BackendDown` renders its own text and the assertion above never looks for
   * `BackendDown`'s own marker. This proves the destructive path really does
   * destroy what the positive test checks, by forcing exactly that path.
   */
  it('NEGATIVE CONTROL: a LOUD failure (the first read itself) shows BackendDown, not the note', async () => {
    stubFetchRoutes({
      [NOTES]: { status: 503, body: { error: 'experiment_storage_unavailable' } },
    });
    renderPanel(null);

    await screen.findByText(/Backend Not Running/);
    // The list content is gone — replaced by `BackendDown`, not disclosed beside
    // it. `CaptureNote` itself is unconditionally rendered even here (D2's own
    // rule: nothing removes the box while `version` is unknown; its SUBMIT button
    // is disabled instead), so the meaningful absence is the note's OWN text, not
    // the composer's presence.
    expect(screen.queryByText(noteFixture().text)).toBeNull();
    fireEvent.change(screen.getByLabelText('Capture a note'), { target: { value: 'x' } });
    expect(screen.getByRole('button', { name: 'Capture Note' })).toBeDisabled();
  });
});

// --- 15. C1 — the silent branch must not swallow a failure it has nothing to protect ---

/*
 * THE DEFECT, AND WHY IT IS FILED HERE A SECOND TIME.
 *
 * I-2 above stopped a failing SILENT reload from replacing the whole panel with
 * `BackendDown`. `IngestionProposalsPanel` was then given the same fix, modelled
 * explicitly on this one — and its independent review (C1) found that the fix, as
 * written in both files, carried a Critical regression. It was fixed in the sibling
 * and left standing here.
 *
 * `wasSilent` is the INTENT of a request ("do not blank the list while this runs").
 * It is NOT evidence that anything is currently on screen to protect. A silent
 * reload can begin while the very first, LOUD load is still in flight;
 * `generationRef` then discards the loud response; and if the silent one fails, the
 * `.catch` returned with no `setList` call at all — leaving `list` at
 * `{status: 'loading'}` FOREVER. The disclosure is suppressed too, because the
 * notice renders only over a loaded list. A permanent spinner, no error, no retry,
 * no recovery short of navigating away.
 *
 * WHICH TRIGGERS ARE REACHABLE **HERE** — measured on this panel, not inherited from
 * the sibling's report, because the two panels differ:
 *
 *   - THE `Show` FILTER: REACHABLE. The toolbar and its `<select>` render during
 *     `'loading'` and are not disabled. Measured before the fix:
 *     `{spinner: true, alert: false, notice: false, buttons: ['Capture Note']}`.
 *   - A CHANGE-FEED `activity` SIGNAL: **NOT** reachable, unlike in the sibling.
 *     This panel's activity effect is gated on `version !== null`, and `version` is
 *     set only alongside `{status: 'data'}` — so no feed signal can start a reload
 *     before the first load has succeeded. Pinned by its own test below.
 */
describe('C1: a silent reload that fails before anything has ever loaded', () => {
  it(
    'REPRODUCTION: a Show-filter change that supersedes an in-flight FIRST load, and ' +
      'then fails, shows BackendDown rather than a permanent silent spinner',
    async () => {
      let failed = 0;
      stubFetchRoutes({
        [PROPOSALS]: { body: proposalsCapabilities() },
        // The first, LOUD load never resolves — it is still in flight when the
        // reader touches the filter, and `generationRef` discards it afterwards.
        [NOTES]: () => new Promise(() => {}) as never,
        [`${NOTES}?state=mapped`]: () => {
          failed += 1;
          return { status: 503, body: { error: 'experiment_storage_unavailable' } };
        },
      });
      const view = renderPanel(null);
      await screen.findByText(/Loading this record's unmapped notes/);

      // The reader changes `Show` before that first load has resolved. This is a
      // SILENT reload (see the `onChange` comment) and it supersedes the first.
      fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'mapped' } });
      await waitFor(() => expect(failed).toBe(1));

      // NOT a permanent spinner. The full `BackendDown` panel appears, because
      // `listStatusRef.current` was `'loading'` — nothing had ever succeeded, so
      // there was nothing to protect and this correctly took the LOUD path.
      expect(await screen.findByText(/Backend Not Running/)).toBeTruthy();
      expect(screen.queryByText(/Loading this record's unmapped notes/)).toBeNull();
      expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
      // And the non-destructive notice is NOT also showing beside it — the two are
      // mutually exclusive by design.
      expect(
        screen.queryByText(/A background refresh of this list did not complete/),
      ).toBeNull();
      expect(screen.queryByText(/could not be applied, so it is still showing/)).toBeNull();
      view.unmount();
    },
  );

  it(
    'the OTHER trigger is closed here by the version gate: a feed signal during an ' +
      'in-flight first load issues no second read at all',
    async () => {
      /*
       * This is a property of THIS panel, and it is the reason the sibling's PROBE
       * does not reproduce here. If the `version !== null` gate on the activity
       * effect is ever removed, this test fails — and the reproduction above is
       * then what keeps the removal from reintroducing the permanent spinner,
       * because `listStatusRef` catches the trigger whatever set it in motion.
       */
      let reads = 0;
      stubFetchRoutes({
        [PROPOSALS]: { body: proposalsCapabilities() },
        [NOTES]: () => {
          reads += 1;
          return new Promise(() => {}) as never;
        },
      });
      const view = renderPanel(null);
      await screen.findByText(/Loading this record's unmapped notes/);

      view.rerender(
        <MemoryRouter
          initialEntries={['/']}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <UnmappedNotesPanel experimentId={EXP} activity={recordMovedActivityFor(9)} />
        </MemoryRouter>,
      );
      await new Promise((resolve) => setTimeout(resolve, 30));
      expect(reads).toBe(1);
      view.unmount();
    },
  );
});

// --- 16. a failed Show-filter change says the filter was not applied -----------

describe('a Show-filter change that fails', () => {
  /*
   * MEASURED BEFORE THIS CHANGE: after a failing change to `Mapped`, the `<select>`
   * read `mapped` while the unfiltered note was still on screen, and the only
   * disclosure said the list "may be out of date". Both halves were wrong — the
   * list is exactly as up to date as it was, and the view the reader asked for was
   * never applied at all.
   */
  it('names the filter as unapplied, keeps the previous list, and offers a retry', async () => {
    let mappedReads = 0;
    stubFetchRoutes({
      [PROPOSALS]: { body: proposalsCapabilities() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [`${NOTES}?state=mapped`]: () => {
        mappedReads += 1;
        return { status: 503, body: { error: 'experiment_storage_unavailable' } };
      },
    });
    renderPanel(null);
    await screen.findByText(noteFixture().text);

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'mapped' } });
    await waitFor(() => expect(mappedReads).toBe(1));

    // THE SENTENCE IS THE VIEW-CHANGE ONE, not the generic staleness one.
    expect(
      await screen.findByText(/Show filter could not be applied, so it is still showing/, {
        selector: NOTICE,
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/A background refresh of this list did not complete/),
    ).toBeNull();

    // NOTHING WAS DESTROYED, and the control is deliberately NOT reverted — so
    // "Try Again" retries the view the reader actually asked for.
    expect(screen.getByText(noteFixture().text)).toBeTruthy();
    expect((screen.getByLabelText('Show') as HTMLSelectElement).value).toBe('mapped');
    expect(screen.getByRole('button', { name: 'Try Again' })).toBeTruthy();
  });

  it('THE RETRY CONTROL IS REAL: Try Again re-issues the CURRENT view and clears the notice', async () => {
    /*
     * Pinned because in the sibling panel, deleting the equivalent control
     * entirely passed every test in its file. Deleting `Try Again` here, or
     * pointing it at `reload(false)`, or having it re-request the pre-change
     * filter, each fails this test.
     */
    let mappedReads = 0;
    stubFetchRoutes({
      [PROPOSALS]: { body: proposalsCapabilities() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [`${NOTES}?state=mapped`]: () => {
        mappedReads += 1;
        if (mappedReads === 1) {
          return { status: 503, body: { error: 'experiment_storage_unavailable' } };
        }
        return {
          body: notesPage(
            [
              noteFixture({
                id: 'mapped-note',
                text: 'a mapped note',
                display_text: 'a mapped note',
                state: 'mapped',
              }),
            ],
            { total: 1 },
          ),
        };
      },
    });
    renderPanel(null);
    await screen.findByText(noteFixture().text);

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'mapped' } });
    await screen.findByText(/Show filter could not be applied/, { selector: NOTICE });

    // Something typed, to prove the retry is silent and destroys nothing.
    fireEvent.change(screen.getByLabelText('Capture a note'), {
      target: { value: 'half-typed note about the beam' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Try Again' }));
    // IT RETRIED `?state=mapped`, i.e. the view the reader asked for, not the one
    // that was on screen — and the read that succeeded cleared the disclosure.
    await waitFor(() => expect(mappedReads).toBe(2));
    expect(await screen.findByText('a mapped note')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText(/Show filter could not be applied/, { selector: NOTICE })).toBeNull(),
    );
    expect(
      (screen.getByLabelText('Capture a note') as HTMLTextAreaElement).value,
    ).toBe('half-typed note about the beam');
  });

  it('the disclosure is SPOKEN through the permanently-mounted region, not by the notice itself', async () => {
    /*
     * A conditionally-mounted `aria-live` region is never announced — this panel's
     * own `.notes-count` comment states that rule, and the first version of this
     * notice broke it. So the notice element must carry no `aria-live` and no
     * `role`, and the sentence must reach the `role="status"` region that is
     * mounted from first paint.
     */
    stubFetchRoutes({
      [PROPOSALS]: { body: proposalsCapabilities() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [`${NOTES}?state=mapped`]: {
        status: 503,
        body: { error: 'experiment_storage_unavailable' },
      },
    });
    const { container } = renderPanel(null);
    await screen.findByText(noteFixture().text);

    const live = screen.getByRole('status');
    expect(live.textContent).toBe('');

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'mapped' } });
    const notice = await screen.findByText(/Show filter could not be applied/, {
      selector: NOTICE,
    });

    // The VISIBLE notice is not itself a live region.
    const noticeEl = notice.closest('.notes-background-refresh-notice');
    expect(noticeEl).toBeTruthy();
    expect(noticeEl?.getAttribute('aria-live')).toBeNull();
    expect(noticeEl?.getAttribute('role')).toBeNull();

    // The SPOKEN half reached the already-mounted region — which is the same node
    // as before, not a remount.
    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toMatch(
        /Show filter could not be applied/,
      ),
    );
    expect(screen.getByRole('status')).toBe(live);
    expect(container.querySelectorAll('p[role="status"]').length).toBe(1);
  });

  it('the SAME sentence twice in a row still changes the spoken region', async () => {
    /*
     * Two failed attempts produce a byte-identical string; a `role="status"`
     * region announces a CHANGE to its content, so without the alternating marker
     * the second failure is announced to nobody.
     */
    stubFetchRoutes({
      [PROPOSALS]: { body: proposalsCapabilities() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [`${NOTES}?state=mapped`]: {
        status: 503,
        body: { error: 'experiment_storage_unavailable' },
      },
    });
    renderPanel(null);
    await screen.findByText(noteFixture().text);

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'mapped' } });
    await screen.findByText(/Show filter could not be applied/, { selector: NOTICE });
    const first = screen.getByRole('status').textContent;

    fireEvent.click(screen.getByRole('button', { name: 'Try Again' }));
    await waitFor(() => expect(screen.getByRole('status').textContent).not.toBe(first));
    // Asserted as an INEQUALITY between two observed contents, not as the presence
    // of a marker character: any mechanism that makes the region change passes.
    //
    // AND THE SENTENCE IS STILL THE VIEW-CHANGE ONE. This is where the sibling's
    // `viewChangeRef` mechanism silently degraded: "Try Again" is `reload(true)`
    // and sets no such flag, so the SECOND failure for the SAME unapplied view
    // reported plain staleness while the `<select>` still disagreed with the list.
    // Deciding by `filter` vs `loadedFilterRef` is what keeps it true across a
    // retry — revert that comparison and this assertion fails.
    expect(screen.getByRole('status').textContent).toMatch(
      /Show filter could not be applied/,
    );
    expect(
      screen.getByText(/Show filter could not be applied/, { selector: NOTICE }),
    ).toBeInTheDocument();
  });

  it('the notice never renders over a blanked list: Show All Notes is LOUD and hides it', async () => {
    /*
     * THE RENDER-TIME `list.status === 'data'` GATE IS STILL LOAD-BEARING HERE,
     * unlike in `IngestionProposalsPanel` where the equivalent is now only
     * defensive. `backgroundRefreshError` is cleared only by a later SUCCESSFUL
     * read, and `Show All Notes` in the empty state issues a LOUD reload — so the
     * sentence is still set while `list` moves to `'loading'`. Removing the
     * conjunct renders "Nothing you have open or typed here was affected" over the
     * spinner of a list that has just been blanked. This test kills that mutation.
     */
    let allReads = 0;
    stubFetchRoutes({
      [PROPOSALS]: { body: proposalsCapabilities() },
      [NOTES]: () => {
        allReads += 1;
        // The first, loud mount read succeeds; the later loud read caused by
        // `Show All Notes` never resolves, so the spinner stays up to be observed.
        if (allReads === 1) return { body: notesPage([noteFixture()], { total: 1 }) };
        return new Promise(() => {}) as never;
      },
      // The filtered view is EMPTY but SUCCEEDS, which is what renders `EmptyNotes`
      // and its `Show All Notes` control.
      [`${NOTES}?state=mapped`]: {
        body: notesPage([], { total: 1, by_state: { mapped: 0 } }),
      },
    });
    const view = renderPanel(null);
    await screen.findByText(noteFixture().text);

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'mapped' } });
    const clear = await screen.findByRole('button', { name: 'Show All Notes' });

    // A background refresh now fails while that empty filtered view is on screen.
    // `?state=mapped` is re-requested by the activity reload and still succeeds, so
    // force the failure by pointing the feed reload at a failing response.
    stubFetchRoutes({
      [PROPOSALS]: { body: proposalsCapabilities() },
      [NOTES]: () => new Promise(() => {}) as never,
      [`${NOTES}?state=mapped`]: {
        status: 503,
        body: { error: 'experiment_storage_unavailable' },
      },
    });
    view.rerender(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <UnmappedNotesPanel experimentId={EXP} activity={recordMovedActivityFor(9)} />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText(/A background refresh of this list did not complete/, {
        selector: NOTICE,
      }),
    ).toBeInTheDocument();

    // Now the LOUD reload. The list blanks, and the notice must go with it.
    fireEvent.click(clear);
    expect(await screen.findByText(/Loading this record's unmapped notes/)).toBeTruthy();
    expect(
      screen.queryByText(/A background refresh of this list did not complete/, {
        selector: NOTICE,
      }),
    ).toBeNull();
    view.unmount();
  });
});
