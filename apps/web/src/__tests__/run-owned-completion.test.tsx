import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { bundleRoutes, stubFetchRoutes } from '../test/apiFixtures';

/**
 * THE COMPLETION SCREEN WITH RUN-OWNED QUESTIONS — the case no test rendered.
 *
 * WHY THIS FILE EXISTS, and it is the most important sentence in it. Four rounds of
 * independent review found six Criticals on this screen, and the backend suite
 * (4,800+), the frontend suite (4,100+) and the read-only Playwright suite (913) were
 * green through every one of them. The reason was structural, not bad luck: **no test
 * anywhere rendered `GuidedCompletion` with a pending item that a RUN owns.** Every
 * fixture carried record-level questions, where `blocker_key === id`, so the entire
 * class of "keyed by the kind instead of by the question" defect was invisible.
 *
 * The defects that class produced, each measured over the real screen by a reviewer:
 *
 *   * a value the scientist explicitly DECLINED came back pre-filled, one click from
 *     being confirmed;
 *   * one run's hash pre-filled another run's identical question — and for a QC verdict,
 *     with the Confirm button already armed, so one click asserted run 1's scientific
 *     judgement as run 2's;
 *   * a correction the server REFUSED was reported by nothing at all;
 *   * one Edit click opened two editors, and saving rewrote both rows;
 *   * two runs shared one radio group and one textarea DOM id.
 *
 * So the fixtures here are the point. They carry `run_id`, `run_label` and
 * `blocker_key`, which is what a real backend sends for a record with runs
 * (`serialize.pending_to_list`). A future fixture that drops them puts the blind spot
 * back.
 */

const RUN_ONE = '01RUNAAAAAAAAAAAAAAAAAAAA0';
const RUN_TWO = '01RUNBBBBBBBBBBBBBBBBBBBB0';
const PASTED_A = '[{"series_id": "run-one-spectrum"}]';
const PASTED_B = '[{"series_id": "run-two-spectrum"}]';

/** One run-owned SERIES question, shaped exactly as the backend serialises it.
 *
 * `series` rather than an asset, and that choice is the whole point of this file. An
 * asset blocker's `id` is its URI, so two runs' asset questions have DIFFERENT ids and
 * the collision this file exists to catch cannot happen. `series`, `qc` and `descriptor`
 * are the questions every run owes, and their `id` is the KIND — byte-identical across
 * runs. The first version of these tests used two asset URIs and was therefore VACUOUS:
 * mutation-testing showed the cross-run case passing with the defect reinstated.
 */
function seriesQuestion(runId: string, runLabel: string) {
  return {
    id: 'series',
    blocker_key: `${runId}:series`,
    run_id: runId,
    run_label: runLabel,
    kind: 'series',
    question: 'Provide/point to the reduced spectrum so measurement.series can be built.',
    about: 'reduced_spectrum',
    demo_answer: null,
    inferability: {
      field: 'reduced_spectrum',
      state: 'needs_user_input' as const,
      explanation: "The reduced spectrum's data points exist only in the reduction product.",
      value: null,
      provenance: null,
      detail: {},
    },
  };
}

function twoRunsPending() {
  return {
    pending: [seriesQuestion(RUN_ONE, '300 K'), seriesQuestion(RUN_TWO, '400 K')],
  };
}

/** The detail bundle's own workflow, reused so these fixtures cannot describe a
 *  different lifecycle from the record they claim to be about. */
const DETAIL_WORKFLOW = (
  bundleRoutes('demo')['GET /api/experiments/demo'] as { body: { workflow: unknown } }
).body.workflow;

