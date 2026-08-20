import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within, waitFor } from '@testing-library/react';
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

/**
 * `ApiInvalidation` AS THE BACKEND ACTUALLY SENDS IT — all six keys.
 *
 * The first version of these fixtures carried four, omitting `rev` and `artifact`.
 * `stubFetchRoutes` is untyped, so it typechecked; the cost was concrete and an
 * independent review hit it: `GuidedCompletion` renders
 * `editImpact.artifact?.state`, so the first test to cover the APPLIED edit path
 * crashed on the fixture rather than failing on the product. The file's own header
 * warns that a fixture dropping backend-shaped keys puts the blind spot back — and
 * that is exactly what these two objects had done.
 */
const INVALIDATION = {
  changed: true,
  rev: 1,
  changed_fields: [] as string[],
  reopened_steps: [] as string[],
  artifact: { state: 'none' as const, reason: null },
  reason: 'ok',
};

const RUN_ONE = '01RUNAAAAAAAAAAAAAAAAAAAA0';
const RUN_TWO = '01RUNBBBBBBBBBBBBBBBBBBBB0';
const PASTED_A = '[{"series_id": "run-one-spectrum"}]';
const PASTED_B = '[{"series_id": "run-two-spectrum"}]';
/** The corrected spectrum, shaped so the ROW'S OWN RENDERING changes observably.
 *  `adapt.answerValuePreview` reads `series_id` and counts `channels`, so both are
 *  different from `PASTED_A`'s — otherwise the test would pass on the defect by
 *  finding an unchanged string. */
const CORRECTED_SERIES =
  '[{"series_id": "run-one-corrected", "channels": [1, 2]}]';

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

