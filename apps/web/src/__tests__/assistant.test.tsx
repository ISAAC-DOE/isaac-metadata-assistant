import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import {
  COMPOSER_GUIDED_HELPER,
  GUIDED_ONLY_NOTE,
  MEMORY_UNAVAILABLE_CAVEAT,
  hasVerdictLanguage,
} from '../lib/assistant';
import { compose } from '../lib/assistantComposer';
import {
  experimentDetail,
  pendingResponse,
  validateDryRun,
  auditNotExported,
  warningsDryRun,
  evidenceResponse,
  evidenceExported,
  artifactsNull,
  graphStatusUnavailable,
} from '../test/apiFixtures';
import type { GroundingState, RecordBundle, EvidenceBundle } from '../lib/types';

/*
 * P25.9: ASSISTANT_SAMPLES (the static per-screen sample table) was retired as
 * dead code — no screen imports it; every mounting screen grounds its reply +
 * prompts via `compose()` (assistantComposer.ts) over already-fetched bundle
 * data. These tests exercise `AssistantPanel` against real `compose()` output
 * (built from the same shape-faithful API fixtures assistantComposer.test.ts /
 * memory-composer.test.ts use), not a hand-authored static table.
 */

// A shape-faithful review bundle — same fixture shape as
// assistantComposer.test.ts's reviewState(). Only pending/validate/evidence are
// read by the review composer.
function reviewState(overrides: Partial<RecordBundle> = {}): GroundingState {
  const base = {
    detail: experimentDetail,
    pending: pendingResponse.pending,
    validate: validateDryRun,
    audit: auditNotExported,
    warnings: warningsDryRun,
    evidence: evidenceResponse.evidence,
    graph: graphStatusUnavailable,
  } as unknown as RecordBundle;
  return { context: 'review', bundle: { ...base, ...overrides } };
}

// A shape-faithful evidence bundle — same fixture shape as
// assistantComposer.test.ts's evidenceState(). With no `selectedPath`, the
// leading (files-sourced) chip is "Select a field…" guidance.
function evidenceState(overrides: Partial<EvidenceBundle> = {}): GroundingState {
  const base = {
    detail: experimentDetail,
    evidence: evidenceExported.evidence,
    artifacts: artifactsNull,
    graph: graphStatusUnavailable,
    sourcePreviews: {},
  } as unknown as EvidenceBundle;
  return { context: 'evidence', bundle: { ...base, ...overrides } };
}

const reviewOut = () => compose(reviewState());
const evidenceOut = () => compose(evidenceState());

describe('AssistantPanel is subordinate and never renders a verdict', () => {
  it('renders subordinate copy with a source label and a memory freshness dot', () => {
    const out = evidenceOut();
    const { container, getByText, queryByText } = render(
      <AssistantPanel reply={out.reply} prompts={out.prompts} availability="available" />,
    );
    // every reply names its source — rendered as the friendly Title-Case label,
    // never the raw machine enum (P25.1). The evidence panel's leading chip
    // (no field selected yet) is answeredFrom 'files'.
    expect(getByText(/answered from:/)).toBeInTheDocument();
    expect(getByText('answered from: Evidence & Sources')).toBeInTheDocument();
    expect(queryByText('answered from: files')).toBeNull();
    // P33 HQA#6: the memory-head is the Title-Case state label (no "memory:" colon).
    expect(getByText('Memory Available')).toBeInTheDocument();
    expect(container.querySelector('.assistant-memory')).not.toBeNull();
    // indigo assistant surface, never a verdict class
    expect(container.querySelector('.assistant')).not.toBeNull();
    expect(container.querySelector('.verdict-pass')).toBeNull();
    expect(container.querySelector('.verdict-fail')).toBeNull();
  });

  it('unavailable memory renders the approved quiet caveat; available memory renders none', () => {
    const out = evidenceOut();
    const unavailable = render(
      <AssistantPanel reply={out.reply} prompts={out.prompts} availability="unavailable" />,
    );
    // P25.7 replaced the FALSE "…answered from source files directly" wording:
    // the assistant performs no source lookup. The approved caveat is the
    // MEMORY_UNAVAILABLE_CAVEAT string, and the retired wording must be gone.
    expect(unavailable.getByText(MEMORY_UNAVAILABLE_CAVEAT)).toBeInTheDocument();
    expect(unavailable.queryByText(/answered from source files directly/i)).toBeNull();
    unavailable.unmount();

    const available = render(
      <AssistantPanel reply={out.reply} prompts={out.prompts} availability="available" />,
    );
    expect(available.queryByText(MEMORY_UNAVAILABLE_CAVEAT)).toBeNull();
  });

  it('omitting `availability` renders NO memory head line and NO caveat (P25.7)', () => {
    // A memory-less screen (e.g. Guided Completion) passes no availability, so
    // the panel must make no memory claim at all — neither the `memory:` head
    // line nor any caveat.
    const out = evidenceOut();
    const { container, queryByText } = render(
      <AssistantPanel reply={out.reply} prompts={out.prompts} />,
    );
    expect(queryByText(/^memory:/i)).toBeNull();
    expect(container.querySelector('.assistant-memory')).toBeNull();
    expect(container.querySelector('.assistant-caveat')).toBeNull();
    expect(queryByText(MEMORY_UNAVAILABLE_CAVEAT)).toBeNull();
    // the accurate `answered from:` provenance line is still the source claim
    expect(queryByText(/answered from:/)).toBeInTheDocument();
  });

  it('contains no PASS/FAIL strings', () => {
    const out = reviewOut();
    const { container } = render(
      <AssistantPanel
        reply={out.reply}
        prompts={out.prompts}
        availability="available"
        note="Truth questions route to the CLI — the assistant never renders a verdict."
      />,
    );
    expect(container.textContent).not.toMatch(/\bPASS\b/);
    expect(container.textContent).not.toMatch(/\bFAIL\b/);
  });

  it('the verdict-language guard replaces any reply that would state a verdict', () => {
    const { container } = render(
      <AssistantPanel
        reply={{ text: 'This record is PASS against the schema.', answeredFrom: 'schema' }}
        prompts={[]}
        availability="available"
      />,
    );
    expect(container.textContent).not.toMatch(/\bPASS\b/);
    expect(container.textContent).toMatch(/truth question/i);
  });
});

