/*
 * P36R S2 — Assistant conversation REDESIGN (layout + information architecture).
 *
 * The measured problem this slice fixes (1600×1000, `.record-right.narrow`):
 *   - `.assistant-log` was capped at `max-height: 340px` while its content was
 *     761px, so more than half the transcript was clipped and the topmost
 *     visible message was cut mid-word;
 *   - the composer + Suggested Questions + 7 Agent Actions consumed ~600px of a
 *     ~308px-wide rail BEFORE the conversation began, pushing it below the fold;
 *   - `Clear Conversation` sat between the Agent Actions and the message log;
 *   - in a 3-turn conversation NO user message was visible, so the reader could
 *     not tell what had been asked.
 *
 * These tests pin the new structure. Everything they exercise is READ-ONLY: no
 * assertion here confirms a proposal, and none weakens the verdict-language,
 * single-live-region, write-path, or no-vertical-rail guards (those stay in
 * assistant.test.tsx / assistant-a11y.test.tsx / assistant-agent-ui.test.tsx /
 * no-vertical-rail.test.ts and are untouched).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, waitFor, within } from '@testing-library/react';
import { AssistantPanel, type StageFieldOption } from '../components/AssistantPanel';
import { api } from '../lib/api';
import { appendMessage, clearAllSessions } from '../lib/assistantSession';
import type { AgentContext, Proposal } from '../lib/assistantAgent';
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
const AGENT_PROMPTS = [
  { intent: 'identify_next_missing_field', label: 'Identify the Next Missing Field' },
];

function ctx(overrides: Partial<AgentContext> = {}): AgentContext {
  return {
    experimentId: EXP,
    recordRev: 5,
    version: 'gen.5',
    workflow: {
      current_step: 'complete_metadata',
      ordered_steps: [
        {
          id: 'complete_metadata',
          label: 'Complete Metadata',
          state: 'current',
          current: true,
          reopened: false,
          blocked: false,
          reason: null,
        },
      ],
    },
    evidence: [],
    pending: [
      { id: 'series', label: 'Reduced Series' },
      { id: 'descriptor', label: 'Descriptor' },
    ],
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

function pendingProposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    id: 'proposal-series-5-1',
    experimentId: EXP,
    field: 'series',
    value: 'series-42',
    origin: 'user',
    sourceRev: 5,
    confirmationState: 'pending',
    ...overrides,
  };
}

const CURRENT_FIELD: StageFieldOption = {
  id: 'series',
  label: 'Reduced Series',
  suggestedValue: 'series-42',
  suggestedValueLabel: 'Demo answer (synthetic)',
};

function panel(extra: Record<string, unknown> = {}) {
  return render(
    <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId={EXP} recordRev={5} {...extra} />,
  );
}

async function ask(getByRole: (r: string) => HTMLElement, text: string) {
  const box = getByRole('textbox');
  fireEvent.change(box, { target: { value: text } });
  fireEvent.submit(box.closest('form')!);
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

// ---------------------------------------------------------------------------
// Empty state — guidance + controls, no conversation region
// ---------------------------------------------------------------------------

describe('P36R S2 empty state', () => {
  it('renders Suggested Questions + Agent Actions at full prominence and NO conversation region', () => {
    const { container, getByText } = panel({ agentContext: ctx(), agentPrompts: AGENT_PROMPTS });

    // the prompt controls are present and NOT inside a collapsed disclosure
    expect(container.querySelector('.assistant-empty')).not.toBeNull();
    expect(getByText('Suggested Questions')).toBeInTheDocument();
    expect(getByText('Agent Actions')).toBeInTheDocument();
    expect(container.querySelector('.assistant-prompts')).not.toBeNull();
    expect(container.querySelector('.assistant-agent-prompts')).not.toBeNull();
    expect(container.querySelector('details.assistant-more')).toBeNull();

    // no conversation region is drawn when there is nothing to hold
    expect(container.querySelector('.assistant-conversation')).toBeNull();
    expect(container.querySelectorAll('.assistant-msg').length).toBe(0);

    // the single live region is still MOUNTED (a11y contract) and still empty
    const reply = container.querySelector('.assistant-reply');
    expect(reply).not.toBeNull();
    expect(reply?.getAttribute('aria-live')).toBe('polite');
    expect(reply?.textContent).toBe('');
  });

  it('the prompt controls precede the (chrome-less) log at rest, and the composer is below them', () => {
    const { container } = panel();
    const prompts = container.querySelector('.assistant-prompts')!;
    const log = container.querySelector('.assistant-log')!;
    const composer = container.querySelector('.assistant-composer')!;
    expect(prompts.compareDocumentPosition(log) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(log.compareDocumentPosition(composer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // P36V S-A — Suggested Questions are separated from the composer by a subtle
    // divider, and Agent Actions moved BELOW the composer.
    const divider = container.querySelector('.assistant-empty-divider')!;
    expect(divider).not.toBeNull();
    expect(prompts.compareDocumentPosition(divider) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(divider.compareDocumentPosition(composer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Conversation state — bounded region, collapsed controls, composer always there
// ---------------------------------------------------------------------------

describe('P36R S2 conversation state', () => {
  it('after ONE turn a conversation region exists, the prompt controls collapse, and the composer stays', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { container, getByRole } = panel({ agentContext: ctx(), agentPrompts: AGENT_PROMPTS });

    await ask(getByRole, 'what is this record?');
    await waitFor(() => expect(container.querySelector('.assistant-conversation')).not.toBeNull());

    // the log element IS the conversation region (never re-mounted — the single
    // live region inside it must survive the transition)
    const region = container.querySelector('.assistant-conversation')!;
    expect(region.classList.contains('assistant-log')).toBe(true);
    expect(region.getAttribute('role')).toBe('log');
    expect(region.querySelector('.assistant-reply')).not.toBeNull();

    // the prompt controls are COLLAPSED, not removed
    const disclosure = container.querySelector('details.assistant-more') as HTMLDetailsElement;
    expect(disclosure).not.toBeNull();
    expect(disclosure.open).toBe(false);
    expect(disclosure.querySelector('.assistant-prompts')).not.toBeNull();
    expect(container.querySelector('.assistant-empty')).toBeNull();
    // P36V S-A — and the disclosure is no longer BETWEEN the transcript and the
    // composer: the composer sits directly beneath the transcript, the collapsed
    // controls come after it.
    const composerEl = container.querySelector('.assistant-composer')!;
    expect(region.compareDocumentPosition(composerEl) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      composerEl.compareDocumentPosition(disclosure) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(disclosure.closest('.assistant-body')).toBeNull();

    // asking again is NEVER hidden: the composer is still present and enabled
    const box = getByRole('textbox') as HTMLInputElement;
    expect(box).toBeInTheDocument();
    expect(getByRole('button', { name: /send question/i })).not.toBeDisabled();
  });

  it('the CURRENT turn shows the question that produced the answer (the reader can tell what was asked)', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { container, getByRole } = panel();

    await ask(getByRole, 'what is this record?');
    await waitFor(() => expect(container.querySelector('.assistant-msg-live')).not.toBeNull());

    const live = container.querySelector('.assistant-msg-live')!;
    expect(live.getAttribute('data-role')).toBe('user');
    expect(live.textContent).toContain('what is this record?');
    // it sits inside the conversation region, ABOVE the answer it produced
    const reply = container.querySelector('.assistant-reply')!;
    expect(live.closest('.assistant-conversation')).not.toBeNull();
    expect(live.compareDocumentPosition(reply) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('opening the disclosure exposes the same working Suggested Question pills', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { container, getByRole, getByText } = panel();
    await ask(getByRole, 'first question');
    await waitFor(() => expect(container.querySelector('details.assistant-more')).not.toBeNull());

    const disclosure = container.querySelector('details.assistant-more') as HTMLDetailsElement;
    const summary = disclosure.querySelector('summary')!;
    // a native <details> summary is keyboard-operable and carries a text label
    expect(summary.textContent).toMatch(/suggested questions/i);
    fireEvent.click(summary);

    const pill = getByText('What still needs me?').closest('button')!;
    expect(pill.tagName).toBe('BUTTON');
    expect(pill).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Clear Conversation — in the header, only when there is something to clear
// ---------------------------------------------------------------------------

describe('P36R S2 Clear Conversation placement', () => {
  it('is absent with no conversation and present INSIDE the header once one exists', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { container, getByRole, queryByRole } = panel();

    expect(queryByRole('button', { name: /clear conversation/i })).toBeNull();
    expect(container.querySelector('.assistant-head .assistant-clear')).toBeNull();

    await ask(getByRole, 'what is this record?');
    await waitFor(() =>
      expect(queryByRole('button', { name: /clear conversation/i })).not.toBeNull(),
    );

    const clear = getByRole('button', { name: /clear conversation/i });
    expect(clear.tagName).toBe('BUTTON'); // keyboard-reachable from the header
    expect(clear.closest('.assistant-head')).not.toBeNull();
    // and it is NOT between the controls and the transcript any more
    const log = container.querySelector('.assistant-log')!;
    expect(clear.compareDocumentPosition(log) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector('.assistant-log-toolbar')).toBeNull();
  });

  it('clearing empties the transcript and returns focus to the composer (record state untouched)', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const submitSpy = vi.spyOn(api, 'submitAnswer');
    const editSpy = vi.spyOn(api, 'editField');
    const { container, getByRole, queryByRole } = panel();

    await ask(getByRole, 'q one');
    await waitFor(() =>
      expect(queryByRole('button', { name: /clear conversation/i })).not.toBeNull(),
    );
    fireEvent.click(getByRole('button', { name: /clear conversation/i }));

    expect(container.querySelectorAll('.assistant-msg').length).toBe(0);
    expect(container.querySelector('.assistant-conversation')).toBeNull();
    expect(document.activeElement).toBe(getByRole('textbox'));
    // session-only: no record/truth mutation is ever issued by Clear
    expect(submitSpy).not.toHaveBeenCalled();
    expect(editSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Message distinction + provenance placement
// ---------------------------------------------------------------------------

describe('P36R S2 transcript legibility', () => {
  it('user and assistant turns are distinguishable by data-role AND a text label (never colour alone)', () => {
    appendMessage(EXP, { role: 'user', text: 'user asks' });
    appendMessage(EXP, { role: 'assistant', text: 'assistant answers', answeredFrom: 'workflow' });
    const { container } = panel();

    const user = container.querySelector('.assistant-msg-user')!;
    const asst = container.querySelector('.assistant-msg-assistant')!;
    expect(user.getAttribute('data-role')).toBe('user');
    expect(asst.getAttribute('data-role')).toBe('assistant');
    // a real text label, not just alignment/colour
    expect(within(user as HTMLElement).getByText(/^you$/i)).toBeInTheDocument();
    expect(within(asst as HTMLElement).getByText(/^assistant$/i)).toBeInTheDocument();
    // both live inside the ONE bordered conversation region
    expect(user.closest('.assistant-conversation')).not.toBeNull();
    expect(asst.closest('.assistant-conversation')).not.toBeNull();
  });

  it('provenance renders INSIDE the response block it supports, not as a detached footer', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ sources: [{ label: 'Evidence Audit', navigate_to: null }] }),
    );
    const { container, getByRole } = panel();
    await ask(getByRole, 'what evidence is cited?');
    await waitFor(() => expect(container.querySelector('.assistant-provenance')).not.toBeNull());

    const block = container.querySelector('.assistant-reply-block')!;
    // the `Source:` line AND the cited-source chips both belong to the
    // response block that owns the answer they describe
    expect(block.querySelector('.answered-from')).not.toBeNull();
    expect(block.querySelector('.assistant-provenance')).not.toBeNull();
    expect(container.querySelector('.assistant-provenance')!.closest('.assistant-reply-block')).toBe(
      block,
    );
  });

  it('an archived assistant turn carries its own `Source:` line inside its own bubble', () => {
    appendMessage(EXP, { role: 'assistant', text: 'archived answer', answeredFrom: 'schema' });
    const { container } = panel();
    const bubble = container.querySelector('.assistant-msg-assistant')!;
    expect(bubble.querySelector('.answered-from')?.textContent).toMatch(/Source: Schema Rules/);
  });
});

// ---------------------------------------------------------------------------
// Proposed-action region — not a chat message
// ---------------------------------------------------------------------------

describe('P36R S2 proposed-action region', () => {
  it('a staged proposal renders in a labelled proposed-action region that is NOT a chat message', () => {
    const { container, getByRole } = panel({
      agentContext: ctx(),
      agentPrompts: AGENT_PROMPTS,
      proposal: pendingProposal(),
    });

    const region = container.querySelector('.assistant-proposed') as HTMLElement;
    expect(region).not.toBeNull();
    // P36V — the accessible name now comes from the VISIBLE eyebrow via
    // aria-labelledby rather than a detached aria-label, so a screen reader hears
    // exactly what is on screen and the two cannot drift. Still asserts the name
    // says "proposed action", and additionally pins it to the rendered text and
    // forbids the retired "needs your confirmation" wording — which was untrue of
    // the navigation action this region also holds (it writes nothing).
    const namedBy = document.getElementById(region.getAttribute('aria-labelledby') ?? '');
    expect(namedBy).not.toBeNull();
    expect(namedBy!.textContent).toMatch(/proposed action/i);
    expect(namedBy!.textContent?.trim()).toBe('Proposed Action — Not Applied');
    expect(region.getAttribute('aria-label')).toBeNull();
    // Scoped to the NAME, not the region text: a staged proposal card legitimately
    // says "Needs Your Confirmation" about itself — a write does need confirming.
    // What must never claim it is the region name, which also covers navigation.
    expect(namedBy!.textContent).not.toMatch(/needs your confirmation/i);
    // it is labelled as a PROPOSAL and never implies the action already happened
    expect(region.textContent).toMatch(/not applied/i);
    expect(region.textContent).toMatch(/not changed the official record/i);

    const card = container.querySelector('.agent-proposal')!;
    expect(card.closest('.assistant-proposed')).toBe(region);
    // …and it is neither a conversation bubble nor inside the transcript
    expect(card.classList.contains('assistant-msg')).toBe(false);
    expect(card.closest('.assistant-msg')).toBeNull();
    expect(card.closest('.assistant-log')).toBeNull();

    // the region sits directly above the composer, where it cannot scroll away
    const composer = container.querySelector('.assistant-composer')!;
    expect(region.compareDocumentPosition(composer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Confirm/Cancel are still real buttons and nothing has been written
    expect(getByRole('button', { name: /^confirm$/i }).tagName).toBe('BUTTON');
    expect(getByRole('button', { name: /^cancel$/i }).tagName).toBe('BUTTON');
  });

  it('a StageAnswer affordance renders in the SAME proposed-action region, not in the transcript', () => {
    const { container } = panel({ agentContext: ctx(), stageField: CURRENT_FIELD });
    const stage = container.querySelector('.agent-stage')!;
    expect(stage).not.toBeNull();
    expect(stage.closest('.assistant-proposed')).not.toBeNull();
    expect(stage.closest('.assistant-log')).toBeNull();
    expect(stage.classList.contains('assistant-msg')).toBe(false);
  });

  it('no proposed-action region exists when nothing is proposed', () => {
    const { container } = panel({ agentContext: ctx() });
    expect(container.querySelector('.assistant-proposed')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// CSS source contract (same import.meta.glob idiom as no-vertical-rail.test.ts)
// ---------------------------------------------------------------------------

const cssFiles = import.meta.glob('../components/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

// Comments are stripped first: this file documents its selectors inside block
// comments, so a naive scan would otherwise match a selector NAME mentioned in
// prose rather than the rule that declares it.
const assistantCss = (
  Object.entries(cssFiles).find(([p]) => p.endsWith('/assistant.css'))?.[1] ?? ''
).replace(/\/\*[\s\S]*?\*\//g, '');

/** The declaration body of the FIRST rule whose selector list contains `sel`. */
function ruleBody(css: string, sel: string): string {
  const re = new RegExp(`(^|[,}\\s])${sel.replace(/\./g, '\\.')}\\s*(,[^{]*)?\\{([^}]*)\\}`, 'm');
  const m = re.exec(css);
  return m ? m[3] : '';
}

