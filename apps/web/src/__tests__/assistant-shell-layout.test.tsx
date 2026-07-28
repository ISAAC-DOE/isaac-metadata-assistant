/*
 * P36V.1 — the Assistant SHELL: internal layout contract, header row, and
 * active-conversation order.
 *
 * The measured defect this slice fixes (hosted QA, empty Assistant state): the
 * THIRD Suggested Question was hidden. The cause chain was four declarations
 * deep and every existing test passed straight through it:
 *
 *   1. `.record-right .assistant` is `max-height: calc(100vh - 110px)` —
 *      correctly viewport-bounded;
 *   2. `.assistant-body` was `flex: 1 1 auto; min-height: 0` with NO `overflow`,
 *      so it defaulted to `visible`;
 *   3. `.assistant-empty` was `flex: none` — it refused to shrink — and had no
 *      `overflow` either, so it painted straight out of the body box;
 *   4. `.assistant-foot` is `position: sticky; bottom: 0; z-index: 1` on an
 *      OPAQUE `var(--assist-tint)`, so it repainted ON TOP of the spill.
 *
 * Nothing scrolled, so the third question was not merely clipped — it was
 * unreachable. On Record Workbench the empty state also renders up to 7 Agent
 * Action pills inside that same dock, which enlarges it and worsens the squeeze.
 *
 * HONESTY ABOUT WHAT IS PROVEN HERE. jsdom applies no CSS and reports 0 for
 * every box metric, so no test in this file measures a rendered pixel. Each
 * assertion is labelled as one of two kinds:
 *   · RENDERED  — real DOM structure, order, containment, focus, events;
 *   · CSS SOURCE — the declarations exist in assistant.css (the same
 *     `import.meta.glob` idiom assistant-layout / no-vertical-rail already use).
 * The pixel proof is a browser measurement and belongs in the slice report.
 *
 * Everything exercised here is READ-ONLY: no assertion confirms a proposal, and
 * the only api calls stubbed are the read-only resolvers.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AssistantPanel } from '../components/AssistantPanel';
import { AppRoutes } from '../App';
import { api } from '../lib/api';
import { appendMessage, clearAllSessions } from '../lib/assistantSession';
import type { AgentContext } from '../lib/assistantAgent';
import {
  bundleRoutes,
  evidenceBundleRoutes,
  graphStatusAvailable,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { AssistantMessage, AssistantQueryResponse, SuggestedPrompt } from '../lib/types';

const EXP = '01EXPERIMENTA0000000000000';

const REPLY: AssistantMessage = { text: 'Two fields still need you.', answeredFrom: 'workflow' };

/** THREE suggested questions — the count the record surfaces actually render,
 *  and the count whose last entry the dock used to hide. */
const THREE_PROMPTS: SuggestedPrompt[] = [
  {
    text: 'What still needs me?',
    answeredFrom: 'workflow',
    answer: { text: 'Two fields still need you: Beamline, Edge.', answeredFrom: 'workflow' },
  },
  {
    text: 'What evidence supports this record?',
    answeredFrom: 'files',
    answer: { text: 'Three entries are cited.', answeredFrom: 'files' },
  },
  {
    text: 'What blocks export?',
    answeredFrom: 'workflow',
    answer: { text: 'Two fields block export.', answeredFrom: 'workflow' },
  },
];

/** Seven agent-action pills — the Record Workbench worst case that enlarges the
 *  dock. Only intents in the frozen INTENTS registry render. */
