import './help.css';
import { useEffect, useId, useRef, useState } from 'react';
import { CircleHelp, X } from './icons';
import { LABELS } from '../lib/labels';

const WORKFLOW_STEPS: { label: string; text: string }[] = [
  { label: LABELS.stepDraft, text: 'extracts candidate field values from your files, each tagged with cited evidence.' },
  { label: LABELS.stepComplete, text: 'asks only the questions still blocking export — nothing more.' },
  { label: LABELS.stepExport, text: 'writes the official ISAAC record plus an evidence sidecar.' },
  { label: LABELS.stepValidate, text: 'checks the exported record against the official ISAAC v1.05 schema.' },
  { label: LABELS.stepAudit, text: 'confirms every field in the record still has evidence on file.' },
];

/**
 * Static, honest Help popover — explains only what this prototype actually
 * does (no chat, no fabricated features). Search IS real and lives in its own
 * ⌘K command palette (SearchDialog), separate from this panel. Anchored to the
 * Help button; hand-rolled (no dialog library) per project dependency discipline.
 */
export function HelpPanel() {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const headingId = useId();
  const wasOpen = useRef(false);

  // Escape + click-outside close while open.
  useEffect(() => {
    if (!open) return;

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    function onPointerDown(e: MouseEvent) {
      const target = e.target as Node;
      if (panelRef.current?.contains(target)) return;
      if (buttonRef.current?.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('mousedown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('mousedown', onPointerDown);
    };
  }, [open]);

  // Move focus into the panel on open; return it to the Help button on close.
  useEffect(() => {
    if (open) {
      panelRef.current?.focus();
    } else if (wasOpen.current) {
      buttonRef.current?.focus();
    }
    wasOpen.current = open;
  }, [open]);

  return (
    <div className="help-anchor">
      <button
        ref={buttonRef}
        type="button"
        className="icon-btn"
        aria-label="Help"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <CircleHelp size={16} strokeWidth={2} />
      </button>

      {open && (
        <div
          ref={panelRef}
          className="help-panel"
          role="dialog"
          aria-labelledby={headingId}
          tabIndex={-1}
        >
          <div className="help-panel-head">
            <h2 id={headingId} className="help-panel-title">
              Help
            </h2>
            <button
              type="button"
              className="help-panel-close"
              aria-label="Close help"
              onClick={() => setOpen(false)}
            >
              <X size={14} strokeWidth={2} />
            </button>
          </div>

          <div className="help-panel-body">
            <section className="help-section">
              <h3>How it works</h3>
              <ol className="help-steps">
                {WORKFLOW_STEPS.map((step) => (
                  <li key={step.label}>
                    <strong>{step.label}</strong> {step.text}
                  </li>
                ))}
              </ol>
            </section>

            <section className="help-section">
              <h3>No guessing</h3>
              <p>
                Fields are filled only from evidence or your explicit confirmation.
                &quot;I don&apos;t know&quot; is always a safe answer — a field with no support stays
                empty rather than being guessed.
              </p>
            </section>

            <section className="help-section">
              <h3>Three separate signals</h3>
              <p>
                <strong>{LABELS.evidenceAudit}</strong> is a deterministic evidence-coverage count.{' '}
                <strong>Official {LABELS.signalValidation}</strong> is the ISAAC v1.05 schema
                verdict — the only signal that gates export.{' '}
                <strong>{LABELS.signalAdvisory} review</strong> is AI consistency notes; it never
                blocks or authorizes anything.
              </p>
            </section>

            <section className="help-section">
              <h3>Synthetic mode</h3>
              <p>This prototype runs on synthetic demo data only — no real experiment data.</p>
            </section>

            <section className="help-section">
              <h3>Where evidence lives</h3>
              <p>
                Every field links to its evidence trail in the record. Exports write an evidence
                sidecar (<span className="mono">&lt;record&gt;.evidence.json</span>) beside the
                official record.
              </p>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
