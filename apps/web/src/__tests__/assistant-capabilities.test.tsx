/*
 * P36X — "What Can I Ask?": the Assistant's REAL, per-surface capability catalog.
 *
 * The defect this closes: the panel offered a free-form composer and 2–3 canned
 * "Suggested Questions" chips, while the backend resolver actually recognises
 * eight intent families — and the chips are a SEPARATE local catalog that never
 * reaches that resolver at all. A reader had no way to learn what the deterministic
 * resolver answers.
 *
 * The correctness hazard, and the reason most of this file exists: capability is
 * SCOPE-DEPENDENT. Project Memory submits to `answer_memory_scope`, which answers
 * `memory_lead` and refuses every record family ("This is the Project Memory
 * view…"). A flat list would advertise, on Project Memory, questions Project
 * Memory refuses. So the assertions below check the per-surface scoping and —
 * crucially — check every listed example against the REAL resolver catalogs
 * rather than a hand-copied duplicate:
 *
 *   · the query-resolver examples are matched against `_TRIGGERS` read out of
 *     `apps/api/isaac_api/assistant_query.py` at test time, so a backend catalog
 *     change breaks this test;
 *   · the graph examples are run through the REAL `classifyGraphQuestion` over a
 *     real `GraphIndex`, and must produce the intent they claim.
 *
 * (`apps/api/tests/test_assistant_capabilities_catalog.py` closes the loop from
 * the other side: it reads THIS repo's TS catalog and runs the real Python
 * `classify()` over every example.)
 *
 * Everything here is READ-ONLY: no assertion submits a question, confirms a
 * proposal, or applies anything to the graph.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { fireEvent, render, within } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import { clearAllSessions } from '../lib/assistantSession';
import {
  CAPABILITIES_BOUNDARY,
  CAPABILITIES_DRAFT_KEPT_NOTE,
  CAPABILITIES_INSERT_NOTE,
  CAPABILITIES_MEMORY_SCOPE_NOTE,
  CAPABILITIES_TRIGGER_LABEL,
  GRAPH_CAPABILITY_GROUP,
  MEMORY_CAPABILITY_GROUPS,
  RECORD_CAPABILITY_GROUPS,
  capabilityGroupsFor,
  type CapabilityGroup,
} from '../lib/assistantCapabilities';
import { buildGraphIndex, initialGraphViewState } from '../lib/graphModel';
import { classifyGraphQuestion, type AssistantGraphCapability } from '../lib/graphCommands';
import { memoryGraphAvailable } from '../test/apiFixtures';
import type { AssistantMessage, SuggestedPrompt } from '../lib/types';

const EXP = '01EXPERIMENTA0000000000000';

const REPLY: AssistantMessage = { text: 'Two fields still need you.', answeredFrom: 'workflow' };
const PROMPTS: SuggestedPrompt[] = [
  {
    text: 'What still needs me?',
    answeredFrom: 'workflow',
    answer: { text: 'Two fields still need you.', answeredFrom: 'workflow' },
  },
];

const index = buildGraphIndex(memoryGraphAvailable as never);

/** A `graphCapability` wired the same way `ProjectMemory` wires it: the real
 *  classifier over a real index. `apply` is never called by these tests. */
function graphCapability(): AssistantGraphCapability {
  return {
    classify: (question: string) =>
      classifyGraphQuestion(question, index, { state: initialGraphViewState() }),
    apply: () => {
      throw new Error('apply must never be called from the capability catalog');
    },
    provenance: 'synthetic projection',
  };
}

function panel(extra: Record<string, unknown> = {}) {
  return render(
    <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId={EXP} recordRev={5} {...extra} />,
  );
}

/** Open the control and return its trigger + panel. */
function open(extra: Record<string, unknown> = {}) {
  const view = panel(extra);
  const trigger = view.getByRole('button', { name: CAPABILITIES_TRIGGER_LABEL });
  fireEvent.click(trigger);
  const dialog = view.getByRole('dialog', { name: CAPABILITIES_TRIGGER_LABEL });
  return { ...view, trigger, dialog };
}

