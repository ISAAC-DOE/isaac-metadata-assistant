import './screens.css';
import '../components/artifact.css';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { WorkflowSpine, buildSpine } from '../components/WorkflowSpine';
import { StatusBar } from '../components/StatusBar';
import { VerdictCard } from '../components/VerdictCard';
import { CoverageBadge } from '../components/CoverageBadge';
import { AdvisoryChip } from '../components/AdvisoryChip';
import { ArtifactCard } from '../components/ArtifactCard';
import { AssistantPanel } from '../components/AssistantPanel';
import { Shield } from '../components/icons';
import { ROUTES } from '../lib/routes';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { ASSISTANT_SAMPLES, ROUTE_TO_CLI_NOTE } from '../lib/assistant';
import { DEMO_RECORD_FILE, DEMO_TITLE } from '../lib/mock';

/**
 * S6 · Ready to Export — the trust readout. The deterministic verdict is the
 * largest thing on screen; coverage and advisory sit clearly beneath it as two
 * distinct, quieter cards; the record and sidecar are two separate artifacts.
 * Three signals, three treatments, never merged. Export enabled only on PASS.
 */
export function ExportReadiness() {
  const navigate = useNavigate();
  const { id = '' } = useParams();
  const signals = api.getSignals();
  const artifacts = api.getArtifacts();
  const graph = api.getGraphStatus();

  const validation = signals.validation;
  const coverage = signals.coverage;

  const spine = buildSpine('validate', {
    complete: { meta: '5 of 5 answered' },
    validate: { meta: 'viewing results' },
  });

  const rightPanel = (
    <aside className="record-right narrow" aria-label="Assistant">
      <AssistantPanel
        reply={ASSISTANT_SAMPLES.export.reply}
        prompts={ASSISTANT_SAMPLES.export.prompts}
        freshness={graph.status}
        note={ROUTE_TO_CLI_NOTE}
      />
    </aside>
  );

  return (
    <AppShell
      variant="record"
      topBar={<TopBar variant="record" title={DEMO_TITLE} filename={DEMO_RECORD_FILE} />}
      sidebar={<WorkflowSpine steps={spine} />}
      rightPanel={rightPanel}
      statusBar={
        <StatusBar
          validation={validation}
          coverage={coverage}
          advisory={signals.advisory}
        />
      }
      mainPad="pad"
    >
      {validation !== 'pending' && (
        <VerdictCard
          result={validation}
          onRevalidate={() => undefined}
          onBackToComplete={() => navigate(ROUTES.complete(id))}
        />
      )}

      {validation !== 'pending' && validation.verdict === 'pass' && (
        <>
          <div className="signal-row">
            {coverage !== 'pending' && <CoverageBadge audit={coverage} />}
            <AdvisoryChip
              advisory={signals.advisory}
              explain="A clean local run is not portal sign-off — the upstream validator isn't vendored here."
            />
          </div>

          <div className="ready-heading">
            <span className="dot dot-ready" aria-hidden="true" />
            <span className="ready-label">{LABELS.groupReady}</span>
            <span className="ready-note">
              — doubly gated: no-guessing checks passed, then official schema.
            </span>
          </div>

          <div className="artifact-row">
            {artifacts.map((artifact) => (
              <ArtifactCard artifact={artifact} key={artifact.kind} />
            ))}
          </div>

          <div className="sidecar-note" role="note">
            <Shield size={16} strokeWidth={2} aria-hidden="true" style={{ flex: 'none', color: 'var(--text-slate)' }} />
            <span>
              <strong>Review the sidecar before sharing.</strong> It can carry source paths, URIs and
              hashes. Records are written once — immutable via the CLI, no hand-edit, no overwrite.
            </span>
          </div>
        </>
      )}
    </AppShell>
  );
}
