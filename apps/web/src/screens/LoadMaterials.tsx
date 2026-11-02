import './screens.css';
import '../components/runner.css';
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { Widget } from '../components/Widget';
import { StagedRunner } from '../components/StagedRunner';
import { BackendDown } from '../components/FetchStates';
import { Play, ShieldCheck } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api, ApiError } from '../lib/api';
import { startTutorial, useTutorialState } from '../lib/tutorialController';
import { demoStepsToStages } from '../lib/adapt';
import type { ApiDemoRunResponse } from '../lib/types';

type RunPhase =
  | { name: 'idle' }
  | { name: 'running' }
  // The server refused to re-seed an edited scenario (409 `demo_target_drifted`).
  // A refusal is NOT an error: the backend answered, and answered correctly.
  | { name: 'drifted'; experimentId?: string }
  // The server refused because no worked-example session is open (409
  // `tutorial_scope_required`). Also a refusal, also not an error — and this is the
  // one that used to render as "Backend Not Running".
  | { name: 'scopeRequired' }
  | { name: 'error'; error: ApiError }
  | { name: 'done'; result: ApiDemoRunResponse };

const DEMO_TARGET_DRIFTED = 'demo_target_drifted';
const TUTORIAL_SCOPE_REQUIRED = 'tutorial_scope_required';

/**
 * The typed `error` code on a 409 refusal body, or null.
 *
 * An HTML intercept is excluded first: an edge sign-in page can carry any status
 * and is never a typed refusal. A 409 with a missing, non-object or unrecognised
 * body yields null and falls through to the error state — claiming a specific
 * refusal we did not observe would be exactly the class of lie the honest failure
 * state exists to avoid.
 */
function refusalCode(error: ApiError): string | null {
  if (error.status !== 409 || error.htmlIntercept) return null;
  const body = error.body;
  if (typeof body !== 'object' || body === null) return null;
  const { error: code } = body as Record<string, unknown>;
  return typeof code === 'string' ? code : null;
}

/**
 * Recognise `POST /api/demo/run` answering 409 `demo_target_drifted` because the
 * canonical record has been edited and re-seeding would discard that work.
 *
 * Returns the refusal's record id when the body carries one; the id is optional,
 * and its absence must not suppress the refusal.
 */
function driftRefusal(error: ApiError): { experimentId?: string } | null {
  if (refusalCode(error) !== DEMO_TARGET_DRIFTED) return null;
  const { experiment_id: id } = error.body as Record<string, unknown>;
  return { experimentId: typeof id === 'string' && id !== '' ? id : undefined };
}

/**
 * Recognise `POST /api/demo/run` answering 409 `tutorial_scope_required`: the
 * request carried no `X-Isaac-Tutorial-Session` header, the built-in examples exist
 * only inside such a session, and so there was nothing to run over.
 *
 * WHY THIS BRANCH EXISTS. Without it this refusal fell through to `{name:'error'}`
 * → `BackendDown`, i.e. the screen reported a backend that had answered correctly
 * and instantly as not running. The status alone was never enough to reach it: a
 * `demo_target_drifted` 409 means something different and has a different remedy,
 * so the typed discriminator is what is matched.
 */
function scopeRefusal(error: ApiError): boolean {
  return refusalCode(error) === TUTORIAL_SCOPE_REQUIRED;
}

/**
 * S2 · Load Materials — the on-ramp. Synthetic-first. Run Synthetic Demo calls
 * `POST /api/demo/run` (draft_only) and renders the returned pipeline steps —
 * real commands, real results, nothing staged locally. The local-files path is
 * approval-gated: it calls the governance seam (always 403) and surfaces the
 * server's refusal verbatim; nothing is read or stored.
 */
