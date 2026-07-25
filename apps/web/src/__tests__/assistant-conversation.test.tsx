import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import { appendMessage, clearAllSessions } from '../lib/assistantSession';
import { classifyAnswer } from '../lib/assistantConversation';
import type { AssistantMessage, SuggestedPrompt } from '../lib/types';

/*
 * P29.2 — conversation-style assistant UI (TEST-FIRST, authored RED).
 *
 * The panel keeps the deterministic SAFETY BOUNDARY (explains + points to
 * sources, never a verdict) while presenting the P29.1 ephemeral session as a
 * conversation: a scrollable message list (older → newest, newest at the
 * BOTTOM), the guided prompt pills, and the subordinate caption. No external
 * LLM and no record mutation is added here.
 *
 * P36R S2 re-laid the panel out — header (with Clear) → body (empty state OR the
 * bounded conversation region + a collapsed prompt-controls disclosure) →
 * proposed-action region → sticky composer → caption. The structural facts this
 * file pins (chronological order, live reply last, pill behaviour, role/kind/
 * staleness distinction, the verdict guard, respectful auto-scroll) are all
 * unchanged; the layout contract itself lives in assistant-layout.test.tsx.
 */

const EXP = 'exp-conv';

const REPLY: AssistantMessage = { text: 'Two fields still need you.', answeredFrom: 'workflow' };
const PROMPTS: SuggestedPrompt[] = [
  {
    text: 'What still needs me?',
    answeredFrom: 'workflow',
    answer: { text: 'Two fields still need you: Beamline, Edge.', answeredFrom: 'workflow' },
  },
  // no answer → the pill must stay disabled / non-activatable
  { text: 'A prompt with no answer', answeredFrom: 'schema', answer: undefined },
];

function panel(extra: Record<string, unknown> = {}) {
  return render(
    <AssistantPanel
      reply={REPLY}
      prompts={PROMPTS}
      experimentId={EXP}
      availability="available"
      {...extra}
    />,
  );
}

// Simulate a scroll viewport in jsdom (which does no layout): fake the metrics
// and dispatch a scroll event so the panel recomputes near-bottom.
function setScroll(el: Element, top: number, height: number, client: number) {
  Object.defineProperty(el, 'scrollHeight', { configurable: true, value: height });
  Object.defineProperty(el, 'clientHeight', { configurable: true, value: client });
  Object.defineProperty(el, 'scrollTop', { configurable: true, writable: true, value: top });
  fireEvent.scroll(el);
}

afterEach(() => {
  clearAllSessions();
  sessionStorage.clear();
  vi.restoreAllMocks();
  // @ts-expect-error — clear any matchMedia stub between tests
  delete window.matchMedia;
  // @ts-expect-error — jsdom has no scrollTo; drop any test-installed stub
  delete HTMLElement.prototype.scrollTo;
});

