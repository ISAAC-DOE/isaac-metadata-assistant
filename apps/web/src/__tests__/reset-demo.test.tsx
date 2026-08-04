import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { api, RESET_CONFIRMATION, TUTORIAL_SESSION_HEADER, getTutorialScope } from '../lib/api';
import { LABELS } from '../lib/labels';
import { __resetTutorialStore } from '../lib/tutorialController';
import { atRiskSentence } from '../components/ResetDemoDialog';
import {
  stubFetchRoutes,
  resetDemoRoutes,
  tutorialSessionRoutes,
  TUTORIAL_SESSION_ID,
  demoResetPreviewClean,
  demoResetPreviewAmbiguous,
  demoResetExecuteOk,
  demoResetExecuteStale,
  demoResetExecuteDigestRequired,
  RESET_PLAN_DIGEST,
  RESET_PLAN_DIGEST_FRESH,
  RESET_AT_RISK_NONE,
} from '../test/apiFixtures';
import type { RouteEntry } from '../test/apiFixtures';

/*
 * P26.0b — the guarded Reset Worked Example control.
 *
 * WHERE IT LIVES CHANGED, AND EVERY TEST BELOW MOVED WITH IT. `POST /api/demo/reset`
 * now REQUIRES a worked-example session header and refuses without one, writing
 * nothing. The trigger therefore no longer sits on My Experiments — where it would be
 * a control that looks like it acts and does not — but in the persistent
 * worked-example bar (`components/TutorialSessionBar.tsx`), which exists only while a
 * session is open.
 *
 * So these tests now ENTER a worked-example session first (`renderInSession`) instead
 * of rendering the ordinary My Experiments. Nothing about the control's contract was
 * relaxed to make that work: every assertion below asserts the same property, at the
 * same strength, about the scope the control now acts on. Three assertions were made
 * STRONGER in the move and say so at their site: the trigger's absence from the
 * ordinary workspace is now pinned, the "shared workspace" claim is pinned as
 * FORBIDDEN rather than required (it is false of a per-session scope), and the
 * post-reset refetch is measured as an INCREASE rather than as a floor of two — the
 * walkthrough's own list read would otherwise satisfy a floor of two on its own.
 *
 * Behaviour contract. The control:
 *   - renders ONLY when GET /api/health reports mode "synthetic-only" (authoritative,
 *     fail-closed), and is a restrained *destructive* action, never the primary;
 *   - opens a labeled modal dialog that first PREVIEWS (never mutates) via
 *     POST /api/demo/reset {mode:'preview'}, showing the typed counts;
 *   - warns this is a temporary worked-example workspace and progress will be
 *     discarded;
 *   - requires the operator to type exactly "RESET"; the destructive action stays
 *     disabled until it matches (and always, if any ambiguous record is present);
 *   - on execute sends the exact backend phrase, fires exactly once, then announces
 *     the rebuild so the list is re-read and reflects the canonical five;
 *   - refuses safely (no bypass) when the backend refuses, and never leaks a
 *     credential or internal filesystem path.
 *
 * Every fixture is synthetic. The truth core is never bypassed by the UI.
 */

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

/**
 * Render My Experiments and open a real worked-example session, the way a reader
 * does: by accepting the first-run offer.
 *
 * DELIBERATELY THE REAL PATH, not a seeded store. The control under test is gated on
 * a session actually existing, and `startTutorial` is what creates one — a test seam
 * that set `sessionId` directly would prove the bar renders without proving it renders
 * when it should. The cost is that the walkthrough's coach mark is on screen
 * throughout, which is exactly the real arrangement and is why `dialog()` below
 * resolves the reset dialog BY NAME.
 */
async function renderInSession(routes: Record<string, RouteEntry>) {
  const calls = stubFetchRoutes({ ...tutorialSessionRoutes(), ...routes });
  const rendered = render(
    <MemoryRouter initialEntries={['/experiments']} future={FUTURE}>
      <AppRoutes />
    </MemoryRouter>,
  );
  const view = { ...rendered, calls };
  fireEvent.click(await view.findByRole('button', { name: LABELS.actionStartTutorial }));
  // The bar's affirmative control is NOT health-gated, so it is the right thing to
  // wait on: a `mode: production` case must still get into the session and then find
  // the reset control absent.
  await view.findByRole('button', { name: LABELS.actionRunDemo });
  return view;
}

/** The parsed JSON bodies of every POST /api/demo/reset the app issued, in order. */
function resetPosts(): Array<{ mode: string; confirmation?: string; plan_digest?: string }> {
  const mock = (globalThis.fetch as unknown as { mock: { calls: [unknown, RequestInit?][] } }).mock;
  return mock.calls
    .filter(([input, init]) => String(input).endsWith('/demo/reset') && init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body ?? '{}')));
}

