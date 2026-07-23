import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import type { AssistantMessage, SuggestedPrompt } from '../lib/types';

/*
 * P33 S2 · Honest visual-only composer (D3/C3). The assistant panel now shows a
 * free-text box at the top of its prompt controls, BUT free-form Q&A is not wired
 * in this build. The box must be completely honest: a persistent limitation is
 * visible BEFORE interaction; submitting arbitrary text produces NO network
 * request, NO assistant answer, NO conversation-log entry, NO persistence — only
 * an accessible inline notice pointing to the supported suggested questions, which
 * keep working exactly as before. This pins the no-functionality-change boundary.
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
afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPanel(key: string) {
  return render(<AssistantPanel reply={reply} prompts={prompts} experimentId={key} />);
}

describe('AssistantPanel — honest visual-only composer (P33 S2)', () => {
  it('renders a composer textbox with a persistent limitation BEFORE any interaction', () => {
    const { getByRole, getByText } = renderPanel('composer-key-1');
    // a real, focusable text input exists
    const box = getByRole('textbox');
    expect(box).toBeTruthy();
    // the limitation is stated up front, not only after a failed submit
    expect(getByText(/Guided Questions Only/i)).toBeTruthy();
    expect(getByText(/choose a suggested question/i)).toBeTruthy();
  });

  it('submitting free text makes NO network request and appends NO conversation message', () => {
    const { getByRole, container } = renderPanel('composer-key-2');
    const before = container.querySelectorAll('.assistant-msg').length;
    const box = getByRole('textbox') as HTMLInputElement | HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'what is the sha256 of the raw folder?' } });
    // submit via Enter and/or a send control — whichever the composer supports
    fireEvent.keyDown(box, { key: 'Enter', code: 'Enter' });
    const form = box.closest('form');
    if (form) fireEvent.submit(form);

    expect(fetchSpy).not.toHaveBeenCalled();
    // no assistant answer was fabricated into the log
    expect(container.querySelectorAll('.assistant-msg').length).toBe(before);
    // the only response is the inert honest notice (not a generated answer)
    expect(container.querySelector('.assistant-composer-notice')).toBeTruthy();
  });

  it('surfaces an accessible inline limitation on unsupported submission', () => {
    const { getByRole } = renderPanel('composer-key-3');
    const box = getByRole('textbox');
    fireEvent.change(box, { target: { value: 'free form question' } });
    const form = box.closest('form');
    if (form) fireEvent.submit(form);
    else fireEvent.keyDown(box, { key: 'Enter', code: 'Enter' });
    // a status/alert message tells the user free-form is unsupported and redirects
    const notice = getByRole('status');
    expect(within(notice).getByText(/not supported in this build/i)).toBeTruthy();
  });

  it('suggested questions still work (guided path unchanged)', () => {
    const { getByText, container } = renderPanel('composer-key-4');
    const pill = getByText('What still needs me?');
    fireEvent.click(pill.closest('button') as HTMLButtonElement);
    // clicking a pill activates it (aria-pressed) — the guided answer path is intact
    expect(container.querySelector('.assistant-prompt.active')).toBeTruthy();
  });
});
