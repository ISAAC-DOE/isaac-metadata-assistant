import './screens.css';
import '../components/evidence.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { WorkflowSpine } from '../components/WorkflowSpine';
import { RECORD_WORKSPACES, RecordWorkspaceNav } from '../components/RecordWorkspaceNav';
import { StatusBar } from '../components/StatusBar';
import { FieldGroup } from '../components/FieldGroup';
import { RecordInfoPanel, RecordLinksPanel } from '../components/RecordInfoPanel';
import { RenameExperimentPanel } from '../components/RenameExperimentPanel';
import { RecordDescriptionPanel } from '../components/RecordDescriptionPanel';
import { RunsSection } from '../components/RunsSection';
import { TranscriptCapturePanel } from '../components/TranscriptCapturePanel';
import { UnmappedNotesPanel } from '../components/UnmappedNotesPanel';
import { IngestionProposalsPanel } from '../components/IngestionProposalsPanel';
import { AssetReferencesPanel } from '../components/AssetReferencesPanel';
import { ValidateReview } from '../components/ValidateReview';
import { disposeExperiment, flushExperiment } from '../lib/runAutosaveStore';
import { AssistantPanel, type AgentPrompt } from '../components/AssistantPanel';
import { AssistantDrawer } from '../components/AssistantDrawer';
import { LiveSyncNote } from '../components/LiveSyncNote';
import { RecordActivityNote } from '../components/RecordActivityNote';
import { needsCanonicalRefetch, type RecordChangeSummary } from '../lib/recordChanges';
import { WorkflowProgressBanner } from '../components/WorkflowProgressBanner';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { CircleAlert, ExternalLink } from '../components/icons';
import { ExperimentGraphPanel } from './graph/ExperimentGraphPanel';
import { LABELS } from '../lib/labels';
import {
  RECORD_COMPARE_PARAM,
  RECORD_RUN_PARAM,
  RECORD_VIEW_PARAM,
  ROUTES,
  isRecordView,
  type RecordViewId,
} from '../lib/routes';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { useRecordSession } from '../lib/useRecordSession';
import { useWorkspaceScope, useWorkspaceScopeChanged } from '../lib/workspaceScope';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import type { AgentContext } from '../lib/assistantAgent';
import {
  draftGroupsToFieldGroups,
  pendingSummary,
  stripLifecycleSuffix,
  toAdvisoryResult,
  toAuditResult,
  toValidationResult,
} from '../lib/adapt';
import { compose } from '../lib/assistantComposer';
import type { ApiEvidenceEntry, ApiPendingItem, ApiWorkflow, RecordBundle } from '../lib/types';

/**
 * How many pending questions the record screen's banner lists before it says how
 * many more there are.
 *
 * TEN, and the number is a judgement rather than a measurement: it is enough to see
 * what KIND of thing is being asked without the banner becoming the page. What IS
 * measured is the cost of not having a bound — at 1000 runs this list was 3,002 items
 * and ~15,000 of the screen's 16,134 DOM nodes, while every run card together was 50.
 * See `docs/run-scale-measurements.md`.
 *
 * Exported so a test can assert the boundary rather than hard-coding a second copy of
 * it, and so the overflow copy and the slice can never disagree about the same number.
 */
export const NEEDSYOU_VISIBLE = 10;

/**
 * HOW MANY OPEN QUESTIONS A **LIVE REFRESH** OF THIS SCREEN ASKS FOR.
 *
 * THE INITIAL LOAD IS UNBOUNDED AND DELIBERATELY STAYS THAT WAY — first paint is
 * unchanged, and the assistant's grounding chip is exact over a freshly-loaded record.
 * This bound applies only to a refetch a POLL caused, which is where the cost is: an
 * idle record screen runs two pollers, and before this every signal either of them
 * produced re-downloaded the record's ENTIRE question list. Measured on a 1,000-run
 * record, that list is 3,000 entries / 1.77 MB
 * (`useRecordSession.AGENT_CONTEXT_PENDING_WINDOW` carries the column), and the screen
 * renders ten of them.
 *
 * IT IS `NEEDSYOU_VISIBLE`, NOT A SECOND NUMBER, and the equality is deliberate rather
 * than incidental: this window has to be at least what the banner renders, or the
 * banner would show fewer rows after a background refresh than it showed on load —
 * a list silently shrinking with no act by the reader. Pinned by
 * `__tests__/live-refresh-request-graph.test.tsx`, so the two cannot drift apart.
 *
 * NOTHING IS HIDDEN BY IT. Every COUNT on this screen — the banner title, the overflow
 * sentence, the status-bar phase, the assistant chip — reads `bundle.pendingTotal`,
 * which is the server's `pending_page.total` and speaks for the whole record. The
 * window bounds what is FETCHED, never what is CLAIMED.
 */
export const LIVE_PENDING_WINDOW = NEEDSYOU_VISIBLE;

/**
 * The draft-phase half of the status-bar readout, taken from the SERVER'S OWN
 * workflow derivation instead of from `pending.length === 0`. Called only where
 * `pending.length === 0` (see `LoadedWorkbench`), which is the ONLY thing the
 * caller establishes — see the completion note below.
 *
 * I2 — WHAT WAS FALSE. This read `pending.length > 0 ? 'Draft assembled · N fields
 * to confirm' : 'Draft complete · ready to export'`, and `pending == 0` does not
 * imply export-ready. `apps/api/isaac_api/workspace.py::status` separates
 * `ready_to_export` from `in_review` on exactly that residual — pending 0 with a
 * FAILING official-schema dry-run is `in_review` — and `workflow.derive_workflow`
 * agrees: measured, `derive_workflow(pending_count=0, draft_ok=True, ready=False,
 * exported=False, rev=1)` returns `current_step == 'review_export_readiness'` with
 * the `export` step `blocked`. So on such a record this footer claimed "ready to
 * export" while `WorkflowProgressBanner` on the SAME screen, from the SAME
 * `detail.workflow`, said "Not ready to export yet".
 *
 * F3 — WHAT WAS STILL FALSE AFTER THAT FIX, and what this comment used to claim.
 * It said "every other step maps to the action the banner already names … so the
 * two strings cannot contradict". That was untrue of the retained `Draft complete`
 * PREFIX on the `review_evidence` step. `derive_workflow` leaves `review_evidence`
 * unsatisfied exactly when `pending_count == 0 and draft_ok` is false
 * (`apps/api/isaac_api/workflow.py`), and `draft_ok` is
 * `validate_draft(self.draft).ok` (`workspace.py`) — the no-guessing DRAFT
 * VALIDATOR is failing. `pending_count` is computed independently of it, so an
 * evidence-less finalized field is a draft-validator error that never appears in
 * `pending`. In that state the banner on this screen says "Evidence review needed /
 * This record's evidence checks aren't passing yet." while this line asserted the
 * draft was complete. The state is real, not hypothetical:
 * `apps/api/tests/test_corpus_mutation.py` asserts
 * `derive_workflow(pending_count=0, draft_ok=False, …)['current_step'] ==
 * 'review_evidence'`.
 *
 * So `review_evidence` now carries the banner's OWN words and no completion claim,
 * and the two remaining `Draft complete` prefixes are made only where the server
 * reports `draft_ok` true (`export` and `review_export_readiness` are both
 * downstream of the `review_evidence` step being satisfied). What THIS function
 * guarantees is therefore narrow and checkable: the positive readiness claim is
 * made for exactly one step id, no step whose banner denies the evidence checks
 * carries a completion claim, and an unrecognised or absent `current_step` claims
 * neither readiness nor completion — it states only the thing the caller
 * established, that no confirmation questions are open.
 *
 * Deliberately not worded "not ready to export yet": that phrase contains "ready
 * to export" as a substring, and a footer whose truthfulness is pinned by tests
 * should not be one missed negation away from reading as its own opposite.
 */
export function draftPhaseFromWorkflow(workflow: ApiWorkflow | null): string {
  switch (workflow?.current_step) {
    case 'export':
      return 'Draft complete · ready to export';
    case 'review_export_readiness':
      return 'Draft complete · review export readiness';
    case 'review_evidence':
      // The banner's own heading, verbatim. No "Draft complete": `draft_ok` is
      // false in this state, which is exactly what makes the step current.
      return 'Evidence review needed';
    default:
      return 'No open questions';
  }
}

