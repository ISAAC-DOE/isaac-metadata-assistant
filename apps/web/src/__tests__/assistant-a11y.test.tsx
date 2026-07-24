/*
 * P34.5 (part 1) — accessibility, degradation, and long-content hardening of the
 * free-form Assistant added in P34.1–P34.4.
 *
 * These tests pin the a11y + robustness contract of the NEW assistant elements
 * (composer, single live region, provenance, stale row + Ask again, follow-ups,
 * Clear). Where a guarantee already held before this slice it is asserted here
 * rather than re-implemented; where it was genuinely deficient (focus after
 * Clear; a defensive timeout) the fix is covered.
 *
 * Everything exercised is READ-ONLY: only api.askAssistant / api.askMemory are
 * ever called — never submitAnswer / editField / confirmProposal.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, waitFor, within } from '@testing-library/react';

// Mock the router so NavSourceChip's navigation is observable without a <Router>.
const { navigateSpy } = vi.hoisted(() => ({ navigateSpy: vi.fn() }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateSpy }));

import { AssistantPanel } from '../components/AssistantPanel';
import { ApiError, api } from '../lib/api';
import * as agentModule from '../lib/assistantAgent';
import { ASSISTANT_EMPTY_STATE, ASSISTANT_UNAVAILABLE } from '../lib/assistant';
import { clearAllSessions } from '../lib/assistantSession';
import type { AssistantMessage, AssistantQueryResponse, SuggestedPrompt } from '../lib/types';

const EXP = '01EXPERIMENTA0000000000000';

const REPLY: AssistantMessage = { text: 'Two fields still need you.', answeredFrom: 'workflow' };
const PROMPTS: SuggestedPrompt[] = [
  {
    text: 'What still needs me?',
    answeredFrom: 'workflow',
    answer: { text: 'Two fields still need you.', answeredFrom: 'workflow' },
  },
];

function answerResponse(over: Partial<AssistantQueryResponse> = {}): AssistantQueryResponse {
  return {
    answer: 'The record is a Cu K-edge XANES draft; the current step is Complete Metadata.',
    result: 'answered',
    grounding: ['workflow'],
    sources: [{ label: 'Workflow & Artifacts', navigate_to: null }],
    record_rev: 5,
    version: 'gen.5',
    stale: false,
    followups: [],
    ...over,
  };
}

function panel(extra: Record<string, unknown> = {}) {
  return render(
    <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId={EXP} recordRev={5} {...extra} />,
  );
}

async function submit(getByRole: (r: string) => HTMLElement, text: string) {
  const box = getByRole('textbox');
  fireEvent.change(box, { target: { value: text } });
  fireEvent.submit(box.closest('form')!);
}

beforeEach(() => {
  clearAllSessions();
  sessionStorage.clear();
  navigateSpy.mockReset();
});
afterEach(() => {
  clearAllSessions();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe('P34.5 accessible names', () => {
  it('composer input + send control have real accessible names and Enter (form submit) queries', async () => {
    const spy = vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole, getByLabelText } = panel();
    // the input's accessible name comes from its aria-label
    const box = getByRole('textbox');
    expect(getByLabelText(/ask the assistant a question/i)).toBe(box);
    // the icon-only submit control still has a name and is a real keyboard button
    const send = getByRole('button', { name: /send question/i });
    expect(send.tagName).toBe('BUTTON');
    expect(send.getAttribute('type')).toBe('submit');
    // Enter inside a single-field form submits the form natively — modelled by a
    // form submit, which issues the read-only query.
    fireEvent.change(box, { target: { value: 'what is this record?' } });
    fireEvent.submit(box.closest('form')!);
    expect(spy).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(spy).toHaveBeenCalled());
  });

  it('provenance list, nav chips, follow-ups, Ask again, and Clear all have accessible names', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({
        sources: [
          { label: 'Record Workbench', navigate_to: `/record/${EXP}` },
          { label: 'Evidence Audit', navigate_to: null },
        ],
        followups: ['What is the edge?'],
      }),
    );
    const { getByRole, container } = panel();
    // two submits: the first archives into the log (so Clear appears), the second
    // is the CURRENT answer (so its provenance + follow-up chips are shown)
    await submit(getByRole, 'what is this record?');
    await waitFor(() => expect(container.querySelector('.assistant-provenance')).toBeTruthy());
    await submit(getByRole, 'and the edge?');
    await waitFor(() =>
      expect(container.querySelectorAll('.assistant-msg').length).toBeGreaterThan(0),
    );

    // the cited-sources list is a named list
    const list = getByRole('list', { name: /cited sources/i });
    expect(list).toBeTruthy();
    // a nav chip's accessible name is its source label
    within(list).getByRole('button', { name: 'Record Workbench' });
    // a non-nav source is NOT a focusable button (a plain label span)
    const plain = within(list).getByText('Evidence Audit');
    expect(plain.tagName).toBe('SPAN');
    expect(within(list).queryByRole('button', { name: 'Evidence Audit' })).toBeNull();

    // the follow-up chip is named by its question text
    getByRole('button', { name: /What is the edge\?/ });
    // Clear conversation is named + keyboard-operable (native button)
    const clear = getByRole('button', { name: /clear conversation/i });
    expect(clear.tagName).toBe('BUTTON');
  });

  it('the live stale row associates with the answer and offers a named Ask again', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse({ record_rev: 5 }));
    const { getByRole, container, rerender } = panel();
    await submit(getByRole, 'what is this record?');
    await waitFor(() => expect(container.querySelector('.assistant-provenance')).toBeTruthy());

    // advance the record → the SAME live answer is now stale
    rerender(
      <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId={EXP} recordRev={9} />,
    );
    const reply = container.querySelector('.assistant-reply') as HTMLElement;
    const stale = container.querySelector('.assistant-msg-stale') as HTMLElement;
    // programmatic association: the answer region points at the stale note
    expect(reply.getAttribute('aria-describedby')).toBe(stale.id);
    getByRole('button', { name: /ask again with the current record/i });
  });
});

describe('P34.5 single live region', () => {
  it('exactly one polite live region announces loading → answer; the history log is aria-live="off"', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole, container } = panel();

    // the conversation log carries an explicit aria-live="off" (its implicit
    // role="log" polite live region is suppressed so archived turns are silent)
    const log = getByRole('log');
    expect(log.getAttribute('aria-live')).toBe('off');

    // exactly ONE polite live region exists (the reply <p>) — no second noisy one
    const polite = container.querySelectorAll('[aria-live="polite"]');
    expect(polite.length).toBe(1);
    const reply = polite[0] as HTMLElement;
    expect(reply.classList.contains('assistant-reply')).toBe(true);

    // loading is announced first, in that one region, with aria-busy
    await submit(getByRole, 'what is this record?');
    expect(reply.getAttribute('aria-busy')).toBe('true');
    expect(reply.textContent).toMatch(/working/i);

    // then the resolved answer replaces it in the SAME region (busy clears)
    await waitFor(() => expect(reply.textContent).toMatch(/Cu K-edge XANES draft/i));
    expect(reply.getAttribute('aria-busy')).toBeNull();
    // still exactly one polite region after resolve
    expect(container.querySelectorAll('[aria-live="polite"]').length).toBe(1);
  });

  it('an error answer is announced in the SAME single live region (not a new one)', async () => {
    vi.spyOn(api, 'askAssistant').mockRejectedValue(new ApiError('down', { unreachable: true }));
    const { getByRole, container } = panel();
    await submit(getByRole, 'anything');
    const reply = container.querySelector('.assistant-reply') as HTMLElement;
    await waitFor(() => expect(reply.textContent).toContain(ASSISTANT_UNAVAILABLE));
    expect(container.querySelectorAll('[aria-live="polite"]').length).toBe(1);
    expect(reply.getAttribute('aria-busy')).toBeNull();
  });
});

describe('P34.5 focus management', () => {
  it('focus moves to the answer region after a query resolves', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole, container } = panel();
    await submit(getByRole, 'what is this record?');
    const reply = container.querySelector('.assistant-reply') as HTMLElement;
    await waitFor(() => expect(reply.textContent).toMatch(/Cu K-edge XANES draft/i));
    await waitFor(() => expect(document.activeElement).toBe(reply));
  });

  it('after Clear, focus returns to the composer input (never lost to <body>)', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole, getByText, container } = panel();

    // ask twice so the first archives into the log and Clear appears
    await submit(getByRole, 'q one');
    await waitFor(() => expect(getByText(/Cu K-edge XANES draft/i)).toBeInTheDocument());
    await submit(getByRole, 'q two');
    await waitFor(() =>
      expect(container.querySelectorAll('.assistant-msg').length).toBeGreaterThan(0),
    );

    fireEvent.click(getByRole('button', { name: /clear conversation/i }));
    const box = getByRole('textbox');
    expect(document.activeElement).toBe(box);
    // and the rail is back at rest
    expect(getByText(ASSISTANT_EMPTY_STATE)).toBeInTheDocument();
  });
});

describe('P34.5 degradation robustness', () => {
  it('a rejected query clears loading, re-enables the composer, shows unavailable, and does not throw', async () => {
    vi.spyOn(api, 'askAssistant').mockRejectedValue(new ApiError('down', { unreachable: true }));
    const { getByRole, getByText, container } = panel();
    await submit(getByRole, 'anything');
    await waitFor(() => expect(getByText(ASSISTANT_UNAVAILABLE)).toBeInTheDocument());
    // loading resolved: aria-busy cleared and the send control is enabled again
    const reply = container.querySelector('.assistant-reply') as HTMLElement;
    expect(reply.getAttribute('aria-busy')).toBeNull();
    const send = getByRole('button', { name: /send question/i }) as HTMLButtonElement;
    expect(send.disabled).toBe(false);
    // the composer stays usable — the input still accepts a fresh question
    const box = getByRole('textbox') as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'again' } });
    expect(box.value).toBe('again');
  });

  it('an assistant failure never touches record/workflow mutation controls', async () => {
    vi.spyOn(api, 'askAssistant').mockRejectedValue(new ApiError('down', { unreachable: true }));
    const submitSpy = vi.spyOn(api, 'submitAnswer');
    const editSpy = vi.spyOn(api, 'editField');
    const confirmSpy = vi.spyOn(agentModule, 'confirmProposal');
    const { getByRole, getByText } = panel();
    await submit(getByRole, 'anything');
    await waitFor(() => expect(getByText(ASSISTANT_UNAVAILABLE)).toBeInTheDocument());
    expect(submitSpy).not.toHaveBeenCalled();
    expect(editSpy).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('a hung query is bounded by a defensive timeout → composer un-sticks to unavailable', async () => {
    vi.useFakeTimers();
    try {
      // a query that never settles on its own
      vi.spyOn(api, 'askAssistant').mockReturnValue(new Promise<never>(() => {}));
      const { getByRole, container } = panel();
      const box = getByRole('textbox');
      fireEvent.change(box, { target: { value: 'hangs forever' } });
      fireEvent.submit(box.closest('form')!);

      const reply = container.querySelector('.assistant-reply') as HTMLElement;
      expect(reply.getAttribute('aria-busy')).toBe('true');

      // advance past the client-side ceiling; the timeout rejects → unavailable
      await vi.advanceTimersByTimeAsync(20001);
      expect(reply.textContent).toContain(ASSISTANT_UNAVAILABLE);
      expect(reply.getAttribute('aria-busy')).toBeNull();
      const send = getByRole('button', { name: /send question/i }) as HTMLButtonElement;
      expect(send.disabled).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('P34.5 long-content wrapping (no forced inline width)', () => {
  const LONG =
    'Supercalifragilisticexpialidocious'.repeat(6) +
    ' a very long grounded answer that must wrap within the panel and never force horizontal scroll';

  it('a very long answer renders in the wrapping reply region with no inline width', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ answer: LONG, followups: [LONG] }),
    );
    const { getByRole, container } = panel();
    await submit(getByRole, LONG);
    const reply = container.querySelector('.assistant-reply') as HTMLElement;
    await waitFor(() => expect(reply.textContent).toContain('Supercalifragilistic'));
    // the wrapping class is applied and no forced inline width is set
    expect(reply.classList.contains('assistant-reply')).toBe(true);
    expect(reply.style.width).toBe('');
    // the follow-up label carries the wrapping class + no inline width
    const followup = container.querySelector('.assistant-followup') as HTMLElement;
    expect(followup).toBeTruthy();
    expect(followup.style.width).toBe('');
  });

  it('a long question archived into the log wraps in the message bubble class', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole, container } = panel();
    // first turn, then a second submit archives the first (question + answer)
    await submit(getByRole, LONG);
    await waitFor(() => expect(container.querySelector('.assistant-reply')!.textContent).toMatch(/Cu K-edge/i));
    await submit(getByRole, 'second');
    await waitFor(() => expect(container.querySelectorAll('.assistant-msg').length).toBeGreaterThan(0));
    const userBubble = container.querySelector('.assistant-msg-user') as HTMLElement;
    expect(userBubble).toBeTruthy();
    expect(userBubble.textContent).toContain('Supercalifragilistic');
    // the bubble uses the wrapping class and sets no forced inline width
    expect(userBubble.style.width).toBe('');
  });
});
