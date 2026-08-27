/*
 * A PENDING ENTRY THE SERVER READ BUT CANNOT BE ANSWERED — SAID ACCURATELY, ONCE.
 *
 * WHY THIS FILE EXISTS, and why it is separate from `unreadable-pending-entry.test.tsx`.
 * That file pins the entry the server COULD NOT READ. An independent review found that
 * the client was applying the same copy, the same predicate and the same silence to a
 * SECOND class the server marks `unavailable`, and getting all of it wrong:
 *
 *   - a stored `{"question": "q?"}` with no `kind` is READ perfectly well — the server
 *     serves the prose — and is UNANSWERABLE, because the answer key is the kind and
 *     there is none (`POST /answers` refuses the fabricated `"blocker"` key **422
 *     `unrecognized_field`**, measured over HTTP). The screen said "1 stored question
 *     could not be read" and rendered the scientist's own sentence NOWHERE;
 *   - `assistantComposer.explain_pending_item` interpolated `${item.question}` under a
 *     comment asserting the field was non-optional — a premise the widening commit had
 *     itself deleted — and rendered the literal `"null"` for `{"kind": "qc"}`, a shape
 *     the API accepts an answer for (measured **200**);
 *   - "Every question reviewed this visit" gated on `!blocker`, which stopped meaning
 *     "every question" the moment `blocker` began deriving from the ANSWERABLE subset;
 *   - two divergent "unreadable" predicates disagreed, so the assistant offered to
 *     stage a value under an answer key nothing accepts;
 *   - and an answerable entry carrying a non-string `question` reached
 *     `<h2>{blocker.question}</h2>`, which React refuses to render. There is no
 *     ErrorBoundary anywhere in this application, so the page blanks.
 *
 * The rule these tests pin: what a surface SAYS must be true of every entry it counts,
 * the prose the server sent must appear somewhere, and ONE predicate decides
 * answerability everywhere.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, render, renderHook } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { UNREADABLE_BLOCKER_LABEL, isAnswerablePendingItem, pendingSummary } from '../lib/adapt';
import { api } from '../lib/api';
import { COMPLETE_CATALOG } from '../lib/assistantComposer';
import { clearAllSessions } from '../lib/assistantSession';
import { useRecordSession } from '../lib/useRecordSession';
import type { ApiExperimentDetail, ApiPendingItem, GroundingState } from '../lib/types';
import {
  EXP_ID,
  bundleRoutes,
  evidenceClassificationResponse,
  experimentDetail,
  stubFetchRoutes,
} from '../test/apiFixtures';

/**
 * READ, BUT UNANSWERABLE. What `serialize.pending_to_list` emits for a stored
 * `{"question": "Which detector was used?"}` — prose preserved, every key that would be
 * an answer key `null`, and a reason that says WHY rather than claiming a failed read.
 */
const NO_KIND: ApiPendingItem = {
  id: null,
  kind: null,
  question: 'Which detector was used?',
  about: null,
  demo_answer: null,
  inferability: null,
  run_id: null,
  run_label: null,
  blocker_key: null,
  unavailable: true,
  unavailable_reason:
    'this stored blocking question names no kind, so ISAAC has no key an answer could be submitted under',
};

/** UNREADABLE: no prose either. The other class, kept beside it for contrast. */
const NO_PROSE: ApiPendingItem = {
  ...NO_KIND,
  question: null,
  unavailable_reason: 'this stored blocking question is a number, not a question',
};

/** ANSWERABLE, and legitimately carrying no prose — the shape C2 rendered as "null". */
const KIND_ONLY: ApiPendingItem = {
  id: 'qc',
  kind: 'qc',
  question: null,
  about: null,
  demo_answer: null,
  inferability: null,
  run_id: null,
  run_label: null,
  blocker_key: 'qc',
};

const ANSWERABLE: ApiPendingItem = {
  ...KIND_ONLY,
  question: 'What is the QC verdict for this measurement?',
  about: 'measurement.qc.status',
};

// --- C1: the prose is shown, and nothing false is said about it ---------------

describe('C1 — an entry the server READ but cannot be answered', () => {
  it('is labelled with the scientist’s own question, not "could not be read"', () => {
    const summary = pendingSummary(NO_KIND);
    expect(summary.label).toBe('Which detector was used?');
    expect(summary.label).not.toBe(UNREADABLE_BLOCKER_LABEL);
    // The locator is ALWAYS the server's reason — that is what distinguishes the two
    // classes, and what an operator needs in order to repair the stored document.
    expect(summary.locator).toBe(NO_KIND.unavailable_reason);
  });

  it('falls back to the generic label only when the server sent no prose', () => {
    expect(pendingSummary(NO_PROSE).label).toBe(UNREADABLE_BLOCKER_LABEL);
    expect(pendingSummary({ ...NO_KIND, question: '   ' }).label).toBe(UNREADABLE_BLOCKER_LABEL);
  });
});

// --- I8: a non-string question can never reach a renderer ----------------------

