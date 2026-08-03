import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { api } from '../lib/api';
import {
  stubFetchRoutes,
  resetDemoRoutes,
  demoResetPreviewClean,
  demoResetPreviewAmbiguous,
  demoResetExecuteOk,
} from '../test/apiFixtures';

/*
 * P26.0b — the guarded Reset Workspace control on My Experiments.
 *
 * Behaviour contract (test-first; RED until the control + dialog + api.resetDemo
 * exist). The control:
 *   - renders ONLY when GET /api/health reports mode "synthetic-only" (authoritative,
 *     fail-closed), and is a restrained *destructive* action, never the primary;
 *   - opens a labeled modal dialog that first PREVIEWS (never mutates) via
 *     POST /api/demo/reset {mode:'preview'}, showing the typed counts;
 *   - warns this is a shared hosted example workspace and progress will be discarded;
 *   - requires the operator to type exactly "RESET"; the destructive action stays
 *     disabled until it matches (and always, if any ambiguous record is present);
 *   - on execute sends the exact backend phrase, fires exactly once, then refreshes
 *     the list from the backend and reflects the canonical five;
 *   - refuses safely (no bypass) when the backend refuses, and never leaks a
 *     credential or internal filesystem path.
 *
 * Every fixture is synthetic. The truth core is never bypassed by the UI.
 */

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

function renderHome(routes: Record<string, { status?: number; body: unknown }>) {
  const calls = stubFetchRoutes(routes);
  const view = render(
    <MemoryRouter initialEntries={['/experiments']} future={FUTURE}>
      <AppRoutes />
    </MemoryRouter>,
  );
  return { ...view, calls };
}

/** The parsed JSON bodies of every POST /api/demo/reset the app issued, in order. */
function resetPosts(): Array<{ mode: string; confirmation?: string }> {
  const mock = (globalThis.fetch as unknown as { mock: { calls: [unknown, RequestInit?][] } }).mock;
  return mock.calls
    .filter(([input, init]) => String(input).endsWith('/demo/reset') && init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body ?? '{}')));
}

function countCalls(calls: string[], key: string): number {
  return calls.filter((k) => k === key).length;
}

/** Open the Reset Workspace dialog, focusing the trigger first so focus-return is testable. */
async function openReset(view: ReturnType<typeof renderHome>) {
  const trigger = (await view.findByRole('button', { name: 'Reset Workspace' })) as HTMLButtonElement;
  trigger.focus();
  fireEvent.click(trigger);
  // the dialog appears once the preview resolves
  await view.findByRole('dialog');
  return trigger;
}

