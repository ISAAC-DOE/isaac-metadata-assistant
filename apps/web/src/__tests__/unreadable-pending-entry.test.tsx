/*
 * A PENDING ENTRY THE SERVER COULD NOT READ IS DISCLOSED — NEVER RENDERED AS A QUESTION.
 *
 * WHY THIS FILE EXISTS. `GET /api/experiments/{id}/pending` used to answer **500** for a
 * persisted `draft["pending"]` holding anything that is not a question object (`[7]`,
 * `["a string"]`, `[None]`, or a bare `7`, which `workspace._blocker_entries` turns into
 * `[7]`). It now serves ONE entry per stored blocker and marks the unreadable one
 * `unavailable: true` with an `unavailable_reason` naming the shape it found, inventing
 * no `id`, `kind`, `question`, example answer or inferability decision
 * (`serialize._unreadable_blocker`).
 *
 * That fixes the read and hands the CLIENT a shape it had never seen. Rendered through
 * the ordinary path it produced, measured in this suite before the changes under test:
 *
 *   - `pendingSummary` -> `{ label: null }`, an EMPTY row in the "Needs You" list;
 *   - `pendingItemToBlocker` -> `label: titleCase(String(null))` = **"Null"**, an empty
 *     question, `inputType: 'text'` — a free-text box for a blocker no answer can close;
 *   - `itemKey` -> `null` for every such entry, so skipping one skipped ALL of them;
 *   - the assistant, had the entry been filtered out instead, answering "there are no
 *     pending fields — none is currently blocking" over a record that is refused for
 *     exactly that entry.
 *
 * The rule these tests pin: an unreadable entry is COUNTED (the record stays blocked),
 * NAMED (the server's own reason is shown), and NOT ANSWERABLE (no control, no answer
 * key, no claim that the work is done).
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, render, renderHook, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  UNREADABLE_BLOCKER_LABEL,
  isAnswerablePendingItem,
  pendingSummary,
} from '../lib/adapt';
import { api } from '../lib/api';
import { clearAllSessions } from '../lib/assistantSession';
import { runIntent } from '../lib/assistantAgent';
import { useRecordSession } from '../lib/useRecordSession';
import type { AgentContext } from '../lib/assistantAgent';
import type { ApiExperimentDetail, ApiPendingItem } from '../lib/types';
import {
  EXP_ID,
  bundleRoutes,
  evidenceClassificationResponse,
  experimentDetail,
  stubFetchRoutes,
} from '../test/apiFixtures';

/** Exactly what `serialize._unreadable_blocker` emits — every key, every null. */
const UNREADABLE: ApiPendingItem = {
  id: null,
  kind: null,
  question: null,
  about: null,
  demo_answer: null,
  inferability: null,
  run_id: null,
  run_label: null,
  blocker_key: null,
  unavailable: true,
  unavailable_reason: 'this stored blocking question is a number, not a question',
};

/** One ordinary, answerable question, shaped as the same serializer emits it. */
const ANSWERABLE: ApiPendingItem = {
  id: 'qc',
  kind: 'qc',
  question: 'What is the QC verdict for this measurement?',
  about: 'measurement.qc.status',
  demo_answer: null,
  inferability: {
    field: 'measurement.qc.status',
    state: 'needs_user_input' as const,
    explanation: 'A QC verdict is a scientific judgement; it must come from you.',
    value: null,
    provenance: null,
    detail: {},
  },
  run_id: null,
  run_label: null,
  blocker_key: 'qc',
};

// --- the adapters ------------------------------------------------------------

