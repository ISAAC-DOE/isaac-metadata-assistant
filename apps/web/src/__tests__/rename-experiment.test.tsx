/*
 * NAME AND NOTE — the rename affordance, and the three ways it could quietly destroy
 * text a scientist typed.
 *
 * THE FINDING THIS CLOSES. `title` was written exactly once, by the create form, and
 * `source.description` was written once and published by no read at all. Where a
 * deployment stores experiments durably — the hosted one does — a typo in either was a
 * permanent property of a stored record, and the note could never even be seen.
 *
 * WHAT THIS FILE PINS, and every item is honesty rather than layout:
 *
 *   1. the affordance is REACHABLE — a button in the tab order, not a disclosure the
 *      reader has to find, because "no affordance existed" was the whole finding;
 *   2. a rename sends ONLY the field that changed. Sending both keys unconditionally
 *      would make every title correction also rewrite the note, and the server reads
 *      an absent key as "leave it alone" — so what is on the wire is asserted, not
 *      just the outcome;
 *   3. an UNKNOWN note (an older deployment that reports no `description`) is NOT
 *      rendered as an empty box. A blank box over a value we were never shown is a
 *      Save that destroys real text, and the control is withheld instead;
 *   4. nothing typed is ever truncated. Neither control carries `maxLength`; over the
 *      limit the form refuses in words and keeps the text;
 *   5. a `412` — someone else changed the record — gets its own sentence, because
 *      "could not be saved" would leave the reader retrying against a validator that
 *      will refuse again;
 *   6. the panel offers NO discard control, and that absence is asserted rather than
 *      assumed. No committed sentence authorises removing an experiment row, and a UI
 *      that hinted otherwise would be promising something that does not exist.
 *
 * `stubFetchRoutes` REJECTS any route it was not given, so the route map in each test
 * is itself a structural assertion: a map without the PATCH proves a rendering test
 * writes nothing.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { RecordNamePanel } from '../components/RecordNamePanel';
import { LABELS } from '../lib/labels';
import { stubFetchRoutes, type RouteEntry } from '../test/apiFixtures';
import type { ApiExperimentDetail } from '../lib/types';

const ID = '01SYNTHRENAMEEXP0000000000';
const TYPO = 'Ni foil calibraton';
const FIXED = 'Ni foil calibration';

afterEach(() => {
  vi.unstubAllGlobals();
});

function detail(over: Partial<ApiExperimentDetail> = {}): ApiExperimentDetail {
  return {
    id: ID,
    title: TYPO,
    status: 'needs_attention',
    created_utc: '2099-04-02T09:00:00Z',
    pending_count: 3,
    evidenced_field_count: 0,
    exported: false,
    record_id: null,
    rev: 1,
    updated_utc: '2099-04-02T09:15:00Z',
    version: 'gen1.1',
    draft_ok: false,
    artifact_refs: { record_filename: null, sidecar_filename: null },
    source_files: [],
    description: 'the note as first typed',
    workflow: { steps: [], current_step: 'complete_metadata' } as unknown as ApiExperimentDetail['workflow'],
    artifact: { state: 'none', reason: null },
    ...over,
  } as ApiExperimentDetail;
}

const PATCH_KEY = `PATCH /api/experiments/${ID}`;

/**
 * The panel under a router.
 *
 * `stubFetchRoutes` returns the request KEYS only, so the PATCH's own `init` is
 * captured by the route thunk itself — which is the only place it exists. That is
 * load-bearing for this file rather than incidental: several assertions below are
 * about the BODY (which keys are present, which are deliberately absent), and a test
 * that could only see "a PATCH happened" would pass over exactly the defect that
 * matters — a rename that also rewrote a note the reader never mentioned.
 */
function mount(
  over: Partial<ApiExperimentDetail> = {},
  patchResult?: () => { status?: number; body?: unknown },
) {
  const saved = vi.fn();
  const sent: RequestInit[] = [];
  const routes: Record<string, RouteEntry> = {};
  if (patchResult) {
    routes[PATCH_KEY] = (init?: RequestInit) => {
      if (init) sent.push(init);
      return patchResult();
    };
  }
  const calls = stubFetchRoutes(routes);
  render(
    <MemoryRouter>
      <RecordNamePanel detail={detail(over)} onSaved={saved} />
    </MemoryRouter>,
  );
  return { saved, calls, sent };
}

/** The single PATCH body the stub received, parsed. */
function patchBody(sent: RequestInit[]): Record<string, unknown> {
  expect(sent.length, 'expected exactly one PATCH request').toBe(1);
  return JSON.parse(String(sent[0].body));
}

/** The happy PATCH: the record as it reads after the rename. */
const okPatch = () => ({ body: detail({ title: FIXED }) });

// =============================================================================
// 1. the affordance exists and is reachable
// =============================================================================

