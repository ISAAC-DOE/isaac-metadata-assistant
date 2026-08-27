import './discard.css';
import { useEffect, useId, useRef, useState } from 'react';

import { X } from './icons';
import type { DiscardCopy } from '../lib/discardContent';

/**
 * DISCARD STAGED CAPTURE INPUT — one control, one shape, four panels.
 *
 * THIS COMPONENT CANNOT TALK TO THE SERVER, AND THAT IS THE GUARANTEE RATHER THAN AN
 * OMISSION. It imports no API module, takes no experiment id, holds no version token
 * and issues no request. Discarding something the server has never seen must not
 * consult the server about it: there is no row to compare-and-swap against, no
 * `If-Match` that would mean anything, and no failure mode worth inventing. A
 * precondition token would be a weaker promise than this one, because it would still
 * be a request that could be observed, rate-limited, logged, or refused.
 * `__tests__/discard-staged-capture.test.tsx` asserts the absence directly, per panel:
 * every method the panel issued across a whole discard is `GET`.
 *
 * WHAT IT IS NOT ALLOWED TO SAY. See `lib/discardContent.ts`. In short: this control
 * clears an input on screen. This application has no note deletion — `routes.py`
 * states so as a governing rule — so no Discard may read as one.
 *
 * ── THE PATTERN, AND WHY IT IS THE SAME EVERYWHERE ──────────────────────────────
 *
 * A quiet, right-aligned secondary trigger, and a second, explicit step that states in
 * words what goes and what does not. Every one of them uses the confirm step, including
 * the one that holds a single box, and that uniformity is a decision with a reason: each Discard has to put its truthful scope sentence somewhere a SIGHTED
 * reader meets it, and a subtle secondary control has no room for a sentence. The
 * choice was between a permanently-visible disclaimer beside every capture box
 * (standing chrome for a control most readers never press), and a sentence that
 * appears when the control is pressed. The second is also, for free, the "explicit
 * intent" property: no single click of anything — a trigger, a stray tab-and-space, a
 * primary control — ever destroys typing.
 *
 * ── FOUR PROPERTIES, EACH BUILT RATHER THAN ASSERTED ─────────────────────────────
 *
 * **Never present-but-inert.** The trigger is ABSENT while `staged` is false, never
 * disabled. A disabled Discard is a control that says there is something to discard
 * and then refuses; an absent one says there is nothing.
 *
 * **Idempotent by construction.** `onDiscard` is reachable only from the commit
 * button, which is mounted only while `open && staged`. A second discard is therefore
 * not a no-op that had to be coded — it is unreachable until something is staged again.
 *
 * **It cannot fire on blur, close, unmount or navigation.** There is no effect that
 * calls `onDiscard`, and the component exports no imperative handle. The only caller
 * is the commit button's `onClick`.
 *
 * **It does not move the layout.** `.discard-slot` reserves its row height whether or
 * not the trigger is in it, so the surrounding form does not jump on the first
 * keystroke or the last backspace. The confirm step DOES take space when it opens —
 * that is a disclosure the reader asked for, not a shift they did not.
 *
 * ── FOCUS ────────────────────────────────────────────────────────────────────────
 *
 * Every destination is mounted by the same render that unmounts the control the reader
 * activated, so each move runs in an effect after commit rather than in the handler —
 * the contract `RunCard`, `UnmappedNotesPanel` and `RenameExperimentPanel` all keep,
 * for the reason `RenameExperimentPanel` records: a `.focus()` in the handler is called
 * on a node that is about to be replaced.
 *
 *   opened   → the commit button, so the decision is under the caret
 *   kept     → the trigger, which is where the reader was
 *   discarded→ `onFocusAfterDiscard` if the panel named somewhere better (usually the
 *              box that just emptied), otherwise this slot — `RunInheritedPanel`'s rule:
 *              landing on a stable place inside the form is a place, landing on `<body>`
 *              is what the mechanism exists to prevent. The slot carries the live region
 *              ONLY when this component hosts one; a panel that supplied `onAnnounce`
 *              announces through its own region elsewhere on screen, and this line used
 *              to say "the slot, which carries the live region" as though that were
 *              always true. It is true of `GuidedPrompt` and of nothing else today.
 *              Announcement is not what makes the destination correct — a polite region
 *              is read wherever it lives — but the sentence should not claim otherwise.
 *   vanished → the slot, when the staged content disappeared underneath an open
 *              confirm (the reader emptied the box by hand while it was open). The
 *              sentence stops being true, so the step closes without announcing a
 *              discard that did not happen.
 */
