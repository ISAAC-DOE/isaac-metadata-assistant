import './assistant.css';
import { useState } from 'react';
import { Check, CircleHelp, MessageSquare } from './icons';
import { LABELS } from '../lib/labels';
import { answerValuePreview } from '../lib/adapt';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import { QC_VERDICTS } from '../lib/types';
import {
  DescriptorForm,
  EMPTY_DESCRIPTOR,
  SeriesEntry,
  descriptorIsComplete,
  descriptorPayload,
  seriesParseError,
  type DescriptorDraft,
} from './StructuredValueEntry';
import type { PendingBlocker, QcAnswer, QcVerdict } from '../lib/types';

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
  initialValue?: unknown;
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
  /**
   * The structured sibling of {@link onTextChange}, for a blocker whose answer is not a
   * string. Every keystroke and every selection is reported so the owner's surviving
   * copy cannot drift from what is on screen — the property `onTextChange` exists for,
   * and the one the verdict control shipped without, making the screen's "what you
   * typed is kept, including through Refresh" false for exactly that blocker.
   */
  onStagedChange?: (value: unknown) => void;
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
  onStagedChange,
}: GuidedPromptProps) {
  /* `initialValue` is `unknown` because a verdict blocker's answer is an object. The
     text inputs take only the string form; anything else is not a pasted value and
     must not be coerced into one (`String({})` would put "[object Object]" in the box). */
  const [text, setTextState] = useState(typeof initialValue === 'string' ? initialValue : '');
  /* Every write goes through here so the caller's surviving copy cannot drift from
     what is on screen. A second setter would be one `setTextState` away from a
     half-preserved field, which is worse than none. */
  const setText = (value: string) => {
    setTextState(value);
    onTextChange?.(value);
  };
  const [staged, setStaged] = useState(initialStaged); // structured: demo value accepted for confirm
  /* A QC verdict is two inputs that only mean something together — the verdict and
     the reasoning behind it — so they are staged together and submitted as one value.
     `verdict` starts EMPTY on purpose: the blocker's own text says there is no default
     and none is assumed, "not even 'valid'", and a preselected control would assume
     one by doing nothing. */
  /* EVERY DOM ID AND THE RADIO GROUP NAME ARE BUILT FROM `blocker.key`, NOT `blocker.id`.
     `id` is the blocker KIND, so two runs each owing a QC verdict rendered EIGHT radios
     in ONE group named `qc-verdict-qc` — selecting a verdict for one run cleared the
     other — and two textareas both carrying `id="qc-note-qc"`, so `<label htmlFor>`
     resolved to whichever came first and `aria-describedby` was ambiguous. An
     independent review measured all three, and a duplicate id is an axe violation as
     well as a broken control. */
  const initialVerdict =
    initialValue && typeof initialValue === 'object' ? (initialValue as QcAnswer) : undefined;
  const [verdict, setVerdict] = useState<QcVerdict | ''>(initialVerdict?.status ?? '');
  const [verdictNote, setVerdictNote] = useState(initialVerdict?.evidence ?? '');

  /* ENTERED structured values, for a record that has no worked example to confirm.
     Held here beside `text` and `verdict` for the same reason they are: the owner's
     surviving copy is fed back through `initialValue`, and every write is reported. */
  const [descriptor, setDescriptor] = useState<DescriptorDraft>(
    initialValue && typeof initialValue === 'object' && 'name' in (initialValue as object)
      ? (initialValue as DescriptorDraft)
      : EMPTY_DESCRIPTOR,
  );
  const [seriesText, setSeriesText] = useState(
    /* A staged series survives as the RAW TEXT the reader typed, not as parsed JSON:
       half-written JSON is still their work, and reparsing it to restore it would lose
       exactly the state a Refresh most needs to preserve. */
    typeof initialValue === 'string' && blocker.kind === 'series' ? initialValue : '',
  );

  /* EVERY WRITE GOES THROUGH HERE, for the same reason `setText` does — and it was
     missing, which made this control the one place the screen's own promise was false.
     `GuidedCompletion` holds staged input ABOVE the prompt precisely so a Refresh does
     not destroy it, and renders "What you typed is kept, including through Refresh"
     next to the Refresh button. That channel carried only `text`, so a verdict and a
     paragraph of reasoning were silently discarded by the very button the sentence
     reassures the reader about — on the one blocker whose input is most expensive to
     retype. */
  const reportStaged = (next: Partial<QcAnswer>) => {
    const merged: QcAnswer = {
      status: next.status ?? (verdict as QcVerdict),
      evidence: next.evidence ?? verdictNote,
    };
    onStagedChange?.(merged);
  };

  const demo = blocker.demo_answer;
  const structured = blocker.inputType === 'structured';
  const isVerdict = blocker.inputType === 'verdict';

  /* BOTH halves are required, and this comment used to justify that with a backend
     behaviour that DOES NOT EXIST. The old text said "the draft validator refuses a
     verdict with no provenance … so a verdict submitted without a note is accepted by
     the store and then blocks the export anyway". Measured: it does not.
     `complete.apply_answers` writes the `block_evidence["qc:status"]` confirmation
     unconditionally, so `draft_validator`'s `_claim_covered` check is satisfied and a
     note-less verdict exports clean.

     The true reasons, both checkable:
       - `portal_warnings.QC_NONVALID_WITHOUT_EVIDENCE` fires for `failed`,
         `compromised` and `pending` without evidence. It is advisory and non-gating,
         and it does NOT fire for `valid`.
       - the schema's own `measurement.qc.evidence` is described as REQUIRED IN PRACTICE
         when the status is not `valid`.

     So requiring a note for EVERY verdict, `valid` included, is a PRODUCT DECISION
     stricter than any backend rule — taken because the reasoning is worth most at the
     moment the person has it, and because a verdict recorded without it is a scientific
     judgement with no trail. Stating that plainly is the point; the previous version
     borrowed authority from a refusal that never happens. */
  /* A structured blocker with NO example is answerable by ENTRY now. `demo` present
     keeps the confirm-the-example flow untouched — a walkthrough record must not start
     asking a reader to type a spectrum. */
  const entering = structured && demo === undefined;
  const entryKind = blocker.kind === 'series' ? 'series' : 'descriptor';
  const entryReady = entering
    ? entryKind === 'series'
      ? seriesText.trim() !== '' && seriesParseError(seriesText) === null
      : descriptorIsComplete(descriptor)
    : false;

  const canConfirm = entering
    ? entryReady
    : structured
    ? staged && demo !== undefined
    : isVerdict
      ? verdict !== '' && verdictNote.trim().length > 0
      : text.trim().length > 0;

  const handleConfirm = () => {
    if (!canConfirm) return;
    if (entering) {
      onConfirm(
        entryKind === 'series' ? JSON.parse(seriesText) : descriptorPayload(descriptor),
      );
      return;
    }
    if (isVerdict) {
      onConfirm({ status: verdict, evidence: verdictNote.trim() });
      return;
    }
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

      {/* WHOSE QUESTION THIS IS. Without it, three runs each needing a spectrum render
          three byte-identical cards — same question, same path, same label — and a
          scientist has no way to tell which run they are answering. `runLabel` was
          carried through the adapter and read by nothing until an independent review
          measured the consequence. A record-level question has no run and shows
          nothing extra, so a zero-run record is unchanged. */}
      {blocker.runLabel && (
        <p className="guided-owner">
          <span className="guided-owner-label">Run</span>
          {blocker.runLabel}
        </p>
      )}

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
        {isVerdict ? (
          <>
            <div className="guided-field-label">{blocker.path}</div>
            <div className="guided-verdict">
              <fieldset className="guided-verdict-set">
                <legend className="guided-verdict-legend">QC verdict</legend>
                {QC_VERDICTS.map((option) => (
                  <label key={option} className="guided-verdict-option">
                    <input
                      type="radio"
                      name={`qc-verdict-${blocker.key}`}
                      value={option}
                      checked={verdict === option}
                      onChange={() => {
                        setVerdict(option);
                        reportStaged({ status: option });
                      }}
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </fieldset>
              <label className="guided-verdict-note-label" htmlFor={`qc-note-${blocker.key}`}>
                How was it determined?
              </label>
              <textarea
                id={`qc-note-${blocker.key}`}
                className="input guided-verdict-note"
                value={verdictNote}
                onChange={(e) => {
                  setVerdictNote(e.target.value);
                  reportStaged({ evidence: e.target.value });
                }}
                rows={3}
                aria-required="true"
                aria-describedby={`qc-hint-${blocker.key}`}
                placeholder="what you checked, and what you saw…"
              />
              <p className="guided-verdict-hint" id={`qc-hint-${blocker.key}`}>
                A verdict is a scientific judgement. Nothing is assumed for you — not even
                &ldquo;valid&rdquo; — and the record stays incomplete until you make one.{' '}
                {/* NAMES THE REASON THE BUTTON IS DEAD. Without it a scientist who picks a
                    verdict and stops sees a disabled control with no explanation, and a
                    screen-reader user gets less than that. */}
                <strong>Both the verdict and how you determined it are required.</strong>
              </p>
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
            </div>
          </>
        ) : structured ? (
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
            ) : entryKind === 'series' ? (
              <SeriesEntry
                idPrefix={`entry-${blocker.key}`}
                text={seriesText}
                onChange={(next) => {
                  setSeriesText(next);
                  onStagedChange?.(next);
                }}
              />
            ) : (
              <DescriptorForm
                idPrefix={`entry-${blocker.key}`}
                value={descriptor}
                onChange={(next) => {
                  setDescriptor(next);
                  onStagedChange?.(next);
                }}
              />
            )}
            {entering && (
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
