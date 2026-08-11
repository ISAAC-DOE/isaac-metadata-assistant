/*
 * WHAT ONE RUN INHERITS FROM ITS RECORD, AND WHAT IT DELIBERATELY DOES NOT.
 *
 * This panel used to be strictly read-only, and its copy said so: "Change an
 * inherited value on the experiment, not here." That sentence is now false, and
 * it is replaced rather than softened — a run CAN hold its own value at a
 * record-level address, through the two operations this panel drives:
 *
 *   POST …/runs/{id}/overrides        record this run's own value at one address
 *   POST …/runs/{id}/overrides/clear  drop it, so the run inherits again
 *
 * FOUR PROPERTIES OF THE DOMAIN THIS UI HAS TO BE FAITHFUL TO, none of which it
 * implements — every one of them is decided by `workspace.resolve_inherited` and
 * `Experiment.set_run_override`, and this file only READS their answer:
 *
 *   1. NOTHING IS COPIED DOWN. A run stores the override and only the override.
 *      An inherited value is resolved live at read time, so it still changes when
 *      the record does. The panel therefore never caches a "resolved" value of
 *      its own and never computes one — it renders `run.inherited[address]`.
 *   2. AN OVERRIDE IS HISTORICAL AS WELL AS CURRENT. It records what it
 *      DISPLACED at the moment it was recorded, and that copy is never
 *      refreshed. So an overridden row can honestly show three different things:
 *      what this run holds, what the record says NOW, and what was displaced.
 *      When the last two differ the row says the record has moved since — because
 *      two unexplained values side by side read as a bug.
 *   3. REVERTING RESTORES INHERITANCE BY REFERENCE. The run goes back to holding
 *      NO value there — not to holding a copy of what the record currently says —
 *      so it follows every later change again. The panel says exactly that, and
 *      never offers to "copy the record's value down", which would be a different
 *      and much worse operation.
 *   4. RE-RECORDING THE SAME OVERRIDE IS A NO-OP. The server does not restamp it
 *      and does not advance the run. This panel detects that (the run's `rev` did
 *      not move) and reports "already held", not "recorded" — presenting a no-op
 *      as a change is how an audit trail acquires entries nothing happened at.
 *
 * PROVENANCE IS NOT VERIFICATION. Every label here says where a value CAME FROM —
 * inherited from the record, or overridden on this run. None of them says the
 * value is right, checked, or scientifically verified: that is what Check Run and
 * the official-schema gate are for, and this panel never renders a verdict.
 *
 * THE DISTINCTION IS NEVER COLOUR ALONE. An overridden row carries a glyph, the
 * word "Overridden", a different surface treatment AND a different border weight
 * (see `runs.css`); an inherited one carries the inheritance glyph and the words
 * "Inherited from record". Any one of those alone would identify the state.
 *
 * CONFIRMATION IS NOT AUTOMATIC. Both operations refuse with `422
 * confirmation_required` unless the request carries `confirmed_by_user: true`,
 * and this panel never sends `true` on the reader's behalf: recording an override
 * requires a ticked confirmation box beside the value, and reverting requires a
 * second, explicit click. `api.setRunOverride`/`clearRunOverride` take the flag as
 * an argument and pass it through, so the assertion is made here, where the
 * gesture is, and nowhere else.
 *
 * EVERY CONTROL HERE DESTROYS ITSELF WHEN IT IS ACTIVATED, so this panel MOVES
 * FOCUS — and it did not, which was a real keyboard defect rather than a polish
 * item. Opening the form unmounts the button that opened it; cancelling unmounts
 * the form; a successful write replaces the row's controls with different ones.
 * With nothing moving focus, activating any of them dropped the caret to `<body>`
 * (measured), so a keyboard or screen-reader reader on row 9 of 13 had to tab back
 * through the skip link, the app shell and eight rows to reach the input they had
 * just revealed. An axe scan cannot see this: axe does not evaluate focus
 * movement. {@link FOCUS_KEYS} lists every control focus is moved to, and
 * `focusAfter` states what is focused at each exit and why; the last resort is the
 * panel itself, never `<body>`.
 *
 * A 412 NAMES A CONTROL THAT IS ON SCREEN. The stale notice used to say "Refresh
 * this run" while the ONLY refresh in the app was `RunCard`'s, gated on
 * `autosave.status === 'conflict'` — a state an override 412 never enters, because
 * the override write does not go through `useRunAutosave` at all. Measured on this
 * branch's own compare-and-swap scenario: zero refresh buttons, zero conflict
 * banners, and every retry 412ing forever because `run.version` in the prop could
 * not advance. The notice now carries its own refresh, which re-reads the run and
 * hands it up through `onRun` — so the version the next attempt sends is the one
 * the server holds and the retry can actually succeed.
 */