export function LoadMaterials() {
  const navigate = useNavigate();
  const [run, setRun] = useState<RunPhase>({ name: 'idle' });

  /*
   * B-05 — THE PRIMARY CONTROL USED TO BE A BUTTON THAT COULD NOT WORK. The built-in
   * example records exist only inside a worked-example session, and
   * `POST /api/demo/run` answers `409 tutorial_scope_required` to any request that
   * carries no session header. Outside a session the card's primary action therefore
   * failed EVERY time, and the screen explained why only AFTER the press — a control
   * that looks like it acts and does not.
   *
   * The signal is the one `api.ts::request` uses to decide whether to send the header
   * (`sessionId` mirrors `getTutorialScope()`), so this screen and the server cannot
   * disagree about whether a press would be scoped. Outside a session the card now
   * offers the control that DOES work — the same "Launch Guided Demo" and the same
   * audited disclosure the empty My Experiments state uses — and makes no demo-run
   * request at all. It is an explicit press for exactly that purpose, so it is not
   * the screen "quietly starting the walkthrough on the reader's behalf", which the
   * scope-refusal panel below is still careful not to do.
   *
   * The `scopeRequired` refusal below is KEPT, as the fallback for the one case this
   * gate cannot see: a session that ended between render and press.
   */
  const tutorial = useTutorialState();
  const inWorkedExample = tutorial.sessionId !== null;
  const launchRef = useRef<HTMLButtonElement>(null);
  // The same double-submit guard `ExperimentsHome` documents: `startTutorial` awaits a
  // round trip before it holds a session, so a second press in that window would open
  // and orphan a second one.
  const launchBusy = tutorial.phase !== 'idle';

  const startDemo = () => {
    setRun({ name: 'running' });
    api
      .runDemo('draft_only')
      .then((result) => setRun({ name: 'done', result }))
      .catch((error: ApiError) => {
        const drift = driftRefusal(error);
        if (drift) {
          setRun({ name: 'drifted', experimentId: drift.experimentId });
        } else if (scopeRefusal(error)) {
          setRun({ name: 'scopeRequired' });
        } else {
          setRun({ name: 'error', error });
        }
      });
  };

  return (
    <AppShell
      variant="full"
      /* THE SAME CHROME AS EVERY OTHER SCREEN (2026-10-12 clutter audit). This
         surface used to mount a breadcrumb-only top bar with no left navigation
         and no Help, so a reader who reached it had one way out (the brand mark)
         and no help at all. It now carries the home top bar — search, workspace
         chip, Help — and the primary navigation, with no item current, because
         `/load` is not a navigation destination (no global nav item is added
         without a decision, `ISAAC_PRODUCT_DECISIONS.md` after DEC-51). */
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav />}
      mainPad="pad"
    >
      <div className="load-page">
        {/*
          FINDING A11Y-05 fix, and since 2026-10-12 the heading is VISIBLE. It was
          `sr-only` because the on-ramp's visual design had no title and the
          document outline was what was missing. With the same chrome as every
          other screen, the page header is part of that design — so the one
          `<h1>` is now reachable by sight AND by assistive technology, which is a
          stronger form of what the fix was for.

          `LABELS.screenLoad` is the name this surface already carries in
          navigation, so the outline and the nav agree.
        */}
        <div className="page-header">
          <div>
            <h1 className="page-title">{LABELS.screenLoad}</h1>
          </div>
        </div>

        <div className="onramps">
          {/*
            WIDGET 1 — "Try a worked example". The primary action on this screen.
            Its long description (what the example assembles, why it runs inside the
            Guided Walkthrough, what starting one does) moved behind the widget's
            info panel, which `Widget` keeps in the DOM while closed — so the
            Start control is still DESCRIBED BY the audited disclosure, and
            `load-worked-example-session.test.tsx` still reads it here.
          */}
          <Widget
            id="load-example-title"
            className="load-widget load-widget-example"
            title={LABELS.loadExampleTitle}
            icon={<Play size={16} strokeWidth={2.2} />}
            sub={LABELS.loadExampleSub}
            infoLabel={LABELS.loadExampleInfoLabel}
            info={
              <>
                <p>{LABELS.loadExampleBody}</p>
                {!inWorkedExample && (
                  <p id="load-launch-hint">
                    {LABELS.demoRunsInsideGuidedDemo} {LABELS.launchGuidedDemoBody}
                  </p>
                )}
              </>
            }
          >
            {inWorkedExample ? (
              <button
                type="button"
                className="btn btn-primary load-widget-cta"
                onClick={startDemo}
                disabled={run.name === 'running'}
              >
                {run.name === 'running' ? 'Running…' : LABELS.actionRunDemoShort}
              </button>
            ) : (
              <button
                ref={launchRef}
                type="button"
                className="btn btn-primary load-widget-cta"
                disabled={launchBusy}
                aria-describedby="load-launch-hint"
                /* The visible verb is the button's whole name on this card, whose
                   title already says Guided Walkthrough; the full name keeps it
                   distinct from every other Start in the app (WCAG 2.5.3: it opens
                   with the visible word). */
                aria-label={tutorial.completed ? LABELS.actionReplayTutorial : LABELS.actionStartTutorial}
                onClick={() => startTutorial(launchRef.current)}
              >
                {tutorial.completed ? LABELS.actionReplay : LABELS.actionStart}
              </button>
            )}
          </Widget>

          {/* ~~WIDGET 2 — "Can I Load My Own Files?", the GovernanceBanner above it
              and the "Try an Upload" button~~ — retired 2026-11-02 (owner's
              direction: no standing disclaimers). The guided walkthrough is the
              one thing this screen does. */}
        </div>

        {run.name === 'running' && (
          <div className="runner-status">
            <span className="dot dot-processing" aria-hidden="true" />
            <span className="runner-status-label">Example Run — Running</span>
            <span className="runner-status-note">running…</span>
          </div>
        )}

        {/*
         * The protective refusal. `role="alert"` matches how this screen (and
         * the export conflict on S6) announces a state that appears in answer to
         * a click; the visual treatment is the same protective slate as the
         * governance refusal above, never the red error treatment — the backend
         * is healthy and has just done the right thing. Focus deliberately stays
         * on the example-run button: the alert announces itself, and the remedy
         * button follows in DOM order.
         */}
        {run.name === 'drifted' && (
          <div
            className="upload-blocked demo-refused"
            role="alert"
            aria-labelledby="demo-refused-title"
          >
            <ShieldCheck size={14} strokeWidth={2.1} aria-hidden="true" />
            <div>
              <p id="demo-refused-title" className="demo-refused-title">
                <strong>{LABELS.demoDriftedTitle}</strong>
              </p>
              <p>{LABELS.demoDriftedBody}</p>
              <p>{LABELS.demoDriftedRemedy}</p>
              {run.experimentId && (
                <p className="demo-refused-id">
                  {LABELS.demoDriftedScenario} <span className="mono">{run.experimentId}</span>
                </p>
              )}
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate(ROUTES.experiments)}
              >
                {LABELS.actionGoToExperiments}
              </button>
            </div>
          </div>
        )}

        {/*
         * The scope refusal. Same protective treatment as the drift refusal above
         * and the governance refusal at the top of the screen — never the red error
         * treatment, because nothing failed: the server answered, correctly, that
         * the records this control acts on are not in the workspace this request
         * addressed. `role="alert"` because it appears in answer to a click.
         *
         * The remedy is a NAVIGATION, not a repair. It does not offer to open a
         * worked example from here: that would be this screen quietly starting the
         * guided walkthrough on the reader's behalf, and the control that does it
         * has its own home, its own copy about what it discards, and its own place
         * in the walkthrough's lifecycle.
         */}
        {run.name === 'scopeRequired' && (
          <div
            className="upload-blocked demo-refused"
            role="alert"
            aria-labelledby="demo-scope-required-title"
          >
            <ShieldCheck size={14} strokeWidth={2.1} aria-hidden="true" />
            <div>
              <p id="demo-scope-required-title" className="demo-refused-title">
                <strong>{LABELS.demoScopeRequiredTitle}</strong>
              </p>
              <p>{LABELS.demoScopeRequiredBody}</p>
              <p>{LABELS.demoScopeRequiredRemedy}</p>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate(ROUTES.settingsTab('help'))}
              >
                {LABELS.actionGoToHelpAndTutorial}
              </button>
            </div>
          </div>
        )}

        {run.name === 'error' && <BackendDown error={run.error} onRetry={startDemo} />}

        {run.name === 'done' && (
          <>
            <div className="runner-status">
              <span
                className={`dot ${run.result.status === 'needs_attention' ? 'dot-attention' : 'dot-ready'}`}
                aria-hidden="true"
              />
              <span className="runner-status-label">Example Run — Draft Assembled</span>
              <span className="runner-status-note">
                {run.result.status === 'needs_attention'
                  ? 'paused for your input · your turn'
                  : `status · ${run.result.status}`}
              </span>
            </div>

            <StagedRunner stages={demoStepsToStages(run.result.steps)} />

            <div className="runner-open">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate(ROUTES.record(run.result.experiment_id))}
              >
                Open the Record →
              </button>
              <span className="runner-open-note mono">{run.result.experiment_id}</span>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
