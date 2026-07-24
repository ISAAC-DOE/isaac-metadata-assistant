import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import { api } from '../lib/api';
import { clearAllSessions } from '../lib/assistantSession';
import type { AssistantMessage, AssistantQueryResponse, SuggestedPrompt } from '../lib/types';

/*
 * P33 Human-QA #1 (carried into P34.2) — the composer must show a visible
 * placeholder ("Ask a question", sentence case) whenever the input is empty, and
 * it must lose the placeholder while text exists / regain it when cleared. The
 * placeholder is NOT the accessible name (a real aria-label is preserved). The
 * placeholder behavior is unchanged by P34.2; what changed is the submit path —
 * an empty submit is still a no-op, but a non-empty submit now calls the READ-ONLY
 * grounded resolver (there is no longer a "not supported" notice).
 */

const reply: AssistantMessage = { text: 'Here is some guidance.', answeredFrom: 'workflow' };
const prompts: SuggestedPrompt[] = [
  {
    text: 'What still needs me?',
    answeredFrom: 'workflow',
    answer: { text: 'Two fields still need you.', answeredFrom: 'workflow' },
  },
];

let fetchSpy: ReturnType<typeof vi.fn>;
beforeEach(() => {
  clearAllSessions();
  sessionStorage.clear();
  fetchSpy = vi.fn(() => Promise.reject(new Error('no network stubbed for placeholder tests')));
  vi.stubGlobal('fetch', fetchSpy);
});
afterEach(() => {
  clearAllSessions();
  sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function answerResponse(): AssistantQueryResponse {
  return {
    answer: 'Two fields still need you.',
    result: 'answered',
    grounding: ['workflow'],
    sources: [{ label: 'Workflow & Artifacts', navigate_to: null }],
    record_rev: 5,
    version: 'gen.5',
    stale: false,
    followups: [],
  };
}

function renderPanel(key: string) {
  return render(<AssistantPanel reply={reply} prompts={prompts} experimentId={key} />);
}

describe('P33 HQA#1 — composer placeholder', () => {
  it('shows the sentence-case placeholder "Ask a question" when empty', () => {
    const { getByRole } = renderPanel('hqa1-a');
    const box = getByRole('textbox') as HTMLInputElement;
    expect(box.placeholder).toBe('Ask a question');
    expect(box.value).toBe('');
  });

  it('preserves a real accessible name INDEPENDENT of the placeholder', () => {
    const { getByRole } = renderPanel('hqa1-b');
    const box = getByRole('textbox') as HTMLInputElement;
    // the accessible name must NOT come from the placeholder alone
    const ariaLabel = box.getAttribute('aria-label');
    expect(ariaLabel).toBeTruthy();
    expect(ariaLabel).not.toBe('Ask a question');
  });

  it('placeholder is present regardless of value; value drives visibility natively', () => {
    const { getByRole } = renderPanel('hqa1-c');
    const box = getByRole('textbox') as HTMLInputElement;
    // typing sets a value (the browser then hides the placeholder natively) …
    fireEvent.change(box, { target: { value: 'hello' } });
    expect(box.value).toBe('hello');
    expect(box.placeholder).toBe('Ask a question');
    // … clearing restores the empty value (placeholder shows again natively)
    fireEvent.change(box, { target: { value: '' } });
    expect(box.value).toBe('');
    expect(box.placeholder).toBe('Ask a question');
  });

  it('empty submission does nothing: no query, no message, no notice', () => {
    const spy = vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole, container } = renderPanel('hqa1-d');
    const box = getByRole('textbox') as HTMLInputElement;
    const before = container.querySelectorAll('.assistant-msg').length;
    fireEvent.submit(box.closest('form')!); // empty value
    expect(spy).not.toHaveBeenCalled();
    expect(container.querySelectorAll('.assistant-msg').length).toBe(before);
    // the retired inline notice never renders
    expect(container.querySelector('.assistant-composer-notice')).toBeNull();
  });

  it('non-empty submission now calls the READ-ONLY resolver and renders the answer (no notice)', async () => {
    const spy = vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole, getByText, container } = renderPanel('hqa1-e');
    const box = getByRole('textbox') as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'what is the sha256?' } });
    fireEvent.submit(box.closest('form')!);
    expect(spy).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(getByText(/two fields still need you/i)).toBeInTheDocument());
    // there is no "not supported" notice anymore
    expect(container.querySelector('.assistant-composer-notice')).toBeNull();
  });
});
