import './assistant.css';
import { useState } from 'react';
import { MessageSquare, ChevronRight, SendHorizontal } from './icons';
import { LABELS } from '../lib/labels';
import {
  FREEFORM_NOT_WIRED,
  MEMORY_UNAVAILABLE_CAVEAT,
  SOURCE_LABELS,
  SUBORDINATE_CAPTION,
  hasVerdictLanguage,
} from '../lib/assistant';
import type { AssistantMessage, MemoryAvailability, SuggestedPrompt } from '../lib/types';

interface AssistantPanelProps {
  reply: AssistantMessage;
  prompts: SuggestedPrompt[];
  /** The primary memory-plane axis (P24.10): available vs unavailable. */
  availability: MemoryAvailability;
  /** Optional subordinate note, e.g. "truth questions route to the CLI…". */
  note?: string;
}

/**
 * Subordinate indigo helper — final placeholder form. Guided prompts are PRIMARY:
 * clicking one swaps in its STATIC, source-labeled sample answer (each names the
 * doc it is grounded in). Free-form input is rendered SECONDARY and clearly marked
 * not wired in this prototype. Every reply carries `answered from:` + a memory
 * freshness dot, and NEVER renders PASS/FAIL or a validity claim — the
 * verdict-language guard strips any reply that would state a verdict. The panel
 * explains and points to sources; it never decides.
 */
export function AssistantPanel({ reply, prompts, availability, note }: AssistantPanelProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const active =
    activeIndex !== null ? (prompts[activeIndex]?.answer ?? reply) : reply;

  // Structural guard: the assistant must never render a verdict.
  const guarded = hasVerdictLanguage(active.text);
  const safeText = guarded
    ? 'That is a truth question — open the Validate surface for the deterministic verdict.'
    : active.text;
  const sourceDoc = guarded ? undefined : active.sourceDoc;

  const caveat = availability === 'unavailable' ? MEMORY_UNAVAILABLE_CAVEAT : undefined;

  return (
    <section className="assistant" aria-label="Assistant (advisory)">
      <div className="assistant-head">
        <span className="assistant-icon" aria-hidden="true">
          <MessageSquare size={15} strokeWidth={2} />
        </span>
        <span className="assistant-label">{LABELS.assistant}</span>
        <span className="assistant-memory">
          <span className="dot dot-memory" aria-hidden="true" />
          memory: {availability}
        </span>
      </div>

      <p className="assistant-reply">{safeText}</p>
      <div className="assistant-sources">
        <span className="answered-from">answered from: {SOURCE_LABELS[active.answeredFrom]}</span>
        {sourceDoc && <span className="assistant-sourcedoc mono">From {sourceDoc}</span>}
      </div>

      {caveat && <p className="assistant-caveat">{caveat}</p>}
      {note && <p className="assistant-note">{note}</p>}

      <div className="assistant-suggested-eyebrow eyebrow">{LABELS.suggestedQuestions}</div>
      <div className="assistant-prompts">
        {prompts.map((p, i) => (
          <button
            type="button"
            className={`assistant-prompt${activeIndex === i ? ' active' : ''}`}
            key={p.text}
            aria-pressed={activeIndex === i}
            disabled={!p.answer}
            onClick={() => p.answer && setActiveIndex(i)}
          >
            <span>{p.text}</span>
            <ChevronRight className="chev" size={15} strokeWidth={2} aria-hidden="true" />
          </button>
        ))}
      </div>

      <div className="assistant-freeform">
        <div className="assistant-input" aria-hidden="true">
          <input
            type="text"
            placeholder="or ask your own question…"
            aria-label="Ask the assistant (not wired in this prototype)"
            disabled
          />
          <button type="button" className="assistant-send" aria-label="Send" disabled>
            <SendHorizontal size={15} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
        <p className="assistant-freeform-note">{FREEFORM_NOT_WIRED}</p>
      </div>

      <p className="assistant-caption">{SUBORDINATE_CAPTION}</p>
    </section>
  );
}
