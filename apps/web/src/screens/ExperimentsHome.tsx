import './screens.css';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { ExperimentQueue } from '../components/ExperimentQueue';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Play, Plus } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { queueSubcount, summariesToQueueGroups } from '../lib/adapt';

/**
 * S1 · My Experiments — home queue, live from `GET /api/experiments`. Answers
 * "what needs me next?" — not a KPI dashboard. Groups are derived from the
 * server-supplied status only. API down → the honest "Backend Not Running" state.
 */
export function ExperimentsHome() {
  const navigate = useNavigate();
  const result = useFetch(() => api.listExperiments(), []);

  let subcount = '';
  let body: ReactNode;

  if (result.status === 'loading') {
    body = <LoadingPanel label="Loading your experiments…" />;
  } else if (result.status === 'error') {
    body = <BackendDown error={result.error} onRetry={result.reload} />;
  } else {
    const summaries = result.data;
    subcount = queueSubcount(summaries);
    const groups = summariesToQueueGroups(summaries);
    body =
      groups.length > 0 ? (
        <ExperimentQueue groups={groups} />
      ) : (
        <p className="queue-empty">
          No experiments yet — run the synthetic demo to create your first record.
        </p>
      );
  }

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
          {subcount && <p className="page-subcount">{subcount}</p>}
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

      {body}
    </AppShell>
  );
}