const headings = (dialog: HTMLElement): string[] =>
  [...dialog.querySelectorAll('.assistant-capabilities-eyebrow')].map((el) =>
    (el.textContent ?? '').trim(),
  );

const exampleButtons = (dialog: HTMLElement): HTMLElement[] =>
  [...dialog.querySelectorAll('button.assistant-capabilities-example')] as HTMLElement[];

beforeEach(() => {
  clearAllSessions();
  sessionStorage.clear();
});
afterEach(() => {
  clearAllSessions();
  sessionStorage.clear();
});

// ---------------------------------------------------------------------------
// 1 — the control: renders, opens, closes, and returns focus
// ---------------------------------------------------------------------------

describe('P36X · the What Can I Ask? control', () => {
  it('renders a closed disclosure trigger, with no catalog in the DOM until asked', () => {
    const { getByRole, queryByRole, container } = panel();
    const trigger = getByRole('button', { name: CAPABILITIES_TRIGGER_LABEL });
    expect(trigger.tagName).toBe('BUTTON');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger.getAttribute('aria-controls')).toBe('assistant-capabilities-panel');
    expect(queryByRole('dialog')).toBeNull();
    // it lives in the composer dock, never between the transcript and the composer
    expect(trigger.closest('.assistant-foot')).not.toBeNull();
    expect(trigger.closest('.assistant-body')).toBeNull();
    // and the advisory caption is still the last thing in the panel
    const foot = container.querySelector('.assistant-foot') as HTMLElement;
    expect(foot.lastElementChild).toBe(container.querySelector('.assistant-caption'));
  });

  it('opens on click, names itself with its own visible label, and moves focus into the panel', () => {
    const { trigger, dialog } = open();
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(dialog.id).toBe('assistant-capabilities-panel');
    expect(document.activeElement).toBe(dialog);
  });

  it('closes from the Close control and returns focus to the trigger', () => {
    const { trigger, dialog, queryByRole } = open();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
    expect(queryByRole('dialog')).toBeNull();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(document.activeElement).toBe(trigger);
  });

  it('closes on Escape and returns focus to the trigger', () => {
    const { trigger, dialog, queryByRole } = open();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('is fully keyboard-operable: the trigger toggles, and every control is a focusable button', () => {
    const { trigger, dialog, queryByRole } = open();
    // a real <button> is activated by Enter/Space natively; toggling it again closes
    for (const control of [
      ...exampleButtons(dialog),
      within(dialog).getByRole('button', { name: 'Close' }),
    ]) {
      expect(control.tagName).toBe('BUTTON');
      expect(control).not.toBeDisabled();
      (control as HTMLButtonElement).focus();
      expect(control).toHaveFocus();
    }
    fireEvent.click(trigger);
    expect(queryByRole('dialog')).toBeNull();
    // a second activation re-opens it
    fireEvent.click(trigger);
    expect(queryByRole('dialog', { name: CAPABILITIES_TRIGGER_LABEL })).not.toBeNull();
  });

  it('states the bounded-catalog boundary in the panel itself, not behind a further disclosure', () => {
    const { dialog } = open();
    const boundary = within(dialog).getByText(CAPABILITIES_BOUNDARY);
    expect(boundary.closest('details')).toBeNull();
    // and not inside the scroll region either — it must be readable without
    // scrolling, as a caveat that has to be scrolled to is a caveat half-given
    expect(boundary.closest('.assistant-capabilities-list')).toBeNull();
    // never a verdict
    expect(dialog.textContent).not.toMatch(/\b(PASS|FAIL)\b/);
  });

  /*
   * The forbidden-copy guard, widened after review. The shipped strings were
   * clean, but the guard was not: it tested `'ai '` (missing "AI-powered" and a
   * sentence-final "AI."), `'understands'` (missing "understand" / "understanding"),
   * and said nothing at all about `model`, `intelligen`, `reason`, `natural
   * language`, `generative` or `learn`. Stems and word boundaries, so a regression
   * in any inflection is caught rather than the one spelling that existed.
   */
  const FORBIDDEN_COPY: readonly RegExp[] = [
    /\bA\.?I\b/i,
    /\bLLM\b/i,
    /language model/i,
    /natural language/i,
    /\bmodel/i,
    /intelligen/i,
    /generative/i,
    /\breason/i,
    /\blearn/i,
    /understand/i,
    /\bchatbot/i,
    /anything you want/i,
    /ask me anything/i,
  ];

  it('implies no model, no intelligence and no learning, on any surface', () => {
    // every surface's copy, including the graph group and the memory-scope note
    for (const extra of [
      {},
      { queryScope: 'memory' },
      { queryScope: 'memory', graphCapability: graphCapability() },
    ]) {
      const view = open(extra);
      const text = view.dialog.textContent ?? '';
      for (const forbidden of FORBIDDEN_COPY) {
        expect(text, `capability copy implies more than it is: ${forbidden}`).not.toMatch(forbidden);
      }
      view.unmount();
    }
    // the draft-kept variant is copy too, and is only rendered with a draft present
    const view = panel();
    fireEvent.change(view.getByRole('textbox'), { target: { value: 'half a question' } });
    fireEvent.click(view.getByRole('button', { name: CAPABILITIES_TRIGGER_LABEL }));
    const dialog = view.getByRole('dialog', { name: CAPABILITIES_TRIGGER_LABEL });
    expect(dialog.textContent).toContain(CAPABILITIES_DRAFT_KEPT_NOTE);
    for (const forbidden of FORBIDDEN_COPY) {
      expect(dialog.textContent ?? '', `${forbidden}`).not.toMatch(forbidden);
    }
  });
});

// ---------------------------------------------------------------------------
// 1b — the popover cannot be stranded open over the composer
// ---------------------------------------------------------------------------

/*
 * The review's DO-NOT-SHIP finding. The popover is non-modal (correct: it is a
 * short reference list, not a task) but it overlays the composer input, and it
 * had only two dismissal paths, both requiring focus to still be inside it:
 * `Close`, and an Escape handled by `onKeyDown` on the panel element — which React
 * delegates from that subtree, so Escape died the moment focus left. Clicking into
 * the transcript therefore left an opaque overlay over the composer with Escape
 * inert.
 *
 * Non-modality is preserved: nothing outside is inert, there is no focus trap and
 * no `aria-modal`. What is added is dismissal from outside.
 */
describe('P36X · the popover is dismissible from outside, and never strands', () => {
  it('closes on a pointerdown outside the anchor and returns focus to the trigger', () => {
    const { trigger, container, queryByRole } = open();
    const transcript = container.querySelector('.assistant-body') as HTMLElement;
    expect(transcript).not.toBeNull();
    expect(transcript.closest('.assistant-capabilities')).toBeNull();

    fireEvent.pointerDown(transcript);

    expect(queryByRole('dialog')).toBeNull();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(document.activeElement).toBe(trigger);
  });

  it('closes on Escape while focus is OUTSIDE the panel, and returns focus to the trigger', () => {
    const { trigger, getByRole, queryByRole } = open();
    // the exact stranding case: focus lands back on the composer input, which the
    // still-open overlay covers
    const box = getByRole('textbox') as HTMLInputElement;
    box.focus();
    expect(document.activeElement).toBe(box);
    expect(queryByRole('dialog')).not.toBeNull();

    fireEvent.keyDown(box, { key: 'Escape' });

    expect(queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('a pointerdown INSIDE the anchor does not dismiss it (the trigger keeps toggling once)', () => {
    const { trigger, dialog, queryByRole } = open();
    fireEvent.pointerDown(dialog);
    expect(queryByRole('dialog')).not.toBeNull();
    // and the trigger itself is inside the anchor, so its own toggle still closes
    fireEvent.pointerDown(trigger);
    fireEvent.click(trigger);
    expect(queryByRole('dialog')).toBeNull();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('removes its document listeners on close and on unmount', () => {
    // after Close, a stray Escape / outside pointerdown must not re-enter the
    // handler (nothing to close, and nothing may steal focus back to the trigger)
    const first = open();
    fireEvent.click(within(first.dialog).getByRole('button', { name: 'Close' }));
    const box = first.getByRole('textbox') as HTMLInputElement;
    box.focus();
    fireEvent.keyDown(box, { key: 'Escape' });
    fireEvent.pointerDown(document.body);
    expect(document.activeElement).toBe(box);
    first.unmount();

    // and an unmount while OPEN leaves nothing attached
    const second = open();
    second.unmount();
    expect(() => {
      fireEvent.keyDown(document.body, { key: 'Escape' });
      fireEvent.pointerDown(document.body);
    }).not.toThrow();
  });

  it('is still non-modal: no focus trap, no aria-modal, nothing outside made inert', () => {
    const { dialog, getByRole } = open();
    expect(dialog).not.toHaveAttribute('aria-modal');
    expect(dialog.getAttribute('role')).toBe('dialog');
    // Tab is NOT intercepted, and the composer outside it is still reachable
    const box = getByRole('textbox') as HTMLInputElement;
    box.focus();
    expect(document.activeElement).toBe(box);
    expect(box.closest('.assistant-capabilities')).toBeNull();
    expect(box).not.toHaveAttribute('inert');
  });
});

// ---------------------------------------------------------------------------
// 2 — choosing an example INSERTS, never submits
// ---------------------------------------------------------------------------

describe('P36X · choosing an example fills the composer and sends nothing', () => {
  it('inserts the exact text, closes the panel, focuses the composer, and issues no request', () => {
    const calls: string[] = [];
    const fetchSpy = ((...args: unknown[]) => {
      calls.push(String(args[0]));
      return Promise.reject(new Error('no request may be made'));
    }) as unknown as typeof fetch;
    const realFetch = globalThis.fetch;
    globalThis.fetch = fetchSpy;
    try {
      const { dialog, container, getByRole, queryByRole } = open();
      const first = exampleButtons(dialog)[0];
      const text = (first.querySelector('span') as HTMLElement).textContent ?? '';
      expect(text).toBe(RECORD_CAPABILITY_GROUPS[0].examples[0].text);

      fireEvent.click(first);

      const box = getByRole('textbox') as HTMLInputElement;
      expect(box.value).toBe(text);
      // NOT submitted: no live turn, no question bubble, no in-flight state
      expect(container.querySelector('.assistant-msg')).toBeNull();
      expect((container.querySelector('.assistant-reply') as HTMLElement).textContent).toBe('');
      expect(calls).toEqual([]);
      // the panel closed and focus moved to the composer, the next thing to use
      expect(queryByRole('dialog')).toBeNull();
      expect(document.activeElement).toBe(box);
    } finally {
      globalThis.fetch = realFetch;
    }
  });

  /*
   * It also never DESTROYS a draft. `setComposerText(text)` used to overwrite a
   * half-typed question with no warning — a reference list silently discarding the
   * reader's own words. The insert now applies only to an empty composer, and the
   * panel says so BEFORE the click, so declining to overwrite is predictable
   * rather than a control that appears to do nothing.
   */
  it('states the insert note on an empty composer and inserts into it', () => {
    const { dialog, getByRole } = open();
    expect(dialog.textContent).toContain(CAPABILITIES_INSERT_NOTE);
    expect(dialog.textContent).not.toContain(CAPABILITIES_DRAFT_KEPT_NOTE);
    // direction-free: the composer sits ABOVE this control in `.assistant-foot`,
    // and the popover opens upward over it, so "the box below" was simply false
    expect(CAPABILITIES_INSERT_NOTE).not.toMatch(/below|above|beneath|under/i);
    fireEvent.click(exampleButtons(dialog)[0]);
    expect((getByRole('textbox') as HTMLInputElement).value).toBe(
      RECORD_CAPABILITY_GROUPS[0].examples[0].text,
    );
  });

  it('keeps an in-progress draft, says so first, and still closes and focuses the composer', () => {
    const view = panel();
    const box = view.getByRole('textbox') as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'why is the edge field empty' } });
    fireEvent.click(view.getByRole('button', { name: CAPABILITIES_TRIGGER_LABEL }));
    const dialog = view.getByRole('dialog', { name: CAPABILITIES_TRIGGER_LABEL });

    // announced before any click, in place of the insert note
    expect(dialog.textContent).toContain(CAPABILITIES_DRAFT_KEPT_NOTE);
    expect(dialog.textContent).not.toContain(CAPABILITIES_INSERT_NOTE);

    fireEvent.click(exampleButtons(dialog)[0]);

    // the draft survived, character for character
    expect(box.value).toBe('why is the edge field empty');
    // and the click still did the two things it visibly promises
    expect(view.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(box);
  });

  it('treats a whitespace-only composer as empty', () => {
    const view = panel();
    const box = view.getByRole('textbox') as HTMLInputElement;
    fireEvent.change(box, { target: { value: '   ' } });
    fireEvent.click(view.getByRole('button', { name: CAPABILITIES_TRIGGER_LABEL }));
    const dialog = view.getByRole('dialog', { name: CAPABILITIES_TRIGGER_LABEL });
    expect(dialog.textContent).toContain(CAPABILITIES_INSERT_NOTE);
    fireEvent.click(exampleButtons(dialog)[0]);
    expect(box.value).toBe(RECORD_CAPABILITY_GROUPS[0].examples[0].text);
  });
});

// ---------------------------------------------------------------------------
// 3 — per-surface scoping
// ---------------------------------------------------------------------------

describe('P36X · the catalog lists only what the CURRENT surface supports', () => {
  const RECORD_HEADINGS = RECORD_CAPABILITY_GROUPS.map((g) => g.heading);

  it('a record surface lists the record families', () => {
    const { dialog } = open();
    expect(headings(dialog)).toEqual(RECORD_HEADINGS);
    // the record families are genuinely there, not just their headings
    expect(exampleButtons(dialog).length).toBe(
      RECORD_CAPABILITY_GROUPS.reduce((n, g) => n + g.examples.length, 0),
    );
    // no graph group without a graph capability
    expect(headings(dialog)).not.toContain(GRAPH_CAPABILITY_GROUP.heading);
  });

  it('Project Memory lists the memory family and NONE of the record families', () => {
    const { dialog } = open({ queryScope: 'memory' });
    expect(headings(dialog)).toEqual(MEMORY_CAPABILITY_GROUPS.map((g) => g.heading));
    for (const heading of RECORD_HEADINGS.filter((h) => h !== 'Project Memory')) {
      expect(headings(dialog), `${heading} is refused on this surface`).not.toContain(heading);
    }
    // the questions themselves are absent, not merely their headings
    const shown = exampleButtons(dialog).map((b) => (b.textContent ?? '').trim());
    for (const group of RECORD_CAPABILITY_GROUPS) {
      if (group.heading === 'Project Memory') continue;
      for (const example of group.examples) {
        expect(shown, `${example.text} would be refused here`).not.toContain(example.text);
      }
    }
    // and the surface's own limit is stated plainly
    expect(within(dialog).getByText(CAPABILITIES_MEMORY_SCOPE_NOTE)).toBeInTheDocument();
  });

  it('Graph Navigation appears ONLY while a graphCapability is actually wired', () => {
    const withGraph = open({ queryScope: 'memory', graphCapability: graphCapability() });
    expect(headings(withGraph.dialog)).toContain(GRAPH_CAPABILITY_GROUP.heading);
    withGraph.unmount();

    // the same surface, with the capability withdrawn (Graph tab not showing)
    const withoutGraph = open({ queryScope: 'memory' });
    expect(headings(withoutGraph.dialog)).not.toContain(GRAPH_CAPABILITY_GROUP.heading);
    for (const example of GRAPH_CAPABILITY_GROUP.examples) {
      expect(
        (withoutGraph.dialog.textContent ?? '').includes(example.text),
        `${example.text} is not intercepted without a graph capability`,
      ).toBe(false);
    }
    // this is still a memory surface, so its own scope limit is stated regardless
    expect(withoutGraph.dialog.textContent).toContain(CAPABILITIES_MEMORY_SCOPE_NOTE);
    withoutGraph.unmount();
    const record = open();
    // the memory-scope note is not shown on a record surface, either
    expect(record.dialog.textContent).not.toContain(CAPABILITIES_MEMORY_SCOPE_NOTE);
  });

  it('the selector itself is a pure function of the two facts the panel knows', () => {
    expect(capabilityGroupsFor('record')).toEqual(RECORD_CAPABILITY_GROUPS);
    expect(capabilityGroupsFor('memory')).toEqual(MEMORY_CAPABILITY_GROUPS);
    expect(capabilityGroupsFor('memory', { graph: true })).toEqual([
      ...MEMORY_CAPABILITY_GROUPS,
      GRAPH_CAPABILITY_GROUP,
    ]);
    // every group carries at least one example — a heading with no backing
    // question is never rendered
    for (const scope of ['record', 'memory'] as const) {
      for (const group of capabilityGroupsFor(scope, { graph: true })) {
        expect(group.examples.length, `${group.heading} has no example`).toBeGreaterThan(0);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// 4 — every listed example routes, checked against the REAL resolver catalogs
// ---------------------------------------------------------------------------

const HERE = dirname(fileURLToPath(import.meta.url));
const RESOLVER_SOURCE = readFileSync(
  resolve(HERE, '../../../api/isaac_api/assistant_query.py'),
  'utf8',
);

/**
 * The backend's `_TRIGGERS` table, read out of the Python source at test time —
 * NOT a copy maintained here. A renamed intent or a deleted trigger phrase
 * therefore fails this test instead of silently leaving a dead example on screen.
 */
function backendTriggers(): Map<string, string[]> {
  const block = /_TRIGGERS: dict\[str, tuple\[str, \.\.\.\]\] = \{([\s\S]*?)\n\}\n/.exec(
    RESOLVER_SOURCE,
  );
  expect(block, '_TRIGGERS was not found in assistant_query.py').not.toBeNull();
  const constants = new Map<string, string>();
  for (const m of RESOLVER_SOURCE.matchAll(/^([A-Z_]+) = "([a-z_]+)"$/gm)) {
    constants.set(m[1], m[2]);
  }
  const table = new Map<string, string[]>();
  // Each entry is `CONSTANT: ( "phrase", "phrase", … ),`
  for (const entry of block![1].matchAll(/([A-Z_]+):\s*\(([\s\S]*?)\n {4}\),/g)) {
    const intent = constants.get(entry[1]);
    expect(intent, `${entry[1]} is not an intent constant`).toBeTruthy();
    table.set(
      intent!,
      [...entry[2].matchAll(/"([^"]+)"/g)].map((m) => m[1]),
    );
  }
  return table;
}

/** The resolver's own normalization, as `assistant_query.normalize` performs it. */
function normalize(question: string): string {
  return question
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/^[ \t\r\n.?!,;:"'`()[\]{}]+|[ \t\r\n.?!,;:"'`()[\]{}]+$/g, '');
}

describe('P36X · every listed example routes to the family it is listed under', () => {
  const triggers = backendTriggers();
  const allGroups: CapabilityGroup[] = [
    ...RECORD_CAPABILITY_GROUPS,
    ...MEMORY_CAPABILITY_GROUPS,
    GRAPH_CAPABILITY_GROUP,
  ];

  it('the backend catalog was really read (all eight families, with phrases)', () => {
    expect([...triggers.keys()].sort()).toEqual(
      [
        'evidence_summary',
        'export_blockers',
        'export_readiness',
        'field_provenance',
        'memory_lead',
        'pending_fields',
        'record_summary',
        'workflow_step',
      ].sort(),
    );
    for (const [intent, phrases] of triggers) {
      expect(phrases.length, `${intent} has no trigger phrases`).toBeGreaterThan(0);
    }
  });

  it('every query-resolver example contains a real trigger phrase of its own intent, and no rival scores higher', () => {
    const score = (normalized: string, intent: string) =>
      (triggers.get(intent) ?? []).filter((p) => normalized.includes(p)).length;

    for (const group of allGroups) {
      if (group.resolvedBy !== 'query-resolver') continue;
      for (const example of group.examples) {
        const normalized = normalize(example.text);
        const own = score(normalized, example.intent);
        expect(own, `"${example.text}" matches no ${example.intent} trigger`).toBeGreaterThan(0);
        for (const rival of triggers.keys()) {
          if (rival === example.intent) continue;
          // A rival family must not out-score the advertised one. (`record_summary`
          // is the resolver's catch-all and yields on a tie, so an equal score
          // against it is still correct.)
          const rivalScore = score(normalized, rival);
          /*
           * Exactly the two ties `_resolve_tie` actually resolves, no wider:
           *   · `record_summary` is the sole member of `_GENERAL_INTENTS`, and a
           *     catch-all always yields to a specific intent; and
           *   · the ONE specific precedence pair, `_EXPORT_PAIR` — blockers over
           *     readiness. Any other tie between distinct specific intents returns
           *     AMBIGUOUS, so permitting "any rival may tie an export_blockers
           *     example" (as this guard used to) would have accepted a catalog
           *     entry the resolver refuses.
           */
          const allowedTie =
            rival === 'record_summary' ||
            (example.intent === 'export_blockers' && rival === 'export_readiness');
          expect(
            allowedTie ? rivalScore <= own : rivalScore < own,
            `"${example.text}" scores ${rivalScore} for ${rival} vs ${own} for ${example.intent}`,
          ).toBe(true);
        }
      }
    }
  });

  it('every graph example is recognised by the REAL graph classifier as the intent it claims', () => {
    for (const example of GRAPH_CAPABILITY_GROUP.examples) {
      const proposal = classifyGraphQuestion(example.text, index, {
        state: initialGraphViewState(),
      });
      expect(proposal, `"${example.text}" is not recognised as a graph question`).not.toBeNull();
      expect(proposal!.intent).toBe(example.intent);
      // recognised AND resolvable — a listed example must not resolve to nothing
      expect(proposal!.status).toBe('ready');
      expect(proposal!.actions.length).toBeGreaterThan(0);
    }
  });

  it('no example is a duplicate, and none is a wall of prose', () => {
    const seen = new Set<string>();
    for (const group of [...RECORD_CAPABILITY_GROUPS, GRAPH_CAPABILITY_GROUP]) {
      for (const example of group.examples) {
        expect(seen.has(example.text), `${example.text} is listed twice`).toBe(false);
        seen.add(example.text);
        expect(example.text.length, example.text).toBeLessThan(70);
      }
    }
  });

  /*
   * CONCISION, measured on the LARGEST surface. The guard used to bound the
   * memory+graph surface — 2 groups / 5 examples, ~507 characters — at 900, i.e.
   * 78% headroom, while leaving the RECORD surface (6 groups / 10 examples, the
   * biggest and the one most readers see) unbounded. It now measures the record
   * surface — 579 characters shipped — at 700, in the shape the sibling
   * `graph-help-concision.test.tsx` established: a ceiling, a ratio (the two
   * standing sentences are 184 of those 579, bounded at 40%), and per-row caps.
   *
   * As there, jsdom computes no layout, so none of this proves what fits on a
   * screen. It holds the shape that makes a compact popover possible.
   */
  it('stays a compact catalog on the largest surface, not a document', () => {
    const flat = (el: HTMLElement) => (el.textContent ?? '').replace(/\s+/g, ' ').trim();

    const record = open();
    const whole = flat(record.dialog);
    expect(whole.length, whole).toBeLessThan(700);

    // MOSTLY CATALOG, not prose: the two standing sentences (insert note +
    // boundary) stay a minority of the panel's text.
    const prose = [...record.dialog.querySelectorAll('.assistant-capabilities-note, .assistant-capabilities-boundary')]
      .map((p) => flat(p as HTMLElement))
      .join(' ');
    expect(prose.length).toBeGreaterThan(0);
    expect(
      prose.length,
      `prose=${prose.length} of whole=${whole.length}`,
    ).toBeLessThan(whole.length * 0.4);

    // per-row caps: every example row is a question, never a paragraph, and every
    // group heading is a short label
    const rows = exampleButtons(record.dialog);
    expect(rows.length).toBeGreaterThan(8);
    for (const row of rows) expect(flat(row).length, flat(row)).toBeLessThan(70);
    for (const heading of headings(record.dialog)) expect(heading.length).toBeLessThan(40);
    // and no single paragraph is a wall
    for (const p of [...record.dialog.querySelectorAll('p')]) {
      expect(flat(p as HTMLElement).length, flat(p as HTMLElement)).toBeLessThan(200);
    }
    record.unmount();

    // the other surfaces are smaller, and stay under the same ceiling
    for (const extra of [
      { queryScope: 'memory' },
      { queryScope: 'memory', graphCapability: graphCapability() },
    ]) {
      const view = open(extra);
      expect(flat(view.dialog).length).toBeLessThan(700);
      view.unmount();
    }
  });
});

// ---------------------------------------------------------------------------
// 5 — the clip mitigation: content order, and the styling the caveat rests on
// ---------------------------------------------------------------------------

/*
 * A MITIGATION, not a proof. The popover opens upward from a dock that, in the
 * empty-conversation state, can sit near the top of a content-sized rail; its top
 * edge is what an ancestor `.screen-card { overflow: hidden }` would clip, and a
 * clip there is outside this popover's own scrollport, so clipped content cannot
 * be scrolled back. jsdom computes NO layout, so nothing here can show whether the
 * popover fits — that is a human browser check. What is asserted is the structure
 * the mitigation consists of: the scroll region is the group list, and the two
 * honesty-critical sentences sit below it, outside the scroll region, nearest the
 * trigger.
 */
describe('P36X · the honesty copy is the clip-resistant part of the popover', () => {
  const css = Object.values(
    import.meta.glob('../components/assistant.css', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>,
  )[0];

  it('scrolls the catalog, not the panel, and puts both sentences after it', () => {
    const { dialog } = open();
    const list = dialog.querySelector('.assistant-capabilities-list') as HTMLElement;
    expect(list).not.toBeNull();
    // every group is inside the scroll region…
    const groups = [...dialog.querySelectorAll('.assistant-capabilities-group')];
    expect(groups.length).toBe(RECORD_CAPABILITY_GROUPS.length);
    for (const group of groups) expect(list.contains(group)).toBe(true);
    // …and neither sentence is
    const note = within(dialog).getByText(CAPABILITIES_INSERT_NOTE);
    const boundary = within(dialog).getByText(CAPABILITIES_BOUNDARY);
    for (const p of [note, boundary]) expect(list.contains(p)).toBe(false);
    // order in the panel: catalog, then the sentences, then Close nearest the trigger
    const order = [...dialog.children];
    expect(order.indexOf(list)).toBeLessThan(order.indexOf(note));
    expect(order.indexOf(note)).toBeLessThan(order.indexOf(boundary));
    expect(order.indexOf(boundary)).toBeLessThan(
      order.indexOf(within(dialog).getByRole('button', { name: 'Close' })),
    );
  });

  it('bounds the popover and gives the scroll region the rules it depends on', () => {
    // the cap was lowered from 46vh to reduce how far the panel reaches upward
    const panelRule = /\.assistant-capabilities-panel \{([^}]*)\}/.exec(css)?.[1] ?? '';
    const cap = /max-height:\s*(\d+(?:\.\d+)?)vh/.exec(panelRule);
    expect(cap, 'the popover must stay viewport-bounded').not.toBeNull();
    expect(Number(cap![1])).toBeLessThanOrEqual(34);
    // the list is the scrollport, and can actually shrink inside the flex column
    const listRule = /\.assistant-capabilities-list \{([^}]*)\}/.exec(css)?.[1] ?? '';
    expect(listRule).toMatch(/overflow-y:\s*auto/);
    expect(listRule).toMatch(/min-height:\s*0/);
    expect(listRule).toMatch(/flex:\s*1 1 auto/);
    // no sideways scrollbar from a long example, at either level
    expect(panelRule).toMatch(/overflow-x:\s*hidden/);
    expect(listRule).toMatch(/overflow-x:\s*hidden/);
  });

  it('renders the boundary sentence at an AA-contrast token, not tertiary text', () => {
    // #78838f on the white popover surface is 3.86:1 at 11px — below AA, on the one
    // sentence that tells the reader anything outside the catalog is refused.
    const boundaryRule = /\.assistant-capabilities-boundary \{([^}]*)\}/.exec(css)?.[1] ?? '';
    expect(boundaryRule).toMatch(/color:\s*var\(--text-secondary\)/);
    expect(boundaryRule).not.toMatch(/color:\s*var\(--text-tertiary\)/);
  });
});