import { useEffect, useRef, useState } from 'react';
import { ApiError, api } from '../lib/api';
import { CornerDownRight, Pencil, RotateCcw, TriangleAlert } from './icons';
import {
  buildOverridePayload,
  overrideRows,
  overrideValueKind,
  readOverrideRefusal,
  type OverrideRefusal,
  type OverrideRow,
} from '../lib/runOverrides';
import type { ApiRunView } from '../lib/types';

/** The outcome of the last write, for the panel's one live region. */
type Outcome =
  | { kind: 'recorded'; address: string; recordedUtc: string }
  | { kind: 'unchanged'; address: string }
  | { kind: 'reverted'; address: string }
  | { kind: 'nothing-to-revert'; address: string }
  // A re-read is NOT a write, and it is reported in the same region because it is
  // the answer to a failure reported there: the run on screen is the server's
  // again, and the override the 412 refused is still not recorded.
  | { kind: 'refreshed'; address: string };

/** A write that did not happen, and the reason, as the server gave it. */
type Failure =
  | { kind: 'refused'; address: string; refusal: OverrideRefusal }
  | { kind: 'stale'; address: string }
  | { kind: 'error'; address: string; message: string };

const FALLBACK_REFUSAL =
  'The server refused this override and this build could not read its reason. Nothing was written.';

/**
 * The controls focus may be moved to, keyed by kind and address.
 *
 * A KEY RATHER THAN A REF PER CONTROL, because the destination usually does not
 * exist yet at the moment the move is decided: activating a control unmounts it
 * and mounts the next one in the same commit. So a move is REQUESTED by key and
 * resolved after the DOM has settled, against whatever is mounted then.
 */
const FOCUS_KEYS = {
  /** The button that opens the override form — "Override for this run" / "Change this run's value". */
  openTrigger: (address: string) => `open:${address}`,
  /** The button that opens the revert confirmation — "Revert to inherited". */
  revertTrigger: (address: string) => `revert:${address}`,
  /** The value box inside the open override form. */
  formInput: (address: string) => `input:${address}`,
  /** The open form's submit — "Record override". */
  formSubmit: (address: string) => `submit:${address}`,
  /** The revert confirmation's own submit — "Confirm revert". */
  confirmRevert: (address: string) => `confirm:${address}`,
  /** The stale notice's own re-read control. */
  refresh: (address: string) => `refresh:${address}`,
  /** The failure notice itself, focusable only programmatically. */
  failure: (address: string) => `failure:${address}`,
} as const;