export function DiscardStaged({
  staged,
  copy,
  onDiscard,
  onAnnounce,
  onFocusAfterDiscard,
  className,
}: {
  /** Is there anything staged to discard? False ⇒ no control renders at all. */
  staged: boolean;
  /** The authored copy for this control. See `lib/discardContent.ts`. */
  copy: DiscardCopy;
  /**
   * The PANEL'S OWN live region, when it has one. Supplying it suppresses the region
   * below, and that is not a nicety.
   *
   * `UnmappedNotesPanel`, `ConflictResolutionPanel` and `TranscriptCapturePanel` each
   * already keep one always-mounted `role="status"` for exactly this purpose — "the ACT
   * announcement, separate from the counts". A second unnamed polite region in the same
   * panel is a second thing for a screen reader to arbitrate between, for one sentence
   * that belongs in the first; and it broke nine existing tests that locate that panel's
   * one announcement channel by role, which is the same ambiguity showing up
   * mechanically.
   *
   * Omit it where the panel has no such channel — today only `GuidedPrompt` — and this
   * component supplies one rather than announcing nothing. Adding a self-hosted region
   * to a NEW panel is not free: see `lib/discardContent.ts`'s note on why the Assistant
   * composer has no Discard, where exactly that cost is what withdrew one.
   */
  onAnnounce?: (text: string) => void;
  /**
   * Clear the staged input. MUST be synchronous local state work and MUST NOT issue a
   * request — the whole guarantee of this control is that discarding unsent input is
   * not a conversation with the server.
   */
  onDiscard: () => void;
  /** Where focus belongs afterwards. Omit to land on the announced slot. */
  onFocusAfterDiscard?: () => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [announced, setAnnounced] = useState('');
  const ids = useId();
  const confirmId = `${ids}-confirm`;

  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const commitRef = useRef<HTMLButtonElement | null>(null);
  const slotRef = useRef<HTMLDivElement | null>(null);
  const exit = useRef<'kept' | 'discarded' | 'vanished' | null>(null);

  /*
   * THE CONFIRM STEP CLOSES IF ITS SUBJECT DISAPPEARS. A reader can empty the box by
   * hand while the step is open — it sits below the box, not over it — and at that
   * moment its sentence describes input that is already gone. Closing silently is the
   * honest outcome: no discard happened, so nothing is announced.
   */
  useEffect(() => {
    if (!staged && open) {
      exit.current = 'vanished';
      setOpen(false);
    }
  }, [staged, open]);

  useEffect(() => {
    if (open) {
      commitRef.current?.focus();
      return;
    }
    const how = exit.current;
    if (how === null) return;
    exit.current = null;
    if (how === 'kept') {
      triggerRef.current?.focus();
      return;
    }
    if (how === 'discarded' && onFocusAfterDiscard) {
      onFocusAfterDiscard();
      return;
    }
    slotRef.current?.focus();
    // `onFocusAfterDiscard` is deliberately not a dependency: re-running this effect
    // because a parent re-created an inline callback would steal focus from wherever
    // the reader had moved it to. The effect is keyed on the transition, not on the
    // identity of the destination.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const keep = () => {
    exit.current = 'kept';
    setOpen(false);
  };

  const discard = () => {
    // The one call site. Nothing here awaits, retries, or reports a failure, because
    // there is no request to fail.
    onDiscard();
    if (onAnnounce) onAnnounce(copy.announcement);
    else setAnnounced(copy.announcement);
    exit.current = 'discarded';
    setOpen(false);
  };

  return (
    <div
      className={className === undefined ? 'discard-slot' : `discard-slot ${className}`}
      ref={slotRef}
      tabIndex={-1}
      data-staged={staged ? 'yes' : 'no'}
    >
      {/* ALWAYS MOUNTED, empty when there is nothing to say — `RenameExperimentPanel`'s
          rule, for its reason: a live region inserted together with its content is
          announced unreliably, and this is the only place the outcome is stated. Absent
          entirely when the panel routes the sentence into its own; see `onAnnounce`. */}
      {onAnnounce === undefined && (
        /*
         * `role="status"` WITHOUT AN EXPLICIT `aria-live` ATTRIBUTE, and the omission is
         * deliberate rather than an oversight. `role="status"` carries an implicit
         * `aria-live="polite"`, so this announces exactly as the version with the
         * attribute would.
         *
         * The convention it follows is `AssistantPanel`'s, which announces the
         * CONVERSATION through one explicitly-marked polite region (the reply `<p>`,
         * with the history log forced to `aria-live="off"`) and writes its two
         * SECONDARY announcements this way instead — `.assistant-degraded` and
         * `.agent-proposal-stale` are both `role="status"` with no attribute. A discard
         * outcome is secondary in exactly that sense.
         *
         * It does NOT make a self-hosted region free. `graph-semantic-zoom.test.tsx`
         * counts `role="status"` across the whole document on Project Memory and
         * requires exactly one, which is what withdrew the Assistant composer's Discard;
         * a panel that already owns an announcement channel should pass `onAnnounce`.
         */
        <p className="sr-only" role="status" aria-atomic="true">
          {announced}
        </p>
      )}

      {/*
        THE TRIGGER STAYS MOUNTED WHILE THE STEP IS OPEN, which is `RunCard`'s shape for
        its removal confirmation and is the reason to copy it rather than invent one. A
        trigger that unmounts on activation can never carry `aria-expanded={true}`: a
        screen-reader user hears "collapsed", presses it, and the control they pressed no
        longer exists — so the attribute would describe a state the element never reaches.
        Mounted, it is a real disclosure: `aria-expanded` moves, `aria-controls` points at
        something that is in the document, and pressing it again closes the step.
      */}
      {staged && (
        <button
          ref={triggerRef}
          type="button"
          className="discard-trigger"
          aria-expanded={open}
          aria-controls={open ? confirmId : undefined}
          onClick={() => (open ? keep() : setOpen(true))}
        >
          <X size={13} strokeWidth={2} aria-hidden="true" />
          {copy.trigger}
        </button>
      )}

      {staged && open && (
        <div
          className="discard-confirm"
          id={confirmId}
          role="group"
          aria-label={copy.trigger}
          onKeyDown={(event) => {
            // Escape leaves the step the same way "Keep it" does — including the focus
            // return — so a reader who opened it by accident is not trapped in it.
            if (event.key === 'Escape') {
              event.stopPropagation();
              keep();
            }
          }}
        >
          <p className="discard-confirm-text">{copy.body}</p>
          <div className="discard-confirm-actions">
            <button
              ref={commitRef}
              type="button"
              className="btn btn-danger-quiet"
              onClick={discard}
            >
              {copy.commit}
            </button>
            <button type="button" className="btn btn-secondary" onClick={keep}>
              {copy.keep}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
