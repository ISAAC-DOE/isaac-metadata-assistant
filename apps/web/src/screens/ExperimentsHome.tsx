import './screens.css';
import { useEffect, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { ExperimentQueue } from '../components/ExperimentQueue';
import { TutorialPromotion } from '../components/TutorialPromotion';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
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
         * THE PERMANENT ORDINARY STATE, not a transient one — so it is written as
         * a real empty state rather than a one-line placeholder.
         *
         * This build has no way to create or import a record: there is no
         * `POST /api/experiments`, `create_experiment` has no production caller,
         * and `POST /api/uploads` refuses every upload by design. The five
         * built-in examples now exist only inside a worked-example session, so
         * this list is empty until an import capability exists.
         *
         * Copy rules this had to satisfy, each because the previous wording broke
         * one of them: it must not promise creation or import (the earlier "run
         * the synthetic demo to create your first record" did); it must not point
         * at the built-in example as if it were in this list (the wording it
         * replaces, "open the built-in example", did once the examples moved into
         * a session); and it must not blame the reader for an absence the
         * deployment caused.
         */
        <div className="queue-empty-state">
          <h2 className="queue-empty-title">No experiments yet</h2>
          <p className="queue-empty-body">
            Experiments you work on will appear here. This deployment cannot yet create or
            import a record, so nothing has been added.
          </p>
          <p className="queue-empty-body">In the meantime you can:</p>
          <ul className="queue-empty-list">
            <li>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate(`${ROUTES.governance}?tab=validator`)}
              >
                Open Validator
              </button>
              <span className="queue-empty-hint">
                Check a record file you already have against the official ISAAC schema.
              </span>
            </li>
            <li>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate(ROUTES.settings)}
              >
                {LABELS.actionReplayTutorial}
              </button>
              <span className="queue-empty-hint">
                Walk through a complete worked example in a temporary workspace of its own.
              </span>
            </li>
          </ul>
        </div>
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
        {/*
         * TWO CONTROLS WERE REMOVED FROM HERE, and neither was a styling choice.
         *
         * "Open the Worked Example" navigated to `/load`, whose own button calls
         * `POST /api/demo/run`; and "Reset Workspace" (ResetDemoDialog) calls
         * `POST /api/demo/reset`. Both endpoints now REQUIRE a worked-example
         * session header and refuse without one, writing nothing. Left mounted
         * here they would be dead controls in the ordinary workspace — a button
         * that looks like it acts and does not — which is exactly the failure
         * mode the P1 comment below was written about.
         *
         * They are not deleted: both are still correct INSIDE a worked-example
         * session, which is reached from Settings & API → Help & Tutorial. The
         * example records live only in such a session, so the controls that
         * rebuild them belong there too.
         *
         * Earlier P1 note, kept because it records why there is no create action:
         * a "New Record" button used to sit here, styled primary, navigating to
         * ROUTES.load. It promised a capability the build does not have — `/load`
         * offers the worked example and one permanently 403'd upload seam, and
         * nothing there accepts anything a user supplies. There is still no
         * record-creation route in this application, so no control here may imply
         * one.
         */}
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