function dialog(view: ReturnType<typeof renderHome>) {
  return view.getByRole('dialog');
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- 1–3. presence, synthetic-only gate, non-primary treatment ---------------

describe('P26.0b · Reset Workspace — presence & treatment', () => {
  it('renders the Reset Workspace control on My Experiments in synthetic-only mode', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    expect(await view.findByRole('button', { name: 'Reset Workspace' })).toBeInTheDocument();
  });

  it('does NOT render the control when the backend is not synthetic-only', async () => {
    const view = renderHome(resetDemoRoutes({ mode: 'production' }).routes);
    // wait until the page (and the health probe) have settled
    await view.findByRole('button', { name: 'Open the Worked Example' });
    await waitFor(() =>
      expect(view.queryByRole('button', { name: 'Reset Workspace' })).toBeNull(),
    );
  });

  it('is a restrained destructive action — not the primary on the screen', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    const reset = (await view.findByRole('button', { name: 'Reset Workspace' })) as HTMLButtonElement;
    /*
     * P1 removed the button this test used to reach for. It was labelled "New
     * Record", styled btn-primary, and navigated to the SAME route as the
     * example-run button beside it — promising a capability the build does not
     * have. The screen's one affirmative action inherited the primary treatment,
     * so the property under test is unchanged: SOMETHING affirmative is primary,
     * and Reset must not borrow that styling.
     */
    const primary = view.getByRole('button', {
      name: 'Open the Worked Example',
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

describe('P26.0b · Reset Workspace — preview (non-mutating) & disclosure', () => {
  it('opening the dialog previews (mode:preview) and issues no execute', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    await openReset(view);
    const posts = resetPosts();
    expect(posts).toHaveLength(1);
    expect(posts[0].mode).toBe('preview');
    expect(posts.some((p) => p.mode === 'execute')).toBe(false);
    // no execute confirmation phrase was ever sent
    expect(posts[0].confirmation).toBeUndefined();
  });

  it('preview displays current / canonical / legacy / ambiguous / final counts', async () => {
    const view = renderHome(resetDemoRoutes().routes);
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

  it('states that this is a shared hosted example workspace and progress is discarded', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    await openReset(view);
    const text = (dialog(view).textContent ?? '').toLowerCase();
    expect(text).toContain('shared');
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
});

// --- 9–12. typed confirmation gate; cancel / escape do not mutate -------------

describe('P26.0b · Reset Workspace — confirmation gate', () => {
  it('keeps the destructive action disabled until exactly "RESET" is typed', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    const action = d.getByRole('button', { name: 'Reset Shared Workspace' }) as HTMLButtonElement;
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
    const view = renderHome(resetDemoRoutes().routes);
    const trigger = await openReset(view);
    fireEvent.click(within(dialog(view)).getByRole('button', { name: 'Cancel' }));
    expect(view.queryByRole('dialog')).toBeNull();
    expect(resetPosts().some((p) => p.mode === 'execute')).toBe(false);
    expect(document.activeElement).toBe(trigger);
  });

  it('Escape closes the dialog without mutating and returns focus to the trigger', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    const trigger = await openReset(view);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(view.queryByRole('dialog')).toBeNull();
    expect(resetPosts().some((p) => p.mode === 'execute')).toBe(false);
    expect(document.activeElement).toBe(trigger);
  });

  it('pressing Enter with a non-matching phrase does not execute', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    await openReset(view);
    const input = within(dialog(view)).getByRole('textbox');
    fireEvent.change(input, { target: { value: 'nope' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(resetPosts().some((p) => p.mode === 'execute')).toBe(false);
  });
});

// --- 13–16. dialog a11y: labelled, focus in / trapped / returned --------------

describe('P26.0b · Reset Workspace — dialog accessibility', () => {
  it('is a modal dialog labelled by its visible title', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    await openReset(view);
    const d = dialog(view);
    expect(d.getAttribute('aria-modal')).toBe('true');
    const labelledby = d.getAttribute('aria-labelledby');
    expect(labelledby).toBeTruthy();
    expect(document.getElementById(labelledby!)!.textContent).toMatch(/Reset the Shared Workspace/i);
  });

  it('moves focus into the dialog on open', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    await openReset(view);
    expect(dialog(view).contains(document.activeElement)).toBe(true);
  });

  it('traps Tab within the dialog', async () => {
    const view = renderHome(resetDemoRoutes().routes);
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
    const view = renderHome(resetDemoRoutes().routes);
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

describe('P26.0b · Reset Workspace — single-submit safety', () => {
  it('executing sends the exact backend confirmation phrase exactly once', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: 'Reset Shared Workspace' }));
    await waitFor(() => expect(resetPosts().some((p) => p.mode === 'execute')).toBe(true));
    const executes = resetPosts().filter((p) => p.mode === 'execute');
    expect(executes).toHaveLength(1);
    expect(executes[0].confirmation).toBe('RESET SYNTHETIC DEMO');
  });

  it('double-clicking the destructive action cannot produce two executions', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    const action = d.getByRole('button', { name: 'Reset Shared Workspace' });
    fireEvent.click(action);
    fireEvent.click(action);
    await waitFor(() => expect(resetPosts().some((p) => p.mode === 'execute')).toBe(true));
    expect(resetPosts().filter((p) => p.mode === 'execute')).toHaveLength(1);
  });
});

// --- 20–21. ambiguous refusal is safe and offers no bypass --------------------

describe('P26.0b · Reset Workspace — ambiguous refusal', () => {
  it('when the preview is refused for ambiguity, execution is disabled with no bypass', async () => {
    const view = renderHome(resetDemoRoutes({ preview: demoResetPreviewAmbiguous }).routes);
    await openReset(view);
    const d = within(dialog(view));
    const text = (dialog(view).textContent ?? '').toLowerCase();
    expect(text).toMatch(/refus|cannot|safety|ambiguous/);
    // no "delete it yourself" style bypass is offered
    expect(text).not.toMatch(/delete.*manual|manually delete|override/);
    // typing the phrase must NOT enable execution while ambiguous
    const action = d.getByRole('button', { name: 'Reset Shared Workspace' }) as HTMLButtonElement;
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    expect(action.disabled).toBe(true);
  });

  it('an ambiguous refusal never issues an execute request', async () => {
    const view = renderHome(resetDemoRoutes({ preview: demoResetPreviewAmbiguous }).routes);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    const action = d.getByRole('button', { name: 'Reset Shared Workspace' });
    fireEvent.click(action);
    expect(resetPosts().some((p) => p.mode === 'execute')).toBe(false);
  });
});

// --- 22–24. success refreshes from the backend to the canonical five ----------

describe('P26.0b · Reset Workspace — success refreshes the dashboard', () => {
  it('after a successful reset the experiments list is re-fetched and shows the canonical five', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    // the legacy demo rows are present before the reset (two identically-titled
    // managed-legacy records — use the plural query since the title is shared)
    expect((await view.findAllByText(/Demo \(demo\/run\)/)).length).toBeGreaterThanOrEqual(1);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: 'Reset Shared Workspace' }));

    // the list endpoint is hit again after the execute (initial load + refresh)
    await waitFor(() =>
      expect(countCalls(view.calls, 'GET /api/experiments')).toBeGreaterThanOrEqual(2),
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
    const view = renderHome(resetDemoRoutes().routes);
    await openReset(view);
    const d = within(dialog(view));
    fireEvent.change(d.getByRole('textbox'), { target: { value: 'RESET' } });
    fireEvent.click(d.getByRole('button', { name: 'Reset Shared Workspace' }));
    await waitFor(() => expect(resetPosts().some((p) => p.mode === 'execute')).toBe(true));
    // no unhandled error banner
    expect(view.queryByText(/unexpected error|something went wrong/i)).toBeNull();
  });
});

// --- 25–26. no secret/path leak; existing example-run action intact -----------

describe('P26.0b · Reset Workspace — leak safety & coexistence', () => {
  it('never renders a credential or internal filesystem path', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    await openReset(view);
    const text = view.container.textContent ?? '';
    for (const forbidden of ['Bearer', 'Authorization', 'VITE_API_KEY', '/data/', '/tmp/', 'isaac-workspace']) {
      expect(text).not.toContain(forbidden);
    }
  });

  it('leaves the existing example-run action intact', async () => {
    const view = renderHome(resetDemoRoutes().routes);
    expect(await view.findByRole('button', { name: 'Open the Worked Example' })).toBeInTheDocument();
  });
});

