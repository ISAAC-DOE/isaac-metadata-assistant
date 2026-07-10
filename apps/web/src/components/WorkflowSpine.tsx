import './workflow.css';
import { Check, Pencil, Lock } from './icons';
import { LABELS } from '../lib/labels';
import type { SpineStep } from '../lib/types';

interface WorkflowSpineProps {
  steps: SpineStep[];
}

/**
 * The gated pipeline (Draft → Complete → Export → Validate → Audit) showing the
 * current blocking gate. Locked steps are not clickable — forward motion is
 * earned by resolving gates, never by dismissing them. No "skip"/"export anyway".
 */
export function WorkflowSpine({ steps }: WorkflowSpineProps) {
  return (
    <nav className="spine" aria-label="Workflow pipeline">
      <div className="spine-eyebrow eyebrow">{LABELS.workflowEyebrow}</div>
      <ol className="spine-steps">
        {steps.map((step) => (
          <li
            key={step.key}
            className={`spine-step ${step.state}`}
            aria-current={step.state === 'active' ? 'step' : undefined}
            aria-disabled={step.state === 'locked' ? true : undefined}
          >
            <span className="spine-disc" aria-hidden="true">
              {step.state === 'done' && <Check size={14} strokeWidth={2.6} />}
              {step.state === 'active' &&
                (step.number !== undefined ? step.number : <Pencil size={13} strokeWidth={2.2} />)}
              {step.state === 'locked' && <Lock size={12} strokeWidth={2} />}
            </span>
            <span className="spine-text">
              <span className="spine-label">{step.label}</span>
              {step.meta && <span className="spine-meta">{step.meta}</span>}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  );
}

/** The shared spine gate order, parameterized by which step is active. */
export function buildSpine(
  active: 'draft' | 'complete' | 'export' | 'validate' | 'audit',
  overrides?: Partial<Record<string, Partial<SpineStep>>>,
): SpineStep[] {
  const order: { key: string; label: string; meta: string }[] = [
    { key: 'draft', label: LABELS.stepDraft, meta: 'reviewing 26 fields' },
    { key: 'complete', label: LABELS.stepComplete, meta: '5 fields need you' },
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
