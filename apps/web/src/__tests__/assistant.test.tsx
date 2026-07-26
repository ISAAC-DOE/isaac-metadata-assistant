import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import {
  ASSISTANT_COMPOSER_HELPER,
  GUIDED_ONLY_NOTE,
  MEMORY_UNAVAILABLE_CAVEAT,
  SUBORDINATE_CAPTION,
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
  it('rests with an empty live region (no placeholder text/chrome), then a guided prompt surfaces a Title-Case source label + memory dot', () => {
    const out = evidenceOut();
    const { container, getByText, queryByText } = render(
      <AssistantPanel reply={out.reply} prompts={out.prompts} availability="available" />,
    );
    // P36.1: the resting rail's live region is mounted, aria-live, and EMPTY —
    // no placeholder text, no visible card chrome — never a fully absent element.
    expect(queryByText(/Ask a question or choose a suggested prompt\./)).toBeNull();
    const reply = container.querySelector('.assistant-reply');
    expect(reply).not.toBeNull();
    expect(reply?.getAttribute('aria-live')).toBe('polite');
    expect(reply?.textContent).toBe('');
    expect(reply?.classList.contains('assistant-reply--empty')).toBe(true);
    // clicking a guided prompt surfaces an answer whose source renders as the
    // friendly Title-Case label, never the raw machine enum (P25.1).
    fireEvent.click(getByText('What is the evidence sidecar?'));
    expect(getByText(/Source:/)).toBeInTheDocument();
    expect(queryByText(/Source: files$/)).toBeNull();
    // P36.1: the SAME live region now carries the answer text and drops the
    // empty modifier — it was never unmounted/re-mounted.
    expect(reply?.textContent).not.toBe('');
    expect(reply?.classList.contains('assistant-reply--empty')).toBe(false);
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
    const { container, getByText, queryByText } = render(
      <AssistantPanel reply={out.reply} prompts={out.prompts} />,
    );
    expect(queryByText(/^memory:/i)).toBeNull();
    expect(container.querySelector('.assistant-memory')).toBeNull();
    expect(container.querySelector('.assistant-caveat')).toBeNull();
    expect(queryByText(MEMORY_UNAVAILABLE_CAVEAT)).toBeNull();
    // after asking a guided question, the accurate `Source:` provenance shows
    fireEvent.click(getByText('What is the evidence sidecar?'));
    expect(queryByText(/Source:/)).toBeInTheDocument();
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

  it('the verdict-language guard replaces any live answer that would state a verdict', () => {
    // A guided prompt whose (would-be) answer states a verdict must be replaced by
    // the routing text when it becomes the live turn — the panel never renders PASS.
    const { container, getByText } = render(
      <AssistantPanel
        reply={{ text: 'neutral guidance.', answeredFrom: 'schema' }}
        prompts={[
          {
            text: 'Is it valid?',
            answeredFrom: 'schema',
            answer: { text: 'This record is PASS against the schema.', answeredFrom: 'schema' },
          },
        ]}
        availability="available"
      />,
    );
    fireEvent.click(getByText('Is it valid?'));
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

  it('shows a WIRED composer (SECONDARY send) with the grounded-scope helper; the legacy guided-note stays de-duped and the subordinate caption is the single advisory footer', () => {
    const out = evidenceOut();
    const { getByRole, getByText, queryByText, getByLabelText, container } = render(
      <AssistantPanel reply={out.reply} prompts={out.prompts} availability="available" />,
    );
    // P34.2: a real labelled text input plus a SECONDARY-styled send control (never
    // the primary action), with the persistent grounded-scope helper visible.
    const box = getByRole('textbox');
    expect(box).toBeInTheDocument();
    expect(getByLabelText(/ask the assistant/i)).toBe(box);
    const send = getByRole('button', { name: /send/i });
    expect(send.className).toMatch(/btn-secondary/);
    expect(send.className).not.toMatch(/btn-primary/); // never styled as the primary action
    // the persistent helper names the grounded scopes the resolver answers over …
    expect(getByText(ASSISTANT_COMPOSER_HELPER)).toBeInTheDocument();
    // … and the legacy standalone guided-note is never surfaced.
    expect(queryByText(GUIDED_ONLY_NOTE)).toBeNull();
    // subordinate-to-deterministic-validation caption remains the single footer.
    // P36V S-A re-worded it and DROPPED the explicit negative claim "It never
    // validates"; the review restored it. Both halves are pinned separately so
    // neither can be dropped again silently:
    //   · the exact approved sentence, verbatim, in exactly one element;
    //   · the standalone POSITIVE assertion that the claim is present.
    const caption = container.querySelector('.assistant-caption') as HTMLElement;
    expect(caption).not.toBeNull();
    expect(caption.textContent).toBe(SUBORDINATE_CAPTION);
    expect(caption.textContent).toBe(
      'The Assistant is advisory: it explains artifacts and points to sources. ' +
        'It never validates — deterministic validation remains authoritative.',
    );
    expect(getByText(SUBORDINATE_CAPTION)).toBeInTheDocument();
    expect(container.querySelectorAll('.assistant-caption').length).toBe(1);
    // the explicit NEGATIVE capability claim, and the authority it defers to
    expect(getByText(/never validates/i)).toBeInTheDocument();
    expect(caption.textContent).toMatch(/never validates/i);
    expect(caption.textContent).toMatch(/deterministic validation remains authoritative/i);
    // the retired wording is gone (no stale duplicate advisory sentence survives)
    expect(queryByText(/advisory — it explains/i)).toBeNull();
    expect(caption.textContent).not.toMatch(/points to sources; deterministic/);
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
