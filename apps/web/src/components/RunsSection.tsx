/*
 * THE RUNS SECTION — the list, and the one control that adds to it.
 *
 * WHY IT OWNS ITS OWN FETCH rather than joining the record bundle. The bundle
 * is eight concurrent reads that every record screen performs; runs are needed
 * by ONE of them. Fetching separately also means a Run API that is unavailable
 * degrades to a contained panel inside this section instead of taking the whole
 * record screen down with it — the field workbench above still renders, and the
 * reader is told which part is missing.
 *
 * THE EXPERIMENT VERSION IS HELD HERE, and this is the one piece of state that
 * needs saying twice. Creating a run mutates the EXPERIMENT, so it carries the
 * experiment's `If-Match`; the create response returns the experiment's NEW
 * version, which is what the next create must carry. Reading it from the record
 * bundle's `detail.version` instead would be stale from the first create
 * onwards, and every subsequent Add Run would be a 412 the reader could do
 * nothing about.
 */

import './runs.css';
import { useCallback, useState } from 'react';
import { RunCard } from './RunCard';
import { LoadingPanel, BackendDown } from './FetchStates';
import { Plus } from './icons';
import { api, ApiError } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import type { ApiRunsResponse, ApiRunView } from '../lib/types';

export function RunsSection({ experimentId }: { experimentId: string }) {
  const listing = useFetch(() => api.listRuns(experimentId), [experimentId]);

  return (
    <section className="runs-section" aria-labelledby="runs-heading">
      <div className="runs-head">
        <h2 className="runs-title" id="runs-heading">
          Runs
        </h2>
        <p className="runs-sub">
          One run per set of measurement conditions. Values entered here belong to this run
          alone; everything under Inherited from Experiment is read from the experiment.
        </p>
      </div>

      {listing.status === 'loading' && <LoadingPanel label="Loading this experiment's runs…" />}
      {listing.status === 'error' && (
        <BackendDown error={listing.error} onRetry={listing.reload} />
      )}
      {listing.status === 'data' && (
        // Keyed on the experiment so switching records rebuilds the list state
        // rather than carrying one record's runs into another's.
        <RunsList key={experimentId} experimentId={experimentId} initial={listing.data} />
      )}
    </section>
  );
}

function RunsList({
  experimentId,
  initial,
}: {
  experimentId: string;
  initial: ApiRunsResponse;
}) {
  const [runs, setRuns] = useState<ApiRunView[]>(initial.runs);
  const [experimentVersion, setExperimentVersion] = useState(initial.experiment_version);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [focusRunId, setFocusRunId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  /*
   * ONE RUN IS REPLACED BY ID, and never by position. Two runs on one screen
   * each hold their own autosave state, their own version and their own edits;
   * a splice by index would attach one run's server response to whichever card
   * happened to be in that slot.
   */
  const replaceRun = useCallback((next: ApiRunView) => {
    setRuns((prev) => prev.map((r) => (r.id === next.id ? next : r)));
  }, []);

  const addRun = () => {
    setAdding(true);
    setAddError(null);
    api
      .createRun(experimentId, { experimentVersion })
      .then((res) => {
        setRuns((prev) => [...prev, res.run]);
        setExperimentVersion(res.experiment_version);
        setExpanded((prev) => ({ ...prev, [res.run.id]: true }));
        setFocusRunId(res.run.id);
        setAdding(false);
      })
      .catch((err: unknown) => {
        setAdding(false);
        // The message is whatever could be ESTABLISHED. A 412 is named as what
        // it is — this experiment moved on — because the remedy differs from
        // every other failure: reload, do not retry.
        const status = err instanceof ApiError ? err.status : undefined;
        if (status === 412) {
          setAddError(
            'This experiment changed somewhere else, so the run was not created. Reload the page to pick up the current version.',
          );
          return;
        }
        setAddError(
          err instanceof Error ? err.message : 'The run could not be created.',
        );
      });
  };

  return (
    <>
      <div className="runs-toolbar">
        <button type="button" className="btn btn-primary" onClick={addRun} disabled={adding}>
          <Plus size={15} strokeWidth={2.2} aria-hidden="true" />
          {adding ? 'Adding Run…' : 'Add Run'}
        </button>
        <span className="runs-count">
          {runs.length} {runs.length === 1 ? 'run' : 'runs'}
        </span>
      </div>

      {addError !== null && (
        <p className="runs-error" role="alert">
          {addError}
        </p>
      )}

      {runs.length === 0 ? (
        <p className="runs-empty">
          No runs yet. Add one for the first set of conditions you measured.
        </p>
      ) : (
        <div className="runs-list">
          {runs.map((run) => (
            <RunCard
              key={run.id}
              experimentId={experimentId}
              run={run}
              expanded={expanded[run.id] ?? false}
              onToggle={() =>
                setExpanded((prev) => ({ ...prev, [run.id]: !(prev[run.id] ?? false) }))
              }
              onRun={replaceRun}
              focusOnMount={focusRunId === run.id}
              onFocused={() => setFocusRunId(null)}
            />
          ))}
        </div>
      )}
    </>
  );
}
