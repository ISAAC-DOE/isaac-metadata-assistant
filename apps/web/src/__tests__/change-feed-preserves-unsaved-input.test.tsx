/*
 * A BACKGROUND UPDATE MUST NOT DESTROY WHAT A SCIENTIST IS TYPING.
 *
 * This is the requirement this whole slice is organised around, and it is here because
 * `CLAUDE.md` §11 records the repository getting it wrong three times: three banners
 * promised "your input is kept" beside a Refresh that destroyed it. Adding a poller
 * that refetches a form is the fastest way to reintroduce that defect, so the guarantee
 * is pinned before anything else can rely on it.
 *
 * WHAT IS ASSERTED, AND HOW. The LIVE `value` of the real `<textarea>` a scientist
 * typed into — never a class name, never a banner's presence, never a mock's call
 * count. A test that asserted "the banner appeared" would pass on a build that showed
 * the banner AND cleared the field, which is exactly the shape of the original defect.
 *
 * AND THE NEGATIVE CONTROL IS PART OF THE GUARANTEE, not decoration. The last test in
 * this file reinstates a clobbering refresh and proves the assertion above FAILS
 * against it. Without that, a passing suite cannot distinguish "the input is protected"
 * from "the event never arrived", and the second reads identically to the first.
 *
 * ── A CORRECTION, BECAUSE THE EVIDENCE FOR THIS PROPERTY WAS MISATTRIBUTED ────────
 *
 * The slice's own report claimed this control had been proven by mutation, quoting the
 * symptom `expected '' to be '[{"series_id": "half-typed-by-a-scien…'`. An independent
 * review ran that mutation and a harsher variant and **the symptom does not
 * reproduce** — and this correction is recorded here, in the file, rather than left in
 * a report nobody re-reads.
 *
 * WHAT ACTUALLY HAPPENS UNDER THE MUTATION, re-measured here rather than relayed.
 * Wiring `onEntitiesChanged: () => reload()` into `LoadedCompletion`'s
 * `useRecordSession` makes that reload REMOUNT `LoadedCompletion`, which resets
 * `session.activity` — so FOUR of the five tests fail on `Unable to find an element
 * with the text: /Updated elsewhere:/i`, and none of them reaches its text assertion.
 * Removing that one precondition line and re-running the first test on the mutated
 * build makes it PASS: under the mutation the typed text is **fully intact**, because
 * `staged` is a ref owned by the PARENT, above the component the remount replaces.
 *
 * THE QUOTED SYMPTOM IS REAL, BUT IT BELONGS TO THE NEGATIVE CONTROL AT THE BOTTOM OF
 * THIS FILE — a full `unmount()` plus a fresh `render`, which is the only way a test
 * can destroy the parent's ref from outside. That is why the control has to do it that
 * way, and why it is not decoration.
 *
 * THE PROPERTY IS STILL TRUE. What proves it is not the mutation the report cited; it
 * is the ref's OWNERSHIP, which `GuidedCompletion`'s own comment states accurately, and
 * the negative control below, which shows the assertion failing the moment that owner
 * is destroyed.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { api } from '../lib/api';
import { POLL_INTERVAL_MS } from '../lib/useRecordSync';
import { bundleRoutes, stubFetchRoutes } from '../test/apiFixtures';
import type { ApiChangeEntry, ApiChangeFeedPage } from '../lib/types';

const RUN_ONE = '01RUNAAAAAAAAAAAAAAAAAAAA0';
const TYPED = '[{"series_id": "half-typed-by-a-scientist", "channels": [1, 2, 3]}]';

/** One run-owned SERIES question with NO worked example, which is the only case in
 *  which `StructuredValueEntry` renders a free-text form at all. */
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

function page(over: Partial<ApiChangeFeedPage> = {}): ApiChangeFeedPage {
  return {
    changes: [],
    next_cursor: 'CURSOR-0',
    has_more: false,
    limit: 50,
    returned: 0,
    remaining: 0,
    kinds: ['experiment', 'proposal', 'run'],
    ...over,
  };
}

/** Entries at a revision far above anything the fixture's `version` can hold, so
 *  `summariseChanges` cannot filter them and the event definitely arrives. */