describe('the rename affordance', () => {
  it('shows the current name and note without any disclosure to open first', () => {
    mount();
    // The section heading, the two labelled values, and the control — all present on
    // arrival. A collapsed section would satisfy none of these.
    expect(screen.getByText(LABELS.renameRecordSection)).toBeTruthy();
    expect(screen.getByText(TYPO)).toBeTruthy();
    expect(screen.getByText('the note as first typed')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    ).toBeTruthy();
  });

  it('names its labels in the markup rather than only in the visual column', () => {
    mount();
    // A definition list, so a screen reader pairs each label with its value instead
    // of announcing four unrelated lines.
    const nameLabel = screen.getByText(LABELS.renameRecordNameLabel);
    expect(nameLabel.tagName).toBe('DT');
    expect(screen.getByText(LABELS.renameRecordNoteLabel).tagName).toBe('DT');
  });

  it('says a rename never invalidates the exported record', () => {
    // This is the sentence that makes the correction feel safe on an EXPORTED record,
    // and it is true: the server's freshness check compares record content and
    // neither field reaches a record. If that ever stops being true the backend test
    // `test_renaming_an_exported_record_leaves_its_artifact_current` goes red — this
    // one pins that the claim is actually shown to the reader.
    mount({ exported: true, record_id: ID, artifact: { state: 'current', reason: null } });
    expect(screen.getByText(LABELS.renameRecordHint)).toBeTruthy();
  });

  it('offers no discard, delete or remove control anywhere', () => {
    // Asserted rather than assumed. No committed sentence authorises removing an
    // experiment row, and a control that implied one exists would be advertising a
    // capability the API does not publish.
    mount();
    for (const name of [/discard/i, /delete/i, /remove/i, /archive/i]) {
      expect(screen.queryByRole('button', { name })).toBeNull();
    }
  });

  it('opens a form whose fields are prefilled from the record', () => {
    mount();
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    const title = screen.getByLabelText(LABELS.renameRecordNameLabel) as HTMLInputElement;
    const note = screen.getByLabelText(LABELS.renameRecordNoteLabel) as HTMLTextAreaElement;
    expect(title.value).toBe(TYPO);
    expect(note.value).toBe('the note as first typed');
    // NEITHER CONTROL CARRIES `maxLength`: it truncates a pasted paragraph silently,
    // and the reader's next act would be to save text missing its end (D5).
    expect(title.getAttribute('maxLength')).toBeNull();
    expect(note.getAttribute('maxLength')).toBeNull();
  });
});

// =============================================================================
// 2. what goes on the wire
// =============================================================================

describe('what a rename sends', () => {
  it('sends ONLY the title when only the title changed', async () => {
    const { sent, saved } = mount({}, okPatch);
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNameLabel), {
      target: { value: FIXED },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    const body = patchBody(sent);
    expect(body).toEqual({ title: FIXED });
    // THE ABSENCE IS THE ASSERTION. The server reads a missing key as "leave that
    // field alone", so a body carrying `description` here would rewrite a note the
    // reader never mentioned.
    expect('description' in body).toBe(false);
  });

  it('sends ONLY the note when only the note changed', async () => {
    const { sent, saved } = mount({}, okPatch);
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNoteLabel), {
      target: { value: 'the corrected note' },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(patchBody(sent)).toEqual({ description: 'the corrected note' });
  });

  it('sends the RECORD version as a strong If-Match', async () => {
    const { sent, saved } = mount({}, okPatch);
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNameLabel), {
      target: { value: FIXED },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect((sent[0].headers as Record<string, string>)['If-Match']).toBe('"gen1.1"');
  });

  it('sends an empty string to CLEAR the note rather than omitting the key', async () => {
    const { sent, saved } = mount({}, okPatch);
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNoteLabel), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    // Omitting it would mean "leave the note alone", so clearing would be impossible.
    expect(patchBody(sent)).toEqual({ description: '' });
  });

  it('writes nothing at all when the reader changed neither field', async () => {
    // The map carries NO PATCH route, so any request would be rejected by the stub —
    // which is the structural half of this assertion.
    const { calls, saved } = mount();
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    // No request, and the form closes rather than reporting a failure: nothing went
    // wrong, so nothing may be described as having gone wrong.
    expect(calls).not.toContain(PATCH_KEY);
    expect(saved).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
      ).toBeTruthy(),
    );
  });
});

// =============================================================================
// 3. the note this client was never shown
// =============================================================================