function countCalls(calls: string[], key: string): number {
  return calls.filter((k) => k === key).length;
}

type SessionView = Awaited<ReturnType<typeof renderInSession>>;

/** Open the reset dialog, focusing the trigger first so focus-return is testable. */
async function openReset(view: SessionView) {
  const trigger = (await view.findByRole('button', {
    name: LABELS.actionResetDemo,
  })) as HTMLButtonElement;
  trigger.focus();
  fireEvent.click(trigger);
  // the dialog appears once the preview resolves
  await waitFor(() => expect(dialog(view)).toBeInTheDocument());
  return trigger;
}

/**
 * The reset dialog, resolved BY ITS ACCESSIBLE NAME.
 *
 * A bare `getByRole('dialog')` used to be unambiguous because the reset dialog was the
 * only one on My Experiments. The walkthrough's coach mark is also a `role="dialog"`
 * (deliberately: it names and describes itself), and it is on screen for the whole of
 * every test in this file now. Naming the dialog is a MORE precise query than the one
 * it replaces — it would fail if the dialog lost its label, which the bare query would
 * not — so it is not a loosening.
 */
function dialog(view: SessionView) {
  return view.getByRole('dialog', { name: new RegExp(LABELS.resetDialogTitle, 'i') });
}

/** The reset dialog, or null — the same name-scoped query, for absence assertions.
 *  A bare `queryByRole('dialog')` would now resolve the coach mark and never be null,
 *  which would make every "the dialog closed" assertion below unfalsifiable. */
function resetDialogOrNull(view: SessionView): HTMLElement | null {
  return view.queryByRole('dialog', { name: new RegExp(LABELS.resetDialogTitle, 'i') });
}

afterEach(() => {
  vi.unstubAllGlobals();
  // The walkthrough's store is a module singleton and holds the open session id, and
  // `api.ts` holds the scope the header is built from. Both must be cleared or a later
  // test starts inside the previous test's session.
  __resetTutorialStore();
  sessionStorage.clear();
});

// --- 1–3. presence, synthetic-only gate, non-primary treatment ---------------

describe('P26.0b · Reset Worked Example — presence & treatment', () => {
  it('renders the reset control in the worked-example bar in synthetic-only mode', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    const reset = await view.findByRole('button', { name: LABELS.actionResetDemo });
    expect(reset).toBeInTheDocument();
    // It is in the worked-example bar, not loose on the screen — the bar is what
    // scopes it, and a trigger outside it would not be session-gated.
    expect(reset.closest('.tutorial-session-bar')).not.toBeNull();
  });

  /*
   * ADDED IN THE MOVE, not carried over: the control's ABSENCE from the ordinary
   * workspace is now a pinned property rather than a consequence of where it happens
   * to be mounted. `POST /api/demo/reset` refuses without the session header, so a
   * trigger here would be a dead control — the exact defect the move fixed.
   */
  it('does NOT render on the ordinary My Experiments, where the endpoint refuses', async () => {
    const calls = stubFetchRoutes(resetDemoRoutes().routes);
    const view = render(
      <MemoryRouter initialEntries={['/experiments']} future={FUTURE}>
        <AppRoutes />
      </MemoryRouter>,
    );
    // Wait for the loaded screen (the offer only renders on the data branch), so this
    // cannot pass merely because nothing has rendered yet.
    await view.findByRole('button', { name: LABELS.actionStartTutorial });
    expect(calls).toContain('GET /api/experiments');
    expect(view.queryByRole('button', { name: LABELS.actionResetDemo })).toBeNull();
    expect(document.querySelector('.tutorial-session-bar')).toBeNull();
    // ...and no request was ever made to the reset endpoint from this screen.
    expect(calls.filter((c) => c.includes('/demo/reset'))).toEqual([]);
  });

  it('does NOT render the control when the backend is not synthetic-only', async () => {
    const view = await renderInSession(resetDemoRoutes({ mode: 'production' }).routes);
    // wait until the page (and the health probe) have settled
    await view.findByRole('button', { name: LABELS.actionRunDemo });
    await waitFor(() =>
      expect(view.queryByRole('button', { name: LABELS.actionResetDemo })).toBeNull(),
    );
  });

  it('is a restrained destructive action — not the primary on the screen', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    const reset = (await view.findByRole('button', {
      name: LABELS.actionResetDemo,
    })) as HTMLButtonElement;
    /*
     * P1 removed the button this test used to reach for. It was labelled "New
     * Record", styled btn-primary, and navigated to the SAME route as the
     * example-run button beside it — promising a capability the build does not
     * have. The screen's one affirmative action inherited the primary treatment,
     * so the property under test is unchanged: SOMETHING affirmative is primary,
     * and Reset must not borrow that styling.
     *
     * D2 moved BOTH controls into the worked-example bar — they are the two
     * operations that require the session header — so the affirmative control this
     * compares against is the same control it always was, in its new home.
     */
    const primary = view.getByRole('button', {
      name: LABELS.actionRunDemo,
    }) as HTMLButtonElement;
    expect(primary.className).toContain('btn-primary');
    expect(reset.className).not.toContain('btn-primary');
    // and it is a genuinely separate control from the affirmative one
    expect(reset).not.toBe(primary);
    // The removal is pinned, not incidental: no control on this screen may offer
    // record creation, because nothing in this build can create a record.
    expect(view.queryByRole('button', { name: /new record|new experiment|create/i })).toBeNull();
  });
});

