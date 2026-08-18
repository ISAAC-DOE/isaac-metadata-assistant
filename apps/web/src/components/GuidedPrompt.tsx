import './assistant.css';
import { useState } from 'react';
import { Check, CircleHelp, MessageSquare } from './icons';
import { LABELS } from '../lib/labels';
import { answerValuePreview } from '../lib/adapt';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import type { PendingBlocker } from '../lib/types';

interface GuidedPromptProps {
  blocker: PendingBlocker;
  index: number; // 0-based
  total: number;
  onConfirm: (value: unknown) => void;
  onDontKnow: () => void;
  submitting?: boolean;
  /**
   * P28.3 edit mode: prefill the free-text (hash/text) input with the current
   * value so a correction starts from what is already confirmed. For a structured
   * blocker `initialStaged` pre-stages the demo value (nothing scientific is ever
   * typed by the assistant). Undefined ⇒ the normal blank propose→confirm flow.
   */
  initialValue?: string;
  initialStaged?: boolean;
  /** The confirm-button label; defaults to "Confirm" (edit mode passes "Save"). */
  confirmLabel?: string;
  /** The secondary-action label; defaults to the "I don't know…" copy. Edit mode
   *  passes "Cancel" so the same control abandons the correction with no mutation. */
  dontKnowLabel?: string;
  /** Hide the "a blank stays blank" completion hint (irrelevant in edit mode). */
  hideBlankHint?: boolean;
  /**
   * Report every keystroke upward so the caller can hold the staged answer somewhere
   * that OUTLIVES this component.
   *
   * WHY IT EXISTS. `text` is local state, and the completion screen's `Refresh`
   * button calls `useFetch`'s `reload`, which sets `{status: 'loading'}` and
   * unmounts `LoadedCompletion` — and this component with it. The banner beside that
   * button said "your input is kept", and one variant told the reader to press it.
   * The claim was true only until they followed the instruction. The caller now keeps
   * the value in a ref on a component the reload does NOT unmount, and hands it back
   * through `initialValue`.
   */
  onTextChange?: (value: string) => void;
}

/**
 * The one-question-at-a-time completion card — the single place AI touches a
 * value, made a two-step human-owned gate. The assistant never prefills a
 * scientific value: an asset hash is pasted by the user; a structured
 * series/descriptor value can only be *confirmed* from the labeled example
 * answer ("Example answer — not a value until you confirm" — the label is the
 * server's `serialize._DEMO_LABEL`, rendered verbatim; this docstring quoted the
 * retired "Demo answer (synthetic)" long after the string changed),
 * never auto-filled and never auto-submitted. "I don't know" is calm and
 * legitimate — it writes nothing and leaves the field honestly missing.
 *
 * Rendered with `key={blocker.id}` by the parent, so its input state resets
 * cleanly for each question.
 */
