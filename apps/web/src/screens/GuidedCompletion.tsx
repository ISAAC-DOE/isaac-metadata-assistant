import './screens.css';
import '../components/assistant.css';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { WorkflowSpine } from '../components/WorkflowSpine';
import { StatusBar } from '../components/StatusBar';
import { GuidedPrompt } from '../components/GuidedPrompt';
import { StatusChip } from '../components/StatusChip';
import { AssistantPanel } from '../components/AssistantPanel';
import { AssistantDrawer } from '../components/AssistantDrawer';
import { LiveSyncNote } from '../components/LiveSyncNote';
import { WorkflowProgressBanner } from '../components/WorkflowProgressBanner';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Check, CircleHelp, Pencil } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api, ApiError } from '../lib/api';
import { compose } from '../lib/assistantComposer';
import { useFetch } from '../lib/useFetch';
import { useRecordSession } from '../lib/useRecordSession';
import { answerValuePreview, pendingItemToBlocker } from '../lib/adapt';
import type {
  ApiExperimentDetail,
  ApiInvalidation,
  ApiPendingItem,
  PendingBlocker,
} from '../lib/types';

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
        sidebar={<WorkflowSpine workflow={null} recordId={id} />}
        mainPad="centered"
        width="readable"
      >
        {/* M1 (P33 S6) — the non-data branch renders FetchStates' <h2> with no
            <h1>; give the surface a screen-level heading so its document outline
            starts at h1 like every other routed surface (A11Y-1 contract). */}
        <h1 className="sr-only">{LABELS.screenComplete}</h1>
        {load.status === 'loading' ? (
          <LoadingPanel label="Loading the blockers from the ISAAC API…" />
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
  /** The raw confirmed value, kept so an Edit can prefill the current value. */
  rawValue: unknown;
  /** The originating blocker, kept so an Edit can reconstruct the GuidedPrompt. */
  blocker: PendingBlocker;
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
  // P28.3 — summary-first edit of an already-confirmed field. `editingId` is the
  // answered row currently in inline edit mode (null = all read-only summary).
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<ApiError | null>(null);
  // The last successful edit's downstream-invalidation (P28.2), surfaced honestly
  // (reason + reopened/stale note). Never locally re-derived — server-reported.
  const [editImpact, setEditImpact] = useState<ApiInvalidation | null>(null);
  // P27.5 — the optimistic-concurrency token. Initialized from the loaded detail
  // and re-adopted from every accepted answer response; sent as If-Match on the
  // next submit so a concurrent edit elsewhere is caught (412) instead of clobbered.
  const [currentVersion, setCurrentVersion] = useState(detail.version);

  // P27.6 — this surface holds STAGED, unsent input (the GuidedPrompt field), so
  // a change signal must NOT auto-refetch (that would discard the input) and must
  // NOT auto-merge. We only raise a proactive "changed elsewhere" banner; the
  // submit stays ETag-guarded, so a stale submit still gets a 412 as the hard
  // backstop. Refresh (below) re-loads via the parent and re-adopts the fresh
  // version, which remounts this component and clears the banner + staged input.
  const [changedElsewhere, setChangedElsewhere] = useState(false);
  // P29.4 — the ONE shared record-session owner. This surface holds STAGED,
  // unsent input, so the owner's `onChange` must ONLY raise the proactive banner
  // (never auto-refetch / auto-merge, which would discard the input). The owner
  // still invalidates any stale staged assistant proposal and exposes the SAME
  // authoritative version/AgentContext the assistant reads, so the assistant and
  // this form can never disagree on the current revision.
  const session = useRecordSession(id, {
    detail: { ...detail, version: currentVersion },
    onChange: () => setChangedElsewhere(true),
  });
  const degraded = session.syncDegraded;

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

  const confirmAnswer = (blocker: PendingBlocker, value: unknown) => {
    setSubmitting(true);
    setSubmitError(null);
    api
      .submitAnswer(id, { [blocker.id]: value }, currentVersion)
      .then((resp) => {
        setPending(resp.pending);
        setCurrentVersion(resp.version); // adopt the fresh token for the next submit
        setSkipped((prev) => {
          if (!prev.has(blocker.id)) return prev;
          const next = new Set(prev);
          next.delete(blocker.id);
          return next;
        });
        setAnswered((prev) => [
          ...prev,
          {
            id: blocker.id,
            label: blocker.label,
            storedValue: answerValuePreview(blocker.kind, value),
            rawValue: value,
            blocker,
          },
        ]);
      })
      .catch((err: ApiError) => setSubmitError(err))
      .finally(() => setSubmitting(false));
  };

  // P28.3 — enter/leave inline edit for one answered row. Entering clears any prior
  // edit error/impact; Cancel restores the summary with NO API call and NO mutation.
  const startEdit = (rowId: string) => {
    setEditingId(rowId);
    setEditError(null);
    setEditImpact(null);
  };
  const cancelEdit = () => {
    setEditingId(null);
    setEditError(null);
  };

  // Save a correction: POST /edit with the held If-Match token (P27.5), adopt the
  // fresh version, update the summary row's value, and surface the server-reported
  // downstream impact. A 412 keeps the editor mounted (input preserved) and shows
  // the existing stale-write recovery banner. An unchanged submit is a backend
  // no-op (200) — the row simply stays as it was.
  const saveEdit = (blocker: PendingBlocker, value: unknown) => {
    setEditSubmitting(true);
    setEditError(null);
    api
      .editField(id, { [blocker.id]: value }, currentVersion)
      .then((resp) => {
        setCurrentVersion(resp.version);
        setPending(resp.pending);
        setAnswered((prev) =>
          prev.map((a) =>
            a.id === blocker.id
              ? { ...a, storedValue: answerValuePreview(blocker.kind, value), rawValue: value }
              : a,
          ),
        );
        setEditImpact(resp.invalidation);
        setEditingId(null);
      })
      .catch((err: ApiError) => setEditError(err))
      .finally(() => setEditSubmitting(false));
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

  const statusBar =
    remaining === 0 ? (
      <StatusBar
        phase="All blockers resolved · ready to export"
        phaseDot="ready"
        note="Every field is confirmed or resolved — export is now unlocked."
      />
    ) : (
      // R1b — the note used to read "Export unlocks automatically once every field
      // is confirmed or honestly left missing." The second half was false: export
      // requires `pending_count == 0` (apps/api/isaac_api/workflow.py:
      // `complete_metadata = pending_count == 0`), and pressing "I don't know"
      // sends nothing and leaves the question in `pending`. So leaving a field
      // honestly missing never unlocks export — and this screen's own
      // skipped-list copy already said the opposite ("Export stays gated until
      // each is confirmed"), so the surface contradicted itself.
      <StatusBar
        phase={`${remaining} of ${total} fields still to confirm`}
        note="Export unlocks once every field is confirmed. Saying you don't know keeps a question open — the system will not invent a value for it."
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
  // P29.6 — the assistant's narrow staging option for the current pending field:
  // its identity + the SAME labeled synthetic demo value the manual GuidedPrompt
  // offers. No demo value (e.g. a pasted-hash blocker) ⇒ no `suggestedValue`, so
  // the assistant surfaces no staging trigger and never invents one.
  const currentBlocker = currentItem ? pendingItemToBlocker(currentItem) : null;
  const stageField = currentBlocker
    ? {
        id: currentBlocker.id,
        label: currentBlocker.about ?? currentBlocker.question ?? currentBlocker.id,
        suggestedValue: currentBlocker.demo_answer?.value,
        suggestedValueLabel: currentBlocker.demo_answer?.label,
      }
    : undefined;

  const rightPanel = (
    <AssistantDrawer railClassName="record-right narrow">
      <AssistantPanel
        {...compose({
          context: 'complete',
          detail,
          pending,
          selectedPendingId: currentItem?.id,
        })}
        experimentId={detail.id}
        recordRev={detail.rev}
        agentContext={session.context}
        degraded={session.degraded}
        // P29.6 — the current pending question is the ONE field the assistant may
        // offer to STAGE an answer for. It reuses the SAME labeled synthetic demo
        // value the manual GuidedPrompt exposes via "Use This Suggestion" (the
        // assistant never invents a value — no `suggestedValue` ⇒ no trigger); the
        // user selects it, it is guarded through `proposeForField(source:'user')`
        // into an UNCONFIRMED card, and Confirm writes through the SAME
        // confirmProposal path the manual form's If-Match uses. `reload` re-syncs
        // BOTH surfaces after a write (unmount→remount re-fetches detail+pending);
        // the manual GuidedPrompt below still works independently (manual parity).
        stageField={stageField}
        onRefresh={reload}
        // P25.7: this screen loads only {detail, pending} — it never consults the
        // memory/graph plane, so it makes NO memory-availability claim. We pass
        // no `availability`, and the panel then renders neither the `memory:`
        // head line nor any memory caveat. (Previously it passed
        // availability="available" to dodge the spec-§6-flagged-false caveat;
        // omitting it is the honest fix — the screen never fetched graph status.)
      />
    </AssistantDrawer>
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
      sidebar={<WorkflowSpine workflow={detail.workflow} recordId={id} />}
      rightPanel={rightPanel}
      statusBar={statusBar}
      mainPad="centered"
      /* One question at a time — a reading/answering surface, not a workbench.
         `readable` (760px) is the shared token for that measure; it supersedes
         the local 720px `.centered-col.narrow` literal, which stays as the
         fallback for screens that do not opt in. */
      width="readable"
    >
      <div className="centered-col narrow">{children}</div>
    </AppShell>
  );

  // P27.6 — the proactive "changed elsewhere" notice (input-preserving) + the
  // degraded indicator. Rendered at the top of both loaded branches. Refresh
  // uses the parent reload, which remounts LoadedCompletion (fresh detail +
  // version) and thereby clears the banner and re-adopts the current token.
  const liveNotes = (
    <>
      {changedElsewhere && (
        <div className="livesync-changed completion-submit-error" role="status">
          <span className="livesync-changed-text">
            This record changed elsewhere. Your input is kept — review the current record before
            submitting.
          </span>
          <button type="button" className="btn btn-secondary" onClick={reload}>
            Refresh
          </button>
        </div>
      )}
      <LiveSyncNote degraded={degraded} onRefresh={reload} />
      <WorkflowProgressBanner
        workflow={detail.workflow}
        recordId={id}
        pendingCount={detail.pending_count}
      />
    </>
  );

  // P28.3 stale-write recovery banner for an in-flight edit (reuses the SAME
  // wording + Refresh path as the answer 412). The editor stays mounted so the
  // input is preserved; Refresh reloads current state (no auto-merge).
  const editErrorBanner = editError && (
    <div style={{ marginTop: 10 }}>
      {editError.unreachable ? (
        <BackendDown error={editError} onRetry={() => setEditError(null)} />
      ) : editError.status === 412 ? (
        <div className="completion-submit-error" role="alert">
          This record changed elsewhere. Nothing was applied — your input is kept. Refresh to load
          the current state.
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
          That correction could not be applied ({editError.status ?? 'error'}). Nothing was changed
          — try again.
        </div>
      )}
    </div>
  );

  // Each confirmed field renders READ-ONLY (value + Confirmed chip + an explicit
  // Edit button). Editing one swaps that row for an inline GuidedPrompt prefilled
  // with the current value; Cancel restores the summary with no mutation.
  const answeredRows = answered.map((ans) =>
    editingId === ans.id ? (
      <div className="answered-editing" key={ans.id}>
        <GuidedPrompt
          key={`edit-${ans.id}`}
          blocker={ans.blocker}
          index={0}
          total={1}
          submitting={editSubmitting}
          initialValue={typeof ans.rawValue === 'string' ? ans.rawValue : undefined}
          initialStaged={ans.blocker.inputType === 'structured'}
          confirmLabel={LABELS.actionSave}
          dontKnowLabel={LABELS.actionCancel}
          hideBlankHint
          onConfirm={(value) => saveEdit(ans.blocker, value)}
          onDontKnow={cancelEdit}
        />
        {editErrorBanner}
      </div>
    ) : (
      <div className="answered-row" key={ans.id}>
        <span className="answered-check" aria-hidden="true">
          <Check size={13} strokeWidth={2.6} />
        </span>
        <span className="answered-label">{ans.label}</span>
        {/* R1b — was `stored {ans.storedValue}`. `storedValue` is
            `answerValuePreview(kind, value)` over the value the CLIENT submitted:
            `ApiAnswersResponse` is `{pending, status, workflow, invalidation}` plus
            version fields and carries NO echo of what was stored. The server may
            also drop an answer it does not recognise
            (`routes.py::_answers_to_apply_shape`: "Blank and unrecognised answers
            are dropped rather than applied"), so "stored" was a claim about server
            state that nothing in the response supports. The value is still shown;
            only the unsupported verb is gone. The neighbouring "Confirmed by You"
            chip is the accurate claim — the reader confirmed it. */}
        <span className="answered-stored">you answered {ans.storedValue}</span>
        <span className="answered-trailing">
          <StatusChip kind="confirmed" />
          <button
            type="button"
            className="answered-edit"
            onClick={() => startEdit(ans.id)}
            aria-label={`Edit ${ans.label}`}
            disabled={editingId !== null}
          >
            <Pencil size={13} strokeWidth={2.2} aria-hidden="true" />
            {LABELS.actionEdit}
          </button>
        </span>
      </div>
    ),
  );

  // The honest downstream-impact of the last successful edit (P28.2): the server's
  // reason, plus a stale-artifact / reopened-steps note where deterministically
  // known. role="status" (announced, not color-only); never locally re-derived.
  const editImpactNote = editImpact && editImpact.changed && (
    <div className="edit-impact" role="status">
      <Check size={14} strokeWidth={2.4} aria-hidden="true" />
      <div>
        <div className="edit-impact-reason">{editImpact.reason}</div>
        {editImpact.artifact.state === 'stale' && (
          <p className="edit-impact-note">
            The exported record is now out of date — records are immutable, so regenerate (or reset
            the workspace) to refresh it.
          </p>
        )}
      </div>
    </div>
  );

  // Finished: 0 remaining -> ready to export (route to S6). Also covers the
  // "0 blockers on arrival" case.
  if (remaining === 0) {
    return shell(
      <>
        {liveNotes}
        <div className="completion-header">
          <h1 className="completion-title">All Fields Resolved</h1>
          <span className={`completion-counter${total === 0 ? ' completion-counter-prose' : ''}`}>
            {total === 0 ? 'No open questions.' : `${answered.length} / ${total}`}
          </span>
        </div>
        {answeredRows}
        {editImpactNote}
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
      {liveNotes}
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
      {editImpactNote}

      {blocker && (
        <div style={{ marginTop: 10 }}>
          <GuidedPrompt
            key={blocker.id}
            blocker={blocker}
            index={Math.min(answered.length + skippedItems.length, total - 1)}
            total={total}
            submitting={submitting}
            onConfirm={(value) => confirmAnswer(blocker, value)}
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

      {/* R1b — the title used to read "You've reviewed every question · N left
          honestly missing", which presented SESSION state as a durable review
          outcome. The skip decision lives only in the `skipped` useState above:
          pressing "I don't know" sends nothing (deliberately — inventing a value
          would be worse), and `LoadedCompletion` is remounted by every reload, so
          the set is gone on refresh and on navigating away. Persisting it needs a
          new backend field, which is out of scope here, so the copy states the
          scope it can actually keep. */}
      {!blocker && skippedItems.length > 0 && (
        <div className="completion-allskipped" role="note">
          <div className="completion-allskipped-title">
            You've been through every question in this visit · {skippedItems.length} you said you
            don't know
          </div>
          <p className="completion-allskipped-text">
            Nothing was invented for these. This list is only for the current visit — it is not
            saved, so a reload brings all {skippedItems.length} back as open questions. Export stays
            gated until each is confirmed: answer one when you're ready, or return to the record.
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

      {/* R1b — same scoping as the all-skipped summary above: this list is client
          state for the current visit, and the eyebrow says so rather than reading
          as a recorded property of the record. */}
      {skippedItems.length > 0 && (
        <div className="leftmissing">
          <div className="leftmissing-eyebrow eyebrow">
            Left Honestly Missing · This Visit Only, Not Saved
          </div>
          {skippedItems.map((item) => (
            <div className="leftmissing-row" key={item.id}>
              <CircleHelp size={14} strokeWidth={2} aria-hidden="true" />
              <span className="leftmissing-q">{item.question}</span>
              <button
                type="button"
                className="leftmissing-answer"
                onClick={() => answerLater(item.id)}
              >
                Answer Now
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
