/*
 * P26.0b · Reset Worked Example — the guarded control for the built-in examples.
 *
 * SCOPE, first, because it changed and everything else follows from it. These five
 * example records exist ONLY inside a worked-example session, one independent copy
 * per session, and `POST /api/demo/reset` now REQUIRES the session header and
 * refuses without it. So this control renders only inside the persistent
 * worked-example bar (`components/TutorialSessionBar.tsx`), it can only ever affect
 * that one session's copies, and it can never touch the ordinary workspace — not
 * because it checks, but because the request it issues addresses a directory
 * namespace that contains nothing else. It is NOT rendered on My Experiments, where
 * it had become a control that looks like it acts and does not.
 *
 * Fail-closed: the whole control renders ONLY when GET /api/health reports the
 * authoritative synthetic-only mode. It is a restrained *destructive* action, not
 * the page primary. Opening the modal PREVIEWS (never mutates) via
 * POST /api/demo/reset {mode:'preview'}, shows the typed counts + a derived summary
 * of the confirmed work at risk + a plain-language disclosure, and gates execution
 * behind a typed "RESET". Execution sends the exact backend phrase exactly once,
 * then announces the rebuild so any surface showing workspace-derived data refetches
 * it. An ambiguous/refused preview disables execution permanently with no bypass.
 * The UI never authorizes a reset — every count and decision is server-derived.
 *
 * R1 — THE PRECONDITION, and why the UI part of it matters. This dialog is exactly
 * the gap the `plan_digest` closes: the operator reads a classification, thinks, and
 * presses the button some seconds later. The preview's digest is carried into the
 * execute, so if anything changed in between the server refuses (412/428) and writes
 * nothing.
 *
 * What this component must therefore NEVER do is present a retry as a formality. A
 * stale refusal RE-PREVIEWS (read-only), shows the refreshed figures, and CLEARS the
 * typed gate, so a second attempt requires the operator to read the new numbers and
 * arm the action again. Auto-retrying with a fresh digest would reinstate the exact
 * defect — a reset the operator authorised against figures that no longer applied.
 */

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { api, RESET_CONFIRMATION } from '../lib/api';
import { clearAllSessions } from '../lib/assistantSession';
import { notifyWorkspaceRebuilt } from '../lib/workspaceInvalidation';
import { useFetch } from '../lib/useFetch';
import { LABELS } from '../lib/labels';
import { TriangleAlert } from './icons';
import type { ApiDemoResetAtRisk, ApiDemoResetResult } from '../lib/types';

/** The short phrase the operator types to arm the destructive action (not the
 *  backend phrase — that is sent internally, never surfaced or auto-filled). */
const TYPED_GATE = 'RESET';

type Preview =
  | { status: 'loading' }
  | { status: 'data'; data: ApiDemoResetResult }
  | { status: 'error' };

/** `stale` is the R1 precondition refusal (412/428): nothing was written, and the
 *  remedy is to re-read refreshed figures — NOT to press the same button again. */
type ExecuteState = 'idle' | 'pending' | 'done' | 'refused' | 'stale' | 'error';

/**
 * The at-risk sentence, built ONLY from the server's derived counts.
 *
 * Every clause names a real number. There is deliberately no "some", no "may", and
 * no softening: a disclosure whose whole purpose is to stop an accidental loss must
 * not hedge the size of the loss. When all three counts are zero the sentence says
 * so outright rather than being omitted — silence would read as "not calculated".
 */
export function atRiskSentence(at: ApiDemoResetAtRisk | undefined): string {
  if (!at) return '';
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const parts: string[] = [];
  if (at.confirmed_answers > 0) {
    parts.push(plural(at.confirmed_answers, 'confirmed answer', 'confirmed answers'));
  }
  if (at.examples_with_progress > 0) {
    parts.push(
      `${plural(at.examples_with_progress, 'built-in example', 'built-in examples')} carrying progress`,
    );
  }
  if (at.exported_artifacts > 0) {
    parts.push(plural(at.exported_artifacts, 'record you exported', 'records you exported'));
  }
  if (parts.length === 0) return LABELS.resetAtRiskNothing;
  const listed =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
  return `${listed}. Resetting discards ${parts.length === 1 ? 'it' : 'them'} permanently.`;
}