describe('P36R S2 assistant.css structural contract', () => {
  it('assistant.css is loadable and no longer caps the log at the clipping 340px height', () => {
    expect(assistantCss.length).toBeGreaterThan(0);
    expect(assistantCss).toMatch(/\.assistant-log\s*\{/);
    // the measured clip: clientHeight 340 vs scrollHeight 761
    expect(assistantCss).not.toMatch(/max-height:\s*340px/);
    const log = ruleBody(assistantCss, '.assistant-log');
    expect(log).not.toMatch(/max-height/);
  });

  it('the conversation region flexes, scrolls, and never collapses to nothing', () => {
    const region = ruleBody(assistantCss, '.assistant-conversation');
    expect(region.length).toBeGreaterThan(0);
    expect(region).toMatch(/flex:\s*1/);
    expect(region).toMatch(/min-height:\s*\d+px/);
    expect(region).toMatch(/overflow-y:\s*auto/);
    expect(region).toMatch(/overflow-x:\s*hidden/);
  });

  it('the conversation region uses ONE full four-sided border shorthand (never a colored vertical rail)', () => {
    const region = ruleBody(assistantCss, '.assistant-conversation');
    // a full `border:` shorthand — the permanent no-vertical-rail rule forbids a
    // colored border-left/border-right anywhere (enforced in no-vertical-rail.test.ts)
    expect(region).toMatch(/(^|\n)\s*border:\s*1px solid var\(--assist-border\);/);
    expect(region).not.toMatch(/border-(left|right)/);
  });

  it('the panel is a flex column whose body absorbs the height, with a docked composer', () => {
    const panelRule = ruleBody(assistantCss, '.assistant');
    expect(panelRule).toMatch(/flex-direction:\s*column/);
    expect(panelRule).toMatch(/min-height:\s*0/);
    const body = ruleBody(assistantCss, '.assistant-body');
    expect(body).toMatch(/flex:\s*1/);
    expect(body).toMatch(/min-height:\s*0/);
    const foot = ruleBody(assistantCss, '.assistant-foot');
    expect(foot).toMatch(/position:\s*sticky/);
    expect(foot).toMatch(/bottom:\s*0/);
  });

  /*
   * BOUNDED-COLUMN GUARD (regression, P36R S2 review).
   *
   * The first cut of this slice deleted the 340px clip but let the panel STRETCH
   * to its rail — and the rail's height is the MAIN column's height (1407px on a
   * populated record at a 1000px viewport), so the composer landed at y≈1213,
   * off screen. jsdom applies no CSS and cannot catch that, so this is a
   * CSS-SOURCE PROXY, not proof: it asserts the declarations that make the panel
   * a viewport-bounded column with the conversation as the only scrolling part.
   * The real proof is a browser measurement (composer rect inside the viewport,
   * conversation scrollHeight > clientHeight, rail scrollHeight <= clientHeight)
   * at 1600×1000 / 1440×800 / 1280×720 — recorded in the slice report. This test
   * exists so the contract cannot be silently reverted.
   */
  it('the panel is VIEWPORT-BOUNDED in its rails and never stretches to the rail height', () => {
    // `ruleBody` escapes the dots itself — pass the selector UNESCAPED (an
    // already-escaped selector double-escapes and silently matches nothing).
    const rail = ruleBody(assistantCss, '.record-right .assistant');
    expect(rail.length).toBeGreaterThan(0);
    // content-sized, never `flex: 1` (which stretched it to the 1407px rail)
    expect(rail).toMatch(/flex:\s*0 0 auto/);
    expect(rail).not.toMatch(/flex:\s*1\b/);
    // capped to the viewport so the composer + caption stay inside the fold
    expect(rail).toMatch(/max-height:\s*calc\(100vh\s*-\s*\d+px\)/);
    expect(rail).toMatch(/min-height:\s*0/);
  });

  it('the conversation is the ONLY scrolling part; head / empty state / composer are flex:none', () => {
    const region = ruleBody(assistantCss, '.assistant-conversation');
    expect(region).toMatch(/flex:\s*1 1 auto/);
    expect(region).toMatch(/overflow-y:\s*auto/);
    // a positive floor (never collapses) that is still small enough to shrink
    // when a proposed action / degraded notice shares the bounded column
    expect(region).toMatch(/min-height:\s*\d+px/);
    for (const sel of ['.assistant-head', '.assistant-empty', '.assistant-more', '.assistant-proposed', '.assistant-foot']) {
      expect(ruleBody(assistantCss, sel), `${sel} must not absorb the column`).toMatch(
        /flex:\s*none/,
      );
    }
  });

  it('every text carrier in the conversation wraps rather than forcing horizontal overflow', () => {
    for (const sel of ['.assistant-msg', '.assistant-msg-text', '.assistant-reply']) {
      expect(ruleBody(assistantCss, sel)).toMatch(/overflow-wrap:\s*anywhere/);
    }
    // buttons/chips that carry arbitrary-length labels wrap too
    for (const sel of ['.assistant-prompt', '.assistant-agent-prompt', '.answered-from']) {
      expect(ruleBody(assistantCss, sel)).toMatch(/overflow-wrap:\s*anywhere/);
    }
  });
});