describe('hasVerdictLanguage — the structural guard the panel runs over every composed string', () => {
  it('detects reserved verdict wording', () => {
    expect(hasVerdictLanguage('the record is PASS')).toBe(true);
    expect(hasVerdictLanguage('FAIL against schema')).toBe(true);
    expect(hasVerdictLanguage('the beamline came from the sheet')).toBe(false);
  });

  // The no-verdict guarantee over EVERY composed string (all five contexts,
  // many bundle-state permutations) is enforced exhaustively in
  // `lib/assistantComposer.test.ts` ("no-verdict guarantee across every
  // composed string", per review/export/evidence/complete context) and
  // `__tests__/memory-composer.test.ts` ("guard cleanliness sweep over EVERY
  // composed string", memory context). This is a lightweight smoke check that
  // the guard also holds for the review/evidence outputs this file renders.
  it('no reply/prompt/answer text from the review or evidence compose() output states a verdict', () => {
    for (const out of [reviewOut(), evidenceOut()]) {
      const strings = [out.reply.text, ...out.prompts.flatMap((p) => [p.text, p.answer?.text ?? ''])];
      for (const s of strings) {
        expect(hasVerdictLanguage(s)).toBe(false);
      }
    }
  });
});

describe('assistant final placeholder form: guided prompts + source-labeled answers', () => {
  it('clicking a guided prompt shows its composed answer', () => {
    const out = evidenceOut();
    const sidecarPrompt = out.prompts.find((p) => p.text === 'What is the evidence sidecar?')!;
    const { getByText } = render(
      <AssistantPanel reply={out.reply} prompts={out.prompts} availability="available" />,
    );
    // guided prompts are primary; clicking one swaps in its composed answer
    fireEvent.click(getByText(sidecarPrompt.text));
    expect(
      getByText(/ISAAC assistant convention, not part of the official ISAAC schema/),
    ).toBeInTheDocument();
  });

  it('is honestly guided-first: an inert visual-only composer (SECONDARY send) with a persistent guided-only helper; the standalone guided-note is de-duped and the subordinate caption is the single advisory footer', () => {
    const out = evidenceOut();
    const { getByRole, getByText, queryByText, getByLabelText } = render(
      <AssistantPanel reply={out.reply} prompts={out.prompts} availability="available" />,
    );
    // P33 S2 (D3/C3): the panel now shows an HONEST visual-only composer — a real
    // labelled text input plus a SECONDARY-styled send control (never the primary
    // action), with the persistent guided-only helper visible before interaction.
    const box = getByRole('textbox');
    expect(box).toBeInTheDocument();
    expect(getByLabelText(/ask the assistant/i)).toBe(box);
    const send = getByRole('button', { name: /send/i });
    expect(send.className).toMatch(/btn-secondary/);
    expect(send.className).not.toMatch(/btn-primary/); // never styled as the primary action
    // the persistent guided-only helper states the limitation up front …
    expect(getByText(COMPOSER_GUIDED_HELPER)).toBeInTheDocument();
    // … and the now-redundant standalone guided-note is de-duped away.
    expect(queryByText(GUIDED_ONLY_NOTE)).toBeNull();
    // subordinate-to-deterministic-validation caption remains the single footer
    expect(getByText(/advisory — it explains/i)).toBeInTheDocument();
    expect(getByText(/never validates/i)).toBeInTheDocument();
  });

  it('prompt chips remain keyboard-accessible real buttons', () => {
    const out = evidenceOut();
    const { getAllByRole } = render(
      <AssistantPanel reply={out.reply} prompts={out.prompts} availability="available" />,
    );
    const buttons = getAllByRole('button');
    // every clickable prompt chip is a real <button>, focusable/clickable —
    // the only input surface the assistant offers.
    expect(buttons.length).toBeGreaterThan(0);
    for (const chip of buttons) {
      expect(chip.tagName).toBe('BUTTON');
      if (!chip.hasAttribute('disabled')) {
        chip.focus();
        expect(chip).toHaveFocus();
      }
    }
  });
});
