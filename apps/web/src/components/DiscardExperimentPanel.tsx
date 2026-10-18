import './rename-experiment.css';
import '../screens/screens.css';
import { useEffect, useId, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronDown, ChevronRight, TriangleAlert } from './icons';
import { api, ApiError } from '../lib/api';
import { clearSession } from '../lib/assistantSession';
import { isExampleRecordId } from '../lib/exampleRecords';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { serverMessageOf, statusOf } from '../lib/mutationErrors';
import type { ApiExperimentDetail } from '../lib/types';

/**
 * DISCARD AN EXPERIMENT — the control `POST /api/experiments/{id}/discard` has been
 * waiting for since it shipped (B-08).
 *
 * ITS SHAPE IS `RenameExperimentPanel`'s AND `MoveExperimentPanel`'s, with ONE
 * deliberate departure. It is the same collapsed-on-arrival `.field-group` section as
 * its two siblings, so a scientist who never needs it pays one line for it. But where
 * the rename panel's own header argues AGAINST a modal ("four things to get right for
 * one text box"), this is the one control on the screen with no undo, and the
 * confirmation is a real dialog: `role="alertdialog"`, `aria-modal`, focus moved in on
 * open (to the SAFE button), Tab contained, Escape = keep, focus returned to the opener.
 * It reuses the `.artifact-modal` shell `ResetDemoDialog` uses and hand-rolls the
 * same containment, rather than introducing a shared hook for it (`QA-021`, declined
 * while one of the three dialogs is the destructive reset path).
 *
 * WHAT IS OFFERED, AND WHY NOT MORE OR LESS. The server decides what may be discarded
 * and refuses with a typed `409` and a `message` ending "Nothing was removed.". Two of
 * those refusals are visible to the client BEFORE a press — a built-in worked example
 * (a fixed, build-time id list) and a record that has already produced an official
 * record (`exported`) — so for those the control is replaced by the reason, not left as
 * a button that can only fail. The other four (submitted, an exported run, published
 * artifacts on disk, the database's own backstop) are facts about history and disk this
 * screen does not hold; for those the control is offered and the SERVER'S OWN MESSAGE
 * is shown verbatim when it refuses. A client-side guess at "submitted" would be a
 * second definition of a rule only the server can evaluate.
 *
 * THE PRECONDITION IS THE RECORD'S CURRENT TOKEN, and a 412 is handled exactly as the
 * rename panel handles it: the message stands, the confirm button stays disabled, and
 * the silent refresh (`onSaved`) re-reads the record, so the retry carries the new
 * token and the reader has seen what changed. `*` is never sent — the route refuses it.
 *
 * A SUCCESSFUL DISCARD NAVIGATES AWAY IMMEDIATELY. The record no longer exists, so any
 * further read of it is a 404; staying on the screen would let a poll race the removal
 * into a "Record Not Found" the reader never caused. The destination receives the title
 * in router state so it can say what happened — focus is otherwise lost with the dialog.
 */