// --- §4 client contract: resetDemo reads the typed body on refusal, not throws -

describe('P26.0b · api.resetDemo — typed outcomes', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('preview returns the typed body on 200', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { body: demoResetPreviewClean } });
    const res = await (api as unknown as { resetDemo: (m: string, c?: string) => Promise<Record<string, unknown>> }).resetDemo('preview');
    expect(res.status).toBe('ok');
    expect(res.legacy_count).toBe(2);
  });

  it('execute success returns the typed body on 200', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { body: demoResetExecuteOk } });
    const res = await (api as unknown as { resetDemo: (m: string, c?: string) => Promise<Record<string, unknown>> }).resetDemo('execute', 'RESET SYNTHETIC DEMO');
    expect(res.status).toBe('ok');
    expect(res.removed_count).toBe(2);
  });

  it('reads the typed refusal body on a 409 (ambiguous) rather than throwing', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { status: 409, body: { ...demoResetPreviewAmbiguous, mode: 'execute' } } });
    const res = await (api as unknown as { resetDemo: (m: string, c?: string) => Promise<Record<string, unknown>> }).resetDemo('execute', 'RESET SYNTHETIC DEMO');
    expect(res.status).toBe('refused');
    expect(res.ambiguous_count).toBe(1);
  });

  it('reads the typed refusal body on a 403 (not synthetic) rather than throwing', async () => {
    stubFetchRoutes({ 'POST /api/demo/reset': { status: 403, body: { ...demoResetPreviewClean, status: 'refused' } } });
    const res = await (api as unknown as { resetDemo: (m: string, c?: string) => Promise<Record<string, unknown>> }).resetDemo('preview');
    expect(res.status).toBe('refused');
  });
});