describe('I8 — an answerable entry carrying non-prose', () => {
  const OBJECT_QUESTION = { ...KIND_ONLY, question: { a: 1 } as unknown as string };

  it('is not classed answerable, so it cannot reach <h2>{blocker.question}</h2>', () => {
    expect(isAnswerablePendingItem(OBJECT_QUESTION)).toBe(false);
    // The two shapes that ARE legitimate stay legitimate — this guard must not become
    // the "requiring the prose" version the predicate's own docstring warns against.
    expect(isAnswerablePendingItem(KIND_ONLY)).toBe(true);
    expect(isAnswerablePendingItem(ANSWERABLE)).toBe(true);
    // `undefined` too — a recorded fixture may omit the key entirely. Cast because the
    // wire type declares `string | null`; the predicate has to survive a response that
    // does not, which is the whole reason the `typeof` checks are not redundant with
    // the `unavailable` flag.
    expect(
      isAnswerablePendingItem({ ...KIND_ONLY, question: undefined as unknown as string }),
    ).toBe(true);
  });

  it('rejects every other non-prose JSON type too', () => {
    for (const q of [7, true, ['a'], { a: 1 }]) {
      expect(isAnswerablePendingItem({ ...KIND_ONLY, question: q as unknown as string })).toBe(
        false,
      );
    }
  });
});

// --- C2 / I10: no consumer renders "null", and none promises a missing control --

function completeState(pending: ApiPendingItem[], selectedPendingId?: string): GroundingState {
  return {
    context: 'complete',
    detail: experimentDetail,
    pending,
    selectedPendingId,
  } as unknown as GroundingState;
}

/** The chip's own resolved text, read through the catalog the panel renders. */
function textOf(pending: ApiPendingItem[], chipId: string, selected?: string): string {
  const chip = COMPLETE_CATALOG.find((c) => c.id === chipId);
  expect(chip, `chip ${chipId} is missing`).toBeTruthy();
  const message = chip!.resolve(completeState(pending, selected));
  expect(message, `chip ${chipId} resolved to null`).toBeTruthy();
  return message!.text;
}

describe('C2 — the assistant never interpolates a null field', () => {
  it('explains a kind-with-no-prose question without printing "null"', () => {
    const text = textOf([KIND_ONLY], 'explain_pending_item', 'qc');
    expect(text.toLowerCase()).not.toContain('null');
    expect(text).toContain('Answer via propose → stage → confirm below.');
    // The subject falls back down the SAME ladder `pendingSummary` uses, so the two
    // surfaces cannot name the same field differently.
    expect(text.startsWith('qc.')).toBe(true);
  });

  it('is unchanged for an ordinary question with prose', () => {
    const text = textOf([ANSWERABLE], 'explain_pending_item', 'qc');
    expect(text).toBe(
      'What is the QC verdict for this measurement? — about measurement.qc.status. ' +
        'Answer via propose → stage → confirm below.',
    );
  });
});

describe('I10 — the assistant does not promise a control that is not there', () => {
  it('drops "Confirm or skip each below" when an entry has no widget', () => {
    const summary = textOf([ANSWERABLE, NO_KIND], 'pending_summary');
    expect(summary).not.toContain('Confirm or skip each below.');
    expect(summary).toContain('cannot be answered here');
    // THE COUNT IS NOT FILTERED. Both entries block the record, and filtering them out
    // of the count is the "all resolved" lie every surface here exists to prevent.
    expect(summary).toContain('2 fields');
  });

  it('keeps it when every entry really is answerable', () => {
    const summary = textOf([ANSWERABLE, KIND_ONLY], 'pending_summary');
    expect(summary).toContain('Confirm or skip each below.');
  });

  it('names an unreadable entry by the server’s reason, never "unnamed pending field"', () => {
    const summary = textOf([NO_PROSE], 'pending_summary');
    expect(summary).not.toContain('unnamed pending field');
    expect(summary).toContain('is a number, not a question');
  });
});

// --- I9: one predicate, everywhere ---------------------------------------------

