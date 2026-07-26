/*
 * P36V S-A — the Assistant PANEL PRESENTATION CONTRACT.
 *
 * What this slice changed, and therefore what these tests pin:
 *   1. the header is icon + "Assistant" with the availability STATUS ROW directly
 *      BENEATH the title (it used to sit at the far right of the header), and
 *      Clear Conversation on the right of that same block;
 *   2. the clear control's VISIBLE label is the full "Clear Conversation" (it read
 *      "Clear" with a contradicting aria-label "Clear conversation");
 *   3. the status row has THREE states, all of which exist in the app:
 *        (a) `availability` given + the panel is the axis's sole visible owner
 *            (Record Workbench, Export Readiness) → the row renders;
 *        (b) `availability` given but the PAGE already owns the visible label
 *            (Project Memory's GraphStatusChip, Evidence Explorer's status-bar
 *            chip) → `showAvailabilityStatus={false}` suppresses the row, while
 *            `availability` still drives `classifyAnswer` and the caveat;
 *        (c) `availability` omitted — the mount cannot know it (Guided
 *            Completion) → nothing renders and nothing is fabricated;
 *   4. Clear fully resets ephemeral state, INCLUDING the staged, unconfirmed
 *      proposal, which previously survived it;
 *   5. EVERY assistant answer — the live one included — renders as a labelled
 *      left-aligned bubble (icon + visible "Assistant" + text). The live answer
 *      used to be a bare, border-less, label-less <p>;
 *   6. provenance reads "Source: <label>" (was the lowercase "answered from:");
 *   7. an answer's follow-ups carry the visible Title-Case label "Related
 *      Questions", distinct from the global "Suggested Questions";
 *   8. active order: header → transcript → composer → collapsed controls → footer;
 *   9. empty order: header → guidance → Suggested Questions → divider → composer
 *      → Agent Actions → footer;
 *  10. the advisory footer keeps its hair divider + secondary colour and is now
 *      italicised.
 *
 * Everything exercised here is READ-ONLY. No assertion confirms a proposal; the
 * only api calls stubbed are the read-only resolvers (askAssistant / askMemory).
 * The verdict-language, single-live-region, write-path and no-vertical-rail
 * guards are NOT relaxed anywhere — the bubble deliberately uses a full
 * four-sided `border:` shorthand and is asserted to have no coloured
 * border-left/border-right (no-vertical-rail.test.ts remains the system-wide
 * scan; this file adds a targeted check for the new selectors).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AssistantPanel, type StageFieldOption } from '../components/AssistantPanel';
import { AppRoutes } from '../App';
import { api } from '../lib/api';
import { SOURCE_LABELS, SUBORDINATE_CAPTION } from '../lib/assistant';
import { appendMessage, clearAllSessions } from '../lib/assistantSession';
import type { AgentContext, Proposal } from '../lib/assistantAgent';
import {
  bundleRoutes,
  evidenceBundleRoutes,
  graphStatusAvailable,
  stubFetchRoutes,
} from '../test/apiFixtures';
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
    pending: [{ id: 'series', label: 'Reduced Series' }],
    ...overrides,
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

async function ask(getByRole: (r: string) => HTMLElement, text: string) {
  const box = getByRole('textbox');
  fireEvent.change(box, { target: { value: text } });
  fireEvent.submit(box.closest('form')!);
}

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  clearAllSessions();
  sessionStorage.clear();
});
afterEach(() => {
  clearAllSessions();
  sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// 1 + 3 — header block: title, STATUS ROW beneath it, Clear on the right
// ---------------------------------------------------------------------------

describe('P36V S-A · header + status row', () => {
  it('the status row sits BENEATH the title inside the header, not in the trailing control group', () => {
    const { container } = panel({ availability: 'available' });

    const head = container.querySelector('.assistant-head') as HTMLElement;
    const titles = head.querySelector('.assistant-head-titles') as HTMLElement;
    const label = head.querySelector('.assistant-label') as HTMLElement;
    const row = head.querySelector('.assistant-memory') as HTMLElement;

    expect(titles).not.toBeNull();
    expect(label.closest('.assistant-head-titles')).toBe(titles);
    // the status row is in the SAME stacked block as the title …
    expect(row).not.toBeNull();
    expect(row.closest('.assistant-head-titles')).toBe(titles);
    // … it comes AFTER the title (i.e. it reads beneath it) …
    expect(label.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // … and it is NOT in the header's trailing (far-right) group any more.
    expect(row.closest('.assistant-head-right')).toBeNull();
    // Title Case + the icon-independent dot (colour is never the only signal)
    expect(row.textContent).toMatch(/^\s*Memory Available\s*$/);
    expect(row.querySelector('.dot-memory')).not.toBeNull();
    // and the header still carries the assistant icon + Title-Case title
    expect(head.querySelector('.assistant-icon svg')).not.toBeNull();
    expect(label.textContent).toBe('Assistant');
  });

  it('renders the unavailable state in the SAME row, in Title Case', () => {
    const { container } = panel({ availability: 'unavailable' });
    const row = container.querySelector('.assistant-head .assistant-memory') as HTMLElement;
    expect(row.textContent).toMatch(/^\s*Memory Unavailable\s*$/);
    expect(row.textContent).not.toMatch(/memory: unavailable/i);
  });

  it('renders NOTHING where the mount cannot truthfully know the availability (never a default)', () => {
    // no `availability` prop ⇒ the screen made no memory claim ⇒ no status row,
    // no fabricated "Available", no placeholder, no "Unknown" invention.
    const { container } = panel();
    expect(container.querySelector('.assistant-memory')).toBeNull();
    expect(container.querySelector('.assistant-head')!.textContent).not.toMatch(/memory/i);
    expect(container.querySelector('.assistant-caveat')).toBeNull();
  });

  it('showAvailabilityStatus={false} hides the ROW only — the caveat still renders', () => {
    // State (b): the mount KNOWS the axis (and needs it) but the page already
    // owns the visible label. Suppressing the row must not suppress the honest
    // memory caveat, which is driven by `availability` alone.
    const { container } = panel({ availability: 'unavailable', showAvailabilityStatus: false });
    expect(container.querySelector('.assistant-memory')).toBeNull();
    const caveat = container.querySelector('.assistant-caveat') as HTMLElement;
    expect(caveat).not.toBeNull();
    expect(caveat.textContent).toMatch(
      /Project Memory is unavailable, so no memory-based answer is available here\./,
    );
    // and with the row shown, the caveat is IDENTICAL — the flag is presentation
    // only, never a capability switch.
    const shown = panel({ availability: 'unavailable' });
    expect(
      (shown.container.querySelector('.assistant-caveat') as HTMLElement).textContent,
    ).toBe(caveat.textContent);
    expect(shown.container.querySelector('.assistant-memory')).not.toBeNull();
  });

  it('showAvailabilityStatus={false} does NOT change classifyAnswer: a graph answer stays degraded', () => {
    // The OTHER consumer of `availability`: `classifyAnswer` marks a
    // graph-sourced answer `degraded` when memory is unavailable and `advisory`
    // when it is available. The visible-row flag must not touch that. Read
    // through the archived bubble's `data-kind`, which the classification drives.
    const graphPrompts: SuggestedPrompt[] = [
      {
        text: 'What is related?',
        answeredFrom: 'graph',
        answer: { text: 'Two indexed leads mention this sample.', answeredFrom: 'graph' },
      },
      {
        text: 'Anything else?',
        answeredFrom: 'graph',
        answer: { text: 'One further indexed lead.', answeredFrom: 'graph' },
      },
    ];
    const kindOf = (extra: Record<string, unknown>) => {
      const { container, getByText, unmount } = render(
        <AssistantPanel
          reply={REPLY}
          prompts={graphPrompts}
          experimentId={EXP}
          recordRev={5}
          {...extra}
        />,
      );
      // ask, then ask again so the FIRST turn archives with its classification
      fireEvent.click(getByText('What is related?'));
      fireEvent.click(getByText('Anything else?'));
      const archived = container.querySelector('.assistant-msg-assistant') as HTMLElement;
      const kind = archived.getAttribute('data-kind');
      const hasCaveat = container.querySelector('.assistant-caveat') !== null;
      unmount();
      clearAllSessions();
      sessionStorage.clear();
      return { kind, hasCaveat };
    };

    const shown = kindOf({ availability: 'unavailable' });
    const hidden = kindOf({ availability: 'unavailable', showAvailabilityStatus: false });
    const available = kindOf({ availability: 'available', showAvailabilityStatus: false });

    // the classification is real (not a constant), and the flag never moves it
    expect(shown.kind).toBe('degraded');
    expect(hidden.kind).toBe('degraded');
    expect(available.kind).toBe('advisory');
    expect(hidden.hasCaveat).toBe(true);
    expect(shown.hasCaveat).toBe(true);
    expect(available.hasCaveat).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 2 + 4 — Clear Conversation: label, conditionality, FULL ephemeral reset
// ---------------------------------------------------------------------------

describe('P36V S-A · Clear Conversation', () => {
  it('is hidden with nothing to clear, and its VISIBLE label is the full "Clear Conversation"', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { container, getByRole, queryByRole } = panel({ availability: 'available' });

    // hidden at rest, and it reserves NO space when hidden
    expect(queryByRole('button', { name: 'Clear Conversation' })).toBeNull();
    expect(container.querySelector('.assistant-clear')).toBeNull();
    const right = container.querySelector('.assistant-head-right') as HTMLElement;
    expect(right.children.length).toBe(0); // `:empty` collapses it in CSS

    await ask(getByRole, 'what is this record?');
    await waitFor(() =>
      expect(container.querySelector('.assistant-clear')).not.toBeNull(),
    );

    const clear = getByRole('button', { name: 'Clear Conversation' });
    // the VISIBLE text is the full label (not the abbreviated "Clear")
    expect(clear.textContent?.trim()).toBe('Clear Conversation');
    // the accessible name comes from that same visible text — there is no
    // aria-label that could contradict or re-case it
    expect(clear.getAttribute('aria-label')).toBeNull();
    // it lives on the right of the header block, keyboard-reachable
    expect(clear.tagName).toBe('BUTTON');
    expect(clear.closest('.assistant-head-right')).not.toBeNull();
    expect(clear.closest('.assistant-head')).not.toBeNull();
  });

  it('clears the transcript, the live answer, the follow-ups AND the staged proposal, then focuses the composer', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ followups: ['What is the edge?'] }),
    );
    const submitSpy = vi.spyOn(api, 'submitAnswer');
    const editSpy = vi.spyOn(api, 'editField');
    const { container, getByRole, getByText, queryByText } = panel({
      availability: 'available',
      agentContext: ctx(),
      agentPrompts: AGENT_PROMPTS,
      proposal: pendingProposal(),
    });

    // a conversation, an answer with follow-ups, and a STAGED proposal all exist
    await ask(getByRole, 'q one');
    await waitFor(() => expect(container.querySelector('.assistant-followup')).not.toBeNull());
    expect(container.querySelector('.agent-proposal')).not.toBeNull();
    expect(container.querySelector('.assistant-proposed')).not.toBeNull();
    expect(getByText('Related Questions')).toBeInTheDocument();

    fireEvent.click(getByRole('button', { name: 'Clear Conversation' }));

    // nothing ephemeral survives
    expect(container.querySelectorAll('.assistant-msg').length).toBe(0);
    expect(container.querySelector('.assistant-conversation')).toBeNull();
    expect(container.querySelector('.assistant-followup')).toBeNull();
    expect(queryByText('Related Questions')).toBeNull();
    // THE BUG THIS SLICE FIXED: the staged, unconfirmed proposal used to survive
    // a Clear and keep offering Confirm over a discarded conversation.
    expect(container.querySelector('.agent-proposal')).toBeNull();
    expect(container.querySelector('.assistant-proposed')).toBeNull();
    // the live answer bubble is back to rendering as nothing
    const reply = container.querySelector('.assistant-reply')!;
    expect(reply.textContent).toBe('');
    expect(reply.classList.contains('assistant-reply--empty')).toBe(true);
    expect(
      container.querySelector('.assistant-answer')!.classList.contains('assistant-answer--empty'),
    ).toBe(true);
    // the correct EMPTY state is restored (guidance + Suggested Questions + divider)
    expect(container.querySelector('.assistant-empty')).not.toBeNull();
    expect(container.querySelector('.assistant-empty-divider')).not.toBeNull();
    expect(container.querySelector('details.assistant-more')).toBeNull();
    // focus lands on the always-present composer, not <body>
    expect(document.activeElement).toBe(getByRole('textbox'));
    // and NOTHING was written: Clear is session-only
    expect(submitSpy).not.toHaveBeenCalled();
    expect(editSpy).not.toHaveBeenCalled();
  });

  it('a StageAnswer affordance is also cleared, and re-staging is still possible afterwards', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { container, getByRole } = panel({
      availability: 'available',
      agentContext: ctx(),
      stageField: CURRENT_FIELD,
    });
    await ask(getByRole, 'q one');
    await waitFor(() => expect(container.querySelector('.assistant-clear')).not.toBeNull());

    // stage a value → an UNCONFIRMED proposal card appears (no write)
    fireEvent.click(getByRole('button', { name: /stage answer/i }));
    expect(container.querySelector('.agent-proposal')).not.toBeNull();

    fireEvent.click(getByRole('button', { name: 'Clear Conversation' }));
    expect(container.querySelector('.agent-proposal')).toBeNull();
    // the staging affordance itself returns (one staged value at a time)
    expect(container.querySelector('.agent-stage')).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 5 + 6 + 7 — the assistant bubble, `Source:`, `Related Questions`
// ---------------------------------------------------------------------------

describe('P36V S-A · the assistant answer bubble', () => {
  it('the LIVE answer is a labelled bubble: icon + visible "Assistant" + the answer text', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { container, getByRole } = panel({ availability: 'available' });
    await ask(getByRole, 'what is this record?');
    await waitFor(() =>
      expect(container.querySelector('.assistant-reply')!.textContent).toMatch(/Cu K-edge/),
    );

    const bubble = container.querySelector('.assistant-answer') as HTMLElement;
    expect(bubble).not.toBeNull();
    expect(bubble.getAttribute('data-role')).toBe('assistant');
    expect(bubble.classList.contains('assistant-answer--empty')).toBe(false);
    // a REAL text label, not colour or alignment alone, plus the icon
    const role = bubble.querySelector('.assistant-msg-role') as HTMLElement;
    expect(role.textContent?.trim()).toBe('Assistant');
    expect(role.querySelector('svg')).not.toBeNull();
    expect(within(bubble).getByText(/^Assistant$/)).toBeInTheDocument();
    // the answer text lives inside the same bubble (still the ONE live region)
    const reply = bubble.querySelector('.assistant-reply') as HTMLElement;
    expect(reply.getAttribute('aria-live')).toBe('polite');
    expect(reply.textContent).toMatch(/Cu K-edge/);
    // still exactly one polite live region overall (no second announcer added)
    expect(container.querySelectorAll('[aria-live="polite"]').length).toBe(1);
    // the bubble is left-aligned, never a chat message in the log's message list
    expect(bubble.classList.contains('assistant-msg')).toBe(false);
  });

  it('at rest the live bubble renders as NOTHING — no chrome and no orphan "Assistant" label', () => {
    const { container } = panel({ availability: 'available' });
    const bubble = container.querySelector('.assistant-answer') as HTMLElement;
    expect(bubble.classList.contains('assistant-answer--empty')).toBe(true);
    expect(bubble.querySelector('.assistant-msg-role')).toBeNull();
    expect(bubble.textContent).toBe('');
  });

  it('an ARCHIVED answer is the same labelled bubble (icon + "Assistant")', () => {
    appendMessage(EXP, { role: 'assistant', text: 'archived answer', answeredFrom: 'schema' });
    const { container } = panel({ availability: 'available' });
    const bubble = container.querySelector('.assistant-msg-assistant') as HTMLElement;
    expect(bubble).not.toBeNull();
    expect(bubble.getAttribute('data-role')).toBe('assistant');
    const role = bubble.querySelector('.assistant-msg-role') as HTMLElement;
    expect(role.textContent?.trim()).toBe('Assistant');
    expect(role.querySelector('svg')).not.toBeNull();
    // it lives inside the ONE bordered conversation region
    expect(bubble.closest('.assistant-conversation')).not.toBeNull();
  });

  it('a REFUSAL still renders as a labelled Assistant bubble, but withholds the provenance line', async () => {
    // an honest refusal returns EMPTY grounding — there is no source to attribute
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ answer: 'That is outside what I can answer here.', grounding: [], sources: [] }),
    );
    const { container, getByRole } = panel({ availability: 'available' });
    await ask(getByRole, 'who won the 1998 world cup?');
    await waitFor(() =>
      expect(container.querySelector('.assistant-reply')!.textContent).toMatch(/outside what/),
    );

    const bubble = container.querySelector('.assistant-answer') as HTMLElement;
    expect(bubble.classList.contains('assistant-answer--empty')).toBe(false);
    expect(bubble.querySelector('.assistant-msg-role')!.textContent?.trim()).toBe('Assistant');
    // no invented source claim (case-insensitive: a lowercase `source:`
    // regression must not slip past either — P36V review, M5)
    expect(bubble.querySelector('.answered-from')).toBeNull();
    expect(container.textContent).not.toMatch(/source:/i);
  });

  it('provenance reads Title-Case "Source: <label>" inside the bubble, on BOTH the live and archived turns', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    appendMessage(EXP, { role: 'assistant', text: 'archived answer', answeredFrom: 'schema' });
    const { container, getByRole } = panel({ availability: 'available' });

    // archived
    const archived = container.querySelector('.assistant-msg-assistant') as HTMLElement;
    const archivedSrc = archived.querySelector('.answered-from') as HTMLElement;
    expect(archivedSrc.textContent).toBe(`Source: ${SOURCE_LABELS.schema}`);
    expect(archivedSrc.closest('.assistant-msg-assistant')).toBe(archived);

    // live
    await ask(getByRole, 'what is this record?');
    await waitFor(() => expect(container.querySelector('.assistant-answer .answered-from')).not.toBeNull());
    const live = container.querySelector('.assistant-answer') as HTMLElement;
    expect((live.querySelector('.answered-from') as HTMLElement).textContent).toBe(
      `Source: ${SOURCE_LABELS.workflow}`,
    );
    // the retired lowercase sentence fragment is gone everywhere
    expect(container.textContent).not.toMatch(/answered from:/i);
  });

  it('an answer’s follow-ups carry the visible "Related Questions" label, inside that answer, distinct from "Suggested Questions"', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ followups: ['What is the edge?', 'What is the beamline?'] }),
    );
    const { container, getByRole, getByText } = panel({ availability: 'available' });
    await ask(getByRole, 'what is this record?');
    await waitFor(() => expect(container.querySelector('.assistant-followups')).not.toBeNull());

    const group = container.querySelector('.assistant-followups') as HTMLElement;
    // a VISIBLE Title-Case label, and the group's accessible name IS that element
    const eyebrow = group.querySelector('.assistant-followups-eyebrow') as HTMLElement;
    expect(eyebrow.textContent).toBe('Related Questions');
    expect(group.getAttribute('role')).toBe('group');
    // P36V review (M1) — named BY the visible eyebrow (`aria-labelledby`), the
    // same pattern `.assistant-proposed` uses. A detached `aria-label` carrying
    // the same words made a screen reader announce "Related Questions" twice:
    // once as the group name, once as the eyebrow's own text.
    expect(eyebrow.id).toBeTruthy();
    expect(group.getAttribute('aria-labelledby')).toBe(eyebrow.id);
    expect(document.getElementById(group.getAttribute('aria-labelledby')!)).toBe(eyebrow);
    expect(group.getAttribute('aria-label')).toBeNull();
    // exactly ONE element carries this wording — the name is not a second copy
    expect(container.querySelectorAll('.assistant-followups-eyebrow').length).toBe(1);
    expect(getByText('Related Questions')).toBeInTheDocument();
    // it is attached to the answer it belongs to …
    expect(group.closest('.assistant-answer')).not.toBeNull();
    // … and is a different label from the global control group
    expect(getByText('Suggested Questions')).toBeInTheDocument();
    expect(eyebrow.textContent).not.toBe('Suggested Questions');
    // the follow-ups themselves are still real buttons, capped at two
    const chips = group.querySelectorAll('button.assistant-followup');
    expect(chips.length).toBe(2);
    for (const c of chips) expect(c.tagName).toBe('BUTTON');
  });
});

// ---------------------------------------------------------------------------
// 8 + 9 + 10 — order, and the advisory footer
// ---------------------------------------------------------------------------

/** True when `a` precedes `b` in document order. */
function precedes(a: Element, b: Element): boolean {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
}