/**
 * The phase DOT for the same readout, from the same derivation as the text above.
 *
 * F2 — WHAT WAS FALSE, one line away from the corrected sentence. The dot read
 * `pending.length > 0 ? 'attention' : detail.exported ? 'idle' : 'ready'`, and
 * `.dot-ready` is painted `var(--pass-solid)` (`styles/base.css`), a token declared
 * under "signal 1 — validation verdict (RESERVED, hard gate)"
 * (`styles/tokens.css`). So a record with `pending_count == 0` and a FAILING
 * official dry-run rendered the corrected text "Draft complete · review export
 * readiness" beside a PASS-GREEN dot, while the banner above it said "Not ready to
 * export yet": the sentence was fixed and the colour went on making the claim.
 *
 * The tones now mirror `WorkflowProgressBanner`'s two tones for the same step ids —
 * amber `attention` while something still blocks, and the banner's calm action-blue
 * "this is the next step" treatment as `.dot-progress`, which borrows no verdict
 * token. An unrecognised or absent step is `idle` (neutral grey): no claim.
 */
export function draftPhaseDotFromWorkflow(
  workflow: ApiWorkflow | null,
): 'attention' | 'progress' | 'idle' {
  switch (workflow?.current_step) {
    case 'export':
      return 'progress';
    case 'review_export_readiness':
    case 'review_evidence':
      return 'attention';
    default:
      return 'idle';
  }
}

/**
 * S3 · Review Record — the core workbench, live from the record bundle
 * (detail / draft / pending / validate / audit / warnings / evidence / graph —
 * eight endpoints, fetched together, rendered apart). Grouped, calm draft;
 * evidence one tap away in the right panel (above the subordinate assistant,
 * hard-divided); the blocking gate on the left; the trust readout along the
 * bottom with each signal in its own labeled segment, never merged.
 */
export function RecordWorkbench() {
  const { id = '' } = useParams();

  /*
   * IS THE NEXT RUN OF THE FETCHER A **LIVE REFRESH**? — a single-shot flag, consumed
   * by the fetcher itself.
   *
   * `useFetch` has ONE fetcher for three callers: the deps effect (first paint), the
   * explicit `reload` (the Refresh button, and the down-state retry) and `reloadSilent`
   * (a poll signal, and the post-write refresh). Only the last of those may bound the
   * question list — first paint must not change, and a reader who PRESSED Refresh is
   * asking for the authoritative read. So the mode travels in a ref that
   * `reloadFromSignal` sets immediately before calling `reloadSilent`, which invokes
   * the fetcher SYNCHRONOUSLY, and the fetcher clears the flag as its first act.
   *
   * SINGLE-SHOT, NOT STICKY, and the difference is what stops the bound leaking. If the
   * flag persisted, the next `reload` — a deliberate human act — would silently be
   * served a windowed list too. Clearing it on read means the bounded mode lasts
   * exactly one fetch and every other caller keeps the behaviour it had.
   */
  const liveRefreshRef = useRef(false);
  const bundle = useFetch(() => {
    const live = liveRefreshRef.current;
    liveRefreshRef.current = false;
    return api.getRecordBundle(id, live ? { pendingLimit: LIVE_PENDING_WINDOW } : {});
  }, [id]);

  /*
   * THE RUN AUTOSAVE STORE IS DISPOSED HERE — at the RECORD screen's boundary, not at a
   * card's, and that difference is the whole of the Phase-2 change.
   *
   * Save state deliberately outlives a `RunCard`, because a card can unmount and an
   * edit's outcome must survive that. NOTE THE CORRECTION: this used to say a card
   * unmounts "one click away … the Graph tab takes it down". IT NO LONGER DOES — the
   * fields tabpanel is now kept mounted and hidden, precisely so an unsaved textarea is
   * not destroyed by a tab switch, and three other headers in this change were
   * corrected for exactly this while this one was missed. A card still unmounts on
   * paging, searching, filtering and leaving the record, so the reason this store
   * exists is unchanged; only the example was falsified. It must not outlive the record
   * screen either, or the map keeps an entry for every run a session ever opened.
   *
   * `disposeExperiment` IS CONSERVATIVE, AND THE COST OF THAT IS REAL RATHER THAN
   * THEORETICAL. It refuses to drop an entry that is mid-flight or still holding edits,
   * so leaving the screen never discards a write that has not landed — which is the
   * right trade for a scientist. The consequence, MEASURED (12 records abandoned each
   * holding one refused edit retain 12 entries indefinitely; nothing revisits them):
   * the map grows for exactly the runs that still have something unsent. An earlier
   * version of this comment implied disposal bounded growth in general. It bounds it
   * for entries with nothing to remember, which is every entry whose last write
   * succeeded. Entries that hold a refusal are kept ON PURPOSE, because `Retry Save`
   * needs them; a sweep would have to decide when to discard a scientist's unsent edit,
   * and that is not a decision to make silently.
   */
  useEffect(() => () => disposeExperiment(id), [id]);
  // D1 — this record belongs to the workspace scope the surface was opened in. If
  // that scope changes (the walkthrough's temporary workspace was discarded, and
  // with it these records) nothing loaded here describes anything any more. See
  // `lib/workspaceScope.ts` for why the answer is to leave rather than to re-read.
  const scopeChanged = useWorkspaceScopeChanged();

  // P29.4 — the ONE shared record-session owner for this record: the single
  // poller + the authoritative version + the live P29.3 AgentContext the
  // assistant reads. On a change signal it invalidates any stale staged proposal
  // and silently refetches this read-only bundle (never blanks to loading). The
  // fetched bundle stays authoritative; the poller only tells us WHEN to refresh.
  const detail = bundle.status === 'data' ? bundle.data.detail : undefined;
  /*
   * SELECTIVE REFRESH. The rule — and the reason a proposal-only page refetches
   * nothing, and the honest note that in this build a proposal act usually moves the
   * record's entry too — lives ONCE, in `recordChanges.needsCanonicalRefetch`. It is
   * deliberately not restated here: it was written out three times, drifted from
   * nothing, and was pinned only against a fourth copy inside a test.
   *
   * What is local to this screen is the ACTION: `bundle.reloadSilent()`, a background refetch of this
   * screen's own bundle that never blanks it and is not a page reload.
   */
  /*
   * ── THE COALESCING GATE: AT MOST **ONE** BUNDLE REFETCH IN FLIGHT. ───────────────
   *
   * WHAT IT FIXES, AND IT WAS TWO FULL BUNDLES PER EVENT, NOT ONE. Two pollers watch
   * this screen and BOTH used to refetch. `useRecordSync` conditionally GETs the record
   * and, on a 200, calls `onChange` -> `reloadSilent()`. `useChangeFeed` reports which
   * entities moved and, when `needsCanonicalRefetch` says this screen's canonical read
   * is stale, called `reloadSilent()` AGAIN — for the same save, at the same revision.
   * Whichever poller lost the race did the second one. Measured, one run edit issued
   * 20 requests, of which 18 were two identical nine-request bundles and two of those
   * eighteen were the record's ENTIRE open-question list, downloaded twice. See
   * `docs/evidence/live-refresh-request-graph-2026-09-02.md`.
   *
   * ── THE KEY IS IN-FLIGHTNESS, AND IT IS DELIBERATELY **NOT** A REVISION. ─────────
   *
   * The first version of this gate compared revisions — "have I already asked for a
   * refetch at or past rev R?" — and it was WRONG, in a way an existing fixture caught
   * on the first run. The optimistic-concurrency token has the form
   * `"<generation>.<rev>"`, so **a rev is not monotonic across generations**: the
   * record fixtures move `1.0` -> `2.0`, which is a real change and derives the SAME
   * rev (0) on both sides. A rev-keyed gate silently refused every refetch across a
   * generation boundary — a live update dropped for good, which is the exact class of
   * defect this whole slice exists to remove. The failure is recorded here rather than
   * quietly corrected, because "compare the revs" is the obvious thing to reach for.
   *
   * In-flightness needs no arithmetic and no ordering assumption. A refetch reads the
   * record as it is WHEN IT RUNS, so any signal arriving while one is outstanding is
   * about a change that refetch will already carry; a signal arriving after it settles
   * is either genuinely newer, or is filtered by `summariseChanges` against the freshly
   * adopted revision. Both are handled, and neither needs this gate to know a number.
   *
   * WHAT IT GUARANTEES, in the words of the properties the tests assert: N feed entries
   * in one page cost ONE refetch (they share a page and produce one summary); a signal
   * arriving while a refetch is outstanding costs at most ONE follow-up; and the two
   * pollers between them cost ONE bundle per record movement, whichever wins the race.
   *
   * IT RE-OPENS ON **EVERY** SETTLEMENT, WHICH IS THE HALF THAT IS EASY TO LEAVE OUT
   * AND EXPENSIVE TO OMIT. A dropped signal is only safe if the refetch it was dropped
   * in favour of actually completed. `reloadSilent` keeps the old data and raises
   * `refreshFailed` when it does not — so the gate watches the SETTLED value's identity
   * (a new bundle object, or an error) and `refreshFailed` beside it. Without that, one
   * failed refetch would close this gate permanently: the poller would keep answering
   * 200, every signal would keep being dropped as redundant, and the screen would keep
   * showing pre-change data with the only recourse being the human pressing Refresh.
   *
   * IT IS NOT A CACHE AND IT HOLDS NO RECORD DATA — one boolean and one object
   * identity, kept only to answer "is a read outstanding".
   */
  const refetchInFlightRef = useRef(false);
  const settledRef = useRef<{ id: string; value: unknown }>({ id, value: undefined });
  {
    // A different record is a different question; nothing outstanding for the old one
    // may gate the new one.
    if (settledRef.current.id !== id) {
      settledRef.current = { id, value: undefined };
      refetchInFlightRef.current = false;
    }
    // `useFetch` exposes no settle callback, so settlement is observed as what it
    // actually is: a NEW value. Both a fresh bundle object and an error count —
    // `getRecordBundle` returns a fresh object literal every time, so identity is a
    // faithful signal and never a false negative on unchanged content.
    const settledValue =
      bundle.status === 'data' ? bundle.data : bundle.status === 'error' ? bundle.error : undefined;
    if (settledValue !== settledRef.current.value) {
      settledRef.current.value = settledValue;
      refetchInFlightRef.current = false;
    }
    // A SILENT refetch that failed settles nothing visible — `useFetch` keeps the old
    // data on purpose, so the branch above cannot see it. This is the other half.
    if (bundle.refreshFailed) refetchInFlightRef.current = false;
  }

  /**
   * Refetch this screen's bundle because a poller said something moved — unless one is
   * already outstanding. The caller is left no decision to make, which is the point:
   * two call sites cannot implement the rule two ways, which is how the duplicate
   * refetch existed in the first place.
   */
  const reloadFromSignal = () => {
    if (refetchInFlightRef.current) return;
    refetchInFlightRef.current = true;
    liveRefreshRef.current = true;
    bundle.reloadSilent();
  };

  const session = useRecordSession(id, {
    detail,
    // The poller carries a fresh `detail`, and this screen deliberately does not read
    // it: adopting a record's version without the eight reads beside it would leave
    // the fields, evidence and verdicts on screen describing an older revision than
    // the token they would be written back with. The bundle refetch is the adoption.
    onChange: () => reloadFromSignal(),
    onEntitiesChanged: (summary) => {
      // ONE shared gate — `recordChanges.needsCanonicalRefetch`, not a copy of its
      // expression. This exact predicate stood inline here, in the other two
      // read-only screens, and a fourth time in the mount test that was the only
      // thing exercising it; see that function for what drifting cost.
      //
      if (needsCanonicalRefetch(summary)) reloadFromSignal();
    },
  });
  const degraded = session.syncDegraded;

  // P29.4b — after a confirmed proposal write, recompute the shared record state
  // (manual fields, workflow, evidence, export readiness) and refetch the bundle
  // so the manual UI reflects the new value.
  const onAgentRefresh = () => {
    session.refresh();
    bundle.reloadSilent();
  };

  /*
   * The workspace this record was read from is no longer the workspace being
   * addressed. Return the reader to a surface that is real in the scope they are
   * now in, replacing this entry so Back does not walk them into it again.
   *
   * Rendered BEFORE the fetch-state branches so no already-loaded field, banner or
   * heading reaches the DOM in the changed scope, and deliberately WITHOUT issuing
   * a fresh request: a 404 here would be true and useless, and its copy would read
   * as a fault when the only thing that happened is that a temporary workspace was
   * discarded exactly as it said it would be.
   */
  if (scopeChanged) return <Navigate to={ROUTES.experiments} replace />;

  if (bundle.status !== 'data') {
    return (
      <AppShell
        variant="record"
        topBar={<TopBar variant="record" title={LABELS.screenReview} />}
        sidebar={<WorkflowSpine workflow={null} recordId={id} />}
        mainPad="pad"
      >
        <h1 className="sr-only">{LABELS.screenReview}</h1>
        {bundle.status === 'loading' ? (
          <LoadingPanel label="Loading the record from the ISAAC API…" />
        ) : (
          <BackendDown error={bundle.error} onRetry={bundle.reload} />
        )}
      </AppShell>
    );
  }

  return (
    <LoadedWorkbench
      id={id}
      bundle={bundle.data}
      /* ONE indicator for two pollers. Both say the same thing to a reader —
         background updating is not currently working — and `LiveSyncNote` already
         carries that one sentence, so a second notice would be two notices for one
         fact. Which poller degraded is a developer's question, not a scientist's. */
      degraded={degraded || session.feedDegraded}
      activity={session.activity}
      proposalActivity={session.proposalActivity}
      runActivity={session.runActivity}
      agentContext={session.context}
      agentDegraded={session.degraded}
      onManualRefresh={bundle.reload}
      onAgentRefresh={onAgentRefresh}
      // R1b — a silent refetch that failed (the poll-signalled one above, or the
      // post-write one in `onAgentRefresh`) must not be invisible: the reader
      // would be looking at pre-write state believing it is current.
      refreshFailed={bundle.refreshFailed}
    />
  );
}