// --- 4–8. preview is non-mutating and shows the typed counts + warnings -------

describe('P26.0b · Reset Worked Example — preview (non-mutating) & disclosure', () => {
  it('opening the dialog previews (mode:preview) and issues no execute', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const posts = resetPosts();
    expect(posts).toHaveLength(1);
    expect(posts[0].mode).toBe('preview');
    expect(posts.some((p) => p.mode === 'execute')).toBe(false);
    // no execute confirmation phrase was ever sent
    expect(posts[0].confirmation).toBeUndefined();
  });

  it('preview displays current / canonical / legacy / ambiguous / final counts', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    // labels are the operator-facing vocabulary from the spec
    expect(d.getByText('Current Experiments')).toBeInTheDocument();
    expect(d.getByText('Built-in Examples Restored')).toBeInTheDocument();
    expect(d.getByText('Additional Records Removed')).toBeInTheDocument();
    expect(d.getByText('Ambiguous Records')).toBeInTheDocument();
    expect(d.getByText('Final Experiments')).toBeInTheDocument();
    // the numeric values come straight from the preview response
    const text = dialog(view).textContent ?? '';
    expect(text).toMatch(/\b7\b/); // previous_count
    expect(text).toMatch(/\b5\b/); // canonical / final
    expect(text).toMatch(/\b2\b/); // legacy_count
  });

  /*
   * THE SCOPE WORD FLIPPED POLARITY, and that is a correction rather than a
   * relaxation. This test used to REQUIRE the word "shared", because the five
   * examples lived in the single ordinary workspace that every reader of the hosted
   * deployment saw. They now live in a worked-example session: one directory per
   * session, mutually invisible (`test_two_sessions_are_independently_mutable_and_
   * mutually_invisible`). "Shared" is therefore FALSE here — it would over-state the
   * blast radius and under-state the privacy of the scope at the same time — so it is
   * now FORBIDDEN, and the true property it stood for (the scope is temporary, and
   * the reader's own records are not in it) is required in its place.
   *
   * Everything else in this test is unchanged, including the two clauses P1 tightened.
   */
  it('states that this is a temporary worked-example workspace and progress is discarded', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const text = (dialog(view).textContent ?? '').toLowerCase();
    expect(text).toContain('temporary');
    // the scope, both halves: what it IS, and what it is not
    expect(text).toMatch(/belonging to this walkthrough alone/);
    expect(text).toMatch(/nothing in my experiments is in this scope/);
    // the retired claim must not come back — a session is not shared with anyone
    expect(text).not.toMatch(/\bshared\b/);
    // P1: was `toContain('synthetic')`. The disclosure now names the thing being
    // reset ("example workspace") instead of the data regime, which the mode chip
    // and the Governance surface own. Pinned MORE tightly than before — the old
    // check accepted the bare word anywhere and the alternation accepted either
    // half of the destructive claim; both halves are now required.
    expect(text).toContain('example workspace');
    expect(text).toMatch(/progress/);
    expect(text).toMatch(/discards/);
    expect(text).toMatch(/restores all five/);
    expect(text).toContain('real data is unaffected');
  });

  /*
   * P1 review — this pins the SHAPE of the reassurance clause, not just its words.
   *
   * The clause has been wrong twice. It first denied a data class on the
   * deployment's behalf ("holds no real experiment data"); that was replaced by a
   * positive WHOLE-CONTENT claim ("this workspace is built only from committed
   * example files") which was FALSE — a 64-char canary posted to
   * `POST /api/experiments/{id}/answers` is present in the persisted workspace
   * state file and absent from both committed reference files, so the workspace
   * holds what users store as well as what was committed. Worse, that wording was
   * chosen partly BECAUSE the positive form slipped past the honesty sweep in
   * `db-recon-truthfulness.test.tsx`, which only nets denials.
   *
   * So the negative assertion below is deliberately a PATTERN over the whole
   * family of whole-content claims, not the one retired string: the next variant
   * ("contains only…", "holds no real…") must fail here too. What the clause is
   * allowed to say is a MODE claim — which the control is already gated on, since
   * it renders only when health reports `synthetic-only`.
   */
  it('makes a mode claim, never a whole-content claim about the workspace', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const text = (dialog(view).textContent ?? '').toLowerCase();

    // the mode claim, and the two checkable facts that qualify it
    expect(text).toContain('synthetic-only mode');
    expect(text).toMatch(/come from committed files/);
    expect(text).toMatch(/every upload is refused/);

    // ...and NOT any claim about the whole of what the workspace contains
    expect(text).not.toMatch(/built only from|contains only|holds no real/i);
  });
});