describe('the adapters partition an unreadable entry out of the answerable path', () => {
  it('names it, and shows the SERVER reason rather than a guess', () => {
    const summary = pendingSummary(UNREADABLE);
    expect(summary.label).toBe(UNREADABLE_BLOCKER_LABEL);
    expect(summary.locator).toBe(UNREADABLE.unavailable_reason);
    // NOT the old rendering: `KIND_LABEL[null] ?? null` was null, an empty row.
    expect(summary.label).not.toBeNull();
    expect(summary.label.toLowerCase()).not.toContain('null');
  });

  it('refuses it as answerable, on the SERVER flag first', () => {
    expect(isAnswerablePendingItem(UNREADABLE)).toBe(false);
    expect(isAnswerablePendingItem(ANSWERABLE)).toBe(true);
    // THE FLAG IS LOAD-BEARING ON ITS OWN. An entry that carried a readable id and kind
    // but was still marked unavailable must be refused — otherwise the client would be
    // overruling the server's own statement about its document.
    expect(
      isAnswerablePendingItem({ ...ANSWERABLE, unavailable: true }),
    ).toBe(false);
    // AND SO ARE THE TYPE CHECKS, for a response that omits the flag (an older backend
    // or a fixture): a null id is not an answer key.
    expect(isAnswerablePendingItem({ ...UNREADABLE, unavailable: undefined })).toBe(false);
  });

  it('does NOT reject an entry that merely has no question text', () => {
    /* A REGRESSION GUARD ON THE GUARD, and it is not hypothetical: the first version of
     * `isAnswerablePendingItem` also required `typeof question === 'string'`. The server
     * authors no question prose it was not given, so a stored `{"kind": "qc"}` is served
     * with `question: null` and IS answerable — `POST /answers {"qc": ...}` takes it.
     * Requiring the prose would have made the client refuse a question the API accepts,
     * and would have shown "could not read" over an entry the server never called
     * unreadable. */
    const noProse: ApiPendingItem = { ...ANSWERABLE, question: null };
    expect(isAnswerablePendingItem(noProse)).toBe(true);
    // And it is still named — by its kind label, not by an empty string.
    expect(pendingSummary(noProse).label.length).toBeGreaterThan(0);
  });
});

// --- the assistant -----------------------------------------------------------

const CTX = (pending: AgentContext['pending']): AgentContext => ({
  experimentId: '01EXPERIMENTA0000000000000',
  recordRev: 2,
  version: 'genabc.2',
  workflow: { current_step: 'complete_metadata', ordered_steps: [] },
  evidence: [],
  pending,
});

describe('the assistant does not report a blocked record as having nothing pending', () => {
  it('says the entry cannot be read, and does not offer to stage a value for it', () => {
    const out = runIntent('identify_next_missing_field', CTX([
      { id: null, label: UNREADABLE.unavailable_reason!, unreadable: true },
    ]));
    // THE CLAIM THAT MUST NOT APPEAR. Filtering unreadable entries out of the agent's
    // context — the smaller change — produced exactly this sentence over a record the
    // export gate refuses.
    expect(out.text).not.toMatch(/no pending fields/i);
    // AND THE PROMISE THAT MUST NOT APPEAR. There is no answer key to stage a value
    // under, so offering is a promise the confirm step could not keep.
    expect(out.text).not.toMatch(/can stage a value/i);
    expect(out.text).toMatch(/could not read|cannot .*read|not a question/i);
    expect(out.text).toContain(UNREADABLE.unavailable_reason!);
  });

  it('is unchanged for an ordinary question', () => {
    const out = runIntent('identify_next_missing_field', CTX([
      { id: 'qc', label: 'QC Verdict' },
    ]));
    expect(out.text).toContain('QC Verdict');
    expect(out.text).toMatch(/can stage a value/i);
  });

  it('still reports an EMPTY list as nothing pending', () => {
    const out = runIntent('identify_next_missing_field', CTX([]));
    expect(out.text).toMatch(/no pending fields/i);
  });
});

// --- the agent context the assistant actually receives -----------------------
//
// The three tests above run `runIntent` against a hand-built context, so they prove the
// intent behaves — not that the app ever hands it an unreadable entry. That mapping is
// `useRecordSession.toPendingItems`, and it is where the tempting shortcut lives:
// filtering the entry out there passes every test above and produces the false "nothing
// is pending". So the hook is exercised directly.