// The review-screen INTENT pills. Every entry is an INTENTS-native, target-free
// read intent with a repository-native Title Case label (the panel drops any that
// are not in the frozen registry). Read-only: none mutates — the only write is an
// explicit Confirm on a staged proposal, routed through confirmProposal.
const REVIEW_AGENT_PROMPTS: AgentPrompt[] = [
  { intent: 'explain_current_state', label: 'Explain the Current Step' },
  { intent: 'identify_next_missing_field', label: 'Identify the Next Missing Field' },
  { intent: 'explain_step_blocker', label: 'Explain What Is Blocking' },
  { intent: 'show_inferred_candidates', label: 'Show Inferred Candidates' },
  { intent: 'review_evidence_conflicts', label: 'Review Evidence Conflicts' },
  { intent: 'explain_unknown', label: 'Explain Unknown Fields' },
  { intent: 'review_export_readiness', label: 'Review Export Readiness' },
];

/**
 * WHICH INTENTS LEAD ON WHICH WORKSPACE — a REORDERING, and nothing else.
 *
 * NO NEW INTENT IS INVENTED HERE, and none can be: the catalog is a bounded,
 * deterministic BACKEND registry (`CLAUDE.md` §11/§15) and `AssistantPanel`
 * drops any pill naming an intent the frozen registry does not hold. Adding one
 * on the client would produce a control that silently disappears, which is worse
 * than not offering it.
 *
 * NOTHING IS SUBSET AWAY EITHER. Every workspace still offers all seven; only the
 * ORDER changes, so a reader who has learned where a pill lives never finds it
 * missing because of which workspace they happen to be on. The leads below are
 * the intents whose answer is about the content in front of the reader.
 */
const WORKSPACE_PROMPT_LEADS: Record<RecordViewId, readonly AgentPrompt['intent'][]> = {
  // The canonical order already opens with the whole-record questions, which is
  // what a reader on the fields is asking. Nothing to promote.
  fields: [],
  // A reader here is deciding what a run still owes and what the system thinks it
  // could infer.
  runs: ['show_inferred_candidates', 'explain_step_blocker'],
  // A reader here is judging candidates against what the record already holds.
  capture: ['review_evidence_conflicts', 'show_inferred_candidates'],
  /*
   * DELIBERATELY EMPTY, and stated rather than filled in for symmetry. The graph
   * is a view of the record as a whole, so the question a reader arrives with is
   * the one the canonical order already opens with. An entry naming
   * `explain_current_state` would reorder nothing — it is already first — and a
   * lead list that is a no-op reads as a decision when it is not one.
   */
  graph: [],
};

/** The seven pills, led by this workspace's own. Stable and total: every intent
 *  appears exactly once, in canonical order behind the leads. */