describe('P36V S-A · panel order', () => {
  it('ACTIVE: header → transcript → composer → collapsed controls → advisory footer', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { container, getByRole } = panel({
      availability: 'available',
      agentContext: ctx(),
      agentPrompts: AGENT_PROMPTS,
    });
    await ask(getByRole, 'what is this record?');
    await waitFor(() => expect(container.querySelector('.assistant-conversation')).not.toBeNull());

    const head = container.querySelector('.assistant-head')!;
    const log = container.querySelector('.assistant-log')!;
    const composer = container.querySelector('.assistant-composer')!;
    const more = container.querySelector('details.assistant-more')!;
    const caption = container.querySelector('.assistant-caption')!;

    expect(precedes(head, log)).toBe(true);
    expect(precedes(log, composer)).toBe(true);
    expect(precedes(composer, more)).toBe(true);
    expect(precedes(more, caption)).toBe(true);

    // the composer is DIRECTLY beneath the transcript: no prompt controls, no
    // Suggested Questions / Agent Actions pills sit between them.
    for (const sel of ['details.assistant-more', '.assistant-prompts', '.assistant-agent-prompts']) {
      const el = container.querySelector(sel);
      if (el) expect(precedes(composer, el)).toBe(true);
    }
    expect(container.querySelector('.assistant-body details.assistant-more')).toBeNull();
  });

  it('EMPTY: header → guidance → Suggested Questions → divider → composer → Agent Actions → footer, with no filler card', () => {
    const { container } = panel({
      availability: 'available',
      agentContext: ctx(),
      agentPrompts: AGENT_PROMPTS,
    });

    const head = container.querySelector('.assistant-head')!;
    const guidance = container.querySelector('.assistant-empty-note')!;
    const prompts = container.querySelector('.assistant-prompts')!;
    const divider = container.querySelector('.assistant-empty-divider')!;
    const composer = container.querySelector('.assistant-composer')!;
    const agent = container.querySelector('.assistant-agent-actions')!;
    const caption = container.querySelector('.assistant-caption')!;

    expect(precedes(head, guidance)).toBe(true);
    expect(precedes(guidance, prompts)).toBe(true);
    expect(precedes(prompts, divider)).toBe(true);
    expect(precedes(divider, composer)).toBe(true);
    expect(precedes(composer, agent)).toBe(true);
    expect(precedes(agent, caption)).toBe(true);

    // ONE guidance sentence, and the divider is a hairline break, not a card
    expect(container.querySelectorAll('.assistant-empty-note').length).toBe(1);
    expect(guidance.textContent!.split('. ').length).toBeLessThanOrEqual(2);
    expect(divider.textContent).toBe('');
    expect(divider.getAttribute('aria-hidden')).toBe('true');
    // no collapsed disclosure while there is no conversation
    expect(container.querySelector('details.assistant-more')).toBeNull();
  });

  it('the advisory footer is the single, last, italicised caption with the approved copy', () => {
    const { container } = panel({ availability: 'available' });
    const captions = container.querySelectorAll('.assistant-caption');
    expect(captions.length).toBe(1);
    const caption = captions[0] as HTMLElement;
    expect(caption.textContent).toBe(
      'The Assistant is advisory: it explains artifacts and points to sources. ' +
        'It never validates — deterministic validation remains authoritative.',
    );
    expect(caption.textContent).toBe(SUBORDINATE_CAPTION);
    // the explicit negative capability claim is part of the footer (P36V review,
    // I2 — it was dropped in the same slice that added an Open Validator button
    // and a Deterministic Schema Check card to this very panel)
    expect(caption.textContent).toMatch(/never validates/i);
    // it is the LAST thing in the panel
    const panelEl = container.querySelector('.assistant') as HTMLElement;
    const foot = container.querySelector('.assistant-foot') as HTMLElement;
    expect(foot.lastElementChild).toBe(caption);
    expect(panelEl.lastElementChild).toBe(foot);
    // it never states a verdict
    expect(caption.textContent).not.toMatch(/\b(PASS|FAIL)\b/);
  });
});

