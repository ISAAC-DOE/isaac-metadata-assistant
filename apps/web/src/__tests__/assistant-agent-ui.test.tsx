/*
 * P29.4b — wire the DETERMINISTIC P29.3 agent into the interactive conversation
 * panel (TEST-FIRST, authored RED before AssistantPanel is wired).
 *
 * These tests exercise the agent-in-panel contract:
 *   - a prompt pill RUNS a real intent (runIntent) against the LIVE AgentContext
 *     and appends the result to the chronological conversation (not static text);
 *   - only INTENTS-supported intents are surfaced;
 *   - an appended result is version-bound and marked stale when the record moves;
 *   - a staged proposal renders UNCONFIRMED, mutates NOTHING on display, and only
 *     an explicit Confirm writes — routed through confirmProposal (version as
 *     If-Match), never the api directly, never before confirm, never a retry/merge
 *     after a 412; Cancel mutates nothing;
 *   - a stale proposal cannot be confirmed;
 *   - inferred_candidate / unknown / conflicting classifications are honest;
 *   - a degraded context shows the honest state and answers no dataset intent
 *     while the manual (composed) UI still renders;
 *   - after a successful confirm the shared state is refreshed and a summary is
 *     appended;
 *   - keyboard a11y + focus movement;
 *   - the P29.1 leak-safe boundary is extended to the agent-result + proposal
 *     render/persist path (a nested secret is neither persisted nor rendered).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import { api } from '../lib/api';
import * as agentModule from '../lib/assistantAgent';
import { appendMessage, clearAllSessions } from '../lib/assistantSession';
import type { AgentContext, Proposal } from '../lib/assistantAgent';
import type { AssistantMessage, SuggestedPrompt } from '../lib/types';

const EXP = '01EXPERIMENTA0000000000000';

function ctx(overrides: Partial<AgentContext> = {}): AgentContext {
  return {
    experimentId: EXP,
    recordRev: 5,
    version: 'gen.5',
    workflow: {
      current_step: 'complete_metadata',
      ordered_steps: [
        { id: 'load_record', label: 'Load Record', state: 'completed', current: false, reopened: false, blocked: false, reason: null },
        { id: 'complete_metadata', label: 'Complete Metadata', state: 'current', current: true, reopened: false, blocked: false, reason: null },
        { id: 'review_export_readiness', label: 'Review Export Readiness', state: 'blocked', current: false, reopened: false, blocked: true, reason: "Complete 'Complete Metadata' first." },
      ],
    },
    evidence: [
      { field: 'sample.material', classification: 'supported', value_state: 'confirmed', explanation: 'Backed by observed evidence.', sources: [{ source_type: 'spreadsheet' }] },
      { field: 'xas.edge', classification: 'inferred_candidate', value_state: 'candidate', explanation: 'Proposed by a derivation rule; unconfirmed.', sources: [{ source_type: 'derivation' }] },
      { field: 'sample.mass_mg', classification: 'conflicting_evidence', value_state: 'candidate', explanation: 'Evidence asserts incompatible values.', sources: [{ source_type: 'user_confirmation' }, { source_type: 'user_confirmation' }] },
      { field: 'sample.origin', classification: 'unknown', value_state: 'none', explanation: 'No defensible value.', sources: [] },
    ],
    pending: [
      { id: 'series', label: 'Reduced Series' },
      { id: 'descriptor', label: 'Descriptor' },
    ],
    ...overrides,
  };
}

const REPLY: AssistantMessage = { text: 'Two fields still need you.', answeredFrom: 'workflow' };
const PROMPTS: SuggestedPrompt[] = [
  {
    text: 'What still needs me?',
    answeredFrom: 'workflow',
    answer: { text: 'Two fields still need you: Beamline, Edge.', answeredFrom: 'workflow' },
  },
];

// The default read-intent pills a screen surfaces (INTENTS-native, target-free).
const AGENT_PROMPTS = [
  { intent: 'identify_next_missing_field', label: 'Identify the Next Missing Field' },
  { intent: 'explain_current_state', label: 'Explain the Current Step' },
  { intent: 'show_inferred_candidates', label: 'Show Inferred Candidates' },
];

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

function panel(extra: Record<string, unknown> = {}) {
  return render(
    <AssistantPanel
      reply={REPLY}
      prompts={PROMPTS}
      experimentId={EXP}
      recordRev={5}
      agentContext={ctx()}
      agentPrompts={AGENT_PROMPTS}
      {...extra}
    />,
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

// ---------------------------------------------------------------------------
// Intent pills RUN the agent (not static text swap)
// ---------------------------------------------------------------------------

describe('P29.4b agent pills run real intents', () => {
  it('a pill invokes the correct intent and appends the RESULT chronologically (not static composer text)', () => {
    const { getByText, container } = panel();
    const before = container.querySelectorAll('.assistant-msg').length;

    fireEvent.click(getByText('Identify the Next Missing Field'));

    const msgs = Array.from(container.querySelectorAll('.assistant-msg'));
    expect(msgs.length).toBe(before + 1);
    const appended = msgs[msgs.length - 1];
    // The real runIntent output (the ACTUAL first pending field), not a static string.
    expect(appended.textContent).toContain('Reduced Series');
    // It is an assistant message in the log, newest at the bottom.
    expect(appended.classList.contains('assistant-msg-assistant')).toBe(true);
  });

  it('does NOT render an intent that is not in INTENTS', () => {
    const { queryByText } = panel({
      agentPrompts: [
        { intent: 'identify_next_missing_field', label: 'Identify the Next Missing Field' },
        { intent: 'delete_everything', label: 'Delete Everything' },
      ],
    });
    expect(queryByText('Identify the Next Missing Field')).not.toBeNull();
    expect(queryByText('Delete Everything')).toBeNull();
  });

  it('one activation produces exactly one appended result (one request per activation)', () => {
    const { getByText, container } = panel();
    const before = container.querySelectorAll('.assistant-msg').length;
    fireEvent.click(getByText('Explain the Current Step'));
    expect(container.querySelectorAll('.assistant-msg').length).toBe(before + 1);
  });

  it('an appended result is version-bound and marked stale once the record advances', () => {
    const { getByText, container, rerender } = panel();
    fireEvent.click(getByText('Identify the Next Missing Field'));

    // record advances: rev 5 → 6
    rerender(
      <AssistantPanel
        reply={REPLY}
        prompts={PROMPTS}
        experimentId={EXP}
        recordRev={6}
        agentContext={ctx({ recordRev: 6, version: 'gen.6' })}
        agentPrompts={AGENT_PROMPTS}
      />,
    );

    const appended = Array.from(container.querySelectorAll('.assistant-msg')).find((m) =>
      m.textContent?.includes('Reduced Series'),
    )!;
    expect(appended.classList.contains('is-stale')).toBe(true);
    expect(appended.textContent).toMatch(/earlier version/i);
  });

  it('agent pills are real keyboard-focusable buttons', () => {
    const { getByText } = panel();
    const pill = getByText('Identify the Next Missing Field').closest('button')!;
    expect(pill.tagName).toBe('BUTTON');
    expect(pill).not.toBeDisabled();
    pill.focus();
    expect(pill).toHaveFocus();
  });

  it('moves focus into the conversation after an intent runs', () => {
    const { getByText, container } = panel();
    fireEvent.click(getByText('Identify the Next Missing Field'));
    const appended = Array.from(container.querySelectorAll('.assistant-msg')).find((m) =>
      m.textContent?.includes('Reduced Series'),
    )! as HTMLElement;
    expect(appended).toHaveFocus();
  });
});

// ---------------------------------------------------------------------------
// Proposal card: UNCONFIRMED, mutation-gated, honest classifications
// ---------------------------------------------------------------------------

describe('P29.4b unconfirmed proposal card', () => {
  it('displaying a proposal performs NO api mutation', () => {
    const submit = vi.spyOn(api, 'submitAnswer');
    const edit = vi.spyOn(api, 'editField');
    const { container } = panel({ proposal: pendingProposal() });
    expect(container.querySelector('.agent-proposal')).not.toBeNull();
    expect(submit).not.toHaveBeenCalled();
    expect(edit).not.toHaveBeenCalled();
  });

  it('the card is explicitly UNCONFIRMED and states it has not changed the official record', () => {
    const { container } = panel({ proposal: pendingProposal() });
    const card = container.querySelector('.agent-proposal')!;
    expect(card.textContent).toMatch(/not changed the official record/i);
    expect(card.textContent).toMatch(/series-42/); // the user's value, verbatim
    expect(card.textContent).toMatch(/user/i); // origin
  });

  it('Confirm routes through confirmProposal ONCE with the current version, refreshes, and appends a summary', async () => {
    const submit = vi.spyOn(api, 'submitAnswer').mockResolvedValue({ version: 'gen.6', pending: [] } as never);
    const confirmSpy = vi.spyOn(agentModule, 'confirmProposal');
    const onRefresh = vi.fn();
    const { getByRole, container } = panel({ proposal: pendingProposal(), onRefresh });

    fireEvent.click(getByRole('button', { name: /^confirm$/i }));

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
    // routed through the agent's confirmProposal, not a direct api call
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    // exactly one mutation, carrying the current version as If-Match
    expect(submit).toHaveBeenCalledTimes(1);
    expect(submit.mock.calls[0][2]).toBe('gen.5');
    // a deterministic confirmed summary is appended to the conversation
    await waitFor(() =>
      expect(
        Array.from(container.querySelectorAll('.assistant-msg')).some((m) =>
          /confirmed/i.test(m.textContent ?? ''),
        ),
      ).toBe(true),
    );
  });

  it('a double Confirm click results in exactly ONE api call (no double-submit)', async () => {
    const submit = vi.spyOn(api, 'submitAnswer').mockResolvedValue({ version: 'gen.6', pending: [] } as never);
    const { getByRole } = panel({ proposal: pendingProposal(), onRefresh: vi.fn() });
    const btn = getByRole('button', { name: /^confirm$/i });
    fireEvent.click(btn);
    fireEvent.click(btn);
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('a 412 stale conflict marks the proposal stale with NO retry and NO auto-merge', async () => {
    const err = Object.assign(new Error('stale'), { status: 412 });
    const submit = vi.spyOn(api, 'submitAnswer').mockRejectedValue(err);
    const onRefresh = vi.fn();
    const { getByRole, container } = panel({ proposal: pendingProposal(), onRefresh });

    fireEvent.click(getByRole('button', { name: /^confirm$/i }));

    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    // no silent retry, no auto-merge, no refresh of a write that did not land
    expect(submit).toHaveBeenCalledTimes(1);
    expect(onRefresh).not.toHaveBeenCalled();
    // the card now shows a stale state and its Confirm is disabled
    await waitFor(() => {
      const card = container.querySelector('.agent-proposal')!;
      expect(card.className).toMatch(/stale/);
    });
    const confirm = getByRole('button', { name: /^confirm$/i }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
  });

  /*
   * THE SECOND `/edit` CONSUMER, which had no test at all.
   *
   * `grep -rn "422" src/__tests__/*assistant*` returned nothing before these three.
   * `confirmProposal` catches 412 and RETHROWS, and `onConfirm` was `try`/`finally`
   * with no `catch`, so a 422 became an unhandled rejection and the reader was shown
   * nothing. Before the server refused this case the SAME input produced a 200 and this
   * panel appended `Confirmed "<field>". Your value was sent to the record…` — the fix
   * replaced a false claim with silence, and these tests are the rest of it.
   *
   * Reachable without tampering: `stageAnswer` records the reader's value verbatim with
   * no format validation, and an already-answered field routes to `editField`. Every
   * proposal below names `sample.material`, which is NOT in `ctx().pending`, so the
   * confirm goes to `editField` exactly as it does in the product.
   */
  const UNSTORABLE_422 = () =>
    Object.assign(new Error('unstorable'), {
      status: 422,
      body: { error: 'invalid_field_value', key: 'sample.material', keys: ['sample.material'] },
    });

  function msgTexts(container: HTMLElement): string[] {
    return Array.from(container.querySelectorAll('.assistant-msg')).map(
      (m) => m.textContent ?? '',
    );
  }

  it('a 422 invalid_field_value is REPORTED, says the previous value stands, and claims no success', async () => {
    const edit = vi.spyOn(api, 'editField').mockRejectedValue(UNSTORABLE_422());
    const onRefresh = vi.fn();
    const { getByRole, container } = panel({
      proposal: pendingProposal({ field: 'sample.material', value: 'CuO2' }),
      onRefresh,
    });

    fireEvent.click(getByRole('button', { name: /^confirm$/i }));

    await waitFor(() => expect(edit).toHaveBeenCalledTimes(1));
    // The reader is told something. Silence was the state this test was added to end.
    await waitFor(() =>
      expect(msgTexts(container).some((t) => /could not be confirmed/i.test(t))).toBe(true),
    );
    const note = msgTexts(container).find((t) => /could not be confirmed/i.test(t))!;
    // The claim the 422 supports, and the one a scientist needs.
    expect(note).toMatch(/nothing was written/i);
    expect(note).toMatch(/still holds the value it held before/i);
    // NOT a success. The old 200 path appended exactly this sentence.
    expect(msgTexts(container).some((t) => /Your value was sent to the record/i.test(t))).toBe(
      false,
    );
    // A refused write is not a write: nothing to refresh.
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('a non-412, non-422 failure claims NOTHING about what reached the record', async () => {
    const edit = vi
      .spyOn(api, 'editField')
      .mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    const { getByRole, container } = panel({
      proposal: pendingProposal({ field: 'sample.material', value: 'CuO2' }),
      onRefresh: vi.fn(),
    });

    fireEvent.click(getByRole('button', { name: /^confirm$/i }));

    await waitFor(() => expect(edit).toHaveBeenCalledTimes(1));
    const note = await waitFor(
      () => msgTexts(container).find((t) => /could not be confirmed/i.test(t))!,
    );
    // A 500 establishes only that the request failed. It does NOT establish that the
    // record is untouched, so this message must not say so.
    expect(note).not.toMatch(/nothing was written/i);
    expect(note).not.toMatch(/still holds the value it held before/i);
    expect(note).toMatch(/reload the record/i);
  });

  it('a 412 still marks the proposal stale — the new catch did not swallow it', async () => {
    const edit = vi
      .spyOn(api, 'editField')
      .mockRejectedValue(Object.assign(new Error('stale'), { status: 412 }));
    const { getByRole, container } = panel({
      proposal: pendingProposal({ field: 'sample.material', value: 'CuO2' }),
      onRefresh: vi.fn(),
    });

    fireEvent.click(getByRole('button', { name: /^confirm$/i }));

    await waitFor(() => expect(edit).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(container.querySelector('.agent-proposal')!.className).toMatch(/stale/),
    );
    // The 412 wording, not the new catch's wording.
    expect(msgTexts(container).some((t) => /changed since it was proposed/i.test(t))).toBe(true);
    expect(msgTexts(container).some((t) => /reload the record/i.test(t))).toBe(false);
  });

  it('Cancel performs no mutation and clears the proposal', () => {
    const submit = vi.spyOn(api, 'submitAnswer');
    const edit = vi.spyOn(api, 'editField');
    const { getByRole, container } = panel({ proposal: pendingProposal() });

    fireEvent.click(getByRole('button', { name: /^cancel$/i }));

    expect(submit).not.toHaveBeenCalled();
    expect(edit).not.toHaveBeenCalled();
    expect(container.querySelector('.agent-proposal')).toBeNull();
  });

  it('a stale proposal (record advanced past sourceRev) cannot be confirmed', () => {
    const submit = vi.spyOn(api, 'submitAnswer');
    // proposal grounded in rev 4; live context is rev 5
    const { getByRole, container } = panel({ proposal: pendingProposal({ sourceRev: 4 }) });
    const confirm = getByRole('button', { name: /^confirm$/i }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    const card = container.querySelector('.agent-proposal')!;
    expect(card.className).toMatch(/stale/);
    fireEvent.click(confirm);
    expect(submit).not.toHaveBeenCalled();
  });

  it('a proposal from a DIFFERENT experiment is never actionable', () => {
    const submit = vi.spyOn(api, 'submitAnswer');
    const { getByRole } = panel({ proposal: pendingProposal({ experimentId: 'OTHER-EXP' }) });
    const confirm = getByRole('button', { name: /^confirm$/i }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.click(confirm);
    expect(submit).not.toHaveBeenCalled();
  });

  it('an inferred_candidate proposal is visually + textually distinct and never presented as confirmed fact', () => {
    const { container } = panel({
      proposal: pendingProposal({ field: 'xas.edge', value: 'K', classification: 'inferred_candidate', explanation: 'Proposed by a derivation rule; unconfirmed.' }),
    });
    const card = container.querySelector('.agent-proposal')!;
    expect(card.getAttribute('data-classification')).toBe('inferred_candidate');
    expect(card.className).toMatch(/inferred/);
    expect(card.textContent).toMatch(/candidate|unconfirmed|not confirmed/i);
    expect(card.textContent).not.toMatch(/\bconfirmed value\b/i);
  });

  it('an unknown proposal shows NO guessed value', () => {
    const { container } = panel({
      proposal: pendingProposal({ field: 'sample.origin', value: null, classification: 'unknown', explanation: 'No defensible value.' }),
    });
    const card = container.querySelector('.agent-proposal')!;
    expect(card.getAttribute('data-classification')).toBe('unknown');
    expect(card.textContent).toMatch(/unknown|no defensible|no value/i);
    // no fabricated value in the proposed-value slot
    expect(card.querySelector('.agent-proposal-value')).toBeNull();
  });

  it('a conflicting proposal presents no winner', () => {
    const { container } = panel({
      proposal: pendingProposal({ field: 'sample.mass_mg', value: '1.0', classification: 'conflicting_evidence', explanation: 'Evidence asserts incompatible values.' }),
    });
    const card = container.querySelector('.agent-proposal')!;
    expect(card.getAttribute('data-classification')).toBe('conflicting_evidence');
    expect(card.textContent).toMatch(/no winner|both|resolve|human/i);
  });

  it('Confirm and Cancel are real keyboard-focusable buttons', () => {
    const { getByRole } = panel({ proposal: pendingProposal(), onRefresh: vi.fn() });
    for (const name of [/^confirm$/i, /^cancel$/i]) {
      const btn = getByRole('button', { name }) as HTMLButtonElement;
      expect(btn.tagName).toBe('BUTTON');
      btn.focus();
      expect(btn).toHaveFocus();
    }
  });
});

// ---------------------------------------------------------------------------
// Degraded — honest, manual-first
// ---------------------------------------------------------------------------

describe('P29.4b degraded is honest and manual-first', () => {
  it('shows the honest degraded state, disables dataset intents, but keeps the composed (manual) UI', () => {
    const { getByText, container } = panel({
      degraded: true,
      agentContext: ctx({ degraded: true }),
    });
    // honest degraded copy
    expect(container.querySelector('.assistant-degraded')?.textContent).toBe(agentModule.DEGRADED_MESSAGE);
    // dataset-specific agent pills are disabled (does not answer)
    const pill = getByText('Identify the Next Missing Field').closest('button') as HTMLButtonElement;
    expect(pill.disabled).toBe(true);
    // the composed (manual) guided prompts still render
    expect(container.querySelectorAll('.assistant-prompt').length).toBe(PROMPTS.length);
    expect(getByText('What still needs me?')).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Leak-safe boundary extended to the agent-result + proposal render/persist path
// ---------------------------------------------------------------------------

describe('P29.4b leak-safe boundary on the agent result + proposal path', () => {
  // Unmistakably-FAKE fixtures that still trip the sanitizer (a `Bearer ` prefix
  // and a >=32-char hex run of a single char) WITHOUT being a credential-shaped
  // token the repo leak-scanner would (correctly) reject in a committed file.
  const SECRET = 'Bearer NOT-A-REAL-SECRET-TOKEN-SYNTHETIC';
  const HEX = 'a'.repeat(40);

  it('a secret embedded in an intent result is neither persisted nor rendered', () => {
    // craft a context whose evidence explanation carries a secret; the read
    // intent surfaces that explanation verbatim — the panel must scrub it.
    const leaky = ctx({
      evidence: [
        { field: 'sample.origin', classification: 'unknown', value_state: 'none', explanation: `token ${HEX}`, sources: [] },
      ],
    });
    const { getByText, container } = panel({
      agentContext: leaky,
      agentPrompts: [{ intent: 'explain_unknown', label: 'Explain Unknown Fields' }],
    });
    fireEvent.click(getByText('Explain Unknown Fields'));

    expect(container.textContent).not.toContain(HEX);
    expect(JSON.stringify(sessionStorage)).not.toContain(HEX);
  });

  it('a nested secret inside a proposal value is not rendered', () => {
    const { container } = panel({
      proposal: pendingProposal({ value: { note: SECRET, hash: HEX } }),
    });
    expect(container.textContent).not.toContain('sk-');
    expect(container.textContent).not.toContain(HEX);
    expect(JSON.stringify(sessionStorage)).not.toContain(HEX);
  });
});

/*
 * THE WITHHELD-MESSAGE RENDER, WHICH NO TEST PINNED.
 *
 * An independent review deleted the entire withheld-render branch — restoring the
 * exact blank-bubble defect the fix exists to remove — and the whole frontend suite
 * still passed, 153 files / 4033 tests. Every test for that fix was storage-level:
 * they proved `textWithheld` is recorded and that no fragment is stored, and nothing
 * proved a reader is ever told. The user-visible half was unprotected.
 */
describe('a message whose text was withheld says so instead of rendering blank', () => {
  it('renders the withheld sentence, not an empty bubble', () => {
    // Seeded through the REAL store, and through the real scrubber: a text carrying a
    // 64-hex digest is exactly what `sanitize` withholds. Constructing the stored
    // shape by hand would let the test pass even if `sanitize` stopped setting the
    // flag.
    appendMessage(EXP, { role: 'user', text: `is sha256 ${'9'.repeat(64)} recorded?` });
    const view = panel();
    const bubble = view.container.querySelector('.assistant-msg-withheld');
    expect(bubble, 'the withheld branch did not render').not.toBeNull();
    expect(bubble?.textContent ?? '').toMatch(/not shown because it was not stored/);
    // THE DEFECT ASSERTION: the paragraph must not be empty, which is what it was.
    expect((bubble?.textContent ?? '').trim().length).toBeGreaterThan(20);
    // And it must not claim the live answer was affected — only the archive is.
    expect(bubble?.textContent ?? '').toMatch(/was not affected/);
  });

  it('does NOT render the withheld sentence for an ordinary message', () => {
    // The positive half: without this, always rendering the notice would satisfy the
    // assertions above and put it on every message.
    appendMessage(EXP, { role: 'user', text: 'what is the sample formula?' });
    const view = panel();
    expect(view.container.querySelector('.assistant-msg-withheld')).toBeNull();
    expect(view.container.textContent).toContain('what is the sample formula?');
  });
});
