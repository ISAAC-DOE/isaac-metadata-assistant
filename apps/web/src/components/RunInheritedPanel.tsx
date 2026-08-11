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
 */

import { useState } from 'react';
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
  | { kind: 'nothing-to-revert'; address: string };

/** A write that did not happen, and the reason, as the server gave it. */
type Failure =
  | { kind: 'refused'; address: string; refusal: OverrideRefusal }
  | { kind: 'stale'; address: string }
  | { kind: 'error'; address: string; message: string };

const FALLBACK_REFUSAL =
  'The server refused this override and this build could not read its reason. Nothing was written.';

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
      })
      .catch((err: unknown) => setFailure(failFrom(row.address, err)))
      .finally(() => setBusy(null));
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
      })
      .catch((err: unknown) => setFailure(failFrom(row.address, err)))
      .finally(() => setBusy(null));
  };

  return (
    <section className="run-inherited" aria-label="Values inherited from the record">
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
                  <>The record carries no value at this address.</>
                )}
              </p>
            )}

            <div className="run-inherited-actions">
              {editing !== row.address && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => {
                    setReverting(null);
                    setOutcome(null);
                    setFailure(null);
                    setEditing(row.address);
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
                  onClick={() => {
                    closeForm();
                    setOutcome(null);
                    setFailure(null);
                    setReverting(row.address);
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
                onCancel={closeForm}
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
                    onClick={() => submitRevert(row)}
                    disabled={busy === row.address}
                  >
                    {busy === row.address ? 'Reverting…' : 'Confirm revert'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setReverting(null)}
                    disabled={busy === row.address}
                  >
                    Keep the override
                  </button>
                </div>
              </div>
            )}

            {failure !== null && failure.address === row.address && (
              <FailureNotice failure={failure} />
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
  }
}

function FailureNotice({ failure }: { failure: Failure }) {
  if (failure.kind === 'stale') {
    return (
      <div className="run-inherited-failure" role="alert">
        <TriangleAlert size={14} strokeWidth={2.2} aria-hidden="true" />
        <div>
          {/*
            NOT A SUCCESS, AND NOT AMBIGUOUS. The route checks the precondition inside
            the same critical section as the write, so a 412 here means this override
            was not recorded — unlike the run autosave's retry case, nothing was ever
            handed to the server unanswered. Refreshing the card is the remedy, and it
            is named rather than implied.
          */}
          <p className="run-inherited-failure-title">
            This run changed somewhere else — the override was not recorded.
          </p>
          <p className="run-inherited-failure-text">
            Nothing was written. Refresh this run to load the version the server holds, then
            record the override again if you still want it.
          </p>
        </div>
      </div>
    );
  }
  if (failure.kind === 'error') {
    return (
      <div className="run-inherited-failure" role="alert">
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
    <div className="run-inherited-failure" role="alert">
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
          <>The record carries no value at this address. </>
        )}
        {numeric && 'The record holds a number here, so this is sent as a number. '}
        This records only that you entered this value on this run — it is not a check that
        the value is right.
      </p>
      <input
        id={inputId}
        className="run-input"
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
        <button type="submit" className="btn btn-secondary" disabled={!confirmed || busy}>
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