const NEWS: ApiChangeEntry[] = [
  {
    kind: 'experiment',
    entity_id: 'demo',
    changed_at_rev: 9999,
    version: 'gen.9999',
    rev: 9999,
    generation: 'gen',
    updated_utc: '2026-08-30T12:00:00Z',
  },
  {
    kind: 'proposal',
    entity_id: '01SYNTHETICPROPOSALPROPOS',
    changed_at_rev: 9999,
    updated_utc: '2026-08-30T12:00:00Z',
    state: 'open',
  },
];

/*
 * FAKE TIMERS ARE INSTALLED BEFORE `render`, AND THAT ORDERING IS THE WHOLE HARNESS.
 *
 * The first version of this file installed them AFTER awaiting `findByText`. The
 * poller's first `setTimeout` had therefore already been scheduled on the REAL clock,
 * so advancing the fake one fired nothing, the change event never arrived, and the
 * preservation assertion passed for exactly the wrong reason — the defect the negative
 * control at the bottom of this file exists to catch, arriving through the harness
 * rather than through the product.
 *
 * So: fake timers first, then settle the bundle's promises by advancing zero
 * milliseconds (which flushes microtasks without moving the poll cadence), then query
 * synchronously. `findBy*` is deliberately not used — under fake timers its own
 * polling is what has to be driven, and driving it explicitly is clearer than
 * configuring it.
 */
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

/** Let the bundle fetches resolve without advancing the poll cadence. */
async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

/** Advance past one poll cadence and let the response be applied. */
async function onePoll() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS + 50);
  });
}

/** Mount the completion screen with fake timers already running, and settle it. */
async function mountCompletion() {
  vi.useFakeTimers();
  vi.spyOn(Math, 'random').mockReturnValue(0.5);
  const screen = renderComplete();
  await settle();
  // The premise of every test here: the run-owned question is on screen.
  expect(screen.getByText('300 K')).toBeInTheDocument();
  return screen;
}

