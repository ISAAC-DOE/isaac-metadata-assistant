import './assistant.css';
import { MessageSquare, ChevronRight, SendHorizontal } from './icons';
import { LABELS } from '../lib/labels';
import { hasVerdictLanguage } from '../lib/assistant';
import type { AssistantMessage, GraphFreshness, SuggestedPrompt } from '../lib/types';

interface AssistantPanelProps {
  reply: AssistantMessage;
  prompts: SuggestedPrompt[];
  freshness: GraphFreshness;
  /** Optional subordinate note, e.g. "truth questions route to the CLI…". */
  note?: string;
}

/**
 * Subordinate indigo helper. `answered from:` on every reply; a memory freshness
 * dot; NEVER renders PASS/FAIL or a validity claim (truth questions route to the
 * deterministic surfaces). The verdict-language guard strips any reply that
 * would state a verdict — the panel explains, it never decides.
 */
export function AssistantPanel({ reply, prompts, freshness, note }: AssistantPanelProps) {
  // Structural guard: the assistant must never render a verdict.
  const safeReply = hasVerdictLanguage(reply.text)
    ? 'That is a truth question — open the Validate surface for the deterministic verdict.'
    : reply.text;

  return (
    <section className="assistant" aria-label="Assistant (advisory)">
      <div className="assistant-head">
        <span className="assistant-icon" aria-hidden="true">
          <MessageSquare size={15} strokeWidth={2} />
        </span>
        <span className="assistant-label">{LABELS.assistant}</span>
        <span className="assistant-memory">
          <span className="dot dot-memory" aria-hidden="true" />
          memory: {freshness}
        </span>
      </div>

      <p className="assistant-reply">{safeReply}</p>
      <span className="answered-from">answered from: {reply.answeredFrom}</span>

      {note && <p className="assistant-note">{note}</p>}

      <div className="assistant-suggested-eyebrow eyebrow">{LABELS.suggestedQuestions}</div>
      <div className="assistant-prompts">
        {prompts.map((p) => (
          <button type="button" className="assistant-prompt" key={p.text}>
            <span>{p.text}</span>
            <ChevronRight className="chev" size={15} strokeWidth={2} aria-hidden="true" />
          </button>
        ))}
      </div>

      <div className="assistant-input">
        <input type="text" placeholder="or ask your own question…" aria-label="Ask the assistant" />
        <button type="button" className="assistant-send" aria-label="Send">
          <SendHorizontal size={15} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}