export function RunInheritedPanel({
  experimentId,
  run,
  onRun,
}: {
  experimentId: string;
  run: ApiRunView;
  /** Adopt the refreshed run the server returned. */
  onRun: (run: ApiRunView) => void;
}) {
  const rows = overrideRows(run);

  /** The address whose override form is open, and what has been entered in it. */
  const [editing, setEditing] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [entryError, setEntryError] = useState<string | null>(null);
  /** The address whose revert is awaiting its second, explicit click. */
  const [reverting, setReverting] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  /** The address whose run re-read is in flight, and why the last one did not happen. */
  const [refreshing, setRefreshing] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  /*
   * WHERE FOCUS GOES, AND WHY IT IS A QUEUE RATHER THAN A `focus()` CALL.
   *
   * Every destination below is mounted by the SAME render that unmounts the
   * control the reader activated, so calling `focus()` in the handler would call
   * it on a node that is about to be replaced. A request is therefore recorded as
   * an ordered list of candidate keys and resolved in an effect, after commit,
   * against the map of controls actually mounted.
   *
   * THE LIST IS ORDERED BECAUSE A ROW CAN LOSE THE CONTROL IT CAME FROM. Reverting
   * an override at an address the RECORD carries nothing at removes the row
   * entirely (`overrideRows` drops a row with no value that is no longer
   * overridden), and a successful write replaces a row's trigger with a
   * differently-labelled one. So each exit names its preferred destination and its
   * honest fallbacks, and the final fallback is the panel itself — which is why it
   * carries `tabIndex={-1}`. Landing on the panel is a deliberate, announced place
   * beside the live region that says what happened; landing on `<body>` is what
   * this whole mechanism exists to prevent.
   */
  const controls = useRef(new Map<string, HTMLElement>());
  const [focusRequest, setFocusRequest] = useState<readonly string[] | null>(null);
  const sectionRef = useRef<HTMLElement | null>(null);
  const bindControl = (key: string) => (el: HTMLElement | null) => {
    if (el === null) controls.current.delete(key);
    else controls.current.set(key, el);
  };
  const focusAfter = (...keys: readonly string[]) => setFocusRequest(keys);
  useEffect(() => {
    if (focusRequest === null) return;
    for (const key of focusRequest) {
      const el = controls.current.get(key);
      if (el !== undefined && el.isConnected) {
        el.focus();
        setFocusRequest(null);
        return;
      }
    }
    sectionRef.current?.focus();
    setFocusRequest(null);
  }, [focusRequest]);

  if (rows.length === 0) return null;

  const closeForm = () => {
    setEditing(null);
    setText('');
    setConfirmed(false);
    setEntryError(null);
  };

  /**
   * Turn a thrown `ApiError` into something TRUE about what happened.
   *
   * A 412 is the compare-and-swap refusal, and it is the one case in which a
   * "success" would be an outright lie: the route returns it from inside the same
   * critical section that would have written, so the override was NOT recorded.
   * A 422 carries the server's own typed sentence, which is shown verbatim.
   * Anything else keeps the client's own message — never a refusal the server did
   * not make.
   */
  const failFrom = (address: string, err: unknown): Failure => {
    if (err instanceof ApiError) {
      if (err.status === 412) return { kind: 'stale', address };
      if (err.status === 422) {
        const refusal = readOverrideRefusal(err.body);
        return refusal !== null
          ? { kind: 'refused', address, refusal }
          : { kind: 'refused', address, refusal: { message: FALLBACK_REFUSAL, findings: [] } };
      }
      return { kind: 'error', address, message: err.message };
    }
    return {
      kind: 'error',
      address,
      message: err instanceof Error ? err.message : 'The override could not be sent.',
    };
  };

  const submitOverride = (row: OverrideRow) => {
    const built = buildOverridePayload(row, text);
    if (!built.ok) {
      setEntryError(built.error);
      return;
    }
    setEntryError(null);
    setBusy(row.address);
    setOutcome(null);
    setFailure(null);
    /*
     * THE NO-OP IS DETECTED FROM THE RUN'S OWN REVISION, not guessed from the
     * text. `set_run_override` compares the payload it was given against the
     * stored one and returns the existing override unchanged when they are equal,
     * without restamping it and without advancing the run — so an unmoved `rev` IS
     * the server's answer to "did anything change", read off the refreshed run it
     * returned rather than inferred here.
     */
    const revBefore = run.rev;
    api
      .setRunOverride(
        experimentId,
        run.id,
        { address: row.address, payload: built.payload, confirmedByUser: confirmed },
        run.version,
      )
      .then((res) => {
        onRun(res.run);
        setOutcome(
          res.run.rev === revBefore
            ? { kind: 'unchanged', address: row.address }
            : { kind: 'recorded', address: row.address, recordedUtc: res.override.recorded_utc },
        );
        closeForm();
        /*
         * BACK TO THE ROW'S TRIGGER, WHICH NOW SAYS SOMETHING ELSE. A successful
         * record turns an inherited row into an overridden one, so the button that
         * reappears where the form was reads "Change this run's value · <path>"
         * rather than "Override for this run · <path>" — moving focus onto it
         * therefore ANNOUNCES the row's new state through the control's own name,
         * on top of the polite live region. The write can also remove the row (a
         * re-record cannot, but the same exit is used by every close), so the panel
         * is the fallback.
         */
        focusAfter(FOCUS_KEYS.openTrigger(row.address));
      })
      .catch((err: unknown) => {
        setFailure(failFrom(row.address, err));
        /*
         * A REFUSED WRITE LEAVES THE FORM OPEN, and focus cannot usefully be left
         * where it was: the submit sets `disabled` for the whole round trip, so the
         * control the reader activated is not one they can act from when the answer
         * arrives. Focus moves to the notice instead — the error-summary pattern, a
         * `tabIndex={-1}` container the reader lands on, with the 412's own refresh
         * one Tab away. Not back to the submit, because for `not_overridable` an
         * identical retry cannot succeed and focusing it would suggest otherwise.
         */
        focusAfter(FOCUS_KEYS.failure(row.address), FOCUS_KEYS.formSubmit(row.address));
      })
      .finally(() => setBusy(null));
  };

  /**
   * Re-read this run and adopt the server's version — the 412's named remedy.
   *
   * IT IS NOT `useRunAutosave`'s REFRESH, and that is a deliberate choice rather
   * than duplication. `refreshRun` in the autosave store DROPS every held field
   * edit (`entry.pending = {}`) because it exists to resolve a conflict about
   * those very edits. An override 412 is a conflict about something else entirely:
   * the reader may have unsent text in a run field box, and discarding it to
   * recover an override they have not recorded yet would be a second, larger loss.
   * This re-read touches nothing but the run this panel renders — the store keeps
   * its own token, and `useRunAutosave`'s `seedVersion` adopts the new one only
   * when the store is idle and empty, which is exactly the case in which adopting
   * is safe.
   *
   * NOTHING IS WRITTEN HERE, and the outcome says so: a re-read is not a retry,
   * and the override the 412 refused stays unrecorded until the reader records it.
   */
  const refreshRun = (row: OverrideRow) => {
    setRefreshing(row.address);
    setRefreshError(null);
    api
      .getRun(experimentId, run.id)
      .then((res) => {
        onRun(res.run);
        setFailure(null);
        setOutcome({ kind: 'refreshed', address: row.address });
        /*
         * TO THE RETRY THE COPY NAMES. The notice the reader activated has been
         * answered and unmounted; the form is still open, still holding their value
         * and their ticked confirmation, so "Record override" is the single next
         * act. If the failure came from the revert flow instead, its own confirm is
         * that act; if neither is open, the row's trigger is.
         */
        focusAfter(
          FOCUS_KEYS.formSubmit(row.address),
          FOCUS_KEYS.confirmRevert(row.address),
          FOCUS_KEYS.openTrigger(row.address),
        );
      })
      .catch((err: unknown) => {
        // The notice STAYS, because the 412 it reports is still true and still
        // unresolved. Saying the re-read failed is the honest addition; silently
        // doing nothing would make this the very control the finding warned about.
        setRefreshError(
          err instanceof Error
            ? err.message
            : 'This run could not be re-read. Nothing was written.',
        );
        focusAfter(FOCUS_KEYS.refresh(row.address), FOCUS_KEYS.failure(row.address));
      })
      .finally(() => setRefreshing(null));
  };

  const submitRevert = (row: OverrideRow) => {
    setBusy(row.address);
    setOutcome(null);
    setFailure(null);
    api
      .clearRunOverride(
        experimentId,
        run.id,
        { address: row.address, confirmedByUser: true },
        run.version,
      )
      .then((res) => {
        onRun(res.run);
        // `cleared: false` is a SUCCESS the contract defines — the address held no
        // override, nothing was written and the run did not advance. Reported as
        // what it is, so a reader is never told a removal happened that did not.
        setOutcome({
          kind: res.cleared ? 'reverted' : 'nothing-to-revert',
          address: row.address,
        });
        setReverting(null);
        /*
         * THE REVERT TRIGGER IS GONE — this is the one exit where the control the
         * reader started from cannot come back, because the row no longer holds an
         * override to revert. Focus goes to the row's remaining control, which now
         * reads "Override for this run · <path>" and states the new state by name.
         * And the ROW ITSELF can be gone: reverting at an address the record
         * carries nothing at drops it from `overrideRows`, so the panel is the
         * fallback rather than `<body>`.
         */
        focusAfter(FOCUS_KEYS.openTrigger(row.address));
      })
      .catch((err: unknown) => {
        setFailure(failFrom(row.address, err));
        // Same reasoning as the override submit: "Confirm revert" is disabled for the
        // whole round trip, so it is not a place to leave the reader.
        focusAfter(FOCUS_KEYS.failure(row.address), FOCUS_KEYS.confirmRevert(row.address));
      })
      .finally(() => setBusy(null));
  };

  return (
    <section
      className="run-inherited"
      aria-label="Values inherited from the record"
      /*
        FOCUSABLE ONLY PROGRAMMATICALLY. `tabIndex={-1}` keeps the panel out of the
        tab order — nothing about the sequential path through this card changes —
        and makes it a landing place for the one case where the control a reader
        came from no longer exists. It is a named region, so landing here announces
        "Values inherited from the record" rather than nothing at all.
      */
      tabIndex={-1}
      ref={sectionRef}
    >
      <p className="run-inherited-eyebrow">Inherited from the record</p>
      <p className="run-inherited-note">
        These values are entered once on the record and read live by every run that does
        not override them — nothing is copied into a run, so changing one on the record
        changes it here too. A run may hold its own value at one of these addresses
        instead; that is an override, and it is recorded on this run alone.
      </p>
      <ul className="run-inherited-list">
        {rows.map((row) => (
          <li
            className="run-inherited-row"
            key={row.address}
            data-state={row.state}
            data-address={row.address}
          >
            <div className="run-inherited-head">
              <span className="run-inherited-path">{row.path}</span>
              <span className="run-inherited-value">
                {row.text ?? (
                  <span className="run-inherited-novalue">
                    No value recorded on this run
                  </span>
                )}
              </span>
              <span className="run-inherited-state" data-state={row.state}>
                {row.state === 'overridden' ? (
                  <>
                    <Pencil size={12} strokeWidth={2.2} aria-hidden="true" />
                    Overridden on this run
                  </>
                ) : (
                  <>
                    <CornerDownRight size={12} strokeWidth={2.2} aria-hidden="true" />
                    Inherited from record
                  </>
                )}
              </span>
            </div>

            {/*
              THE SOURCE CONTEXT STAYS VISIBLE ON AN OVERRIDDEN ROW. Hiding the
              record's value once a run diverges would leave a reader unable to see
              WHAT was diverged from — and unable to notice that the record has since
              moved, which is the one fact `displaced_payload` exists to make
              visible.
            */}
            {row.state === 'overridden' && (
              <p className="run-inherited-source">
                {row.recordText !== null ? (
                  <>
                    The record currently says <span className="run-inherited-source-value">{row.recordText}</span>
                    {row.recordMovedSince && row.displacedText !== null && (
                      <>
                        {' '}
                        — it said <span className="run-inherited-source-value">{row.displacedText}</span> when this
                        override was recorded
                      </>
                    )}
                    .
                  </>
                ) : (
                  /*
                    TWO DIFFERENT FACTS, AND THIS USED TO STATE ONLY THE FIRST.
                    `valueText` returns `null` both for an address the record
                    carries nothing at AND for one carrying an object or an array,
                    which no row here can render in one line without making a claim
                    about its content. "Carries no value" is a false statement about
                    the second, so the row says whichever one holds. Latent rather
                    than live — every overridable `field:` address is `str`/`float`
                    server-side today — and kept because a latent false sentence is
                    still a false sentence, and the honest one costs a branch.
                  */
                  <>
                    {row.recordUnrenderable
                      ? 'The record carries a value at this address that this row cannot show in one line.'
                      : 'The record carries no value at this address.'}
                  </>
                )}
              </p>
            )}

            <div className="run-inherited-actions">
              {/*
                THE OPEN TRIGGER IS GATED ON THE SERVER'S `overridable`, and this is the
                one condition here that is not about local UI state. A row the route
                will not accept an override at gets no control offering one — because a
                control with exactly one possible outcome, `422 not_overridable`, is not
                an affordance, it is a trap. `field:system.domain` is the live instance:
                it is experiment-level (so it resolves, and its value is still shown
                here) but it is not in the backend's extractor map (so it can never be
                overridden).

                THE ROW ITSELF IS NOT SUPPRESSED. What the record carries at that
                address is real, inherited, and worth seeing; only the control that
                could not work is withheld. Removing the row would hide a value the run
                genuinely resolves.

                REVERT IS DELIBERATELY NOT GATED ON IT — see the next block. The two
                cannot disagree today, and if they ever did, the safe direction is to
                keep the control that REMOVES a recorded act, not the one that adds one.
              */}
              {editing !== row.address && row.overridable && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  ref={bindControl(FOCUS_KEYS.openTrigger(row.address))}
                  onClick={() => {
                    setReverting(null);
                    setOutcome(null);
                    setFailure(null);
                    setRefreshError(null);
                    setEditing(row.address);
                    // THE FORM IS REVEALED AND FOCUS FOLLOWS IT. This button is
                    // about to unmount; the box it revealed is what the reader
                    // asked for and what they must type into next.
                    focusAfter(FOCUS_KEYS.formInput(row.address));
                    /*
                     * THE BOX IS PREFILLED ONLY ON A ROW THAT IS ALREADY OVERRIDDEN,
                     * and the asymmetry is the no-guessing rule, not an inconsistency.
                     * On an INHERITED row the only value available to prefill with is
                     * the RECORD's, and putting a scientific value into a control the
                     * reader did not type it into is how an app comes to record a value
                     * nobody supplied. On an OVERRIDDEN row the value shown is this
                     * run's OWN — already entered and confirmed by a person — so
                     * showing it back is editing what is there, not suggesting
                     * something new. It is also what makes a re-record reachable at
                     * all, which is the case the route's idempotence exists for.
                     */
                    setText(row.state === 'overridden' ? (row.text ?? '') : '');
                    setConfirmed(false);
                    setEntryError(null);
                  }}
                >
                  {/*
                    THE ADDRESS IS APPENDED, NOT INTERPOLATED, and the order is a WCAG
                    2.5.3 (Label in Name) decision rather than a stylistic one. Fifteen
                    buttons reading "Override for this run" have fifteen identical
                    accessible names, so the address has to be in the name — but
                    splicing it into the middle ("Override sample.material.name for this
                    run") would leave the VISIBLE string no longer a contiguous
                    substring of the accessible one, which is exactly what 2.5.3
                    forbids and what breaks speech input ("click Override for this
                    run"). Appended after the visible text, both hold.
                  */}
                  {row.state === 'overridden' ? "Change this run's value" : 'Override for this run'}
                  <span className="sr-only"> · {row.path}</span>
                </button>
              )}
              {row.state === 'overridden' && reverting !== row.address && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  ref={bindControl(FOCUS_KEYS.revertTrigger(row.address))}
                  onClick={() => {
                    closeForm();
                    setOutcome(null);
                    setFailure(null);
                    setRefreshError(null);
                    setReverting(row.address);
                    // The confirmation this button revealed is the act it asked
                    // for, and it is the destructive one — a reader must reach it
                    // deliberately, not by tabbing back from `<body>`.
                    focusAfter(FOCUS_KEYS.confirmRevert(row.address));
                  }}
                >
                  Revert to inherited<span className="sr-only"> · {row.path}</span>
                </button>
              )}
            </div>

            {editing === row.address && (
              <OverrideForm
                row={row}
                text={text}
                onText={(next) => {
                  setText(next);
                  if (entryError !== null) setEntryError(null);
                }}
                confirmed={confirmed}
                onConfirmed={setConfirmed}
                error={entryError}
                busy={busy === row.address}
                onSubmit={() => submitOverride(row)}
                onCancel={() => {
                  closeForm();
                  // BACK WHERE THE READER WAS. Cancelling changes nothing, so the
                  // control that opened the form — which reappears in the same
                  // place, with the same name — is the honest destination.
                  focusAfter(FOCUS_KEYS.openTrigger(row.address));
                }}
                bindControl={bindControl}
              />
            )}

            {reverting === row.address && (
              <div className="run-inherited-confirm">
                {/*
                  THE SENTENCE IS THE DOMAIN'S, NOT A REASSURANCE. Reverting does not
                  restore the displaced value onto the run — it was never taken off
                  the record — and it does not leave a copy behind. The run holds
                  nothing there again and follows the record from now on.
                */}
                <p className="run-inherited-confirm-text">
                  Remove this run's own value at <span className="run-inherited-path-inline">{row.path}</span>? The
                  run will hold nothing there and will read the record's value live again, including
                  every later change to it.
                </p>
                <div className="run-inherited-confirm-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    ref={bindControl(FOCUS_KEYS.confirmRevert(row.address))}
                    onClick={() => submitRevert(row)}
                    disabled={busy === row.address}
                  >
                    {busy === row.address ? 'Reverting…' : 'Confirm revert'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      setReverting(null);
                      // Backing out changes nothing either, so focus returns to the
                      // control that opened this confirmation.
                      focusAfter(FOCUS_KEYS.revertTrigger(row.address));
                    }}
                    disabled={busy === row.address}
                  >
                    Keep the override
                  </button>
                </div>
              </div>
            )}

            {failure !== null && failure.address === row.address && (
              <FailureNotice
                failure={failure}
                path={row.path}
                bindControl={bindControl}
                onRefresh={() => refreshRun(row)}
                refreshing={refreshing === row.address}
                refreshError={refreshError}
              />
            )}
          </li>
        ))}
      </ul>

      {/*
        ONE LIVE REGION FOR THE PANEL, present in the tree before it has anything to
        say — a region added at the same moment it is populated is not reliably
        announced. It carries the address, because a panel with fifteen rows saying
        only "Recorded" names nothing.

        `aria-live="polite" aria-atomic="true"` RATHER THAN `role="status"`, and the
        choice is deliberate rather than a shortcut. The two are equivalent to a
        screen reader — `status` maps to exactly this pair — but the card ALREADY
        owns one `role="status"` for autosave, and a second one inside the same card
        makes "the card's status region" ambiguous to anything that addresses a card
        by role, including the existing tests that do. Two announcing regions about
        two different subjects is right; two regions answering to the same name is
        not. Nothing about what is announced, or when, changes.
      */}
      <p className="run-inherited-outcome" aria-live="polite" aria-atomic="true">
        {outcome !== null && <OutcomeText outcome={outcome} />}
      </p>
    </section>
  );
}

