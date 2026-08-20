import './screens.css';
import '../components/assistant.css';
import { useEffect, useMemo, useState, useRef, type MutableRefObject } from 'react';
import type { ReactNode } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
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
import { isUnstorableFieldValue } from '../lib/mutationErrors';
import { compose } from '../lib/assistantComposer';
import { useFetch } from '../lib/useFetch';
import { useRecordSession } from '../lib/useRecordSession';
import { useWorkspaceScopeChanged } from '../lib/workspaceScope';
import { answerValuePreview, pendingItemToBlocker } from '../lib/adapt';
import type {
  ApiAnswersResponse,
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
  // D1 — the blockers on this screen belong to the workspace scope it was opened
  // in. See `lib/workspaceScope.ts`, and the matching guard on the other three
  // record surfaces: a scope change destroys the record, so there is nothing to
  // re-read and nothing here may keep describing it.
  const scopeChanged = useWorkspaceScopeChanged();

  /*
   * THE STAGED ANSWER, HELD WHERE A REFRESH CANNOT REACH IT.
   *
   * `reload` sets `{status: 'loading'}`, which takes the branch above and unmounts
   * `LoadedCompletion` — and `GuidedPrompt`'s local `text` with it. Three banners on
   * this screen said "your input is kept" beside a `Refresh` button, and two of them
   * told the reader to press it; the claim held only until they did. THIS component
   * is not unmounted by that reload, so a ref here survives it.
   *
   * Keyed by blocker id, because the answer belongs to a question rather than to the
   * screen: after a reload the pending list may have changed, and restoring one
   * question's text into a different question would be worse than losing it.
   *
   * A ref rather than state, deliberately: this must not re-render on every
   * keystroke, and nothing reads it during render except as an initial value.
   */
  /* `unknown`, NOT `string`. It was `string`, and that made the promise above false
     for exactly one blocker: a QC verdict's answer is `{status, evidence}`, so the
     `onTextChange` channel could not carry it and a Refresh destroyed a verdict and a
     paragraph of reasoning while the banner beside the button said it did not — on the
     one question whose input is most expensive to retype. Widening the ref is the whole
     fix; `initialValue` and `discardStaged` are keyed identically and need no change. */
  const staged = useRef<Record<string, unknown>>({});

  /*
   * RESET ON A RECORD CHANGE, because a blocker id is not record-scoped.
   *
   * `blocker_id` is the blocker KIND or an asset URI, not a per-record id, and this
   * ref sits ABOVE `LoadedCompletion`'s `key={id}` — deliberately, so a Refresh
   * cannot destroy it. The consequence an independent review pointed out: if the
   * `:id` param ever changed while this component stayed mounted, one record's staged
   * text could be offered on another record's identical blocker.
   *
   * It found no reachable path today (every `ROUTES.complete(...)` call site passes
   * the current id, so no in-app gesture goes record A -> record B on this route),
   * and one "next record needing attention" link would make it live. Closing it now
   * costs one effect; discovering it later costs a scientist seeing someone else's
   * value under their own question.
   */
  useEffect(() => {
    staged.current = {};
  }, [id]);

  // Before the fetch-state branches, so no question, answered row or heading from
  // the discarded workspace reaches the DOM. `replace`, so Back does not return
  // the reader to a record that no longer exists.
  if (scopeChanged) return <Navigate to={ROUTES.experiments} replace />;

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
      staged={staged}
    />
  );
}

/**
 * Was the answer to `blockerId` APPLIED? Read off the server's own report — never
 * off "the promise resolved".
 *
 * A 200 is not a report that anything was written. `routes.py::_answers_to_apply_shape`
 * drops a blank or unrecognised answer ("Unknown keys are ignored — never invented
 * into the draft"), and `complete.py::apply_answers` leaves a malformed sha256, a
 * wrong-typed series/descriptor or an off-enum qc unapplied and puts the blocker
 * straight back into `remaining_pending`. Both come back 200 with `rev` unmoved.
 *
 * TWO SIGNALS, and both must agree:
 *  1. `pending` — the list the server RECOMPUTED from the post-mutation draft
 *     (`serialize.pending_to_list`). This is the only PER-FIELD statement the
 *     response makes: an applied answer resolves its blocker, an unapplied one is
 *     re-added verbatim. It is the signal to trust for this path.
 *  2. `invalidation.changed` — `exp.save_versioned()`'s own return, i.e. whether the
 *     authoritative draft actually moved. It is a WHOLE-DRAFT fact, so on its own it
 *     cannot say WHICH field landed, and `invalidation.changed_fields` is no better:
 *     it is an echo of the request keys gated on `changed` (`routes.py`:
 *     `changed_fields = submitted_fields if changed else []`).
 *
 * In today's backend the two cannot disagree — resolving a blocker rewrites
 * `pending`, which moves the draft. `&&` is deliberately the direction anyway: if
 * they ever disagree we do not KNOW the value landed, and this screen must not put a
 * "Confirmed by You" chip over a value it cannot support. Fail closed.
 */