describe('P29.2 conversation layout — chronological, not inverted', () => {
  it('renders session messages oldest → newest, with the newest near the bottom', () => {
    appendMessage(EXP, { role: 'user', text: 'Q-ONE', recordRev: 5 });
    appendMessage(EXP, { role: 'assistant', text: 'A-ONE', recordRev: 5, answeredFrom: 'workflow' });
    appendMessage(EXP, { role: 'user', text: 'Q-TWO', recordRev: 5 });
    appendMessage(EXP, { role: 'assistant', text: 'A-TWO', recordRev: 5, answeredFrom: 'schema' });

    const { container } = panel();
    const bubbles = Array.from(container.querySelectorAll('.assistant-msg'));
    expect(bubbles.map((b) => b.textContent)).toEqual([
      expect.stringContaining('Q-ONE'),
      expect.stringContaining('A-ONE'),
      expect.stringContaining('Q-TWO'),
      expect.stringContaining('A-TWO'),
    ]);
    // NOT inverted — first bubble is the oldest
    expect(bubbles[0].textContent).toContain('Q-ONE');

    // the live reply is the newest element, rendered AFTER the last history msg
    const last = bubbles[bubbles.length - 1];
    const reply = container.querySelector('.assistant-reply')!;
    expect(last.compareDocumentPosition(reply) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('EMPTY state places the prompt pills above the (chrome-less) log; once a conversation exists they collapse BELOW the region', () => {
    // P36R S2 re-laid out the panel. At REST the empty state leads with its
    // guidance + Suggested Questions + Agent Actions, and the log — which holds
    // only the empty live region — trails below them, exactly as the P33 S2 · D4
    // ordering did. Once a conversation EXISTS the log becomes the bounded
    // conversation region that takes the available height, and the prompt
    // controls collapse into a disclosure BELOW it (never removed; the composer
    // stays visible at all times). The live reply block remains the newest
    // element at the bottom of the region (asserted in the test above).
    const { container, getByText } = panel();
    const log = container.querySelector('.assistant-log')!;
    const prompts = container.querySelector('.assistant-prompts')!;
    expect(prompts.compareDocumentPosition(log) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector('.assistant-conversation')).toBeNull();

    // start a turn → the region appears and the controls move into the disclosure
    fireEvent.click(getByText('What still needs me?'));
    const region = container.querySelector('.assistant-conversation')!;
    expect(region).toBe(log); // the SAME element — the live region is never re-mounted
    const collapsed = container.querySelector('details.assistant-more')!;
    expect(collapsed).not.toBeNull();
    expect(collapsed.querySelector('.assistant-prompts')).not.toBeNull();
    expect(region.compareDocumentPosition(collapsed) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe('P29.2 prompt pills — interactive, keyboard-activatable, honest disabled', () => {
  it('an answered pill is an enabled native button; a no-answer pill is disabled and non-activatable', () => {
    const { getByText, container } = panel();
    const active = getByText('What still needs me?').closest('button')!;
    const dead = getByText('A prompt with no answer').closest('button')!;

    expect(active.tagName).toBe('BUTTON');
    expect(active).not.toBeDisabled();
    expect(active.getAttribute('tabindex')).not.toBe('-1'); // keyboard reachable

    expect(dead.tagName).toBe('BUTTON');
    expect(dead).toBeDisabled();

    const before = container.querySelectorAll('.assistant-msg').length;
    fireEvent.click(dead);
    // a disabled pill never advances the conversation
    expect(container.querySelectorAll('.assistant-msg').length).toBe(before);
  });
});

describe('P29.2 message distinction — role + kind + staleness (never color-only)', () => {
  it('user and assistant messages are distinguishable by role class AND text label', () => {
    appendMessage(EXP, { role: 'user', text: 'user asks' });
    appendMessage(EXP, { role: 'assistant', text: 'assistant answers', answeredFrom: 'workflow' });
    const { container } = panel();

    const user = container.querySelector('.assistant-msg-user')!;
    const asst = container.querySelector('.assistant-msg-assistant')!;
    expect(user).not.toBeNull();
    expect(asst).not.toBeNull();
    expect(user.getAttribute('data-role')).toBe('user');
    expect(asst.getAttribute('data-role')).toBe('assistant');
    // text labels carry the distinction (not color alone)
    expect(user.textContent).toMatch(/you/i);
    expect(asst.textContent).toMatch(/assistant/i);
  });

  it('a message grounded in an older revision renders a distinct earlier-version indicator (icon + text)', () => {
    appendMessage(EXP, { role: 'assistant', text: 'stale answer', recordRev: 2, answeredFrom: 'workflow' });
    appendMessage(EXP, { role: 'assistant', text: 'fresh answer', recordRev: 5, answeredFrom: 'workflow' });
    const { container } = panel({ recordRev: 5 });

    const bubbles = Array.from(container.querySelectorAll('.assistant-msg'));
    const stale = bubbles.find((b) => b.textContent?.includes('stale answer'))!;
    const fresh = bubbles.find((b) => b.textContent?.includes('fresh answer'))!;

    expect(stale.classList.contains('is-stale')).toBe(true);
    expect(stale.textContent).toMatch(/earlier version/i);
    expect(stale.querySelector('svg')).not.toBeNull(); // icon + text, not color-only
    expect(fresh.classList.contains('is-stale')).toBe(false);
    expect(fresh.textContent).not.toMatch(/earlier version/i);
  });

  it('deterministic-result, advisory, inferred-candidate, degraded and confirmation-request styles are each present and distinct', () => {
    appendMessage(EXP, { role: 'assistant', text: 'det', answeredFrom: 'schema', resultType: 'deterministic-result' });
    appendMessage(EXP, { role: 'assistant', text: 'adv', answeredFrom: 'advisory', resultType: 'advisory' });
    appendMessage(EXP, { role: 'assistant', text: 'inf', answeredFrom: 'files', resultType: 'inferred-candidate' });
    appendMessage(EXP, { role: 'assistant', text: 'deg', answeredFrom: 'graph', resultType: 'degraded' });
    appendMessage(EXP, { role: 'assistant', text: 'con', answeredFrom: 'workflow', resultType: 'confirmation-request' });
    const { container } = panel();

    const kinds = ['deterministic-result', 'advisory', 'inferred-candidate', 'degraded', 'confirmation-request'];
    const labels = new Set<string>();
    for (const k of kinds) {
      const el = container.querySelector(`.kind-${k}`)!;
      expect(el).not.toBeNull();
      expect(el.querySelector('svg')).not.toBeNull(); // each kind carries its own glyph
      const label = el.querySelector('.assistant-msg-kind')?.textContent ?? '';
      expect(label.trim()).not.toBe('');
      labels.add(label.trim());
    }
    // each kind's label is distinct (distinguishable by text, not color)
    expect(labels.size).toBe(kinds.length);
  });

  it('the verdict-language guard strips PASS/FAIL from any rendered assistant message', () => {
    appendMessage(EXP, { role: 'assistant', text: 'This record is PASS against the schema.', answeredFrom: 'schema' });
    const { container } = panel();
    const bubble = container.querySelector('.assistant-msg-assistant')!;
    expect(bubble.textContent).not.toMatch(/\bPASS\b/);
    expect(bubble.textContent).toMatch(/truth question/i);
  });
});

describe('P29.2 respectful auto-scroll + Jump to Latest', () => {
  it('shows Jump to Latest when new content arrives while scrolled up, and hides it near the bottom', () => {
    const { container, queryByRole, getByText } = panel();
    const log = container.querySelector('.assistant-log')!;

    // no jump affordance while near the bottom
    expect(queryByRole('button', { name: /jump to latest/i })).toBeNull();

    // scroll UP (reading older content), then new content arrives
    setScroll(log, 0, 1000, 100);
    fireEvent.click(getByText('What still needs me?'));
    expect(queryByRole('button', { name: /jump to latest/i })).not.toBeNull();

    // return to the bottom → the affordance disappears
    setScroll(log, 900, 1000, 100);
    expect(queryByRole('button', { name: /jump to latest/i })).toBeNull();
  });

  it('moves focus intentionally after a prompt is submitted', () => {
    const { getByText, container } = panel();
    fireEvent.click(getByText('What still needs me?'));
    const reply = container.querySelector('.assistant-reply')!;
    expect(reply).toHaveFocus();
  });

  it('does not use smooth scrolling under prefers-reduced-motion', () => {
    window.matchMedia = vi.fn().mockImplementation((q: string) => ({
      matches: /prefers-reduced-motion/.test(q),
      media: q,
      addEventListener: () => {},
      removeEventListener: () => {},
    })) as unknown as typeof window.matchMedia;
    // jsdom does not implement Element.scrollTo — install a mock we can inspect.
    const scrollSpy = vi.fn();
    HTMLElement.prototype.scrollTo = scrollSpy as unknown as typeof HTMLElement.prototype.scrollTo;

    const { getByText } = panel();
    fireEvent.click(getByText('What still needs me?')); // near bottom → auto-scroll fires
    expect(scrollSpy).toHaveBeenCalled();
    for (const call of scrollSpy.mock.calls) {
      const opts = call[0] as ScrollToOptions;
      expect(opts.behavior).not.toBe('smooth');
    }
  });
});

describe('P29.2 classifyAnswer — deterministic mapping of source → message kind', () => {
  it('maps schema/audit to a deterministic-result kind', () => {
    expect(classifyAnswer('schema').resultType).toBe('deterministic-result');
    expect(classifyAnswer('audit').resultType).toBe('deterministic-result');
  });
  it('maps unavailable memory to a degraded kind, available memory to advisory', () => {
    expect(classifyAnswer('graph', 'unavailable').resultType).toBe('degraded');
    expect(classifyAnswer('graph', 'available').resultType).toBe('advisory');
  });
  it('maps advisory / workflow / files to an advisory kind', () => {
    expect(classifyAnswer('advisory').resultType).toBe('advisory');
    expect(classifyAnswer('workflow').resultType).toBe('advisory');
    expect(classifyAnswer('files').resultType).toBe('advisory');
  });
});