// ---------------------------------------------------------------------------
// 12 — every mount surface
// ---------------------------------------------------------------------------

describe('P36V S-A · the contract holds on every mount surface', () => {
  const RECORD_SURFACES: Array<[string, string, string, boolean]> = [
    // [name, path, load sentinel, does the screen truthfully know availability?]
    ['Record Workbench', '/record/demo', '5 Fields Need Your Confirmation', true],
    ['Guided Completion', '/record/demo/complete', 'Answer 5 Questions to Finish This Record', false],
    ['Export Readiness', '/record/demo/export', '5 fields still block export', true],
  ];

  for (const [name, path, sentinel, knowsAvailability] of RECORD_SURFACES) {
    it(`${name}: header block, one status claim (or none), bubble-capable transcript, docked composer, one caption`, async () => {
      stubFetchRoutes({
        ...bundleRoutes('demo'),
        'GET /api/graph/status': { body: graphStatusAvailable },
      });
      const { findByText, container } = renderAt(path);
      await findByText(sentinel);

      const assistant = container.querySelector('.assistant') as HTMLElement;
      expect(assistant).not.toBeNull();
      // header: icon + Title-Case title in the stacked block
      const titles = assistant.querySelector('.assistant-head-titles') as HTMLElement;
      expect(titles).not.toBeNull();
      expect((titles.querySelector('.assistant-label') as HTMLElement).textContent).toBe('Assistant');
      // status row exactly where the screen truthfully knows the axis
      const row = assistant.querySelector('.assistant-memory');
      if (knowsAvailability) {
        expect(row).not.toBeNull();
        expect(row!.closest('.assistant-head-titles')).toBe(titles);
        expect(row!.textContent).toMatch(/^\s*Memory (Available|Unavailable)\s*$/);
      } else {
        // Guided Completion consults no graph — it claims NOTHING here
        expect(row).toBeNull();
      }
      // the live bubble element exists (mounted, empty at rest) and the composer
      // is directly beneath the transcript
      expect(assistant.querySelector('.assistant-answer')).not.toBeNull();
      const log = assistant.querySelector('.assistant-log')!;
      const composer = assistant.querySelector('.assistant-composer')!;
      expect(precedes(log, composer)).toBe(true);
      // exactly one advisory caption, and it is the approved copy
      const captions = assistant.querySelectorAll('.assistant-caption');
      expect(captions.length).toBe(1);
      expect(captions[0].textContent).toBe(SUBORDINATE_CAPTION);
      // the retired provenance wording appears nowhere on the surface
      expect(assistant.textContent).not.toMatch(/answered from:/i);
    });
  }

  it('Evidence Explorer: state (b) — the status-bar chip owns the axis, so the panel does not restate it', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { findByText, getByText, container } = renderAt('/record/demo/evidence');
    await findByText('Direct Fields');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    // no assistant status row …
    expect(assistant.querySelector('.assistant-memory')).toBeNull();
    // … and the axis is stated exactly once, by the page's chip (singular
    // getByText throws on a duplicate).
    expect(getByText('Memory Unavailable').closest('.assistant')).toBeNull();
    // the rest of the presentation contract is unchanged on this surface
    expect(assistant.querySelector('.assistant-head-titles')).not.toBeNull();
    expect(assistant.querySelector('.assistant-answer')).not.toBeNull();
    expect(assistant.querySelectorAll('.assistant-caption').length).toBe(1);
    expect(assistant.textContent).not.toMatch(/answered from:/i);
  });

  it('Project Memory: state (b) — the page chip owns the axis; the composer is still docked beneath the transcript', async () => {
    stubFetchRoutes({ 'GET /api/graph/status': { body: graphStatusAvailable } });
    const { findByText, getByText, container } = renderAt('/memory');
    await findByText('Memory Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant.querySelector('.assistant-memory')).toBeNull();
    expect(getByText('Memory Available').closest('.assistant')).toBeNull();
    expect(assistant.querySelector('.assistant-head-titles')).not.toBeNull();
    const log = assistant.querySelector('.assistant-log')!;
    expect(precedes(log, assistant.querySelector('.assistant-composer')!)).toBe(true);
    expect(assistant.querySelectorAll('.assistant-caption').length).toBe(1);
    expect(assistant.textContent).not.toMatch(/answered from:/i);
  });
});