export function workspaceAgentPrompts(view: RecordViewId): AgentPrompt[] {
  const leads = WORKSPACE_PROMPT_LEADS[view];
  if (leads.length === 0) return REVIEW_AGENT_PROMPTS;
  const led = leads
    .map((intent) => REVIEW_AGENT_PROMPTS.find((p) => p.intent === intent))
    .filter((p): p is AgentPrompt => p !== undefined);
  return [...led, ...REVIEW_AGENT_PROMPTS.filter((p) => !led.includes(p))];
}

function LoadedWorkbench({
  id,
  bundle,
  degraded,
  activity,
  proposalActivity,
  runActivity,
  agentContext,
  agentDegraded,
  onManualRefresh,
  onAgentRefresh,
  refreshFailed,
}: {
  id: string;
  bundle: RecordBundle;
  degraded: boolean;
  /** The outstanding change-feed summary, or null. Ids and kinds; no content. */
  activity: RecordChangeSummary | null;
  /**
   * THE SAME FEED, ASKED WHETHER A PROPOSAL MOVED — a SECOND prop rather than a reuse
   * of `activity`, and the duplication is the point.
   *
   * `activity` is null once THIS screen's record read has caught up, which is correct
   * for a notice reading "what is on screen was loaded before that". It is wrong for
   * the proposals list, which a record refetch does not touch — so on the ordinary
   * ordering `activity` is null at exactly the moment a colleague's proposal has
   * arrived. See `useRecordSession.proposalActivity`.
   */
  proposalActivity: RecordChangeSummary | null;
  /**
   * THE SAME FEED AGAIN, ASKED WHETHER A RUN MOVED — a THIRD prop rather than a
   * reuse of either of the two above, for the same reason `proposalActivity` is not
   * `activity`: each consumer's "have I caught up?" is answered by a different
   * read, so one summary cannot be null at the right moment for all three.
   *
   * `activity` is null once THIS screen's record bundle has caught up. The runs
   * list is a SEPARATE read with its own version, and a record refetch does not
   * refresh it — so on the ordinary ordering `activity` is null at exactly the
   * moment a colleague's run edit has arrived. See `useRecordSession.runActivity`,
   * which is computed against the run list's own floor for precisely this.
   */
  runActivity: RecordChangeSummary | null;
  agentContext: AgentContext | undefined;
  agentDegraded: boolean;
  onManualRefresh: () => void;
  onAgentRefresh: () => void;
  refreshFailed: boolean;
}) {
  const navigate = useNavigate();
  const { detail, pending, pendingTotal, validate, audit, warnings, evidence, graph } = bundle;

  /*
   * WHICH WORKSPACE IS OPEN — held in the URL, not in component state, so a
   * workspace can be linked, bookmarked and reloaded back into. Anything
   * unrecognised falls back to the field workbench: there is no dead route.
   *
   * ── THE LEGACY RESOLUTION, AND WHY IT IS NOT A REDIRECT ────────────────────
   *
   * `?run=` and `?compare=` are older parameters than the `runs` workspace, and
   * every link minted before this change carries one WITHOUT a `view`. Read
   * literally that URL would open Record Fields with a focused run the reader
   * cannot see — a link that used to work, silently landing somewhere else. So a
   * record URL carrying a run focus or a comparison and NO `view` resolves to
   * `runs`.
   *
   * It resolves rather than redirects. A `Navigate` would rewrite the reader's
   * address, and an address a colleague sent should still read the way it was
   * sent; `ROUTES.recordRun`/`recordCompare` now MINT `view=runs`, so new links
   * are self-describing and the two halves cover each other.
   *
   * AN EXPLICIT `view` ALWAYS WINS, including `view=fields&run=…`, which is a
   * legitimate thing to hold: the run focus survives a trip to another workspace
   * and back precisely because the parameters are independent.
   */
  const [searchParams] = useSearchParams();
  const requestedView = searchParams.get(RECORD_VIEW_PARAM);
  const hasRunAddress =
    (searchParams.get(RECORD_RUN_PARAM) ?? '') !== '' ||
    searchParams.getAll(RECORD_COMPARE_PARAM).length > 0;
  const activeView: RecordViewId = isRecordView(requestedView)
    ? requestedView
    : hasRunAddress
      ? 'runs'
      : 'fields';

  /*
   * THE SWITCH FLUSHES THE RUNS' HELD EDITS. It used to get that for free: the
   * fields panel was a conditional branch, so every `RunCard` unmounted and each
   * card's teardown called `flushPending`. The panels now stay mounted (see the
   * mount refs below), so the property is asked for explicitly instead of being a
   * side effect of destroying the screen. `flushExperiment` is a no-op for a run
   * holding nothing, and never touches a halted or in-flight entry.
   *
   * IT IS THE ONLY THING THIS SCREEN DOES ON A SWITCH. The navigation itself is a
   * real `<Link>` inside `RecordWorkspaceNav`, which copies the current search
   * params and PUSHES — so Back returns to the workspace the reader left, and no
   * other parameter on the address is dropped — which is why this screen no
   * longer writes the parameter itself at all.
   */
  const flushHeldRunEdits = () => flushExperiment(id);

  /*
   * ...AND AGAIN WHENEVER THE WORKSPACE ACTUALLY CHANGES, which is the half the
   * click handler cannot cover.
   *
   * The switch is a PUSH navigation now, so the browser's Back and Forward
   * buttons change `?view=` without any control on this page being pressed —
   * and a reader who edits a run, opens the Graph and presses Back has made the
   * same round trip as one who clicked twice. The click handler fires
   * synchronously on the gesture (which is what the old `selectView` did, and is
   * kept so the flush precedes the URL change); this covers every other way the
   * value can move.
   *
   * DOUBLE-FLUSHING IS FREE AND IS WHY BOTH CAN EXIST: `flushExperiment` is a
   * no-op for a run holding nothing, and never touches a halted or in-flight
   * entry — so on a link click the effect finds the click handler has already
   * sent everything and does nothing at all.
   */
  const lastViewRef = useRef(activeView);
  useEffect(() => {
    if (lastViewRef.current === activeView) return;
    lastViewRef.current = activeView;
    flushExperiment(id);
  }, [activeView, id]);

  /*
   * D1 — A WORKSPACE IS MOUNTED ONCE AND THEN NEVER UNMOUNTED, and that is a
   * data-loss fix rather than a rendering preference.
   *
   * The fields panel used to be one arm of `activeView === 'graph' ? <graph/> :
   * <fields/>`, so a click on the Graph tab DESTROYED every piece of unsaved text
   * inside it, silently and with no confirmation: the transcript box (typed or
   * dictated), the "Capture a note" box, an open note's Edit-wording textarea and
   * dismissal reason, an open asset create/edit form including its Notes and
   * Caption-verbatim textareas, an open run override value, and any run-field text
   * this build could not parse. Splitting one panel into three makes that risk
   * LARGER rather than smaller — there are now three ways to leave a half-typed
   * box instead of one — so all three keep the same treatment.
   *
   * WHY HIDDEN-BUT-MOUNTED RATHER THAN A DRAFT STORE PER BOX. Every one of the
   * boxes above is a different component with a different shape, so a store would
   * be six migrations and six new sources of truth; a panel is one element, and
   * `hidden` is exactly the semantics wanted — the content leaves the layout AND
   * the accessibility tree, so no duplicate heading, control or landmark is
   * exposed while another workspace is open, and axe scans see one at a time.
   *
   * EACH IS LAZY ON FIRST USE, so a deep link to `?view=graph` still costs
   * nothing and a reader who never opens Capture never pays for its three panels'
   * fetches. That is what makes four destinations cheaper than one long page
   * rather than more expensive: the old screen mounted every section on every
   * visit.
   *
   * THE GRAPH STAYS CONDITIONAL, deliberately. `RecordGraphView` documents that it
   * is rebuilt from a fresh read every time the view is opened, which is what makes
   * a stale experiment graph structurally impossible; keeping it mounted would
   * cache it.
   */
  const mounted = useRef<Record<Exclude<RecordViewId, 'graph'>, boolean>>({
    fields: activeView === 'fields',
    runs: activeView === 'runs',
    capture: activeView === 'capture',
  });
  if (activeView !== 'graph') mounted.current[activeView] = true;

  const evidenceByPath = useMemo(
    () => new Map<string, ApiEvidenceEntry>(evidence.map((e) => [e.path, e])),
    [evidence],
  );
  const groups = useMemo(
    () => draftGroupsToFieldGroups(bundle.groups, evidenceByPath),
    [bundle.groups, evidenceByPath],
  );

  // Every group starts collapsed on initial load; user toggles override that.
  const [toggles, setToggles] = useState<Record<string, boolean>>({});
  const isExpanded = (block: string) => toggles[block] ?? false;

  // --- the three signals, each from its own endpoint, each its own segment ---
  // Pre-export, validation is a DRY-RUN and audit has nothing to count — those
  // segments carry the live server result as a note; the reserved PASS/FAIL chip
  // appears only for real (post-export) validation.
  const validationLive = validate.dry_run ? 'pending' : toValidationResult(validate);
  const validationNote = validate.dry_run
    ? `dry-run · ${validate.errors.length} error${validate.errors.length === 1 ? '' : 's'}`
    : undefined;
  const coverageLive = audit.records.length > 0 ? toAuditResult(audit) : 'pending';
  const coverageNote = audit.records.length === 0 ? 'not exported yet' : undefined;
  const advisoryLive = toAdvisoryResult(warnings);

  // The readiness claim comes from `detail.workflow`, never from the pending
  // residual — see `draftPhaseFromWorkflow` above for the measurement. The DOT
  // beside it comes from the same derivation (`draftPhaseDotFromWorkflow`), so the
  // colour cannot claim what the sentence declines to.
  // `exported: true` no longer implies a non-null `record_id`. A record whose runs
  // each export their own official record has NO singular record id — the field is
  // singular and it has several — so this interpolated the literal string and
  // rendered `Exported · null`. Measured. Two lines below, the `filename` prop
  // already guarded with `detail.exported && detail.record_id`; this did not, which
  // is how an unguarded site survived beside a guarded sibling.
  const phase = detail.exported
    ? detail.record_id
      ? `Exported · ${detail.record_id}`
      : 'Exported'
    : pendingTotal > 0
      ? `Draft assembled · ${pendingTotal} fields to confirm`
      : draftPhaseFromWorkflow(detail.workflow);

  // D8 — the right rail is the assistant ONLY (advisory). Deterministic evidence
  // lives inline on every field row (truth, in the main column); the whole-record
  // Evidence Trail affordance now sits beneath the WorkflowSpine (see `sidebar`).
  const rightPanel = (
    <AssistantDrawer railClassName="record-right narrow">
      <AssistantPanel
        {...compose({ context: 'review', bundle })}
        experimentId={id}
        recordRev={detail.rev}
        availability={graph.availability}
        agentContext={agentContext}
        degraded={agentDegraded}
        agentPrompts={workspaceAgentPrompts(activeView)}
        // PR-E — reuses the SAME label `RecordWorkspaceNav`'s own pill row
        // shows for `activeView` (`workspaceRegionName` below does the exact
        // same lookup for the region's aria-label); the panel renders
        // "You are on <label>." beneath its header and re-renders it on every
        // workspace switch without remounting or resetting anything else.
        workspaceContext={RECORD_WORKSPACES.find((w) => w.id === activeView)?.label}
        onRefresh={onAgentRefresh}
      />
    </AssistantDrawer>
  );

  // D8 — the whole-record Evidence Trail affordance, moved out of the (removed)
  // right-rail evidence panel to sit directly beneath the workflow. It reuses the
  // EXISTING /evidence route (ROUTES.evidence) — no new route or evidence system.
  const sidebar = (
    <div className="record-aside">
      <WorkflowSpine workflow={detail.workflow} recordId={id} />
      {/*
        THE FOUR WORKSPACES SIT BETWEEN THE SPINE AND THE EVIDENCE TRAIL, and both
        neighbours are deliberate.

        BELOW THE SPINE, because the spine answers "where am I in the pipeline?"
        and this answers "where can I go on this record?" — the second question
        only arises once the first is oriented. The spine is untouched by this:
        still server-derived, still gated, still the only list here whose entries
        can be blocked.

        ABOVE THE EVIDENCE TRAIL, and NOT merged into it as a fifth peer. That link
        leaves this screen for a separately-routed, spine-gated surface; these four
        stay on it. Presenting a route change as a fifth workspace would make one of
        the five behave unlike the other four with nothing on screen saying so.
      */}
      <RecordWorkspaceNav active={activeView} onNavigate={flushHeldRunEdits} />
      <button
        type="button"
        className="evidence-trail-link"
        data-tutorial-anchor={TUTORIAL_ANCHORS.recordEvidenceTrail}
        onClick={() => navigate(ROUTES.evidence(id))}
      >
        <ExternalLink size={14} strokeWidth={2} aria-hidden="true" />
        <span className="evidence-trail-link-label">{LABELS.evidenceTrail}</span>
        <span className="evidence-trail-link-count">
          {evidence.length} {evidence.length === 1 ? 'entry' : 'entries'}
        </span>
      </button>
    </div>
  );

  return (
    <AppShell
      variant="record"
      topBar={
        <TopBar
          variant="record"
          title={stripLifecycleSuffix(detail.title)}
          filename={
            detail.exported && detail.record_id ? `${detail.record_id}.json` : `${detail.id}`
          }
          stateChip={detail.exported ? 'exported' : 'draft'}
        />
      }
      sidebar={sidebar}
      rightPanel={rightPanel}
      statusBar={
        <StatusBar
          phase={phase}
          phaseDot={
            pendingTotal > 0
              ? 'attention'
              : detail.exported
                ? 'idle'
                : draftPhaseDotFromWorkflow(detail.workflow)
          }
          validation={validationLive}
          coverage={coverageLive}
          advisory={advisoryLive}
          validationPendingNote={validationNote}
          coveragePendingNote={coverageNote}
        />
      }
      mainPad="pad"
    >
      <h1 className="sr-only">{LABELS.screenReview}</h1>
      <RecordActivityNote activity={activity} onRefresh={onManualRefresh} />
      <LiveSyncNote
        degraded={degraded}
        refreshFailed={refreshFailed}
        onRefresh={onManualRefresh}
      />
      <WorkflowProgressBanner
        workflow={detail.workflow}
        recordId={id}
        pendingCount={detail.pending_count}
        excludeSteps={['complete_metadata']}
      />

      {/*
        ── SHELL LEVEL: VISIBLE FROM EVERY WORKSPACE ─────────────────────────
        The needs-you banner used to live INSIDE the fields panel, so opening the
        graph hid the record's own count of outstanding confirmations. It is a
        cross-cutting alert — it mixes run-owned and record-owned blockers and its
        primary action leaves this screen entirely — so no single workspace owns
        it, and hiding it behind one would be the anti-goal this reorganisation
        exists to avoid. It sits below the progress banner and above the workspace
        content, so "how many confirmations remain" is the first content-bearing
        thing on the page whichever workspace is open.
      */}
      <NeedsYouBanner
        activeView={activeView}
        pending={pending}
        pendingTotal={pendingTotal}
        onReviewAnswer={() => navigate(ROUTES.complete(id))}
      />

      {activeView === 'graph' && (
        <section
          id={workspacePanelId('graph')}
          className="record-view-panel"
          aria-label={workspaceRegionName('graph')}
          tabIndex={-1}
        >
          <RecordGraphView id={id} />
        </section>
      )}

      {/* ── RECORD FIELDS — what this record IS ──────────────────────────── */}
      {mounted.current.fields && (
        <section
          id={workspacePanelId('fields')}
          className="record-view-panel"
          aria-label={workspaceRegionName('fields')}
          tabIndex={-1}
          /* Hidden, not removed — see the comment on `mounted`. `hidden` takes
             the whole panel out of the layout and out of the accessibility tree,
             so nothing in it is announced, focusable or scanned while another
             workspace is up. */
          hidden={activeView !== 'fields'}
        >
          {/*
            THE DRAFT BLOCKS ARE THE CAPTURE SURFACE, AND UNTIL RECENTLY A CREATED
            RECORD HAD NONE. Measured over HTTP: `GET /draft` on a record created
            through `POST /api/experiments` returned `{"groups": []}` — zero rows,
            zero groups — so these four sections rendered nothing at all and a
            scientist had no way to learn that a record holds a sample, a facility or
            a technique. The server now returns the group skeleton, so the same call
            returns 26 rows in the same 4 groups a seeded record has.

            `capture` IS WHAT MAKES ONE OF THOSE ROWS WRITABLE HERE, and it is granted
            only on this screen because only this screen holds the record's current
            version token. `FieldCaptureControl` decides per row whether a control may
            be offered at all — two of the 26 paths have a record-level route, and the
            rest say where their value is entered rather than offering a box that
            would be refused.

            `onAgentRefresh` AND NOT `bundle.reload`, for the reason
            `RenameExperimentPanel` below records: the loading variant unmounts this
            entire body, which would destroy the control mid-announcement and drop
            focus to `<body>`.
          */}
          {groups.map((group) => (
            <FieldGroup
              key={group.block}
              group={group}
              expanded={isExpanded(group.block)}
              capture={{
                experimentId: id,
                version: detail.version,
                onSaved: onAgentRefresh,
              }}
              onToggle={() =>
                setToggles((prev) => ({
                  ...prev,
                  [group.block]: !isExpanded(group.block),
                }))
              }
            />
          ))}

          {/*
            ── THE RECORD IDENTITY GROUP ──────────────────────────────────────
            Four sections about the WHOLE record — what it is called, what it is,
            what it holds, and what it points at — rather than about the science
            inside it.

            THE EYEBROW IS THE WHOLE OF THE CHANGE, and it closes a MEASURED
            finding rather than decorating one. The code's own comments have long
            argued that "science" and "reference material about the whole record"
            are different categories that belong in that order — but eight
            structurally different `.fg-header` rows shared one visual idiom with no
            grouping cue, so a reader could not tell where the science stopped
            without reading every label. The eyebrow is the same small-caps idiom
            `WorkflowSpine` already uses for `Workflow`; no new component, no new
            visual language, and nothing about the four panels themselves changes.

            THEY ARE MOUNTED ONCE, HERE, AND NEVER INSIDE A RUN, because all four are
            record-level and that is measured rather than assumed: `links` is on the
            fail-closed "not overridable" list in
            `routes.EXPERIMENT_OVERRIDABLE_ADDRESSES` and `workspace.py` records it as
            neither inherited nor copied into a run's export draft; the classification
            trio lives in the draft's `meta`, which the same module calls "the same for
            every run by construction"; and `timestamps.created_utc` is on the
            unclassified list too, so it is not inherited either
            (`docs/run-scope-decision-packet.md` §2–§3).

            WHY THEY CLOSE THE COLUMN RATHER THAN OPEN IT. The blocks above are the
            science the reader came for; what a record IS, and what it points at, is
            reference material about the whole of it, so it reads as a footer rather
            than as a preamble. Both are collapsed on arrival like every block above
            them, so the cost of being wrong about that is one line each.

            A SECOND, SMALLER REASON, STATED RATHER THAN HIDDEN: four existing specs
            address "the first `.fg-header` on the screen" as a way of reaching the
            first DRAFT block (`live-screens`, `record-session`,
            `p33-hqa-6-heading-and-header`). Mounting these sections above the blocks
            would silently re-point that selector at a section those specs know
            nothing about.
          */}
          <div className="record-identity">
            <div className="record-identity-eyebrow eyebrow">
              {LABELS.recordIdentityEyebrow}
            </div>
            {/* THE RENAME. `onAgentRefresh` AND NOT `onManualRefresh`, deliberately.
                The second is `bundle.reload`, which flips this screen back to its
                loading state — and `RecordWorkbench` unmounts the entire loaded body
                while the fetch is not in `data`, so a save would destroy this panel
                mid-announcement and drop focus to `<body>`. The first is the silent
                refetch plus the record-session recompute, which is what a version
                change actually calls for. */}
            <RenameExperimentPanel detail={detail} onSaved={onAgentRefresh} />
            {/*
              THE RECORD DESCRIPTION — the capture surface for what the record IS: its
              technique and domain, the facility it was measured at, the sample, the
              contributors and the tags.

              WHY IT IS HERE AND NOT INSIDE A RUN. Every value it writes is
              EXPERIMENT-level by `workspace.field_level`, so a run inherits it and does
              not own it. Before this panel existed, the only route that accepted twelve
              of them was a RUN's override — which records a divergence from a value the
              record does not hold — so the product could finish a record it could not
              describe.

              IT SELF-FETCHES AND CARRIES ITS OWN VERSION TOKEN, the discipline
              `UnmappedNotesPanel` already follows: it re-reads the record after each
              write rather than reading `bundle`, because the next save partitions its
              keys on what the SERVER says the record holds, and partitioning on what
              this screen last believed is how a second save gets routed to the wrong
              operation.
            */}
            <RecordDescriptionPanel experimentId={id} />
            <RecordInfoPanel detail={detail} groups={bundle.groups} artifacts={bundle.artifacts} />
            <RecordLinksPanel artifacts={bundle.artifacts} />
          </div>

          {/*
            ASSET REFERENCES CLOSE THIS WORKSPACE, and the placement is an ORCHESTRATOR
            RULING recorded here rather than a preference: an asset is a RECORD-level
            entity that may optionally cite a run, so it belongs with the record rather
            than with the runs. The IA brief argued the other way (§3, "assets are
            run-level for export") and the ruling overrides it; the brief's own
            Assumptions §9 already named this a judgment call that could go either way.

            COLLAPSED ON ARRIVAL, WITH ITS OWN COUNT, so the workspace's footer is one
            line rather than a browser. The count comes from the panel's own loaded
            list and is absent until that read resolves — never optimistic, never a
            number this screen guessed.
          */}
          <AssetReferencesPanel experimentId={id} collapsedByDefault />
        </section>
      )}

      {/* ── RUNS — the measurements this record holds ────────────────────── */}
      {mounted.current.runs && (
        <section
          id={workspacePanelId('runs')}
          className="record-view-panel"
          aria-label={workspaceRegionName('runs')}
          tabIndex={-1}
          hidden={activeView !== 'runs'}
        >
          {/*
            ~~THE RUNS SECTION SITS HERE — on this screen, inside the field workbench,
            ABOVE the draft blocks … A section, not a third view tab. `Record Fields` /
            `Graph` are two renderings of the same content; runs are additional
            content, and putting them behind a tab would hide from a reader on the
            fields view that this experiment has runs at all.~~

            THE THIRD REASON IS WITHDRAWN, AND IT IS STRUCK RATHER THAN DELETED because
            it was a good argument that a measurement overtook. It rested on the runs
            being INVISIBLE behind a tab — and that was true of a `.section-tabs` bar at
            the top of the main column, which named two renderings and said nothing about
            what else the record held. It is not true of a permanent, always-visible
            sidebar list that names `Runs` on every workspace, in any record state,
            beside a count of nothing and a gate of nothing. A reader on Record Fields
            can see that this record has a Runs workspace without scrolling at all,
            which the 3,116px single column could not claim.

            THE FIRST TWO REASONS ARE UNCHANGED AND STILL BINDING: this is the
            experiment screen (`ExperimentsHome` is the queue and knows nothing about
            any one record), and adding a run is an ACTION that goes first — which is
            why `RunsSection` opens this workspace rather than sitting under the
            review below it.
          */}
          <RunsSection
            experimentId={id}
            /* THE FAST PATH: a run-scoped feed summary. Ids and a rev, never content. */
            activity={runActivity}
            /*
             * THE COMPLETENESS PATH: the record bundle's own version token, which moves
             * for the two things the feed structurally cannot report — a run REMOVAL
             * (no `run` entry moves, only the record's own) and a generation change.
             * `RunsSection`'s comments on both props carry the full argument.
             */
            recordVersion={detail.version}
          />

          {/*
            VALIDATE & REVIEW SITS DIRECTLY BELOW THE RUNS, and the placement is the
            argument for it: its findings are addressed BY RUN, and the runs a reader
            is being sent back to are the section immediately above. That adjacency is
            the reason it moved here with them rather than staying beside the fields.

            IT FETCHES NOTHING ON MOUNT — not one request until the button is pressed
            (see the component header on why: `docs/run-scale-measurements.md` made a
            record's runs a payload cost, and N eager per-run checks would be the same
            mistake in request form). So mounting it here costs this workspace nothing
            on load.

            IT IS NOT `RunFindings` MOVED. That component is the PASSIVE read-out on
            the export screen, rendering verdicts a bundle already fetched; this is the
            ACTION, on the screen where the fields and runs are edited, and it reaches
            two channels the export bundle never carries — the run's open blocking
            questions and its no-guessing draft report. Both read the same server
            fields and share `runFindingState` and `FindingList` rather than keeping
            two opinions about them.
          */}
          <ValidateReview experimentId={id} />
        </section>
      )}

      {/* ── CAPTURE & PROPOSALS — what was said, and what it might mean ──── */}
      {mounted.current.capture && (
        <section
          id={workspacePanelId('capture')}
          className="record-view-panel"
          aria-label={workspaceRegionName('capture')}
          tabIndex={-1}
          hidden={activeView !== 'capture'}
        >
          {/*
            CAPTURE → NOTE → PROPOSAL, IN THAT ORDER, AND THE ORDER IS THE WHOLE OF THE
            ARGUMENT — the same three adjacency arguments the single column already
            made, now with nothing between them.

            TRANSCRIPT CAPTURE SITS DIRECTLY ABOVE THE NOTES IT PRODUCES. Finalizing a
            transcript stores EVERY segment of it as an unmapped note, so the panel that
            creates them and the queue they land in are neighbours: a reader who
            finalizes sees, without scrolling past anything else, that their words were
            kept. ABOVE rather than below, because capture precedes triage; the reverse
            order shows a reader the queue before the thing that fills it.

            INGESTION PROPOSALS SIT DIRECTLY BELOW THE NOTES THEY CITE. Every proposal
            names a note — `note_id` is required, and it is what keeps the verbatim
            words safe from every review outcome — so the queue of suggestions reads next
            to the content they were read out of. Reviewing a proposal and triaging the
            note it came from are two decisions about the same sentence.

            ~~A section, not a tab, because behind a tab a reader would never learn
            that this record can hold captured content at all, and an empty tab is
            exactly the surface a person stops opening.~~ — WITHDRAWN for the reason the
            Runs workspace records: the sidebar names `Capture & Proposals` permanently,
            on every workspace, so the existence of the pipeline is visible without
            opening it. What the argument was PROTECTING is unchanged and still holds —
            this build has no automatic producer for proposals, so the ordinary state of
            that panel is empty, and its empty state must keep saying that the absence is
            a fact about the build rather than a failed read.

            `proposalActivity` IS THE CHANGE-FEED SUMMARY THIS SCREEN ALREADY HOLDS,
            asked whether a PROPOSAL moved, threaded in so a proposal that moves
            elsewhere refreshes this list — SILENTLY, so nothing being typed into an open
            editor is destroyed. `activity` would be WRONG here and was, measured in a
            browser: it is null once the RECORD read has caught up, and a proposal act
            moves the record's own rev, so whichever poller resolved first decided
            whether this list ever refreshed. See `recordChanges.ChangeFloors` and
            `apps/web/e2e/mutation/proposals.spec.ts`.
          */}
          <TranscriptCapturePanel experimentId={id} />
          <UnmappedNotesPanel experimentId={id} />
          <IngestionProposalsPanel experimentId={id} activity={proposalActivity} />
        </section>
      )}
    </AppShell>
  );
}