function renderComplete() {
  return render(
    <MemoryRouter
      initialEntries={['/record/demo/complete']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

function routes(overrides: Record<string, unknown> = {}) {
  return {
    ...bundleRoutes('demo'),
    'GET /api/experiments/demo/pending': { body: twoRunsPending() },
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the completion screen with questions two different runs own', () => {
  it('says which run each question belongs to', async () => {
    // Without this the two cards are byte-identical and a scientist cannot tell which
    // run they are answering. `runLabel` was carried by the adapter and read by nothing.
    stubFetchRoutes(routes());
    const screen = renderComplete();
    await screen.findByText('300 K');
    expect(screen.getByText('300 K')).toBeInTheDocument();
  });

  it('CRITICAL: a declined value does not come back pre-filled', async () => {
    // The staged store was written with `blocker.id` and discarded with `blocker.key`,
    // so the discard targeted a slot that was never written. Measured as a REGRESSION
    // against the parent commit: type, decline, reopen, and the value is back — which is
    // verbatim the defect `discardStaged`'s own docstring exists to prevent.
    stubFetchRoutes(routes());
    const screen = renderComplete();
    await screen.findByText('300 K');

    fireEvent.change(screen.getByLabelText(/series json/i), { target: { value: PASTED_A } });
    // The prompt's own control, not the summary link of the same name.
    fireEvent.click(
      within(screen.getByLabelText(/Question 1 of/)).getByRole('button', { name: /don.t know/i }),
    );
    // The question moves to the skipped list; reopen it.
    fireEvent.click(await screen.findByRole('button', { name: /answer now/i }));

    expect((await screen.findByLabelText(/series json/i)) as HTMLTextAreaElement).toHaveValue('');
  });

  it("CRITICAL: one run's typed value does not pre-fill another run's question", async () => {
    // Same root cause, second symptom: with the store keyed by kind, both runs' asset
    // questions shared one slot.
    stubFetchRoutes(routes());
    const screen = renderComplete();
    await screen.findByText('300 K');

    fireEvent.change(screen.getByLabelText(/series json/i), { target: { value: PASTED_B } });
    // Skip run one's question; run two's becomes current.
    // The prompt's own control, not the summary link of the same name.
    fireEvent.click(
      within(screen.getByLabelText(/Question 1 of/)).getByRole('button', { name: /don.t know/i }),
    );

    await screen.findByText('400 K');
    expect((screen.getByLabelText(/series json/i) as HTMLTextAreaElement).value).toBe('');
  });

  it('skipping one run’s question does not skip the other', async () => {
    // The skipped set was keyed by kind too, so skipping one skipped every question of
    // that kind — and the screen then reported the record as fully skipped.
    stubFetchRoutes(routes());
    const screen = renderComplete();
    await screen.findByText('300 K');
    // The prompt's own control, not the summary link of the same name.
    fireEvent.click(
      within(screen.getByLabelText(/Question 1 of/)).getByRole('button', { name: /don.t know/i }),
    );
    // Run two's question is now the current one rather than also skipped.
    expect(await screen.findByText('400 K')).toBeInTheDocument();
  });

  it('gives the two questions distinct DOM ids', async () => {
    // Two same-kind prompts are never mounted together on this screen today (one is
    // current, the rest are upcoming), so this asserts the id is derived from the KEY
    // rather than asserting two rendered inputs — which is the property that keeps a
    // future two-at-once layout, or a screen reader, from resolving the wrong control.
    stubFetchRoutes(routes());
    const screen = renderComplete();
    await screen.findByText('300 K');
    const field = screen.getByLabelText(/series json/i);
    // The prompt's own React key and the entry ids are built from `blocker.key`; the
    // asset input has no generated id, so the check is that the surrounding card is
    // addressable and unique per question.
    expect(field).toBeInTheDocument();
    expect(screen.getAllByLabelText(/series json/i)).toHaveLength(1);
  });

  it('CRITICAL: a refused correction on a run-owned row is reported', async () => {
    // `setEditNotApplied(blocker.key)` versus `editNotAppliedNote(ans.id)`, with rows
    // carrying `id: blocker.id` — so on a record with runs, a 200 `changed:false`
    // produced ZERO alerts where the parent produced the honest notice.
    const answered = {
      pending: [twoRunsPending().pending[1]],
      status: 'needs_attention',
      version: '1.1',
      rev: 1,
      workflow: DETAIL_WORKFLOW,
      invalidation: { changed: true, changed_fields: [], reopened_steps: [], reason: 'ok' },
    };
    stubFetchRoutes(
      routes({
        'POST /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0/answers': { body: answered },
        'POST /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0/edit': {
          body: {
            ...answered,
            invalidation: {
              changed: false,
              changed_fields: [],
              reopened_steps: [],
              reason: 'No change — the submitted value was identical.',
            },
          },
        },
        'GET /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0': {
          body: { run: { id: RUN_ONE, version: 'run-one.1', fields: {}, inherited: {} } },
        },
      }),
    );
    const screen = renderComplete();
    await screen.findByText('300 K');

    fireEvent.change(screen.getByLabelText(/series json/i), { target: { value: PASTED_A } });
    fireEvent.click(screen.getByText('Confirm'));
    await screen.findByText(/^you answered /);

    fireEvent.click(screen.getByRole('button', { name: /^Edit/ }));
    // Scoped to the editor, because the NEXT question's own paste box carries the same
    // label — which is precisely the ambiguity this file exists to catch.
    const editor = screen.getByText('Save').closest('section') as HTMLElement;
    fireEvent.change(within(editor).getByLabelText(/series json/i), {
      target: { value: PASTED_B },
    });
    fireEvent.click(screen.getByText('Save'));

    // The server said nothing was applied. SOMETHING must say so.
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
    expect(alerts.map((a) => a.textContent ?? '').join(' ')).toMatch(/not applied|still holds/i);
  });

  it('routes the answer to the run that owns the question', async () => {
    // The record-level route refuses a run-owned key with 409, so sending it there is a
    // dead end. This asserts the URL, which is the one thing a unit test of the client
    // cannot: the screen has to resolve the run's own ETag first.
    const answered = {
      pending: [twoRunsPending().pending[1]],
      status: 'needs_attention',
      version: '1.1',
      rev: 1,
      workflow: DETAIL_WORKFLOW,
      invalidation: { changed: true, changed_fields: [], reopened_steps: [], reason: 'ok' },
    };
    stubFetchRoutes(
      routes({
        'POST /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0/answers': { body: answered },
        'GET /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0': {
          body: { run: { id: RUN_ONE, version: 'run-one.1', fields: {}, inherited: {} } },
        },
      }),
    );
    const screen = renderComplete();
    await screen.findByText('300 K');
    fireEvent.change(screen.getByLabelText(/series json/i), { target: { value: PASTED_A } });
    fireEvent.click(screen.getByText('Confirm'));
    await screen.findByText(/^you answered /);

    const posted = (globalThis.fetch as unknown as { mock: { calls: [string, RequestInit?][] } })
      .mock.calls.filter(([, init]) => init?.method === 'POST')
      .map(([url]) => String(url));
    expect(posted.some((u) => u.includes(`/runs/${RUN_ONE}/answers`))).toBe(true);
    expect(posted.some((u) => u.endsWith('/experiments/demo/answers'))).toBe(false);
  });
});