/** One run-owned QC question. `qc`'s `id` is the KIND, like `series`. */
function qcQuestion(runId: string, runLabel: string) {
  return {
    id: 'qc',
    blocker_key: `${runId}:qc`,
    run_id: runId,
    run_label: runLabel,
    kind: 'qc',
    question: 'Record the QC verdict for this measurement.',
    about: 'qc',
    demo_answer: null,
    inferability: {
      field: 'qc',
      state: 'needs_user_input' as const,
      explanation: 'A QC verdict is scientific judgement and no rule derives it.',
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

  it('gives two SIMULTANEOUSLY MOUNTED prompts distinct DOM ids', async () => {
    /*
     * THIS TEST WAS VACUOUS AND A REVIEW MEASURED IT. Its first version asserted that
     * one input exists and that there is exactly one of it — nothing about ids —
     * and reverting `idPrefix={`entry-${blocker.key}`}` to `blocker.id` left it GREEN.
     * Its own comment conceded it "asserts the id is derived from the KEY", which it
     * did not do, and called the control "the asset input" while the fixture is a
     * `series` question.
     *
     * The comment's premise was also wrong: two same-kind prompts DO mount together
     * on this screen. Answering a question and pressing Edit mounts the editor's
     * prompt beside the next question's — which is the arrangement that makes a
     * shared DOM id a real ambiguity for a screen reader and a real
     * `duplicate-id` axe finding, not a hypothetical one.
     *
     * So this now walks the reader into that arrangement and reads the ids.
     */
    stubFetchRoutes(
      routes({
        'POST /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0/answers': {
          body: {
            pending: [twoRunsPending().pending[1]],
            status: 'needs_attention',
            version: '1.1',
            rev: 1,
            workflow: DETAIL_WORKFLOW,
            invalidation: { ...INVALIDATION },
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

    // TWO prompts, and their inputs must not share an id.
    const inputs = screen.getAllByLabelText(/series json/i) as HTMLTextAreaElement[];
    expect(inputs).toHaveLength(2);
    const ids = inputs.map((i) => i.id);
    expect(ids.every(Boolean), 'an id-less input cannot be unambiguously labelled').toBe(true);
    expect(new Set(ids).size).toBe(2);
    // AND THE ID IS DERIVED FROM THE KEY, not from the kind — which is the property
    // the revert broke and this test now fails on. Both runs own a `series` question,
    // so an id built from `blocker.id` is byte-identical for the two.
    expect(ids.some((id) => id.includes(RUN_ONE))).toBe(true);
  });

  it('gives two simultaneously mounted QC prompts distinct radio, note and hint ids', async () => {
    /*
     * THE SAME PROPERTY FOR THE `qc` CONTROL, which is where it matters most and was
     * the one part left unpinned. A review measured that reverting only
     * `qc-hint-${blocker.key}` to `blocker.id` left the whole suite green — and that
     * pair is the target of `aria-describedby`, so a duplicate makes a screen reader
     * read one prompt's description for the other's verdict. A QC verdict is
     * scientific judgement; the wrong description beside it is the worst place on
     * this screen for an ambiguity.
     *
     * The radio group `name` is asserted too: two groups sharing a name are ONE group
     * to the browser, so selecting run 2's verdict would clear run 1's.
     */
    stubFetchRoutes(
      routes({
        'GET /api/experiments/demo/pending': {
          body: { pending: [qcQuestion(RUN_ONE, '300 K'), qcQuestion(RUN_TWO, '400 K')] },
        },
        'POST /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0/answers': {
          body: {
            pending: [qcQuestion(RUN_TWO, '400 K')],
            status: 'needs_attention',
            version: '1.1',
            rev: 1,
            workflow: DETAIL_WORKFLOW,
            invalidation: { ...INVALIDATION },
          },
        },
        'GET /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0': {
          body: { run: { id: RUN_ONE, version: 'run-one.1', fields: {}, inherited: {} } },
        },
      }),
    );
    const screen = renderComplete();
    await screen.findByText('300 K');
    fireEvent.click(screen.getByLabelText('valid'));
    fireEvent.change(screen.getByLabelText(/how was it determined/i), { target: { value: 'looks clean' } });
    fireEvent.click(screen.getByText('Confirm'));
    await screen.findByText(/^you answered /);
    fireEvent.click(screen.getByRole('button', { name: /^Edit/ }));

    const radios = screen.getAllByLabelText('valid') as HTMLInputElement[];
    expect(radios).toHaveLength(2);
    /* NO ID IS ASSERTED ON THE RADIOS, and finding that out is why this comment is
       here. The first version of this test required two DISTINCT ids and failed with
       `expected 1 to be 2` — because these inputs carry NO id at all: each is wrapped
       in its own `<label>`, which is implicit association and needs none. The
       assertion was wrong, not the markup. What matters for a radio is the `name`. */
    expect(radios.every((r) => r.id === '')).toBe(true);
    // TWO GROUPS, NOT ONE. A shared `name` makes these mutually exclusive to the
    // browser, so selecting run 2's verdict would silently clear run 1's — a
    // scientific judgement erased by answering a different measurement.
    expect(new Set(radios.map((r) => r.name)).size).toBe(2);
    expect(radios.some((r) => r.name.includes(RUN_ONE))).toBe(true);

    const notes = screen.getAllByLabelText(/how was it determined/i) as HTMLTextAreaElement[];
    expect(notes).toHaveLength(2);
    expect(new Set(notes.map((n) => n.id)).size).toBe(2);
    // THE HINT, reached through `aria-describedby` rather than by its id directly,
    // because that is the path a screen reader takes and the reason the id matters.
    const described = notes.map((n) => n.getAttribute('aria-describedby'));
    expect(described.every(Boolean)).toBe(true);
    expect(new Set(described).size).toBe(2);
    for (const id of described) {
      expect(document.querySelectorAll(`#${CSS.escape(id!)}`)).toHaveLength(1);
    }
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
      invalidation: { ...INVALIDATION },
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

  it('CRITICAL: an APPLIED correction on a run-owned row updates the row it edited', async () => {
    /*
     * THE HALF THE `changed: false` TEST DOES NOT COVER, and an independent review
     * measured that the whole suite stayed green when `saveEdit`'s row match was
     * reverted from `a.id === blocker.key` to `a.id === blocker.id`. The other half of
     * that same fix (`id: blocker.key` on the row) IS pinned by the refused-correction
     * test above; this half was not.
     *
     * The failure it leaves is an honesty defect of exactly the class this branch
     * keeps closing: the server APPLIES the correction (`200`, `changed: true`), no
     * answered row matches, and the summary goes on rendering the OLD value under
     * "you answered" while the record holds the new one. A reader is shown a
     * confirmed value the record does not have.
     *
     * A record-level row can never catch it, because there `blocker_key === id` and
     * the two matches are the same comparison.
     */
    const applied = {
      pending: [twoRunsPending().pending[1]],
      status: 'needs_attention',
      version: '1.1',
      rev: 1,
      workflow: DETAIL_WORKFLOW,
      invalidation: { ...INVALIDATION },
    };
    stubFetchRoutes(
      routes({
        'POST /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0/answers': { body: applied },
        // The server APPLIES it — `changed: true`, which is the difference from the
        // refused-correction case above.
        'POST /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0/edit': { body: applied },
        'GET /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0': {
          body: { run: { id: RUN_ONE, version: 'run-one.1', fields: {}, inherited: {} } },
        },
      }),
    );
    const screen = renderComplete();
    await screen.findByText('300 K');

    fireEvent.change(screen.getByLabelText(/series json/i), { target: { value: PASTED_A } });
    fireEvent.click(screen.getByText('Confirm'));
    const row = await screen.findByText(/^you answered /);
    const before = row.textContent ?? '';

    fireEvent.click(screen.getByRole('button', { name: /^Edit/ }));
    const editor = screen.getByText('Save').closest('section') as HTMLElement;
    fireEvent.change(within(editor).getByLabelText(/series json/i), {
      target: { value: CORRECTED_SERIES },
    });
    fireEvent.click(screen.getByText('Save'));

    // THE ROW MOVED, and to the corrected value specifically — not merely to
    // something different. `run-one-corrected · 2 channels` is the row's own
    // rendering of the value that was just typed.
    const after = await screen.findByText(/^you answered /);
    expect(after.textContent).not.toBe(before);
    expect(after.textContent).toMatch(/run-one-corrected · 2 channels/);
    // AND THE EDITOR CLOSED, which only happens on the applied path — so a test that
    // passed on the defect by finding a stale row cannot also pass this.
    expect(screen.queryByText('Save')).toBeNull();
    // NOTHING SAYS THE CORRECTION WAS REFUSED. The not-applied notice is the other
    // branch's, and rendering both would be two contradictory claims on one screen.
    const alerts = screen.queryAllByRole('alert').map((a) => a.textContent ?? '');
    expect(alerts.join(' ')).not.toMatch(/not applied|still holds/i);
  });

  it('CRITICAL: the assistant stages the CURRENT question and writes to ITS run', async () => {
    /*
     * THE WIRING, WHICH WAS ENTIRELY UNPINNED. An independent review deleted
     * `runId: currentBlocker.runId` (`GuidedCompletion`) and then both
     * `blockerKey: stageField.key` and `runId: stageField.runId`
     * (`AssistantPanel.onStageUserAnswer`) and the whole 4,100-test frontend suite
     * stayed green — because `assistant-agent.test.ts` calls `stageAnswer` with those
     * fields passed BY HAND. It covers the library; nothing covered the path from the
     * screen's current question into the proposal, and that path IS the defect that
     * was fixed: the panel had no way to know which run it was answering.
     *
     * Reinstatable with zero failures is the same as unfixed, one revert away. So this
     * drives the real components — screen mounts panel, panel stages, user confirms —
     * and reads the URL the write went to.
     *
     * A `demo_answer` is required for the staging affordance to render at all
     * (`canStage` needs `suggestedValue`), which is why these fixtures carry one.
     * That is also the honest limit on the scenario: `demo_answer` is served only in
     * example scope, so end-to-end this is reachable when a reader adds a run inside a
     * walkthrough session. The wiring is wrong or right regardless.
     */
    const suggested = [{ series_id: 'suggested-spectrum', channels: [1] }];
    const withDemo = (q: ReturnType<typeof seriesQuestion>) => ({
      ...q,
      demo_answer: { value: suggested, label: 'Example value from the walkthrough' },
    });
    stubFetchRoutes(
      routes({
        'GET /api/experiments/demo/pending': {
          body: {
            pending: [
              withDemo(seriesQuestion(RUN_ONE, '300 K')),
              withDemo(seriesQuestion(RUN_TWO, '400 K')),
            ],
          },
        },
        // BOTH runs' routes are stubbed, deliberately. Stubbing only the expected
        // one would make a write to the wrong run fail as an unstubbed request —
        // the test would go red for the right reason by accident, and would say
        // "the request failed" rather than "it went to the wrong run".
        'POST /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0/answers': {
          body: {
            pending: [withDemo(seriesQuestion(RUN_TWO, '400 K'))],
            status: 'needs_attention',
            version: '1.1',
            rev: 1,
            workflow: DETAIL_WORKFLOW,
            invalidation: { ...INVALIDATION },
          },
        },
        'POST /api/experiments/demo/runs/01RUNBBBBBBBBBBBBBBBBBBBB0/answers': {
          body: {
            pending: [],
            status: 'ready_to_export',
            version: '1.1',
            rev: 1,
            workflow: DETAIL_WORKFLOW,
            invalidation: { ...INVALIDATION },
          },
        },
        'GET /api/experiments/demo/runs/01RUNAAAAAAAAAAAAAAAAAAAA0': {
          body: { run: { id: RUN_ONE, version: 'run-one.1', fields: {}, inherited: {} } },
        },
        'GET /api/experiments/demo/runs/01RUNBBBBBBBBBBBBBBBBBBBB0': {
          body: { run: { id: RUN_TWO, version: 'run-two.7', fields: {}, inherited: {} } },
        },
      }),
    );
    const screen = renderComplete();
    await screen.findByText('300 K');

    /* THE CURRENT QUESTION MUST NOT BE THE FIRST PENDING ENTRY, and finding that out
       is what made this test real. Its first version staged on question 1 and passed
       with all three wiring fields DELETED — because `confirmProposal` falls back to
       matching on `field` (the KIND) when no `blockerKey` arrives, and the first
       `series` entry it finds is run one's, which is the run the test expected. The
       test agreed with the defect by coincidence.
       Skipping question 1 makes run TWO current, so the fallback resolves to the
       WRONG run and the assertion below fails — which is verbatim the C4 defect: one
       run's spectrum written onto another, with that other run's `If-Match`. */
    fireEvent.click(
      within(screen.getByLabelText(/Question 1 of/)).getByRole('button', {
        name: /don.t know/i,
      }),
    );
    await screen.findByText('400 K');

    // The panel's own staging control, not the prompt's "Use This Suggestion".
    const stage = within(
      screen.getByRole('group', { name: /stage an answer for the current field/i }),
    ).getByRole('button', { name: /stage answer/i });
    fireEvent.click(stage);

    /* A PROPOSAL, not a write. Confirm is what writes — and the Confirm SCOPED TO THE
       PANEL, because the GuidedPrompt on the same screen has one of its own. Two
       controls with the same accessible name is the ambiguity this whole file exists
       to catch, so it is resolved rather than worked around with an index. */
    const panel = screen.getByRole('complementary', { name: /assistant/i });
    const confirm = await within(panel).findByRole('button', { name: /^confirm$/i });
    fireEvent.click(confirm);

    /* AWAITED ON THE WRITE ITSELF, not on a screen transition. The assistant's confirm
       path does not re-render the completion screen's question list — asserting on
       "400 K" appearing would be asserting something this path does not do, and would
       fail for a reason unrelated to the wiring under test. */
    const calls = () =>
      (globalThis.fetch as unknown as { mock: { calls: [string, RequestInit?][] } }).mock.calls;
    await waitFor(() =>
      expect(calls().some(([, init]) => init?.method === 'POST')).toBe(true),
    );
    const posted = calls()
      .filter(([, init]) => init?.method === 'POST')
      .map(([url]) => String(url));
    // THE RUN THAT OWNS THE CURRENT QUESTION — run TWO, not run one, and not the
    // record. Run one is the one a kind-based fallback would have picked.
    expect(posted.some((u) => u.includes(`/runs/${RUN_TWO}/answers`))).toBe(true);
    expect(posted.some((u) => u.includes(`/runs/${RUN_ONE}/answers`))).toBe(false);
    expect(posted.some((u) => u.endsWith('/experiments/demo/answers'))).toBe(false);
    // AND IT USED THE RUN'S OWN ETag, which is the other half of the fix: the
    // record's token here is a 412 the reader would be told to resolve by
    // refreshing something that was never stale.
    const write = calls().find(
      ([url, init]) =>
        init?.method === 'POST' && String(url).includes(`/runs/${RUN_TWO}/answers`),
    );
    const headers = (write?.[1]?.headers ?? {}) as Record<string, string>;
    expect(headers['If-Match']).toBe('"run-two.7"');

    /*
     * WHAT THIS TEST PINS AND WHAT IT DOES NOT, measured rather than assumed, because
     * a coverage claim that overstates itself is the defect this file exists to catch.
     *
     * PINNED. Deleting `blockerKey: stageField.key` from
     * `AssistantPanel.onStageUserAnswer` fails this test. That is the wiring that
     * matters: without it `confirmProposal` falls back to matching on the KIND and
     * resolves to whichever run's question comes first in the list.
     *
     * NOT PINNED, and named rather than implied. Deleting either `runId` — the
     * screen's `runId: currentBlocker.runId` or the panel's `runId:
     * stageField.runId` — leaves this test GREEN, and no test on this screen can
     * change that. `confirmProposal` reads `open?.run_id ?? proposal.runId`, and
     * `open` is found through `blockerKey`, so the proposal's own copy is a FALLBACK
     * used only when the staged question is absent from the agent context's pending
     * list at confirm time. Both lists come from the same `GET /pending`, so a unit
     * test cannot make them disagree; reaching it needs a write to land between
     * staging and confirming. It is genuinely reachable and genuinely not
     * deterministically constructible here.
     *
     * The fallback's own behaviour is covered at the library level in
     * `assistant-agent.test.ts`. What was missing, and is now here, is that the
     * screen → panel → library path is live at all.
     */
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
      invalidation: { ...INVALIDATION },
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
