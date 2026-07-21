import './assistant.css';
import { useState } from 'react';
import { MessageSquare, ChevronRight } from './icons';
import { LABELS } from '../lib/labels';
import {
  GUIDED_ONLY_NOTE,
  MEMORY_UNAVAILABLE_CAVEAT,
  SOURCE_LABELS,
  SUBORDINATE_CAPTION,
  hasVerdictLanguage,
} from '../lib/assistant';
import type { AssistantMessage, MemoryAvailability, SuggestedPrompt } from '../lib/types';

interface AssistantPanelProps {
  reply: AssistantMessage;
  prompts: SuggestedPrompt[];
  /**
   * The primary memory-plane axis (P24.10): available vs unavailable — passed
   * ONLY by screens that actually fetch GET /api/graph/status. When OMITTED
   * (P25.7), the screen makes no memory-availability claim: the panel renders
   * neither the `memory:` head line nor the memory caveat, keeping the framing
   * honest for memory-less contexts (e.g. Guided Completion).
   */
  availability?: MemoryAvailability;
  /** Optional subordinate note, e.g. "truth questions route to the CLI…". */
  note?: string;
}

/**
 * Subordinate indigo helper — final placeholder form. Guided prompts are the
 * PRIMARY and ONLY input: clicking one swaps in its STATIC, source-labeled
 * sample answer (each names the doc it is grounded in). There is no free-text
 * affordance — the panel is honestly guided-prompts-only (P25.2), stated via
 * `GUIDED_ONLY_NOTE`. Every reply carries `answered from:` + a memory
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

  // Only a screen that actually fetched graph status may make a memory claim.
  // With `availability` omitted, we render NO memory head line and NO caveat.
  // Dedupe guard: on the Project Memory unavailable mount the composed reply
  // text is byte-identical to MEMORY_UNAVAILABLE_CAVEAT, so rendering both would
  // print the same sentence twice, stacked (reads as broken copy). Suppress the
  // caveat when it equals the reply actually shown. On every other mount the
  // reply is a substantive answer and the caveat is a genuinely distinct
  // footnote, so both still render; the `memory: unavailable` head line is
  // unaffected either way.
  const caveat =
    availability === 'unavailable' && MEMORY_UNAVAILABLE_CAVEAT !== safeText
      ? MEMORY_UNAVAILABLE_CAVEAT
      : undefined;

  return (
    <section className="assistant" aria-label="Assistant (advisory)">
      <div className="assistant-head">
        <span className="assistant-icon" aria-hidden="true">
          <MessageSquare size={15} strokeWidth={2} />
        </span>
        <span className="assistant-label">{LABELS.assistant}</span>
        {availability && (
          <span className="assistant-memory">
            <span className="dot dot-memory" aria-hidden="true" />
            memory: {availability}
          </span>
        )}
      </div>

      <p className="assistant-reply" aria-live="polite">{safeText}</p>
      <div className="assistant-sources">
        <span className="answered-from">answered from: {SOURCE_LABELS[active.answeredFrom]}</span>
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

      <p className="assistant-guided-note">{GUIDED_ONLY_NOTE}</p>

      <p className="assistant-caption">{SUBORDINATE_CAPTION}</p>
    </section>
  );
}
