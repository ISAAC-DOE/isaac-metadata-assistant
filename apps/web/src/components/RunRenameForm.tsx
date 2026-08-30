import { useEffect, useId, useRef, useState } from 'react';
import { api } from '../lib/api';
import { LABELS } from '../lib/labels';
import { mutationFailureCopy, statusOf } from '../lib/mutationErrors';
import type { ApiRunView } from '../lib/types';

/**
 * RENAME ONE RUN — the backend that had no control.
 *
 * `PATCH /api/experiments/{id}/runs/{run_id}` has always documented itself as writing
 * a run's fields "and optionally renaming it", and `api.updateRun`'s body type has
 * carried `label?: string` for as long as it has existed. Measured before this
 * component: NEITHER caller passed it. `lib/runAutosaveStore.ts` sends `{ fields }`,
 * and `TranscriptCapturePanel` sends `{ fields }`. So the capability was reachable
 * only by a person writing the request by hand, and a run named `Run 3` by the
 * server — which is what every run added through this screen is called until somebody
 * says otherwise — could never be given the name of the condition it measured.
 *
 * MEASURED, NOT ASSUMED, over HTTP on a created record with one run:
 *
 *     PATCH …/runs/{id}  {"confirmed_by_user": true, "fields": {}, "label": "300 K"}
 *       -> 200, run.label == "300 K", run.rev 1 -> 2
 *     label ""      -> 422 invalid_label   ("label must not be blank")
 *     label "   "   -> 422 invalid_label
 *     label 7       -> 422 invalid_label   ("label must be a string")
 *     no label, {}  -> 422 unrecognized_field
 *
 * So an empty `fields` map plus a label is an accepted request, and a blank name is
 * refused rather than stored — which is why this form refuses one before sending
 * instead of letting the reader discover it as a server error.
 *
 * NO LENGTH LIMIT IS STATED, and that is a measurement rather than an omission. The
 * route declares none: a 500-character label was accepted and stored verbatim. The
 * experiment rename panel states its limit because `RenameExperimentRequest` declares
 * `max_length`; stating one here would be inventing a rule the server does not have.
 *
 * THE `If-Match` IS THE RUN'S, NOT THE RECORD'S. `api.updateRun`'s own header records
 * this trap: creating a run rewrites the record and takes the record's token, while
 * editing one takes the run's. Sending the wrong one is a 412 the reader would be told
 * to fix by refreshing something that was never stale.
 *
 * A 412 IS NEVER TURNED INTO A SILENT OVERWRITE. The refusal means the run moved and
 * nothing was written; the form keeps the reader's text, says so, and offers the card's
 * existing `Refresh This Run` — the same control and the same words the autosave
 * conflict block already uses. It deliberately does not re-send with the server's
 * `current_version`: that would apply a name to a run whose current state the reader
 * has not seen.
 *
 * IT REUSES `mutationFailureCopy`, so an expired session reads as an expired session
 * here exactly as it does at every other write in the app, rather than as "the name
 * could not be saved".
 */