// --- the record's four WORKSPACES -----------------------------------------
//
// ~~The field workbench and the experiment-scoped graph are two views of the SAME
// record, so they are local page tabs on this screen…~~ — RETIRED. That was true
// of two RENDERINGS of one record; it stopped being true when the record's runs
// and its capture pipeline became destinations of their own, which are different
// CONTENT rather than a second drawing of the same content. The switcher is now
// `RecordWorkspaceNav` in the record's own sidebar: ONE place a reader looks for
// "where can I go from here", instead of a sidebar answering it for the pipeline
// and a tab bar answering it for the content.
//
// The `?view=` deep-link mechanism is UNCHANGED — same parameter, same fallback,
// same `URLSearchParams`-copying discipline. Only the control moved, and gained
// two members.
//
// The graph is still mounted HERE and not on a screen a scientist has to go
// looking for: this is the surface they are already on when working on a record.

const workspacePanelId = (id: RecordViewId) => `record-workspace-${id}`;

/**
 * THE ACCESSIBLE NAME OF A WORKSPACE PANEL, and why it is not just the label.
 *
 * Each panel is a `<section>` with an accessible name, so it is a landmark a
 * screen-reader user can jump to — but "Runs" was ALREADY a landmark on this
 * screen: `RunsSection` renders its own named `<section>`. Two regions with the
 * same role and the same name is axe's `landmark-unique`, and it fired on
 * `record-runs` at every viewport (measured, darwin, 7 cells). Naming the panel
 * "<label> workspace" is the fix, and it is a better name rather than a
 * disambiguating suffix: the sidebar list these panels belong to is headed
 * `Workspaces`, so the landmark list now reads the way the navigation does.
 */
