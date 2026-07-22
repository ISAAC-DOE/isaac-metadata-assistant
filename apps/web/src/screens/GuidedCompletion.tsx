import './screens.css';
import '../components/assistant.css';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { WorkflowSpine, buildSpine } from '../components/WorkflowSpine';
import { StatusBar } from '../components/StatusBar';
import { GuidedPrompt } from '../components/GuidedPrompt';
import { StatusChip } from '../components/StatusChip';
import { AssistantPanel } from '../components/AssistantPanel';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Check, CircleHelp } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api, ApiError } from '../lib/api';
import { compose } from '../lib/assistantComposer';
import { useFetch } from '../lib/useFetch';
import { answerValuePreview, pendingItemToBlocker } from '../lib/adapt';
import type { ApiExperimentDetail, ApiPendingItem } from '../lib/types';

/**
 * S4 · Complete Missing Fields — guided, one-question-at-a-time completion of the
 * `draft.pending[]` blockers, live from the backend. Forms-first. Confirming an
 * answer POSTs `{answers, confirmed_by_user:true}` and the backend returns the
 * shrunken pending list. "I don't know" sends NOTHING and leaves the field
 * honestly missing. The assistant never types a scientific value — a structured
 * series/descriptor is only *confirmed* from the labeled synthetic demo answer.
 */
export function GuidedCompletion() {
  const { id = '' } = useParams();
  const load = useFetch(
    () =>
      Promise.all([api.getExperiment(id), api.getPending(id)]).then(([detail, pending]) => ({
        detail,
        pending,
      })),
    [id],
  );

  if (load.status !== 'data') {
    return (
      <AppShell
        variant="record"
        topBar={<TopBar variant="record" title={LABELS.screenComplete} recordId={id} />}
        sidebar={<WorkflowSpine steps={buildSpine('complete')} recordId={id} />}
        mainPad="centered"
      >
        {load.status === 'loading' ? (
          <LoadingPanel label="Loading the blockers from the local backend…" />
        ) : (
          <BackendDown error={load.error} onRetry={load.reload} />
        )}
      </AppShell>
    );
  }

  return (
    <LoadedCompletion
      key={id}
      id={id}
      detail={load.data.detail}
      initialPending={load.data.pending}
      reload={load.reload}
    />
  );
}

interface Answered {
  id: string;
  label: string;
  storedValue: string;
}

