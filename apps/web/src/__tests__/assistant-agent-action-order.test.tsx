/*
 * B-03 — AGENT ACTION ANSWERS LANDED AT THE TOP OF THE CONVERSATION, WITH NO "YOU" LINE.
 *
 * Measured in Chromium: ask a Suggested Question, then run an Agent Action. The action's
 * answer appeared ABOVE the question that was asked first, and nothing said the reader had
 * asked for it. Cause: a typed or suggested question lives as the LIVE turn, rendered
 * after the archived log; an agent result was written straight into the archive without
 * first moving the live turn there, so the log read [agent answer] then [live question,
 * live answer]. Every other turn archives the previous live turn first
 * (`submitQuestion`, `ask`) — this path alone did not — and it also never wrote the
 * reader's own side of the exchange.
 *
 * The fix is at the one choke point (`appendAgentMessage`): the live turn is settled into
 * the log first, then an agent ACTION adds the reader's line (the action's own label),
 * then its answer. Confirm outcomes and Apply-to-Graph come through the same door and so
 * also land after what preceded them, with no invented "You" line — they are results of a
 * control on a card, not a question.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, within } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import { clearAllSessions, loadSession } from '../lib/assistantSession';
import type { AgentContext } from '../lib/assistantAgent';
import type { SuggestedPrompt } from '../lib/types';

const EXP = '01EXPERIMENTA0000000000000';

const CTX: AgentContext = {
  experimentId: EXP,
  recordRev: 5,
  version: 'gen.5',
  workflow: {
    current_step: 'complete_metadata',
    ordered_steps: [
      { id: 'complete_metadata', label: 'Complete Metadata', state: 'current', current: true, reopened: false, blocked: false, reason: null },
    ],
  },
  evidence: [],
  pending: [{ id: 'series', label: 'Reduced Spectrum' }],
};

const PROMPTS: SuggestedPrompt[] = [
  {
    text: 'What still needs me?',
    answeredFrom: 'workflow',
    answer: { text: 'One field still needs you: Reduced Spectrum.', answeredFrom: 'workflow' },
  },
];
const AGENT_PROMPTS = [
  { intent: 'identify_next_missing_field', label: 'Identify the Next Missing Field' },
  { intent: 'explain_current_state', label: 'Explain the Current Step' },
];

function panel() {
  return render(
    <AssistantPanel
      reply={{ text: '', answeredFrom: 'workflow' }}
      prompts={PROMPTS}
      experimentId={EXP}
      recordRev={5}
      agentContext={CTX}
      agentPrompts={AGENT_PROMPTS}
    />,
  );
}

function open(container: HTMLElement) {
  const trigger = within(container).getByRole('button', { name: /What Can I Ask/i });
  if (trigger.getAttribute('aria-expanded') !== 'true') fireEvent.click(trigger);
}

beforeEach(() => clearAllSessions());
afterEach(() => cleanup());

const ASK = 'What still needs me?';
const ANSWER = 'One field still needs you: Reduced Spectrum.';
const ACTION = 'Identify the Next Missing Field';

describe('an agent action appends in order, after what was already said (B-03)', () => {
  it('the suggested question and its answer stay ABOVE the action and its answer', () => {
    const { container } = panel();
    open(container);
    fireEvent.click(within(container).getByRole('button', { name: ASK }));
    open(container);
    fireEvent.click(within(container).getByRole('button', { name: new RegExp(ACTION) }));

    const log = (container.querySelector('.assistant-log') as HTMLElement).textContent ?? '';
    const at = (needle: string) => log.indexOf(needle);
    expect(at(ASK), 'the first question is in the log').toBeGreaterThanOrEqual(0);
    expect(at(ANSWER)).toBeGreaterThan(at(ASK));
    // the action is a turn the reader took, so it is named …
    expect(at(ACTION)).toBeGreaterThan(at(ANSWER));
    // … and its answer follows it, last.
    const result = 'The next pending field is "Reduced Spectrum"';
    expect(at(result)).toBeGreaterThan(at(ACTION));
  });

  it('writes the reader’s line (the action’s label) and the answer, in that order, into the session', () => {
    const { container } = panel();
    open(container);
    fireEvent.click(within(container).getByRole('button', { name: new RegExp(ACTION) }));
    const messages = loadSession(EXP).messages;
    expect(messages.map((m) => m.role)).toEqual(['user', 'assistant']);
    expect(messages[0].text).toBe(ACTION);
    expect(messages[1].text).toContain('Reduced Spectrum');
  });

  it('settles the previous live turn exactly once — nothing is duplicated in the log', () => {
    const { container } = panel();
    open(container);
    fireEvent.click(within(container).getByRole('button', { name: ASK }));
    open(container);
    fireEvent.click(within(container).getByRole('button', { name: new RegExp(ACTION) }));
    const log = (container.querySelector('.assistant-log') as HTMLElement).textContent ?? '';
    expect(log.split(ANSWER).length - 1, 'the earlier answer appears once').toBe(1);
    expect(loadSession(EXP).messages.map((m) => m.role)).toEqual([
      'user',
      'assistant',
      'user',
      'assistant',
    ]);
  });

  it('two actions in a row are two ordered exchanges', () => {
    const { container } = panel();
    open(container);
    fireEvent.click(within(container).getByRole('button', { name: new RegExp(ACTION) }));
    open(container);
    fireEvent.click(within(container).getByRole('button', { name: /Explain the Current Step/ }));
    const texts = loadSession(EXP).messages.map((m) => m.text ?? '');
    expect(texts[0]).toBe(ACTION);
    expect(texts[2]).toBe('Explain the Current Step');
    expect(texts[3]).toContain('Complete Metadata');
  });
});
