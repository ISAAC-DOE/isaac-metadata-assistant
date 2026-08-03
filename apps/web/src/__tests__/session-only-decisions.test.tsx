/*
 * R1b · Complete Missing Fields must not present session state as a durable
 * review outcome, and must not call a client value "stored".
 *
 * DEFECT A — "leave honestly missing" evaporates. `screens/GuidedCompletion.tsx`
 * holds the decision in `useState` (`const [skipped, setSkipped] = useState(new
 * Set())`). Nothing persists it: no request is sent when the reader presses
 * "I don't know — leave honestly missing" (that is the POINT, and it is correct —
 * inventing a value would be worse), and `LoadedCompletion` is keyed by record id
 * and remounted by every `reload`, so the set is gone on refresh, on navigation
 * away, and on a stale-write Refresh. Yet the surface summarised it as a finished
 * review: "You've reviewed every question · N left honestly missing".
 *
 * PERSISTING IT NEEDS A NEW BACKEND FIELD, which is out of scope for this slice.
 * So the UI must be truthful about what it is: a note about THIS visit. The
 * feature stays — deleting a reader's only way to say "I don't know" would be a
 * regression, and the honest-missing path is the product's whole thesis.
 *
 * DEFECT B — "stored <value>". The answered row rendered `stored {storedValue}`,
 * where `storedValue` is `answerValuePreview(kind, value)` computed from the value
 * the CLIENT just submitted. `ApiAnswersResponse` is `{pending, status, workflow,
 * invalidation}` + version fields — it carries NO echo of what was stored. Worse,
 * `routes.py::_answers_to_apply_shape` documents that "Blank and unrecognised
 * answers are dropped rather than applied", so the server may store nothing at all
 * while the row asserts it did.
 *
 * DEFECT C (adjacent, same feature, same class) — the StatusBar note claimed
 * "Export unlocks automatically once every field is confirmed or honestly left
 * missing". Export requires `pending_count == 0`
 * (`apps/api/isaac_api/workflow.py`: `complete_metadata = pending_count == 0`), and
 * skipping a question does NOT remove it from `pending`. So leaving a field
 * honestly missing never unlocks export — and the same screen's own skipped-list
 * copy already said the opposite ("Export stays gated until each is confirmed").
 *
 * WHAT THIS CANNOT CATCH. It pins wording shapes on one screen. It does not prove
 * the reader understands the scope, and it says nothing about the OTHER
 * client-side-only state on this surface (a staged GuidedPrompt input is also lost
 * on reload — that is standard form behaviour and is not claimed as reviewed).
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect, afterEach, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { bundleRoutes, pendingResponse, answersAfterNotebook, stubFetchRoutes } from '../test/apiFixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

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

const NOTEBOOK_Q = 'What is the sha256 of the processing notebook?';
const DONT_KNOW = "I don't know — leave honestly missing";

// --- A: the skip decision is scoped to the visit ------------------------------

describe('R1b · a session-only decision is not presented as a durable review', () => {
  it('scopes the skipped list to this visit and says it is not saved', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo/complete');
    await findByText(NOTEBOOK_Q);

    fireEvent.click(screen.getByText(DONT_KNOW));
    await findByText('What is the sha256 of the raw scan file?');

    const list = container.querySelector('.leftmissing');
    expect(list, 'the skipped list must still be rendered — the feature stays').not.toBeNull();
    const text = list!.textContent ?? '';
    // It says WHOSE state this is and how long it lasts.
    expect(text).toMatch(/this (visit|session)/i);
    expect(text).toMatch(/(not saved|isn't saved|not kept|no(t|thing) recorded)/i);
  });

  it('the all-reviewed summary does not claim a completed review outcome', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo/complete');
    await findByText(NOTEBOOK_Q);

    // Skip every one of the five questions, reaching the all-skipped summary.
    for (let i = 0; i < pendingResponse.pending.length; i += 1) {
      fireEvent.click(screen.getByText(DONT_KNOW));
    }

    const summary = container.querySelector('.completion-allskipped');
    expect(summary, 'the all-skipped summary must still appear').not.toBeNull();
    const text = summary!.textContent ?? '';

    // The retired framing: a finished, durable review.
    expect(text).not.toMatch(/You've reviewed every question/i);
    // The honest framing: scoped, and explicit that a reload undoes it.
    expect(text).toMatch(/this (visit|session)/i);
    expect(text).toMatch(/(reload|refresh|come back|return)/i);
    // ...and it still tells the reader the useful thing: nothing was invented and
    // export is still gated.
    expect(text).toMatch(/nothing was invented/i);
    expect(text).toMatch(/export/i);
  });
});

// --- B: no "stored" claim without a server echo -------------------------------

describe('R1b · the answered row does not claim the server stored a value', () => {
  it('never renders "stored <the value the client sent>"', async () => {
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': { body: answersAfterNotebook },
    });
    const { findByText, getByLabelText, container } = renderAt('/record/demo/complete');
    await findByText(NOTEBOOK_Q);

    fireEvent.change(getByLabelText('Asset Hash'), { target: { value: 'c3b0c442…' } });
    fireEvent.click(screen.getByText('Confirm'));
    await findByText('1 / 5');

    const row = container.querySelector('.answered-stored');
    expect(row, 'the answered row must still show the value').not.toBeNull();
    // "stored" is a claim about server state that no response field supports.
    expect(row!.textContent ?? '').not.toMatch(/^stored\b/i);
    // The value itself is still shown — this is a wording fix, not a removal.
    expect(row!.textContent ?? '').toContain('c3b0c442…');
  });
});

// --- C: the export-unlock claim -----------------------------------------------

function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();

describe('R1b · the screen does not claim that leaving a field missing unlocks export', () => {
  it('the status note no longer says export unlocks on "honestly left missing"', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo/complete');
    await findByText(NOTEBOOK_Q);

    const bar = container.querySelector('.statusbar');
    expect(bar, 'the status bar must still be rendered').not.toBeNull();
    expect(bar!.textContent ?? '').not.toMatch(
      /unlocks?[^.]{0,60}(honestly )?left missing|confirmed or honestly left missing/i,
    );
  });

  it('and the retired sentence is gone from the source, not merely unreachable', () => {
    const src = readFileSync(join(SRC_DIR, 'screens/GuidedCompletion.tsx'), 'utf8').replace(
      /\s+/g,
      ' ',
    );
    expect(src).not.toContain(
      'Export unlocks automatically once every field is confirmed or honestly left missing.',
    );
  });
});