function routes(overrides: Record<string, unknown> = {}) {
  return {
    ...bundleRoutes('demo'),
    'GET /api/experiments/demo/pending': { body: { pending: [seriesQuestion(RUN_ONE, '300 K')] } },
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('a change-feed update arriving while a scientist is mid-answer', () => {
  it('CRITICAL: the typed text is still in the field, character for character', async () => {
    stubFetchRoutes(routes());
    const changes = vi
      .spyOn(api, 'getChanges')
      .mockResolvedValue(page({ changes: NEWS, returned: 2 }));

    const screen = await mountCompletion();

    const field = screen.getByLabelText(/series json/i) as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: TYPED } });
    expect(field.value).toBe(TYPED); // the premise, so a later pass cannot be vacuous

    // A colleague edits the record. The poll lands while the scientist is typing.
    await onePoll();
    expect(changes).toHaveBeenCalled(); // the event really arrived
    // …and it really reached the screen, which is the OTHER half of not being vacuous.
    expect(screen.getByText(/Updated elsewhere:/i)).toBeInTheDocument();

    // THE ASSERTION: the live value of the element the scientist typed into. Read
    // fresh from the DOM rather than through the stale reference, so a remount that
    // replaced the node with an empty one is caught rather than missed.
    const after = screen.getByLabelText(/series json/i) as HTMLTextAreaElement;
    expect(after.value).toBe(TYPED);
  });

  it('surfaces a stale state instead of silently replacing the edit', async () => {
    /*
     * PRESERVING THE INPUT IS ONLY HALF OF IT. A scientist whose record moved under
     * them must be TOLD, or they submit against a revision they never saw — so the
     * guarantee is "keep the text AND say what happened", never "keep the text
     * quietly".
     */
    stubFetchRoutes(routes());
    vi.spyOn(api, 'getChanges').mockResolvedValue(page({ changes: NEWS, returned: 2 }));

    const screen = await mountCompletion();
    fireEvent.change(screen.getByLabelText(/series json/i), { target: { value: TYPED } });
    await onePoll();

    // Announced politely, in a status region — not an alert, and not a modal.
    const note = screen.getByText(/Updated elsewhere:/i);
    const region = note.closest('[role="status"]');
    expect(region).not.toBeNull();
    expect(region!.getAttribute('aria-live')).toBe('polite');

    // And it states the input guarantee on this surface, because this surface holds
    // unsent input.
    expect(note.textContent).toMatch(/Nothing you have typed is changed or cleared/i);

    // ONE sentence for the batch, not one per entry: two entries arrived.
    expect(screen.queryAllByText(/Updated elsewhere:/i)).toHaveLength(1);

    // The text is STILL there beside the notice — the two are not a trade.
    expect((screen.getByLabelText(/series json/i) as HTMLTextAreaElement).value).toBe(TYPED);
  });

  it('does not re-announce when a later poll says the same thing', async () => {
    /*
     * THE FLOODING GUARD. A record under active edit produces entries on every poll.
     * The message is compared as a STRING, so an identical summary arriving in a new
     * object announces nothing further — which is what keeps a screen-reader user's
     * live region usable.
     */
    stubFetchRoutes(routes());
    vi.spyOn(api, 'getChanges').mockResolvedValue(page({ changes: NEWS, returned: 2 }));
    const screen = await mountCompletion();

    await onePoll();
    const first = screen.getByText(/Updated elsewhere:/i).textContent;
    for (let i = 0; i < 4; i += 1) await onePoll();

    expect(screen.queryAllByText(/Updated elsewhere:/i)).toHaveLength(1);
    expect(screen.getByText(/Updated elsewhere:/i).textContent).toBe(first);
  });

  it('exposes NO proposal content on the completion screen', async () => {
    /*
     * The feed serves a `proposal` kind. It carries lifecycle coordinates and nothing
     * else, and the server pins that on the wire — this asserts the client end: a
     * canary value attached to the entry reaches no rendered text.
     */
    stubFetchRoutes(routes());
    vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({
        changes: [
          {
            ...NEWS[1],
            // Fields the server does not send. If a surface ever spread an entry
            // instead of reading named fields, this is what would appear.
            proposed_value: 'LEAKCANARYVALUE',
            target_field_path: 'field:system.technique',
          } as unknown as ApiChangeEntry,
        ],
        returned: 1,
      }),
    );

    const screen = await mountCompletion();
    await onePoll();

    // The whole rendered document, not just the notice — a leak anywhere counts.
    const body = document.body.textContent ?? '';
    expect(screen.getByText(/Updated elsewhere:/i)).toBeInTheDocument(); // it did render
    for (const leak of [
      'LEAKCANARYVALUE',
      'field:system.technique',
      '01SYNTHETICPROPOSALPROPOS',
    ]) {
      expect(body).not.toContain(leak);
    }
  });

  it('NEGATIVE CONTROL: the same assertion FAILS once the staged store is destroyed', async () => {
    /*
     * WITHOUT THIS TEST THE FIRST ONE PROVES NOTHING. A harness in which the change
     * event never reaches the screen passes the preservation assertion for the wrong
     * reason and reads exactly like a harness in which the input is protected — and
     * that is not hypothetical: the first version of this file did precisely that, by
     * installing fake timers after `render`.
     *
     * So the clobber is reinstated in the only way a test can reinstate it from
     * outside the component: the staged store is destroyed by tearing the screen down
     * and building it again, which is what a refresh WOULD do to the field if
     * `GuidedCompletion` did not hold staged answers in a ref above the component
     * `reload` remounts. The typed text is then gone — and that is what proves the
     * protection in the first test is that ref doing work.
     *
     * It asserts the FAILURE, so this test goes red if the clobber stops clobbering,
     * i.e. if the control loses its ability to tell the two situations apart.
     */
    stubFetchRoutes(routes());
    vi.spyOn(api, 'getChanges').mockResolvedValue(page({ changes: NEWS, returned: 2 }));

    const screen = await mountCompletion();
    const field = screen.getByLabelText(/series json/i) as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: TYPED } });
    expect(field.value).toBe(TYPED);

    // Confirm the protected path first, in the SAME test, so the control and the
    // thing it controls for are compared under one set of conditions.
    await onePoll();
    expect((screen.getByLabelText(/series json/i) as HTMLTextAreaElement).value).toBe(TYPED);

    // THE CLOBBER.
    screen.unmount();
    const reborn = renderComplete();
    await settle();

    const after = reborn.getByLabelText(/series json/i) as HTMLTextAreaElement;
    // With the staged store destroyed, the text is NOT preserved. If this ever comes
    // back as TYPED, this control has stopped distinguishing the two situations and
    // the guarantee above must be re-derived rather than trusted.
    expect(after.value).not.toBe(TYPED);
    expect(after.value).toBe('');
  });
});
