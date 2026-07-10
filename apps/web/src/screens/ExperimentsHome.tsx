import './screens.css';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { ExperimentQueue } from '../components/ExperimentQueue';
import { Play, Plus } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api } from '../lib/api';

/**
 * S1 · My Experiments — home queue. Answers "what needs me next?" — not a KPI
 * dashboard. Project Memory is a separate LeftNav destination, never in the queue.
 */
export function ExperimentsHome() {
  const navigate = useNavigate();
  const groups = api.listExperiments();

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="experiments" />}
      mainPad="pad"
    >
      <div className="page-header">
        <div>
          <h1 className="page-title">{LABELS.screenExperiments}</h1>
          <p className="page-subcount">6 experiments · 1 ready to export</p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-secondary" onClick={() => navigate(ROUTES.load)}>
            <Play size={14} strokeWidth={2} aria-hidden="true" />
            {LABELS.actionRunDemo}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => navigate(ROUTES.load)}>
            <Plus size={15} strokeWidth={2.2} aria-hidden="true" />
            {LABELS.actionNewRecord}
          </button>
        </div>
      </div>

      <ExperimentQueue groups={groups} />
    </AppShell>
  );
}
