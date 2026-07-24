/*
 * P26.0b · Reset Demo — the guarded control for the shared synthetic workspace.
 *
 * Fail-closed: the whole control renders ONLY when GET /api/health reports the
 * authoritative synthetic-only mode. It is a restrained *destructive* action, not
 * the page primary. Opening the modal PREVIEWS (never mutates) via
 * POST /api/demo/reset {mode:'preview'}, shows the typed counts + a plain-language
 * disclosure, and gates execution behind a typed "RESET". Execution sends the exact
 * backend phrase exactly once, then refreshes the list from the backend. An
 * ambiguous/refused preview disables execution permanently with no bypass. The UI
 * never authorizes a reset — every count and decision is server-derived.
 */

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { api, RESET_CONFIRMATION } from '../lib/api';
import { clearAllSessions } from '../lib/assistantSession';
import { useFetch } from '../lib/useFetch';
import { LABELS } from '../lib/labels';
import { TriangleAlert } from './icons';
import type { ApiDemoResetResult } from '../lib/types';

/** The short phrase the operator types to arm the destructive action (not the
 *  backend phrase — that is sent internally, never surfaced or auto-filled). */
const TYPED_GATE = 'RESET';

type Preview =
  | { status: 'loading' }
  | { status: 'data'; data: ApiDemoResetResult }
  | { status: 'error' };

type ExecuteState = 'idle' | 'pending' | 'done' | 'refused' | 'error';

export function ResetDemoDialog({ onResetComplete }: { onResetComplete: () => void }) {
  // Fail-closed synthetic-only gate (authoritative, from GET /api/health).
  const health = useFetch(() => api.health(), []);
  const synthetic = health.status === 'data' && health.data.mode === 'synthetic-only';

  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<Preview>({ status: 'loading' });
  const [confirmText, setConfirmText] = useState('');
  const [executeState, setExecuteState] = useState<ExecuteState>('idle');

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

  const openDialog = () => {
    firedRef.current = false;
    setConfirmText('');
    setExecuteState('idle');
    setPreview({ status: 'loading' });
    setOpen(true);
    api
      .resetDemo('preview')
      .then((data) => setPreview({ status: 'data', data }))
      .catch(() => setPreview({ status: 'error' }));
  };

  const closeDialog = useCallback(() => setOpen(false), []);

  const doExecute = () => {
    if (firedRef.current) return; // already fired (guards double-click)
    if (preview.status !== 'data') return;
    if (refused) return; // ambiguous/refused → no bypass, ever
    if (confirmText !== TYPED_GATE) return; // typed gate not armed
    firedRef.current = true;
    setExecuteState('pending');
    api
      .resetDemo('execute', RESET_CONFIRMATION)
      .then((res) => {
        if (res.status === 'ok') {
          // P29.4 — the demo state was rebuilt, so every ephemeral assistant
          // session (conversation + staged proposals) is now grounded in records
          // that no longer exist. Clear them all so a stale proposal can never be
          // confirmed after a reset, and no prior conversation leaks into the
          // fresh canonical scenarios.
          clearAllSessions();
          setExecuteState('done');
          onResetComplete(); // re-fetch the list from the backend
          closeDialog();
        } else {
          // A safe backend refusal (e.g. state changed under us). No bypass.
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
    refused || !armed || preview.status !== 'data' || executeState === 'pending';

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
                This is a <strong>shared, hosted synthetic workspace</strong>. Resetting
                removes the current synthetic demo progress and recreates the five canonical
                scenarios. Real data is unaffected — this workspace is synthetic-only.
              </p>

              {preview.status === 'error' && (
                <p className="reset-refused" role="note">
                  The preview could not be loaded from the backend. Nothing was changed.
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