describe('a note the server did not report', () => {
  it('says so, and does not offer an empty box to overwrite it with', () => {
    // A deployment older than the rename operation serves no `description` key.
    mount({ description: undefined });
    expect(screen.getByText(LABELS.renameRecordNoteUnknown)).toBeTruthy();
    // NOT "No note": absence of an answer is not an answer.
    expect(screen.queryByText(LABELS.renameRecordNoteEmpty)).toBeNull();

    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    // The title is still editable — that field IS reported. The note box is absent
    // entirely: a blank box over an unknown value is a Save that destroys.
    expect(screen.getByLabelText(LABELS.renameRecordNameLabel)).toBeTruthy();
    expect(screen.queryByLabelText(LABELS.renameRecordNoteLabel)).toBeNull();
  });

  it('distinguishes a note that is genuinely absent from one not reported', () => {
    mount({ description: null });
    expect(screen.getByText(LABELS.renameRecordNoteEmpty)).toBeTruthy();
    expect(screen.queryByText(LABELS.renameRecordNoteUnknown)).toBeNull();
  });

  it('never sends a note when the server did not report one', async () => {
    const { sent, saved } = mount({ description: undefined }, okPatch);
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNameLabel), {
      target: { value: FIXED },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(patchBody(sent)).toEqual({ title: FIXED });
  });
});

// =============================================================================
// 4. refusals — nothing typed is ever lost
// =============================================================================

describe('a refused save', () => {
  it('refuses a blank title in words and keeps the form open', () => {
    const { calls, saved } = mount();
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNameLabel), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    expect(screen.getByRole('alert').textContent).toBe(LABELS.renameRecordTitleRequired);
    expect(calls).not.toContain(PATCH_KEY);
    expect(saved).not.toHaveBeenCalled();
    // And what they typed is still there — not reset, not cleared.
    expect(
      (screen.getByLabelText(LABELS.renameRecordNameLabel) as HTMLInputElement).value,
    ).toBe('   ');
  });

  it('refuses an over-long title, names the overage, and cuts nothing', () => {
    const { calls } = mount();
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    const tooLong = 'x'.repeat(205);
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNameLabel), {
      target: { value: tooLong },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    const alert = screen.getByRole('alert').textContent ?? '';
    expect(alert).toContain('5 characters over the 200-character limit');
    expect(alert).toContain('none of it has been cut');
    expect(calls).not.toContain(PATCH_KEY);
    // The full 205 characters are still in the box.
    expect(
      (screen.getByLabelText(LABELS.renameRecordNameLabel) as HTMLInputElement).value.length,
    ).toBe(205);
  });

  it('gives a 412 its own sentence naming the cause', async () => {
    const { saved } = mount({}, () => ({ status: 412, body: { error: 'stale_write', current_version: 'gen1.4' } }));
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNameLabel), {
      target: { value: FIXED },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    const alert = screen.getByRole('alert').textContent ?? '';
    expect(alert).toContain('changed while you were editing');
    expect(alert).toContain('nothing was saved');
    expect(saved).not.toHaveBeenCalled();
    // The reader's text survives the refusal, so they can retry after reloading.
    expect(
      (screen.getByLabelText(LABELS.renameRecordNameLabel) as HTMLInputElement).value,
    ).toBe(FIXED);
  });

  it('does not reinterpret an unknown failure as a known one', async () => {
    const { saved } = mount({}, () => ({ status: 503, body: { error: 'storage_unavailable' } }));
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNameLabel), {
      target: { value: FIXED },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    const alert = screen.getByRole('alert').textContent ?? '';
    // The generic fallback, NOT the 412 sentence and NOT an invented cause.
    expect(alert).toContain('could not be saved');
    expect(alert).not.toContain('changed while you were editing');
    expect(saved).not.toHaveBeenCalled();
  });
});

// =============================================================================
// 5. after a successful save
// =============================================================================

describe('after a save', () => {
  it('announces it, and asks the screen to refetch rather than patching its own copy', async () => {
    const { saved } = mount({}, okPatch);
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
    );
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNameLabel), {
      target: { value: FIXED },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordSubmit }));

    await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
    // `role="status"` and not `role="alert"`: a save that worked is not an alert, and
    // it must still be announced, because the form has gone and a keyboard user would
    // otherwise have no signal that anything happened.
    const status = await screen.findByRole('status');
    expect(status.textContent).toBe(LABELS.renameRecordSaved);
    // The refetch is the screen's job: the rename moved the record's `version`, which
    // every other write on that screen sends as `If-Match`.
  });

  it('reopens onto the RECORD, never onto an abandoned draft', () => {
    mount();
    const open = () =>
      fireEvent.click(
        screen.getByRole('button', { name: new RegExp(LABELS.actionRenameRecord, 'i') }),
      );
    open();
    fireEvent.change(screen.getByLabelText(LABELS.renameRecordNameLabel), {
      target: { value: 'half-typed thing' },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameRecordCancel }));
    open();
    // The stored title, not the abandoned edit — which a reader would otherwise take
    // for the record's current name.
    expect(
      (screen.getByLabelText(LABELS.renameRecordNameLabel) as HTMLInputElement).value,
    ).toBe(TYPO);
  });
});
