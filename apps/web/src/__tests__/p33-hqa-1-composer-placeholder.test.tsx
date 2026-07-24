import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import type { AssistantMessage, SuggestedPrompt } from '../lib/types';

/*
 * P33 Human-QA #1 — the honest visual-only composer must show a visible
 * placeholder ("Ask a question", sentence case) whenever the input is empty, and
 * it must lose the placeholder while text exists / regain it when cleared. The
 * placeholder is NOT the accessible name (a real aria-label is preserved), and
 * none of the existing honest behavior changes: empty submit does nothing, the
 * box makes no network request, appends no message, and persists nothing.
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
  fetchSpy = vi.fn(() => Promise.reject(new Error('no network in a visual-only composer')));
  vi.stubGlobal('fetch', fetchSpy);
});
afterEach(() => vi.unstubAllGlobals());

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

  it('empty submission does nothing: no network, no message, no notice', () => {
    const { getByRole, container } = renderPanel('hqa1-d');
    const box = getByRole('textbox') as HTMLInputElement;
    const before = container.querySelectorAll('.assistant-msg').length;
    const form = box.closest('form')!;
    fireEvent.submit(form); // empty value
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(container.querySelectorAll('.assistant-msg').length).toBe(before);
    expect(container.querySelector('.assistant-composer-notice')).toBeNull();
  });

  it('non-empty submission stays honest: notice shown, still no network / no message', () => {
    const { getByRole, container } = renderPanel('hqa1-e');
    const box = getByRole('textbox') as HTMLInputElement;
    const before = container.querySelectorAll('.assistant-msg').length;
    fireEvent.change(box, { target: { value: 'what is the sha256?' } });
    fireEvent.submit(box.closest('form')!);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(container.querySelectorAll('.assistant-msg').length).toBe(before);
    expect(container.querySelector('.assistant-composer-notice')).toBeTruthy();
  });
});