// ---------------------------------------------------------------------------
// 11 — long-value wrapping / no horizontal overflow
//
// jsdom applies no CSS and reports 0 for every box metric, so a real overflow
// measurement is impossible here (the browser measurement belongs in the slice
// report). These assertions are therefore of two honest kinds:
//   (a) RENDERED: long content is carried by the wrapping classes and nothing
//       sets a forced inline width that CSS could not recover from;
//   (b) CSS SOURCE: the declarations that make wrapping work are present on the
//       new selectors — the same `import.meta.glob` idiom the existing
//       assistant-layout / no-vertical-rail source contracts use.
// ---------------------------------------------------------------------------

const cssFiles = import.meta.glob('../components/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

// comments stripped first: this stylesheet documents its own selectors in prose
const assistantCss = (
  Object.entries(cssFiles).find(([p]) => p.endsWith('/assistant.css'))?.[1] ?? ''
).replace(/\/\*[\s\S]*?\*\//g, '');

/** The declaration body of the FIRST rule whose selector list contains `sel`. */
function ruleBody(css: string, sel: string): string {
  const re = new RegExp(`(^|[,}\\s])${sel.replace(/\./g, '\\.')}\\s*(,[^{]*)?\\{([^}]*)\\}`, 'm');
  const m = re.exec(css);
  return m ? m[3] : '';
}

describe('P36V S-A · long values wrap; nothing forces horizontal overflow', () => {
  const LONG =
    'Supercalifragilisticexpialidocious'.repeat(6) +
    ' a very long grounded answer that must wrap inside the bubble and never force horizontal scroll';

  it('a very long live answer, its provenance and its Related Questions all wrap with no inline width', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ answer: LONG, followups: [LONG] }),
    );
    const { container, getByRole } = panel({ availability: 'available' });
    await ask(getByRole, LONG);
    await waitFor(() =>
      expect(container.querySelector('.assistant-reply')!.textContent).toContain('Supercalifragilistic'),
    );

    const bubble = container.querySelector('.assistant-answer') as HTMLElement;
    const reply = bubble.querySelector('.assistant-reply') as HTMLElement;
    const source = bubble.querySelector('.answered-from') as HTMLElement;
    const followup = bubble.querySelector('.assistant-followup') as HTMLElement;
    for (const el of [bubble, reply, source, followup]) {
      expect(el).toBeTruthy();
      expect(el.style.width).toBe('');
      expect(el.style.minWidth).toBe('');
      expect(el.style.whiteSpace).toBe('');
    }
    // the long question archived as a user bubble wraps too
    await ask(getByRole, 'second');
    await waitFor(() => expect(container.querySelector('.assistant-msg-user')).not.toBeNull());
    expect((container.querySelector('.assistant-msg-user') as HTMLElement).style.width).toBe('');
  });

  it('CSS SOURCE: every new text carrier declares wrapping and a zero min-width floor', () => {
    expect(assistantCss.length).toBeGreaterThan(0);
    for (const sel of ['.assistant-answer', '.assistant-memory', '.assistant-followups-eyebrow']) {
      const body = ruleBody(assistantCss, sel);
      expect(body.length, `${sel} must declare a rule`).toBeGreaterThan(0);
      expect(body, `${sel} must wrap long content`).toMatch(/overflow-wrap:\s*anywhere/);
    }
    for (const sel of ['.assistant-answer', '.assistant-memory', '.assistant-head-titles']) {
      expect(ruleBody(assistantCss, sel), `${sel} must allow flex shrink`).toMatch(
        /min-width:\s*0/,
      );
    }
    // the bubble is bounded by its container, never wider
    expect(ruleBody(assistantCss, '.assistant-answer')).toMatch(/max-width:\s*100%/);
  });

  it('CSS SOURCE: the assistant bubble is a full four-sided border on a lavender tint — never a coloured accent edge', () => {
    const bubble = ruleBody(assistantCss, '.assistant-msg-assistant');
    expect(bubble.length).toBeGreaterThan(0);
    // ONE full `border:` shorthand (the permanent no-vertical-rail rule)
    expect(bubble).toMatch(/(^|\n)\s*border:\s*1px solid var\(--assist-border\);/);
    expect(bubble).not.toMatch(/border-(left|right)/);
    // a genuinely visible surface: the conversation region is WHITE (--surface),
    // so the bubble must NOT be --surface or it would be invisible (R2).
    expect(bubble).toMatch(/background:\s*var\(--assist-panel-bg\)/);
    expect(bubble).not.toMatch(/background:\s*var\(--surface\)\s*;/);
    // it is left-aligned, not stretched edge-to-edge
    expect(bubble).toMatch(/align-self:\s*flex-start/);
    // …and the live bubble shares that exact rule (one selector list, one look)
    const re = new RegExp(
      '\\.assistant-msg-assistant\\s*,\\s*\\.assistant-answer\\s*\\{',
      'm',
    );
    expect(assistantCss).toMatch(re);
  });

  it('CSS SOURCE: the advisory footer keeps its hair divider + secondary colour and is italicised', () => {
    const caption = ruleBody(assistantCss, '.assistant-caption');
    expect(caption).toMatch(/border-top:\s*1px solid var\(--border-hair\)/);
    expect(caption).toMatch(/font-style:\s*italic/);
    expect(caption).toMatch(/color:\s*var\(--text-secondary\)/);
    expect(caption).toMatch(/font-size:\s*11px/);
  });

  it('CSS SOURCE: the head, the empty divider and the Agent Actions group never absorb the bounded column', () => {
    for (const sel of ['.assistant-head', '.assistant-empty-divider', '.assistant-agent-actions', '.assistant-more', '.assistant-foot']) {
      expect(ruleBody(assistantCss, sel), `${sel} must not absorb the column`).toMatch(
        /flex:\s*none/,
      );
    }
    // and no fixed height was introduced anywhere that could truncate content
    expect(assistantCss).not.toMatch(/\.assistant-answer[^{]*\{[^}]*\bheight:\s*\d/);
    expect(ruleBody(assistantCss, '.assistant-answer')).not.toMatch(/max-height/);
  });
});