export function DiscardExperimentPanel({
  detail,
  onSaved,
}: {
  detail: ApiExperimentDetail;
  /** The SILENT refetch — see `RenameExperimentPanel.onSaved`. Called after a stale-write
   *  refusal so the next attempt carries the current token. */
  onSaved: () => void;
}) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gone, setGone] = useState(false);
  /**
   * THE VERSION THE READER WAS LOOKING AT WHEN THEY OPENED THE DIALOG — and the only version
   * `confirm` may send. `detail` is refreshed silently while the dialog is open (a colleague's
   * rename, a newly added run), so sending `detail.version` at press time attached the
   * confirmation to a record the reader had not seen: measured, a rename over PATCH, the
   * dialog's title updated itself ~7 s later, Discard → 200. A drift marks the dialog stale
   * and a NEW confirmation (close, reopen, read) is required.
   */
  const [openedAt, setOpenedAt] = useState<string | null>(null);
  /** The server answered 412 to this dialog's confirmation. */
  const [sawStale, setSawStale] = useState(false);
  /** The server refused for a reason about the RECORD (a 409): retrying cannot succeed. */
  const [refused, setRefused] = useState(false);

  const firedRef = useRef(false); // synchronous single-submit guard (survives a double-click)
  const openRef = useRef<HTMLButtonElement>(null);
  const keepRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const wasOpen = useRef(false);
  const formId = useId();
  const titleId = `${formId}-title`;
  const bodyId = `${formId}-body`;
  const descId = `${formId}-desc`;
  const errorId = `${formId}-error`;

  const drifted = open && openedAt !== null && openedAt !== detail.version;
  const isStale = sawStale || drifted;
  const blockedReason = isExampleRecordId(detail.id)
    ? LABELS.discardBlockedExample
    : detail.exported || detail.record_id !== null
      ? LABELS.discardBlockedExported
      : null;

  // Focus: INTO the dialog on open (the safe button), BACK to the opener on close.
  useEffect(() => {
    if (open) {
      wasOpen.current = true;
      keepRef.current?.focus();
    } else if (wasOpen.current) {
      wasOpen.current = false;
      openRef.current?.focus();
    }
  }, [open]);

  const close = () => {
    if (busy) return;
    setOpen(false);
    setError(null);
    setGone(false);
  };

  // Escape = keep; Tab / Shift+Tab are contained. Document-level and capture-phase so the
  // keys are handled even in the render gap before focus has moved in.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        if (!busy) {
          setOpen(false);
          setError(null);
          setGone(false);
        }
        return;
      }
      if (e.key !== 'Tab') return;
      const modal = dialogRef.current;
      if (modal === null) return;
      const items = Array.from(
        modal.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (items.length === 0) {
        e.preventDefault();
        modal.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || active === modal || !modal.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !modal.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [open, busy]);

  const confirm = async () => {
    if (firedRef.current || isStale) return;
    firedRef.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await api.discardExperiment(detail.id, openedAt ?? detail.version);
      // The record is gone: drop the Assistant conversation grounded in it so a stale
      // transcript cannot outlive the thing it describes, then leave the screen.
      clearSession(detail.id);
      navigate(ROUTES.experiments, {
        state: {
          discarded: {
            title: result.discarded_title,
            runCount: result.discarded_run_count,
          },
        },
      });
    } catch (err) {
      firedRef.current = false;
      setBusy(false);
      const status = statusOf(err);
      if (status === 412) {
        setSawStale(true);
        setError(LABELS.discardStale);
        onSaved();
        return;
      }
      if (status === 404) {
        setGone(true);
        setError(LABELS.discardGone);
        return;
      }
      // THE SERVER'S OWN SENTENCE, verbatim, whenever a typed refusal carried one — it
      // names which of six reasons applies and ends "Nothing was removed.". A 4xx with
      // no message is still a refusal and says so; anything else (a network failure, a
      // 5xx the server did not explain) claims NEITHER outcome.
      // A 409 is a fact about the record (submitted, exported, …): the button stays off, and
      // the server's own sentence above it is the reason.
      if (status === 409) setRefused(true);
      const said = serverMessageOf(err);
      if (said !== undefined) setError(said);
      else if (err instanceof ApiError && !err.unreachable && status !== undefined && status < 500)
        setError(`${LABELS.discardRefusedPlain} (HTTP ${status})`);
      else setError(LABELS.discardUnknownOutcome);
    }
  };

  const shownError = error ?? (drifted ? LABELS.discardStale : null);
  const Chevron = expanded ? ChevronDown : ChevronRight;
  const runs = detail.run_count;

  return (
    <section className="field-group" aria-label={LABELS.discardSectionLabel}>
      <h2 className="fg-heading">
        <button
          type="button"
          className="fg-header"
          aria-expanded={expanded}
          aria-controls={expanded ? bodyId : undefined}
          onClick={() => setExpanded((isOpen) => !isOpen)}
        >
          <Chevron className="fg-chevron" size={16} strokeWidth={2} aria-hidden="true" />
          <span className="fg-block">{LABELS.discardSectionLabel}</span>
          <span className="record-section-summary record-section-value">
            {LABELS.discardSectionSummary}
          </span>
        </button>
      </h2>
      {expanded && (
        <div className="fg-body" id={bodyId}>
          <p className="rename-hint">{LABELS.discardIntro}</p>
          {blockedReason !== null ? (
            <p className="discard-blocked" role="note">
              {blockedReason}
            </p>
          ) : (
            <div className="rename-actions">
              <button
                ref={openRef}
                type="button"
                className="btn btn-danger-quiet"
                onClick={() => {
                  firedRef.current = false;
                  setError(null);
                  setGone(false);
                  setOpenedAt(detail.version);
                  setSawStale(false);
                  setRefused(false);
                  setOpen(true);
                }}
              >
                <TriangleAlert size={14} strokeWidth={2} aria-hidden="true" />
                {LABELS.discardAction}
              </button>
            </div>
          )}
        </div>
      )}

      {open && (
        <div className="artifact-modal-backdrop" onClick={close}>
          <div
            ref={dialogRef}
            className="artifact-modal discard-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={descId}
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="artifact-modal-head">
              <span id={titleId} className="artifact-modal-title">
                {LABELS.discardDialogTitle}
              </span>
            </div>
            <div className="discard-dialog-body" id={descId}>
              {/* The record is NAMED, as text, so the reader sees which one this is. */}
              <p className="discard-dialog-record">
                <strong>{detail.title}</strong>
                {runs > 0 && (
                  <span className="discard-dialog-runs">
                    {' '}
                    — {runs} run{runs === 1 ? '' : 's'}
                  </span>
                )}
              </p>
              <p className="reset-disclosure">{LABELS.discardWhatGoes}</p>
              <p className="reset-disclosure">{LABELS.discardWhatStays}</p>
              {shownError !== null && (
                <p className="discard-dialog-error" id={errorId} role="alert">
                  {shownError}
                  {gone && (
                    <>
                      {' '}
                      <Link to={ROUTES.experiments}>{LABELS.discardBackToExperiments}</Link>
                    </>
                  )}
                </p>
              )}
            </div>
            <div className="reset-dialog-actions">
              <button
                ref={keepRef}
                type="button"
                className="btn btn-secondary"
                onClick={close}
                disabled={busy}
              >
                {LABELS.discardKeep}
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={confirm}
                disabled={busy || isStale || gone || refused}
              >
                {busy ? LABELS.discardPending : LABELS.discardConfirm}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