export function RunRenameForm({
  experimentId,
  run,
  onRun,
  onRefresh,
  refreshing = false,
}: {
  experimentId: string;
  run: ApiRunView;
  /** Adopt the run the server returned, so the card's label and version both move. */
  onRun: (run: ApiRunView) => void;
  /**
   * Re-read this run from the server. Offered only on a 412, and it is the card's
   * OWN refresh (`useRunAutosave().refresh`) rather than a second reader — a second
   * one would be a second opinion about what the run currently holds.
   */
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState(run.label);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  /**
   * The run version a 412 was returned FOR — the same device `RenameExperimentPanel`
   * uses, for the same reason. Clearing the refusal on the next keystroke would hide
   * a refusal that is still true, because the client still holds exactly the validator
   * that was rejected; the next Save would be refused again and the message would
   * flicker. It retires when a DIFFERENT run version arrives, which is the condition
   * under which a retry can actually succeed.
   */
  const [staleAt, setStaleAt] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const openRef = useRef<HTMLButtonElement>(null);
  const returning = useRef(false);

  const baseId = useId();
  const labelId = `${baseId}-label`;
  const errorId = `${baseId}-error`;
  const statusId = `${baseId}-status`;

  const isStale = staleAt !== null && staleAt === run.version;

  /* Focus follows the form in both directions. Written as an effect and not as a
     `.focus()` inside the handlers because at the moment Cancel runs the opener does
     not exist yet — see `RenameExperimentPanel`, which paid for this first. */
  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
    } else if (returning.current) {
      returning.current = false;
      openRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (staleAt !== null && staleAt !== run.version) {
      setStaleAt(null);
      setError((current) => (current === LABELS.runRenameStale ? null : current));
    }
  }, [run.version, staleAt]);

  const close = () => {
    returning.current = true;
    setOpen(false);
    setError(null);
  };

  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    if (busy) return;
    const trimmed = label.trim();
    if (!trimmed) {
      /* Checked here as well as at the server, because the server's answer would be a
         round trip for a condition this form can already see. The server refuses a
         blank label with `422 invalid_label` regardless of what this renders. */
      setError(LABELS.runRenameRequired);
      inputRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      /* `fields: {}` names no field, so this request writes the label and nothing
         else. It is not a shortcut: the route refuses a body that names neither a
         field nor a label with `422 unrecognized_field`, and a label alone is a
         request it accepts. */
      const response = await api.updateRun(
        experimentId,
        run.id,
        { fields: {}, label: trimmed },
        run.version,
      );
      setBusy(false);
      setSaved(true);
      setStaleAt(null);
      close();
      onRun(response.run);
    } catch (err) {
      setBusy(false);
      if (statusOf(err) === 412) {
        /* THE ONE NAMED CAUSE, read from the status rather than inferred. The form
           stays open holding the reader's text; nothing was written. */
        setStaleAt(run.version);
        setError(LABELS.runRenameStale);
        return;
      }
      setError(mutationFailureCopy(err, LABELS.runRenameFailed));
    }
  };

  return (
    <div className="run-rename">
      {/* ALWAYS MOUNTED, empty when there is nothing to say: a live region inserted
          together with its content is announced unreliably, and this is the one place
          the reader is told the rename actually landed. */}
      <p className="run-rename-status" id={statusId} role="status">
        {saved ? LABELS.runRenameSaved : ''}
      </p>
      {open ? (
        <form className="run-rename-form" onSubmit={submit}>
          <label className="run-field-label" htmlFor={labelId}>
            {LABELS.runRenameLabel}
          </label>
          <div className="run-rename-controls">
            <input
              ref={inputRef}
              id={labelId}
              className="run-input"
              type="text"
              value={label}
              required
              aria-invalid={error !== null || undefined}
              aria-describedby={error !== null ? errorId : undefined}
              onChange={(e) => {
                setLabel(e.target.value);
                // A stale-write refusal is NOT cleared by typing — the held validator
                // is still the rejected one. Every other error is the reader's to fix
                // in the box, so it goes as soon as they start.
                if (error !== null && !isStale) setError(null);
              }}
            />
            <button type="submit" className="btn btn-primary" disabled={busy || isStale}>
              {busy ? LABELS.runRenameSaving : LABELS.runRenameSubmit}
            </button>
            <button type="button" className="btn btn-secondary" onClick={close} disabled={busy}>
              {LABELS.renameCancel}
            </button>
          </div>
          {error !== null && (
            <p className="run-rename-error" id={errorId} role="alert">
              <span>{error}</span>
              {isStale && onRefresh && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={onRefresh}
                  disabled={refreshing}
                >
                  {refreshing ? 'Refreshing…' : 'Refresh This Run'}
                </button>
              )}
            </p>
          )}
        </form>
      ) : (
        <>
          {/*
            THE CURRENT NAME IS NOT REPEATED HERE, and that is a correction rather than
            an omission. A first version rendered it as its own line, which put the run's
            label on the card for a THIRD time — the card header, this section's own
            `currently …` summary, and here — and broke three existing specs that reach a
            card by `getByText(run.label)`. Those specs are right: a name that appears
            three times in one card is three things a reader has to reconcile, and
            weakening them to `getAllByText` would have hidden the duplication rather than
            removed it. The section summary carries the current name, and the box below is
            pre-filled with it.
          */}
          <p className="run-rename-hint">{LABELS.runRenameHint}</p>
          <button
            ref={openRef}
            type="button"
            className="btn btn-secondary"
            /* The accessible name carries the run, exactly as Focus, Compare and
               Remove do on this card: fifty cards each offering a control called
               "Rename" is fifty identically named controls in a screen reader's list.
               It CONTAINS the visible word, so WCAG 2.5.3 still holds. */
            aria-label={`Rename run ${run.label}`}
            onClick={() => {
              setLabel(run.label);
              setError(null);
              setSaved(false);
              setOpen(true);
            }}
          >
            {LABELS.actionRenameRun}
          </button>
        </>
      )}
    </div>
  );
}
