/*
 * P34.4 — cross-surface consistency: the record-agnostic Project-Memory scope.
 *
 * The Project Memory surface mounts the SAME AssistantPanel but passes
 * `queryScope="memory"` (and has no record). These tests pin the P34.4 contract
 * in the panel:
 *   - a memory-scope free-form submit calls `api.askMemory` (NOT askAssistant),
 *     renders the memory answer with its cited-lead provenance chips and the
 *     advisory "leads to verify" framing;
 *   - a record-style question renders the honest "open a record" refusal;
 *   - NO stale badge / Ask-again EVER appears in memory scope (the memory answer
 *     carries a null record_rev, so the stale guard is never satisfied);
 *   - the memory composer path is READ-ONLY — never submitAnswer / editField /
 *     confirmProposal;
 *   - a record-scope panel still calls `api.askAssistant` (unchanged);
 *   - a Suggested-Question click renders through the SAME turn pipeline as a
 *     free-form answer (same `.assistant-reply` region + `Source:` label,
 *     archives to the session identically) and calls NEITHER endpoint.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, waitFor, within } from '@testing-library/react';

// Mock the app router so a cited memory lead's navigation is observable without
// mounting a full <Router> (same approach as assistant-provenance.test.tsx).
const { navigateSpy } = vi.hoisted(() => ({ navigateSpy: vi.fn() }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateSpy }));

import { AssistantPanel } from '../components/AssistantPanel';
import { api } from '../lib/api';
import * as agentModule from '../lib/assistantAgent';
import { clearAllSessions, loadSession } from '../lib/assistantSession';
import type { AssistantMessage, AssistantQueryResponse, SuggestedPrompt } from '../lib/types';

// The Project Memory surface uses this fixed session key (see ProjectMemory.tsx).
const MEM = 'project-memory';
const EXP = '01EXPERIMENTA0000000000000';

const REPLY: AssistantMessage = { text: 'Memory leads appear here.', answeredFrom: 'graph' };
const PROMPTS: SuggestedPrompt[] = [
  {
    text: 'How fresh is project memory?',
    answeredFrom: 'graph',
    answer: { text: 'Memory was indexed recently; confirm every lead.', answeredFrom: 'graph' },
  },
];

// A memory-scope answer: NO record, so record_rev/version are null and stale is
// false. Grounding is ['graph']; the sources ARE the cited leads to verify.
function memoryAnswer(over: Partial<AssistantQueryResponse> = {}): AssistantQueryResponse {
  return {
    answer:
      'Memory suggests 2 leads to verify: Copper oxide, Cu K-edge. ' +
      'Project memory returns leads to verify — never a validation verdict.',
    result: 'answered',
    grounding: ['graph'],
    sources: [
      { label: 'Copper oxide', navigate_to: '/memory?concept=copper' },
      { label: 'Cu K-edge', navigate_to: null },
    ],
    record_rev: null,
    version: null,
    stale: false,
    followups: [],
    ...over,
  };
}

// The honest refusal the memory scope returns for a RECORD question.
function refusal(over: Partial<AssistantQueryResponse> = {}): AssistantQueryResponse {
  return {
    answer:
      'This is the Project Memory view — I answer project-memory questions here. ' +
      'Open a record to ask about its fields, evidence, workflow, or export readiness.',
    result: 'unsupported',
    grounding: [],
    sources: [],
    record_rev: null,
    version: null,
    stale: false,
    followups: [],
    ...over,
  };
}

// A memory-scope panel: `queryScope="memory"`, session key `project-memory`, and
// deliberately NO numeric recordRev (the surface has no record).
function memoryPanel(extra: Record<string, unknown> = {}) {
  return render(
    <AssistantPanel
      reply={REPLY}
      prompts={PROMPTS}
      experimentId={MEM}
      queryScope="memory"
      availability="available"
      {...extra}
    />,
  );
}

function submit(getByRole: (r: string) => HTMLElement, text: string) {
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

describe('P34.4 memory scope — free-form question', () => {
  it('calls api.askMemory (NOT askAssistant) and renders the memory answer + cited leads', async () => {
    const mem = vi.spyOn(api, 'askMemory').mockResolvedValue(memoryAnswer());
    const rec = vi.spyOn(api, 'askAssistant');
    const { getByRole, getByText, container } = memoryPanel();

    submit(getByRole, 'what does project memory know about copper');

    await waitFor(() => expect(mem).toHaveBeenCalledTimes(1));
    expect(mem).toHaveBeenCalledWith({ question: 'what does project memory know about copper' });
    // the record endpoint is NEVER touched from the memory surface
    expect(rec).not.toHaveBeenCalled();

    // the advisory "leads to verify" framing is rendered, no verdict language
    await waitFor(() => expect(getByText(/leads to verify/i)).toBeInTheDocument());
    expect(getByText(/Memory suggests/i)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL)\b/);
    expect(getByText('Source: Project Memory')).toBeInTheDocument();

    // the cited leads render as provenance chips; a /memory lead navigates in-app
    const region = container.querySelector('.assistant-provenance') as HTMLElement;
    expect(region.querySelectorAll('.assistant-provenance-item').length).toBe(2);
    fireEvent.click(within(region).getByRole('button', { name: 'Copper oxide' }));
    expect(navigateSpy).toHaveBeenCalledWith('/memory?concept=copper');
  });

  it('a record-style question renders the honest "open a record" refusal', async () => {
    const mem = vi.spyOn(api, 'askMemory').mockResolvedValue(refusal());
    const { getByRole, getByText, container } = memoryPanel();

    submit(getByRole, 'what still needs me?');

    await waitFor(() => expect(mem).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(getByText(/Open a record/i)).toBeInTheDocument());
    expect(getByText(/Project Memory view/i)).toBeInTheDocument();
    // an honest refusal carries no cited leads
    expect(container.querySelector('.assistant-provenance')).toBeNull();
  });
});

describe('P34.4 memory scope — no staleness affordance ever', () => {
  it('NO stale badge / Ask-again appears even when a numeric recordRev prop is present', async () => {
    vi.spyOn(api, 'askMemory').mockResolvedValue(memoryAnswer());
    // Deliberately pass a numeric recordRev to prove the memory answer's null rev
    // (not the panel prop) is what keeps the live answer out of the stale path.
    const { getByRole, container, queryByText } = memoryPanel({ recordRev: 9 });

    submit(getByRole, 'docs about xanes');
    await waitFor(() => expect(container.querySelector('.assistant-provenance')).toBeTruthy());

    expect(container.querySelector('.assistant-live-stale-row')).toBeNull();
    expect(queryByText('Based on an earlier version')).toBeNull();
    expect(queryByText(/Ask again/i)).toBeNull();
  });
});

describe('P34.4 memory scope — READ-ONLY composer', () => {
  it('a memory free-form submit never calls submitAnswer / editField / confirmProposal', async () => {
    vi.spyOn(api, 'askMemory').mockResolvedValue(memoryAnswer());
    const submitAnswer = vi.spyOn(api, 'submitAnswer');
    const edit = vi.spyOn(api, 'editField');
    const confirm = vi.spyOn(agentModule, 'confirmProposal');
    const { getByRole, container } = memoryPanel();

    submit(getByRole, 'where is the edge concept defined');
    await waitFor(() => expect(container.querySelector('.assistant-provenance')).toBeTruthy());

    expect(submitAnswer).not.toHaveBeenCalled();
    expect(edit).not.toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
  });
});

describe('P34.4 record scope still uses askAssistant (unchanged)', () => {
  it('a record-scope panel (default scope) routes a free-form submit to askAssistant', async () => {
    const rec = vi.spyOn(api, 'askAssistant').mockResolvedValue({
      answer: 'The record is a Cu K-edge XANES draft.',
      result: 'answered',
      grounding: ['workflow'],
      sources: [{ label: 'Workflow & Artifacts', navigate_to: null }],
      record_rev: 5,
      version: 'gen.5',
      stale: false,
      followups: [],
    });
    const mem = vi.spyOn(api, 'askMemory');
    const { getByRole, getByText } = render(
      <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId={EXP} recordRev={5} />,
    );

    submit(getByRole, 'what is this record?');

    await waitFor(() => expect(rec).toHaveBeenCalledTimes(1));
    expect(rec).toHaveBeenCalledWith(EXP, { question: 'what is this record?' });
    expect(mem).not.toHaveBeenCalled();
    await waitFor(() => expect(getByText(/Cu K-edge XANES draft/i)).toBeInTheDocument());
  });
});

describe('P34.4 Suggested Questions use the SAME turn pipeline (no endpoint call)', () => {
  it('a pill click renders through the live-turn surface + answered-from and archives identically, calling neither endpoint', async () => {
    const mem = vi.spyOn(api, 'askMemory');
    const rec = vi.spyOn(api, 'askAssistant');
    const { getByText, container } = memoryPanel();

    // click the precomposed Suggested Question
    fireEvent.click(getByText('How fresh is project memory?'));

    // it renders on the SAME live-turn surface as a free-form answer: the single
    // `.assistant-reply` live region + the `Source:` label.
    const reply = container.querySelector('.assistant-reply') as HTMLElement;
    expect(reply.textContent).toContain('Memory was indexed recently');
    expect(getByText(/Source:/)).toBeInTheDocument();
    // precomposed pills never route through EITHER free-form endpoint
    expect(mem).not.toHaveBeenCalled();
    expect(rec).not.toHaveBeenCalled();

    // it archives into the ephemeral session identically to a free-form turn:
    // starting a new turn moves the pill answer into the persisted log.
    fireEvent.click(container.querySelector('.assistant-composer-input') as HTMLElement);
    fireEvent.change(container.querySelector('.assistant-composer-input') as HTMLElement, {
      target: { value: 'a follow-up question' },
    });
    vi.spyOn(api, 'askMemory').mockResolvedValue(memoryAnswer());
    fireEvent.submit((container.querySelector('.assistant-composer-input') as HTMLElement).closest('form')!);

    await waitFor(() => {
      const archived = loadSession(MEM).messages;
      expect(archived.some((m) => (m.text ?? '').includes('Memory was indexed recently'))).toBe(true);
    });
  });
});
