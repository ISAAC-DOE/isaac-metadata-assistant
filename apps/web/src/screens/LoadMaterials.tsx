import './screens.css';
import '../components/runner.css';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { GovernanceBanner } from '../components/GovernanceBanner';
import { StagedRunner } from '../components/StagedRunner';
import { BackendDown } from '../components/FetchStates';
import { Play, ShieldCheck, Upload, TriangleAlert } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api, ApiError } from '../lib/api';
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

type UploadPhase =
  | { name: 'idle' }
  | { name: 'blocked'; reason: string } // the server's 403 governance refusal, verbatim
  | { name: 'down'; error: ApiError }; // backend unreachable — show BackendDown, never stand-in copy

// Shown only when the server responded but its refusal body carried no reason.
//
// Slice 2A (I5): was "…not enabled in this synthetic prototype." The refusal
// itself is true and unchanged, but "this synthetic prototype" labelled the
// whole application as synthetic, which the deployment no longer is without
// qualification — it may run a protected, read-only diagnostic over an isolated
// test database of production-derived records. The upload gate is a property of
// this workspace, so that is the scope stated. The SERVER's own reason
// (`_UPLOAD_BLOCKED` in apps/api/isaac_api/routes.py) was corrected in the same
// slice and now says "in this workspace" too, with `src/test/apiFixtures.ts`
// pinning the corrected wording. The two are alternatives — this string renders
// only when the server sends none — so they say the same thing on purpose.
const UPLOADS_GATED_FALLBACK =
  'Uploads are approval-gated and not enabled in this workspace.';

/**
 * The two `error` discriminators the backend sends with its 409 demo-run refusals.
 * Both are values from `apps/api/isaac_api/routes.py` — read from there, never
 * guessed, because a code this screen invented would silently never match.
 */
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
  const [upload, setUpload] = useState<UploadPhase>({ name: 'idle' });

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

  const tryLocalFiles = () => {
    // Governance seam: the backend always refuses (403); no file is ever sent.
    api
      .blockUpload()
      .then((body) => setUpload({ name: 'blocked', reason: body.reason || UPLOADS_GATED_FALLBACK }))
      .catch((error: unknown) => {
        // Backend down is NOT a governance refusal — show the honest down state.
        if (error instanceof ApiError && error.unreachable) {
          setUpload({ name: 'down', error });
        } else {
          setUpload({ name: 'blocked', reason: UPLOADS_GATED_FALLBACK });
        }
      });
  };

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="breadcrumb" breadcrumb={LABELS.actionOpenRecord} />}
      mainPad="centered"
    >
      <div className="centered-col">
        {/*
          FINDING A11Y-05 fix. This screen rendered NO heading of any level, so
          a screen-reader user arriving here had nothing to orient by: the
          heading list was empty and "jump to the top heading" went nowhere.

          `sr-only` rather than a visible title, following the five screens that
          already do this (`RecordWorkbench`, `EvidenceExplorer`,
          `ExportReadiness`, `GuidedCompletion`). The visual design of this
          on-ramp is deliberate and a new visible title would change it; the
          document outline is what was missing, and that is what this adds. It
          also paints no new text, so it moves no `color-contrast` count.

          `LABELS.screenLoad` is the name this surface already carries in
          navigation, so the outline and the nav agree.
        */}
        <h1 className="sr-only">{LABELS.screenLoad}</h1>
        <GovernanceBanner onReadPolicy={() => navigate(ROUTES.governance)} />

        <div className="onramps">
          <div className="onramp emphasis">
            <div className="onramp-head">
              <span className="onramp-icon" aria-hidden="true">
                <Play size={16} strokeWidth={2.2} />
              </span>
              <div>
                <div className="onramp-title">Worked Example: CuO Cu K-edge XANES</div>
                <div className="onramp-tagline">a complete example run · ~10s</div>
              </div>
              <span className="onramp-tag">Built-in Example</span>
            </div>
            <p className="onramp-body">
              A fictional year-2099 CuO / Cu K-edge XANES session. Assembles the evidenced draft,
              holds back the fields it won't guess, and — once you confirm them — validates against
              ISAAC v1.05.
            </p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={startDemo}
              disabled={run.name === 'running'}
            >
              {run.name === 'running' ? 'Running…' : LABELS.actionRunDemoShort}
            </button>
          </div>

          <div className="onramp">
            <div className="onramp-head">
              <span className="onramp-icon neutral" aria-hidden="true">
                <Upload size={16} strokeWidth={2} />
              </span>
              <div>
                <div className="onramp-title">{LABELS.actionLoadLocal}</div>
                <div className="onramp-tagline">not enabled in this build</div>
              </div>
              <span className="onramp-tag">Approval-Gated</span>
            </div>
            {upload.name === 'idle' && (
              /*
               * The affordance states what activating it does. There is no file
               * input element here and no drop handler: clicking sends an empty
               * `POST /api/uploads`, which the server refuses with 403 without
               * declaring or parsing a form. So no picker opens and no file is
               * chosen, sent, or read — and the control must not imply otherwise.
               */
              <button type="button" className="drop-target" onClick={tryLocalFiles}>
                Loading your own files is not enabled here. This control opens no file picker and
                takes no dropped file — select it and the server states its refusal.
              </button>
            )}
            {upload.name === 'blocked' && (
              <div className="upload-blocked" role="note">
                <ShieldCheck size={14} strokeWidth={2.1} aria-hidden="true" />
                <span>
                  <strong>Blocked by governance.</strong> {upload.reason}
                </span>
              </div>
            )}
            {upload.name === 'down' && (
              <BackendDown error={upload.error} onRetry={tryLocalFiles} />
            )}
            {/* R1b. "no file is read, parsed, or inspected" was an ABSOLUTE and
                false: `RecordValidator` and `CsvReconcilePanel` both read a
                file the reader picks. The refusal claim holds for the UPLOAD
                path and is kept, scoped to it; the two readers are named
                instead of denied. Pinned to the other two sites that make this
                claim (Governance → Policy, Settings → Data & Privacy) by
                `__tests__/upload-claim-parity.test.tsx`. */}
            <p className="onramp-warn">
              <TriangleAlert size={13} strokeWidth={2.2} aria-hidden="true" />
              Every file upload is refused outright, whatever it contains — the refused request is
              never read, parsed, or inspected. Two review tools elsewhere do read a file you paste
              or pick — the standalone Validator, and campaign-sheet CSV reconciliation — checking
              the text in memory, discarding it, and recording only the outcome, never the content.
              Keeping real or private artifacts out is the operator's responsibility, not a check
              this software performs.
            </p>
          </div>
        </div>

        {run.name === 'running' && (
          <div className="runner-status">
            <span className="dot dot-processing" aria-hidden="true" />
            <span className="runner-status-label">Example Run — Running</span>
            <span className="runner-status-note">calling the deterministic pipeline…</span>
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
