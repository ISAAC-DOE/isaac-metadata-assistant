/*
 * P29.6 — Agent Actionability Closure: the VISIBLE staging trigger (TEST-FIRST,
 * authored RED before the "Stage Answer" affordance is wired into AssistantPanel).
 *
 * This is the gap P29.6 closes: the confirm/mutate machinery (P29.3
 * confirmProposal, P29.4b ProposalCard + Confirm/Cancel) already existed, but the
 * hosted user had NO visible way to STAGE an answer through the assistant. The
 * trigger reuses GuidedPrompt's "Use This Suggestion" value entry — a single
 * button that stages the labeled synthetic value for the CURRENT pending field —
 * so the assistant stays guided-prompts-only (NO freeform chat composer: no
 * textbox, no textarea, no send button). These tests exercise it:
 *   - a "Stage Answer" trigger appears for the current pending field only;
 *   - using it routes the suggested value through the GUARDED `proposeForField`
 *     (source:'user') into an UNCONFIRMED ProposalCard — with NO api mutation;
 *   - a staged user value is labeled user-provided and is NEVER auto-classified as
 *     evidence-supported;
 *   - Confirm writes exactly ONCE through `confirmProposal` (current version as
 *     If-Match) then refreshes; Cancel mutates nothing and restores focus;
 *   - no staging trigger when there is no current pending field / no suggested
 *     value (never a blanket write); the guarded entry refuses Unknown /
 *     conflict-auto-pick / Project Memory sources;
 *   - a nested secret in a staged value is neither rendered nor persisted;
 *   - the trigger + Confirm/Cancel are real keyboard-focusable buttons;
 *   - a stale proposal's Confirm is disabled.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { AssistantPanel, type StageFieldOption } from '../components/AssistantPanel';
import { api } from '../lib/api';
import * as agentModule from '../lib/assistantAgent';
import { proposeForField } from '../lib/assistantAgent';
import { clearAllSessions } from '../lib/assistantSession';
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
        { id: 'complete_metadata', label: 'Complete Metadata', state: 'current', current: true, reopened: false, blocked: false, reason: null },
      ],
    },
    evidence: [
      { field: 'sample.material', classification: 'supported', value_state: 'confirmed', explanation: 'Backed by observed evidence.', sources: [{ source_type: 'spreadsheet' }] },
      { field: 'sample.origin', classification: 'unknown', value_state: 'none', explanation: 'No defensible value.', sources: [] },
      { field: 'sample.mass_mg', classification: 'conflicting_evidence', value_state: 'candidate', explanation: 'Evidence asserts incompatible values.', sources: [] },
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
    answer: { text: 'Two fields still need you.', answeredFrom: 'workflow' },
  },
];

// The current pending field + its labeled synthetic suggestion (the SAME value the
// manual GuidedPrompt exposes via "Use This Suggestion").
const CURRENT_FIELD: StageFieldOption = {
  id: 'series',
  label: 'Reduced Series',
  suggestedValue: 'series-42',
  suggestedValueLabel: 'Demo answer (synthetic)',
};

function panel(extra: Record<string, unknown> = {}) {
  return render(
    <AssistantPanel
      reply={REPLY}
      prompts={PROMPTS}
      experimentId={EXP}
      recordRev={5}
      agentContext={ctx()}
      stageField={CURRENT_FIELD}
      onRefresh={vi.fn()}
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
// The visible staging trigger
// ---------------------------------------------------------------------------

describe('P29.6 the "Stage Answer" trigger appears for the current pending field', () => {
  it('renders a Stage Answer affordance naming the current pending field + its suggestion', () => {
    const { getByRole, container } = panel();
    expect(getByRole('button', { name: /stage answer/i })).not.toBeNull();
    const stage = container.querySelector('.agent-stage')!;
    expect(stage.textContent).toMatch(/Reduced Series/);
    expect(stage.textContent).toMatch(/series-42/); // the labeled synthetic suggestion
  });

  it('the STAGING affordance is a single labeled button — NOT a freeform chat composer (no input/textarea inside it)', () => {
    // P33 S2 (D3): the panel now has a separate, INERT visual-only composer, but
    // the STAGING path itself must never be a chat box — it stays a single
    // labeled "Stage Answer" button that routes only the synthetic suggestion.
    const { container } = panel();
    const stage = container.querySelector('.agent-stage') as HTMLElement;
    expect(stage).not.toBeNull();
    expect(stage.querySelector('input')).toBeNull();
    expect(stage.querySelector('textarea')).toBeNull();
    expect(stage.querySelector('button')).not.toBeNull();
    expect(stage.textContent).toMatch(/stage answer/i);
    // the panel's P33 S2 composer input is inert (visual-only) and lives OUTSIDE
    // the staging affordance — staging never routes free text through it.
    const composerInput = container.querySelector('.assistant-composer-input');
    expect(composerInput).not.toBeNull();
    expect(stage.contains(composerInput)).toBe(false);
  });

  it('renders NO staging trigger when there is no current pending field (never a blanket write)', () => {
    const { queryByRole, container } = panel({ stageField: undefined });
    expect(queryByRole('button', { name: /stage answer/i })).toBeNull();
    expect(container.querySelector('.agent-stage')).toBeNull();
  });

  it('renders NO staging trigger when the field has no synthetic suggestion (assistant never invents one)', () => {
    const { queryByRole } = panel({
      stageField: { id: 'series', label: 'Reduced Series' } as StageFieldOption,
    });
    expect(queryByRole('button', { name: /stage answer/i })).toBeNull();
  });

  it('renders NO staging trigger when the live context is degraded (manual-first, no answering)', () => {
    const { queryByRole } = panel({ degraded: true, agentContext: ctx({ degraded: true }) });
    expect(queryByRole('button', { name: /stage answer/i })).toBeNull();
  });

  it('the trigger is a real keyboard-focusable button', () => {
    const { getByRole } = panel();
    const trigger = getByRole('button', { name: /stage answer/i }) as HTMLButtonElement;
    expect(trigger.tagName).toBe('BUTTON');
    expect(trigger.disabled).toBe(false);
    trigger.focus();
    expect(trigger).toHaveFocus();
  });
});

// ---------------------------------------------------------------------------
// Staging creates an UNCONFIRMED proposal, mutating nothing
// ---------------------------------------------------------------------------

describe('P29.6 staging a value creates an UNCONFIRMED proposal (no mutation)', () => {
  it('Stage Answer renders the unconfirmed ProposalCard with NO api call', () => {
    const submit = vi.spyOn(api, 'submitAnswer');
    const edit = vi.spyOn(api, 'editField');
    const { getByRole, container } = panel();

    fireEvent.click(getByRole('button', { name: /stage answer/i }));

    const card = container.querySelector('.agent-proposal');
    expect(card).not.toBeNull();
    expect(card!.textContent).toMatch(/not changed the official record/i);
    expect(card!.textContent).toMatch(/series-42/); // the value, verbatim
    // nothing was written by staging
    expect(submit).not.toHaveBeenCalled();
    expect(edit).not.toHaveBeenCalled();
  });

  it('once staged, the staging trigger is replaced by the single proposal card (one at a time)', () => {
    const { getByRole, queryByRole, container } = panel();
    fireEvent.click(getByRole('button', { name: /stage answer/i }));
    expect(queryByRole('button', { name: /stage answer/i })).toBeNull();
    expect(container.querySelectorAll('.agent-proposal').length).toBe(1);
    expect(container.querySelector('.agent-stage')).toBeNull();
  });

  it('a staged USER value is labeled user-provided and NEVER auto-classified as evidence-supported', () => {
    // Stage on a field the evidence calls `supported`; a user selecting a value must
    // NOT inherit that classification (it is not evidence — it is a user answer).
    const { getByRole, container } = panel({
      stageField: {
        id: 'sample.material',
        label: 'Material',
        suggestedValue: 'NMC811',
        suggestedValueLabel: 'Demo answer (synthetic)',
      } as StageFieldOption,
    });
    fireEvent.click(getByRole('button', { name: /stage answer/i }));

    const card = container.querySelector('.agent-proposal')!;
    expect(card.textContent).toMatch(/user/i); // origin: user-provided
    expect(card.getAttribute('data-classification')).not.toBe('supported');
    // the "Supported" evidence chip must not appear on a raw user value
    expect(card.querySelector('.agent-proposal-class')).toBeNull();
  });

  it('staging the current field infers no ADDITIONAL field — exactly one proposal for one named field', () => {
    const { getByRole, container } = panel();
    fireEvent.click(getByRole('button', { name: /stage answer/i }));
    const cards = container.querySelectorAll('.agent-proposal');
    expect(cards.length).toBe(1);
    expect(cards[0].querySelector('.mono')?.textContent).toBe('series');
  });
});

// ---------------------------------------------------------------------------
// Confirm / Cancel reuse the existing confirmProposal path
// ---------------------------------------------------------------------------

describe('P29.6 Confirm/Cancel reuse the existing confirmProposal path', () => {
  it('Confirm routes through confirmProposal ONCE with the current version (If-Match), then onRefresh', async () => {
    const submit = vi.spyOn(api, 'submitAnswer').mockResolvedValue({ version: 'gen.6', pending: [] } as never);
    const confirmSpy = vi.spyOn(agentModule, 'confirmProposal');
    const onRefresh = vi.fn();
    const { getByRole } = panel({ onRefresh });

    fireEvent.click(getByRole('button', { name: /stage answer/i }));
    fireEvent.click(getByRole('button', { name: /^confirm$/i }));

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(submit).toHaveBeenCalledTimes(1);
    // current pending field → submitAnswer, carrying the current version as If-Match
    expect(submit.mock.calls[0][2]).toBe('gen.5');
  });

  it('no mutation happens BEFORE Confirm', () => {
    const submit = vi.spyOn(api, 'submitAnswer');
    const { getByRole } = panel();
    fireEvent.click(getByRole('button', { name: /stage answer/i }));
    expect(submit).not.toHaveBeenCalled();
  });

  it('Cancel performs no mutation, clears the proposal, and restores the staging trigger', () => {
    const submit = vi.spyOn(api, 'submitAnswer');
    const edit = vi.spyOn(api, 'editField');
    const { getByRole, container } = panel();

    fireEvent.click(getByRole('button', { name: /stage answer/i }));
    expect(container.querySelector('.agent-proposal')).not.toBeNull();
    fireEvent.click(getByRole('button', { name: /^cancel$/i }));

    expect(submit).not.toHaveBeenCalled();
    expect(edit).not.toHaveBeenCalled();
    expect(container.querySelector('.agent-proposal')).toBeNull();
    // focus is restored to the live reply (no mutation, no lost focus)
    expect(document.activeElement).toBe(container.querySelector('.assistant-reply'));
    // the staging trigger returns
    expect(getByRole('button', { name: /stage answer/i })).not.toBeNull();
  });

  it('Confirm and Cancel on the staged card are real keyboard-focusable buttons', () => {
    const { getByRole } = panel();
    fireEvent.click(getByRole('button', { name: /stage answer/i }));
    for (const name of [/^confirm$/i, /^cancel$/i]) {
      const btn = getByRole('button', { name }) as HTMLButtonElement;
      expect(btn.tagName).toBe('BUTTON');
      btn.focus();
      expect(btn).toHaveFocus();
    }
  });

  it('a stale proposal (record advanced past sourceRev) cannot be confirmed', () => {
    const submit = vi.spyOn(api, 'submitAnswer');
    // proposal staged at rev 5; live context has advanced to rev 6
    const stale: Proposal = {
      id: 'proposal-series-5-1',
      experimentId: EXP,
      field: 'series',
      value: 'series-42',
      origin: 'user-provided',
      sourceRev: 5,
      confirmationState: 'pending',
    };
    const { getByRole, container } = panel({
      proposal: stale,
      agentContext: ctx({ recordRev: 6, version: 'gen.6' }),
      recordRev: 6,
    });
    const confirm = getByRole('button', { name: /^confirm$/i }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    expect(container.querySelector('.agent-proposal')!.className).toMatch(/stale/);
    fireEvent.click(confirm);
    expect(submit).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// The guarded staging entry refuses the forbidden sources (enforced at the UI)
// ---------------------------------------------------------------------------

describe('P29.6 the staging entry is the guarded proposeForField', () => {
  it('refuses to fabricate a value for an Unknown field (candidate)', () => {
    expect(proposeForField(ctx(), { field: 'sample.origin', source: 'candidate' })).toBeNull();
  });

  it('never auto-picks a conflict winner (candidate, no explicit option)', () => {
    expect(proposeForField(ctx(), { field: 'sample.mass_mg', source: 'candidate' })).toBeNull();
  });

  it('Project Memory / graph can never propose a scientific value', () => {
    expect(proposeForField(ctx(), { field: 'series', value: 'x', source: 'memory' } as never)).toBeNull();
    expect(proposeForField(ctx(), { field: 'series', value: 'x', source: 'graph' } as never)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Leak-safe boundary on the staged-value render/persist path
// ---------------------------------------------------------------------------

describe('P29.6 a nested secret in a staged value is neither rendered nor persisted', () => {
  // Unmistakably FAKE: a >=32-char hex run of one char + a Bearer prefix trip the
  // sanitizer without being a credential-shaped token the leak-scanner would reject.
  const HEX = 'a'.repeat(40);
  const SECRET = 'Bearer NOT-A-REAL-SECRET-TOKEN-SYNTHETIC';

  it('a nested secret in the suggested value is scrubbed from the render + suggestion preview', () => {
    const { container } = panel({
      stageField: {
        id: 'series',
        label: 'Reduced Series',
        suggestedValue: { note: SECRET, hash: HEX },
        suggestedValueLabel: 'Demo answer (synthetic)',
      } as StageFieldOption,
    });
    // the trigger renders, but the secret-shaped value never reaches the DOM…
    expect(container.querySelector('.agent-stage')).not.toBeNull();
    expect(container.textContent).not.toContain(HEX);
    expect(container.textContent).not.toContain('Bearer');
  });

  it('a nested secret in a staged proposal value is not rendered or persisted after Confirm attempt', () => {
    const { getByRole, container } = panel({
      stageField: {
        id: 'series',
        label: 'Reduced Series',
        suggestedValue: { hash: HEX },
        suggestedValueLabel: 'Demo answer (synthetic)',
      } as StageFieldOption,
    });
    fireEvent.click(getByRole('button', { name: /stage answer/i }));
    expect(container.querySelector('.agent-proposal')).not.toBeNull();
    expect(container.textContent).not.toContain(HEX);
    expect(JSON.stringify(sessionStorage)).not.toContain(HEX);
  });
});