function OutcomeText({ outcome }: { outcome: Outcome }) {
  const path = outcome.address.replace(/^field:/, '');
  switch (outcome.kind) {
    case 'recorded':
      // The time is the SERVER's `recorded_utc` from this very response. It is shown
      // only here, for a write this browser just made, because the run read path does
      // not republish it — claiming it for an override merely read back would be
      // asserting a time nothing in the response carried.
      return (
        <>
          Override recorded for {path} on this run at {outcome.recordedUtc}. The record's own
          value is unchanged.
        </>
      );
    case 'unchanged':
      return (
        <>
          This run already held that value at {path}. Nothing was written and nothing changed.
        </>
      );
    case 'reverted':
      return (
        <>
          Override removed for {path}. This run reads the record's value again, live.
        </>
      );
    case 'nothing-to-revert':
      return <>There was no override at {path} to remove. Nothing was written.</>;
    case 'refreshed':
      // A RE-READ IS NOT A RETRY, and this sentence exists so the reader cannot
      // mistake one for the other: the run on screen is the server's again, and the
      // override the precondition refused is still not recorded.
      return (
        <>
          This run was re-read from the server. Nothing was written, and the override at{' '}
          {path} is still not recorded — record it again if you still want it.
        </>
      );
  }
}

function FailureNotice({
  failure,
  path,
  bindControl,
  onRefresh,
  refreshing,
  refreshError,
}: {
  failure: Failure;
  path: string;
  bindControl: (key: string) => (el: HTMLElement | null) => void;
  onRefresh: () => void;
  refreshing: boolean;
  refreshError: string | null;
}) {
  /*
   * `tabIndex={-1}` ON THE NOTICE, for the same reason the panel carries one: it is
   * a programmatic landing place, not a tab stop. The control that produced this
   * notice is disabled for the whole round trip, so the reader has to be put
   * somewhere when the answer arrives — the error-summary pattern puts them on the
   * message, with the remedy as the next thing in it.
   */
  const shell = {
    className: 'run-inherited-failure',
    role: 'alert',
    tabIndex: -1,
    ref: bindControl(FOCUS_KEYS.failure(failure.address)),
  } as const;
  if (failure.kind === 'stale') {
    return (
      <div {...shell}>
        <TriangleAlert size={14} strokeWidth={2.2} aria-hidden="true" />
        <div>
          {/*
            NOT A SUCCESS, AND NOT AMBIGUOUS. The route checks the precondition inside
            the same critical section as the write, so a 412 here means this override
            was not recorded — unlike the run autosave's retry case, nothing was ever
            handed to the server unanswered.

            THE REMEDY IS NAMED *AND* PRESENT, and it used to be only named. This copy
            said "Refresh this run to load the version the server holds" while the app's
            only refresh was `RunCard`'s, gated on an autosave conflict an override 412
            never causes: measured on the branch's own CAS scenario, zero refresh
            buttons and zero conflict banners were on screen, so every retry 412'd
            forever and only a full page reload recovered. The button below is that
            refresh — it re-reads the run, hands it up, and the retry can then succeed.
          */}
          <p className="run-inherited-failure-title">
            This run changed somewhere else — the override was not recorded.
          </p>
          <p className="run-inherited-failure-text">
            Nothing was written. Load the version the server holds, then record the override
            again if you still want it.
          </p>
          <div className="run-inherited-failure-actions">
            <button
              type="button"
              className="btn btn-secondary"
              ref={bindControl(FOCUS_KEYS.refresh(failure.address))}
              onClick={onRefresh}
              disabled={refreshing}
            >
              {refreshing ? 'Re-reading…' : 'Refresh this run'}
              {/* The address, appended — the same WCAG 2.5.3 ordering every other
                  control in this panel uses, and what tells this button apart from
                  the card-level "Refresh This Run" the autosave conflict owns. */}
              <span className="sr-only"> · {path}</span>
            </button>
          </div>
          {refreshError !== null && (
            // A control that fails silently is the defect this button was added to
            // remove, not a smaller version of it.
            <p className="run-inherited-failure-text">
              This run could not be re-read: {refreshError} Nothing was written.
            </p>
          )}
        </div>
      </div>
    );
  }
  if (failure.kind === 'error') {
    return (
      <div {...shell}>
        <TriangleAlert size={14} strokeWidth={2.2} aria-hidden="true" />
        <div>
          <p className="run-inherited-failure-title">The override could not be sent.</p>
          <p className="run-inherited-failure-text">{failure.message}</p>
        </div>
      </div>
    );
  }
  const { refusal } = failure;
  return (
    <div {...shell}>
      <TriangleAlert size={14} strokeWidth={2.2} aria-hidden="true" />
      <div>
        {/*
          THE SERVER'S OWN SENTENCE, VERBATIM. It names the address it refused and
          says what may be overridden instead — a generic "could not be saved" would
          drop exactly the part a scientist needs, and a paraphrase would be a second
          copy of a rule this client does not own.
        */}
        <p className="run-inherited-failure-title">
          {refusal.address !== undefined
            ? `This address cannot hold this override: ${refusal.address}`
            : 'The server refused this override.'}
        </p>
        <p className="run-inherited-failure-text">{refusal.message}</p>
        {refusal.findings.length > 0 && (
          <ul className="run-inherited-findings">
            {refusal.findings.map((finding) => (
              <li key={finding}>{finding}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function OverrideForm({
  row,
  text,
  onText,
  confirmed,
  onConfirmed,
  error,
  busy,
  onSubmit,
  onCancel,
  bindControl,
}: {
  row: OverrideRow;
  text: string;
  onText: (next: string) => void;
  confirmed: boolean;
  onConfirmed: (next: boolean) => void;
  error: string | null;
  busy: boolean;
  onSubmit: () => void;
  onCancel: () => void;
  /** Registers the two controls the panel moves focus to — see `FOCUS_KEYS`. */
  bindControl: (key: string) => (el: HTMLElement | null) => void;
}) {
  const inputId = `override-${row.path.replace(/[^A-Za-z0-9]/g, '-')}`;
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;
  const numeric = overrideValueKind(row.resolution) === 'number';
  return (
    <form
      className="run-inherited-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      {/*
        THE BOX STARTS EMPTY, and that is a no-guessing decision rather than a
        convenience one. Pre-filling it with the record's value would put a
        scientific value into a control the reader did not type it into, and a
        submit made without changing it would record an override asserting a value
        this app supplied. The record's value is shown BESIDE the box instead, as
        context.
      */}
      <label className="run-inherited-form-label" htmlFor={inputId}>
        This run's own value for <span className="run-inherited-path-inline">{row.path}</span>
      </label>
      <p className="run-inherited-form-context" id={hintId}>
        {row.recordText !== null ? (
          <>
            The record says <span className="run-inherited-source-value">{row.recordText}</span>.{' '}
          </>
        ) : (
          // The same two facts the row above distinguishes, in the form the reader
          // needs while entering a value: whether there is something there at all.
          <>
            {row.recordUnrenderable
              ? 'The record carries a value at this address that this row cannot show in one line. '
              : 'The record carries no value at this address. '}
          </>
        )}
        {numeric && 'The record holds a number here, so this is sent as a number. '}
        This records only that you entered this value on this run — it is not a check that
        the value is right.
      </p>
      <input
        id={inputId}
        className="run-input"
        ref={bindControl(FOCUS_KEYS.formInput(row.address))}
        type="text"
        inputMode={numeric ? 'decimal' : undefined}
        value={text}
        autoComplete="off"
        aria-invalid={error !== null || undefined}
        aria-describedby={error !== null ? `${hintId} ${errorId}` : hintId}
        onChange={(e) => onText(e.target.value)}
      />
      {error !== null && (
        <span className="run-field-error" id={errorId}>
          <TriangleAlert size={13} strokeWidth={2.2} aria-hidden="true" />
          {error}
        </span>
      )}
      {/*
        THE CONFIRMATION IS THE READER'S, NOT THE CLIENT'S. The operation refuses
        without `confirmed_by_user: true`, and this box is the only thing that sets
        it. It is not pre-ticked, and the submit stays disabled until it is: an
        override displaces a value the record supplied, and the contract makes that
        an explicitly confirmed act rather than a side effect of typing.
      */}
      <label className="run-inherited-form-confirm">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => onConfirmed(e.target.checked)}
        />
        I am recording this as this run's own value, in place of the record's.
      </label>
      <div className="run-inherited-form-actions">
        <button
          type="submit"
          className="btn btn-secondary"
          ref={bindControl(FOCUS_KEYS.formSubmit(row.address))}
          disabled={!confirmed || busy}
        >
          {busy ? 'Recording…' : 'Record override'}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <span className="run-inherited-form-revert-note">
          <RotateCcw size={12} strokeWidth={2.2} aria-hidden="true" />
          You can revert to the inherited value at any time.
        </span>
      </div>
    </form>
  );
}