// --- 9–12. typed confirmation gate; cancel / escape do not mutate -------------

describe('P26.0b · Reset Worked Example — confirmation gate', () => {
  it('keeps the destructive action disabled until exactly "RESET" is typed', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    const action = d.getByRole('button', { name: LABELS.resetConfirmAction }) as HTMLButtonElement;
    const input = d.getByRole('textbox') as HTMLInputElement;

    expect(action.disabled).toBe(true); // nothing typed
    fireEvent.change(input, { target: { value: 'reset' } });
    expect(action.disabled).toBe(true); // wrong case
    fireEvent.change(input, { target: { value: 'RESET NOW' } });
    expect(action.disabled).toBe(true); // extra text
    fireEvent.change(input, { target: { value: 'RESET' } });
    expect(action.disabled).toBe(false); // exact match enables
  });

  it('Cancel closes the dialog and performs no mutation, returning focus to the trigger', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    const trigger = await openReset(view);
    fireEvent.click(within(dialog(view)).getByRole('button', { name: 'Cancel' }));
    expect(resetDialogOrNull(view)).toBeNull();
    expect(resetPosts().some((p) => p.mode === 'execute')).toBe(false);
    expect(document.activeElement).toBe(trigger);
  });

  /*
   * THIS TEST NOW PINS A SECOND PROPERTY, and it is why `GuidedTutorial` gained a
   * guard. The walkthrough registers a capture-phase Escape handler on `document`, and
   * `AppShell` mounts it before anything inside it — so without a guard the walkthrough
   * would see Escape FIRST, call `stopPropagation`, and this dialog could never be
   * closed with the key. Worse, the reader's Escape would silently do something they did
   * not ask for: leave the walkthrough while a destructive confirmation was on screen.
   *
   * So Escape must close the MODAL and leave the walkthrough alone. Both halves are
   * asserted; the second half is the new one.
   */
  it('Escape closes the dialog without mutating, returns focus, and leaves the walkthrough running', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    const trigger = await openReset(view);
    // the walkthrough really is running, so the assertion below is about a real overlay
    expect(document.querySelector('.tutorial-mark')).not.toBeNull();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(resetDialogOrNull(view)).toBeNull();
    expect(resetPosts().some((p) => p.mode === 'execute')).toBe(false);
    expect(document.activeElement).toBe(trigger);
    // The modal owned that Escape: the walkthrough is untouched, and so is its session.
    expect(document.querySelector('.tutorial-mark')).not.toBeNull();
    expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID);
    expect(view.queryByRole('button', { name: LABELS.actionResetDemo })).not.toBeNull();
  });

  it('a SECOND Escape, with no dialog open, does leave the walkthrough', async () => {
    // The other side of the same guard: it must defer to a modal, not swallow Escape
    // whenever one has ever been open.
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    fireEvent.keyDown(document, { key: 'Escape' }); // closes the dialog
    expect(resetDialogOrNull(view)).toBeNull();
    fireEvent.keyDown(document, { key: 'Escape' }); // now leaves the walkthrough
    await waitFor(() => expect(document.querySelector('.tutorial-mark')).toBeNull());
    await waitFor(() => expect(getTutorialScope()).toBeNull());
  });

  it('pressing Enter with a non-matching phrase does not execute', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const input = within(dialog(view)).getByRole('textbox');
    fireEvent.change(input, { target: { value: 'nope' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(resetPosts().some((p) => p.mode === 'execute')).toBe(false);
  });
});

// --- 13–16. dialog a11y: labelled, focus in / trapped / returned --------------

