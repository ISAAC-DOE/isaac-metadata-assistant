import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import { api } from '../lib/api';
import { clearAllSessions } from '../lib/assistantSession';
import type { AssistantMessage, AssistantQueryResponse, SuggestedPrompt } from '../lib/types';

/*
 * P34.2 · The composer is now WIRED to the READ-ONLY grounded resolver
 * (POST /assistant/query). This REWRITES the P33 S2 "inert visual-only composer"
 * contract — a deliberate flip: submitting a non-empty question now calls
 * api.askAssistant, shows a loading indicator, then renders the returned answer
 * with its `Source:` label. There is NO "not supported in this build"
 * notice anymore. An empty/whitespace submit is still a true no-op. The composer
 * path is READ-ONLY: it must never call submitAnswer / editField / confirmProposal.
 */

const reply: AssistantMessage = { text: 'Here is some guidance.', answeredFrom: 'workflow' };
const prompts: SuggestedPrompt[] = [
  {
    text: 'What still needs me?',
    answeredFrom: 'workflow',
    answer: { text: 'Two fields still need you.', answeredFrom: 'workflow' },
  },
];

function answerResponse(over: Partial<AssistantQueryResponse> = {}): AssistantQueryResponse {
  return {
    answer: 'The current step is Complete Metadata; two fields still need you.',
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

beforeEach(() => {
  clearAllSessions();
  sessionStorage.clear();
});
afterEach(() => {
  clearAllSessions();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

function renderPanel(key: string) {
  return render(<AssistantPanel reply={reply} prompts={prompts} experimentId={key} recordRev={5} />);
}

describe('AssistantPanel — wired composer (P34.2)', () => {
  it('renders a labelled composer textbox and a send control (accessible names preserved)', () => {
    const { getByRole, getByLabelText } = renderPanel('composer-key-1');
    const box = getByRole('textbox');
    expect(box).toBeTruthy();
    expect(getByLabelText(/ask the assistant/i)).toBe(box);
    const send = getByRole('button', { name: /send/i });
    expect(send.className).toMatch(/btn-secondary/);
  });

  it('does NOT render the retired "not supported in this build" notice', () => {
    const { container, queryByText } = renderPanel('composer-key-2');
    expect(container.querySelector('.assistant-composer-notice')).toBeNull();
    expect(queryByText(/not supported in this build/i)).toBeNull();
  });

  it('submitting a non-empty question calls askAssistant, shows loading, then renders the answer + source label', async () => {
    const spy = vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole, getByText, container } = renderPanel('composer-key-3');
    const box = getByRole('textbox');
    fireEvent.change(box, { target: { value: 'what still needs me?' } });
    fireEvent.submit(box.closest('form')!);

    // read-only query issued with the trimmed question
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0]).toBe('composer-key-3');
    expect(spy.mock.calls[0][1]).toEqual({ question: 'what still needs me?' });

    // an accessible in-flight indicator is announced in the single live region
    const replyEl = container.querySelector('.assistant-reply')!;
    expect(replyEl.getAttribute('aria-busy')).toBe('true');
    expect(replyEl.textContent).toMatch(/working/i);

    // then the returned answer + its honest source label render
    await waitFor(() =>
      expect(getByText(/two fields still need you/i)).toBeInTheDocument(),
    );
    expect(getByText('Source: Workflow & Artifacts')).toBeInTheDocument();
    expect(container.querySelector('.assistant-reply')!.getAttribute('aria-busy')).toBeNull();
  });

  it('an empty / whitespace submit is a no-op (no fetch)', () => {
    const spy = vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole } = renderPanel('composer-key-4');
    const box = getByRole('textbox') as HTMLInputElement;
    // empty
    fireEvent.submit(box.closest('form')!);
    // whitespace only
    fireEvent.change(box, { target: { value: '   ' } });
    fireEvent.submit(box.closest('form')!);
    expect(spy).not.toHaveBeenCalled();
  });

  it('the composer path is READ-ONLY — it never calls submitAnswer / editField', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const submit = vi.spyOn(api, 'submitAnswer');
    const edit = vi.spyOn(api, 'editField');
    const { getByRole, getByText } = renderPanel('composer-key-5');
    const box = getByRole('textbox');
    fireEvent.change(box, { target: { value: 'is the sha present?' } });
    fireEvent.submit(box.closest('form')!);
    await waitFor(() => expect(getByText(/two fields still need you/i)).toBeInTheDocument());
    expect(submit).not.toHaveBeenCalled();
    expect(edit).not.toHaveBeenCalled();
  });

  it('suggested questions still work (precomposed guided path unchanged)', () => {
    const spy = vi.spyOn(api, 'askAssistant');
    const { getByText, container } = renderPanel('composer-key-6');
    const pill = getByText('What still needs me?');
    fireEvent.click(pill.closest('button') as HTMLButtonElement);
    // clicking a pill activates it (aria-pressed) — the guided answer path is intact
    expect(container.querySelector('.assistant-prompt.active')).toBeTruthy();
    // a pill does NOT route through the endpoint in this slice (that is P34.3)
    expect(spy).not.toHaveBeenCalled();
  });
});
