import './workflow.css';
import { Link, useLocation } from 'react-router-dom';
import { Check, Pencil, Lock, TriangleAlert, CircleDashed } from './icons';
import { LABELS } from '../lib/labels';
import {
  RECORD_CAPTURE_METHOD_PARAM,
  RECORD_VIEW_PARAM,
  ROUTES,
  resolveRecordView,
} from '../lib/routes';
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

/**
 * WHICH STEP'S DESTINATION IS THE PAGE ON SCREEN — read from the URL alone.
 *
 * ── WHY THIS EXISTS (owner QA 2026-09-22, N1) ──────────────────────────────
 *
 * The spine used to answer two questions with one visual. The server's `current`
 * step (what the record needs next) was also the only highlighted row, so
 * `Complete Metadata` stayed blue while the reader was on Runs, Capture, Activity
 * — and even on `/export`, where the page on screen is Review Export Readiness.
 * "How complete is this record?" and "where am I?" are different questions, and
 * each row now answers both separately: a STATE (disc + word, from the server) and
 * a LOCATION (the selected-page background + `aria-current="page"`, from here).
 *
 * DERIVED FROM THE URL, not threaded as a prop, for the reason the document-title
 * floor gives: a screen that forgot to pass it would leave the spine claiming a
 * location it is not on. `pathname` excludes the router `basename`, so this is the
 * same on `/krish`.
 *
 * `review_export_readiness` and `export` share one route; the page there is titled
 * Review Export Readiness (`LABELS.screenExport`), so that is the row it marks.
 * Any record workspace other than Record Fields marks NO row: the rail's own
 * destination list says where the reader is, and one "you are here" is the rule.
 */
export function locationStepFor(pathname: string, search: string): string | null {
  const path = pathname.replace(/\/+$/, '');
  if (/^\/record\/[^/]+\/complete$/.test(path)) return 'complete_metadata';
  if (/^\/record\/[^/]+\/evidence$/.test(path)) return 'review_evidence';
  if (/^\/record\/[^/]+\/export$/.test(path)) return 'review_export_readiness';
  if (/^\/record\/[^/]+$/.test(path)) {
    return resolveRecordView(search) === 'fields' ? 'load_record' : null;
  }
  return null;
}

/**
 * `Record Created`'s destination, the Record Fields workspace — and, ON the record
 * screen, the rest of the address comes along (2026-09-22).
 *
 * The rail's own `Record Fields` row copied the current query string, so a focused
 * run (`?run=`) survived a trip to the fields and back. That row left the rail
 * (N2) and this step is now the way there, so it keeps the same contract: on
 * `/record/<id>` it copies the address, drops the capture task, and names
 * `view=fields` explicitly (a bare `?run=` would otherwise resolve to Runs). From
 * any other record screen it is the plain record address, as it always was.
 */
function fieldsHref(recordId: string, pathname: string, search: string): string {
  if (!/^\/record\/[^/]+\/?$/.test(pathname)) return ROUTES.record(recordId);
  const next = new URLSearchParams(search);
  next.delete(RECORD_VIEW_PARAM);
  next.delete(RECORD_CAPTURE_METHOD_PARAM);
  if ([...next.keys()].length === 0) return ROUTES.record(recordId);
  next.set(RECORD_VIEW_PARAM, 'fields');
  return `${ROUTES.record(recordId)}?${next.toString()}`;
}

/**
 * THE STATE WORD — the non-colour, non-shape half of a row's state, in the
 * scientist's words. Rendered from the server's `state` verbatim; nothing is
 * re-derived. `export` in `current` says `Ready`, because `derive_workflow` makes
 * it current exactly when `review_export_readiness` is satisfied and the record is
 * not yet exported — i.e. ready to export.
 */
