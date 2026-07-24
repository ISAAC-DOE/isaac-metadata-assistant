/*
 * P34.3 — answer provenance, source navigation, live-answer staleness + Ask
 * Again, and Project-Memory citation rendering.
 *
 * These tests pin the P34.3 contract on the live (current) answer:
 *   - an answer's `sources` render one chip each; a source with a safe client
 *     route navigates via the app router on click; a source without one (or with
 *     a non-client target) renders a plain, non-navigating label chip;
 *   - a Project-Memory answer renders its cited leads and keeps the "leads to
 *     verify" advisory framing with no PASS/FAIL verdict language;
 *   - after a live answer resolves at rev N, re-rendering at a HIGHER recordRev
 *     shows the COMPACT "Based on an earlier version" indicator + an "Ask again"
 *     control; Ask again re-queries with the same question and (with a fresh rev)
 *     clears the stale indicator;
 *   - a bare recordRev change NEVER auto-refetches (only an explicit Ask again /
 *     new submit re-queries);
 *   - the provenance / Ask-again / follow-up paths are READ-ONLY — never
 *     submitAnswer / editField / confirmProposal.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, waitFor, within } from '@testing-library/react';

// Mock the app router so the panel's cited-source navigation is observable
// without mounting a full <Router>. `vi.hoisted` gives the factory a spy it can
// safely close over (vi.mock is hoisted above the imports).
const { navigateSpy } = vi.hoisted(() => ({ navigateSpy: vi.fn() }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateSpy }));

import { AssistantPanel } from '../components/AssistantPanel';
import { api } from '../lib/api';
import * as agentModule from '../lib/assistantAgent';
import { clearAllSessions } from '../lib/assistantSession';
import type { AgentContext } from '../lib/assistantAgent';
import type { AssistantMessage, AssistantQueryResponse, SuggestedPrompt } from '../lib/types';

const EXP = '01EXPERIMENTA0000000000000';
const OTHER = '01EXPERIMENTB0000000000000';

const REPLY: AssistantMessage = { text: 'Two fields still need you.', answeredFrom: 'workflow' };
const PROMPTS: SuggestedPrompt[] = [
  { text: 'What still needs me?', answeredFrom: 'workflow' },
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
    evidence: [],
    pending: [],
    ...overrides,
  };
}

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

async function ask(container: HTMLElement, getByRole: (r: string) => HTMLElement, text: string) {
  const box = getByRole('textbox');
  fireEvent.change(box, { target: { value: text } });
  fireEvent.submit(box.closest('form')!);
  await waitFor(() =>
    expect(container.querySelector('.assistant-provenance')).toBeTruthy(),
  );
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

describe('P34.3 provenance chips', () => {
  it('renders one chip per source; a client-route source navigates on click', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({
        sources: [
          { label: 'Record Workbench', navigate_to: `/record/${EXP}` },
          { label: 'Evidence Audit', navigate_to: null },
        ],
      }),
    );
    const { getByRole, container } = panel();
    await ask(container, getByRole, 'what is this record?');

    const chips = container.querySelectorAll('.assistant-provenance-item');
    expect(chips.length).toBe(2);

    // the client-route source is an interactive nav chip; clicking it routes.
    const nav = within(container.querySelector('.assistant-provenance') as HTMLElement).getByRole(
      'button',
      { name: 'Record Workbench' },
    );
    fireEvent.click(nav);
    expect(navigateSpy).toHaveBeenCalledTimes(1);
    expect(navigateSpy).toHaveBeenCalledWith(`/record/${EXP}`);
  });

  it('a source without a nav target renders a plain, non-navigating label chip', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ sources: [{ label: 'Evidence Audit', navigate_to: null }] }),
    );
    const { getByRole, container } = panel();
    await ask(container, getByRole, 'what evidence is cited?');

    const region = container.querySelector('.assistant-provenance') as HTMLElement;
    // no interactive element — it is a plain label chip
    expect(within(region).queryByRole('button')).toBeNull();
    const chip = region.querySelector('.assistant-source-chip');
    expect(chip?.textContent).toBe('Evidence Audit');
    expect(chip?.tagName).toBe('SPAN');
  });

  it('a non-client nav target (e.g. absolute/external) is rendered as a plain chip, never followed', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ sources: [{ label: 'Elsewhere', navigate_to: 'https://example.com/x' }] }),
    );
    const { getByRole, container } = panel();
    await ask(container, getByRole, 'anything');

    const region = container.querySelector('.assistant-provenance') as HTMLElement;
    expect(within(region).queryByRole('button')).toBeNull();
    expect(region.querySelector('.assistant-source-chip')?.textContent).toBe('Elsewhere');
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it('a Project-Memory answer renders its cited leads and keeps the advisory framing (no verdict)', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({
        answer:
          'Memory suggests a related Cu K-edge run; the current record shows only this draft. ' +
          'These are leads to verify, not facts.',
        grounding: ['graph'],
        sources: [
          { label: 'Related Cu K-edge run', navigate_to: `/record/${OTHER}` },
          { label: 'Cu K-edge XANES (concept)', navigate_to: '/memory' },
        ],
      }),
    );
    const { getByRole, getByText, container } = panel({ availability: 'available' });
    await ask(container, getByRole, 'anything related?');

    // the plane label is Project Memory; the chips ARE the cited memory leads.
    expect(getByText('answered from: Project Memory')).toBeInTheDocument();
    const region = container.querySelector('.assistant-provenance') as HTMLElement;
    expect(region.querySelectorAll('.assistant-provenance-item').length).toBe(2);
    expect(within(region).getByRole('button', { name: 'Related Cu K-edge run' })).toBeTruthy();
    expect(within(region).getByRole('button', { name: 'Cu K-edge XANES (concept)' })).toBeTruthy();

    // the advisory framing is preserved; no PASS/FAIL verdict language.
    expect(getByText(/leads to verify/i)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL)\b/);

    // a memory lead navigates in-app on click.
    fireEvent.click(within(region).getByRole('button', { name: 'Cu K-edge XANES (concept)' }));
    expect(navigateSpy).toHaveBeenCalledWith('/memory');
  });
});

describe('D1 — a cited source label carrying verdict language is never rendered as a chip', () => {
  it('filters out a source whose label trips the verdict guard, keeping safe leads', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({
        grounding: ['graph'],
        sources: [
          { label: 'Records valid against v1.05', navigate_to: '/memory/doc1' },
          { label: 'QC gate marked PASS', navigate_to: '/memory/doc2' },
          { label: 'Copper oxide note', navigate_to: '/memory/doc3' },
        ],
      }),
    );
    const { getByRole, container } = panel({ availability: 'available' });
    await ask(container, getByRole, 'anything related?');

    const region = container.querySelector('.assistant-provenance') as HTMLElement;
    // only the one safe lead renders; the two verdict-language labels are dropped.
    const chips = region.querySelectorAll('.assistant-provenance-item');
    expect(chips.length).toBe(1);
    expect(region.textContent).toContain('Copper oxide note');
    expect(container.textContent).not.toMatch(/valid against/i);
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL)\b/);
  });
});

describe('R2 — an honest refusal (empty grounding) hides the misleading `answered from:` line', () => {
  it('a refusal answer renders WITHOUT an answered-from line; a grounded answer still shows it', async () => {
    const spy = vi.spyOn(api, 'askAssistant').mockResolvedValue({
      answer:
        "That question isn't something I can answer from this record's grounded surfaces.",
      result: 'unsupported',
      grounding: [],
      sources: [],
      record_rev: 5,
      version: 'gen.5',
      stale: false,
      followups: [],
    });
    const { getByRole, container } = panel();
    const box = getByRole('textbox');
    fireEvent.change(box, { target: { value: 'what is the oxidation state of iron' } });
    fireEvent.submit(box.closest('form')!);
    await waitFor(() =>
      expect(container.querySelector('.assistant-reply')?.textContent).toContain(
        "isn't something I can answer",
      ),
    );
    // the refusal shows NO `answered from:` provenance line.
    expect(container.textContent).not.toMatch(/answered from:/i);

    // a subsequent normally-grounded answer DOES show the line again.
    spy.mockResolvedValue(answerResponse());
    fireEvent.change(box, { target: { value: 'what is this record?' } });
    fireEvent.submit(box.closest('form')!);
    await waitFor(() =>
      expect(container.querySelector('.assistant-provenance')).toBeTruthy(),
    );
    expect(container.textContent).toMatch(/answered from:/i);
  });
});

describe('P34.3 live staleness + Ask again', () => {
  it('a higher recordRev marks the live answer stale and offers Ask again; Ask again re-queries and clears stale', async () => {
    const spy = vi
      .spyOn(api, 'askAssistant')
      .mockResolvedValue(answerResponse({ record_rev: 5 }));
    const { getByRole, container, rerender, queryByText } = panel();
    await ask(container, getByRole, 'what is this record?');

    // fresh at rev 5 — not stale
    expect(container.querySelector('.assistant-live-stale-row')).toBeNull();

    // the record advances to rev 7 → the SAME live answer is now stale
    rerender(
      <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId={EXP} recordRev={7} />,
    );
    expect(container.querySelector('.assistant-live-stale-row')).toBeTruthy();
    expect(queryByText('Based on an earlier version')).toBeInTheDocument();
    const askAgain = getByRole('button', { name: 'Ask again with the current record' });

    // the stale indicator is programmatically associated with the answer region
    const reply = container.querySelector('.assistant-reply') as HTMLElement;
    const stale = container.querySelector('.assistant-live-stale-row .assistant-msg-stale') as HTMLElement;
    expect(reply.getAttribute('aria-describedby')).toBe(stale.id);

    // Ask again re-queries with the SAME question; the fresh rev clears stale
    spy.mockResolvedValue(answerResponse({ record_rev: 7 }));
    fireEvent.click(askAgain);
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    expect(spy.mock.calls[1][1]).toEqual({ question: 'what is this record?' });
    await waitFor(() => expect(container.querySelector('.assistant-live-stale-row')).toBeNull());
  });
});

describe('P34.3 no auto-regeneration', () => {
  it('changing recordRev alone never calls the resolver', async () => {
    const spy = vi
      .spyOn(api, 'askAssistant')
      .mockResolvedValue(answerResponse({ record_rev: 5 }));
    const { getByRole, container, rerender } = panel();
    await ask(container, getByRole, 'what is this record?');
    expect(spy).toHaveBeenCalledTimes(1);

    // a bare record advance must NOT trigger a refetch — only mark stale
    rerender(
      <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId={EXP} recordRev={9} />,
    );
    rerender(
      <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId={EXP} recordRev={12} />,
    );
    expect(spy).toHaveBeenCalledTimes(1);
    expect(container.querySelector('.assistant-live-stale-row')).toBeTruthy();
  });
});

describe('P34.3 read-only — provenance / Ask again / follow-ups never mutate', () => {
  it('Ask again and a follow-up route only through the read-only resolver', async () => {
    const spy = vi
      .spyOn(api, 'askAssistant')
      .mockResolvedValue(answerResponse({ record_rev: 5, followups: ['What is the edge?'] }));
    const submit = vi.spyOn(api, 'submitAnswer');
    const edit = vi.spyOn(api, 'editField');
    const confirm = vi.spyOn(agentModule, 'confirmProposal');

    const { getByRole, container } = panel({ agentContext: ctx(), onRefresh: vi.fn() });
    await ask(container, getByRole, 'what is this record?');

    // a follow-up chip is offered on a CURRENT answer; clicking it re-queries
    const followup = getByRole('button', { name: /What is the edge\?/ });
    fireEvent.click(followup);
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));

    expect(submit).not.toHaveBeenCalled();
    expect(edit).not.toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
  });
});
