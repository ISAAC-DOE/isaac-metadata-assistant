import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  answersAfterNotebook,
  answersDropped,
  bundleRoutes,
  editApplied,
  editRefused,
  pendingResponse,
  stubFetchRoutes,
  completePendingPage,
} from '../test/apiFixtures';

/**
 * S4 · "Confirmed by You" may only appear over a value the SERVER reported as
 * applied.
 *
 * THE DEFECT THESE PIN. `GuidedCompletion` used to push a field into its `answered`
 * list on any RESOLVED promise, i.e. it treated HTTP 200 as proof of a write. It is
 * not: `routes.py::_answers_to_apply_shape` drops a blank or unrecognised answer, and
 * `complete.py::apply_answers` / `apply_corrections` leave a malformed value
 * unapplied — all of which return 200 with `rev` unmoved. The screen therefore
 * displayed a value the truth core had refused, under a "Confirmed by You" chip, and
 * on the /answers path it also re-rendered the SAME question as still open and
 * inflated the counter: one field both answered and open at once.
 *
 * The two response signals the fix reads are documented on `answerWasApplied` /
 * `editWasApplied` in `screens/GuidedCompletion.tsx`. These tests assert the
 * behaviour in both directions — a positive control per path, so a guard that simply
 * never shows an answered row could not pass.
 */

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const NOTEBOOK_Q = 'What is the sha256 of the processing notebook?';
const NOTEBOOK_URI = pendingResponse.pending[0].id;
const GOOD_SHA = 'c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345';
/** Not 64 hex chars, so `_SHA256_RE` in `complete.py` rejects it. Short enough that
 *  `answerValuePreview` would render it verbatim rather than truncated — so a false
 *  claim would be findable by its exact text. */
const MALFORMED = 'not-a-valid-sha256';

/** The exact no-op `reason` the backend sends, which asserts a cause ("the submitted
 *  value was identical") that is false for a refused value. No screen may render it. */
const BACKEND_NOOP_REASON =
  'No change — the submitted value was identical; nothing was invalidated.';

describe('S4 · an answer is shown as confirmed only when the server reported it applied', () => {
  it('a dropped answer (200, blocker still open, changed:false) claims nothing, moves no counter, and leaves the question open', async () => {
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': { body: answersDropped },
    });
    const { findByText, getByText, getByLabelText, queryByText, container } = renderAt(
      '/record/demo/complete',
    );
    await findByText(NOTEBOOK_Q);
    expect(getByText('0 / 5')).toBeInTheDocument();

    fireEvent.change(getByLabelText('Asset Hash'), { target: { value: MALFORMED } });
    fireEvent.click(getByText('Confirm'));

    // The honest outcome is stated...
    expect(await findByText(/That answer was not applied\./)).toBeInTheDocument();

    // ...NO answered row, and in particular no confirmation chip over the value.
    expect(container.querySelectorAll('.answered-row')).toHaveLength(0);
    expect(queryByText('Confirmed by You')).toBeNull();
    expect(queryByText(new RegExp(`you answered .*${MALFORMED}`))).toBeNull();

    // The counter did not move, and the question is STILL the open one — the two
    // must agree, which is precisely what the old behaviour broke.
    expect(getByText('0 / 5')).toBeInTheDocument();
    expect(getByText(NOTEBOOK_Q)).toBeInTheDocument();
    expect(getByText('Question 1 of 5')).toBeInTheDocument();

    // What the reader typed survives, so they can correct it.
    expect((getByLabelText('Asset Hash') as HTMLInputElement).value).toBe(MALFORMED);
  });

  it('the not-applied note names no cause and never renders the backend no-op reason', async () => {
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': { body: answersDropped },
    });
    const { findByText, getByText, getByLabelText, container } = renderAt('/record/demo/complete');
    await findByText(NOTEBOOK_Q);

    fireEvent.change(getByLabelText('Asset Hash'), { target: { value: MALFORMED } });
    fireEvent.click(getByText('Confirm'));
    const note = await findByText(/That answer was not applied\./);

    // The response carries no cause, so the copy may not invent one. `identical` is
    // pinned by name because the backend's own `reason` claims exactly that and is
    // the nearest available thing to copy.
    expect(note.textContent ?? '').not.toMatch(/malformed|invalid|identical|wrong|sha256/i);
    expect(container.textContent ?? '').not.toContain(BACKEND_NOOP_REASON);
  });

  it('POSITIVE CONTROL: an applied answer (200, blocker resolved, changed:true) still shows the confirmed row', async () => {
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': { body: answersAfterNotebook },
    });
    const { findByText, getByText, getByLabelText, queryByText } = renderAt(
      '/record/demo/complete',
    );
    await findByText(NOTEBOOK_Q);

    fireEvent.change(getByLabelText('Asset Hash'), { target: { value: GOOD_SHA } });
    fireEvent.click(getByText('Confirm'));

    await findByText('1 / 5');
    expect(getByText('Confirmed by You')).toBeInTheDocument();
    expect(queryByText(/That answer was not applied/)).toBeNull();
  });

  it('FAIL CLOSED: the blocker is resolved but changed:false — the answer is not claimed', async () => {
    // The two signals disagree. Today's backend cannot produce this (resolving a
    // blocker rewrites `pending`, which moves the draft), so it stands for a future
    // backend or refactor that reports one without the other. A disagreement means the
    // screen does not KNOW the value landed, so it must not claim it did.
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': {
        body: {
          ...answersDropped,
          pending: pendingResponse.pending.slice(1), // notebook resolved…
          pending_page: completePendingPage(pendingResponse.pending.slice(1)),
          invalidation: { ...answersDropped.invalidation, changed: false }, // …but nothing written
        },
      },
    });
    const { findByText, getByText, getByLabelText, queryByText } = renderAt(
      '/record/demo/complete',
    );
    await findByText(NOTEBOOK_Q);

    fireEvent.change(getByLabelText('Asset Hash'), { target: { value: GOOD_SHA } });
    fireEvent.click(getByText('Confirm'));

    expect(await findByText(/That answer was not applied\./)).toBeInTheDocument();
    expect(queryByText('Confirmed by You')).toBeNull();
    // The server's own list is still adopted — it is a fact either way — so the
    // counter reflects it (4 remaining, none answered) rather than being frozen.
    expect(getByText('0 / 4')).toBeInTheDocument();
  });
});