const workspaceRegionName = (view: RecordViewId) =>
  `${RECORD_WORKSPACES.find((w) => w.id === view)?.label ?? view} workspace`;

/**
 * HOW MANY OWNER GROUPS THE NEEDS-YOU BANNER LISTS.
 *
 * THREE, and it is a judgement rather than a measurement — but the thing it
 * replaces was measured. The banner listed up to ten INDIVIDUAL questions, and on
 * the seeded two-run record that produced six rows of which four were
 * byte-identical duplicates: "Reduced Spectrum", "What is the QC verdict…",
 * "Scientific Descriptor", then the same three again, because Run A and Run B
 * each own the same three kinds and nothing in the row said which run it belonged
 * to. A reader could not resolve the ambiguity without leaving the page.
 *
 * Grouping by owner fixes the ambiguity and shortens the banner at the same time:
 * one line per owner, the owner named, and three lines is enough to see what KIND
 * of thing is being asked without the banner becoming the page.
 */
export const NEEDSYOU_VISIBLE_GROUPS = 3;

/*
 * THE LABEL BUDGET IS `NEEDSYOU_VISIBLE`, SPENT ACROSS THE SHOWN GROUPS — not a
 * per-group cap, and the difference is the whole reason this compaction does not
 * cost a reader information.
 *
 * A per-group cap of three would have shown a reader with FIVE record-level
 * questions only three of them, on a banner that has always shown up to ten. The
 * budget instead bounds the same thing the old list bounded — how many questions
 * are NAMED — and the grouping bounds how many LINES they are named on. Five
 * record-level questions are still all five, on one line instead of five; a
 * thousand runs are three lines instead of three thousand.
 */