describe('P26.0b · Reset Worked Example — dialog accessibility', () => {
  it('is a modal dialog labelled by its visible title', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const d = dialog(view);
    expect(d.getAttribute('aria-modal')).toBe('true');
    const labelledby = d.getAttribute('aria-labelledby');
    expect(labelledby).toBeTruthy();
    expect(document.getElementById(labelledby!)!.textContent).toMatch(new RegExp(LABELS.resetDialogTitle, 'i'));
  });

  it('moves focus into the dialog on open', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    expect(dialog(view).contains(document.activeElement)).toBe(true);
  });

  it('traps Tab within the dialog', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const d = dialog(view);
    const focusable = Array.from(
      d.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => !(el as HTMLButtonElement).disabled);
    expect(focusable.length).toBeGreaterThan(0);
    const last = focusable[focusable.length - 1];
    last.focus();
    // Tab at the last focusable is contained (prevented) and focus stays in-dialog
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(d.contains(document.activeElement)).toBe(true);
    const first = focusable[0];
    first.focus();
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true });
    expect(d.contains(document.activeElement)).toBe(true);
  });

  it('the confirmation input has an accessible label', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const input = within(dialog(view)).getByRole('textbox');
    const name =
      input.getAttribute('aria-label') ||
      (input.getAttribute('aria-labelledby')
        ? document.getElementById(input.getAttribute('aria-labelledby')!)?.textContent
        : '') ||
      (input.id ? document.querySelector(`label[for="${input.id}"]`)?.textContent : '');
    expect((name ?? '').trim().length).toBeGreaterThan(0);
  });
});

// --- 17–19. execute fires exactly once; double-click is safe ------------------

describe('P26.0b · Reset Worked Example — single-submit safety', () => {
  it('executing sends the exact backend confirmation phrase exactly once', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));
    await waitFor(() => expect(resetPosts().some((p) => p.mode === 'execute')).toBe(true));
    const executes = resetPosts().filter((p) => p.mode === 'execute');
    expect(executes).toHaveLength(1);
    expect(executes[0].confirmation).toBe('RESET EXAMPLE WORKSPACE');
  });

  it('double-clicking the destructive action cannot produce two executions', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    const action = d.getByRole('button', { name: LABELS.resetConfirmAction });
    fireEvent.click(action);
    fireEvent.click(action);
    await waitFor(() => expect(resetPosts().some((p) => p.mode === 'execute')).toBe(true));
    expect(resetPosts().filter((p) => p.mode === 'execute')).toHaveLength(1);
  });
});

// --- 20–21. ambiguous refusal is safe and offers no bypass --------------------

describe('P26.0b · Reset Worked Example — ambiguous refusal', () => {
  it('when the preview is refused for ambiguity, execution is disabled with no bypass', async () => {
    const view = await renderInSession(resetDemoRoutes({ preview: demoResetPreviewAmbiguous }).routes);
    await openReset(view);
    const d = within(dialog(view));
    const text = (dialog(view).textContent ?? '').toLowerCase();
    expect(text).toMatch(/refus|cannot|safety|ambiguous/);
    // no "delete it yourself" style bypass is offered
    expect(text).not.toMatch(/delete.*manual|manually delete|override/);
    // typing the phrase must NOT enable execution while ambiguous
    const action = d.getByRole('button', { name: LABELS.resetConfirmAction }) as HTMLButtonElement;
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    expect(action.disabled).toBe(true);
  });

  it('an ambiguous refusal never issues an execute request', async () => {
    const view = await renderInSession(resetDemoRoutes({ preview: demoResetPreviewAmbiguous }).routes);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    const action = d.getByRole('button', { name: LABELS.resetConfirmAction });
    fireEvent.click(action);
    expect(resetPosts().some((p) => p.mode === 'execute')).toBe(false);
  });
});

// --- 22–24. success refreshes from the backend to the canonical five ----------

describe('P26.0b · Reset Worked Example — success refreshes the dashboard', () => {
  it('after a successful reset the experiments list is re-fetched and shows the canonical five', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    // the legacy demo rows are present before the reset (two identically-titled
    // managed-legacy records — use the plural query since the title is shared)
    expect((await view.findAllByText(/Demo \(demo\/run\)/)).length).toBeGreaterThanOrEqual(1);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    /*
     * STRENGTHENED IN THE MOVE. This used to assert a FLOOR of two list reads
     * ("initial load + refresh"). Inside a worked-example session the walkthrough
     * itself reads the list once to resolve its targets, so a floor of two would now
     * be satisfied before the reset ran at all — the assertion would have survived
     * the refetch being deleted. It is now measured as an INCREASE across the
     * execute, which is the property that was always meant.
     */
    const readsBefore = countCalls(view.calls, 'GET /api/experiments');
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));

    await waitFor(() =>
      expect(countCalls(view.calls, 'GET /api/experiments')).toBeGreaterThan(readsBefore),
    );
    // and the refreshed dashboard reflects exactly the five canonical scenarios.
    // P33 S1 redesigned the card: the server-authored lifecycle suffix (e.g.
    // "· Exported Record") is no longer shown on the title — the row now carries
    // ONE clean title plus a lifecycle badge, so the five scenarios are counted by
    // row count + lifecycle badge distribution instead of by title text.
    await waitFor(() => expect(view.container.querySelectorAll('.exp-row')).toHaveLength(5));
    const queue = within(view.container.querySelector('.queue') as HTMLElement);
    expect(queue.getAllByText('Exported')).toHaveLength(1);
    expect(queue.getAllByText('Draft')).toHaveLength(4);
    await waitFor(() => expect(view.queryAllByText(/Demo \(demo\/run\)/)).toHaveLength(0));
  });

  it('does not surface an error state on a successful reset', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));
    await waitFor(() => expect(resetPosts().some((p) => p.mode === 'execute')).toBe(true));
    // no unhandled error banner
    expect(view.queryByText(/unexpected error|something went wrong/i)).toBeNull();
  });
});