const SEVEN_AGENT_PROMPTS = [
  { intent: 'identify_next_missing_field', label: 'Identify the Next Missing Field' },
  { intent: 'explain_current_step', label: 'Explain the Current Step' },
  { intent: 'review_field_evidence', label: 'Review Field Evidence' },
  { intent: 'show_inferred_candidates', label: 'Show Inferred Candidates' },
  { intent: 'review_evidence_conflicts', label: 'Review Evidence Conflicts' },
  { intent: 'explain_unknown', label: 'Explain an Unknown' },
  { intent: 'summarize_record_state', label: 'Summarize the Record State' },
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
    <AssistantPanel
      reply={REPLY}
      prompts={THREE_PROMPTS}
      experimentId={EXP}
      recordRev={5}
      {...extra}
    />,
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

/** True when `a` precedes `b` in document order. */
function precedes(a: Element, b: Element): boolean {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
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
// CSS source contract
// ---------------------------------------------------------------------------

const cssFiles = import.meta.glob('../components/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** Comments stripped first — this stylesheet documents its own selectors in
 *  prose, so a naive scan would match a selector NAME in a comment. */
function loadCss(name: string): string {
  return (Object.entries(cssFiles).find(([p]) => p.endsWith(`/${name}`))?.[1] ?? '').replace(
    /\/\*[\s\S]*?\*\//g,
    '',
  );
}

const assistantCss = loadCss('assistant.css');
const drawerCss = loadCss('assistant-drawer.css');

/** The declaration body of the FIRST rule whose selector list contains `sel`. */
function ruleBody(css: string, sel: string): string {
  const re = new RegExp(`(^|[,}\\s])${sel.replace(/\./g, '\\.')}\\s*(,[^{]*)?\\{([^}]*)\\}`, 'm');
  const m = re.exec(css);
  return m ? m[3] : '';
}

// ---------------------------------------------------------------------------
// TASK 1 — the internal layout contract
// ---------------------------------------------------------------------------

describe('P36V.1 S1 · Suggested Questions are not hidden under the composer dock', () => {
  it('RENDERED: all THREE Suggested Questions render as enabled buttons inside the body, none inside the dock', () => {
    const { container } = panel({ agentContext: ctx(), agentPrompts: SEVEN_AGENT_PROMPTS });

    const body = container.querySelector('.assistant-body') as HTMLElement;
    const foot = container.querySelector('.assistant-foot') as HTMLElement;
    const empty = container.querySelector('.assistant-empty') as HTMLElement;
    expect(body).not.toBeNull();
    expect(foot).not.toBeNull();

    const pills = Array.from(container.querySelectorAll('button.assistant-prompt'));
    expect(pills.length).toBe(3);
    for (const [i, pill] of pills.entries()) {
      expect(pill.tagName, `prompt ${i} must be a real button`).toBe('BUTTON');
      expect(pill, `prompt ${i} must be activatable`).not.toBeDisabled();
      // it lives in the scrolling body, NOT in the opaque sticky dock that used
      // to paint over it
      expect(pill.closest('.assistant-empty'), `prompt ${i} must be in the empty state`).toBe(
        empty,
      );
      expect(pill.closest('.assistant-body'), `prompt ${i} must be in the body`).toBe(body);
      expect(pill.closest('.assistant-foot'), `prompt ${i} must NOT be in the dock`).toBeNull();
    }
    // each question's own text is rendered (the third one included)
    for (const p of THREE_PROMPTS) {
      expect(within(empty).getByText(p.text)).toBeInTheDocument();
    }
    // and the body is a SIBLING that precedes the dock — never nested in it
    expect(body.parentElement).toBe(foot.parentElement);
    expect(precedes(body, foot)).toBe(true);
  });

  it('RENDERED: the composer is not an overlay of the body — it is a following sibling, outside it', () => {
    const { container } = panel({ agentContext: ctx(), agentPrompts: SEVEN_AGENT_PROMPTS });
    const body = container.querySelector('.assistant-body') as HTMLElement;
    const composer = container.querySelector('.assistant-composer') as HTMLElement;

    expect(composer.closest('.assistant-body')).toBeNull();
    expect(composer.closest('.assistant-foot')).not.toBeNull();
    expect(precedes(body, composer)).toBe(true);
  });

  it('CSS SOURCE: neither the dock nor the composer is positioned out of flow over the body', () => {
    // sticky keeps the dock at the bottom of a SCROLLING ancestor; it stays in
    // normal flow, so it reserves its own space and cannot overlap a sibling.
    // absolute/fixed would take it out of flow and let it float over the body.
    const foot = ruleBody(assistantCss, '.assistant-foot');
    expect(foot).toMatch(/position:\s*sticky/);
    expect(foot).not.toMatch(/position:\s*(absolute|fixed)/);
    const composer = ruleBody(assistantCss, '.assistant-composer');
    expect(composer).not.toMatch(/position:\s*(absolute|fixed)/);
  });

  it('CSS SOURCE: the body scrolls internally, so the app does not scroll because of the Assistant', () => {
    // the rail keeps its viewport cap (the panel never stretches to the 1407px
    // main column) …
    const rail = ruleBody(assistantCss, '.record-right .assistant');
    expect(rail).toMatch(/max-height:\s*calc\(100vh\s*-\s*\d+px\)/);
    expect(rail).toMatch(/flex:\s*0 0 auto/);
    // … and the squeeze is absorbed INSIDE the panel, by the body and by the
    // conversation region — not by growing the page.
    const body = ruleBody(assistantCss, '.assistant-body');
    expect(body).toMatch(/flex:\s*1 1 auto/);
    expect(body).toMatch(/min-height:\s*0/);
    expect(body).toMatch(/overflow-y:\s*auto/);
    // scroll chaining is contained so an exhausted inner scroll does not start
    // scrolling the page behind it
    expect(body).toMatch(/overscroll-behavior:\s*contain/);
    const empty = ruleBody(assistantCss, '.assistant-empty');
    expect(empty).toMatch(/overscroll-behavior:\s*contain/);
  });

  it('CSS SOURCE: scrollbars are opt-in (`auto`), never always-on (`scroll`)', () => {
    for (const sel of [
      '.assistant-body',
      '.assistant-empty',
      '.assistant-conversation',
      '.assistant-agent-actions',
      '.assistant-more-body',
    ]) {
      const b = ruleBody(assistantCss, sel);
      expect(b.length, `${sel} must declare a rule`).toBeGreaterThan(0);
      expect(b, `${sel} must not force an always-on scrollbar`).not.toMatch(
        /overflow(-y|-x)?:\s*scroll/,
      );
      expect(b, `${sel} must scroll only when needed`).toMatch(/overflow-y:\s*auto/);
    }
  });

  it('CSS SOURCE: the ≤1024px slide-over drawer contract is preserved', () => {
    // the drawer is still a fixed, right-anchored slide-over with its own scroll;
    // the panel's internal contract is layered inside it, not instead of it
    expect(drawerCss).toMatch(/@media \(max-width: 1024px\)/);
    const p = ruleBody(drawerCss, '.assistant-drawer-panel\\[data-open\\]');
    expect(p).toMatch(/position:\s*fixed/);
    expect(p).toMatch(/overflow-y:\s*auto/);
  });
});

// ---------------------------------------------------------------------------
// TASK 2 — the header row
// ---------------------------------------------------------------------------

describe('P36V.1 S2 · header is ONE balanced row', () => {
  it('RENDERED: the LEFT group is the chat icon + "Assistant"', () => {
    const { container } = panel({ availability: 'available' });
    const head = container.querySelector('.assistant-head') as HTMLElement;
    const icon = head.querySelector('.assistant-icon') as HTMLElement;
    const label = head.querySelector('.assistant-label') as HTMLElement;

    expect(icon.querySelector('svg')).not.toBeNull();
    expect(icon.getAttribute('aria-hidden')).toBe('true'); // decorative, not named twice
    expect(label.textContent).toBe('Assistant');
    // the icon reads immediately before the title
    expect(precedes(icon, label)).toBe(true);
  });

  it('RENDERED: "Memory Available" is the RIGHT group of the SAME row, after the title', () => {
    const { container } = panel({ availability: 'available' });
    const row = container.querySelector('.assistant-head-titles') as HTMLElement;
    const label = row.querySelector('.assistant-label') as HTMLElement;
    const status = row.querySelector('.assistant-memory') as HTMLElement;

    // both groups are children of the ONE header row element
    expect(status).not.toBeNull();
    expect(label.parentElement).toBe(row);
    expect(status.parentElement).toBe(row);
    expect(precedes(label, status)).toBe(true);
    // it is a compact status, not a sentence, and never colour-only
    expect(status.textContent).toMatch(/^\s*Memory Available\s*$/);
    expect(status.querySelector('.dot-memory')).not.toBeNull();
    // it is NOT in the action row that holds Clear Conversation
    expect(status.closest('.assistant-head-right')).toBeNull();
  });

  it('CSS SOURCE: the row is horizontal, the status is pushed right, and its inner gap matches the icon↔title gap', () => {
    const head = ruleBody(assistantCss, '.assistant-head');
    const row = ruleBody(assistantCss, '.assistant-head-titles');
    const status = ruleBody(assistantCss, '.assistant-memory');

    // one row, vertically aligned, no accidental wrapping at desktop width
    expect(row).toMatch(/flex-direction:\s*row/);
    expect(row).toMatch(/align-items:\s*center/);
    expect(row).toMatch(/flex-wrap:\s*nowrap/);
    expect(head).toMatch(/align-items:\s*center/);
    // the status sits at the right edge and stays compact
    expect(status).toMatch(/margin-left:\s*auto/);
    expect(status).toMatch(/flex:\s*none/);

    // the gap INSIDE the right group must visually match the gap between the
    // chat icon and "Assistant" — which is the header's own column gap.
    const headGap = /gap:\s*(?:(\d+(?:\.\d+)?)px\s+)?(\d+(?:\.\d+)?)px/.exec(head);
    const rowGap = /gap:\s*(\d+(?:\.\d+)?)px/.exec(row);
    const statusGap = /gap:\s*(\d+(?:\.\d+)?)px/.exec(status);
    expect(headGap).not.toBeNull();
    expect(rowGap).not.toBeNull();
    expect(statusGap).not.toBeNull();
    // header column gap === row gap === the status group's internal gap
    expect(statusGap![1]).toBe(headGap![2]);
    expect(rowGap![1]).toBe(headGap![2]);
  });

  it('CSS SOURCE: stacking the header is an INTENTIONAL narrow-viewport rule, not accidental wrapping', () => {
    // default: nowrap (asserted above). The only way the two groups stack is
    // this explicit media query.
    const m = /@media\s*\(max-width:\s*\d+px\)\s*\{([\s\S]*?\.assistant-head-titles[\s\S]*?)\n\}/.exec(
      assistantCss,
    );
    expect(m, 'an intentional responsive header rule must exist').not.toBeNull();
    expect(m![1]).toMatch(/\.assistant-head-titles\s*\{[^}]*flex-wrap:\s*wrap/);
    expect(m![1]).toMatch(/\.assistant-memory\s*\{[^}]*margin-left:\s*0/);
  });
});

describe('P36V.1 S2 · per-mount availability gating is unchanged', () => {
  it('RENDERED: no `availability` ⇒ no status row and nothing fabricated', () => {
    const { container } = panel();
    expect(container.querySelector('.assistant-memory')).toBeNull();
    expect(container.querySelector('.assistant-head')!.textContent).not.toMatch(/memory/i);
  });

  it('RENDERED: `showAvailabilityStatus={false}` ⇒ the row is suppressed even though the axis is known', () => {
    const { container } = panel({ availability: 'available', showAvailabilityStatus: false });
    expect(container.querySelector('.assistant-memory')).toBeNull();
  });

  it('RENDERED: the row appears only where the mount owns the axis (default true)', () => {
    const { container } = panel({ availability: 'unavailable' });
    const row = container.querySelector('.assistant-memory') as HTMLElement;
    expect(row.textContent).toMatch(/^\s*Memory Unavailable\s*$/);
  });

  it('RENDERED: the two suppressing mounts state the axis exactly ONCE, and not in the panel', async () => {
    // P36V review finding #4: enabling the row everywhere produced two
    // conflicting accessible names for one axis. Evidence Explorer and Project
    // Memory own the visible label at PAGE level; the panel must stay silent.
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const evidence = renderAt('/record/demo/evidence');
    await evidence.findByText('Direct Fields');
    const evidencePanel = evidence.container.querySelector('.assistant') as HTMLElement;
    expect(evidencePanel.querySelector('.assistant-memory')).toBeNull();
    // singular getByText throws on a duplicate — one statement of the axis
    expect(evidence.getByText('Memory Unavailable').closest('.assistant')).toBeNull();
    evidence.unmount();

    stubFetchRoutes({ 'GET /api/graph/status': { body: graphStatusAvailable } });
    const memory = renderAt('/memory');
    await memory.findByText('Memory Available');
    const memoryPanel = memory.container.querySelector('.assistant') as HTMLElement;
    expect(memoryPanel.querySelector('.assistant-memory')).toBeNull();
    expect(memory.getByText('Memory Available').closest('.assistant')).toBeNull();
  });
});

describe('P36V.1 S2 · Clear Conversation', () => {
  it('RENDERED: hidden with no conversation, and its wrapper reserves no space', () => {
    const { container, queryByRole } = panel({ availability: 'available' });
    expect(queryByRole('button', { name: 'Clear Conversation' })).toBeNull();
    expect(container.querySelector('.assistant-clear')).toBeNull();
    const actionRow = container.querySelector('.assistant-head-right') as HTMLElement;
    expect(actionRow.children.length).toBe(0);
    // CSS SOURCE: an empty wrapper is removed from layout entirely
    expect(assistantCss).toMatch(/\.assistant-head-right:empty\s*\{\s*display:\s*none;?\s*\}/);
  });

  it('RENDERED: with a conversation it appears BENEATH the header row, never between title and status', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { container, getByRole } = panel({ availability: 'available' });
    await ask(getByRole, 'what is this record?');
    await waitFor(() => expect(container.querySelector('.assistant-clear')).not.toBeNull());

    const clear = getByRole('button', { name: 'Clear Conversation' });
    const row = container.querySelector('.assistant-head-titles') as HTMLElement;
    const status = row.querySelector('.assistant-memory') as HTMLElement;

    // the FULL label survives — never abbreviated to "Clear"
    expect(clear.textContent?.trim()).toBe('Clear Conversation');
    expect(clear.getAttribute('aria-label')).toBeNull();
    // it is in the header, in its own action row, AFTER the whole title+status row
    expect(clear.closest('.assistant-head')).not.toBeNull();
    expect(clear.closest('.assistant-head-right')).not.toBeNull();
    expect(clear.closest('.assistant-head-titles')).toBeNull();
    expect(precedes(status, clear)).toBe(true);
    // …and it precedes the transcript (never between the controls and the log)
    expect(precedes(clear, container.querySelector('.assistant-log')!)).toBe(true);
  });

  it('CSS SOURCE: the action row takes its own header line, right-aligned', () => {
    const actionRow = ruleBody(assistantCss, '.assistant-head-right');
    // `flex-basis: 100%` inside a `flex-wrap: wrap` header forces its own line
    expect(actionRow).toMatch(/flex:\s*0 0 100%/);
    expect(actionRow).toMatch(/justify-content:\s*flex-end/);
    expect(ruleBody(assistantCss, '.assistant-head')).toMatch(/flex-wrap:\s*wrap/);
  });

  it('RENDERED: Clear resets the transcript, Related Questions AND the proposed actions, then refocuses the composer', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ followups: ['What is the edge?'] }),
    );
    const submitSpy = vi.spyOn(api, 'submitAnswer');
    const editSpy = vi.spyOn(api, 'editField');
    const { container, getByRole, queryByText } = panel({
      availability: 'available',
      agentContext: ctx(),
      agentPrompts: SEVEN_AGENT_PROMPTS,
    });

    // build a conversation with an archived turn, a live answer and follow-ups
    appendMessage(EXP, { role: 'assistant', text: 'older answer', answeredFrom: 'schema' });
    await ask(getByRole, 'q one');
    await waitFor(() => expect(container.querySelector('.assistant-followup')).not.toBeNull());
    expect(container.querySelector('.assistant-conversation')).not.toBeNull();

    fireEvent.click(getByRole('button', { name: 'Clear Conversation' }));

    expect(container.querySelectorAll('.assistant-msg').length).toBe(0);
    expect(container.querySelector('.assistant-conversation')).toBeNull();
    expect(container.querySelector('.assistant-followup')).toBeNull();
    expect(queryByText('Related Questions')).toBeNull();
    expect(container.querySelector('.assistant-proposed')).toBeNull();
    expect(container.querySelector('.assistant-reply')!.textContent).toBe('');
    // the empty state is restored with all three questions back in the body
    expect(container.querySelectorAll('.assistant-empty button.assistant-prompt').length).toBe(3);
    // focus returns to the composer input (the Clear button just unmounted)
    expect(document.activeElement).toBe(getByRole('textbox'));
    // session-only: nothing was written
    expect(submitSpy).not.toHaveBeenCalled();
    expect(editSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// TASK 3 — active-conversation order + wrapping
// ---------------------------------------------------------------------------

describe('P36V.1 S5 · active conversation order and legibility', () => {
  it('RENDERED: header → Clear → transcript → composer → disclosure → advisory footer', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(answerResponse());
    const { container, getByRole } = panel({
      availability: 'available',
      agentContext: ctx(),
      agentPrompts: SEVEN_AGENT_PROMPTS,
    });
    await ask(getByRole, 'what is this record?');
    await waitFor(() => expect(container.querySelector('.assistant-conversation')).not.toBeNull());

    const row = container.querySelector('.assistant-head-titles')!;
    const clear = container.querySelector('.assistant-clear')!;
    const log = container.querySelector('.assistant-log')!;
    const composer = container.querySelector('.assistant-composer')!;
    const more = container.querySelector('details.assistant-more')!;
    const caption = container.querySelector('.assistant-caption')!;

    expect(precedes(row, clear)).toBe(true);
    expect(precedes(clear, log)).toBe(true);
    expect(precedes(log, composer)).toBe(true);
    expect(precedes(composer, more)).toBe(true);
    expect(precedes(more, caption)).toBe(true);
    // nothing sits between the transcript and the composer
    expect(container.querySelector('.assistant-body details.assistant-more')).toBeNull();
    expect(container.querySelector('.assistant-body .assistant-prompts')).toBeNull();
  });

  it('RENDERED: user and assistant turns are distinct bubbles; Source + Related Questions stay with the answer', async () => {
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ followups: ['What is the edge?'] }),
    );
    const { container, getByRole } = panel({ availability: 'available' });
    await ask(getByRole, 'what is this record?');
    await waitFor(() => expect(container.querySelector('.assistant-followups')).not.toBeNull());

    const userBubble = container.querySelector('.assistant-msg-user') as HTMLElement;
    const answer = container.querySelector('.assistant-answer') as HTMLElement;
    expect(userBubble.getAttribute('data-role')).toBe('user');
    expect(answer.getAttribute('data-role')).toBe('assistant');
    // "Source:" and "Related Questions" belong to the answer, not to the panel
    expect(answer.querySelector('.answered-from')!.textContent).toMatch(/^Source: /);
    expect(container.querySelector('.assistant-followups')!.closest('.assistant-answer')).toBe(
      answer,
    );
  });

  it('RENDERED: the Open Validator control renders as a Proposed Action, not as a chat message', async () => {
    // the action is carried by the answer; when present it must live in the
    // labelled proposed-action region above the composer.
    const withAction: SuggestedPrompt[] = [
      {
        text: 'Is this record valid?',
        answeredFrom: 'schema',
        answer: {
          text: 'That is a truth question — the deterministic check lives on its own surface.',
          answeredFrom: 'schema',
          action: {
            kind: 'open-validator',
            label: 'Open Validator',
            to: '/governance',
          },
        },
      },
    ];
    const { container, getByText } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AssistantPanel reply={REPLY} prompts={withAction} experimentId={EXP} recordRev={5} />
      </MemoryRouter>,
    );
    fireEvent.click(getByText('Is this record valid?'));

    const action = container.querySelector('[data-action="open-validator"]') as HTMLElement;
    expect(action).not.toBeNull();
    // styled as a proposed/next action card, inside the labelled region
    expect(action.classList.contains('agent-stage')).toBe(true);
    expect(action.closest('.assistant-proposed')).not.toBeNull();
    // never a chat message, never inside the transcript
    expect(action.closest('.assistant-msg')).toBeNull();
    expect(action.closest('.assistant-log')).toBeNull();
    // above the composer
    expect(precedes(action, container.querySelector('.assistant-composer')!)).toBe(true);
  });

  it('RENDERED: a very long answer and a very long path carry no inline width or nowrap', async () => {
    const LONG_PATH =
      '/records/01SYNTHTESTEXP000000000000/artifacts/' +
      'a'.repeat(180) +
      '/reduced_series_normalized_mu_vs_energy.json';
    const LONG_ANSWER = `The reduced series is recorded at ${LONG_PATH} and nothing else is claimed.`;
    vi.spyOn(api, 'askAssistant').mockResolvedValue(
      answerResponse({ answer: LONG_ANSWER, followups: [LONG_ANSWER] }),
    );
    const { container, getByRole } = panel({ availability: 'available' });
    await ask(getByRole, LONG_PATH);
    await waitFor(() =>
      expect(container.querySelector('.assistant-reply')!.textContent).toContain(LONG_PATH),
    );

    const bubble = container.querySelector('.assistant-answer') as HTMLElement;
    const carriers = [
      bubble,
      bubble.querySelector('.assistant-reply'),
      bubble.querySelector('.answered-from'),
      bubble.querySelector('.assistant-followup'),
    ] as HTMLElement[];
    for (const el of carriers) {
      expect(el).toBeTruthy();
      expect(el.style.width).toBe('');
      expect(el.style.minWidth).toBe('');
      expect(el.style.whiteSpace).toBe('');
      expect(el.style.overflowX).toBe('');
    }
  });

  it('CSS SOURCE: every carrier that can hold a long path wraps, and nothing scrolls horizontally', () => {
    for (const sel of [
      '.assistant-msg',
      '.assistant-msg-text',
      '.assistant-reply',
      '.assistant-answer',
      '.assistant-followup > span',
      '.answered-from',
      '.assistant-composer-helper',
      '.agent-stage-note',
      '.assistant-caption',
    ]) {
      expect(ruleBody(assistantCss, sel), `${sel} must wrap long content`).toMatch(
        /overflow-wrap:\s*anywhere/,
      );
    }
    // the panel and its scrollports never expose a horizontal scrollbar
    for (const sel of ['.assistant-body', '.assistant-empty', '.assistant-conversation']) {
      expect(ruleBody(assistantCss, sel)).toMatch(/overflow-x:\s*hidden/);
    }
  });
});