/** What the record itself owns, as opposed to any one run. */
const RECORD_LEVEL_OWNER = 'This record';

interface PendingGroup {
  /** `null` for the record-level group; a run id otherwise. Used only as a key. */
  runId: string | null;
  owner: string;
  /** One entry per open question, in the server's order. `pendingSummary`'s shape. */
  questions: { label: string; locator: string | null }[];
}

/**
 * The fetched pending window, grouped by the OWNER the server named.
 *
 * RECORD-LEVEL FIRST, THEN RUNS IN THE ORDER THE SERVER SENT THEM. Nothing is
 * sorted, re-derived or inferred: `run_id`/`run_label` are fields on the wire
 * (`ApiPendingItem`), and an item without a `run_id` is record-owned by the
 * server's own account of it. A run that carries an id and no label is named by
 * its id rather than by a sentence this screen invented.
 *
 * IT GROUPS WHAT WAS FETCHED, WHICH IS NOT ALWAYS THE WHOLE RECORD. A live
 * refresh asks for `LIVE_PENDING_WINDOW` questions, so these groups describe a
 * PREFIX. That is why nothing here is presented as a total: every count the
 * banner claims comes from `pendingTotal`, and the overflow sentence states the
 * remainder in words. See `LIVE_PENDING_WINDOW`'s own note.
 */
export function groupPending(pending: ApiPendingItem[]): PendingGroup[] {
  const groups: PendingGroup[] = [];
  const byKey = new Map<string, PendingGroup>();
  for (const item of pending) {
    const runId = item.run_id ?? null;
    const key = runId ?? '';
    let group = byKey.get(key);
    if (group === undefined) {
      group = {
        runId,
        owner: runId === null ? RECORD_LEVEL_OWNER : (item.run_label ?? runId),
        questions: [],
      };
      byKey.set(key, group);
      groups.push(group);
    }
    group.questions.push(pendingSummary(item));
  }
  // The record's own questions lead: they are the ones no run can answer, and a
  // reader scanning for "what do I owe as the author of this record" should not
  // have to pass a run's list first. `sort` is stable in every engine this ships
  // to, so the runs keep the server's order behind it.
  return [...groups].sort((a, b) => Number(a.runId !== null) - Number(b.runId !== null));
}

/**
 * "N Fields Need Your Confirmation" — the record's outstanding questions, grouped
 * by who owns them, at shell level so it is visible from every workspace.
 *
 * ── WHAT IS BOUNDED, AND WHAT IS NEVER BOUNDED ──────────────────────────────
 *
 * THE COUNT IN THE TITLE IS THE FULL COUNT (`pendingTotal`, the server's
 * `pending_page.total`, which speaks for the whole record), and the overflow line
 * states the remainder explicitly. What must never happen is a truncated list that
 * reads as complete — a scientist who counted three lines and concluded three
 * questions remain would be wrong by however many the window did not carry.
 *
 * THE LIST IS BOUNDED THREE TIMES OVER, and the reason is measured: at 1,000 runs
 * this list was 3,002 items and ~15,000 of the screen's 16,134 DOM nodes, while
 * every run card together was 50. A banner is the wrong place to render three
 * thousand questions in any case — a reader cannot act on item 2,000 from here,
 * and the control that takes them somewhere they can is the button beside it.
 */
