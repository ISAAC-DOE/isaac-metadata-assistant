import './screens.css';
import { useEffect, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { ExperimentQueue } from '../components/ExperimentQueue';
import { ResetDemoDialog } from '../components/ResetDemoDialog';
import { TutorialPromotion } from '../components/TutorialPromotion';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Play } from '../components/icons';
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

  // P27.6 — the dashboard is NOT tightly polled (no interval). It only refetches
  // the list once when the tab regains visibility, so a cross-tab reset/export
  // shows up on return — silently (no loading-flip blank on every refocus),
  // consistent with the rest of P27.6.
  const { reloadSilent } = result;
  useEffect(() => {
    const onVisibility = () => {
      if (!document.hidden) reloadSilent();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [reloadSilent]);

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
        /*
         * P1: the previous copy ("run the synthetic demo to create your first
         * record") promised something this build cannot do. `POST /api/demo/run`
         * writes NOTHING when its canonical target still holds seed content, and
         * `ensure_seeded()` restores all five built-in examples on its own — so a
         * user never creates a record here. The copy now points at what exists.
         */
        <p className="queue-empty">
          No experiments yet — open the built-in example to see a complete record.
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
          <ResetDemoDialog onResetComplete={result.reload} />
          {/*
           * P1: there used to be a SECOND button here, labelled "New Record",
           * styled btn-primary and navigating to ROUTES.load — the same route as
           * this one. It promised a capability the build does not have: `/load`
           * offers the worked example and one permanently 403'd upload seam, and
           * nothing there accepts anything a user supplies. It was removed rather
           * than relabelled, because a duplicate control to a single destination
           * is not worth keeping under any wording. This button inherits the
           * primary treatment it vacated: it is the one affirmative action on the
           * screen, and Reset Workspace must stay the restrained one.
           */}
          <button type="button" className="btn btn-primary" onClick={() => navigate(ROUTES.load)}>
            <Play size={14} strokeWidth={2} aria-hidden="true" />
            {LABELS.actionRunDemo}
          </button>
        </div>
      </div>

      {/*
        The guided walkthrough's first-run offer. Rendered only on the LOADED
        branch: offering a tour of the app over the top of "Backend Not Running"
        would be an invitation to a tour that cannot start, and offering it over
        the loading state would make it flicker on every visit. It disappears for
        good once the walkthrough is finished — no permanent replay card sits in
        the primary workflow (that control lives in Settings & API → Help &
        Tutorial).
      */}
      {result.status === 'data' && <TutorialPromotion />}

      {body}
    </AppShell>
  );
}