describe('S4 · a correction is shown only when the server reported it applied', () => {
  /** Answer the notebook blocker so an editable confirmed row exists. */
  async function answerNotebook(screen: ReturnType<typeof renderAt>) {
    await screen.findByText(NOTEBOOK_Q);
    fireEvent.change(screen.getByLabelText('Asset Hash'), { target: { value: GOOD_SHA } });
    fireEvent.click(screen.getByText('Confirm'));
    await screen.findByText(/^you answered /);
  }

  const answeredRoutes = {
    ...bundleRoutes('demo'),
    'POST /api/experiments/demo/answers': { body: answersAfterNotebook },
  };

  it('a refused correction (200, changed:false) keeps the recorded value, keeps the editor open, and says nothing was applied', async () => {
    stubFetchRoutes({
      ...answeredRoutes,
      'POST /api/experiments/demo/edit': { body: editRefused },
    });
    const screen = renderAt('/record/demo/complete');
    await answerNotebook(screen);

    fireEvent.click(screen.getByRole('button', { name: /Edit Asset Hash/ }));
    fireEvent.change(screen.getByDisplayValue(GOOD_SHA), { target: { value: MALFORMED } });
    fireEvent.click(screen.getByText('Save'));

    expect(await screen.findByText(/Nothing was applied —/)).toBeInTheDocument();

    // The row's value was NOT rewritten to the refused one anywhere on the screen.
    expect(screen.queryByText(new RegExp(`you answered .*${MALFORMED}`))).toBeNull();
    // The editor stays mounted with what was typed, as on a 412 — the correction can
    // be retried without retyping.
    expect(screen.getByDisplayValue(MALFORMED)).toBeInTheDocument();
    // No downstream-impact note: `invalidation.reason` would name a cause the
    // response cannot know, and none of it is rendered.
    expect(screen.container.querySelector('.edit-impact')).toBeNull();
    expect(screen.container.textContent ?? '').not.toContain(BACKEND_NOOP_REASON);

    // Cancel restores the summary showing the value the SERVER holds.
    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.getByText(/^you answered /).textContent).toContain('c3b0c442');
    expect(screen.getByText('Confirmed by You')).toBeInTheDocument();
  });

  it('POSITIVE CONTROL: an applied correction (200, changed:true) updates the row and closes the editor', async () => {
    stubFetchRoutes({
      ...answeredRoutes,
      'POST /api/experiments/demo/edit': { body: editApplied },
    });
    const screen = renderAt('/record/demo/complete');
    await answerNotebook(screen);

    fireEvent.click(screen.getByRole('button', { name: /Edit Asset Hash/ }));
    fireEvent.change(screen.getByDisplayValue(GOOD_SHA), { target: { value: 'e'.repeat(64) } });
    fireEvent.click(screen.getByText('Save'));

    // The server-reported impact is surfaced, the editor closed, the row moved on.
    await screen.findByText('Updated 1 field(s); no downstream steps reopened.');
    expect(screen.queryByDisplayValue('e'.repeat(64))).toBeNull();
    expect(screen.getByText(/^you answered /).textContent).toContain('eeee');
    expect(screen.queryByText(/Nothing was applied —/)).toBeNull();
    // The applied field is the one that was edited (guards against a stray key).
    expect(editApplied.invalidation.changed_fields).toEqual([NOTEBOOK_URI]);
  });
});
