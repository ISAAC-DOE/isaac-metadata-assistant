import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import { ASSISTANT_SAMPLES, hasVerdictLanguage } from '../lib/assistant';

describe('AssistantPanel is subordinate and never renders a verdict', () => {
  it('renders subordinate copy with a source label and a memory freshness dot', () => {
    const { container, getByText } = render(
      <AssistantPanel
        reply={ASSISTANT_SAMPLES.review.reply}
        prompts={ASSISTANT_SAMPLES.review.prompts}
        freshness="fresh"
      />,
    );
    // every reply names its source
    expect(getByText(/answered from:/)).toBeInTheDocument();
    expect(getByText(/memory:/)).toBeInTheDocument();
    // indigo assistant surface, never a verdict class
    expect(container.querySelector('.assistant')).not.toBeNull();
    expect(container.querySelector('.verdict-pass')).toBeNull();
    expect(container.querySelector('.verdict-fail')).toBeNull();
  });

  it('contains no PASS/FAIL strings', () => {
    const { container } = render(
      <AssistantPanel
        reply={ASSISTANT_SAMPLES.export.reply}
        prompts={ASSISTANT_SAMPLES.export.prompts}
        freshness="fresh"
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
        freshness="fresh"
      />,
    );
    expect(container.textContent).not.toMatch(/\bPASS\b/);
    expect(container.textContent).toMatch(/truth question/i);
  });
});

describe('assistant sample messages never contain verdict language', () => {
  it('no static sample reply states PASS/FAIL', () => {
    for (const ctx of Object.values(ASSISTANT_SAMPLES)) {
      expect(hasVerdictLanguage(ctx.reply.text)).toBe(false);
      for (const p of ctx.prompts) {
        expect(hasVerdictLanguage(p.text)).toBe(false);
      }
    }
  });

  it('hasVerdictLanguage detects reserved verdict wording', () => {
    expect(hasVerdictLanguage('the record is PASS')).toBe(true);
    expect(hasVerdictLanguage('FAIL against schema')).toBe(true);
    expect(hasVerdictLanguage('the beamline came from the sheet')).toBe(false);
  });
});

describe('assistant final placeholder form: guided prompts + source-labeled answers', () => {
  it('every clickable prompt answer names a source doc and carries no verdict language', () => {
    for (const ctx of Object.values(ASSISTANT_SAMPLES)) {
      for (const p of ctx.prompts) {
        expect(p.answer).toBeDefined();
        expect(p.answer!.sourceDoc).toMatch(/\.md$/);
        expect(hasVerdictLanguage(p.answer!.text)).toBe(false);
      }
    }
  });

  it('clicking a guided prompt shows its static, source-labeled sample answer', () => {
    const prompt = ASSISTANT_SAMPLES.evidence.prompts[0];
    const { getByText } = render(
      <AssistantPanel
        reply={ASSISTANT_SAMPLES.evidence.reply}
        prompts={ASSISTANT_SAMPLES.evidence.prompts}
        freshness="fresh"
      />,
    );
    // guided prompts are primary; clicking one swaps in its answer
    fireEvent.click(getByText(prompt.text));
    expect(getByText(/assistant convention, not an official ISAAC standard/)).toBeInTheDocument();
    // the answer names its source doc
    const sourceDoc = prompt.answer!.sourceDoc!;
    expect(getByText(sourceDoc, { exact: false })).toBeInTheDocument();
  });

  it('free-form input is secondary and marked not wired; a subordinate caption is visible', () => {
    const { getByText, getByLabelText } = render(
      <AssistantPanel
        reply={ASSISTANT_SAMPLES.evidence.reply}
        prompts={ASSISTANT_SAMPLES.evidence.prompts}
        freshness="fresh"
      />,
    );
    expect(getByText(/not wired in this prototype/i)).toBeInTheDocument();
    const input = getByLabelText(/Ask the assistant/i) as HTMLInputElement;
    expect(input.disabled).toBe(true);
    // subordinate-to-deterministic-validation caption
    expect(getByText(/advisory — it explains/i)).toBeInTheDocument();
    expect(getByText(/never validates/i)).toBeInTheDocument();
  });
});