describe('useRecordSession keeps an unreadable entry in the agent context', () => {
  beforeEach(() => {
    clearAllSessions();
    vi.spyOn(api, 'getPendingPage').mockResolvedValue({
      pending: [UNREADABLE, ANSWERABLE],
    } as never);
    vi.spyOn(api, 'getEvidenceClassification').mockResolvedValue(evidenceClassificationResponse as never);
    vi.spyOn(api, 'checkRecordVersion').mockResolvedValue({ changed: false } as never);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAllSessions();
  });

  it('carries it, flags it, and labels it with the server reason', async () => {
    const { result } = renderHook(() =>
      useRecordSession(EXP_ID, {
        detail: experimentDetail as unknown as ApiExperimentDetail,
      }),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const pending = result.current.context!.pending;
    // KEPT, not filtered: the record is blocked by it, so the assistant must know.
    expect(pending).toHaveLength(2);
    expect(pending[0].unreadable).toBe(true);
    expect(pending[0].id).toBeNull();
    expect(pending[0].label).toBe(UNREADABLE.unavailable_reason);
    // The ordinary entry is untouched by any of this.
    expect(pending[1].unreadable).toBe(false);
    expect(pending[1].id).toBe('qc');
  });
});

// --- the completion screen ---------------------------------------------------

function routes(pending: ApiPendingItem[]) {
  return {
    ...bundleRoutes('demo'),
    'GET /api/experiments/demo': {
      // COHERENT WITH THE LIST. The server counts an unreadable entry as a blocker, so
      // a detail claiming 0 would let an assertion pass off the wrong number.
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the completion screen over an unreadable entry', () => {
  it('discloses it, offers no control for it, and never claims the record is finished', async () => {
    stubFetchRoutes(routes([UNREADABLE]));
    const screen = renderComplete();

    await screen.findByText(UNREADABLE.unavailable_reason!);
    // ~~`/stored question could not be read/i`~~ — the copy is now "cannot be answered
    // here", and the change is a correction rather than a rewording. "Could not be
    // read" is true of THIS entry (a stored number) and was being rendered over a
    // DIFFERENT class the server marks `unavailable`: one whose prose ISAAC read
    // perfectly well and which is unanswerable only because it names no kind. The
    // disclosure counts both, so it may only say what is true of both. The
    // "could not be read" wording survives per-entry, in the server's own reason —
    // asserted by the `findByText` above, which is this entry's actual reason string.
    expect(
      screen.getByText(/stored question cannot be answered here/i),
    ).toBeTruthy();
    expect(screen.getByText(/this record stays blocked/i)).toBeTruthy();

    // NO ANSWERABLE PROMPT. `titleCase(String(null))` produced the label "Null" over a
    // free-text input; the record must offer no way to "answer" an entry that has no
    // answer key.
    expect(screen.queryByText('Null')).toBeNull();
    expect(screen.container.querySelector('.guided-question')).toBeNull();
    // SCOPED TO THE PROMPT, not to the page: the assistant composer's own text input is
    // always mounted and is not a control for this entry. `.guided` is the whole
    // question card — input, confirm button and "I don't know" together — so its absence
    // is the absence of every control this screen could have offered.
    expect(screen.container.querySelector('.guided')).toBeNull();

    // AND NO CLAIM THAT THE WORK IS DONE. This is the honesty defect that filtering the
    // counters (rather than only the queue) would have produced: an empty answerable
    // queue is not a finished record.
    expect(screen.queryByText(/All blockers resolved/i)).toBeNull();
    expect(screen.queryByText(/ready to export/i)).toBeNull();
  });

  it('leaves every OTHER question on the record answerable', async () => {
    stubFetchRoutes(routes([UNREADABLE, ANSWERABLE]));
    const screen = renderComplete();

    // The whole point of serving the entry rather than failing the request: before this,
    // the 500 took the readable question down with it.
    await screen.findByText(ANSWERABLE.question!);
    await waitFor(() => expect(screen.getByText(UNREADABLE.unavailable_reason!)).toBeTruthy());
  });
});