function NeedsYouBanner({
  activeView,
  pending,
  pendingTotal,
  onReviewAnswer,
}: {
  /** Which workspace is open. Decides whether the QUESTIONS are listed — never
   *  whether the banner appears, and never what the count says. */
  activeView: RecordViewId;
  pending: ApiPendingItem[];
  pendingTotal: number;
  onReviewAnswer: () => void;
}) {
  if (pendingTotal <= 0) return null;

  /*
   * ── THE LIST IS ON RECORD FIELDS; THE BANNER IS EVERYWHERE. ────────────────
   *
   * MEASURED: shell-level and fully expanded, this banner owned the top of every
   * workspace — the first section of the open workspace began at y=789 at
   * 1024x768 on the six-question seed, i.e. the banner had taken the whole
   * viewport before the reader saw any of the thing they navigated to. That is
   * the "content pushed far down the page" cost this whole reorganisation exists
   * to remove, reintroduced by the fix for a different problem.
   *
   * SO THE QUESTIONS FOLD, NOT THE BANNER. On Runs, Capture & Proposals and Graph
   * it renders the icon, the count, the one sentence that says a refusal is
   * expected, and the action — which is everything a reader needs in order to
   * decide whether to go and answer them. The itemised list is on Record Fields,
   * which is where the fields those questions are about live.
   *
   * NOT A `<details>`, deliberately. A disclosure would put a control on every
   * workspace whose only outcome is to re-create the problem measured above, and
   * would imply the reader is missing something — they are not: the COUNT is the
   * whole claim, and it is the same number in both forms.
   *
   * THE COUNT NEVER FOLDS. The title reads `pendingTotal`, the server's own
   * `pending_page.total`, in both forms — so a bounded live refresh, a windowed
   * read, or a page of ten out of thirty cannot make this banner understate what
   * the record owes.
   */
  const listed = activeView === 'fields';
  /* THE LINES, AND WHAT EACH ONE IS ALLOWED TO NAME. The budget is spent in order,
     so the record's own questions are never crowded out by a run's; a group that
     the budget cannot finish says how many of ITS OWN it did not name, which is a
     different sentence from the overflow line below and must stay one.

     SKIPPED ENTIRELY WHEN NOTHING IS LISTED, which is not micro-optimisation: on
     first paint `pending` is UNBOUNDED, and a 1,000-run record carries ~3,000
     entries — grouping them on every render of a workspace that renders none of
     them would be the scale cost this screen has already been caught paying once. */
  const shownGroups: { group: PendingGroup; questions: PendingGroup['questions'] }[] = [];
  let budget = NEEDSYOU_VISIBLE;
  if (listed) {
    for (const group of groupPending(pending)) {
      if (shownGroups.length >= NEEDSYOU_VISIBLE_GROUPS || budget <= 0) break;
      const questions = group.questions.slice(0, budget);
      budget -= questions.length;
      shownGroups.push({ group, questions });
    }
  }
  /* How many individual questions the rendered lines actually NAME. Derived from
     what is rendered rather than from `pending.length`, so the overflow sentence
     below cannot claim to have shown a question it truncated. */
  const named = shownGroups.reduce((n, s) => n + s.questions.length, 0);

  return (
    <div className="needsyou-banner" role="note" data-tutorial-anchor={TUTORIAL_ANCHORS.recordPending}>
      <CircleAlert className="needsyou-icon" size={20} strokeWidth={2.2} aria-hidden="true" />
      <div className="needsyou-body">
        <div className="needsyou-title">{pendingTotal} Fields Need Your Confirmation</div>
        <p className="needsyou-text">
          These are values the system refuses to guess. Confirm each before this record can
          export — expected, not a failure.
        </p>
        {listed && (
        <>
        {/*
          ONE ROW PER OWNER, and the questions nested inside it.
          `groupPending`'s note explains what the grouping fixes; what the NESTING
          preserves is the thing the flat list already got right and that a
          "compact" rewrite would quietly have thrown away — each question keeps its
          concise label as the primary text and its technical locator exactly once as
          a demoted mono token, which is how a reader can tell WHICH asset's hash is
          being asked for. Compaction comes from the grouping and the bound, never
          from deleting the locator.
        */}
        <ul className="needsyou-list">
          {shownGroups.map(({ group, questions }) => {
            const unnamed = group.questions.length - questions.length;
            return (
              /* KEYED ON THE OWNER, which is what the row is about. A run-owned
                 question's `id` is its KIND — `series`, `qc`, `descriptor` — so a
                 record with two runs used to produce two `<li key="series">`. */
              <li key={group.runId ?? ''} className="needsyou-group">
                <span className="needsyou-owner">{group.owner}</span>
                <ul className="needsyou-questions">
                  {questions.map((q, i) => (
                    <li key={`${q.label}-${i}`} className="needsyou-item">
                      <span className="needsyou-q">{q.label}</span>
                      {q.locator && <span className="needsyou-about mono">{q.locator}</span>}
                    </li>
                  ))}
                  {/*
                    THIS NUMBER IS EXACT, AND THAT IS STRUCTURAL RATHER THAN LUCKY.
                    It counts the group's questions IN THE FETCHED WINDOW that the
                    budget did not reach — which would understate the record if the
                    window were ever a prefix at the moment a group was truncated.
                    It cannot be: the budget IS `NEEDSYOU_VISIBLE`, and a windowed
                    read asks for `LIVE_PENDING_WINDOW`, which is the same number by
                    construction (see its own note, pinned by
                    `__tests__/live-refresh-request-graph.test.tsx`). So a windowed
                    read delivers at most as many questions as the budget can name
                    and this branch never renders; truncation happens only on the
                    UNBOUNDED first paint, where the window is the whole record.
                  */}
                  {unnamed > 0 && (
                    <li className="needsyou-item-more">and {unnamed} more on this one</li>
                  )}
                </ul>
              </li>
            );
          })}
        </ul>
        {pendingTotal > named && (
          /* NOT `aria-hidden`, and not a "…". A screen-reader user who has just
             been told the count in the title needs to know this list is a prefix
             of it, in words.

             INSIDE THE `listed` BRANCH, because it is a statement ABOUT THE LIST.
             With no list there is no prefix to qualify, and the title already
             carries the full count — printing "showing the first 3 of 30" beside
             nothing would be the only false sentence this banner could produce. */
          <p className="needsyou-more">
            Showing the first {named} of {pendingTotal}. {pendingTotal - named} more are
            waiting — open {LABELS.actionReviewAnswer} to work through all of them.
          </p>
        )}
        </>
        )}
      </div>
      <button type="button" className="btn btn-primary needsyou-action" onClick={onReviewAnswer}>
        {LABELS.actionReviewAnswer} →
      </button>
    </div>
  );
}

/**
 * The graph's own data load.
 *
 * Deliberately a SEPARATE fetch from the record bundle, and deliberately lazy:
 * this component only mounts when the Graph view is selected, so a reader who
 * never opens it never pays for it. It is also deliberately NOT cached — the
 * graph is rebuilt from a fresh read every time the view is opened, which is
 * what makes a stale experiment graph structurally impossible.
 *
 * The scope pair is what enforces tutorial isolation at the model boundary: the
 * scope the bundle was READ in is captured at mount, and compared against the
 * scope the surface is addressing now. They disagree only when a worked-example
 * session was entered or left while this view was open — at which point the
 * records this graph describes no longer exist in the workspace being
 * addressed, and the model refuses rather than drawing them.
 */
function RecordGraphView({ id }: { id: string }) {
  const bundle = useFetch(() => api.getExperimentGraphBundle(id), [id]);
  const currentScope = useWorkspaceScope();
  const readInScope = useRef(currentScope);

  if (bundle.status === 'loading') {
    return <LoadingPanel label="Loading this experiment's graph from the ISAAC API…" />;
  }
  if (bundle.status !== 'data') {
    return <BackendDown error={bundle.error} onRetry={bundle.reload} />;
  }
  return (
    <ExperimentGraphPanel
      bundle={bundle.data}
      readInScope={readInScope.current}
      currentScope={currentScope}
    />
  );
}