export function GuidedPrompt({
  blocker,
  index,
  total,
  onConfirm,
  onDontKnow,
  submitting = false,
  initialValue,
  initialStaged = false,
  confirmLabel = LABELS.actionConfirm,
  dontKnowLabel = LABELS.actionDontKnow,
  hideBlankHint = false,
  onTextChange,
}: GuidedPromptProps) {
  const [text, setTextState] = useState(initialValue ?? ''); // pasted value for hash/text inputs
  /* Every write goes through here so the caller's surviving copy cannot drift from
     what is on screen. A second setter would be one `setTextState` away from a
     half-preserved field, which is worse than none. */
  const setText = (value: string) => {
    setTextState(value);
    onTextChange?.(value);
  };
  const [staged, setStaged] = useState(initialStaged); // structured: demo value accepted for confirm

  const demo = blocker.demo_answer;
  const structured = blocker.inputType === 'structured';

  const canConfirm = structured
    ? staged && demo !== undefined
    : text.trim().length > 0;

  const handleConfirm = () => {
    if (!canConfirm) return;
    onConfirm(structured ? demo!.value : text.trim());
  };

  return (
    <section
      className="guided"
      aria-label={`Question ${index + 1} of ${total}`}
      /* The walkthrough's "answering a question" anchor. */
      data-tutorial-anchor={TUTORIAL_ANCHORS.completionQuestion}
    >
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

      {/* WHY the app is asking instead of answering. Rendered verbatim from the
          server's inferability decision — never re-worded here, so the reason a
          user reads is the reason the backend actually applied. The state is
          exposed as a data attribute so a test can assert the pairing of state
          and copy; a `supported_suggestion` would carry a value, and no blocker
          state ever does (see `inferability.blocker_inferability`). */}
      {blocker.inferability && (
        <p
          className="guided-inferability"
          data-inferability-state={blocker.inferability.state}
        >
          {blocker.inferability.explanation}
        </p>
      )}

      {demo && (
        <div className="guided-suggestion" aria-label="Example answer suggestion">
          <div className="guided-suggestion-head">
            <MessageSquare size={14} strokeWidth={2} aria-hidden="true" />
            {demo.label}
            <span className="guided-suggestion-not">— not a value until you confirm</span>
          </div>
          <p className="guided-suggestion-value mono">
            {typeof demo.value === 'string'
              ? demo.value
              : answerValuePreview(blocker.kind, demo.value)}
          </p>
          <button
            type="button"
            className="btn btn-secondary guided-suggestion-use"
            onClick={() => (structured ? setStaged(true) : setText(String(demo.value)))}
          >
            {structured ? 'Use This Value' : 'Use This Suggestion'}
          </button>
        </div>
      )}

      <div className="guided-field">
        {structured ? (
          <>
            <div className="guided-field-label">{blocker.path}</div>
            {demo ? (
              staged ? (
                <div className="guided-staged" role="status">
                  <Check size={14} strokeWidth={2.4} aria-hidden="true" />
                  Ready to confirm{' '}
                  <span className="mono">{answerValuePreview(blocker.kind, demo.value)}</span>
                </div>
              ) : (
                <p className="guided-structured-hint">
                  A structured value from the reduced pipeline. Confirm the example value above, or
                  leave it honestly missing — the assistant will not type it for you.
                </p>
              )
            ) : (
              <p className="guided-structured-hint">
                No example value is available for this field — leave it honestly missing.
              </p>
            )}
            {demo && (
              <div className="guided-input-row">
                <button
                  type="button"
                  className="btn btn-primary"
                  data-tutorial-anchor={TUTORIAL_ANCHORS.completionConfirm}
                  onClick={handleConfirm}
                  disabled={!canConfirm || submitting}
                >
                  {submitting ? 'Confirming…' : confirmLabel}
                </button>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="guided-field-label">
              {blocker.inputType === 'hash' ? 'sha256' : blocker.path}
            </div>
            <div className="guided-input-row">
              <input
                className="input input-mono"
                type="text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={
                  blocker.inputType === 'hash' ? 'paste 64-character sha256…' : 'type a value…'
                }
                aria-label={blocker.label}
              />
              <button
                type="button"
                className="btn btn-primary"
                data-tutorial-anchor={TUTORIAL_ANCHORS.completionConfirm}
                onClick={handleConfirm}
                disabled={!canConfirm || submitting}
              >
                {submitting ? 'Confirming…' : confirmLabel}
              </button>
            </div>
          </>
        )}
      </div>

      <div className="guided-footer">
        <button
          type="button"
          className="guided-dontknow"
          data-tutorial-anchor={TUTORIAL_ANCHORS.completionDontKnow}
          onClick={onDontKnow}
          disabled={submitting}
        >
          <CircleHelp size={15} strokeWidth={2} aria-hidden="true" />
          {dontKnowLabel}
        </button>
        {!hideBlankHint && (
          <span className="guided-blank">A blank stays blank until you confirm it.</span>
        )}
      </div>
    </section>
  );
}
