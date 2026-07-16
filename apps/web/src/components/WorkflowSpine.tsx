import './workflow.css';
import { Link } from 'react-router-dom';
import { Check, Pencil, Lock } from './icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import type { SpineStep } from '../lib/types';

interface WorkflowSpineProps {
  steps: SpineStep[];
  /** The record id, so already-reached steps (done/active) can link back to their
   * surface. Omitted where there is no record context — then no step navigates. */
  recordId?: string;
}

// Only these gates are standalone destinations. Validate/Audit are read-outs
// shown within the export/record surfaces, not routes of their own, so they
// never become links even when active.
const STEP_ROUTE: Record<string, ((id: string) => string) | undefined> = {
  draft: ROUTES.record,
  complete: ROUTES.complete,
  export: ROUTES.export,
};

/**
 * The gated pipeline (Draft → Complete → Export → Validate → Audit) showing the
 * current blocking gate. Locked steps are not clickable — forward motion is
 * earned by resolving gates, never by dismissing them. No "skip"/"export anyway".
 * Steps already reached (done/active) link back to their surface so a reviewer is
 * never stranded; locked future steps stay non-interactive and semantically locked.
 */
export function WorkflowSpine({ steps, recordId }: WorkflowSpineProps) {
  return (
    <nav className="spine" aria-label="Workflow pipeline">
      <div className="spine-eyebrow eyebrow">{LABELS.workflowEyebrow}</div>
      <ol className="spine-steps">
        {steps.map((step) => {
          const route = STEP_ROUTE[step.key];
          // Never link a locked (future) gate — gating is preserved by keeping
          // forward steps non-interactive. Done/active steps with a real route
          // become links back to that surface.
          const href =
            recordId && route && step.state !== 'locked' ? route(recordId) : undefined;
          const disc = (
            <span className="spine-disc" aria-hidden="true">
              {step.state === 'done' && <Check size={14} strokeWidth={2.6} />}
              {step.state === 'active' &&
                (step.number !== undefined ? step.number : <Pencil size={13} strokeWidth={2.2} />)}
              {step.state === 'locked' && <Lock size={12} strokeWidth={2} />}
            </span>
          );
          const text = (
            <span className="spine-text">
              <span className="spine-label">{step.label}</span>
              {step.meta && <span className="spine-meta">{step.meta}</span>}
            </span>
          );
          return (
            <li
              key={step.key}
              className={`spine-step ${step.state}`}
              aria-current={step.state === 'active' ? 'step' : undefined}
              aria-disabled={step.state === 'locked' ? true : undefined}
            >
              {href ? (
                <Link className="spine-step-row spine-step-link" to={href}>
                  {disc}
                  {text}
                </Link>
              ) : (
                <span className="spine-step-row">
                  {disc}
                  {text}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** The shared spine gate order, parameterized by which step is active. */
export function buildSpine(
  active: 'draft' | 'complete' | 'export' | 'validate' | 'audit',
  overrides?: Partial<Record<string, Partial<SpineStep>>>,
): SpineStep[] {
  // Default meta is the skeleton shown before live data (or a caller override)
  // arrives — shape only, never a fabricated count. Screens that know the real
  // numbers pass them in via `overrides`.
  const order: { key: string; label: string; meta: string }[] = [
    { key: 'draft', label: LABELS.stepDraft, meta: 'reviewing fields' },
    { key: 'complete', label: LABELS.stepComplete, meta: 'fields need you' },
    { key: 'export', label: LABELS.stepExport, meta: 'unlocks when 0 remain' },
    { key: 'validate', label: LABELS.stepValidate, meta: 'the hard gate' },
    { key: 'audit', label: LABELS.stepAudit, meta: 'evidence coverage' },
  ];
  const activeIndex = order.findIndex((s) => s.key === active);
  return order.map((s, i) => {
    const state: SpineStep['state'] = i < activeIndex ? 'done' : i === activeIndex ? 'active' : 'locked';
    const base: SpineStep = { key: s.key, label: s.label, state, meta: state === 'done' ? undefined : s.meta };
    return { ...base, ...overrides?.[s.key] };
  });
}
