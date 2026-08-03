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

/** The `error` discriminator the backend sends with its 409 demo-run refusal. */
const DEMO_TARGET_DRIFTED = 'demo_target_drifted';

/**
 * Recognise the ONE refusal this screen states differently: `POST /api/demo/run`
 * answering 409 `demo_target_drifted` because the canonical scenario has been
 * edited and re-seeding would discard that work.
 *
 * Narrow on purpose. Anything else — a different 409, a missing/garbled body, an
 * edge sign-in page, an unreachable backend — falls through to the existing
 * error state, because claiming "your scenario was protected" about a failure we
 * did not observe would be exactly the same class of lie as the `BackendDown`
 * this branch replaces. Returns the refusal's scenario id when the body carries
 * one; the id is optional, its absence must not suppress the refusal.
 */
function driftRefusal(error: ApiError): { experimentId?: string } | null {
  if (error.status !== 409 || error.htmlIntercept) return null;
  const body = error.body;
  if (typeof body !== 'object' || body === null) return null;
  const { error: code, experiment_id: id } = body as Record<string, unknown>;
  if (code !== DEMO_TARGET_DRIFTED) return null;
  return { experimentId: typeof id === 'string' && id !== '' ? id : undefined };
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
        const refusal = driftRefusal(error);
        setRun(
          refusal
            ? { name: 'drifted', experimentId: refusal.experimentId }
            : { name: 'error', error },
        );
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
            <p className="onramp-warn">
              <TriangleAlert size={13} strokeWidth={2.2} aria-hidden="true" />
              Every file upload is refused outright, whatever it contains — no file is read, parsed,
              or inspected. Keeping real or private artifacts out is the operator's responsibility,
              not a check this software performs.
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
