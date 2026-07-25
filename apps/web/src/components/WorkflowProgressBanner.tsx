import './workflow-progress-banner.css';
import { useLocation, useNavigate } from 'react-router-dom';
import { CircleAlert, Check, type LucideIcon } from './icons';
import { ROUTES } from '../lib/routes';
import type { ApiWorkflow } from '../lib/types';

interface WorkflowProgressBannerProps {
  /** The backend-derived workflow. `null` (or a `null` current_step — every
   * step satisfied / nothing left to do) renders nothing. The client renders
   * this verbatim; it never re-derives step order or completion. */
  workflow: ApiWorkflow | null;
  recordId: string;
  /** The live pending count, for the complete_metadata heading/body copy. */
  pendingCount: number;
  /** Step ids this surface already has its own resident CTA for (e.g.
   * RecordWorkbench's `.needsyou-banner` covers complete_metadata) — suppress
   * this banner for those so the same next action never shows twice. */
  excludeSteps?: string[];
}

// The canonical step id -> route, mirrored EXACTLY from WorkflowSpine.tsx's
// STEP_ROUTE. review_export_readiness and export both live on the export
// surface. These are the ONLY destinations; there is no "skip" route.
const STEP_ROUTE: Record<string, ((id: string) => string) | undefined> = {
  load_record: ROUTES.record,
  complete_metadata: ROUTES.complete,
  review_evidence: ROUTES.evidence,
  review_export_readiness: ROUTES.export,
  export: ROUTES.export,
};

type Tone = 'attention' | 'ready';

interface BannerContent {
  tone: Tone;
  Icon: LucideIcon;
  heading: string;
  body: string;
  actionLabel: string;
}

// current_step is the first UNsatisfied step (backend-derived — see
// apps/api/isaac_api/workflow.py `derive_workflow`). Every heading/body here
// must stay truthful to that derivation:
//  - complete_metadata: pending_count > 0.
//  - review_evidence: pending_count == 0 AND the draft validator is failing.
//  - review_export_readiness: pending_count == 0 AND draft_ok, but the
//    official-schema export DRY-RUN is failing (if it passed, current_step
//    would already be 'export') — this is "not ready yet", never a serene
//    "metadata complete".
//  - export: everything else satisfied; only the export step remains.
// Returns null for any step id with no defined copy here (e.g. load_record,
// which is always satisfied once a record bundle exists) — the banner never
// fabricates copy for a state it doesn't recognize.
function contentFor(step: string, pendingCount: number): BannerContent | null {
  switch (step) {
    case 'complete_metadata': {
      const n = pendingCount;
      return {
        tone: 'attention',
        Icon: CircleAlert,
        heading: `${n} item${n === 1 ? '' : 's'} need${n === 1 ? 's' : ''} your attention`,
        body: `Confirm or complete the remaining ${n === 1 ? 'item' : 'items'} before this record can be exported.`,
        actionLabel: 'Review Items',
      };
    }
    case 'review_evidence':
      return {
        tone: 'attention',
        Icon: CircleAlert,
        heading: 'Evidence review needed',
        body: "This record's evidence checks aren't passing yet.",
        actionLabel: 'Review Evidence',
      };
    case 'review_export_readiness':
      return {
        tone: 'attention',
        Icon: CircleAlert,
        heading: 'Not ready to export yet',
        body:
          "All values are confirmed, but this record doesn't pass the official ISAAC schema " +
          "check yet. Review export readiness to see what's left.",
        actionLabel: 'Review Export Readiness',
      };
    case 'export':
      return {
        tone: 'ready',
        Icon: Check,
        heading: 'Ready to export',
        body: 'No blocking validation or evidence issues remain.',
        actionLabel: 'Continue to Export',
      };
    default:
      return null;
  }
}

/**
 * A compact, state-driven CTA surfacing the single next workflow step —
 * shown only when that step is NOT the surface you're already on (no
 * duplicate call-to-action) and NOT one this surface already covers with its
 * own resident banner (`excludeSteps`). Two tones only: amber advisory (still
 * blocked on something) and a calm action-blue "ready" tone — never the
 * reserved pass/fail verdict hues (--pass-solid, --fail-solid, etc.), which
 * are reserved for validation verdicts (P22C).
 */
export function WorkflowProgressBanner({
  workflow,
  recordId,
  pendingCount,
  excludeSteps,
}: WorkflowProgressBannerProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const currentStep = workflow?.current_step ?? null;
  if (!currentStep) return null;
  if (excludeSteps?.includes(currentStep)) return null;

  const destination = STEP_ROUTE[currentStep]?.(recordId);
  if (!destination || destination === location.pathname) return null;

  const content = contentFor(currentStep, pendingCount);
  if (!content) return null;

  const { Icon, heading, body, actionLabel, tone } = content;

  return (
    <div className={`wf-progress-banner wf-progress-banner--${tone}`} role="note">
      <div className="wf-progress-main">
        <Icon className="wf-progress-icon" size={20} strokeWidth={2.2} aria-hidden="true" />
        <div className="wf-progress-body">
          <div className="wf-progress-heading">{heading}</div>
          <p className="wf-progress-text">{body}</p>
        </div>
      </div>
      <button
        type="button"
        className="btn btn-primary wf-progress-action"
        onClick={() => navigate(destination, { state: { focusMain: true } })}
      >
        {actionLabel} →
      </button>
    </div>
  );
}