export function stepStateWord(step: Pick<ApiWorkflowStep, 'id' | 'state'>): string {
  if (step.state === 'completed') return 'Complete';
  if (step.state === 'current') return step.id === 'export' ? 'Ready' : 'Current requirement';
  if (step.state === 'reopened') return 'Needs review';
  return 'Locked';
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
 * The permanent canonical workflow spine (Record Created → Complete Metadata →
 * Review Evidence → Review Export Readiness → Export). Order and per-step state
 * are DERIVED by the backend and rendered here verbatim — the client never
 * re-derives completion. Each row carries TWO independent signals: its STATE
 * (disc + state word, from the server) and whether it is the displayed PAGE
 * (selected background + aria-current="page", from the URL — see
 * `locationStepFor`). `current` keeps aria-current="step" when it is not also
 * the displayed page; `completed` steps link back to their
 * surface; `reopened` (was-complete, now regressed) is distinct from a
 * never-started `blocked` step by both style and its reason text; blocked and
 * reopened steps are non-navigable and aria-disabled. Never color-only — every
 * state keeps its text label (and, when unsatisfied, a reason).
 */
export function WorkflowSpine({ workflow, recordId }: WorkflowSpineProps) {
  const { pathname, search } = useLocation();
  const locationStep = recordId ? locationStepFor(pathname, search) : null;
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
          /*
           * THE SAME SENTENCE IS NOT PRINTED THREE TIMES.
           *
           * `workflow.py:139` gives EVERY blocked step the same reason --
           * `Complete '<current>' first.` -- which is right for the API: a
           * client may render one step alone, so each step carries its own
           * reason rather than depending on a sibling. On the desktop vertical
           * spine that rendered the identical sentence once per blocked step:
           * measured on a freshly created record, three copies of "Complete
           * 'Complete Metadata' first." stacked down the rail. That is the
           * "everything is just put in here with no thought behind it" the
           * owner reported, and it is a PRESENTATION problem, so it is fixed
           * here and not by weakening the server's contract.
           *
           * The first step carrying a reason prints it; later steps carrying
           * the IDENTICAL string keep it in the DOM and hide it visually, so
           * the accessibility tree is UNCHANGED -- a screen reader still hears
           * why each individual step is locked. Compared by string equality
           * rather than by assuming all blocked reasons match, because
           * `reopened` carries a different sentence and a future state may
           * carry a third.
           */
          const duplicateReason =
            step.reason !== null &&
            workflow.ordered_steps.findIndex((other) => other.reason === step.reason) !==
              workflow.ordered_steps.indexOf(step);
          const route = STEP_ROUTE[step.id];
          const href =
            recordId && route && isNavigable(step.state)
              ? step.id === 'load_record'
                ? fieldsHref(recordId, pathname, search)
                : route(recordId)
              : undefined;
          const disc = <Disc state={step.state} />;
          const isLocation = step.id === locationStep;
          /*
           * `aria-current`: `page` on the row whose destination is on screen, and
           * `step` on the server's current requirement when it is a DIFFERENT row.
           * When they coincide, `page` wins and the visible state word still says
           * "Current requirement", so neither fact is lost to a screen reader.
           */
          const ariaCurrent = isLocation ? 'page' : step.current ? 'step' : undefined;
          const text = (
            <span className="spine-text">
              <span className="spine-label">{step.label}</span>
              {/* The state word. Visible on the vertical desktop spine; in the
                  compact <=1024px stepper it is visually hidden (the disc's SHAPE
                  carries the state there) and stays in the accessibility tree —
                  the same `.spine-meta-compact-narrow` treatment, and therefore the
                  same layout-sweep allowance, as a non-current reason. */}
              <span className="spine-state spine-meta-compact-narrow">
                {stepStateWord(step)}
              </span>
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
                <span
                  className={`spine-meta${step.current ? '' : ' spine-meta-compact-narrow'}${
                    duplicateReason ? ' spine-meta-duplicate' : ''
                  }`}
                >
                  {step.reason}
                </span>
              )}
            </span>
          );
          return (
            <li
              key={step.id}
              className={`spine-step ${step.state}${isLocation ? ' is-location' : ''}`}
              aria-current={ariaCurrent}
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