describe('I9 — the hook and the screen agree on what is answerable', () => {
  const CASES: Array<[string, ApiPendingItem]> = [
    ['read but unanswerable', NO_KIND],
    ['unreadable', NO_PROSE],
    ['answerable, no prose', KIND_ONLY],
    ['answerable', ANSWERABLE],
    ['truthy non-boolean unavailable', { ...ANSWERABLE, unavailable: 1 as unknown as boolean }],
    ['non-string question', { ...ANSWERABLE, question: { a: 1 } as unknown as string }],
  ];

  beforeEach(() => {
    clearAllSessions();
    vi.spyOn(api, 'getEvidenceClassification').mockResolvedValue(
      evidenceClassificationResponse as never,
    );
    vi.spyOn(api, 'checkRecordVersion').mockResolvedValue({ changed: false } as never);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAllSessions();
  });

  it.each(CASES)('agrees on %s', async (_name, item) => {
    vi.spyOn(api, 'getPendingPage').mockResolvedValue({ pending: [item] } as never);
    const { result } = renderHook(() =>
      useRecordSession(EXP_ID, { detail: experimentDetail as unknown as ApiExperimentDetail }),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    // ONE predicate. The hook used to run `p.unavailable === true || p.id === null`,
    // which disagreed with the screen for the FIRST case (`unreadable: false` over an
    // entry the screen called unanswerable, so `assistantAgent` offered to stage a value
    // under the answer key `"blocker"` — refused 422 `unrecognized_field`, so nothing
    // submitted could ever close it). It also failed OPEN on a truthy non-boolean flag
    // where the shared predicate fails CLOSED, and inferred from `id === null`, which is
    // the inference `serialize`'s wire discriminator exists to make unnecessary.
    expect(result.current.context!.pending[0].unreadable).toBe(!isAnswerablePendingItem(item));
  });
});

// --- the completion screen -----------------------------------------------------

function routes(pending: ApiPendingItem[]) {
  return {
    ...bundleRoutes('demo'),
    'GET /api/experiments/demo': {
      body: {
        ...experimentDetail,
        id: 'demo',
        pending_count: pending.length,
        status: 'needs_attention',
      },
    },
    'GET /api/experiments/demo/pending': { body: { pending } },
  };
}

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

describe('the completion screen over a read-but-unanswerable entry', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the prose, and says only what is true of every entry it counts', async () => {
    stubFetchRoutes(routes([NO_KIND]));
    const screen = renderComplete();

    // THE DEFECT: this text appeared nowhere at all — the entry is excluded from the
    // queue, and the disclosure printed only a count and a reason.
    await screen.findByText('Which detector was used?');
    // AND THE FALSE SENTENCE IS GONE. The disclosure counts BOTH classes, so it may
    // only claim what is true of both.
    expect(screen.queryByText(/stored question could not be read/i)).toBeNull();
    expect(screen.getByText(/stored question cannot be answered here/i)).toBeTruthy();
    expect(screen.getByText(/this record stays blocked/i)).toBeTruthy();
    // Still no control — being READ does not make it ANSWERABLE.
    expect(screen.container.querySelector('.guided')).toBeNull();
  });

  it('announces the disclosure the same way as its sibling, and names the region', async () => {
    stubFetchRoutes(routes([NO_KIND]));
    const screen = renderComplete();
    await screen.findByText('Which detector was used?');
    const region = screen.container.querySelector(
      '[aria-label="Stored questions that cannot be answered here"]',
    );
    expect(region).not.toBeNull();
    // `role="note"` is not announced. Its sibling ("N more open questions are not shown
    // here") is a live `status`, and this block carries the more consequential sentence
    // — and it is NOT initial-render-only: it appears after "Show more questions" and
    // after an answer changes the list.
    expect(region!.getAttribute('role')).toBe('status');
  });

  it('renders rather than blanking when an answerable entry carries a non-string question', async () => {
    stubFetchRoutes(routes([{ ...ANSWERABLE, question: { a: 1 } as unknown as string }]));
    const screen = renderComplete();
    // The page still exists. Before the predicate was narrowed, React threw "Objects are
    // not valid as a React child" from the prompt heading, and with no ErrorBoundary
    // anywhere the whole tree unmounted.
    await screen.findByText(/cannot be answered here/i);
    expect(screen.container.querySelector('.guided-question')).toBeNull();
  });

  it('does not claim every question was reviewed while an unanswerable entry is held', async () => {
    stubFetchRoutes(routes([ANSWERABLE, NO_KIND]));
    const screen = renderComplete();
    await screen.findByText('Which detector was used?');

    // Skip the one answerable question. "I don't know" sends nothing — which is exactly
    // why the panel's claim has to be scoped to what it can see.
    const skip = Array.from(screen.container.querySelectorAll('button')).find((b) =>
      /don.t know/i.test(b.textContent ?? ''),
    );
    expect(skip, 'the skip control should be present for the answerable question').toBeTruthy();
    await act(async () => {
      skip!.click();
      await Promise.resolve();
    });

    // With every ANSWERABLE question skipped and a single page held, the old guard
    // (`!blocker && skippedItems.length > 0 && notShown === 0`) was satisfied — over a
    // second entry the reader was never shown here and which still blocks the record.
    expect(screen.queryByText(/Every question reviewed this visit/i)).toBeNull();
  });

  it('still shows the panel when every entry on the page really is answerable', async () => {
    stubFetchRoutes(routes([ANSWERABLE]));
    const screen = renderComplete();
    await screen.findByText('What is the QC verdict for this measurement?');
    const skip = Array.from(screen.container.querySelectorAll('button')).find((b) =>
      /don.t know/i.test(b.textContent ?? ''),
    );
    await act(async () => {
      skip!.click();
      await Promise.resolve();
    });
    // THE NEGATIVE CONTROL. Adding `unreadable.length === 0` must not disable the panel
    // in the state it was written for.
    expect(screen.getByText(/Every question reviewed this visit/i)).toBeTruthy();
  });
});