function answerWasApplied(resp: ApiAnswersResponse, blockerId: string): boolean {
  const stillOpen = resp.pending.some((p) => p.id === blockerId);
  return resp.invalidation.changed === true && !stillOpen;
}

/**
 * Was the CORRECTION applied? One signal only, and that is a property of the
 * backend rather than a shortcut: `complete.py::apply_corrections` "NEVER touches
 * pending", so the recomputed `pending` list is byte-identical whether the
 * correction landed or was refused and carries no information here. The whole-draft
 * signal is also SUFFICIENT on this path, because `apply_corrections` writes nothing
 * outside the submitted keys — so a draft that moved can only be this correction.
 *
 * `changed: false` covers two real outcomes that the response cannot tell apart: a
 * value `apply_corrections` refused (a malformed sha256 leaves the current value
 * untouched) and a submit identical to what is already recorded. That is why the
 * copy below reports only that nothing was applied and never names a cause — and
 * why it never renders `invalidation.reason`, which asserts the second cause ("the
 * submitted value was identical") for BOTH. That wording is recorded as known-wrong
 * and deliberately unchanged in `apps/api/tests/test_export_recovery.py:1361`.
 */
function editWasApplied(resp: ApiAnswersResponse): boolean {
  return resp.invalidation.changed === true;
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
  staged,
}: {
  id: string;
  detail: ApiExperimentDetail;
  initialPending: ApiPendingItem[];
  reload: () => void;
  /** Staged answers keyed by blocker id, held by the parent so a `reload` — which
   *  unmounts this component — cannot destroy what the reader typed. */
  staged: MutableRefObject<Record<string, unknown>>;
}) {
  const navigate = useNavigate();
  const [pending, setPending] = useState<ApiPendingItem[]>(initialPending);
  const [answered, setAnswered] = useState<Answered[]>([]);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<ApiError | null>(null);
  // The blocker id of the last answer the SERVER did not report as applied (200,
  // nothing written). Not an ApiError — no exception was thrown — so it needs its
  // own state, and it is keyed by blocker id so the note stays attached to the
  // question it belongs to and cannot follow the reader to the next one.
  const [answerNotApplied, setAnswerNotApplied] = useState<string | null>(null);
  // Same, for a correction the server did not report as applied.
  const [editNotApplied, setEditNotApplied] = useState<string | null>(null);
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

  /* THE TOKEN A WRITE NEEDS DEPENDS ON WHO OWNS THE QUESTION.
   *
   * A record-level answer takes the RECORD's version, which this screen already holds.
   * A run-owned one goes to the run's route and takes THE RUN's version, which this
   * screen does not — so it is read immediately before the write. That is one extra
   * round trip on the questions that need it, and the alternative (caching a run
   * version alongside the record's) is a second staleness to keep in step for no gain:
   * `GET /pending` does not report run versions, so there is nothing to keep it fresh
   * from.
   *
   * Sending the record's token to a run route is not a silent bug — it is a 412 — but
   * it is a 412 the reader would be told to resolve by refreshing something that was
   * never stale, which is why the tokens are resolved here rather than at the caller.
   */
  const tokenFor = async (blocker: PendingBlocker): Promise<string | undefined> => {
    if (!blocker.runId) return currentVersion;
    const { run } = await api.getRun(id, blocker.runId);
    return run.version;
  };

  const confirmAnswer = (blocker: PendingBlocker, value: unknown) => {
    setSubmitting(true);
    setSubmitError(null);
    setAnswerNotApplied(null);
    tokenFor(blocker)
      .then((token) => api.submitAnswer(id, { [blocker.id]: value }, token, blocker.runId))
      .then((resp) => {
        // Server-reported state first, unconditionally: the recomputed question list
        // and the fresh If-Match token are facts either way.
        setPending(resp.pending);
        setCurrentVersion(resp.version); // adopt the fresh token for the next submit
        if (answerWasApplied(resp, blocker.id)) {
          // APPLIED, so the staged copy has done its job. Kept only until the record
          // holds the value: leaving it would re-offer a value the record already has
          // if this blocker ever returned to `pending` through a downstream
          // invalidation, which reads as an unsaved edit that is not one.
          discardStaged(blocker.id);
        }
        if (!answerWasApplied(resp, blocker.id)) {
          // The server did not report this value as applied, so this screen may not
          // show it as answered. No `answered` row (so no "Confirmed by You" chip
          // over a value the record does not hold), no counter movement — `total` is
          // `answered.length + pending.length`, so not pushing here is also what
          // keeps the count honest — and the question stays exactly where the server
          // left it: open. The typed input survives, because `pending` still holds
          // this blocker so `GuidedPrompt`'s `key` is unchanged and it is not
          // remounted.
          setAnswerNotApplied(blocker.id);
          return;
        }
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
    setEditNotApplied(null);
  };
  /*
   * DISCARD A STAGED ANSWER, because a ref that outlives the INTENT is its own defect.
   *
   * The staged store exists so a Refresh cannot destroy what the reader typed. It must
   * NOT survive an act by which the reader abandoned that text — and in the first
   * version of this fix it did, which an independent review caught in two places:
   *
   *   * Cancel on an Edit restored the abandoned correction the next time Edit was
   *     opened, in place of the confirmed value, and Save would have written it with
   *     `confirmed_by_user` semantics;
   *   * "I don't know — leave honestly missing" left the typed answer staged, so
   *     "Answer Now" came back pre-filled with a value the scientist had explicitly
   *     declined to assert, one click from being confirmed.
   *
   * Both are the same root cause and this is the one place that fixes it. Keyed
   * exactly as the read is keyed, so a rename cannot silently stop discarding.
   */
  const discardStaged = (key: string) => {
    delete staged.current[key];
  };

  const cancelEdit = () => {
    // The reader abandoned this correction. It must not come back.
    if (editingId !== null) discardStaged(`edit:${editingId}`);
    setEditingId(null);
    setEditError(null);
    setEditNotApplied(null);
  };

  // Save a correction: POST /edit with the held If-Match token (P27.5), adopt the
  // fresh version, update the summary row's value, and surface the server-reported
  // downstream impact. A 412 keeps the editor mounted (input preserved) and shows
  // the existing stale-write recovery banner. A submit the server does not report as
  // applied (200 with `invalidation.changed:false` — a refused value, or a submit
  // identical to what is already recorded) leaves the row's value ALONE and keeps the
  // editor open, because the recorded value did not become the typed one.
  const saveEdit = (blocker: PendingBlocker, value: unknown) => {
    setEditSubmitting(true);
    setEditError(null);
    setEditNotApplied(null);
    tokenFor(blocker)
      .then((token) => api.editField(id, { [blocker.id]: value }, token, blocker.runId))
      .then((resp) => {
        setCurrentVersion(resp.version);
        setPending(resp.pending);
        if (!editWasApplied(resp)) {
          // Nothing was written, so nothing here may move: the summary row keeps the
          // value the server last confirmed, the editor stays mounted with what was
          // typed (as on a 412), and no `editImpact` is rendered — its
          // `invalidation.reason` would name a cause the response cannot know.
          setEditNotApplied(blocker.id);
          return;
        }
        setAnswered((prev) =>
          prev.map((a) =>
            a.id === blocker.id
              ? { ...a, storedValue: answerValuePreview(blocker.kind, value), rawValue: value }
              : a,
          ),
        );
        setEditImpact(resp.invalidation);
        // The correction is stored, so the staged copy is spent. Same reason as the
        // answer path above.
        discardStaged(`edit:${blocker.id}`);
        setEditingId(null);
      })
      .catch((err: ApiError) => setEditError(err))
      .finally(() => setEditSubmitting(false));
  };

  const leaveMissing = (blockerId: string) => {
    // Declining to answer is an ABANDONMENT of whatever was typed. Without this the
    // value returns pre-filled under "Answer Now", one click from being confirmed.
    discardStaged(blockerId);
    setSkipped((prev) => new Set(prev).add(blockerId));
    // The reader has moved on from this question; the not-applied note described the
    // submit they just abandoned, so it must not be waiting for them if they come
    // back to it via "Answer Now".
    setAnswerNotApplied((prev) => (prev === blockerId ? null : prev));
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
      /*
       * F4 — WHAT WAS FALSE HERE, and it was the stronger version of the defect the
       * Review screen's footer was corrected for. This read
       * `phase="All blockers resolved · ready to export"`, `phaseDot="ready"`,
       * `note="Every field is confirmed or resolved — export is now unlocked."` on
       * the sole basis of `remaining === pending.length === 0`. "Export is now
       * unlocked" is measurably false: `POST /api/experiments/{id}/export` runs
       * `export_draft` and returns `ok: false` having written NOTHING when the
       * official report fails (`apps/api/isaac_api/routes.py`), independently of the
       * pending count — the canonical seed `…SEED0000000004` is exactly that record
       * (full answers minus the descriptor's required `uncertainty`, so pending 0
       * and the dry-run failing). And the reader reaches Review THROUGH this screen,
       * so the corrected footer there was preceded by a stronger uncorrected claim
       * here.
       *
       * WEAKENED TO WHAT `pending.length === 0` ESTABLISHES rather than fetched:
       * `detail.workflow` is on this screen, but it is the value from the parent's
       * last load, and this branch is reached by answering the last question in
       * THIS component's local state (`pending` comes from the answer responses),
       * so that workflow object can be a revision behind the sentence it would be
       * justifying. The honest claim from local state alone is that no confirmation
       * questions remain, plus a statement of what decides export — which is what
       * the body copy of the panel below has always said.
       *
       * The dot is `progress`, not `ready`: `.dot-ready` is `var(--pass-solid)`,
       * reserved for the validation verdict (see `StatusBar`'s `phaseDot` type).
       *
       * The note stays at or under the length of the false one it replaces (61 vs 62
       * characters, measured): the sibling branch below records that a longer note
       * wrapped at the 640px/200%-zoom layout viewport and pushed the status bar 1px
       * past the screen card.
       */
      <StatusBar
        phase="All blockers resolved"
        phaseDot="progress"
        note="The official ISAAC schema check runs next and decides export."
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
        /* R1b. The old note said export unlocks "once every field is confirmed OR
           honestly left missing" — false: the gate is `pending_count == 0`, and
           saying "I don't know" sends nothing, so it leaves the field pending and
           export stays shut. The correction must also stay SHORT: a longer first
           draft wrapped at the 640px/200%-zoom layout viewport and pushed the
           status bar 1px past the screen card (zoom-200 layout baseline). This is
           shorter than the false sentence it replaces. */
        note="Export unlocks once every field is confirmed — saying you don't know leaves it open."
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
            This record changed elsewhere. What you typed is kept, including through Refresh —
            review the current record before submitting.
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
          This record changed elsewhere. Nothing was applied — what you typed is kept, including
          through Refresh. Refresh to load the current state.
          <button
            type="button"
            className="btn btn-secondary"
            style={{ marginLeft: 10 }}
            onClick={reload}
          >
            Refresh
          </button>
        </div>
      ) : isUnstorableFieldValue(editError) ? (
        /*
         * A VALUE THE RECORD CANNOT STORE, and the reason this branch exists rather
         * than falling through to the generic one below.
         *
         * The server refuses `POST /edit` with `invalid_field_value` when a recognised
         * field carries a value it cannot write — a malformed sha256, a `series` that
         * is not a list of objects. Before that refusal existed, this path answered
         * 200 and the SCREEN had to interpret it; the copy it used then said the one
         * thing that actually matters to a scientist, which the generic sentence below
         * does not: THE VALUE YOU HAD IS STILL THERE. That sentence is kept here.
         *
         * Every claim is one the response supports. `Nothing was written` is what the
         * 422 asserts; `still holds the value it held before` follows from it, because
         * the route refuses before it mutates. No cause is named beyond the shape,
         * because the response names none — it does not say WHY the value is wrong, and
         * inventing a reason would be the defect this whole path exists to avoid.
         */
        /*
         * `data-testid`, and it is not decoration. `e2e/mutation/evidence.spec.ts` used
         * this notice only as a WAYPOINT — proof the request finished — and matched it by
         * sentence, so it broke twice for reasons that had nothing to do with the
         * property that spec exists to test (the evidence trail). A stable hook ends the
         * recurrence. `edit.spec.ts` still matches the prose, deliberately: there the
         * sentence IS the thing under test.
         */
        <div
          className="completion-submit-error"
          role="alert"
          data-testid="edit-unstorable-notice"
        >
          That correction was not applied — this field still holds the value it held before, and
          nothing was written. Check the value and try again.
        </div>
      ) : (
        <div className="completion-submit-error" role="alert">
          That correction could not be applied ({editError.status ?? 'error'}). Nothing was changed
          — try again.
        </div>
      )}
    </div>
  );

  // A correction the SERVER did not report as applied. It answered 200, so there is
  // no `ApiError` and nothing threw — the old code took that as proof and rewrote the
  // row to the typed value, putting a "Confirmed by You" chip over something the
  // record had refused. Every claim here is one the response supports: `changed:false`
  // means the authoritative draft did not move, so the field still holds what it held,
  // and `apply_corrections` never writes a substitute. NO CAUSE IS NAMED: a refused
  // value and a submit identical to the recorded one are indistinguishable in this
  // response (see `editWasApplied`), so guessing between them would be the same class
  // of defect this note exists to fix.
  const editNotAppliedNote = (rowId: string) =>
    editNotApplied === rowId && (
      <div style={{ marginTop: 10 }}>
        <div className="completion-submit-error" role="alert">
          Nothing was applied — this field still holds its previously confirmed value, and nothing
          was invented in its place. Try again, or Cancel to keep it.
        </div>
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
          /* An IN-PROGRESS edit takes precedence over the confirmed value, so a
             Refresh mid-edit restores what the reader had rewritten rather than
             snapping back to the stored value. Namespaced `edit:` so an edit and a
             fresh answer to the same blocker cannot overwrite one another. */
          /* `rawValue` is passed through for a STRUCTURED answer too now. It used to be
             gated on `typeof === 'string'`, so a `qc` row's edit form opened with blank
             radios and a blank note — contradicting this screen's own claim that an
             edit is "prefilled with the current value". A series/descriptor value is
             still not prefilled into a text box: it is confirmed via `initialStaged`. */
          initialValue={
            staged.current[`edit:${ans.id}`] ??
            (ans.blocker.inputType === 'verdict' ? ans.rawValue : undefined) ??
            (typeof ans.rawValue === 'string' ? ans.rawValue : undefined)
          }
          onTextChange={(value) => {
            staged.current[`edit:${ans.id}`] = value;
          }}
          onStagedChange={(value) => {
            staged.current[`edit:${ans.id}`] = value;
          }}
          initialStaged={ans.blocker.inputType === 'structured'}
          confirmLabel={LABELS.actionSave}
          dontKnowLabel={LABELS.actionCancel}
          hideBlankHint
          onConfirm={(value) => saveEdit(ans.blocker, value)}
          onDontKnow={cancelEdit}
        />
        {editErrorBanner}
        {editNotAppliedNote(ans.id)}
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

  // An answer the SERVER did not report as applied. The response was 200 and nothing
  // threw, which is exactly why this state needs its own note: the old code read a
  // resolved promise as proof and added an answered row, so the screen claimed a value
  // under a "Confirmed by You" chip that the truth core had dropped, while the same
  // question re-rendered below as still open.
  //
  // Rendered on `answerNotApplied` alone rather than on it MATCHING the current
  // question, and on BOTH loaded branches. Keying it to the question read better and
  // silently showed nothing in the cases the guard exists for: in the fail-closed
  // disagreement (the blocker resolved but the draft did not move) the refused question
  // is no longer current — and if it was the last one, the screen switches to the
  // all-resolved branch — so an unapplied write would have been reported by neither a
  // row nor a note. `leaveMissing` clears it, so moving on does not carry it along.
  //
  // Both sentences hold in every not-applied case: a blocker the server re-added is one
  // whose value `apply_answers` did not write, a draft that did not move was not written
  // to at all, and neither path substitutes a value. No cause is named — the response
  // does not carry one.
  const answerNotAppliedNote = answerNotApplied !== null && (
    <div className="completion-submit-error" role="alert" style={{ marginTop: 10 }}>
      That answer was not applied. The record was not updated with the value you entered, and
      nothing was invented in its place — try again, or say you don't know to leave it missing.
    </div>
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

  // Finished: 0 remaining -> the official schema check is what remains (route to
  // S6). Also covers the "0 blockers on arrival" case. Deliberately no longer
  // described as "-> ready to export": `pending_count == 0` is not export
  // readiness (see the F4 note on `statusBar` above).
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
        {answerNotAppliedNote}
        {/* F4, second site on this screen. The title read "This record is ready to
            export." — the same claim the footer below it was corrected for, from the
            same basis (`remaining === 0`), and it renders SIMULTANEOUSLY with that
            footer, so leaving it would have made the screen contradict itself an inch
            apart. The body sentence already stated the truthful sequence and is
            unchanged; the title now claims only what the empty pending list
            establishes. The disc is `.dot-progress` for the reason in
            `styles/base.css`: `.dot-ready` is the reserved validation-verdict hue and
            this is workflow progress. */}
        <div className="completion-done" role="status">
          <span className="dot dot-progress" aria-hidden="true" />
          <div>
            <div className="completion-done-title">Nothing is left for you to confirm.</div>
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
            /* Restored across a Refresh, and kept current on every keystroke. See
               the `staged` ref in the parent for why it lives there. */
            initialValue={staged.current[blocker.id]}
            onTextChange={(value) => {
              staged.current[blocker.id] = value;
            }}
            onStagedChange={(value) => {
              staged.current[blocker.id] = value;
            }}
            onConfirm={(value) => confirmAnswer(blocker, value)}
            onDontKnow={() => leaveMissing(blocker.id)}
          />
        </div>
      )}

      {answerNotAppliedNote}

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
          {/* KEPT NO LONGER THAN THE COPY IT REPLACED, and that is a hard constraint,
              not a style preference. The first scoping draft ran several lines longer;
              at 200% zoom (a 640px layout viewport) it pushed the page tall enough that
              the status-bar phase text clipped vertically by ONE pixel. Caught by the
              zoom-200 layout baseline — no unit test sees it, and it reproduces on both
              platforms. A second, shorter draft still overflowed by 1px; this is the
              third.
              The "not saved" claim is not lost, it MOVED: the eyebrow below states it
              outright, and "a reload brings all N back as open questions" says the same
              thing concretely. If this block grows again, run the zoom-200 layout spec
              before assuming it fits. */}
          <div className="completion-allskipped-title">
            Every question reviewed this visit · {skippedItems.length} you don't know
          </div>
          <p className="completion-allskipped-text">
            Nothing was invented. A reload brings all {skippedItems.length} back as open questions,
            and export stays gated until each is confirmed.
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
            //
            // AND THE INPUT NOW SURVIVES THAT REFRESH TOO. The parenthetical above was
            // true of the 412 itself and false of the remedy offered beside it: the
            // reload DOES unmount this component. The parent holds the staged text in
            // a ref it hands back through `initialValue`, so the sentence below is now
            // accurate rather than accurate-until-you-press-the-button.
            <div className="completion-submit-error" role="alert">
              This record changed elsewhere. Nothing was applied — what you typed is kept, including
              through Refresh. Refresh to load the current state.
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
          {/* Both halves are load-bearing and `session-only-decisions.test.tsx`
              requires both: "This Visit" is the DURATION, "Not Saved" is the
              PERSISTENCE. A shorter draft kept only the second, and the guard caught
              it — dropping the duration leaves the reader unable to tell whether the
              list survives navigation. The zoom-200 headroom that pays for these
              words comes from the workflow note above, not from here. */}
          <div className="leftmissing-eyebrow eyebrow">
            Left Honestly Missing · This Visit, Not Saved
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