function LoadedCompletion({
  id,
  detail,
  initialPending,
  reload,
}: {
  id: string;
  detail: ApiExperimentDetail;
  initialPending: ApiPendingItem[];
  reload: () => void;
}) {
  const navigate = useNavigate();
  const [pending, setPending] = useState<ApiPendingItem[]>(initialPending);
  const [answered, setAnswered] = useState<Answered[]>([]);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<ApiError | null>(null);
  // P27.5 — the optimistic-concurrency token. Initialized from the loaded detail
  // and re-adopted from every accepted answer response; sent as If-Match on the
  // next submit so a concurrent edit elsewhere is caught (412) instead of clobbered.
  const [currentVersion, setCurrentVersion] = useState(detail.version);

  const total = answered.length + pending.length;
  const remaining = pending.length;
  const currentItem = useMemo(
    () => pending.find((p) => !skipped.has(p.id)),
    [pending, skipped],
  );
  const skippedItems = pending.filter((p) => skipped.has(p.id));
  const upcomingItems = pending.filter(
    (p) => p.id !== currentItem?.id && !skipped.has(p.id),
  );

  const confirmAnswer = (blockerId: string, kind: string, label: string, value: unknown) => {
    setSubmitting(true);
    setSubmitError(null);
    api
      .submitAnswer(id, { [blockerId]: value }, currentVersion)
      .then((resp) => {
        setPending(resp.pending);
        setCurrentVersion(resp.version); // adopt the fresh token for the next submit
        setSkipped((prev) => {
          if (!prev.has(blockerId)) return prev;
          const next = new Set(prev);
          next.delete(blockerId);
          return next;
        });
        setAnswered((prev) => [
          ...prev,
          { id: blockerId, label, storedValue: answerValuePreview(kind, value) },
        ]);
      })
      .catch((err: ApiError) => setSubmitError(err))
      .finally(() => setSubmitting(false));
  };

  const leaveMissing = (blockerId: string) => {
    setSkipped((prev) => new Set(prev).add(blockerId));
  };

  const answerLater = (blockerId: string) => {
    setSkipped((prev) => {
      const next = new Set(prev);
      next.delete(blockerId);
      return next;
    });
  };

  const spine = buildSpine(remaining === 0 ? 'export' : 'complete', {
    draft: { meta: `${detail.evidenced_field_count} fields reviewed` },
    complete: {
      number: answered.length,
      // Only claim a real ratio — `total === 0` (no blockers ever existed) has
      // nothing honest to count, so leave meta unset rather than render the
      // same dishonest "0 of 0" the counter above was fixed to avoid.
      ...(total > 0 ? { meta: `${answered.length} of ${total} answered` } : {}),
    },
    export: {
      meta: remaining === 0 ? 'ready to export' : `${remaining} to go`,
    },
  });

  const statusBar =
    remaining === 0 ? (
      <StatusBar
        phase="All blockers resolved · ready to export"
        phaseDot="ready"
        note="Every field is confirmed or resolved — export is now unlocked."
      />
    ) : (
      <StatusBar
        phase={`${remaining} of ${total} fields still to confirm`}
        note="Export unlocks automatically once every field is confirmed or honestly left missing."
      />
    );

  // P25.6: the grounded assistant now mounts in the Complete context (Phase 25
  // plan §20). It is subordinate — the guided completion form (truth) renders
  // first; the assistant only echoes the pending queue this screen already holds
  // and routes the "does missing block export?" truth question to Validate. It
  // adds NO fetch (Q-D: {detail, pending} only) and never drives
  // propose→stage→confirm. `selectedPendingId = currentItem?.id` keeps the
  // "what does this question want?" answer aligned with the active question.
  // Mounted on BOTH loaded branches via `shell`, never on loading / backend-down.
  const rightPanel = (
    <aside className="record-right narrow" aria-label="Assistant">
      <AssistantPanel
        {...compose({
          context: 'complete',
          detail,
          pending,
          selectedPendingId: currentItem?.id,
        })}
        // P25.7: this screen loads only {detail, pending} — it never consults the
        // memory/graph plane, so it makes NO memory-availability claim. We pass
        // no `availability`, and the panel then renders neither the `memory:`
        // head line nor any memory caveat. (Previously it passed
        // availability="available" to dodge the spec-§6-flagged-false caveat;
        // omitting it is the honest fix — the screen never fetched graph status.)
      />
    </aside>
  );

  const shell = (children: ReactNode) => (
    <AppShell
      variant="record"
      topBar={
        <TopBar
          variant="record"
          title={detail.title}
          filename={`draft · ${detail.id}`}
          recordId={id}
          surface={LABELS.screenComplete}
        />
      }
      sidebar={<WorkflowSpine steps={spine} recordId={id} />}
      rightPanel={rightPanel}
      statusBar={statusBar}
      mainPad="centered"
    >
      <div className="centered-col narrow">{children}</div>
    </AppShell>
  );

  const answeredRows = answered.map((ans) => (
    <div className="answered-row" key={ans.id}>
      <span className="answered-check" aria-hidden="true">
        <Check size={13} strokeWidth={2.6} />
      </span>
      <span className="answered-label">{ans.label}</span>
      <span className="answered-stored">stored {ans.storedValue}</span>
      <span className="answered-trailing">
        <StatusChip kind="confirmed" />
      </span>
    </div>
  ));

  // Finished: 0 remaining -> ready to export (route to S6). Also covers the
  // "0 blockers on arrival" case.
  if (remaining === 0) {
    return shell(
      <>
        <div className="completion-header">
          <h1 className="completion-title">All Fields Resolved</h1>
          <span className={`completion-counter${total === 0 ? ' completion-counter-prose' : ''}`}>
            {total === 0 ? 'No open questions.' : `${answered.length} / ${total}`}
          </span>
        </div>
        {answeredRows}
        <div className="completion-done" role="status">
          <span className="dot dot-ready" aria-hidden="true" />
          <div>
            <div className="completion-done-title">This record is ready to export.</div>
            <p className="completion-done-text">
              Every blocker the system refused to guess is now confirmed or resolved. The official
              schema check runs next, on the Ready to Export screen.
            </p>
          </div>
        </div>
        <div className="completion-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate(ROUTES.export(id))}
          >
            Go to Ready to Export →
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate(ROUTES.record(id))}
          >
            ← Back to Review Record
          </button>
        </div>
      </>,
    );
  }

  const blocker = currentItem ? pendingItemToBlocker(currentItem) : null;

  return shell(
    <>
      <div className="completion-header">
        <h1 className="completion-title">Answer {total} Questions to Finish This Record</h1>
        <span className="completion-counter">
          {answered.length} / {total}
        </span>
      </div>

      <div className="progress" role="img" aria-label={`${answered.length} of ${total} answered`}>
        {Array.from({ length: total }).map((_, i) => (
          <span
            key={i}
            className={`progress-seg${
              i < answered.length ? ' answered' : i === answered.length && blocker ? ' current' : ''
            }`}
          />
        ))}
      </div>

      {answeredRows}

      {blocker && (
        <div style={{ marginTop: 10 }}>
          <GuidedPrompt
            key={blocker.id}
            blocker={blocker}
            index={Math.min(answered.length + skippedItems.length, total - 1)}
            total={total}
            submitting={submitting}
            onConfirm={(value) => confirmAnswer(blocker.id, blocker.kind, blocker.label, value)}
            onDontKnow={() => leaveMissing(blocker.id)}
          />
        </div>
      )}

      {upcomingItems.map((item, i) => (
        <div className="upcoming-row" key={item.id}>
          <span className="upcoming-num" aria-hidden="true">
            {answered.length + skippedItems.length + 2 + i}
          </span>
          <span className="upcoming-label">{item.question}</span>
          <span className="upcoming-path">{item.about ?? item.kind}</span>
        </div>
      ))}

      {!blocker && skippedItems.length > 0 && (
        <div className="completion-allskipped" role="note">
          <div className="completion-allskipped-title">
            You've reviewed every question · {skippedItems.length} left honestly missing
          </div>
          <p className="completion-allskipped-text">
            Nothing was invented for these. Export stays gated until each is confirmed — answer one
            when you're ready, or return to the record.
          </p>
        </div>
      )}

      {submitError && (
        <div style={{ marginTop: 12 }}>
          {submitError.unreachable ? (
            <BackendDown error={submitError} onRetry={() => setSubmitError(null)} />
          ) : submitError.status === 412 ? (
            // P27.5 stale write: a concurrent edit changed the record. Nothing was
            // applied and the user's staged/unsent input stays put (GuidedPrompt is
            // not unmounted here). Refresh re-fetches current state via the parent
            // useFetch reload — no auto-retry, no auto-merge.
            <div className="completion-submit-error" role="alert">
              This record changed elsewhere. Nothing was applied — your input is kept. Refresh to
              load the current state.
              <button
                type="button"
                className="btn btn-secondary"
                style={{ marginLeft: 10 }}
                onClick={reload}
              >
                Refresh
              </button>
            </div>
          ) : (
            <div className="completion-submit-error" role="alert">
              That answer could not be applied ({submitError.status ?? 'error'}). Nothing was
              changed — try again.
            </div>
          )}
        </div>
      )}

      {skippedItems.length > 0 && (
        <div className="leftmissing">
          <div className="leftmissing-eyebrow eyebrow">Left Honestly Missing</div>
          {skippedItems.map((item) => (
            <div className="leftmissing-row" key={item.id}>
              <CircleHelp size={14} strokeWidth={2} aria-hidden="true" />
              <span className="leftmissing-q">{item.question}</span>
              <button
                type="button"
                className="leftmissing-answer"
                onClick={() => answerLater(item.id)}
              >
                Answer now
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="completion-actions" style={{ marginTop: 18 }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => navigate(ROUTES.record(id))}
        >
          ← Back to Review Record
        </button>
      </div>
    </>,
  );
}