// --- 25–26. no secret/path leak; existing example-run action intact -----------

describe('P26.0b · Reset Worked Example — leak safety & coexistence', () => {
  it('never renders a credential or internal filesystem path', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const text = view.container.textContent ?? '';
    for (const forbidden of ['Bearer', 'Authorization', 'VITE_API_KEY', '/data/', '/tmp/', 'isaac-workspace']) {
      expect(text).not.toContain(forbidden);
    }
  });

  it('leaves the existing example-run action intact', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    // Both example-workspace controls moved together — they are the two operations
    // that require the session header — so this affirmative one is still beside the
    // destructive one, in the bar rather than in the page header.
    const run = await view.findByRole('button', { name: LABELS.actionRunDemo });
    expect(run).toBeInTheDocument();
    expect(run.closest('.tutorial-session-bar')).not.toBeNull();
  });

  /*
   * ADDED IN THE MOVE. Every request the dialog issues must carry the session scope:
   * that — not a filter, not a check inside the dialog — is what confines the reset to
   * these five copies. Asserted on the outgoing headers, because the scope is applied
   * in `api.ts`'s single `request()` choke point and a future API function that
   * bypassed it would be invisible to any assertion about the dialog itself.
   */
  it('sends the worked-example scope on every reset request it issues', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));
    await waitFor(() => expect(resetPosts().some((p) => p.mode === 'execute')).toBe(true));

    const mock = (globalThis.fetch as unknown as {
      mock: { calls: [unknown, RequestInit?][] };
    }).mock;
    const resetCalls = mock.calls.filter(([input]) => String(input).endsWith('/demo/reset'));
    expect(resetCalls.length).toBeGreaterThanOrEqual(2); // the preview and the execute
    for (const [, init] of resetCalls) {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      expect(headers[TUTORIAL_SESSION_HEADER]).toBe(TUTORIAL_SESSION_ID);
    }
    expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID);
  });
});

// --- §4 client contract: resetDemo reads the typed body on refusal, not throws -

/** `api.resetDemo`, reached without its public typing (the tests assert on the raw
 *  body shape, which is the point — the client must not swallow it). */
type RawResetDemo = (
  m: string,
  c?: string,
  digest?: string,
) => Promise<Record<string, unknown>>;
const rawResetDemo = () => (api as unknown as { resetDemo: RawResetDemo }).resetDemo;

