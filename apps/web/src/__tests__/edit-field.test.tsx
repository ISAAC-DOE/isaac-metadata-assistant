import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  answersAfterNotebook,
  bundleRoutes,
  editApplied,
  editStaleWrite,
  pendingResponse,
  stubFetchRoutes,
} from '../test/apiFixtures';

/**
 * P28.3 · summary-first + explicit edit of an already-confirmed field. A field
 * confirmed this session renders READ-ONLY (value + Confirmed chip + an explicit
 * Edit button); Edit opens an inline editor prefilled with the current value; Save
 * POSTs /edit with the held If-Match token and adopts the fresh version; Cancel
 * makes no call; a 412 shows the existing stale-write recovery banner.
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

const NOTEBOOK_URI = pendingResponse.pending[0].id; // asset blocker keys on its uri
const SHA = 'c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345';

/** All POST bodies + headers sent to the /edit endpoint (parsed). */
function editPosts(): { body: unknown; ifMatch?: string }[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls
    .filter(([url, init]) => init?.method === 'POST' && String(url).endsWith('/edit'))
    .map(([, init]) => ({
      body: JSON.parse(String(init?.body)),
      ifMatch: (init?.headers as Record<string, string> | undefined)?.['If-Match'],
    }));
}

/** Answer the processing-notebook blocker so it becomes a confirmed summary row. */
async function answerNotebook(screen: ReturnType<typeof renderAt>) {
  const { findByText, getByText, getByLabelText } = screen;
  await findByText('What is the sha256 of the processing notebook?');
  fireEvent.change(getByLabelText('Asset Hash'), { target: { value: SHA } });
  fireEvent.click(getByText('Confirm'));
  // the answered summary row appears (adopting version 1.1 from the response)
  await findByText(/^stored /);
}

function completeRoutes() {
  return {
    ...bundleRoutes('demo'),
    'POST /api/experiments/demo/answers': { body: answersAfterNotebook }, // version → 1.1
  };
}

describe('S4 · summary-first edit of a confirmed field (P28.3)', () => {
  it('a confirmed field renders read-only with a Confirmed chip + an explicit Edit button', async () => {
    stubFetchRoutes(completeRoutes());
    const screen = renderAt('/record/demo/complete');
    await answerNotebook(screen);

    expect(screen.getByText('Confirmed by You')).toBeInTheDocument();
    const editBtn = screen.getByRole('button', { name: /Edit Asset Hash/ });
    expect(editBtn).toBeInTheDocument();
    // read-only summary: no edit input mounted until Edit is clicked
    expect(screen.queryByDisplayValue(SHA)).toBeNull();
  });

  it('entering Edit pre-fills the current value in an inline editor', async () => {
    stubFetchRoutes(completeRoutes());
    const screen = renderAt('/record/demo/complete');
    await answerNotebook(screen);

    fireEvent.click(screen.getByRole('button', { name: /Edit Asset Hash/ }));
    // the GuidedPrompt edit input is prefilled with the confirmed value (uniquely
    // identified by that display value — the still-pending question's input is empty)
    expect(screen.getByDisplayValue(SHA)).toBeInTheDocument();
    // an explicit Save + Cancel are offered
    expect(screen.getByText('Save')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('Cancel makes NO API call and restores the read-only summary', async () => {
    stubFetchRoutes(completeRoutes());
    const screen = renderAt('/record/demo/complete');
    await answerNotebook(screen);

    fireEvent.click(screen.getByRole('button', { name: /Edit Asset Hash/ }));
    fireEvent.click(screen.getByText('Cancel'));

    // back to the summary row, no /edit request issued
    expect(screen.getByRole('button', { name: /Edit Asset Hash/ })).toBeInTheDocument();
    expect(editPosts()).toHaveLength(0);
  });

  it('a successful edit sends the held If-Match, adopts the new version, and surfaces the impact', async () => {
    stubFetchRoutes({
      ...completeRoutes(),
      'POST /api/experiments/demo/edit': { body: editApplied },
    });
    const screen = renderAt('/record/demo/complete');
    await answerNotebook(screen);

    fireEvent.click(screen.getByRole('button', { name: /Edit Asset Hash/ }));
    fireEvent.change(screen.getByDisplayValue(SHA), { target: { value: 'e'.repeat(64) } });
    fireEvent.click(screen.getByText('Save'));

    // the honest downstream-impact (P28.2) is surfaced from the server response
    await screen.findByText('Updated 1 field(s); no downstream steps reopened.');

    const posts = editPosts();
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({
      answers: { [NOTEBOOK_URI]: 'e'.repeat(64) },
      confirmed_by_user: true,
    });
    // the If-Match echoes the version ADOPTED from the prior answer (1.1), not 1.0
    expect(posts[0].ifMatch).toBe('"1.1"');
  });

  it('a 412 on edit shows the existing stale-write recovery banner (no auto-merge, input kept)', async () => {
    stubFetchRoutes({
      ...completeRoutes(),
      'POST /api/experiments/demo/edit': { status: 412, body: editStaleWrite },
    });
    const screen = renderAt('/record/demo/complete');
    await answerNotebook(screen);

    fireEvent.click(screen.getByRole('button', { name: /Edit Asset Hash/ }));
    fireEvent.change(screen.getByDisplayValue(SHA), { target: { value: 'staged-edit' } });
    fireEvent.click(screen.getByText('Save'));

    expect(
      await screen.findByText(
        /This record changed elsewhere\. Nothing was applied — your input is kept\./,
      ),
    ).toBeInTheDocument();
    // no auto-merge: the editor is still mounted with the typed value preserved
    expect(screen.getByDisplayValue('staged-edit')).toBeInTheDocument();
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('viewing/editing a confirmed field issues NO backend request (no hidden workflow mutation)', async () => {
    const calls = stubFetchRoutes(completeRoutes());
    const screen = renderAt('/record/demo/complete');
    await answerNotebook(screen);

    const before = calls.length;
    fireEvent.click(screen.getByRole('button', { name: /Edit Asset Hash/ }));
    // entering edit mode is purely local — the backend-derived workflow is untouched
    expect(calls.length).toBe(before);
    // the sidebar workflow still shows its loaded current step (never locally flipped)
    expect(screen.getAllByText('Complete Metadata').length).toBeGreaterThan(0);
  });
});
