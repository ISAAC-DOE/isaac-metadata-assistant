import './assistant.css';
import { MessageSquare, CircleHelp } from './icons';
import { LABELS } from '../lib/labels';
import type { PendingBlocker } from '../lib/types';

interface GuidedPromptProps {
  blocker: PendingBlocker;
  index: number; // 0-based
  total: number;
  onConfirm?: (value: string) => void;
  onDontKnow?: () => void;
}

/**
 * The one-question-at-a-time completion card — propose → confirm → evidence, the
 * single place AI touches a value. The input is the primary control; the
 * assistant suggestion is subordinate indigo, labeled "— not a value" and never
 * a prefilled answer. "I don't know" is calm and legitimate, never red.
 */
export function GuidedPrompt({ blocker, index, total, onConfirm, onDontKnow }: GuidedPromptProps) {
  return (
    <section className="guided" aria-label={`Question ${index + 1} of ${total}`}>
      <div className="guided-head">
        <span className="guided-num" aria-hidden="true">
          {index + 1}
        </span>
        <span className="guided-index">
          Question {index + 1} of {total}
        </span>
        <span className="guided-path">{blocker.path}</span>
      </div>

      <h2 className="guided-question">{blocker.question}</h2>
      {blocker.context && <p className="guided-context">{blocker.context}</p>}

      {blocker.suggestion && (
        <div className="guided-suggestion">
          <div className="guided-suggestion-head">
            <MessageSquare size={14} strokeWidth={2} aria-hidden="true" />
            {LABELS.assistantSuggestion}
            <span className="guided-suggestion-not">— not a value</span>
          </div>
          <p className="guided-suggestion-text">{blocker.suggestion.text}</p>
          <div className="guided-suggestion-src">
            <span className="answered-from">answered from: {blocker.suggestion.answeredFrom}</span>
            {blocker.suggestion.locator && (
              <span className="guided-suggestion-loc">{blocker.suggestion.locator}</span>
            )}
          </div>
        </div>
      )}

      <div className="guided-field">
        <div className="guided-field-label">
          {blocker.inputType === 'hash' ? 'sha256' : blocker.inputType === 'number' ? 'number' : blocker.path}
        </div>
        <div className="guided-input-row">
          {blocker.inputType === 'enum' ? (
            <select className="input" aria-label={blocker.label} defaultValue="">
              <option value="" disabled>
                Select a value…
              </option>
              {blocker.enumOptions?.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          ) : blocker.inputType === 'number' ? (
            <>
              <input
                className="input input-mono"
                type="text"
                inputMode="decimal"
                placeholder="value"
                aria-label={blocker.label}
              />
              {blocker.unit && <span className="guided-unit">{blocker.unit} · σ</span>}
            </>
          ) : (
            <input
              className="input input-mono"
              type="text"
              placeholder="paste 64-character sha256…"
              aria-label={blocker.label}
            />
          )}
          <button type="button" className="btn btn-primary" onClick={() => onConfirm?.('')}>
            {LABELS.actionConfirm}
          </button>
        </div>
      </div>

      <div className="guided-footer">
        <button type="button" className="guided-dontknow" onClick={onDontKnow}>
          <CircleHelp size={15} strokeWidth={2} aria-hidden="true" />
          {LABELS.actionDontKnow}
        </button>
        <span className="guided-blank">A blank stays blank until you confirm it.</span>
      </div>
    </section>
  );
}