describe('P26.0b · api.resetDemo — typed outcomes', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('preview returns the typed body on 200', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { body: demoResetPreviewClean } });
    const res = await rawResetDemo()('preview');
    expect(res.status).toBe('ok');
    expect(res.legacy_count).toBe(2);
  });

  it('execute success returns the typed body on 200', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { body: demoResetExecuteOk } });
    const res = await rawResetDemo()('execute', 'RESET EXAMPLE WORKSPACE', RESET_PLAN_DIGEST);
    expect(res.status).toBe('ok');
    expect(res.removed_count).toBe(2);
  });

  it('reads the typed refusal body on a 409 (ambiguous) rather than throwing', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { status: 409, body: { ...demoResetPreviewAmbiguous, mode: 'execute' } } });
    const res = await rawResetDemo()('execute', 'RESET EXAMPLE WORKSPACE', RESET_PLAN_DIGEST);
    expect(res.status).toBe('refused');
    expect(res.ambiguous_count).toBe(1);
  });

  it('reads the typed refusal body on a 403 (not synthetic) rather than throwing', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { status: 403, body: { ...demoResetPreviewClean, status: 'refused' } } });
    const res = await rawResetDemo()('preview');
    expect(res.status).toBe('refused');
  });

  /*
   * R1. A 412/428 is a REFUSAL, not a failure, and the distinction is load-bearing:
   * the body carries the current digest and the refreshed figures, which is exactly
   * what the dialog needs in order to explain what changed. If `resetDemo` threw
   * these as HTTP errors the dialog could only say "request failed", about the one
   * outcome it most needs to be clear about.
   */
  it('reads the typed refusal body on a 412 (stale precondition) rather than throwing', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { status: 412, body: demoResetExecuteStale } });
    const res = await rawResetDemo()('execute', 'RESET EXAMPLE WORKSPACE', RESET_PLAN_DIGEST);
    expect(res.status).toBe('refused');
    expect(res.refusal_reason).toBe('plan_digest_stale');
    expect(res.removed_count).toBe(0);
    // ...and it carries the digest a fresh attempt would need
    expect(res.plan_digest).toBe(RESET_PLAN_DIGEST_FRESH);
  });

  it('reads the typed refusal body on a 428 (precondition omitted) rather than throwing', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { status: 428, body: demoResetExecuteDigestRequired } });
    const res = await rawResetDemo()('execute', 'RESET EXAMPLE WORKSPACE');
    expect(res.status).toBe('refused');
    expect(res.refusal_reason).toBe('plan_digest_required');
    expect(res.removed_count).toBe(0);
  });

  it('sends the digest on execute and never on preview', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { body: demoResetPreviewClean } });
    await rawResetDemo()('preview');
    await rawResetDemo()('execute', 'RESET EXAMPLE WORKSPACE', RESET_PLAN_DIGEST);
    const posts = resetPosts();
    expect(posts[0]).toEqual({ mode: 'preview' });
    expect(posts[1].plan_digest).toBe(RESET_PLAN_DIGEST);
  });

  it('does NOT invent a digest when it has none — the SERVER decides', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { status: 428, body: demoResetExecuteDigestRequired } });
    await rawResetDemo()('execute', 'RESET EXAMPLE WORKSPACE');
    const execute = resetPosts().find((p) => p.mode === 'execute')!;
    expect(execute.plan_digest).toBeUndefined();
    expect(Object.keys(execute).sort()).toEqual(['confirmation', 'mode']);
  });
});

// --- R1 · the precondition is carried, and a stale refusal is honest -----------

describe('R1 · Reset Worked Example — the plan-digest precondition', () => {
  it('carries the digest from its OWN preview into the execute', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));
    await waitFor(() => expect(resetPosts().some((p) => p.mode === 'execute')).toBe(true));
    const execute = resetPosts().find((p) => p.mode === 'execute')!;
    expect(execute.plan_digest).toBe(RESET_PLAN_DIGEST);
    expect(execute.confirmation).toBe(RESET_CONFIRMATION);
  });

  it('a stale refusal says nothing was reset, in plain language and not in HTTP', async () => {
    const view = await renderInSession(
      resetDemoRoutes({ executeStatus: 412, execute: demoResetExecuteStale }).routes,
    );
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));

    const alert = await view.findByRole('alert');
    const text = (alert.textContent ?? '').toLowerCase();
    expect(text).toContain('nothing was reset');
    expect(text).toContain('no records were changed');
    expect(text).toContain('confirm again');
    // never HTTP jargon, never a suggestion that something broke
    expect(text).not.toMatch(/\b412\b|\b428\b|precondition|digest|http|error|failed/);
  });

  it('a stale refusal re-previews and DISARMS the action — no safe-looking retry', async () => {
    const view = await renderInSession(
      resetDemoRoutes({ executeStatus: 412, execute: demoResetExecuteStale }).routes,
    );
    await openReset(view);
    const d = within(dialog(view));
    const input = d.getByRole('textbox') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));
    await view.findByRole('alert');

    // exactly ONE execute was attempted — nothing auto-retried
    await waitFor(() =>
      expect(resetPosts().filter((p) => p.mode === 'execute')).toHaveLength(1),
    );
    // a SECOND preview ran, so the figures on screen are the current ones
    await waitFor(() =>
      expect(resetPosts().filter((p) => p.mode === 'preview').length).toBeGreaterThanOrEqual(2),
    );
    // the typed gate was cleared and the destructive action is disarmed again
    expect((d.getByRole('textbox') as HTMLInputElement).value).toBe('');
    const action = d.getByRole('button', { name: LABELS.resetConfirmAction }) as HTMLButtonElement;
    expect(action.disabled).toBe(true);
    // and the dialog is still open (the explanation was not flashed away)
    expect(resetDialogOrNull(view)).not.toBeNull();
  });

  it('after re-arming, the second execute carries the REFRESHED digest', async () => {
    const view = await renderInSession(
      resetDemoRoutes({
        executeStatus: 412,
        execute: demoResetExecuteStale,
        previewRefresh: { ...demoResetPreviewClean, plan_digest: RESET_PLAN_DIGEST_FRESH },
      }).routes,
    );
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));
    await view.findByRole('alert');
    await waitFor(() =>
      expect(resetPosts().filter((p) => p.mode === 'preview').length).toBeGreaterThanOrEqual(2),
    );
    await waitFor(() =>
      expect((d.getByRole('textbox') as HTMLInputElement).disabled).toBe(false),
    );

    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    await waitFor(() =>
      expect(
        (d.getByRole('button', { name: LABELS.resetConfirmAction }) as HTMLButtonElement).disabled,
      ).toBe(false),
    );
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));
    await waitFor(() =>
      expect(resetPosts().filter((p) => p.mode === 'execute')).toHaveLength(2),
    );
    const executes = resetPosts().filter((p) => p.mode === 'execute');
    expect(executes[0].plan_digest).toBe(RESET_PLAN_DIGEST);
    expect(executes[1].plan_digest).toBe(RESET_PLAN_DIGEST_FRESH);
  });

  it('a 428 is handled exactly like a stale refusal, not as an error', async () => {
    const view = await renderInSession(
      resetDemoRoutes({ executeStatus: 428, execute: demoResetExecuteDigestRequired }).routes,
    );
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));
    const alert = await view.findByRole('alert');
    expect((alert.textContent ?? '').toLowerCase()).toContain('nothing was reset');
    expect(view.queryByText(/could not be completed/i)).toBeNull();
  });
});