export function ResetDemoDialog() {
  // Fail-closed synthetic-only gate (authoritative, from GET /api/health).
  const health = useFetch(() => api.health(), []);
  const synthetic = health.status === 'data' && health.data.mode === 'synthetic-only';

  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<Preview>({ status: 'loading' });
  const [confirmText, setConfirmText] = useState('');
  const [executeState, setExecuteState] = useState<ExecuteState>('idle');
  /** A re-preview is in flight over an already-open dialog (after a stale refusal). */
  const [refreshing, setRefreshing] = useState(false);

  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const firedRef = useRef(false); // single-submit guard (sync, survives double-click)
  const wasOpenRef = useRef(false);
  const titleId = useId();
  const inputId = useId();

  // The dialog surface is only mounted once the preview has settled — the spec's
  // "show a loading state, then the counts". Until then a lightweight, non-dialog
  // loading backdrop is shown (so the counts are present the moment role=dialog is).
  const settled = preview.status !== 'loading';
  const dialogOpen = open && settled;

  const refused =
    preview.status === 'data' &&
    (preview.data.status === 'refused' || preview.data.ambiguous_count > 0);

  /**
   * Re-run the (read-only) preview.
   *
   * `refresh` deliberately does NOT drop back to the `loading` state: that would
   * unmount the dialog (see `dialogOpen` below), throw focus back to the trigger,
   * and flash away the very explanation the operator needs to read. The figures
   * update in place and the action stays disabled while they do.
   */
  const runPreview = useCallback((kind: 'initial' | 'refresh' = 'initial') => {
    if (kind === 'initial') setPreview({ status: 'loading' });
    else setRefreshing(true);
    return api
      .resetDemo('preview')
      .then((data) => setPreview({ status: 'data', data }))
      .catch(() => setPreview({ status: 'error' }))
      .finally(() => setRefreshing(false));
  }, []);

  const openDialog = () => {
    firedRef.current = false;
    setConfirmText('');
    setExecuteState('idle');
    setRefreshing(false);
    setOpen(true);
    void runPreview('initial');
  };

  const closeDialog = useCallback(() => setOpen(false), []);

  const doExecute = () => {
    if (firedRef.current) return; // already fired (guards double-click)
    if (preview.status !== 'data') return;
    if (refused) return; // ambiguous/refused → no bypass, ever
    if (confirmText !== TYPED_GATE) return; // typed gate not armed
    firedRef.current = true;
    setExecuteState('pending');
    // The digest comes from THIS dialog's own preview — never from a constant, a
    // cache, or a value the client made up. If the workspace has moved, the server
    // refuses and nothing is written.
    api
      .resetDemo('execute', RESET_CONFIRMATION, preview.data.plan_digest)
      .then((res) => {
        if (res.status === 'ok') {
          // P29.4 — the workspace was rebuilt, so every ephemeral assistant
          // session (conversation + staged proposals) is now grounded in records
          // that no longer exist. Clear them all so a stale proposal can never be
          // confirmed after a reset, and no prior conversation leaks into the
          // fresh built-in examples.
          clearAllSessions();
          setExecuteState('done');
          // The record set was rebuilt on the server, so every surface showing
          // workspace-derived data must re-read it. Announced rather than called
          // directly: this control is chrome now and owns no list of its own.
          notifyWorkspaceRebuilt();
          closeDialog();
        } else if (
          res.refusal_reason === 'plan_digest_stale' ||
          res.refusal_reason === 'plan_digest_required'
        ) {
          // R1 — the precondition refused and NOTHING was written. Re-preview so the
          // operator sees the current figures, and clear the typed gate so they must
          // arm the action again deliberately. Do NOT retry: the approval they gave
          // was for figures that no longer apply.
          setExecuteState('stale');
          setConfirmText('');
          firedRef.current = false; // a NEW, re-armed attempt is allowed
          void runPreview('refresh');
        } else {
          // A different safe backend refusal (ambiguous record, wrong mode). No bypass.
          setExecuteState('refused');
        }
      })
      .catch(() => {
        // Network / unexpected status. Nothing was written; show a safe message.
        setExecuteState('error');
      });
  };

  // Move focus into the dialog on open; return it to the trigger on close.
  useEffect(() => {
    if (dialogOpen) {
      dialogRef.current?.focus();
      wasOpenRef.current = true;
    } else if (wasOpenRef.current) {
      triggerRef.current?.focus();
      wasOpenRef.current = false;
    }
  }, [dialogOpen]);

  // Escape closes; Tab / Shift+Tab are trapped within the dialog (hand-rolled
  // containment). Capture phase so the dialog handles the keys first.
  useEffect(() => {
    if (!dialogOpen) return;
    const modal = dialogRef.current;
    if (!modal) return;

    const focusable = () =>
      Array.from(
        modal.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])',
        ),
      );

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        closeDialog();
        return;
      }
      if (e.key !== 'Tab') return;
      const items = focusable();
      if (items.length === 0) {
        e.preventDefault();
        modal!.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || active === modal || !modal!.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [dialogOpen, closeDialog]);

  if (!synthetic) return null; // fail-closed: hidden unless authoritatively synthetic

  const data = preview.status === 'data' ? preview.data : null;
  const armed = confirmText === TYPED_GATE;
  const actionDisabled =
    refused ||
    !armed ||
    preview.status !== 'data' ||
    executeState === 'pending' ||
    // The figures are mid-refresh after a stale refusal: nothing may be authorised
    // against numbers that are about to change.
    refreshing;

  return (
    <>
      <button
        type="button"
        ref={triggerRef}
        className="btn btn-danger-quiet"
        onClick={openDialog}
      >
        <TriangleAlert size={14} strokeWidth={2} aria-hidden="true" />
        {LABELS.actionResetDemo}
      </button>

      {open && !settled && (
        <div className="artifact-modal-backdrop" aria-hidden="true">
          <div className="reset-loading card">Loading reset preview…</div>
        </div>
      )}

      {dialogOpen && (
        <div className="artifact-modal-backdrop" onClick={closeDialog}>
          <div
            ref={dialogRef}
            className="artifact-modal reset-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="artifact-modal-head">
              <span id={titleId} className="artifact-modal-title">
                {LABELS.resetDialogTitle}
              </span>
            </div>

            <div className="reset-dialog-body">
              <p className="reset-disclosure">
                {/*
                 * TWO CORRECTIONS ARE RECORDED IN THIS COPY, not one.
                 *
                 * 1. "shared, hosted example workspace" was true of the single
                 *    ordinary workspace the examples used to live in. It is FALSE of a
                 *    worked-example session: each session is its own directory and two
                 *    sessions are mutually invisible, so nothing another reader does
                 *    can appear here and nothing done here can appear to them. Saying
                 *    "shared" would over-state the blast radius in one direction and
                 *    under-state the privacy of the scope in the other. What IS true
                 *    and matters more is that the scope is temporary.
                 *
                 * 2. HISTORY of the last clause, kept: a positive whole-content claim
                 *    was tried here ("this workspace is built only from committed
                 *    example files") and it was false, because a confirmed answer or an
                 *    edit is persisted into the record's workspace state, so the
                 *    workspace also holds what users store. It was replaced with a MODE
                 *    claim, which the control is already gated on, plus two
                 *    independently checkable facts. That structure is unchanged.
                 */}
                This is a <strong>temporary worked-example workspace</strong>, belonging to this
                walkthrough alone. Resetting discards the current progress on the built-in
                examples in it and restores all five to their original state. Nothing in My
                Experiments is in this scope. Real data is unaffected — this workspace runs in
                synthetic-only mode: the examples come from committed files and every upload is
                refused.
              </p>

              {preview.status === 'error' && (
                <p className="reset-refused" role="note">
                  The preview could not be loaded from the backend. Nothing was changed.
                </p>
              )}

              {/*
                * R1 — the DERIVED at-risk disclosure, placed ABOVE the count table
                * on purpose. The counts answer "how many records", which is not the
                * question an operator about to lose an afternoon is asking. This
                * answers "what of mine goes away", with server-computed numbers.
                * `aria-live` because it is re-computed in place after a stale
                * refusal, and a screen-reader user must hear the new figure rather
                * than discover it by re-reading.
                */}
              {data && (
                <p className="reset-at-risk" role="note" aria-live="polite">
                  <strong>{LABELS.resetAtRiskLabel}:</strong>{' '}
                  {atRiskSentence(data.at_risk)}
                </p>
              )}

              {data && (
                <dl className="reset-counts">
                  <div className="reset-count-row">
                    <dt>{LABELS.resetCountCurrent}</dt>
                    <dd>{' '}{data.previous_count}{' '}</dd>
                  </div>
                  <div className="reset-count-row">
                    <dt>{LABELS.resetCountCanonical}</dt>
                    <dd>{' '}{data.canonical_count}{' '}</dd>
                  </div>
                  <div className="reset-count-row">
                    <dt>{LABELS.resetCountLegacy}</dt>
                    <dd>{' '}{data.legacy_count}{' '}</dd>
                  </div>
                  <div className="reset-count-row">
                    <dt>{LABELS.resetCountAmbiguous}</dt>
                    <dd>{' '}{data.ambiguous_count}{' '}</dd>
                  </div>
                  <div className="reset-count-row reset-count-final">
                    <dt>{LABELS.resetCountFinal}</dt>
                    <dd>{' '}{data.final_count}{' '}</dd>
                  </div>
                </dl>
              )}

              {refused && (
                <p className="reset-refused" role="note">
                  This reset was <strong>refused for safety</strong> because an ambiguous record
                  is present. No records were changed, and the reset stays disabled.
                </p>
              )}

              {/*
                * R1 — the precondition refusal. It is NOT an error and NOT the
                * ambiguous refusal: nothing was written, the operator did nothing
                * wrong, and the way forward is to read the refreshed figures above
                * and confirm again. There is deliberately no "Try again" button —
                * the destructive action below is the only way forward, and it is
                * disarmed until the gate is re-typed.
                */}
              {executeState === 'stale' && (
                <p className="reset-refused" role="alert">
                  <strong>{LABELS.resetStaleTitle}.</strong> {LABELS.resetStaleBody}
                </p>
              )}

              {executeState === 'refused' && (
                <p className="reset-refused" role="note">
                  The backend refused the reset for safety. No records were changed.
                </p>
              )}
              {executeState === 'error' && (
                <p className="reset-refused" role="note">
                  The reset could not be completed. No records were changed.
                </p>
              )}

              <div className="reset-confirm-field">
                <label htmlFor={inputId} className="reset-confirm-label">
                  Type {TYPED_GATE} to confirm this destructive reset
                </label>
                <input
                  id={inputId}
                  type="text"
                  className="input input-mono"
                  autoComplete="off"
                  value={confirmText}
                  disabled={refused}
                  aria-label={`Type ${TYPED_GATE} to confirm this destructive reset`}
                  onChange={(e) => setConfirmText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      doExecute(); // guarded: a non-matching phrase never executes
                    }
                  }}
                />
              </div>
            </div>

            <div className="reset-dialog-actions">
              <button type="button" className="btn btn-secondary" onClick={closeDialog}>
                {LABELS.actionCancel}
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={actionDisabled}
                onClick={doExecute}
              >
                {LABELS.resetConfirmAction}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
