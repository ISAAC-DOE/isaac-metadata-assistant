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
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { UnmappedNotesPanel } from '../components/UnmappedNotesPanel';
import {
  noteFixture,
  notesEmpty,
  notesPage,
  stubFetchRoutes,
} from '../test/apiFixtures';

const EXP = 'demo';
const NOTES = `GET /api/experiments/${EXP}/notes`;

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPanel() {
  return render(
    <MemoryRouter
      initialEntries={['/']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <UnmappedNotesPanel experimentId={EXP} />
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