// --- R1 · the derived at-risk disclosure ---------------------------------------

describe('R1 · Reset Worked Example — what you would lose', () => {
  it('states the actual server-derived numbers, not a vague warning', async () => {
    const view = await renderInSession(resetDemoRoutes().routes);
    await openReset(view);
    const text = dialog(view).textContent ?? '';
    expect(text).toContain(LABELS.resetAtRiskLabel);
    // demoResetPreviewClean.at_risk = {3 answers, 2 examples, 1 export}
    expect(text).toContain('3 confirmed answers');
    expect(text).toContain('2 built-in examples carrying progress');
    expect(text).toContain('1 record you exported');
    expect(text).toMatch(/discards them permanently/);
  });

  it('says so outright when there is nothing to lose', async () => {
    const view = await renderInSession(
      resetDemoRoutes({
        preview: { ...demoResetPreviewClean, at_risk: RESET_AT_RISK_NONE },
      }).routes,
    );
    await openReset(view);
    expect(dialog(view).textContent).toContain(LABELS.resetAtRiskNothing);
  });

  it('the sentence is derived, singular/plural correct, and never invented', () => {
    // Unit-level, because the SENTENCE is the disclosure and a wrong number here is
    // the defect the whole slice exists to prevent.
    expect(atRiskSentence(RESET_AT_RISK_NONE)).toBe(LABELS.resetAtRiskNothing);
    expect(
      atRiskSentence({ confirmed_answers: 1, examples_with_progress: 0, exported_artifacts: 0 }),
    ).toBe('1 confirmed answer. Resetting discards it permanently.');
    expect(
      atRiskSentence({ confirmed_answers: 0, examples_with_progress: 1, exported_artifacts: 0 }),
    ).toBe('1 built-in example carrying progress. Resetting discards it permanently.');
    expect(
      atRiskSentence({ confirmed_answers: 2, examples_with_progress: 0, exported_artifacts: 3 }),
    ).toBe(
      '2 confirmed answers and 3 records you exported. Resetting discards them permanently.',
    );
    expect(
      atRiskSentence({ confirmed_answers: 4, examples_with_progress: 5, exported_artifacts: 1 }),
    ).toBe(
      '4 confirmed answers, 5 built-in examples carrying progress and 1 record you ' +
        'exported. Resetting discards them permanently.',
    );
    // a missing block yields nothing at all rather than a fabricated reassurance
    expect(atRiskSentence(undefined)).toBe('');
  });

  it('the at-risk figure is refreshed after a stale refusal', async () => {
    const view = await renderInSession(
      resetDemoRoutes({
        executeStatus: 412,
        execute: demoResetExecuteStale,
        previewRefresh: {
          ...demoResetPreviewClean,
          plan_digest: RESET_PLAN_DIGEST_FRESH,
          at_risk: { confirmed_answers: 9, examples_with_progress: 4, exported_artifacts: 0 },
        },
      }).routes,
    );
    await openReset(view);
    const d = within(dialog(view));
    expect(dialog(view).textContent).toContain('3 confirmed answers');
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: LABELS.resetConfirmAction }));
    await view.findByRole('alert');
    await waitFor(() => expect(dialog(view).textContent).toContain('9 confirmed answers'));
    expect(dialog(view).textContent).not.toContain('3 confirmed answers');
  });
});
