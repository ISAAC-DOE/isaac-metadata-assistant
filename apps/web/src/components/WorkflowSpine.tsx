import './workflow.css';
import { Link } from 'react-router-dom';
import { Check, Pencil, Lock, TriangleAlert, CircleDashed } from './icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import { CANONICAL_STEPS } from '../lib/workflowSteps';
import type { ApiWorkflow, ApiWorkflowStep } from '../lib/types';

interface WorkflowSpineProps {
  /** The backend-derived workflow. `null` renders the loading skeleton (labels
   * only — never a fabricated count or a guessed current step). The client
   * renders this verbatim; it never re-derives step order or completion. */
  workflow: ApiWorkflow | null;
  /** The record id, so navigable steps can link back to their surface. Omitted
   * where there is no record context — then no step navigates. */
  recordId?: string;
}

// The canonical step id → route. review_export_readiness and export both live on
// the export surface. These are the ONLY destinations; there is no "skip" route.
const STEP_ROUTE: Record<string, ((id: string) => string) | undefined> = {
  load_record: ROUTES.record,
  complete_metadata: ROUTES.complete,
  review_evidence: ROUTES.evidence,
  review_export_readiness: ROUTES.export,
  export: ROUTES.export,
};

// Only completed and current steps navigate. Gating is preserved by keeping
// blocked/reopened steps non-interactive — forward motion is earned by resolving
// the current gate, never by clicking ahead. A reopened step is a regressed
// prerequisite; it is reached again by resolving the current step first.
function isNavigable(state: ApiWorkflowStep['state']): boolean {
  return state === 'completed' || state === 'current';
}

function Disc({ state }: { state: ApiWorkflowStep['state'] }) {
  return (
    <span className="spine-disc" aria-hidden="true">
      {state === 'completed' && <Check size={14} strokeWidth={2.6} />}
      {state === 'current' && <Pencil size={13} strokeWidth={2.2} />}
      {state === 'reopened' && <TriangleAlert size={13} strokeWidth={2.2} />}
      {state === 'blocked' && <Lock size={12} strokeWidth={2} />}
    </span>
  );
}

/**
 * The permanent canonical workflow spine (Load Record → Complete Metadata →
 * Review Evidence → Review Export Readiness → Export). Order and per-step state
 * are DERIVED by the backend and rendered here verbatim — the client never
 * re-derives completion. `current` is visually distinct and carries
 * aria-current="step"; `completed` steps stay green and link back to their
 * surface; `reopened` (was-complete, now regressed) is distinct from a
 * never-started `blocked` step by both style and its reason text; blocked and
 * reopened steps are non-navigable and aria-disabled. Never color-only — every
 * state keeps its text label (and, when unsatisfied, a reason).
 */
export function WorkflowSpine({ workflow, recordId }: WorkflowSpineProps) {
  if (workflow === null) {
    // Loading skeleton: labels only, muted discs, nothing navigable, no counts.
    // The fixed order + labels come from `lib/workflowSteps.ts` (CANONICAL_STEPS),
    // the ONE client-side copy — a second hand-maintained array used to live here.
    // The live spine below still renders the backend's own labels; the skeleton
    // exists purely so the shape is visible before the bundle arrives.
    return (
      <nav
        className="spine"
        aria-label="Workflow pipeline"
        data-tutorial-anchor={TUTORIAL_ANCHORS.recordWorkflow}
      >
        <div className="spine-eyebrow eyebrow">{LABELS.workflowEyebrow}</div>
        <ol className="spine-steps">
          {CANONICAL_STEPS.map((step) => (
            <li key={step.id} className="spine-step skeleton" aria-disabled>
              <span className="spine-step-row">
                <span className="spine-disc" aria-hidden="true">
                  <CircleDashed size={13} strokeWidth={2} />
                </span>
                <span className="spine-text">
                  <span className="spine-label">{step.label}</span>
                </span>
              </span>
            </li>
          ))}
        </ol>
      </nav>
    );
  }

  return (
    <nav
        className="spine"
        aria-label="Workflow pipeline"
        data-tutorial-anchor={TUTORIAL_ANCHORS.recordWorkflow}
      >
      <div className="spine-eyebrow eyebrow">{LABELS.workflowEyebrow}</div>
      <ol className="spine-steps">
        {workflow.ordered_steps.map((step) => {
          const route = STEP_ROUTE[step.id];
          const href =
            recordId && route && isNavigable(step.state) ? route(recordId) : undefined;
          const disc = <Disc state={step.state} />;
          const text = (
            <span className="spine-text">
              <span className="spine-label">{step.label}</span>
              {/* The reason is shown for unsatisfied steps only, giving a
               * non-color signal that also distinguishes reopened from blocked.
               *
               * I-2 (independent review, 2026-09-03) — `spine-meta-compact-narrow`
               * is a DEDICATED class, not the structural
               * `.spine-step:not(.current) .spine-meta` selector the CSS fix
               * could otherwise have used, because `e2e/layout-allowlist.ts`'s
               * own rule 1 requires a HIDDEN-TEXT allowance to name "a specific
               * class" on the element itself, not a descendant/ancestor
               * selector. The class exists in the DOM at every viewport
               * (React has no viewport awareness); `workflow.css` gives it a
               * visually-hidden treatment ONLY inside the `<=1024px` media
               * query, so at desktop widths it is present but inert and the
               * text renders exactly as it always has. */}
              {step.reason && (
                <span className={`spine-meta${step.current ? '' : ' spine-meta-compact-narrow'}`}>
                  {step.reason}
                </span>
              )}
            </span>
          );
          return (
            <li
              key={step.id}
              className={`spine-step ${step.state}`}
              aria-current={step.current ? 'step' : undefined}
              aria-disabled={isNavigable(step.state) ? undefined : true}
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