// ---------------------------------------------------------------------------
// Every Assistant mount still renders
// ---------------------------------------------------------------------------

describe('P36V.1 · all five Assistant mounts still render the panel shell', () => {
  const MOUNTS: Array<[string, string, string]> = [
    ['Record Workbench', '/record/demo', '5 Fields Need Your Confirmation'],
    ['Guided Completion', '/record/demo/complete', 'Answer 5 Questions to Finish This Record'],
    ['Export Readiness', '/record/demo/export', '5 fields still block export'],
  ];

  for (const [name, path, sentinel] of MOUNTS) {
    it(`RENDERED: ${name} mounts head / body / dock with the composer outside the body`, async () => {
      stubFetchRoutes({
        ...bundleRoutes('demo'),
        'GET /api/graph/status': { body: graphStatusAvailable },
      });
      const { findByText, container } = renderAt(path);
      await findByText(sentinel);

      const assistant = container.querySelector('.assistant') as HTMLElement;
      expect(assistant).not.toBeNull();
      const head = assistant.querySelector('.assistant-head')!;
      const body = assistant.querySelector('.assistant-body')!;
      const foot = assistant.querySelector('.assistant-foot')!;
      expect(precedes(head, body)).toBe(true);
      expect(precedes(body, foot)).toBe(true);
      // the title row exists; the composer is docked outside the scrolling body
      expect(
        (assistant.querySelector('.assistant-head-titles .assistant-label') as HTMLElement)
          .textContent,
      ).toBe('Assistant');
      expect(assistant.querySelector('.assistant-composer')!.closest('.assistant-body')).toBeNull();
      // every Suggested Question the screen supplies is in the body, not the dock
      const pills = assistant.querySelectorAll('button.assistant-prompt');
      expect(pills.length).toBeGreaterThan(0);
      for (const pill of pills) expect(pill.closest('.assistant-foot')).toBeNull();
    });
  }

  it('RENDERED: Evidence Explorer mounts the panel shell', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo/evidence');
    await findByText('Direct Fields');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant.querySelector('.assistant-head-titles')).not.toBeNull();
    expect(assistant.querySelector('.assistant-body')).not.toBeNull();
    expect(assistant.querySelector('.assistant-composer')!.closest('.assistant-body')).toBeNull();
  });

  it('RENDERED: Project Memory mounts the panel shell', async () => {
    stubFetchRoutes({ 'GET /api/graph/status': { body: graphStatusAvailable } });
    const { findByText, container } = renderAt('/memory');
    await findByText('Memory Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant.querySelector('.assistant-head-titles')).not.toBeNull();
    expect(assistant.querySelector('.assistant-body')).not.toBeNull();
    expect(assistant.querySelector('.assistant-composer')!.closest('.assistant-body')).toBeNull();
  });
});
