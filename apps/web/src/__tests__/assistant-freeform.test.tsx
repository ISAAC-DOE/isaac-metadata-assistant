/*
 * P34.2 — free-form composer wired to the READ-ONLY grounded resolver.
 *
 * This slice removes the redundant on-mount auto-reply, wires the composer to
 * POST /assistant/query (a non-mutating query), and adds bounded conversation +
 * Clear Conversation. These tests pin the new contract end-to-end in the panel:
 *   - the rail RESTS with an EMPTY live region (P36.1 — no placeholder text, no
 *     auto "still need you" card) on mount;
 *   - a free-form submit shows a loading indicator then the resolved answer;
 *   - a provider/network error renders the honest unavailable message while the
 *     surrounding controls (pills, composer) stay usable;
 *   - Clear Conversation empties the log and returns the live region to empty;
 *   - Suggested Questions still work via the precomposed path (no endpoint call);
 *   - Agent Actions are unchanged (a pill still runs a real intent);
 *   - the composer path is READ-ONLY — never submitAnswer / editField / confirm.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import { ApiError, api } from '../lib/api';
import * as agentModule from '../lib/assistantAgent';
import { ASSISTANT_UNAVAILABLE } from '../lib/assistant';
import { clearAllSessions } from '../lib/assistantSession';
import type { AgentContext } from '../lib/assistantAgent';
import type { AssistantMessage, AssistantQueryResponse, SuggestedPrompt } from '../lib/types';

const EXP = '01EXPERIMENTA0000000000000';

const REPLY: AssistantMessage = { text: 'Two fields still need you.', answeredFrom: 'workflow' };
const PROMPTS: SuggestedPrompt[] = [
  {
    text: 'What still needs me?',
    answeredFrom: 'workflow',
    answer: { text: 'Two fields still need you: Beamline, Edge.', answeredFrom: 'workflow' },
  },
];

function ctx(overrides: Partial<AgentContext> = {}): AgentContext {
  return {
    experimentId: EXP,
    recordRev: 5,
    version: 'gen.5',
    workflow: {
      current_step: 'complete_metadata',
      ordered_steps: [
        { id: 'complete_metadata', label: 'Complete Metadata', state: 'current', current: true, reopened: false, blocked: false, reason: null },
      ],
    },
    evidence: [
      { field: 'sample.material', classification: 'supported', value_state: 'confirmed', explanation: 'Backed by observed evidence.', sources: [{ source_type: 'spreadsheet' }] },
    ],
    pending: [
      { id: 'series', label: 'Reduced Series' },
      { id: 'descriptor', label: 'Descriptor' },
    ],
    ...overrides,
  };
}

const AGENT_PROMPTS = [{ intent: 'identify_next_missing_field', label: 'Identify the Next Missing Field' }];

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

beforeEach(() => {
  clearAllSessions();
  sessionStorage.clear();
});
afterEach(() => {
  clearAllSessions();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe('P36.1 empty live region (no placeholder, no auto-reply)', () => {
  it('rests with an empty, chrome-suppressed live region and shows NO auto pending-summary card on mount', () => {
    const { container, queryByText } = panel();
    // P36.1: no resting placeholder text at all.
    expect(queryByText(/Ask a question or choose a suggested prompt\./)).toBeNull();
    // the old auto-reply ("still need you") is NOT announced on mount
    expect(queryByText(/still need you/i)).toBeNull();
    // the single live region stays MOUNTED, aria-live, but empty — no visible
    // card chrome (the `--empty` modifier).
    const reply = container.querySelector('.assistant-reply');
    expect(reply).not.toBeNull();
    expect(reply?.getAttribute('aria-live')).toBe('polite');
    expect(reply?.textContent).toBe('');
    expect(reply?.classList.contains('assistant-reply--empty')).toBe(true);
    // and there is no history + no answered-from line at rest
    expect(container.querySelectorAll('.assistant-msg').length).toBe(0);
    expect(container.querySelector('.answered-from')).toBeNull();
  });
});

describe('P34.2 free-form submit', () => {
  it('submit → loading → resolved answer with its source label', async () => {
    const spy = vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole, getByText, container } = panel();
    const box = getByRole('textbox');
    fireEvent.change(box, { target: { value: 'what is this record?' } });
    fireEvent.submit(box.closest('form')!);

    // loading is announced in the single live region
    expect(container.querySelector('.assistant-reply')!.getAttribute('aria-busy')).toBe('true');

    expect(spy).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(getByText(/Cu K-edge XANES draft/i)).toBeInTheDocument());
    expect(getByText('answered from: Workflow & Artifacts')).toBeInTheDocument();
  });

  it('a provider/network error renders the honest unavailable message; controls stay usable', async () => {
    vi.spyOn(api, 'askAssistant').mockRejectedValue(new ApiError('down', { unreachable: true }));
    const { getByRole, getByText, container } = panel();
    const box = getByRole('textbox');
    fireEvent.change(box, { target: { value: 'anything' } });
    fireEvent.submit(box.closest('form')!);

    await waitFor(() => expect(getByText(ASSISTANT_UNAVAILABLE)).toBeInTheDocument());
    // the surrounding controls are unaffected — the guided pills still work
    fireEvent.click(getByText('What still needs me?'));
    expect(container.querySelector('.assistant-prompt.active')).toBeTruthy();
  });
});

describe('P34.2 Clear Conversation', () => {
  it('appears once there is history and returns the live region to empty (P36.1)', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { getByRole, getByText, queryByRole, container } = panel();

    // no clear control at rest
    expect(queryByRole('button', { name: /clear conversation/i })).toBeNull();

    // ask two questions so the first archives into the log
    const box = getByRole('textbox');
    fireEvent.change(box, { target: { value: 'q one' } });
    fireEvent.submit(box.closest('form')!);
    await waitFor(() => expect(getByText(/Cu K-edge XANES draft/i)).toBeInTheDocument());
    fireEvent.change(box, { target: { value: 'q two' } });
    fireEvent.submit(box.closest('form')!);
    await waitFor(() => expect(container.querySelectorAll('.assistant-msg').length).toBeGreaterThan(0));

    // the clear control is now present; clicking it empties the log + resets state
    const clear = getByRole('button', { name: /clear conversation/i });
    fireEvent.click(clear);
    expect(container.querySelectorAll('.assistant-msg').length).toBe(0);
    // P36.1: the SAME live region, mounted, back to empty — no placeholder text.
    const reply = container.querySelector('.assistant-reply');
    expect(reply).not.toBeNull();
    expect(reply?.textContent).toBe('');
    expect(reply?.classList.contains('assistant-reply--empty')).toBe(true);
    expect(queryByRole('button', { name: /clear conversation/i })).toBeNull();
  });
});

describe('P34.2 preserved surfaces', () => {
  it('Suggested Questions still work via the precomposed path (no endpoint call)', () => {
    const spy = vi.spyOn(api, 'askAssistant');
    const { getByText, container } = panel();
    fireEvent.click(getByText('What still needs me?'));
    expect(container.querySelector('.assistant-prompt.active')).toBeTruthy();
    expect(getByText(/Beamline, Edge/)).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it('Agent Actions are unchanged — a pill still runs a real intent', () => {
    const spy = vi.spyOn(api, 'askAssistant');
    const { getByText, container } = panel({ agentContext: ctx(), agentPrompts: AGENT_PROMPTS });
    const before = container.querySelectorAll('.assistant-msg').length;
    fireEvent.click(getByText('Identify the Next Missing Field'));
    const msgs = Array.from(container.querySelectorAll('.assistant-msg'));
    expect(msgs.length).toBe(before + 1);
    expect(msgs[msgs.length - 1].textContent).toContain('Reduced Series');
    // agent actions never route through the read-only query endpoint
    expect(spy).not.toHaveBeenCalled();
  });
});

describe('P34.2 authority boundary — composer is READ-ONLY', () => {
  it('a free-form submit never calls submitAnswer / editField / confirmProposal', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const submit = vi.spyOn(api, 'submitAnswer');
    const edit = vi.spyOn(api, 'editField');
    const confirm = vi.spyOn(agentModule, 'confirmProposal');
    const { getByRole, getByText } = panel({ agentContext: ctx(), onRefresh: vi.fn() });
    const box = getByRole('textbox');
    fireEvent.change(box, { target: { value: 'read-only question' } });
    fireEvent.submit(box.closest('form')!);
    await waitFor(() => expect(getByText(/Cu K-edge XANES draft/i)).toBeInTheDocument());
    expect(submit).not.toHaveBeenCalled();
    expect(edit).not.toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
  });
});
