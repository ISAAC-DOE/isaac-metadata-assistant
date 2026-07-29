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
  | { name: 'error'; error: ApiError }
  | { name: 'done'; result: ApiDemoRunResponse };

type UploadPhase =
  | { name: 'idle' }
  | { name: 'blocked'; reason: string } // the server's 403 governance refusal, verbatim
  | { name: 'down'; error: ApiError }; // backend unreachable — show BackendDown, never stand-in copy

// Shown only when the server responded but its refusal body carried no reason.
const UPLOADS_GATED_FALLBACK =
  'Uploads are approval-gated and not enabled in this synthetic prototype.';

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
      .catch((error: ApiError) => setRun({ name: 'error', error }));
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
      topBar={<TopBar variant="breadcrumb" breadcrumb={LABELS.actionNewRecord} />}
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
                <div className="onramp-title">Run the Synthetic Demo</div>
                <div className="onramp-tagline">the reference happy path · ~10s</div>
              </div>
              <span className="onramp-tag">Safe · Fake</span>
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
            <span className="runner-status-label">Synthetic Demo — Running</span>
            <span className="runner-status-note">calling the deterministic pipeline…</span>
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
              <span className="runner-status-label">Synthetic Demo — Draft Assembled</span>
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
