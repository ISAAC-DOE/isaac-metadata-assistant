import './screens.css';
import '../components/runner.css';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { GovernanceBanner } from '../components/GovernanceBanner';
import { StagedRunner } from '../components/StagedRunner';
import { Play, Upload, TriangleAlert } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api } from '../lib/api';
import { DEMO_ID } from '../lib/mock';

/**
 * S2 · Load Materials — the on-ramp. Synthetic-first. Progress maps to real
 * commands; the run pauses honestly at the 5 blockers. The local-files path is
 * present but governance-gated (structured only; real-looking → Governance).
 */
export function LoadMaterials() {
  const navigate = useNavigate();
  const stages = api.getRunnerStages();

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
              A fictional year-2099 CuO / Cu K-edge XANES session. Assembles 26 evidenced fields,
              holds back the 5 it won't guess, and — once you confirm them — reaches PASS against
              ISAAC v1.05.
            </p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate(ROUTES.record(DEMO_ID))}
            >
              {LABELS.actionRunDemoShort}
            </button>
          </div>

          <div className="onramp">
            <div className="onramp-head">
              <span className="onramp-icon neutral" aria-hidden="true">
                <Upload size={16} strokeWidth={2} />
              </span>
              <div>
                <div className="onramp-title">{LABELS.actionLoadLocal}</div>
                <div className="onramp-tagline">stays on this machine</div>
              </div>
              <span className="onramp-tag">Local-First</span>
            </div>
            <div className="drop-target">
              Drop <span className="mono">.csv</span> / <span className="mono">.xlsx</span> or an
              archive listing — structured formats only, unstructured extraction is not built yet.
            </div>
            <p className="onramp-warn">
              <TriangleAlert size={13} strokeWidth={2.2} aria-hidden="true" />
              A file that looks real or private is intercepted and routed to governance — nothing is
              extracted.
            </p>
          </div>
        </div>

        <div className="runner-status">
          <span className="dot dot-processing" aria-hidden="true" />
          <span className="runner-status-label">Synthetic Demo — In Progress</span>
          <span className="runner-status-note">paused for your input · your turn</span>
        </div>

        <StagedRunner stages={stages} onAnswer={() => navigate(ROUTES.complete(DEMO_ID))} />
      </div>
    </AppShell>
  );
}
